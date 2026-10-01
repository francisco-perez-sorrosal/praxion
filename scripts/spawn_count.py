#!/usr/bin/env python3
"""Per-slug spawn/resume tally with a budget verdict, read from the observations WAL.

The orchestrator consults this before each agent spawn -- a miscount is a silent budget
breach, so this never reports a false "0 spawns, within budget": an absent WAL, an
unrecognised slug, or a plugin-cache repo root all withhold (exit 2) rather than guess.

Functional core (`tally`, `classify_resume`, `verdict`) is pure over already-parsed
data; the WAL, transcript directory, and argv live in the I/O-shell/CLI section below.

Counting model: a spawn is an `agent_id` first recorded by an `agent_start` row or by a
spawn-result `tool_use` row (`spawned_agent_id`, the `Agent` call's result); every later
`agent_start` for the same id is a resume (a SendMessage resume reuses the agent_id).
Other `agent_stop`/`tool_use` rows never contribute.

Attribution: each agent counts toward exactly one slug, its owner, decided by the first
rule that applies. (1) Its first `agent_start` lacks `slug_attribution` (a row written
before spawns were attributed by prompt): the row's `project`. (2) A spawn-result row
names it: that row's `task_slug` (the slug the spawn's prompt stated), or its `project`
when the prompt stated none. (3) At read time, its own transcript's first user message
(skipped under `--no-context`): the slug that message states, or the start row's `project`
when it states none. (4) Otherwise it is unattributed, and counts toward no slug. A
transcript is evidence only for as long as it exists; nothing is written back. A resume
follows its spawn's owner. A slug is seen when some row's `project` names it or
some agent's owner is it; a resume's message or an unattributed spawn never makes one seen.

Each resume is classified against the resuming agent's own subagent transcript (globbed
on the session UUID, since this CLI is never handed the hashed project-dir name Claude
Code uses): `heavy` when the last assistant turn at/before the resume timestamp carries
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens` at or above
`--heavy-context` (default 250,000), `light` below it, `unsized` when unknown.

Budget verdict: `charged` is every attributed spawn (definite) plus every heavy resume;
unsized resumes and every unattributed spawn in the log form the pending pool, each of
which could still turn out to be charged to this slug. `within` needs
`charged + unsized + unattributed <= budget`; `over` is `charged > budget`;
`indeterminate` is the remainder; `no-budget` when `--budget` is omitted. Exit 0 for
within/indeterminate/no-budget, 1 for over, 2 for withheld (`wal-absent`, `slug-unseen`,
`plugin-cache-root`).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent

# hooks/_observation_log is a sibling package to this file's own scripts/
# directory -- both live one level under the repo root.
sys.path.insert(0, str(SCRIPT_DIR.parent / "hooks"))
from _hook_utils import stated_task_slug  # noqa: E402 (after sys.path injection)
from _observation_log import reader  # noqa: E402 (after sys.path injection)

# Default resume-classification boundary (input + cache-read + cache-creation tokens).
HEAVY_CONTEXT_DEFAULT = 250_000

# Where an agent's own transcript lives under `<projects_dir>/*/<session_id>/`: directly
# under `subagents/`, or under a Workflow run's directory beneath it.
_TRANSCRIPT_LAYOUTS = ("subagents", "subagents/workflows/*")


# -- Pure core ------------------------------------------------------------------------


@dataclass(frozen=True)
class Resume:
    """One later `agent_start` row for an already-spawned agent_id.

    `session_id` defaults to "" so a Resume can be constructed without knowing about
    transcript lookup -- `tally()` fills it from the raw row; `resolve_resume_context`
    (I/O shell) is the only consumer.
    """

    at: str
    context_tokens: int | None
    session_id: str = ""


@dataclass(frozen=True)
class AgentTally:
    """One agent_id's spawn plus every later resume, in WAL order.

    `owner` is the slug the agent counts toward; `None` means unattributed and has no
    other meaning. `session_id` and `project` come from the spawn's first record.
    """

    agent_id: str
    agent_type: str
    spawned_at: str
    resumes: tuple[Resume, ...]
    owner: str | None = None
    session_id: str = ""
    project: str = ""


@dataclass(frozen=True)
class Verdict:
    """The budget-relevant summary of a set of tallies at a given threshold/budget."""

    label: str  # "within" | "over" | "indeterminate" | "no-budget"
    spawns: int
    charged: int
    resumes_light: int
    resumes_heavy: int
    resumes_unsized: int
    budget: int | None


def tally(rows: list[dict]) -> tuple[AgentTally, ...]:
    """Group the rows naming a spawned agent by `agent_id`, in order of first record.

    The first `agent_start` is the spawn and every later one a resume; a spawn-result
    `tool_use` row also witnesses the spawn, so an agent whose start was never delivered
    still counts once. Ignores every other row. Deliberately does not filter by slug --
    scoping to the owner is the I/O shell's job, upstream.
    """
    order: dict[str, None] = {}
    starts: dict[str, list[dict]] = {}
    results: dict[str, dict] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("event_type") == "agent_start":
            agent_id = row.get("agent_id")
            if agent_id:
                order.setdefault(agent_id)
                starts.setdefault(agent_id, []).append(row)
        elif row.get("event_type") == "tool_use":
            agent_id = row.get("spawned_agent_id")
            if agent_id and isinstance(agent_id, str):
                order.setdefault(agent_id)
                results.setdefault(agent_id, row)

    return tuple(
        _agent_tally(agent_id, starts.get(agent_id, []), results.get(agent_id))
        for agent_id in order
    )


def _agent_tally(agent_id: str, starts: list[dict], result: dict | None) -> AgentTally:
    spawn_row = starts[0] if starts else (result or {})
    return AgentTally(
        agent_id=agent_id,
        agent_type=str(spawn_row.get("agent_type" if starts else "spawned_agent_type") or ""),
        spawned_at=str(spawn_row.get("timestamp") or ""),
        resumes=tuple(
            Resume(
                at=str(row.get("timestamp") or ""),
                context_tokens=None,
                session_id=str(row.get("session_id") or ""),
            )
            for row in starts[1:]
        ),
        owner=_row_owner(starts[0] if starts else None, result),
        session_id=str(spawn_row.get("session_id") or ""),
        project=str(spawn_row.get("project") or ""),
    )


def _row_owner(first_start: dict | None, result: dict | None) -> str | None:
    """The slug the logged rows attribute an agent to, or `None` when they do not."""
    if first_start is not None and not first_start.get("slug_attribution"):
        return first_start.get("project") or None
    if result is not None:
        return result.get("task_slug") or result.get("project") or None
    return None


def seen_slugs(rows: list[dict], tallies: tuple[AgentTally, ...]) -> set[str]:
    """Every slug the log can speak for: any row's `project`, plus every agent's owner."""
    projects = {row["project"] for row in rows if isinstance(row, dict) and row.get("project")}
    return projects | {t.owner for t in tallies if t.owner is not None}


def classify_resume(context_tokens: int | None, threshold: int) -> str:
    """`heavy` at or above `threshold`, `light` below it, `unsized` when unknown."""
    if context_tokens is None:
        return "unsized"
    return "heavy" if context_tokens >= threshold else "light"


def verdict(
    tallies: tuple[AgentTally, ...],
    budget: int | None,
    threshold: int,
    pending_spawns: int = 0,
) -> Verdict:
    """Compute the budget verdict for `tallies` at `threshold` against `budget`.

    `pending_spawns` is every spawn in the log not yet attributed to any slug: each could
    still turn out to belong to these `tallies`, so it holds the verdict like an unsized resume.
    """
    classifications = [
        classify_resume(resume.context_tokens, threshold)
        for agent_tally in tallies
        for resume in agent_tally.resumes
    ]
    resumes_light = classifications.count("light")
    resumes_heavy = classifications.count("heavy")
    resumes_unsized = classifications.count("unsized")

    # Every attributed spawn is definite; an unsized resume or an unattributed spawn is not.
    charged = len(tallies) + resumes_heavy
    if budget is None:
        label = "no-budget"
    elif charged > budget:
        label = "over"
    elif charged + resumes_unsized + pending_spawns > budget:
        label = "indeterminate"
    else:
        label = "within"

    return Verdict(
        label=label,
        spawns=len(tallies),
        charged=charged,
        resumes_light=resumes_light,
        resumes_heavy=resumes_heavy,
        resumes_unsized=resumes_unsized,
        budget=budget,
    )


# -- I/O shell ---------------------------------------------------------------------------


class _WalUnreadableError(Exception):
    """A log segment exists but could not be read (permissions, I/O)."""


def _read_wal_rows(repo_root: Path) -> tuple[list[Path], list[dict], int]:
    """Read the rotated archive segment then the active observation log.

    Returns (files_that_existed, parsed_rows, rows_skipped). A missing file is
    silently skipped -- withholding on a totally absent WAL is the caller's job. A
    malformed/non-dict line is skipped and counted, never treated as a reason to
    zero the whole run. A segment that exists but cannot be read raises
    `_WalUnreadableError`: counting spawns over a partial log would under-report
    the budget, so the caller withholds instead.
    """
    state_dir = repo_root / ".ai-state"
    existing = list(reader.segments(state_dir, archives=True))
    rows: list[dict] = []
    skipped = 0
    for path in existing:
        segment = reader.read_segment(path)
        if segment.error is not None:
            raise _WalUnreadableError(f"{path}: {segment.error}")
        rows.extend(segment.rows)
        skipped += len(segment.malformed_lines)
    return existing, rows, skipped


def _find_agent_transcript(projects_dir: Path, session_id: str, agent_id: str) -> Path | None:
    """The agent's own transcript, or None.

    Globs `<projects_dir>/*/<session_id>/<layout>/agent-<agent_id>.jsonl` -- the leading
    project-dir component is unknown here (only the session UUID is).
    """
    if not session_id:
        return None
    try:
        for layout in _TRANSCRIPT_LAYOUTS:
            matches = sorted(projects_dir.glob(f"*/{session_id}/{layout}/agent-{agent_id}.jsonl"))
            if matches:
                return matches[0]
    except OSError:
        return None
    return None


def _lookup_transcript_context(
    projects_dir: Path, session_id: str, agent_id: str, before_ts: str
) -> int | None:
    """Token size at the last assistant turn at/before `before_ts`, or None."""
    transcript = _find_agent_transcript(projects_dir, session_id, agent_id)
    if transcript is None:
        return None
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    best_ts, best_usage = "", None
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if row.get("type") != "assistant" or row.get("agentId") != agent_id:
            continue
        ts = str(row.get("timestamp") or "")
        if before_ts and ts > before_ts:
            continue
        if ts >= best_ts:
            best_ts = ts
            best_usage = row.get("message", {}).get("usage", {})
    if best_usage is None:
        return None
    return (
        int(best_usage.get("input_tokens", 0) or 0)
        + int(best_usage.get("cache_read_input_tokens", 0) or 0)
        + int(best_usage.get("cache_creation_input_tokens", 0) or 0)
    )


def resolve_resume_context(agent_tally: AgentTally, projects_dir: Path) -> AgentTally:
    """Return a new AgentTally with every Resume's context_tokens filled in."""
    resolved = tuple(
        replace(
            resume,
            context_tokens=_lookup_transcript_context(
                projects_dir, resume.session_id, agent_tally.agent_id, resume.at
            ),
        )
        for resume in agent_tally.resumes
    )
    return replace(agent_tally, resumes=resolved)


