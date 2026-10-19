"""Tests for kernel_run_index.py and the run findings it feeds -- cited runs resolve to their results.

Each case plants results files and the index that describes them in a directory of its own, then
judges a switched record against it: a canary per refusal with a counter-case that passes, a
continued run read as one lineage, and the index held to the files beside it. One case reads the
repository's own ledger and results, which must pass as committed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_ledger as kl  # noqa: E402
import kernel_ledger_checks as lc  # noqa: E402
import kernel_model as km  # noqa: E402
import kernel_run_index as kri  # noqa: E402
from kernel_eligibility import ELIGIBLE_ROLES  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLE = "researcher"
EARLY, PASSING = "20261101T000000Z-early0", "20261102T000000Z-pass00"
FIRST_PART, LATER_PART = "20261103T000000Z-part01", "20261104T000000Z-part02"


# -- Builders: results files, their index, a switched record citing them ---------------


def indexed(
    run_id: str, pairs: int = 24, flip: str = "clear", role: str = ROLE, root: str | None = None
) -> dict:
    return {"id": run_id, "role": role, "pairs": pairs, "flip": flip, "root": root or run_id}


def plant(directory_root: Path, *runs: dict, skipped: tuple[str, ...] = ()) -> Path:
    """Results files for `runs` and the index the eval would write for them; the directory."""
    directory = directory_root / kri.RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    entries = {}
    for run in runs:
        raw = json.dumps({"run": {"id": run["id"]}}).encode("utf-8")
        (directory / f"{run['id']}.json").write_bytes(raw)
        entries[run["id"]] = {
            "file": f"{run['id']}.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "lineage_root": run["root"],
            "ending": "finished",
            "roles": {run["role"]: {"complete_pairs": run["pairs"], "flip": run["flip"]}},
        }
    index = {"schema": kri.INDEX_SCHEMA, "runs": entries, "skipped": list(skipped)}
    (directory / kri.INDEX_NAME).write_text(json.dumps(index), encoding="utf-8")
    return directory


def cited(run_id: str, pairs: int = 24, passes: bool = True) -> dict:
    entry = lc.ADHERENCE_ENTRY
    return {"id": run_id, "complete_pairs": pairs, "passes_flip_rule": passes, "entry": entry}


def switched(*runs: dict, passing: str = PASSING) -> kl.Ledger:
    row = {
        "status": "switched",
        "since": "2026-10-12",
        "runs": list(runs),
        "passing_run": passing,
        "probe_before_tokens": 31_000,
        "probe_after_tokens": 22_000,
        "flip_rule_ratified": True,
        "flip_ratified": True,
    }
    return kl.parse_ledger({"version": 1, "roles": {ROLE: row}}, frozenset(ELIGIBLE_ROLES))


def findings(root: Path, ledger: kl.Ledger) -> list[tuple[str, str]]:
    adherence = kri.read_adherence(root)
    found = (*lc.run_index_findings(adherence), *lc.cited_run_findings(ledger, adherence))
    return [(finding.kind, f"{finding.subject} -- {finding.detail}") for finding in found]


def kinds(root: Path, ledger: kl.Ledger) -> list[str]:
    return [kind for kind, _ in findings(root, ledger)]


THE_RECORD = switched(cited(EARLY, 13, False), cited(PASSING))


# -- Each refusal, beside the record that passes -----------------------------------------


def test_a_record_whose_cited_runs_resolve_to_their_results_passes(tmp_path: Path) -> None:
    plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING))

    assert findings(tmp_path, THE_RECORD) == []


def test_a_cited_run_the_index_does_not_list_is_refused_naming_role_and_run(tmp_path: Path) -> None:
    plant(tmp_path, indexed(PASSING))

    assert findings(tmp_path, THE_RECORD) == [
        (
            "I9-run-missing",
            f"role {ROLE} -- cites run {EARLY!r}, which has no readable results file in "
            f"{kri.RESULTS_DIR}",
        )
    ]


def test_a_cited_run_whose_listed_file_is_gone_is_refused_and_the_index_is_stale(
    tmp_path: Path,
) -> None:
    directory = plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING))
    (directory / f"{PASSING}.json").unlink()

    found = findings(tmp_path, THE_RECORD)

    assert [kind for kind, _ in found] == ["I9-run-index-stale", "I9-run-missing"]
    assert all(PASSING in text for _, text in found)


def test_a_cited_run_whose_results_measured_another_role_is_refused(tmp_path: Path) -> None:
    plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING, role="verifier"))

    found = findings(tmp_path, THE_RECORD)

    assert [kind for kind, _ in found] == ["I9-run-wrong-role"]
    assert PASSING in found[0][1]
    assert "measured verifier, not researcher" in found[0][1]


def test_a_cited_run_recording_other_complete_pairs_than_its_results_is_refused(
    tmp_path: Path,
) -> None:
    plant(tmp_path, indexed(EARLY, 12, "underpowered"), indexed(PASSING))

    found = findings(tmp_path, THE_RECORD)

    assert [kind for kind, _ in found] == ["I9-run-pairs-differ"]
    assert "with 13 complete pairs" in found[0][1]
    assert "reached 12 complete pairs" in found[0][1]


def test_a_cited_run_whose_pass_flag_disagrees_with_its_verdict_is_refused(tmp_path: Path) -> None:
    plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING))
    ledger = switched(cited(EARLY, 13, True), cited(PASSING))

    found = findings(tmp_path, ledger)

    assert [kind for kind, _ in found] == ["I9-run-flag-disagrees"]
    assert EARLY in found[0][1]
    assert "underpowered" in found[0][1]


def test_a_passing_run_whose_results_hold_fewer_than_twenty_pairs_is_refused(
    tmp_path: Path,
) -> None:
    plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING, 19))

    assert "I9-run-passing-short" in kinds(tmp_path, THE_RECORD)


def test_a_passing_run_whose_results_verdict_is_not_clear_is_refused(tmp_path: Path) -> None:
    plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING, 24, "not clear"))

    assert kinds(tmp_path, THE_RECORD) == ["I9-run-flag-disagrees", "I9-run-passing-short"]


def test_runs_cited_by_a_record_that_is_not_switched_are_not_resolved(tmp_path: Path) -> None:
    plant(tmp_path)
    trial = {"status": "trial", "since": "2026-10-12", "runs": [cited(EARLY)]}
    ledger = kl.parse_ledger({"version": 1, "roles": {ROLE: trial}}, frozenset(ELIGIBLE_ROLES))

    assert findings(tmp_path, ledger) == []


# -- A continued run is one run ---------------------------------------------------------


def lineage(pairs: int = 24, flip: str = "clear") -> tuple[dict, dict]:
    """A continued run as the index lists it: every part carries the whole lineage's values."""
    return (
        indexed(FIRST_PART, pairs, flip, root=FIRST_PART),
        indexed(LATER_PART, pairs, flip, root=FIRST_PART),
    )


