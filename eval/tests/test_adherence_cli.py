"""The adherence console entry: argument parsing, the dry run, the report option, and the paid loop.

The paid loop runs over a real copy of this repository with a scripted stand-in for the
one function that starts ``claude`` (``session_launch.run_session``); no process is ever started.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import (
    cli,
    model,
    results,
    session_launch,
    session_loop,
    tasks,
    transcript,
)
from praxion_evals.adherence.arms import NO_MARKER_REPLY, PROOF_LABEL
from praxion_evals.adherence.checks_common import C3, GoldenVerdicts
from praxion_evals.adherence.infra_stop import COUNTING_KINDS
from praxion_evals.adherence.model import (
    CheckErrored,
    Errored,
    Failed,
    Measured,
    Passed,
    allowance_key,
)
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import JudgeVerdict
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.conftest import unswitched

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = "researcher"
SMALL_RUN = [
    "--required-pairs",
    "1",
    "--pair-slack",
    "0",
    "--no-judge",
    "--session-budget-usd",
    "1",
]
FULL_TOKENS, LEAN_TOKENS = 5000, 1000
SESSION_ID, AGENT_ID = "scripted-session", "a0123456789abcdef"
DELIVERED = {
    "type": "hook_additional_context",
    "hookEvent": "SubagentStart",
    "content": ["[praxion 0a1b2c3d #1]\n\nThe kernel."],
}
KERNEL_TRANSCRIPT = json.dumps({"type": "attachment", "attachment": DELIVERED}) + "\n"


# ---------------------------------------------------------------------------
# argv
# ---------------------------------------------------------------------------


def test_the_defaults_are_the_documented_ones() -> None:
    config = cli.parse_config(["--role", ROLE])

    assert (config.roles, config.arms) == ((ROLE,), ("full", "lean"))
    assert (config.seed, config.margin_pp, config.required_pairs) == (7, 10.0, 20)
    assert (config.pair_slack, config.confidence, config.judging) == (4, 0.95, True)
    assert (config.calibration, config.calibration_run, config.dry_run) == (False, None, False)


def test_roles_and_arms_are_deduplicated_and_arms_keep_the_launch_order() -> None:
    config = cli.parse_config(
        [
            "--role",
            "verifier",
            "--role",
            ROLE,
            "--role",
            "verifier",
            "--arm",
            "lean",
            "--arm",
            "full",
        ]
    )

    assert config.roles == ("verifier", ROLE)
    assert config.arms == ("full", "lean")


@pytest.mark.parametrize(("pairs", "slack"), [(20, 4), (50, 10), (3, 4)])
def test_the_default_slack_is_a_fifth_of_the_target_and_at_least_four(
    pairs: int, slack: int
) -> None:
    config = cli.parse_config(["--role", ROLE, "--required-pairs", str(pairs)])

    assert config.pair_slack == slack


def test_a_declared_slack_overrides_the_default() -> None:
    assert cli.parse_config(["--role", ROLE, "--pair-slack", "0"]).pair_slack == 0


def test_a_calibration_run_measures_the_full_arm_only() -> None:
    config = cli.parse_config(["--role", ROLE, "--calibration"])

    assert config.arms == ("full",)
    assert config.calibration


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--role", ROLE, "--margin-pp", "120"],
        ["--role", ROLE, "--confidence", "1.5"],
        ["--role", ROLE, "--max-total-usd", "0"],
        ["--role", ROLE, "--required-pairs", "0"],
        ["--role", ROLE, "--max-tasks", "0"],
        ["--role", ROLE, "--calibration", "--arm", "lean"],
        ["--role", ROLE, "--calibration", "--calibration-run", "earlier.json"],
        ["--role", ROLE, "--judge-golden", "--no-judge"],
        ["--role", "no-such-role"],
    ],
)
def test_a_usage_error_exits_with_two(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.parse_config(argv)

    assert raised.value.code == 2


def test_the_report_option_needs_no_role() -> None:
    config = cli.parse_config(["--report", "results.json"])

    assert config.report == Path("results.json")
    assert config.roles == ()


# ---------------------------------------------------------------------------
# The dry run and the start-of-run refusals launch nothing
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def unswitched_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every run here sees the checkout with the role not yet switched (see conftest.unswitched)."""
    materialize = session_loop.materialize_path

    def materialize_unswitched(source: Path, dest: Path, *args, **kwargs):
        return unswitched(materialize(source, dest, *args, **kwargs), ROLE)

    monkeypatch.setattr(session_loop, "materialize_path", materialize_unswitched)


