"""Behavioral tests for `CostCollector` itself -- the orchestration wiring
that threads the read pass and the aggregate pass together through the real
`collect()`/`resolve()` entry points, plus the executable half of the
dec-378 measured-cost-plus-guard pair proven through that same path.

**Import strategy**: every test imports from `cost_collector` inside the
test body (the "RED/GREEN deferred-import convention" this test suite
inherits from `test_git_collector.py`), preserved for consistency with the
read-pass and aggregate-pass siblings this file was split from.

**Interface pinned by this test file**:

- `CostCollector(Collector)` -- `name = "cost"`, `tier = 0`; constructor
  `CostCollector(repo_root: str)`; `resolve(env) -> ResolutionResult`;
  `collect(ctx) -> CollectorResult`.

**Fixture provenance**: `pre_attribution_row`, `attributed_row`, and
`calibration_log_excerpt_path` are shared fixtures defined in
`scripts/project_metrics/tests/conftest.py` -- see its module docstring for
full provenance (the calibration-log excerpt's own content is further
described in `test_cost_collector_aggregate.py`'s module docstring, since
that file is the excerpt's primary consumer).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# The dec-378 executable guard, proven through the real collect() path.
# ---------------------------------------------------------------------------


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


class TestCostCollectorArchives:
    """Every retained archive is read, and a missing position degrades the report visibly."""

    def test_counts_agents_from_every_archive_and_names_a_missing_position(
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
        state = repo / ".ai-state"
        for position in (1, 3):
            row = {**attributed_row, "agent_id": f"archived-{position}"}
            (state / f"observations.jsonl.{position}").write_text(json.dumps(row) + "\n")
        monkeypatch.setattr(
            cost_collector, "_resolve_main_checkout", lambda repo_root: (None, "not needed")
        )

        result = cost_collector.CostCollector(repo_root=str(repo)).collect(
            CollectionContext(repo_root=str(repo), window_days=90, git_sha="deadbeef")
        )

        assert result.data["coverage"]["attributed_rows"] == 3
        assert result.status == "partial"
        assert any(str(state / "observations.jsonl.2") in issue for issue in result.issues)


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
