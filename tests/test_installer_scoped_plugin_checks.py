"""The Claude Code installer judges only what Praxion owns.

Two installer checks used to over-reach:

- The orphan check searched every cached plugin version for Claude Code's
  `.orphaned_at` marker. Claude Code stamps every superseded version with one,
  so any machine that has ever updated the plugin was reported as "won't load".
  Only the version the plugin registry points at decides whether it loads.
- The settings.json hook handling treated the whole `hooks` key as Praxion's.
  Earlier Praxion versions did write hooks there, but so do users and other
  tools; `--check` told users to delete the key and `--uninstall` deleted it.
  Only entries whose command runs a script from Praxion's old
  `.claude-plugin/hooks/` directory are Praxion's.

Test strategy: the ownership rules are unit-tested through `lib/settings_hooks.py`
(pure functions plus its CLI on temp files). The orphan and hooks warnings are
tested end to end through `install_claude.sh code --check`, which is read-only,
against a temp HOME with `claude`/`npm` stubbed first on PATH.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "lib" / "settings_hooks.py"
INSTALL_CLAUDE = REPO_ROOT / "install_claude.sh"

PRAXION_CMD = "python3 /Users/someone/praxion/.claude-plugin/hooks/send_event.py"
FOREIGN_CMD = "/Users/someone/.claude/hooks/other-tool/audit-log.sh"


def _load_helper():
    spec = importlib.util.spec_from_file_location("settings_hooks", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _group(*commands: str, matcher: str = "") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": c} for c in commands]}


def _foreign_only() -> dict:
    return {
        "theme": "dark",
        "hooks": {
            "PreToolUse": [_group(FOREIGN_CMD, matcher="Bash")],
            "SessionStart": [_group("/Users/someone/.claude/hooks/other-tool/session-start.sh")],
        },
    }


def _mixed() -> dict:
    return {
        "theme": "dark",
        "hooks": {
            "SessionStart": [_group(PRAXION_CMD), _group("/opt/other/start.sh")],
            "PostToolUse": [_group(FOREIGN_CMD, PRAXION_CMD, matcher="Bash")],
            "Stop": [_group(PRAXION_CMD)],
        },
    }


# --- ownership rules (pure functions) ---------------------------------------


def test_foreign_hooks_are_not_praxion_owned():
    helper = _load_helper()
    assert helper.praxion_hook_commands(_foreign_only()) == []


def test_settings_without_hooks_have_no_praxion_hooks():
    helper = _load_helper()
    assert helper.praxion_hook_commands({"theme": "dark"}) == []


def test_praxion_hooks_are_found_among_foreign_ones():
    helper = _load_helper()
    assert helper.praxion_hook_commands(_mixed()) == [PRAXION_CMD, PRAXION_CMD, PRAXION_CMD]


def test_stripping_keeps_every_foreign_hook_and_other_setting():
    helper = _load_helper()
    stripped, removed = helper.strip_praxion_hooks(_mixed())

    assert removed == 3
    assert stripped["theme"] == "dark"
    assert stripped["hooks"] == {
        "SessionStart": [_group("/opt/other/start.sh")],
        "PostToolUse": [_group(FOREIGN_CMD, matcher="Bash")],
    }


def test_stripping_only_praxion_hooks_drops_the_empty_hooks_key():
    helper = _load_helper()
    only_praxion = {"theme": "dark", "hooks": {"Stop": [_group(PRAXION_CMD)]}}

    stripped, removed = helper.strip_praxion_hooks(only_praxion)

    assert removed == 1
    assert stripped == {"theme": "dark"}


def test_stripping_foreign_only_settings_changes_nothing():
    helper = _load_helper()
    original = _foreign_only()

    stripped, removed = helper.strip_praxion_hooks(original)

    assert removed == 0
    assert stripped == _foreign_only()


# --- helper CLI on a real file ----------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER), *args], capture_output=True, text=True, check=False
    )


def test_cli_check_exits_zero_only_when_praxion_hooks_are_present(tmp_path):
    mixed = tmp_path / "mixed.json"
    mixed.write_text(json.dumps(_mixed()))
    foreign = tmp_path / "foreign.json"
    foreign.write_text(json.dumps(_foreign_only()))

    assert _cli("check", str(mixed)).returncode == 0
    assert _cli("check", str(foreign)).returncode == 1
    assert _cli("check", str(tmp_path / "missing.json")).returncode == 1


def test_cli_check_reports_an_unreadable_file_without_crashing(tmp_path):
    broken = tmp_path / "settings.json"
    broken.write_text("{not json")

    result = _cli("check", str(broken))

    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_cli_remove_rewrites_only_praxion_entries(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(_mixed(), indent=2) + "\n")

    result = _cli("remove", str(settings))

    assert result.returncode == 0
    assert "3" in result.stdout
    after = json.loads(settings.read_text())
    assert helper_free_of_praxion(after)
    assert after["hooks"]["PostToolUse"] == [_group(FOREIGN_CMD, matcher="Bash")]
    assert settings.read_text().endswith("\n")


def test_cli_remove_leaves_foreign_only_settings_byte_identical(tmp_path):
    settings = tmp_path / "settings.json"
    original = json.dumps(_foreign_only(), indent=4)  # deliberately not the helper's indent
    settings.write_text(original)

    result = _cli("remove", str(settings))

    assert result.returncode == 0
    assert settings.read_text() == original


def helper_free_of_praxion(settings: dict) -> bool:
    return _load_helper().praxion_hook_commands(settings) == []


# --- end to end through the read-only installer check -----------------------


def _stub_bin(tmp_path: Path) -> Path:
    bindir = tmp_path / "stubbin"
    bindir.mkdir()
    for name in ("claude", "npm"):
        stub = bindir / name
        stub.write_text("#!/bin/sh\nexit 1\n")
        stub.chmod(0o755)
    return bindir


def _seed_plugin(home: Path, installed: str, orphaned_versions: tuple[str, ...]) -> None:
    cache = home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion"
    for version in {installed, *orphaned_versions}:
        (cache / version / "hooks").mkdir(parents=True)
        (cache / version / "hooks" / "hooks.json").write_text("{}")
    for version in orphaned_versions:
        (cache / version / ".orphaned_at").write_text("1790568650946")
    plugins = home / ".claude" / "plugins"
    (plugins / "installed_plugins.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "praxion@bit-agora": [
                        {
                            "scope": "user",
                            "installPath": str(cache / installed),
                            "version": installed,
                        }
                    ]
                },
            }
        )
    )
    (plugins / "known_marketplaces.json").write_text(json.dumps({"bit-agora": {}}))


def _check(home: Path, tmp_path: Path) -> str:
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{_stub_bin(tmp_path)}{os.pathsep}{os.environ['PATH']}",
        "NO_COLOR": "1",
    }
    result = subprocess.run(
        ["bash", str(INSTALL_CLAUDE), "code", "--check"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    return result.stdout + result.stderr


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    return home


def test_check_ignores_markers_on_superseded_versions(home, tmp_path):
    _seed_plugin(home, installed="0.40.0", orphaned_versions=("0.38.0", "0.39.0"))

    output = _check(home, tmp_path)

    assert "orphaned_at" not in output


def test_check_flags_a_marker_on_the_installed_version(home, tmp_path):
    _seed_plugin(home, installed="0.40.0", orphaned_versions=("0.40.0",))

    output = _check(home, tmp_path)

    assert "orphaned_at" in output


def test_check_ignores_foreign_settings_hooks(home, tmp_path):
    _seed_plugin(home, installed="0.40.0", orphaned_versions=())
    (home / ".claude" / "settings.json").write_text(json.dumps(_foreign_only()))

    output = _check(home, tmp_path)

    assert "Stale" not in output


def test_check_flags_leftover_praxion_settings_hooks(home, tmp_path):
    _seed_plugin(home, installed="0.40.0", orphaned_versions=())
    (home / ".claude" / "settings.json").write_text(json.dumps(_mixed()))

    output = _check(home, tmp_path)

    assert "Stale" in output
    assert "remove the 'hooks' key" not in output
