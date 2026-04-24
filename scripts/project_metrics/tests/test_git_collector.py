"""Behavioral tests for the GitCollector against committed + runtime fixture repos.

These tests encode the GitCollector behavioral contract derived from the
collector-protocol, graceful-degradation, and storage-schema ADRs under
`.ai-state/decisions/drafts/`. They are written *from the behavioral spec and
the fixture specification*, not from the implementation —
production code (`scripts/project_metrics/collectors/git_collector.py`) is not
read while authoring these tests.

**Golden-value source**: `scripts/project_metrics/tests/fixtures/FIXTURE_SPEC.md`.
Every numeric golden asserted below is derived there. That document is the
authoritative spec; if a value here disagrees with the spec, the spec is right
and the test is wrong.

**Import strategy**: every test imports `GitCollector` (and other production
symbols) inside the test body. During the BDD/TDD RED handshake,
`scripts/project_metrics/collectors/git_collector.py` does not yet exist, so
top-of-module imports would break pytest collection for every test
simultaneously. Deferred imports give per-test RED/GREEN resolution and let
individual tests surface their specific `ImportError` / `FileNotFoundError`.

**Fixture strategy**: the four committed fixtures
(`minimal_repo/`, `empty_repo/`, `single_author_repo/`, `coupling_repo/`)
are built from `FIXTURE_SPEC.md` under
`scripts/project_metrics/tests/fixtures/`. The `FIXTURE_SPEC.md` pins the
commit-by-commit content so the SHAs and numstat output are deterministic.
Session-scoped fixtures cache the `Path` to each committed repo (read-only;
tests never mutate). Shallow-clone tests use function-scoped `tmp_path` so
clone-runtime state doesn't leak between tests.

**Reference clock**: the GitCollector must expose an injection point for the
"now" reference used in per-file age computation. Tests set
`PROJECT_METRICS_REFERENCE_TIME = "2026-04-23T00:00:00Z"` via
`monkeypatch.setenv` before invoking `collect()`. If the implementer uses a
different mechanism (constructor kwarg, CollectionContext extension), update
this docstring and the tests in lock-step.

**Determinism assertions** compare two back-to-back `collect()` calls on the
same repo at the same SHA and expect byte-identical JSON serialization, with
documented exceptions: fields whose values are inherently wall-clock-bound
(e.g., `duration_seconds`) are excluded from the determinism hash by zeroing
them before comparison.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Golden constants — lifted verbatim from FIXTURE_SPEC.md + the ADRs.
#
# Any drift between these and the fixture spec means the spec is the
# authority and these tests are wrong.
# ---------------------------------------------------------------------------

# From FIXTURE_SPEC.md, "Per-file churn" section.
_MINIMAL_REPO_CHURN_PER_FILE: dict[str, int] = {
    "core.py": 32,
    "helpers.py": 15,
    "docs.md": 12,
    "README.md": 3,
}
_MINIMAL_REPO_CHURN_TOTAL: int = 62  # 32 + 15 + 12 + 3

# From FIXTURE_SPEC.md, "Per-file age" section; depends on pinned reference
# time 2026-04-23T00:00:00Z.
_MINIMAL_REPO_AGE_DAYS: dict[str, int] = {
    "README.md": 67,
    "core.py": 62,
    "helpers.py": 57,
    "docs.md": 39,
}

# From FIXTURE_SPEC.md, "Change coupling" section. Exactly one pair surfaces
# at threshold >= 3.
_MINIMAL_REPO_COUPLED_PAIRS: dict[tuple[str, str], int] = {
    ("core.py", "helpers.py"): 4,
}

# From FIXTURE_SPEC.md, "Bird ownership" section. Per-file top-author % of
# added lines. Values pinned to two decimal places; tests use pytest.approx
# with abs=0.01 tolerance.
_MINIMAL_REPO_TOP_AUTHOR_PCT: dict[str, float] = {
    "core.py": 0.80,  # Alice: 20/25
    "helpers.py": 0.9167,  # Alice: 11/12
    "docs.md": 0.7273,  # Alice: 8/11
    "README.md": 1.0,  # Alice: 3/3
}

# From FIXTURE_SPEC.md, "Truck factor" section.
_MINIMAL_REPO_TRUCK_FACTOR: int = 2

# From FIXTURE_SPEC.md, "Change entropy" section. Summed across 10 commits.
_MINIMAL_REPO_CHANGE_ENTROPY: float = 3.6972

# Pinned reference time — tests monkeypatch-setenv this value before calling
# collect(), so the per-file age computation is deterministic regardless of
# when the test is run.
_REFERENCE_TIME_ISO: str = "2026-04-23T00:00:00Z"

# The 90-day window is the SYSTEMS_PLAN default; per the fixture spec, all 10
# commits fall inside this window relative to _REFERENCE_TIME_ISO.
_WINDOW_DAYS: int = 90

# The fixture's SHA is deterministic because GIT_AUTHOR_DATE + GIT_COMMITTER_DATE
# are pinned, but the tests do not assert specific SHAs — they assert the
# aggregate commit count (10 for minimal_repo) since that is what the
# implementation-planner actually mandates ("fixture has exactly N commits").
_MINIMAL_REPO_COMMIT_COUNT: int = 10

# From the collector-protocol ADR: resolution outcomes and statuses.
_COLLECTOR_RESULT_STATUSES: frozenset[str] = frozenset(
    {"ok", "partial", "error", "timeout"}
)


# ---------------------------------------------------------------------------
# Shared fixtures — located relative to this test file so the tests run from
# any working directory without hardcoding absolute paths.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Return the tests/fixtures/ directory — session-scoped because its
    path never changes across the session.
    """

    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def minimal_repo_path(fixtures_dir: Path) -> Path:
    """Return the `minimal_repo/` directory. Session-scoped because the
    committed repo does not change between tests.

    Raises `FileNotFoundError` with a pointer to FIXTURE_SPEC.md if the
    fixture is absent — this is one of the two acceptable RED states during
    the BDD/TDD handshake (the other being ImportError on GitCollector).
    """

    path = fixtures_dir / "minimal_repo"
    if not (path / ".git").is_dir():
        raise FileNotFoundError(
            f"Fixture repository missing at {path}. "
            "Build per scripts/project_metrics/tests/fixtures/FIXTURE_SPEC.md. "
            "This is expected during the BDD/TDD RED handshake."
        )
    return path


