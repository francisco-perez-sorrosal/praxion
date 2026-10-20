"""Tests for the cited-run findings of kernel_ledger_checks.py: a run is judged from its results.

Each case plants results files (as the adherence eval writes them) and the index that describes
them in a directory of its own, then judges a switched record against both. A canary per finding
kind: the known-bad case is refused beside the known-good one that passes. Imports gate modules
only (never `check_kernel_manifest`), so the mutation sensor can run it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_ledger as kl  # noqa: E402
import kernel_ledger_checks as lc  # noqa: E402
import kernel_run_evidence as kre  # noqa: E402
import kernel_run_index as kri  # noqa: E402
from kernel_eligibility import ELIGIBLE_ROLES  # noqa: E402

ROLE = "researcher"
EARLY, PASSING = "20261101T000000Z-early0", "20261102T000000Z-pass00"
PART_ONE, PART_TWO, PART_THREE = (
    "20261103T000000Z-part01",
    "20261104T000000Z-part02",
    "20261105T000000Z-part03",
)
SCORED = ["C1", kre.convention_check_name(ROLE)]
Index = dict[str, Any]


# -- Builders: results files, the index that describes them, a switched record -------------


def session(task: str, arm: str, role: str = ROLE, measured: bool = True) -> dict:
    status = {"kind": "measured"} if measured else {"kind": "errored", "error_kind": "timeout"}
    return {
        "setup": {"arm": arm, "role": role, "task_id": task, "template_id": f"x-{task}"},
        "status": status,
    }


def pairs_of(count: int, role: str = ROLE) -> list[dict]:
    return [session(f"t{n}", arm, role) for n in range(count) for arm in ("full", "lean")]


def standing(parts: list[str], pairs: int = 24, flip: str = "clear", role: str = ROLE) -> dict:
    entry = {
        "lineage_root": parts[0],
        "parts": parts,
        "complete_pairs": pairs,
        "flip": flip,
        "scored_checks": SCORED,
    }
    return {role: entry}


def results(run_id: str, sessions: list[dict], recorded: dict | None, **run_keys: Any) -> dict:
    """A results file; `recorded` is its `standing` (None: it records none)."""
    file = {
        "schema_version": "adherence/1",
        "run": {"id": run_id, **run_keys},
        "sessions": sessions,
    }
    return file if recorded is None else {**file, "standing": recorded}


def whole(run_id: str, pairs: int = 24, flip: str = "clear", **run_keys: Any) -> dict:
    """A one-part run of `pairs` complete pairs that records the standing it reached."""
    return results(run_id, pairs_of(pairs), standing([run_id], pairs, flip), **run_keys)


def root_of(file: dict, held: dict[str, dict]) -> str:
    parent = file["run"].get("continues")
    return file["run"]["id"] if parent is None else root_of(held[parent], held)


def index_entry(file: dict, raw: bytes, root: str, tip: dict) -> dict:
    kept = ("complete_pairs", "flip", "scored_checks")
    recorded = tip.get("standing", standing([root]))
    return {
        "file": f"{file['run']['id']}.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "lineage_root": root,
        "ending": "finished",
        "roles": {role: {key: entry[key] for key in kept} for role, entry in recorded.items()},
    }


def plant(tmp_path: Path, *files: dict, edit: Callable[[Index], None] = lambda index: None) -> None:
    """Write the results files and the index the eval would write; `edit` is a hand edit of it."""
    directory = tmp_path / kri.RESULTS_DIR
    directory.mkdir(parents=True)
    held = {file["run"]["id"]: file for file in files}
    tips = {root_of(file, held): file for file in files}  # the last file of each chain
    entries = {}
    for file in files:
        raw = json.dumps(file).encode("utf-8")
        (directory / f"{file['run']['id']}.json").write_bytes(raw)
        root = root_of(file, held)
        entries[file["run"]["id"]] = index_entry(file, raw, root, tips[root])
    index: Index = {"schema": kri.INDEX_SCHEMA, "runs": entries, "skipped": []}
    edit(index)
    (directory / kri.INDEX_NAME).write_text(json.dumps(index), encoding="utf-8")


def cited(run_id: str, pairs: int = 24, passes: bool = True) -> dict:
    return {
        "id": run_id,
        "complete_pairs": pairs,
        "passes_flip_rule": passes,
        "entry": lc.ADHERENCE_ENTRY,
    }


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


def findings(tmp_path: Path, ledger: kl.Ledger) -> list[tuple[str, str]]:
    found = lc.cited_run_findings(ledger, kri.read_adherence(tmp_path))
    return [(finding.kind, f"{finding.subject} -- {finding.detail}") for finding in found]


def kinds(tmp_path: Path, ledger: kl.Ledger) -> list[str]:
    return [kind for kind, _ in findings(tmp_path, ledger)]


def edit_entry(run_id: str, **fields: Any) -> Callable[[Index], None]:
    return lambda index: index["runs"][run_id].update(fields)


def edit_roles(run_id: str, **fields: Any) -> Callable[[Index], None]:
    return lambda index: index["runs"][run_id]["roles"][ROLE].update(fields)


PASSING_ALONE = switched(cited(PASSING))
EARLY_AND_PASSING = switched(cited(EARLY, 13, False), cited(PASSING))


# -- The record beside the results: pairs, flag, sufficiency ---------------------------------


def test_a_record_that_the_results_files_bear_out_passes(tmp_path: Path) -> None:
    plant(tmp_path, whole(EARLY, 13, "underpowered"), whole(PASSING))

    assert findings(tmp_path, EARLY_AND_PASSING) == []


def test_a_record_citing_more_pairs_than_the_sessions_give_is_refused_naming_both(
    tmp_path: Path,
) -> None:
    plant(tmp_path, whole(PASSING))

    found = findings(tmp_path, switched(cited(PASSING, 30)))

    assert [kind for kind, _ in found] == ["I9-run-pairs-differ"]
    assert f"role {ROLE}" in found[0][1]
    assert f"cites run {PASSING!r} with 30 complete pairs" in found[0][1]
    assert f"run {PASSING!r} reached 24 complete pairs" in found[0][1]


def test_a_task_whose_latest_lean_session_errored_is_not_a_complete_pair(tmp_path: Path) -> None:
    later = [session("t0", "lean", measured=False)]
    plant(tmp_path, results(PASSING, [*pairs_of(24), *later], standing([PASSING], 24)))

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == [
        "I9-run-index-pairs-differ",
        "I9-run-pairs-differ",
        "I9-run-recorded-pairs-differ",
    ]
    assert "with 24 complete pairs" in found[1][1]
    assert "reached 23 complete pairs" in found[1][1]


def test_a_task_whose_lean_error_came_before_its_measured_session_stays_complete(
    tmp_path: Path,
) -> None:
    earlier = [session("t0", "lean", measured=False)]
    plant(tmp_path, results(PASSING, [*earlier, *pairs_of(24)], standing([PASSING], 24)))

    assert findings(tmp_path, PASSING_ALONE) == []


def test_a_not_clear_run_flagged_as_passing_is_refused_though_the_index_says_clear(
    tmp_path: Path,
) -> None:
    plant(tmp_path, whole(PASSING, 24, "not clear"), edit=edit_roles(PASSING, flip="clear"))

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == [
        "I9-run-index-flip-differs",
        "I9-run-flag-disagrees",
        "I9-run-passing-short",
    ]
    assert all(PASSING in text and ROLE in text for _, text in found)


def test_a_run_flagged_as_not_passing_beside_a_not_clear_standing_is_honest(
    tmp_path: Path,
) -> None:
    plant(tmp_path, whole(EARLY, 24, "not clear"), whole(PASSING))

    assert findings(tmp_path, switched(cited(EARLY, 24, False), cited(PASSING))) == []


def test_a_passing_run_whose_sessions_give_nineteen_pairs_is_refused_whatever_it_claims(
    tmp_path: Path,
) -> None:
    plant(tmp_path, whole(PASSING, kl.REQUIRED_PAIRS - 1))

    assert kinds(tmp_path, switched(cited(PASSING, 24))) == [
        "I9-run-pairs-differ",
        "I9-run-passing-short",
    ]


def test_a_passing_run_of_twenty_pairs_standing_clear_passes(tmp_path: Path) -> None:
    plant(tmp_path, whole(PASSING, kl.REQUIRED_PAIRS))

    assert findings(tmp_path, switched(cited(PASSING, kl.REQUIRED_PAIRS))) == []


def test_a_closed_lineage_stands_not_clear_whatever_its_file_records(tmp_path: Path) -> None:
    closed = results(PASSING, pairs_of(24), standing([PASSING]), ending={"kind": "closed"})
    plant(tmp_path, closed)

    assert kinds(tmp_path, PASSING_ALONE) == [
        "I9-run-index-flip-differs",
        "I9-run-flag-disagrees",
        "I9-run-passing-short",
    ]


def test_a_cited_run_whose_results_measured_another_role_is_refused(tmp_path: Path) -> None:
    other = results(PASSING, pairs_of(24, "verifier"), standing([PASSING], role="verifier"))
    plant(tmp_path, other)

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == ["I9-run-wrong-role"]
    assert "whose results measured verifier, not researcher" in found[0][1]


def test_a_cited_run_whose_results_measured_two_other_roles_names_both_in_order(
    tmp_path: Path,
) -> None:
    sessions = [*pairs_of(2, "verifier"), *pairs_of(2, "planner")]
    plant(tmp_path, results(PASSING, sessions, standing([PASSING], role="verifier")))

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == ["I9-run-wrong-role"]
    assert "whose results measured planner, verifier, not researcher" in found[0][1]


def test_a_cited_run_whose_results_measured_no_role_says_so(tmp_path: Path) -> None:
    plant(tmp_path, results(PASSING, [], standing([PASSING], 0)))

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == ["I9-run-wrong-role"]
    assert "whose results measured no role, not researcher" in found[0][1]


def test_a_cited_run_the_index_does_not_list_is_refused_naming_role_and_run(tmp_path: Path) -> None:
    plant(tmp_path, whole(EARLY, 13, "underpowered"))

    assert findings(tmp_path, EARLY_AND_PASSING) == [
        (
            "I9-run-missing",
            f"role {ROLE} -- cites run {PASSING!r}, which has no readable results file in "
            f"{kri.RESULTS_DIR}",
        )
    ]


def test_a_part_cited_with_other_pairs_is_judged_against_the_whole_lineage(tmp_path: Path) -> None:
    first = results(PART_ONE, pairs_of(24), None)
    tip = results(PART_TWO, pairs_of(24), standing([PART_ONE, PART_TWO]), continues=PART_ONE)
    plant(tmp_path, first, tip)

    found = findings(tmp_path, switched(cited(PART_TWO, 20), passing=PART_TWO))

    assert [kind for kind, _ in found] == ["I9-run-pairs-differ"]
    assert f"the lineage of {PART_ONE!r} (parts {PART_ONE}, {PART_TWO}) reached 24" in found[0][1]


def test_a_cited_run_the_results_files_cannot_chain_is_refused_as_missing(tmp_path: Path) -> None:
    first = results(PART_ONE, pairs_of(24), None)
    fork = [
        results(part, pairs_of(24), standing([PART_ONE, part]), continues=PART_ONE)
        for part in (PART_TWO, PART_THREE)
    ]
    plant(tmp_path, first, *fork)

    found = findings(tmp_path, switched(cited(PART_TWO), passing=PART_TWO))

    assert [kind for kind, _ in found] == ["I9-run-missing"]
    assert "whose results files give no one lineage" in found[0][1]
    assert f"cites run {PART_TWO!r}" in found[0][1]


# -- The index beside the results ---------------------------------------------------------------


def test_an_index_raising_a_runs_pairs_is_refused_naming_both_figures(tmp_path: Path) -> None:
    plant(tmp_path, whole(PASSING), edit=edit_roles(PASSING, complete_pairs=30))

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == ["I9-run-index-pairs-differ"]
    assert f"the index lists run {PASSING!r} with 30 complete pairs" in found[0][1]
    assert "reached 24 complete pairs" in found[0][1]


def test_an_index_listing_no_standing_for_the_role_is_refused(tmp_path: Path) -> None:
    plant(tmp_path, whole(PASSING), edit=lambda index: index["runs"][PASSING]["roles"].clear())

    found = findings(tmp_path, PASSING_ALONE)

    assert [kind for kind, _ in found] == ["I9-run-index-pairs-differ"]
    assert "with no standing" in found[0][1]


def test_an_index_labelling_a_not_clear_run_clear_is_refused_naming_both_labels(
    tmp_path: Path,
) -> None:
    plant(
        tmp_path,
        whole(EARLY, 24, "not clear"),
        whole(PASSING),
        edit=edit_roles(EARLY, flip="clear"),
    )

    found = findings(tmp_path, switched(cited(EARLY, 24, False), cited(PASSING)))

    assert [kind for kind, _ in found] == ["I9-run-index-flip-differs"]
    assert f"the index labels run {EARLY!r} 'clear'" in found[0][1]
    assert "stands not clear" in found[0][1]


def test_an_index_regrouping_two_runs_into_one_lineage_is_refused_for_each(tmp_path: Path) -> None:
    plant(
        tmp_path,
        whole(EARLY, 13, "underpowered"),
        whole(PASSING),
        edit=edit_entry(PASSING, lineage_root=EARLY),
    )

    found = findings(tmp_path, EARLY_AND_PASSING)

    assert [kind for kind, _ in found] == ["I9-run-lineage-differs", "I9-run-lineage-differs"]
    assert f"the index lists the lineage of run {EARLY!r} as {EARLY}, {PASSING}" in found[0][1]
    assert f"the results files chain {PASSING}" in found[1][1]


@pytest.mark.parametrize("part", [PART_ONE, PART_TWO])
def test_a_continued_run_is_one_lineage_whichever_part_is_cited(tmp_path: Path, part: str) -> None:
    first = results(PART_ONE, pairs_of(24), None)
    tip = results(PART_TWO, pairs_of(24), standing([PART_ONE, PART_TWO]), continues=PART_ONE)
    plant(tmp_path, first, tip)

    assert findings(tmp_path, switched(cited(part), passing=part)) == []


def test_a_results_file_recording_more_pairs_than_its_sessions_give_is_refused(
    tmp_path: Path,
) -> None:
    plant(tmp_path, results(PASSING, pairs_of(24), standing([PASSING], 30)))

    found = findings(tmp_path, switched(cited(PASSING, 30)))

    assert sorted(kind for kind, _ in found) == [
        "I9-run-index-pairs-differ",
        "I9-run-pairs-differ",
        "I9-run-recorded-pairs-differ",
    ]
    recorded = next(text for kind, text in found if kind == "I9-run-recorded-pairs-differ")
    assert f"records 30 complete pairs for run {PASSING!r}" in recorded
    assert "reached 24 complete pairs" in recorded


def test_a_lineage_whose_last_part_records_no_standing_is_refused_naming_role_and_run(
    tmp_path: Path,
) -> None:
    first = results(PART_ONE, pairs_of(24), None)
    unfinished = results(PART_TWO, pairs_of(24), None, continues=PART_ONE)
    plant(tmp_path, first, unfinished)

    found = findings(tmp_path, switched(cited(PART_TWO), passing=PART_TWO))

    assert [kind for kind, _ in found] == ["I9-run-standing-unrecorded"]
    assert f"role {ROLE}" in found[0][1]
    assert f"cites run {PART_TWO!r}, whose lineage records no standing for {ROLE}" in found[0][1]


def test_a_ledger_that_is_not_switched_judges_no_run(tmp_path: Path) -> None:
    plant(tmp_path, whole(PASSING, 5))

    assert lc.cited_run_findings(None, kri.read_adherence(tmp_path)) == ()


def test_a_trial_record_cites_runs_that_are_not_judged(tmp_path: Path) -> None:
    plant(tmp_path, whole(PASSING, 5))
    trial = {"status": "trial", "since": "2026-10-12", "runs": [cited(PASSING, 30)]}
    ledger = kl.parse_ledger({"version": 1, "roles": {ROLE: trial}}, frozenset(ELIGIBLE_ROLES))

    assert findings(tmp_path, ledger) == []