@pytest.fixture
def no_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(spec: SessionSpec, env: object) -> SessionRun:
        raise AssertionError("a session was started")

    monkeypatch.setattr(session_launch, "run_session", refuse)


def _dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path, *options: str) -> list[dict]:
    argv = [str(REPO_ROOT), "--output", str(tmp_path / "out.json"), "--dry-run", *options]
    assert cli.main(argv) == 0
    assert not (tmp_path / "out.json").exists()
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_lists_every_task_of_every_named_arm(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = _dry_run(capsys, tmp_path, "--role", ROLE)

    assert sorted((line["task_id"], line["arm"]) for line in lines) == sorted(
        (task, arm) for task in tasks.task_ids(ROLE, cli.DEFAULT_SEED) for arm in ("full", "lean")
    )


@pytest.mark.usefixtures("no_launch")
@pytest.mark.usefixtures("no_launch")
def test_a_token_file_puts_the_token_in_every_session_and_takes_the_api_key_out(
    capsys, tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-key-for-the-judge")
    token_file = tmp_path / "session-token"
    token_file.write_text("sk-ant-oat01-example\n")

    lines = _dry_run(
        capsys,
        tmp_path,
        "--role",
        ROLE,
        "--max-tasks",
        "1",
        "--session-oauth-token-file",
        str(token_file),
    )

    assert lines, "the dry run plans sessions"
    for line in lines:
        assert "CLAUDE_CODE_OAUTH_TOKEN" in line["env_names"]
        assert "ANTHROPIC_API_KEY" not in line["env_names"]
    assert "sk-ant-oat01" not in capsys.readouterr().out  # names only, never the token


def test_a_dry_run_of_a_calibration_lists_the_full_arm_only(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = _dry_run(capsys, tmp_path, "--role", ROLE, "--calibration")

    assert {line["arm"] for line in lines} == {"full"}


@pytest.mark.usefixtures("no_launch")
def test_a_capped_dry_run_plans_that_many_tasks_per_role_per_arm_and_keeps_the_target(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    argv = [str(REPO_ROOT), "--output", str(tmp_path / "out.json"), "--dry-run", "--role", ROLE]

    assert cli.main([*argv, "--max-tasks", "2", "--required-pairs", "20"]) == 0

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]
    assert len(lines) == 2 * 2
    assert len({line["task_id"] for line in lines}) == 2
    assert f"{ROLE}: 2 tasks (target 20)" in captured.err


def test_a_cap_above_the_target_plus_slack_changes_nothing() -> None:
    capped = cli.plan_tasks(cli.parse_config(["--role", ROLE, "--max-tasks", "1000"]))
    plain = cli.plan_tasks(cli.parse_config(["--role", ROLE]))

    assert capped == plain


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_uses_the_declared_slack_for_the_task_count(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = _dry_run(capsys, tmp_path, "--role", ROLE, "--arm", "full", *SMALL_RUN)

    assert len(lines) == 1


@pytest.mark.usefixtures("no_launch")
def test_an_existing_output_is_refused_before_anything_else(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "out.json"
    output.write_text("earlier", encoding="utf-8")

    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(output)])

    assert code == 2
    assert "--overwrite" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "earlier"


@pytest.mark.usefixtures("no_launch")
def test_a_role_with_no_task_kit_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(tasks, "ROLE_KITS", {})
    tasks.kit_for.cache_clear()
    try:
        code = cli.main(
            [str(REPO_ROOT), "--role", "sentinel", "--output", str(tmp_path / "o.json")]
        )
    finally:
        tasks.kit_for.cache_clear()  # the empty table's refusals must not outlive the patch

    assert code == 2
    assert "sentinel" in capsys.readouterr().err


def test_a_paid_run_without_a_credential_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, no_launch: None, tmp_path: Path
) -> None:
    for key in session_loop.CREDENTIAL_KEYS:
        monkeypatch.delenv(key, raising=False)

    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(tmp_path / "o.json")])

    assert code == 2
    assert not (tmp_path / "o.json").exists()


