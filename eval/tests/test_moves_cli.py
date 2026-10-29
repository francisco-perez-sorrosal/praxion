"""The move half of the entry: ``--move`` reaches it, its options are parsed once, and ``--dry-run``
prices the floor run and the paired run together without launching or writing anything."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from praxion_evals.adherence import cli
from praxion_evals.adherence.lineage import Finished, Interrupted
from praxion_evals.adherence.moves import cli as moves_cli
from praxion_evals.adherence.moves import declaration, results, runner
from praxion_evals.adherence.moves.lineage import Closed, Stopped
from praxion_evals.adherence.moves.model import MoveName
from praxion_evals.adherence.moves.results import FloorRun, PairedRun
from praxion_evals.adherence.moves.stop import Launched, MoveStopReason
from praxion_evals.live.report import CREDENTIAL_KEYS
from tests.test_moves_results import common, floor_run, moves_dir, scored, trigger

REPO_ROOT = Path(__file__).resolve().parents[2]
MOVE = "git-conventions"
DEFAULT_PAIRED_SESSIONS = 48
DEFAULT_FLOOR_SESSIONS = 8


def dry_run(capsys, *options: str, move: str = MOVE) -> list[list[str]]:
    code = cli.main([str(REPO_ROOT), "--move", move, "--dry-run", *options])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return [line.split() for line in captured.out.splitlines()]


def refused(capsys, *argv: str) -> str:
    code = cli.main(list(argv))
    assert code == moves_cli.EXIT_USAGE
    return capsys.readouterr().err


def usage_error(capsys, *argv: str) -> str:
    with pytest.raises(SystemExit) as exit_:
        cli.main(list(argv))
    assert exit_.value.code == moves_cli.EXIT_USAGE
    return capsys.readouterr().err


def test_a_dry_run_prices_the_floor_and_paired_runs_at_fifty_six_sessions(capsys):
    lines = dry_run(capsys)

    assert ["total", "floor=8", "paired=48", "all=56"] in lines
    assert Counter(line[1] for line in lines if line[0] == "session") == {
        "floor": DEFAULT_FLOOR_SESSIONS,
        "paired": DEFAULT_PAIRED_SESSIONS,
    }


def test_a_dry_run_prices_no_calibration_session(capsys):
    assert ["calibration", "sessions=0"] in dry_run(capsys)


def test_a_session_line_names_task_fixture_kind_wording_variant_and_arm(capsys):
    sessions = [line for line in dry_run(capsys) if line[0] == "session"]

    assert {len(line) for line in sessions} == {7}
    assert {line[4] for line in sessions} == {"managed", "unmanaged"}
    assert {line[6] for line in sessions} == {"floor", "full", "lean"}


def test_a_paired_task_lists_both_arms_and_a_floor_task_only_the_floor(capsys):
    lines = dry_run(capsys)
    arms = Counter((line[1], line[6]) for line in lines if line[0] == "session")

    assert arms == {
        ("floor", "floor"): DEFAULT_FLOOR_SESSIONS,
        ("paired", "full"): DEFAULT_PAIRED_SESSIONS // 2,
        ("paired", "lean"): DEFAULT_PAIRED_SESSIONS // 2,
    }
    assert {line[3] for line in lines if line[:2] == ["task", "floor"]} == {"sessions=1"}
    assert {line[3] for line in lines if line[:2] == ["task", "paired"]} == {"sessions=2"}


def test_the_same_seed_lists_the_same_order_and_another_seed_a_different_one(capsys):
    first = dry_run(capsys, "--seed", "7")

    assert dry_run(capsys, "--seed", "7") == first
    assert dry_run(capsys, "--seed", "8") != first


def test_max_tasks_caps_both_runs_but_the_floor_keeps_its_minimum(capsys):
    with_cap = dry_run(capsys, "--max-tasks", "6")

    assert ["total", "floor=6", "paired=12", "all=18"] in with_cap
    assert "floor run holds at least" in refused(
        capsys, str(REPO_ROOT), "--move", MOVE, "--dry-run", "--max-tasks", "3"
    )


def test_a_dry_run_refuses_a_run_kind_or_a_cited_floor_run(capsys):
    named = (str(REPO_ROOT), "--move", MOVE, "--dry-run")

    assert "takes no --run" in usage_error(capsys, *named, "--run", "paired")
    assert "takes no --run" in usage_error(capsys, *named, "--floor-run", "floor-1")


def test_a_run_without_a_kind_or_a_floor_citation_on_a_floor_run_is_refused(capsys):
    assert "name the run" in usage_error(capsys, str(REPO_ROOT), "--move", MOVE)
    assert "needs --run paired" in usage_error(
        capsys, str(REPO_ROOT), "--move", MOVE, "--run", "floor", "--floor-run", "floor-1"
    )


def test_a_move_without_a_kit_is_refused_naming_it(capsys):
    assert "no move kit is named 'no-such-move'" in refused(
        capsys, str(REPO_ROOT), "--move", "no-such-move", "--dry-run"
    )


def test_a_name_no_move_can_have_is_a_usage_error(capsys):
    assert "--move" in usage_error(capsys, "--move", "Not A Name", "--dry-run")


def test_a_role_and_a_move_cannot_be_named_together(capsys):
    error = usage_error(capsys, "--role", "implementer", "--move", MOVE, "--dry-run")

    assert "not allowed with" in error


def test_a_declaration_of_another_move_is_refused_naming_both(capsys, tmp_path):
    other = moves_cli.declarations.KITS_ROOT / "adr-conventions" / "declaration.json"

    error = refused(
        capsys, str(REPO_ROOT), "--move", MOVE, "--dry-run", "--declaration", str(other)
    )

    assert "declares the move adr-conventions, not git-conventions" in error


def test_the_move_seed_default_is_the_role_entrys():
    assert moves_cli.DEFAULT_SEED == cli.DEFAULT_SEED


def test_the_move_defaults_are_the_role_entrys_so_a_move_bills_and_pins_as_a_role_run_does():
    for name in (
        "DEFAULT_SESSION_BUDGET_USD",
        "DEFAULT_MARGIN_PP",
        "DEFAULT_MODEL",
        "DEFAULT_EFFORT",
    ):
        assert getattr(moves_cli, name) == getattr(cli, name), name


# --- --run: the plan a run is conducted under ---

TOKEN_FILE = "session.token"


@pytest.fixture
def conducted(monkeypatch, capsys):
    """Run the entry with the runner and the harness stood in; hands back the plan it was given."""
    plans: list[runner.RunPlan] = []
    ending = [Finished()]

    def fake_conduct(plan):
        plans.append(plan)
        common = SimpleNamespace(run_id="run-1", ending=ending[0])
        return SimpleNamespace(
            path=plan.moves_dir / "run-1.json",
            run=SimpleNamespace(run_kind=plan.kind, common=common),
        )

    monkeypatch.setattr(runner, "conduct", fake_conduct)
    monkeypatch.setattr(moves_cli, "query_claude_version", lambda: "2.1.312")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    def run(*options: str) -> tuple[int, runner.RunPlan | None]:
        code = cli.main([str(REPO_ROOT), "--move", MOVE, *options])
        return code, plans[-1] if plans else None

    run.ending = ending
    run.capsys = capsys
    return run


def test_a_move_run_takes_the_token_file_and_every_cap_option_as_a_role_run_does(
    conducted, tmp_path
):
    token = tmp_path / TOKEN_FILE
    token.write_text("sk-ant-oat01-example\n", encoding="utf-8")
    code, plan = conducted(
        "--run",
        "floor",
        "--session-oauth-token-file",
        str(token),
        "--max-total-usd",
        "12.5",
        "--session-budget-usd",
        "1.25",
    )

    assert code == 0
    assert plan is not None
    assert (plan.session_token_file, plan.run_cap_usd, plan.session_budget_usd) == (
        token,
        12.5,
        1.25,
    )


def test_a_move_run_without_billing_options_has_the_role_entrys_caps_and_no_token_file(conducted):
    _, plan = conducted("--run", "floor")

    assert plan is not None
    assert plan.session_token_file is None
    assert plan.run_cap_usd == cli.RUNNER_SPEND_CAP_USD
    assert plan.session_budget_usd == cli.DEFAULT_SESSION_BUDGET_USD


def test_a_cap_that_cannot_spend_anything_is_a_usage_error(conducted):
    for option in ("--max-total-usd", "--session-budget-usd"):
        with pytest.raises(SystemExit):
            conducted("--run", "floor", option, "0")
        assert "must be above 0.0" in conducted.capsys.readouterr().err


def test_a_run_carries_its_options_into_the_plan(conducted):
    _, plan = conducted(
        "--run", "paired", "--floor-run", "ledger/moves/floor-9.json", "--max-tasks", "4",
        "--stop-count", "5", "--seed", "11",
    )  # fmt: skip

    assert plan is not None
    assert (plan.kind, plan.floor_run, plan.max_tasks, plan.seed) == ("paired", "floor-9", 4, 11)
    assert plan.stop_rule.count == 5
    assert plan.harness_version == "2.1.312"
    assert plan.moves_dir == REPO_ROOT / ".ai-state" / "eval_ledger" / "adherence" / "moves"


def test_a_run_without_a_credential_is_refused_before_it_is_conducted(conducted, monkeypatch):
    for key in CREDENTIAL_KEYS:
        monkeypatch.delenv(key, raising=False)

    code, plan = conducted("--run", "floor")

    assert (code, plan) == (moves_cli.EXIT_USAGE, None)
    assert "no credential" in conducted.capsys.readouterr().err


def test_a_run_whose_only_credential_is_the_token_file_is_conducted(
    conducted, monkeypatch, tmp_path
):
    for key in CREDENTIAL_KEYS:
        monkeypatch.delenv(key, raising=False)
    token = tmp_path / TOKEN_FILE
    token.write_text("sk-ant-oat01-example\n", encoding="utf-8")

    code, plan = conducted("--run", "floor", "--session-oauth-token-file", str(token))

    assert code == 0
    assert plan is not None
    assert plan.session_token_file == token


@pytest.mark.parametrize(
    "prepare",
    [lambda token: None, lambda token: token.write_text(" \n", encoding="utf-8")],
    ids=["missing", "blank"],
)
def test_a_token_file_that_holds_no_token_is_refused_before_the_run_is_conducted(
    conducted, tmp_path, prepare
):
    token = tmp_path / TOKEN_FILE
    prepare(token)

    code, plan = conducted("--run", "floor", "--session-oauth-token-file", str(token))

    assert (code, plan) == (moves_cli.EXIT_USAGE, None)
    assert "session token file" in conducted.capsys.readouterr().err


def test_a_run_that_did_not_finish_exits_incomplete_and_says_where_its_file_is(conducted):
    conducted.ending[0] = Interrupted()

    code, plan = conducted("--run", "floor")

    assert code == moves_cli.EXIT_INCOMPLETE
    assert plan is not None
    out = conducted.capsys.readouterr().out
    assert "ended interrupted" in out
    assert f"results: {plan.moves_dir / 'run-1.json'}" in out


# --- --report: a results file that lives in moves/ ---


def written(tmp_path: Path, run: FloorRun | PairedRun) -> Path:
    return results.write(tmp_path / "adherence" / "moves", run)


def kit_sessions(arms):
    """Passing sessions of the kit's first three tasks, each scored on the declared checks."""
    declared = declaration.kit(MOVE)
    held = {check.name: trigger(check.name) for check in declared.checks.checks}
    tasks = runner.KITS[MOVE].tasks(declared, 7)
    return [replace(scored(task.task_id, arm), checks=held) for task in tasks[:3] for arm in arms]


