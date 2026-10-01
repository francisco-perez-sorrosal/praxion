"""The spawn-count check proves the counter's tally matches spawns the hooks recorded.

The hooks write the log from a known set of simulated spawns (from a
subdirectory, a resume, a spawn naming no slug, a spawn for another slug), then
`scripts/spawn_count.py` counts it. The check passes only when the reported
spawns, resumes and agent ids for the slug equal the known set exactly, and a
slug no row names is withheld rather than counted as zero. Any difference,
an undercount included, fails the check and shows expected against reported.

Each dead counter below changes only `scripts/spawn_count.py`, in a scratch copy
of the repository.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tests.acceptance.drivers import dead_gates
from tests.acceptance.drivers.gate_liveness import (
    Gate,
    LivenessRun,
    RepoCopy,
    Verdict,
    make_copy,
    run_liveness,
)


def _run_spawn_check(copy: RepoCopy) -> tuple[LivenessRun, Verdict]:
    run = run_liveness(copy, [Gate.SPAWN_COUNT])
    return run, run.verdict(Gate.SPAWN_COUNT)


def _copy_with_dead_counter(tmp_path: Path, kill: Callable[[RepoCopy], None]) -> RepoCopy:
    copy = make_copy(tmp_path)
    kill(copy)
    copy.commit("dead spawn counter")
    return copy


def test_counter_tallying_hook_written_spawns_exactly_passes_the_check(tmp_path):
    run, verdict = _run_spawn_check(make_copy(tmp_path))

    assert verdict.passed, run.describe()
    assert run.exit_code == 0, run.describe()


def test_counter_attributing_spawns_by_checkout_name_fails_the_check_showing_both_tallies(
    tmp_path,
):
    copy = _copy_with_dead_counter(tmp_path, dead_gates.spawn_counter_attributes_by_checkout_name)

    run, verdict = _run_spawn_check(copy)

    assert not verdict.passed, run.describe()
    assert run.exit_code != 0, run.describe()
    assert "expected" in verdict.reason.lower(), (
        f"the failure should show the expected tally beside the reported one\n{run.describe()}"
    )


def test_counter_that_reports_nothing_fails_the_check(tmp_path):
    copy = _copy_with_dead_counter(tmp_path, dead_gates.spawn_counter_says_nothing)

    run, verdict = _run_spawn_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"


def test_counter_answering_an_unseen_slug_with_zero_fails_the_check(tmp_path):
    copy = _copy_with_dead_counter(tmp_path, dead_gates.spawn_counter_counts_unseen_slug_as_zero)

    run, verdict = _run_spawn_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"


def test_missing_counter_fails_the_check_and_says_why(tmp_path):
    copy = _copy_with_dead_counter(tmp_path, lambda c: c.remove(dead_gates.SPAWN_COUNT))

    run, verdict = _run_spawn_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"
