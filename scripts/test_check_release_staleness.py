"""Tests for check_release_staleness.py -- release-staleness diagnostic.

Behavioral tests:

1. Reports in-sync when HEAD registers the same artifacts as the last release.
2. CANARY: flags agents/skills/commands added after the release tag, and
   ``--check`` exits non-zero on that known-bad input (gate-liveness proof it
   bites -- see rules/swe/gate-liveness.md).
3. Excludes commands/README.md from the command set.
4. Exits 0 when no release tag exists (advisory, never aborts).
5. Auto-detects the newest v* tag as the baseline.

Uses a real temporary git repo (functions under test take an explicit
repo_root), exercising the actual git-tree extraction rather than mocks.
Import strategy mirrors scripts/test_check_squash_safety.py.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_release_staleness.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_release_staleness", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


crs = _load_module()


# -- Temp-repo helpers --------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def _write_plugin(repo: Path, agents: list[str]) -> None:
    manifest = repo / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"name": "praxion", "agents": [f"./agents/{a}.md" for a in agents]})
    )


def _write_skill(repo: Path, name: str) -> None:
    path = repo / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n")


def _write_command(repo: Path, name: str) -> None:
    path = repo / "commands" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


# -- Tests --------------------------------------------------------------------


def test_in_sync_when_head_matches_release(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _write_skill(repo, "refactoring")
    _write_command(repo, "sentinel")
    _commit(repo, "feat: baseline")
    _git(repo, "tag", "v0.1.0")

    result = crs.compute_staleness(repo, "v0.1.0", "HEAD")

    assert not result.is_stale
    assert result.total == 0


def test_flags_artifacts_added_after_release(tmp_path: Path) -> None:
    # CANARY: known-bad input -- artifacts exist at HEAD but not at the tag.
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _write_skill(repo, "refactoring")
    _commit(repo, "feat: baseline")
    _git(repo, "tag", "v0.1.0")

    _write_plugin(repo, ["researcher", "interface-designer"])
    _write_skill(repo, "web-ui-design")
    _write_command(repo, "review-interface")
    _commit(repo, "feat: add interface-designer")

    result = crs.compute_staleness(repo, "v0.1.0", "HEAD")

    assert result.is_stale
    assert result.new_agents == ["interface-designer"]
    assert result.new_skills == ["web-ui-design"]
    assert result.new_commands == ["review-interface"]


def test_check_flag_exits_nonzero_when_stale(tmp_path: Path) -> None:
    # CANARY (CLI surface): --check must abort on the known-bad input.
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _commit(repo, "feat: baseline")
    _git(repo, "tag", "v0.1.0")
    _write_plugin(repo, ["researcher", "interface-designer"])
    _commit(repo, "feat: add agent")

    with pytest.raises(SystemExit) as exc:
        crs.main(["--repo-root", str(repo), "--base-ref", "v0.1.0", "--check"])

    assert exc.value.code == 1


def test_check_flag_exits_zero_when_in_sync(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _commit(repo, "feat: baseline")
    _git(repo, "tag", "v0.1.0")

    with pytest.raises(SystemExit) as exc:
        crs.main(["--repo-root", str(repo), "--base-ref", "v0.1.0", "--check"])

    assert exc.value.code == 0


def test_excludes_command_readme(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _commit(repo, "feat: baseline")
    _git(repo, "tag", "v0.1.0")
    _write_command(repo, "README")
    _commit(repo, "docs: add commands readme")

    result = crs.compute_staleness(repo, "v0.1.0", "HEAD")

    assert result.new_commands == []
    assert not result.is_stale


def test_no_release_tag_exits_zero(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _commit(repo, "feat: baseline")  # no tag created

    with pytest.raises(SystemExit) as exc:
        crs.main(["--repo-root", str(repo), "--check"])

    assert exc.value.code == 0


def test_latest_release_tag_picks_newest_v_tag(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_plugin(repo, ["researcher"])
    _commit(repo, "feat: baseline")
    _git(repo, "tag", "v0.1.0")
    _write_plugin(repo, ["researcher", "promethean"])
    _commit(repo, "feat: more")
    _git(repo, "tag", "v0.2.0")

    assert crs.latest_release_tag(repo) == "v0.2.0"
