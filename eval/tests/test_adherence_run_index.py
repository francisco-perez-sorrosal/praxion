"""The run index: one digest-checked entry per results file, written beside the files by a finished
run and by a close, and rebuilt from the files alone by ``--reindex``."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence import cli, report, results, run_index
from praxion_evals.adherence.lineage import parts_before
from praxion_evals.adherence.model import Errored, Measured, Passed
from praxion_evals.adherence.session_loop import OUTPUT_DIR
from tests.adherence_run_support import (
    REASON,
    ROLE,
    STOPPED_BOTH_ARMS,
    Script,
    close_run,
    ended_as,
    run_small,
)
from tests.test_adherence_results import declared, pair_of_sessions, session, write_run

pytestmark = pytest.mark.usefixtures("full_first", "unswitched_checkout")

REPOSITORY = Path(__file__).resolve().parents[2]
RECORDED = REPOSITORY / OUTPUT_DIR
INDEX = results.RUN_INDEX_NAME
CLOSED = {
    "kind": "closed",
    "reason": "the credit was cut off",
    "at": "2026-10-12T10:00:00+00:00",
    "interim": {},
    "stopped": {"kind": "interrupted"},
}


def indexed(directory: Path) -> dict[str, Any]:
    run_index.write_index(directory)
    return json.loads((directory / INDEX).read_text(encoding="utf-8"))


def continued_run(directory: Path, **tip_extra: Any) -> None:
    """A run in two parts that together make the two pairs it declared (neither part makes both)."""
    write_run(directory, "part-1", [*pair_of_sessions("t1")], settings=declared(2))
    write_run(
        directory,
        "part-2",
        [*pair_of_sessions("t2")],
        settings=declared(2),
        extra={"continues": "part-1", **tip_extra},
    )


# ---------------------------------------------------------------------------
# One entry per results file
# ---------------------------------------------------------------------------


def test_every_results_file_has_an_entry_naming_its_file_digest_root_and_ending(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")], extra={"ending": {"kind": "finished"}})
    write_run(tmp_path, "run-b", [*pair_of_sessions("t1")])

    entries = indexed(tmp_path)["runs"]

    assert list(entries) == ["run-a", "run-b"]
    assert entries["run-a"]["file"] == "run-a.json"
    assert entries["run-a"]["lineage_root"] == "run-a"
    assert (entries["run-a"]["ending"], entries["run-b"]["ending"]) == ("finished", "legacy")


def test_the_digest_is_the_sha256_of_the_files_bytes(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])

    digest = indexed(tmp_path)["runs"]["run-a"]["sha256"]

    assert digest == hashlib.sha256((tmp_path / "run-a.json").read_bytes()).hexdigest()


def test_the_digest_changes_with_the_file(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    before = indexed(tmp_path)["runs"]["run-a"]["sha256"]

    write_run(tmp_path, "run-a", [*pair_of_sessions("t1"), *pair_of_sessions("t2")])

    assert indexed(tmp_path)["runs"]["run-a"]["sha256"] != before


def test_each_role_carries_its_complete_pairs_and_flip_label(tmp_path: Path):
    both = [*pair_of_sessions("t1"), *pair_of_sessions("t2", role="verifier")]
    write_run(tmp_path, "run-a", both, roles=("researcher", "verifier"), settings=declared(1))

    roles = indexed(tmp_path)["runs"]["run-a"]["roles"]

    assert roles == {
        "researcher": {"complete_pairs": 1, "flip": "clear", "scored_checks": ["C1", "C3"]},
        "verifier": {"complete_pairs": 1, "flip": "clear", "scored_checks": ["C1", "C3"]},
    }


def test_a_role_short_of_its_declared_pairs_is_underpowered_with_the_pairs_it_has(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")], settings=declared(5))

    roles = indexed(tmp_path)["runs"]["run-a"]["roles"]

    assert roles == {
        "researcher": {"complete_pairs": 1, "flip": "underpowered", "scored_checks": []}
    }


def test_a_check_the_verdict_does_not_cover_is_not_listed_as_scored(tmp_path: Path):
    only_c1 = Measured({"C1": Passed()}, 1000)
    sessions = [session("t1", "full", only_c1), session("t1", "lean", only_c1)]
    write_run(tmp_path, "run-a", sessions)

    roles = indexed(tmp_path)["runs"]["run-a"]["roles"]

    assert roles["researcher"]["scored_checks"] == ["C1"]


def test_a_pair_with_an_errored_side_is_not_a_complete_pair(tmp_path: Path):
    errored = session("t2", "lean", Errored("timeout", "the session timed out"))
    sessions = [*pair_of_sessions("t1"), session("t2", "full"), errored]
    write_run(tmp_path, "run-a", sessions)

    roles = indexed(tmp_path)["runs"]["run-a"]["roles"]

    assert roles["researcher"]["complete_pairs"] == 1


# ---------------------------------------------------------------------------
# A continued run is one run; a closed run reached no verdict
# ---------------------------------------------------------------------------


def test_every_part_of_a_continued_run_carries_the_pairs_and_label_of_the_whole_lineage(
    tmp_path: Path,
):
    continued_run(tmp_path)

    entries = indexed(tmp_path)["runs"]

    whole = {"researcher": {"complete_pairs": 2, "flip": "clear", "scored_checks": ["C1", "C3"]}}
    assert (entries["part-1"]["roles"], entries["part-2"]["roles"]) == (whole, whole)


def test_every_part_names_the_root_of_its_lineage(tmp_path: Path):
    continued_run(tmp_path)

    entries = indexed(tmp_path)["runs"]

    assert (entries["part-1"]["lineage_root"], entries["part-2"]["lineage_root"]) == (
        "part-1",
        "part-1",
    )


def test_a_tips_recorded_listing_of_its_own_earlier_parts_is_not_read_as_another_draw(
    tmp_path: Path,
):
    listing = {"researcher": {"draws": [{"run_ids": ["part-1"], "flip": "underpowered"}]}}
    plain, listed = tmp_path / "plain", tmp_path / "listed"
    for directory, extra in ((plain, {}), (listed, {"earlier": listing})):
        directory.mkdir()
        continued_run(directory, **extra)

    assert indexed(listed)["runs"]["part-2"]["roles"] == indexed(plain)["runs"]["part-2"]["roles"]


def test_a_closed_run_is_not_clear_however_its_pairs_read(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")], extra={"ending": CLOSED})

    entry = indexed(tmp_path)["runs"]["run-a"]

    assert entry["ending"] == "closed"
    assert entry["roles"] == {
        "researcher": {"complete_pairs": 1, "flip": "not clear", "scored_checks": ["C1", "C3"]}
    }


def test_a_continued_run_whose_tip_was_closed_is_not_clear_in_every_part(tmp_path: Path):
    continued_run(tmp_path, ending=CLOSED)

    entries = indexed(tmp_path)["runs"]

    assert [entries[part]["roles"]["researcher"]["flip"] for part in ("part-1", "part-2")] == [
        "not clear",
        "not clear",
    ]


# ---------------------------------------------------------------------------
# Files that are not results files, and the index itself
# ---------------------------------------------------------------------------


def test_a_json_file_that_is_not_a_results_file_is_listed_apart_in_name_order(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    (tmp_path / "notes.json").write_text('{"not": "a results file"}')
    (tmp_path / "broken.json").write_text("{")

    document = indexed(tmp_path)

    assert document["skipped"] == ["broken.json", "notes.json"]
    assert list(document["runs"]) == ["run-a"]


def test_the_index_is_neither_a_run_nor_a_stray_file_when_it_is_rebuilt(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    indexed(tmp_path)

    document = indexed(tmp_path)

    assert (list(document["runs"]), document["skipped"]) == (["run-a"], [])


def test_a_listing_of_earlier_runs_does_not_name_the_index_as_a_stray_file(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    indexed(tmp_path)

    listing = results.earlier_runs(tmp_path, ("researcher",), lambda earlier, role: ())

    assert listing.skipped_files == ()


def test_two_files_holding_one_run_are_refused(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    shutil.copy(tmp_path / "run-a.json", tmp_path / "copy.json")

    with pytest.raises(ValueError, match="copy.json and run-a.json both hold run run-a"):
        run_index.write_index(tmp_path)


def test_an_empty_directory_has_an_index_of_nothing(tmp_path: Path):
    assert indexed(tmp_path) == {"schema": 2, "runs": {}, "skipped": []}


# ---------------------------------------------------------------------------
# One writer: written whole, the same every time
# ---------------------------------------------------------------------------


def test_writing_the_index_again_leaves_it_byte_for_byte(tmp_path: Path):
    continued_run(tmp_path)
    (tmp_path / "notes.json").write_text("[]")
    run_index.write_index(tmp_path)
    first = (tmp_path / INDEX).read_bytes()

    run_index.write_index(tmp_path)

    assert (tmp_path / INDEX).read_bytes() == first


def test_writing_the_index_leaves_no_temporary_file_behind(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])

    run_index.write_index(tmp_path)

    assert sorted(path.name for path in tmp_path.iterdir()) == [INDEX, "run-a.json"]


# ---------------------------------------------------------------------------
# --reindex, a finished run and a close
# ---------------------------------------------------------------------------


def checkout_with_a_run(root: Path) -> Path:
    directory = root / OUTPUT_DIR
    directory.mkdir(parents=True)
    write_run(directory, "run-a", [*pair_of_sessions("t1")])
    return directory


def test_reindex_rebuilds_the_index_of_the_named_checkouts_results_directory(tmp_path: Path):
    directory = checkout_with_a_run(tmp_path)

    code = cli.main([str(tmp_path), "--reindex"])

    assert code == 0
    assert json.loads((directory / INDEX).read_text())["runs"]["run-a"]["file"] == "run-a.json"


def test_reindex_replaces_a_stale_index_and_is_idempotent_byte_for_byte(tmp_path: Path):
    directory = checkout_with_a_run(tmp_path)
    (directory / INDEX).write_text('{"schema": 1, "runs": {}, "skipped": ["stale.json"]}')
    cli.main([str(tmp_path), "--reindex"])
    first = (directory / INDEX).read_bytes()

    cli.main([str(tmp_path), "--reindex"])

    assert (directory / INDEX).read_bytes() == first
    assert b"stale.json" not in first


@pytest.mark.parametrize(
    "beside",
    [["--role", ROLE], ["--report", "run.json"], ["--close", "run-a"], ["--output", "out.json"]],
)
def test_reindex_takes_nothing_beside_it(beside: list[str]):
    with pytest.raises(SystemExit) as raised:
        cli.parse_config(["--reindex", *beside])

    assert raised.value.code == 2


def test_a_finished_run_writes_the_index_beside_its_results_file(
    paid: Callable[[Script], None], tmp_path: Path
):
    paid(Script())

    run = run_small(tmp_path)[1]

    entry = json.loads((tmp_path / INDEX).read_text())["runs"][run.run.id]
    assert entry["file"] == "out.json"
    assert entry["sha256"] == hashlib.sha256((tmp_path / "out.json").read_bytes()).hexdigest()
    assert entry["ending"] == "finished"


def test_closing_a_run_rewrites_the_index_with_the_closed_ending(
    paid: Callable[[Script], None], tmp_path: Path
):
    paid(Script())
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)

    close_run(tmp_path, stopped.run.id, "--reason", REASON)

    entry = json.loads((tmp_path / INDEX).read_text())["runs"][stopped.run.id]
    assert entry["ending"] == "closed"
    assert entry["sha256"] == hashlib.sha256((tmp_path / "stopped.json").read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# The eight recorded runs
# ---------------------------------------------------------------------------

# The runs recorded when the index was first written, oldest first; later runs index themselves.
EIGHT_RECORDED_RUNS = (
    "20261014T023850Z-809185",
    "20261014T031818Z-d71d91",
    "20261014T033052Z-4f6604",
    "20261014T045733Z-7050ca",
    "20261014T152926Z-723e7a",
    "20261015T035717Z-03a785",
    "20261015T082642Z-672192",
    "20261016T024750Z-62073e",
)
STANDING = re.compile(
    r"^Role (?P<role>\S+): (?:underpowered|flip verdict (?P<flip>clear|not clear))[^\n]*\n"
    r"\s+(?P<pairs>\d+) complete pairs of",
    re.MULTILINE,
)


def reported_standing(path: Path) -> dict[str, dict[str, Any]]:
    """Each role's complete pairs and flip label as the report of the file prints them."""
    tip = results.load(path)
    text = report.render(tip, parts_before(tip, path.parent))
    return {
        found["role"]: {
            "complete_pairs": int(found["pairs"]),
            "flip": found["flip"] or "underpowered",
        }
        for found in STANDING.finditer(text)
    }


