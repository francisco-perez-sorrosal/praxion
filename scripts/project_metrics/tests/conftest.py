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
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.project_metrics.tests.fixtures import build_fixtures


@pytest.fixture(scope="session", autouse=True)
def _rebuild_git_fixtures() -> None:
    """Build the four fixture repos once per test session.

    Idempotent: each repo directory is removed and reinitialized, so stale
    state from a prior run cannot leak into the current session. Scoped to
    ``session`` because building all four repos takes <1s and the contents
    never vary within a run.
    """

    fixtures_dir = Path(build_fixtures.__file__).resolve().parent
    minimal = fixtures_dir / "minimal_repo"
    # Quick short-circuit if all five already exist from a prior invocation
    # in the same directory (e.g., developer ran build_fixtures.py manually
    # before running pytest). Re-running is safe but wastes ~0.5s.
    if (
        minimal.joinpath(".git").is_dir()
        and (fixtures_dir / "empty_repo" / ".git").is_dir()
        and (fixtures_dir / "single_author_repo" / ".git").is_dir()
        and (fixtures_dir / "coupling_repo" / ".git").is_dir()
        and (fixtures_dir / "minimal_stdlib_repo" / ".git").is_dir()
    ):
        return
    build_fixtures.build_all()
