"""The pure core that turns session records into the baseline JSON, the
canary block, and the EVAL_LOG row draft — cli.py's orchestration is the only
caller, through the four public functions below.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from praxion_evals.live import scenarios
from praxion_evals.live.materialize import PathTarget, RefTarget, TargetIdentity
from praxion_evals.live.results import compute_lowered, compute_pass_rate

if TYPE_CHECKING:
    from praxion_evals.live.materialize import Degradation, Materialization, Variant
    from praxion_evals.live.spend import SpendLedger

CREDENTIAL_KEYS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN")
RUNNER_VERSION = "praxion-evals-live 0.37.0"
_SECRET_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")


def variant_record(
    variant: Variant,
    copy: Materialization,
    isolation_proof: dict[str, Any],
    session_records: Sequence[tuple[str, str, dict[str, Any]]],
) -> dict[str, Any]:
    """``session_records``: ``(scenario_id, case_id, session record)`` triples —
    cli.py resolves the case id from its own ``SessionTask`` before calling in,
    so this module never needs to know that type."""
    by_scenario: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for scenario_id, one_case_id, record in session_records:
        by_scenario.setdefault(scenario_id, []).append((one_case_id, record))

    scenario_blocks = []
    for scenario_id in scenarios.SCENARIOS:
        by_case: dict[str, list[dict[str, Any]]] = {}
        for one_case_id, record in by_scenario.get(scenario_id, []):
            by_case.setdefault(one_case_id, []).append(record)
        cases = [_case_block(one_case_id, records) for one_case_id, records in by_case.items()]
        counts = _sum_counts(c["counts"] for c in cases)
        scenario_blocks.append(
            {
                "scenario_id": scenario_id,
                "counts": counts,
                "pass_rate": compute_pass_rate(passed=counts["pass"], failed=counts["fail"]),
                "cases": cases,
            }
        )
    return {
        "variant": variant,
        "target": _target_json(copy.target),
        "degradation": _degradation_json(copy.degradation),
        "isolation_proof": isolation_proof,
        "scenarios": scenario_blocks,
        "totals": _totals([record for _, _, record in session_records]),
    }


def _case_block(one_case_id: str, session_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counts = _counts(session_records)
    return {
        "case_id": one_case_id,
        "counts": counts,
        "pass_rate": compute_pass_rate(passed=counts["pass"], failed=counts["fail"]),
        "sessions": list(session_records),
    }


def _counts(session_records: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "error": 0}
    for record in session_records:
        counts[record["outcome"]] += 1
    return counts


def _sum_counts(all_counts: Iterable[Mapping[str, int]]) -> dict[str, int]:
    total = {"pass": 0, "fail": 0, "error": 0}
    for counts in all_counts:
        for key in total:
            total[key] += counts[key]
    return total


_TOKEN_FIELDS = ("input", "output", "cache_creation", "cache_read")


def _totals(session_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    errors = sum(1 for record in session_records if record["outcome"] == "error")
    cost = sum(record.get("cost_usd") or 0 for record in session_records)
    tokens = {
        field: sum((record.get("usage") or {}).get(field, 0) for record in session_records)
        for field in _TOKEN_FIELDS
    }
    return {
        "scenario_sessions": len(session_records),
        "errors": errors,
        "cost_usd": cost,
        "tokens": tokens,
    }


def _target_json(target: TargetIdentity) -> dict[str, Any]:
    if isinstance(target, RefTarget):
        return {"kind": "ref", "ref": target.ref, "sha": target.sha}
    if isinstance(target, PathTarget):
        return {
            "kind": "path",
            "path": target.path,
            "head_sha": target.head_sha,
            "dirty": target.dirty,
        }
    raise TypeError(f"unrecognized target identity: {target!r}")  # pragma: no cover — exhaustive


def _degradation_json(degradation: Degradation | None) -> dict[str, Any] | None:
    if degradation is None:
        return None
    return {
        "file": degradation.file,
        "heading": degradation.heading,
        "removed_bytes": degradation.removed_bytes,
        "sha256_before": degradation.sha256_before,
        "sha256_after": degradation.sha256_after,
    }


def build_output(
    args: argparse.Namespace,
    started_at: str,
    variant_records: Sequence[dict[str, Any]],
    ledger: SpendLedger | None = None,
) -> dict[str, Any]:
    canary_block = None
    if args.canary and len(variant_records) == 2:
        canary_block = _canary_block(variant_records[0], variant_records[1])
    return {
        "schema_version": 1,
        "run": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "runner": RUNNER_VERSION,
            "complete": not _any_evaluation_exception(variant_records),
            "model": {"requested": args.model, "resolved": _resolved_models(variant_records)},
            "effort": args.effort,
            "k": args.k,
            # None = every scenario; a list marks a partial run, never a baseline.
            "scenarios": args.scenario,
            "judge": {"model": "claude-haiku-4-5"} if args.judge else None,
            "spend_usd": ledger.spent_usd if ledger is not None else None,
        },
        "variants": list(variant_records),
        "canary": canary_block,
    }


def _spawn_selection_scenario(variant_record_: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next(
        (s for s in variant_record_["scenarios"] if s["scenario_id"] == "spawn-selection"), None
    )


def _canary_block(head: Mapping[str, Any], canary: Mapping[str, Any]) -> dict[str, Any]:
    """``lowered`` reflects a per-case guard, not pooled scenario rates: a
    variant where three of five cases only ever errored (never graded) must
    not read as "the guard caught it" just because the pooled rate moved."""
    head_scenario = _spawn_selection_scenario(head)
    canary_scenario = _spawn_selection_scenario(canary)
    head_rate = head_scenario["pass_rate"] if head_scenario else None
    canary_rate = canary_scenario["pass_rate"] if canary_scenario else None
    graded_in_both = _every_case_graded_in_both(head_scenario, canary_scenario)
    return {
        "scenario_id": "spawn-selection",
        "head_pass_rate": head_rate,
        "canary_pass_rate": canary_rate,
        "delta": None if head_rate is None or canary_rate is None else canary_rate - head_rate,
        "lowered": compute_lowered(head_rate=head_rate, canary_rate=canary_rate)
        if graded_in_both
        else None,
    }


def _every_case_graded_in_both(
    head_scenario: Mapping[str, Any] | None, canary_scenario: Mapping[str, Any] | None
) -> bool:
    head_cases = {c["case_id"]: c for c in (head_scenario or {}).get("cases", [])}
    canary_cases = {c["case_id"]: c for c in (canary_scenario or {}).get("cases", [])}
    case_ids = set(head_cases) | set(canary_cases)
    if not case_ids:
        return False
    return all(
        _case_was_graded(head_cases.get(cid)) and _case_was_graded(canary_cases.get(cid))
        for cid in case_ids
    )


def _case_was_graded(case: Mapping[str, Any] | None) -> bool:
    if case is None:
        return False
    counts = case["counts"]
    return counts["pass"] + counts["fail"] > 0


def _any_evaluation_exception(variant_records: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        session.get("error_kind") == "evaluation_exception"
        for record in variant_records
        for scenario in record["scenarios"]
        for case in scenario["cases"]
        for session in case["sessions"]
    )


def _resolved_models(variant_records: Sequence[Mapping[str, Any]]) -> list[str]:
    models = {
        session["model_resolved"]
        for record in variant_records
        for scenario in record["scenarios"]
        for case in scenario["cases"]
        for session in case["sessions"]
        if session.get("model_resolved")
    }
    return sorted(models)


def write_output(output: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2) + "\n"
    leak = _leaked_credential(text)
    if leak is not None:
        raise RuntimeError(f"refusing to write the baseline JSON: {leak}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _leaked_credential(text: str) -> str | None:
    """A session's captured text (subagent output, an ADR fragment) is
    committed verbatim; scan it the way the recorder scans its fixtures."""
    if _SECRET_SHAPE.search(text):
        return "output contains an sk-ant- shaped substring"
    for key in CREDENTIAL_KEYS:
        value = os.environ.get(key)
        if value and value in text:
            return f"output contains the value of {key}"
    return None


def print_eval_log_row(output: Mapping[str, Any], resolved: Path | str) -> None:
    """9 columns, matching ``.ai-state/eval_ledger/EVAL_LOG.md``'s header:
    date | commit | purpose | mechanical | judged | always-loaded tokens |
    listing tokens | family5 verdict | notes. The per-scenario pass rates
    and the canary verdict are the measurement — they ride in the notes
    cell rather than being dropped, since this row has no other place for
    them among the sibling harness's columns."""
    head = next((v for v in output["variants"] if v["variant"] == "head"), None)
    commit = resolved if isinstance(resolved, str) else "path-target"
    mechanical = (head or {}).get("totals", {}).get("scenario_sessions", 0)
    judged = "yes" if output["run"]["judge"] else "no"
    notes = f"live context-layer run, k={output['run']['k']}; {_notes_measurement(output, head)}"
    print(
        "\nEVAL_LOG.md row draft (append to .ai-state/eval_ledger/EVAL_LOG.md):\n"
        f"| {output['run']['finished_at'][:10]} | {commit[:12]} | context-layer-live "
        f"| {mechanical} sessions | {judged} | — | — | — | {notes} |"
    )


def _notes_measurement(output: Mapping[str, Any], head: Mapping[str, Any] | None) -> str:
    selected = output["run"].get("scenarios")
    scenarios = [
        s
        for s in (head or {}).get("scenarios", [])
        if selected is None or s["scenario_id"] in selected
    ]
    rates = "; ".join(f"{s['scenario_id']}={_pct(s['pass_rate'])}" for s in scenarios)
    if selected is not None:
        rates = f"partial run ({', '.join(selected)}); {rates}"
    canary = output.get("canary")
    if canary is None:
        return rates
    verdict = f"lowered={canary['lowered']} (head={_pct(canary['head_pass_rate'])}, canary={_pct(canary['canary_pass_rate'])})"
    return f"{rates}; {verdict}"


def _pct(rate: float | None) -> str:
    return "null" if rate is None else f"{rate:.0%}"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
