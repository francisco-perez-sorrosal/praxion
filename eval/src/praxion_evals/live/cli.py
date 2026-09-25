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

    cd eval && uv run praxion-evals-live --k 3 --canary --dry-run
    cd eval && uv run praxion-evals-live --k 3 --canary --output out.json &

A full run outlives the Bash tool's 10-minute limit; run it detached. A
per-session failure (a judge exception, a fixture-build error) becomes that
one session's error record — it never discards the rest of an already-paid
run; ``run.complete`` is ``False`` whenever that happened.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from praxion_evals.harness.cli import resolve_target
from praxion_evals.harness.families.seeded_scenarios import (
    grade_mechanical,
    judge_scenario,
    load_scenario_fixtures,
)
from praxion_evals.live import report, scenarios
from praxion_evals.live.materialize import (
    CANARY_FILE,
    install_user_scope,
    make_writable,
    materialize_path,
    materialize_ref,
    plant_nonces,
    tree_digest,
)
from praxion_evals.live.report import CREDENTIAL_KEYS, now_iso
from praxion_evals.live.results import (
    Errored,
    Failed,
    NotElicited,
    Outcome,
    Passed,
    capture_to_outcome,
    to_session_record,
)
from praxion_evals.live.session import (
    SessionSpec,
    build_argv,
    build_env,
    classify,
    isolation_breach,
    parse_stream,
    run_session,
    session_error,
)
from praxion_evals.live.spend import RUNNER_SPEND_CAP_USD, SpendLedger

if TYPE_CHECKING:
    from praxion_evals.live.materialize import Materialization, NoncePlant, Variant
    from praxion_evals.live.scenarios import ScenarioSpec
    from praxion_evals.live.session import SessionEnvelope, SessionRun

DEFAULT_OUTPUT = Path(".ai-state/eval_ledger/context_layer_baseline.json")
DEFAULT_K = 3
DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "medium"
PREFLIGHT_MODEL = "sonnet"
PREFLIGHT_BUDGET_USD = 1.0
# Read once, here — the isolation check itself stays pure and takes this in.
REAL_HOME = Path.home()
# Scenarios whose ground truth is a filesystem delta rather than the envelope alone.
_FS_DELTA_SCENARIOS = ("ui-step-conformance", "adr-authoring", "lightweight-fix")
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
    repo_root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    resolved = _resolve_target_or_head(args.target, repo_root)
    if args.dry_run:
        _print_dry_run(args, resolved)
        return 0
    output = _resolve_output(args.output, repo_root)
    if output.exists() and not args.overwrite:
        print(f"{output} exists; pass --overwrite to replace it.")
        return 2
    return _run(args, repo_root, resolved, output)


def _missing_credential(environ: Mapping[str, str]) -> bool:
    return not any(environ.get(key) for key in CREDENTIAL_KEYS)


def _resolve_output(raw: Path | None, repo_root: Path) -> Path:
    """The documented invocation is always ``cd eval && …``; the default must
    not resolve against that cwd, or it lands untracked under ``eval/``."""
    return repo_root / DEFAULT_OUTPUT if raw is None else raw


def _resolve_target_or_head(target: str | None, repo_root: Path) -> Path | str:
    """Unlike ``resolve_target``, an unset target resolves the checkout's
    actual current commit — not ``main``, which can be behind it."""
    if target is None:
        return _git(repo_root, "rev-parse", "HEAD").strip()
    return resolve_target(target, repo_root)


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
    parser.add_argument(
        "--output", type=Path, default=None, help=f"default: <repo root>/{DEFAULT_OUTPUT}"
    )
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
    return {data["scenario_id"]: data for data in load_scenario_fixtures()}


# ---------------------------------------------------------------------------
# Session tasks — one per (variant, scenario, case, repeat)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionTask:
    scenario_id: str
    case_index: int
    case_count: int
    repeat: int
    seeded: Mapping[str, Any]


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
        # of a skill reference under `<copy>/skills/**` is denied. The edit
        # half of the grant is neutralized: the copy is read-only on disk.
        add_dir=plugin_dir,
    )


# ---------------------------------------------------------------------------
# --dry-run — every argv and env key set, nothing spawned
# ---------------------------------------------------------------------------


def _print_dry_run(args: argparse.Namespace, resolved: Path | str) -> None:
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


