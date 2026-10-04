"""Driver for the surfaces that install, repair and check a project's git hooks.

Runs the existing entry points as a user or a command would, in scratch
repositories, with their own HOME, no inherited `GIT_*`, `CLAUDE*` or `PRAXION_*`
variables, and `python3` on PATH the suite's interpreter:

* the onboarding hook reconciler, `scripts/install_git_hooks.py`, in one of its
  install, heal, status and uninstall modes (plugin root: this repository);
* the pin upgrade, `scripts/upgrade_project_pins.sh`, against a managed project
  onboarded by an earlier release, with a fake live plugin install whose
  `scripts/git-finalize-hook.sh` the hooks must end up pointing at;
* the hook-mirror check, `scripts/check_hook_installation.py`;
* the finalize dispatcher, invoked under a name it does not serve.

A hook slot is compared across names by its shape: absent, a symlink and its
target, or a file and its body with the slot's own name masked, plus the body of
any `<name>.pre-praxion` backup beside it. Two slots treated alike have equal
shapes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.acceptance.drivers.hooks import FINALIZE_HOOKS

REPO_ROOT = Path(__file__).resolve().parents[3]
RECONCILER = REPO_ROOT / "scripts" / "install_git_hooks.py"
PIN_UPGRADE = REPO_ROOT / "scripts" / "upgrade_project_pins.sh"
MIRROR_CHECK = REPO_ROOT / "scripts" / "check_hook_installation.py"
DISPATCHER = REPO_ROOT / "scripts" / "git-finalize-hook.sh"
PROJECT_HOOKS = ("pre-commit", *FINALIZE_HOOKS)
EARLIER_FINALIZE_HOOKS = ("post-merge", "post-commit", "post-checkout")
LIVE_VERSION = "0.9.0"
EARLIER_VERSION = "0.8.0"
BACKUP_SUFFIX = ".pre-praxion"


def _env(sandbox: Path) -> dict[str, str]:
    home = sandbox / "home"
    bin_dir = sandbox / "bin"
    home.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    python3 = bin_dir / "python3"
    if not python3.exists():
        python3.symlink_to(sys.executable)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))}
    env.update(
        HOME=str(home),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=str(home / ".gitconfig"),
        PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    )
    return env


def _run(command: list[str], sandbox: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, env=_env(sandbox), capture_output=True, text=True, timeout=300
    )


def git_in(repo: Path, sandbox: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], sandbox, repo)


def plain_repository(path: Path, sandbox: Path) -> Path:
    """An empty git repository on `main` with no hooks."""
    path.mkdir(parents=True, exist_ok=True)
    git_in(path, sandbox, "init", "-q", "-b", "main")
    hooks = path / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    for sample in hooks.glob("*.sample"):
        sample.unlink()
    return path


def reconcile(
    repo: Path, sandbox: Path, mode: str, *extra: str
) -> subprocess.CompletedProcess[str]:
    """Run the onboarding hook reconciler in `mode` (install, heal, status, uninstall)."""
    return _run(
        [sys.executable, str(RECONCILER), f"--{mode}", "--repo-root", str(repo), *extra],
        sandbox,
        REPO_ROOT,
    )


def hooks_dir_in_use(repo: Path, sandbox: Path) -> Path:
    """The directory git runs hooks from: `core.hooksPath` when set, else `.git/hooks`."""
    configured = git_in(repo, sandbox, "config", "--get", "core.hooksPath").stdout.strip()
    if not configured:
        return repo / ".git" / "hooks"
    path = Path(configured)
    return path if path.is_absolute() else repo / path


def write_hook(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def foreign_hook_body(name: str) -> str:
    return f"#!/bin/sh\necho 'a foreign {name} hook ran'\n"


def slot_shape(hooks_dir: Path, name: str) -> tuple:
    """What occupies the slot `name`, with the name itself masked, and its backup."""
    slot = hooks_dir / name
    backup = hooks_dir / f"{name}{BACKUP_SUFFIX}"
    backup_body = (
        backup.read_text(encoding="utf-8").replace(name, "<hook>") if backup.exists() else None
    )
    if slot.is_symlink():
        return ("symlink", os.readlink(slot), backup_body)
    if slot.is_file():
        body = slot.read_text(encoding="utf-8").replace(name, "<hook>")
        return ("file", body, os.access(slot, os.X_OK), backup_body)
    return ("absent", backup_body)


def installed_hook_names(hooks_dir: Path) -> set[str]:
    """The hook slots a directory fills (samples and backups excluded)."""
    return {
        entry.name
        for entry in hooks_dir.iterdir()
        if not entry.name.endswith((".sample", BACKUP_SUFFIX))
    }


# -- The pin upgrade ---------------------------------------------------------------------


def managed_project(tmp_path: Path) -> tuple[Path, Path]:
    """A project onboarded by an earlier release, and the live plugin install it must point at.

    Its three finalize hooks point at an earlier, garbage-collected plugin version,
    its `post-rewrite` slot is empty, and its manifest records the hooks an earlier
    release installed.
    """
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "proj", sandbox)
    (repo / ".ai-state").mkdir()
    live = repo / "cache" / "praxion" / LIVE_VERSION
    stale = repo / "cache" / "praxion" / EARLIER_VERSION
    write_hook(live / "scripts" / "git-finalize-hook.sh", "#!/usr/bin/env bash\n")
    (stale / "scripts").mkdir(parents=True)
    for name in EARLIER_FINALIZE_HOOKS:
        (repo / ".git" / "hooks" / name).symlink_to(stale / "scripts" / "git-finalize-hook.sh")
    shutil.rmtree(stale)
    git_in(
        repo,
        sandbox,
        "config",
        "merge.observations-jsonl.driver",
        f"python3 {stale}/scripts/merge_driver_observations.py %O %A %B",
    )
    (repo / ".gitattributes").write_text(
        ".ai-state/observations.jsonl merge=observations-jsonl\n", encoding="utf-8"
    )
    manifest = {
        "plugin": "praxion@bit-agora",
        "onboarded_with_version": EARLIER_VERSION,
        "onboarded_at": "2026-01-01T00:00:00Z",
        "scope": "user",
        "artifacts": {
            "hooks": ["pre-commit", *EARLIER_FINALIZE_HOOKS],
            "merge_drivers": ["observations-jsonl"],
            "gitattributes": [".ai-state/observations.jsonl merge=observations-jsonl"],
        },
    }
    (repo / ".ai-state" / ".praxion-onboard.json").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    return repo, live


def upgrade_pins(repo: Path, live: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return _run(
        ["bash", str(PIN_UPGRADE), "--repo-root", str(repo), "--plugin-path", str(live), *extra],
        repo.parent / "sandbox",
        repo,
    )


def live_hook(live: Path) -> str:
    return str(live / "scripts" / "git-finalize-hook.sh")


def link_target(repo: Path, name: str) -> str | None:
    slot = repo / ".git" / "hooks" / name
    return os.readlink(slot) if slot.is_symlink() else None


def recorded_hooks(repo: Path) -> list[str]:
    manifest = json.loads((repo / ".ai-state" / ".praxion-onboard.json").read_text("utf-8"))
    return manifest["artifacts"]["hooks"]


def snapshot(repo: Path) -> dict[str, object]:
    """Every hook slot's shape and the manifest, to tell whether a run changed anything."""
    hooks = repo / ".git" / "hooks"
    return {
        "slots": {entry.name: slot_shape(hooks, entry.name) for entry in sorted(hooks.iterdir())},
        "manifest": (repo / ".ai-state" / ".praxion-onboard.json").read_text("utf-8"),
    }


# -- The mirror check and the dispatcher ----------------------------------------------------


def mirror_check(repo: Path, sandbox: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        [sys.executable, str(MIRROR_CHECK), "--repo-root", str(repo), "--json", "--check"],
        sandbox,
        REPO_ROOT,
    )


def run_dispatcher_as(name: str, repo: Path, sandbox: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the finalize dispatcher through a slot called `name`, as git would."""
    slot = repo / ".git" / "hooks" / name
    slot.symlink_to(DISPATCHER)
    return _run([str(slot)], sandbox, repo)
