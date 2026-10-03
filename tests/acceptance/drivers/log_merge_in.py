"""Driver for merge-in: a worktree's log rows copied into the main checkout's log.

Two boundaries:

* merge-in itself, run for one worktree of a repository: it copies into the
  main checkout's log every row of the worktree's log (its active log and every
  archive) that the main log does not already hold, and reports how many rows
  it copied, skipped as already held, and skipped as malformed, plus a reason
  whenever something could not be read or written. It honours the recording
  mode in effect (`PRAXION_OBSERVATION_LOG`). The driver runs the merge-in
  command and maps its JSON report onto `MergeInReport`.
* the merge-time trigger: once installed in a main checkout the way a managed
  repository has it, a merge or a pull run in that checkout which brings in the
  branch of a still-existing worktree performs the same merge-in. The driver
  installs the one git hook a managed repository's finalize dispatcher serves
  for a merge, and nothing else.

A command that does not exist yet fails the scenario with an assertion naming
it, never a collection error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MERGE_IN_SCRIPT = "scripts/merge_worktree_log.py"
FINALIZE_DISPATCHER = REPO_ROOT / "scripts" / "git-finalize-hook.sh"


@dataclass(frozen=True)
class MergeInReport:
    copied: int
    skipped: int  # rows the main log already held
    malformed: int  # lines of the worktree's log that were not a JSON object
    reason: str | None  # why something could not be read or written; None when nothing failed
    output: str  # everything merge-in printed, for scenarios that check what it says
    exit_code: int


def _require_merge_in_command(subject: str) -> None:
    assert (REPO_ROOT / MERGE_IN_SCRIPT).is_file(), (
        f"{subject} {MERGE_IN_SCRIPT} does not exist yet"
    )


def merge_in(main: Path, worktree: Path, *, mode: str | None = None) -> MergeInReport:
    """Merge the log of `worktree` into the log of `main`; `mode` sets the recording mode."""
    _require_merge_in_command("the merge-in command")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_", "GIT_"))}
    if mode is not None:
        env["PRAXION_OBSERVATION_LOG"] = mode
    result = subprocess.run(
        [
            sys.executable,
            MERGE_IN_SCRIPT,
            "--repo-root",
            str(main),
            "--worktree",
            str(worktree),
            "--json",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"merge-in printed no JSON report (exit {result.returncode}): "
            f"{result.stdout[:500]!r} {result.stderr[-1500:]!r}"
        ) from exc
    return MergeInReport(
        copied=report["copied"],
        skipped=report["skipped"],
        malformed=report["malformed"],
        reason=report["reason"],
        output=result.stdout + result.stderr,
        exit_code=result.returncode,
    )


def install_merge_trigger(main: Path) -> None:
    """Install the merge-time trigger in `main` the way a managed repository has it."""
    # Without this, a scenario that only asserts the merge itself succeeds would pass
    # on a repository whose hook has nothing to run.
    _require_merge_in_command("the merge-time trigger runs the merge-in command, which")
    hook = main / ".git" / "hooks" / "post-merge"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.unlink(missing_ok=True)
    hook.symlink_to(FINALIZE_DISPATCHER)
