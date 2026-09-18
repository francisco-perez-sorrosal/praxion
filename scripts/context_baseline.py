#!/usr/bin/env python3
"""Context guard: reports orchestrator/subagent context usage against the P3.1
baseline (`.ai-work/process-economy-p3-1/BASELINE.md`).

Praxion sets no compaction threshold and reads no live utilisation (D1) --
this script is a **measurement instrument**, not an enforcement gate. It
answers "what would an operator-chosen threshold have fired on" (`--band`),
never a Praxion-shipped recommendation.

Two layers, mirroring `self_healing_metrics.py`'s split:

    load(project_root) -> list[dict]     all I/O -- walks the Claude Code
                                          project transcripts + the WAL
    compute(rows, band=None, ...) -> dict pure aggregation into the
                                          `ContextBaselineReport` shape

`load()` promotes the ad hoc `baseline/{baseline,retype,main_sessions,
first_turn}.py` scripts used to produce `BASELINE.md` -- same regexes, same
percentile formula, same agent-type classification cascade, folded into one
pass per transcript file instead of the original scripts' several. Their
parsing logic is already correct and measured; nothing here rewrites it.

Percentile convention: a floor-indexed pick (`sorted(xs)[min(len(xs)-1,
int(p*len(xs)))]`), NOT `statistics.median` -- `BASELINE.md`'s published
numbers were computed with this exact formula and a guard that silently used
a different one would diverge on even-length groups.

Tests are fixture-only (`scripts/test_context_baseline.py`) -- real
transcripts are never committed or read in CI; the reproduction against this
machine's own transcripts is a manual, LEARNINGS.md-recorded check.

Run: `python3 scripts/context_baseline.py --project-root DIR [--band TOKENS]
[--json] [--table]`
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from _repo_root import git_toplevel_from_cwd

# The model's context window -- a fixed constant, never a CLI-supplied value
# (D1: Praxion ships no threshold, so there is nothing to make configurable).
_WINDOW_TOKENS = 1_000_000

# `baseline.py`'s simple "You are the X" match on the raw (un-lowered) first
# prompt, tried before the broader cascade below.
_SIMPLE_ROLE_RE = re.compile(r"You are the ([a-z-]+)")
_SLUG_RE = re.compile(r"Task slug:\s*`?([a-z0-9-]+)")

# `retype.py`'s broader classifier -- praxion:/@/"you are (the|a|an)" prefixed,
# or a bare substring hit -- tried only when the simple match above fails.
_ROLE_NAMES = (
    "systems-architect",
    "implementation-planner",
    "implementer",
    "test-engineer",
    "verifier",
    "researcher",
    "context-engineer",
    "doc-engineer",
    "sentinel",
    "discipline-consultant",
    "interface-designer",
    "promethean",
    "roadmap-cartographer",
    "skill-genesis",
    "architect-validator",
    "cicd-engineer",
)
_BROAD_ROLE_RE = re.compile(
    r"(?:you are (?:the |a |an )?|praxion:|@)`?(" + "|".join(_ROLE_NAMES) + r")"
)


# --------------------------------------------------------------------------- #
# I/O layer (the only impure functions)
# --------------------------------------------------------------------------- #
def _transcripts_dir(project_root: Path) -> Path:
    """Claude Code's per-project transcript directory: the project's absolute
    path with every "/" replaced by "-", under `~/.claude/projects/`."""
    mangled = str(project_root).replace("/", "-")
    return Path.home() / ".claude" / "projects" / mangled


def _agent_types_from_wal(wal_path: Path) -> dict[str, str]:
    """`agent_id -> agent_type` from `agent_start` WAL rows (join key for
    subagent transcripts, which carry the id in their filename)."""
    id2type: dict[str, str] = {}
    if not wal_path.exists():
        return id2type
    for line in wal_path.read_text(encoding="utf-8").splitlines():
        if '"agent_start"' not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event_type") == "agent_start" and row.get("agent_id"):
            id2type[row["agent_id"]] = row.get("agent_type")
    return id2type


def _classify_from_prompt(first_prompt: str) -> str:
    """`baseline.py`'s simple match, falling back to `retype.py`'s broader one
    -- the exact two-pass cascade the ad hoc scripts ran against a WAL-unjoined
    transcript, folded into one so `load()` reads each file once. Returns
    "unknown" (no hit) or "multi" (2+ substring hits) as their own literal
    values -- never merged into each other or silently dropped."""
    match = _SIMPLE_ROLE_RE.search(first_prompt)
    if match:
        return match.group(1)
    low = first_prompt[:1500].lower()
    match = _BROAD_ROLE_RE.search(low)
    if match:
        return match.group(1)
    hits = [name for name in _ROLE_NAMES if name in low]
    if len(hits) == 1:
        return hits[0]
    return "multi" if hits else "unknown"


def _context_tokens(usage: dict) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def _iter_records(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _parse_subagent_transcript(path: Path) -> dict | None:
    """One pass over a subagent transcript. Returns `None` when the agent
    never reached an assistant turn with usage (dropped, mirroring
    `baseline.py`'s `if turns == 0: continue`)."""
    turns = peak = tools = compactions = 0
    first_turn: int | None = None
    first_prompt = ""
    for record in _iter_records(path):
        if record.get("isCompactSummary") or record.get("type") == "summary":
            compactions += 1
        message = record.get("message") or {}
        if not isinstance(message, dict):
            continue
        content = message.get("content")

        if record.get("type") == "user" and not first_prompt:
            first_prompt = _content_text(content)

        if record.get("type") != "assistant":
            continue
        usage = message.get("usage") or {}
        if not usage:
            continue
        turns += 1
        ctx = _context_tokens(usage)
        peak = max(peak, ctx)
        if first_turn is None and usage.get("cache_creation_input_tokens") is not None:
            first_turn = ctx
        if isinstance(content, list):
            tools += sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")

    if turns == 0:
        return None
    slug_match = _SLUG_RE.search(first_prompt)
    return {
        "kind": "subagent",
        "atype": _classify_from_prompt(first_prompt),
        "slug": slug_match.group(1) if slug_match else "unknown",
        "peak": peak,
        "first_turn": first_turn or 0,
        "turns": turns,
        "tools": tools,
        "compactions": compactions,
        "spawns": [],
    }


def _parse_main_transcript(path: Path) -> dict | None:
    """One pass over a main-session transcript."""
    turns = peak = compactions = 0
    first_turn: int | None = None
    spawns: list[list] = []
    for record in _iter_records(path):
        if record.get("isCompactSummary"):
            compactions += 1
        message = record.get("message") or {}
        if not isinstance(message, dict) or record.get("type") != "assistant":
            continue
        usage = message.get("usage") or {}
        if not usage:
            continue
        turns += 1
        ctx = _context_tokens(usage)
        peak = max(peak, ctx)
        if first_turn is None and usage.get("cache_creation_input_tokens") is not None:
            first_turn = ctx
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Agent"
                ):
                    spawned_type = (block.get("input") or {}).get("subagent_type", "?")
                    spawns.append([ctx, spawned_type])

    if turns == 0:
        return None
    return {
        "kind": "main",
        "atype": None,
        "slug": None,
        "peak": peak,
        "first_turn": first_turn or 0,
        "turns": turns,
        "tools": 0,
        "compactions": compactions,
        "spawns": spawns,
    }


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def load(project_root: Path) -> list[dict]:
    """Walk this project's transcripts + WAL into `compute()`'s row shape.

    Impure: the only function in this module that touches the filesystem.
    """
    transcripts_dir = _transcripts_dir(project_root)
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    id2type = _agent_types_from_wal(wal_path)

    rows: list[dict] = []
    for path in sorted(transcripts_dir.glob("*/subagents/agent-*.jsonl")):
        row = _parse_subagent_transcript(path)
        if row is None:
            continue
        agent_id = path.name[len("agent-") : -len(".jsonl")]
        wal_type = id2type.get(agent_id)
        if wal_type:
            row["atype"] = wal_type.replace("praxion:", "")
        rows.append(row)

    for path in sorted(transcripts_dir.glob("*.jsonl")):
        row = _parse_main_transcript(path)
        if row is not None:
            rows.append(row)

    return rows


