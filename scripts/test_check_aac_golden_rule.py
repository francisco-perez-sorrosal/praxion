"""Behavioral tests for check_aac_golden_rule.py.

The AaC golden rule: generated artifacts cannot drift from their sources.
Tests verify gate mode (exit-code enforcement), override syntax, no-op
short-circuit, graceful degradation, and audit mode for sentinel reuse.

Import strategy: mirrors sibling test files -- load via importlib.util so
the script can be exercised as a module without installing it as a package.

Test-execution strategy: real micro-repos (git init / git add / git commit)
via tmp_path -- fewer mocks to maintain than mocked subprocess, and the
tests validate actual git diff output parsing rather than mocked strings.
The helpers _make_repo / _stage_file / _run_gate / _run_audit encapsulate
the plumbing so each test body reads as a behavior specification.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_aac_golden_rule.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_aac_golden_rule", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_aac_golden_rule"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

# Public API aliases
main = _mod.main
run_gate = _mod.run_gate
run_audit = _mod.run_audit
_check_path_pair = _mod._check_path_pair
_check_fence_interior = _mod._check_fence_interior


# ---------------------------------------------------------------------------
# Micro-repo helpers
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).resolve().parent / "test_fixtures" / "aac_golden_rule"


def _make_repo(tmp_path: Path) -> Path:
    """Create a bare git repo in tmp_path/repo and return its path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        check=True,
        capture_output=True,
        cwd=str(repo),
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
        cwd=str(repo),
    )
    return repo


def _stage_file(repo: Path, relpath: str, content: str) -> None:
    """Write content to repo/relpath and `git add` it."""
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relpath], check=True, capture_output=True, cwd=str(repo))


def _commit_file(repo: Path, relpath: str, content: str, msg: str = "init") -> str:
    """Write, add, and commit a file; return the commit SHA."""
    _stage_file(repo, relpath, content)
    subprocess.run(
        ["git", "commit", "-m", msg],
        check=True,
        capture_output=True,
        cwd=str(repo),
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(repo),
    )
    return result.stdout.strip()


def _run_gate(repo: Path) -> int:
    """Invoke main() in gate mode against the micro-repo and return exit code."""
    orig_dir = os.getcwd()
    os.chdir(str(repo))
    try:
        return main(["--mode=gate", f"--repo-root={repo}"])
    finally:
        os.chdir(orig_dir)


def _run_audit(repo: Path, horizon: int = 10, emit_json: bool = False) -> int:
    """Invoke main() in audit mode against the micro-repo and return exit code."""
    orig_dir = os.getcwd()
    os.chdir(str(repo))
    try:
        argv = ["--mode=audit", f"--repo-root={repo}", f"--horizon={horizon}"]
        if emit_json:
            argv.append("--json")
        return main(argv)
    finally:
        os.chdir(orig_dir)


def _capture_audit_json(repo: Path, horizon: int = 10, capsys: Any = None) -> list:
    """Run audit with --json and return the parsed findings list."""
    _run_audit(repo, horizon=horizon, emit_json=True)
    if capsys is not None:
        captured = capsys.readouterr()
        return json.loads(captured.out)
    return []


# ---------------------------------------------------------------------------
# AC-1: path-pair detection (diagram output staged without its .c4 source)
# ---------------------------------------------------------------------------


def test_d2_staged_without_c4_fails(tmp_path: Path) -> None:
    """Staging a .d2 output without its .c4 source must exit 1."""
    repo = _make_repo(tmp_path)
    _stage_file(repo, "docs/diagrams/system/main.d2", "digraph {}\n")
    assert _run_gate(repo) == 1


def test_svg_staged_without_c4_fails(tmp_path: Path) -> None:
    """Staging an .svg output without its .c4 source must exit 1."""
    repo = _make_repo(tmp_path)
    _stage_file(repo, "docs/diagrams/system/main.svg", "<svg/>\n")
    assert _run_gate(repo) == 1


def test_d2_staged_with_c4_passes(tmp_path: Path) -> None:
    """Staging both the .d2 output and its .c4 source must exit 0."""
    repo = _make_repo(tmp_path)
    _stage_file(repo, "docs/diagrams/system/main.d2", "digraph {}\n")
    _stage_file(repo, "docs/diagrams/system.c4", "// source\n")
    assert _run_gate(repo) == 0


