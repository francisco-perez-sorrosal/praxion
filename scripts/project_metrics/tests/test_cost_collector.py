"""Behavioral tests for the cost collector's read pass.

These tests encode the read-pass behavioral contract derived from the
pipeline's behavioral specification (source discovery,
provenance classification, dedup) -- written from the behavioral spec, not
from the implementation. Production code
(``scripts/project_metrics/collectors/cost_collector.py``) does not exist yet
and is not read while authoring these tests.

**Import strategy**: every test imports from ``cost_collector`` inside the
test body (the "RED/GREEN deferred-import convention" this test suite
inherits from ``test_git_collector.py``), so pytest collection succeeds while
the module is absent and each test surfaces its own
``ImportError``/``ModuleNotFoundError`` individually.

**Interface pinned by this test file** (no production code existed to read,
so these names are this file's own contract; the rationale behind each
pinned name was recorded in the pipeline's learnings):

- ``Provenance`` -- a four-member enum (``ATTRIBUTED``, ``PARENT_SOURCED``,
  ``PRE_ATTRIBUTION``, ``UNPARSED``) with hyphenated string values matching
  the spec's variant names.
- ``_classify(row: dict) -> Provenance``
- ``AttributedRow`` -- frozen dataclass, fields in this exact order:
  ``agent_id, session_id, pipeline_slug, agent_type, agent_type_source,
  model, tokens_in, tokens_out, cache_read, cache_create, duration_ms,
  timestamp, source_path``.
- ``_attributed_from_row(row: dict, source_path: str) -> AttributedRow | None``
- ``SourceRef`` -- frozen dataclass:
  ``path, kind, checkout, mtime_iso, lines_scanned, agent_stop_rows,
  attributed_rows``.
- ``_resolve_main_checkout(repo_root: str) -> tuple[str | None, str | None]``
  -- the injectable module-level seam wrapping ``git rev-parse``; tests
  monkeypatch this rather than shelling out, mirroring
  ``git_collector.py``'s ``shutil.which`` monkeypatch convention.
- ``discover_sources(repo_root: str) -> tuple[list[SourceRef], list[str]]``
- ``read_agent_stop_rows(path: str) -> tuple[list[dict], str | None]``
- ``dedup_attributed_rows(rows) -> tuple[list[AttributedRow], list[str]]``

**Interface pinned by the aggregate-pass extension** (tier join, bucket
aggregation, coverage guard, F12 cell; the rationale behind each name was
recorded in the pipeline's learnings):

- ``TierResolved`` / ``TierAmbiguous`` / ``TierUnknown`` -- frozen dataclasses,
  the three-variant tier-join result (``TierResolved(tier, rows)``,
  ``TierAmbiguous(tiers, rows)``, ``TierUnknown(reason)``).
- ``parse_calibration_log(path: str) -> dict[str, list[str]]`` -- slug (the
  Task cell's first whitespace-delimited token) to an ordered list of
  normalized ``Actual Tier`` tokens (the cell's leading alphabetic run), one
  per calibration-log row for that slug.
- ``resolve_tier(slug: str, tier_index: dict[str, list[str]]) -> TierResolved | TierAmbiguous | TierUnknown``
- ``PipelineBucket`` -- frozen dataclass: ``pipeline_slug, tier, tier_reason,
  attributed_rows, sessions, models, tokens, by_agent_type``.
- ``build_pipeline_buckets(rows, tier_index) -> list[PipelineBucket]`` -- the
  ONE fold every per-pipeline/per-tier/per-agent-type table projects from.
- ``unresolved_agent_type_share(rows) -> dict`` -- ``{"unresolved_rows",
  "attributed_rows", "share"}`` over a sequence of ``AttributedRow``.
- ``Coverage`` -- frozen dataclass: ``attributed_rows, total_agent_stop_rows,
  quarantine, duplicate_agent_ids, sessions_durable, sessions_with_slug,
  sessions_slug_unknown, sources``.
- ``summary_row_slug(row: dict) -> str`` -- ``row.get("pipeline_slug",
  "unknown")``.
- ``summary_row_is_rollup_unattributed(row: dict) -> bool`` -- true when the
  row's ``tokens_by_agent_type`` carries any populated rollup.
- ``_audit_totals(coverage: Coverage, buckets: list[PipelineBucket]) -> list[str]``
  -- the dec-378 executable guard; returns violated-invariant messages, empty
  when consistent.
- ``compute_f12_cell(buckets: list[PipelineBucket]) -> dict`` -- the two result
  shapes (``{"status": "n/a", "reason": ...}`` /
  ``{"status": "rendered", "basis": "tokens_total", "standard": {...},
  "lightweight": {...}, "ratio": ...}``), sharing no numeric key.
- ``CostCollector(Collector)`` -- ``name = "cost"``, ``tier = 0``; constructor
  ``CostCollector(repo_root: str)``; ``resolve(env) -> ResolutionResult``;
  ``collect(ctx) -> CollectorResult``.

**Fixture provenance** (stated once here; restated per-use below):

- ``attributed.jsonl`` -- **verbatim**, one real ``agent_stop`` row copied
  byte-for-byte from
  ``.claude/worktrees/process-economy-p3-6-adopt/.ai-state/observations.jsonl``
  (``usage_source: "subagent-transcript"``).
- ``pre_attribution.jsonl`` -- **verbatim**, one real ``agent_stop`` row
  copied byte-for-byte from ``/Users/fperez/dev/praxion/.ai-state/observations.jsonl``
  (no ``usage_source`` key; token fields populated).
- ``unparsed.jsonl`` -- **verbatim**, one real ``agent_stop`` row copied
  byte-for-byte from the same file (no ``usage_source`` key; no token
  fields present at all).
- ``parent_sourced_synthetic.jsonl`` -- **synthesized**: the
  ``pre_attribution.jsonl`` row with ``"usage_source"`` set to
  ``"parent-transcript"``. Zero live examples of this variant exist in the
  corpus (measured 2026-09-22); presenting it as a corpus excerpt would be
  false, so it is labelled synthetic here and at its point of use.
- Dedup fixtures (same-``agent_id`` cases) -- **hand-constructed** in the
  test bodies below, copying the ``attributed.jsonl`` row's field shape with
  varied ``agent_id``/``source_path``/token values. The dedup rule is a
  mechanical rule over row shape, not a provenance claim, so hand
  construction is acceptable here specifically (see the plan's fixture
  strategy note).
- ``calibration_log_excerpt.md`` -- **verbatim**, nine pipe-table rows (plus
  header and separator) copied byte-for-byte from
  ``.ai-state/calibration_log.md``: the two agreeing Standard-tier rows for
  ``process-economy-p3-2-adopt`` and ``process-economy-p3-6-adopt``, plus
  every row for the three slugs whose calibration rows disagree on tier
  (``sentinel-fanout-audit``: Full + Standard; ``process-economy-phase1``:
  Direct + Lightweight + Full; ``process-economy-p2-residual``: Direct +
  Standard).
- ``summary_rollup_unattributed.jsonl`` -- **verbatim**, one committed
  session-summary row copied byte-for-byte from this worktree's own
  ``.ai-state/observations_summary.jsonl`` (session ``50ac9347...``),
  carrying the measured 14,666,970,597-token ``tokens_by_agent_type``
  rollup. This row (like every row in that file today) also lacks
  ``pipeline_slug`` -- it doubles as the pre-change fixture for the
  ``slug: unknown`` census path, the same single-session reuse choice this
  test suite's own legacy-row fixture already made.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixture loading -- one real JSONL line per file under fixtures/cost/.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cost_fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "cost"


def _load_single_row(path: Path) -> dict[str, Any]:
    """Read a one-line JSONL fixture into a dict. Fails loudly if the fixture
    is missing or holds anything other than exactly one JSON line -- a
    silently-empty fixture would make every dependent test vacuously pass.
    """

    lines = [line for line in path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1, f"Fixture {path} must hold exactly one JSONL row; found {len(lines)}."
    return json.loads(lines[0])


@pytest.fixture
def attributed_row(cost_fixtures_dir: Path) -> dict[str, Any]:
    """Verbatim `agent_stop` row, `usage_source: "subagent-transcript"`.

    Source: .claude/worktrees/process-economy-p3-6-adopt/.ai-state/observations.jsonl
    """

    return _load_single_row(cost_fixtures_dir / "attributed.jsonl")


@pytest.fixture
def pre_attribution_row(cost_fixtures_dir: Path) -> dict[str, Any]:
    """Verbatim `agent_stop` row, no `usage_source` key, tokens populated.

    Source: /Users/fperez/dev/praxion/.ai-state/observations.jsonl
    """

    return _load_single_row(cost_fixtures_dir / "pre_attribution.jsonl")


@pytest.fixture
def unparsed_row(cost_fixtures_dir: Path) -> dict[str, Any]:
    """Verbatim `agent_stop` row, no `usage_source` key, no token fields.

    Source: /Users/fperez/dev/praxion/.ai-state/observations.jsonl
    """

    return _load_single_row(cost_fixtures_dir / "unparsed.jsonl")


@pytest.fixture
def parent_sourced_row(cost_fixtures_dir: Path) -> dict[str, Any]:
    """SYNTHESIZED: pre_attribution_row with usage_source forced to
    "parent-transcript". No live example of this variant exists in the
    corpus (measured 2026-09-22, 0 of 5,098 distinct agent_ids) -- this
    fixture is fabricated to exercise the branch, not a real excerpt.
    """

    return _load_single_row(cost_fixtures_dir / "parent_sourced_synthetic.jsonl")


# ---------------------------------------------------------------------------
# Provenance classification -- the four-way honesty partition.
# ---------------------------------------------------------------------------


class TestClassifyProvenance:
    """`_classify(row) -> Provenance` is the sole entry point for the
    honesty partition; every variant must round-trip through it correctly.
    """

    def test_classifies_subagent_transcript_row_as_attributed(
        self, attributed_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        assert _classify(attributed_row) is Provenance.ATTRIBUTED

    def test_classifies_synthesized_parent_transcript_row_as_parent_sourced(
        self, parent_sourced_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        assert _classify(parent_sourced_row) is Provenance.PARENT_SOURCED

    def test_honest_marker_with_every_token_field_null_is_not_attributed(
        self, attributed_row: dict[str, Any]
    ) -> None:
        """Attribution needs the honest marker AND at least one usage field;
        a marker over four nulls has nothing to attribute and would otherwise
        enter every total as a zero-token row."""

        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        row = {
            **attributed_row,
            "tokens_in": None,
            "tokens_out": None,
            "cache_read": None,
            "cache_create": None,
        }

        assert _classify(row) is Provenance.UNPARSED

    @pytest.mark.parametrize("corrupt_value", ["n/a", float("inf")])
    def test_a_token_field_that_cannot_be_coerced_quarantines_the_row_as_unparsed(
        self, attributed_row: dict[str, Any], corrupt_value: object
    ) -> None:
        """A usage number the collector cannot read is not silently zero --
        the row lands in the population named for exactly that, so the
        census and the read path agree and the coverage block says so."""

        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        row = {**attributed_row, "tokens_in": corrupt_value}

        assert _classify(row) is Provenance.UNPARSED

    def test_a_pre_attribution_row_with_an_unreadable_token_field_is_unparsed(
        self, pre_attribution_row: dict[str, Any]
    ) -> None:
        """The key-absent branch applies the same readability rule, so the
        census and the read path never disagree about which quarantine
        bucket a corrupt row belongs to."""

        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        row = {**pre_attribution_row, "tokens_out": "n/a"}

        assert _classify(row) is Provenance.UNPARSED

    def test_classifies_key_absent_row_with_tokens_as_pre_attribution(
        self, pre_attribution_row: dict[str, Any]
    ) -> None:
        """The 286-row pre-fix population: `usage_source` key is entirely
        absent (not merely falsy) and at least one token field is non-null.
        """

        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        assert "usage_source" not in pre_attribution_row, (
            "Fixture drift: pre_attribution_row must lack the usage_source "
            "key entirely to exercise the absence-based partition."
        )
        assert _classify(pre_attribution_row) is Provenance.PRE_ATTRIBUTION

    def test_classifies_key_absent_row_with_no_tokens_as_unparsed(
        self, unparsed_row: dict[str, Any]
    ) -> None:
        """A row with the usage_source key absent AND no token fields
        present at all must NOT be conflated with pre-attribution -- the
        distinction the quarantine exists to make.
        """

        from scripts.project_metrics.collectors.cost_collector import (
            Provenance,
            _classify,
        )

        assert "usage_source" not in unparsed_row
        assert "tokens_in" not in unparsed_row
        assert _classify(unparsed_row) is Provenance.UNPARSED

    def test_provenance_has_exactly_four_members(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import Provenance

        assert {member.value for member in Provenance} == {
            "attributed",
            "parent-sourced",
            "pre-attribution",
            "unparsed",
        }


# ---------------------------------------------------------------------------
# AttributedRow construction -- the only path into the honest population.
# ---------------------------------------------------------------------------


class TestAttributedFromRow:
    """`_attributed_from_row` is the only constructor path for AttributedRow
    -- it must return None for every non-attributed variant and coerce
    null token fields to 0 at construction, never downstream.
    """

    def test_builds_attributed_row_with_every_field_populated(
        self, attributed_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            AttributedRow,
            _attributed_from_row,
        )

        result = _attributed_from_row(attributed_row, source_path="fixtures/cost/attributed.jsonl")

        assert isinstance(result, AttributedRow)
        assert result.agent_id == "a76bb0db75981064f"
        assert result.session_id == "f24cda13-489f-4da1-a37c-b6bacd468135"
        assert result.pipeline_slug == "process-economy-p3-6-adopt"
        assert result.agent_type == "praxion:context-engineer"
        assert result.agent_type_source == "payload"
        assert result.model == "claude-sonnet-5"
        assert result.tokens_in == 80
        assert result.tokens_out == 21796
        assert result.cache_read == 3359140
        assert result.cache_create == 321135
        assert result.duration_ms == 226552
        assert result.timestamp == "2026-09-20T22:13:04.658354+00:00"
        assert result.source_path == "fixtures/cost/attributed.jsonl"

    def test_returns_none_for_pre_attribution_row(
        self, pre_attribution_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import _attributed_from_row

        assert _attributed_from_row(pre_attribution_row, source_path="x.jsonl") is None

    def test_returns_none_for_unparsed_row(self, unparsed_row: dict[str, Any]) -> None:
        from scripts.project_metrics.collectors.cost_collector import _attributed_from_row

        assert _attributed_from_row(unparsed_row, source_path="x.jsonl") is None

    def test_returns_none_for_synthesized_parent_sourced_row(
        self, parent_sourced_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import _attributed_from_row

        assert _attributed_from_row(parent_sourced_row, source_path="x.jsonl") is None

    def test_coerces_null_token_fields_to_zero_at_construction(self) -> None:
        """Hand-constructed: an attributed row (usage_source correct, at
        least one usage field non-null so it classifies attributed) with two
        of its four token fields explicitly null. Not sourced from the
        corpus -- built to exercise the None-to-0 token coercion path, which
        no live row happens to exhibit.
        """

        from scripts.project_metrics.collectors.cost_collector import _attributed_from_row

        row = {
            "timestamp": "2026-09-21T00:00:00+00:00",
            "session_id": "session-coercion-case",
            "agent_type": "praxion:implementer",
            "agent_id": "coercion-agent-id",
            "project": "some-pipeline",
            "event_type": "agent_stop",
            "agent_type_source": "payload",
            "tokens_in": None,
            "tokens_out": 100,
            "cache_read": None,
            "cache_create": 50,
            "duration_ms": 1000,
            "model": "claude-sonnet-5",
            "usage_source": "subagent-transcript",
        }

        result = _attributed_from_row(row, source_path="x.jsonl")

        assert result is not None
        assert result.tokens_in == 0
        assert result.cache_read == 0
        assert result.tokens_out == 100
        assert result.cache_create == 50

    def test_an_infinite_duration_degrades_to_zero_instead_of_raising(
        self, attributed_row: dict[str, Any]
    ) -> None:
        """`json.loads` accepts `Infinity`; one odd non-token field must never
        fail the whole run -- the contract is a degraded field, never a
        raise the runner has to catch."""

        from scripts.project_metrics.collectors.cost_collector import _attributed_from_row

        row = {**attributed_row, "duration_ms": float("inf")}

        result = _attributed_from_row(row, source_path="x.jsonl")

        assert result is not None
        assert result.duration_ms == 0


# ---------------------------------------------------------------------------
# Source discovery -- injectable git seam, tmp_path filesystem, ordering + degradation.
# ---------------------------------------------------------------------------


def _touch(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestDiscoverSources:
    """`discover_sources` enumerates the documented source set, de-duplicated
    by resolved path. Git is never shelled out to in these tests --
    `_resolve_main_checkout` is monkeypatched, the module-level seam this
    test file pins for exactly that purpose.
    """

    def test_dedupes_when_repo_root_is_the_main_checkout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector

        checkout = tmp_path / "checkout"
        _touch(checkout / ".ai-state" / "observations.jsonl", "{}\n")
        _touch(checkout / ".ai-state" / "observations.jsonl.1", "{}\n")
        _touch(checkout / ".ai-state" / "observations_summary.jsonl", "{}\n")
        _touch(
            checkout
            / ".claude"
            / "worktrees"
            / "other-pipeline"
            / ".ai-state"
            / "observations.jsonl",
            "{}\n",
        )

        monkeypatch.setattr(
            cost_collector, "_resolve_main_checkout", lambda repo_root: (str(checkout), None)
        )

        sources, issues = cost_collector.discover_sources(str(checkout))

        assert issues == []
        # repo_root's own WAL and the main checkout's WAL resolve to the
        # same path -- must appear exactly once, not twice.
        wal_paths = [s.path for s in sources if s.kind == "wal" and s.checkout == "checkout"]
        assert wal_paths == [str(checkout / ".ai-state" / "observations.jsonl")]

        kinds_and_checkouts = [(s.kind, s.checkout) for s in sources]
        assert kinds_and_checkouts == [
            ("wal", "checkout"),
            ("wal-archive", "checkout"),
            ("wal", "other-pipeline"),
            ("summary", "checkout"),
        ], f"Unexpected discovery order/set: {kinds_and_checkouts!r}"

    def test_includes_both_repo_root_and_main_when_they_differ(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector

        repo_root = tmp_path / "worktree-x"
        main_checkout = tmp_path / "main"
        _touch(repo_root / ".ai-state" / "observations.jsonl", "{}\n")
        _touch(main_checkout / ".ai-state" / "observations.jsonl", "{}\n")

        monkeypatch.setattr(
            cost_collector,
            "_resolve_main_checkout",
            lambda repo_root_arg: (str(main_checkout), None),
        )

        sources, issues = cost_collector.discover_sources(str(repo_root))

        assert issues == []
        checkouts = {s.checkout for s in sources}
        assert checkouts == {"worktree-x", "main"}, (
            "Both the worktree's own WAL and the main checkout's WAL must be "
            "visible -- this is the source-set symmetry the anchor exists for."
        )

    def test_git_rev_parse_failure_degrades_to_repo_root_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector

        repo_root = tmp_path / "detached"
        _touch(repo_root / ".ai-state" / "observations.jsonl", "{}\n")

        monkeypatch.setattr(
            cost_collector,
            "_resolve_main_checkout",
            lambda repo_root_arg: (None, "not a git repository"),
        )

        sources, issues = cost_collector.discover_sources(str(repo_root))

        assert [s.checkout for s in sources] == ["detached"], (
            "On git-rev-parse failure the source set must shrink to "
            "repo_root only -- no worktree/main paths."
        )
        assert "worktree discovery unavailable: not a git repository" in issues


# ---------------------------------------------------------------------------
# Streaming reader -- graceful degradation, per-source.
# ---------------------------------------------------------------------------


class TestReadAgentStopRows:
    """`read_agent_stop_rows` streams one source file, filtering to
    `event_type == "agent_stop"`, and degrades unreadable/malformed sources
    to zero rows with a named issue rather than raising.
    """

    def test_reads_only_agent_stop_rows_from_a_well_formed_file(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.cost_collector import read_agent_stop_rows

        path = tmp_path / "observations.jsonl"
        path.write_text(
            json.dumps({"event_type": "agent_stop", "agent_id": "x"})
            + "\n"
            + json.dumps({"event_type": "session_start", "agent_id": "y"})
            + "\n"
        )

        rows, issue = read_agent_stop_rows(str(path))

        assert issue is None
        assert len(rows) == 1
        assert rows[0]["agent_id"] == "x"

    def test_missing_file_degrades_to_zero_rows_with_named_issue(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.cost_collector import read_agent_stop_rows

        rows, issue = read_agent_stop_rows(str(tmp_path / "does-not-exist.jsonl"))

        assert rows == []
        assert issue is not None
        assert "does-not-exist.jsonl" in issue

    def test_malformed_file_degrades_to_zero_rows_without_raising(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.cost_collector import read_agent_stop_rows

        path = tmp_path / "malformed.jsonl"
        path.write_text("{ this is not valid json\n")

        rows, issue = read_agent_stop_rows(str(path))

        assert rows == []
        assert issue is not None

    def test_torn_trailing_line_keeps_the_valid_rows_and_counts_the_skip(
        self, tmp_path: Path
    ) -> None:
        """The WAL is append-only and live: a torn last line while a session
        is running is a normal state, not corruption of the rows before it.
        Those rows are kept; the skip is reported as a counted issue, never
        as a silently smaller file."""
        from scripts.project_metrics.collectors.cost_collector import read_agent_stop_rows

        valid = json.dumps({"event_type": "agent_stop", "agent_id": "x"})
        path = tmp_path / "live.jsonl"
        path.write_text(valid + "\n" + valid.replace('"x"', '"y"') + '\n{"event_type": "agent_st')

        rows, issue = read_agent_stop_rows(str(path))

        assert [row["agent_id"] for row in rows] == ["x", "y"]
        assert issue is not None
        assert "1 malformed line" in issue


# ---------------------------------------------------------------------------
# Dedup -- last-in-file, first-across-files, by agent_id.
# ---------------------------------------------------------------------------


def _attributed_row_from_template(
    attributed_row: dict[str, Any], *, agent_id: str, tokens_out: int, source_path: str
) -> Any:
    """Build an AttributedRow by copying attributed_row's field shape with
    the identifying fields swapped -- hand-constructed per the dedup
    fixture strategy (mechanical rule, not a provenance claim).
    """

    from scripts.project_metrics.collectors.cost_collector import _attributed_from_row

    row = dict(attributed_row)
    row["agent_id"] = agent_id
    row["tokens_out"] = tokens_out
    result = _attributed_from_row(row, source_path=source_path)
    assert result is not None, "Template row must still classify as attributed."
    return result


class TestDedupAttributedRows:
    """`dedup_attributed_rows` keeps exactly one row per `agent_id`: the
    last row within a file, and the first file in source order across
    files. Cross-file repeats are recorded, never silently collapsed or
    summed -- including the same-agent_id-different-payload case the
    plan's own pre-mortem names as a risk to pin.
    """

    def test_last_in_file_wins_for_an_intra_file_duplicate(
        self, attributed_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import dedup_attributed_rows

        earlier = _attributed_row_from_template(
            attributed_row, agent_id="shared-agent", tokens_out=1111, source_path="fileA.jsonl"
        )
        later_different_payload = _attributed_row_from_template(
            attributed_row, agent_id="shared-agent", tokens_out=2222, source_path="fileA.jsonl"
        )

        deduped, duplicate_agent_ids = dedup_attributed_rows([earlier, later_different_payload])

        assert len(deduped) == 1
        assert deduped[0].tokens_out == 2222, (
            "The row appearing LAST in file order must survive, even though "
            "the two rows carry different payloads for the same agent_id -- "
            "this is not summed and the earlier row is not silently kept."
        )
        assert duplicate_agent_ids == [], (
            "An intra-file repeat is not a cross-file duplicate; "
            "duplicate_agent_ids records cross-file repeats only."
        )

    def test_first_across_files_wins_and_repeat_is_recorded(
        self, attributed_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import dedup_attributed_rows

        file_a_earlier = _attributed_row_from_template(
            attributed_row, agent_id="shared-agent", tokens_out=1111, source_path="fileA.jsonl"
        )
        file_a_later = _attributed_row_from_template(
            attributed_row, agent_id="shared-agent", tokens_out=2222, source_path="fileA.jsonl"
        )
        file_b_repeat = _attributed_row_from_template(
            attributed_row, agent_id="shared-agent", tokens_out=3333, source_path="fileB.jsonl"
        )
        solo = _attributed_row_from_template(
            attributed_row, agent_id="solo-agent", tokens_out=9999, source_path="fileA.jsonl"
        )

        deduped, duplicate_agent_ids = dedup_attributed_rows(
            [file_a_earlier, file_a_later, file_b_repeat, solo]
        )

        by_agent_id = {row.agent_id: row for row in deduped}
        assert set(by_agent_id) == {"shared-agent", "solo-agent"}, (
            "Exactly one surviving row per agent_id -- the cross-file "
            "repeat must not add a second bucket entry or vanish entirely."
        )
        assert by_agent_id["shared-agent"].source_path == "fileA.jsonl", (
            "fileA precedes fileB in source order, so fileA's row wins the "
            "cross-file tie, not the last-seen file."
        )
        assert by_agent_id["shared-agent"].tokens_out == 2222, (
            "Within the winning file, last-in-file still applies."
        )
        assert duplicate_agent_ids == ["shared-agent"], (
            "The cross-file repeat is named, not swallowed -- coverage.duplicate_agent_ids "
            "must be able to report it."
        )

    def test_no_duplicates_leaves_every_row_and_reports_empty(
        self, attributed_row: dict[str, Any]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import dedup_attributed_rows

        row_one = _attributed_row_from_template(
            attributed_row, agent_id="agent-one", tokens_out=100, source_path="fileA.jsonl"
        )
        row_two = _attributed_row_from_template(
            attributed_row, agent_id="agent-two", tokens_out=200, source_path="fileA.jsonl"
        )

        deduped, duplicate_agent_ids = dedup_attributed_rows([row_one, row_two])

        assert {row.agent_id for row in deduped} == {"agent-one", "agent-two"}
        assert duplicate_agent_ids == []


# ---------------------------------------------------------------------------
# Fixture integrity -- sanity that the committed fixtures were not corrupted.
# ---------------------------------------------------------------------------


class TestCostFixtureIntegrity:
    """Not a collector assertion -- guards the fixture files themselves."""

    def test_attributed_fixture_has_the_expected_agent_id(
        self, attributed_row: dict[str, Any]
    ) -> None:
        assert attributed_row["agent_id"] == "a76bb0db75981064f"
        assert attributed_row["usage_source"] == "subagent-transcript"

    def test_pre_attribution_fixture_lacks_usage_source_key(
        self, pre_attribution_row: dict[str, Any]
    ) -> None:
        assert "usage_source" not in pre_attribution_row
        assert pre_attribution_row["tokens_in"] is not None

    def test_parent_sourced_fixture_is_labelled_synthetic_and_shares_pre_attribution_shape(
        self, parent_sourced_row: dict[str, Any], pre_attribution_row: dict[str, Any]
    ) -> None:
        assert parent_sourced_row["usage_source"] == "parent-transcript"
        assert parent_sourced_row["agent_id"] == pre_attribution_row["agent_id"], (
            "The synthetic fixture is the pre_attribution row with only "
            "usage_source changed -- every other field must still match."
        )


# ---------------------------------------------------------------------------
# Tier join -- resolving a pipeline slug to a calibration-log tier.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def calibration_log_excerpt_path(cost_fixtures_dir: Path) -> Path:
    return cost_fixtures_dir / "calibration_log_excerpt.md"


class TestParseCalibrationLog:
    """`parse_calibration_log` builds the slug -> tier-tokens index every
    tier-resolution test below reads from.
    """

    def test_normalizes_the_actual_tier_cells_leading_alphabetic_token(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import parse_calibration_log

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        assert index["process-economy-p3-2-adopt"] == ["Standard"]
        assert index["process-economy-p3-6-adopt"] == ["Standard"]
        assert set(index["sentinel-fanout-audit"]) == {"Full", "Standard"}, (
            "Both sentinel-fanout-audit rows must be indexed -- prose-decorated "
            "cells like 'Standard (batched, ...)' must normalize to 'Standard', "
            "not fail to parse or be indexed under the raw prose."
        )

    @pytest.mark.skipif(
        os.geteuid() == 0,
        reason="root ignores file modes; remove when the reader is injected",
    )
    def test_an_unreadable_calibration_log_is_a_named_issue_not_a_raise(
        self, tmp_path: Path, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import _load_tier_index

        log = tmp_path / ".ai-state" / "calibration_log.md"
        log.parent.mkdir()
        log.write_text(calibration_log_excerpt_path.read_text())
        log.chmod(0o000)
        issues: list[str] = []

        try:
            index = _load_tier_index(str(tmp_path), issues)
        finally:
            log.chmod(0o600)

        assert index == {}
        assert len(issues) == 1, issues
        assert "calibration log unreadable" in issues[0], issues

    def test_an_invalid_utf8_byte_in_the_log_degrades_that_cell_not_the_index(
        self, tmp_path: Path, calibration_log_excerpt_path: Path
    ) -> None:
        """The WAL reader and the producing hook both decode with
        `errors="replace"`; the calibration log gets the same treatment so
        one bad byte cannot raise a `UnicodeDecodeError` out of `collect()`."""

        from scripts.project_metrics.collectors.cost_collector import parse_calibration_log

        log = tmp_path / "calibration_log.md"
        log.write_bytes(
            calibration_log_excerpt_path.read_bytes()
            + b"| 2026-01-01 | bad\xff-row | x | x | Direct | x | x |\n"
        )

        index = parse_calibration_log(str(log))

        assert index["process-economy-p3-6-adopt"] == ["Standard"]


class TestResolveTier:
    """`resolve_tier` is the join itself -- slug -> tier is not a function,
    so it must expose three outcomes, never silently pick one.
    """

    @pytest.mark.parametrize("slug", ["process-economy-p3-2-adopt", "process-economy-p3-6-adopt"])
    def test_resolves_a_single_agreeing_slug_to_its_tier(
        self, calibration_log_excerpt_path: Path, slug: str
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            TierResolved,
            parse_calibration_log,
            resolve_tier,
        )

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        result = resolve_tier(slug, index)

        assert isinstance(result, TierResolved)
        assert result.tier == "Standard"

    @pytest.mark.parametrize(
        ("slug", "expected_tiers"),
        [
            ("sentinel-fanout-audit", {"Full", "Standard"}),
            ("process-economy-phase1", {"Direct", "Lightweight", "Full"}),
            ("process-economy-p2-residual", {"Direct", "Standard"}),
        ],
    )
    def test_resolves_a_disagreeing_slug_to_ambiguous_with_every_tier_listed(
        self, calibration_log_excerpt_path: Path, slug: str, expected_tiers: set[str]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            TierAmbiguous,
            parse_calibration_log,
            resolve_tier,
        )

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        result = resolve_tier(slug, index)

        assert isinstance(result, TierAmbiguous)
        assert set(result.tiers) == expected_tiers, (
            "A silent first-wins pick would fabricate a tier -- every "
            "disagreeing tier must be listed, not just the first one seen."
        )

    def test_resolves_a_slug_absent_from_the_calibration_log_to_unknown(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            TierUnknown,
            parse_calibration_log,
            resolve_tier,
        )

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        result = resolve_tier("no-such-pipeline-ever-ran", index)

        assert isinstance(result, TierUnknown)
        assert result.reason == "no-calibration-row"


# ---------------------------------------------------------------------------
# Pipeline bucket aggregation -- one bucket list, three projections.
# ---------------------------------------------------------------------------


def _make_attributed_row(**overrides: Any) -> Any:
    """Build an `AttributedRow` directly via its dataclass constructor --
    a test data builder with minimal, overridable defaults, per the
    aggregate pass's own fixture strategy (a mechanical rule over row
    shape, not a provenance claim, so hand construction is appropriate).
    """

    from scripts.project_metrics.collectors.cost_collector import AttributedRow

    defaults: dict[str, Any] = {
        "agent_id": "agent-default",
        "session_id": "session-default",
        "pipeline_slug": "process-economy-p3-2-adopt",
        "agent_type": "praxion:implementer",
        "agent_type_source": "payload",
        "model": "claude-sonnet-5",
        "tokens_in": 10,
        "tokens_out": 20,
        "cache_read": 30,
        "cache_create": 40,
        "duration_ms": 1000,
        "timestamp": "2026-09-21T00:00:00+00:00",
        "source_path": "fixtures/cost/synthetic.jsonl",
    }
    defaults.update(overrides)
    return AttributedRow(**defaults)


class TestBuildPipelineBuckets:
    """`build_pipeline_buckets` folds attributed rows into one bucket per
    `pipeline_slug`, joined to its tier -- the single population every
    per-pipeline/per-tier/per-agent-type table is a projection of.
    """

    def test_folds_same_slug_rows_into_one_bucket_carrying_the_resolved_tier(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            build_pipeline_buckets,
            parse_calibration_log,
        )

        tier_index = parse_calibration_log(str(calibration_log_excerpt_path))
        row_one = _make_attributed_row(
            agent_id="a1",
            pipeline_slug="process-economy-p3-2-adopt",
            agent_type="praxion:implementer",
            tokens_in=10,
            tokens_out=20,
            cache_read=30,
            cache_create=40,
        )
        row_two = _make_attributed_row(
            agent_id="a2",
            pipeline_slug="process-economy-p3-2-adopt",
            agent_type="praxion:test-engineer",
            tokens_in=1,
            tokens_out=2,
            cache_read=3,
            cache_create=4,
        )

        buckets = build_pipeline_buckets([row_one, row_two], tier_index)

        assert len(buckets) == 1, "Both rows share one pipeline_slug -- one bucket, not two."
        bucket = buckets[0]
        assert bucket.pipeline_slug == "process-economy-p3-2-adopt"
        assert bucket.tier == "Standard"
        assert bucket.attributed_rows == 2
        assert bucket.tokens["tokens_total"] == (10 + 20 + 30 + 40) + (1 + 2 + 3 + 4)
        assert set(bucket.by_agent_type) == {"praxion:implementer", "praxion:test-engineer"}

    def test_an_unjoinable_slug_still_gets_its_own_bucket_marked_unknown(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            build_pipeline_buckets,
            parse_calibration_log,
        )

        tier_index = parse_calibration_log(str(calibration_log_excerpt_path))
        row = _make_attributed_row(agent_id="a1", pipeline_slug="never-calibrated")

        buckets = build_pipeline_buckets([row], tier_index)

        assert len(buckets) == 1
        assert buckets[0].tier == "unknown", (
            "An unjoinable pipeline stays visible, never dropped -- the "
            "brief's core constraint for an uncalibrated slug."
        )

    def test_per_tier_and_per_agent_type_totals_never_disagree_with_the_grand_total(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        """Three tables -- per-pipeline, per-tier, per-agent-type -- must be
        three projections of the SAME bucket list. Grouping the same
        buckets two different ways (by tier, by agent type) and comparing
        each grouped sum against the ungrouped grand total is the property
        that makes the tables structurally unable to disagree -- three
        independent scans over the raw rows could silently drift apart,
        one fold over one list cannot.
        """

        from scripts.project_metrics.collectors.cost_collector import (
            build_pipeline_buckets,
            parse_calibration_log,
        )

        tier_index = parse_calibration_log(str(calibration_log_excerpt_path))
        rows = [
            _make_attributed_row(
                agent_id="std-1",
                pipeline_slug="process-economy-p3-2-adopt",
                agent_type="praxion:implementer",
                tokens_in=10,
                tokens_out=20,
                cache_read=30,
                cache_create=40,
            ),
            _make_attributed_row(
                agent_id="std-2",
                pipeline_slug="process-economy-p3-6-adopt",
                agent_type="praxion:test-engineer",
                tokens_in=1,
                tokens_out=2,
                cache_read=3,
                cache_create=4,
            ),
        ]

        buckets = build_pipeline_buckets(rows, tier_index)
        grand_total = sum(bucket.tokens["tokens_total"] for bucket in buckets)

        tier_totals: dict[str, int] = {}
        for bucket in buckets:
            tier_totals[bucket.tier] = (
                tier_totals.get(bucket.tier, 0) + bucket.tokens["tokens_total"]
            )

        agent_type_totals: dict[str, int] = {}
        for bucket in buckets:
            for agent_type, agent_tokens in bucket.by_agent_type.items():
                agent_type_totals[agent_type] = (
                    agent_type_totals.get(agent_type, 0) + agent_tokens["tokens_total"]
                )

        assert sum(tier_totals.values()) == grand_total, (
            "Grouping the same buckets by tier must reproduce the grand "
            "total -- the per-tier table cannot show a different sum than "
            "the per-pipeline table."
        )
        assert sum(agent_type_totals.values()) == grand_total, (
            "Grouping the same buckets by agent type must also reproduce the grand total."
        )


class TestUnresolvedAgentTypeShare:
    """The unresolved `agent_type_source` share is its own figure, never
    folded into a named agent type's total.
    """

    def test_reports_the_unresolved_share_of_attributed_rows(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            unresolved_agent_type_share,
        )

        resolved_row = _make_attributed_row(agent_id="r1", agent_type_source="payload")
        unresolved_row_a = _make_attributed_row(agent_id="u1", agent_type_source="unresolved")
        unresolved_row_b = _make_attributed_row(agent_id="u2", agent_type_source="unresolved")

        result = unresolved_agent_type_share([resolved_row, unresolved_row_a, unresolved_row_b])

        assert result["unresolved_rows"] == 2
        assert result["attributed_rows"] == 3
        assert result["share"] == pytest.approx(2 / 3)

    def test_zero_attributed_rows_reports_a_zero_share_without_dividing_by_zero(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            unresolved_agent_type_share,
        )

        result = unresolved_agent_type_share([])

        assert result["unresolved_rows"] == 0
        assert result["attributed_rows"] == 0
        assert result["share"] == 0


# ---------------------------------------------------------------------------
# Committed-summary census -- read-only, never a token source.
# ---------------------------------------------------------------------------


class TestSummaryRowCensusHelpers:
    """The committed summary's pipeline-slug census, and the
    summary-rollup-unattributed quarantine population its
    `tokens_by_agent_type` rollup belongs to -- over the committed
    `observations_summary.jsonl` row shape.
    """

    def test_a_summary_row_without_pipeline_slug_reads_as_unknown(
        self, cost_fixtures_dir: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import summary_row_slug

        row = _load_single_row(cost_fixtures_dir / "summary_rollup_unattributed.jsonl")

        assert "pipeline_slug" not in row, "Fixture drift: every committed row lacks the key today."
        assert summary_row_slug(row) == "unknown"

    def test_a_summary_row_carrying_pipeline_slug_reads_its_real_slug(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import summary_row_slug

        row = {"session_id": "x", "pipeline_slug": "process-economy-p3-2-adopt"}

        assert summary_row_slug(row) == "process-economy-p3-2-adopt"

    def test_the_measured_14_billion_token_rollup_is_counted_as_quarantined(
        self, cost_fixtures_dir: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            summary_row_is_rollup_unattributed,
        )

        row = _load_single_row(cost_fixtures_dir / "summary_rollup_unattributed.jsonl")

        assert summary_row_is_rollup_unattributed(row) is True

    def test_a_summary_row_with_no_token_rollup_is_not_quarantined(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            summary_row_is_rollup_unattributed,
        )

        row = {"session_id": "y", "tokens_by_agent_type": {}}

        assert summary_row_is_rollup_unattributed(row) is False


class TestAggregatePassFixtureIntegrity:
    """Guards the aggregate-pass fixtures themselves, not the collector."""

    def test_summary_rollup_fixture_carries_the_measured_token_total(
        self, cost_fixtures_dir: Path
    ) -> None:
        row = _load_single_row(cost_fixtures_dir / "summary_rollup_unattributed.jsonl")

        total = sum(sum(per_type.values()) for per_type in row["tokens_by_agent_type"].values())

        assert total == 14_666_970_597
        assert "pipeline_slug" not in row


# ---------------------------------------------------------------------------
# The dec-378 executable guard -- re-derivation, not assertion.
# ---------------------------------------------------------------------------


def _make_coverage(**overrides: Any) -> Any:
    from scripts.project_metrics.collectors.cost_collector import Coverage

    defaults: dict[str, Any] = {
        "attributed_rows": 2,
        "total_agent_stop_rows": 5,
        "quarantine": {
            "parent-sourced": 0,
            "pre-attribution": 1,
            "unparsed": 2,
            "summary-rollup-unattributed": 0,
        },
        "duplicate_agent_ids": [],
        "sessions_durable": 0,
        "sessions_with_slug": 0,
        "sessions_slug_unknown": 0,
        "sources": [],
    }
    defaults.update(overrides)
    return Coverage(**defaults)


def _make_pipeline_bucket(**overrides: Any) -> Any:
    from scripts.project_metrics.collectors.cost_collector import PipelineBucket

    defaults: dict[str, Any] = {
        "pipeline_slug": "process-economy-p3-2-adopt",
        "tier": "Standard",
        "tier_reason": None,
        "attributed_rows": 2,
        "sessions": 1,
        "models": frozenset({"claude-sonnet-5"}),
        "tokens": {
            "tokens_in": 0,
            "tokens_out": 0,
            "cache_read": 0,
            "cache_create": 0,
            "tokens_total": 0,
        },
        "by_agent_type": {},
    }
    defaults.update(overrides)
    return PipelineBucket(**defaults)


class TestAuditTotals:
    """`_audit_totals` re-derives two counts from independent sources and
    compares them before any total is published -- proven here at the unit
    level; the fault-injection test below proves it fires through the full
    `collect()` path.
    """

    def test_consistent_counts_produce_no_issues(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import _audit_totals

        coverage = _make_coverage()
        bucket = _make_pipeline_bucket(attributed_rows=2)

        assert _audit_totals(coverage, [bucket]) == []

    def test_a_bucket_sum_mismatched_with_coverage_names_the_invariant(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import _audit_totals

        coverage = _make_coverage(attributed_rows=2)
        bucket = _make_pipeline_bucket(attributed_rows=99)  # deliberately wrong

        issues = _audit_totals(coverage, [bucket])

        assert issues, "A bucket-sum/coverage mismatch must be reported, never silently accepted."
        assert "attributed" in issues[0].lower()

    def test_a_quarantine_census_mismatched_with_the_total_names_the_invariant(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import _audit_totals

        coverage = _make_coverage(total_agent_stop_rows=999)  # no longer sums correctly
        bucket = _make_pipeline_bucket(attributed_rows=2)

        issues = _audit_totals(coverage, [bucket])

        assert issues, (
            "attributed + quarantine must equal total_agent_stop_rows, or the guard fires."
        )


class TestCostCollectorFaultInjection:
    """The executable half of the dec-378 measured-cost-plus-guard pair: force a `pre-attribution`
    row past the classifier and prove the guard catches it through the
    real `collect()` path -- not assumed to, proven to.
    """

    def test_a_misclassified_row_reaching_a_total_is_rejected_with_no_totals_published(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        pre_attribution_row: dict[str, Any],
    ) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector
        from scripts.project_metrics.collectors.base import CollectionContext

        assert "usage_source" not in pre_attribution_row, (
            "Fixture drift: this row must be a genuine pre-attribution row "
            "for the injection to mean anything."
        )

        wal_path = tmp_path / ".ai-state" / "observations.jsonl"
        wal_path.parent.mkdir(parents=True, exist_ok=True)
        wal_path.write_text(json.dumps(pre_attribution_row) + "\n")

        # No real worktree discovery for this test -- isolates it from the
        # ambient environment entirely (determinism, not just speed).
        monkeypatch.setattr(
            cost_collector, "_resolve_main_checkout", lambda repo_root: (None, "not needed")
        )
        # The fault: force the classifier to call a genuine pre-attribution
        # row "attributed". The guard must catch this WITHOUT trusting the
        # (now-compromised) classifier's own verdict a second time.
        monkeypatch.setattr(
            cost_collector, "_classify", lambda row: cost_collector.Provenance.ATTRIBUTED
        )

        collector = cost_collector.CostCollector(repo_root=str(tmp_path))
        ctx = CollectionContext(repo_root=str(tmp_path), window_days=30, git_sha="deadbeef")

        result = collector.collect(ctx)

        assert result.status == "error"
        assert "pipelines" not in result.data
        assert "tiers" not in result.data
        assert "agent_types" not in result.data
        assert result.issues, "A caught invariant violation must be named, not silent."
        assert "invariant" in result.issues[0].lower()

    def test_a_miscounted_dedup_drop_is_rejected_with_no_totals_published(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        pre_attribution_row: dict[str, Any],
    ) -> None:
        """`total_agent_stop_rows` is derived from the read pass's own
        per-source row counts, never re-derived from the same census that
        also produces `attributed_rows`/`quarantine` -- so a defect in the
        census's own dedup bookkeeping is still visible as a genuine
        mismatch between two independently sourced numbers, not silently
        absorbed by a call-site `len(before) - len(after)` recompute (which
        would just re-measure whatever the -- possibly buggy -- dedup call
        actually returned and stay self-consistent regardless of what
        happened).
        """

        import scripts.project_metrics.collectors.cost_collector as cost_collector
        from scripts.project_metrics.collectors.base import CollectionContext

        # Two genuinely distinct pre-attribution rows (different agent_ids)
        # -- no real duplicate exists, so an honest dedup pass drops nothing.
        row_a = dict(pre_attribution_row)
        row_a["agent_id"] = "audit-row-a"
        row_b = dict(pre_attribution_row)
        row_b["agent_id"] = "audit-row-b"

        wal_path = tmp_path / ".ai-state" / "observations.jsonl"
        wal_path.parent.mkdir(parents=True, exist_ok=True)
        wal_path.write_text(json.dumps(row_a) + "\n" + json.dumps(row_b) + "\n")

        monkeypatch.setattr(
            cost_collector, "_resolve_main_checkout", lambda repo_root: (None, "not needed")
        )

        # The fault: the dedup core silently drops the second entry but
        # misreports zero rows dropped.
        real_dedup = cost_collector._dedup_by_agent_id

        def _lying_dedup(items, agent_id_of, source_path_of):
            deduped, duplicate_ids, _honest_dropped = real_dedup(items, agent_id_of, source_path_of)
            if len(deduped) > 1:
                deduped = deduped[:-1]
            return deduped, duplicate_ids, 0

        monkeypatch.setattr(cost_collector, "_dedup_by_agent_id", _lying_dedup)

        collector = cost_collector.CostCollector(repo_root=str(tmp_path))
        ctx = CollectionContext(repo_root=str(tmp_path), window_days=30, git_sha="deadbeef")

        result = collector.collect(ctx)

        assert result.status == "error"
        assert "pipelines" not in result.data
        assert "tiers" not in result.data
        assert "agent_types" not in result.data
        assert result.issues, "A caught invariant violation must be named, not silent."
        assert "invariant" in result.issues[0].lower()


# ---------------------------------------------------------------------------
# CostCollector.resolve -- the always-present-vs-absent split.
# ---------------------------------------------------------------------------


def _populate_repo(
    root: Path, attributed_row: dict[str, Any], calibration_log_excerpt: Path
) -> None:
    """One attributed WAL row plus the calibration-log excerpt under `root/.ai-state/`."""

    ai_state = root / ".ai-state"
    ai_state.mkdir(parents=True)
    (ai_state / "observations.jsonl").write_text(json.dumps(attributed_row) + "\n")
    (ai_state / "calibration_log.md").write_text(calibration_log_excerpt.read_text())


class TestCostCollectorProductionWiring:
    """The runner builds every collector with the repository root and then
    threads the literal `"."` through `CollectionContext.repo_root` -- the
    readiness collector's fallback treats that `"."` as absent and reads its
    constructor root. Every other `collect()` test in this module supplies
    an absolute context root, a configuration the runner never uses; these
    two drive the real call shape.
    """

    def test_runner_shaped_context_publishes_absolute_paths_and_named_checkouts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        attributed_row: dict[str, Any],
        calibration_log_excerpt_path: Path,
    ) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector
        from scripts.project_metrics.collectors.base import CollectionContext

        repo = tmp_path / "praxion"
        _populate_repo(repo, attributed_row, calibration_log_excerpt_path)
        monkeypatch.setattr(
            cost_collector, "_resolve_main_checkout", lambda repo_root: (None, "not needed")
        )
        monkeypatch.chdir(repo)

        collector = cost_collector.CostCollector(repo_root=str(repo))
        result = collector.collect(
            CollectionContext(repo_root=".", window_days=90, git_sha="deadbeef")
        )

        sources = result.data["coverage"]["sources"]
        assert sources, f"No sources published; issues={result.issues!r}"
        relative = [s["path"] for s in sources if not Path(s["path"]).is_absolute()]
        assert relative == [], f"A published source path must be absolute: {relative!r}"
        assert {s["checkout"] for s in sources} == {"praxion"}, (
            f"Every source must name its checkout; got {[s['checkout'] for s in sources]!r}"
        )

    def test_reads_the_constructor_root_when_the_process_cwd_is_elsewhere(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        attributed_row: dict[str, Any],
        calibration_log_excerpt_path: Path,
    ) -> None:
        """`git rev-parse --show-toplevel` (the CLI's root) works from any
        subdirectory, so the constructor root and the process cwd can differ
        in production; `collect()` must read the former."""

        import scripts.project_metrics.collectors.cost_collector as cost_collector
        from scripts.project_metrics.collectors.base import CollectionContext

        repo = tmp_path / "praxion"
        _populate_repo(repo, attributed_row, calibration_log_excerpt_path)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.setattr(
            cost_collector, "_resolve_main_checkout", lambda repo_root: (None, "not needed")
        )
        monkeypatch.chdir(elsewhere)

        collector = cost_collector.CostCollector(repo_root=str(repo))
        result = collector.collect(
            CollectionContext(repo_root=".", window_days=90, git_sha="deadbeef")
        )

        assert result.data["coverage"]["attributed_rows"] == 1, result.issues
        assert result.data["pipelines"][0]["tier"] == "Standard", (
            "The tier index must be read from the constructor root, not the cwd: "
            f"{result.data['pipelines']!r} issues={result.issues!r}"
        )


class TestCostCollectorResolve:
    def test_registers_as_the_cost_collector_at_tier_zero(self) -> None:
        """The collector must register under the exact name the report's
        JSON root key and `## Cost` heading are keyed on, and at tier 0
        (universal, not language-specific), so the runner always attempts
        it regardless of detected language.
        """

        import scripts.project_metrics.collectors.cost_collector as cost_collector

        collector = cost_collector.CostCollector(repo_root=".")

        assert collector.name == "cost"
        assert collector.tier == 0

    def test_resolves_available_when_the_wal_exists(self, tmp_path: Path) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector
        from scripts.project_metrics.collectors.base import Available, ResolutionEnv

        (tmp_path / ".ai-state").mkdir()
        (tmp_path / ".ai-state" / "observations.jsonl").write_text("")

        collector = cost_collector.CostCollector(repo_root=str(tmp_path))

        assert isinstance(collector.resolve(ResolutionEnv()), Available)

    def test_resolves_not_applicable_when_no_observability_artifacts_exist(
        self, tmp_path: Path
    ) -> None:
        import scripts.project_metrics.collectors.cost_collector as cost_collector
        from scripts.project_metrics.collectors.base import NotApplicable, ResolutionEnv

        collector = cost_collector.CostCollector(repo_root=str(tmp_path))

        result = collector.resolve(ResolutionEnv())

        assert isinstance(result, NotApplicable)
        assert "observability" in result.reason.lower()


# ---------------------------------------------------------------------------
# F12 cell -- the withheld-verdict shape, and the rendered ratio.
# ---------------------------------------------------------------------------


class TestComputeF12Cell:
    """Two shapes sharing no numeric key -- a consumer cannot read a
    ratio out of an `n/a` cell.
    """

    def test_renders_na_when_the_lightweight_median_is_zero_tokens(self) -> None:
        """Attributed rows do not imply a non-zero total; a zero divisor is
        an `n/a` cell with a reason, never a raise."""

        from scripts.project_metrics.collectors.cost_collector import compute_f12_cell

        zero_tokens = {
            "tokens_in": 0,
            "tokens_out": 0,
            "cache_read": 0,
            "cache_create": 0,
            "tokens_total": 0,
        }
        standard_bucket = _make_pipeline_bucket(
            pipeline_slug="standard-1",
            tier="Standard",
            attributed_rows=1,
            tokens={**zero_tokens, "tokens_total": 1000},
        )
        lightweight_bucket = _make_pipeline_bucket(
            pipeline_slug="lightweight-1",
            tier="Lightweight",
            attributed_rows=1,
            tokens=zero_tokens,
        )

        cell = compute_f12_cell([standard_bucket, lightweight_bucket])

        assert cell["status"] == "n/a"
        assert "zero" in cell["reason"].lower(), cell
        assert "ratio" not in cell

    def test_renders_na_with_a_reason_when_one_tier_has_zero_attributed_rows(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import compute_f12_cell

        standard_bucket = _make_pipeline_bucket(
            pipeline_slug="process-economy-p3-2-adopt",
            tier="Standard",
            attributed_rows=5,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 1000,
            },
        )

        cell = compute_f12_cell([standard_bucket])

        assert cell["status"] == "n/a"
        assert "lightweight" in cell["reason"].lower()
        assert "standard" not in cell
        assert "ratio" not in cell

    def test_renders_the_ratio_with_both_sample_sizes_and_basis_when_both_tiers_qualify(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import compute_f12_cell

        standard_bucket_one = _make_pipeline_bucket(
            pipeline_slug="standard-1",
            tier="Standard",
            attributed_rows=1,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 1000,
            },
        )
        standard_bucket_two = _make_pipeline_bucket(
            pipeline_slug="standard-2",
            tier="Standard",
            attributed_rows=1,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 3000,
            },
        )
        lightweight_bucket = _make_pipeline_bucket(
            pipeline_slug="lightweight-1",
            tier="Lightweight",
            attributed_rows=1,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 500,
            },
        )

        cell = compute_f12_cell([standard_bucket_one, standard_bucket_two, lightweight_bucket])

        assert cell["status"] == "rendered"
        assert cell["basis"] == "tokens_total"
        assert cell["standard"]["n"] == 2
        assert cell["lightweight"]["n"] == 1
        assert cell["ratio"] == pytest.approx(
            cell["standard"]["median"] / cell["lightweight"]["median"]
        )
