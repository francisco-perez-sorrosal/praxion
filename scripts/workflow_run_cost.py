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
      "window": {start, end} | null,           # the run's transcript wall-clock span
    }

Cost-report row (the full key set, exact):
    agent_id, kind, label, phase, agent_type, model, peak_context_tokens,
    output_tokens, turns, tool_uses, duration_ms, transcript, journal_result,
    wal, wal_agreement -- plus `attribution` on every unobserved-helper row

Two layers, mirroring `context_baseline.py`'s split:

    load(...)    -> dict   all I/O -- resolves the run, reads the journal,
                            joins transcripts/meta/WAL/main-transcript
    compute(...) -> dict   pure join of `load()`'s raw materials into the
                            report envelope above

An `unobserved-helper` row (dec-370's harness-helper class) is a WAL
`agent_stop` whose `agent_id` the journal roster never names and whose
timestamp falls inside the run's transcript window -- co-occurrence, not a
proven parent, which is why every such row carries
`attribution: time-window-heuristic`. Reported in its own section, never
merged into `agents`, so a cost total built from `agents` alone is never
silently inflated by a row the run itself didn't spawn.

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
    window = _run_window(transcripts)
    unobserved_ids = sorted(
        agent_id
        for agent_id, row in wal_rows.items()
        if agent_id not in roster and _within(window, row.get("timestamp"))
    )
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
        "window": window,
        "orchestrator": _orchestrator_stats(main_path, resolved["wf_id"]),
    }


def _transcript_stats(path: Path) -> dict | None:
    """One pass over an agent transcript: model (first assistant turn's),
    peak context tokens, summed output tokens, turn/tool-use counts, and the
    first/last record stamps (the run window's raw material). `None`
    when the file has no assistant turn with usage -- covers both "the file
    does not exist" and "the file exists but is empty"."""
    model = None
    peak_context_tokens = 0
    output_tokens = 0
    turns = 0
    tool_uses = 0
    first_ts = None
    last_ts = None
    for record in wr.iter_transcript_records(path):
        stamp = _parse_ts(record.get("timestamp"))
        if stamp is not None:
            first_ts = stamp if first_ts is None or stamp < first_ts else first_ts
            last_ts = stamp if last_ts is None or stamp > last_ts else last_ts
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
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def _read_wal(wal_path: Path) -> dict[str, dict]:
    """`agent_id -> {tokens_in, tokens_out, cache_read, cache_create, model,
    duration_ms, usage_source, timestamp}` from `agent_stop` WAL rows. The last row for
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
            "timestamp": record.get("timestamp"),
        }
    return rows


def _parse_ts(value) -> datetime | None:
    """An ISO-8601 stamp (`Z` or offset form -- transcripts write the former,
    the WAL the latter) as an aware datetime, or `None`."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _run_window(transcripts: dict[str, dict | None]) -> dict | None:
    """The run's wall-clock span: earliest first stamp to latest last stamp
    across the rostered transcripts, or `None` when none carries a stamp."""
    starts = [s["first_ts"] for s in transcripts.values() if s and s.get("first_ts")]
    ends = [s["last_ts"] for s in transcripts.values() if s and s.get("last_ts")]
    if not starts or not ends:
        return None
    return {"start": min(starts), "end": max(ends)}


def _within(window: dict | None, stamp) -> bool:
    parsed = _parse_ts(stamp)
    return bool(window and parsed and window["start"] <= parsed <= window["end"])


def _window_json(window: dict | None) -> dict | None:
    return {key: value.isoformat() for key, value in window.items()} if window else None


def _orchestrator_stats(main_path: Path, wf_id: str) -> dict:
    """The main-session context at the `Workflow` launch turn and at the next
    assistant turn. The launch is the assistant turn whose `Workflow`
    `tool_use` is answered by a `tool_result` naming `wf_id` -- the harness
    echoes the run directory into that result -- never the first launch by
    position: one session may hold several fan-outs, and the report is keyed
    by the run it was asked for. `return_bytes` is that result's size; the
    next assistant turn with usage after the launch gives the second reading.
    Every field is `null` when the main transcript is missing or no launch in
    it names the run -- not a run-level failure (no CLI reason code covers
    it); `--session` is the recovery when the transcript lives elsewhere."""
    records = list(wr.iter_transcript_records(main_path))
    launch = _find_launch(records, wf_id)
    if launch is None:
        return {
            "launch_turn_tokens": None,
            "next_turn_tokens": None,
            "delta": None,
            "return_bytes": None,
        }
    launch_idx, launch_tokens, return_bytes = launch

    next_tokens = None
    for record in records[launch_idx + 1 :]:
        if record.get("type") != "assistant":
            continue
        usage = (record.get("message") or {}).get("usage") or {}
        if usage:
            next_tokens = wr.context_tokens(usage)
            break

    delta = next_tokens - launch_tokens if next_tokens is not None else None
    return {
        "launch_turn_tokens": launch_tokens,
        "next_turn_tokens": next_tokens,
        "delta": delta,
        "return_bytes": return_bytes,
    }


def _find_launch(records: list[dict], wf_id: str) -> tuple[int, int, int] | None:
    """`(index, context_tokens, return_bytes)` of the launch turn whose
    answering `tool_result` names `wf_id`, or `None` when no launch does."""
    for i, record in enumerate(records):
        block = _workflow_tool_use_block(record)
        if block is None:
            continue
        result = _tool_result_content(records[i + 1 :], block.get("id"))
        if result is None or wf_id not in result:
            continue
        usage = (record.get("message") or {}).get("usage") or {}
        return i, wr.context_tokens(usage), len(result.encode("utf-8"))
    return None


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


def _tool_result_content(records: list[dict], tool_use_id: str | None) -> str | None:
    """The JSON-serialised content of the `tool_result` answering
    `tool_use_id` among `records`, or `None` when nothing answers it."""
    if tool_use_id is None:
        return None
    for record in records:
        if record.get("type") != "user":
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and block.get("tool_use_id") == tool_use_id
            ):
                return json.dumps(block.get("content"))
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
    for row in unobserved:
        row["attribution"] = "time-window-heuristic"
    return {
        "wf_id": loaded["wf_id"],
        "agents": agents,
        "unobserved": unobserved,
        "window": _window_json(loaded.get("window")),
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
        "--session",
        default=None,
        help="Main-session transcript path override, for a transcript that is not the run directory's sibling.",
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
