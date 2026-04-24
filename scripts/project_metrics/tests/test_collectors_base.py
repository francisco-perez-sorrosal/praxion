"""Behavioral tests for the collector protocol and its result dataclasses.

These tests encode the three-method collector contract (`resolve`, `collect`,
`describe`), the tagged-union resolution outcomes (`Available`, `Unavailable`,
`NotApplicable`), the four collection-result statuses (`ok`, `partial`, `error`,
`timeout`), and the uniform five-status `tool_availability` JSON shape. They
are written *from the behavioral spec*, not the implementation — production
code (`scripts/project_metrics/collectors/base.py`) is not read while authoring
these tests.

Two ADRs are the canonical contract:

* The collector-protocol ADR defines the three-method ABC, resolution outcomes,
  `CollectorResult` shape, `ResolutionEnv`, and `CollectionContext`.
* The graceful-degradation ADR defines the five-status `tool_availability`
  block and the namespace skip-marker shape.

Import strategy: each test imports symbols from
`scripts.project_metrics.collectors.base` at test-body time (deferred import).
This is deliberate — during the BDD/TDD RED handshake, the module stub does not
yet export these symbols, and top-of-module imports would break pytest
collection for every test in this file simultaneously. Deferred imports give
per-test RED/GREEN resolution.

Golden values (status constants, skip-marker shapes, context field names) are
hardcoded inline below, not imported from the production module — importing
them would make the tests tautological. If the ADR ever changes, update these
constants in lock-step with the production code.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Golden constants — lifted verbatim from the two canonical ADRs.
# ---------------------------------------------------------------------------

# From the collector-protocol ADR ("Decision" section, resolution outcomes):
# Available | Unavailable | NotApplicable are the *three* resolution variants.
_RESOLUTION_VARIANT_NAMES: tuple[str, ...] = (
    "Available",
    "Unavailable",
    "NotApplicable",
)

# From the same ADR ("Decision" section, CollectorResult shape): status is one
# of *four* literal values. Note this is distinct from the tool_availability
# status set below — `ok` / `partial` belong to the collector's own return
# contract, whereas `error` / `timeout` appear on *both* surfaces (the runner
# may elevate an uncaught exception into a tool_availability error even if the
# collector itself never returned anything).
_COLLECTOR_RESULT_STATUSES: tuple[str, ...] = ("ok", "partial", "error", "timeout")

# From the graceful-degradation ADR ("Skip-marker shapes"): tool_availability
# values carry one of *five* status literals. `error` and `timeout` are the
# runner-wrapper-level outcomes; they overlap with CollectorResult.status by
# design, so a run that timed out renders the same way in tool_availability
# regardless of whether the collector caught the deadline or the runner did.
_TOOL_AVAILABILITY_STATUSES: frozenset[str] = frozenset(
    {"available", "unavailable", "not_applicable", "error", "timeout"}
)

# From the graceful-degradation ADR ("Skip-marker shapes"), the namespace
# block that a skipped collector contributes to the JSON root. This is what
# the MD renderer reads to produce the "_not computed — <reason>_" line.
_NAMESPACE_SKIP_MARKER_KEYS: frozenset[str] = frozenset({"status", "reason", "tool"})
_NAMESPACE_SKIP_MARKER_STATUS: str = "skipped"
_NAMESPACE_SKIP_MARKER_REASON: str = "tool_unavailable"

# From the collector-protocol ADR: `CollectionContext` carries exactly these
# three fields, no more. A fourth field here would silently change the
# determinism contract (collector output must be reproducible given identical
# context; a fourth field would widen that invariant).
_COLLECTION_CONTEXT_FIELDS: frozenset[str] = frozenset(
    {"repo_root", "window_days", "git_sha"}
)


# ---------------------------------------------------------------------------
# Resolution-result tagged-union shape
# ---------------------------------------------------------------------------


class TestResolutionResultShape:
    """The three resolution outcomes carry the specific fields the ADR mandates.

    Available  -> (version: str, details: dict)
    Unavailable -> (reason: str, install_hint: str)
    NotApplicable -> (reason: str)

    These fields are the minimal information the runner needs to render the
    tool_availability block and the Install-to-improve section. Renaming or
    dropping one of them silently regresses the user-facing install hints.
    """

    def test_three_resolution_variants_are_importable(self) -> None:
        """All three variants must be exported from `collectors.base`."""
        from scripts.project_metrics.collectors import base

        for variant_name in _RESOLUTION_VARIANT_NAMES:
            assert hasattr(base, variant_name), (
                f"Missing resolution variant: {variant_name} — the ADR mandates "
                f"Available / Unavailable / NotApplicable as the three outcomes."
            )

    def test_available_variant_carries_version_and_details(self) -> None:
        """`Available(version=..., details=...)` constructs and preserves its fields."""
        from scripts.project_metrics.collectors.base import Available

        outcome = Available(version="1.2.3", details={"path": "/usr/bin/scc"})

        assert outcome.version == "1.2.3"
        assert outcome.details == {"path": "/usr/bin/scc"}

    def test_unavailable_variant_carries_reason_and_install_hint(self) -> None:
        """`Unavailable(reason=..., install_hint=...)` preserves both human-facing strings."""
        from scripts.project_metrics.collectors.base import Unavailable

        outcome = Unavailable(
            reason="scc binary not found on PATH",
            install_hint="brew install scc",
        )

        assert outcome.reason == "scc binary not found on PATH"
        assert outcome.install_hint == "brew install scc"

    def test_not_applicable_variant_carries_reason_only(self) -> None:
        """`NotApplicable(reason=...)` is the silent-skip variant — no install hint."""
        from scripts.project_metrics.collectors.base import NotApplicable

        outcome = NotApplicable(reason="no .py sources in git ls-files")

        assert outcome.reason == "no .py sources in git ls-files"

    def test_resolution_variants_are_distinct_types(self) -> None:
        """Available, Unavailable, NotApplicable must be separate types so a
        caller can pattern-match (isinstance) to decide what to render."""
        from scripts.project_metrics.collectors.base import (
            Available,
            NotApplicable,
            Unavailable,
        )

        available = Available(version="1.0.0", details={})
        unavailable = Unavailable(reason="missing", install_hint="install it")
        not_applicable = NotApplicable(reason="no matching sources")

        # Each outcome must be an instance only of its own variant (plus any
        # shared base class). Using isinstance here rather than type() equality
        # so a shared ResolutionResult base class does not break the test.
        assert not isinstance(available, Unavailable)
        assert not isinstance(available, NotApplicable)
        assert not isinstance(unavailable, Available)
        assert not isinstance(unavailable, NotApplicable)
        assert not isinstance(not_applicable, Available)
        assert not isinstance(not_applicable, Unavailable)


# ---------------------------------------------------------------------------
# Collection-context shape
# ---------------------------------------------------------------------------


class TestCollectionContextShape:
    """`CollectionContext(repo_root, window_days, git_sha)` — exactly three fields.

    A fourth field here would be a silent breach of the determinism contract:
    `collect()` MUST be deterministic given the same ctx, so ctx is the full
    set of values a collector is allowed to vary on. Every new axis of variance
    is an ADR-amendment-level decision.
    """

    def test_collection_context_constructs_with_three_fields(self) -> None:
        from scripts.project_metrics.collectors.base import CollectionContext

        ctx = CollectionContext(
            repo_root="/tmp/fixture-repo",
            window_days=90,
            git_sha="abcdef1234567890abcdef1234567890abcdef12",
        )

        assert ctx.repo_root == "/tmp/fixture-repo"
        assert ctx.window_days == 90
        assert ctx.git_sha == "abcdef1234567890abcdef1234567890abcdef12"

    def test_collection_context_field_set_is_frozen_to_three(self) -> None:
        """Guard against silent addition of new context fields.

        If a future change adds `branch` or `origin_url` to the context, this
        test fails loudly — at which point the decision is either to roll that
        back or to amend the protocol ADR and this golden field set together.
        """
        from dataclasses import fields

        from scripts.project_metrics.collectors.base import CollectionContext

        field_names = {f.name for f in fields(CollectionContext)}
        assert field_names == _COLLECTION_CONTEXT_FIELDS, (
            f"CollectionContext fields drifted from the three the ADR mandates. "
            f"Expected: {sorted(_COLLECTION_CONTEXT_FIELDS)}; "
            f"got: {sorted(field_names)}."
        )


# ---------------------------------------------------------------------------
# Collector ABC — three abstract methods + describe() default
# ---------------------------------------------------------------------------


class TestCollectorAbstractContract:
    """The `Collector` base class enforces the three-method contract.

    Instantiating Collector without overriding `resolve` and `collect` must
    raise TypeError; Python's ABCMeta enforces this mechanically. The third
    method `describe()` may have a sensible default per the ADR
    ("Consequences: Mitigated by providing sensible describe() defaults in
    the base class"), so subclasses overriding only resolve and collect must
    be instantiable and return a valid CollectorDescription.
    """

    def test_cannot_instantiate_collector_without_overriding_abstracts(self) -> None:
        """Direct instantiation of the ABC raises TypeError."""
        from scripts.project_metrics.collectors.base import Collector

        with pytest.raises(TypeError):
            Collector()  # type: ignore[abstract]

    def test_subclass_missing_resolve_cannot_instantiate(self) -> None:
        """A subclass that implements only `collect` but not `resolve` is still abstract."""
        from scripts.project_metrics.collectors.base import (
            Collector,
            CollectionContext,
            CollectorResult,
        )

        class PartialCollector(Collector):
            name = "partial"
            tier = 0
            required = False
            languages: frozenset[str] = frozenset()

            def collect(self, ctx: CollectionContext) -> CollectorResult:
                return CollectorResult(status="ok")

        with pytest.raises(TypeError):
            PartialCollector()  # type: ignore[abstract]

    def test_subclass_missing_collect_cannot_instantiate(self) -> None:
        """A subclass that implements only `resolve` but not `collect` is still abstract."""
        from scripts.project_metrics.collectors.base import (
            Available,
            Collector,
            ResolutionEnv,
        )

        class PartialCollector(Collector):
            name = "partial"
            tier = 0
            required = False
            languages: frozenset[str] = frozenset()

            def resolve(self, env: ResolutionEnv) -> Any:
                return Available(version="1.0", details={})

        with pytest.raises(TypeError):
            PartialCollector()  # type: ignore[abstract]

    def test_minimal_subclass_with_default_describe_instantiates(self) -> None:
        """Subclass overrides only resolve and collect — default describe() suffices.

        Per the protocol ADR "Consequences: Mitigated by providing sensible
        describe() defaults in the base class." A slim 40-line wrapper (e.g.,
        the coverage collector) should not have to implement describe()
        just to satisfy the ABC.
        """
        from scripts.project_metrics.collectors.base import (
            Available,
            Collector,
            CollectionContext,
            CollectorDescription,
            CollectorResult,
            ResolutionEnv,
        )

        class MinimalCollector(Collector):
            name = "minimal"
            tier = 0
            required = False
            languages: frozenset[str] = frozenset()

            def resolve(self, env: ResolutionEnv) -> Any:
                return Available(version="1.0.0", details={})

            def collect(self, ctx: CollectionContext) -> CollectorResult:
                return CollectorResult(status="ok", data={})

        instance = MinimalCollector()
        description = instance.describe()

        assert isinstance(description, CollectorDescription), (
            "Default describe() must return a CollectorDescription instance so "
            "slim wrappers do not have to override it."
        )


# ---------------------------------------------------------------------------
# CollectorResult — four status literals
# ---------------------------------------------------------------------------


class TestCollectorResultStatuses:
    """The `CollectorResult` dataclass represents all four collector outcomes.

    Status is one of `ok`, `partial`, `error`, `timeout`. Callers use the
    status literal to route rendering; a drift here (adding `no_artifact` or
    `stale` as a literal, for instance) would be a silent broadening of the
    collector contract and is flagged by testing all four statuses explicitly.
    """

    @pytest.mark.parametrize("status", list(_COLLECTOR_RESULT_STATUSES))
    def test_collector_result_accepts_each_canonical_status(self, status: str) -> None:
        """Constructing with each of the four canonical statuses succeeds."""
        from scripts.project_metrics.collectors.base import CollectorResult

        result = CollectorResult(
            status=status,
            data={"key": "value"},
            issues=["non-fatal warning"],
            duration_seconds=0.125,
        )

        assert result.status == status

    def test_collector_result_default_issues_is_empty_list(self) -> None:
        """Issues defaults to an empty list so tests don't have to pass one."""
        from scripts.project_metrics.collectors.base import CollectorResult

        result = CollectorResult(status="ok")

        assert result.issues == []

    def test_collector_result_default_data_is_empty_dict(self) -> None:
        """Data defaults to empty so an error-status result doesn't have to supply it."""
        from scripts.project_metrics.collectors.base import CollectorResult

        result = CollectorResult(status="error")

        assert result.data == {}