def _run(args: argparse.Namespace, repo_root: Path, resolved: Path | str, output: Path) -> int:
    run_root = Path(tempfile.mkdtemp(prefix="praxion-evals-live-"))
    started_at = now_iso()
    ledger = SpendLedger(cap_usd=args.max_total_usd)
    fixtures_by_id = _load_fixtures_by_id()
    variant_records: list[dict[str, Any]] = []
    try:
        for variant in ("head", "canary") if args.canary else ("head",):
            record, ledger = _run_variant(
                variant, args, repo_root, resolved, run_root, fixtures_by_id, ledger
            )
            variant_records.append(record)
            if record["isolation_proof"]["status"] != "proven":
                # A canary whose own `lowered` verdict reads null anyway (no
                # HEAD case to compare against) is pure spend for nothing.
                break
    finally:
        if args.keep_sandbox:
            print(f"sandbox kept: {run_root}")
        else:
            make_writable(run_root)  # a read-only copy inside it would refuse rmtree
            shutil.rmtree(run_root, ignore_errors=True)
    data = report.build_output(args, started_at, variant_records, ledger)
    report.write_output(output, data)
    print(f"wrote {output}")
    report.print_eval_log_row(data, resolved)
    return 0


def _run_variant(
    variant: Variant,
    args: argparse.Namespace,
    repo_root: Path,
    resolved: Path | str,
    run_root: Path,
    fixtures_by_id: Mapping[str, Mapping[str, Any]],
    ledger: SpendLedger,
) -> tuple[dict[str, Any], SpendLedger]:
    scenario_copy = _materialize(resolved, repo_root, run_root / f"{variant}-copy", variant)
    # A separate, "identically built" copy for the preflight: nonce planting
    # writes markers into the copy's files, and those must never bleed into
    # the text every scenario session's context actually loads.
    preflight_copy = _materialize(
        resolved, repo_root, run_root / f"{variant}-preflight-copy", variant
    )
    make_writable(preflight_copy.root)  # the copy is read-only on disk once built
    plant = plant_nonces(preflight_copy.root, CANARY_FILE)
    preflight, ledger = _run_preflight(
        preflight_copy, plant, run_root / f"{variant}-preflight", args, ledger
    )
    isolation_proof = _isolation_proof(preflight, plant, copy_root=preflight_copy.root)
    if isolation_proof["status"] != "proven":
        return report.variant_record(variant, scenario_copy, isolation_proof, []), ledger

    tasks = variant_tasks(fixtures_by_id, args.k, variant)
    # Namespaced by variant: two variants sharing one `run_root` must never
    # produce the same session-directory name for their first task.
    session_records, ledger = _run_tasks(
        tasks, scenario_copy, run_root / variant, args, fixtures_by_id, ledger
    )
    # report.py's aggregation core doesn't know about SessionTask (cli.py's
    # own orchestration type) — resolve each record's identity here instead.
    identified = [(task.scenario_id, case_id(task), record) for task, record in session_records]
    return report.variant_record(variant, scenario_copy, isolation_proof, identified), ledger


def _materialize(
    resolved: Path | str, repo_root: Path, dest: Path, variant: Variant
) -> Materialization:
    if isinstance(resolved, Path):
        return materialize_path(resolved, dest, variant)
    return materialize_ref(repo_root, resolved, dest, variant)


# ---------------------------------------------------------------------------
# Preflight — proves isolation once per variant before any scenario runs
# ---------------------------------------------------------------------------


def _run_preflight(
    copy: Materialization,
    plant: NoncePlant,
    session_root: Path,
    args: argparse.Namespace,
    ledger: SpendLedger,
) -> tuple[dict[str, Any] | None, SpendLedger]:
    """Run the one preflight session; ``None`` means the run-level cap refused it."""
    admitted, ledger = _reserve(ledger, PREFLIGHT_BUDGET_USD)
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
    ledger = _settle(ledger, PREFLIGHT_BUDGET_USD, envelope)
    return {"run": run, "envelope": envelope}, ledger


def _preflight_prompt(plant: NoncePlant) -> str:
    prefix = next(iter(plant.markers().values())).rsplit("-", 2)[0]
    return (
        f"Reply with nothing but every marker string of the form {prefix}-<SURFACE>-<hex> "
        "that appears anywhere in your context layer, one per line."
    )


def _isolation_proof(
    preflight: dict[str, Any] | None, plant: NoncePlant, *, copy_root: Path
) -> dict[str, Any]:
    """Telemetry-first, like every scenario session's check: echoing all four
    nonces proves the target layer loaded, not that nothing else did."""
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
    breach = isolation_breach(envelope, copy_root)
    if kind is not None or missing or breach is not None:
        detail = kind or breach or f"missing markers: {missing}"
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
) -> tuple[list[tuple[SessionTask, dict[str, Any]]], SpendLedger]:
    """Sequential by design: session order stays reproducible in the JSON, and
    the run-level spend cap must see one committed decision at a time."""
    records: list[tuple[SessionTask, dict[str, Any]]] = []
    for index, task in enumerate(tasks):
        session_root = run_root / f"{case_id(task)}-{task.repeat}-{index}"
        record, ledger = _run_one_session(task, copy, session_root, args, fixtures_by_id, ledger)
        records.append((task, record))
    if tree_digest(copy.root) != copy.tree_digest:
        # The read-only permission is the primary guard; this is the
        # detection backstop for whatever bypasses it (a bug, a permissive
        # tool). A mutated copy invalidates every session this variant ran.
        records = [
            (
                task,
                to_session_record(
                    Errored(kind="isolation_breach", detail="materialization mutated"),
                    repeat=task.repeat,
                ),
            )
            for task, _ in records
        ]
    return records, ledger