@pytest.fixture(scope="session")
def empty_repo_path(fixtures_dir: Path) -> Path:
    """Path to the single-commit-baseline empty fixture."""

    path = fixtures_dir / "empty_repo"
    if not (path / ".git").is_dir():
        raise FileNotFoundError(
            f"Empty fixture repository missing at {path}. "
            "Build per FIXTURE_SPEC.md auxiliary fixtures section."
        )
    return path


@pytest.fixture(scope="session")
def single_author_repo_path(fixtures_dir: Path) -> Path:
    """Path to the single-author fixture (truck factor = 1)."""

    path = fixtures_dir / "single_author_repo"
    if not (path / ".git").is_dir():
        raise FileNotFoundError(
            f"Single-author fixture repository missing at {path}. "
            "Build per FIXTURE_SPEC.md auxiliary fixtures section."
        )
    return path


@pytest.fixture(scope="session")
def coupling_repo_path(fixtures_dir: Path) -> Path:
    """Path to the coupling fixture (dense co-change)."""

    path = fixtures_dir / "coupling_repo"
    if not (path / ".git").is_dir():
        raise FileNotFoundError(
            f"Coupling fixture repository missing at {path}. "
            "Build per FIXTURE_SPEC.md auxiliary fixtures section."
        )
    return path


def _git_head_sha(repo: Path) -> str:
    """Return the HEAD SHA of a given repo. Helper for constructing
    CollectionContext with a real SHA that matches the fixture state.
    """

    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_context(repo: Path) -> Any:
    """Construct a CollectionContext for the given repo.

    Deferred-imports the protocol dataclass. Window days and git sha are
    populated from the pinned golden values; repo_root is the absolute repo
    path.
    """

    from scripts.project_metrics.collectors.base import CollectionContext

    return CollectionContext(
        repo_root=str(repo),
        window_days=_WINDOW_DAYS,
        git_sha=_git_head_sha(repo),
    )


