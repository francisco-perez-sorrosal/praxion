"""Collector orchestration: registry, two-pass lifecycle, error isolation, timeout.

The runner threads a fleet of registered `Collector` instances through two
passes and produces a partially-populated `schema.Report`:

1. **Resolve pass** — call `resolve()` on every registered collector. The
   result populates `tool_availability[name]` via `to_tool_availability_json`.
   Collectors whose resolution is `Unavailable` or `NotApplicable` get a 3-key
   skip marker in `collectors[name]` via `skip_marker_for_namespace`; their
   `collect()` is never called. If a *required* collector (`required=True`, set
   only on the hard-floor `GitCollector`) resolves `Unavailable`, the run
   aborts — no meaningful report can exist without the hard-floor tool.

2. **Collect pass** — call `collect(ctx)` on every Available collector, in
   registration order. Each invocation is wrapped in a thread-enforced timeout
   and a `BaseException` catch. A non-required collector that raises or times
   out downgrades to `status='error'` / `status='timeout'` in
   `tool_availability` and a same-shape namespace block; the run continues.
   A required collector that raises propagates out of `run()` — the runner
   must not silently continue past a hard-floor failure.

The runner produces a **partial aggregate**: `commit_sha`, `timestamp`, and
`window_days` are populated from the injected git probe and the caller's
kwarg; the other 13 aggregate columns are filled with type-appropriate
"empty" sentinels (0, 0.0, or None) and are finalized by the composition
layers (hotspot/trends/report) downstream.

The registry is an ordered list of `Collector` instances. Registration order
is authoritative — the runner does not sort by name, tier, or any other key.
"""

from __future__ import annotations

import subprocess
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.project_metrics import schema
from scripts.project_metrics.collectors.base import (
    Available,
    Collector,
    CollectionContext,
    CollectorResult,
    NotApplicable,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
    skip_marker_for_namespace,
    to_tool_availability_json,
)

__all__ = ["CollectorRegistry", "Runner", "default_registry"]


# ---------------------------------------------------------------------------
# Constants — tunables that must not drift silently.
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT_SECONDS: float = 120.0
_TRACEBACK_EXCERPT_MAX_CHARS: int = 8192
_GIT_PROBE_TIMEOUT_SECONDS: float = 10.0


# ---------------------------------------------------------------------------
# Registry — ordered list of collector instances.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectorRegistry:
    """Ordered, immutable registry of collector instances.

    Registration order is the execution order used by the runner in both
    passes. Consumers iterate `.collectors`; the runner never reorders.

    The dataclass is frozen so a registry handed to the runner cannot be
    mutated mid-run; subclasses that need additional behavior wrap a fresh
    `CollectorRegistry` rather than mutating the list in place.
    """

    collectors: list[Collector] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers — traceback truncation and timeout-enforced invocation.
# ---------------------------------------------------------------------------


def _format_truncated_traceback(exc: BaseException) -> str:
    """Format `exc`'s traceback and truncate to the public char bound.

    The graceful-degradation ADR caps `traceback_excerpt` so a pathological
    deep-chain exception cannot flood the JSON artifact. Truncation appends a
    marker so readers know the excerpt was cut; the excerpt is informational
    (for debugging) not load-bearing (no parser downstream).
    """

    raw = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if len(raw) <= _TRACEBACK_EXCERPT_MAX_CHARS:
        return raw
    marker = "\n...[truncated]"
    keep = _TRACEBACK_EXCERPT_MAX_CHARS - len(marker)
    return raw[:keep] + marker


