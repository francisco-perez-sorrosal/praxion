"""Tests for check_doc_manifest_freshness.py -- F11's manifest-freshness check.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input, not merely that it passes on the current good
state.

All tests build a hermetic git repo in `tmp_path` with explicit
`GIT_COMMITTER_DATE`/`GIT_AUTHOR_DATE` per commit, so ordering between
`generated_at` and a commit's committer date is fully controlled rather than
racing real wall-clock time.

The golden bad-case and both inverse guards are drawn straight from the
check's own docstring: a manifest whose `generated_at` predates a later
add/delete/rename under `docs/` or `.ai-state/` must WARN; a commit that only
edits the body of an already-indexed file must not; the manifest's own
regeneration commit (which routinely also touches `docs/` in the same commit)
must not.

The three skip-state tests below are this rework's own canary: before it,
`run_f11` returned a bare `[]` for all three states (and for the two clean
states), so a consumer could not tell "could not run" from "ran and found
nothing". `test_missing_manifest_signals_a_skip_not_an_empty_list` fails
against that pre-fix shape -- `report["skipped"]` does not exist on a list --
which is the non-vacuity proof: this canary bites the defect it is named for.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import check_doc_manifest_freshness as cdmf
import pytest

_T1 = "2026-01-01T00:00:00+00:00"
_T2 = "2026-01-02T00:00:00+00:00"
_T3 = "2026-01-03T00:00:00+00:00"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "commit.gpgsign", "false")


def _commit(repo: Path, message: str, iso_date: str) -> str:
    """Commit the current index at a controlled committer/author date."""
    env = dict(os.environ, GIT_COMMITTER_DATE=iso_date, GIT_AUTHOR_DATE=iso_date)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)


def _write_manifest(repo: Path, generated_at: str) -> None:
    _write(repo, cdmf.MANIFEST_REL, f"schema_version: 2\ngenerated_at: '{generated_at}'\n")


def _build_stale_repo(repo: Path) -> tuple[str, str]:
    """Build the shared stale-manifest fixture: an indexed page, a manifest
    regenerated at `_T2`, then a later commit adding a new docs/ page at `_T3`.

    Returns `(self_sha, newer_sha)` so callers that need to assert on either
    sha (the golden bad-case) can, while callers that only need the fixture's
    shape (the CLI-contract tests) can ignore the return value.
    """
    _init_repo(repo)
    _write(repo, "docs/existing.md", "# Existing\n")
    _commit(repo, "docs: add existing page", _T1)

    _write_manifest(repo, _T2)
    self_sha = _commit(repo, "chore: regenerate doc manifest", _T2)

    _write(repo, "docs/new-page.md", "# New\n")
    newer_sha = _commit(repo, "docs: add new page", _T3)

    return self_sha, newer_sha


def _run_cli(tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(cdmf.__file__)), "--repo-root", str(tmp_path), *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )


# -- Skip states: could not examine reality, signalled via `skipped` ----------


def test_missing_manifest_signals_a_skip_not_an_empty_list(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    report = cdmf.run_f11(tmp_path)

    assert report["skipped"] == {"reason": "manifest-absent", "detail": cdmf.MANIFEST_REL}
    assert report["findings"] == []


def test_unparseable_generated_at_signals_a_skip_not_an_empty_list(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_manifest(tmp_path, "not-a-timestamp")
    _commit(tmp_path, "chore: add manifest", _T1)

    report = cdmf.run_f11(tmp_path)

    assert report["skipped"] == {
        "reason": "generated-at-unparseable",
        "detail": cdmf.MANIFEST_REL,
    }
    assert report["findings"] == []


def test_non_utf8_manifest_signals_a_skip_not_a_traceback(tmp_path: Path) -> None:
    """Sixth-state canary (rework rw-00594c26): a manifest whose bytes are not
    valid UTF-8 raises `UnicodeDecodeError` from `read_text`, a `ValueError`
    subclass `main`'s `except OSError` never caught pre-fix -- a raw
    traceback and exit 1 for a `--json` consumer. Bites before this fix
    (`report["skipped"]` would never be reached at all).
    """
    manifest_path = tmp_path / cdmf.MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"generated_at: '\xff\xfe\x00\x01not-utf8'\n")

    report = cdmf.run_f11(tmp_path)

    assert report["skipped"]["reason"] == "manifest-unreadable"
    assert cdmf.MANIFEST_REL in report["skipped"]["detail"]
    assert report["findings"] == []


def test_non_utf8_manifest_cli_emits_well_formed_json(tmp_path: Path) -> None:
    """Same defect, through the CLI: `--json` must never hand a consumer empty
    stdout or a traceback -- exit 0 (a skip is never a finding) with a
    well-formed envelope on stdout.
    """
    manifest_path = tmp_path / cdmf.MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"generated_at: '\xff\xfe\x00\x01not-utf8'\n")

    rc = _run_cli(tmp_path, "--json")

    assert rc.returncode == 0
    assert rc.stdout.strip() != ""
    assert '"manifest-unreadable"' in rc.stdout


def test_unreadable_mode_manifest_signals_a_skip_not_empty_stdout(tmp_path: Path) -> None:
    """Sixth-state canary (rework rw-00594c26): a `0o000` manifest raises
    `PermissionError` (an `OSError`), which pre-fix `main` caught and turned
    into `sys.exit(0)` with **no JSON printed at all** -- worse for a
    `--json` consumer than the bare `[]` this rework replaced. Bites before
    this fix (`report["skipped"]` would never be reached; `run_f11` itself
    raised).
    """
    if os.geteuid() == 0:
        pytest.skip("root ignores file modes; the unreadable-file shape cannot be built")
    manifest_path = tmp_path / cdmf.MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(f"generated_at: '{_T1}'\n", encoding="utf-8")
    manifest_path.chmod(0o000)
    try:
        report = cdmf.run_f11(tmp_path)
    finally:
        manifest_path.chmod(0o644)  # restore so tmp_path teardown can remove it

    assert report["skipped"]["reason"] == "manifest-unreadable"
    assert report["findings"] == []


def test_no_git_repository_signals_a_skip_not_an_empty_list(tmp_path: Path) -> None:
    """A readable, parseable manifest sitting outside any git repository is the
    concrete `git-unanswerable` case -- `git log` cannot answer for a directory
    that is not a repository at all, distinct from "answered, nothing found".
    """
    (tmp_path / cdmf.MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / cdmf.MANIFEST_REL).write_text(f"generated_at: '{_T1}'\n", encoding="utf-8")

    report = cdmf.run_f11(tmp_path)

    assert report["skipped"] == {"reason": "git-unanswerable", "detail": "docs/ .ai-state/"}
    assert report["findings"] == []


# -- Golden bad-case -----------------------------------------------------------


def test_stale_manifest_warns_naming_the_offending_commit(tmp_path: Path) -> None:
    """Golden bad-case: generated_at predates a later commit that ADDS a docs/ page."""
    self_sha, newer_sha = _build_stale_repo(tmp_path)

    report = cdmf.run_f11(tmp_path)

    assert report["skipped"] is None
    findings = report["findings"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["check"] == "F11"
    assert finding["severity"] == "warn"
    assert finding["entity"] == cdmf.MANIFEST_REL
    assert newer_sha[:12] in finding["message"]
    assert self_sha[:12] not in finding["message"]
    assert "build_doc_manifest.py" in finding["message"]


# -- Inverse guard 1: body-only edit to an already-indexed file -----------------


def test_body_only_edit_to_already_indexed_file_does_not_warn(tmp_path: Path) -> None:
    """A commit that only edits an already-indexed file's body (no A/D/R) must not WARN,
    even though it postdates generated_at -- --diff-filter=ADR excludes it entirely.
    """
    _init_repo(tmp_path)
    _write(tmp_path, "docs/existing.md", "# Existing\n")
    _commit(tmp_path, "docs: add existing page", _T1)

    _write_manifest(tmp_path, _T2)
    _commit(tmp_path, "chore: regenerate doc manifest", _T2)

    _write(tmp_path, "docs/existing.md", "# Existing (edited body)\n")
    _commit(tmp_path, "docs: reword existing page", _T3)

    assert cdmf.run_f11(tmp_path) == {"check": "F11", "skipped": None, "findings": []}


# -- Inverse guard 2: the manifest's own regeneration commit --------------------


def test_manifest_own_regeneration_commit_does_not_warn_even_though_it_touches_docs(
    tmp_path: Path,
) -> None:
    """The manifest's own regeneration commit is excluded by sha, not by path -- even
    when that same commit also adds a docs/ page (the builder stamps generated_at
    *before* the commit, so a naive unexcluded comparison would false-positive here).

    This is also the "no qualifying commit" clean state: once the self-commit is
    excluded, nothing remains to compare against -- a real, non-skip answer.
    """
    _init_repo(tmp_path)
    _write_manifest(tmp_path, "2025-12-31T23:59:00+00:00")  # stamped before the commit
    _write(tmp_path, "docs/rendered-page.md", "# Rendered\n")
    _commit(tmp_path, "chore: regenerate doc manifest", _T1)

    assert cdmf.run_f11(tmp_path) == {"check": "F11", "skipped": None, "findings": []}


# -- CLI contract: advisory by default -------------------------------------------


def test_exits_zero_by_default_even_with_findings(tmp_path: Path) -> None:
    _build_stale_repo(tmp_path)

    rc = _run_cli(tmp_path, "--json")

    assert rc.returncode == 0
    assert '"warn"' in rc.stdout


def test_check_flag_exits_one_on_findings(tmp_path: Path) -> None:
    _build_stale_repo(tmp_path)

    rc = _run_cli(tmp_path, "--check")

    assert rc.returncode == 1
