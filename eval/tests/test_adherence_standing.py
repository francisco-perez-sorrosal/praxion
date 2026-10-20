"""The standing a results file records: what its whole lineage stands on, per role.

The value and its codec live in ``results``; the one function that builds it from a lineage's parts
lives in ``run_index``; a run's finalize and a close write it into the file they write anyway.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import results, run_index
from praxion_evals.adherence.model import Measured, Passed
from praxion_evals.adherence.results import RoleStanding
from tests.adherence_run_support import (
    REASON,
    ROLE,
    STOPPED_BOTH_ARMS,
    Script,
    close_run,
    ended_as,
    run_small,
)
from tests.test_adherence_results import (
    declared,
    pair_of_sessions,
    run_results,
    session,
    write_run,
)

pytestmark = pytest.mark.usefixtures("full_first", "unswitched_checkout")

RESEARCHER = "researcher"
CLOSED = {
    "kind": "closed",
    "reason": "the credit was cut off",
    "at": "2026-10-12T10:00:00+00:00",
    "interim": {},
    "stopped": {"kind": "interrupted"},
}


def standing(**changes: object) -> RoleStanding:
    fields: dict[str, object] = {
        "lineage_root": "run-a",
        "parts": ("run-a",),
        "complete_pairs": 2,
        "flip": "clear",
        "scored_checks": ("C1", "C3"),
    }
    return RoleStanding(**{**fields, **changes})  # type: ignore[arg-type]


def standing_json() -> dict[str, object]:
    return {
        "lineage_root": "run-a",
        "parts": ["run-a"],
        "complete_pairs": 1,
        "flip": "clear",
        "scored_checks": ["C1"],
    }


def continued_run(directory: Path, **tip_extra: object) -> None:
    write_run(directory, "part-1", [*pair_of_sessions("t1")], settings=declared(2))
    write_run(
        directory,
        "part-2",
        [*pair_of_sessions("t2")],
        settings=declared(2),
        extra={"continues": "part-1", **tip_extra},
    )


def standing_written(directory: Path, run_id: str) -> RoleStanding:
    """The standing a run finalized with ``run_id`` would write, over the directory's parts."""
    written = results.load(directory / f"{run_id}.json")
    return run_index.standing_ending_at(directory, written)[RESEARCHER]


# ---------------------------------------------------------------------------
# The value and its codec
# ---------------------------------------------------------------------------


def test_a_recorded_standing_round_trips_through_the_results_file(tmp_path: Path):
    recorded = replace(run_results([*pair_of_sessions("t1")]), standing={RESEARCHER: standing()})
    path = tmp_path / "run.json"

    results.write_atomic(path, recorded)

    assert results.load(path) == recorded
    assert json.loads(path.read_text())["standing"] == {
        RESEARCHER: {
            "lineage_root": "run-a",
            "parts": ["run-a"],
            "complete_pairs": 2,
            "flip": "clear",
            "scored_checks": ["C1", "C3"],
        }
    }


def test_a_file_without_a_standing_loads_as_none_and_reserializes_without_the_key(tmp_path: Path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(results.to_json(run_results([*pair_of_sessions("t1")]))) + "\n")
    assert "standing" not in json.loads(path.read_text())

    loaded = results.load(path)

    assert loaded.standing is None
    assert "standing" not in results.to_json(loaded)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"scored_checks": ("C3", "C1")}, "sorted and unique"),
        ({"scored_checks": ("C1", "C1")}, "sorted and unique"),
        ({"flip": "underpowered"}, "scored no check"),
        ({"parts": ()}, "names the parts"),
        ({"lineage_root": "run-b"}, "first part"),
        ({"complete_pairs": -1}, "not negative"),
        ({"flip": "maybe"}, "flip is one of"),
    ],
)
def test_a_standing_that_breaks_an_invariant_is_refused(changes: dict, message: str):
    with pytest.raises(ValueError, match=message):
        standing(**changes)


def test_a_lineage_that_ended_closed_stands_not_clear_or_is_refused():
    with pytest.raises(ValueError, match="ended closed"):
        RoleStanding.of(("run-a",), 2, "clear", ("C1",), closed=True)


