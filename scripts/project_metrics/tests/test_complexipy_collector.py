"""Behavioral tests for the ComplexipyCollector — Python cognitive complexity via ``uvx complexipy``.

These tests encode the ComplexipyCollector behavioral contract derived from the
collector-protocol and graceful-degradation ADRs under
``.ai-state/decisions/drafts/``. They are written *from the behavioral spec, not
from the implementation* — production code
(``scripts/project_metrics/collectors/complexipy_collector.py``) is deliberately
not read while authoring these tests.

**The distinguishing contract for this collector**: it is the first
language-specific collector that fully exercises the ``NotApplicable``
resolution outcome. Lizard and scc are language-agnostic; complexipy only
handles Python. A repository with zero ``.py`` files must produce
``NotApplicable``, not ``Unavailable`` — the distinction matters because
the MD renderer surfaces them differently:

* ``Unavailable`` → renders an actionable install hint in the
  "Install to improve" section.
* ``NotApplicable`` → silently omits the tool from the report; no install
  hint, because there is nothing the user can do.

**Import strategy**: every test imports ``ComplexipyCollector`` (and related
protocol symbols) inside the test body. During the BDD/TDD RED handshake the
production module does not yet exist, so top-of-module imports would break
pytest collection for every test in this file simultaneously. Deferred imports
give per-test RED/GREEN resolution.

**Mock strategy**: the collector shells out to ``uvx`` + ``complexipy`` and
also queries ``git ls-files`` to detect ``.py`` presence. Tests mock
``subprocess.run`` and ``shutil.which`` at the production module's namespace
(``scripts.project_metrics.collectors.complexipy_collector``). This
"patch-where-used" approach avoids the lazy-import gotcha that would affect
patching at ``subprocess.run``'s source module. When a test needs to route
different ``subprocess.run`` invocations to different canned outputs (e.g.,
one call for ``git ls-files``, a second for ``uvx complexipy --version``),
``side_effect`` is a callable that inspects the argv and returns an
appropriate ``CompletedProcess``.

**Percentile assertions use plausible bands, not exact equality**. The plan
does not pin a quantile formulation, so tests assert
``min_plausible <= value <= max_plausible`` across the valid methods
(R-7 linear, stdlib ``statistics.quantiles`` exclusive/inclusive, numpy
default). This lets the implementer pick any reasonable percentile definition
without churning tests; exact equality would tie the test to one implementation
detail the ADRs intentionally leave open.

**Canned JSON**: ``_SAMPLE_COMPLEXIPY_JSON`` below is a flat list of
per-function records (the shape ``complexipy --output-json`` emits). Three
files contribute 9 functions with distinct cognitive complexity scores,
sized small enough that per-file rollups and the repo-wide p95 are
hand-verifiable.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Canned complexipy JSON — shape: flat list of per-function records. Complexipy
# emits one record per analyzed function; the collector rolls these up per
# file and computes an aggregate p95 across the full flat list.
#
# Per-file cognitive distribution:
#   src/app.py     → [5, 3, 7]        max=7,  count=3
#   src/helpers.py → [2, 4, 6, 8]     max=8,  count=4
#   src/util.py    → [1, 2]           max=2,  count=2
#
# Sorted flat list across all 9 functions:
#   [1, 2, 2, 3, 4, 5, 6, 7, 8]
#
# Across R-7 linear, stdlib inclusive quantiles, and numpy default, p95
# falls in the band [6.0, 8.0]. p75 falls in [5.0, 7.0]. max = 8, min = 1.
# ---------------------------------------------------------------------------

_SAMPLE_COMPLEXIPY_RECORDS: list[dict[str, Any]] = [
    {
        "file": "src/app.py",
        "function_name": "handle_request",
        "cognitive_complexity": 5,
        "line_start": 12,
    },
    {
        "file": "src/app.py",
        "function_name": "validate_payload",
        "cognitive_complexity": 3,
        "line_start": 40,
    },
    {
        "file": "src/app.py",
        "function_name": "dispatch",
        "cognitive_complexity": 7,
        "line_start": 72,
    },
    {
        "file": "src/helpers.py",
        "function_name": "format_timestamp",
        "cognitive_complexity": 2,
        "line_start": 8,
    },
    {
        "file": "src/helpers.py",
        "function_name": "parse_line",
        "cognitive_complexity": 4,
        "line_start": 25,
    },
    {
        "file": "src/helpers.py",
        "function_name": "encode_chunk",
        "cognitive_complexity": 6,
        "line_start": 55,
    },
    {
        "file": "src/helpers.py",
        "function_name": "decode_chunk",
        "cognitive_complexity": 8,
        "line_start": 90,
    },
    {
        "file": "src/util.py",
        "function_name": "is_empty",
        "cognitive_complexity": 1,
        "line_start": 5,
    },
    {
        "file": "src/util.py",
        "function_name": "join_path",
        "cognitive_complexity": 2,
        "line_start": 18,
    },
]

_SAMPLE_COMPLEXIPY_JSON: str = json.dumps(_SAMPLE_COMPLEXIPY_RECORDS)


# ---------------------------------------------------------------------------
# Plausible-band constants for percentile assertions. Computed across the
# three quantile methods in common use (R-7 linear, stdlib inclusive, numpy
# default). The bands are wide enough to admit any reasonable implementation
# choice but tight enough to catch wildly-wrong rollups.
# ---------------------------------------------------------------------------

# Sorted cognitive scores across the 9 functions:
# [1, 2, 2, 3, 4, 5, 6, 7, 8]
_AGGREGATE_P95_MIN: float = 6.0
_AGGREGATE_P95_MAX: float = 8.0
_AGGREGATE_P75_MIN: float = 5.0
_AGGREGATE_P75_MAX: float = 7.0

# Per-file max cognitive (unambiguous across any percentile method).
_FILE_MAX_COGNITIVE: dict[str, int] = {
    "src/app.py": 7,
    "src/helpers.py": 8,
    "src/util.py": 2,
}

# Per-file function counts (unambiguous).
_FILE_FUNCTION_COUNT: dict[str, int] = {
    "src/app.py": 3,
    "src/helpers.py": 4,
    "src/util.py": 2,
}

_TOTAL_FUNCTION_COUNT: int = 9


# ---------------------------------------------------------------------------
# Shared helpers.
# ---------------------------------------------------------------------------


def _make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess for mocked ``subprocess.run`` return values."""

    return subprocess.CompletedProcess(
        args=args or ["uvx", "complexipy"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _git_ls_files_with_python() -> subprocess.CompletedProcess[str]:
    """Canned ``git ls-files`` stdout listing mixed Python + non-Python files."""

    return _make_completed_process(
        stdout=(
            "README.md\nsrc/app.py\nsrc/helpers.py\nsrc/util.py\ntests/test_app.py\n"
        ),
        args=["git", "ls-files"],
    )


def _git_ls_files_without_python() -> subprocess.CompletedProcess[str]:
    """Canned ``git ls-files`` stdout listing zero ``.py`` entries."""

    return _make_completed_process(
        stdout=("README.md\nmain.go\nsrc/handler.go\nsrc/model.go\nMakefile\n"),
        args=["git", "ls-files"],
    )


def _route_by_argv(
    argv_to_result: dict[str, subprocess.CompletedProcess[str]],
) -> Any:
    """Build a ``side_effect`` that routes mocked ``subprocess.run`` calls by argv.

    The complexipy collector is expected to perform two distinct subprocess
    invocations during ``resolve()``:

    1. ``git ls-files`` — to detect whether any ``.py`` files exist.
    2. ``uvx complexipy --version`` — to confirm the tool is reachable.

    The router inspects the first argv token of the call and returns the
    configured CompletedProcess. If no key matches, a generic success is
    returned so tests that don't care about a specific branch still pass.
    Unknown argv also raises a clear error message rather than silently
    returning wrong data.
    """

    def _side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv_candidate = args[0] if args else kwargs.get("args") or []
        if not isinstance(argv_candidate, (list, tuple)):
            argv_candidate = []
        for key, result in argv_to_result.items():
            if any(key == tok for tok in argv_candidate):
                return result
        raise AssertionError(
            "Unexpected subprocess.run argv during complexipy test: "
            f"{argv_candidate!r}. Test expected to match one of "
            f"{list(argv_to_result.keys())!r}."
        )

    return _side_effect


def _make_context(repo_root: Path) -> Any:
    """Build a CollectionContext from the protocol base module.

    Deferred import so the fixture doesn't break collection during the RED
    handshake. ``git_sha`` is a fixed placeholder.
    """

    from scripts.project_metrics.collectors.base import CollectionContext

    return CollectionContext(
        repo_root=str(repo_root),
        window_days=90,
        git_sha="0" * 40,
    )


def _make_env() -> Any:
    """Build a default ResolutionEnv for resolve()."""

    from scripts.project_metrics.collectors.base import ResolutionEnv

    return ResolutionEnv()


# ---------------------------------------------------------------------------
# Static metadata — attributes every collector advertises to the runner.
# ---------------------------------------------------------------------------


class TestComplexipyStaticMetadata:
    """Class-level attributes that the runner and schema layer depend on."""

    def test_collector_name_is_complexipy(self) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        # Name becomes the JSON namespace key. The aggregate pipeline reads
        # ``complexipy.<...>`` to populate ``cognitive_p95``; renaming
        # silently breaks the aggregate column wiring.
        assert ComplexipyCollector.name == "complexipy"

    def test_collector_is_not_required(self) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        # Only GitCollector is required=True per the collector-protocol ADR.
        # Complexipy is a soft dependency; its absence must not fail the run.
        assert ComplexipyCollector.required is False

    def test_collector_declares_python_language(self) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        # Complexipy is Python-only. The languages frozenset must explicitly
        # carry "python" so the runner can decide applicability. Asserting
        # set-membership rather than equality leaves room for the implementer
        # to add other Python-adjacent language identifiers (e.g., "python3")
        # without breaking the test — but the contract is that "python" is
        # present.
        assert isinstance(ComplexipyCollector.languages, frozenset)
        assert "python" in ComplexipyCollector.languages, (
            "ComplexipyCollector must declare 'python' in its languages "
            f"frozenset; got {ComplexipyCollector.languages!r}"
        )


# ---------------------------------------------------------------------------
# Resolve-phase tests — Available when uvx is on PATH, complexipy responds,
# and the repository contains at least one .py file.
# ---------------------------------------------------------------------------


class TestComplexipyResolveAvailable:
    """``resolve()`` returns Available when uvx, complexipy, and .py files all present."""

    def test_resolve_returns_available_with_parsed_version(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        # Three-branch route: git ls-files returns .py files, uvx is on PATH,
        # `uvx complexipy --version` returns "4.1.0".
        side_effect = _route_by_argv(
            {
                "git": _git_ls_files_with_python(),
                "uvx": _make_completed_process(stdout="complexipy 4.1.0\n"),
            }
        )
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(f"{target}.subprocess.run", side_effect=side_effect),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Available), (
            f"Expected Available when uvx + complexipy + .py files all resolve; "
            f"got {type(result).__name__}"
        )
        # Version should surface "4.1.0" somewhere — some implementations
        # strip leading text (e.g. "complexipy 4.1.0"), others trust the
        # pipe verbatim. Use substring containment to stay robust.
        assert "4.1.0" in result.version


# ---------------------------------------------------------------------------
# Resolve-phase tests — Unavailable when uvx is absent (or version probe fails).
# ---------------------------------------------------------------------------


class TestComplexipyResolveUnavailable:
    """``resolve()`` returns Unavailable when uvx is missing or version call fails."""

    def test_resolve_returns_unavailable_when_uvx_missing(self) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        # shutil.which returns None (uvx off PATH). Implementers may still
        # probe git ls-files first; patch subprocess.run generically so
        # either ordering works.
        with (
            patch(f"{target}.shutil.which", return_value=None),
            patch(
                f"{target}.subprocess.run",
                return_value=_git_ls_files_with_python(),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when uvx is off PATH; got {type(result).__name__}"
        )
        # Reason should mention uvx (or an equivalent marker) so the
        # install-to-improve section can render an actionable message.
        assert "uvx" in result.reason.lower()
        # Install hint should point at installing uv (the uvx provider).
        assert "uv" in result.install_hint.lower()

    def test_resolve_returns_unavailable_when_version_call_fails(self) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        # uvx present, .py files present, but `uvx complexipy --version`
        # exits non-zero (e.g., uvx cannot fetch complexipy).
        def _side_effect(*args: Any, **kwargs: Any) -> Any:
            argv = args[0] if args else kwargs.get("args") or []
            if isinstance(argv, (list, tuple)) and argv and argv[0] == "git":
                return _git_ls_files_with_python()
            raise subprocess.CalledProcessError(
                returncode=1, cmd=["uvx", "complexipy", "--version"]
            )

        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(f"{target}.subprocess.run", side_effect=_side_effect),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when version probe fails; got "
            f"{type(result).__name__}"
        )


# ---------------------------------------------------------------------------
# Resolve-phase tests — NotApplicable when repo has no .py files. This is the
# distinguishing case for the complexipy collector: different from
# Unavailable because the user cannot fix it by installing anything.
# ---------------------------------------------------------------------------


class TestComplexipyResolveNotApplicable:
    """``resolve()`` returns NotApplicable when the repository has zero .py files."""

    def test_resolve_returns_not_applicable_when_repo_has_no_python_files(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.base import NotApplicable
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        # git ls-files returns a list of files with no .py entries. uvx is
        # present on PATH — so the outcome must not be Unavailable.
        side_effect = _route_by_argv(
            {
                "git": _git_ls_files_without_python(),
                "uvx": _make_completed_process(stdout="complexipy 4.1.0\n"),
            }
        )
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(f"{target}.subprocess.run", side_effect=side_effect),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, NotApplicable), (
            f"Expected NotApplicable when the repo has zero .py files; got "
            f"{type(result).__name__}. Distinction matters: Unavailable "
            f"would imply the user can fix it by installing something, but "
            f"a Go-only repo cannot benefit from a Python complexity tool."
        )

    def test_not_applicable_reason_mentions_python_or_no_files(self) -> None:
        from scripts.project_metrics.collectors.base import NotApplicable
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        side_effect = _route_by_argv(
            {
                "git": _git_ls_files_without_python(),
                "uvx": _make_completed_process(stdout="complexipy 4.1.0\n"),
            }
        )
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(f"{target}.subprocess.run", side_effect=side_effect),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, NotApplicable)
        # Reason should indicate Python-absence so logs/debugging are clear.
        # Soft match across plausible phrasings: "python", "no .py",
        # "no python", "source files".
        lowered = result.reason.lower()
        assert any(phrase in lowered for phrase in ("python", ".py", "source")), (
            "Expected NotApplicable.reason to mention Python source absence; "
            f"got reason={result.reason!r}"
        )

    def test_not_applicable_outcome_is_not_unavailable(self) -> None:
        """NotApplicable must not leak into the Unavailable branch.

        The tagged union uses ``isinstance`` discrimination. A naive
        implementation that returns ``Unavailable(reason="no .py files")``
        would mask the distinction and cause the MD renderer to emit a
        bogus install hint on a Go-only project. This test guards that
        failure mode explicitly.
        """

        from scripts.project_metrics.collectors.base import (
            NotApplicable,
            Unavailable,
        )
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        side_effect = _route_by_argv(
            {
                "git": _git_ls_files_without_python(),
                "uvx": _make_completed_process(stdout="complexipy 4.1.0\n"),
            }
        )
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(f"{target}.subprocess.run", side_effect=side_effect),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, NotApplicable)
        assert not isinstance(result, Unavailable), (
            "NotApplicable must be a distinct ResolutionResult variant from "
            "Unavailable. Returning an Unavailable subclass here would cause "
            "the MD renderer to surface an install hint for a repo where "
            "the tool fundamentally cannot apply."
        )


