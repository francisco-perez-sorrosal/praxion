"""Driver for merge-in: a worktree's log rows copied into the main checkout's log.

Two assumed boundaries, both unbound until a binding step names them:

* merge-in itself, run for one worktree of a repository: it copies into the
  main checkout's log every row of the worktree's log (its active log and every
  archive) that the main log does not already hold, and reports how many rows
  it copied, skipped as already held, and skipped as malformed, plus a reason
  whenever something could not be read or written. It honours the recording
  mode in effect (`PRAXION_OBSERVATION_LOG`).
* the merge-time trigger: once installed in a main checkout the way a managed
  repository has it, a merge or a pull run in that checkout which brings in the
  branch of a still-existing worktree performs the same merge-in.

Each unbound function raises with the assumption in words.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MergeInReport:
    copied: int
    skipped: int  # rows the main log already held
    malformed: int  # lines of the worktree's log that were not a JSON object
    reason: str | None  # why something could not be read or written; None when nothing failed
    output: str  # everything merge-in printed, for scenarios that check what it says
    exit_code: int


def merge_in(main: Path, worktree: Path, *, mode: str | None = None) -> MergeInReport:
    """Merge the log of `worktree` into the log of `main`; `mode` sets the recording mode."""
    raise NotImplementedError(
        "unbound: merge-in of one worktree's observation log into the main checkout's log, "
        "reporting copied, already-held and malformed counts and a reason on failure, "
        "has not been bound to this driver yet"
    )


def install_merge_trigger(main: Path) -> None:
    """Install the merge-time trigger in `main` the way a managed repository has it."""
    raise NotImplementedError(
        "unbound: the trigger that merges a still-existing worktree's log when the main "
        "checkout merges or pulls that worktree's branch has not been bound to this driver yet"
    )
