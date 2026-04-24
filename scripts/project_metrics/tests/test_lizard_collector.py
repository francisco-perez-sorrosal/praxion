"""Behavioral tests for the LizardCollector — cross-language CCN via ``uvx lizard``.

These tests encode the LizardCollector behavioral contract derived from the
collector-protocol and graceful-degradation ADRs under
``.ai-state/decisions/drafts/``. They are written *from the behavioral spec, not from
the implementation* — production code
(``scripts/project_metrics/collectors/lizard_collector.py``) is deliberately
not read while authoring these tests.

**Import strategy**: every test imports ``LizardCollector`` (and related
protocol symbols) inside the test body. During the BDD/TDD RED handshake the
production module does not yet exist, so top-of-module imports would break
pytest collection for every test in this file simultaneously. Deferred imports
give per-test RED/GREEN resolution and let individual tests surface their
specific ``ImportError`` / ``ModuleNotFoundError``.

**Mock strategy**: the collector shells out to ``uvx`` + ``lizard``; tests
mock ``subprocess.run`` and ``shutil.which`` at the production module's
namespace (``scripts.project_metrics.collectors.lizard_collector``) to
exercise the resolve/collect branches without requiring ``uvx`` on the test
machine. The "patch-where-used" approach avoids the lazy-import gotcha that
would affect patching at ``subprocess.run``'s source module.

**Percentile assertions use plausible bands, not exact equality**. The plan
does not pin a quantile formulation (R-7 linear vs. stdlib
``statistics.quantiles`` exclusive vs. numpy default), so tests assert
``min_plausible <= value <= max_plausible`` across the valid methods. This
lets the implementer pick any reasonable percentile definition without
churning tests; exact equality would tie the test to one implementation
detail that the ADRs intentionally leave open.

**Canned XML**: ``_SAMPLE_LIZARD_XML`` below is hand-shaped in the
CheckStyle-derived ``cppncss`` format lizard emits for ``--xml``. Three files
contribute 9 well-formed function records plus 1 intentionally-malformed
record (non-numeric CCN), so the partial-success path has a concrete failure
to surface in ``CollectorResult.issues``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Canned lizard XML — shape derived from the ``lizard --xml`` reference output
# (CheckStyle-adjacent ``cppncss`` root). The fixture is sized small enough
# that per-file rollups and the repo-wide p95 are hand-verifiable.
#
# Per-file CCN distribution:
#   src/core.py    → [5, 3, 7]               max=7,  count=3
#   src/helpers.py → [2, 4, 6, 8]            max=8,  count=4
#   src/util.py    → [1, 2]                  max=2,  count=2
# One extra record in src/util.py is intentionally malformed (non-numeric CCN)
# to exercise the partial-success path.
#
# Aggregate (all 9 well-formed functions, sorted):
#   [1, 2, 2, 3, 4, 5, 6, 7, 8]
#   Across R-7 linear, stdlib exclusive quantiles, and numpy default, p95
#   falls in the band [6.0, 8.0]. p75 falls in [5.0, 7.0]. max = 8, min = 1.
# ---------------------------------------------------------------------------

_SAMPLE_LIZARD_XML: str = """<?xml version="1.0" ?>
<cppncss>
  <measure type="Function">
    <labels>
      <label>Nr.</label>
      <label>NCSS</label>
      <label>CCN</label>
      <label>Functions</label>
    </labels>
    <item name="process_input(arg) at src/core.py:10">
      <value>1</value><value>20</value><value>5</value><value>1</value>
    </item>
    <item name="validate(arg) at src/core.py:42">
      <value>2</value><value>10</value><value>3</value><value>1</value>
    </item>
    <item name="dispatch(arg) at src/core.py:78">
      <value>3</value><value>30</value><value>7</value><value>1</value>
    </item>
    <item name="format_msg(arg) at src/helpers.py:5">
      <value>4</value><value>8</value><value>2</value><value>1</value>
    </item>
    <item name="parse_line(arg) at src/helpers.py:20">
      <value>5</value><value>15</value><value>4</value><value>1</value>
    </item>
    <item name="encode(arg) at src/helpers.py:45">
      <value>6</value><value>25</value><value>6</value><value>1</value>
    </item>
    <item name="decode(arg) at src/helpers.py:75">
      <value>7</value><value>35</value><value>8</value><value>1</value>
    </item>
    <item name="is_empty(arg) at src/util.py:3">
      <value>8</value><value>2</value><value>1</value><value>1</value>
    </item>
    <item name="join_path(arg) at src/util.py:12">
      <value>9</value><value>5</value><value>2</value><value>1</value>
    </item>
    <item name="broken(arg) at src/util.py:30">
      <value>10</value><value>4</value><value>NOT_A_NUMBER</value><value>1</value>
    </item>
  </measure>