def _run_collect_with_timeout(
    collector: Collector,
    ctx: CollectionContext,
    timeout_seconds: float,
) -> tuple[str, CollectorResult | None, BaseException | None]:
    """Invoke `collector.collect(ctx)` with a thread-enforced deadline.

    Returns a 3-tuple `(outcome, result, exc)` where `outcome` is one of:

    * `"ok"` — `collect()` returned a `CollectorResult`; `result` is set.
    * `"error"` — `collect()` raised; `exc` is the caught exception.
    * `"timeout"` — deadline elapsed; the worker thread is orphaned (daemon)
      and `result` / `exc` are both `None`.

    A daemon thread is used so an orphaned in-flight `collect()` cannot block
    interpreter shutdown. `threading.Thread` with `join(timeout=...)` is the
    simplest stdlib primitive that yields the required semantics; a
    `ThreadPoolExecutor` would work too but its non-daemon worker pool can
    delay pytest shutdown when a collector sleeps past its deadline.
    """

    container: dict[str, Any] = {}

    def _worker() -> None:
        try:
            container["result"] = collector.collect(ctx)
        except BaseException as worker_exc:  # noqa: BLE001 — captured for caller
            container["exc"] = worker_exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    if thread.is_alive():
        return "timeout", None, None
    if "exc" in container:
        return "error", None, container["exc"]
    return "ok", container["result"], None


# ---------------------------------------------------------------------------
# Git probe — default implementation + injection point.
# ---------------------------------------------------------------------------


def _default_git_probe() -> tuple[str, str]:
    """Resolve (HEAD SHA, current UTC ISO-8601 timestamp).

    Invoked once at start-of-run to stamp the aggregate's run_id coordinates.
    Fails loud on missing `git` or a detached/broken repo — the runner relies
    on these two values being honest, and a silent fallback would produce a
    confusing artifact. Callers that need a different behavior (tests, CI)
    inject their own probe via the `git_probe` kwarg.
    """

    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=_GIT_PROBE_TIMEOUT_SECONDS,
    )
    sha = completed.stdout.strip()
    timestamp = datetime.now(timezone.utc).isoformat()
    return sha, timestamp


# ---------------------------------------------------------------------------
# Runner — two-pass orchestrator.
# ---------------------------------------------------------------------------


