"""Tests for hooks/notice_working_directory.sh -- the agent is told where a Bash call left it.

The hook keeps one record per session (`v1 settled|moving`, home, last) under the
per-user config directory and adds one line of context per move away from home. These
tests drive it as the harness does (payload on stdin, `pre` or `post` argument) under
every POSIX shell present, and read the record it leaves.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "notice_working_directory.sh"
SESSION = "session-notice"
AGED_SECONDS = 30 * 24 * 3600

SHELLS = [
    pytest.param(name, marks=pytest.mark.skipif(shutil.which(name) is None, reason=f"no {name}"))
    for name in ("sh", "dash", "bash")
]


@pytest.fixture(params=SHELLS)
def shell(request: pytest.FixtureRequest) -> str:
    """Each POSIX shell the hook must behave identically under."""
    return request.param


@dataclass(frozen=True)
class Places:
    """A project, a directory outside it, a subdirectory, and the hook's config home."""

    project: Path
    elsewhere: Path
    inner: Path
    home: Path

    @property
    def store(self) -> Path:
        return self.home / ".claude" / "praxion" / "cwd-notice"

    @property
    def record(self) -> Path:
        return self.store / SESSION

    @property
    def interpreter_log(self) -> Path:
        return self.home / "interpreter-starts.log"

    def named(self, name: str) -> Path:
        return {"P": self.project, "E": self.elsewhere, "S": self.inner}[name]


@pytest.fixture
def places(tmp_path: Path) -> Places:
    root = tmp_path.resolve()
    found = Places(root / "project", root / "elsewhere", root / "project" / "src", root / "home")
    for directory in (found.project, found.elsewhere, found.inner, found.home):
        directory.mkdir(parents=True, exist_ok=True)
    _write_interpreter_stand_in(found)
    return found


def _write_interpreter_stand_in(places: Places) -> None:
    """A `python3` first on PATH that records each start, so a test can count them."""
    bin_dir = places.home / "bin"
    bin_dir.mkdir()
    for name in ("python3", "python"):
        stand_in = bin_dir / name
        stand_in.write_text(f'#!/bin/sh\necho started >> "{places.interpreter_log}"\n')
        stand_in.chmod(0o755)


@dataclass(frozen=True)
class HookRun:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def contexts(self) -> list[str]:
        if not self.stdout.strip():
            return []
        return [json.loads(self.stdout)["hookSpecificOutput"]["additionalContext"]]


def run_hook(shell: str, places: Places, event: str, stdin: str) -> HookRun:
    env = {
        "PATH": os.pathsep.join([str(places.home / "bin"), os.environ.get("PATH", "")]),
        "HOME": str(places.home),
        "CLAUDE_CONFIG_DIR": str(places.home / ".claude"),
    }
    result = subprocess.run(
        [shell, str(HOOK), event],
        input=stdin,
        cwd=places.project,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    return HookRun(result.returncode, result.stdout, result.stderr)


def payload(cwd: Path | str, command: str = "ls", **fields: object) -> str:
    """The documented key order: the session id and the cwd come before `tool_input`."""
    body: dict[str, object] = {
        "session_id": SESSION,
        "transcript_path": "/nowhere/transcript.jsonl",
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "Move around"},
        "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
    }
    body.update(fields)
    return json.dumps(body)


def seed(places: Places, tag: str, home: Path, last: Path) -> None:
    places.store.mkdir(parents=True, exist_ok=True)
    places.record.write_text(f"v1 {tag}\n{home}\n{last}\n")


def seed_named(places: Places, start: tuple[str, str, str] | None) -> None:
    """Seed a record whose directories are named by letter; None leaves the session unseen."""
    if start is not None:
        tag, home, last = start
        seed(places, tag, places.named(home), places.named(last))


def record_of(places: Places) -> tuple[str, str, str] | None:
    if not places.record.exists():
        return None
    tag, home, last = places.record.read_text().splitlines()
    return tag, home, last


def expected(places: Places, tag: str, home: str, last: str) -> tuple[str, str, str]:
    return f"v1 {tag}", str(places.named(home)), str(places.named(last))


