#!/usr/bin/env python3
"""Per-slug spawn/resume tally with a budget verdict, read from the observations WAL.

The orchestrator consults this before each agent spawn -- a miscount is a silent budget
breach, so this never reports a false "0 spawns, within budget": an absent WAL, an
unrecognised slug, or a plugin-cache repo root all withhold (exit 2) rather than guess.

Functional core (`tally`, `classify_resume`, `verdict`) is pure over already-parsed
data; the WAL, transcript directory, and argv live in the I/O-shell/CLI section below.

Counting model: a spawn is the FIRST `agent_start` row for a given `agent_id`; every
later `agent_start` for the same id is a resume (a SendMessage resume reuses the
agent_id). `agent_stop`/`tool_use` rows never contribute. Each resume is classified
against the resuming agent's own subagent transcript (globbed on the session UUID,
since this CLI is never handed the hashed project-dir name Claude Code uses): `heavy`
when the last assistant turn at/before the resume timestamp carries
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens` at or above
`--heavy-context` (default 250,000), `light` below it, `unsized` when unknown.

Budget verdict: a tally whose resumes are ALL resolved contributes its spawn to the
definite `charged` count, plus every heavy resume. A tally with >=1 unsized resume
instead folds its WHOLE contribution into the pending `unsized` pool -- partitioning
definite-vs-pending by agent (not by resume event) is what lets the borderline check
express "could still turn out over" without tracking which agents span both buckets.
`within` needs `charged <= budget` AND `charged + unsized <= budget`; `over` is
`charged > budget`; `indeterminate` is the remainder; `no-budget` when `--budget` is
omitted. Exit 0 for within/indeterminate/no-budget, 1 for over, 2 for withheld
(`wal-absent`, `slug-unseen`, `plugin-cache-root`).
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

# Default resume-classification boundary (input + cache-read + cache-creation tokens).
HEAVY_CONTEXT_DEFAULT = 250_000

WAL_FILENAMES = ("observations.jsonl.1", "observations.jsonl")  # rotation order


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
    """One agent_id's spawn plus every later resume, in WAL order."""

    agent_id: str
    agent_type: str
    spawned_at: str
    resumes: tuple[Resume, ...]


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
    """Group `agent_start` rows by `agent_id`: first start is a spawn, rest are resumes.

    Ignores every other event_type and any row missing an agent_id. Deliberately does
    not filter by `project` -- scoping to one slug is the I/O shell's job, upstream.
    """
    order: list[str] = []
    spawn_rows: dict[str, dict] = {}
    resume_lists: dict[str, list[Resume]] = {}

    for row in rows:
        if not isinstance(row, dict) or row.get("event_type") != "agent_start":
            continue
        agent_id = row.get("agent_id")
        if not agent_id:
            continue
        if agent_id not in spawn_rows:
            spawn_rows[agent_id] = row
            resume_lists[agent_id] = []
            order.append(agent_id)
        else:
            resume_lists[agent_id].append(
                Resume(
                    at=str(row.get("timestamp") or ""),
                    context_tokens=None,
                    session_id=str(row.get("session_id") or ""),
                )
            )

    return tuple(
        AgentTally(
            agent_id=agent_id,
            agent_type=str(spawn_rows[agent_id].get("agent_type") or ""),
            spawned_at=str(spawn_rows[agent_id].get("timestamp") or ""),
            resumes=tuple(resume_lists[agent_id]),
        )
        for agent_id in order
    )


def classify_resume(context_tokens: int | None, threshold: int) -> str:
    """`heavy` at or above `threshold`, `light` below it, `unsized` when unknown."""
    if context_tokens is None:
        return "unsized"
    return "heavy" if context_tokens >= threshold else "light"


def verdict(tallies: tuple[AgentTally, ...], budget: int | None, threshold: int) -> Verdict:
    """Compute the budget verdict for `tallies` at `threshold` against `budget`."""
    resumes_light = resumes_heavy = resumes_unsized = 0
    definite_spawns = 0
    for agent_tally in tallies:
        tally_has_unsized = False
        for resume in agent_tally.resumes:
            classification = classify_resume(resume.context_tokens, threshold)
            if classification == "heavy":
                resumes_heavy += 1
            elif classification == "light":
                resumes_light += 1
            else:
                resumes_unsized += 1
                tally_has_unsized = True
        if not tally_has_unsized:
            definite_spawns += 1

    charged = definite_spawns + resumes_heavy
    if budget is None:
        label = "no-budget"
    elif charged > budget:
        label = "over"
    elif charged + resumes_unsized > budget:
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