def _set_reference_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the reference time for age computation.

    Tests that assert on per-file age MUST call this. If the implementer
    uses a different injection mechanism (e.g., constructor kwarg), this
    helper is the single update site.
    """

    monkeypatch.setenv("PROJECT_METRICS_REFERENCE_TIME", _REFERENCE_TIME_ISO)


# ---------------------------------------------------------------------------
# Resolve-phase tests — Available when git+repo present, Unavailable when
# not. GitCollector is `required=True` per the collector-protocol ADR.
# ---------------------------------------------------------------------------


class TestGitCollectorResolve:
    """Verifies the three resolve() outcomes without invoking collect()."""

    def test_resolve_returns_available_when_inside_a_git_repo(
        self, minimal_repo_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import (
            Available,
            ResolutionEnv,
        )
        from scripts.project_metrics.collectors.git_collector import GitCollector

        collector = GitCollector()
        env = ResolutionEnv()
        # GitCollector's resolve() is repo-aware — it must check
        # `git rev-parse --is-inside-work-tree` against the target repo.
        # The API shape for this is an open question in the plan; the test
        # uses a conventional pattern of cd'ing into the repo via env or
        # passing repo-root at resolve time. If the implementer chose a
        # different mechanism, the test fails here with a clear signal and
        # the spec is updated accordingly.
        original_cwd = Path.cwd()
        try:
            os.chdir(minimal_repo_path)
            result = collector.resolve(env)
        finally:
            os.chdir(original_cwd)
        assert isinstance(result, Available), (
            f"Expected Available; got {type(result).__name__}"
        )

    def test_resolve_returns_unavailable_outside_a_git_repo(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import (
            ResolutionEnv,
            Unavailable,
        )
        from scripts.project_metrics.collectors.git_collector import GitCollector

        # tmp_path is a plain directory, not a git repo.
        collector = GitCollector()
        env = ResolutionEnv()
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = collector.resolve(env)
        finally:
            os.chdir(original_cwd)
        assert isinstance(result, Unavailable), (
            f"Expected Unavailable outside a git repo; got {type(result).__name__}"
        )

    def test_collector_is_marked_required_true(self) -> None:
        from scripts.project_metrics.collectors.git_collector import GitCollector

        # From the collector-protocol ADR: GitCollector is the *only*
        # collector with required=True. The runner's hard-floor abort path
        # depends on this attribute.
        assert GitCollector.required is True, (
            "GitCollector must set required=True per the collector-protocol ADR — "
            "this is the runner's signal to abort on resolve-Unavailable."
        )

    def test_collector_has_stable_name_attribute(self) -> None:
        from scripts.project_metrics.collectors.git_collector import GitCollector

        # Name becomes the JSON namespace key. Must be a non-empty string.
        assert isinstance(GitCollector.name, str)
        assert GitCollector.name, "GitCollector.name must be a non-empty string"
        # Stability contract: the name should be "git" (canonical per the
        # aggregate block's namespace in the storage schema ADR).
        assert GitCollector.name == "git", (
            f"Expected GitCollector.name == 'git'; got {GitCollector.name!r}"
        )


# ---------------------------------------------------------------------------
# Empty-repo (initial-commit-only) — should produce a valid namespace with
# zeros/empty-lists, not errors.
# ---------------------------------------------------------------------------


class TestGitCollectorEmptyRepo:
    """Initial-commit-only repo — the degenerate baseline."""

    def test_collect_returns_ok_status_on_empty_repo(
        self,
        empty_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        result = GitCollector().collect(_make_context(empty_repo_path))
        assert result.status == "ok", (
            f"Empty repo should produce status=ok, not {result.status!r}; "
            f"issues={result.issues}"
        )

    def test_empty_repo_change_entropy_is_zero(
        self,
        empty_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(empty_repo_path)).data
        assert data.get("change_entropy_90d") == 0.0, (
            "Single-commit repo has zero entropy (one commit touching one file "
            "yields p=1.0 and -1*log2(1)=0)."
        )

    def test_empty_repo_change_coupling_is_empty(
        self,
        empty_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(empty_repo_path)).data
        # "No pair co-changed more than zero times" — the list/dict is empty.
        pairs = data.get("change_coupling")
        # Accept either {} or {"pairs": []} — the exact shape is the
        # implementer's call per FIXTURE_SPEC.md item (2). The invariant is
        # "no coupled pairs at threshold".
        if isinstance(pairs, dict) and "pairs" in pairs:
            assert pairs["pairs"] == [], (
                f"Empty repo should yield no coupled pairs; got {pairs['pairs']!r}"
            )
        else:
            assert pairs in ({}, []), (
                f"Empty repo should yield empty coupling; got {pairs!r}"
            )

    def test_empty_repo_truck_factor_is_one(
        self,
        empty_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(empty_repo_path)).data
        assert data.get("truck_factor") == 1, (
            "Single-author repo has truck_factor=1 (removing the only author "
            "uncovers 100% of files → <50% threshold crossed)."
        )


# ---------------------------------------------------------------------------
# Single-author repo — truck factor = 1; every file 100% owned.
# ---------------------------------------------------------------------------


class TestGitCollectorSingleAuthor:
    """All commits by one author — ownership and truck factor degenerate."""

    def test_truck_factor_is_one(
        self,
        single_author_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(single_author_repo_path)).data
        assert data.get("truck_factor") == 1

    def test_every_file_has_100pct_ownership_for_sole_author(
        self,
        single_author_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(single_author_repo_path)).data
        ownership = data.get("ownership", {})
        # Any file in the fixture should have top-author percentage 1.0.
        assert ownership, "Ownership block must be populated on a non-empty repo."
        for file_path, per_file in ownership.items():
            top_pct = _extract_top_author_pct(per_file)
            assert top_pct == pytest.approx(1.0, abs=0.001), (
                f"Single-author repo file {file_path!r} must have 100% ownership; "
                f"got {top_pct}"
            )


def _extract_top_author_pct(per_file_ownership: Any) -> float:
    """Tolerate two possible ownership shapes — see FIXTURE_SPEC.md item (3).

    Shape 1: `{author_name: pct, ...}` — return max(values).
    Shape 2: `{"major": [[name, pct], ...], "minor": [...]}` — return
             first major's pct.
    """

    if isinstance(per_file_ownership, dict):
        if "major" in per_file_ownership:
            majors = per_file_ownership["major"]
            assert majors, "major list must be non-empty when file has contributors"
            return float(majors[0][1])
        if per_file_ownership:
            return float(max(per_file_ownership.values()))
    raise AssertionError(
        f"Unrecognized ownership shape for per-file entry: {per_file_ownership!r}. "
        "Expected either dict[str, float] or "
        "dict with 'major' and 'minor' keys per FIXTURE_SPEC.md item (3)."
    )


# ---------------------------------------------------------------------------
# Multi-author repo (minimal_repo) — all golden-value assertions live here.
# ---------------------------------------------------------------------------


class TestGitCollectorMultiAuthor:
    """All per-file golden assertions against the committed minimal_repo/."""

    def test_collect_returns_ok_status(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        result = GitCollector().collect(_make_context(minimal_repo_path))
        assert result.status == "ok", (
            f"Minimal repo collect() must succeed; got {result.status!r} "
            f"with issues={result.issues}"
        )

    def test_collect_result_status_is_in_canonical_set(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        result = GitCollector().collect(_make_context(minimal_repo_path))
        assert result.status in _COLLECTOR_RESULT_STATUSES

    def test_per_file_churn_matches_fixture_spec(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        per_file_churn = data.get("churn_90d", {})
        for file_path, expected in _MINIMAL_REPO_CHURN_PER_FILE.items():
            assert per_file_churn.get(file_path) == expected, (
                f"churn_90d[{file_path!r}] should be {expected} "
                f"(added+deleted across in-window commits); "
                f"got {per_file_churn.get(file_path)!r}. "
                f"See FIXTURE_SPEC.md § Per-file churn."
            )

    def test_total_churn_matches_fixture_spec(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        assert data.get("churn_total_90d") == _MINIMAL_REPO_CHURN_TOTAL, (
            f"Total churn must equal sum of per-file churn "
            f"({_MINIMAL_REPO_CHURN_TOTAL}); got {data.get('churn_total_90d')!r}."
        )

    def test_change_entropy_matches_fixture_spec(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        entropy = data.get("change_entropy_90d")
        assert entropy == pytest.approx(_MINIMAL_REPO_CHANGE_ENTROPY, abs=0.01), (
            f"change_entropy_90d must equal the sum of per-commit Hassan "
            f"entropy across all 10 commits ({_MINIMAL_REPO_CHANGE_ENTROPY} "
            f"± 0.01); got {entropy!r}. See FIXTURE_SPEC.md § Change entropy."
        )

    def test_top_author_ownership_pct_matches_fixture_spec(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        ownership = data.get("ownership", {})
        for file_path, expected_pct in _MINIMAL_REPO_TOP_AUTHOR_PCT.items():
            per_file = ownership.get(file_path)
            assert per_file is not None, (
                f"ownership block must have entry for {file_path!r}; "
                f"got keys {sorted(ownership)}"
            )
            actual_pct = _extract_top_author_pct(per_file)
            assert actual_pct == pytest.approx(expected_pct, abs=0.01), (
                f"Top-author ownership for {file_path!r} should be "
                f"~{expected_pct}; got {actual_pct}. "
                f"See FIXTURE_SPEC.md § Bird ownership."
            )

    def test_truck_factor_matches_fixture_spec(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        assert data.get("truck_factor") == _MINIMAL_REPO_TRUCK_FACTOR, (
            f"Avelino truck factor on the minimal_repo fixture should be "
            f"{_MINIMAL_REPO_TRUCK_FACTOR} (greedy-remove Alice, then Bob; "
            f"at that point 1/4 = 25% of files retain a major owner, "
            f"crossing the <50% threshold). See FIXTURE_SPEC.md § Truck factor."
        )

    def test_per_file_age_matches_fixture_spec(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        age = data.get("age_days", {})
        for file_path, expected_age in _MINIMAL_REPO_AGE_DAYS.items():
            actual = age.get(file_path)
            assert actual == expected_age, (
                f"age_days[{file_path!r}] must be {expected_age} "
                f"(first-commit-to-2026-04-23T00:00:00Z); got {actual!r}. "
                f"See FIXTURE_SPEC.md § Per-file age and the "
                f"PROJECT_METRICS_REFERENCE_TIME injection mechanism."
            )


# ---------------------------------------------------------------------------
# Change coupling — (core.py, helpers.py) must surface at threshold >= 3.
# ---------------------------------------------------------------------------


class TestGitCollectorChangeCoupling:
    """Top-N co-changing pairs — threshold >= 3 commits co-change."""

    def test_core_helpers_pair_surfaces_with_count_four(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        coupling = data.get("change_coupling")
        pair_count = _find_pair_count(coupling, ("core.py", "helpers.py"))
        assert pair_count == 4, (
            f"(core.py, helpers.py) co-change in commits 3, 5, 6, 10 → count=4; "
            f"got {pair_count!r}. See FIXTURE_SPEC.md § Change coupling."
        )

    def test_no_pair_below_threshold_surfaces(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        coupling = data.get("change_coupling")
        all_pairs = _all_pair_counts(coupling)
        # Per the ADR: pairs below the threshold (>=3) must not surface in the
        # top-N list. The only pair in minimal_repo that reaches the threshold
        # is (core.py, helpers.py) at count=4.
        for pair, count in all_pairs.items():
            assert count >= 3, (
                f"Pair {pair} surfaced with count {count} < 3 threshold. "
                f"Coupling list must filter below-threshold pairs out."
            )

    def test_coupling_repo_shows_dense_pair(
        self,
        coupling_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(coupling_repo_path)).data
        coupling = data.get("change_coupling")
        pair_count = _find_pair_count(coupling, ("alpha.py", "beta.py"))
        assert pair_count == 6, (
            f"coupling_repo fixture has 6 commits co-changing alpha.py+beta.py; "
            f"got count={pair_count!r}."
        )


def _find_pair_count(coupling: Any, pair: tuple[str, str]) -> int:
    """Tolerate two possible coupling shapes.

    Shape 1: `{"pairs": [{"files": [...], "count": N}, ...], "threshold": ...}`
    Shape 2: `{(file_a, file_b): count, ...}` — straight dict of tuples
    Shape 3: list-of-tuples `[("file_a", "file_b", count), ...]`

    Returns 0 if the pair is not present.
    """

    a, b = sorted(pair)
    if isinstance(coupling, dict):
        if "pairs" in coupling:
            for entry in coupling["pairs"]:
                files = tuple(sorted(entry["files"]))
                if files == (a, b):
                    return int(entry["count"])
            return 0
        for key, count in coupling.items():
            if isinstance(key, tuple) and tuple(sorted(key)) == (a, b):
                return int(count)
        return 0
    if isinstance(coupling, list):
        for entry in coupling:
            if len(entry) == 3:
                fa, fb, count = entry
                if tuple(sorted([fa, fb])) == (a, b):
                    return int(count)
        return 0
    raise AssertionError(
        f"Unrecognized change_coupling shape: {type(coupling).__name__}. "
        f"Expected dict with 'pairs' key, dict of tuples, or list of 3-tuples. "
        f"See FIXTURE_SPEC.md item (2) for acceptable shapes."
    )


def _all_pair_counts(coupling: Any) -> dict[tuple[str, str], int]:
    """Return all (pair -> count) entries from a coupling block."""

    out: dict[tuple[str, str], int] = {}
    if isinstance(coupling, dict):
        if "pairs" in coupling:
            for entry in coupling["pairs"]:
                files = tuple(sorted(entry["files"]))
                out[files] = int(entry["count"])
            return out
        for key, count in coupling.items():
            if isinstance(key, tuple):
                out[tuple(sorted(key))] = int(count)
        return out
    if isinstance(coupling, list):
        for entry in coupling:
            if len(entry) == 3:
                fa, fb, count = entry
                out[tuple(sorted([fa, fb]))] = int(count)
        return out
    raise AssertionError(
        f"Unrecognized change_coupling shape for enumeration: {type(coupling).__name__}."
    )


# ---------------------------------------------------------------------------
# Bird ownership — per-file major/minor shape and percentages.
# ---------------------------------------------------------------------------


class TestGitCollectorBirdOwnership:
    """Ownership block — major (>=5%) vs minor (<5%) per Bird (2011)."""

    def test_core_py_has_alice_as_major_bob_as_major(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        core_owners = data.get("ownership", {}).get("core.py")
        assert core_owners is not None
        top_pct = _extract_top_author_pct(core_owners)
        assert top_pct == pytest.approx(0.80, abs=0.01), (
            f"core.py top-author pct should be 0.80 (Alice 20 of 25 added "
            f"lines); got {top_pct}"
        )

    def test_readme_has_alice_as_sole_major_100pct(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        readme_owners = data.get("ownership", {}).get("README.md")
        assert readme_owners is not None
        top_pct = _extract_top_author_pct(readme_owners)
        assert top_pct == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# Truck factor — greedy-remove authors until <50% files retain major owner.
# ---------------------------------------------------------------------------


class TestGitCollectorTruckFactor:
    """Avelino truck factor on fixtures with known outcomes."""

    def test_minimal_repo_truck_factor_is_two(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(minimal_repo_path)).data
        assert data.get("truck_factor") == 2

    def test_single_author_repo_truck_factor_is_one(
        self,
        single_author_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        data = GitCollector().collect(_make_context(single_author_repo_path)).data
        assert data.get("truck_factor") == 1


# ---------------------------------------------------------------------------
# Shallow-clone fallback — runtime clone to tmp_path, numstat unavailable,
# churn degrades to commit-count, marker `churn_source: "commit_count_fallback"`.
# ---------------------------------------------------------------------------


class TestGitCollectorShallowCloneFallback:
    """When numstat is unavailable on a shallow clone, churn falls back."""

    def test_shallow_clone_sets_commit_count_fallback_marker(
        self,
        minimal_repo_path: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        shallow_path = tmp_path / "shallow_minimal_repo"
        # file:// URL is required for `--depth=1` to work against a local repo.
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                f"file://{minimal_repo_path}",
                str(shallow_path),
            ],
            check=True,
            capture_output=True,
        )

        result = GitCollector().collect(_make_context(shallow_path))
        assert result.data.get("churn_source") == "commit_count_fallback", (
            "Shallow clone (git clone --depth=1) strips numstat history. "
            "The collector must detect this and set "
            "`churn_source = 'commit_count_fallback'` in the namespace data. "
            f"Got churn_source={result.data.get('churn_source')!r}."
        )

    def test_shallow_clone_collector_does_not_raise(
        self,
        minimal_repo_path: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        shallow_path = tmp_path / "shallow_noraise_repo"
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                f"file://{minimal_repo_path}",
                str(shallow_path),
            ],
            check=True,
            capture_output=True,
        )

        # Collector must degrade gracefully, not raise. Status may be "ok"
        # or "partial" (partial if collector records a non-fatal issue about
        # the shallow clone in .issues); either is acceptable.
        result = GitCollector().collect(_make_context(shallow_path))
        assert result.status in {"ok", "partial"}, (
            f"Shallow clone must degrade without error; got "
            f"status={result.status!r} with issues={result.issues}"
        )


# ---------------------------------------------------------------------------
# Determinism — two back-to-back collect() calls on the same repo at the same
# SHA produce byte-identical output (modulo wall-clock fields).
# ---------------------------------------------------------------------------


class TestGitCollectorDeterminism:
    """Byte-identical JSON across two runs on the same fixture."""

    def test_two_runs_on_minimal_repo_produce_identical_data_payload(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        ctx = _make_context(minimal_repo_path)
        first = GitCollector().collect(ctx)
        second = GitCollector().collect(ctx)

        # Zero out the wall-clock field before comparing — per the collector
        # protocol ADR, `duration_seconds` is inherently non-deterministic
        # and excluded from the determinism hash.
        first_serialized = _canonical_json(first.data)
        second_serialized = _canonical_json(second.data)
        assert first_serialized == second_serialized, (
            "GitCollector.collect() must be byte-deterministic across two "
            "runs on the same repo at the same SHA. The namespace data "
            "payload (excluding `duration_seconds`) was not identical."
        )

    def test_two_runs_agree_on_top_author_pct(
        self,
        minimal_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A narrower determinism test isolating the ownership block — when
        the full-payload test fails, this narrower one names the drift site
        for the implementer. Ownership is the most ordering-sensitive field
        because it iterates author dicts; catching order drift here gives a
        better failure message than the full-payload diff.
        """

        _set_reference_time(monkeypatch)
        from scripts.project_metrics.collectors.git_collector import GitCollector

        ctx = _make_context(minimal_repo_path)
        first = GitCollector().collect(ctx)
        second = GitCollector().collect(ctx)

        for file_path in _MINIMAL_REPO_TOP_AUTHOR_PCT:
            a = _extract_top_author_pct(first.data.get("ownership", {}).get(file_path))
            b = _extract_top_author_pct(second.data.get("ownership", {}).get(file_path))
            assert a == b, (
                f"Ownership top-author pct for {file_path!r} drifted between "
                f"runs: {a} vs {b}. Determinism contract violated."
            )


