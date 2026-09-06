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

A fourth namespace-only status, **partial**, layers on top of the three
resolve()-level outcomes above: a scoped test run rewrites the same
``coverage.xml`` a full-suite run would, so the artifact's
mere presence and freshness say nothing about how much of the repository it
actually measured. ``collect()`` compares ``measured_files`` (from the
artifact) against ``source_files_total`` (from the repository) and, when the
ratio falls under ``_MIN_ARTIFACT_SCOPE``, reports ``status == "partial"``
and withholds ``line_pct`` (set to ``None``) so a 2-of-190-file run cannot
masquerade as a repo-wide number. **Partial takes precedence over stale**:
an artifact that is both stale and under-scoped reports ``"partial"``, not
``"stale"`` -- the scope problem is the one that would otherwise corrupt
downstream aggregation and trends.

Payload emitted in ``data`` when available:

* ``status`` -- ``"ok"``, ``"stale"``, or ``"partial"``; the per-namespace
  marker consumed by the MD renderer to print the freshness/scope caveat.
* ``artifact_path`` -- absolute or repo-relative path of the parsed artifact;
  included so debugging "why did the number change?" is a one-glance check.
* ``artifact_format`` -- ``"cobertura"`` or ``"lcov"``; disambiguates which
  parser ran. Useful when both formats are present and one gets updated more
  often than the other.
* ``line_pct`` -- overall line coverage as a float in [0.0, 1.0], or ``None``
  when ``status == "partial"``.
* ``per_file`` -- dict mapping each source file to its own
  ``{"line_pct", "lines_total", "lines_covered"}`` triple. The aggregate
  composition layer reads this to populate per-file rollups. Emitted even
  when partial -- only the misleading aggregate is withheld.
* ``measured_files`` -- count of ``per_file`` keys that resolve to a path
  under ``repo_root``; scratch-directory-style absolute paths from a scoped
  run do not resolve there and are excluded.
* ``source_files_total`` -- count of repository files sharing the extension
  set of the measured files, excluding ecosystem-noise directories and
  test-shaped paths. The denominator that gives ``measured_files`` meaning.
* ``artifact_scope_pct`` -- ``measured_files / source_files_total``, or
  ``None`` when the denominator is zero (no comparable source files found).

Staleness detection uses git commit timestamps rather than filesystem mtimes
so CI checkouts (which rewrite mtimes on every clone) do not spuriously mark
every artifact stale. When the artifact is untracked (not committed to git),
the collector falls back to the filesystem mtime to avoid hard-failing on
gitignored artifacts that are regenerated on demand.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from scripts.project_metrics._path_filter import is_excluded_path
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

_COVERAGE_INSTALL_HINT_GENERIC: str = (
    "generate a coverage report (coverage.xml or lcov.info) before running /project-metrics"
)
_COVERAGE_INSTALL_HINT_REFRESH: str = (
    "run `/project-metrics --refresh-coverage` to invoke the project's "
    "configured coverage target and produce coverage.xml"
)

_NO_ARTIFACT_REASON: str = "no_artifact"

_GIT_LOG_TIMEOUT_SECONDS: float = 5.0
_GIT_LS_FILES_TIMEOUT_SECONDS: float = 5.0

# Discovery order: repo root first (most common), then a conventional
# ``coverage/`` subdirectory. First hit wins. Cobertura before LCOV so XML
# wins when both are present -- arbitrary but stable.
_ARTIFACT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("coverage.xml", "cobertura"),
    ("coverage/coverage.xml", "cobertura"),
    ("lcov.info", "lcov"),
    ("coverage/lcov.info", "lcov"),
)

# ---------------------------------------------------------------------------
# Artifact-scope calibration -- below this fraction of measured-vs-source
# files, an artifact is deemed too narrow to trust for a repo-wide line_pct
# (see the module docstring's "partial" status entry). 0.25 was chosen
# against this repo's own incident: the clobbered artifact measured 2 of 191
# files (0.010), the full one 140 of 191 (0.733) -- any threshold between
# those two values draws the same line.
# ---------------------------------------------------------------------------

