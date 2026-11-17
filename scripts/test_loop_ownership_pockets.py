"""Tests for how the gate asks who owns a red node that a non-root pocket's run printed.

A plan's `Read-only:` entry names a node as the repository does (`eval/tests/x.py::t`), while a
run inside the `eval` pocket prints it relative to the pocket (`tests/x.py::t`). The scope's
runs and the `Check:` run are read through `Ownership.in_pocket`, which puts the pocket's
directory in front of the id before any entry is compared.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record_gate as gating  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_io import CommandRun  # noqa: E402
from _step_loop_ownership import Ownership, repository_form  # noqa: E402
from _step_loop_pocket_runs import CutOff, Finished, NotStarted, PocketBound  # noqa: E402

STEP = "Step "
POCKET = "eval"
POCKET_NODE = "tests/test_x.py::test_t"
REPO_NODE = f"{POCKET}/{POCKET_NODE}"
RED_OUTPUT = f"FAILED {POCKET_NODE} - assert 0\n== 1 failed, 2 passed in 0.10s =="
LOG = Path("/repo/.ai-work/demo/gate/s1/1.log")
FAILING_CHECK = f"uv run --project {POCKET} pytest -q"
CHECK_ARGV = tuple(FAILING_CHECK.split())


def owned_by_later_step(*entries: str) -> Ownership:
    return Ownership("1", {"1": (), "2": entries}, frozenset())


def read_in(pocket: str, rule):
    run = Finished(pocket, ("pytest",), 1, RED_OUTPUT, LOG)
    return gating.read_observed(pocket, run, rule)


def step_checking(command: str):
    plan = f"### {STEP}1: t\n\n**Check**: `{command}` expects pass>=1 fail=0\n"
    (step,) = parse_plan_steps(plan)
    return step


def check_failing(rule, tmp_path, monkeypatch):
    ran = CommandRun(CHECK_ARGV, str(tmp_path), RED_OUTPUT, 1)
    monkeypatch.setattr(gating, "bounded_check", lambda *_: ran)
    run = gating.check_run(tmp_path, tmp_path / "gate", step_checking(FAILING_CHECK), rule, 0.0)
    assert run is not None
    return run


def test_the_same_node_id_is_pending_in_the_pocket_that_holds_it_and_not_in_the_root() -> None:
    rule = owned_by_later_step(REPO_NODE)

    asked = (
        rule.in_pocket(POCKET).is_pending(POCKET_NODE),
        rule.in_pocket(".").is_pending(POCKET_NODE),
    )

    assert asked == (True, False)


def test_an_errored_node_is_owned_in_the_pocket_like_a_failed_one() -> None:
    rule = owned_by_later_step(REPO_NODE)

    assert rule.in_pocket(POCKET).is_pending_error(POCKET_NODE) is True


@pytest.mark.parametrize("spelling", [POCKET, f"{POCKET}/", f"./{POCKET}"])
def test_a_pocket_is_joined_whatever_way_it_is_spelled(spelling: str) -> None:
    assert repository_form(spelling, POCKET_NODE) == REPO_NODE


@pytest.mark.parametrize("root", [".", ""])
def test_the_root_pocket_leaves_a_node_id_as_it_is(root: str) -> None:
    assert repository_form(root, POCKET_NODE) == POCKET_NODE


def test_a_node_a_later_step_owns_in_a_pocket_run_is_pending_and_names_no_failure() -> None:
    reading = read_in(POCKET, owned_by_later_step(REPO_NODE))

    assert (reading.finished.pending, reading.failures) == (1, ())


def test_a_node_nobody_owns_in_a_pocket_run_still_fails_named_as_the_repository_does() -> None:
    reading = read_in(POCKET, owned_by_later_step())

    assert (reading.finished.pending, reading.failures) == (0, (REPO_NODE,))


def test_an_entry_spelled_relative_to_the_pocket_owns_nothing_of_it() -> None:
    reading = read_in(POCKET, owned_by_later_step(POCKET_NODE))

    assert reading.failures == (REPO_NODE,)


def test_a_check_in_a_pocket_reads_a_node_a_later_step_owns_as_pending(
    tmp_path, monkeypatch
) -> None:
    run = check_failing(owned_by_later_step(REPO_NODE), tmp_path, monkeypatch)

    assert (run.pending, run.failed_ids, run.red) == (1, (), False)


def test_a_check_in_a_pocket_names_a_node_nobody_owns_as_the_repository_does(
    tmp_path, monkeypatch
) -> None:
    run = check_failing(owned_by_later_step(), tmp_path, monkeypatch)

    assert (run.pending, run.failed_ids, run.red) == (0, (REPO_NODE,), True)


def pending_in(pocket: str) -> gating.GateRun:
    rule = owned_by_later_step(repository_form(pocket, POCKET_NODE))
    return read_in(pocket, rule).finished


def test_the_same_relative_id_pending_in_two_pockets_counts_twice_once_merged() -> None:
    merged = gating.merge_finished((pending_in("."), pending_in(POCKET)))

    assert (merged.pending, merged.pending_ids) == (2, (POCKET_NODE, REPO_NODE))


@pytest.mark.parametrize(
    "observed",
    [
        pytest.param(
            CutOff(PocketBound(POCKET, 1.0, "default"), ("pytest",), (), RED_OUTPUT, LOG),
            id="cut-off",
        ),
        pytest.param(NotStarted(POCKET, "no interpreter", RED_OUTPUT), id="not-started"),
    ],
)
def test_a_run_that_did_not_finish_asks_a_real_ownership_in_its_pocket(observed) -> None:
    reading = gating.read_observed(POCKET, observed, owned_by_later_step(REPO_NODE))

    assert (reading.failures, reading.finished) == ((), None)


def check_printing(command: str, output: str, rule, tmp_path, monkeypatch):
    ran = CommandRun(tuple(command.split()), str(tmp_path), output, 1)
    monkeypatch.setattr(gating, "bounded_check", lambda *_: ran)
    return gating.check_run(tmp_path, tmp_path / "gate", step_checking(command), rule, 0.0)


def test_a_check_naming_its_pocket_by_an_absolute_path_owns_its_nodes_as_the_repository_does(
    tmp_path, monkeypatch
) -> None:
    absolute = f"uv run --directory {tmp_path / POCKET} pytest -q"

    run = check_printing(
        absolute, RED_OUTPUT, owned_by_later_step(REPO_NODE), tmp_path, monkeypatch
    )

    assert (run.pending, run.failed_ids) == (1, ())


@pytest.mark.xfail(
    strict=True,
    reason="`uv run --project` keeps the working directory, so pytest's rootdir, not the option,"
    " decides the form of the ids it prints; reading it needs a design choice",
)
def test_a_check_whose_project_option_keeps_the_working_directory_names_each_node_once(
    tmp_path, monkeypatch
) -> None:
    repository_ids = RED_OUTPUT.replace(POCKET_NODE, REPO_NODE)

    run = check_printing(
        FAILING_CHECK, repository_ids, owned_by_later_step(), tmp_path, monkeypatch
    )

    assert run.failed_ids == (REPO_NODE,)


def test_a_rule_that_knows_no_pockets_is_asked_the_pocket_relative_id() -> None:
    class PocketRelative:
        def is_pending(self, node_id: str) -> bool:
            return node_id == POCKET_NODE

        def is_pending_error(self, node_id: str) -> bool:
            return False

    assert read_in(POCKET, PocketRelative()).failures == ()
