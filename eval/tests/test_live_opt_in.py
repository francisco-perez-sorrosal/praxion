"""The live runner stays operator-invoked: no automation surface reaches it.

`praxion-evals-live` spends API money on every run, so it must never start
from a hook, a CI workflow, an agent prompt, a repo script, or the plain
`/eval-praxion` harness. This scans those surfaces for any reference to the
package or its console entry — a structural promise made executable, so a
future edit that wires the runner into automation fails here instead of
spending money unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVE_REFERENCES = ("praxion_evals.live", "praxion-evals-live")
_AUTOMATION_SURFACES = (
    "hooks",
    ".github/workflows",
    "agents",
    "scripts",
    "eval/src/praxion_evals/harness",
)
_SCANNED_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".json", ".md", ".toml"}


def _files_under(surface: str) -> list[Path]:
    root = _REPO_ROOT / surface
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in _SCANNED_SUFFIXES and "__pycache__" not in path.parts
    )


@pytest.mark.parametrize("surface", _AUTOMATION_SURFACES)
def test_automation_surface_never_references_the_live_runner(surface: str) -> None:
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in _files_under(surface)
        if any(
            ref in path.read_text(encoding="utf-8", errors="replace") for ref in _LIVE_REFERENCES
        )
    ]

    assert offenders == [], (
        f"{surface} references the paid live runner; it must stay operator-invoked: {offenders}"
    )


@pytest.mark.parametrize("surface", _AUTOMATION_SURFACES)
def test_each_automation_surface_is_actually_scanned(surface: str) -> None:
    assert _files_under(surface), f"{surface} yielded no files — the guard would pass vacuously"
