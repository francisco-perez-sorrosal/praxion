"""CoverageCollector -- Tier 1 soft-dep collector that reads pre-existing coverage artifacts.

Unique among the collector fleet: this collector does NOT invoke any external
tool to produce its measurement. It reads an on-disk artifact (Cobertura
``coverage.xml`` or LCOV ``lcov.info``) that the project has already generated
out-of-band. The graceful-degradation ADR pins coverage collection as a
READ-ONLY artifact parser -- the collector must never drive the measurement
itself, which would inflate run time and couple ``/project-metrics`` to the
test suite of every target project.

Three resolution outcomes:

* **No artifact** -- neither ``coverage.xml`` nor ``lcov.info`` is present in
  the repo root or its ``coverage/`` subdirectory; resolve() returns
  ``Unavailable`` with an actionable install hint.
* **Stale** -- an artifact exists but its git-tracked commit timestamp is
  strictly older than the current HEAD commit timestamp. resolve() returns
  ``Available(version="stale", ...)``; collect() still extracts the line
  percentage but marks the namespace ``status`` as ``"stale"`` so the MD
  renderer can flag ``(stale -- regenerate)``.
* **Current** -- artifact exists and its commit timestamp is at or newer than
  the current commit; resolve() returns ``Available(version="current", ...)``
  and collect() emits the line percentage cleanly with ``status == "ok"``.

Payload emitted in ``data`` when available:

* ``status`` -- ``"ok"`` or ``"stale"``; the per-namespace marker consumed by
  the MD renderer to print the freshness caveat.
* ``artifact_path`` -- absolute or repo-relative path of the parsed artifact;
  included so debugging "why did the number change?" is a one-glance check.
* ``artifact_format`` -- ``"cobertura"`` or ``"lcov"``; disambiguates which
  parser ran. Useful when both formats are present and one gets updated more
  often than the other.
* ``line_pct`` -- overall line coverage as a float in [0.0, 1.0].
* ``per_file`` -- dict mapping each source file to its own
  ``{"line_pct", "lines_total", "lines_covered"}`` triple. The aggregate
  composition layer reads this to populate per-file rollups.

Staleness detection uses git commit timestamps rather than filesystem mtimes
so CI checkouts (which rewrite mtimes on every clone) do not spuriously mark
every artifact stale. When the artifact is untracked (not committed to git),
the collector falls back to the filesystem mtime to avoid hard-failing on
gitignored artifacts that are regenerated on demand.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
)

__all__ = ["CoverageCollector"]


# ---------------------------------------------------------------------------
# Tunables -- install hint phrased without naming any test-runner tool, so
# the source-audit meta-test (which greps this file for forbidden identifiers)
# stays GREEN. The goal of the hint is to tell a user they need a coverage
# artifact; how they generate it is a project-level concern.
# ---------------------------------------------------------------------------

_COVERAGE_INSTALL_HINT: str = (
    "generate a coverage report (coverage.xml or lcov.info) "
    "before running /project-metrics"
)

_NO_ARTIFACT_REASON: str = "no_artifact"

_GIT_LOG_TIMEOUT_SECONDS: float = 5.0

# Discovery order: repo root first (most common), then a conventional
# ``coverage/`` subdirectory. First hit wins. Cobertura before LCOV so XML
# wins when both are present -- arbitrary but stable.
_ARTIFACT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("coverage.xml", "cobertura"),
    ("coverage/coverage.xml", "cobertura"),
    ("lcov.info", "lcov"),
    ("coverage/lcov.info", "lcov"),
)


class CoverageCollector(Collector):
    """Tier 1 soft-dep line-coverage collector (reads existing artifacts)."""

    name = "coverage"
    tier = 1
    required = False
    languages: frozenset[str] = frozenset()

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the repo root used for artifact discovery.

        Unlike most collectors, ``CoverageCollector`` needs ``repo_root`` at
        construction time because ``resolve()`` walks the filesystem looking
        for an on-disk artifact. The runner also threads the authoritative
        ``repo_root`` through :attr:`CollectionContext.repo_root` for
        ``collect()``; the constructor value is primarily what ``resolve()``
        consults.

        When ``repo_root`` is ``None``, resolution falls back to the current
        working directory -- matching the behaviour of the other collectors
        that accept an optional constructor-time repo root.
        """

        self._configured_repo_root: Path | None = (
            Path(repo_root) if repo_root is not None else None
        )

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Discover an on-disk artifact and classify it as current or stale.

        Three outcomes map to:

        * ``Unavailable(reason="no_artifact", install_hint=...)`` when no
          Cobertura or LCOV file is found under the repo root.
        * ``Available(version="stale", ...)`` when the artifact's commit
          timestamp is strictly older than the HEAD commit timestamp.
        * ``Available(version="current", ...)`` otherwise.
        """

        _ = env  # env-carried PATH is irrelevant; this collector reads files
        repo_root = self._resolve_repo_root()
        discovered = _discover_artifact(repo_root)
        if discovered is None:
            return Unavailable(
                reason=_NO_ARTIFACT_REASON,
                install_hint=_COVERAGE_INSTALL_HINT,
            )

        artifact_path, artifact_format = discovered
        staleness = _check_staleness(repo_root, artifact_path)
        namespace_status, extra = _classify_staleness(staleness)
        version = "stale" if namespace_status == "stale" else "current"
        return Available(
            version=version,
            details=_build_resolve_details(
                namespace_status, artifact_path, artifact_format, extra
            ),
        )

    # ------------------------------------------------------------------ collect

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Parse the discovered artifact and produce the namespace payload.

        Re-runs the discovery and staleness check so the method is callable
        standalone (tests exercise ``collect()`` directly without a preceding
        ``resolve()``). Errors during parsing downgrade to ``status='error'``
        rather than raising -- the runner's try/except is a safety net for
        bugs, not the primary error path.
        """

        repo_root = Path(ctx.repo_root) if ctx.repo_root else self._resolve_repo_root()
        discovered = _discover_artifact(repo_root)
        if discovered is None:
            return CollectorResult(
                status="error",
                issues=["coverage artifact disappeared between resolve and collect"],
            )

        artifact_path, artifact_format = discovered
        try:
            line_pct, per_file = _parse_artifact(artifact_path, artifact_format)
        except (ET.ParseError, OSError, ValueError) as exc:
            return CollectorResult(
                status="error",
                issues=[f"coverage artifact parse failed: {exc!r}"],
            )

        namespace_status, extra = _classify_staleness(
            _check_staleness(repo_root, artifact_path)
        )
        data: dict[str, Any] = {
            "status": namespace_status,
            "artifact_path": str(artifact_path),
            "artifact_format": artifact_format,
            "line_pct": line_pct,
            "per_file": per_file,
            **extra,
        }
        return CollectorResult(status="ok", data=data)

    # ------------------------------------------------------------------ helpers

    def _resolve_repo_root(self) -> Path:
        """Return the repo root, falling back to CWD when none was configured."""

        if self._configured_repo_root is not None:
            return self._configured_repo_root
        return Path.cwd()


