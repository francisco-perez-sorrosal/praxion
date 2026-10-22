"""Tests for the results files the commit gate cannot read: kept by name with why, and refused.

Reading keeps each file it could not parse beside the files it could, and a cited run whose
`continues` chain reaches such a file is refused naming it (`I9-run-part-unreadable`), never as a
lineage that merely looks different. A canary per refusal, with the known-good case that passes
beside it. Imports gate modules only (never `check_kernel_manifest`), so the mutation sensor can
run it; the plant builders are the evidence tests'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_run_evidence as kre  # noqa: E402
import kernel_run_index as kri  # noqa: E402
import test_kernel_ledger_checks_evidence as ev  # noqa: E402

NOT_JSON = b'{"run": {"id": "cut off mid-wr'
NOT_TEXT = b"\x80\x81\x82" * 64  # no byte order mark, and not UTF-8
PART_ONE, PART_TWO, PART_THREE = ev.PART_ONE, ev.PART_TWO, ev.PART_THREE
UNRELATED = "20261001T000000Z-other0"


def spoil(root: Path, run_id: str, content: bytes) -> None:
    (root / kri.RESULTS_DIR / f"{run_id}{kre.RESULTS_SUFFIX}").write_bytes(content)


def plant_continued(root: Path, *, pairs: int = 24) -> None:
    """A run stopped after its first part and continued: two parts, one lineage, clear."""
    first = ev.results(PART_ONE, ev.pairs_of(pairs), None)
    tip = ev.results(
        PART_TWO, ev.pairs_of(pairs), ev.standing([PART_ONE, PART_TWO]), continues=PART_ONE
    )
    ev.plant(root, first, tip)


def refused(root: Path, run_id: str) -> list[tuple[str, str]]:
    return ev.findings(root, ev.switched(ev.cited(run_id), passing=run_id))


# -- Reading keeps what it cannot parse --------------------------------------------------------


def test_a_directory_of_readable_files_has_nothing_unreadable(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING))

    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert ([file.run_id for file in reading.files], dict(reading.unreadable)) == ([ev.PASSING], {})


@pytest.mark.parametrize(
    ("content", "why"),
    [(NOT_JSON, "not JSON"), (NOT_TEXT, "not text")],
    ids=["not JSON", "not text"],
)
def test_a_file_that_is_not_json_text_is_kept_by_name_with_why(
    tmp_path: Path, content: bytes, why: str
) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING), ev.whole(ev.EARLY))
    spoil(tmp_path, ev.EARLY, content)

    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert [file.run_id for file in reading.files] == [ev.PASSING]
    assert list(reading.unreadable) == [f"{ev.EARLY}.json"]
    assert reading.unreadable[f"{ev.EARLY}.json"].startswith(why)


def test_a_results_file_of_a_shape_the_gate_cannot_parse_is_kept_by_name_with_why(
    tmp_path: Path,
) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING))
    broken = ev.whole(ev.EARLY)
    del broken["sessions"]
    spoil(tmp_path, ev.EARLY, json.dumps(broken).encode("utf-8"))

    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert reading.unreadable[f"{ev.EARLY}.json"].startswith(
        "not a results file this gate can parse"
    )


def test_a_path_that_cannot_be_opened_as_a_file_is_kept_by_name_with_why(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING))
    (tmp_path / kri.RESULTS_DIR / "a-directory.json").mkdir()

    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert reading.unreadable["a-directory.json"].startswith("cannot be read")


def test_json_that_is_no_results_file_is_passed_over_not_reported(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING))  # the index is such a file, and so is any other

    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert dict(reading.unreadable) == {}


def test_the_files_alone_are_what_read_run_files_gives(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING), ev.whole(ev.EARLY))
    spoil(tmp_path, ev.EARLY, NOT_JSON)

    files = kre.read_run_files(tmp_path / kri.RESULTS_DIR)

    assert [file.run_id for file in files] == [ev.PASSING]


# -- The unreadable part a lineage reaches -----------------------------------------------------


def test_the_chain_of_a_continuation_reaches_its_unreadable_earlier_part(tmp_path: Path) -> None:
    plant_continued(tmp_path)
    spoil(tmp_path, PART_ONE, NOT_JSON)
    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    part = kre.unreadable_part(reading.files, reading.unreadable, PART_TWO)

    assert part is not None
    assert (part.run_id, part.file) == (PART_ONE, f"{PART_ONE}.json")
    assert part.reason.startswith("not JSON")


def test_a_run_whose_own_file_is_unreadable_is_its_own_unreadable_part(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING))
    spoil(tmp_path, ev.PASSING, NOT_TEXT)
    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    part = kre.unreadable_part(reading.files, reading.unreadable, ev.PASSING)

    assert part is not None
    assert part.file == f"{ev.PASSING}.json"


def test_a_chain_of_readable_parts_reaches_nothing_unreadable(tmp_path: Path) -> None:
    plant_continued(tmp_path)
    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert kre.unreadable_part(reading.files, reading.unreadable, PART_TWO) is None


def test_an_unreadable_file_the_chain_does_not_reach_is_not_its_part(tmp_path: Path) -> None:
    plant_continued(tmp_path)
    (tmp_path / kri.RESULTS_DIR / f"{UNRELATED}.json").write_bytes(NOT_JSON)
    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert kre.unreadable_part(reading.files, reading.unreadable, PART_TWO) is None


def test_a_gap_in_the_chain_with_no_unreadable_file_behind_it_reaches_nothing(
    tmp_path: Path,
) -> None:
    plant_continued(tmp_path)
    (tmp_path / kri.RESULTS_DIR / f"{PART_ONE}.json").unlink()
    reading = kre.read_results(tmp_path / kri.RESULTS_DIR)

    assert kre.unreadable_part(reading.files, reading.unreadable, PART_TWO) is None


def test_a_chain_that_loops_ends_without_reaching_an_unreadable_part() -> None:
    loop = [
        kre.RunFile(PART_ONE, PART_TWO, "finished", (), kre.Unrecorded("x")),
        kre.RunFile(PART_TWO, PART_ONE, "finished", (), kre.Unrecorded("x")),
    ]

    assert kre.unreadable_part(loop, {}, PART_ONE) is None


# -- The refusal -------------------------------------------------------------------------------


def test_a_continuation_whose_earlier_part_reads_cleanly_passes(tmp_path: Path) -> None:
    plant_continued(tmp_path)

    assert refused(tmp_path, PART_TWO) == []


@pytest.mark.parametrize(
    ("content", "why"),
    [(NOT_JSON, "not JSON"), (NOT_TEXT, "not text")],
    ids=["not JSON", "not text"],
)
def test_an_unreadable_earlier_part_is_refused_naming_its_file_and_why_and_nothing_else(
    tmp_path: Path, content: bytes, why: str
) -> None:
    plant_continued(tmp_path)
    spoil(tmp_path, PART_ONE, content)

    found = refused(tmp_path, PART_TWO)

    assert [kind for kind, _ in found] == ["I9-run-part-unreadable"]
    assert f"role {ev.ROLE}" in found[0][1]
    assert f"cites run {PART_TWO!r}" in found[0][1]
    assert f"{PART_ONE}.json" in found[0][1]
    assert why in found[0][1]


def test_a_cited_run_whose_own_file_is_unreadable_is_refused_naming_that_file(
    tmp_path: Path,
) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING))
    spoil(tmp_path, ev.PASSING, NOT_JSON)

    found = refused(tmp_path, ev.PASSING)

    assert [kind for kind, _ in found] == ["I9-run-part-unreadable"]
    assert f"{ev.PASSING}.json" in found[0][1]
    assert "not JSON" in found[0][1]


def test_each_cited_run_is_judged_on_its_own_chain(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.EARLY, 13, "underpowered"), ev.whole(ev.PASSING))
    spoil(tmp_path, ev.EARLY, NOT_JSON)

    found = ev.findings(tmp_path, ev.switched(ev.cited(ev.EARLY, 13, False), ev.cited(ev.PASSING)))

    assert [kind for kind, _ in found] == ["I9-run-part-unreadable"]
    assert f"{ev.EARLY}.json" in found[0][1]


def test_an_unreadable_file_outside_every_cited_chain_refuses_nothing(tmp_path: Path) -> None:
    plant_continued(tmp_path)
    (tmp_path / kri.RESULTS_DIR / f"{UNRELATED}.json").write_bytes(NOT_JSON)

    assert refused(tmp_path, PART_TWO) == []


def test_a_gap_in_the_chain_with_no_unreadable_file_is_still_refused_as_missing(
    tmp_path: Path,
) -> None:
    plant_continued(tmp_path)
    (tmp_path / kri.RESULTS_DIR / f"{PART_ONE}.json").unlink()

    assert [kind for kind, _ in refused(tmp_path, PART_TWO)] == ["I9-run-missing"]
