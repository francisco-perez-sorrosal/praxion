"""The adoption ledger's git history: the move a commit makes, and when a trial re-opened.

`kernel_ledger` judges values; this module reads them out of git, for the two judgements that
need a commit's time:

- **The move under the gate.** When the ledger in the tree differs from HEAD's, a commit is
  being built on HEAD: the move is HEAD -> tree, and the new commit's time is the gate's own
  clock, which that commit's time can only follow. When the tree's ledger is HEAD's, the move
  judged is HEAD's own (first parent -> HEAD), dated by HEAD's committer time.
- **The liveness bound.** A trial re-opened from held is judged from the commit that re-opened
  it, found on the plugin root's first-parent history of the ledger, so no spawn made while the
  role was held is ever judged. A plugin root without that history cannot place a re-opening:
  its adopted roles are judged from their recorded start and named as unplaced.

Commit times have whole-second resolution: a spawn in the same second as the re-opening
commit, before it, is judged (a declared limit).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import kernel_ledger as kl
import kernel_model as km
from _git_runner import run_git

HEAD = "HEAD"
FIRST_PARENT = "HEAD^"


@dataclass(frozen=True)
class PlacedAdoptions:
    """The adopted roles with their judged start, and those whose re-opening could not be placed."""

    adoptions: Mapping[str, kl.Adoption]
    unplaced: tuple[str, ...]


@dataclass(frozen=True)
class Present:
    """The parent ledger was read."""

    ledger: kl.ParentLedger


@dataclass(frozen=True)
class Absent:
    """The move starts from no ledger: no repository, no commit, or no ledger in the commit."""


@dataclass(frozen=True)
class Unreadable:
    """The commit holds a ledger too broken to read: not the same as holding none."""

    detail: str


ParentRead = Present | Absent | Unreadable


def parent_ledger(
    root: Path, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> ParentRead:
    """The ledger the judged move starts from, with both commits' times.

    Read as leniently as the moves allow (status, start, run ids): a commit that repairs a
    ledger the model now refuses must not be blocked by the old one. A parent too broken
    even for that is `Unreadable`, never `Absent`: judged as none, its first appearance
    would be exempt again.
    """
    head = _ledger_at(root, HEAD)
    if _read_text(root / km.LEDGER_PATH) != head:
        base_rev, base, built_at = HEAD, head, None
    else:
        base_rev, base, built_at = FIRST_PARENT, _ledger_at(root, FIRST_PARENT), HEAD
    if base is None:  # no repository, no commit, or no ledger in the commit moved from
        return Absent()
    try:
        entries = kl.parse_entries(km.parse_yaml(base, f"{km.LEDGER_PATH} at {base_rev}"))
    except km.KernelModelError as unreadable:
        return Unreadable(str(unreadable))
    judged_at = clock() if built_at is None else commit_time(root, built_at)
    return Present(kl.ParentLedger(entries, commit_time(root, base_rev), judged_at))


def placed_adoptions(plugin_root: Path) -> PlacedAdoptions:
    """Who `plugin_root`'s ledger adopts, each judged from its start or its re-opening commit."""
    adoptions = kl.load_adoptions(plugin_root)
    history = ledger_history(plugin_root)
    if history is None:
        return PlacedAdoptions(adoptions, tuple(sorted(adoptions)))
    return PlacedAdoptions(kl.judged_adoptions(adoptions, history), ())


def ledger_history(root: Path) -> tuple[kl.LedgerVersion, ...] | None:
    """The tree's ledger, then each first-parent commit of it, newest first; None: no history."""
    logged = run_git(root, "log", "--first-parent", "--format=%H %cI", "--", km.LEDGER_PATH)
    commits = [line.split(" ", 1) for line in logged.stdout.splitlines() if line.strip()]
    if logged.returncode != 0 or not commits:
        return None
    versions = [kl.LedgerVersion(None, km.load_statuses(root))]
    for sha, stamp in commits:
        text = _ledger_at(root, sha)
        try:
            statuses = km.parse_statuses(km.parse_yaml(text or "", f"{km.LEDGER_PATH} at {sha}"))
        except km.KernelModelError:
            continue  # a version that does not read places nothing; the walk goes on
        versions.append(kl.LedgerVersion(datetime.fromisoformat(stamp), statuses))
    return tuple(versions)


def commit_time(root: Path, revision: str) -> datetime:
    shown = run_git(root, "log", "-1", "--format=%cI", revision, "--")
    if shown.returncode != 0 or not shown.stdout.strip():
        raise km.KernelModelError(f"{revision!r} is not a revision of {root}")
    return datetime.fromisoformat(shown.stdout.strip())


def _ledger_at(root: Path, revision: str) -> str | None:
    shown = run_git(root, "show", f"{revision}:{km.LEDGER_PATH}")
    return shown.stdout if shown.returncode == 0 else None


def _read_text(path: Path) -> str | None:
    return path.read_bytes().decode("utf-8") if path.is_file() else None