# ---------------------------------------------------------------------------
# Determinism discipline — `collect()` is byte-stable given the same ctx
# ---------------------------------------------------------------------------


class TestCollectDeterminism:
    """`collect()` MUST be deterministic given the same context.

    The ADR phrases it: "MUST be deterministic given the same git SHA and
    file-system state." At the protocol level, we verify this by constructing
    a mock collector whose `collect()` implementation is pure (no clock, no
    random, no env) and showing that two successive invocations with the same
    context produce byte-identical output via the schema's JSON serializer.
    """

    def test_mock_collector_returns_byte_identical_output_across_two_calls(
        self,
    ) -> None:
        """Same context in -> same JSON bytes out, on every call."""
        from scripts.project_metrics.collectors.base import (
            Available,
            Collector,
            CollectionContext,
            CollectorResult,
            ResolutionEnv,
        )
        from scripts.project_metrics.schema import to_json as _schema_to_json

        class DeterministicCollector(Collector):
            name = "deterministic"
            tier = 0
            required = False
            languages: frozenset[str] = frozenset()

            def resolve(self, env: ResolutionEnv) -> Any:
                return Available(version="0.1.0", details={})

            def collect(self, ctx: CollectionContext) -> CollectorResult:
                # Fully deterministic: the payload is a function of the context
                # fields only, with no clock or random input.
                return CollectorResult(
                    status="ok",
                    data={
                        "repo_root": ctx.repo_root,
                        "window_days": ctx.window_days,
                        "git_sha": ctx.git_sha,
                        "derived_count": 7,
                    },
                    issues=[],
                    duration_seconds=0.0,  # not wall-clock — the test asserts
                    # byte-identical output, so duration cannot be real time.
                )

        ctx = CollectionContext(
            repo_root="/tmp/fixture-repo",
            window_days=90,
            git_sha="abcdef1234567890abcdef1234567890abcdef12",
        )

        collector = DeterministicCollector()
        first = collector.collect(ctx)
        second = collector.collect(ctx)

        # Structural equality on the dataclasses themselves.
        assert first == second

        # Byte-identical serialization: go through `json.dumps` (not the schema
        # module's `to_json`, which operates on Report objects, not
        # CollectorResult) with the same sort-and-separator discipline the
        # schema module uses elsewhere.
        from dataclasses import asdict

        first_bytes = json.dumps(
            asdict(first), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        second_bytes = json.dumps(
            asdict(second), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        assert first_bytes == second_bytes, (
            "Two invocations of the same deterministic collector with the same "
            "context must produce byte-identical JSON. Non-determinism here would "
            "make the trend-delta contract impossible to uphold."
        )

        # Sanity check: the schema-level to_json is also available and
        # deterministic — callers down the pipeline use it on Report.
        assert callable(_schema_to_json)


# ---------------------------------------------------------------------------
# Five-status `tool_availability` JSON shape + namespace skip-marker
# ---------------------------------------------------------------------------


class TestToolAvailabilityFiveStatusShape:
    """The uniform `tool_availability` JSON shape covers exactly five statuses.

    From the graceful-degradation ADR:

        "tool_availability": {
          "<name>": {"status": "available",     "version": "..."}
                  | {"status": "unavailable",   "reason": "...",  "install_hint": "..."}
                  | {"status": "not_applicable","reason": "..."}
                  | {"status": "error",         "reason": "...",  "traceback_excerpt": "..."}
                  | {"status": "timeout",       "timeout_seconds": N}
        }

    `Available` / `Unavailable` / `NotApplicable` are direct renderings of
    their matching `ResolutionResult` variant; `error` and `timeout` arise
    from the runner wrapping `collect()` (an uncaught exception turns into
    `error`, a hit deadline turns into `timeout`). Collectively these are the
    five statuses the UI and MD renderer may receive. A serialization path
    that can't express all five is a broken contract.
    """

    def test_available_serializes_with_version(self) -> None:
        """`Available(version=..., details=...)` round-trips through JSON with status='available' and a version field."""
        from scripts.project_metrics.collectors.base import (
            Available,
            to_tool_availability_json,
        )

        payload = to_tool_availability_json(Available(version="1.2.3", details={}))

        assert payload["status"] == "available"
        assert payload["version"] == "1.2.3"
        assert payload["status"] in _TOOL_AVAILABILITY_STATUSES

    def test_unavailable_serializes_with_reason_and_install_hint(self) -> None:
        """`Unavailable(...)` serializes with status='unavailable' and both actionable strings."""
        from scripts.project_metrics.collectors.base import (
            Unavailable,
            to_tool_availability_json,
        )

        payload = to_tool_availability_json(
            Unavailable(reason="scc not found", install_hint="brew install scc")
        )

        assert payload["status"] == "unavailable"
        assert payload["reason"] == "scc not found"
        assert payload["install_hint"] == "brew install scc"
        assert payload["status"] in _TOOL_AVAILABILITY_STATUSES

    def test_not_applicable_serializes_with_reason_only(self) -> None:
        """`NotApplicable(...)` serializes with status='not_applicable' — no install hint."""
        from scripts.project_metrics.collectors.base import (
            NotApplicable,
            to_tool_availability_json,
        )

        payload = to_tool_availability_json(NotApplicable(reason="no .py sources"))

        assert payload["status"] == "not_applicable"
        assert payload["reason"] == "no .py sources"
        # NotApplicable is the "silent" variant — no install hint, because
        # there is nothing the user can do to fix it.
        assert "install_hint" not in payload
        assert payload["status"] in _TOOL_AVAILABILITY_STATUSES

    def test_all_three_resolution_outcomes_serialize_to_valid_status_literals(
        self,
    ) -> None:
        """Every ResolutionResult serializes to a status in the five-literal set."""
        from scripts.project_metrics.collectors.base import (
            Available,
            NotApplicable,
            Unavailable,
            to_tool_availability_json,
        )

        outcomes = [
            Available(version="1.0.0", details={}),
            Unavailable(reason="missing", install_hint="install it"),
            NotApplicable(reason="no matching sources"),
        ]

        for outcome in outcomes:
            payload = to_tool_availability_json(outcome)
            assert payload["status"] in _TOOL_AVAILABILITY_STATUSES, (
                f"Serialized status {payload['status']!r} is not in the five-status "
                f"uniform shape. Expected one of {sorted(_TOOL_AVAILABILITY_STATUSES)}."
            )
            # Sanity: whatever was serialized must round-trip as JSON.
            json.dumps(payload)  # raises if non-serializable

    def test_error_and_timeout_statuses_are_in_the_canonical_set(self) -> None:
        """The runner-level `error` / `timeout` statuses complete the five-status set.

        These are produced by the runner, not the resolve() contract — the
        runner catches an uncaught collector exception and renders it as
        `status='error'`, or enforces a timeout and renders `status='timeout'`.
        This test is a guardrail: the string literals themselves must live in
        the canonical set so downstream consumers match against them.
        """
        assert "error" in _TOOL_AVAILABILITY_STATUSES
        assert "timeout" in _TOOL_AVAILABILITY_STATUSES

    def test_five_status_set_has_exactly_five_members(self) -> None:
        """Exactly five — not four (merging error/timeout), not six (adding no_artifact)."""
        assert len(_TOOL_AVAILABILITY_STATUSES) == 5, (
            "The graceful-degradation ADR mandates exactly five tool_availability "
            "statuses. The schema.py docstring lists 'no_artifact' and 'stale' "
            "which are NOT in this canonical set — if that drift is real, the "
            "schema docstring is wrong and the ADR wins (per the test-engineer "
            "prompt: 'If the two ADRs ever disagree on any field, flag it in "
            "TEST_RESULTS — don't pick one silently.')."
        )


class TestNamespaceSkipMarkerShape:
    """Namespace blocks for skipped collectors use a uniform three-key shape.

    From the graceful-degradation ADR:

        "<namespace>": {"status": "skipped", "reason": "tool_unavailable", "tool": "<name>"}

    This is what the MD renderer reads to produce `_not computed — <reason>_`
    with one function regardless of which collector was skipped. Adding a
    fourth key (or dropping one of the three) breaks the uniform-rendering
    invariant that lets the MD renderer stay small.
    """

    def test_skip_marker_has_exactly_three_keys(self) -> None:
        """Status + reason + tool — nothing more, nothing less."""
        from scripts.project_metrics.collectors.base import skip_marker_for_namespace

        marker = skip_marker_for_namespace(tool_name="lizard")

        assert set(marker.keys()) == _NAMESPACE_SKIP_MARKER_KEYS

    def test_skip_marker_status_literal_is_skipped(self) -> None:
        """The literal value is 'skipped' — the MD renderer matches on this."""
        from scripts.project_metrics.collectors.base import skip_marker_for_namespace

        marker = skip_marker_for_namespace(tool_name="lizard")

        assert marker["status"] == _NAMESPACE_SKIP_MARKER_STATUS

    def test_skip_marker_reason_defaults_to_tool_unavailable(self) -> None:
        """The reason literal is `tool_unavailable` when no reason is given."""
        from scripts.project_metrics.collectors.base import skip_marker_for_namespace

        marker = skip_marker_for_namespace(tool_name="lizard")

        assert marker["reason"] == _NAMESPACE_SKIP_MARKER_REASON

    def test_skip_marker_tool_field_names_the_skipped_collector(self) -> None:
        """The `tool` field names which collector was skipped — the MD Install
        to improve section uses it."""
        from scripts.project_metrics.collectors.base import skip_marker_for_namespace

        marker = skip_marker_for_namespace(tool_name="pydeps")

        assert marker["tool"] == "pydeps"

    def test_skip_marker_is_json_serializable(self) -> None:
        """The marker contains only plain strings — json.dumps round-trips
        it losslessly, same as any other JSON namespace block."""
        from scripts.project_metrics.collectors.base import skip_marker_for_namespace

        marker = skip_marker_for_namespace(tool_name="coverage")
        serialized = json.dumps(marker, sort_keys=True, separators=(",", ":"))
        restored = json.loads(serialized)

        assert restored == marker


# ---------------------------------------------------------------------------
# ResolutionEnv — symbol presence (lightweight)
# ---------------------------------------------------------------------------


class TestResolutionEnvPresence:
    """`ResolutionEnv` is the bundle the runner hands to `resolve()`.

    The collector-protocol ADR describes it as "env paths + PATH lookup helpers" — a
    small helper, not a rich domain object. We test only that it exists and
    is constructable, leaving helper-method specifics to the implementer.
    Over-specifying the helper shape here would couple this test to
    implementation choices that don't affect the contract.
    """

    def test_resolution_env_is_importable(self) -> None:
        from scripts.project_metrics.collectors import base

        assert hasattr(base, "ResolutionEnv"), (
            "ResolutionEnv must be exported from collectors.base — the runner "
            "constructs one and passes it to resolve() once per run."
        )