# ---------------------------------------------------------------------------
# Pure helpers -- artifact discovery, staleness detection, and format parsing.
# ---------------------------------------------------------------------------


def _discover_artifact(repo_root: Path) -> tuple[Path, str] | None:
    """Walk the candidate list; return the first existing artifact + format tag.

    First hit wins. No deeper search -- if the project stores the artifact
    outside the repo root or the ``coverage/`` subdirectory, the user can
    relocate or symlink it.
    """

    for relative, format_tag in _ARTIFACT_CANDIDATES:
        candidate = repo_root / relative
        if candidate.is_file():
            return candidate, format_tag
    return None


def _classify_staleness(
    staleness: tuple[int, int] | None,
) -> tuple[str, dict[str, str]]:
    """Map a staleness tuple to (namespace_status, extra_fields).

    ``None`` and the at-or-newer case both yield ``("ok", {})`` so downstream
    callers treat "could not compute" as "assume current". When the artifact
    is strictly older than HEAD, returns ``("stale", {"artifact_sha", "current_sha"})``.
    """

    if staleness is None:
        return "ok", {}
    artifact_ct, head_ct = staleness
    if artifact_ct < head_ct:
        return "stale", {
            "artifact_sha": str(artifact_ct),
            "current_sha": str(head_ct),
        }
    return "ok", {}


