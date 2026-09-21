#!/usr/bin/env python3
"""Per-run cost reader over a Workflow-tool run directory: joins
`journal.jsonl` (the roster) -> `agent-<id>.meta.json` -> `agent-<id>.jsonl`
(the transcript) -> `.ai-state/observations.jsonl` `agent_stop` WAL rows ->
the main-session transcript, all keyed by `agent_id`, never by position or
label. A **measurement instrument**, not a gate: it always exits 0 once a run
is found and read, however its `wal_agreement` verdicts land -- a
cost-reconciliation disagreement is exactly the fact this instrument exists to
surface, not something for it to fail on.

Layout, journal parsing, and transcript/JSONL access are shared with
`check_lens_isolation.py` through the sibling module `_workflow_run.py`; this
file owns only the cost-specific join and the report shape below.

Report envelope:
    {
      "wf_id": str,
      "agents": [<cost-report row>, ...],      # kind == "workflow-agent"
      "unobserved": [<cost-report row>, ...],   # kind == "unobserved-helper"
      "orchestrator": {launch_turn_tokens, next_turn_tokens, delta, return_bytes},
    }

Cost-report row (the full key set, exact):
    agent_id, kind, label, phase, agent_type, model, peak_context_tokens,
    output_tokens, turns, tool_uses, duration_ms, transcript, journal_result,
    wal, wal_agreement

Two layers, mirroring `context_baseline.py`'s split:

    load(...)    -> dict   all I/O -- resolves the run, reads the journal,
                            joins transcripts/meta/WAL/main-transcript
    compute(...) -> dict   pure join of `load()`'s raw materials into the
                            report envelope above

An `unobserved-helper` row (dec-370's harness-helper class, A12) is a WAL
`agent_stop` whose `agent_id` the journal roster never names -- reported in
its own section, never merged into `agents`, so a cost total built from
`agents` alone is never silently inflated by a row the run itself didn't spawn.

Any field that cannot be derived is `null`, never a plausible default --
`capture_session.py`'s own stance ("an honest empty beats a plausible wrong
number").

Run: `python3 scripts/workflow_run_cost.py --run <wf_id|latest>
[--project-root DIR] [--session PATH] [--json] [--table]`
`python3 scripts/workflow_run_cost.py --list [--project-root DIR] [--json]`
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import _workflow_run as wr
from _repo_root import git_toplevel_from_cwd


# --------------------------------------------------------------------------- #
# I/O layer
# --------------------------------------------------------------------------- #
def load(
    project_root: Path,
    transcripts_dir: Path,
    *,
    run_arg: str,
    session_override: str | None,
) -> dict:
    """Resolve one run and read every file its cost report joins against.

    Impure: the only function in this module that touches the filesystem.
    Raises `wr.WorkflowRunError` for any of the five named failure classes
    (`run-not-found`, `run-ambiguous`, `journal-unreadable`, `run-empty`,
    `transcripts-missing`) -- a silent zero-agent report is the one failure
    mode a measurement instrument must not have.
    """
    resolved = wr.resolve_run(transcripts_dir, run_arg)
    run_dir = resolved["run_dir"]
    roster = wr.read_journal(run_dir)

    transcripts = {
        agent_id: _transcript_stats(wr.agent_transcript_path(run_dir, agent_id))
        for agent_id in roster
    }
    if roster and all(stats is None for stats in transcripts.values()):
        raise wr.WorkflowRunError(
            "transcripts-missing",
            f"none of {len(roster)} rostered agents has a transcript on disk under {run_dir}",
        )

    meta = {agent_id: wr.read_meta(wr.agent_meta_path(run_dir, agent_id)) for agent_id in roster}
    wal_rows = _read_wal(project_root / ".ai-state" / "observations.jsonl")
    unobserved_ids = sorted(set(wal_rows) - set(roster))
    unobserved_transcripts = {
        agent_id: _transcript_stats(wr.agent_transcript_path(run_dir, agent_id))
        for agent_id in unobserved_ids
    }

    if session_override:
        main_path = Path(session_override)
    else:
        main_path = wr.main_transcript_path(transcripts_dir, wr.session_from_run_dir(run_dir))

    return {
        "wf_id": resolved["wf_id"],
        "roster": roster,
        "transcripts": transcripts,
        "meta": meta,
        "wal_rows": wal_rows,
        "unobserved_ids": unobserved_ids,
        "unobserved_transcripts": unobserved_transcripts,
        "orchestrator": _orchestrator_stats(main_path),
    }


def _transcript_stats(path: Path) -> dict | None:
    """One pass over an agent transcript: model (first assistant turn's),
    peak context tokens, summed output tokens, turn/tool-use counts. `None`
    when the file has no assistant turn with usage -- covers both "the file
    does not exist" and "the file exists but is empty"."""
    model = None
    peak_context_tokens = 0
    output_tokens = 0
    turns = 0
    tool_uses = 0
    for record in wr.iter_transcript_records(path):
        if record.get("type") != "assistant":
            continue
        message = record.get("message") or {}
        usage = message.get("usage") or {}
        if not usage:
            continue
        turns += 1
        if model is None:
            model = message.get("model")
        peak_context_tokens = max(peak_context_tokens, wr.context_tokens(usage))
        output_tokens += usage.get("output_tokens", 0)
        content = message.get("content")
        if isinstance(content, list):
            tool_uses += sum(
                1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
            )

    if turns == 0:
        return None
    return {
        "model": model,
        "peak_context_tokens": peak_context_tokens,
        "output_tokens": output_tokens,
        "turns": turns,
        "tool_uses": tool_uses,
        "path": path,
    }


def _read_wal(wal_path: Path) -> dict[str, dict]:
    """`agent_id -> {tokens_in, tokens_out, cache_read, cache_create, model,
    duration_ms, usage_source}` from `agent_stop` WAL rows. The last row for
    a given `agent_id` wins when several exist."""
    rows: dict[str, dict] = {}
    for record in wr.iter_transcript_records(wal_path):
        if record.get("event_type") != "agent_stop":
            continue
        agent_id = record.get("agent_id")
        if not agent_id:
            continue
        rows[agent_id] = {
            "tokens_in": record.get("tokens_in"),
            "tokens_out": record.get("tokens_out"),
            "cache_read": record.get("cache_read"),
            "cache_create": record.get("cache_create"),
            "model": record.get("model"),
            "duration_ms": record.get("duration_ms"),
            "usage_source": record.get("usage_source"),
        }
    return rows


def _orchestrator_stats(main_path: Path) -> dict:
    """The main-session context at the `Workflow` launch turn and at the next
    assistant turn (S1): find the first assistant record whose content carries
    a `tool_use` block named `"Workflow"`, record its context tokens, then the
    same for the next assistant turn with usage after it. `return_bytes` looks
    for a `tool_result` block answering that same `tool_use` id between the
    two turns. Every field is `null` when the main transcript is missing or
    carries no such turn -- not a run-level failure, since I3/I4 name no
    reason code for it (A10's escape hatch, `--session`, is the recovery)."""
    records = list(wr.iter_transcript_records(main_path))

    launch_idx = None
    launch_tokens = None
    launch_tool_id = None
    for i, record in enumerate(records):
        block = _workflow_tool_use_block(record)
        if block is None:
            continue
        usage = (record.get("message") or {}).get("usage") or {}
        launch_idx, launch_tokens, launch_tool_id = i, wr.context_tokens(usage), block.get("id")
        break

    if launch_idx is None:
        return {
            "launch_turn_tokens": None,
            "next_turn_tokens": None,
            "delta": None,
            "return_bytes": None,
        }

    next_tokens = None
    return_bytes = None
    for record in records[launch_idx + 1 :]:
        if return_bytes is None:
            return_bytes = _tool_result_bytes(record, launch_tool_id)
        if next_tokens is None and record.get("type") == "assistant":
            usage = (record.get("message") or {}).get("usage") or {}
            if usage:
                next_tokens = wr.context_tokens(usage)
        if next_tokens is not None and return_bytes is not None:
            break

    delta = next_tokens - launch_tokens if next_tokens is not None else None
    return {
        "launch_turn_tokens": launch_tokens,
        "next_turn_tokens": next_tokens,
        "delta": delta,
        "return_bytes": return_bytes,
    }


def _workflow_tool_use_block(record: dict) -> dict | None:
    if record.get("type") != "assistant":
        return None
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, list):
        return None
    return next(
        (
            b
            for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Workflow"
        ),
        None,
    )