def test_a_results_file_is_a_moves_by_the_directory_it_lives_in(tmp_path):
    path = written(tmp_path, floor_run(sessions=()))

    assert moves_cli.is_move_results(path)
    assert not moves_cli.is_move_results(path.parent.parent / "other.json")


def test_the_report_of_a_paired_run_names_its_subject_as_a_move(tmp_path):
    floor = floor_run("floor-1", sessions=kit_sessions(["floor"]))
    written(tmp_path, floor)
    sessions = kit_sessions(["full", "lean"])
    orders = {session.task_id: ("lean", "full") for session in sessions}
    paired = common("paired-1", ("full", "lean"), sessions, launch_orders=orders)
    path = written(tmp_path, PairedRun(paired, ("floor-1",), "underpowered", {}))

    text = moves_cli.report_text(path)

    assert text.startswith(f"Move {MOVE}: paired run paired-1")
    assert "role" not in text.splitlines()[0].lower()
    assert "Move run report" in text


def test_the_report_of_a_floor_run_states_its_floor_failures(tmp_path):
    path = written(tmp_path, floor_run("floor-1", sessions=kit_sessions(["floor"])))

    text = moves_cli.report_text(path)

    assert text.startswith(f"Move {MOVE}: floor run floor-1")
    assert "figure | commit message form | floor | 0 | 3" in text


