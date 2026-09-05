"""Behavioral test for the `partially-managed` detection predicate.

RED-first (BDD/TDD): `scripts/onboard-project`'s `detect_state()`
currently greps only `CLAUDE.md` for `^## Agent Pipeline$` (state 4 in
`skills/onboard-project/references/detection.md`'s 6-state table). A
sidecar-placed, team-owned project keeps its Praxion blocks in
`CLAUDE.local.md` (the `untouched` case) and never writes to the tracked
`CLAUDE.md` at all — so today's predicate misclassifies such a project as
`git-no-praxion` (state 5) instead of `partially-managed` (state 4), and a
re-run would try to onboard it from scratch rather than recognizing it.

This drives `scripts/onboard-project` as a real subprocess against a scratch
git repository — mirroring `tests/consumer_layout/contract.py`'s isolated-git
pattern and `scripts/test_onboard_project_placement.py`'s sandbox pattern —
so the assertion is that the *mechanical* predicate implementation agrees
with the prose, not merely that the prose says the right thing (that half is
covered separately in `tests/commands/test_onboard_placement_phase_matrix.py`
::test_detection_partially_managed_predicate_names_claude_local_md).

Concurrency note: `scripts/onboard-project` is being edited concurrently by
the paired implementer step. This test is expected to stay RED until that
fix lands; it is read-only with respect to that script (invoked via
subprocess, never edited here).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_UNDER_TEST = REPO_ROOT / "scripts" / "onboard-project"

# Same isolation `tests/consumer_layout/contract.py` and
# `scripts/test_onboard_project_placement.py` use: a developer with a
# merge driver or user.name registered at global scope must not change what
# this test observes.
_ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, **_ISOLATED_GIT_ENV},
    )


def _team_owned_sidecar_project(root: Path) -> Path:
    """A project whose Praxion blocks live in `CLAUDE.local.md` (the
    `untouched` case): a tracked `CLAUDE.md` the team wrote, no `CLAUDE.md`
    Agent Pipeline marker, and the marker only in the untracked
    `CLAUDE.local.md` sidecar-placement writes to instead. No `.ai-state/`
    and no chained finalize hook either, so every earlier state-4 disjunct
    is deliberately absent -- only the CLAUDE.local.md clause can save this
    fixture from misclassifying as state 5 (`git-no-praxion`)."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "CLAUDE.md").write_text("# Team notes\n\nThis is our own file.\n", encoding="utf-8")
    (root / "CLAUDE.local.md").write_text(
        "## Agent Pipeline\n\nThis project follows Praxion's tier-driven agent pipeline.\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("placeholder\n", encoding="utf-8")
    _git(root, "add", "CLAUDE.md", "README.md")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def run_onboard_check(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_UNDER_TEST), "--check", "--json"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, **_ISOLATED_GIT_ENV},
    )


@pytest.mark.skipif(not SCRIPT_UNDER_TEST.exists(), reason="scripts/onboard-project not found")
def test_a_claude_local_md_only_project_is_classified_partially_managed(tmp_path: Path) -> None:
    """`detect_state()` must consult `CLAUDE.local.md` as well as
    `CLAUDE.md` for the Agent Pipeline marker, so a sidecar-placed,
    team-owned project (blocks shadowed in CLAUDE.local.md, tracked
    CLAUDE.md left untouched) is recognized as `partially-managed` rather
    than read as an ordinary git repo Praxion has never touched."""
    project = _team_owned_sidecar_project(tmp_path / "project")

    result = run_onboard_check(project)

    assert '"state":"partially-managed"' in result.stdout, (
        "detect_state() did not classify a CLAUDE.local.md-only project as "
        f"partially-managed. stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.skipif(not SCRIPT_UNDER_TEST.exists(), reason="scripts/onboard-project not found")
def test_a_plain_git_repo_with_neither_claude_file_is_not_partially_managed(
    tmp_path: Path,
) -> None:
    """Negative control for the fix above: a repo carrying no Agent Pipeline
    marker anywhere must NOT be swept into partially-managed by a
    broadened predicate -- it should still resolve to git-no-praxion."""
    project = tmp_path / "project"
    project.mkdir(parents=True)
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "Test")
    (project / "README.md").write_text("placeholder\n", encoding="utf-8")
    _git(project, "add", "README.md")
    _git(project, "commit", "-q", "-m", "seed")

    result = run_onboard_check(project)

    assert '"state":"git-no-praxion"' in result.stdout, (
        "a plain git repo with no Agent Pipeline marker anywhere must "
        f"resolve to git-no-praxion, not be swept into partially-managed. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
