"""The complete-skills' registry fallback, run as the skills' own `bash` block runs it.

Outside a plugin session Claude Code substitutes nothing, so the block's plugin-root token
stays inert text and the block falls back to the plugin registry. Each scenario runs the
install skill's block under `bash` with a scratch `HOME` holding a registry of one shape, and
a stand-in `install.sh` in each install path that names the root it was run from.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SKILL = REPO_ROOT / "skills" / "praxion-complete-install" / "SKILL.md"
NOT_FOUND = "Praxion plugin not found"
_BASH_FENCE_RE = re.compile(r"^```bash[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def _block() -> str:
    (block,) = _BASH_FENCE_RE.findall(INSTALL_SKILL.read_text(encoding="utf-8"))
    return block


def _install_path(home: Path, version: str) -> Path:
    root = home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / version
    root.mkdir(parents=True)
    check = root / "install.sh"
    check.write_text('#!/bin/sh\necho "checked from $(dirname "$0") $*"\n', encoding="utf-8")
    check.chmod(check.stat().st_mode | stat.S_IXUSR)
    return root


def _registry(home: Path, text: str) -> None:
    path = home / ".claude" / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(home: Path) -> str:
    environ = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    environ["HOME"] = str(home)
    done = subprocess.run(
        ["bash", "-c", _block()], capture_output=True, text=True, env=environ, timeout=60
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def test_an_entry_without_a_scope_still_resolves(home: Path) -> None:
    root = _install_path(home, "9.9.9")
    _registry(home, json.dumps({"plugins": {"praxion@bit-agora": [{"installPath": str(root)}]}}))

    assert _run(home) == f"Praxion plugin root: {root}\nchecked from {root} code --check\n"


def test_an_entry_without_an_install_path_is_passed_over(home: Path) -> None:
    root = _install_path(home, "9.9.9")
    entries = [{"scope": "user"}, {"scope": "project", "installPath": str(root)}]
    _registry(home, json.dumps({"plugins": {"praxion@bit-agora": entries}}))

    assert _run(home) == f"Praxion plugin root: {root}\nchecked from {root} code --check\n"


def test_the_user_scope_entry_wins_over_one_listed_before_it(home: Path) -> None:
    older, newer = _install_path(home, "9.9.8"), _install_path(home, "9.9.9")
    entries = [
        {"scope": "project", "installPath": str(older)},
        {"scope": "user", "installPath": str(newer)},
    ]
    _registry(home, json.dumps({"plugins": {"praxion@bit-agora": entries}}))

    assert _run(home) == f"Praxion plugin root: {newer}\nchecked from {newer} code --check\n"


def test_a_registry_that_is_not_json_finds_no_plugin(home: Path) -> None:
    _install_path(home, "9.9.9")
    _registry(home, "{ not json")

    assert NOT_FOUND in _run(home)


def test_no_registry_finds_no_plugin_even_with_cached_versions(home: Path) -> None:
    _install_path(home, "9.9.9")

    assert NOT_FOUND in _run(home)
