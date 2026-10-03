"""Every archive the log keeps is ignored by version control, here and in onboarded projects.

The archives a real rotation writes, listed by the log's owner, never show up
as untracked files: not in a checkout carrying this repository's ignore rules,
and not in a project onboarding set up.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.acceptance.drivers.log_segments import (
    LEGACY_ARCHIVE_NAME,
    listed_archives,
    listed_segments,
    rotate_times,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session
from tests.acceptance.drivers.onboarding import scaffold_new_project, untracked_files
from tests.acceptance.drivers.repository import new_repository

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_ID = "5e551011-0000-4000-8000-0000000e0001"


def _rotate_three_times(tmp_path: Path, project: Path) -> set[str]:
    """Relative paths of every segment and the legacy archive name, after three rotations."""
    state_dir_of(project).mkdir(exist_ok=True)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, project)
    rotate_times(session, state_dir_of(project), 3)
    archives = listed_archives(state_dir_of(project))
    assert len(archives) >= 2, f"three rotations should keep several archives, found {archives}"
    segments = {p.relative_to(project).as_posix() for p in listed_segments(state_dir_of(project))}
    return segments | {f".ai-state/{LEGACY_ARCHIVE_NAME}"}


def test_this_repositorys_ignore_rules_ignore_every_archive_a_rotation_writes(
    tmp_path: Path,
) -> None:
    project = new_repository(tmp_path / "ignore-rules")
    shutil.copyfile(REPO_ROOT / ".gitignore", project / ".gitignore")
    segments = _rotate_three_times(tmp_path, project)

    untracked = set(untracked_files(project))

    assert segments & untracked == set()


def test_a_project_onboarding_sets_up_ignores_every_archive_a_rotation_writes(
    tmp_path: Path,
) -> None:
    project = scaffold_new_project(tmp_path / "onboarding")
    segments = _rotate_three_times(tmp_path, project)

    untracked = set(untracked_files(project))

    assert segments & untracked == set()
