"""Builders for the repository histories the merge-trigger scenarios start from.

Every builder works with plain git and the observation-log drivers: a worktree
"holds a log" when rows were appended to its own `.ai-state/` log; a branch is
"merged without hooks" when it was merged before any hook was installed, so its
worktree is already in the main checkout's history while its rows are not in the
main log -- the state in which a trigger that judged "brought in" wrongly would
copy rows it must not.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from tests.acceptance.drivers.hooks import Hooked
from tests.acceptance.drivers.log_rows import agent_start
from tests.acceptance.drivers.log_segments import append_rows, history_rows, state_dir_of
from tests.acceptance.drivers.repository import (
    add_worktree,
    branch_of,
    commit_file,
    git,
)

CONFLICT_FILE = "shared.txt"


def rows_for(name: str, count: int = 3) -> list[dict]:
    """Distinct rows a pipeline running in worktree `name` recorded."""
    return [
        agent_start(
            f"{name}-agent-{n:04d}",
            at=f"2026-10-03T10:{n:02d}:00+00:00",
            project=name,
            session_id=f"{name}-session",
        )
        for n in range(count)
    ]


def worktree_holding_rows(main: Path, name: str, *, commits: int = 1) -> tuple[Path, list[dict]]:
    """A worktree with `commits` commits of its own and a log holding rows of its own."""
    worktree = add_worktree(main, name)
    rows = rows_for(name)
    append_rows(state_dir_of(worktree), rows)
    # File names and messages never spell the worktree's name, so a line naming it
    # in an operation's output is the hooks' report, not git's own summary.
    tag = hashlib.sha1(name.encode()).hexdigest()[:8]
    for n in range(commits):
        commit_file(worktree, f"work-{tag}-{n}.txt", f"{tag} {n}\n", f"work {tag} {n}")
    return worktree, rows


def conflicting_change(checkout: Path, side: str) -> str:
    """Commit a change to the one file both sides edit; returns the new HEAD."""
    return commit_file(checkout, CONFLICT_FILE, f"{side}\n", f"{side}: edit the shared file")


def merged_without_hooks(main: Path, name: str) -> None:
    git(main, "merge", "--no-edit", "--no-ff", branch_of(name))


def canonical(rows: list[dict]) -> Counter:
    """Rows as a multiset of canonical JSON, so key order and spacing never matter."""
    return Counter(json.dumps(r, sort_keys=True) for r in rows)


def times_held(main: Path, rows: list[dict]) -> list[int]:
    """How many times the main log's history holds each of `rows`, in order."""
    held = canonical(history_rows(state_dir_of(main)))
    return [held[json.dumps(r, sort_keys=True)] for r in rows]


def resolve_conflict(hooked: Hooked, checkout: Path | None = None) -> None:
    target = (checkout or hooked.main) / CONFLICT_FILE
    target.write_text("resolved\n", encoding="utf-8")
    hooked.git("add", CONFLICT_FILE, cwd=checkout)


def write_project_setting(main: Path, settings_file: str, key: str, value: str) -> None:
    """Put `key=value` in the `env` of the main checkout's `.claude/<settings_file>`."""
    target = main / ".claude" / settings_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"env": {key: value}}) + "\n", encoding="utf-8")
