"""`install.sh code --check` judges which version `~/.claude/CLAUDE.md` follows, not only that it is linked.

The check runs from a plugin root shaped like a cache version directory (its surfaces are links
to this checkout's, so the real installer and hook run), against a scratch home whose
instructions link names an earlier cached version's render. `claude` and `npm` are stubbed first
on PATH. Nothing here reads a real home or plugin cache.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE = Path(".claude") / "plugins" / "cache" / "bit-agora" / "praxion"
_SURFACES = ("install_claude.sh", "lib", "hooks", "scripts", "rules", "claude")
_BEHIND_WORDS = "CLAUDE.md is behind this version"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def installed_root(home: Path) -> Path:
    root = home / _CACHE / "1.0.0"
    root.mkdir(parents=True)
    for surface in _SURFACES:
        (root / surface).symlink_to(REPO_ROOT / surface)
    return root


def _link_instructions_to(home: Path, render: Path) -> None:
    render.parent.mkdir(parents=True, exist_ok=True)
    render.write_text("rendered\n", encoding="utf-8")
    (home / ".claude" / "CLAUDE.md").symlink_to(render)


def _check(home: Path, root: Path, tmp_path: Path) -> str:
    stubs = tmp_path / "stubbin"
    stubs.mkdir()
    for name in ("claude", "npm"):
        (stubs / name).write_text("#!/bin/sh\nexit 1\n")
        (stubs / name).chmod(0o755)
    environ = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "NO_COLOR": "1",
    }
    done = subprocess.run(
        ["bash", str(root / "install_claude.sh"), "code", "--check"],
        capture_output=True,
        text=True,
        env=environ,
        timeout=120,
    )
    return done.stdout + done.stderr


def test_a_link_into_an_earlier_versions_render_is_reported_behind(
    tmp_path: Path, home: Path, installed_root: Path
) -> None:
    _link_instructions_to(home, home / _CACHE / "0.9.0" / "claude" / "config" / "CLAUDE.md")

    assert _BEHIND_WORDS in _check(home, installed_root, tmp_path)


def test_a_link_outside_the_plugin_cache_is_not_reported_behind(
    tmp_path: Path, home: Path, installed_root: Path
) -> None:
    _link_instructions_to(home, tmp_path / "clone" / "claude" / "config" / "CLAUDE.md")

    assert _BEHIND_WORDS not in _check(home, installed_root, tmp_path)
