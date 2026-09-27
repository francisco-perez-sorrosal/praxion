"""Tests for `ledger_health.py` -- the probe's CLI, digest, and policy surface.

Drives the CLI as a subprocess wherever the assertion is about *behavior*
(the public wire contract a judge or the sentinel consumes) rather than
internal representation -- `ledger_health.py`'s own file does not exist yet,
so every test here is expected to fail at collection or at first invocation
with `ModuleNotFoundError` / a non-existent-script `FileNotFoundError`
surfaced through a non-zero, unexpected subprocess result. That is the RED
signature this file is designed to produce; see `TEST_RESULTS.md`.

The probe's CLI scope here is `--digest` / `--all` / `--ids` / `--class` /
`--repo-root` only -- **not** `--json` (the flat TD07 envelope comes
later, since it needs the anchor/window machinery that step adds). Every
test below stays inside that scope.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import ledger_health
import ledger_snapshot
import pytest
from _ledger_triage_testkit import build_fixture_repo

# `base_repo` is a pytest fixture from `conftest.py` (no import needed --
# pytest auto-discovers it by parameter name).

SCRIPT_PATH = Path(__file__).resolve().parent / "ledger_health.py"

REQUIRED_ROW_KEYS = {
    "id",
    "row",
    "key",
    "judgment",
    "candidate_classes",
    "evidence",
    "context",
    "withheld",
    "rank",
}
REQUIRED_ENVELOPE_KEYS = {
    "schema",
    "head",
    "anchor",
    "generated_at",
    "oracles",
    "withheld",
    "rows",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _digest(repo_root: Path, *extra: str) -> dict:
    result = _run("--digest", "--repo-root", str(repo_root), *extra)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return json.loads(result.stdout)


# -- Advisory contract (`--digest` half) ---------------------------------


def test_digest_leaves_ledger_files_byte_identical_and_exits_zero(base_repo: Path) -> None:
    ledger_path = base_repo / ".ai-state" / "TECH_DEBT_LEDGER.md"
    resolved_path = base_repo / ".ai-state" / "TECH_DEBT_RESOLVED.md"
    before = (ledger_path.read_bytes(), resolved_path.read_bytes())
    result = _run("--digest", "--all", "--repo-root", str(base_repo))
    after = (ledger_path.read_bytes(), resolved_path.read_bytes())
    assert result.returncode == 0
    assert before == after
    payload = json.loads(result.stdout)
    assert payload["rows"], "expected findings on the frozen fixture"


def test_script_carries_the_executable_bit() -> None:
    """`os.access(path, X_OK)` -- required by the installer filter so the
    shipped `/triage-debt` command finds this script on `PATH`."""
    assert SCRIPT_PATH.exists(), f"expected {SCRIPT_PATH} to exist"
    assert os.access(SCRIPT_PATH, os.X_OK), f"{SCRIPT_PATH} is missing its executable bit"


# -- Digest contract --------------------------------------------


def test_digest_envelope_has_every_required_top_level_key(base_repo: Path) -> None:
    payload = _digest(base_repo, "--all")
    assert REQUIRED_ENVELOPE_KEYS <= payload.keys()
    assert payload["schema"] == "ledger-triage-digest/1"


def test_digest_row_carries_every_required_field(base_repo: Path) -> None:
    payload = _digest(base_repo, "--ids", "td-064")
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert REQUIRED_ROW_KEYS <= row.keys()
    assert row["id"] == "td-064"
    assert row["row"]["notes"], "notes must be carried verbatim, not summarized"


@pytest.mark.parametrize("row_id", ["td-257", "td-264", "td-270", "td-281"])
def test_digest_reports_discriminated_key_status(base_repo: Path, row_id: str) -> None:
    payload = _digest(base_repo, "--ids", row_id)
    assert payload["rows"][0]["key"]["status"] == "discriminated"


def test_digest_all_returns_every_active_row_candidates_first(base_repo: Path) -> None:
    payload = _digest(base_repo, "--all")
    ids = [row["id"] for row in payload["rows"]]
    assert len(ids) == 17, f"expected all 17 fixture rows, got {len(ids)}"
    candidate_ids = {row["id"] for row in payload["rows"] if row["candidate_classes"]}
    first_seven_ids = ids[: len(candidate_ids)]
    assert set(first_seven_ids) == candidate_ids, "candidates must sort first"


def test_ids_filter_restricts_output_to_named_rows(base_repo: Path) -> None:
    payload = _digest(base_repo, "--ids", "td-064,td-185")
    assert {row["id"] for row in payload["rows"]} == {"td-064", "td-185"}


def test_class_filter_restricts_to_rows_carrying_that_evidence_class(base_repo: Path) -> None:
    payload = _digest(base_repo, "--all", "--class", "self-amended")
    for row in payload["rows"]:
        assert "self-amended" in row["candidate_classes"]
    ids = {row["id"] for row in payload["rows"]}
    assert "td-064" in ids
    assert "td-185" not in ids


# -- Withheld reporting (corpus scope) -----------------------------------


def test_missing_adr_corpus_reports_corpus_scope_withheld(tmp_path: Path) -> None:
    repo_root = build_fixture_repo(tmp_path, "base")
    import shutil

    shutil.rmtree(repo_root / ".ai-state" / "decisions")

    payload = _digest(repo_root, "--all")
    corpus_withheld = {
        entry["class"] for entry in payload["withheld"] if entry.get("scope") == "corpus"
    }
    assert "decision-drift" in corpus_withheld
    assert "goal-link-unresolved" in corpus_withheld


# -- Script errors -------------------------------------------------------------------


def test_plugin_cache_repo_root_is_refused_with_exit_two(tmp_path: Path) -> None:
    """An installed plugin's cache is never a project to probe."""
    cache_root = tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0"
    cache_root.mkdir(parents=True)
    result = _run("--digest", "--repo-root", str(cache_root))
    assert result.returncode == 2
    assert "plugin-cache" in result.stderr