# ---------------------------------------------------------------------------
# The transition table, one row per case
# ---------------------------------------------------------------------------

# (from record or None, event, cwd, command, to record, a notice is added)
TRANSITIONS = {
    "unseen-pre-settles-where-it-is": (None, "pre", "P", "ls", ("settled", "P", "P"), False),
    "unseen-post-settles-where-it-is": (None, "post", "E", "ls", ("settled", "E", "E"), False),
    "moving-pre-same-place-moved-nothing": (
        ("moving", "P", "P"),
        "pre",
        "P",
        "ls",
        ("settled", "P", "P"),
        False,
    ),
    "moving-pre-new-place-is-announced": (
        ("moving", "P", "P"),
        "pre",
        "E",
        "ls",
        ("settled", "P", "E"),
        True,
    ),
    "moving-pre-back-home-is-silent": (
        ("moving", "P", "E"),
        "pre",
        "P",
        "ls",
        ("settled", "P", "P"),
        False,
    ),
    "settled-pre-new-place-is-the-harness-moving-home": (
        ("settled", "P", "P"),
        "pre",
        "E",
        "ls",
        ("settled", "E", "E"),
        False,
    ),
    "settled-post-new-place-is-announced": (
        ("settled", "P", "P"),
        "post",
        "E",
        "ls",
        ("settled", "P", "E"),
        True,
    ),
    "moving-post-new-place-is-announced": (
        ("moving", "P", "P"),
        "post",
        "S",
        "ls",
        ("settled", "P", "S"),
        True,
    ),
    "settled-post-back-home-is-silent": (
        ("settled", "P", "E"),
        "post",
        "P",
        "ls",
        ("settled", "P", "P"),
        False,
    ),
    "settled-post-same-place-with-a-cd-is-moving": (
        ("settled", "P", "P"),
        "post",
        "P",
        "cd src",
        ("moving", "P", "P"),
        False,
    ),
}


@pytest.mark.parametrize(
    ("start", "event", "cwd", "command", "end", "announced"),
    list(TRANSITIONS.values()),
    ids=list(TRANSITIONS),
)
def test_each_transition_leaves_its_record_and_announces_only_a_move_away_from_home(
    shell, places, start, event, cwd, command, end, announced
):
    seed_named(places, start)

    run = run_hook(shell, places, event, payload(places.named(cwd), command))

    assert record_of(places) == expected(places, *end)
    assert len(run.contexts) == int(announced), run.contexts


@pytest.mark.parametrize(
    "command",
    ["make && pushd /tmp", "git pull\ncd src", "make;cd src", "(popd)", "cd\tsrc", "ls|cd"],
    ids=[
        "after-an-operator",
        "on-a-new-line",
        "after-a-semicolon",
        "in-a-subshell",
        "before-a-tab",
        "last",
    ],
)
def test_a_directory_change_word_anywhere_in_the_command_marks_the_call_moving(
    shell, places, command
):
    seed(places, "settled", places.project, places.project)

    run_hook(shell, places, "post", payload(places.project, command))

    assert record_of(places) == expected(places, "moving", "P", "P")


# (record, event, cwd, command): nothing changes, so the record file is not rewritten
UNCHANGED = {
    "settled-pre-same-place": (("settled", "P", "P"), "pre", "P", "cat x"),
    "settled-post-same-place-no-directory-change": (("settled", "P", "P"), "post", "P", "ls cdrom"),
    "moving-post-same-place-no-directory-change": (("moving", "P", "P"), "post", "P", "ls"),
    "moving-post-same-place-another-cd": (("moving", "P", "P"), "post", "P", "cd /tmp"),
}


@pytest.mark.parametrize(
    ("start", "event", "cwd", "command"), list(UNCHANGED.values()), ids=list(UNCHANGED)
)
def test_a_call_that_changes_nothing_neither_writes_nor_adds(
    shell, places, start, event, cwd, command
):
    seed_named(places, start)
    os.utime(places.record, (1, 1))

    run = run_hook(shell, places, event, payload(places.named(cwd), command))

    assert (run.stdout, places.record.stat().st_mtime) == ("", 1)