@pytest.mark.parametrize(
    "malformed",
    [
        ["not", "an", "object"],
        {RESEARCHER: "not an object"},
        {RESEARCHER: {"lineage_root": "run-a", "parts": ["run-a"], "flip": "clear"}},
        {RESEARCHER: {**standing_json(), "parts": "run-a"}},
        {RESEARCHER: {**standing_json(), "complete_pairs": True}},
        {RESEARCHER: {**standing_json(), "scored_checks": ["C3", "C1"]}},
        {"verifier": standing_json()},
    ],
)
def test_a_file_whose_recorded_standing_is_malformed_is_refused(malformed: object):
    document = results.to_json(run_results([*pair_of_sessions("t1")]))
    document["standing"] = malformed

    with pytest.raises(ValueError, match="standing"):
        results.from_json(document)


# ---------------------------------------------------------------------------
# What a lineage stands on
# ---------------------------------------------------------------------------


def test_a_run_of_one_part_stands_on_its_own_pairs_flip_and_scored_checks(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])

    assert standing_written(tmp_path, "run-a") == RoleStanding(
        "run-a", ("run-a",), 1, "clear", ("C1", "C3")
    )


def test_a_continued_run_records_the_standing_of_its_whole_lineage(tmp_path: Path):
    continued_run(tmp_path)

    assert standing_written(tmp_path, "part-2") == RoleStanding(
        "part-1", ("part-1", "part-2"), 2, "clear", ("C1", "C3")
    )


def test_a_part_that_ends_a_lineage_leaves_the_parts_after_it_out(tmp_path: Path):
    continued_run(tmp_path)

    assert standing_written(tmp_path, "part-1").parts == ("part-1",)


def test_a_part_stands_in_for_the_file_of_its_run_already_in_the_directory(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    longer = run_results([*pair_of_sessions("t1"), *pair_of_sessions("t2")], run_id="run-a")

    stood = run_index.standing_ending_at(tmp_path, longer)[RESEARCHER]

    assert stood.complete_pairs == 2


def test_a_lineage_closed_on_request_reads_not_clear_however_its_pairs_read(tmp_path: Path):
    continued_run(tmp_path, ending=CLOSED)

    stood = standing_written(tmp_path, "part-2")

    assert (stood.flip, stood.complete_pairs) == ("not clear", 2)


def test_a_role_whose_verdict_gives_no_per_check_verdict_scored_no_check(tmp_path: Path):
    unmeasured = Measured({"C9": Passed()}, 1000)  # a check the catalog does not score
    sessions = [session("t1", arm, unmeasured) for arm in ("full", "lean")]
    write_run(tmp_path, "run-a", sessions)

    stood = standing_written(tmp_path, "run-a")

    assert (stood.complete_pairs, stood.scored_checks) == (1, ())


def test_an_underpowered_role_scored_no_check(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")], settings=declared(5))

    stood = standing_written(tmp_path, "run-a")

    assert (stood.flip, stood.scored_checks) == ("underpowered", ())


# ---------------------------------------------------------------------------
# Finalize and close write it in the one write of their file
# ---------------------------------------------------------------------------


def test_a_finalized_run_records_the_standing_its_verdict_gives(
    paid: Callable[[Script], None], tmp_path: Path
):
    paid(Script())

    code, run = run_small(tmp_path)

    document = json.loads((tmp_path / "out.json").read_text())
    verdict = document["verdicts"][ROLE]
    scored = sorted(set(verdict["check_verdicts"]) - set(verdict["not_covered"]))
    recorded = run.standing[ROLE]  # type: ignore[index]
    assert code == 0
    assert (recorded.parts, recorded.complete_pairs) == ((run.run.id,), verdict["complete_pairs"])
    assert (recorded.flip, list(recorded.scored_checks)) == (verdict["flip"], scored)


def test_a_finalize_rewrites_no_results_file_already_written(
    paid: Callable[[Script], None], tmp_path: Path
):
    paid(Script())
    write_run(tmp_path, "earlier", [*pair_of_sessions("t1")])
    before = (tmp_path / "earlier.json").read_bytes()

    run_small(tmp_path)

    assert (tmp_path / "earlier.json").read_bytes() == before


def test_closing_a_stopped_run_records_not_clear_in_its_own_file_and_no_other(
    paid: Callable[[Script], None], tmp_path: Path
):
    paid(Script())
    write_run(tmp_path, "earlier", [*pair_of_sessions("t1")])
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)
    before = (tmp_path / "earlier.json").read_bytes()

    close_run(tmp_path, stopped.run.id, "--reason", REASON)

    recorded = results.load(tmp_path / "stopped.json").standing[ROLE]  # type: ignore[index]
    assert (recorded.parts, recorded.flip) == ((stopped.run.id,), "not clear")
    assert (tmp_path / "earlier.json").read_bytes() == before
