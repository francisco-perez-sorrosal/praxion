"""A stopped run of the paired move has a life as a run: it is read back, closed with a reason,
listed beside the runs of its axis and reindexed, while a continuation of it is refused, before
anything is written, in the ruling's words. Each run here is built with the model's own types."""

from __future__ import annotations

import pytest

from praxion_evals.adherence import cli, results
from praxion_evals.adherence.infra_stop import Launched, StopReason
from praxion_evals.adherence.lineage import (
    Closed,
    InfraStopped,
    SpendRefused,
    ending_from_json,
    ending_of,
    ending_to_json,
    pending_stop,
)
from tests.adherence_run_support import (
    PAIRED,
    PAIRED_ROLE,
    REASON,
    TASKS,
    cli_in,
    planted,
    snapshot,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")

ROLE = PAIRED_ROLE
RULING = (
    "run {id} cannot be continued: --continue takes no run of the refactoring-delivery axis;"
    " close it (--close {id} --reason TEXT) and start a fresh run"
)


def _stop(arm: str = "preloaded", scope: str = "both-arms") -> InfraStopped:
    sessions = tuple(Launched(task, arm, 1) for task in TASKS)  # type: ignore[arg-type]
    return InfraStopped(StopReason("result_error", "credit", ROLE, arm, sessions, scope))  # type: ignore[arg-type]


# --- a stopped paired run is read back ---


@pytest.mark.parametrize("ending", [_stop("preloaded"), _stop("delivered", "one-arm")])
def test_a_stop_in_an_arm_of_the_paired_axis_is_read_back_as_written(ending, tmp_path):
    directory = planted(tmp_path, "paired-1", PAIRED, ending)

    assert ending_from_json(ending_to_json(ending)) == ending
    assert ending_of(results.load(directory / "paired-1.json")) == ending


@pytest.mark.parametrize("field", ["arm", "session"])
def test_a_stop_naming_an_arm_of_no_axis_is_still_refused(field):
    document = ending_to_json(_stop())
    if field == "arm":
        document["arm"] = "partial"
    else:
        document["sessions"][0]["arm"] = "partial"

    with pytest.raises(ValueError, match="unknown arm 'partial'"):
        ending_from_json(document)


# --- it is closed, listed and reindexed ---


def test_a_stopped_paired_run_is_closed_with_a_reason_and_keeps_its_axis(tmp_path):
    stopped = _stop()
    directory = planted(tmp_path, "paired-1", PAIRED, stopped)

    code = cli_in(directory, "--close", "paired-1", "--reason", REASON)

    closed = results.load(directory / "paired-1.json")
    ending = ending_of(closed)
    assert code == 0
    assert isinstance(ending, Closed)
    assert (ending.reason, ending.stopped) == (REASON, stopped)
    assert closed.run.extra["axis"] == PAIRED


def test_a_closed_paired_run_is_listed_as_an_earlier_draw_of_the_paired_axis_only(tmp_path):
    directory = planted(tmp_path, "paired-1", PAIRED, _stop())
    assert cli_in(directory, "--close", "paired-1", "--reason", REASON) == 0

    paired = results.earlier_runs(directory, (ROLE,), lambda earlier, role: (), axis=PAIRED)
    default = results.earlier_runs(directory, (ROLE,), lambda earlier, role: ())

    assert [draw.run_ids for draw in paired.by_role[ROLE].draws] == [("paired-1",)]
    assert default.by_role[ROLE].draws == ()
    assert default.skipped_files == paired.skipped_files == ()


def test_reindexing_lists_a_stopped_paired_run(tmp_path):
    directory = planted(tmp_path, "paired-1", PAIRED, _stop())

    code = cli.main([str(tmp_path), "--reindex"])

    index = (directory / "index.json").read_text()
    assert code == 0
    assert "paired-1" in index


# --- it blocks its role until closed, and is not continued ---


def test_a_stopped_paired_run_blocks_a_fresh_run_of_its_role_until_it_is_closed(tmp_path):
    directory = planted(tmp_path, "paired-1", PAIRED, SpendRefused(TASKS))

    blocking = pending_stop(directory, ROLE, PAIRED)
    assert blocking is not None
    assert blocking.run_id == "paired-1"

    assert cli_in(directory, "--close", "paired-1", "--reason", REASON) == 0
    assert pending_stop(directory, ROLE, PAIRED) is None


def test_continuing_a_stopped_paired_run_is_refused_in_the_rulings_words_and_writes_nothing(
    tmp_path, capsys
):
    directory = planted(tmp_path, "paired-1", PAIRED, _stop())
    before = snapshot(directory)

    code = cli_in(directory, "--continue", "paired-1")

    assert code == 2
    assert RULING.format(id="paired-1") in capsys.readouterr().err
    assert snapshot(directory) == before


def test_the_refusal_to_continue_a_paired_run_does_not_depend_on_how_it_stopped(tmp_path, capsys):
    directory = planted(tmp_path, "paired-1", PAIRED, SpendRefused(TASKS))

    assert cli_in(directory, "--continue", "paired-1") == 2
    assert RULING.format(id="paired-1") in capsys.readouterr().err


def test_continuing_a_stopped_default_run_is_not_refused_for_its_axis(tmp_path, capsys):
    directory = planted(tmp_path, "default-1", "inherited-context", SpendRefused(TASKS))

    cli_in(directory, "--continue", "default-1")

    assert "takes no run of the" not in capsys.readouterr().err
