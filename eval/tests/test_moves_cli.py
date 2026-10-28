"""The move half of the entry: ``--move`` reaches it, its options are parsed once, and ``--dry-run``
prices the floor run and the paired run together without launching or writing anything."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from praxion_evals.adherence import cli
from praxion_evals.adherence.moves import cli as moves_cli

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
