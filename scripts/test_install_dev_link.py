"""Tests for install_claude.sh's --dev-link / --dev-link=off mode.

Resolves td-036: contributors editing hooks/, scripts/, or commands/ locally
could not test against plugin-cache-resolved code paths without manually
`cp`-ing files into the installed plugin cache between iterations.
`--dev-link` replaces the cache copies of the three cache-resolved runtime
surfaces with directory-level symlinks back to the working tree; `--dev-link=off`
restores the pre-link cache contents from a `.pre-dev-link` backup.

These tests drive the real bash script via subprocess against a synthetic
HOME (registry + cache dir) and a synthetic source tree — hermetic, no real
~/.claude touched. Two env-var overrides make this possible:
  - HOME                        redirects ~/.claude/plugins/... resolution
  - PRAXION_DEV_LINK_SOURCE_DIR redirects the "working tree" source dirs
    (production always uses the script's own SCRIPT_DIR)

Key cases:
  - --dev-link symlinks hooks/, scripts/, commands/ and backs up originals
  - a symlinked hook still executes through its ${CLAUDE_PLUGIN_ROOT} path
    (gate-liveness for the directory-symlink mechanism itself)
  - a second --dev-link is idempotent (no re-backup, no error)
  - --dev-link=off restores the pre-link cache contents
  - refuses cleanly (non-zero + message) with no pinned install, an unrelated
    registry, a resolved path escaping the plugin's own cache tree, both
    flags combined, or desktop mode
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "install_claude.sh"


def _run(home: Path, source_dir: Path | None, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    if source_dir is not None:
        env["PRAXION_DEV_LINK_SOURCE_DIR"] = str(source_dir)
    else:
        env.pop("PRAXION_DEV_LINK_SOURCE_DIR", None)
    return subprocess.run(
        ["bash", str(_SCRIPT), "code", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _cache_dir(home: Path, version: str = "0.12.0") -> Path:
    return home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / version


def _write_registry(home: Path, install_path: Path, version: str = "0.12.0") -> None:
    reg_dir = home / ".claude" / "plugins"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / "installed_plugins.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "praxion@bit-agora": [
                        {
                            "scope": "user",
                            "installPath": str(install_path),
                            "version": version,
                        }
                    ]
                }
            }
        )
    )


@pytest.fixture
def env(tmp_path: Path) -> dict:
    """A synthetic HOME with a pinned praxion install + a synthetic source tree."""
    home = tmp_path / "home"
    cache = _cache_dir(home)
    for surface in ("hooks", "scripts", "commands"):
        (cache / surface).mkdir(parents=True)
    (cache / "hooks" / "marker.txt").write_text("fetched-copy\n")
    _write_registry(home, cache)

    source = tmp_path / "src"
    (source / "hooks").mkdir(parents=True)
    (source / "scripts").mkdir(parents=True)
    (source / "commands").mkdir(parents=True)
    hook = source / "hooks" / "my_hook.sh"
    hook.write_text(
        '#!/usr/bin/env bash\necho "hello from working tree via ${CLAUDE_PLUGIN_ROOT:-unset}"\n'
    )
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    (source / "scripts" / "marker.txt").write_text("source-copy\n")
    (source / "commands" / "marker.txt").write_text("source-copy\n")

    return {"home": home, "cache": cache, "source": source}


@pytest.mark.parametrize("surface", ["hooks", "scripts", "commands"])
def test_dev_link_symlinks_surface_and_backs_up_original(env, surface):
    r = _run(env["home"], env["source"], "--dev-link")
    assert r.returncode == 0, r.stderr

    target = env["cache"] / surface
    assert target.is_symlink()
    assert os.readlink(target) == str(env["source"] / surface)
    assert (env["cache"] / f"{surface}.pre-dev-link").is_dir()


def test_dev_link_preserves_original_content_in_backup(env):
    r = _run(env["home"], env["source"], "--dev-link")
    assert r.returncode == 0, r.stderr
    assert (env["cache"] / "hooks.pre-dev-link" / "marker.txt").read_text() == "fetched-copy\n"


def test_symlinked_hook_still_executes_through_plugin_root_path(env):
    """Gate-liveness: a directory-level symlink must not break Claude Code's
    ${CLAUDE_PLUGIN_ROOT}/<surface>/<file> resolution."""
    r = _run(env["home"], env["source"], "--dev-link")
    assert r.returncode == 0, r.stderr

    plugin_root = env["cache"]
    hook_path = plugin_root / "hooks" / "my_hook.sh"
    result = subprocess.run(
        [str(hook_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(plugin_root)},
    )
    assert result.returncode == 0, result.stderr
    assert f"hello from working tree via {plugin_root}" in result.stdout


def test_dev_link_is_idempotent(env):
    first = _run(env["home"], env["source"], "--dev-link")
    assert first.returncode == 0, first.stderr
    second = _run(env["home"], env["source"], "--dev-link")
    assert second.returncode == 0, second.stderr
    assert "already dev-linked" in second.stdout
    # still a symlink to the same source, no duplicate backup churn
    assert os.readlink(env["cache"] / "hooks") == str(env["source"] / "hooks")


@pytest.mark.parametrize("surface", ["hooks", "scripts", "commands"])
def test_dev_link_off_restores_surface_from_backup(env, surface):
    _run(env["home"], env["source"], "--dev-link")
    r = _run(env["home"], env["source"], "--dev-link=off")
    assert r.returncode == 0, r.stderr

    target = env["cache"] / surface
    assert target.is_dir()
    assert not target.is_symlink()
    assert not (env["cache"] / f"{surface}.pre-dev-link").exists()


def test_dev_link_off_preserves_original_fetched_content(env):
    _run(env["home"], env["source"], "--dev-link")
    _run(env["home"], env["source"], "--dev-link=off")
    assert (env["cache"] / "hooks" / "marker.txt").read_text() == "fetched-copy\n"


def test_dev_link_off_when_not_linked_is_noop(env):
    r = _run(env["home"], env["source"], "--dev-link=off")
    assert r.returncode == 0, r.stderr
    assert "not dev-linked, nothing to do" in r.stdout
    assert (env["cache"] / "hooks").is_dir()
    assert not (env["cache"] / "hooks").is_symlink()


def test_missing_source_surface_warns_and_skips(env, tmp_path):
    sparse_source = tmp_path / "sparse-src"
    (sparse_source / "hooks").mkdir(parents=True)
    # scripts/ and commands/ intentionally absent

    r = _run(env["home"], sparse_source, "--dev-link")
    assert r.returncode == 0, r.stderr
    assert (env["cache"] / "hooks").is_symlink()
    assert (env["cache"] / "scripts").is_dir()
    assert not (env["cache"] / "scripts").is_symlink()
    assert "scripts: no such directory in working tree" in r.stdout


def test_refuses_when_no_registry(tmp_path):
    home = tmp_path / "home-empty"
    home.mkdir()
    r = _run(home, tmp_path / "src", "--dev-link")
    assert r.returncode != 0
    assert "No plugin registry" in r.stderr


def test_refuses_when_plugin_not_installed(tmp_path):
    home = tmp_path / "home-no-entry"
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"plugins": {}})
    )
    r = _run(home, tmp_path / "src", "--dev-link")
    assert r.returncode != 0
    assert "is not installed" in r.stderr


def test_refuses_when_resolved_path_escapes_plugin_cache(tmp_path):
    home = tmp_path / "home-evil"
    evil_target = tmp_path / "not-the-plugin-cache"
    evil_target.mkdir(parents=True)
    _write_registry(home, evil_target)
    r = _run(home, tmp_path / "src", "--dev-link")
    assert r.returncode != 0
    assert "refusing to touch it" in r.stderr


def test_refuses_when_both_flags_combined(env):
    r = _run(env["home"], env["source"], "--dev-link", "--dev-link=off")
    assert r.returncode != 0
    assert "mutually exclusive" in r.stderr


def test_refuses_desktop_mode(env):
    result = subprocess.run(
        ["bash", str(_SCRIPT), "desktop", "--dev-link"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(env["home"])},
    )
    assert result.returncode != 0
    assert "only supported with 'code' mode" in result.stderr