</cppncss>
"""


# ---------------------------------------------------------------------------
# Plausible-band constants for percentile assertions. Computed across the
# three quantile methods in common use (R-7 linear, stdlib exclusive,
# numpy default). The bands are wide enough to admit any reasonable
# implementation choice but tight enough to catch wildly-wrong rollups.
# ---------------------------------------------------------------------------

# Sorted per-file CCN across the 9 well-formed functions:
# [1, 2, 2, 3, 4, 5, 6, 7, 8]
_AGGREGATE_CCN_P95_MIN: float = 6.0
_AGGREGATE_CCN_P95_MAX: float = 8.0
_AGGREGATE_CCN_P75_MIN: float = 5.0
_AGGREGATE_CCN_P75_MAX: float = 7.0

# Per-file max CCN (unambiguous across any percentile method).
_FILE_MAX_CCN: dict[str, int] = {
    "src/core.py": 7,
    "src/helpers.py": 8,
    "src/util.py": 2,  # only the two well-formed funcs count; malformed skipped
}

# Per-file function counts (unambiguous; excludes the malformed record).
_FILE_FUNCTION_COUNT: dict[str, int] = {
    "src/core.py": 3,
    "src/helpers.py": 4,
    "src/util.py": 2,
}

# Total well-formed function count across the fixture XML.
_TOTAL_FUNCTION_COUNT: int = 9


# ---------------------------------------------------------------------------
# Shared helpers.
# ---------------------------------------------------------------------------


def _make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess for mocked ``subprocess.run`` return values."""

    return subprocess.CompletedProcess(
        args=["uvx", "lizard"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _make_context(repo_root: Path) -> Any:
    """Build a CollectionContext from the protocol base module.

    Deferred import so the fixture doesn't break collection during the RED
    handshake. ``git_sha`` is a fixed placeholder — the lizard collector does
    not depend on SHA content, only on repo_root.
    """

    from scripts.project_metrics.collectors.base import CollectionContext

    return CollectionContext(
        repo_root=str(repo_root),
        window_days=90,
        git_sha="0" * 40,
    )


def _make_env() -> Any:
    """Build a default ResolutionEnv — tests that need path injection override."""

    from scripts.project_metrics.collectors.base import ResolutionEnv

    return ResolutionEnv()


# ---------------------------------------------------------------------------
# Static metadata — attributes every collector advertises to the runner.
# ---------------------------------------------------------------------------


class TestLizardCollectorStaticMetadata:
    """Class-level attributes that the runner and schema layer depend on."""

    def test_collector_name_is_lizard(self) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        # Name becomes the JSON namespace key. The aggregate pipeline reads
        # ``lizard.<...>`` to populate ``ccn_p95``; renaming silently breaks
        # the aggregate column wiring.
        assert LizardCollector.name == "lizard"

    def test_collector_is_not_required(self) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        # Only GitCollector is required=True per the collector-protocol ADR.
        # Lizard is a soft dependency; its absence must not fail the run.
        assert LizardCollector.required is False

    def test_collector_declares_multiple_languages(self) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        # Lizard supports ~17 languages. The exact set is not pinned by the
        # ADRs; the contract is only that it is a non-empty frozenset
        # (language-agnostic collectors use empty; lizard is not empty).
        assert isinstance(LizardCollector.languages, frozenset)
        assert len(LizardCollector.languages) >= 2, (
            "LizardCollector advertises broad language support; expected "
            "a frozenset with several language identifiers."
        )


# ---------------------------------------------------------------------------
# Resolve-phase tests — Available when ``uvx lizard --version`` succeeds.
# ---------------------------------------------------------------------------


class TestLizardResolveAvailable:
    """``resolve()`` returns Available when uvx is on PATH and lizard responds."""

    def test_resolve_returns_available_with_parsed_version(self) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()

        # Mock shutil.which to report uvx present; mock subprocess.run to
        # return the version string. Patch at the production module's
        # namespace to intercept the collector's own lookups.
        target = "scripts.project_metrics.collectors.lizard_collector"
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                return_value=_make_completed_process(stdout="1.22.0\n"),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Available), (
            f"Expected Available when uvx + lizard resolve; got {type(result).__name__}"
        )
        # Version should surface "1.22.0" somewhere — some implementations
        # strip leading text (e.g. "lizard 1.22.0"), others trust the pipe
        # verbatim. Use substring containment to stay robust.
        assert "1.22.0" in result.version


# ---------------------------------------------------------------------------
# Resolve-phase tests — Unavailable when uvx is absent.
# ---------------------------------------------------------------------------


class TestLizardResolveUnavailable:
    """``resolve()`` returns Unavailable when uvx is missing or lizard errors."""

    def test_resolve_returns_unavailable_when_uvx_missing(self) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(f"{target}.shutil.which", return_value=None):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when uvx is off PATH; got {type(result).__name__}"
        )
        # Reason should mention uvx (or an equivalent marker) so the
        # install-to-improve section can render an actionable message.
        assert "uvx" in result.reason.lower()
        # Install hint should point at installing uv (the uvx provider).
        assert "uv" in result.install_hint.lower()

    def test_resolve_returns_unavailable_when_lizard_version_call_fails(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        # uvx is present, but ``uvx lizard --version`` exits non-zero
        # (e.g., uvx cannot fetch the lizard package for any reason).
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    returncode=1, cmd=["uvx", "lizard", "--version"]
                ),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable)