def _read_wal_rows(repo_root: Path) -> tuple[list[Path], list[dict], int]:
    """Read `.ai-state/observations.jsonl.1` then `.ai-state/observations.jsonl`.

    Returns (files_that_existed, parsed_rows, rows_skipped). A missing file is
    silently skipped -- withholding on a totally absent WAL is the caller's job. A
    malformed/non-dict line is skipped and counted, never treated as a reason to
    zero the whole run.
    """
    state_dir = repo_root / ".ai-state"
    existing: list[Path] = []
    rows: list[dict] = []
    skipped = 0
    for name in WAL_FILENAMES:
        candidate = state_dir / name
        if not candidate.exists():
            continue
        existing.append(candidate)
        try:
            raw_lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in raw_lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                skipped += 1
                continue
            if isinstance(row, dict):
                rows.append(row)
            else:
                skipped += 1
    return existing, rows, skipped


def _lookup_transcript_context(
    projects_dir: Path, session_id: str, agent_id: str, before_ts: str
) -> int | None:
    """Token size at the last assistant turn at/before `before_ts`, or None.

    Globs `<projects_dir>/*/<session_id>/subagents/agent-<agent_id>.jsonl` -- the
    leading project-dir component is unknown here (only the session UUID is).
    """
    if not session_id:
        return None
    try:
        matches = sorted(projects_dir.glob(f"*/{session_id}/subagents/agent-{agent_id}.jsonl"))
    except OSError:
        return None
    if not matches:
        return None
    try:
        lines = matches[0].read_text(encoding="utf-8").splitlines()
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


def _build_envelope(
    slug: str,
    sources: list[Path],
    repo_root: Path,
    rows_skipped: int,
    tallies: tuple[AgentTally, ...],
    result: Verdict,
    threshold: int,
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
    return {
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


def _format_human(envelope: dict) -> str:
    lines = [
        f"spawn_count: slug={envelope['slug']!r} verdict={envelope['verdict']}",
        f"  spawns={envelope['spawns']} charged={envelope['charged']} budget={envelope['budget']}",
        f"  resumes: light={envelope['resumes']['light']} "
        f"heavy={envelope['resumes']['heavy']} unsized={envelope['resumes']['unsized']}",
        f"  sources={envelope['sources']} rows_skipped={envelope['rows_skipped']}",
    ]
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
    parser.add_argument("--slug", required=True, help="Pipeline slug (WAL `project` field).")
    parser.add_argument("--repo-root", default=None, help="Default: discovered via git.")
    parser.add_argument("--budget", type=int, default=None, help="Spawn budget; omit to skip.")
    parser.add_argument("--heavy-context", type=int, default=HEAVY_CONTEXT_DEFAULT)
    parser.add_argument("--projects-dir", default=None, help="Default: ~/.claude/projects.")
    parser.add_argument("--no-context", action="store_true", help="Every resume reads unsized.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        _fail("plugin-cache-root", f"refusing to operate on a plugin-cache path: {repo_root}")
        return 2
    sources, all_rows, rows_skipped = _read_wal_rows(repo_root)
    if not sources:
        _fail("wal-absent", f"no .ai-state/observations.jsonl[.1] found under {repo_root}.")
        return 2
    projects_seen = sorted({row.get("project") for row in all_rows if row.get("project")})
    if args.slug not in projects_seen:
        seen = ", ".join(projects_seen) if projects_seen else "(none)"
        _fail("slug-unseen", f"slug {args.slug!r} not seen in the WAL. Projects observed: {seen}.")
        return 2

    scoped_rows = [row for row in all_rows if row.get("project") == args.slug]
    tallies = tally(scoped_rows)
    if not args.no_context:
        projects_dir = (
            Path(args.projects_dir) if args.projects_dir else Path.home() / ".claude" / "projects"
        )
        tallies = tuple(resolve_resume_context(t, projects_dir) for t in tallies)
    result = verdict(tallies, args.budget, args.heavy_context)
    envelope = _build_envelope(
        args.slug, sources, repo_root, rows_skipped, tallies, result, args.heavy_context
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
