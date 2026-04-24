"""Collector abstract base class, result dataclasses, and resolution/collection contexts.

This module defines the three-method collector contract (`resolve`, `collect`,
`describe`) plus the dataclasses the runner threads through its two-pass
lifecycle. The contract is:

* `resolve()` checks tool availability and returns one of three tagged-union
  variants (`Available`, `Unavailable`, `NotApplicable`); it never runs the
  underlying analysis.
* `collect()` runs the analysis only when resolution returned `Available`,
  producing a `CollectorResult` with one of four statuses (`ok`, `partial`,
  `error`, `timeout`), a namespace-scoped data payload, non-fatal issues, and
  wall-clock duration.
* `describe()` returns static metadata; a sensible default is provided so a
  slim wrapper only overrides `resolve` and `collect`.

Two serialization helpers convert protocol outputs into the canonical JSON
shapes the runner renders:

* `to_tool_availability_json(result)` maps a `ResolutionResult` variant into
  the uniform 5-status `tool_availability[name]` entry (available / unavailable
  / not_applicable / error / timeout — the error/timeout members of that set
  are populated by the runner wrapper, not this module).
* `skip_marker_for_namespace(tool_name)` returns the 3-key namespace block
  (`status`/`reason`/`tool`) that the MD renderer uses to produce the uniform
  "_not computed — <reason>_" line.

All result types are frozen dataclasses so once a collector has emitted a
record, no consumer can mutate it out from under the serializer.
"""

from __future__ import annotations

import abc
import shutil
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Available",
    "Collector",
    "CollectorDescription",
    "CollectorResult",
    "CollectionContext",
    "NotApplicable",
    "ResolutionEnv",
    "ResolutionResult",
    "Unavailable",
    "skip_marker_for_namespace",
    "to_tool_availability_json",
]


# ---------------------------------------------------------------------------
# Namespace skip-marker constants — mirror the graceful-degradation ADR's
# uniform 3-key shape so the MD renderer can handle every skip with one
# function regardless of which collector is being rendered.
# ---------------------------------------------------------------------------

_NAMESPACE_SKIP_STATUS = "skipped"
_NAMESPACE_SKIP_REASON = "tool_unavailable"


# ---------------------------------------------------------------------------
# Resolution-result tagged union
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionResult:
    """Base type for the three resolution outcomes.

    A shared base lets callers annotate return types precisely without
    widening to `Any`, while still permitting `isinstance` pattern-matching
    to route rendering between the three concrete variants below.
    """


@dataclass(frozen=True)
class Available(ResolutionResult):
    """Tool is present; `collect()` will run.

    `version` is the resolved tool version (informational; shown in
    `tool_availability`). `details` carries optional per-tool metadata such
    as the resolved binary path.
    """

    version: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Unavailable(ResolutionResult):
    """Tool is applicable but absent — user can fix by installing it.

    Reported with an actionable install hint so the MD "Install to improve"
    section can offer a one-liner. Distinct from `NotApplicable`: there IS
    a user action here.
    """

    reason: str
    install_hint: str


@dataclass(frozen=True)
class NotApplicable(ResolutionResult):
    """Tool does not apply to this repository — silent skip.

    Carries only a reason (for logs and debugging). No install hint, because
    there is nothing the user can do — the tool is not appropriate for this
    repo shape (e.g., Python complexity collector on a Go-only project).
    """

    reason: str


# ---------------------------------------------------------------------------
# Collection-time context — the full set of values a collector may vary on.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectionContext:
    """Fully describes the axis along which a collector is allowed to vary.

    Exactly three fields: `repo_root`, `window_days`, `git_sha`. The
    determinism contract says `collect()` MUST produce byte-identical output
    given the same context, so any new axis of variance (branch name, origin
    URL, runtime env) is an ADR-amendment-level decision — it widens the
    variance surface and the test suite guards the field set against drift.

    `repo_root` is a string rather than a `pathlib.Path` because the record
    passes through `dataclasses.asdict` into JSON; strings serialize natively
    and callers that need `Path` semantics wrap locally (`Path(ctx.repo_root)`).
    """

    repo_root: str
    window_days: int
    git_sha: str


# ---------------------------------------------------------------------------
# Resolution-time context — bundles PATH-lookup helpers for `resolve()`.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionEnv:
    """Environment bundle handed to every collector's `resolve()`.

    Carries the resolved `PATH` and `PYTHONPATH` (so tests can inject
    synthetic environments without monkeypatching `os.environ`) plus a
    `which()` helper. Collectors that need richer behavior can read the
    string fields directly and call `shutil.which` themselves; most will
    prefer `env.which("scc")` for readability.
    """

    path: str = ""
    pythonpath: str = ""

    def which(self, command: str) -> str | None:
        """Locate `command` on the bundled PATH; return its absolute path or None.

        Delegates to `shutil.which`, passing `self.path` when populated so
        the resolution is isolated from the ambient process environment.
        When `path` is empty, falls back to the ambient PATH — this is the
        default behavior most collectors want in production.
        """

        if self.path:
            return shutil.which(command, path=self.path)
        return shutil.which(command)


