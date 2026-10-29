"""The scratch project a kit builds for a session: files on disk, a git history, shipped blocks.

Kits differ in what their fixtures hold, not in how a fixture is made, so the helpers every kit
needs live here: writing a tree of files, running git apart from the operator's own configuration,
and the ``CLAUDE.md`` a managed project carries.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# The checkout's shipped blocks, which a managed fixture's ``CLAUDE.md`` carries.
CANONICAL_BLOCKS = Path(__file__).resolve().parents[5] / "claude" / "canonical-blocks"

IDENTITY = (
    ("user.name", "Fixture Author"),
    ("user.email", "fixture-author@example.invalid"),
    ("commit.gpgsign", "false"),  # a session commits without a signing agent
)

Files = tuple[tuple[str, str], ...]  # (path, content) pairs, in write order


def write_files(root: Path, files: Files) -> None:
    """Write each ``(path, content)`` pair under ``root``, creating directories as needed."""
    for path, content in files:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` apart from the operator's own configuration; return its stdout."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    done = subprocess.run(
        ["git", "-C", str(repo), *args], env=env, check=True, capture_output=True, text=True
    )
    return done.stdout


def project_instructions(excluding: frozenset[str]) -> str:
    """The shipped blocks, in file order and but for those named, as a project's ``CLAUDE.md``."""
    blocks = [
        path.read_text(encoding="utf-8").strip()
        for path in sorted(CANONICAL_BLOCKS.glob("*.md"))
        if path.name not in excluding
    ]
    return "\n\n".join(["# Fixture project", *blocks]) + "\n"