def _tool_result_bytes(record: dict, tool_use_id: str | None) -> int | None:
    if tool_use_id is None or record.get("type") != "user":
        return None
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_result"
            and block.get("tool_use_id") == tool_use_id
        ):
            return len(json.dumps(block.get("content")).encode("utf-8"))
    return None


# --------------------------------------------------------------------------- #
# pure join (fixture-testable without touching the filesystem)
# --------------------------------------------------------------------------- #
def compute(loaded: dict) -> dict:
    """Join `load()`'s raw materials into the report envelope. Pure: every
    input is a value already in memory."""
    agents = [
        _build_row(
            agent_id,
            label=entry["label"],
            phase=entry["phase"],
            journal_result=entry["journal_result"],
            transcript_stats=loaded["transcripts"][agent_id],
            meta=loaded["meta"].get(agent_id),
            wal_row=loaded["wal_rows"].get(agent_id),
            kind="workflow-agent",
        )
        for agent_id, entry in loaded["roster"].items()
    ]
    unobserved = [
        _build_row(
            agent_id,
            label=None,
            phase=None,
            journal_result=None,
            transcript_stats=loaded["unobserved_transcripts"].get(agent_id),
            meta=None,
            wal_row=loaded["wal_rows"].get(agent_id),
            kind="unobserved-helper",
        )
        for agent_id in loaded["unobserved_ids"]
    ]
    return {
        "wf_id": loaded["wf_id"],
        "agents": agents,
        "unobserved": unobserved,
        "orchestrator": loaded["orchestrator"],
    }