@pytest.mark.parametrize("part", [FIRST_PART, LATER_PART])
def test_a_citation_of_any_part_resolves_to_the_whole_lineage(tmp_path: Path, part: str) -> None:
    plant(tmp_path, *lineage())

    assert findings(tmp_path, switched(cited(part), passing=part)) == []


def test_a_part_cited_with_its_own_pairs_is_judged_against_its_lineage(tmp_path: Path) -> None:
    plant(tmp_path, *lineage())

    found = findings(tmp_path, switched(cited(LATER_PART, 20), passing=LATER_PART))

    assert [kind for kind, _ in found] == ["I9-run-pairs-differ"]
    assert f"the lineage of {FIRST_PART!r} (parts {FIRST_PART}, {LATER_PART})" in found[0][1]


def test_a_record_citing_two_parts_of_one_lineage_counts_one_run(tmp_path: Path) -> None:
    plant(tmp_path, *lineage())
    both = switched(cited(FIRST_PART), cited(LATER_PART), passing=LATER_PART)
    one = switched(cited(LATER_PART), passing=LATER_PART)

    assert findings(tmp_path, both) == findings(tmp_path, one) == []


def test_a_cited_closed_run_is_a_not_clear_draw_that_refuses_nothing_alone(
    tmp_path: Path,
) -> None:
    plant(tmp_path, indexed(EARLY, 13, "not clear"), indexed(PASSING))

    assert findings(tmp_path, THE_RECORD) == []


