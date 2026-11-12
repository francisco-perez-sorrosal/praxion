"""Whether a working directory belongs to a managed project, and which one.

The single home of the "is this directory served by a ``.ai-state/``?" question:
``locate`` answers it for the observation log, ``scope_of`` for everything that
is delivered only to managed projects. A session may work from any subdirectory of a checkout, yet its project is the
directory whose root holds ``.ai-state/``: ``locate`` walks up from the working
directory to the nearest such directory and stops at the first ``.git`` entry,
so a separate clone nested inside a managed project never borrows its host's
state.

It also names the tracked state files Praxion's own hooks rewrite
(`HOOK_WRITTEN_STATE_FILES`), declared here once so a reader of git's dirty or
committed paths can tell a session's work from its by-products.

Runs on every hook call: ``pathlib`` and ``collections`` only, no subprocess,
at most two ``stat`` calls per directory level.
"""

from __future__ import annotations

from collections import namedtuple
from pathlib import Path

STATE_DIRNAME = ".ai-state"
CHECKOUT_MARKER = ".git"  # a directory in a clone, a file in a linked worktree

# Tracked files in the state directory that Praxion's own hooks rewrite as a
# by-product of any session: the Stop hook's per-session summary row (dec-377),
# the commit gate's ratchet sample, the post-commit chain's doc manifest. They
# ride the next state commit, so a session finds them modified whatever it
# works on: their dirtiness says a session ran, never what it was about.
SUMMARY_FILENAME = "observations_summary.jsonl"
TOKEN_BASELINE_FILENAME = "token_budget_baseline.json"
DOC_MANIFEST_FILENAME = "doc_manifest.yaml"
HOOK_WRITTEN_STATE_FILES = frozenset(
    {SUMMARY_FILENAME, TOKEN_BASELINE_FILENAME, DOC_MANIFEST_FILENAME}
)


def is_hook_written_state(path):
    """Whether a path, as git prints it, names one of `HOOK_WRITTEN_STATE_FILES`.

    Judged by the last two components: a project nested below the checkout root
    keeps its state in its own ``.ai-state/``, and a file of the same name
    anywhere else is ordinary work. Git quotes a path that holds a space.
    """
    directory, _, name = path.strip('"').rpartition("/")
    return name in HOOK_WRITTEN_STATE_FILES and directory.rpartition("/")[2] == STATE_DIRNAME


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
