"""Tests for `locate_session` in hooks/_agent_transcript.py -- a top-level session's transcript.

The harness files a session at `<config>/projects/<slug of its cwd>/<session id>.jsonl`; the
slug swaps every character outside `[A-Za-z0-9]` for `-`. Every config directory here is a
`tmp_path`; the default arm is reached by pointing `HOME` at one, never at the real home.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_transcript import CONFIG_DIR_VARIABLE, locate, locate_session  # noqa: E402

SESSION_ID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
OTHER_ID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f1"
PROJECT_CWD = Path("/work/my.repo_x")
PROJECT_SLUG = "-work-my-repo-x"


def put_session(config: Path, project: str, session_id: str = SESSION_ID) -> Path:
    directory = config / "projects" / project
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("{}\n")
    return path


def test_the_transcript_is_found_at_the_path_derived_from_the_working_directory(
    tmp_path: Path,
) -> None:
    written = put_session(tmp_path, PROJECT_SLUG)

    assert locate_session(SESSION_ID, PROJECT_CWD, tmp_path) == written


def test_every_character_outside_letters_and_digits_becomes_a_hyphen_in_the_slug(
    tmp_path: Path,
) -> None:
    put_session(tmp_path, "other-project")
    written = put_session(tmp_path, "-a-b-c-d")

    assert locate_session(SESSION_ID, Path("/a b/c.d"), tmp_path) == written


def test_the_derived_path_wins_over_another_project_holding_the_same_id(tmp_path: Path) -> None:
    put_session(tmp_path, "-aaa-first-by-name")
    derived = put_session(tmp_path, PROJECT_SLUG)

    assert locate_session(SESSION_ID, PROJECT_CWD, tmp_path) == derived


def test_a_slug_that_drifted_is_absorbed_by_the_search_across_projects(tmp_path: Path) -> None:
    found_elsewhere = put_session(tmp_path, "-work-my-repo-x-hashed-1a2b3c")

    assert locate_session(SESSION_ID, PROJECT_CWD, tmp_path) == found_elsewhere


def test_a_symlinked_working_directory_is_resolved_before_the_slug_is_derived(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    config = tmp_path / "config"
    resolved_slug = re.sub(r"[^A-Za-z0-9]", "-", str(real.resolve()))
    written = put_session(config, resolved_slug)
    put_session(config, "-decoy", OTHER_ID)

    assert locate_session(SESSION_ID, link, config) == written


def test_a_session_without_a_transcript_is_none(tmp_path: Path) -> None:
    put_session(tmp_path, PROJECT_SLUG, OTHER_ID)

    assert locate_session(SESSION_ID, PROJECT_CWD, tmp_path) is None


def test_the_config_directory_variable_names_the_directory_searched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = put_session(tmp_path, PROJECT_SLUG)
    monkeypatch.setenv(CONFIG_DIR_VARIABLE, str(tmp_path))

    assert locate_session(SESSION_ID, PROJECT_CWD) == written


def test_without_the_variable_the_dot_claude_directory_of_the_home_is_searched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = put_session(tmp_path / ".claude", PROJECT_SLUG)
    monkeypatch.delenv(CONFIG_DIR_VARIABLE, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert locate_session(SESSION_ID, PROJECT_CWD) == written


def test_two_sessions_in_one_project_are_never_confused(tmp_path: Path) -> None:
    first = put_session(tmp_path, PROJECT_SLUG, SESSION_ID)
    second = put_session(tmp_path, PROJECT_SLUG, OTHER_ID)

    found = (
        locate_session(SESSION_ID, PROJECT_CWD, tmp_path),
        locate_session(OTHER_ID, PROJECT_CWD, tmp_path),
    )

    assert found == (first, second)


@pytest.mark.parametrize("session_id", ["*", "../" + SESSION_ID, "", "a/b", SESSION_ID[:-1]])
def test_a_string_that_is_not_the_id_of_a_stored_session_finds_nothing(
    tmp_path: Path, session_id: str
) -> None:
    put_session(tmp_path, PROJECT_SLUG)

    assert locate_session(session_id, PROJECT_CWD, tmp_path) is None


def test_a_subagent_lookup_does_not_find_a_session_file(tmp_path: Path) -> None:
    put_session(tmp_path, PROJECT_SLUG)

    assert locate(SESSION_ID, config=tmp_path) is None
