"""Scratch places for project gating: projects, their state, the install and the plugin.

A place is a git working tree or a plain directory under a scenario's sandbox, optionally
carrying `.ai-state/` with a synthetic decision index whose titles carry a marker, a linked
worktree, or a project `CLAUDE.md` written from the shipped instruction blocks (this
checkout's, or the base's frozen copy). The install is `bash install.sh code --relink` into a
scratch HOME; the plugin is this checkout behind a frozen kernel adoption ledger, so what a
spawn receives never follows the checkout's own `.ai-state/`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tests.acceptance.drivers import model_routing_move as routing_move
from tests.acceptance.drivers.kernel_sandbox import isolated_env
from tests.acceptance.drivers.process_text_oracles import FIXTURES, REPO_ROOT, fixture_text

BLACKLIST = ".claude/praxion-rules.yaml"
TEMPLATE = ".claude/praxion-rules.yaml.example"


# -- Places ---------------------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Gating Acceptance",
            "-c",
            "user.email=gating@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        env=isolated_env(cwd.parent / f".{cwd.name}-git"),
        check=True,
        capture_output=True,
        timeout=60,
    )


def decisions_index(marker: str) -> str:
    """A decision index whose two decisions carry `marker` in their titles."""
    return fixture_text("decisions_index.md").replace("<marker>", marker)


def plant_state(directory: Path, marker: str | None = None) -> Path:
    """Give `directory` a `.ai-state/` and, with `marker`, a decision index."""
    state = directory / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    if marker is not None:
        (state / "decisions").mkdir(exist_ok=True)
        (state / "decisions" / "DECISIONS_INDEX.md").write_text(
            decisions_index(marker), encoding="utf-8"
        )
    return directory


def repository(path: Path, *, state_marker: str | None = None, managed: bool = False) -> Path:
    """A git working tree with one commit; `managed` (or a marker) gives it committed state."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("# scratch\n", encoding="utf-8")
    if managed or state_marker is not None:
        plant_state(path, state_marker)
        (path / ".ai-state" / "README.md").write_text("state\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "start")
    return path


def linked_worktree(main: Path, path: Path) -> Path:
    _git(main, "worktree", "add", "-q", "-b", "gating-wt", str(path))
    return path


def shipped_instructions() -> str:
    """A project CLAUDE.md written from this checkout's shipped instruction blocks (every
    `claude/canonical-blocks/*.md` but the hackathon block, in name order)."""
    blocks = sorted((REPO_ROOT / "claude" / "canonical-blocks").glob("*.md"))
    return "\n\n".join(
        b.read_text(encoding="utf-8") for b in blocks if b.name != "hackathon-mode.md"
    )


def project_with_current_instructions(path: Path) -> Path:
    """A managed project whose own CLAUDE.md this checkout's shipped blocks wrote."""
    repository(path, managed=True)
    (path / "CLAUDE.md").write_text(shipped_instructions(), encoding="utf-8")
    return path


def project_with_old_instructions(path: Path) -> Path:
    """A managed project whose own CLAUDE.md the base's shipped blocks wrote."""
    repository(path, managed=True)
    (path / "CLAUDE.md").write_text(fixture_text("base_project_CLAUDE.md"), encoding="utf-8")
    return path


def write_blacklist(directory: Path, disable: list[str]) -> None:
    listed = "".join(f"  - '{pattern}'\n" for pattern in disable)
    target = directory / BLACKLIST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"version: 1\ndisable:\n{listed}", encoding="utf-8")


# -- The install and the plugin --------------------------------------------------------------------


def installed_home(scratch: Path) -> Path:
    """A HOME after `bash install.sh code --relink` from this checkout (the scratch's `home`)."""
    result = routing_move.install(scratch)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return scratch / "home"


def copy_home(template: Path, dest: Path) -> Path:
    shutil.copytree(template, dest, symlinks=True)
    return dest


def plugin_root(dest: Path) -> Path:
    """This checkout as the running plugin, with a frozen kernel adoption ledger in place of the
    live one, so what a spawn receives never follows the checkout's own `.ai-state/`."""
    dest.mkdir(parents=True, exist_ok=True)
    for entry in REPO_ROOT.iterdir():
        if entry.name not in (".ai-state", ".ai-work", ".git", ".claude"):
            (dest / entry.name).symlink_to(entry)
    (dest / ".ai-state").mkdir()
    shutil.copy(FIXTURES / "kernel_adoption.yaml", dest / ".ai-state" / "kernel_adoption.yaml")
    return dest
