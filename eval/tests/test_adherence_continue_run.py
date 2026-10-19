"""Continuing a stopped run over a scripted `claude`: the later part declares what the run
declared, launches again only the tasks no part finished (whole, in both arms, in the planned
order, each with its own retry), records the harness version it ran under and names the run it
continues, while a run that did not stop continuably, or that would not measure the same thing
under the same declarations, or that could replace a paid session file, is refused before
anything launches."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence import cli, results, session_loop
from praxion_evals.adherence.arms import PROOF_LABEL
from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    DEFAULT_STOP_COUNT,
    EvidenceTail,
    Launched,
    StopReason,
    StopRule,
)
from praxion_evals.adherence.lineage import (
    Finished,
    InfraStopped,
    ReadTip,
    SpendRefused,
    _fails_alike,
    continuation_refusals,
    ending_of,
    ending_to_json,
    never_launched,
    relaunch_tasks,
)
from praxion_evals.adherence.model import Errored, Measured, SessionRecord
from praxion_evals.adherence.run_identity import MeasuredIdentity, tree_digest
from praxion_evals.live.session import SessionSpec
from tests.adherence_run_support import (
    ROLE,
    Script,
    run_small,
    scripted_checkout,
)
from tests.stopped_run_support import (
    BOTH_IN_STREAK,
    LAUNCHED_AGAIN,
    LEAN_BEFORE_STREAK,
    LEAN_IN_STREAK,
    LEAN_ONLY,
    NEVER_LAUNCHED,
    REFUSED,
    STOPPED,
    STOPPING_KIND,
    STOPPING_TAIL,
    build_stopped,
    rewritten,
    stopped_in_eight_shapes,
)
from tests.test_adherence_results import declared, run_results, session

SEEDED_LAUNCH_ORDER = session_loop.launch_order  # as imported, before `full_first` fixes it

# Every task launches full first, as the shapes below read.
pytestmark = pytest.mark.usefixtures("full_first", "unswitched_checkout")


def _continue(tmp_path: Path, run_id: str, *options: str, name: str = "part.json") -> int:
    where = ["--output", str(tmp_path / name)]  # its directory is where the stopped run is
    return cli.main([str(scripted_checkout()), "--continue", run_id, *where, *options])


def _task_sessions(script: Script) -> list[SessionSpec]:
    """The task sessions the script launched since it was installed; the arm proofs are not."""
    return [spec for spec in script.specs if PROOF_LABEL not in spec.prompt]


@pytest.fixture(scope="module")
def stopped_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The directory of a stopped run launched full arm first, built once for every test."""
    return build_stopped(tmp_path_factory, seeded_order=False)


@pytest.fixture(scope="module")
def stopped_dir_seeded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The directory of a stopped run launched in the seed's order, built once."""
    return build_stopped(tmp_path_factory, seeded_order=True)


@pytest.fixture
def stopped(
    request: pytest.FixtureRequest, paid: Callable[[Script], None], tmp_path: Path
) -> results.RunResults:
    """A stopped run in ``tmp_path``: a copy of the one built for the module, in the order the test asks."""
    seeded = "seeded_launch_order" in request.fixturenames
    source = request.getfixturevalue("stopped_dir_seeded" if seeded else "stopped_dir")
    shutil.copytree(source, tmp_path, dirs_exist_ok=True)
    paid(Script())
    return results.load(tmp_path / STOPPED)


def _planned(run: results.RunResults, *positions: int) -> list[str]:
    planned = run.run.extra["tasks"][ROLE]
    return [planned[at] for at in positions]


def _relaunched(part: results.RunResults) -> list[tuple[str, str]]:
    return [(r.setup.task_id, r.setup.arm) for r in part.sessions]


# ---------------------------------------------------------------------------
# What a continuation launches
# ---------------------------------------------------------------------------


def test_a_continuation_launches_again_exactly_the_tasks_no_part_finished_in_both_arms(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())

    code = _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    assert code == 0
    assert {task for task, _ in _relaunched(part)} == set(_planned(stopped, *LAUNCHED_AGAIN))
    assert len(_relaunched(part)) == 2 * len(LAUNCHED_AGAIN)


@pytest.fixture
def seeded_launch_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """The order the seed gives each task, for a test that reads it: undoes ``full_first``."""
    monkeypatch.setattr(session_loop, "launch_order", SEEDED_LAUNCH_ORDER)


