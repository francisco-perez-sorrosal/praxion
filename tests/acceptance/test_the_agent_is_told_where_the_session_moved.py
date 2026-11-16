"""After a Bash call leaves the session elsewhere, the agent is told where it now is.

A call whose command changes directory and leaves the session outside the project root
yields one line naming the directory the session is now in and the project root, at the
latest before the agent's next call runs. A call that comes home, a call that moves
nothing, and a payload the hook cannot read add nothing and exit cleanly.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.bash_hooks import HookCall, moved, run_session

ANSWERS = {"payload-shows-the-move": True, "payload-shows-the-old-directory": False}


def _places(tmp_path):
    project = (tmp_path / "project").resolve()
    elsewhere = (tmp_path / "elsewhere").resolve()
    project.mkdir()
    elsewhere.mkdir()
    return project, elsewhere


def _lines_naming(contexts: list[str], *names: str) -> list[str]:
    return [line for c in contexts for line in c.splitlines() if all(n in line for n in names)]


@pytest.mark.parametrize("answer", list(ANSWERS))
def test_a_move_outside_the_project_names_the_new_directory_and_the_root_in_one_line(
    tmp_path, answer
):
    project, elsewhere = _places(tmp_path)
    calls = moved(project, f"cd {elsewhere} && ls", elsewhere, payload_shows_move=ANSWERS[answer])

    run = run_session(tmp_path, project, calls)

    assert _lines_naming(run.contexts, str(elsewhere), str(project)), run.contexts


@pytest.mark.parametrize("answer", list(ANSWERS))
def test_a_move_into_a_subdirectory_names_the_new_directory(tmp_path, answer):
    project, _ = _places(tmp_path)
    inner = project / "src"
    inner.mkdir()
    calls = moved(project, "cd src", inner, payload_shows_move=ANSWERS[answer])

    run = run_session(tmp_path, project, calls)

    assert _lines_naming(run.contexts, str(inner)), run.contexts


def test_a_call_that_comes_back_to_the_root_adds_nothing(tmp_path):
    project, elsewhere = _places(tmp_path)
    calls = moved(project, f"cd {elsewhere} && cd {project}", project, payload_shows_move=True)

    run = run_session(tmp_path, project, calls)

    assert run.contexts == []


def test_a_call_that_moves_nothing_adds_nothing(tmp_path):
    project, _ = _places(tmp_path)

    run = run_session(tmp_path, project, moved(project, "ls -la", project, payload_shows_move=True))

    assert run.contexts == []


@pytest.mark.parametrize(
    "raw", ["", "{not json", "[]"], ids=["empty", "malformed", "not-an-object"]
)
def test_an_unreadable_payload_adds_nothing_and_exits_cleanly(tmp_path, raw):
    project, _ = _places(tmp_path)
    calls = [HookCall("PreToolUse", "", project), HookCall("PostToolUse", "", project)]

    run = run_session(tmp_path, project, calls, raw=raw)

    assert run.contexts == []
    assert set(run.exit_codes) == {0}, run.exit_codes
