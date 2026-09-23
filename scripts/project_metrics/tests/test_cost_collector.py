"""Behavioral tests for the cost collector's read pass.

These tests encode the read-pass behavioral contract derived from
``.ai-work/process-economy-p3-5/SYSTEMS_PLAN.md`` (source discovery,
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
so these names are this file's own contract -- see
``.ai-work/process-economy-p3-5/LEARNINGS_test-engineer.md`` for the
rationale behind each pinned name):

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
"""

from __future__ import annotations

import json
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
