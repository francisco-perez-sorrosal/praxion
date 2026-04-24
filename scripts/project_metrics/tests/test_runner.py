"""Behavioral tests for the runner's two-pass lifecycle + error-isolation contract.

The runner is the orchestrator that threads a fleet of registered collectors
through a resolution pass, then a collection pass, producing a canonical
`Report` with a populated `tool_availability` map and per-namespace blocks.
These tests encode the contract *from the ADRs and the plan*, not from the
implementation — production code (`scripts/project_metrics/runner.py`) is not
read while authoring these tests. Two ADRs are load-bearing:

* Collector-protocol ADR (`dec-draft-c566b978`) — lifecycle: resolve-before-collect,
  registration-order determinism, error isolation ("a collector's top-level
  process errors is caught by the runner"), GitCollector exception as the only
  fatal case.
* Graceful-degradation ADR (`dec-draft-8b26adef`) — five-status tool_availability
  shape (`available`/`unavailable`/`not_applicable`/`error`/`timeout`), uniform
  three-key namespace skip-marker `{"status", "reason", "tool"}`.

Import strategy: every test imports `runner` symbols inside the test body
(deferred import). During the BDD/TDD RED handshake, the `runner.py` stub has
`__all__ = []` and exports nothing — top-of-module imports would break pytest
collection for every test simultaneously. Deferred imports give per-test
RED/GREEN resolution.

Golden constants are hardcoded inline below. Importing them from production
would make the tests tautological; the five-status set and the three-key
skip-marker shape are the ADR contracts, not the runner's implementation.

Test-driven contracts set here that the plan does not pin verbatim (flagged
in the report to the implementer):

1. `Runner` takes its collector registry via constructor injection
   (`Runner(registry=CollectorRegistry([...]))`), not via a module-level
   singleton. Constructor injection makes each test pass its own registry.
2. `CollectorRegistry(collectors: list[Collector])` exposes `.collectors` as
   an iterable preserving registration order. The runner reads this iterable
   in both passes.
3. `Runner.run(window_days: int, top_n: int) -> Report` returns a
   `schema.Report` whose `tool_availability` is keyed by collector `name`,
   whose `collectors` map holds the per-collector payload (raw data for
   resolved-and-succeeded collectors, skip marker otherwise), and whose
   `aggregate` block carries the run_id coordinates (commit_sha + timestamp).
4. Git probe is injectable via a keyword argument (default: calls
   `subprocess.run`). Tests pass a stub callable returning a fixed
   `(sha, timestamp_iso)` tuple so assertions don't depend on the working
   tree's actual HEAD.
5. Timeout is injectable via `default_timeout_seconds` (default 120.0 per
   the SYSTEMS_PLAN risk register). Tests inject a tiny value and a
   collector that sleeps past it.
6. The "hard floor" collector is identified by its `required` class
   attribute (True only on GitCollector per the Collector ABC's class-level
   metadata), not by name string equality. This decouples the runner from
   any specific collector name.

GitCollector-raising contract (plan line 151, 158): the runner "aborts with
non-zero exit" when a required collector raises. Tests assert the runner
propagates the exception (i.e., the run does not silently continue). The
implementer may choose `SystemExit`, a domain-specific `FatalCollectorError`,
or re-raising the original — the test uses `pytest.raises(BaseException)` to
accept any of these while guaranteeing the non-continuation invariant.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Golden constants — lifted verbatim from the two canonical ADRs.
# ---------------------------------------------------------------------------

# From the graceful-degradation ADR, "Skip-marker shapes" section.
_TOOL_AVAILABILITY_STATUSES: frozenset[str] = frozenset(
    {"available", "unavailable", "not_applicable", "error", "timeout"}
)

# Namespace skip-marker for collectors the runner resolved as Unavailable /
# NotApplicable. Three keys, exactly.
_NAMESPACE_SKIP_MARKER_KEYS: frozenset[str] = frozenset({"status", "reason", "tool"})
_NAMESPACE_SKIP_MARKER_STATUS: str = "skipped"
_NAMESPACE_SKIP_MARKER_REASON: str = "tool_unavailable"

# Fixed git coordinates used by tests that need a reproducible run_id. Any
# 40-char hex string + any ISO-8601 UTC timestamp satisfies the contract;
# these are chosen to be obviously synthetic.
_FIXED_SHA: str = "abcdef1234567890abcdef1234567890abcdef12"
_FIXED_TIMESTAMP: str = "2026-04-23T23:00:00Z"


# ---------------------------------------------------------------------------
# Mock collector builders — stdlib only, no unittest.mock needed.
#
# Each builder returns a concrete `Collector` subclass so the ABC enforcement
# in `collectors.base` does not trip. Subclassing (rather than MagicMock) also
# makes the test intent readable: a reader sees exactly which resolve/collect
# behavior each mock models.
# ---------------------------------------------------------------------------


def _make_available_ok_collector(
    name: str,
    *,
    tier: int = 0,
    required: bool = False,
    payload: dict[str, Any] | None = None,
    collect_calls: list[str] | None = None,
):
    """Return a Collector subclass whose resolve() -> Available and collect() -> ok.

    When `collect_calls` is provided, the collector appends its own name to
    that list each time `collect()` is invoked; tests use this to assert
    registration order and to assert that never-resolved collectors never have
    `collect()` called.
    """

    from scripts.project_metrics.collectors.base import (
        Available,
        Collector,
        CollectionContext,
        CollectorResult,
        ResolutionEnv,
    )

    _name = name
    _payload = payload or {"value": name}
    _calls = collect_calls

    class _AvailableOk(Collector):
        name = _name
        tier = 0
        required = False
        languages: frozenset[str] = frozenset()

        def resolve(self, env: ResolutionEnv) -> Any:
            return Available(version="1.0.0", details={})

        def collect(self, ctx: CollectionContext) -> CollectorResult:
            if _calls is not None:
                _calls.append(_name)
            return CollectorResult(status="ok", data=dict(_payload))

    # Apply per-instance overrides of tier/required via attribute assignment.
    _AvailableOk.tier = tier
    _AvailableOk.required = required
    return _AvailableOk()


def _make_unavailable_collector(
    name: str,
    *,
    required: bool = False,
    collect_calls: list[str] | None = None,
):
    """Return a Collector whose resolve() -> Unavailable. collect() must never run."""

    from scripts.project_metrics.collectors.base import (
        Collector,
        CollectionContext,
        CollectorResult,
        ResolutionEnv,
        Unavailable,
    )

    _name = name
    _calls = collect_calls

    class _UnavailableCollector(Collector):
        name = _name
        tier = 0
        required = False
        languages: frozenset[str] = frozenset()

        def resolve(self, env: ResolutionEnv) -> Any:
            return Unavailable(
                reason=f"{_name} binary not on PATH",
                install_hint=f"install {_name}",
            )

        def collect(self, ctx: CollectionContext) -> CollectorResult:
            # If this ever runs, the runner violated the contract. Record so
            # the assertion surfaces in the test failure rather than a stale
            # "collect never called" assumption.
            if _calls is not None:
                _calls.append(f"UNEXPECTED:{_name}")
            return CollectorResult(status="ok", data={})

    _UnavailableCollector.required = required
    return _UnavailableCollector()


def _make_not_applicable_collector(
    name: str,
    *,
    collect_calls: list[str] | None = None,
):
    """Return a Collector whose resolve() -> NotApplicable. Silent skip."""

    from scripts.project_metrics.collectors.base import (
        Collector,
        CollectionContext,
        CollectorResult,
        NotApplicable,
        ResolutionEnv,
    )

    _name = name
    _calls = collect_calls

    class _NotApplicableCollector(Collector):
        name = _name
        tier = 0
        required = False
        languages: frozenset[str] = frozenset()

        def resolve(self, env: ResolutionEnv) -> Any:
            return NotApplicable(reason=f"no matching sources for {_name}")

        def collect(self, ctx: CollectionContext) -> CollectorResult:
            if _calls is not None:
                _calls.append(f"UNEXPECTED:{_name}")
            return CollectorResult(status="ok", data={})

    return _NotApplicableCollector()


def _make_raising_collector(
    name: str,
    *,
    required: bool = False,
    raise_exc: BaseException | None = None,
):
    """Return a Collector whose resolve() -> Available but collect() raises.

    `raise_exc` defaults to `RuntimeError("boom in " + name)`. When `required`
    is True, this collector models the GitCollector hard-floor fatal case.
    """

    from scripts.project_metrics.collectors.base import (
        Available,
        Collector,
        CollectionContext,
        CollectorResult,
        ResolutionEnv,
    )

    exc = raise_exc if raise_exc is not None else RuntimeError(f"boom in {name}")
    _name = name
    _exc = exc

    class _RaisingCollector(Collector):
        name = _name
        tier = 0
        required = False
        languages: frozenset[str] = frozenset()

        def resolve(self, env: ResolutionEnv) -> Any:
            return Available(version="1.0.0", details={})

        def collect(self, ctx: CollectionContext) -> CollectorResult:
            raise _exc

    _RaisingCollector.required = required
    return _RaisingCollector()


def _make_sleeping_collector(name: str, *, sleep_seconds: float = 10.0):
    """Return a Collector whose collect() sleeps long enough to trigger timeout.

    The runner should enforce its configured timeout and record `status=timeout`
    in `tool_availability` without actually waiting the full duration — either
    via a thread-based deadline or an explicit cancellation mechanism. The
    test sets the runner's timeout small enough that either implementation
    hits it quickly.
    """

    from scripts.project_metrics.collectors.base import (
        Available,
        Collector,
        CollectionContext,
        CollectorResult,
        ResolutionEnv,
    )

    _name = name
    _sleep = sleep_seconds

    class _SleepingCollector(Collector):
        name = _name
        tier = 0
        required = False
        languages: frozenset[str] = frozenset()

        def resolve(self, env: ResolutionEnv) -> Any:
            return Available(version="1.0.0", details={})

        def collect(self, ctx: CollectionContext) -> CollectorResult:
            # Respect thread interrupts if the runner uses one: sleep in
            # small slices so an external cancellation signal (e.g.,
            # Event.set) can preempt. Check the monotonic clock at each
            # slice so even a cooperative cancellation protocol works.
            deadline = time.monotonic() + _sleep
            while time.monotonic() < deadline:
                time.sleep(0.05)
            return CollectorResult(status="ok", data={"slept": _sleep})

    return _SleepingCollector()


def _fixed_git_probe(sha: str = _FIXED_SHA, timestamp: str = _FIXED_TIMESTAMP):
    """Return a callable matching the runner's git-probe injection point.

    The probe is invoked once at start-of-run and returns the `(sha, timestamp)`
    tuple the runner embeds in the aggregate block. Tests inject a fixed
    probe so assertions don't depend on the repo's current HEAD.
    """

    def _probe() -> tuple[str, str]:
        return (sha, timestamp)

    return _probe


def _build_runner(
    collectors: list[Any],
    *,
    default_timeout_seconds: float = 120.0,
    git_probe: Any = None,
):
    """Construct `Runner(registry=CollectorRegistry(collectors), ...)`.

    Wrapped in a helper so the test-driven constructor contract lives in one
    place. If the implementer renames these kwargs, this wrapper is the sole
    site that needs updating — individual tests do not re-specify the kwargs.
    """

    from scripts.project_metrics.runner import CollectorRegistry, Runner

    registry = CollectorRegistry(collectors)
    return Runner(
        registry=registry,
        default_timeout_seconds=default_timeout_seconds,
        git_probe=git_probe or _fixed_git_probe(),
    )


# ---------------------------------------------------------------------------
# Two-pass lifecycle: resolve for all, collect only for Available
# ---------------------------------------------------------------------------


class TestRunnerTwoPassLifecycle:
    """The runner performs exactly two passes over the registered collectors.

    Pass 1 — `resolve()` on every registered collector, in registration order;
    results populate `tool_availability`.
    Pass 2 — `collect()` ONLY on collectors whose resolution was `Available`,
    in registration order. Collectors resolved as `Unavailable` or
    `NotApplicable` get a namespace skip marker; their `collect()` is never
    called.

    The canonical source is the collector-protocol ADR "Lifecycle ordering"
    section: (1) Registration, (2) Resolution pass populates tool_availability,
    (3) Collection pass runs only on Available resolvers.
    """

    def test_collect_is_called_for_every_available_collector(self) -> None:
        """When all three collectors resolve Available, all three collect() run."""
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector("alpha", collect_calls=collect_calls),
            _make_available_ok_collector("beta", collect_calls=collect_calls),
            _make_available_ok_collector("gamma", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        runner.run(window_days=90, top_n=10)

        assert collect_calls == ["alpha", "beta", "gamma"], (
            "All three Available collectors must have collect() called, in "
            "registration order. Observed: " + repr(collect_calls)
        )

    def test_collect_is_not_called_for_unavailable_collector(self) -> None:
        """A collector that resolves Unavailable must NOT have collect() invoked."""
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector("alpha", collect_calls=collect_calls),
            _make_unavailable_collector("beta", collect_calls=collect_calls),
            _make_available_ok_collector("gamma", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        runner.run(window_days=90, top_n=10)

        assert "UNEXPECTED:beta" not in collect_calls, (
            "collect() was invoked on an Unavailable collector — the runner "
            "must skip collect() whenever resolve() returned Unavailable."
        )
        assert collect_calls == ["alpha", "gamma"]

    def test_collect_is_not_called_for_not_applicable_collector(self) -> None:
        """A collector that resolves NotApplicable must NOT have collect() invoked."""
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector("alpha", collect_calls=collect_calls),
            _make_not_applicable_collector("beta", collect_calls=collect_calls),
            _make_available_ok_collector("gamma", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        runner.run(window_days=90, top_n=10)

        assert "UNEXPECTED:beta" not in collect_calls
        assert collect_calls == ["alpha", "gamma"]

    def test_tool_availability_populated_for_every_registered_collector(self) -> None:
        """Every registered collector has an entry in tool_availability regardless of outcome.

        Five registered collectors -> five entries in the tool_availability
        map. Unavailable and NotApplicable collectors are not dropped; they
        are recorded with their respective status literals.
        """
        collectors = [
            _make_available_ok_collector("alpha"),
            _make_unavailable_collector("beta"),
            _make_not_applicable_collector("gamma"),
            _make_available_ok_collector("delta"),
            _make_unavailable_collector("epsilon"),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        tool_availability = report.tool_availability
        expected_names = {"alpha", "beta", "gamma", "delta", "epsilon"}
        assert set(tool_availability.keys()) == expected_names, (
            "Every registered collector name must appear as a key in "
            "tool_availability. Expected: "
            + repr(sorted(expected_names))
            + "; got: "
            + repr(sorted(tool_availability.keys()))
        )


# ---------------------------------------------------------------------------
# Registration order determinism
# ---------------------------------------------------------------------------


class TestRegistrationOrderDeterminism:
    """Collectors execute in registration order — not alphabetic, not by tier.

    The plan explicitly says "Git first, Coverage last" for the production
    registry. Here we assert the mechanism (registration order is respected)
    with synthetic names that would shuffle under any automatic sort.
    """

    def test_collect_runs_in_registration_order_even_when_names_are_reverse_alphabetic(
        self,
    ) -> None:
        """Registration order wins over alphabetic sort."""
        collect_calls: list[str] = []
        # Names chosen to expose alphabetic re-sorting: registration order is
        # zulu, yankee, xray — which is strictly reverse-alphabetic. If the
        # runner silently sorts collectors alphabetically, we'll see the
        # order flip.
        collectors = [
            _make_available_ok_collector("zulu", collect_calls=collect_calls),
            _make_available_ok_collector("yankee", collect_calls=collect_calls),
            _make_available_ok_collector("xray", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        runner.run(window_days=90, top_n=10)

        assert collect_calls == ["zulu", "yankee", "xray"], (
            "Registration order must be preserved. If the runner sorted by "
            "name, the order would be ['xray', 'yankee', 'zulu']. Observed: "
            + repr(collect_calls)
        )

    def test_collect_runs_in_registration_order_even_when_tiers_differ(
        self,
    ) -> None:
        """Registration order wins over tier ordering.

        A naive implementation might sort by tier (Tier 0 first, Tier 1 second).
        Registration order is the canonical ordering — we register Tier 1
        before Tier 0 and verify the runner does NOT reshuffle.
        """
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector(
                "tier_one_first", tier=1, collect_calls=collect_calls
            ),
            _make_available_ok_collector(
                "tier_zero_second", tier=0, collect_calls=collect_calls
            ),
        ]
        runner = _build_runner(collectors)

        runner.run(window_days=90, top_n=10)

        assert collect_calls == ["tier_one_first", "tier_zero_second"]

    def test_git_first_coverage_last_registration_order_preserved(self) -> None:
        """Plan line: 'Git first, Coverage last' — assert the convention the
        runner uses is literally the registration-order list it was given.

        Mimics the production registration list shape: git, scc, lizard,
        complexipy, pydeps, coverage. The runner's job is to execute them in
        exactly that order; our synthetic registry uses the same names so the
        assertion reads as a one-to-one mirror of the plan's "Git first,
        Coverage last" prose.
        """
        collect_calls: list[str] = []
        # `required=True` on the git stand-in to match GitCollector's class
        # attribute contract. It still succeeds here; the fatal-path test
        # elsewhere exercises the raising case.
        collectors = [
            _make_available_ok_collector(
                "git", required=True, collect_calls=collect_calls
            ),
            _make_available_ok_collector("scc", collect_calls=collect_calls),
            _make_available_ok_collector("lizard", collect_calls=collect_calls),
            _make_available_ok_collector("complexipy", collect_calls=collect_calls),
            _make_available_ok_collector("pydeps", collect_calls=collect_calls),
            _make_available_ok_collector("coverage", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        runner.run(window_days=90, top_n=10)

        assert collect_calls[0] == "git", "Git must run first when registered first."
        assert collect_calls[-1] == "coverage", (
            "Coverage must run last when registered last."
        )
        assert collect_calls == [
            "git",
            "scc",
            "lizard",
            "complexipy",
            "pydeps",
            "coverage",
        ]


# ---------------------------------------------------------------------------
# Error isolation — non-git collector exceptions downgrade to status='error'
# ---------------------------------------------------------------------------


class TestErrorIsolationForNonRequiredCollectors:
    """A non-required collector raising in collect() is caught; the run continues.

    Per dec-draft-8b26adef and dec-draft-c566b978, an uncaught exception in
    `collect()` is wrapped by the runner into `tool_availability[name] =
    {"status": "error", ...}` with a truncated traceback excerpt, and the
    namespace block is a skip/error marker. Subsequent collectors still run.
    """

    def test_raising_collector_does_not_abort_run(self) -> None:
        """A collector raising RuntimeError in collect() does not stop the run."""
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector("alpha", collect_calls=collect_calls),
            _make_raising_collector("beta"),
            _make_available_ok_collector("gamma", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        assert "gamma" in collect_calls, (
            "A collector after a raising one must still have collect() called. "
            "The raising collector's exception must be caught by the runner."
        )
        # All three collectors still present in tool_availability.
        assert set(report.tool_availability.keys()) == {"alpha", "beta", "gamma"}

    def test_raising_collector_records_error_status_in_tool_availability(self) -> None:
        """tool_availability[name].status == 'error' for the raising collector."""
        collectors = [
            _make_available_ok_collector("alpha"),
            _make_raising_collector("beta"),
            _make_available_ok_collector("gamma"),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        beta_availability = report.tool_availability["beta"]
        status = _availability_status(beta_availability)
        assert status == "error", (
            "tool_availability['beta'].status must be 'error' after collect() "
            "raised. Got: " + repr(status)
        )
        assert status in _TOOL_AVAILABILITY_STATUSES

    def test_raising_collector_records_truncated_traceback_excerpt(self) -> None:
        """tool_availability[error-collector] carries a traceback_excerpt string.

        Per the graceful-degradation ADR's error shape:
          {"status": "error", "reason": "...", "traceback_excerpt": "..."}

        The excerpt must be present, must be a string, must be non-empty, and
        must be bounded in length — the runner truncates to prevent gigabytes
        of chained traceback from flooding the JSON artifact.
        """
        collectors = [_make_raising_collector("beta")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        availability = report.tool_availability["beta"]
        excerpt = _traceback_excerpt(availability)

        assert excerpt is not None, (
            "A raising collector must have a traceback_excerpt recorded in "
            "tool_availability; got None."
        )
        assert isinstance(excerpt, str)
        assert len(excerpt) > 0, "traceback_excerpt must not be empty"
        # Bounded length — upper bound generous so implementer has flexibility,
        # but asserts truncation happens. A full Python traceback can easily
        # exceed 10 KB for deep call chains; an excerpt capped at 4 KB is
        # reasonable. 8 KB is the assertion ceiling here to leave room.
        assert len(excerpt) <= 8192, (
            f"traceback_excerpt length {len(excerpt)} exceeds 8192-char "
            f"truncation bound. The runner must truncate long tracebacks."
        )

    def test_raising_collector_produces_namespace_skip_or_error_marker(self) -> None:
        """The namespace block for a raising collector must be a skip/error marker.

        Per dec-draft-8b26adef, a skipped namespace block uses the uniform
        3-key shape `{"status": "skipped"|"error", "reason": ..., "tool": ...}`.
        For a raising collector, the namespace block carries status="error"
        rather than the normal collector data payload — the MD renderer must
        be able to distinguish "collector ran and produced data" from
        "collector raised and we have nothing."
        """
        collectors = [_make_raising_collector("beta")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        namespace_block = _namespace_block(report, "beta")
        assert namespace_block is not None, (
            "Namespace block for a raising collector must exist — it is the "
            "MD renderer's hook for 'this collector errored.'"
        )
        block_status = _extract_status(namespace_block)
        assert block_status in {"error", "skipped"}, (
            "Raising collector's namespace block status must be 'error' or "
            "'skipped'. Got: " + repr(block_status)
        )

    def test_multiple_raising_collectors_all_isolated(self) -> None:
        """Multiple non-required collectors can raise; all are isolated."""
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector("alpha", collect_calls=collect_calls),
            _make_raising_collector("beta_raiser"),
            _make_available_ok_collector("gamma", collect_calls=collect_calls),
            _make_raising_collector("delta_raiser"),
            _make_available_ok_collector("epsilon", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        # The three non-raising collectors all ran to completion.
        assert collect_calls == ["alpha", "gamma", "epsilon"]
        # Both raisers recorded as error in tool_availability.
        assert _availability_status(report.tool_availability["beta_raiser"]) == "error"
        assert _availability_status(report.tool_availability["delta_raiser"]) == "error"


# ---------------------------------------------------------------------------
# Hard-floor contract — GitCollector (required=True) raising is FATAL
# ---------------------------------------------------------------------------


class TestHardFloorGitFatalContract:
    """The only collector whose exception aborts the run is the required one.

    `required=True` is the class-level marker of the hard-floor collector
    (set on GitCollector only, per the Collector ABC metadata). The runner
    MUST NOT swallow a required collector's exception — if git is dead the
    run has no meaningful output and must signal fatal.

    The exact exception type is an implementation detail (the implementer may
    choose SystemExit, a domain-specific FatalCollectorError, or re-raising
    the original RuntimeError). The test uses `pytest.raises(BaseException)`
    to accept any non-swallowing behavior while guaranteeing the run does
    not silently continue.
    """

    def test_required_collector_raising_aborts_the_run(self) -> None:
        """A required collector raising in collect() aborts the whole run."""
        collect_calls: list[str] = []
        collectors = [
            _make_raising_collector("git", required=True),
            _make_available_ok_collector("scc", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        # BaseException covers SystemExit (a common abort idiom for CLI tools)
        # AND every normal Exception subclass. The invariant asserted is "the
        # run did not complete normally" — not any specific exception type.
        with pytest.raises(BaseException):
            runner.run(window_days=90, top_n=10)

        # The non-required collector registered after the fatal one must NOT
        # have run — the abort is immediate, not deferred.
        assert "scc" not in collect_calls, (
            "A required collector raising must abort before subsequent "
            "collectors run. 'scc' ran anyway: the runner is not honoring "
            "the hard-floor contract."
        )

    def test_required_collector_resolving_unavailable_aborts_the_run(self) -> None:
        """If the required collector resolves Unavailable, the run aborts.

        The graceful-degradation ADR's hard-floor row says `git` being absent
        is a fatal condition. A required collector whose resolve() returns
        Unavailable is the same contract — there is no way to produce a
        meaningful report without the hard-floor tool.
        """
        collect_calls: list[str] = []
        collectors = [
            _make_unavailable_collector("git", required=True),
            _make_available_ok_collector("scc", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        with pytest.raises(BaseException):
            runner.run(window_days=90, top_n=10)

        assert "scc" not in collect_calls

    def test_non_required_raising_collector_does_not_abort(self) -> None:
        """Guardrail: the abort is triggered by `required=True`, not by any
        raise. Flip `required` to False on the same raising collector — the
        run must complete."""
        collect_calls: list[str] = []
        collectors = [
            _make_raising_collector("not_git", required=False),
            _make_available_ok_collector("scc", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        assert "scc" in collect_calls
        assert _availability_status(report.tool_availability["not_git"]) == "error"


# ---------------------------------------------------------------------------
# Timeout contract — a collector exceeding its deadline is recorded as timeout
# ---------------------------------------------------------------------------


class TestTimeoutContract:
    """A collector whose `collect()` exceeds the runner's timeout is recorded
    as `status='timeout'`.

    The SYSTEMS_PLAN risk register names 120s as the default per-collector
    timeout. The runner exposes this as `default_timeout_seconds` so tests
    can inject a small value and exercise the path quickly.
    """

    def test_slow_collector_records_timeout_status(self) -> None:
        """A collector that sleeps past the deadline records status=timeout."""
        # Inject a 0.25-second deadline against a 5-second sleep. The runner
        # must terminate (or mark-as-timed-out) within a small multiple of
        # the deadline — this test fails slowly if the runner ignores the
        # deadline and waits the full sleep.
        collectors = [
            _make_available_ok_collector("alpha"),
            _make_sleeping_collector("slow_one", sleep_seconds=5.0),
            _make_available_ok_collector("gamma"),
        ]
        runner = _build_runner(collectors, default_timeout_seconds=0.25)

        start = time.monotonic()
        report = runner.run(window_days=90, top_n=10)
        elapsed = time.monotonic() - start

        status = _availability_status(report.tool_availability["slow_one"])
        assert status == "timeout", (
            "A collector exceeding default_timeout_seconds must be recorded "
            "with status='timeout'. Got: " + repr(status)
        )
        # Bound: the whole run must not wait the full sleep. Generous upper
        # bound — implementer picks thread-based or process-based enforcement;
        # 3.0 seconds covers either without false-failing on a slow CI host.
        assert elapsed < 3.0, (
            f"Runner waited {elapsed:.2f}s despite 0.25s timeout on a slow "
            "collector. The runner must enforce the timeout, not rely on the "
            "collector to self-terminate."
        )

    def test_timeout_does_not_abort_run(self) -> None:
        """A non-required collector timing out does not stop subsequent collectors."""
        collect_calls: list[str] = []
        collectors = [
            _make_available_ok_collector("alpha", collect_calls=collect_calls),
            _make_sleeping_collector("slow_one", sleep_seconds=5.0),
            _make_available_ok_collector("gamma", collect_calls=collect_calls),
        ]
        runner = _build_runner(collectors, default_timeout_seconds=0.25)

        runner.run(window_days=90, top_n=10)

        assert "alpha" in collect_calls
        assert "gamma" in collect_calls, (
            "A collector after a timeout must still run. The timeout is "
            "isolated to the slow collector, not fatal to the run."
        )


# ---------------------------------------------------------------------------
# Namespace block shape — successful vs skipped vs errored
# ---------------------------------------------------------------------------


class TestNamespaceBlockShape:
    """Each collector contributes a namespace block keyed by its `name`.

    * Successful: raw `CollectorResult.data` passed through.
    * Unavailable / NotApplicable: 3-key skip marker `{"status": "skipped",
      "reason": "tool_unavailable", "tool": "<name>"}`.
    * Errored: 3-key error marker with `status="error"`.
    """

    def test_successful_collector_namespace_block_contains_raw_data(self) -> None:
        """A status=ok collector's namespace block carries the CollectorResult.data."""
        collectors = [
            _make_available_ok_collector(
                "alpha", payload={"some_metric": 42, "notes": "hi"}
            ),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        block = _namespace_block(report, "alpha")
        data = _extract_data(block)
        assert data is not None
        assert data == {"some_metric": 42, "notes": "hi"}, (
            "A successful collector's namespace block must contain its "
            "CollectorResult.data verbatim. Got: " + repr(data)
        )

    def test_unavailable_collector_namespace_block_is_skip_marker(self) -> None:
        """Unavailable collector -> namespace block matches the 3-key skip marker."""
        collectors = [_make_unavailable_collector("beta")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        block = _namespace_block(report, "beta")
        marker = _extract_skip_marker(block)
        assert marker is not None, (
            "Unavailable collector's namespace block must be a skip marker, "
            "not a CollectorResult-shaped dict."
        )
        assert set(marker.keys()) == _NAMESPACE_SKIP_MARKER_KEYS
        assert marker["status"] == _NAMESPACE_SKIP_MARKER_STATUS
        assert marker["reason"] == _NAMESPACE_SKIP_MARKER_REASON
        assert marker["tool"] == "beta"

    def test_not_applicable_collector_namespace_block_is_skip_marker(self) -> None:
        """NotApplicable collector -> namespace block matches the 3-key skip marker."""
        collectors = [_make_not_applicable_collector("gamma")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        block = _namespace_block(report, "gamma")
        marker = _extract_skip_marker(block)
        assert marker is not None
        assert set(marker.keys()) == _NAMESPACE_SKIP_MARKER_KEYS
        assert marker["tool"] == "gamma"

    def test_namespace_keys_mirror_collector_names(self) -> None:
        """Every namespace block's key equals the collector's `name` attribute."""
        collectors = [
            _make_available_ok_collector("alpha"),
            _make_unavailable_collector("beta"),
            _make_not_applicable_collector("gamma"),
        ]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        all_namespace_keys = _all_namespace_keys(report)
        expected = {"alpha", "beta", "gamma"}
        assert expected.issubset(all_namespace_keys), (
            "Every collector name must appear as a namespace key. Expected "
            f"subset: {sorted(expected)}; observed keys: "
            f"{sorted(all_namespace_keys)}"
        )


# ---------------------------------------------------------------------------
# Run_id coordinates — git SHA + UTC timestamp captured at start of run
# ---------------------------------------------------------------------------


class TestRunIdCoordinates:
    """The runner captures `(commit_sha, timestamp)` at start-of-run.

    Both coordinates land in the `aggregate` block of the final `Report`,
    per the SYSTEMS_PLAN Aggregate-columns table. Tests inject a stub probe
    so the captured SHA and timestamp are known in advance.
    """

    def test_commit_sha_from_probe_lands_in_aggregate_block(self) -> None:
        """The sha returned by the git probe appears in aggregate.commit_sha."""
        collectors = [_make_available_ok_collector("alpha")]
        probe_sha = "0123456789abcdef0123456789abcdef01234567"
        probe_ts = "2026-01-01T00:00:00Z"
        runner = _build_runner(
            collectors, git_probe=_fixed_git_probe(sha=probe_sha, timestamp=probe_ts)
        )

        report = runner.run(window_days=90, top_n=10)

        aggregate_sha = _aggregate_field(report, "commit_sha")
        assert aggregate_sha == probe_sha, (
            "aggregate.commit_sha must equal the sha returned by the injected "
            f"git probe. Expected {probe_sha!r}; got {aggregate_sha!r}."
        )

    def test_timestamp_from_probe_lands_in_aggregate_block(self) -> None:
        """The timestamp returned by the git probe appears in aggregate.timestamp."""
        collectors = [_make_available_ok_collector("alpha")]
        probe_sha = _FIXED_SHA
        probe_ts = "2027-06-15T12:34:56Z"
        runner = _build_runner(
            collectors, git_probe=_fixed_git_probe(sha=probe_sha, timestamp=probe_ts)
        )

        report = runner.run(window_days=90, top_n=10)

        aggregate_ts = _aggregate_field(report, "timestamp")
        assert aggregate_ts == probe_ts, (
            "aggregate.timestamp must equal the timestamp returned by the "
            f"injected git probe. Expected {probe_ts!r}; got {aggregate_ts!r}."
        )

    def test_window_days_from_run_kwarg_lands_in_aggregate_block(self) -> None:
        """`run(window_days=...)` is recorded in aggregate.window_days."""
        collectors = [_make_available_ok_collector("alpha")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=45, top_n=10)

        aggregate_window = _aggregate_field(report, "window_days")
        assert aggregate_window == 45, (
            "aggregate.window_days must reflect the window_days passed to "
            f"run(). Expected 45; got {aggregate_window!r}."
        )


# ---------------------------------------------------------------------------
# Empty composition/trends fields — Runner's output is NOT the final report
# ---------------------------------------------------------------------------


class TestEmptyCompositionAndTrendsFields:
    """The runner's Report leaves composition layers empty.

    Hot-spots, trends, and report_file-style post-processing fields are
    populated by later pipeline layers (hotspot.py, trends.py, report.py).
    The runner's job is limited to collector orchestration; it MUST NOT
    fabricate composed outputs. A consumer that mistakes the runner's
    Report for a finished artifact fails early if these fields are empty.
    """

    def test_hotspots_field_is_empty_after_runner(self) -> None:
        """Report.hotspots is empty (composition layer has not run yet)."""
        collectors = [_make_available_ok_collector("alpha")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        # Accept empty dict, empty list, or None — the contract is "nothing
        # composed yet", not "specific empty type."
        hotspots = getattr(report, "hotspots", None)
        assert not hotspots, (
            "Runner output must not populate hotspots — that is hotspot.py's "
            f"job. Got: {hotspots!r}"
        )

    def test_trends_field_is_first_run_placeholder(self) -> None:
        """Report.trends is the schema's first_run default, not a computed delta block."""
        collectors = [_make_available_ok_collector("alpha")]
        runner = _build_runner(collectors)

        report = runner.run(window_days=90, top_n=10)

        trends = getattr(report, "trends", None)
        assert trends is not None, (
            "Report.trends should always exist — the schema default is "
            "TrendBlock(status='first_run')."
        )
        # Accept either the schema default TrendBlock(status='first_run'),
        # or a dict with matching status — the runner contract is "trends is
        # not yet computed," represented by the first_run placeholder.
        status = getattr(trends, "status", None)
        if status is None and isinstance(trends, dict):
            status = trends.get("status")
        assert status == "first_run", (
            "Runner must leave trends as the schema's first_run placeholder; "
            "trends.py is responsible for computing deltas. Got status="
            f"{status!r}"
        )


# ---------------------------------------------------------------------------
# Registry shape — CollectorRegistry exposes registration order
# ---------------------------------------------------------------------------


class TestCollectorRegistryShape:
    """`CollectorRegistry(collectors: list[Collector])` preserves order.

    The runner reads the registry's ordered iterable in both passes. Tests
    here pin the registry API shape independent of the runner — if the
    implementer ever splits registry into a separate file, these tests still
    apply.
    """

    def test_registry_is_importable_from_runner_module(self) -> None:
        """CollectorRegistry is exported from runner.py."""
        from scripts.project_metrics import runner as runner_mod

        assert hasattr(runner_mod, "CollectorRegistry"), (
            "CollectorRegistry must be exported from scripts.project_metrics.runner. "
            "This is the wire-in point for the default_registry factory's collector list."
        )

    def test_registry_preserves_registration_order(self) -> None:
        """Registry.collectors yields entries in the order they were registered."""
        from scripts.project_metrics.runner import CollectorRegistry

        alpha = _make_available_ok_collector("alpha")
        beta = _make_available_ok_collector("beta")
        gamma = _make_available_ok_collector("gamma")
        registry = CollectorRegistry([alpha, beta, gamma])

        names = [c.name for c in registry.collectors]
        assert names == ["alpha", "beta", "gamma"], (
            "CollectorRegistry.collectors must preserve registration order. "
            f"Got: {names!r}"
        )


# ---------------------------------------------------------------------------
# Helpers — accessor utilities tolerant of the exact Report shape.
#
# The schema.Report dataclass is stable (see `scripts/project_metrics/schema.py`),
# but the implementer has some latitude in HOW the runner stores per-collector
# namespace output and tool_availability entries. These helpers try the
# documented field paths and fall back to alternative shapes — any of them
# is acceptable as long as the contract (keys + values) is honored.
# ---------------------------------------------------------------------------


def _availability_status(entry: Any) -> str | None:
    """Pull the `status` field from a tool_availability entry.

    Tolerates: ToolAvailability dataclass, plain dict, or SimpleNamespace.
    """
    status = getattr(entry, "status", None)
    if status is not None:
        return status
    if isinstance(entry, dict):
        return entry.get("status")
    return None


def _traceback_excerpt(entry: Any) -> str | None:
    """Pull `traceback_excerpt` from an error-status tool_availability entry.

    The graceful-degradation ADR names the field `traceback_excerpt`. If the
    implementer lands it under `details["traceback_excerpt"]` or `error` or
    similar, the fallbacks here keep the test robust.
    """
    excerpt = getattr(entry, "traceback_excerpt", None)
    if excerpt is not None:
        return excerpt
    if isinstance(entry, dict):
        excerpt = entry.get("traceback_excerpt")
        if excerpt is not None:
            return excerpt
    # Fallback: some implementations store inside a `details` dict.
    details = getattr(entry, "details", None) or (
        entry.get("details") if isinstance(entry, dict) else None
    )
    if isinstance(details, dict):
        return details.get("traceback_excerpt")
    return None


def _namespace_block(report: Any, collector_name: str) -> Any:
    """Pull the namespace block for `collector_name` from the report.

    The runner may store per-collector namespace blocks either:
      (a) under `report.collectors[name]` as a CollectorResult (primary
          shape per `schema.Report.collectors`), or
      (b) under `report.<collector_name>` as an attribute, or
      (c) inside a `namespaces` dict.
    All three are acceptable; the test is robust to whichever the implementer
    chose.
    """
    # (a) collectors map on the Report dataclass (primary).
    collectors_map = getattr(report, "collectors", None)
    if collectors_map is not None:
        try:
            value = collectors_map.get(collector_name)
        except AttributeError:
            value = None
        if value is not None:
            return value
    # (b) attribute on the report itself.
    direct = getattr(report, collector_name, None)
    if direct is not None:
        return direct
    # (c) namespaces dict.
    namespaces = getattr(report, "namespaces", None)
    if isinstance(namespaces, dict):
        return namespaces.get(collector_name)
    # (d) Fallback: the entire Report may be stored as a dict in some
    # transitional implementations.
    if isinstance(report, dict):
        return report.get(collector_name) or report.get("collectors", {}).get(
            collector_name
        )
    return None


def _extract_status(block: Any) -> str | None:
    """Pull the `status` field from a namespace block.

    A CollectorResult has `.status` directly; a skip marker has `["status"]`.
    """
    if block is None:
        return None
    status = getattr(block, "status", None)
    if status is not None:
        return status
    if isinstance(block, dict):
        return block.get("status")
    return None


def _extract_data(block: Any) -> dict | None:
    """Pull the `data` field from a namespace block that represents a successful
    collection.

    A CollectorResult has `.data` (dict); a skip marker has no `data` key.
    """
    if block is None:
        return None
    data = getattr(block, "data", None)
    if data is not None:
        return data
    if isinstance(block, dict) and "data" in block:
        return block["data"]
    return None


def _extract_skip_marker(block: Any) -> dict | None:
    """If `block` is a skip marker (3-key dict), return it; else None.

    A namespace block may come through as:
      * A `skip_marker_for_namespace` result — a plain dict with exactly
        `{"status", "reason", "tool"}`.
      * A CollectorResult wrapping the skip marker in its `data` field.

    Both shapes are acceptable — this helper normalizes.
    """
    if block is None:
        return None
    # Direct: plain dict with the three keys.
    if isinstance(block, dict) and set(block.keys()) == _NAMESPACE_SKIP_MARKER_KEYS:
        return block
    # Indirect: a CollectorResult with data being the skip marker.
    data = _extract_data(block)
    if isinstance(data, dict) and set(data.keys()) == _NAMESPACE_SKIP_MARKER_KEYS:
        return data
    # Tolerant: if the dict has the three skip-marker keys PLUS optional
    # extra fields, still accept it as a skip marker by looking at `status`.
    if isinstance(block, dict) and block.get("status") == _NAMESPACE_SKIP_MARKER_STATUS:
        # Project out the canonical three keys.
        return {k: block[k] for k in _NAMESPACE_SKIP_MARKER_KEYS if k in block} or None
    return None


def _all_namespace_keys(report: Any) -> set[str]:
    """Enumerate every namespace-block key present in the report."""
    keys: set[str] = set()
    collectors_map = getattr(report, "collectors", None)
    if collectors_map is not None:
        try:
            keys.update(collectors_map.keys())
        except AttributeError:
            pass
    namespaces = getattr(report, "namespaces", None)
    if isinstance(namespaces, dict):
        keys.update(namespaces.keys())
    if isinstance(report, dict):
        keys.update(report.keys())
    return keys


def _aggregate_field(report: Any, field_name: str) -> Any:
    """Pull `report.aggregate.<field_name>`, tolerating dataclass or dict shape.

    `schema.AggregateBlock` is a frozen dataclass; some intermediate
    implementations may hold it as a dict. Both are accepted.
    """
    aggregate = getattr(report, "aggregate", None)
    if aggregate is None and isinstance(report, dict):
        aggregate = report.get("aggregate")
    if aggregate is None:
        return None
    if hasattr(aggregate, field_name):
        return getattr(aggregate, field_name)
    if isinstance(aggregate, dict):
        return aggregate.get(field_name)
    return None


# ---------------------------------------------------------------------------
# Suppress an unused-import warning for the `threading` module — it is used
# only by a planned future test for cancellation cooperation. Keep imported
# here so the implementer knows threading is available in the test env.
# ---------------------------------------------------------------------------

_ = threading


# ---------------------------------------------------------------------------
# default_registry — six-collector factory, declaration order, fresh on each call.
# ---------------------------------------------------------------------------


class TestDefaultRegistry:
    """Validates the registry wire-up: six concrete collectors in declaration order."""

    def test_default_registry_contains_all_six_collectors_in_declaration_order(
        self, tmp_path
    ):
        from scripts.project_metrics.runner import default_registry

        registry = default_registry(repo_root=tmp_path)
        names = [c.name for c in registry.collectors]
        assert names == ["git", "scc", "lizard", "complexipy", "pydeps", "coverage"]

    def test_default_registry_returns_fresh_list_on_each_call(self, tmp_path):
        from scripts.project_metrics.runner import default_registry

        registry_1 = default_registry(repo_root=tmp_path)
        registry_2 = default_registry(repo_root=tmp_path)
        # Different registry objects; different collector instance objects.
        assert registry_1 is not registry_2
        assert registry_1.collectors[0] is not registry_2.collectors[0]
