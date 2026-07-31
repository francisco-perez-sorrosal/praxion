"""Tests for scripts/check_id_citation_discipline.py.

Regression coverage for the extensionless-bash gap discovered during the
Phase 2 dispatch-reworks pipeline verifier pass: bash scripts without a `.sh`
extension (e.g., `scripts/dispatch-reworks`) were previously skipped by the
detector because file selection was extension-only. The shebang-detection
extension closes that gap.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts" / "check_id_citation_discipline.py"


def _make_exec_script(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def test_explicit_extensionless_bash_with_violation_is_detected(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "my-tool"
    _make_exec_script(
        script, "#!/usr/bin/env bash\n# Step 1 smoke-check should be caught\necho hi\n"
    )

    result = _run(
        ["--files", str(script), "--repo-root", str(tmp_path)],
        cwd=tmp_path,
    )

    assert (
        result.returncode == 1
    ), f"expected exit 1; got {result.returncode}\n{result.stdout}\n{result.stderr}"
    assert "step-ref" in result.stdout
    assert "Step 1" in result.stdout


def test_explicit_extensionless_bash_clean_returns_zero(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "clean-tool"
    _make_exec_script(script, "#!/usr/bin/env bash\necho hello world\n")

    result = _run(
        ["--files", str(script), "--repo-root", str(tmp_path)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, f"expected exit 0; got {result.returncode}\n{result.stdout}"


def test_full_scan_finds_extensionless_executable_bash(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "another-tool"
    _make_exec_script(script, "#!/bin/bash\n# REQ-FOO-01 should be caught\n")

    result = _run(["--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 1
    assert "REQ-FOO-01" in result.stdout or "req-id" in result.stdout


def test_full_scan_skips_extensionless_non_bash(tmp_path: Path) -> None:
    """Extensionless text files without a bash shebang are not scanned."""
    readme = tmp_path / "README"
    readme.write_text("# Step 1 — historical chapter heading, not a citation\n")
    readme.chmod(readme.stat().st_mode | stat.S_IXUSR)

    result = _run(["--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0


def test_full_scan_skips_extensionless_bash_without_exec_bit(tmp_path: Path) -> None:
    """In full-repo mode the executable-bit heuristic skips non-exec bash files."""
    not_exec = tmp_path / "scripts" / "not-executable"
    not_exec.parent.mkdir(parents=True)
    not_exec.write_text("#!/usr/bin/env bash\n# Step 9 — should NOT trigger in full scan\n")
    # Intentionally do not chmod +x.

    result = _run(["--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0


def test_explicit_pass_bypasses_exec_bit_heuristic(tmp_path: Path) -> None:
    """Explicit --files passes scan extensionless bash regardless of exec bit."""
    script = tmp_path / "scripts" / "sourceable-lib"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\n# Step 4 leak in a sourceable bash lib\n")
    # No exec bit on purpose.

    result = _run(
        ["--files", str(script), "--repo-root", str(tmp_path)],
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert "Step 4" in result.stdout


def test_shebang_other_shells_recognized(tmp_path: Path) -> None:
    for shell_path in ("/bin/sh", "/usr/bin/env zsh", "/bin/dash", "/usr/bin/env ksh"):
        script = tmp_path / f"scripts/tool-{shell_path.replace('/', '_').replace(' ', '_')}"
        _make_exec_script(script, f"#!{shell_path}\n# REQ-X-01\n")
        result = _run(
            ["--files", str(script), "--repo-root", str(tmp_path)],
            cwd=tmp_path,
        )
        assert result.returncode == 1, f"shebang {shell_path!r} not recognized"


# --- draft-adr-id pattern (td-101) --------------------------------------
#
# These canaries are written against a `draft-adr-id` PATTERNS entry that
# does not exist yet — RED by design. They pin the behavior a future
# `PATTERNS` tuple entry must satisfy (REQ-A12/A13/A14); today the checker
# has no pattern matching `dec-draft-<hash>` at all, so every test below
# currently fails at its `returncode == 1` assertion, not on an
# ImportError/collection error.

EXEMPT_DRAFT_ID_PREFIXES = (
    "rules",
    "skills",
    "agents",
    "commands",
    "docs",
    ".ai-state",
    ".ai-work",
)


def test_detects_draft_adr_id_citation(tmp_path: Path) -> None:
    """A bare `dec-draft-<hash>` citation in code is flagged under the
    `draft-adr-id` pattern name (REQ-A12)."""
    module = tmp_path / "src" / "module.py"
    module.parent.mkdir(parents=True)
    module.write_text('DRAFT_REF = "dec-draft-abcd1234"  # narrates a historical fix\n')

    result = _run(["--files", str(module), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert (
        result.returncode == 1
    ), f"expected a draft-adr-id violation; got exit {result.returncode}\n{result.stdout}"
    assert "[draft-adr-id]" in result.stdout
    assert "dec-draft-abcd1234" in result.stdout


def test_ignore_marker_suppresses_draft_adr_id_flag(tmp_path: Path) -> None:
    """The per-line `id-citation-discipline:ignore` marker suppresses the
    flag on its own line (REQ-A13) without suppressing an unmarked sibling
    citation in the same file — a dual assertion so this canary cannot pass
    vacuously (a checker that dropped the pattern entirely, or one that
    suppressed the whole file instead of just the marked line, both fail
    this test)."""
    module = tmp_path / "src" / "module.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        'UNMARKED = "dec-draft-abcd1234"\n'
        'MARKED = "dec-draft-deadbeef"  # id-citation-discipline:ignore\n'
    )

    result = _run(["--files", str(module), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 1, (
        f"expected the unmarked citation to be flagged; got exit {result.returncode}\n"
        f"{result.stdout}"
    )
    assert (
        result.stdout.count("[draft-adr-id]") == 1
    ), f"expected exactly one finding (the unmarked line only):\n{result.stdout}"
    assert "dec-draft-abcd1234" in result.stdout
    assert "dec-draft-deadbeef" not in result.stdout


@pytest.mark.parametrize("prefix", EXEMPT_DRAFT_ID_PREFIXES)
def test_dec_draft_literal_under_exempt_path_is_not_flagged(tmp_path: Path, prefix: str) -> None:
    """A `dec-draft-<hash>` literal under a teaching-material or
    pipeline-state path (`rules/`, `skills/`, `agents/`, `commands/`,
    `docs/`, `.ai-state/`, `.ai-work/`) is out of the gate's scope, while an
    identical citation outside any exempt path is still flagged — the
    control file proves the exemption is path-scoped, not a blanket
    suppression that would pass this test vacuously today."""
    exempt_file = tmp_path / prefix / "notes.py"
    exempt_file.parent.mkdir(parents=True)
    exempt_file.write_text('EXAMPLE = "dec-draft-cafebabe"\n')

    control_file = tmp_path / "src" / "module.py"
    control_file.parent.mkdir(parents=True)
    control_file.write_text('EXAMPLE = "dec-draft-cafebabe"\n')

    result = _run(["--repo-root", str(tmp_path)], cwd=tmp_path)

    assert (
        "[draft-adr-id]" in result.stdout
    ), f"expected the control (non-exempt) file's citation to be flagged\n{result.stdout}"
    assert str(control_file.relative_to(tmp_path)) in result.stdout
    assert str(exempt_file.relative_to(tmp_path)) not in result.stdout


def test_finalized_dec_nnn_citation_is_not_flagged(tmp_path: Path) -> None:
    """A finalized `dec-NNN` citation — explicitly permitted by
    `rules/swe/id-citation-discipline.md`'s lifecycle table — is never
    flagged, even in the same file as a still-draft citation that is
    flagged, proving the pattern targets the draft shape specifically and
    not any `dec-` prefix."""
    module = tmp_path / "src" / "module.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        'DRAFT_REF = "dec-draft-facade00"  # not yet finalized\n# Rationale documented in dec-308\n'
    )

    result = _run(["--files", str(module), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert (
        result.returncode == 1
    ), f"expected the draft citation to be flagged; got exit {result.returncode}\n{result.stdout}"
    assert result.stdout.count("[draft-adr-id]") == 1
    assert "dec-draft-facade00" in result.stdout
    assert "dec-308" not in result.stdout