# ---------------------------------------------------------------------------
# The golden-case record
# ---------------------------------------------------------------------------


def test_the_golden_record_counts_the_cases_the_judge_got_wrong() -> None:
    right = GoldenVerdicts(bad=Failed("missed"), good=Passed())
    wrong = GoldenVerdicts(bad=Passed(), good=Passed())

    record = session_loop.golden_record({"C3": right, "C9": wrong})

    assert record["observed_error"] == 0.25
    assert record["cases"]["C3"]["separates"] is True
    assert record["cases"]["C9"]["bad"] == {"outcome": "passed"}


def test_an_errored_golden_case_is_recorded_but_neither_right_nor_wrong() -> None:
    errored = GoldenVerdicts(bad=CheckErrored("judge down"), good=Passed())

    assert session_loop.golden_record({"C3": errored})["observed_error"] == 0.0
    assert (
        session_loop.golden_record({"C3": GoldenVerdicts(CheckErrored("x"), CheckErrored("y"))})[
            "observed_error"
        ]
        is None
    )


class _ScriptedJudge(JudgeClient):
    """Fails the golden bad case and passes everything else, as a faithful judge would."""

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        verdict = "FAIL" if artifact == C3.golden_bad_case else "PASS"  # type: ignore[union-attr]
        return JudgeVerdict(verdict=verdict, findings=(), score=0, raw={})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The paid loop, over a scripted `claude`
# ---------------------------------------------------------------------------


class Script:
    """Answers each launch like a session would, and records what was launched."""

    delivers_kernel = True  # a lean spawn records its kernel in the role's own transcript

    def __init__(
        self, *, cost: float | None = 0.01, fail_launch: Callable[[int], bool] | None = None
    ):
        self.cost = cost
        self.fail_launch = fail_launch or (lambda number: False)
        self.specs: list[SessionSpec] = []

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        self.specs.append(spec)
        if self.fail_launch(len(self.specs)):
            return SessionRun("", "scripted failure", 3)
        return SessionRun(self._stream(spec, env), "", 0)

    def _stream(self, spec: SessionSpec, env: dict[str, str]) -> str:
        role = re.search(r"praxion:([a-z-]+)", spec.prompt).group(1)  # type: ignore[union-attr]
        lean = "lean" in spec.plugin_dir.name
        answer = self._answer(spec, env, lean)
        if lean and self.delivers_kernel:
            config_dir = Path(env["CLAUDE_CONFIG_DIR"])
            path = transcript.transcript_path(config_dir, str(spec.cwd), SESSION_ID, AGENT_ID)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(KERNEL_TRANSCRIPT)
        spawned = f"{answer}\nagentId: {AGENT_ID} (to resume)"
        tokens = LEAN_TOKENS if lean else FULL_TOKENS
        usage = {
            "input_tokens": 2,
            "cache_creation_input_tokens": tokens,
            "cache_read_input_tokens": 0,
        }
        plugin = {"name": "praxion", "source": "praxion@inline", "path": str(spec.plugin_dir)}
        result = {"type": "result", "subtype": "success", "is_error": False, "result": answer}
        result["session_id"] = SESSION_ID
        if self.cost is not None:
            result["total_cost_usd"] = self.cost
        events = [
            {
                "type": "system",
                "subtype": "init",
                "plugins": [plugin],
                "mcp_servers": [],
                "cwd": str(spec.cwd),
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Agent",
                            "input": {"subagent_type": f"praxion:{role}", "prompt": "do it"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "parent_tool_use_id": "t1",
                "message": {"content": [{"type": "text", "text": answer}], "usage": usage},
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "t1", "content": spawned}]
                },
            },
            result,
        ]
        return "\n".join(json.dumps(event) for event in events)

    @staticmethod
    def _answer(spec: SessionSpec, env: dict[str, str], lean: bool) -> str:
        if PROOF_LABEL not in spec.prompt:
            return "Findings are in the report.\n[COMPLETE]"
        if lean:
            return NO_MARKER_REPLY
        planted = (Path(env["CLAUDE_CONFIG_DIR"]) / "CLAUDE.md").read_text(encoding="utf-8")
        return re.findall(rf"{PROOF_LABEL}-[0-9a-f]+", planted)[-1]


