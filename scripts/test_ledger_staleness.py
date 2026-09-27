"""Tests for triage-stamp staleness: a judged row resurfaces only when its window moved.

A row stamped by `/triage-debt` is judged against the commit its stamp names. From then
on its evidence is computed over `anchor..HEAD`, not `first-seen..HEAD`, so a kept row
stays quiet until something it depends on changes -- and comes back the moment it does.
Every case builds a real, hermetic git repo holding one row, `td-902`, located at
`scripts/x.py`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import ledger_health
import ledger_snapshot
from _ledger_triage_testkit import IDENTITY, git_ok, one_row_repo

SCRIPT_PATH = Path(__file__).resolve().parent / "ledger_health.py"
LEDGER = Path(".ai-state") / "TECH_DEBT_LEDGER.md"
RESOLVED = Path(".ai-state") / "TECH_DEBT_RESOLVED.md"


def _commit(repo_root: Path, message: str) -> None:
    git_ok(repo_root, "add", "-A")
    git_ok(repo_root, *IDENTITY, "commit", "-q", "-m", message)


def _head(repo_root: Path) -> str:
    return git_ok(repo_root, "rev-parse", "--short=12", "HEAD").stdout.strip()


KEPT = "kept: scripts/x.py:1 holds"


def _stamp(repo_root: Path, verdict: str = KEPT) -> None:
    """Judge td-902 against the current HEAD and commit the stamp on top."""
    stamp = f"[triage 2026-09-27 @{_head(repo_root)}] {verdict}"
    ledger = repo_root / LEDGER
    ledger.write_text(
        ledger.read_text().replace(" | 000000000000 |", f" // {stamp} | 000000000000 |")
    )
    _commit(repo_root, "chore(state): triage td-902")


def _stamped_repo(tmp_path: Path, verdict: str = KEPT) -> Path:
    """td-902 judged against the seed commit, the stamp itself committed on top."""
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    _stamp(repo_root, verdict)
    return repo_root


def _relocate(repo_root: Path, location: str) -> None:
    ledger = repo_root / LEDGER
    ledger.write_text(ledger.read_text().replace("| scripts/x.py |", f"| {location} |"))
    _commit(repo_root, f"chore(state): relocate td-902 to {location}")


def _write_adr(repo_root: Path, name: str, dec_id: str, status: str, extra: str = "") -> None:
    """An ADR dated long before any anchor: only its tree membership places it in time."""
    decisions = repo_root / ".ai-state" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / name).write_text(
        f"---\nid: {dec_id}\ntitle: T\nstatus: {status}\ndate: 2026-01-01\n{extra}---\n\nB.\n"
    )


def _row_citing_dec_010(tmp_path: Path, status: str, extra: str = "") -> Path:
    repo_root = one_row_repo(tmp_path, "Premise per dec-010.", ())
    _write_adr(repo_root, "010-old.md", "dec-010", status, extra)
    _commit(repo_root, "docs: dec-010")
    return repo_root


def _delta(repo_root: Path) -> ledger_snapshot.RowDelta:
    snapshot = ledger_snapshot.gather(repo_root)
    (row,) = [row for row in snapshot.active_rows if row.id == "td-902"]
    return ledger_snapshot.row_delta(snapshot, row)


def _classes(repo_root: Path) -> set[str]:
    return {ledger_snapshot.signal_class_name(signal) for signal in _delta(repo_root).signals}


def _signal_types(repo_root: Path) -> set[str]:
    return {type(signal).__name__ for signal in _delta(repo_root).signals}


# -- A judged row whose window has not moved stays quiet ----------------------------------


def test_a_kept_row_is_not_a_candidate_while_nothing_it_depends_on_moved(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    assert _classes(repo_root) == set()


def test_a_judged_row_is_windowed_at_its_stamp_not_its_first_seen(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    assert type(_delta(repo_root).window).__name__ == "AnchorWindow"


# -- Each trigger brings it back -------------------------------------------------------------


def test_editing_the_kept_evidence_file_resurfaces_the_row(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    (repo_root / "scripts" / "x.py").write_text("changed\n")
    _commit(repo_root, "fix: touch the evidence")

    assert "evidence-moved" in _classes(repo_root)


def test_deleting_the_location_after_the_stamp_resurfaces_the_row(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    git_ok(repo_root, "rm", "-q", "scripts/x.py")
    _commit(repo_root, "chore: remove x")

    assert "location-decay" in _classes(repo_root)


def test_deleting_a_directory_location_after_the_stamp_resurfaces_the_row(tmp_path: Path) -> None:
    """Git lists files, never directories: the anchor tree holds `scripts/pkg/a.py`, not
    `scripts/pkg/`, and the directory must still count as present at the anchor."""
    repo_root = one_row_repo(tmp_path, "Premise.", ("scripts/pkg/a.py",))
    _relocate(repo_root, "scripts/pkg/")
    _stamp(repo_root)
    git_ok(repo_root, "rm", "-r", "-q", "scripts/pkg")
    _commit(repo_root, "chore: remove pkg")

    assert "location-decay" in _classes(repo_root)


def test_a_kept_row_on_a_directory_that_still_exists_stays_quiet(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ("scripts/pkg/a.py",))
    _relocate(repo_root, "scripts/pkg/")
    _stamp(repo_root)

    assert _classes(repo_root) == set()


def test_a_later_decision_superseding_another_on_the_location_resurfaces_the_row(
    tmp_path: Path,
) -> None:
    repo_root = _stamped_repo(tmp_path)
    decisions = repo_root / ".ai-state" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "002-new.md").write_text(
        "---\nid: dec-002\ntitle: New\nstatus: accepted\ndate: 2099-01-01\n"
        "supersedes: dec-001\naffected_files:\n  - scripts/x.py\n---\n\nBody.\n"
    )
    (decisions / "001-old.md").write_text(
        "---\nid: dec-001\ntitle: Old\nstatus: superseded\ndate: 2026-01-01\n"
        "superseded_by: dec-002\naffected_files:\n  - scripts/x.py\n---\n\nBody.\n"
    )
    _commit(repo_root, "docs: supersede dec-001")

    snapshot = ledger_snapshot.gather(repo_root)
    (item,) = [a for a in ledger_health.assess(snapshot) if a.row.id == "td-902"]
    assert "decision-drift" in item.classes
    assert item.tier == "medium"


# -- A stamp that cannot be trusted resurfaces the row, never silences it -------------------


def test_a_stamp_anchored_to_an_unknown_commit_is_unusable(tmp_path: Path) -> None:
    repo_root = one_row_repo(
        tmp_path, "Premise. // [triage 2026-09-27 @abc1234def56] kept: scripts/x.py:1 ok", ()
    )
    assert "judgment-unusable" in _classes(repo_root)


def test_a_discard_stamp_on_a_row_that_is_still_active_is_unusable(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path, "discarded: premise refuted at scripts/x.py:1")
    assert "judgment-unusable" in _classes(repo_root)


def test_without_git_a_stamped_row_is_withheld_not_flagged(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    shutil.rmtree(repo_root / ".git")

    snapshot = ledger_snapshot.gather(repo_root)
    assert "judgment-unusable" not in _classes(repo_root)
    assert "judgment-unusable:unanchored" in {w.class_name for w in snapshot.withheld}


# -- A tombstone that keeps being re-detected is surfaced -----------------------------------


def test_a_discarded_row_re_detected_after_its_stamp_is_reported(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    ledger, resolved = repo_root / LEDGER, repo_root / RESOLVED
    header, row = ledger.read_text().rsplit("\n| td-902", 1)
    stamp = f"[triage 2026-09-27 @{_head(repo_root)}] discarded: moot per td-903"
    row = (
        ("| td-902" + row)
        .replace("| 2026-01-01 | 2026-01-01 |", "| 2026-01-01 | 2026-10-05 |")
        .replace("| open |", "| wontfix |")
        .replace("| Premise. |", f"| Premise. // {stamp} |")
    )
    ledger.write_text(header + "\n")
    resolved.write_text(resolved.read_text() + row)
    _commit(repo_root, "chore(state): discard td-902")

    snapshot = ledger_snapshot.gather(repo_root)
    (found,) = ledger_snapshot.discard_recurrences(snapshot)
    assert found[0].id == "td-902"


# -- TD07: the sentinel family envelope ------------------------------------------------------


def _td07(repo_root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_td07_emits_exactly_the_flat_family_envelope(tmp_path: Path) -> None:
    envelope = _td07(_stamped_repo(tmp_path))
    assert set(envelope) == {"check", "skipped", "examined", "findings", "info", "bound"}
    assert envelope["check"] == "TD07"


def test_td07_reports_a_medium_tier_candidate_as_info(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    (repo_root / "scripts" / "x.py").write_text("changed\n")
    _commit(repo_root, "fix: touch the evidence")

    findings = _td07(repo_root)["findings"]
    (finding,) = [f for f in findings if f["entity"] == "td-902"]
    assert finding["severity"] == "info"


def test_td07_reports_an_unavailable_oracle_as_a_warning(tmp_path: Path) -> None:
    """This repo has no ADR corpus: the decision classes are withheld, and say so."""
    findings = _td07(_stamped_repo(tmp_path))["findings"]
    withheld = {f["entity"] for f in findings if f["kind"] == "triage-withheld"}
    assert "decision-drift" in withheld


def test_td07_never_writes_the_ledger(tmp_path: Path) -> None:
    repo_root = _stamped_repo(tmp_path)
    before = (repo_root / LEDGER).read_bytes()
    _td07(repo_root)
    assert (repo_root / LEDGER).read_bytes() == before
