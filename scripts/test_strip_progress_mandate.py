"""Tests for the PROGRESS.md writer-discipline guard.

`--check` passed for a whole phase while five surfaces still promised
producer-side behaviour no agent performs, because nothing outside `agents/` was
scanned. These tests pin the wider scan, its allowlist, and the fact that
something actually runs it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "strip_progress_mandate.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from strip_progress_mandate import (  # noqa: E402
    WIDER_SCAN_ALLOWLIST,
    WIDER_SCAN_GLOBS,
    check_wider_surfaces,
)


def test_repo_is_clean() -> None:
    assert check_wider_surfaces() == []


@pytest.mark.parametrize("rel", sorted(WIDER_SCAN_ALLOWLIST))
def test_allowlisted_paths_exist(rel: str) -> None:
    """A renamed or deleted allowlist entry must fail loudly, not silently
    un-guard the surface it was covering."""
    assert (REPO_ROOT / rel).is_file(), f"{rel} is allowlisted but absent"


@pytest.mark.parametrize("rel", sorted(WIDER_SCAN_ALLOWLIST))
def test_allowlisted_paths_still_mention_progress(rel: str) -> None:
    """An entry whose file no longer mentions PROGRESS.md is dead weight that
    would silently permit a future reintroduction."""
    assert "PROGRESS" in (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_reintroduced_claim_is_flagged(tmp_path: Path) -> None:
    """The canary: a producer-side claim in a scanned, non-allowlisted file
    must fail the check."""
    target = REPO_ROOT / "skills" / "roadmap-synthesis" / "SKILL.md"
    original = target.read_text(encoding="utf-8")
    backup = tmp_path / "SKILL.md"
    backup.write_text(original, encoding="utf-8")
    try:
        target.write_text(
            original + "\n- `PROGRESS.md` — phase-transition signals\n", encoding="utf-8"
        )
        assert any("roadmap-synthesis" in v for v in check_wider_surfaces())
    finally:
        target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    assert check_wider_surfaces() == []


def test_check_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_precommit_pattern_covers_every_scanned_glob() -> None:
    """Every directory the scan reads must be able to trigger the hook, or a
    drifting file lands without the guard ever running."""
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook = re.search(r"- id: progress-mandate-drift.*?files: '([^']+)'", config, re.DOTALL)
    assert hook, "progress-mandate-drift hook is not registered in .pre-commit-config.yaml"
    pattern = re.compile(hook.group(1))
    for glob in WIDER_SCAN_GLOBS:
        sample = next(iter(sorted(REPO_ROOT.glob(glob))), None)
        assert sample is not None, f"glob {glob} matches nothing"
        rel = sample.relative_to(REPO_ROOT).as_posix()
        assert pattern.match(rel), f"{rel} (from {glob}) is not covered by the hook pattern"
