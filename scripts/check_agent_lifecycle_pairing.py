#!/usr/bin/env python3
"""P03: every `agent_start` that ran has a matching `agent_stop`.

Reads `.ai-state/observations.jsonl` (JSONL, one record per line) and pairs
`event_type: agent_start` with `event_type: agent_stop` **on `agent_id`** --
the only field that identifies a single spawn. Pairing on `agent_type` is the
trap this check exists to avoid: concurrent instances share a type, so one
sibling's stop silently satisfies another's start and the fleet reports
clean (see `test_warn_pairs_on_agent_id_not_agent_type`).

Two boundaries are not findings:

1. **In-flight exclusion.** An agent still running legitimately has a start
   and no stop. Every record whose `session_id` equals the newest record's
   in the file is excluded from pairing entirely -- it is not evidence of
   anything, in either direction.
2. **WAL truncation at the front.** Rotation and `.ai-state/` merges can
   strip the file's earlier lines, so an `agent_stop` whose start predates
   the truncation point is a boundary artifact, not a defect. Unmatched
   stops are reported as INFO, never WARN.

Unpaired starts are classified into exactly one bucket -- the classifier's
own total-count assertion is the enforcement point for this invariant:

* **`findings` (WARN)** -- post-baseline (dated on/after 2026-09-05, the date
  the main-agent `Stop` hook began synthesizing a stop for a subagent
  suspended at its turn limit or halted by the orchestrator) *and* the
  `agent_id` appears in >=1 `tool_use` record. That one ran and then
  vanished -- the lost stop this check exists to catch.
* **`info.pre_baseline`** -- dated before 2026-09-05. The emitter of that
  era could not see a suspension; no change to this repository closes it
  retroactively.
* **`info.no_tool_use`** -- post-baseline but the `agent_id` never appears
  in any `tool_use` record. Died on arrival, upstream of any hook -- there
  was no Stop hook for it to miss.
* **`info.incidents`** -- overrides all three of the above. Unpaired starts
  sharing one `session_id`, one `agent_type`, and a narrow time window
  (`INCIDENT_WINDOW`, below) are a single upstream *incident*, not a *rate*
  spread across the fleet; summing them into the WARN/no_tool_use counts
  reports one already-over event as ongoing systemic failure. A cluster
  collapses to one `info.incidents` entry naming its session, window and
  concentration -- `not_this_fleet` records whether the (namespace-stripped)
  `agent_type` matches no file in `agents/`.

`INCIDENT_WINDOW` (15 minutes) is a judgment call: the row text specifies
only "a narrow time window" without a number. Fifteen minutes is short
enough that no ordinary multi-agent pipeline batch would false-positive as
an incident, long enough to catch the retry storms this check was written
for. Recorded as a load-bearing assumption in this pipeline's `LEARNINGS.md`.

Unmatched stops are read the opposite way: the classifier's own pairing
already knows *that* a stop is unmatched, and reads the stop row's own
`start_correlation` field only to say *which* INFO class it is.
`hooks/capture_session.py` records the emitter's own real-time verdict
there, computed from its own bounded tail-window lookup -- narrower than
this check's whole-file view, which is exactly why the two can disagree.
A **missing** field is `unattested`, never treated as agreement (a record
written before the field existed, or a synthesized entry, silently read as
"confirmed paired" would turn an unaudited backlog into a clean bill). A
present field that disagrees with the WAL-derived verdict this check
computes fresh (via `resolve_start_correlation`, re-run here with this
check's own whole-file `any_row_seen` answer) is `producer_log_disagreement`
-- the WAL wins, and the disagreement itself is the finding, never silently
resolved in either direction. A stop the classifier's own pairing *did*
match is never run through this branch at all, regardless of what its own
field claims -- the WAL's pairing is authoritative once a match exists.

Before matching `agent_type` against files in `agents/`, any `<namespace>:`
plugin-prefix (e.g. `praxion:implementer`) is stripped and the bare
`<name>.md` is matched -- this fleet's roster is registered under more than
one local namespace, so a prefixed `agent_type` alone is not evidence of a
different fleet.

Imports the correlation-verdict constants and `resolve_agent_id` /
`resolve_agent_type` / `resolve_start_correlation` from
`hooks/capture_session.py` rather than re-literalling them -- the WAL
emitter and this reader must never drift on what these values mean.

Golden bad-cases and inverse guards: see `scripts/test_check_agent_lifecycle_pairing.py`.

Invocation:

    check_agent_lifecycle_pairing.py                  # human-readable summary
    check_agent_lifecycle_pairing.py --json           # machine-readable JSON object
    check_agent_lifecycle_pairing.py --check          # exit 1 when any WARN finding, else 0
    check_agent_lifecycle_pairing.py --repo-root DIR  # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when >=1 WARN finding is
present. Always 0 when `.ai-state/observations.jsonl` is absent.
Exit code 2 when the resolved root is a plugin-cache path.

Invoked by the sentinel's P dimension (`--json`); also runnable standalone.

Cites: SYSTEMS_PLAN.md § The Extraction Contract, § Data Structures (`LifecycleReport`).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from _repo_root import is_plugin_cache_path, resolve_repo_root  # noqa: E402
from _script_cli import configure_logging  # noqa: E402
from capture_session import (  # noqa: E402
    CORRELATION_PAIRED,
    CORRELATION_UNOBSERVED_AGENT,
    CORRELATION_UNOBSERVED_START,
    resolve_agent_id,
    resolve_agent_type,
    resolve_start_correlation,
)

SCRIPT_DIR = Path(__file__).resolve().parent

CHECK_ID = "P03"
SEVERITY = "warn"

# Relative to repo_root -- the WAL this check reads.
OBSERVATIONS_REL = ".ai-state/observations.jsonl"
AGENTS_DIR_REL = "agents"

_START_EVENT = "agent_start"
_STOP_EVENT = "agent_stop"
_TOOL_EVENT = "tool_use"

# The date the main-agent Stop hook began synthesizing a stop for a
# turn-limited or orchestrator-halted subagent (see module docstring). An
# unpaired start before this date is a known-unrecoverable backlog gap, not
# a live defect.
PRE_BASELINE_CUTOFF = datetime(2026, 9, 5, tzinfo=timezone.utc)

# See module docstring: a judgment call, not a measured constant.
INCIDENT_WINDOW = timedelta(minutes=15)

logger = logging.getLogger("check_agent_lifecycle_pairing")


# -- Parsing --------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    """One parsed WAL line, holding only the fields this check reads."""

    event_type: str
    agent_id: str
    agent_type: str
    session_id: str
    timestamp: datetime | None
    start_correlation: str | None


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp, or None if missing/unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_line(line: str) -> _Row | None:
    """Parse one JSONL line into a `_Row`, or None if malformed/not a dict.

    Reuses the WAL's own `resolve_agent_id`/`resolve_agent_type` rather than
    reading `agent_id`/`agent_type` directly -- a written row is exactly the
    payload shape those resolvers accept, so this stays correct if a future
    row omits a field the raw-dict read would have silently returned "" for.
    """
    try:
        raw = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    event_type = str(raw.get("event_type") or "")
    agent_type, _source = resolve_agent_type(raw, event_type)
    return _Row(
        event_type=event_type,
        agent_id=resolve_agent_id(raw),
        agent_type=agent_type,
        session_id=str(raw.get("session_id") or ""),
        timestamp=_parse_timestamp(raw.get("timestamp")),
        start_correlation=raw.get("start_correlation") or None,
    )


def _read_rows(obs_path: Path) -> tuple[list[_Row], list[str]]:
    """Return `(rows, withheld)` for every line in `obs_path`.

    A line that fails to parse is counted into `withheld` (naming its line
    number) and excluded from every other count -- never silently dropped.
    """
    rows: list[_Row] = []
    withheld: list[str] = []
    for line_no, line in enumerate(obs_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = _parse_line(line)
        if row is None:
            withheld.append(f"line {line_no}: unparseable JSONL record, excluded")
            continue
        rows.append(row)
    return rows, withheld


# -- Fleet roster -----------------------------------------------------------------


def _strip_namespace(agent_type: str) -> str:
    """Return `agent_type` with any `<namespace>:` plugin-prefix removed."""
    return agent_type.rsplit(":", 1)[-1] if ":" in agent_type else agent_type


def _known_agent_names(repo_root: Path) -> set[str]:
    agents_dir = repo_root / AGENTS_DIR_REL
    if not agents_dir.is_dir():
        return set()
    return {p.stem for p in agents_dir.glob("*.md")}


# -- Unpaired-start classification -------------------------------------------------


def _cluster_incidents(
    unpaired: list[_Row], known_agents: set[str]
) -> tuple[list[dict], list[_Row]]:
    """Group `unpaired` starts sharing `(session_id, agent_type)` into one
    `info.incidents` entry each when they cluster inside `INCIDENT_WINDOW`.

    Returns `(incidents, remainder)` -- `remainder` holds every start not
    absorbed into a cluster (including every start with no parseable
    timestamp, which cannot support a window comparison), for individual
    base-label classification by the caller. Clustering runs before, and
    takes priority over, the pre_baseline/no_tool_use/WARN base labels: a
    burst that happens to also be pre-baseline or tool-use-free is still one
    incident, not one differently-labeled entry per member.
    """
    groups: dict[tuple[str, str], list[_Row]] = defaultdict(list)
    remainder: list[_Row] = []
    for row in unpaired:
        if row.timestamp is None:
            remainder.append(row)
            continue
        groups[(row.session_id, row.agent_type)].append(row)

    incidents: list[dict] = []
    for (session_id, agent_type), members in groups.items():
        if len(members) < 2:
            remainder.extend(members)
            continue
        ordered = sorted(members, key=lambda r: r.timestamp)
        span = ordered[-1].timestamp - ordered[0].timestamp
        if span > INCIDENT_WINDOW:
            remainder.extend(members)
            continue
        incidents.append(
            {
                "session_id": session_id,
                "window_start": ordered[0].timestamp.isoformat(),
                "window_end": ordered[-1].timestamp.isoformat(),
                "agent_type": agent_type,
                "count": len(members),
                "not_this_fleet": _strip_namespace(agent_type) not in known_agents,
            }
        )
    return incidents, remainder


def _classify_unpaired_starts(
    unpaired: list[_Row], ran_tool_ids: set[str], known_agents: set[str]
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Return `(findings, pre_baseline, no_tool_use, incidents)`.

    Every entry of `unpaired` lands in exactly one of these four buckets --
    `incidents` counts a whole cluster as one entry (see `_cluster_incidents`),
    so the total-count invariant is `len(unpaired) == len(findings) +
    len(pre_baseline) + len(no_tool_use) + sum(i["count"] for i in incidents)`.
    """
    incidents, remainder = _cluster_incidents(unpaired, known_agents)

    findings: list[dict] = []
    pre_baseline: list[dict] = []
    no_tool_use: list[dict] = []
    for row in remainder:
        if row.timestamp is not None and row.timestamp < PRE_BASELINE_CUTOFF:
            pre_baseline.append({"agent_id": row.agent_id, "session_id": row.session_id})
        elif row.agent_id not in ran_tool_ids:
            no_tool_use.append({"agent_id": row.agent_id, "session_id": row.session_id})
        else:
            findings.append(
                {
                    "check": CHECK_ID,
                    "severity": SEVERITY,
                    "entity": row.agent_id,
                    "message": (
                        f"{row.agent_id} (agent_type={row.agent_type}, "
                        f"session_id={row.session_id}) started, ran tool_use, and never stopped"
                    ),
                }
            )
    return findings, pre_baseline, no_tool_use, incidents