# --- --continue, --close and --reindex: a run is found by its file in moves/ ---

STOPPED = Stopped(MoveStopReason("auth", "401", "floor", (Launched("t1", "floor", 1),), "one-arm"))  # type: ignore[arg-type]


@pytest.fixture
def stopped_in(tmp_path) -> Path:
    """A checkout whose move results hold one stopped floor run, ``floor-1``."""
    results.write(moves_dir(tmp_path), floor_run("floor-1", sessions=(), ending=STOPPED))
    return tmp_path


def test_a_run_is_a_moves_by_where_its_file_lives(stopped_in):
    subject = moves_cli.run_subject([str(stopped_in), "--close", "floor-1", "--reason", "x"])

    assert subject == moves_cli.MoveSubject(MoveName(MOVE))


def test_a_run_with_no_file_in_moves_is_left_to_the_role_path(stopped_in):
    assert moves_cli.run_subject([str(stopped_in), "--continue", "role-run-9"]) is None


def test_a_command_line_that_names_no_run_is_left_to_the_role_path(stopped_in):
    assert moves_cli.run_subject([str(stopped_in), "--reindex"]) is None


def test_closing_a_stopped_move_run_records_the_reason_in_its_own_file(stopped_in, capsys):
    code = cli.main([str(stopped_in), "--close", "floor-1", "--reason", "the credential lapsed"])

    ending = results.load(moves_dir(stopped_in) / "floor-1.json").common.ending
    assert (code, isinstance(ending, Closed), ending.reason) == (0, True, "the credential lapsed")
    assert "closed run floor-1: the credential lapsed" in capsys.readouterr().out