# ---------------------------------------------------------------------------
# Resolve-phase tests — Unavailable on first-run timeout.
# ---------------------------------------------------------------------------


class TestLizardResolveTimeout:
    """The 120s first-run cache-fill deadline converts TimeoutExpired to Unavailable."""

    def test_resolve_returns_unavailable_when_version_probe_times_out(self) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["uvx", "lizard", "--version"], timeout=120
                ),
            ),
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
            or ("120" in result.reason)
        )

    def test_resolve_emits_first_run_hint_on_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                return_value=_make_completed_process(stdout="1.22.0\n"),
            ),
        ):
            collector.resolve(_make_env())

        # The plan says the collector emits a one-line "resolving Tier 1
        # tools (first-time cache fill, may take up to 2 minutes)" warning
        # on stderr *before* invoking uvx. Soft-match to stay robust across
        # wording choices: "first-run", "cache fill", or "first-time" should
        # all satisfy the contract.
        captured = capsys.readouterr().err.lower()
        assert any(
            phrase in captured
            for phrase in ("first-run", "first-time", "cache fill", "cache-fill")
        ), (
            "Expected a user-visible first-run hint on stderr during resolve(); "
            f"captured stderr was: {captured!r}"
        )


# ---------------------------------------------------------------------------
# Collect-phase tests — canonical happy path over canned XML.
# ---------------------------------------------------------------------------