# -- Unmatched-stop classification -------------------------------------------------


def _classify_unmatched_stops(unmatched: list[_Row], any_row_seen: set[str]) -> tuple[dict, list]:
    """Return `(unmatched_stops, producer_log_disagreement)` for `unmatched` stops.

    `any_row_seen` is the set of `agent_id`s appearing in any non-stop
    record (start or tool_use) -- it feeds `resolve_start_correlation`'s
    `any_row_seen` parameter, giving this check's own whole-file verdict to
    compare the stop row's self-reported field against.
    """
    unmatched_stops = {
        CORRELATION_UNOBSERVED_START: [],
        CORRELATION_UNOBSERVED_AGENT: [],
        "unattested": [],
    }
    producer_log_disagreement: list[dict] = []
    for row in unmatched:
        wal_verdict = resolve_start_correlation(
            _STOP_EVENT, start_row_seen=False, any_row_seen=row.agent_id in any_row_seen
        )
        # A self-report of "paired" is checked ahead of the generic
        # mismatch below and named explicitly: this classifier only
        # reaches here for a stop its own pairing already found unmatched,
        # so "paired" is always a disagreement, and the spec calls this
        # exact case out by name -- worth a reader seeing it named rather
        # than inferred from the generic inequality that would also catch it.
        disagrees = row.start_correlation is not None and (
            row.start_correlation == CORRELATION_PAIRED or row.start_correlation != wal_verdict
        )
        if row.start_correlation is None:
            unmatched_stops["unattested"].append(row.agent_id)
        elif disagrees:
            producer_log_disagreement.append(
                {
                    "agent_id": row.agent_id,
                    "self_reported": row.start_correlation,
                    "wal_verdict": wal_verdict,
                }
            )
        else:
            unmatched_stops[wal_verdict].append(row.agent_id)
    return unmatched_stops, producer_log_disagreement