# -- Stamp check: shape is not enough, every anchor must resolve ---------------------------

_STAMP = "[triage 2026-09-27 @9ad0e205c05f] "


def _refusals(repo_root: Path, row_id: str, text: str, commits: bool = True) -> list[str]:
    snapshot = ledger_snapshot.gather(repo_root)
    return ledger_health.stamp_refusals(snapshot, row_id, _STAMP + text, lambda _r, _s: commits)


def test_a_stamp_whose_anchors_all_resolve_may_be_written(base_repo: Path) -> None:
    assert _refusals(base_repo, "td-270", "kept: scripts/check_gate_liveness.py:10 holds") == []


def test_a_discard_citing_a_decision_that_does_not_exist_is_refused(base_repo: Path) -> None:
    (reason,) = _refusals(base_repo, "td-270", "discarded: made moot by dec-999")
    assert "dec-999" in reason


def test_a_row_cannot_anchor_its_own_discard(base_repo: Path) -> None:
    reasons = _refusals(base_repo, "td-270", "discarded: duplicate of td-270")
    assert any("own stamp" in reason for reason in reasons)


def test_a_discard_citing_an_unreachable_commit_is_refused(base_repo: Path) -> None:
    (reason,) = _refusals(base_repo, "td-270", "discarded: fixed by c95a9e96", commits=False)
    assert "c95a9e96" in reason


def test_a_merge_into_a_resolved_row_is_refused(base_repo: Path) -> None:
    reasons = _refusals(base_repo, "td-270", "merged into td-095")
    assert any("survivor" in reason for reason in reasons)


def test_a_stamp_for_a_row_that_is_not_active_is_refused(base_repo: Path) -> None:
    (reason,) = _refusals(base_repo, "td-095", "kept: scripts/check_gate_liveness.py:10 holds")
    assert "not an active row" in reason


def test_the_stamp_check_cli_exits_one_on_refusal_and_zero_when_clean(base_repo: Path) -> None:
    root = ("--repo-root", str(base_repo))
    clean = _run(
        *root,
        "--row",
        "td-270",
        "--check-stamp",
        _STAMP + "kept: scripts/check_gate_liveness.py:1 ok",
    )
    refused = _run(
        *root, "--row", "td-270", "--check-stamp", _STAMP + "discarded: moot per dec-999"
    )
    assert (clean.returncode, clean.stdout.strip()) == (0, "ok")
    assert refused.returncode == 1
    assert "dec-999" in refused.stdout


def test_check_stamp_without_a_row_is_a_usage_error() -> None:
    assert _run("--check-stamp", _STAMP + "kept: a/b.py:1 ok").returncode == 2