def _run_one_session(
    task: SessionTask,
    copy: Materialization,
    session_root: Path,
    args: argparse.Namespace,
    fixtures_by_id: Mapping[str, Mapping[str, Any]],
    ledger: SpendLedger,
) -> tuple[dict[str, Any], SpendLedger]:
    spec_def = scenarios.SCENARIOS[task.scenario_id]
    admitted, ledger = _reserve(ledger, spec_def.max_budget_usd)
    if isinstance(admitted, Errored):
        return to_session_record(admitted, repeat=task.repeat), ledger
    ledger = admitted
    envelope: SessionEnvelope | None = None
    settled = False
    try:
        install_user_scope(copy.root, session_root)
        fixture = session_root / "fixture"
        spec_def.build_fixture(fixture, task.seeded)
        before = scenarios.snapshot(fixture) if task.scenario_id in _FS_DELTA_SCENARIOS else None
        # commit-staging's ground truth is the commit history, not file
        # content: the seeded working tree already differs from HEAD before
        # the session runs, so a content snapshot would show no delta.
        baseline_sha = (
            _git(fixture, "rev-parse", "HEAD").strip()
            if task.scenario_id == "commit-staging"
            else None
        )
        spec = build_spec(task, copy.root, session_root, args.model, args.effort)
        run = run_session(spec, build_env(session_root, os.environ))
        envelope = parse_stream(run.stdout)
        ledger = _settle(ledger, spec_def.max_budget_usd, envelope)
        settled = True
        outcome = _evaluate(
            task,
            spec_def,
            copy.root,
            run,
            envelope,
            fixture,
            before,
            fixtures_by_id,
            args,
            baseline_sha=baseline_sha,
        )
    except Exception as exc:  # a fixture/judge/infra failure becomes this session's record,
        # never aborts a run that already paid for every other session.
        if not settled:
            ledger = _settle(ledger, spec_def.max_budget_usd, None)
        outcome = Errored(kind="evaluation_exception", detail=f"{type(exc).__name__}: {exc}")
    record = to_session_record(outcome, repeat=task.repeat)
    if envelope is not None:
        record |= _session_metrics(envelope)
    return record, ledger


def _session_metrics(envelope: SessionEnvelope) -> dict[str, Any]:
    result, init = envelope.final_result, envelope.init
    return {
        "cost_usd": result.total_cost_usd if result else None,
        "model_resolved": init.model if init else None,
        "num_turns": result.num_turns if result else None,
        "duration_ms": result.duration_ms if result else None,
        "permission_denials": result.permission_denials if result else None,
        "usage": _usage(result.usage) if result else None,
    }


def _usage(usage: Mapping[str, Any] | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "input": usage.get("input_tokens", 0),
        "output": usage.get("output_tokens", 0),
        "cache_creation": usage.get("cache_creation_input_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
    }


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
    *,
    baseline_sha: str | None = None,
) -> Outcome:
    error = session_error(envelope, run, copy_root, real_home=REAL_HOME)
    if error is not None:
        return error
    if spec_def.requires_structured_output and not _has_structured_output(envelope):
        return Errored(kind="structured_output_missing", detail="no structured_output reported")
    fs_delta = None
    if before is not None:
        fs_delta = scenarios.compute_fs_delta(before, scenarios.snapshot(fixture))
    elif baseline_sha is not None:
        fs_delta = scenarios.commit_fs_delta(fixture, baseline_sha)
    capture = spec_def.capture(envelope, fs_delta, task.seeded)
    if isinstance(capture, NotElicited):
        return capture_to_outcome(capture)
    data = _graded_data(task, fixtures_by_id[task.scenario_id], capture.value)
    passed, findings = (spec_def.mechanical_check or grade_mechanical)(data)
    if not passed:
        return Failed(kind="graded", recorded=capture.value, findings=tuple(findings))
    if not args.judge:
        return Passed(recorded=capture.value, findings=tuple(findings))
    # Deliberately not hoisted: `from X import Y` binds a snapshot at import
    # time, and tests monkeypatch `judge_client.select_judge_client` on the
    # module object — a module-level binding here would not observe that.
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


def _reserve(ledger: SpendLedger, budget_usd: float) -> tuple[SpendLedger | Errored, SpendLedger]:
    admitted = ledger.reserve(budget_usd)
    if isinstance(admitted, Errored):
        return admitted, ledger
    return admitted, admitted


def _settle(
    ledger: SpendLedger, budget_usd: float, envelope: SessionEnvelope | None
) -> SpendLedger:
    cost = envelope.final_result.total_cost_usd if envelope and envelope.final_result else None
    return ledger.settle(budget_usd, cost)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


if __name__ == "__main__":
    sys.exit(main())