# ---------------------------------------------------------------------------
# Resolve-phase tests — Unavailable on first-run timeout for the version probe.
# ---------------------------------------------------------------------------


class TestComplexipyResolveTimeout:
    """The first-run cache-fill deadline converts TimeoutExpired to Unavailable."""

    def test_resolve_returns_unavailable_when_version_probe_times_out(self) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"

        # git ls-files succeeds (so we reach the uvx branch), but
        # `uvx complexipy --version` times out during first-run cache fill.
        def _side_effect(*args: Any, **kwargs: Any) -> Any:
            argv = args[0] if args else kwargs.get("args") or []
            if isinstance(argv, (list, tuple)) and argv and argv[0] == "git":
                return _git_ls_files_with_python()
            raise subprocess.TimeoutExpired(
                cmd=["uvx", "complexipy", "--version"], timeout=120
            )

        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(f"{target}.subprocess.run", side_effect=_side_effect),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when first-run cache fill times out; got "
            f"{type(result).__name__}"
        )
        # Reason should hint at the timeout condition so the MD renderer can
        # disambiguate "not installed" vs "timed out during first-run fetch".
        combined_reason = result.reason.lower()
        assert (
            "timeout" in combined_reason
            or "timed out" in combined_reason
            or "120" in result.reason
        ), (
            "Expected Unavailable.reason to mention timeout / timed out / "
            f"120 seconds; got reason={result.reason!r}"
        )