class TestLizardCollectSuccess:
    """``collect()`` parses lizard XML into per-file CCN rollups."""

    def test_collect_returns_ok_status_on_well_formed_xml(self, tmp_path: Path) -> None:
        # Build XML that contains only the well-formed records (drop the
        # broken one for the pure happy-path assertion).
        xml_without_broken = _SAMPLE_LIZARD_XML.replace(
            '    <item name="broken(arg) at src/util.py:30">\n'
            "      <value>10</value><value>4</value>"
            "<value>NOT_A_NUMBER</value><value>1</value>\n"
            "    </item>\n",
            "",
        )

        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=xml_without_broken),
        ):
            result = collector.collect(_make_context(tmp_path))

        assert result.status == "ok", (
            f"Expected status='ok' on well-formed XML; got status={result.status!r}, "
            f"issues={result.issues!r}"
        )

    def test_collect_populates_per_file_rollups(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        # The namespace data should carry per-file rollups; the exact nesting
        # key for "per file" is not pinned by the ADR — the test accepts
        # either a top-level "files" dict or the per-file keys at root.
        data = result.data
        files_block = data.get("files") or {
            k: v for k, v in data.items() if isinstance(v, dict) and "max_ccn" in v
        }
        assert files_block, (
            f"Expected per-file rollup block in collector data; keys were "
            f"{list(data.keys())}"
        )

        # All three well-formed files must show up.
        for expected_file in _FILE_MAX_CCN:
            assert expected_file in files_block, (
                f"Expected per-file entry for {expected_file!r} in rollup; "
                f"got {list(files_block.keys())!r}"
            )

    def test_per_file_max_ccn_matches_canned_xml(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        data = result.data
        files_block = data.get("files") or {
            k: v for k, v in data.items() if isinstance(v, dict) and "max_ccn" in v
        }
        for file_path, expected_max in _FILE_MAX_CCN.items():
            file_entry = files_block[file_path]
            assert file_entry["max_ccn"] == expected_max, (
                f"File {file_path!r}: expected max_ccn={expected_max}, got "
                f"max_ccn={file_entry['max_ccn']!r}"
            )

    def test_per_file_function_count_matches_canned_xml(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        data = result.data
        files_block = data.get("files") or {
            k: v for k, v in data.items() if isinstance(v, dict) and "max_ccn" in v
        }
        for file_path, expected_count in _FILE_FUNCTION_COUNT.items():
            file_entry = files_block[file_path]
            assert file_entry["function_count"] == expected_count, (
                f"File {file_path!r}: expected function_count={expected_count}, "
                f"got function_count={file_entry['function_count']!r}"
            )


# ---------------------------------------------------------------------------
# Partial-success — malformed XML records do not abort the whole run.
# ---------------------------------------------------------------------------


class TestLizardCollectPartialOnMalformedXml:
    """A malformed ``<item>`` downgrades to partial without aborting the run."""

    def test_malformed_record_produces_partial_status(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        # The fixture XML contains one record with CCN="NOT_A_NUMBER". The
        # collector must skip it but continue, per the
        # graceful-degradation ADR's error-isolation clause.
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        assert result.status == "partial", (
            f"Expected status='partial' when malformed XML record is "
            f"present; got status={result.status!r}, issues={result.issues!r}"
        )

    def test_malformed_record_populates_issues_list(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        # A human-readable description of *what* was skipped must land in
        # issues so the MD renderer can surface it. The exact wording is not
        # pinned — the test only requires non-empty list with some reference
        # to the offending file or CCN value.
        assert result.issues, (
            "Expected issues list to be populated with a description of the "
            f"skipped malformed record; got issues={result.issues!r}"
        )
        joined = " ".join(result.issues).lower()
        assert "util.py" in joined or "ccn" in joined or "malform" in joined, (
            "Expected issues to mention the offending file or the malformed "
            f"CCN field; got issues={result.issues!r}"
        )

    def test_malformed_record_does_not_appear_in_rollup(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        # src/util.py has two well-formed functions (CCN=1, CCN=2) and one
        # malformed one. The rollup must reflect only the two, so
        # function_count == 2 and max_ccn == 2.
        data = result.data
        files_block = data.get("files") or {
            k: v for k, v in data.items() if isinstance(v, dict) and "max_ccn" in v
        }
        util_entry = files_block["src/util.py"]
        assert util_entry["function_count"] == 2, (
            "Malformed record must not be counted in function_count; "
            f"got {util_entry['function_count']!r}"
        )
        assert util_entry["max_ccn"] == 2, (
            "Malformed record's CCN value must not influence max_ccn; "
            f"got {util_entry['max_ccn']!r}"
        )


# ---------------------------------------------------------------------------
# Aggregate rollup — p95 across ALL functions (flat list, not per-file).
# ---------------------------------------------------------------------------


class TestLizardAggregateRollup:
    """Repo-wide p95 and the empty-repo null contract."""

    def test_aggregate_ccn_p95_falls_in_plausible_band(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML),
        ):
            result = collector.collect(_make_context(tmp_path))

        # Aggregate p95 sits in data somewhere — either at the data root or
        # in an "aggregate" sub-block. Accept either shape.
        aggregate = result.data.get("aggregate") or result.data
        ccn_p95 = aggregate.get("ccn_p95")
        assert ccn_p95 is not None, (
            f"Expected ccn_p95 populated for a non-empty fixture; got "
            f"None. Data keys: {list(result.data.keys())}"
        )
        assert _AGGREGATE_CCN_P95_MIN <= ccn_p95 <= _AGGREGATE_CCN_P95_MAX, (
            f"Aggregate ccn_p95 outside plausible quantile band: expected "
            f"[{_AGGREGATE_CCN_P95_MIN}, {_AGGREGATE_CCN_P95_MAX}], got "
            f"{ccn_p95!r}. Sorted CCN values in fixture: "
            f"[1, 2, 2, 3, 4, 5, 6, 7, 8]."
        )

    def test_aggregate_ccn_p95_is_null_for_empty_repo(self, tmp_path: Path) -> None:
        """When lizard finds no functions, p95 is null (not 0).

        A zero would be indistinguishable from "the repo has only CCN=0
        one-liners"; null unambiguously says "no signal to compute on".
        """

        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        # Minimal well-formed XML with zero item elements — lizard emits
        # exactly this shape on a repo with no analyzable sources.
        empty_xml = (
            '<?xml version="1.0" ?>\n'
            "<cppncss>\n"
            '  <measure type="Function">\n'
            "    <labels>\n"
            "      <label>Nr.</label><label>NCSS</label>"
            "<label>CCN</label><label>Functions</label>\n"
            "    </labels>\n"
            "  </measure>\n"
            "</cppncss>\n"
        )
        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            return_value=_make_completed_process(stdout=empty_xml),
        ):
            result = collector.collect(_make_context(tmp_path))

        aggregate = result.data.get("aggregate") or result.data
        ccn_p95 = aggregate.get("ccn_p95")
        assert ccn_p95 is None, (
            f"Expected ccn_p95 is None for empty repo (no functions); got "
            f"{ccn_p95!r}. The null semantics ADR mandates null, not 0, when "
            f"there is no signal to compute on."
        )


# ---------------------------------------------------------------------------
# Skip-marker shape — delegates to the shared helper.
# ---------------------------------------------------------------------------


class TestLizardSkipMarker:
    """When lizard is Unavailable, the namespace contributes the uniform skip marker."""

    def test_skip_marker_for_lizard_has_uniform_three_key_shape(self) -> None:
        from scripts.project_metrics.collectors.base import (
            skip_marker_for_namespace,
        )

        marker = skip_marker_for_namespace("lizard")

        # Three-key shape pinned by the graceful-degradation ADR: the MD
        # renderer consumes this exact shape across every collector's
        # namespace when it's unavailable.
        assert marker == {
            "status": "skipped",
            "reason": "tool_unavailable",
            "tool": "lizard",
        }


# ---------------------------------------------------------------------------
# Subprocess timeout handling during the collect phase — the run-wide 120s
# budget and a downgrade path rather than an uncaught raise.
# ---------------------------------------------------------------------------


class TestLizardCollectTimeout:
    """A TimeoutExpired during collect() downgrades cleanly, never raises uncaught."""

    def test_collect_downgrades_on_timeout_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.lizard_collector import (
            LizardCollector,
        )

        collector = LizardCollector()
        target = "scripts.project_metrics.collectors.lizard_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["uvx", "lizard", "--xml"], timeout=120
            ),
        ):
            # Per the collector-protocol ADR: collect() must downgrade
            # analysis-level errors to status='error'/'timeout' rather than
            # propagating. The runner's try/except is a safety net, not the
            # primary error path.
            result = collector.collect(_make_context(tmp_path))

        assert result.status in ("timeout", "error"), (
            f"Expected graceful downgrade to status='timeout' or 'error' on "
            f"subprocess timeout; got status={result.status!r}"
        )


# ---------------------------------------------------------------------------
# Guard against silent dependency drift.
# ---------------------------------------------------------------------------


def test_subprocess_run_is_called_with_xml_flag(tmp_path: Path) -> None:
    """The collector must pass ``--xml`` so the parser sees the expected format.

    This is a defensive test: the XML parser is tuned to the ``cppncss``
    shape lizard emits under ``--xml``. A silent switch to ``--csv`` or the
    default output would yield a zero-record parse, which could silently
    look like "an empty repo" instead of a parser mismatch.
    """

    from scripts.project_metrics.collectors.lizard_collector import LizardCollector

    collector = LizardCollector()
    target = "scripts.project_metrics.collectors.lizard_collector"
    mock_run = MagicMock(
        return_value=_make_completed_process(stdout=_SAMPLE_LIZARD_XML)
    )
    with patch(f"{target}.subprocess.run", mock_run):
        collector.collect(_make_context(tmp_path))

    # At least one of the subprocess.run invocations must contain --xml in
    # its argv. Accept either positional (args[0]) or kwarg (args=) forms.
    found_xml_flag = False
    for call in mock_run.call_args_list:
        argv_candidate = call.args[0] if call.args else call.kwargs.get("args", [])
        if isinstance(argv_candidate, (list, tuple)) and "--xml" in argv_candidate:
            found_xml_flag = True
            break
    assert found_xml_flag, (
        "Expected collect() to invoke lizard with --xml; none of the observed "
        f"subprocess.run calls carried that flag. Calls: "
        f"{mock_run.call_args_list!r}"
    )
