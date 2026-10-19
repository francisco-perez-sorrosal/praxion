"""The adherence console entry: argument parsing, the declared settings and stop rule, the dry
run and the start-of-run refusals, and the report option.

The paid loop itself is in `test_adherence_cli_paid_loop.py`, closing and continuing a stopped run
in `test_adherence_cli_close.py`, and what a task tells the grader in
`test_adherence_cli_task_facts.py`. None of them starts a process: the one function that starts
``claude`` (``session_launch.run_session``) is a scripted stand-in.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import (
    cli,
    model,
    session_loop,
    tasks,
)
from praxion_evals.adherence.infra_stop import COUNTING_KINDS
from tests.adherence_run_support import (
    REPO_ROOT,
    ROLE,
    SMALL_RUN,
    Script,
    dry_run,
    run_small,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")


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


def test_every_new_run_declares_the_own_discordance_method_and_no_allowance() -> None:
    settings = cli.declared_settings(cli.parse_config(["--role", ROLE]))

    assert settings.allowance_method == model.OWN_DISCORDANCE_EXACT
    assert settings.allowance_source is None
    assert dict(settings.allowances) == {}


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


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_lists_every_task_of_every_named_arm(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = dry_run(capsys, tmp_path, "--role", ROLE)

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

    lines = dry_run(
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
    lines = dry_run(capsys, tmp_path, "--role", ROLE, "--calibration")

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
    lines = dry_run(capsys, tmp_path, "--role", ROLE, "--arm", "full", *SMALL_RUN)

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


def test_the_report_option_renders_a_results_file_and_launches_nothing(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = Script()
    paid(script)
    _, loaded = run_small(tmp_path)
    launched = len(script.specs)
    capsys.readouterr()

    code = cli.main(["--report", str(tmp_path / "out.json")])

    assert code == 0
    assert loaded.run.id in capsys.readouterr().out
    assert len(script.specs) == launched