def test_the_tasks_launched_again_run_in_their_planned_and_seeded_order(
    paid: Callable[[Script], None],
    seeded_launch_order: None,
    stopped: results.RunResults,
    tmp_path: Path,
) -> None:
    paid(Script())

    _continue(tmp_path, stopped.run.id)

    seed = stopped.run.extra["seed"]
    again = _planned(stopped, *LAUNCHED_AGAIN)
    expected = [(task, arm) for task in again for arm in SEEDED_LAUNCH_ORDER(seed, task)]
    full_first_order = [(task, arm) for task in again for arm in ("full", "lean")]
    assert expected != full_first_order, "the seed draws an order a fixed one would not give"
    assert _relaunched(results.load(tmp_path / "part.json")) == expected


def test_lean_failures_recorded_before_the_stop_stand_in_the_stopped_part(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())
    recorded = (tmp_path / STOPPED).read_text(encoding="utf-8")

    _continue(tmp_path, stopped.run.id)

    kept = set(_planned(stopped, LEAN_BEFORE_STREAK, LEAN_ONLY))
    part = results.load(tmp_path / "part.json")
    assert not kept & {task for task, _ in _relaunched(part)}
    assert (tmp_path / STOPPED).read_text(encoding="utf-8") == recorded, "the stop is rewritten"


