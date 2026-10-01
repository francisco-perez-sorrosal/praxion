"""Which log, and which ``project``, a working directory belongs to.

The package's one answer to that question. A session may work from any
subdirectory of a checkout, yet its events belong to the project whose root
holds ``.ai-state/``: ``locate`` walks up from the working directory to the
nearest such directory and stops at the first ``.git`` entry, so a separate
clone nested inside a recording project never writes into its host's log.

Runs on every hook call: ``pathlib`` and ``collections`` only, no subprocess,
at most two ``stat`` calls per directory level.
"""

from __future__ import annotations

from collections import namedtuple
from pathlib import Path

STATE_DIRNAME = ".ai-state"
CHECKOUT_MARKER = ".git"  # a directory in a clone, a file in a linked worktree

# ``project`` names the directory that holds the state, never a resolved link
# target: ``.ai-state`` may be a symlink to a directory kept elsewhere.
Location = namedtuple("Location", ("state_dir", "project_dir", "project"))


def locate(cwd):
    """The `Location` serving ``cwd``, or None when no log serves it.

    The directory itself wins when it holds ``.ai-state/``. Otherwise the
    nearest ancestor that does serves it, provided that ancestor sits at or
    below the checkout root (the first directory up with a ``.git`` entry). A
    directory that is in no checkout, or whose checkout holds no state, has no
    log. Never raises: a non-string or empty ``cwd`` and any ``OSError`` give
    None.
    """
    if not isinstance(cwd, str) or not cwd:
        return None
    try:
        project_dir = _serving_directory(Path(cwd))
    except OSError:
        return None
    if project_dir is None:
        return None
    return Location(project_dir / STATE_DIRNAME, project_dir, project_dir.name)


def _serving_directory(start):
    """The nearest directory at or above ``start`` holding the state, never
    past the checkout root; ``start`` itself needs no checkout around it."""
    nearest = None
    for directory in (start, *start.parents):
        if nearest is None and (directory / STATE_DIRNAME).is_dir():
            nearest = directory
            if directory == start:
                return start
        if (directory / CHECKOUT_MARKER).exists():
            return nearest
    return None