# -- Core classification ------------------------------------------------------------


def classify(repo_root: Path) -> dict:
    """Build the canonical envelope: the `LifecycleReport` for the full WAL."""
    obs_path = repo_root / OBSERVATIONS_REL
    if not obs_path.is_file():
        return _skipped_report("substrate-absent", str(obs_path))

    rows, withheld = _read_rows(obs_path)
    if not rows:
        return _empty_report(withheld, excluded_in_flight_session=None)

    newest_session = rows[-1].session_id
    examined_rows = [r for r in rows if r.session_id != newest_session]
    excluded_count = len(rows) - len(examined_rows)

    starts = [r for r in examined_rows if r.event_type == _START_EVENT]
    stops = [r for r in examined_rows if r.event_type == _STOP_EVENT]
    tool_use_ids = {r.agent_id for r in examined_rows if r.event_type == _TOOL_EVENT}
    non_stop_ids = {r.agent_id for r in examined_rows if r.event_type != _STOP_EVENT}

    start_ids = {r.agent_id for r in starts}
    stop_ids = {r.agent_id for r in stops}
    unpaired_starts = [r for r in starts if r.agent_id not in stop_ids]
    unmatched_stops_rows = [r for r in stops if r.agent_id not in start_ids]

    known_agents = _known_agent_names(repo_root)
    findings, pre_baseline, no_tool_use, incidents = _classify_unpaired_starts(
        unpaired_starts, tool_use_ids, known_agents
    )
    unmatched_stops, producer_log_disagreement = _classify_unmatched_stops(
        unmatched_stops_rows, non_stop_ids
    )

    return {
        "check": CHECK_ID,
        "skipped": None,
        "examined": {
            "records": len(rows),
            "sessions": len({r.session_id for r in rows}),
            "excluded_in_flight_session": newest_session if excluded_count else None,
        },
        "findings": findings,
        "info": {
            "incidents": incidents,
            "pre_baseline": pre_baseline,
            "no_tool_use": no_tool_use,
            "unmatched_stops": unmatched_stops,
            "producer_log_disagreement": producer_log_disagreement,
        },
        "withheld": withheld,
        "bound": (
            "P03 clean means no agent that did work went unstopped, not that every spawn completed."
        ),
    }


