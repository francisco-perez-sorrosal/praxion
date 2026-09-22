"""Shared run-directory access for the Workflow-tool cost/isolation surface.

Imported (not executed) by `workflow_run_cost.py` and `check_lens_isolation.py`
as a sibling module -- `scripts/` is on `sys.path[0]` when either runs. Neither
imports the other; both import this one, so the workflow-run layout has a
single definition rather than two that could drift.

Layout, measured live against a real Workflow run (this repo's own spike,
2026-09-19; the harness's `workflow-authoring` skill is the upstream
reference): a run lives at
`~/.claude/projects/<mangled-project>/<session>/subagents/workflows/<wf_id>/`
and holds `agent-<id>.jsonl` (transcript), `agent-<id>.meta.json`
({agentType, description, workflowPhase, spawnDepth, ...}) and `journal.jsonl`
(launched / started{key, agentId, label, phase} / result{key, agentId, result}
events discriminated by a `type` key, in that order per agent). The main-session transcript is a sibling
`.jsonl` file one level up, alongside the `<session>/` directory.

The context-token convention (`input_tokens + cache_read_input_tokens +
cache_creation_input_tokens`) is `context_baseline.py`'s own formula, reused
here rather than imported -- the two scripts stay independent siblings, and
duplicating a three-line pure function is cheaper than coupling this module to
`context_baseline.py`'s own CLI surface.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


class WorkflowRunError(Exception):
    """A run-read failure with a named CLI reason code.

    One exception type for every typed failure (run resolution, journal
    parsing, transcript availability) -- callers branch on `.reason`, not on
    the exception's class, so adding a new reason never adds a new class.
    """

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


# --------------------------------------------------------------------------- #
# project <-> run-directory resolution
# --------------------------------------------------------------------------- #
def transcripts_dir(project_root: Path) -> Path:
    """Claude Code's per-project transcript directory: the project's absolute
    path with every "/" and "." replaced by "-", under `~/.claude/projects/`.
    The "." rule matters for worktrees under `.claude/worktrees/`, whose
    harness directory reads `...-praxion--claude-worktrees-...`."""
    mangled = str(project_root).replace("/", "-").replace(".", "-")
    return Path.home() / ".claude" / "projects" / mangled


def session_from_run_dir(run_dir: Path) -> str:
    """The session id a run directory belongs to: `run_dir` is
    `<transcripts_dir>/<session>/subagents/workflows/<wf_id>/`, so the
    session name is three parents up."""
    return run_dir.parent.parent.parent.name


def main_transcript_path(transcripts_dir: Path, session: str) -> Path:
    """The default main-session transcript: a sibling `.jsonl` of the
    session's own subdirectory, where the harness writes it. Callers
    needing a different path
    (a non-default session, a moved transcript) use their own `--session`
    override instead of this default."""
    return transcripts_dir / f"{session}.jsonl"


def list_runs(transcripts_dir: Path) -> list[dict]:
    """Every known workflow run under this project's transcripts, each as
    `{wf_id, session, run_dir, mtime}` (`mtime` is the run's `journal.jsonl`
    mtime -- the "latest" resolution below and any `--list` timestamp both
    read it from here, not from two different places)."""
    runs = []
    for journal_path in sorted(transcripts_dir.glob("*/subagents/workflows/*/journal.jsonl")):
        run_dir = journal_path.parent
        runs.append(
            {
                "wf_id": run_dir.name,
                "session": session_from_run_dir(run_dir),
                "run_dir": run_dir,
                "mtime": journal_path.stat().st_mtime,
            }
        )
    return runs


def resolve_run(transcripts_dir: Path, run_arg: str) -> dict:
    """Resolve `--run <wf_id|latest>` to one `{wf_id, session, run_dir}`.

    "latest" picks the run whose `journal.jsonl` has the newest mtime;
    an exact tie is genuinely ambiguous, not arbitrary, and is refused rather
    than broken by directory-listing order.
    """
    runs = list_runs(transcripts_dir)
    if run_arg == "latest":
        if not runs:
            raise WorkflowRunError(
                "run-not-found", f"no workflow runs found under {transcripts_dir}"
            )
        newest_mtime = max(run["mtime"] for run in runs)
        newest = [run for run in runs if run["mtime"] == newest_mtime]
        if len(newest) > 1:
            tied = ", ".join(run["wf_id"] for run in newest)
            raise WorkflowRunError(
                "run-ambiguous", f"{len(newest)} runs tie for newest journal mtime: {tied}"
            )
        chosen = newest[0]
    else:
        matches = [run for run in runs if run["wf_id"] == run_arg]
        if not matches:
            raise WorkflowRunError(
                "run-not-found", f"no workflow run named {run_arg!r} under {transcripts_dir}"
            )
        chosen = matches[0]
    return {"wf_id": chosen["wf_id"], "session": chosen["session"], "run_dir": chosen["run_dir"]}


# --------------------------------------------------------------------------- #
# journal parsing
# --------------------------------------------------------------------------- #
def read_journal(run_dir: Path) -> dict:
    """Parse `run_dir/journal.jsonl` into an ordered roster:
    `{agent_id: {label, phase, journal_result}}`, `journal_result` being
    `"present"` once a `result` event for that agent is seen, `"absent"`
    otherwise (a started-but-never-resulted agent, reported rather than
    dropped).

    Raises `WorkflowRunError("journal-unreadable", ...)` when any non-blank
    line fails to parse as JSON (a partly corrupt journal would read as a
    smaller roster -- a wrong answer, not a lesser one), and `WorkflowRunError("run-empty", ...)` when
    parsing succeeds but no `started` event names an agent -- the two states
    the CLI reason-code contract distinguishes by name, kept apart here
    rather than collapsed into one generic decode failure.
    """
    path = run_dir / "journal.jsonl"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    records = []
    parse_failures = 0
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            parse_failures += 1
    if parse_failures:
        raise WorkflowRunError(
            "journal-unreadable",
            f"{parse_failures} of {len(lines)} line(s) in {path} failed to parse",
        )

    roster: dict[str, dict] = {}
    for record in records:
        event = record.get("type")
        agent_id = record.get("agentId")
        if event == "started" and agent_id:
            roster[agent_id] = {
                "label": record.get("label"),
                "phase": record.get("phase"),
                "journal_result": "absent",
            }
        elif event == "result" and agent_id in roster:
            roster[agent_id]["journal_result"] = "present"

    if not roster:
        raise WorkflowRunError("run-empty", f"{path} names no agent in its roster")
    return roster


# --------------------------------------------------------------------------- #
# per-agent file paths + generic transcript/JSONL iteration
# --------------------------------------------------------------------------- #
def agent_transcript_path(run_dir: Path, agent_id: str) -> Path:
    return run_dir / f"agent-{agent_id}.jsonl"


def agent_meta_path(run_dir: Path, agent_id: str) -> Path:
    return run_dir / f"agent-{agent_id}.meta.json"


def read_meta(path: Path) -> dict | None:
    """`agent-<id>.meta.json` as a dict, or `None` when absent or malformed
    -- an honest null, never a guessed default."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def iter_transcript_records(path: Path) -> Iterator[dict]:
    """One JSON object per non-blank line of `path`; malformed lines are
    skipped, not raised -- a transcript or WAL file with one corrupted line
    should still yield every other line, exactly like `context_baseline.py`'s
    own record iterator. Yields nothing when `path` does not exist."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def context_tokens(usage: dict) -> int:
    """`context_baseline.py`'s own convention: the sum that stood in for
    "context at this turn" throughout the published baseline."""
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )
