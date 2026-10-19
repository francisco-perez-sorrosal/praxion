"""The adoption ledger's git history: the move a commit makes, and when a trial re-opened.

`kernel_ledger` judges values; this module reads them out of git, for the judgements that
need the parent commit or a commit's time:

- **The move under the gate.** When the ledger in the tree differs from HEAD's, a commit is
  being built on HEAD: the move is HEAD -> tree, and the new commit's time is the gate's own
  clock, which that commit's time can only follow. When the tree's ledger is HEAD's, the move
  judged is HEAD's own (first parent -> HEAD), dated by HEAD's committer time.
- **The liveness bound.** A trial re-opened from held is judged from the commit that re-opened
  it, found on the plugin root's first-parent history of the ledger, so no spawn made while the
  role was held is ever judged. A plugin root without that history cannot place a re-opening:
  its adopted roles are judged from their recorded start and named as unplaced.
- **What the move starts from besides the ledger.** The eligible roles pinned in
  `scripts/kernel_eligibility.py`, the adoption records as written and the agent definitions,
  all at that same parent commit: a commit that changes the pin carries no record and no flag.

Commit times have whole-second resolution: a spawn in the same second as the re-opening
commit, before it, is judged (a declared limit).
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kernel_ledger as kl
import kernel_model as km
from _git_runner import run_git

HEAD = "HEAD"
FIRST_PARENT = "HEAD^"
ELIGIBILITY_PIN = "scripts/kernel_eligibility.py"
PINNED_NAME = "ELIGIBLE_ROLES"
# Whatever a move reads from the tree: a tree differing from HEAD in these is a commit being built.
MOVE_INPUTS = (km.LEDGER_PATH, ELIGIBILITY_PIN, "agents")


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


@dataclass(frozen=True)
class NotYetPinned:
    """The parent commit pins no eligible roles anywhere: it predates the module and its list.

    There is no earlier list to hold the commit to, so nothing is judged against one.
    """


@dataclass(frozen=True)
class ParentFlip:
    """What the parent commit held, that a change of the eligible roles cannot share a commit with."""

    eligible: tuple[str, ...] | NotYetPinned
    records: Mapping[str, object]  # role -> adoption record as written
    definitions: Mapping[str, str]  # agent -> definition text, for each agent that has one


def parent_ledger(
    root: Path, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> ParentRead:
    """The ledger the judged move starts from, with both commits' times.

    Read as leniently as the moves allow (status, start, run ids): a commit that repairs a
    ledger the model now refuses must not be blocked by the old one. A parent too broken
    even for that is `Unreadable`, never `Absent`: judged as none, its first appearance
    would be exempt again.
    """
    base_rev, judged_rev = _base_revision(root)
    base = _ledger_at(root, base_rev)
    if base is None:  # no repository, no commit, or no ledger in the commit moved from
        return Absent()
    try:
        entries = kl.parse_entries(km.parse_yaml(base, f"{km.LEDGER_PATH} at {base_rev}"))
    except km.KernelModelError as unreadable:
        return Unreadable(str(unreadable))
    judged_at = clock() if judged_rev is None else commit_time(root, judged_rev)
    return Present(kl.ParentLedger(entries, commit_time(root, base_rev), judged_at))


def parent_flip(root: Path, agents: Collection[str]) -> ParentFlip | None:
    """The eligible roles, adoption records and definitions the judged move starts from.

    None when the parent commit is not in this clone (a shallow one, or no repository): a move
    that has no parent to be placed against is not judged, as with the ledger itself.
    """
    parent, _ = _base_revision(root)
    if run_git(root, "rev-parse", f"{parent}^{{commit}}").returncode != 0:
        return None
    ledger = ledger_mapping(_ledger_at(root, parent), f"{km.LEDGER_PATH} at {parent}")
    texts = {name: _blob_at(root, parent, f"agents/{name}.md") for name in agents}
    return ParentFlip(
        _eligible_at(root, parent, ledger),
        written_records(ledger),
        {name: text for name, text in texts.items() if text is not None},
    )


def ledger_mapping(text: str | None, where: str) -> Mapping[str, Any]:
    """The ledger in `text` as the mapping it is; empty when there is no ledger."""
    return km.parse_yaml(text, where) if text is not None else {}


def written_records(ledger: Mapping[str, Any]) -> Mapping[str, object]:
    """The adoption records under `roles` as written, by role: nothing more is read of them."""
    return km.as_mapping(ledger.get("roles") or {}, "roles")


def pinned_roles(source: str, where: str) -> tuple[str, ...]:
    """The roles in the literal tuple `source` binds to `ELIGIBLE_ROLES`, read without running it."""
    try:
        bound = next(
            statement.value
            for statement in ast.parse(source).body
            if isinstance(statement, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == PINNED_NAME for t in statement.targets)
        )
        roles = ast.literal_eval(bound)
    except (SyntaxError, StopIteration, ValueError) as exc:
        raise km.KernelModelError(f"{where}: binds no literal {PINNED_NAME}") from exc
    if not isinstance(roles, tuple) or not all(isinstance(role, str) for role in roles):
        raise km.KernelModelError(f"{where}: {PINNED_NAME} is not a tuple of role names")
    return roles


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


def _base_revision(root: Path) -> tuple[str, str | None]:
    """The parent a move is judged from, and the commit judged (None: one being built on HEAD).

    A tree that differs from HEAD in a move's inputs is a commit being built on HEAD; a tree
    that is HEAD's has its own move judged, from its first parent.
    """
    changed = run_git(root, "status", "--porcelain", *MOVE_INPUTS)
    return (HEAD, None) if changed.stdout else (FIRST_PARENT, HEAD)


def _eligible_at(
    root: Path, revision: str, ledger: Mapping[str, Any]
) -> tuple[str, ...] | NotYetPinned:
    """The pin at `revision`; from before the pin, the list its ledger carried; else none."""
    if (pin := _blob_at(root, revision, ELIGIBILITY_PIN)) is not None:
        return pinned_roles(pin, f"{ELIGIBILITY_PIN} at {revision}")
    listed = ledger.get(kl.ELIGIBLE_KEY)
    if isinstance(listed, list):
        return tuple(role for role in listed if isinstance(role, str))
    return NotYetPinned()


def _ledger_at(root: Path, revision: str) -> str | None:
    return _blob_at(root, revision, km.LEDGER_PATH)


def _blob_at(root: Path, revision: str, path: str) -> str | None:
    shown = run_git(root, "show", f"{revision}:{path}")
    return shown.stdout if shown.returncode == 0 else None
