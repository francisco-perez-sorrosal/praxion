"""The three largest files of this change, and every file split from them, stay under 800 lines.

The run loop and the common checks of the adherence eval, and the kernel and adoption
gate, are split by cohesion before this change grows them. Files split from the two eval
modules stay in the adherence package; files split from the gate are the gate's own
`scripts/` modules (named for the kernel or the gate), test modules aside.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CEILING = 800
NAMED = (
    "eval/src/praxion_evals/adherence/session_loop.py",
    "eval/src/praxion_evals/adherence/checks_common.py",
    "scripts/check_kernel_manifest.py",
)
ADHERENCE_PACKAGE = REPO_ROOT / "eval" / "src" / "praxion_evals" / "adherence"


def lines_of(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def gate_modules() -> list[Path]:
    scripts = REPO_ROOT / "scripts"
    return sorted(
        p
        for p in scripts.rglob("*.py")
        if ("kernel" in p.name or "manifest" in p.name) and not p.name.startswith("test_")
    )


@pytest.mark.parametrize("relpath", NAMED)
def test_each_named_file_is_under_the_ceiling(relpath: str) -> None:
    assert lines_of(REPO_ROOT / relpath) < CEILING


@pytest.mark.parametrize("path", sorted(ADHERENCE_PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_every_module_of_the_adherence_package_is_under_the_ceiling(path: Path) -> None:
    assert lines_of(path) < CEILING


@pytest.mark.parametrize("path", gate_modules(), ids=lambda p: p.name)
def test_every_module_of_the_kernel_gate_is_under_the_ceiling(path: Path) -> None:
    assert lines_of(path) < CEILING