_MIN_ARTIFACT_SCOPE: float = 0.25

# Basename shapes that mark a file as test code rather than source, for the
# ``source_files_total`` denominator. Matched with fnmatch, case-sensitive
# (test naming conventions in every language covered here are lower-case).
_TEST_BASENAME_GLOBS: tuple[str, ...] = (
    "test_*.*",
    "*_test.*",
    "conftest.py",
    "*.test.*",
    "*.spec.*",
)

# Directory-segment names that mark an entire subtree as test code.
_TEST_DIR_SEGMENTS: frozenset[str] = frozenset({"tests", "test"})


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

        self._configured_repo_root: Path | None = Path(repo_root) if repo_root is not None else None

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
                install_hint=_choose_install_hint(repo_root),
            )

        artifact_path, artifact_format = discovered
        staleness = _check_staleness(repo_root, artifact_path)
        namespace_status, extra = _classify_staleness(staleness)
        version = "stale" if namespace_status == "stale" else "current"
        return Available(
            version=version,
            details=_build_resolve_details(namespace_status, artifact_path, artifact_format, extra),
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

        namespace_status, extra = _classify_staleness(_check_staleness(repo_root, artifact_path))

        measured_files, measured_extensions = _classify_measured_files(per_file, repo_root)
        source_files_total = _count_source_files(repo_root, measured_extensions)
        artifact_scope_pct = _artifact_scope_pct(measured_files, source_files_total)

        is_partial = artifact_scope_pct is not None and artifact_scope_pct < _MIN_ARTIFACT_SCOPE
        issues: list[str] = []
        if is_partial:
            namespace_status = "partial"
            line_pct = None
            issues.append(
                f"coverage artifact measures only {measured_files} of "
                f"{source_files_total} source files -- regenerate coverage.xml "
                "from the full test suite before trusting line coverage"
            )

        data: dict[str, Any] = {
            "status": namespace_status,
            "artifact_path": str(artifact_path),
            "artifact_format": artifact_format,
            "line_pct": line_pct,
            "per_file": per_file,
            "measured_files": measured_files,
            "source_files_total": source_files_total,
            "artifact_scope_pct": artifact_scope_pct,
            **extra,
        }
        return CollectorResult(
            status="partial" if is_partial else "ok",
            data=data,
            issues=issues,
        )

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


# ---------------------------------------------------------------------------
# Artifact scope -- how much of the repository the artifact actually
# measured, independent of whether it's stale. See the module docstring's
# "partial" status entry for the incident this guards against.
# ---------------------------------------------------------------------------


def _classify_measured_files(
    per_file: dict[str, Any], repo_root: Path
) -> tuple[int, frozenset[str]]:
    """Count ``per_file`` keys that resolve under ``repo_root``; collect their extensions.

    A scoped test run still writes absolute paths for files outside the
    current tree in some environments (a test-runner scratch copy of the
    source tree, a different checkout). Those entries cannot
    be compared against ``repo_root``'s own file count without inflating or
    deflating the denominator, so they are excluded from both the numerator
    and the extension set that drives it. Resolution is lexical (``Path.resolve``
    with no existence requirement) -- the artifact may reference a file that
    has since been renamed or deleted, which is a legitimate measured entry.
    """

    resolved_repo_root = repo_root.resolve()
    measured = 0
    extensions: set[str] = set()
    for raw_path in per_file:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved != resolved_repo_root and resolved_repo_root not in resolved.parents:
            continue
        measured += 1
        suffix = Path(raw_path).suffix
        if suffix:
            extensions.add(suffix)
    return measured, frozenset(extensions)


def _is_test_shaped_path(repo_relative_path: str) -> bool:
    """Return True when ``repo_relative_path`` is test code, not source.

    Two independent shapes both disqualify a path: a ``tests/``/``test/``
    directory segment anywhere above the file, or a test-shaped basename
    (``test_*.py``, ``*_test.py``, ``conftest.py``, ``*.test.*``, ``*.spec.*``).
    Either alone is sufficient -- a helper module living inside ``tests/``
    with a plain name is still test code.
    """

    parts = [part for part in repo_relative_path.replace("\\", "/").split("/") if part]
    if not parts:
        return False
    directory_parts, basename = parts[:-1], parts[-1]
    if any(part in _TEST_DIR_SEGMENTS for part in directory_parts):
        return True
    return any(fnmatch.fnmatch(basename, pattern) for pattern in _TEST_BASENAME_GLOBS)


def _list_repo_files(repo_root: Path) -> list[str]:
    """Return every repo-relative file path, preferring ``git ls-files``.

    Falls back to a filesystem walk (pruning ``DEFAULT_EXCLUDED_DIRS``) when
    ``repo_root`` is not a git checkout or git is unavailable -- the
    denominator must still be computable for a plain directory.
    """

    tracked = _run_git_ls_files(repo_root)
    if tracked is not None:
        return tracked
    return _walk_repo_files(repo_root)


def _run_git_ls_files(repo_root: Path) -> list[str] | None:
    """Return ``git ls-files`` output as repo-relative paths, or None on failure."""

    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_LS_FILES_TIMEOUT_SECONDS,
            cwd=str(repo_root),
        )
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        OSError,
    ):
        return None
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _walk_repo_files(repo_root: Path) -> list[str]:
    """Enumerate files under ``repo_root`` via ``os.walk``, pruning excluded dirs."""

    results: list[str] = []
    for current_dir, dirnames, filenames in os.walk(repo_root):
        rel_dir = Path(current_dir).relative_to(repo_root).as_posix()
        dirnames[:] = [
            name
            for name in dirnames
            if not is_excluded_path(f"{rel_dir}/{name}" if rel_dir != "." else name)
        ]
        for filename in filenames:
            results.append(f"{rel_dir}/{filename}" if rel_dir != "." else filename)
    return results