# -- The index against the files beside it ------------------------------------------------


def test_a_results_file_changed_since_it_was_indexed_makes_the_index_stale(
    tmp_path: Path,
) -> None:
    directory = plant(tmp_path, indexed(EARLY, 13, "underpowered"), indexed(PASSING))
    (directory / f"{EARLY}.json").write_text('{"edited": true}', encoding="utf-8")

    found = findings(tmp_path, THE_RECORD)

    assert found == [
        (
            "I9-run-index-stale",
            f"{kri.RESULTS_DIR}/{EARLY}.json -- changed since indexed: rebuild index.json with "
            f"`{lc.ADHERENCE_ENTRY} --reindex`",
        )
    ]


def test_a_results_file_the_index_lacks_makes_it_stale_and_a_skipped_one_does_not(
    tmp_path: Path,
) -> None:
    directory = plant(tmp_path, indexed(PASSING), skipped=("notes.json",))
    (directory / "notes.json").write_text("not a run", encoding="utf-8")
    (directory / f"{EARLY}.json").write_text("{}", encoding="utf-8")

    found = findings(tmp_path, switched(cited(PASSING)))

    assert [(kind, text.split(" -- ")[0]) for kind, text in found] == [
        ("I9-run-index-stale", f"{kri.RESULTS_DIR}/{EARLY}.json")
    ]


def test_results_files_with_no_index_are_each_unlisted(tmp_path: Path) -> None:
    directory = plant(tmp_path, indexed(PASSING))
    (directory / kri.INDEX_NAME).unlink()

    assert kinds(tmp_path, switched(cited(PASSING))) == ["I9-run-index-stale", "I9-run-missing"]


def test_a_checkout_with_no_results_directory_has_nothing_to_hold(tmp_path: Path) -> None:
    adherence = kri.read_adherence(tmp_path)

    assert lc.run_index_findings(adherence) == ()
    assert adherence.lineage_of(PASSING) is None


# -- An index the gate cannot read --------------------------------------------------------


def listed_part(root: str, flip: str = "clear") -> dict:
    roles = {ROLE: {"complete_pairs": 24, "flip": flip}}
    return {"file": "r.json", "sha256": "0", "lineage_root": root, "roles": roles}


def index_text(runs: dict) -> str:
    return json.dumps({"schema": kri.INDEX_SCHEMA, "runs": runs, "skipped": []})


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        json.dumps({"schema": 2, "runs": {}, "skipped": []}),
        json.dumps({"schema": 1, "runs": [], "skipped": []}),
        json.dumps(
            {
                "schema": 1,
                "runs": {"r": {"file": "r.json", "sha256": "0", "lineage_root": "r", "roles": {}}},
            }
        ),
        json.dumps(
            {
                "schema": 1,
                "skipped": [],
                "runs": {
                    "r": {
                        "file": "r.json",
                        "sha256": "0",
                        "lineage_root": "r",
                        "roles": {ROLE: {"complete_pairs": 24, "flip": "passed"}},
                    }
                },
            }
        ),
        index_text({"r": listed_part(root="gone")}),
        index_text({"a": listed_part(root="a"), "b": listed_part(root="a", flip="not clear")}),
    ],
)
def test_an_index_of_any_other_shape_is_an_input_error_naming_it(text: str) -> None:
    with pytest.raises(km.KernelModelError, match="index.json"):
        kri.parse_index(text.encode("utf-8"))


def test_an_index_that_is_not_utf8_is_an_input_error_naming_it(tmp_path: Path) -> None:
    directory = plant(tmp_path, indexed(PASSING))
    (directory / kri.INDEX_NAME).write_bytes(b"\xff{}")

    with pytest.raises(km.KernelModelError, match="index.json"):
        kri.read_adherence(tmp_path)


# -- The repository as committed ----------------------------------------------------------


def test_the_committed_ledger_rests_on_its_committed_results() -> None:
    ledger = kl.load_ledger(REPO_ROOT, km.agent_definitions(REPO_ROOT))

    assert findings(REPO_ROOT, ledger) == []