@pytest.mark.parametrize(
    "fields",
    [
        {"tool_input": {"command": "ls", "description": "cd into the build directory"}},
        {
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": "run cd /x then", "stderr": "", "interrupted": False},
        },
    ],
    ids=["description", "tool-output-of-a-command-with-no-description"],
)
def test_a_directory_change_outside_the_command_is_not_a_pending_move(shell, places, fields):
    seed(places, "settled", places.project, places.project)
    os.utime(places.record, (1, 1))

    run_hook(shell, places, "post", payload(places.project, **fields))

    assert places.record.stat().st_mtime == 1


def test_the_same_physical_directory_by_another_name_is_not_a_move(shell, places):
    alias = places.home / "alias"
    alias.symlink_to(places.project)
    seed(places, "settled", places.project, places.project)

    run = run_hook(shell, places, "post", payload(alias))

    assert (run.stdout, record_of(places)) == ("", expected(places, "settled", "P", "P"))


def test_a_record_of_another_shape_reads_unseen_and_is_rewritten(shell, places):
    places.store.mkdir(parents=True)
    places.record.write_text("v0 settled\nnot-a-path\n")

    run = run_hook(shell, places, "post", payload(places.elsewhere))

    assert (run.stdout, record_of(places)) == ("", expected(places, "settled", "E", "E"))


# ---------------------------------------------------------------------------
# The notice itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("event", "name"), [("pre", "PreToolUse"), ("post", "PostToolUse")])
def test_the_notice_is_one_line_of_context_for_the_firing_event_naming_both_directories(
    shell, places, event, name
):
    seed(places, "moving", places.project, places.project)

    run = run_hook(shell, places, event, payload(places.elsewhere))

    doc = json.loads(run.stdout)
    context = doc["hookSpecificOutput"]["additionalContext"]
    assert doc["hookSpecificOutput"]["hookEventName"] == name
    assert len(run.stdout.splitlines()) == 1
    assert str(places.elsewhere) in context, context
    assert str(places.project) in context, context


def _session(shell: str, places: Places, calls: list[tuple[str, Path, str]]) -> list[str]:
    return [
        context
        for event, cwd, command in calls
        for context in run_hook(shell, places, event, payload(cwd, command)).contexts
    ]


@pytest.mark.parametrize(
    "payload_shows_move", [True, False], ids=["shows-the-move", "shows-the-old-directory"]
)
def test_a_move_away_adds_exactly_one_line_whichever_payload_shows_it(
    shell, places, payload_shows_move
):
    command = f"cd {places.elsewhere} && ls"
    post_cwd = places.elsewhere if payload_shows_move else places.project
    calls = [
        ("pre", places.project, command),
        ("post", post_cwd, command),
        ("pre", places.elsewhere, "ls"),
        ("post", places.elsewhere, "ls"),
    ]

    contexts = _session(shell, places, calls)

    assert len(contexts) == 1, contexts
    assert str(places.elsewhere) in contexts[0]
    assert str(places.project) in contexts[0]


def test_a_payload_without_spaces_after_its_colons_reads_the_same(shell, places):
    seed(places, "settled", places.project, places.project)
    compact = json.dumps(json.loads(payload(places.elsewhere)), separators=(",", ":"))

    run = run_hook(shell, places, "post", compact)

    assert len(run.contexts) == 1, run.stdout
    assert record_of(places) == expected(places, "settled", "P", "E")


def test_a_cd_from_an_entered_worktree_into_the_main_checkout_is_announced(shell, places):
    worktree = places.project / ".claude" / "worktrees" / "feature"
    worktree.mkdir(parents=True)
    command = f"cd {places.project}"
    calls = [
        ("pre", places.project, "ls"),
        ("pre", worktree, "ls"),
        ("post", worktree, "ls"),
        ("post", places.project, command),
        ("pre", places.project, "ls"),
    ]

    contexts = _session(shell, places, calls)

    assert len(contexts) == 1, contexts
    assert f"in {places.project};" in contexts[0]
    assert f"root is {worktree}." in contexts[0]