def recorded_files() -> list[Path]:
    return [RECORDED / f"{run_id}.json" for run_id in EIGHT_RECORDED_RUNS]


def test_the_recorded_runs_are_indexed_with_the_pairs_and_labels_the_report_shows():
    document = json.loads((RECORDED / INDEX).read_text())

    for path in recorded_files():
        entry = document["runs"][results.load(path).run.id]
        figures = {
            role: {"complete_pairs": s["complete_pairs"], "flip": s["flip"]}
            for role, s in entry["roles"].items()
        }
        assert figures == reported_standing(path), path.name


def test_the_researcher_runs_were_indexed_with_zero_zero_two_thirteen_and_twenty_four_pairs():
    entries = json.loads((RECORDED / INDEX).read_text())["runs"].values()

    pairs = [
        e["roles"]["researcher"]["complete_pairs"] for e in entries if "researcher" in e["roles"]
    ]

    assert pairs == [0, 0, 2, 13, 24]


def test_the_committed_index_is_what_reindex_writes(tmp_path: Path):
    for path in RECORDED.glob("*.json"):
        if path.name != INDEX:
            shutil.copy(path, tmp_path / path.name)

    run_index.write_index(tmp_path)

    assert (tmp_path / INDEX).read_bytes() == (RECORDED / INDEX).read_bytes()