def _empty_report(withheld: list[str], excluded_in_flight_session: str | None) -> dict:
    return {
        "check": CHECK_ID,
        "skipped": None,
        "examined": {
            "records": 0,
            "sessions": 0,
            "excluded_in_flight_session": excluded_in_flight_session,
        },
        "findings": [],
        "info": {
            "incidents": [],
            "pre_baseline": [],
            "no_tool_use": [],
            "unmatched_stops": {
                CORRELATION_UNOBSERVED_START: [],
                CORRELATION_UNOBSERVED_AGENT: [],
                "unattested": [],
            },
            "producer_log_disagreement": [],
        },
        "withheld": withheld,
        "bound": (
            "P03 clean means no agent that did work went unstopped, not that every spawn completed."
        ),
    }


def _skipped_report(reason: str, path: str) -> dict:
    return {
        "check": CHECK_ID,
        "skipped": {"reason": reason, "path": path},
        "examined": None,
        "findings": [],
        "info": {},
        "withheld": [],
        "bound": "P03 did not run; no lifecycle-pairing conclusion can be drawn.",
    }


# -- CLI --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_agent_lifecycle_pairing",
        description=(
            "Advisory: flag agent_start records with no matching agent_stop. "
            "Called by sentinel P03."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any P03 WARN finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    if report["skipped"] is not None:
        return f"check_agent_lifecycle_pairing: skipped ({report['skipped']['reason']})"
    findings = report["findings"]
    if not findings:
        return (
            "check_agent_lifecycle_pairing: no P03 WARNs across "
            f"{report['examined']['records']} records."
        )
    lines = [f"P03 WARN ({len(findings)} unpaired start(s)):"]
    lines.extend(f"  - {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        print(text, file=sys.stderr if report["findings"] else sys.stdout)

    return 1 if (args.check and report["findings"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_agent_lifecycle_pairing: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