class Runner:
    """Two-pass orchestrator over a `CollectorRegistry`.

    Constructor takes all kwargs so tests can inject any of them in isolation:

    * `registry` — the ordered list of collectors to execute. Required.
    * `default_timeout_seconds` — per-collector `collect()` deadline. Default
      120.0 matches the SYSTEMS_PLAN risk register.
    * `git_probe` — zero-arg callable returning `(sha, iso_timestamp)`. Default
      invokes `git rev-parse HEAD` + `datetime.now(UTC).isoformat()`.

    `run(window_days, top_n)` returns a `schema.Report` with:

    * `tool_availability[name]` populated for every registered collector
      (one of the 5 status literals per graceful-degradation ADR).
    * `collectors[name]` populated with either the `CollectorResult` from a
      successful `collect()`, or a 3-key namespace skip/error marker.
    * `aggregate` partially populated: `commit_sha`, `timestamp`,
      `window_days`, and `schema_version` carry real values; the other 12
      columns carry type-appropriate empty sentinels, to be filled by the
      composition layers downstream.
    * `hotspots`, `trends`, `run_metadata` at schema defaults — the runner
      is explicitly not responsible for composing these.

    A required collector (`collector.required == True`) that fails fast is
    the only path that aborts `run()`. Non-required failures downgrade.
    """

    def __init__(
        self,
        *,
        registry: CollectorRegistry,
        default_timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        git_probe: Callable[[], tuple[str, str]] | None = None,
    ) -> None:
        self._registry = registry
        self._default_timeout_seconds = default_timeout_seconds
        self._git_probe = git_probe if git_probe is not None else _default_git_probe

    def run(self, *, window_days: int, top_n: int) -> schema.Report:
        """Execute both passes and return the partially-populated report.

        `top_n` is accepted here for contract stability — the runner does not
        use it (it is a composition-layer concern) but the CLI always supplies
        it, and a runner that silently drops it would create a split API
        between direct callers and the CLI. We forward it to nothing today;
        the hotspot composer consumes it once composition layers thread
        through the Report.
        """

        del top_n  # forwarded by caller; not used at runner layer.

        sha, timestamp = self._git_probe()
        env = ResolutionEnv()
        ctx = CollectionContext(
            repo_root=".",
            window_days=window_days,
            git_sha=sha,
        )

        tool_availability: dict[str, schema.ToolAvailability] = {}
        collectors_map: dict[str, Any] = {}

        resolutions = self._run_resolve_pass(env, tool_availability, collectors_map)
        self._run_collect_pass(ctx, resolutions, tool_availability, collectors_map)

        aggregate = _build_partial_aggregate(
            commit_sha=sha, timestamp=timestamp, window_days=window_days
        )
        return schema.Report(
            schema_version=schema.SCHEMA_VERSION,
            aggregate=aggregate,
            tool_availability=tool_availability,
            collectors=collectors_map,
        )

    # -- Pass 1 ------------------------------------------------------------

    def _run_resolve_pass(
        self,
        env: ResolutionEnv,
        tool_availability: dict[str, schema.ToolAvailability],
        collectors_map: dict[str, Any],
    ) -> dict[str, ResolutionResult]:
        """Call `resolve()` on every collector; populate availability + skip markers.

        Returns a map of `name -> ResolutionResult` that the collect pass
        consults to decide whether to invoke `collect()`. A required
        collector that resolves `Unavailable` aborts the run here rather
        than waiting for the collect pass to notice.
        """

        resolutions: dict[str, ResolutionResult] = {}
        for collector in self._registry.collectors:
            name = collector.name
            result = collector.resolve(env)
            resolutions[name] = result
            tool_availability[name] = _build_tool_availability_record(result)
            if isinstance(result, (Unavailable, NotApplicable)):
                collectors_map[name] = skip_marker_for_namespace(name)
                if collector.required:
                    raise RuntimeError(
                        f"Required collector {name!r} resolved "
                        f"{type(result).__name__}: "
                        f"{getattr(result, 'reason', 'no reason provided')}"
                    )
        return resolutions

    # -- Pass 2 ------------------------------------------------------------

    def _run_collect_pass(
        self,
        ctx: CollectionContext,
        resolutions: dict[str, ResolutionResult],
        tool_availability: dict[str, schema.ToolAvailability],
        collectors_map: dict[str, Any],
    ) -> None:
        """Call `collect()` on every Available collector; catch non-required errors.

        A required collector raising or timing out propagates out of this
        method — the caller (`run()`) does not swallow it, so `pytest.raises`
        in the tests sees the exception. Non-required failures are recorded
        in `tool_availability` + `collectors_map` and the loop continues.
        """

        for collector in self._registry.collectors:
            name = collector.name
            if not isinstance(resolutions[name], Available):
                continue
            outcome, result, exc = _run_collect_with_timeout(
                collector, ctx, self._default_timeout_seconds
            )
            if outcome == "ok":
                # result is non-None when outcome == "ok" (see helper contract).
                assert result is not None
                collectors_map[name] = result
                continue
            if outcome == "timeout":
                if collector.required:
                    raise TimeoutError(
                        f"Required collector {name!r} exceeded "
                        f"{self._default_timeout_seconds}s timeout"
                    )
                tool_availability[name] = _build_timeout_record(
                    self._default_timeout_seconds
                )
                collectors_map[name] = _build_namespace_error_marker(
                    name, status="timeout"
                )
                continue
            # outcome == "error"
            assert exc is not None
            if collector.required:
                raise exc
            tool_availability[name] = _build_error_record(exc)
            collectors_map[name] = _build_namespace_error_marker(name, status="error")


# ---------------------------------------------------------------------------
# ToolAvailability record builders — one per status class.
# ---------------------------------------------------------------------------


def _build_tool_availability_record(
    result: ResolutionResult,
) -> schema.ToolAvailability:
    """Map a resolution variant onto `schema.ToolAvailability`.

    Delegates to `to_tool_availability_json` for the canonical dict shape and
    lifts the dict fields into the dataclass; this keeps the ADR-defined
    shape definition in one place (collectors/base.py) while producing the
    typed record the schema module requires.
    """

    payload = to_tool_availability_json(result)
    status = payload["status"]
    if isinstance(result, Available):
        return schema.ToolAvailability(status=status, version=result.version)
    if isinstance(result, Unavailable):
        return schema.ToolAvailability(
            status=status,
            reason=result.reason,
            hint=result.install_hint,
        )
    if isinstance(result, NotApplicable):
        return schema.ToolAvailability(status=status, reason=result.reason)
    raise TypeError(f"Unknown ResolutionResult variant: {type(result).__name__}")


