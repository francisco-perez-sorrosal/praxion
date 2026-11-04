"""Whether a working directory belongs to a managed project, and which one.

The single home of the "is this directory served by a ``.ai-state/``?" question:
``locate`` answers it for the observation log, ``scope_of`` for everything that
is delivered only to managed projects. A session may work from any subdirectory of a checkout, yet its project is the
directory whose root holds ``.ai-state/``: ``locate`` walks up from the working
directory to the nearest such directory and stops at the first ``.git`` entry,
so a separate clone nested inside a managed project never borrows its host's
state.

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


# Immutable like the dataclasses they stand in for: ``dataclasses`` and
# ``typing`` are off the hook hot path (``locate`` runs on every tool call).
# Callers tell the cases apart by type (``isinstance``), never by tuple equality.
Managed = namedtuple("Managed", ("root", "state_dir"))  # root holds state_dir
Unmanaged = namedtuple("Unmanaged", ())  # no .ai-state/ serves the directory

ProjectScope = Managed | Unmanaged


def scope_of(cwd):
    """The `ProjectScope` of ``cwd``: `Managed` exactly when `locate` finds a
    location for it. The one constructor of the type, so every managed-only
    behaviour shares the log's answer by construction. Never raises, and keeps
    nothing between calls: every call evaluates the directory afresh."""
    location = locate(cwd)
    if location is None:
        return Unmanaged()
    return Managed(location.project_dir, location.state_dir)


def locate(cwd):
    """The `Location` serving ``cwd``, or None when no state serves it.

    The directory itself wins when it holds ``.ai-state/``. Otherwise the
    nearest ancestor that does serves it, provided that ancestor sits at or
    below the checkout root (the first directory up with a ``.git`` entry). A
    directory that is in no checkout, or whose checkout holds no state, has no
    log. A relative ``cwd`` has no meaning to a hook (it would resolve against
    the hook's own directory), and one that no longer exists -- a removed linked
    worktree, a deleted subdirectory -- would otherwise be read as its
    still-recording parents by path text alone: both give None. Never raises: a
    non-string or empty ``cwd`` and any ``OSError`` give None.
    """
    if not isinstance(cwd, str) or not cwd:
        return None
    start = Path(cwd)
    try:
        if not start.is_absolute() or not start.is_dir():
            return None
        project_dir = _serving_directory(start)
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
