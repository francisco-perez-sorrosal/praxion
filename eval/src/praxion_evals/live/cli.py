#!/usr/bin/env python3
"""``praxion-evals-live``: live-capture the seeded context-layer scenarios.

For each variant (HEAD, and — with ``--canary`` — a degraded copy) this
materializes the target, proves isolation once with a nonce preflight, then
runs ``k`` fresh sandboxed ``claude -p`` sessions per case, captures each
session's observable through :mod:`praxion_evals.live.scenarios`, grades it
through the harness's own seam, and writes one baseline JSON. Every paid
session is opt-in: this console entry is the *only* way to reach one — never
``/eval-praxion``, a hook, or CI (structurally: no other module here imports
this one).

    cd eval && uv run praxion-evals-live main --k 3 --canary --dry-run
    cd eval && uv run praxion-evals-live main --k 3 --canary --output out.json &

A full run outlives the Bash tool's 10-minute limit; run it detached.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from praxion_evals.harness.cli import resolve_target
from praxion_evals.harness.families.seeded_scenarios import grade_mechanical, judge_scenario
from praxion_evals.live import scenarios
from praxion_evals.live.spend import RUNNER_SPEND_CAP_USD

if TYPE_CHECKING:
    from praxion_evals.live.materialize import Materialization, Variant
    from praxion_evals.live.results import Outcome
    from praxion_evals.live.scenarios import ScenarioSpec
    from praxion_evals.live.session import SessionEnvelope, SessionRun
    from praxion_evals.live.spend import SpendLedger

CREDENTIAL_KEYS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN")
DEFAULT_OUTPUT = Path(".ai-state/eval_ledger/context_layer_baseline.json")
DEFAULT_K = 3
DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "medium"
PREFLIGHT_MODEL = "sonnet"
PREFLIGHT_BUDGET_USD = 1.0
RUNNER_VERSION = "praxion-evals-live 0.37.0"
HEAD_RULE_RELPATH = "rules/swe/agent-behavioral-contract.md"
# Scenarios whose ground truth is a filesystem delta rather than the envelope alone.
_FS_DELTA_SCENARIOS = ("adr-authoring", "lightweight-fix")
# The recorded_* field each non-spawn-selection scenario's graded copy replaces.
_RECORDED_FIELD = {
    "ui-step-conformance": "recorded_output",
    "adr-authoring": "adr_fragment",
    "commit-staging": "recorded_command",
    "lightweight-fix": "recorded_artifacts_written",
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if _missing_credential(os.environ):
        print(f"No credential in the environment; set one of {', '.join(CREDENTIAL_KEYS)}.")
        return 2
    if args.output.exists() and not args.overwrite:
        print(f"{args.output} exists; pass --overwrite to replace it.")
        return 2
    repo_root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    resolved = resolve_target(args.target, repo_root)
    if args.dry_run:
        _print_dry_run(args, resolved)
        return 0
    return _run(args, repo_root, resolved)


def _missing_credential(environ: Mapping[str, str]) -> bool:
    return not any(environ.get(key) for key in CREDENTIAL_KEYS)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live-capture the seeded context-layer scenarios (spends API money)."
    )
    parser.add_argument(
        "target", nargs="?", default=None, help="git ref, sha, or path; default HEAD"
    )
    parser.add_argument("--k", type=_positive_int, default=DEFAULT_K)
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--max-total-usd", type=float, default=RUNNER_SPEND_CAP_USD)
    parser.add_argument("--keep-sandbox", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return value


def _load_fixtures_by_id() -> dict[str, dict[str, Any]]:
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures

    return {data["scenario_id"]: data for data in load_scenario_fixtures()}


# ---------------------------------------------------------------------------
# Session tasks — one per (variant, scenario, case, repeat)
# ---------------------------------------------------------------------------


class SessionTask:
    __slots__ = ("scenario_id", "case_index", "case_count", "repeat", "seeded")

    def __init__(
        self,
        scenario_id: str,
        case_index: int,
        case_count: int,
        repeat: int,
        seeded: Mapping[str, Any],
    ) -> None:
        self.scenario_id = scenario_id
        self.case_index = case_index
        self.case_count = case_count
        self.repeat = repeat
        self.seeded = seeded


def case_id(task: SessionTask) -> str:
    return task.scenario_id if task.case_count == 1 else f"{task.scenario_id}#{task.case_index}"


def build_tasks(fixtures_by_id: Mapping[str, Mapping[str, Any]], k: int) -> list[SessionTask]:
    """One task per (scenario, case, repeat) across every scenario, in a fixed order."""
    tasks: list[SessionTask] = []
    for scenario_id in scenarios.SCENARIOS:
        data = fixtures_by_id[scenario_id]
        cases = data["cases"] if scenario_id == "spawn-selection" else [data]
        for case_index, case in enumerate(cases, start=1):
            tasks.extend(
                SessionTask(scenario_id, case_index, len(cases), repeat, case)
                for repeat in range(1, k + 1)
            )
    return tasks


# The canary tests the tier/agent-selection guard specifically; the other
# four scenarios make no claim about the section it degrades.
CANARY_SCENARIOS = ("spawn-selection",)


def variant_tasks(
    fixtures_by_id: Mapping[str, Mapping[str, Any]], k: int, variant: Variant
) -> list[SessionTask]:
    tasks = build_tasks(fixtures_by_id, k)
    if variant == "canary":
        return [t for t in tasks if t.scenario_id in CANARY_SCENARIOS]
    return tasks


def build_spec(task: SessionTask, plugin_dir: Path, session_root: Path, model: str, effort: str):
    from praxion_evals.live.session import SessionSpec

    spec_def = scenarios.SCENARIOS[task.scenario_id]
    return SessionSpec(
        prompt=spec_def.prompt(task.seeded),
        model=model,
        effort=effort,
        plugin_dir=plugin_dir,
        cwd=session_root / "fixture",
        permission_mode=spec_def.permission_mode,
        max_budget_usd=spec_def.max_budget_usd,
        allowed_tools=spec_def.allowed_tools,
        json_schema=spec_def.json_schema,
        forward_subagent_text=spec_def.forward_subagent_text,
        # The plugin copy lies outside the session's cwd; without this, Read
        # of a skill reference under `<copy>/skills/**` is denied.
        add_dir=plugin_dir,
    )


# ---------------------------------------------------------------------------
# --dry-run — every argv and env key set, nothing spawned
# ---------------------------------------------------------------------------


def _print_dry_run(args: argparse.Namespace, resolved: Path | str) -> None:
    from praxion_evals.live.session import build_argv, build_env

    run_root = Path(tempfile.gettempdir()) / "praxion-evals-live-<run>"
    print(f"target: {args.target or 'HEAD'} -> {resolved} (materialized into {run_root}/head-copy)")
    fixtures_by_id = _load_fixtures_by_id()
    for variant in ("head", "canary") if args.canary else ("head",):
        representative = [
            task for task in variant_tasks(fixtures_by_id, args.k, variant) if task.repeat == 1
        ]
        for task in representative:
            session_root = run_root / f"{variant}-{case_id(task)}"
            spec = build_spec(
                task, run_root / f"{variant}-copy", session_root, args.model, args.effort
            )
            argv = build_argv(spec)
            env_keys = sorted(build_env(session_root, os.environ))
            print(f"\n[{variant} {case_id(task)}]\n  argv: {argv}\n  env keys: {env_keys}")


# ---------------------------------------------------------------------------
# The paid run
# ---------------------------------------------------------------------------


def _run(args: argparse.Namespace, repo_root: Path, resolved: Path | str) -> int:
    from praxion_evals.live.spend import SpendLedger

    run_root = Path(tempfile.mkdtemp(prefix="praxion-evals-live-"))
    started_at = _now_iso()
    ledger = SpendLedger(cap_usd=args.max_total_usd)
    lock = threading.Lock()
    fixtures_by_id = _load_fixtures_by_id()
    variant_records: list[dict[str, Any]] = []
    try:
        for variant in ("head", "canary") if args.canary else ("head",):
            record, ledger = _run_variant(
                variant, args, repo_root, resolved, run_root, fixtures_by_id, ledger, lock
            )
            variant_records.append(record)
    finally:
        if args.keep_sandbox:
            print(f"sandbox kept: {run_root}")
        else:
            shutil.rmtree(run_root, ignore_errors=True)
    output = _build_output(args, started_at, variant_records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    _print_eval_log_row(output)
    return 0


def _run_variant(
    variant: Variant,
    args: argparse.Namespace,
    repo_root: Path,
    resolved: Path | str,
    run_root: Path,
    fixtures_by_id: Mapping[str, Mapping[str, Any]],
    ledger: SpendLedger,
    lock: threading.Lock,
) -> tuple[dict[str, Any], SpendLedger]:
    from praxion_evals.live.materialize import plant_nonces

    scenario_copy = _materialize(resolved, repo_root, run_root / f"{variant}-copy", variant)
    # A separate, "identically built" copy for the preflight: nonce planting
    # writes markers into the copy's files, and those must never bleed into
    # the text every scenario session's context actually loads.
    preflight_copy = _materialize(
        resolved, repo_root, run_root / f"{variant}-preflight-copy", variant
    )
    plant = plant_nonces(preflight_copy.root, _rule_relpath(variant))
    preflight, ledger = _run_preflight(
        preflight_copy, plant, run_root / f"{variant}-preflight", args, ledger, lock
    )
    isolation_proof = _isolation_proof(preflight, plant)
    if isolation_proof["status"] != "proven":
        return _variant_record(variant, scenario_copy, isolation_proof, []), ledger

    tasks = variant_tasks(fixtures_by_id, args.k, variant)
    session_records, ledger = _run_tasks(
        tasks, scenario_copy, run_root, args, fixtures_by_id, ledger, lock
    )
    return _variant_record(variant, scenario_copy, isolation_proof, session_records), ledger


def _rule_relpath(variant: Variant) -> str:
    from praxion_evals.live.materialize import CANARY_FILE

    return CANARY_FILE if variant == "canary" else HEAD_RULE_RELPATH


def _materialize(
    resolved: Path | str, repo_root: Path, dest: Path, variant: Variant
) -> Materialization:
    from praxion_evals.live.materialize import materialize_path, materialize_ref

    if isinstance(resolved, Path):
        return materialize_path(resolved, dest, variant)
    return materialize_ref(repo_root, resolved, dest, variant)


# ---------------------------------------------------------------------------
# Preflight — proves isolation once per variant before any scenario runs
# ---------------------------------------------------------------------------


def _run_preflight(
    copy: Materialization,
    plant: Any,
    session_root: Path,
    args: argparse.Namespace,
    ledger: SpendLedger,
    lock: threading.Lock,
) -> tuple[dict[str, Any] | None, SpendLedger]:
    """Run the one preflight session; ``None`` means the run-level cap refused it."""
    from praxion_evals.live.materialize import install_user_scope
    from praxion_evals.live.results import Errored
    from praxion_evals.live.session import SessionSpec, build_env, parse_stream, run_session

    admitted, ledger = _reserve(ledger, lock, PREFLIGHT_BUDGET_USD)
    if isinstance(admitted, Errored):
        return None, ledger
    install_user_scope(copy.root, session_root)
    fixture = session_root / "fixture"
    fixture.mkdir(parents=True)
    spec = SessionSpec(
        prompt=_preflight_prompt(plant),
        model=PREFLIGHT_MODEL,
        effort=args.effort,
        plugin_dir=copy.root,
        cwd=fixture,
        permission_mode="default",
        max_budget_usd=PREFLIGHT_BUDGET_USD,
        add_dir=copy.root,
    )
    run = run_session(spec, build_env(session_root, os.environ))
    envelope = parse_stream(run.stdout)
    ledger = _settle(ledger, lock, PREFLIGHT_BUDGET_USD, envelope)
    return {"run": run, "envelope": envelope}, ledger


def _preflight_prompt(plant: Any) -> str:
    prefix = next(iter(plant.markers().values())).rsplit("-", 2)[0]
    return (
        f"Reply with nothing but every marker string of the form {prefix}-<SURFACE>-<hex> "
        "that appears anywhere in your context layer, one per line."
    )


def _isolation_proof(preflight: dict[str, Any] | None, plant: Any) -> dict[str, Any]:
    from praxion_evals.live.session import classify

    if preflight is None:
        return {
            "status": "failed",
            "model": PREFLIGHT_MODEL,
            "detail": "run-level budget exhausted",
        }
    run, envelope = preflight["run"], preflight["envelope"]
    kind = classify(envelope, run.exit_code, run.timed_out)
    text = envelope.final_result.result_text if envelope.final_result else None
    missing = plant.missing_from(text or "")
    if kind is not None or missing:
        detail = kind or f"missing markers: {missing}"
        return {"status": "failed", "model": PREFLIGHT_MODEL, "detail": detail}
    init = envelope.init
    return {
        "status": "proven",
        "model": init.model if init else None,
        "markers": dict.fromkeys(plant.markers(), "present"),
        "plugins": [p.get("source") for p in init.plugins] if init else [],
        "mcp_servers": list(init.mcp_servers) if init else [],
        "auth_source": init.api_key_source if init else None,
        "cost_usd": envelope.final_result.total_cost_usd if envelope.final_result else None,
    }


# ---------------------------------------------------------------------------
# Scenario sessions
# ---------------------------------------------------------------------------


def _run_tasks(
    tasks: Sequence[SessionTask],
    copy: Materialization,
    run_root: Path,
    args: argparse.Namespace,
    fixtures_by_id: Mapping[str, Mapping[str, Any]],
    ledger: SpendLedger,
    lock: threading.Lock,
) -> tuple[list[tuple[SessionTask, dict[str, Any]]], SpendLedger]:
    """Sequential by design: session order stays reproducible in the JSON, and
    the run-level spend cap must see one committed decision at a time."""
    records: list[tuple[SessionTask, dict[str, Any]]] = []
    for index, task in enumerate(tasks):
        session_root = run_root / f"{case_id(task)}-{task.repeat}-{index}"
        record, ledger = _run_one_session(
            task, copy, session_root, args, fixtures_by_id, ledger, lock
        )
        records.append((task, record))
    return records, ledger


def _run_one_session(
    task: SessionTask,
    copy: Materialization,
    session_root: Path,
    args: argparse.Namespace,
    fixtures_by_id: Mapping[str, Mapping[str, Any]],
    ledger: SpendLedger,
    lock: threading.Lock,
) -> tuple[dict[str, Any], SpendLedger]:
    from praxion_evals.live.materialize import install_user_scope
    from praxion_evals.live.results import Errored, to_session_record
    from praxion_evals.live.session import build_env, parse_stream, run_session

    spec_def = scenarios.SCENARIOS[task.scenario_id]
    admitted, ledger = _reserve(ledger, lock, spec_def.max_budget_usd)
    if isinstance(admitted, Errored):
        return to_session_record(admitted, repeat=task.repeat), ledger
    install_user_scope(copy.root, session_root)
    fixture = session_root / "fixture"
    spec_def.build_fixture(fixture, task.seeded)
    before = scenarios.snapshot(fixture) if task.scenario_id in _FS_DELTA_SCENARIOS else None
    spec = build_spec(task, copy.root, session_root, args.model, args.effort)
    run = run_session(spec, build_env(session_root, os.environ))
    envelope = parse_stream(run.stdout)
    ledger = _settle(ledger, lock, spec_def.max_budget_usd, envelope)
    outcome = _evaluate(
        task, spec_def, copy.root, run, envelope, fixture, before, fixtures_by_id, args
    )
    return to_session_record(outcome, repeat=task.repeat), ledger


def _evaluate(
    task: SessionTask,
    spec_def: ScenarioSpec,
    copy_root: Path,
    run: SessionRun,
    envelope: SessionEnvelope,
    fixture: Path,
    before: dict[str, tuple[str, str]] | None,
    fixtures_by_id: Mapping[str, Mapping[str, Any]],
    args: argparse.Namespace,
) -> Outcome:
    from praxion_evals.live.results import Errored, Failed, NotElicited, Passed, capture_to_outcome
    from praxion_evals.live.session import session_error

    error = session_error(envelope, run, copy_root)
    if error is not None:
        return error
    if spec_def.requires_structured_output and not _has_structured_output(envelope):
        return Errored(kind="structured_output_missing", detail="no structured_output reported")
    fs_delta = (
        scenarios.compute_fs_delta(before, scenarios.snapshot(fixture))
        if before is not None
        else None
    )
    capture = spec_def.capture(envelope, fs_delta, task.seeded)
    if isinstance(capture, NotElicited):
        return capture_to_outcome(capture)
    data = _graded_data(task, fixtures_by_id[task.scenario_id], capture.value)
    passed, findings = grade_mechanical(data)
    if not passed:
        return Failed(kind="graded", recorded=capture.value, findings=tuple(findings))
    if not args.judge:
        return Passed(recorded=capture.value, findings=tuple(findings))
    from praxion_evals.harness.judge_client import select_judge_client

    verdict = judge_scenario(data, select_judge_client())
    judged_findings = (*findings, *verdict.findings)
    if verdict.verdict == "FAIL":
        return Failed(kind="graded", recorded=capture.value, findings=judged_findings)
    return Passed(recorded=capture.value, findings=judged_findings)


def _has_structured_output(envelope: SessionEnvelope) -> bool:
    result = envelope.final_result
    return bool(
        result and isinstance(result.structured_output, Mapping) and result.structured_output
    )


def _graded_data(task: SessionTask, fixture_yaml: Mapping[str, Any], value: Any) -> dict[str, Any]:
    """A deep-enough copy of the frozen fixture with only ``recorded_*`` replaced."""
    if task.scenario_id == "spawn-selection":
        case = dict(fixture_yaml["cases"][task.case_index - 1])
        case["recorded_tier"] = value["recorded_tier"]
        case["recorded_agents"] = value["recorded_agents"]
        return {**fixture_yaml, "cases": [case]}
    return {**fixture_yaml, _RECORDED_FIELD[task.scenario_id]: value}


# ---------------------------------------------------------------------------
# Spend guard — one ledger, serialized across every launch in the run
# ---------------------------------------------------------------------------


def _reserve(
    ledger: SpendLedger, lock: threading.Lock, budget_usd: float
) -> tuple[SpendLedger | Any, SpendLedger]:
    with lock:
        admitted = ledger.reserve(budget_usd)
    from praxion_evals.live.results import Errored

    if isinstance(admitted, Errored):
        return admitted, ledger
    return admitted, admitted


def _settle(
    ledger: SpendLedger, lock: threading.Lock, budget_usd: float, envelope: SessionEnvelope
) -> SpendLedger:
    cost = envelope.final_result.total_cost_usd if envelope.final_result else None
    with lock:
        return ledger.settle(budget_usd, cost)


# ---------------------------------------------------------------------------
# Aggregation and output
# ---------------------------------------------------------------------------


def _variant_record(
    variant: Variant,
    copy: Materialization,
    isolation_proof: dict[str, Any],
    session_records: Sequence[tuple[SessionTask, dict[str, Any]]],
) -> dict[str, Any]:
    from praxion_evals.live.results import compute_pass_rate

    by_scenario: dict[str, list[tuple[SessionTask, dict[str, Any]]]] = {}
    for task, record in session_records:
        by_scenario.setdefault(task.scenario_id, []).append((task, record))

    scenario_blocks = []
    for scenario_id in scenarios.SCENARIOS:
        by_case: dict[str, list[dict[str, Any]]] = {}
        for task, record in by_scenario.get(scenario_id, []):
            by_case.setdefault(case_id(task), []).append(record)
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
        "totals": _totals(session_records),
    }


def _case_block(one_case_id: str, session_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    from praxion_evals.live.results import compute_pass_rate

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


def _totals(session_records: Sequence[tuple[SessionTask, dict[str, Any]]]) -> dict[str, Any]:
    errors = sum(1 for _, record in session_records if record["outcome"] == "error")
    return {"scenario_sessions": len(session_records), "errors": errors}


def _target_json(target: Any) -> dict[str, Any]:
    from praxion_evals.live.materialize import PathTarget, RefTarget

    if isinstance(target, RefTarget):
        return {"kind": "ref", "ref": target.ref, "sha": target.sha}
    if isinstance(target, PathTarget):
        return {
            "kind": "path",
            "path": target.path,
            "head_sha": target.head_sha,
            "dirty": target.dirty,
        }
    raise TypeError(f"unrecognized target identity: {target!r}")


def _degradation_json(degradation: Any) -> dict[str, Any] | None:
    if degradation is None:
        return None
    return {
        "file": degradation.file,
        "heading": degradation.heading,
        "removed_bytes": degradation.removed_bytes,
        "sha256_before": degradation.sha256_before,
        "sha256_after": degradation.sha256_after,
    }


def _build_output(
    args: argparse.Namespace, started_at: str, variant_records: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    from praxion_evals.live.results import compute_lowered

    canary_block = None
    if args.canary and len(variant_records) == 2:
        head_rate = _spawn_selection_pass_rate(variant_records[0])
        canary_rate = _spawn_selection_pass_rate(variant_records[1])
        canary_block = {
            "scenario_id": "spawn-selection",
            "head_pass_rate": head_rate,
            "canary_pass_rate": canary_rate,
            "delta": None if head_rate is None or canary_rate is None else canary_rate - head_rate,
            "lowered": compute_lowered(head_rate=head_rate, canary_rate=canary_rate),
        }
    return {
        "schema_version": 1,
        "run": {
            "started_at": started_at,
            "finished_at": _now_iso(),
            "runner": RUNNER_VERSION,
            "model": {"requested": args.model, "resolved": _resolved_models(variant_records)},
            "effort": args.effort,
            "k": args.k,
            "judge": {"model": "claude-haiku-4-5"} if args.judge else None,
        },
        "variants": variant_records,
        "canary": canary_block,
    }


def _spawn_selection_pass_rate(variant_record: Mapping[str, Any]) -> float | None:
    scenario = next(
        (s for s in variant_record["scenarios"] if s["scenario_id"] == "spawn-selection"), None
    )
    return scenario["pass_rate"] if scenario else None


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


def _print_eval_log_row(output: Mapping[str, Any]) -> None:
    head = next((v for v in output["variants"] if v["variant"] == "head"), None)
    pass_rates = [s["pass_rate"] for s in head["scenarios"]] if head else []
    print(
        "\nEVAL_LOG.md row draft:\n"
        f"| {output['run']['finished_at']} | context-layer-live | "
        f"k={output['run']['k']} | pass_rates={pass_rates} | "
        f"canary_lowered={(output['canary'] or {}).get('lowered')} |"
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


if __name__ == "__main__":
    sys.exit(main())