@pytest.fixture
def paid(monkeypatch: pytest.MonkeyPatch) -> Callable[[Script], None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-credential")
    monkeypatch.setattr(session_loop, "query_claude_version", lambda: "9.9.9-test")

    def install(script: Script) -> None:
        monkeypatch.setattr(session_launch, "run_session", script)

    return install


@pytest.fixture
def full_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every task launches the full arm first, so a scripted run's expectations read in arm order."""
    monkeypatch.setattr(session_loop, "launch_order", lambda seed, task_id: ("full", "lean"))


class Explodes(Script):
    """Launches the third session like the others, then raises as a decode failure would."""

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        run = super().__call__(spec, env)
        if len(self.specs) == 3:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return run


def _run(tmp_path: Path, *options: str, name: str = "out.json") -> tuple[int, results.RunResults]:
    output = tmp_path / name
    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(output), *SMALL_RUN, *options])
    return code, results.load(output)


def _sessions(loaded: results.RunResults) -> list[tuple[str, str]]:
    return [(r.setup.arm, type(r.status).__name__) for r in loaded.sessions]


@pytest.mark.usefixtures("full_first")
def test_an_exception_after_the_session_was_launched_is_charged_the_full_session_budget(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Explodes())

    loaded = _run(tmp_path, "--max-total-usd", "4")[1]

    assert _sessions(loaded) == [("full", "Errored"), ("lean", "Measured")]
    exploded = loaded.sessions[0]
    assert getattr(exploded.status, "kind", None) == "evaluation_exception"
    assert exploded.cost_usd == 1.0  # the session budget: the process may have run and spent
    assert loaded.run.extra["spend"]["spent_usd"] == pytest.approx(1.0 + 3 * 0.01)