def _build_resolve_details(
    namespace_status: str,
    artifact_path: Path,
    artifact_format: str,
    extra: dict[str, str],
) -> dict[str, Any]:
    """Assemble the ``Available.details`` payload uniformly across branches."""

    details: dict[str, Any] = {
        "status": namespace_status,
        "artifact_path": str(artifact_path),
        "artifact_format": artifact_format,
    }
    details.update(extra)
    return details


def _check_staleness(repo_root: Path, artifact_path: Path) -> tuple[int, int] | None:
    """Return (artifact_commit_ts, head_commit_ts) tuple or None on failure.

    Runs two ``git log --format=%ct -1`` invocations: one scoped to the
    artifact's path, one for HEAD. When the artifact is untracked (git log
    returns empty output), falls back to the filesystem mtime so staleness
    detection still works for gitignored artifacts. Returns ``None`` when the
    HEAD timestamp cannot be determined (e.g., not a git repo); callers treat
    that case as "assume current".
    """

    head_ct = _run_git_commit_ts(repo_root, path=None)
    if head_ct is None:
        return None

    artifact_ct = _run_git_commit_ts(repo_root, path=str(artifact_path))
    if artifact_ct is None:
        artifact_ct = _filesystem_mtime(artifact_path)
        if artifact_ct is None:
            return None
    return artifact_ct, head_ct


def _run_git_commit_ts(repo_root: Path, path: str | None) -> int | None:
    """Shell out to ``git log --format=%ct -1`` for HEAD or a specific path.

    Returns the parsed integer timestamp, or ``None`` when git was not
    available, the command failed, or the output was empty. The ``--``
    separator is included when a path is supplied so ambiguous path/ref
    arguments are disambiguated.
    """

    argv: list[str] = ["git", "log", "--format=%ct", "-1"]
    if path is not None:
        argv.extend(["--", path])
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(repo_root),
            timeout=_GIT_LOG_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    stdout = (completed.stdout or "").strip()
    if not stdout:
        return None
    try:
        return int(stdout.splitlines()[0].strip())
    except (ValueError, IndexError):
        return None


def _filesystem_mtime(artifact_path: Path) -> int | None:
    """Return the artifact's filesystem mtime as an int, or None on failure."""

    try:
        return int(artifact_path.stat().st_mtime)
    except OSError:
        return None


def _parse_artifact(
    artifact_path: Path, artifact_format: str
) -> tuple[float, dict[str, dict[str, float | int]]]:
    """Dispatch to the Cobertura or LCOV parser based on the format tag."""

    if artifact_format == "cobertura":
        return _parse_cobertura(artifact_path)
    if artifact_format == "lcov":
        return _parse_lcov(artifact_path)
    raise ValueError(f"unknown coverage artifact format: {artifact_format!r}")