def _message_text(row: dict) -> str | None:
    """The text of a transcript `user` row: a plain string, or its text blocks joined."""
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return "\n".join(blocks) if blocks else None
    return None


def _first_user_text(transcript: Path) -> str | None:
    """The text of the transcript's first `user` message, or None when unreadable or not text."""
    try:
        with transcript.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("type") == "user":
                    return _message_text(row)
    except (OSError, UnicodeDecodeError):
        return None
    return None


def resolve_owner(agent_tally: AgentTally, projects_dir: Path) -> AgentTally:
    """Attribute an unattributed agent from its own transcript; leave an attributed one alone.

    The owner is the slug the transcript's first user message states, else the spawn's
    `project`. No readable prompt leaves the agent unattributed.
    """
    if agent_tally.owner is not None:
        return agent_tally
    transcript = _find_agent_transcript(projects_dir, agent_tally.session_id, agent_tally.agent_id)
    if transcript is None:
        return agent_tally
    prompt = _first_user_text(transcript)
    if prompt is None:
        return agent_tally
    owner = stated_task_slug(prompt) or agent_tally.project or None
    return replace(agent_tally, owner=owner)


def _build_envelope(
    slug: str,
    sources: list[Path],
    repo_root: Path,
    rows_skipped: int,
    tallies: tuple[AgentTally, ...],
    result: Verdict,
    threshold: int,
    unattributed: tuple[AgentTally, ...] = (),
) -> dict:
    by_agent_type: dict[str, int] = {}
    agents: list[dict] = []
    for agent_tally in tallies:
        by_agent_type[agent_tally.agent_type] = by_agent_type.get(agent_tally.agent_type, 0) + 1
        agents.append(
            {
                "agent_id": agent_tally.agent_id,
                "agent_type": agent_tally.agent_type,
                "spawned_at": agent_tally.spawned_at,
                "resumes": [
                    {
                        "at": resume.at,
                        "context_tokens": resume.context_tokens,
                        "class": classify_resume(resume.context_tokens, threshold),
                    }
                    for resume in agent_tally.resumes
                ],
            }
        )

    # sources are always built as repo_root / ".ai-state" / <name> -- relative_to never fails.
    envelope = {
        "slug": slug,
        "sources": [str(p.relative_to(repo_root)) for p in sources],
        "rows_skipped": rows_skipped,
        "spawns": result.spawns,
        "resumes": {
            "light": result.resumes_light,
            "heavy": result.resumes_heavy,
            "unsized": result.resumes_unsized,
        },
        "charged": result.charged,
        "budget": result.budget,
        "verdict": result.label,
        "by_agent_type": by_agent_type,
        "agents": agents,
    }
    # Only present when non-empty, so a log of rows written before attribution reports
    # byte-for-byte what it always did.
    if unattributed:
        envelope["unattributed"] = [
            {
                "agent_id": t.agent_id,
                "agent_type": t.agent_type,
                "spawned_at": t.spawned_at,
            }
            for t in unattributed
        ]
    return envelope


