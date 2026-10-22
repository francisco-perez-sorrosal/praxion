"""Tests for kernel_run_standing.py: the one standing both flip-gate readers parse a record with.

The leaf is held to its own shape rules, to agreement between the two readers that use it (the run
index and a cited run's results files accept and refuse the same figures, with the same reason), and
to loading where nothing but the standard library can be imported.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import kernel_model as km  # noqa: E402
import kernel_run_evidence as kre  # noqa: E402
import kernel_run_index as kri  # noqa: E402
import kernel_run_standing as krs  # noqa: E402

ROLE = "researcher"
RUN = "20261101T000000Z-aaaaaa"
FILE_NAME = f"{RUN}.json"

# (complete_pairs, flip, scored_checks) as a record states them, and what each reads as
WELL_FORMED = [
    (24, "clear", ["C1", "C3"]),
    (0, "not clear", []),
    (2, "underpowered", []),
]
# the same figures where one is wrong, and the reason both readers must give
MALFORMED = [
    ("24", "clear", ["C1"], "complete_pairs '24' is not a count"),
    (True, "clear", ["C1"], "complete_pairs True is not a count"),
    (-1, "clear", ["C1"], "complete_pairs -1 is not a count"),
    (2.5, "clear", ["C1"], "complete_pairs 2.5 is not a count"),
    (24, "maybe", ["C1"], "flip 'maybe' is none of clear, not clear, underpowered"),
    (24, None, ["C1"], "flip None is none of"),
    (24, "clear", ["C3", "C1"], "scored_checks ['C3', 'C1'] are not sorted and unique"),
    (24, "clear", ["C1", "C1"], "scored_checks ['C1', 'C1'] are not sorted and unique"),
    (24, "clear", "C1", "scored_checks 'C1' is not a list"),
    (24, "clear", [1], "scored_checks 1 is not text"),
    (2, "underpowered", ["C1"], "an underpowered standing scored no check, yet lists ['C1']"),
]


# -- The two readers, each handed one standing as its own file shape records it ---------------


def figures(pairs, flip, scored) -> dict:
    return {"complete_pairs": pairs, "flip": flip, "scored_checks": scored}


def evidence_reading(tmp_path: Path, record: dict):
    """What the results-file reader makes of a file recording `record` for the role."""
    entry = record | {"lineage_root": RUN, "parts": [RUN]}
    data = {
        "schema_version": kre.RESULTS_SCHEMA,
        "run": {"id": RUN},
        "sessions": [],
        "standing": {ROLE: entry},
    }
    (tmp_path / FILE_NAME).write_text(json.dumps(data), encoding="utf-8")
    return kre.read_run_files(tmp_path)[0].recorded


def index_reading(record: dict):
    """What the run-index reader makes of an index listing `record` for the role."""
    entry = {"file": FILE_NAME, "sha256": "0" * 64, "lineage_root": RUN, "roles": {ROLE: record}}
    data = {"schema": kri.INDEX_SCHEMA, "runs": {RUN: entry}, "skipped": []}
    entries, _ = kri.parse_index(json.dumps(data).encode("utf-8"))
    return entries[RUN].roles[ROLE]


@pytest.mark.parametrize(("pairs", "flip", "scored"), WELL_FORMED)
def test_both_readers_read_a_well_formed_standing_as_the_same_value(tmp_path, pairs, flip, scored):
    record = figures(pairs, flip, scored)

    from_files = evidence_reading(tmp_path, record)

    assert isinstance(from_files, kre.Lineage)
    assert from_files.standing[ROLE].figures == index_reading(record)
    assert index_reading(record) == krs.Standing(pairs, flip, tuple(scored))


@pytest.mark.parametrize(("pairs", "flip", "scored", "reason"), MALFORMED)
def test_both_readers_refuse_a_malformed_standing_for_the_same_reason(
    tmp_path, pairs, flip, scored, reason
):
    record = figures(pairs, flip, scored)

    from_files = evidence_reading(tmp_path, record)

    assert isinstance(from_files, kre.Unrecorded)
    assert reason in from_files.reason
    with pytest.raises(km.KernelModelError) as refusal:
        index_reading(record)
    assert reason in str(refusal.value)


def test_the_two_readers_share_one_standing_value_and_one_set_of_labels():
    assert kre.Standing is krs.Standing
    assert kri.Standing is krs.Standing
    assert kri.CLEAR == krs.CLEAR


# -- The typed reads ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("read", "value", "expected"),
    [
        (krs.as_text, "name", "name"),
        (krs.as_count, 0, 0),
        (krs.as_count, 24, 24),
        (krs.as_list, [1, "a"], [1, "a"]),
        (krs.as_mapping, {"a": 1}, {"a": 1}),
        (krs.as_sorted_unique_texts, ["a", "b"], ("a", "b")),
        (krs.as_sorted_unique_texts, [], ()),
    ],
)
def test_a_typed_read_returns_a_well_formed_value(read, value, expected):
    assert read(value, "field") == expected


@pytest.mark.parametrize(
    ("read", "value", "reason"),
    [
        (krs.as_text, 3, "field 3 is not text"),
        (krs.as_count, -1, "field -1 is not a count"),
        (krs.as_count, False, "field False is not a count"),
        (krs.as_list, (1,), "field (1,) is not a list"),
        (krs.as_mapping, [1], "field [1] is not a mapping"),
        (krs.as_sorted_unique_texts, ["b", "a"], "field ['b', 'a'] are not sorted and unique"),
        (krs.as_sorted_unique_texts, ["a", 1], "field 1 is not text"),
    ],
)
def test_a_typed_read_refuses_a_malformed_value_naming_the_field_and_the_reason(
    read, value, reason
):
    with pytest.raises(krs.ShapeError) as refusal:
        read(value, "field")

    assert str(refusal.value) == reason


# -- Loading ----------------------------------------------------------------------------

LOAD_WITH_STDLIB_ONLY = """
import sys

scripts, leaf = sys.argv[1:3]


class OnlyTheStandardLibrary:
    def find_spec(self, name, path=None, target=None):
        if name.partition(".")[0] not in sys.stdlib_module_names | {leaf}:
            raise ImportError(f"{name} is not the standard library")


sys.meta_path.insert(0, OnlyTheStandardLibrary())
sys.path.insert(0, scripts)
module = __import__(leaf)
assert module.read_standing(2, "clear", ["C1"]).complete_pairs == 2
"""


def test_the_leaf_loads_where_only_the_standard_library_can_be_imported():
    run = subprocess.run(
        [sys.executable, "-I", "-c", LOAD_WITH_STDLIB_ONLY, str(SCRIPTS), "kernel_run_standing"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr[-500:]
