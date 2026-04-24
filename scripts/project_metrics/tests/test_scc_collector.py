"""Behavioral tests for the SccCollector against mocked subprocess invocations.

These tests encode the contract from the plan (step S6a in
``.ai-work/project-metrics/IMPLEMENTATION_PLAN.md``), the collector-protocol ADR
(``dec-draft-c566b978``) and the graceful-degradation ADR (``dec-draft-8b26adef``).
They are written *from the behavioral spec*, not the implementation — production
code (``scripts/project_metrics/collectors/scc_collector.py``) does not yet
exist when these tests are written. Deferred imports give each test a clean
RED signal during the BDD/TDD handshake instead of collapsing collection for
the whole file.

**scc is a soft dependency** (``required = False``). When ``resolve()`` reports
``Unavailable`` the runner feeds the uniform 3-key skip marker into the
``scc`` namespace so the MD renderer can degrade gracefully.

**Mock strategy** — every subprocess interaction is patched at
``scripts.project_metrics.collectors.scc_collector.subprocess.run`` and
``shutil.which`` is patched via :class:`ResolutionEnv` whose ``which`` method
is backed by ``shutil.which``; tests monkeypatch ``shutil.which`` at the
module level so the collector's ``env.which("scc")`` probe is intercepted
without requiring knowledge of the collector's internal structure.

**Canned scc JSON fixture** — one realistic ``scc --format json`` payload
covering 2 languages (Python + Markdown), 4 files, computable totals.
Reused across the "collect succeeds" tests so golden values derive once.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Golden constants — derived from the plan and the two canonical ADRs.
# ---------------------------------------------------------------------------

# Collector identity (plan § S6a; collector-protocol ADR):
#   name becomes the JSON namespace key.
#   tier = 0 (universal; scc augments SLOC totals when present).
#   required = False (soft dependency — graceful skip when absent).
_EXPECTED_NAME: str = "scc"
_EXPECTED_TIER: int = 0
_EXPECTED_REQUIRED: bool = False

# Pinned version string the tests expect ``scc --version`` to emit. Matches the
# ``v3.7.0+`` lower bound in the plan's Tech Stack section.
_SCC_VERSION_STDOUT: str = "scc version 3.7.0\n"
_EXPECTED_SCC_VERSION: str = "3.7.0"

# Short probe timeout expected for ``scc --version`` (plan § S6a: "2s timeout").
# Tests do not assert the exact value (implementer's choice) but do assert
# that a ``TimeoutExpired`` surfaces as ``Unavailable`` with a probe-timed-out
# reason fragment.
_SCC_PROBE_TIMEOUT_FRAGMENT: str = "timed out"

# From the graceful-degradation ADR, the namespace skip-marker shape is a
# 3-key dict exactly matching ``skip_marker_for_namespace`` in base.py.
_EXPECTED_SKIP_MARKER: dict[str, str] = {
    "status": "skipped",
    "reason": "tool_unavailable",
    "tool": "scc",
}

# From the collector-protocol ADR, four canonical statuses.
_COLLECTOR_RESULT_STATUSES: frozenset[str] = frozenset(
    {"ok", "partial", "error", "timeout"}
)


# ---------------------------------------------------------------------------
# Canned scc JSON fixture — module-level constant reused across the collect()
# success tests. Shape matches ``scc --format json`` (top-level list of
# language objects with per-file records).
# ---------------------------------------------------------------------------

SAMPLE_SCC_JSON: list[dict[str, Any]] = [
    {
        "Name": "Python",
        "Bytes": 8200,
        "CodeBytes": 7100,
        "Lines": 530,
        "Code": 450,
        "Comment": 50,
        "Blank": 30,
        "Complexity": 120,
        "Count": 3,
        "WeightedComplexity": 0,
        "Files": [
            {
                "Filename": "scripts/project_metrics/foo.py",
                "Language": "Python",
                "Bytes": 3500,
                "Lines": 220,
                "Code": 180,
                "Comment": 25,
                "Blank": 15,
                "Complexity": 55,
            },
            {
                "Filename": "scripts/project_metrics/bar.py",
                "Language": "Python",
                "Bytes": 3100,
                "Lines": 210,
                "Code": 175,
                "Comment": 20,
                "Blank": 15,
                "Complexity": 48,
            },
            {
                "Filename": "scripts/project_metrics/__init__.py",
                "Language": "Python",
                "Bytes": 1600,
                "Lines": 100,
                "Code": 95,
                "Comment": 5,
                "Blank": 0,
                "Complexity": 17,
            },
        ],
    },
    {
        "Name": "Markdown",
        "Bytes": 4100,
        "CodeBytes": 3900,
        "Lines": 180,
        "Code": 150,
        "Comment": 0,
        "Blank": 30,
        "Complexity": 0,
        "Count": 2,
        "WeightedComplexity": 0,
        "Files": [
            {
                "Filename": "docs/README.md",
                "Language": "Markdown",
                "Bytes": 2600,
                "Lines": 110,
                "Code": 95,
                "Comment": 0,
                "Blank": 15,
                "Complexity": 0,
            },
            {
                "Filename": "docs/INSTALL.md",
                "Language": "Markdown",
                "Bytes": 1500,
                "Lines": 70,
                "Code": 55,
                "Comment": 0,
                "Blank": 15,
                "Complexity": 0,
            },
        ],
    },
]

# Derived golden aggregates (computed from SAMPLE_SCC_JSON so the tests catch
# any drift between the fixture and the expected rollup):
_EXPECTED_SLOC_TOTAL: int = 450 + 150  # Python 450 Code + Markdown 150 Code = 600
_EXPECTED_LANGUAGE_COUNT: int = 2
_EXPECTED_FILE_COUNT: int = 5  # 3 Python + 2 Markdown


# ---------------------------------------------------------------------------
# Helper builders — construct ``subprocess.run`` return values matching both
# the ``scc --version`` probe and the ``scc --format json <repo>`` invocation.
# ---------------------------------------------------------------------------


def _completed_version_process() -> SimpleNamespace:
    """Return a stand-in for ``subprocess.run`` result of ``scc --version``.

    ``SimpleNamespace`` mirrors the attribute access surface the collector
    uses (``returncode``, ``stdout``, ``stderr``) without binding to
    ``CompletedProcess``'s full constructor signature.
    """

    return SimpleNamespace(
        returncode=0,
        stdout=_SCC_VERSION_STDOUT,
        stderr="",
    )


def _completed_collect_process(payload: list[dict[str, Any]]) -> SimpleNamespace:
    """Return a stand-in for ``scc --format json <repo>`` success output."""

    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def _build_run_side_effect(
    version_result: SimpleNamespace | Exception,
    collect_result: SimpleNamespace | Exception | None = None,
):
    """Construct a side effect routing ``scc --version`` vs ``scc --format json``.

    The collector invokes ``subprocess.run(["scc", "--version"], ...)`` during
    ``resolve`` and ``subprocess.run(["scc", "--format", "json", <repo>], ...)``
    during ``collect``. This helper inspects ``args[0]`` (the command list) to
    decide which canned result to return; it raises if either side is
    exercised without being configured.
    """

    def _side_effect(*args: Any, **_kwargs: Any) -> SimpleNamespace:
        cmd = args[0]
        if (
            isinstance(cmd, list)
            and len(cmd) >= 2
            and cmd[0] == "scc"
            and cmd[1] == "--version"
        ):
            if isinstance(version_result, Exception):
                raise version_result
            return version_result
        if (
            isinstance(cmd, list)
            and len(cmd) >= 3
            and cmd[0] == "scc"
            and cmd[1] == "--format"
        ):
            if collect_result is None:
                raise AssertionError(
                    "collect_result not configured, but collector invoked scc --format json"
                )
            if isinstance(collect_result, Exception):
                raise collect_result
            return collect_result
        raise AssertionError(
            f"Unexpected subprocess.run invocation: args={args!r} kwargs={_kwargs!r}"
        )

    return _side_effect


# ---------------------------------------------------------------------------
# Collector-identity tests — class-level attributes and describe() contract.
# ---------------------------------------------------------------------------


class TestSccCollectorIdentity:
    """The four class-level attributes the runner uses for registration."""

    def test_name_is_scc(self) -> None:
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        assert SccCollector.name == _EXPECTED_NAME, (
            f"SccCollector.name must be {_EXPECTED_NAME!r}; "
            f"got {SccCollector.name!r}. Namespace key in report JSON."
        )

    def test_tier_is_zero(self) -> None:
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        # scc augments the Tier 0 universal layer (SLOC totals and language
        # breakdown); tier=0 per the plan's § Tech Stack + § S6a.
        assert SccCollector.tier == _EXPECTED_TIER

    def test_required_is_false(self) -> None:
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        # Soft dependency — absence degrades to the stdlib SLOC fallback
        # in GitCollector, not an abort.
        assert SccCollector.required is _EXPECTED_REQUIRED, (
            "SccCollector must be a soft dep (required=False); only "
            "GitCollector is the hard floor."
        )

    def test_describe_returns_valid_description(self) -> None:
        from scripts.project_metrics.collectors.base import CollectorDescription
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        description = SccCollector().describe()
        assert isinstance(description, CollectorDescription)
        assert description.name == _EXPECTED_NAME
        assert description.tier == _EXPECTED_TIER
        # Languages attribute is a frozenset — scc is language-agnostic (it
        # detects languages itself), so the attribute is empty or at least
        # a frozenset.
        assert isinstance(description.languages, frozenset)


# ---------------------------------------------------------------------------
# resolve() — Available case: scc binary on PATH, --version succeeds.
# ---------------------------------------------------------------------------


class TestSccResolveAvailable:
    """scc present and responsive — resolve() must return Available."""

    def test_resolve_returns_available_when_scc_version_succeeds(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Available, ResolutionEnv
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        with (
            patch(
                "scripts.project_metrics.collectors.scc_collector.shutil.which",
                return_value="/usr/local/bin/scc",
            ),
            patch(
                "scripts.project_metrics.collectors.scc_collector.subprocess.run",
                side_effect=_build_run_side_effect(_completed_version_process()),
            ),
        ):
            result = collector.resolve(env)

        assert isinstance(result, Available), (
            f"Expected Available; got {type(result).__name__} (result={result!r})"
        )

    def test_available_version_is_parsed_from_stdout(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import Available, ResolutionEnv
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        with (
            patch(
                "scripts.project_metrics.collectors.scc_collector.shutil.which",
                return_value="/usr/local/bin/scc",
            ),
            patch(
                "scripts.project_metrics.collectors.scc_collector.subprocess.run",
                side_effect=_build_run_side_effect(_completed_version_process()),
            ),
        ):
            result = collector.resolve(env)

        assert isinstance(result, Available)
        # Version parsing strips the "scc version " prefix (mirrors
        # GitCollector's _resolve_git_version). Tolerates either the raw
        # "3.7.0" or the raw stdout — the stable contract is that the
        # expected version substring is present.
        assert _EXPECTED_SCC_VERSION in result.version, (
            f"Version string must contain {_EXPECTED_SCC_VERSION!r}; "
            f"got {result.version!r}"
        )


# ---------------------------------------------------------------------------
# resolve() — Unavailable case: scc absent from PATH OR scc probe raises
# FileNotFoundError.
# ---------------------------------------------------------------------------


class TestSccResolveUnavailable:
    """scc is missing — resolve() must return Unavailable with an install hint."""

    def test_resolve_returns_unavailable_when_which_returns_none(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import (
            ResolutionEnv,
            Unavailable,
        )
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        # shutil.which returns None — scc not installed. subprocess.run is
        # still patched to fail loudly if the collector invokes it after the
        # which-check already signalled absence.
        with (
            patch(
                "scripts.project_metrics.collectors.scc_collector.shutil.which",
                return_value=None,
            ),
            patch(
                "scripts.project_metrics.collectors.scc_collector.subprocess.run",
                side_effect=AssertionError(
                    "subprocess.run should not be invoked when shutil.which returns None"
                ),
            ),
        ):
            result = collector.resolve(env)

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when scc is absent; got {type(result).__name__}"
        )

    def test_unavailable_carries_actionable_install_hint(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import (
            ResolutionEnv,
            Unavailable,
        )
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        with patch(
            "scripts.project_metrics.collectors.scc_collector.shutil.which",
            return_value=None,
        ):
            result = collector.resolve(env)

        assert isinstance(result, Unavailable)
        # Install hint must be a non-empty string referencing scc — so the
        # MD renderer's "Install to improve" section has something to show.
        assert result.install_hint, "install_hint must be non-empty"
        assert "scc" in result.install_hint.lower(), (
            f"install_hint should name scc explicitly; got {result.install_hint!r}"
        )
        # Reason must be a non-empty string describing what happened. The
        # exact wording is implementer's choice but must be informative.
        assert result.reason, "reason must be non-empty"

    def test_resolve_returns_unavailable_when_subprocess_raises_file_not_found(
        self, tmp_path: Path
    ) -> None:
        """Race-condition path: ``shutil.which`` reported a path, but the
        binary disappeared before ``subprocess.run`` executed. The collector
        must translate ``FileNotFoundError`` into ``Unavailable`` rather than
        letting the exception escape.
        """

        from scripts.project_metrics.collectors.base import (
            ResolutionEnv,
            Unavailable,
        )
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        with (
            patch(
                "scripts.project_metrics.collectors.scc_collector.shutil.which",
                return_value="/usr/local/bin/scc",
            ),
            patch(
                "scripts.project_metrics.collectors.scc_collector.subprocess.run",
                side_effect=_build_run_side_effect(
                    FileNotFoundError("scc binary vanished between which() and run()")
                ),
            ),
        ):
            result = collector.resolve(env)

        assert isinstance(result, Unavailable), (
            "FileNotFoundError during scc --version probe must map to Unavailable"
        )


# ---------------------------------------------------------------------------
# resolve() — Timeout case: ``scc --version`` hangs past the probe budget.
# ---------------------------------------------------------------------------


class TestSccResolveTimeout:
    """scc exists but times out during --version probe."""

    def test_resolve_returns_unavailable_when_version_probe_times_out(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import (
            ResolutionEnv,
            Unavailable,
        )
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        with (
            patch(
                "scripts.project_metrics.collectors.scc_collector.shutil.which",
                return_value="/usr/local/bin/scc",
            ),
            patch(
                "scripts.project_metrics.collectors.scc_collector.subprocess.run",
                side_effect=_build_run_side_effect(
                    subprocess.TimeoutExpired(cmd=["scc", "--version"], timeout=2.0)
                ),
            ),
        ):
            result = collector.resolve(env)

        assert isinstance(result, Unavailable), (
            "TimeoutExpired on scc --version must map to Unavailable, not raise"
        )

    def test_timeout_unavailable_reason_mentions_timeout(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import (
            ResolutionEnv,
            Unavailable,
        )
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        env = ResolutionEnv()

        with (
            patch(
                "scripts.project_metrics.collectors.scc_collector.shutil.which",
                return_value="/usr/local/bin/scc",
            ),
            patch(
                "scripts.project_metrics.collectors.scc_collector.subprocess.run",
                side_effect=_build_run_side_effect(
                    subprocess.TimeoutExpired(cmd=["scc", "--version"], timeout=2.0)
                ),
            ),
        ):
            result = collector.resolve(env)

        assert isinstance(result, Unavailable)
        # The reason should reference the timeout so the MD surface reads
        # "scc probe timed out" (or similar) rather than a generic
        # "not available" line. Tolerates phrasing variations by matching a
        # substring only.
        assert _SCC_PROBE_TIMEOUT_FRAGMENT in result.reason.lower(), (
            f"Unavailable.reason should mention 'timed out' when --version "
            f"times out; got {result.reason!r}"
        )


# ---------------------------------------------------------------------------
# collect() — success path: scc --format json emits the canned fixture, the
# collector parses it into the per-language / per-file breakdown the
# aggregate layer consumes.
# ---------------------------------------------------------------------------


class TestSccCollectSuccess:
    """scc collect() against the canned JSON fixture populates the namespace."""

    def test_collect_returns_collector_result_with_ok_status(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import (
            CollectionContext,
            CollectorResult,
        )
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        ctx = CollectionContext(
            repo_root=str(tmp_path),
            window_days=90,
            git_sha="0" * 40,
        )

        with patch(
            "scripts.project_metrics.collectors.scc_collector.subprocess.run",
            side_effect=_build_run_side_effect(
                _completed_version_process(),
                _completed_collect_process(SAMPLE_SCC_JSON),
            ),
        ):
            result = collector.collect(ctx)

        assert isinstance(result, CollectorResult)
        assert result.status == "ok", (
            f"collect() on a well-formed scc payload must return status='ok'; "
            f"got {result.status!r} with issues={result.issues}"
        )
        assert result.status in _COLLECTOR_RESULT_STATUSES

    def test_collect_populates_language_breakdown(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import CollectionContext
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        ctx = CollectionContext(
            repo_root=str(tmp_path),
            window_days=90,
            git_sha="0" * 40,
        )

        with patch(
            "scripts.project_metrics.collectors.scc_collector.subprocess.run",
            side_effect=_build_run_side_effect(
                _completed_version_process(),
                _completed_collect_process(SAMPLE_SCC_JSON),
            ),
        ):
            data = collector.collect(ctx).data

        breakdown = data.get("language_breakdown")
        assert breakdown is not None, (
            "data must carry a 'language_breakdown' key mapping language → "
            "rollup. See plan § S6a task description."
        )
        # Accept either shape: {lang: {"sloc": N, "file_count": M}} or
        # {lang: N_sloc}. The stable contract is that Python and Markdown
        # both appear and carry the SLOC totals from SAMPLE_SCC_JSON.
        assert "Python" in breakdown, (
            f"language_breakdown must name 'Python'; keys={sorted(breakdown)}"
        )
        assert "Markdown" in breakdown, (
            f"language_breakdown must name 'Markdown'; keys={sorted(breakdown)}"
        )

    def test_collect_populates_per_file_sloc(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import CollectionContext
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        ctx = CollectionContext(
            repo_root=str(tmp_path),
            window_days=90,
            git_sha="0" * 40,
        )

        with patch(
            "scripts.project_metrics.collectors.scc_collector.subprocess.run",
            side_effect=_build_run_side_effect(
                _completed_version_process(),
                _completed_collect_process(SAMPLE_SCC_JSON),
            ),
        ):
            data = collector.collect(ctx).data

        per_file = data.get("per_file_sloc")
        assert per_file is not None, (
            "data must carry a 'per_file_sloc' key mapping path → int"
        )
        # All 5 canned files must appear.
        assert "scripts/project_metrics/foo.py" in per_file
        assert "scripts/project_metrics/bar.py" in per_file
        assert "scripts/project_metrics/__init__.py" in per_file
        assert "docs/README.md" in per_file
        assert "docs/INSTALL.md" in per_file
        # The SLOC value for foo.py must be 180 (Code field in the fixture).
        assert per_file["scripts/project_metrics/foo.py"] == 180, (
            f"per_file_sloc['scripts/project_metrics/foo.py'] must be 180 "
            f"(Code field in canned SAMPLE_SCC_JSON); got "
            f"{per_file['scripts/project_metrics/foo.py']!r}"
        )

    def test_collect_aggregates_sloc_total_correctly(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import CollectionContext
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        ctx = CollectionContext(
            repo_root=str(tmp_path),
            window_days=90,
            git_sha="0" * 40,
        )

        with patch(
            "scripts.project_metrics.collectors.scc_collector.subprocess.run",
            side_effect=_build_run_side_effect(
                _completed_version_process(),
                _completed_collect_process(SAMPLE_SCC_JSON),
            ),
        ):
            data = collector.collect(ctx).data

        assert data.get("sloc_total") == _EXPECTED_SLOC_TOTAL, (
            f"sloc_total must equal sum of per-language Code totals "
            f"({_EXPECTED_SLOC_TOTAL} = 450 Python + 150 Markdown); "
            f"got {data.get('sloc_total')!r}"
        )

    def test_collect_reports_language_count(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import CollectionContext
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        ctx = CollectionContext(
            repo_root=str(tmp_path),
            window_days=90,
            git_sha="0" * 40,
        )

        with patch(
            "scripts.project_metrics.collectors.scc_collector.subprocess.run",
            side_effect=_build_run_side_effect(
                _completed_version_process(),
                _completed_collect_process(SAMPLE_SCC_JSON),
            ),
        ):
            data = collector.collect(ctx).data

        assert data.get("language_count") == _EXPECTED_LANGUAGE_COUNT, (
            f"language_count must be {_EXPECTED_LANGUAGE_COUNT} (Python + "
            f"Markdown); got {data.get('language_count')!r}"
        )

    def test_collect_reports_file_count(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import CollectionContext
        from scripts.project_metrics.collectors.scc_collector import SccCollector

        collector = SccCollector(repo_root=tmp_path)
        ctx = CollectionContext(
            repo_root=str(tmp_path),
            window_days=90,
            git_sha="0" * 40,
        )

        with patch(
            "scripts.project_metrics.collectors.scc_collector.subprocess.run",
            side_effect=_build_run_side_effect(
                _completed_version_process(),
                _completed_collect_process(SAMPLE_SCC_JSON),
            ),
        ):
            data = collector.collect(ctx).data

        assert data.get("file_count") == _EXPECTED_FILE_COUNT, (
            f"file_count must be {_EXPECTED_FILE_COUNT} (3 Python + 2 "
            f"Markdown); got {data.get('file_count')!r}"
        )


# ---------------------------------------------------------------------------
# Namespace skip-marker integration — when SccCollector is unavailable, the
# runner calls ``skip_marker_for_namespace("scc")`` to populate the namespace
# block. This test validates the helper's output shape rather than the
# collector's code directly (the marker lives in base.py, not scc_collector.py,
# but the shape is part of the contract the plan requires tested here).
# ---------------------------------------------------------------------------


class TestSccNamespaceSkipMarker:
    """When scc is unavailable, the runner emits the uniform 3-key skip block."""

    def test_skip_marker_shape_for_scc(self) -> None:
        from scripts.project_metrics.collectors.base import skip_marker_for_namespace

        marker = skip_marker_for_namespace(_EXPECTED_NAME)
        assert marker == _EXPECTED_SKIP_MARKER, (
            f"skip_marker_for_namespace('scc') must equal {_EXPECTED_SKIP_MARKER!r}; "
            f"got {marker!r}. Adding/removing keys breaks the uniform-rendering "
            f"invariant."
        )