def test_architecture_md_hunk_inside_generated_region_without_source_fails(
    tmp_path: Path,
) -> None:
    """Staging a hunk inside an aac:generated fence without staging its source must exit 1."""
    repo = _make_repo(tmp_path)
    # Commit a baseline ARCHITECTURE.md with a generated fence
    baseline = _FIXTURES / "arch_doc_with_generated_fence.md"
    _commit_file(repo, "ARCHITECTURE.md", baseline.read_text(), "add arch doc")
    # Now stage a modification inside the generated fence region (lines 7-9)
    updated = (
        "# Architecture\n\n"
        "## System Overview\n\n"
        "Authored context here.\n\n"
        "<!-- aac:generated source=docs/diagrams/system.c4 view=L1 -->\n"
        "| Component | Role |\n"
        "|-----------|------|\n"
        "| API | Front door |\n"
        "| Worker | Background jobs |\n"  # new row inside generated fence
        "<!-- aac:end -->\n\n"
        "## Design Rationale\n\n"
        "More authored content.\n"
    )
    _stage_file(repo, "ARCHITECTURE.md", updated)
    assert _run_gate(repo) == 1


def test_architecture_md_hunk_inside_authored_region_passes(tmp_path: Path) -> None:
    """Staging a hunk inside an aac:authored fence must exit 0 (authored is not gated)."""
    repo = _make_repo(tmp_path)
    baseline = _FIXTURES / "arch_doc_with_authored_fence.md"
    _commit_file(repo, "ARCHITECTURE.md", baseline.read_text(), "add arch doc")
    updated = (
        "# Architecture\n\n"
        "## Rationale\n\n"
        "<!-- aac:authored owner=architect -->\n"
        "This section was updated with new rationale text.\n"
        "<!-- aac:end -->\n\n"
        "## Summary\n\n"
        "Authored text outside any fence.\n"
    )
    _stage_file(repo, "ARCHITECTURE.md", updated)
    assert _run_gate(repo) == 0


def test_architecture_md_hunk_outside_any_fence_passes(tmp_path: Path) -> None:
    """Staging a hunk outside any fence in ARCHITECTURE.md must exit 0."""
    repo = _make_repo(tmp_path)
    baseline = _FIXTURES / "arch_doc_no_fences.md"
    _commit_file(repo, "ARCHITECTURE.md", baseline.read_text(), "add arch doc")
    updated = (
        "# Architecture\n\n"
        "## Overview\n\n"
        "This document was updated without any fence.\n\n"
        "## Components\n\n"
        "- Component A\n"
        "- Component B\n"
        "- Component C\n"  # new line outside fence
    )
    _stage_file(repo, "ARCHITECTURE.md", updated)
    assert _run_gate(repo) == 0


# ---------------------------------------------------------------------------
# AC-1: finding message contains the relevant path
# ---------------------------------------------------------------------------


def test_d2_violation_finding_contains_path(tmp_path: Path, capsys: Any) -> None:
    """The violation message must identify the offending file path."""
    repo = _make_repo(tmp_path)
    _stage_file(repo, "docs/diagrams/myapp/context.d2", "digraph {}\n")
    _run_gate(repo)
    out = capsys.readouterr().out
    assert "docs/diagrams/myapp/context.d2" in out


# ---------------------------------------------------------------------------
# AC-2: override syntax
# ---------------------------------------------------------------------------


def test_code_override_comment_passes(tmp_path: Path) -> None:
    """A # aac-override: <reason> on the staged diff line must exit 0."""
    repo = _make_repo(tmp_path)
    content = "digraph {}\n# aac-override: refactoring d2 directly during migration\n"
    _stage_file(repo, "docs/diagrams/system/main.d2", content)
    assert _run_gate(repo) == 0


def test_html_override_comment_passes(tmp_path: Path) -> None:
    """An <!-- aac-override: reason --> on the staged diff line must exit 0."""
    repo = _make_repo(tmp_path)
    content = "<!-- aac-override: emergency fix during migration -->\n<svg/>\n"
    _stage_file(repo, "docs/diagrams/system/main.svg", content)
    assert _run_gate(repo) == 0


def test_override_with_empty_reason_fails(tmp_path: Path) -> None:
    """# aac-override: with no reason text must be treated as no override and exit 1."""
    repo = _make_repo(tmp_path)
    content = "digraph {}\n# aac-override:\n"
    _stage_file(repo, "docs/diagrams/system/main.d2", content)
    assert _run_gate(repo) == 1


def test_override_with_only_whitespace_reason_fails(tmp_path: Path) -> None:
    """# aac-override:    (only whitespace) must be treated as no override and exit 1."""
    repo = _make_repo(tmp_path)
    content = "digraph {}\n# aac-override:   \n"
    _stage_file(repo, "docs/diagrams/system/main.d2", content)
    assert _run_gate(repo) == 1


def test_override_on_previous_added_line_passes(tmp_path: Path) -> None:
    """Override on the previous added line (line adjacency rule) must exit 0."""
    repo = _make_repo(tmp_path)
    # Override on the first line, content on the second — both are new (+) lines
    content = "# aac-override: updating generated diagram during migration sprint\ndigraph {}\n"
    _stage_file(repo, "docs/diagrams/system/main.d2", content)
    assert _run_gate(repo) == 0


