"""Characterization test for the triage write protocol.

This suite exercises **existing, untouched** `check_state_ledgers.py` --
The `/triage-debt` command relies on running `--backfill` then `--check`
after every triage write , and the hazard it guards
against is not triage-specific: any notes edit on a discriminated row already
flips `check_dedup_keys` to a blocking `dedup-mismatch`. No new production
code is needed for this file to pass -- it needs no `ledger_snapshot.py` or
`ledger_health.py` import, so it is not expected to show the RED signature
the paired suites show; it is a green characterization of a contract the
command is built to satisfy.

Fixture pattern mirrors `scripts/test_check_state_ledgers.py`: a synthetic
`.ai-state/` ledger pair, driven through the real CLI via subprocess (the
shape `/triage-debt` itself will invoke).
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from state_ledger_schema import normalize_location

SCRIPT_PATH = Path(__file__).resolve().parent / "check_state_ledgers.py"

HEADER = (
    "# Technical Debt Ledger\n\n**Schema**: 14 row fields + 1 structural `dedup_key`.\n\n"
    "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | "
    "source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |\n"
    "|----|----------|-------|-----------|----------|---------------|----------------|"
    "--------|------------|-----------|-----------|--------|-------------|-------|-----------|\n"
)

RESOLVED_HEADER = HEADER  # same schema, same header shape


def _base_key(*, klass: str, location: str, direction: str, goal_type: str, goal_value: str) -> str:
    payload = "|".join((klass, normalize_location(location), direction, goal_type, goal_value))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]  # noqa: S324 - identity, test fixture


def _notes_digest(notes: str) -> str:
    return hashlib.sha1(notes.encode("utf-8")).hexdigest()[:8]  # noqa: S324 - identity, test fixture


def _row(row_id: str, *, klass: str, location: str, notes: str, dedup_key: str) -> str:
    cells = [
        row_id,
        "suggested",
        klass,
        "code-to-goals",
        location,
        "code-quality",
        "",
        "verifier",
        "2026-01-01",
        "2026-01-01",
        "implementer",
        "open",
        "",
        notes,
        dedup_key,
    ]
    return "| " + " | ".join(cells) + " |\n"


def _run(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-root", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_pair(repo_root: Path, *, discriminated_notes: str, plain_notes: str) -> tuple[str, str]:
    """One discriminated row (`td-800`) sharing a base key with `td-801`, plus
    one plain row (`td-802`) with no colliding peer. Returns (discriminated_key,
    plain_key) so the caller can compute the "amended" key after editing notes.
    """
    common = {
        "klass": "other",
        "location": "scripts/a.py",
        "direction": "code-to-goals",
        "goal_type": "code-quality",
        "goal_value": "",
    }
    base = _base_key(**common)
    discriminated_key = hashlib.sha1(
        (
            f"{common['klass']}|{normalize_location(common['location'])}|"
            f"{common['direction']}|{common['goal_type']}|{common['goal_value']}|"
            f"{_notes_digest(discriminated_notes)}"
        ).encode()
    ).hexdigest()[:12]  # noqa: S324 - identity, test fixture

    plain_key = _base_key(
        klass="other",
        location="scripts/b.py",
        direction="code-to-goals",
        goal_type="code-quality",
        goal_value="",
    )

    state = repo_root / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    rows = (
        _row(
            "td-800",
            klass="other",
            location="scripts/a.py",
            notes=discriminated_notes,
            dedup_key=discriminated_key,
        )
        + _row(
            "td-801",
            klass="other",
            location="scripts/a.py",
            notes="the base-key holder",
            dedup_key=base,
        )
        + _row(
            "td-802", klass="other", location="scripts/b.py", notes=plain_notes, dedup_key=plain_key
        )
    )
    (state / "TECH_DEBT_LEDGER.md").write_text(HEADER + rows, encoding="utf-8")
    (state / "TECH_DEBT_RESOLVED.md").write_text(RESOLVED_HEADER, encoding="utf-8")
    return discriminated_key, plain_key


def _append_stamp(repo_root: Path, row_id: str, stamp: str) -> None:
    """Simulate a triage write: append ` // <stamp>` to one row's `notes` cell."""
    path = repo_root / ".ai-state" / "TECH_DEBT_LEDGER.md"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith(f"| {row_id} "):
            cells = line.rstrip("\n").split("|")
            # cells[0] is "" (leading pipe), cells[-1] is "" (trailing pipe),
            # cells[-2] is dedup_key, so notes is cells[-3].
            cells[-3] = f" {cells[-3].strip()} // {stamp} "
            lines[i] = "|".join(cells) + "\n"
            break
    else:
        raise AssertionError(f"{row_id} not found in {path}")
    path.write_text("".join(lines), encoding="utf-8")


# -- The characterization -------------------------------------------------------


def test_triage_stamp_on_discriminated_row_blocks_check_with_dedup_mismatch(
    tmp_path: Path,
) -> None:
    discriminated_notes = "the discriminated finding"
    discriminated_key, _ = _seed_pair(
        tmp_path, discriminated_notes=discriminated_notes, plain_notes="the plain finding"
    )

    clean = _run(tmp_path, "--check")
    assert clean.returncode == 0, f"fixture must start clean: {clean.stdout}\n{clean.stderr}"

    _append_stamp(tmp_path, "td-800", "[triage 2026-09-27 @abc1234] kept: scripts/a.py good")

    dirty = _run(tmp_path, "--check", "--json")
    assert dirty.returncode == 1
    import json

    payload = json.loads(dirty.stdout)
    kinds = {f["kind"] for f in payload["findings"] if f["row_id"] == "td-800"}
    assert "dedup-mismatch" in kinds


def test_backfill_then_check_is_clean_after_the_same_triage_stamp(tmp_path: Path) -> None:
    discriminated_notes = "the discriminated finding"
    _seed_pair(tmp_path, discriminated_notes=discriminated_notes, plain_notes="the plain finding")
    _append_stamp(tmp_path, "td-800", "[triage 2026-09-27 @abc1234] kept: scripts/a.py good")

    dirty = _run(tmp_path, "--check")
    assert dirty.returncode == 1

    backfilled = _run(tmp_path, "--backfill")
    assert backfilled.returncode == 0

    clean = _run(tmp_path, "--check")
    assert clean.returncode == 0, f"{clean.stdout}\n{clean.stderr}"


def test_triage_stamp_on_a_plain_row_never_needs_a_backfill(tmp_path: Path) -> None:
    """A plain (non-colliding) row's `dedup_key` never depends on `notes` --
    the 5-tuple formula excludes it -- so the same edit leaves `--check` clean
    with no backfill step at all."""
    _seed_pair(
        tmp_path, discriminated_notes="the discriminated finding", plain_notes="the plain finding"
    )
    _append_stamp(tmp_path, "td-802", "[triage 2026-09-27 @abc1234] kept: scripts/b.py good")

    result = _run(tmp_path, "--check")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