# ---------------------------------------------------------------------------
# Collection result — the payload `collect()` returns.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectorResult:
    """Wrapper around a single collector's `collect()` output.

    `status` is one of `ok` / `partial` / `error` / `timeout`. `data` is the
    collector's namespace-block contribution (empty dict when status is
    `error`). `issues` accumulates non-fatal warnings. `duration_seconds` is
    wall-clock for the collect pass — note that tests asserting byte-identical
    output set this to `0.0` deliberately, because wall-clock is inherently
    non-deterministic.
    """

    status: str
    data: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Collector static metadata — returned by describe().
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectorDescription:
    """Static metadata a collector advertises to the runner and report layer.

    Pulled from the four class-level attributes the `Collector` ABC requires
    subclasses to set (`name`, `tier`, `languages`) plus a `description`
    string sourced from the subclass's docstring or a `description` override.
    """

    name: str
    tier: int
    languages: frozenset[str]
    description: str


# ---------------------------------------------------------------------------
# Collector abstract base class.
# ---------------------------------------------------------------------------


class Collector(abc.ABC):
    """Three-method abstract contract every collector implements.

    Subclasses declare four class-level attributes the runner uses for
    registration and filtering:

    * `name` — stable identifier; becomes the JSON namespace key.
    * `tier` — 0 (universal) or 1 (language-specific).
    * `required` — True only for the GitCollector hard-floor contract.
    * `languages` — frozenset of language identifiers; empty means
      language-agnostic.

    Subclasses override `resolve` and `collect` (mandatory) and optionally
    `describe` (a sensible default reads the class attributes plus the
    subclass docstring, so a 40-line wrapper stays slim).
    """

    # Class-level metadata — subclasses override these. Defaults here keep
    # `Collector()` itself well-formed for type-checker purposes; the ABC
    # mechanism still blocks instantiation because the abstract methods
    # below are unimplemented.
    name: str = ""
    tier: int = 0
    required: bool = False
    languages: frozenset[str] = frozenset()

    @abc.abstractmethod
    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Check whether this collector's tool is available for this run.

        Must not run the analysis. Called exactly once per run, before
        `collect()`. Returns one of the three `ResolutionResult` variants.
        """

    @abc.abstractmethod
    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Run the analysis; produce the namespace payload.

        Called only when `resolve()` returned `Available`. Must be
        deterministic given the same context. Must downgrade analysis-level
        errors to `status='partial'` or `status='error'` rather than raising
        — the runner's try/except is a safety net for bugs, not the primary
        error path.
        """

    def describe(self) -> CollectorDescription:
        """Return static metadata. Default implementation reads class attrs.

        Slim wrappers (e.g., the coverage collector) can rely on this default;
        richer collectors can override to supply custom descriptions or
        tool URLs. The default pulls the docstring's first line as the
        description when present, falling back to the empty string.
        """

        docstring = (self.__class__.__doc__ or "").strip()
        description = docstring.splitlines()[0] if docstring else ""
        return CollectorDescription(
            name=self.name,
            tier=self.tier,
            languages=self.languages,
            description=description,
        )


# ---------------------------------------------------------------------------
# Serialization helpers.
# ---------------------------------------------------------------------------


def to_tool_availability_json(result: ResolutionResult) -> dict[str, Any]:
    """Convert a `ResolutionResult` into the canonical `tool_availability` entry.

    The graceful-degradation ADR defines the uniform 5-status shape:

        {"status": "available",     "version": "..."}
        {"status": "unavailable",   "reason": "...", "install_hint": "..."}
        {"status": "not_applicable","reason": "..."}
        {"status": "error",         "reason": "...", "traceback_excerpt": "..."}
        {"status": "timeout",       "timeout_seconds": N}

    This helper covers the three resolution-time variants; the `error` and
    `timeout` members of the 5-status set are emitted by the runner wrapper
    when a collector raises uncaught or exceeds its deadline, and are
    constructed there, not here.
    """

    if isinstance(result, Available):
        return {"status": "available", "version": result.version}
    if isinstance(result, Unavailable):
        return {
            "status": "unavailable",
            "reason": result.reason,
            "install_hint": result.install_hint,
        }
    if isinstance(result, NotApplicable):
        return {"status": "not_applicable", "reason": result.reason}
    raise TypeError(
        f"Unknown ResolutionResult variant: {type(result).__name__}. "
        f"Expected Available, Unavailable, or NotApplicable."
    )


def skip_marker_for_namespace(tool_name: str) -> dict[str, str]:
    """Return the 3-key namespace block for a skipped collector.

    Shape (verbatim from the graceful-degradation ADR):

        {"status": "skipped", "reason": "tool_unavailable", "tool": "<name>"}

    The MD renderer reads this shape to produce `_not computed — <reason>_`
    with one function regardless of which collector was skipped. Adding a
    fourth key (or dropping one) breaks the uniform-rendering invariant.
    """

    return {
        "status": _NAMESPACE_SKIP_STATUS,
        "reason": _NAMESPACE_SKIP_REASON,
        "tool": tool_name,
    }
