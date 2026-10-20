"""Tests for the convention-check finding of kernel_ledger_checks.py: the passing run scored it.

Each case plants one results file per run (as the adherence eval writes them) and the index that
describes them in a directory of its own, then judges a switched record against both. A canary per
way the check goes unscored, beside the known-good run that scored it. Imports gate modules only
(never `check_kernel_manifest`), so the mutation sensor can run it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_ledger as kl  # noqa: E402
import kernel_ledger_checks as lc  # noqa: E402
import kernel_run_evidence as kre  # noqa: E402
import kernel_run_index as kri  # noqa: E402
from kernel_eligibility import ELIGIBLE_ROLES  # noqa: E402

ROLE = "researcher"
EARLY, PASSING = "20261101T000000Z-early0", "20261102T000000Z-pass00"
PAIRS = kl.REQUIRED_PAIRS
CONVENTION = kre.convention_check_name(ROLE)
OTHER_CHECK = "C1"
UNSCORED = "I9-run-convention-unscored"


# -- Builders: a results file, the index that describes it, a switched record ----------------


def sessions() -> list[dict]:
    return [
        {
            "setup": {"arm": arm, "role": ROLE, "task_id": f"t{n}", "template_id": f"x-t{n}"},
            "status": {"kind": "measured"},
        }
        for n in range(PAIRS)
        for arm in ("full", "lean")
    ]


def results_file(run_id: str, scored: list[str], flip: str = "clear") -> dict:
    """A one-part run of `PAIRS` complete pairs whose recorded standing scored `scored`."""
    entry = {
        "lineage_root": run_id,
        "parts": [run_id],
        "complete_pairs": PAIRS,
        "flip": flip,
        "scored_checks": sorted(scored),
    }
    return {
        "schema_version": "adherence/1",
        "run": {"id": run_id},
        "sessions": sessions(),
        "standing": {ROLE: entry},
    }


def legacy_file(run_id: str, verdict_checks: list[str], not_covered: list[str]) -> dict:
    """A one-part run written before `standing` existed: the verdict is the standing."""
    verdict = {
        "complete_pairs": PAIRS,
        "flip": "clear",
        "check_verdicts": dict.fromkeys(verdict_checks, "pass"),
        "not_covered": not_covered,
    }
    file = {key: value for key, value in results_file(run_id, []).items() if key != "standing"}
    return {**file, "verdicts": {ROLE: verdict}}


def plant(tmp_path: Path, *files: dict) -> None:
    """Write each results file and the schema-2 index the eval would write over them."""
    directory = tmp_path / kri.RESULTS_DIR
    directory.mkdir(parents=True)
    entries = {}
    for file in files:
        run_id = file["run"]["id"]
        raw = json.dumps(file).encode("utf-8")
        (directory / f"{run_id}.json").write_bytes(raw)
        entries[run_id] = index_entry(file, raw)
    index = {"schema": kri.INDEX_SCHEMA, "runs": entries, "skipped": []}
    (directory / kri.INDEX_NAME).write_text(json.dumps(index), encoding="utf-8")


def index_entry(file: dict, raw: bytes) -> dict[str, Any]:
    run_id = file["run"]["id"]
    recorded = file.get("standing") or {
        ROLE: {
            "complete_pairs": PAIRS,
            "flip": "clear",
            "scored_checks": sorted(set(file["verdicts"][ROLE]["check_verdicts"])),
        }
    }
    kept = ("complete_pairs", "flip", "scored_checks")
    return {
        "file": f"{run_id}.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "lineage_root": run_id,
        "ending": "finished",
        "roles": {role: {key: entry[key] for key in kept} for role, entry in recorded.items()},
    }


def cited(run_id: str, passes: bool = True) -> dict:
    return {
        "id": run_id,
        "complete_pairs": PAIRS,
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


# -- The passing run scored the role's convention check --------------------------------------


def test_a_passing_run_that_scored_the_convention_check_passes(tmp_path: Path) -> None:
    plant(tmp_path, results_file(PASSING, [OTHER_CHECK, CONVENTION]))

    assert findings(tmp_path, switched(cited(PASSING))) == []


def test_a_passing_run_that_left_the_convention_check_uncovered_is_refused(tmp_path: Path) -> None:
    plant(tmp_path, results_file(PASSING, [OTHER_CHECK]))

    found = findings(tmp_path, switched(cited(PASSING)))

    assert [kind for kind, _ in found] == [UNSCORED]
    assert f"role {ROLE}" in found[0][1]
    assert f"run {PASSING!r}" in found[0][1]
    assert f"did not score {CONVENTION!r}: it scored {OTHER_CHECK}" in found[0][1]


def test_a_passing_run_whose_verdict_records_no_scored_checks_is_refused(tmp_path: Path) -> None:
    plant(tmp_path, results_file(PASSING, []))

    found = findings(tmp_path, switched(cited(PASSING)))

    assert [kind for kind, _ in found] == [UNSCORED]
    assert f"run {PASSING!r}" in found[0][1]
    assert "it scored no check" in found[0][1]


def test_an_earlier_cited_run_need_not_have_scored_the_convention_check(tmp_path: Path) -> None:
    plant(
        tmp_path,
        results_file(EARLY, [OTHER_CHECK], flip="not clear"),
        results_file(PASSING, [CONVENTION]),
    )

    assert findings(tmp_path, switched(cited(EARLY, passes=False), cited(PASSING))) == []


def test_a_run_before_the_standing_was_recorded_is_judged_from_its_verdict(tmp_path: Path) -> None:
    scored = legacy_file(PASSING, [OTHER_CHECK, CONVENTION], not_covered=[])
    uncovered = legacy_file(EARLY, [OTHER_CHECK, CONVENTION], not_covered=[CONVENTION])
    plant(tmp_path, scored, uncovered)

    assert findings(tmp_path, switched(cited(PASSING))) == []
    found = findings(tmp_path, switched(cited(EARLY), passing=EARLY))
    assert [kind for kind, _ in found] == [UNSCORED]
    assert f"run {EARLY!r}" in found[0][1]