def _count_source_files(repo_root: Path, extensions: frozenset[str]) -> int:
    """Count repository files sharing ``extensions``, excluding noise and test paths."""

    if not extensions:
        return 0
    count = 0
    for rel_path in _list_repo_files(repo_root):
        if is_excluded_path(rel_path):
            continue
        if _is_test_shaped_path(rel_path):
            continue
        if Path(rel_path).suffix in extensions:
            count += 1
    return count


def _artifact_scope_pct(measured_files: int, source_files_total: int) -> float | None:
    """Return ``measured_files / source_files_total``, or None when the denominator is zero."""

    if source_files_total <= 0:
        return None
    return measured_files / source_files_total


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


def _build_per_file_entry(lines_total: int, lines_covered: int) -> dict[str, float | int]:
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


def _choose_install_hint(repo_root: Path) -> str:
    """Pick the install hint that matches what the project already has wired.

    When ``pyproject.toml`` carries a ``[tool.coverage.*]`` section, the
    project has coverage tooling configured and the existing
    ``--refresh-coverage`` CLI flag will produce ``coverage.xml`` for
    them. Otherwise fall back to the generic "generate a coverage
    report" message that does not assume any particular workflow.

    Intentionally narrow: only the ``[tool.coverage.*]`` signal is
    consulted. The collector contract forbids referencing test-runner
    identifiers in this source file (an architectural invariant test
    enforces it), so the probe deliberately does not check for runner-
    specific markers like addopts.

    Designed to never raise: any IO failure falls back to the generic
    hint. The probe is intentionally lightweight (text grep, no TOML
    library).
    """

    if _pyproject_has_coverage_config(repo_root):
        return _COVERAGE_INSTALL_HINT_REFRESH
    return _COVERAGE_INSTALL_HINT_GENERIC


def _pyproject_has_coverage_config(repo_root: Path) -> bool:
    """Return True when ``pyproject.toml`` has a ``[tool.coverage.*]`` section.

    A single substring check is sufficient: ``[tool.coverage.`` is the
    canonical TOML header prefix for coverage.py configuration and is
    distinctive enough that false positives are not a realistic risk.
    """

    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return "[tool.coverage." in text


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
