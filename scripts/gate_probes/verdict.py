"""The liveness verdict: what one probe reports about one gate.

A liveness check must never pass by default, so the verdict makes the two
legal states the only representable ones: a pass carries no reason and no
findings, a failure carries a reason of the form `expected ...; observed ...`.
The constructor enforces both, so no probe can build a vague failure or a
passing verdict that still names a problem.

The JSON report is schema 1:

    {"schema": 1, "passed": bool, "verdicts": [<verdict>, ...]}

with one entry per selected gate, always in `GateId` order. `passed` is the
conjunction of the entries and is checked on parse, never trusted. A report
with no verdicts is rejected on both sides: it would read as a vacuous pass.

Each verdict entry is `{"gate", "passed", "reason", "elapsed_s", "unselected",
"notes"}`; `unselected` pairs are `[test file, file it read]`, filled only by the
selection audit.

Stdlib-only. Tests: `scripts/gate_probes/test_verdict.py`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1

_FAILURE_REASON = re.compile(r"expected\s+\S.*;\s*observed\s+\S", re.DOTALL)


class GateId(StrEnum):
    """The four gates, in the order a run reports them."""

    MUTATION_SENSOR = "mutation-sensor"
    OBSERVATION_HOOKS = "observation-hooks"
    SPAWN_COUNT = "spawn-count"
    SELECTION_AUDIT = "selection-audit"


_ORDER = {gate: position for position, gate in enumerate(GateId)}


@dataclass(frozen=True)
class Verdict:
    gate: GateId
    passed: bool
    reason: str  # why it failed: "expected ...; observed ..."; empty exactly when passed
    elapsed_s: float
    unselected: tuple[tuple[str, str], ...] = ()  # selection audit: (test file, file it read)
    notes: tuple[str, ...] = ()  # informational, never a finding

    def __post_init__(self) -> None:
        if self.elapsed_s < 0:
            raise ValueError(f"elapsed_s must not be negative, got {self.elapsed_s}")
        if self.passed and (self.reason or self.unselected):
            raise ValueError("a passed verdict carries no reason and no unselected reads")
        if not self.passed and not _FAILURE_REASON.match(self.reason):
            raise ValueError(
                "a failed verdict needs a reason of the form 'expected ...; observed ...', "
                f"got {self.reason!r}"
            )


def render_json(verdicts: Sequence[Verdict]) -> str:
    """The schema-1 report for `verdicts`, entries ordered by gate."""
    if not verdicts:
        raise ValueError("a liveness report with no verdicts would read as a pass")
    ordered = sorted(verdicts, key=lambda verdict: _ORDER[verdict.gate])
    seen = [verdict.gate for verdict in ordered]
    if len(set(seen)) != len(seen):
        raise ValueError("a gate appears twice in one liveness report")
    payload = {
        "schema": SCHEMA_VERSION,
        "passed": all(verdict.passed for verdict in ordered),
        "verdicts": [_entry(verdict) for verdict in ordered],
    }
    return json.dumps(payload, indent=2)


def parse_json(text: str) -> tuple[Verdict, ...]:
    """The verdicts of a schema-1 report; a malformed or inconsistent report is a ValueError."""
    payload = json.loads(text)
    if payload.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"unsupported report schema {payload.get('schema')!r}")
    verdicts = tuple(_verdict(entry) for entry in payload["verdicts"])
    if not verdicts:
        raise ValueError("a liveness report with no verdicts would read as a pass")
    positions = [_ORDER[verdict.gate] for verdict in verdicts]
    if positions != sorted(set(positions)):
        raise ValueError("verdicts are not in the fixed gate order, once each")
    if payload["passed"] != all(verdict.passed for verdict in verdicts):
        raise ValueError("the report's passed flag disagrees with its verdicts")
    return verdicts


def _entry(verdict: Verdict) -> dict[str, object]:
    return {
        "gate": verdict.gate.value,
        "passed": verdict.passed,
        "reason": verdict.reason,
        "elapsed_s": verdict.elapsed_s,
        "unselected": [list(pair) for pair in verdict.unselected],
        "notes": list(verdict.notes),
    }


def _verdict(entry: Mapping[str, Any]) -> Verdict:
    return Verdict(
        gate=GateId(entry["gate"]),
        passed=bool(entry["passed"]),
        reason=str(entry["reason"]),
        elapsed_s=float(entry["elapsed_s"]),
        unselected=tuple((test, read) for test, read in entry["unselected"]),
        notes=tuple(entry["notes"]),
    )
