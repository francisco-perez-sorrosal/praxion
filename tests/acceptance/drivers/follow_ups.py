"""Driver for a task directory's follow-up record, as the cleanup safety check reads it.

A scenario builds `.ai-work/<task-slug>/` under its own temporary directory, writes a
follow-up record (`FOLLOW_UPS.md`) and any other pipeline document into it, and runs the
cleanup safety check over that directory from outside.

Bound here, because the specification or the base commit fixes them:

- the check is `python3 scripts/clean_work_safety.py`, pointed at a `.ai-work/` directory with
  `--ai-work-root PATH` and given the task slugs to classify; `--json` prints its verdicts as
  one object whose `task_dirs` hold each directory's `slug`, `classification` (`BLOCK`, `WARN`
  or `SAFE`) and `reasons`; it exits 1 when any directory is `BLOCK` (its usage and docstring
  at the base commit);
- a follow-up item carries a state word (`open`, `fixed`, `ledgered`, `dropped`), the state's
  argument (a commit, a row id, a reason; none for `open`) and a description of the debt.

Bound by the design: an item is one line, `- [<state>] <description>`, where `<state>` is the
state word followed by a space and the argument only when the argument is not empty. So
`open` is `- [open] ...`, `fixed 4f3c2a1` is `- [fixed 4f3c2a1] ...`, and an item the check
cannot read is written as given (`- [done] ...`, `- [fixed] ...`).

Isolation: every process runs with `kernel_sandbox.isolated_env`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import (
    REPO_ROOT,
    RunResult,
    _run,
    isolated_env,
)

CHECK = "scripts/clean_work_safety.py"
RECORD = "FOLLOW_UPS.md"


@dataclass(frozen=True)
class FollowUp:
    """One item of small debt: its state word, the state's argument, and what the debt is."""

    state: str
    argument: str
    description: str


def open_item(description: str) -> FollowUp:
    return FollowUp("open", "", description)


def fixed(description: str, sha: str = "4f3c2a1") -> FollowUp:
    return FollowUp("fixed", sha, description)


def ledgered(description: str, row: str = "td-987") -> FollowUp:
    return FollowUp("ledgered", row, description)


def dropped(description: str, reason: str = "superseded by the feature's own rename") -> FollowUp:
    return FollowUp("dropped", reason, description)


def record_text(items: list[FollowUp]) -> str:
    """The whole follow-up record holding `items`, one per line, in the designed shape.

    Every item is written as given, legal or not: an unknown state word sits where a state
    word goes, and an empty argument is left out where an argument goes, so a scenario can
    hand the check an item it cannot read.
    """
    return "".join(f"- [{_state_text(item)}] {item.description}\n" for item in items)


def _state_text(item: FollowUp) -> str:
    return f"{item.state} {item.argument}" if item.argument else item.state


# -- Task directories ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Workspace:
    """A `.ai-work/` directory a scenario fills."""

    root: Path

    def task(self, slug: str) -> Path:
        path = self.root / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write(self, slug: str, name: str, text: str) -> None:
        (self.task(slug) / name).write_text(text, encoding="utf-8")

    def write_record(self, slug: str, items: list[FollowUp]) -> None:
        self.write(slug, RECORD, record_text(items))


def workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / ".ai-work"
    root.mkdir(parents=True, exist_ok=True)
    return Workspace(root)


# -- The cleanup safety check -----------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    exit_code: int
    classification: str
    reasons: list[dict]
    output: str

    def reasons_naming(self, text: str) -> list[dict]:
        return [r for r in self.reasons if text in json.dumps(r, ensure_ascii=False)]


def _check(space: Workspace, slug: str, *flags: str) -> RunResult:
    argv = [sys.executable, str(REPO_ROOT / CHECK), "--ai-work-root", str(space.root), *flags]
    return _run([*argv, slug], space.root.parent, isolated_env(space.root.parent / ".check"))


def classify(space: Workspace, slug: str) -> Verdict:
    """The check's `--json` verdict on one task directory."""
    result = _check(space, slug, "--json")
    assert "{" in result.output, f"the check printed no JSON verdict:\n{result.output}"
    report, _ = json.JSONDecoder().raw_decode(result.output[result.output.index("{") :])
    [task] = [t for t in report["task_dirs"] if t["slug"] == slug]
    return Verdict(result.exit_code, task["classification"], task["reasons"], result.output)


def classify_text(space: Workspace, slug: str) -> RunResult:
    """The check's text verdict on one task directory."""
    return _check(space, slug)