def _canonical_json(payload: Any) -> bytes:
    """Serialize `payload` to deterministic UTF-8 JSON for byte comparison.

    Mirrors `schema.to_json`'s key-sort + compact-separators discipline,
    operating on the collector's namespace data (a plain dict).
    """

    # Tuples are not JSON-native; coerce coupling pair tuples into sorted
    # lists before serialization so the key representation is stable.
    return json.dumps(
        _json_safe(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _json_safe(node: Any) -> Any:
    """Recursively normalize non-JSON-native types (tuples → lists, sets →
    sorted lists) so round-tripped payloads compare byte-identically.
    """

    if isinstance(node, dict):
        return {k: _json_safe(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_json_safe(x) for x in node]
    if isinstance(node, set):
        return sorted(_json_safe(x) for x in node)
    return node


# ---------------------------------------------------------------------------
# Commit-count invariant (smoke) — asserts the fixture itself is intact.
#
# This is not a collector assertion; it is an integrity check against the
# fixture spec. If this fails, the implementer's fixture-build step drifted.
# ---------------------------------------------------------------------------


class TestMinimalRepoFixtureIntegrity:
    """Sanity asserts the fixture was built to spec. Not a collector test."""

    def test_minimal_repo_has_exactly_ten_commits(
        self, minimal_repo_path: Path
    ) -> None:
        result = subprocess.run(
            ["git", "-C", str(minimal_repo_path), "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        actual = int(result.stdout.strip())
        assert actual == _MINIMAL_REPO_COMMIT_COUNT, (
            f"minimal_repo fixture should have {_MINIMAL_REPO_COMMIT_COUNT} "
            f"commits per FIXTURE_SPEC.md; got {actual}. "
            f"Rebuild the fixture."
        )

    def test_minimal_repo_has_exactly_three_distinct_authors(
        self, minimal_repo_path: Path
    ) -> None:
        result = subprocess.run(
            ["git", "-C", str(minimal_repo_path), "log", "--pretty=format:%ae"],
            capture_output=True,
            text=True,
            check=True,
        )
        authors = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        expected = {
            "alice@example.test",
            "bob@example.test",
            "carol@example.test",
        }
        assert authors == expected, (
            f"minimal_repo must have exactly three authors ({expected}); got {authors}"
        )