# ---------------------------------------------------------------------------
# AC-3: no-op when no relevant paths are staged
# ---------------------------------------------------------------------------


def test_no_staged_paths_matching_pattern_exits_zero(tmp_path: Path) -> None:
    """Staging only unrelated paths must exit 0 with no findings."""
    repo = _make_repo(tmp_path)
    _stage_file(repo, "tests/foo.py", "def test_example(): pass\n")
    assert _run_gate(repo) == 0


def test_no_staged_paths_at_all_exits_zero(tmp_path: Path) -> None:
    """When nothing is staged, gate must exit 0 silently."""
    repo = _make_repo(tmp_path)
    assert _run_gate(repo) == 0


# ---------------------------------------------------------------------------
# AC-4: graceful degradation when AAC_GOLDEN_RULE_VALIDATOR_LIKEC4=disabled
# ---------------------------------------------------------------------------


def test_likec4_disabled_env_does_not_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With LIKEC4 disabled, the gate continues and returns the same path-pair decision."""
    monkeypatch.setenv("AAC_GOLDEN_RULE_VALIDATOR_LIKEC4", "disabled")
    repo = _make_repo(tmp_path)
    # A clean case: no relevant staged paths — should still exit 0
    _stage_file(repo, "README.md", "# hi\n")
    assert _run_gate(repo) == 0


def test_likec4_disabled_gate_still_enforces_path_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With LIKEC4 disabled, path-pair violations are still caught (v1.1 does not use likec4)."""
    monkeypatch.setenv("AAC_GOLDEN_RULE_VALIDATOR_LIKEC4", "disabled")
    repo = _make_repo(tmp_path)
    _stage_file(repo, "docs/diagrams/system/main.d2", "digraph {}\n")
    # The env var disables hypothetical likec4-specific checks; path-pair is stdlib-only
    assert _run_gate(repo) == 1


# ---------------------------------------------------------------------------
# AC-5: audit mode for sentinel
# ---------------------------------------------------------------------------


def test_audit_mode_with_clean_history_no_findings(tmp_path: Path, capsys: Any) -> None:
    """Audit mode over clean commits must exit 0 and emit an empty JSON findings list."""
    repo = _make_repo(tmp_path)
    # Three commits that touch only unrelated files
    _commit_file(repo, "README.md", "# hi\n", "init")
    _commit_file(repo, "src/foo.py", "x = 1\n", "add foo")
    _commit_file(repo, "src/bar.py", "y = 2\n", "add bar")
    exit_code = _run_audit(repo, horizon=3, emit_json=True)
    assert exit_code == 0
    findings = json.loads(capsys.readouterr().out)
    assert findings == []


def test_audit_mode_with_violations_emits_findings(tmp_path: Path, capsys: Any) -> None:
    """Audit mode over a commit with a .d2 change (no .c4) must emit at least one finding."""
    repo = _make_repo(tmp_path)
    _commit_file(repo, "README.md", "# hi\n", "init")
    # Commit a .d2 without its .c4 — a golden-rule violation
    _commit_file(
        repo,
        "docs/diagrams/system/main.d2",
        "digraph {}\n",
        "update generated diagram without source",
    )
    exit_code = _run_audit(repo, horizon=3, emit_json=True)
    assert exit_code == 0  # audit always exits 0
    findings = json.loads(capsys.readouterr().out)
    assert len(findings) >= 1
    assert any("docs/diagrams/system/main.d2" in f["path"] for f in findings)


def test_audit_mode_with_overrides_no_findings(tmp_path: Path, capsys: Any) -> None:
    """Audit mode must not produce findings for commits with a valid override comment."""
    repo = _make_repo(tmp_path)
    _commit_file(repo, "README.md", "# hi\n", "init")
    # Commit a .d2 with a valid override comment
    _commit_file(
        repo,
        "docs/diagrams/system/main.d2",
        "# aac-override: one-off hotfix during incident\ndigraph {}\n",
        "update generated diagram with override",
    )
    exit_code = _run_audit(repo, horizon=3, emit_json=True)
    assert exit_code == 0
    findings = json.loads(capsys.readouterr().out)
    assert findings == []


def test_audit_mode_always_exits_zero_on_violations(tmp_path: Path) -> None:
    """Audit mode must exit 0 even when findings exist (sentinel decides escalation)."""
    repo = _make_repo(tmp_path)
    _commit_file(repo, "README.md", "# hi\n", "init")
    _commit_file(repo, "docs/diagrams/system/main.d2", "digraph {}\n", "violation")
    assert _run_audit(repo, horizon=3) == 0