def _format_human(envelope: dict) -> str:
    lines = [
        f"spawn_count: slug={envelope['slug']!r} verdict={envelope['verdict']}",
        f"  spawns={envelope['spawns']} charged={envelope['charged']} budget={envelope['budget']}",
        f"  resumes: light={envelope['resumes']['light']} "
        f"heavy={envelope['resumes']['heavy']} unsized={envelope['resumes']['unsized']}",
        f"  sources={envelope['sources']} rows_skipped={envelope['rows_skipped']}",
    ]
    if "unattributed" in envelope:
        lines.append(f"  unattributed={len(envelope['unattributed'])}")
    return "\n".join(lines)


def _fail(reason: str, message: str) -> None:
    print(f"{reason}: {message}", file=sys.stderr)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="spawn_count",
        description=(
            "Count agent spawns/resumes for a pipeline slug from the observations WAL "
            "and report a budget verdict -- consult before each spawn."
        ),
    )
    parser.add_argument(
        "--slug", required=True, help="Pipeline slug: the `Task slug:` a spawn's prompt states."
    )
    parser.add_argument("--repo-root", default=None, help="Default: discovered via git.")
    parser.add_argument("--budget", type=int, default=None, help="Spawn budget; omit to skip.")
    parser.add_argument("--heavy-context", type=int, default=HEAVY_CONTEXT_DEFAULT)
    parser.add_argument("--projects-dir", default=None, help="Default: ~/.claude/projects.")
    parser.add_argument("--no-context", action="store_true", help="Every resume reads unsized.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _projects_dir(args: argparse.Namespace) -> Path | None:
    """Where transcripts are read from; None when `--no-context` says to read none."""
    if args.no_context:
        return None
    return Path(args.projects_dir) if args.projects_dir else Path.home() / ".claude" / "projects"


def _unseen_message(slug: str, seen: set[str]) -> str:
    return (
        f"slug {slug!r} not seen in the WAL. Slugs seen: {', '.join(sorted(seen)) or '(none)'}. "
        "A slug is seen when some row's project names it or some spawn's prompt states it "
        "(`Task slug: <slug>`); a resume's message and a spawn of unknown attribution never "
        "make one seen."
    )


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        _fail("plugin-cache-root", f"refusing to operate on a plugin-cache path: {repo_root}")
        return 2
    try:
        sources, all_rows, rows_skipped = _read_wal_rows(repo_root)
    except _WalUnreadableError as exc:
        _fail("wal-unreadable", str(exc))
        return 2
    if not sources:
        _fail("wal-absent", f"no observation log found under {repo_root} (checked .ai-state/).")
        return 2
    all_tallies = tally(all_rows)
    projects_dir = _projects_dir(args)
    if projects_dir is not None:
        all_tallies = tuple(resolve_owner(t, projects_dir) for t in all_tallies)
    seen = seen_slugs(all_rows, all_tallies)
    if args.slug not in seen:
        _fail("slug-unseen", _unseen_message(args.slug, seen))
        return 2

    tallies = tuple(t for t in all_tallies if t.owner == args.slug)
    unattributed = tuple(t for t in all_tallies if t.owner is None)
    if projects_dir is not None:
        tallies = tuple(resolve_resume_context(t, projects_dir) for t in tallies)
    result = verdict(tallies, args.budget, args.heavy_context, pending_spawns=len(unattributed))
    envelope = _build_envelope(
        args.slug,
        sources,
        repo_root,
        rows_skipped,
        tallies,
        result,
        args.heavy_context,
        unattributed,
    )
    print(json.dumps(envelope, indent=2) if args.json else _format_human(envelope))
    return 1 if result.label == "over" else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except Exception as exc:  # noqa: BLE001 -- withhold rather than guess on any failure
        _fail("error", str(exc))
        sys.exit(2)
    sys.exit(code)


if __name__ == "__main__":
    main()