def _ts_field(transcript_stats: dict | None, key: str):
    """One `transcript_stats` field, or `None` when the agent has no
    transcript -- the one ternary `_build_row` would otherwise repeat once
    per field."""
    return transcript_stats[key] if transcript_stats else None


def _build_row(
    agent_id, *, label, phase, journal_result, transcript_stats, meta, wal_row, kind
) -> dict:
    return {
        "agent_id": agent_id,
        "kind": kind,
        "label": label,
        "phase": phase,
        "agent_type": (meta or {}).get("agentType"),
        "model": _ts_field(transcript_stats, "model"),
        "peak_context_tokens": _ts_field(transcript_stats, "peak_context_tokens"),
        "output_tokens": _ts_field(transcript_stats, "output_tokens"),
        "turns": _ts_field(transcript_stats, "turns"),
        "tool_uses": _ts_field(transcript_stats, "tool_uses"),
        "duration_ms": wal_row.get("duration_ms") if wal_row else None,
        "transcript": str(transcript_stats["path"]) if transcript_stats else None,
        "journal_result": journal_result,
        "wal": dict(wal_row) if wal_row else None,
        "wal_agreement": _wal_agreement(transcript_stats, wal_row),
    }


def _wal_agreement(transcript_stats: dict | None, wal_row: dict | None) -> str:
    """The observable verdict this suite pins: a missing transcript always
    wins over a missing WAL row (there is nothing to compare either way, but
    "no transcript" is the harder gap), then a missing WAL row, then a
    straight comparison on `tokens_out` vs. the transcript's summed
    `output_tokens` -- the one field the tests exercise disagreement on."""
    if transcript_stats is None:
        return "transcript-missing"
    if wal_row is None:
        return "wal-missing"
    if wal_row.get("tokens_out") != transcript_stats["output_tokens"]:
        return "differ"
    return "agree"


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _iso(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _disp(value) -> str:
    """`value`, or `-` for the honest nulls a table row may carry."""
    return "-" if value is None else str(value)


def render_table(report: dict) -> str:
    lines = [
        f"wf_id={report['wf_id']}  agents={len(report['agents'])}  "
        f"unobserved={len(report['unobserved'])}",
        "",
        f"{'label':16} {'phase':10} {'model':20} {'peak_ctx':>10} {'out_tok':>8} "
        f"{'turns':>6} {'wal_agreement':16}",
    ]
    for row in report["agents"]:
        lines.append(
            f"{(row['label'] or '?'):16} {(row['phase'] or '?'):10} {(row['model'] or '?'):20} "
            f"{_disp(row['peak_context_tokens']):>10} {_disp(row['output_tokens']):>8} "
            f"{_disp(row['turns']):>6} {row['wal_agreement']:16}"
        )
    orch = report["orchestrator"]
    lines += [
        "",
        f"orchestrator: launch={orch['launch_turn_tokens']} next={orch['next_turn_tokens']} "
        f"delta={orch['delta']}",
    ]
    return "\n".join(lines)


def render_list_table(payload: list[dict]) -> str:
    lines = [f"{'wf_id':24} launched_at"]
    lines += [f"{run['wf_id']:24} {run['launched_at']}" for run in payload]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-run cost reader over a Workflow-tool run directory (measurement only, never gates)."
    )
    parser.add_argument("--run", default=None, help="Workflow run id, or 'latest'.")
    parser.add_argument(
        "--list", action="store_true", help="Enumerate known runs with their launch timestamps."
    )
    parser.add_argument(
        "--project-root", default=None, help="Project root; defaults to git toplevel of CWD."
    )
    parser.add_argument(
        "--session", default=None, help="Main-session transcript path override (A10 escape hatch)."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--table", action="store_true", help="Emit the report as a table (default)."
    )
    args = parser.parse_args(argv)

    project_root = (
        Path(args.project_root).resolve() if args.project_root else git_toplevel_from_cwd()
    )
    if project_root is None:
        print("error: not inside a git worktree and no --project-root given", file=sys.stderr)
        return 2
    transcripts_dir = wr.transcripts_dir(project_root)

    if args.list:
        runs = wr.list_runs(transcripts_dir)
        payload = [{"wf_id": run["wf_id"], "launched_at": _iso(run["mtime"])} for run in runs]
        print(json.dumps(payload, indent=2) if args.json else render_list_table(payload))
        return 0

    if not args.run:
        print("error: --run <wf_id|latest> or --list is required", file=sys.stderr)
        return 2

    try:
        loaded = load(
            project_root, transcripts_dir, run_arg=args.run, session_override=args.session
        )
    except wr.WorkflowRunError as exc:
        print(f"error: {exc.reason}: {exc}", file=sys.stderr)
        return 2

    report = compute(loaded)
    print(json.dumps(report, indent=2) if args.json else render_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