def _build_error_record(exc: BaseException) -> schema.ToolAvailability:
    """Error-status record with a truncated traceback excerpt for debugging."""

    excerpt = _format_truncated_traceback(exc)
    return schema.ToolAvailability(
        status="error",
        reason=f"{type(exc).__name__}: {exc}",
        details={"traceback_excerpt": excerpt},
    )


def _build_timeout_record(timeout_seconds: float) -> schema.ToolAvailability:
    """Timeout-status record preserving the configured deadline."""

    return schema.ToolAvailability(
        status="timeout",
        reason=f"collect() exceeded {timeout_seconds}s deadline",
        details={"timeout_seconds": timeout_seconds},
    )


# ---------------------------------------------------------------------------
# Namespace block builders — error/timeout markers mirror the skip-marker shape.
# ---------------------------------------------------------------------------


def _build_namespace_error_marker(tool_name: str, *, status: str) -> dict[str, str]:
    """3-key namespace block for a collector that raised or timed out.

    Mirrors `skip_marker_for_namespace` in shape so the MD renderer can
    handle every non-success namespace with one code path. The only
    differences from the Unavailable/NotApplicable skip marker are the
    `status` literal (`error` or `timeout`) and the `reason` literal
    (`collect_raised` or `collect_timeout`).
    """

    reason = "collect_raised" if status == "error" else "collect_timeout"
    return {"status": status, "reason": reason, "tool": tool_name}


# ---------------------------------------------------------------------------
# Aggregate construction — partial population at the runner layer.
# ---------------------------------------------------------------------------


def _build_partial_aggregate(
    *, commit_sha: str, timestamp: str, window_days: int
) -> schema.AggregateBlock:
    """Build an `AggregateBlock` with only the run_id coordinates populated.

    The 13 metric columns carry type-appropriate empty sentinels — 0 for
    counts, 0.0 for computed floats, None for nullable metrics. The
    composition layers (hotspot.py, trends.py, per-collector aggregate
    mergers) finalize these columns. A consumer that reads the runner's
    output directly sees honest "not yet computed" zeros rather than
    fabricated numbers.
    """

    return schema.AggregateBlock(
        schema_version=schema.SCHEMA_VERSION,
        timestamp=timestamp,
        commit_sha=commit_sha,
        window_days=window_days,
        sloc_total=0,
        file_count=0,
        language_count=0,
        ccn_p95=None,
        cognitive_p95=None,
        cyclic_deps=None,
        churn_total_90d=0,
        change_entropy_90d=0.0,
        truck_factor=0,
        hotspot_top_score=0.0,
        hotspot_gini=0.0,
        coverage_line_pct=None,
    )


# ---------------------------------------------------------------------------
# Default registry — the six-collector factory wired into the CLI.
# ---------------------------------------------------------------------------


def default_registry(repo_root: Path | str) -> CollectorRegistry:
    """Return a fresh registry containing all six collectors in declaration order.

    Declaration order is the execution contract — the runner never reorders:

        Git (required hard floor) -> Scc -> Lizard -> Complexipy -> Pydeps -> Coverage

    Fresh instances are built on every call so callers can instantiate
    multiple runners in the same process without sharing collector state.
    Concrete collector classes are imported lazily inside the function body
    to keep `runner.py` free of module-level dependencies on the concrete
    collector modules (they import from `collectors.base`, so top-level
    imports here would pull the full collector tree into every runner load).
    """

    from scripts.project_metrics.collectors.complexipy_collector import (
        ComplexipyCollector,
    )
    from scripts.project_metrics.collectors.coverage_collector import CoverageCollector
    from scripts.project_metrics.collectors.git_collector import GitCollector
    from scripts.project_metrics.collectors.lizard_collector import LizardCollector
    from scripts.project_metrics.collectors.pydeps_collector import PydepsCollector
    from scripts.project_metrics.collectors.scc_collector import SccCollector

    return CollectorRegistry(
        collectors=[
            GitCollector(repo_root=repo_root),
            SccCollector(repo_root=repo_root),
            LizardCollector(repo_root=repo_root),
            ComplexipyCollector(repo_root=repo_root),
            PydepsCollector(repo_root=repo_root),
            CoverageCollector(repo_root=repo_root),
        ]
    )
