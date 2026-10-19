"""A run's lineage is parsed from its results directory: the parts of one declared run, oldest
first, refused when they fork, loop or leave a gap. A stopped run left neither continued nor closed
is found by its role, and closing one records why."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from praxion_evals.adherence import results
from praxion_evals.adherence.lineage import (
    Finished,
    Interrupted,
    Lineage,
    PartRef,
    ReadTip,
    RunEnding,
    SpendRefused,
    close,
    continuable,
    ending_of,
    ending_to_json,
    pending_stop,
)
from tests.lineage_support import (
    closed_ending,
    identity,
    infra_stop,
    read_tip,
    write_part,
)
from tests.test_adherence_report import results_of
from tests.test_adherence_results import pair_of_sessions

# ---------------------------------------------------------------------------
# A run's lineage: the parts of one declared run
# ---------------------------------------------------------------------------


def _ids(chain: Lineage) -> list[str]:
    return [part.run_id for part in chain.parts]


def test_a_run_nothing_continues_is_a_lineage_of_one_part(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")

    chain = Lineage.parse(tmp_path, "run-a")

    assert (_ids(chain), chain.tip.run_id) == (["run-a"], "run-a")


@pytest.mark.parametrize("named", ["run-a", "run-b", "run-c"])
def test_any_part_names_the_whole_lineage_oldest_first(tmp_path: Path, named: str) -> None:
    write_part(tmp_path, "run-c", continues="run-b")
    write_part(tmp_path, "run-a")
    write_part(tmp_path, "run-b", continues="run-a")

    assert _ids(Lineage.parse(tmp_path, named)) == ["run-a", "run-b", "run-c"]


def test_only_the_latest_part_is_the_tip(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")
    write_part(tmp_path, "run-b", continues="run-a")

    assert Lineage.parse(tmp_path, "run-a").tip.run_id == "run-b"


def test_a_part_remembers_its_file_and_the_run_it_continues(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")
    write_part(tmp_path, "run-b", continues="run-a")

    first, second = Lineage.parse(tmp_path, "run-b").parts

    assert (first, second) == (
        PartRef("run-a", tmp_path / "run-a.json", None),
        PartRef("run-b", tmp_path / "run-b.json", "run-a"),
    )


def test_runs_that_are_not_in_the_lineage_are_left_out(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")
    write_part(tmp_path, "run-b", continues="run-a")
    write_part(tmp_path, "run-elsewhere")

    assert _ids(Lineage.parse(tmp_path, "run-a")) == ["run-a", "run-b"]


def test_a_json_file_that_is_not_a_results_file_does_not_break_a_lineage(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")
    (tmp_path / "stray.json").write_text("[1, 2]", encoding="utf-8")

    assert _ids(Lineage.parse(tmp_path, "run-a")) == ["run-a"]


@pytest.mark.parametrize("named", ["run-a", "run-b", "run-c"])
def test_a_lineage_where_two_parts_continue_one_is_refused_whichever_part_is_named(
    tmp_path: Path, named: str
) -> None:
    write_part(tmp_path, "run-a")
    write_part(tmp_path, "run-b", continues="run-a")
    write_part(tmp_path, "run-c", continues="run-a")

    with pytest.raises(ValueError, match=r"forks: run-b, run-c all continue run-a"):
        Lineage.parse(tmp_path, named)


def test_a_part_continuing_a_run_no_file_holds_is_a_gap(tmp_path: Path) -> None:
    write_part(tmp_path, "run-b", continues="run-lost")

    with pytest.raises(ValueError, match=r"gap: run run-b continues run-lost"):
        Lineage.parse(tmp_path, "run-b")


def test_a_predecessor_that_cannot_be_read_is_a_gap(tmp_path: Path) -> None:
    (tmp_path / "run-a.json").write_text("{not json", encoding="utf-8")
    write_part(tmp_path, "run-b", continues="run-a")

    with pytest.raises(ValueError, match=r"gap: run run-b continues run-a"):
        Lineage.parse(tmp_path, "run-b")


def test_parts_that_continue_each_other_are_refused_as_a_loop(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a", continues="run-b")
    write_part(tmp_path, "run-b", continues="run-a")

    with pytest.raises(ValueError, match=r"loops"):
        Lineage.parse(tmp_path, "run-a")


def test_a_run_no_file_holds_has_no_lineage(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")

    with pytest.raises(ValueError, match=r"holds run run-missing"):
        Lineage.parse(tmp_path, "run-missing")


def test_two_files_holding_one_run_are_refused(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a")
    (tmp_path / "copy.json").write_text((tmp_path / "run-a.json").read_text(), encoding="utf-8")

    with pytest.raises(ValueError, match=r"copy.json and run-a.json both hold run run-a"):
        Lineage.parse(tmp_path, "run-a")


def test_a_lineage_has_a_part() -> None:
    with pytest.raises(ValueError, match=r"at least one part"):
        Lineage(())


def test_a_lineage_built_out_of_order_is_refused() -> None:
    first = PartRef("run-a", Path("run-a.json"), None)
    second = PartRef("run-b", Path("run-b.json"), "run-a")

    with pytest.raises(ValueError, match=r"run run-b continues 'run-a', not its predecessor None"):
        Lineage((second, first))


# ---------------------------------------------------------------------------
# A stopped run left neither continued nor closed
# ---------------------------------------------------------------------------


def test_the_stopped_run_of_a_role_that_nothing_resolved_is_pending(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a", ending=Finished())
    write_part(tmp_path, "run-b", ending=infra_stop())

    pending = pending_stop(tmp_path, "researcher")

    assert pending == PartRef("run-b", tmp_path / "run-b.json", None)


def test_a_stop_of_another_role_is_not_pending_for_this_one(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a", ending=infra_stop())

    assert pending_stop(tmp_path, "verifier") is None


def test_nothing_is_pending_in_a_directory_with_no_stopped_run(tmp_path: Path) -> None:
    write_part(tmp_path, "run-a", ending=Finished())
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")

    assert pending_stop(tmp_path, "researcher") is None


@pytest.mark.parametrize(
    "ending",
    [infra_stop("one-arm"), Interrupted(), closed_ending(), None],
    ids=["one-arm stop", "interrupt", "closed", "recorded before endings"],
)
def test_a_run_that_was_not_continuable_when_it_stopped_blocks_nothing(
    tmp_path: Path, ending: RunEnding | None
) -> None:
    write_part(tmp_path, "run-a", ending=ending)

    assert pending_stop(tmp_path, "researcher") is None


def test_a_stop_that_was_continued_is_resolved_and_a_continuation_that_stopped_is_pending(
    tmp_path: Path,
) -> None:
    write_part(tmp_path, "run-a", ending=infra_stop())
    write_part(tmp_path, "run-b", continues="run-a", ending=SpendRefused(("task-1",)))

    assert pending_stop(tmp_path, "researcher") == PartRef(
        "run-b", tmp_path / "run-b.json", "run-a"
    )

    write_part(tmp_path, "run-c", continues="run-b", ending=Finished())

    assert pending_stop(tmp_path, "researcher") is None


# ---------------------------------------------------------------------------
# Closing a stopped run
# ---------------------------------------------------------------------------

CLOSED_AT = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


def test_closing_a_stopped_run_records_the_reason_the_time_and_the_ending_it_closes() -> None:
    stopped = infra_stop()

    closed = close(read_tip(stopped), "the credential is gone for good", CLOSED_AT)

    assert (closed.reason, closed.at, closed.stopped) == (
        "the credential is gone for good",
        "2026-10-17T09:00:00+00:00",
        stopped,
    )
    assert not continuable(closed)


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_close_without_a_reason_is_refused(reason: str) -> None:
    with pytest.raises(ValueError, match="closing a run needs a reason"):
        close(read_tip(infra_stop()), reason, CLOSED_AT)


def test_a_close_at_a_time_that_names_no_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="must carry a UTC offset"):
        close(read_tip(infra_stop()), "gone", datetime(2026, 10, 17, 9, 0))


@pytest.mark.parametrize(
    "ending", [Finished(), closed_ending(), None], ids=["finished", "closed", "recorded before"]
)
def test_a_run_that_did_not_stop_cannot_be_closed(ending: RunEnding | None) -> None:
    with pytest.raises(ValueError, match="did not stop"):
        close(read_tip(ending), "gone", CLOSED_AT)


def test_only_the_latest_part_of_a_lineage_can_be_closed() -> None:
    with pytest.raises(ValueError, match="continued by run-b"):
        close(read_tip(infra_stop(), continued_by="run-b"), "gone", CLOSED_AT)


def test_the_closed_ending_carries_the_per_check_result_the_run_had_reached() -> None:
    pairs = [s for task in ("task-0", "task-1") for s in pair_of_sessions(task)]
    ending = {"ending": ending_to_json(infra_stop())}
    tip = ReadTip(results_of(pairs, required_pairs=2, extra=ending), identity())

    interim = close(tip, "gone", CLOSED_AT).interim

    assert interim == {"researcher.C1": "clear", "researcher.C3": "clear"}


def test_a_role_short_of_pairs_is_carried_as_underpowered() -> None:
    ending = {"ending": ending_to_json(infra_stop())}
    tip = ReadTip(results_of([], required_pairs=2, extra=ending), identity())

    assert close(tip, "gone", CLOSED_AT).interim == {"researcher": "underpowered"}


def test_a_closed_ending_survives_the_results_file(tmp_path: Path) -> None:
    closed = close(read_tip(infra_stop()), "gone", CLOSED_AT)
    write_part(tmp_path, "run-a", ending=closed)

    assert ending_of(results.load(tmp_path / "run-a.json")) == closed
