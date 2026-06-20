"""Tests for upgrade_project_pins.sh -- post-upgrade drift reconciliation.

The script re-points a managed project's four version-pinned Praxion surfaces
(finalize-hook symlinks, the observations merge driver, retired merge drivers,
and the onboard-manifest version stamp) to the live plugin install after a
plugin upgrade. These tests drive the real bash script via subprocess against a
synthetic managed project, asserting on observable end state rather than
internals.

Key cases:
  - stale /i-am/<old>/ pins are re-pointed to the live path
  - --check reports drift (exit 1) and mutates nothing
  - a second apply is idempotent (no further changes, --check exits 0)
  - a retired merge driver is unset and dropped from .gitattributes + manifest
  - a dev/self-host symlink (resolves to a real file outside the cache) is left
    untouched -- the self-host safety guard
  - a non-Praxion merge driver is never overwritten
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "upgrade_project_pins.sh"


def _run(repo: Path, plugin: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_SCRIPT), "--repo-root", str(repo), "--plugin-path", str(plugin), *args],
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def project(tmp_path: Path) -> dict:
    """A managed project with stale 0.8.0 pins and a live 0.9.0 install."""
    repo = tmp_path / "proj"
    (repo / ".ai-state").mkdir(parents=True)
    (repo / ".git" / "hooks").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)

    live = repo / "cache" / "i-am" / "0.9.0"
    stale = repo / "cache" / "i-am" / "0.8.0"
    (live / "scripts").mkdir(parents=True)
    (stale / "scripts").mkdir(parents=True)
    (live / "scripts" / "git-finalize-hook.sh").write_text("#!/usr/bin/env bash\n")

    # stale finalize-hook symlinks, then GC the old cache -> dangling
    for h in ("post-merge", "post-commit", "post-checkout"):
        (repo / ".git" / "hooks" / h).symlink_to(stale / "scripts" / "git-finalize-hook.sh")
    shutil.rmtree(stale)

    _git(
        repo,
        "config",
        "merge.observations-jsonl.driver",
        f"python3 {stale}/scripts/merge_driver_observations.py %O %A %B",
    )
    _git(
        repo,
        "config",
        "merge.memory-json.driver",
        f"python3 {stale}/scripts/merge_driver_memory.py %O %A %B",
    )
    (repo / ".gitattributes").write_text(
        ".ai-state/observations.jsonl merge=observations-jsonl\n"
        ".ai-state/memory.json merge=memory-json\n"
    )
    (repo / ".ai-state" / ".praxion-onboard.json").write_text(
        json.dumps(
            {
                "plugin": "i-am@bit-agora",
                "onboarded_with_version": "0.8.0",
                "onboarded_at": "2026-01-01T00:00:00Z",
                "scope": "user",
                "artifacts": {
                    "hooks": ["pre-commit", "post-merge", "post-commit", "post-checkout"],
                    "merge_drivers": ["observations-jsonl", "memory-json"],
                    "gitattributes": [
                        ".ai-state/observations.jsonl merge=observations-jsonl",
                        ".ai-state/memory.json merge=memory-json",
                    ],
                },
            }
        )
    )
    return {"repo": repo, "live": live}


def _manifest(repo: Path) -> dict:
    return json.loads((repo / ".ai-state" / ".praxion-onboard.json").read_text())


def test_check_reports_drift_without_mutating(project):
    repo, live = project["repo"], project["live"]
    before = os.readlink(repo / ".git" / "hooks" / "post-merge")
    r = _run(repo, live, "--check")
    assert r.returncode == 1, r.stderr
    # nothing mutated
    assert os.readlink(repo / ".git" / "hooks" / "post-merge") == before
    assert _manifest(repo)["onboarded_with_version"] == "0.8.0"


def test_apply_repoints_all_surfaces(project):
    repo, live = project["repo"], project["live"]
    r = _run(repo, live)
    assert r.returncode == 0, r.stderr
    live_hook = str(live / "scripts" / "git-finalize-hook.sh")
    for h in ("post-merge", "post-commit", "post-checkout"):
        assert os.readlink(repo / ".git" / "hooks" / h) == live_hook
    assert (
        _git(repo, "config", "--get", "merge.observations-jsonl.driver")
        == f"python3 {live}/scripts/merge_driver_observations.py %O %A %B"
    )
    assert _manifest(repo)["onboarded_with_version"] == "0.9.0"


def test_retired_driver_removed(project):
    repo, live = project["repo"], project["live"]
    _run(repo, live)
    # driver unset
    rc = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "merge.memory-json.driver"]
    ).returncode
    assert rc != 0
    # dropped from .gitattributes and manifest
    assert "memory-json" not in (repo / ".gitattributes").read_text()
    assert _manifest(repo)["artifacts"]["merge_drivers"] == ["observations-jsonl"]


def test_apply_is_idempotent(project):
    repo, live = project["repo"], project["live"]
    _run(repo, live)
    second = _run(repo, live)
    assert "Already current" in second.stdout, second.stdout
    assert _run(repo, live, "--check").returncode == 0


def test_dry_run_mutates_nothing(project):
    repo, live = project["repo"], project["live"]
    before = os.readlink(repo / ".git" / "hooks" / "post-merge")
    r = _run(repo, live, "--dry-run")
    assert r.returncode == 0
    assert "would change" in r.stdout
    assert os.readlink(repo / ".git" / "hooks" / "post-merge") == before
    assert _manifest(repo)["onboarded_with_version"] == "0.8.0"


def test_dev_self_host_symlink_left_untouched(project):
    """A finalize hook that resolves to a real file outside the /i-am/ cache is
    a dev/self-host install and must not be re-pointed."""
    repo, live = project["repo"], project["live"]
    dev = repo / "devtree" / "scripts"
    dev.mkdir(parents=True)
    (dev / "git-finalize-hook.sh").write_text("#!/usr/bin/env bash\n")
    hp = repo / ".git" / "hooks" / "post-merge"
    hp.unlink()
    hp.symlink_to(dev / "git-finalize-hook.sh")
    _run(repo, live)
    # unchanged: still points at the dev tree, not the live cache
    assert os.readlink(hp) == str(dev / "git-finalize-hook.sh")


def test_non_praxion_driver_not_overwritten(project):
    repo, live = project["repo"], project["live"]
    _git(repo, "config", "merge.observations-jsonl.driver", "my-custom-driver %O")
    r = _run(repo, live)
    assert r.returncode == 0
    assert _git(repo, "config", "--get", "merge.observations-jsonl.driver") == "my-custom-driver %O"
    assert "refusing to overwrite" in r.stdout


def test_refuses_non_onboarded_project(tmp_path: Path):
    repo = tmp_path / "bare"
    (repo / ".git").mkdir(parents=True)
    live = tmp_path / "cache" / "i-am" / "0.9.0" / "scripts"
    live.mkdir(parents=True)
    r = _run(repo, live.parent)
    assert r.returncode == 1
    assert "not a Praxion-onboarded project" in r.stderr
