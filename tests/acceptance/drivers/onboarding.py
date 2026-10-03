"""Driver that sets up a new project the way onboarding does, in a sandbox.

Runs `scripts/onboard-project <name> <target>` (new mode) with its own HOME, a
plugins file claiming the plugin is installed, and a stub `claude` first on
PATH that accepts the hand-off and does nothing -- the same isolation the
script's own shell test uses. The result is the scaffolded project directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ONBOARD = REPO_ROOT / "scripts" / "onboard-project"


def scaffold_new_project(sandbox: Path, name: str = "onboarded-app") -> Path:
    bin_dir = sandbox / "bin"
    home = sandbox / "home"
    target = sandbox / "target"
    for directory in (bin_dir, home / ".claude" / "plugins", target):
        directory.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "claude"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        '{"praxion@bit-agora": {"version": "test"}}\n', encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_", "GIT_"))}
    env["HOME"] = str(home)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(
        [shutil.which("bash") or "/bin/bash", str(ONBOARD), name, str(target)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    project = target / name
    detail = f"(exit {result.returncode}): {result.stderr[-1500:]}"
    assert result.returncode == 0, f"onboarding failed {detail}"
    assert project.is_dir(), f"onboarding did not scaffold {project} {detail}"
    return project


def untracked_files(project: Path) -> list[str]:
    """Untracked, unignored files, relative to the project root."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=True,
    )
    return [line[3:] for line in result.stdout.splitlines() if line.startswith("?? ")]