@pytest.mark.usefixtures("full_first")
def test_each_arm_is_proven_then_the_task_runs_in_both_arms_in_turn(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    code, loaded = _run(tmp_path)

    assert code == 0
    assert loaded.run.complete
    assert [("lean" in s.plugin_dir.name) for s in script.specs] == [False, True, False, True]
    assert _sessions(loaded) == [("full", "Measured"), ("lean", "Measured")]
    assert {arm: loaded.arms[ROLE][arm]["built"] for arm in ("full", "lean")} == {
        "full": True,
        "lean": True,
    }
    assert loaded.arms[ROLE]["lean"]["proof"]["cross_checked"] is True
    assert loaded.run.claude_code_version == "9.9.9-test"
    assert loaded.run.extra["retries"] == []


@pytest.mark.usefixtures("full_first")
def test_a_lean_session_whose_transcript_is_absent_names_the_path_it_looked_at(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    script.delivers_kernel = False
    paid(script)

    lean = _run(tmp_path)[1].sessions[1].status

    assert getattr(lean, "kind", None) == "kernel_missing"
    assert f"/subagents/agent-{AGENT_ID}.jsonl was not found" in lean.detail


@pytest.mark.usefixtures("full_first")
def test_a_transient_infrastructure_error_is_retried_once_and_the_retry_replaces_it(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number == 4)  # the lean task session
    paid(script)

    code, loaded = _run(tmp_path)

    assert code == 0
    assert _sessions(loaded) == [("full", "Measured"), ("lean", "Errored"), ("lean", "Measured")]
    assert loaded.run.extra["retries"] == [
        {
            "role": ROLE,
            "arm": "lean",
            "task_id": loaded.sessions[0].setup.task_id,
            "after": "exit_nonzero",
        }
    ]
    assert isinstance(results.pairs_of(loaded, ROLE)[0].lean, Measured)


def test_an_error_that_keeps_failing_is_retried_once_only_and_leaves_the_run_incomplete(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number >= 2)  # every launch after the proof
    paid(script)

    code, loaded = _run(tmp_path, "--arm", "lean")

    assert code == 1
    assert len(script.specs) == 3  # the proof, the lean session and its one retry
    assert _sessions(loaded) == [("lean", "Errored"), ("lean", "Errored")]
    assert not loaded.run.complete


@pytest.mark.usefixtures("full_first")
def test_a_session_that_reports_no_cost_is_charged_its_budget_and_the_cap_refuses_the_rest(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(cost=None)
    paid(script)

    code, loaded = _run(tmp_path, "--max-total-usd", "2")

    assert code == 1
    assert len(script.specs) == 2  # the two proofs fill the cap
    assert [
        (r.setup.arm, r.status.kind) for r in loaded.sessions if isinstance(r.status, Errored)
    ] == [
        ("full", "launch_refused"),
        ("lean", "launch_refused"),
    ]
    assert len(loaded.run.refused_launches) == 2
    assert loaded.run.extra["spend"] == {"cap_usd": 2.0, "spent_usd": 2.0}


def test_an_arm_whose_proof_fails_runs_no_task(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number == 1)  # the full arm's proof
    paid(script)

    code, loaded = _run(tmp_path)

    assert code == 1
    assert loaded.arms[ROLE]["full"]["built"] is False
    assert loaded.arms[ROLE]["lean"]["built"] is True
    assert _sessions(loaded) == [("lean", "Measured")]


def test_the_stop_rule_defaults_to_three_failures_and_two_thousand_characters() -> None:
    rule = cli.declared_settings(cli.parse_config(["--role", ROLE])).stop_rule

    assert rule is not None
    assert (rule.count, rule.tail_chars, rule.masking) == (3, 2000, "v1")
    assert rule.kinds == COUNTING_KINDS


def test_a_declared_stop_count_and_tail_bound_reach_the_rule() -> None:
    config = cli.parse_config(["--role", ROLE, "--stop-count", "5", "--tail-chars", "300"])

    rule = cli.declared_settings(config).stop_rule

    assert rule is not None
    assert (rule.count, rule.tail_chars) == (5, 300)


@pytest.mark.parametrize("stop_count", ["0", "1", "2", "-3"])
def test_a_stop_count_below_three_is_a_usage_error_naming_the_stop(
    stop_count: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.parse_config(["--role", ROLE, "--stop-count", stop_count])

    assert raised.value.code == 2
    assert "stop count must be at least 3" in capsys.readouterr().err


def test_a_tail_bound_of_zero_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.parse_config(["--role", ROLE, "--tail-chars", "0"])

    assert raised.value.code == 2


def test_the_stop_rule_survives_the_settings_json_round_trip() -> None:
    settings = cli.declared_settings(cli.parse_config(["--role", ROLE, "--stop-count", "4"]))

    wire = model.settings_to_json(settings)

    assert wire["stop_rule"]["count"] == 4
    assert model.settings_from_json(wire) == settings


def test_settings_written_before_the_stop_rule_load_without_one() -> None:
    wire = model.settings_to_json(cli.declared_settings(cli.parse_config(["--role", ROLE])))
    del wire["stop_rule"]

    assert model.settings_from_json(wire).stop_rule is None
    assert "stop_rule" not in model.settings_to_json(model.settings_from_json(wire))


def test_a_stop_rule_naming_another_masking_rule_is_refused() -> None:
    wire = model.settings_to_json(cli.declared_settings(cli.parse_config(["--role", ROLE])))
    wire["stop_rule"]["masking"] = "v2"

    with pytest.raises(ValueError, match="masking"):
        model.settings_from_json(wire)


def test_an_allowance_is_declared_per_role_and_check_and_read_by_that_role_only() -> None:
    settings = cli.declared_settings(
        cli.parse_config(["--role", ROLE, "--role", "verifier"]),
        "calibration-1",
        {allowance_key("C1", ROLE): 3},
    )

    assert settings.allowance("C1", ROLE) == 3
    assert settings.allowance("C1", "verifier") == 0


def test_golden_cases_are_judged_once_and_recorded_before_any_session(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paid(Script())
    monkeypatch.setattr(session_loop, "select_judge_client", _ScriptedJudge)
    output = tmp_path / "golden.json"

    code = cli.main(
        [
            str(REPO_ROOT),
            "--role",
            ROLE,
            "--output",
            str(output),
            "--judge-golden",
            "--max-total-usd",
            "0.5",
            "--session-budget-usd",
            "1",
        ]
    )

    recorded = results.load(output).golden_bad_case_verdicts
    assert code == 1  # the cap refused the proofs
    assert recorded is not None
    assert recorded["observed_error"] == 0.0
    assert recorded["cases"]["C3"]["separates"] is True


def test_judging_that_is_unavailable_is_a_usage_error_before_anything_is_written(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paid(Script())

    def unavailable() -> JudgeClient:
        raise RuntimeError("no judge credentials")

    monkeypatch.setattr(session_loop, "select_judge_client", unavailable)

    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(tmp_path / "o.json")])

    assert code == 2
    assert not (tmp_path / "o.json").exists()


def test_the_report_option_renders_a_results_file_and_launches_nothing(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = Script()
    paid(script)
    _, loaded = _run(tmp_path)
    launched = len(script.specs)
    capsys.readouterr()

    code = cli.main(["--report", str(tmp_path / "out.json")])

    assert code == 0
    assert loaded.run.id in capsys.readouterr().out
    assert len(script.specs) == launched


# ---------------------------------------------------------------------------
# What a task tells the grader, and the one C6 page probe
# ---------------------------------------------------------------------------


def _task_with(variant_label: str) -> tasks.TaskSpec:
    every_task = tasks.generate(ROLE, cli.DEFAULT_SEED, tasks.producible_task_count(ROLE, 7))
    return next(t for t in every_task if t.task_id.endswith(f".{variant_label}"))


def test_an_injection_task_tells_the_grader_what_was_planted_and_whether_the_page_was_reachable() -> (
    None
):
    task = _task_with("injection")

    reachable = session_launch._task_facts(task, page_available=True)
    unreachable = session_launch._task_facts(task, page_available=False)

    assert reachable["planted_effect"] == tasks.PLANTED_INJECTION.effect_path
    assert (reachable["fetchable_page"], unreachable["fetchable_page"]) == (True, False)


def test_an_early_stop_task_is_marked_as_forced_and_plants_nothing() -> None:
    facts = session_launch._task_facts(_task_with("early-stop"), page_available=True)

    assert facts["forced_stop"] is True
    assert (facts["planted_instruction"], facts["fetchable_page"]) == (None, False)


def test_the_page_is_probed_once_and_only_when_a_task_needs_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probes: list[str] = []
    monkeypatch.setattr(session_loop, "page_is_fetchable", lambda url: probes.append(url) or False)
    config = cli.parse_config(["--role", ROLE, "--output", str(tmp_path / "o.json")])
    checkout = session_loop.Checkout(REPO_ROOT, "0" * 40, False)
    planned = {ROLE: [_task_with("injection")]}
    output = tmp_path / "o.json"
    settings = cli.declared_settings(config)
    started = session_loop.datetime.now(session_loop.UTC)
    provisional = session_loop._provisional(
        config, checkout, planned, settings, "run", "1", started, output
    )
    context = session_loop.Context(
        config, checkout, planned, None, output, tmp_path, "https://page", True
    )
    state = session_loop.RunState(provisional, session_loop.SpendLedger(cap_usd=1.0))

    unproven = session_loop._probe_page(context, state, [])
    first = session_loop._probe_page(context, unproven, ["full"])
    again = session_loop._probe_page(context, first, ["full", "lean"])

    assert unproven.page_fetchable is None
    assert (first.page_fetchable, again.page_fetchable, probes) == (False, False, ["https://page"])
    assert first.results.run.extra["c6_page"] == {"url": "https://page", "fetchable": False}
