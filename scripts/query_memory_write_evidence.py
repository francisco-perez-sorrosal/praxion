#!/usr/bin/env python3
"""Query WAL evidence for the `memory: user` frontmatter drop-by-evidence sweep (P1.8).

Re-derives, per `praxion:*` agent_type, both figures the drop rule needs:
  - spawn count: number of `agent_start` rows for that agent_type
  - memory-write count: number of `tool_use` rows with tool_name in {Write, Edit}
    whose `file_paths` contain a memory-directory marker

The memory-write count is reported under BOTH marker filters, verbatim and
separately, per the plan's evidence requirement:
  (a) file_paths containing "agent-memory" (the subagent memory dir)
  (b) file_paths containing "/memory/"     (the harness auto-memory dir)

Always queries the MAIN checkout's WAL (`/Users/fperez/dev/praxion/.ai-state/observations.jsonl`)
by absolute path -- a pipeline worktree's own WAL starts empty and would
silently produce a false "zero signal" for every agent type.

Usage:
    python3 scripts/query_memory_write_evidence.py [--wal PATH]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

MAIN_WAL_DEFAULT = "/Users/fperez/dev/praxion/.ai-state/observations.jsonl"
AGENT_PREFIX = "praxion:"
MARKER_A = "agent-memory"
MARKER_B = "/memory/"

# Drop rule: keep `memory: user` when spawns < KEEP_MIN_SPAWNS (insufficient
# sample) OR when writes(marker) > 0 under either filter; drop only when
# spawns >= KEEP_MIN_SPAWNS AND writes == 0 under both filters.
KEEP_MIN_SPAWNS = 5


def iter_rows(wal_path: Path):
    with wal_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def query(wal_path: Path) -> dict[str, dict]:
    spawns: Counter[str] = Counter()
    writes_a: Counter[str] = Counter()
    writes_b: Counter[str] = Counter()

    for row in iter_rows(wal_path):
        agent_type = row.get("agent_type", "")
        if not agent_type.startswith(AGENT_PREFIX):
            continue
        if row.get("event_type") == "agent_start":
            spawns[agent_type] += 1
        elif row.get("event_type") == "tool_use" and row.get("tool_name") in {"Write", "Edit"}:
            file_paths = row.get("file_paths") or []
            joined = " ".join(file_paths)
            if MARKER_A in joined:
                writes_a[agent_type] += 1
            if MARKER_B in joined:
                writes_b[agent_type] += 1

    all_agents = set(spawns) | set(writes_a) | set(writes_b)
    result = {}
    for agent in sorted(all_agents):
        n = spawns[agent]
        a = writes_a[agent]
        b = writes_b[agent]
        keep = n < KEEP_MIN_SPAWNS or a > 0 or b > 0
        result[agent] = {
            "spawns": n,
            "writes_agent_memory": a,
            "writes_slash_memory": b,
            "decision": "keep" if keep else "drop",
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wal",
        default=MAIN_WAL_DEFAULT,
        help="path to observations.jsonl (default: main checkout)",
    )
    args = parser.parse_args()

    wal_path = Path(args.wal)
    if not wal_path.exists():
        print(f"WAL not found at {wal_path}", flush=True)
        return 1

    result = query(wal_path)
    header = f"{'agent_type':<45} {'spawns':>7} {'agent-memory':>13} {'/memory/':>9}  decision"
    print(header)
    print("-" * len(header))
    for agent, stats in result.items():
        print(
            f"{agent:<45} {stats['spawns']:>7} {stats['writes_agent_memory']:>13} "
            f"{stats['writes_slash_memory']:>9}  {stats['decision']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