# ---------------------------------------------------------------------------
# Collect-phase tests — canonical happy path over canned JSON.
# ---------------------------------------------------------------------------


class TestComplexipyCollectSuccess:
    """``collect()`` parses complexipy JSON into per-file cognitive rollups."""

    def test_collect_returns_ok_status_on_well_formed_json(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        assert result.status == "ok", (
            f"Expected status='ok' on well-formed complexipy JSON; got "
            f"status={result.status!r}, issues={result.issues!r}"
        )

    def test_collect_populates_per_file_rollups(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        # The namespace data should carry per-file rollups; accept either
        # a top-level "files" dict or the per-file keys at root (the ADR
        # does not pin the exact nesting key).
        data = result.data
        files_block = data.get("files") or {
            k: v
            for k, v in data.items()
            if isinstance(v, dict) and "max_cognitive" in v
        }
        assert files_block, (
            f"Expected per-file rollup block in collector data; keys were "
            f"{list(data.keys())}"
        )

        # All three well-formed files must show up.
        for expected_file in _FILE_MAX_COGNITIVE:
            assert expected_file in files_block, (
                f"Expected per-file entry for {expected_file!r}; got "
                f"{list(files_block.keys())!r}"
            )

    def test_per_file_max_cognitive_matches_canned_json(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        data = result.data
        files_block = data.get("files") or {
            k: v
            for k, v in data.items()
            if isinstance(v, dict) and "max_cognitive" in v
        }
        for file_path, expected_max in _FILE_MAX_COGNITIVE.items():
            file_entry = files_block[file_path]
            assert file_entry["max_cognitive"] == expected_max, (
                f"File {file_path!r}: expected max_cognitive={expected_max}, "
                f"got max_cognitive={file_entry['max_cognitive']!r}"
            )

    def test_per_file_function_count_matches_canned_json(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        data = result.data
        files_block = data.get("files") or {
            k: v
            for k, v in data.items()
            if isinstance(v, dict) and "max_cognitive" in v
        }
        for file_path, expected_count in _FILE_FUNCTION_COUNT.items():
            file_entry = files_block[file_path]
            assert file_entry["function_count"] == expected_count, (
                f"File {file_path!r}: expected function_count={expected_count}, "
                f"got function_count={file_entry['function_count']!r}"
            )

    def test_per_file_cognitive_scores_list_matches_canned_json(
        self, tmp_path: Path
    ) -> None:
        """Per-file ``cognitive_scores`` is a flat list of all the function scores.

        The aggregate p95 rollup is computed across *all* functions, not
        across per-file summaries, so the per-file record must preserve
        the raw scores (not just a summary). A sorted comparison is used
        because the emission order is not pinned.
        """

        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        data = result.data
        files_block = data.get("files") or {
            k: v
            for k, v in data.items()
            if isinstance(v, dict) and "max_cognitive" in v
        }
        expected_scores: dict[str, list[int]] = {
            "src/app.py": [3, 5, 7],
            "src/helpers.py": [2, 4, 6, 8],
            "src/util.py": [1, 2],
        }
        for file_path, expected_sorted in expected_scores.items():
            file_entry = files_block[file_path]
            actual_scores = sorted(file_entry["cognitive_scores"])
            assert actual_scores == expected_sorted, (
                f"File {file_path!r}: expected sorted cognitive_scores="
                f"{expected_sorted}, got {actual_scores!r}"
            )


# ---------------------------------------------------------------------------
# Aggregate rollup — p95 across ALL functions (flat list, not per-file).
# ---------------------------------------------------------------------------


class TestComplexipyAggregateRollup:
    """Repo-wide p95 and the empty-repo null contract."""

    def test_aggregate_cognitive_p95_falls_in_plausible_band(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        # Aggregate sits in data somewhere — either at the root or in an
        # "aggregate" sub-block. Accept either shape.
        aggregate = result.data.get("aggregate") or result.data
        cognitive_p95 = aggregate.get("cognitive_p95")
        assert cognitive_p95 is not None, (
            f"Expected cognitive_p95 populated for non-empty fixture; got "
            f"None. Data keys: {list(result.data.keys())}"
        )
        assert _AGGREGATE_P95_MIN <= cognitive_p95 <= _AGGREGATE_P95_MAX, (
            f"Aggregate cognitive_p95 outside plausible quantile band: "
            f"expected [{_AGGREGATE_P95_MIN}, {_AGGREGATE_P95_MAX}], got "
            f"{cognitive_p95!r}. Sorted cognitive scores in fixture: "
            f"[1, 2, 2, 3, 4, 5, 6, 7, 8]."
        )

    def test_aggregate_total_function_count_matches_fixture(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_COMPLEXIPY_JSON),
        ):
            result = collector.collect(_make_context(tmp_path))

        aggregate = result.data.get("aggregate") or result.data
        total = aggregate.get("total_function_count")
        assert total == _TOTAL_FUNCTION_COUNT, (
            f"Expected total_function_count={_TOTAL_FUNCTION_COUNT} across "
            f"3 files × [3, 4, 2] functions; got {total!r}"
        )

    def test_aggregate_cognitive_p95_is_null_for_empty_project(
        self, tmp_path: Path
    ) -> None:
        """When complexipy finds no functions, cognitive_p95 is null (not 0).

        A zero would be indistinguishable from "every function has cognitive
        complexity 0"; null unambiguously says "no signal to compute on."
        This matches the lizard collector's analogous contract.
        """

        from scripts.project_metrics.collectors.complexipy_collector import (
            ComplexipyCollector,
        )

        # Complexipy emits an empty JSON array when no functions are found
        # (e.g., a repo with .py files that contain only module-level code).
        empty_json = "[]"
        collector = ComplexipyCollector()
        target = "scripts.project_metrics.collectors.complexipy_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=empty_json),
        ):
            result = collector.collect(_make_context(tmp_path))

        aggregate = result.data.get("aggregate") or result.data
        cognitive_p95 = aggregate.get("cognitive_p95")
        assert cognitive_p95 is None, (
            f"Expected cognitive_p95 is None for empty-function project; "
            f"got {cognitive_p95!r}. Null semantics: 0 would collide with "
            f"'every function is trivial'; None unambiguously means 'no "
            f"signal to compute on'."
        )

        total = aggregate.get("total_function_count")
        assert total == 0, (
            f"Expected total_function_count=0 on empty-function project; got {total!r}"
        )


# ---------------------------------------------------------------------------
# Skip-marker shape — delegates to the shared helper.
# ---------------------------------------------------------------------------


class TestComplexipySkipMarker:
    """When complexipy is Unavailable OR NotApplicable, the namespace skip marker is uniform."""

    def test_skip_marker_for_complexipy_has_uniform_three_key_shape(self) -> None:
        from scripts.project_metrics.collectors.base import (
            skip_marker_for_namespace,
        )

        marker = skip_marker_for_namespace("complexipy")

        # Three-key shape pinned by the graceful-degradation ADR: the MD
        # renderer consumes this exact shape across every collector's
        # namespace when it's unavailable or not applicable. Same helper
        # serves both outcomes — the distinction lives in
        # tool_availability, not in the namespace block.
        assert marker == {
            "status": "skipped",
            "reason": "tool_unavailable",
            "tool": "complexipy",
        }