def test_a_closed_run_is_standing_closed_in_the_index(stopped_in):
    cli.main([str(stopped_in), "--close", "floor-1", "--reason", "gone"])

    index = json.loads((moves_dir(stopped_in) / "index.json").read_text(encoding="utf-8"))

    assert index["runs"]["floor-1"]["standing"] == "closed"


def test_a_run_that_did_not_stop_cannot_be_closed(tmp_path, capsys):
    results.write(moves_dir(tmp_path), floor_run("floor-1", sessions=()))

    code = cli.main([str(tmp_path), "--close", "floor-1", "--reason", "gone"])

    assert code == moves_cli.EXIT_USAGE
    assert "nothing to close" in capsys.readouterr().err


def test_a_close_without_a_reason_is_a_usage_error(stopped_in, capsys):
    with pytest.raises(SystemExit):
        cli.main([str(stopped_in), "--move", MOVE, "--close", "floor-1"])

    assert "--close RUN and --reason TEXT go together" in capsys.readouterr().err


def test_a_continuation_names_no_run_to_start(stopped_in, capsys):
    with pytest.raises(SystemExit):
        cli.main([str(stopped_in), "--continue", "floor-1", "--run", "floor"])

    assert "--continue RUN takes no --run" in capsys.readouterr().err


def test_a_continuation_carries_the_options_beside_it_into_its_plan(stopped_in, monkeypatch):
    plans: list[runner.RunPlan] = []
    rule = Path("rules/swe/vcs/git-conventions.md")  # the declaration reads the rule it moves
    (stopped_in / rule).parent.mkdir(parents=True)
    (stopped_in / rule).write_text((REPO_ROOT / rule).read_text(encoding="utf-8"), encoding="utf-8")

    def fake_conduct(plan):
        plans.append(plan)
        common = SimpleNamespace(run_id="floor-2", ending=Finished())
        run = SimpleNamespace(run_kind=plan.kind, common=common)
        return SimpleNamespace(path=plan.moves_dir / "floor-2.json", run=run)

    monkeypatch.setattr(runner, "conduct", fake_conduct)
    monkeypatch.setattr(moves_cli, "query_claude_version", lambda: "2.1.312")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    cli.main([str(stopped_in), "--continue", "floor-1", "--seed", "3", "--max-total-usd", "9"])

    assert (plans[0].continues, plans[0].supplied_options, plans[0].run_cap_usd) == (
        "floor-1",
        ("--seed", "--max-total-usd"),
        9.0,
    )


def test_reindexing_rebuilds_the_move_index_beside_its_files(stopped_in, capsys):
    (moves_dir(stopped_in) / "index.json").unlink()

    code = moves_cli.reindex(moves_dir(stopped_in).parent)

    assert (code, (moves_dir(stopped_in) / "index.json").exists()) == (0, True)
    assert "indexed" in capsys.readouterr().out


def test_reindexing_a_checkout_with_no_move_results_creates_nothing(tmp_path):
    assert moves_cli.reindex(tmp_path / "adherence") == 0
    assert not (tmp_path / "adherence").exists()


def test_the_report_of_a_continued_floor_run_counts_the_sessions_of_its_whole_lineage(tmp_path):
    written(tmp_path, floor_run("floor-1", sessions=kit_sessions(["floor"]), ending=STOPPED))
    path = written(
        tmp_path, floor_run("floor-2", sessions=kit_sessions(["floor"]), continues="floor-1")
    )

    text = moves_cli.report_text(path)

    assert "figure | commit message form | floor | 0 | 6" in text