# --------------------------------------------------------------------------- #
# pure aggregation (unit-tested against fixtures -- no filesystem, no clock)
# --------------------------------------------------------------------------- #
def _percentile(values: list[int], p: float, default: int = 0) -> int:
    """Floor-indexed pick pinned to `baseline/baseline.py`'s `q(xs, p)` --
    deliberately NOT `statistics.median`; see module docstring."""
    if not values:
        return default
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def _percentile_summary(values: list[int]) -> dict[str, int]:
    if not values:
        return {"p50": 0, "p90": 0, "max": 0}
    return {"p50": _percentile(values, 0.5), "p90": _percentile(values, 0.9), "max": max(values)}


def _aggregate_main(main_rows: list[dict]) -> dict:
    spawn_ctx: dict[str, list[int]] = defaultdict(list)
    for row in main_rows:
        for ctx, spawned_type in row["spawns"]:
            spawn_ctx[spawned_type].append(ctx)
    return {
        "peak": _percentile_summary([r["peak"] for r in main_rows]),
        "first_turn": {"p50": _percentile([r["first_turn"] for r in main_rows], 0.5)},
        "spawn_context": {
            t: {"n": len(xs), **_percentile_summary(xs)} for t, xs in spawn_ctx.items()
        },
    }


def _aggregate_by_agent_type(subagent_rows: list[dict]) -> dict:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in subagent_rows:
        by_type[row["atype"]].append(row)

    result = {}
    for atype, group in by_type.items():
        peaks = [r["peak"] for r in group]
        result[atype] = {
            "n": len(group),
            "first_turn_p50": _percentile([r["first_turn"] for r in group], 0.5),
            "peak_p50": _percentile(peaks, 0.5),
            "peak_p90": _percentile(peaks, 0.9),
            "peak_max": max(peaks),
            "turns_p50": _percentile([r["turns"] for r in group], 0.5),
            "tools_p50": _percentile([r["tools"] for r in group], 0.5),
            "compacted": sum(1 for r in group if r["compactions"] > 0),
        }
    return result


