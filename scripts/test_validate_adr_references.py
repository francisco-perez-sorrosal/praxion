"""Canary tests for scripts/validate_adr_references.py.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. These tests feed the validator an ADR whose
affected_files: entry points to a non-existent file and assert it is flagged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "validate_adr_references.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "validate_adr_references", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_adr_references"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
parse_affected_files = _mod.parse_affected_files


def _write_adr(decisions_dir: Path, name: str, affected_files: list[str]) -> Path:
    """Write a minimal ADR file with an affected_files: block-list frontmatter."""
    block_entries = "".join(f"  - {p}\n" for p in affected_files)
    text = (
        "---\n"
        f"id: dec-draft-test\n"
        f"title: Test ADR\n"
        f"status: proposed\n"
        f"date: 2026-01-01\n"
        f"affected_files:\n{block_entries}"
        "---\n\n## Context\n\nTest.\n"
    )
    p = decisions_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _write_adr_inline(
    decisions_dir: Path, name: str, affected_files: list[str]
) -> Path:
    """Write a minimal ADR with affected_files as inline list frontmatter."""
    inline = "[" + ", ".join(f'"{p}"' for p in affected_files) + "]"
    text = (
        "---\n"
        f"id: dec-draft-test\n"
        f"title: Test ADR\n"
        f"status: proposed\n"
        f"date: 2026-01-01\n"
        f"affected_files: {inline}\n"
        "---\n\n## Context\n\nTest.\n"
    )
    p = decisions_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Unit tests for parse_affected_files
# ---------------------------------------------------------------------------


def test_parses_block_list_affected_files(tmp_path: Path) -> None:
    """parse_affected_files extracts entries from a YAML block-list."""
    adr = _write_adr(tmp_path, "001-test.md", ["scripts/foo.py", "rules/bar.md"])
    paths = parse_affected_files(adr.read_text())
    assert paths == ["scripts/foo.py", "rules/bar.md"]


def test_parses_inline_list_affected_files(tmp_path: Path) -> None:
    """parse_affected_files extracts entries from an inline JSON-array."""
    adr = _write_adr_inline(tmp_path, "002-test.md", ["scripts/baz.py"])
    paths = parse_affected_files(adr.read_text())
    assert paths == ["scripts/baz.py"]


def test_returns_empty_for_adr_without_affected_files(tmp_path: Path) -> None:
    """An ADR with no affected_files field returns an empty list."""
    text = "---\nid: dec-draft-x\ntitle: No files\nstatus: proposed\ndate: 2026-01-01\n---\n"
    assert parse_affected_files(text) == []


# ---------------------------------------------------------------------------
# Canary: dangling affected_files reference triggers non-zero exit
# ---------------------------------------------------------------------------


def test_flags_dangling_affected_files_reference(tmp_path: Path) -> None:
    """Canary: an ADR citing a file that does not exist on disk causes exit 1.

    The gate exists to catch ADRs that reference files deleted or moved since
    the ADR was written. The validator must return non-zero when any reference
    cannot be resolved.
    """
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "001-missing.md", ["scripts/nonexistent_file_xyz.py"])

    # Patch REPO_ROOT and ADR_DIR to point at our tmp fixture, then call main().
    # We monkeypatch module-level globals directly on the already-loaded module.
    orig_repo_root = _mod.REPO_ROOT
    orig_adr_dir = _mod.ADR_DIR
    try:
        _mod.REPO_ROOT = tmp_path
        _mod.ADR_DIR = decisions_dir
        rc = _mod.main()
    finally:
        _mod.REPO_ROOT = orig_repo_root
        _mod.ADR_DIR = orig_adr_dir

    assert rc == 1, (
        f"validate_adr_references must return 1 when affected_files has a dangling "
        f"reference; got {rc}"
    )


def test_accepts_adr_with_all_files_present(tmp_path: Path) -> None:
    """Happy path: an ADR whose affected_files all exist on disk exits 0."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    # Create the referenced file so it resolves
    existing = tmp_path / "scripts" / "real_file.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("# exists\n", encoding="utf-8")

    _write_adr(decisions_dir, "002-present.md", ["scripts/real_file.py"])

    orig_repo_root = _mod.REPO_ROOT
    orig_adr_dir = _mod.ADR_DIR
    try:
        _mod.REPO_ROOT = tmp_path
        _mod.ADR_DIR = decisions_dir
        rc = _mod.main()
    finally:
        _mod.REPO_ROOT = orig_repo_root
        _mod.ADR_DIR = orig_adr_dir

    assert rc == 0, f"validator must return 0 when all references resolve; got {rc}"


def test_accepts_adr_with_no_affected_files(tmp_path: Path) -> None:
    """Happy path: an ADR with no affected_files field exits 0."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    text = "---\nid: dec-draft-y\ntitle: No files\nstatus: proposed\ndate: 2026-01-01\n---\n"
    (decisions_dir / "003-none.md").parent.mkdir(parents=True, exist_ok=True)
    (decisions_dir / "003-none.md").write_text(text, encoding="utf-8")

    orig_repo_root = _mod.REPO_ROOT
    orig_adr_dir = _mod.ADR_DIR
    try:
        _mod.REPO_ROOT = tmp_path
        _mod.ADR_DIR = decisions_dir
        rc = _mod.main()
    finally:
        _mod.REPO_ROOT = orig_repo_root
        _mod.ADR_DIR = orig_adr_dir

    assert rc == 0, (
        f"validator must return 0 when there are no references to check; got {rc}"
    )