def test_a_session_in_its_entered_worktree_hears_nothing(shell, places):
    worktree = places.project / ".claude" / "worktrees" / "feature"
    worktree.mkdir(parents=True)
    calls = [
        ("pre", places.project, "ls"),
        ("pre", worktree, "ls"),
        ("post", worktree, "git status"),
        ("pre", worktree, "ls"),
        ("post", worktree, "ls"),
    ]

    assert _session(shell, places, calls) == []


# ---------------------------------------------------------------------------
# Silent and fail-open
# ---------------------------------------------------------------------------


def test_a_subagent_payload_adds_nothing_and_keeps_no_record(shell, places):
    seed(places, "moving", places.project, places.project)
    os.utime(places.record, (1, 1))

    run = run_hook(
        shell, places, "pre", payload(places.elsewhere, agent_id="agent-1", agent_type="x")
    )

    assert (run.exit_code, run.stdout, places.record.stat().st_mtime) == (0, "", 1)


UNREADABLE = {
    "empty": "",
    "malformed": "{not json",
    "not-an-object": "[]",
    "foreign-without-a-session": json.dumps(
        {"conversation_id": "c", "cwd": "/tmp", "command": "cd /"}
    ),
    "session-outside-the-safe-alphabet": json.dumps({"session_id": "../x", "cwd": "/tmp"}),
    "relative-cwd": json.dumps({"session_id": SESSION, "cwd": "project"}),
    "cwd-not-a-string": json.dumps({"session_id": SESSION, "cwd": None}),
}


@pytest.mark.parametrize("stdin", list(UNREADABLE.values()), ids=list(UNREADABLE))
@pytest.mark.parametrize("event", ["pre", "post"])
def test_an_unreadable_payload_adds_nothing_keeps_no_record_and_exits_cleanly(
    shell, places, event, stdin
):
    run = run_hook(shell, places, event, stdin)

    assert (run.exit_code, run.stdout, run.stderr) == (0, "", "")
    assert not places.store.exists()


def test_a_path_holding_a_double_quote_is_never_announced(shell, places):
    quoted = places.home / 'say "hi"'
    quoted.mkdir()
    seed(places, "moving", places.project, places.project)

    run = run_hook(shell, places, "pre", payload(quoted))

    assert (run.exit_code, run.stdout, run.stderr) == (0, "", "")
    assert record_of(places) == expected(places, "moving", "P", "P")


def test_an_unknown_event_argument_adds_nothing(shell, places):
    run = run_hook(shell, places, "later", payload(places.elsewhere))

    assert (run.exit_code, run.stdout, run.stderr) == (0, "", "")
    assert not places.store.exists()


def test_an_unwritable_config_directory_adds_nothing_and_exits_cleanly(shell, places):
    (places.home / ".claude").write_text("a file where the directory should be")

    run = run_hook(shell, places, "post", payload(places.elsewhere))

    assert (run.exit_code, run.stdout, run.stderr) == (0, "", "")


def test_a_silent_call_starts_no_interpreter(shell, places):
    seed(places, "settled", places.project, places.project)

    run = run_hook(shell, places, "post", payload(places.project, "git status && ls -la"))

    assert run.stdout == ""
    assert not places.interpreter_log.exists(), places.interpreter_log.read_text()


def test_a_new_session_clears_records_quiet_for_a_week_and_keeps_the_rest(shell, places):
    places.store.mkdir(parents=True)
    stale, fresh = places.store / "old-session", places.store / "busy-session"
    stale.write_text("v1 settled\n/a\n/a\n")
    fresh.write_text("v1 settled\n/b\n/b\n")
    aged = stale.stat().st_mtime - AGED_SECONDS
    os.utime(stale, (aged, aged))

    run_hook(shell, places, "pre", payload(places.project))

    assert sorted(p.name for p in places.store.iterdir()) == ["busy-session", SESSION]


def test_the_hook_is_executable():
    assert os.access(HOOK, os.X_OK), f"{HOOK} is not executable (chmod +x required)"