def _aggregate_by_pipeline(subagent_rows: list[dict]) -> dict:
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for row in subagent_rows:
        by_slug[row["slug"]].append(row)

    result = {}
    for slug, group in by_slug.items():
        peaks = [r["peak"] for r in group]
        result[slug] = {
            "agents": len(group),
            "sum_peak": sum(peaks),
            "max_peak": max(peaks),
            "over_100k": sum(1 for p in peaks if p > 100_000),
            "over_150k": sum(1 for p in peaks if p > 150_000),
        }
    return result


def _would_compact_count(peaks: list[int], threshold: int) -> dict[str, int]:
    return {"n": sum(1 for p in peaks if p > threshold), "of": len(peaks)}


def _band_counterfactual(
    threshold: int,
    main_rows: list[dict],
    subagent_rows: list[dict],
    by_agent_type: dict[str, dict],
) -> dict:
    """`--band` is an operator-supplied analysis threshold, never a value
    Praxion sets or ships (D1) -- counts what would have crossed it, nothing
    more."""
    would_compact = {"main": _would_compact_count([r["peak"] for r in main_rows], threshold)}
    for atype in by_agent_type:
        peaks = [r["peak"] for r in subagent_rows if r["atype"] == atype]
        would_compact[atype] = _would_compact_count(peaks, threshold)
    return {
        "threshold": threshold,
        "window_tokens": _WINDOW_TOKENS,
        "would_compact": would_compact,
    }


def compute(
    rows: list[dict], band: int | None = None, *, generated_at: str, source_root: str
) -> dict:
    """Aggregate `load()`'s rows into the `ContextBaselineReport` shape.

    Pure: no filesystem access, no clock read -- `generated_at` and
    `source_root` are supplied by the caller and echoed back unchanged, which
    is what makes this function fixture-testable without mocking either.
    """
    main_rows = [r for r in rows if r["kind"] == "main"]
    subagent_rows = [r for r in rows if r["kind"] == "subagent"]
    by_agent_type = _aggregate_by_agent_type(subagent_rows)

    report = {
        "generated_at": generated_at,
        "source_root": source_root,
        "sessions": len(main_rows),
        "subagents": len(subagent_rows),
        "main": _aggregate_main(main_rows),
        "by_agent_type": by_agent_type,
        "by_pipeline": _aggregate_by_pipeline(subagent_rows),
    }
    if band is not None:
        report["band"] = _band_counterfactual(band, main_rows, subagent_rows, by_agent_type)
    return report


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render_table(report: dict) -> str:
    lines = [
        f"sessions={report['sessions']}  subagents={report['subagents']}  "
        f"source={report['source_root']}",
        "",
        "main peak p50/p90/max: "
        f"{report['main']['peak']['p50']:,}/{report['main']['peak']['p90']:,}/"
        f"{report['main']['peak']['max']:,}  first_turn p50={report['main']['first_turn']['p50']:,}",
        "",
        f"{'type':24} {'n':>4} {'first p50':>10} {'peak p50':>10} {'peak p90':>10} {'peak max':>10}",
    ]
    for atype, stats in sorted(report["by_agent_type"].items(), key=lambda kv: -kv[1]["n"]):
        lines.append(
            f"{atype:24} {stats['n']:>4} {stats['first_turn_p50']:>10,} "
            f"{stats['peak_p50']:>10,} {stats['peak_p90']:>10,} {stats['peak_max']:>10,}"
        )
    if "band" in report:
        band = report["band"]
        lines += ["", f"band threshold={band['threshold']:,} (window={band['window_tokens']:,}):"]
        for key, wc in band["would_compact"].items():
            lines.append(f"  {key:24} {wc['n']}/{wc['of']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Context guard: reports usage against the P3.1 baseline (analysis only, sets no threshold)."
    )
    parser.add_argument(
        "--project-root", default=None, help="Project root; defaults to git toplevel of CWD."
    )
    parser.add_argument(
        "--band",
        type=int,
        default=None,
        help="Operator-supplied absolute-token threshold for a would-compact counterfactual.",
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

    rows = load(project_root)
    report = compute(
        rows,
        band=args.band,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_root=str(_transcripts_dir(project_root)),
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=False))
    else:
        print(render_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
