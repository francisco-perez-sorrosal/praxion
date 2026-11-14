"""A paired run of the move declines what it does not support, and costs the ordinary comparison nothing.

Asked to continue a stopped run, to calibrate, or to run an arm of the ordinary comparison, a
paired run refuses before it writes or launches anything, naming the option; for a stopped paired
run it says to close it and start a fresh one. Closing, listing and reporting a paired run work as
for any run, and an ordinary run beside a paired one starts and lists as it always has.

Every session is a stand-in, so nothing here is paid for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers import paired_move_runs as paired

ROLE = "implementer"
REASON = "the paired run was stopped by a spent credit balance; a fresh one replaces it"
USAGE_LINE = re.compile(r"^usage: ", re.MULTILINE)
CRASH = "Traceback (most recent call last)"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return paired.new_checkout(tmp_path)


@pytest.fixture
def stopped(tmp_path: Path, checkout: Path) -> paired.PairedRun:
    return paired.stopped_paired_run(tmp_path, checkout, ROLE)


def assert_refused_before_anything(
    run: paired.PairedRun, written_before: dict[str, str], checkout: Path, named: str
) -> None:
    """The run's own refusal, naming `named`, with nothing launched and no results file touched.

    argparse rejecting the command line also exits non-zero with nothing launched, and its usage
    echo prints every option name, so the refusal must carry no usage line; a crash's traceback
    can print any name, so it must carry none either.
    """
    assert run.exit_code != 0, f"the paired run accepted {named}"
    assert run.launches == (), f"a session launched before the refusal of {named}"
    assert not USAGE_LINE.search(run.printed), f"argparse rejected the command: {run.printed}"
    assert CRASH not in run.printed, f"the run crashed instead of refusing: {run.printed}"
    assert named in run.printed, f"the refusal does not name {named}: {run.printed}"
    assert paired.results_snapshot(checkout) == written_before, "the refused run wrote results"


# -- Refused before anything is written or launched ---------------------------------------------


def test_continuing_a_stopped_paired_run_is_refused_and_told_to_close_it_and_start_afresh(
    tmp_path: Path, checkout: Path, stopped: paired.PairedRun
) -> None:
    paired.assert_stopped(stopped)
    written = paired.results_snapshot(checkout)

    asked = paired.run_paired(
        tmp_path, checkout, ROLE, extra_args=("--continue", stopped.results_path.stem)
    )

    assert_refused_before_anything(asked, written, checkout, "--continue")
    assert re.search(r"\bclos", asked.printed, re.IGNORECASE), asked.printed
    assert re.search(r"\b(fresh|new)\b", asked.printed, re.IGNORECASE), asked.printed


def test_calibrating_a_paired_run_is_refused_before_anything_is_written_or_launched(
    tmp_path: Path, checkout: Path
) -> None:
    written = paired.results_snapshot(checkout)

    asked = paired.run_paired(tmp_path, checkout, ROLE, extra_args=("--calibration",))

    assert_refused_before_anything(asked, written, checkout, "--calibration")


@pytest.mark.parametrize(
    ("arms", "ordinary_arm"),
    [(("preloaded", "full"), "full"), (("delivered", "lean"), "lean")],
)
def test_a_paired_run_asked_for_an_arm_of_the_ordinary_comparison_is_refused_naming_it(
    tmp_path: Path, checkout: Path, arms: tuple[str, str], ordinary_arm: str
) -> None:
    written = paired.results_snapshot(checkout)

    asked = paired.run_paired(tmp_path, checkout, ROLE, arms=arms)

    assert_refused_before_anything(asked, written, checkout, ordinary_arm)


# -- Closed, listed and reported as any run ------------------------------------------------------


def test_a_stopped_paired_run_closed_with_a_reason_is_listed_by_the_next_paired_run(
    tmp_path: Path, checkout: Path, stopped: paired.PairedRun
) -> None:
    paired.assert_stopped(stopped)
    closed = paired.close(tmp_path, checkout, stopped.results_path, REASON)

    fresh = paired.run_paired(
        tmp_path, checkout, ROLE, paired.every_session_ends_in(paired.credit_exhausted())
    )
    listed = runs.earlier_runs(fresh.results_path, ROLE)

    assert closed == 0, "the stopped paired run could not be closed with a reason"
    assert fresh.launches, "no session launched after the stopped paired run was closed"
    assert [(d.run_ids, d.interim) for d in listed.draws] == [((stopped.results_path.stem,), True)]


def test_a_stopped_paired_run_is_reported_as_any_run_is(
    tmp_path: Path, stopped: paired.PairedRun
) -> None:
    paired.assert_stopped(stopped)
    rendering = paired.report(tmp_path, stopped.results_path)

    assert rendering.exit_code == 0, rendering.stderr[-2000:]
    assert [ln for ln in rendering.text.splitlines() if ln.startswith(f"Role {ROLE}:")], (
        f"the report has no line for {ROLE}:\n{rendering.text[:2000]}"
    )


# -- The ordinary comparison is unchanged ---------------------------------------------------------


def test_an_ordinary_run_beside_a_stopped_paired_run_starts_and_lists_no_paired_run(
    tmp_path: Path, checkout: Path, stopped: paired.PairedRun
) -> None:
    paired.assert_stopped(stopped)
    ordinary = runs.run_with_stand_in(
        tmp_path, checkout, runs.Plan(role=ROLE, max_tasks=1), runs.Script()
    )
    listed = runs.earlier_runs(ordinary.results_path, ROLE)
    named = [
        *(run_id for draw in listed.draws for run_id in draw.run_ids),
        *listed.apart,
        *listed.calibration,
    ]

    assert ordinary.launches, f"the ordinary run did not start: {ordinary.stderr[-2000:]}"
    assert stopped.results_path.stem not in named