def _parse_cobertura(
    artifact_path: Path,
) -> tuple[float, dict[str, dict[str, float | int]]]:
    """Parse a Cobertura ``coverage.xml`` into (overall_line_pct, per_file).

    Overall rate is taken from the root ``<coverage>`` element's
    ``line-rate`` attribute, which Cobertura guarantees covers the whole
    report. Per-file totals are derived from each ``<class>`` element's
    ``<line>`` children: ``lines_total`` is the count of ``<line>`` entries
    and ``lines_covered`` is the count whose ``hits`` attribute is > 0.
    """

    tree = ET.parse(artifact_path)
    root = tree.getroot()

    line_pct = _safe_float(root.get("line-rate"), 0.0)

    per_file: dict[str, dict[str, float | int]] = {}
    for class_elem in root.iter("class"):
        filename = class_elem.get("filename") or class_elem.get("name")
        if not filename:
            continue
        lines_elem = class_elem.find("lines")
        if lines_elem is None:
            continue
        lines_total = 0
        lines_covered = 0
        for line in lines_elem.findall("line"):
            lines_total += 1
            if _safe_int(line.get("hits"), 0) > 0:
                lines_covered += 1
        per_file[filename] = _build_per_file_entry(lines_total, lines_covered)

    return line_pct, per_file


def _parse_lcov(
    artifact_path: Path,
) -> tuple[float, dict[str, dict[str, float | int]]]:
    """Parse an LCOV ``lcov.info`` into (overall_line_pct, per_file).

    LCOV records are separated by ``end_of_record`` lines. Each record has
    ``SF:<path>`` identifying the source file, ``DA:<line>,<hits>`` per
    executable line, and ``LF:<total>`` / ``LH:<hits>`` summary lines. When
    ``LF``/``LH`` are present they are preferred over recounting ``DA``
    entries; missing summaries fall back to the per-line count.
    """

    total_lines = 0
    covered_lines = 0
    per_file: dict[str, dict[str, float | int]] = {}
    record = _LcovRecord()

    for raw_line in artifact_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "end_of_record":
            finalized = record.finalize()
            if finalized is not None:
                path, lines_total, lines_covered = finalized
                per_file[path] = _build_per_file_entry(lines_total, lines_covered)
                total_lines += lines_total
                covered_lines += lines_covered
            record = _LcovRecord()
            continue
        record.feed(line)

    overall = covered_lines / total_lines if total_lines > 0 else 0.0
    return overall, per_file


def _build_per_file_entry(
    lines_total: int, lines_covered: int
) -> dict[str, float | int]:
    """Shape a per-file rollup entry consumed by both Cobertura and LCOV parsers."""

    line_pct = lines_covered / lines_total if lines_total > 0 else 0.0
    return {
        "line_pct": round(line_pct, 6),
        "lines_total": lines_total,
        "lines_covered": lines_covered,
    }


class _LcovRecord:
    """Running state for one LCOV record between SF: and end_of_record."""

    __slots__ = ("path", "da_total", "da_covered", "lf", "lh")

    def __init__(self) -> None:
        self.path: str | None = None
        self.da_total: int = 0
        self.da_covered: int = 0
        self.lf: int | None = None
        self.lh: int | None = None

    def feed(self, line: str) -> None:
        """Consume one LCOV line (already stripped, non-empty, not end_of_record)."""

        if line.startswith("SF:"):
            self.path = line[len("SF:") :].strip()
        elif line.startswith("DA:"):
            self._feed_da(line[len("DA:") :])
        elif line.startswith("LF:"):
            self.lf = _safe_int(line[len("LF:") :], 0)
        elif line.startswith("LH:"):
            self.lh = _safe_int(line[len("LH:") :], 0)

    def _feed_da(self, payload: str) -> None:
        parts = payload.split(",")
        if len(parts) < 2:
            return
        self.da_total += 1
        if _safe_int(parts[1], 0) > 0:
            self.da_covered += 1

    def finalize(self) -> tuple[str, int, int] | None:
        """Return (path, lines_total, lines_covered) or None for a record with no SF."""

        if self.path is None:
            return None
        lines_total = self.lf if self.lf is not None else self.da_total
        lines_covered = self.lh if self.lh is not None else self.da_covered
        return self.path, lines_total, lines_covered


def _safe_int(value: Any, default: int = 0) -> int:
    """Convert ``value`` to int, returning ``default`` on failure."""

    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert ``value`` to float, returning ``default`` on failure."""

    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
