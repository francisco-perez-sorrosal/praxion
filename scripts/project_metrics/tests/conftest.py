"""Pytest fixtures shared across the project_metrics test suite.

Git-backed test fixtures (``minimal_repo/``, ``empty_repo/``,
``single_author_repo/``, ``coupling_repo/``) are **rebuilt at the start of
each test session** by invoking :mod:`build_fixtures`. Committing nested
``.git/`` directories directly into the Praxion repository is not viable —
git treats them as embedded sub-repositories and silently drops their
contents at clone time. The build-on-demand approach achieves the same
goal (deterministic fixture SHAs pinned by ``GIT_*_DATE`` environment
variables) without fighting git's nested-repo protections.

The session-scoped autouse fixture runs before any test reads a fixture
path, so per-test ``(path / ".git").is_dir()`` guards see the rebuilt
state immediately.

**Cost collector: shared row fixtures** (cross-file: both the read-pass
tests and ``TestCostCollectorFaultInjection`` in the collector-wiring file
consume them):

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

``calibration_log_excerpt_path`` (the ``.ai-state/calibration_log.md``
excerpt fixture) is likewise a conftest citizen rather than living in
``test_cost_collector_aggregate.py`` alone: ``TestCostCollectorProductionWiring``
in ``test_cost_collector_collector.py`` also depends on it, and pytest
fixtures defined in one test module are not visible to a sibling test
module -- only to fixtures declared in ``conftest.py``.
"""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.project_metrics.tests.fixtures import build_fixtures

_FIXTURE_REPOS = (
    "minimal_repo",
    "empty_repo",
    "single_author_repo",
    "coupling_repo",
    "minimal_stdlib_repo",
)


def _fixtures_built(fixtures_dir: Path) -> bool:
    return all((fixtures_dir / name / ".git").is_dir() for name in _FIXTURE_REPOS)


@pytest.fixture(scope="session", autouse=True)
def _rebuild_git_fixtures() -> None:
    """Build the five fixture repos once, however many workers start at once.

    Every pytest-xdist worker runs its own session, so on a cold checkout
    (CI's starting state) several workers reach this fixture together. The
    repos live at fixed paths that 11 test modules read, so the build is
    serialized with an exclusive ``flock`` and re-checked under the lock:
    the first worker builds, the rest wait and then find the repos present.
    Without the lock the workers race inside ``build_all`` and fail with
    ``FileExistsError`` (615 errors measured on 2026-09-27).
    """

    fixtures_dir = Path(build_fixtures.__file__).resolve().parent
    if _fixtures_built(fixtures_dir):
        return
    with open(fixtures_dir / ".build.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not _fixtures_built(fixtures_dir):
            build_fixtures.build_all()


@pytest.fixture(autouse=True)
def _scrub_judge_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Anthropic judge credentials from every test's environment.

    Hermeticity guard: without it, an ambient developer credential (a shell
    export, or a leak from code-under-test writing ``os.environ``) lets
    ``enrich_readiness`` pass its auth gate inside the integration tests and
    POST real judge requests to the Anthropic API mid-suite — slow, billable,
    and order-dependent. Tests that exercise auth explicitly are unaffected:
    their own ``monkeypatch.setenv`` runs after this autouse fixture and wins
    for the test's duration.
    """

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


# ---------------------------------------------------------------------------
# Cost collector: shared row fixtures -- one real JSONL line per file under
# fixtures/cost/. See the module docstring for provenance.
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


@pytest.fixture(scope="session")
def calibration_log_excerpt_path(cost_fixtures_dir: Path) -> Path:
    return cost_fixtures_dir / "calibration_log_excerpt.md"
