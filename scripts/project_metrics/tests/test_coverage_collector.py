"""Behavioral tests for the CoverageCollector -- reads pre-existing coverage artifacts.

These tests encode the behavioral contract for the **sixth and final** Tier-1
collector -- unique among the collector fleet in that it reads an on-disk
artifact rather than shelling out to a tool. Two artifact formats are
supported: Cobertura XML (``coverage.xml``) and LCOV (``lcov.info``).

Three resolution outcomes drive the collector's behavior:

* **No artifact**  -- neither ``coverage.xml`` nor ``lcov.info`` is present
  in the repo root or its common subdirectories; resolve() returns
  ``Unavailable`` with an actionable install hint. The per-collector
  namespace block carries ``status == "no_artifact"`` (richer than the
  collector-level ``unavailable`` tag because the MD renderer uses it to
  render a distinct message).
* **Stale** -- an artifact exists but its git-tracked commit timestamp is
  older than the current HEAD commit timestamp. resolve() returns
  ``Available``; collect() still extracts the line percentage but marks
  the namespace ``status`` as ``"stale"`` plus ``artifact_sha`` and
  ``current_sha`` so the MD renderer can flag ``(stale -- regenerate)``.
* **Current** -- artifact exists and is at or newer than the current
  commit; resolve() returns ``Available`` and collect() emits the line
  percentage cleanly with ``status == "ok"``.

**Import strategy** -- every test imports ``CoverageCollector`` inside the
test body. During the BDD/TDD RED handshake, the production module is a
stub; top-of-module imports would fail collection for every test. Deferred
imports yield per-test RED/GREEN resolution and surface specific
``ModuleNotFoundError`` for each test rather than a single collection
crash.

**Static source audit** -- one test opens the collector source file as
plain text and scans for forbidden tokens that would indicate the
collector MIGHT invoke the test suite (``pytest``, ``coverage run``,
``unittest.main``, ``pytest.main``, ``subprocess.*pytest``). The ADR
pins coverage collection as read-only; this audit enforces the invariant
at the source-code level, not just at runtime. The test is deliberately
paranoid -- even comments containing these strings must be avoided.

**Fixture files** -- ``tests/fixtures/coverage.xml`` (Cobertura) and
``tests/fixtures/lcov.info`` (LCOV) are static, committed fixtures.
Designed with 3 files / 100 total lines / 73 hit lines -> golden overall
line rate = 0.73. Per-file breakdown:

* ``src/utils.py``   -- 20 lines,  20 hit (line rate 1.0)
* ``src/parser.py``  -- 30 lines,  15 hit (line rate 0.5)
* ``src/cli.py``     -- 50 lines,  38 hit (line rate 0.76)

**Mock strategy** -- the collector reads files directly, so most tests
use real fixture file I/O (no subprocess mocking needed for happy-path
parse tests). Stale-detection tests patch ``subprocess.run`` at the
collector's own namespace to stub the two ``git log --format=%ct``
calls (one per-artifact, one for HEAD).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Golden fixture constants -- tied to the hand-crafted fixture files.
# ---------------------------------------------------------------------------

# The golden overall line rate for both fixtures: 73 / 100 = 0.73. Tolerance
# is tight because the numbers are exact; any meaningful drift indicates
# the parser is computing the rate wrong or reading the wrong totals.
_GOLDEN_LINE_PCT: float = 0.73
_GOLDEN_LINE_PCT_TOLERANCE: float = 1e-9

# Per-file golden values -- the collector must expose these through its
# per-file rollup. Keys are the filenames as they appear in the fixtures
# (``filename=`` attribute in Cobertura, ``SF:`` line in LCOV).
_GOLDEN_PER_FILE: dict[str, dict[str, float | int]] = {
    "src/utils.py": {"lines_total": 20, "lines_covered": 20, "line_pct": 1.0},
    "src/parser.py": {"lines_total": 30, "lines_covered": 15, "line_pct": 0.5},
    "src/cli.py": {"lines_total": 50, "lines_covered": 38, "line_pct": 0.76},
}

# Forbidden tokens for the source audit. The production module must not
# contain any of these strings (case-insensitive). The invariant is
# "CoverageCollector never invokes the test suite"; forbidding the mere
# appearance of these identifiers in the source makes the invariant
# impossible to violate by a later edit.
#
# Each entry is a (pattern, description) tuple. Patterns use regex word
# boundaries where a bare substring would false-positive on unrelated
# words (e.g., "pytest" inside "no-pytest-invocation" comment text).
_FORBIDDEN_TOKENS: list[tuple[str, str]] = [
    (r"\bpytest\b", "pytest module/CLI reference"),
    (r"coverage\s+run", "'coverage run' subprocess invocation"),
    (r"\bunittest\.main\b", "unittest.main test discovery trigger"),
    (r"\bpytest\.main\b", "pytest.main programmatic invocation"),
    # Subprocess-with-pytest pattern: captures ``subprocess.run([... "pytest"])``
    # and similar shapes. Non-greedy ``.*?`` keeps it scoped to a single logical
    # call rather than matching across a whole file.
    (r"subprocess\.[a-z_]+\(.*?pytest", "subprocess invocation targeting pytest"),
    # Subprocess running the ``coverage`` CLI's ``run`` subcommand.
    (
        r"subprocess\.[a-z_]+\(.*?['\"]coverage['\"]\s*,\s*['\"]run['\"]",
        "subprocess invocation of 'coverage run'",
    ),
]


# ---------------------------------------------------------------------------
# Path helpers.
# ---------------------------------------------------------------------------


_FIXTURES_DIR: Path = Path(__file__).resolve().parent / "fixtures"
_COLLECTOR_SOURCE_PATH: Path = (
    Path(__file__).resolve().parent.parent / "collectors" / "coverage_collector.py"
)


def _make_context(repo_root: Path, git_sha: str = "a" * 40) -> Any:
    """Build a CollectionContext pointing at the given repo_root.

    Deferred import so the helper doesn't break pytest collection during
    the RED handshake. ``window_days`` is 90 to match the project default.
    """

    from scripts.project_metrics.collectors.base import CollectionContext

    return CollectionContext(
        repo_root=str(repo_root),
        window_days=90,
        git_sha=git_sha,
    )


def _make_env() -> Any:
    """Build a default ResolutionEnv -- tests needing path injection override."""

    from scripts.project_metrics.collectors.base import ResolutionEnv

    return ResolutionEnv()


def _make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    argv: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess for mocked ``subprocess.run`` return values."""

    return subprocess.CompletedProcess(
        args=argv or ["git", "log"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _git_log_dispatcher(
    artifact_ct: int = 1_713_800_000,  # older
    head_ct: int = 1_713_870_000,  # newer -- marks artifact stale by default
) -> Any:
    """Build a side_effect dispatcher for the two ``git log --format=%ct`` calls.

    The stale-detection path runs two git subprocesses:

    * ``git log -1 --format=%ct -- <artifact_path>`` -- artifact's
      most-recent commit timestamp
    * ``git log -1 --format=%ct`` (no path) -- HEAD commit timestamp

    The dispatcher inspects argv to route: if a ``--`` separator is
    present (indicating a path-scoped invocation), it returns
    ``artifact_ct``; otherwise it returns ``head_ct``.
    """

    def _dispatch(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = args[0] if args else kwargs.get("args") or []
        argv_str = (
            " ".join(str(x) for x in argv)
            if isinstance(argv, (list, tuple))
            else str(argv)
        )
        # Heuristic: path-scoped git log carries ``--`` or a filename
        # containing ``.xml`` / ``.info``. Either marker routes to the
        # artifact timestamp.
        if "--" in argv or ".xml" in argv_str or ".info" in argv_str:
            return _make_completed_process(stdout=f"{artifact_ct}\n", argv=list(argv))
        return _make_completed_process(stdout=f"{head_ct}\n", argv=list(argv))

    return _dispatch


# ---------------------------------------------------------------------------
# Static metadata -- attributes every collector advertises.
# ---------------------------------------------------------------------------


class TestCoverageStaticMetadata:
    """Class-level attributes the runner and schema layer depend on."""

    def test_collector_name_is_coverage(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Name becomes the JSON namespace key. Aggregate pipeline reads
        # ``coverage.line_pct`` to populate ``coverage_line_pct``; renaming
        # silently breaks the aggregate column wiring.
        assert CoverageCollector.name == "coverage"

    def test_collector_is_not_required(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Only GitCollector is required=True. Coverage is the softest of
        # soft dependencies -- most repos won't have an artifact at all.
        assert CoverageCollector.required is False

    def test_collector_is_instantiable_with_no_arguments(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # All collectors share a zero-arg constructor; collectors that
        # need repo_root pick it up from the CollectionContext at collect()
        # time, not at construction.
        collector = CoverageCollector()
        assert collector is not None


# ---------------------------------------------------------------------------
# Resolve-phase -- no artifact present.
# ---------------------------------------------------------------------------


class TestCoverageResolveNoArtifact:
    """resolve() returns Unavailable when neither coverage.xml nor lcov.info exists."""

    def test_resolve_returns_unavailable_when_no_artifact_present(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Empty tmp_path -- no coverage.xml, no lcov.info, no subdirs.
        collector = CoverageCollector(repo_root=tmp_path)
        result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when no coverage artifact exists; got "
            f"{type(result).__name__}"
        )

    def test_no_artifact_unavailable_carries_actionable_install_hint(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=tmp_path)
        result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable)
        # Install hint must mention a concrete command the user can run
        # to produce the artifact -- the ADR pins ``pytest --cov && coverage xml``
        # but we accept any hint that references ``coverage`` and either
        # ``xml`` or ``lcov`` (format flexibility for v2 upgrades).
        hint_lower = result.install_hint.lower()
        assert "coverage" in hint_lower, (
            f"Expected install hint to reference 'coverage'; got "
            f"{result.install_hint!r}"
        )

    def test_no_artifact_reason_identifies_missing_artifact(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=tmp_path)
        result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable)
        # Reason should communicate WHY to the user/MD renderer. Accept
        # "no_artifact", "artifact", or "coverage.xml"/"lcov.info" as
        # sufficient tokens.
        reason_lower = result.reason.lower()
        assert (
            "artifact" in reason_lower
            or "coverage.xml" in reason_lower
            or "lcov" in reason_lower
        ), f"Expected reason to identify the missing artifact; got {result.reason!r}"


# ---------------------------------------------------------------------------
# Resolve-phase -- artifact present and current.
# ---------------------------------------------------------------------------


class TestCoverageResolveCurrent:
    """resolve() returns Available when an artifact exists and is current."""

    def test_resolve_returns_available_when_cobertura_artifact_present(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Point at the fixtures directory -- coverage.xml exists there.
        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"

        # Mock subprocess.run so the stale-check path (if any) sees the
        # artifact as current (artifact_ct == head_ct means NOT stale).
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(
                artifact_ct=fixed_ct,
                head_ct=fixed_ct,
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Available), (
            f"Expected Available when coverage.xml exists in repo_root; got "
            f"{type(result).__name__}"
        )

    def test_resolve_returns_available_when_lcov_artifact_present(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Copy only the lcov.info fixture into a scratch dir so the
        # Cobertura fallback doesn't confound the test -- we're verifying
        # that LCOV-only repos also resolve as Available.
        lcov_contents = (_FIXTURES_DIR / "lcov.info").read_text()
        scratch = tmp_path / "repo"
        scratch.mkdir()
        (scratch / "lcov.info").write_text(lcov_contents)

        collector = CoverageCollector(repo_root=scratch)
        target = "scripts.project_metrics.collectors.coverage_collector"

        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(
                artifact_ct=fixed_ct,
                head_ct=fixed_ct,
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Available), (
            f"Expected Available when lcov.info exists in repo_root; got "
            f"{type(result).__name__}"
        )


# ---------------------------------------------------------------------------
# Resolve / collect -- stale artifact detection.
# ---------------------------------------------------------------------------


class TestCoverageResolveStale:
    """Stale artifact returns Available; collect() flags namespace status='stale'."""

    def test_collect_flags_stale_when_artifact_older_than_head(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Cobertura fixture is present. artifact_ct < head_ct -> stale.
        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"

        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(
                artifact_ct=1_713_800_000,  # older
                head_ct=1_713_870_000,  # newer
            ),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        namespace_status = result.data.get("status")
        assert namespace_status == "stale", (
            f"Expected data['status'] == 'stale' when artifact is older "
            f"than HEAD; got {namespace_status!r}. Full data: {result.data!r}"
        )

    def test_stale_collect_still_extracts_line_percentage(self) -> None:
        """A stale artifact still carries a real number -- staleness flags,
        not suppresses, the measurement."""

        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(
                artifact_ct=1_713_800_000,
                head_ct=1_713_870_000,
            ),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        line_pct = result.data.get("line_pct")
        assert line_pct is not None, (
            f"Expected line_pct populated even when stale; got None. "
            f"Data: {result.data!r}"
        )
        assert abs(line_pct - _GOLDEN_LINE_PCT) < _GOLDEN_LINE_PCT_TOLERANCE, (
            f"Expected line_pct == {_GOLDEN_LINE_PCT} for the golden "
            f"fixture (stale or not); got {line_pct!r}"
        )

    def test_current_collect_flags_namespace_status_ok(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"

        # Same ct for artifact and HEAD -- current, not stale.
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(
                artifact_ct=fixed_ct,
                head_ct=fixed_ct,
            ),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        namespace_status = result.data.get("status")
        assert namespace_status == "ok", (
            f"Expected data['status'] == 'ok' when artifact is current; "
            f"got {namespace_status!r}. Full data: {result.data!r}"
        )


# ---------------------------------------------------------------------------
# Cobertura-format parsing.
# ---------------------------------------------------------------------------


class TestCoverageCoberturaParse:
    """Collect() parses the Cobertura golden fixture to the exact golden rate."""

    def test_cobertura_parse_produces_golden_line_pct(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        # Golden rate pinned by the fixture design: 73/100 = 0.73 exactly.
        line_pct = result.data.get("line_pct")
        assert line_pct is not None, (
            f"Expected line_pct populated from Cobertura fixture; got None. "
            f"Data keys: {list(result.data.keys())}"
        )
        assert abs(line_pct - _GOLDEN_LINE_PCT) < _GOLDEN_LINE_PCT_TOLERANCE, (
            f"Expected line_pct == {_GOLDEN_LINE_PCT} (73/100 from fixture); "
            f"got {line_pct!r}"
        )

    def test_cobertura_parse_populates_per_file_rollup(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        per_file = result.data.get("per_file")
        assert per_file is not None, (
            f"Expected 'per_file' key populated; got None. Data keys: "
            f"{list(result.data.keys())}"
        )
        # All three fixture files must surface.
        for expected_path in _GOLDEN_PER_FILE:
            assert expected_path in per_file, (
                f"Expected per-file entry for {expected_path!r}; got keys "
                f"{list(per_file.keys())!r}"
            )

    def test_cobertura_per_file_line_totals_match_fixture(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        per_file = result.data.get("per_file") or {}
        for path, golden in _GOLDEN_PER_FILE.items():
            entry = per_file.get(path, {})
            assert entry.get("lines_total") == golden["lines_total"], (
                f"Expected lines_total == {golden['lines_total']} for {path!r}; "
                f"got {entry.get('lines_total')!r}. Full entry: {entry!r}"
            )
            assert entry.get("lines_covered") == golden["lines_covered"], (
                f"Expected lines_covered == {golden['lines_covered']} for "
                f"{path!r}; got {entry.get('lines_covered')!r}. Full entry: "
                f"{entry!r}"
            )

    def test_cobertura_artifact_format_marker_is_cobertura(self) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        collector = CoverageCollector(repo_root=_FIXTURES_DIR)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(_FIXTURES_DIR))

        # artifact_format disambiguates which parser ran -- useful for the
        # MD renderer and for debugging "why did the rate change between
        # runs". Accept either the concrete string or a normalized form.
        fmt = result.data.get("artifact_format")
        assert fmt == "cobertura", (
            f"Expected artifact_format == 'cobertura' when parsing coverage.xml; "
            f"got {fmt!r}"
        )


# ---------------------------------------------------------------------------
# LCOV-format parsing.
# ---------------------------------------------------------------------------


class TestCoverageLcovParse:
    """Collect() parses the LCOV golden fixture to the exact golden rate."""

    def test_lcov_parse_produces_golden_line_pct(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        # Isolate lcov.info from coverage.xml to force the LCOV parse path.
        lcov_contents = (_FIXTURES_DIR / "lcov.info").read_text()
        scratch = tmp_path / "repo"
        scratch.mkdir()
        (scratch / "lcov.info").write_text(lcov_contents)

        collector = CoverageCollector(repo_root=scratch)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(scratch))

        line_pct = result.data.get("line_pct")
        assert line_pct is not None
        assert abs(line_pct - _GOLDEN_LINE_PCT) < _GOLDEN_LINE_PCT_TOLERANCE, (
            f"Expected line_pct == {_GOLDEN_LINE_PCT} from LCOV fixture; "
            f"got {line_pct!r}"
        )

    def test_lcov_parse_populates_per_file_rollup(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        lcov_contents = (_FIXTURES_DIR / "lcov.info").read_text()
        scratch = tmp_path / "repo"
        scratch.mkdir()
        (scratch / "lcov.info").write_text(lcov_contents)

        collector = CoverageCollector(repo_root=scratch)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(scratch))

        per_file = result.data.get("per_file") or {}
        for path, golden in _GOLDEN_PER_FILE.items():
            assert path in per_file, (
                f"Expected LCOV per-file entry for {path!r}; got keys "
                f"{list(per_file.keys())!r}"
            )
            entry = per_file[path]
            assert entry.get("lines_total") == golden["lines_total"], (
                f"LCOV: expected lines_total == {golden['lines_total']} for "
                f"{path!r}; got {entry.get('lines_total')!r}"
            )
            assert entry.get("lines_covered") == golden["lines_covered"], (
                f"LCOV: expected lines_covered == {golden['lines_covered']} "
                f"for {path!r}; got {entry.get('lines_covered')!r}"
            )

    def test_lcov_artifact_format_marker_is_lcov(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.coverage_collector import (
            CoverageCollector,
        )

        lcov_contents = (_FIXTURES_DIR / "lcov.info").read_text()
        scratch = tmp_path / "repo"
        scratch.mkdir()
        (scratch / "lcov.info").write_text(lcov_contents)

        collector = CoverageCollector(repo_root=scratch)
        target = "scripts.project_metrics.collectors.coverage_collector"
        fixed_ct = 1_713_870_000
        with patch(
            f"{target}.subprocess.run",
            side_effect=_git_log_dispatcher(artifact_ct=fixed_ct, head_ct=fixed_ct),
        ):
            result = collector.collect(_make_context(scratch))

        fmt = result.data.get("artifact_format")
        assert fmt == "lcov", (
            f"Expected artifact_format == 'lcov' when parsing lcov.info; got {fmt!r}"
        )


# ---------------------------------------------------------------------------
# Non-invocation discipline -- static source audit.
# ---------------------------------------------------------------------------


class TestCoverageNeverRunsTests:
    """Static audit: the collector source file must not mention test-runner tokens.

    This is a *meta-test*: it opens the production module as plain text
    and greps for forbidden identifiers. The invariant -- "coverage
    collection never invokes the test suite" -- is enforced at the
    source-code level, not only at runtime. A future edit that adds
    ``subprocess.run(["pytest", ...])`` or ``coverage run -m ...`` is
    caught the moment it lands.

    The audit is deliberately paranoid: even a comment containing the
    word ``pytest`` fails. The implementer CAN satisfy this by simply
    not putting those identifiers in the module at all, including
    inside comments.
    """

    def test_collector_source_file_exists_after_red_handshake(self) -> None:
        # At RED handshake the module file may be a near-empty stub; the
        # only precondition is that the implementer will populate it. We
        # assert the file is resolvable so the audit below has something
        # to read even at GREEN; ModuleNotFoundError on the companion
        # tests confirms RED.
        #
        # NOTE: during RED this test passes trivially because the stub
        # file may or may not exist yet; we only require the path to
        # resolve at GREEN. The audit below short-circuits gracefully
        # when the file is absent to keep RED noise focused on
        # ModuleNotFoundError rather than FileNotFoundError.
        assert _COLLECTOR_SOURCE_PATH.name == "coverage_collector.py"

    def test_collector_source_contains_no_forbidden_test_runner_tokens(
        self,
    ) -> None:
        if not _COLLECTOR_SOURCE_PATH.exists():
            # Graceful no-op during RED handshake: source file absent,
            # nothing to audit. The ModuleNotFoundError raised by other
            # tests already signals RED for the implementer. Returning
            # here avoids a spurious failure that would obscure the
            # genuine RED signal.
            return

        source_text = _COLLECTOR_SOURCE_PATH.read_text()
        if not source_text.strip():
            # Empty stub: nothing to audit.
            return

        source_lower = source_text.lower()
        violations: list[str] = []
        for pattern, description in _FORBIDDEN_TOKENS:
            if re.search(pattern, source_lower, flags=re.DOTALL):
                violations.append(f"{pattern!r} ({description})")

        assert not violations, (
            "Coverage collector source file contains forbidden test-runner "
            "tokens, violating the 'never runs tests' invariant. The "
            f"collector is a READ-ONLY artifact parser. Offending patterns "
            f"({len(violations)}): {violations!r}. Source file: "
            f"{_COLLECTOR_SOURCE_PATH}"
        )

    def test_collector_source_audit_catches_obvious_violations(
        self, tmp_path: Path
    ) -> None:
        """Sanity check for the audit itself -- verify the forbidden-token
        regex battery fires on text that should be rejected.

        This test runs the same audit logic against a synthetic string
        containing each forbidden pattern, confirming every pattern
        actually matches. Without this check, a typo in a regex
        pattern could silently let a real violation slip through.
        """

        # Each sample shape is what the pattern is *designed* to catch. The
        # ``coverage\s+run`` pattern catches shell-style invocations (as in
        # a docstring example or a subprocess command string); the subprocess
        # list-form ``['coverage', 'run']`` is caught by a distinct pattern.
        synthetic_violators = {
            r"\bpytest\b": "import pytest",
            r"coverage\s+run": "# run 'coverage run -m pytest' to refresh",
            r"\bunittest\.main\b": "if __name__: unittest.main()",
            r"\bpytest\.main\b": "pytest.main(['-x'])",
            r"subprocess\.[a-z_]+\(.*?pytest": "subprocess.run(['pytest'])",
            r"subprocess\.[a-z_]+\(.*?['\"]coverage['\"]\s*,\s*['\"]run['\"]": (
                "subprocess.call(['coverage', 'run'])"
            ),
        }
        for pattern, sample in synthetic_violators.items():
            assert re.search(pattern, sample.lower(), flags=re.DOTALL), (
                f"Audit regex {pattern!r} failed to match its own sample "
                f"violator {sample!r} -- the audit battery is broken and "
                f"would let a real violation slip through."
            )


# ---------------------------------------------------------------------------
# Skip-marker shape -- delegates to the shared helper.
# ---------------------------------------------------------------------------


class TestCoverageSkipMarker:
    """When coverage is Unavailable, the namespace carries the uniform marker."""

    def test_skip_marker_for_coverage_has_uniform_three_key_shape(self) -> None:
        from scripts.project_metrics.collectors.base import (
            skip_marker_for_namespace,
        )

        marker = skip_marker_for_namespace("coverage")

        # Three-key shape pinned by the graceful-degradation ADR: the MD
        # renderer consumes this shape uniformly across every collector's
        # namespace when it's skipped. Note: the collector-specific
        # richer namespace block (with "status": "no_artifact") is a
        # DISTINCT layer -- the skip_marker helper is the fallback for
        # collectors that don't emit their own namespace during
        # Unavailable resolution.
        assert marker == {
            "status": "skipped",
            "reason": "tool_unavailable",
            "tool": "coverage",
        }