def test_a_relaunched_session_has_its_own_retry_whatever_the_stopped_run_retried(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    proofs = 2  # one per arm, launched before any task
    paid(Script(fail_launch=lambda number: number == proofs + 1))

    _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    first = _planned(stopped, LEAN_IN_STREAK)[0]
    statuses = [
        type(r.status) for r in part.sessions if (r.setup.task_id, r.setup.arm) == (first, "full")
    ]
    assert statuses == [Errored, Measured]
    assert part.run.extra["retries"] == [
        {"role": ROLE, "arm": "full", "task_id": first, "after": "exit_nonzero"}
    ]


def test_a_continuation_of_a_continuation_launches_only_what_neither_part_finished(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script(cost=None))  # each session is charged its whole budget: room for two proofs, a pair
    _continue(tmp_path, stopped.run.id, "--session-budget-usd", "1", "--max-total-usd", "4")
    second = results.load(tmp_path / "part.json")
    paid(Script())

    _continue(tmp_path, second.run.id, name="third.json")

    third = results.load(tmp_path / "third.json")
    assert isinstance(ending_of(second), SpendRefused)
    assert {task for task, _ in _relaunched(third)} == set(
        _planned(stopped, BOTH_IN_STREAK, REFUSED, NEVER_LAUNCHED)
    )
    assert [part["run_id"] for part in third.run.extra["lineage"]] == [
        stopped.run.id,
        second.run.id,
        third.run.id,
    ]


# ---------------------------------------------------------------------------
# What the later part records
# ---------------------------------------------------------------------------


def test_the_later_part_names_the_run_it_continues_and_declares_what_it_declared(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())

    _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    assert part.run.extra["continues"] == stopped.run.id
    assert part.run.extra["lineage"] == [
        {
            "run_id": stopped.run.id,
            "stop": f"3 lean sessions in a row ended in {STOPPING_KIND} with the same evidence",
        },
        {"run_id": part.run.id, "stop": None},
    ]
    assert part.settings == stopped.settings
    assert part.run.extra["tasks"] == stopped.run.extra["tasks"], "the whole plan, not the relaunch"
    assert ending_of(part) == Finished()
    assert {arm: part.arms[ROLE][arm]["built"] for arm in ("full", "lean")} == {
        "full": True,
        "lean": True,
    }, "each part builds and proves its own arms"


def test_the_later_part_records_the_harness_version_it_ran_under(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_loop, "query_claude_version", lambda: "9.9.10-later")

    _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    assert (stopped.run.claude_code_version, part.run.claude_code_version) == (
        "9.9.9-test",
        "9.9.10-later",
    )


# ---------------------------------------------------------------------------
# Refused before anything launches
# ---------------------------------------------------------------------------


def test_a_continuation_of_a_run_that_finished_its_plan_is_refused_before_any_launch(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    paid(Script())
    run = run_small(tmp_path, name=STOPPED)[1]
    finished = rewritten(tmp_path, run, Finished())
    script = Script()
    paid(script)
    capsys.readouterr()

    code = _continue(tmp_path, finished.run.id)

    assert code == 2
    assert f"run {finished.run.id} finished its plan" in capsys.readouterr().err
    assert script.specs == []
    assert not (tmp_path / "part.json").exists()


@pytest.mark.parametrize(
    ("options", "named"),
    [
        (["--margin-pp", "5"], "--margin-pp"),
        (["--seed", "8"], "--seed"),
        (["--max-tasks", "2"], "--max-tasks"),
    ],
    ids=["margin", "seed", "task cap"],
)
def test_an_option_that_changes_a_declaration_is_refused_naming_it(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    options: list[str],
    named: str,
) -> None:
    script = Script()
    paid(script)
    capsys.readouterr()

    code = _continue(tmp_path, stopped.run.id, *options)

    assert code == 2
    assert named in capsys.readouterr().err
    assert script.specs == []


def test_options_that_restate_the_declarations_are_accepted(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    script = Script()
    paid(script)
    restated = ["--role", ROLE, "--no-judge", "--max-tasks", "8", "--seed", "7"]

    code = _continue(tmp_path, stopped.run.id, *restated, "--session-budget-usd", "2")

    assert code == 0
    assert _task_sessions(script), "the continuation launched its tasks"


def _refused_beside(
    script: Script, capsys: pytest.CaptureFixture[str], code: int, tmp_path: Path, *named: str
) -> None:
    refusal = capsys.readouterr().err
    assert code == 2
    assert all(word in refusal for word in named), f"the refusal does not name {named}: {refusal}"
    assert script.specs == [], "a session launched before the refusal"
    assert not (tmp_path / "part.json").exists()


def test_a_recorded_launch_order_other_than_the_seeds_is_refused_naming_the_task(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    orders = stopped.run.extra["launch_order"][ROLE]
    task = next(iter(orders))
    swapped = {**orders, task: list(reversed(orders[task]))}
    extra = {**stopped.run.extra, "launch_order": {ROLE: swapped}}
    results.write_atomic(
        tmp_path / STOPPED, replace(stopped, run=replace(stopped.run, extra=extra))
    )
    script = Script()
    paid(script)
    capsys.readouterr()

    code = _continue(tmp_path, stopped.run.id)

    _refused_beside(script, capsys, code, tmp_path, f"launch_orders.{ROLE}.{task}")


def test_a_continuation_asked_to_overwrite_its_own_lineage_leaves_the_paid_file_untouched(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = Script()
    paid(script)
    recorded = (tmp_path / STOPPED).read_bytes()
    capsys.readouterr()

    code = _continue(tmp_path, stopped.run.id, "--output", str(tmp_path / STOPPED), "--overwrite")

    _refused_beside(script, capsys, code, tmp_path, "is a results file of the run's own lineage")
    assert (tmp_path / STOPPED).read_bytes() == recorded, "a paid session file was replaced"


def test_a_continuation_names_no_budget_so_it_runs_under_the_limits_the_run_recorded(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    run = stopped_in_eight_shapes(tmp_path, "--session-budget-usd", "2", "--max-total-usd", "7")

    _continue(tmp_path, run.run.id)

    part = results.load(tmp_path / "part.json").run.extra
    assert (part["session_budget_usd"], part["spend"]["cap_usd"]) == (2.0, 7.0)


def test_a_results_file_that_records_no_tasks_is_refused_naming_what_is_missing(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    extra = {k: v for k, v in stopped.run.extra.items() if k != "tasks"}
    results.write_atomic(
        tmp_path / STOPPED, replace(stopped, run=replace(stopped.run, extra=extra))
    )
    script = Script()
    paid(script)
    capsys.readouterr()

    code = _continue(tmp_path, stopped.run.id)

    _refused_beside(script, capsys, code, tmp_path, "'tasks'")


# ---------------------------------------------------------------------------
# Measuring the same thing: the identity now against the stopped run's, as pure values
# ---------------------------------------------------------------------------

STOP_RULE = StopRule.parse(DEFAULT_STOP_COUNT, COUNTING_KINDS, 2000)
STOPPED_DECLARATION = replace(
    declared(), stop_rule=STOP_RULE, allowance_method="own-discordance-exact"
)


def _identity(**changes: Any) -> MeasuredIdentity:
    held: dict[str, Any] = {
        "tree": "tree-a",
        "model": "claude-opus-5-5",
        "seed": 7,
        "tasks": {ROLE: ("task-0", "task-1")},
        "launch_orders": {ROLE: {"task-0": ("full", "lean"), "task-1": ("lean", "full")}},
        "declared": STOPPED_DECLARATION,
        "roles": {},
    }
    return MeasuredIdentity(**{**held, **changes})


def _stopped_tip() -> ReadTip:
    ending = InfraStopped(StopReason("exit_nonzero", "", ROLE, "lean", (), "both-arms"))  # type: ignore[arg-type]
    run = run_results([], extra={"ending": ending_to_json(ending)})
    return ReadTip(run, _identity())


def _declared(**changes: Any) -> dict[str, Any]:
    return {"declared": replace(STOPPED_DECLARATION, **changes)}


@pytest.mark.parametrize(
    ("now", "named"),
    [
        (_declared(margin_pp=12.0), "declared.margin_pp"),
        (_declared(confidence=0.9), "declared.confidence"),
        (_declared(required_pairs=9), "declared.required_pairs"),
        (_declared(pair_slack=2), "declared.pair_slack"),
        (_declared(retry_policy="one retry, after anything"), "declared.retry_policy"),
        (_declared(allowance_method=None), "declared.allowance_method"),
        (_declared(stop_rule=StopRule.parse(5, COUNTING_KINDS, 2000)), "declared.stop_rule.count"),
        (_declared(stop_rule=StopRule.parse(3, {"timeout"}, 2000)), "declared.stop_rule.kinds"),
        (
            _declared(stop_rule=StopRule.parse(3, COUNTING_KINDS, 500)),
            "declared.stop_rule.tail_chars",
        ),
        ({"model": "claude-opus-5-6"}, "model"),
        ({"seed": 8}, "seed"),
        ({"tasks": {ROLE: ("task-0",)}}, f"tasks.{ROLE}"),
        (
            {"launch_orders": {ROLE: {"task-0": ("lean", "full"), "task-1": ("lean", "full")}}},
            f"launch_orders.{ROLE}.task-0",
        ),
    ],
    ids=[
        "margin",
        "confidence",
        "target",
        "slack",
        "retry policy",
        "allowance method",
        "stop count",
        "counting kinds",
        "tail bound",
        "resolved model",
        "seed",
        "planned tasks",
        "launch order",
    ],
)
def test_every_difference_in_what_is_declared_or_drawn_is_refused_naming_it(
    now: dict[str, Any], named: str
) -> None:
    (refused,) = continuation_refusals(_stopped_tip(), _identity(**now), ())

    assert refused.startswith(f"changed since the stop: {named}:")


def _recorded_first() -> results.RunResults:
    """The first part of a run as the options below are read against: a target of 8 pairs, no
    slack, and the default margin, confidence, stop rule and effort."""
    extra = {
        "roles": [ROLE],
        "arms": ["full", "lean"],
        "judging": False,
        "calibration": False,
        "effort": "medium",
        "tasks": {ROLE: ["task-0", "task-1"]},
    }
    settings = replace(STOPPED_DECLARATION, required_pairs=8)
    return run_results([], settings=settings, extra=extra)


def _changed_by(*options: str) -> tuple[str, ...]:
    first = _recorded_first()
    argv = ["--continue", first.run.id, *options]
    config = cli.parse_config(argv)
    declared = cli.recorded_config(config, first)
    return cli._changed_options(cli.given_options(argv), config, declared, first)


@pytest.mark.parametrize(
    "options",
    [
        ["--model", "sonnet"],
        ["--effort", "low"],
        ["--confidence", "0.9"],
        ["--required-pairs", "9"],
        ["--pair-slack", "2"],
        ["--stop-count", "5"],
        ["--tail-chars", "500"],
        ["--judge-golden"],
    ],
    ids=["model", "effort", "confidence", "target", "slack", "stop count", "tail bound", "golden"],
)
def test_an_option_naming_another_value_than_the_run_declared_is_named_as_a_change(
    options: list[str],
) -> None:
    assert _changed_by(*options) == (options[0],)


def test_options_restating_the_run_declared_are_no_change() -> None:
    restated = ["--model", "claude-opus-5-5", "--effort", "medium", "--required-pairs", "8"]

    assert _changed_by(*restated, "--confidence", "0.95", "--stop-count", "3", "--no-judge") == ()


def test_a_first_part_that_records_no_tasks_is_refused_naming_it() -> None:
    first = _recorded_first()
    extra = {k: v for k, v in first.run.extra.items() if k != "tasks"}
    first = replace(first, run=replace(first.run, extra=extra))
    declared_again = cli.recorded_config(cli.parse_config(["--continue", first.run.id]), first)

    with pytest.raises(ValueError, match=f"run {first.run.id} does not record its planned tasks"):
        cli._replanned(declared_again, first)


@pytest.mark.parametrize(
    ("options", "named"),
    [
        (["--overwrite"], ["--overwrite"]),
        (["--output", "OWN"], ["is a results file of the run's own lineage"]),
        (["--output", "OWN", "--overwrite"], ["--overwrite", "own lineage"]),
        (["--output", "ELSEWHERE"], []),
    ],
    ids=["overwrite", "its own file", "its own file, overwritten", "another file"],
)
def test_a_continuation_that_could_replace_a_lineage_file_is_refused_naming_why(
    tmp_path: Path, options: list[str], named: list[str]
) -> None:
    where = {"OWN": tmp_path / "own.json", "ELSEWHERE": tmp_path / "other.json"}
    argv = ["--continue", "x", *(str(where.get(option, option)) for option in options)]

    refused = cli._output_refusals(cli.parse_config(argv), [tmp_path / "own.json"])

    assert len(refused) == len(named)
    assert all(word in line for word, line in zip(named, refused, strict=True))


def test_a_path_of_the_tree_that_changed_is_named_beside_the_tree_difference() -> None:
    now = _identity(tree="tree-b")

    refused = continuation_refusals(_stopped_tip(), now, (), [".ai-state/kernel_adoption.yaml"])

    assert len(refused) == 2
    assert refused[0].startswith("changed since the stop: tree:")
    assert ".ai-state/kernel_adoption.yaml" in refused[1]


# ---------------------------------------------------------------------------
# Which paths of the tree changed since the commit a run launched at
# ---------------------------------------------------------------------------

ADOPTION = ".ai-state/kernel_adoption.yaml"
RESULTS_FILE = ".ai-state/eval_ledger/adherence/stopped.json"
TELEMETRY = ".ai-state/observations.jsonl"


def _vcs(repo: Path, *args: str) -> str:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.org"]
    done = subprocess.run(
        ["git", "-C", str(repo), *identity, *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _write(repo: Path, path: str, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


@pytest.fixture
def launched_at(tmp_path: Path) -> tuple[Path, str]:
    """A committed repository with `scratch/` ignored, and the commit a run launched at."""
    repo = tmp_path / "launched"
    repo.mkdir()
    _vcs(repo, "init", "-q", "-b", "main")
    for path in (ADOPTION, RESULTS_FILE, TELEMETRY, "agents/researcher.md", ".gitignore"):
        _write(repo, path, "scratch/\n" if path == ".gitignore" else "one\n")
    _vcs(repo, "add", ".")
    _vcs(repo, "commit", "-q", "-m", "launch")
    return repo, _vcs(repo, "rev-parse", "HEAD")


def _committed(repo: Path, path: str) -> None:
    _write(repo, path, "two\n")
    _vcs(repo, "add", "--", path)
    _vcs(repo, "commit", "-q", "-m", f"change {path}")


def test_committing_a_results_file_after_the_launch_changes_no_path_and_not_the_digest(
    launched_at: tuple[Path, str],
) -> None:
    repo, commit = launched_at
    digest = tree_digest(repo)

    _committed(repo, RESULTS_FILE)

    assert cli.paths_changed_since(repo, commit) == ()
    assert tree_digest(repo) == digest


def test_a_commit_to_the_adoption_ledger_after_the_launch_names_it(
    launched_at: tuple[Path, str],
) -> None:
    repo, commit = launched_at

    _committed(repo, ADOPTION)

    assert cli.paths_changed_since(repo, commit) == (ADOPTION,)


def test_edits_deletions_and_new_files_in_the_working_tree_are_named_sorted(
    launched_at: tuple[Path, str],
) -> None:
    repo, commit = launched_at
    _write(repo, "agents/researcher.md", "edited\n")
    (repo / ADOPTION).unlink()
    _write(repo, "docs/new.md", "new\n")

    assert cli.paths_changed_since(repo, commit) == (
        ADOPTION,
        "agents/researcher.md",
        "docs/new.md",
    )


def test_hook_written_telemetry_and_ignored_files_are_not_named(
    launched_at: tuple[Path, str],
) -> None:
    repo, commit = launched_at
    _committed(repo, TELEMETRY)
    _write(repo, "scratch/notes.txt", "ignored\n")

    assert cli.paths_changed_since(repo, commit) == ()


def test_a_commit_the_repository_does_not_hold_names_no_path(launched_at: tuple[Path, str]) -> None:
    repo, _ = launched_at

    assert cli.paths_changed_since(repo, "0" * 40) == ()


# ---------------------------------------------------------------------------
# Which sessions a stop's window leaves failed: the stop's own reading of a failure
# ---------------------------------------------------------------------------

STOPPING_BUDGET = "the role spent its session budget (result_subtype=error_max_budget)"
RESULT_ERROR = "result_error"


def _result_error(
    task: str, arm: str, detail: str = "the session failed", tail: str = STOPPING_TAIL
) -> SessionRecord:
    return session(task, arm, Errored(RESULT_ERROR, detail, tails=EvidenceTail(tail, "")))  # type: ignore[arg-type]


def _lean_stop(sessions: list[SessionRecord], tasks: tuple[str, ...]) -> results.RunResults:
    """A run that stopped on one lean failure in each of ``tasks``, its last lean sessions."""
    streak = tuple(Launched(task, "lean", 1) for task in tasks)
    masked = EvidenceTail(STOPPING_TAIL, "").masked()
    ending = InfraStopped(StopReason(RESULT_ERROR, masked, ROLE, "lean", streak, "both-arms"))  # type: ignore[arg-type]
    extra = {"tasks": {ROLE: list(tasks)}, "ending": ending_to_json(ending)}
    return run_results(sessions, settings=replace(declared(), stop_rule=STOP_RULE), extra=extra)


@pytest.mark.parametrize(
    ("other_arm", "never_launched_too"),
    [
        (_result_error("t1", "full"), True),
        (_result_error("t1", "full", STOPPING_BUDGET), False),
        (_result_error("t1", "full", tail="another channel failure"), False),
    ],
    ids=["failed as the streak did", "stopped by its own budget", "failed another way"],
)
def test_the_other_arms_session_in_the_window_is_never_launched_only_if_it_failed_as_the_streak_did(
    other_arm: SessionRecord, never_launched_too: bool
) -> None:
    sessions = [_result_error("t0", "lean"), other_arm, _result_error("t1", "lean")]
    run = _lean_stop([*sessions, _result_error("t2", "lean")], ("t0", "t1", "t2"))

    assert (1 in never_launched(run)) is never_launched_too


@pytest.mark.parametrize(
    ("record", "alike"),
    [
        (_result_error("t1", "full"), True),
        (_result_error("t1", "full", STOPPING_BUDGET), False),
        (_result_error("t1", "full", tail="another channel failure"), False),
        (
            session(
                "t1", "full", Errored("timeout", "slow", tails=EvidenceTail(STOPPING_TAIL, ""))
            ),
            False,
        ),  # type: ignore[arg-type]
        (session("t1", "full"), False),
    ],
    ids=["same kind and tail", "budget stopped", "other tail", "other kind", "measured"],
)
def test_a_session_fails_alike_only_as_the_stops_own_fold_reads_the_failure(
    record: SessionRecord, alike: bool
) -> None:
    assert _fails_alike(STOP_RULE, record, _result_error("t2", "lean")) is alike


def test_a_stop_in_a_run_that_declared_no_stop_rule_is_refused() -> None:
    run = replace(_lean_stop([_result_error("t0", "lean")], ("t0",)), settings=declared())

    with pytest.raises(ValueError, match="declares no stop rule"):
        never_launched(run)


# ---------------------------------------------------------------------------
# What earlier parts finished stays finished
# ---------------------------------------------------------------------------


def _part(run_id: str, *sessions: SessionRecord) -> results.RunResults:
    return run_results(sessions, run_id=run_id, extra={"tasks": {ROLE: ["t0", "t1", "t2"]}})


def test_a_task_an_earlier_part_finished_is_not_launched_again() -> None:
    first = _part("a", session("t0", "full"), session("t0", "lean"))

    assert relaunch_tasks(_part("b"), ROLE, [first]) == ("t1", "t2")


def test_a_later_part_completes_the_pair_an_earlier_part_began() -> None:
    first = _part("a", session("t1", "full"))
    second = _part("b", session("t1", "lean"))

    assert relaunch_tasks(second, ROLE, [first]) == ("t0", "t2")


def test_a_session_the_earlier_part_never_launched_does_not_count_in_the_fold() -> None:
    refused = Errored("launch_refused", "the cap is spent")
    first = _part("a", session("t2", "full", refused), session("t2", "lean", refused))

    assert relaunch_tasks(_part("b"), ROLE, [first]) == ("t0", "t1", "t2")


def test_an_outcome_other_than_measured_in_an_earlier_part_stands() -> None:
    first = _part("a", session("t0", "full"), session("t0", "lean", Errored("result_error", "x")))

    assert relaunch_tasks(_part("b"), ROLE, [first]) == ("t1", "t2")
