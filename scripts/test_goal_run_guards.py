"""Tests for what `run` grants the headless worker and refuses before it starts one.

The worker may edit its step's files and the task's progress file, and holds only the
pre-approvals `run` grants it: allow rules of the user's, the project's and the local settings
are mirrored as denials when they are harmless to the goal, and refused when they are not. The
scratch checkout and the stand-in `claude` are those of ``test_goal_run.py``; a real `claude` is
never started, and every test reads its own private configuration directory, never the real one.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _goal_run  # noqa: E402
from _goal_run import Treatment, classify  # noqa: E402
from test_goal_run import (  # noqa: E402
    CHECK_COMMAND,
    SETTINGS,
    SLUG,
    WIDGET,
    Scratch,
    build_scratch,
    deny_rules,
    install_stand_in,
    put,
    sandbox,  # noqa: F401 -- the autouse fixture of the suite whose harness this one reuses
)
from test_goal_worker import option_values  # noqa: E402

PYTEST_CHECK = "uv run pytest tests/test_widget.py -q -p no:cacheprovider"
RESOLVER = "python3 scripts/resolve_test_scope.py"
READ_TOOLS = ["Read", "Glob", "Grep"]
PUSH, REPO_ADMIN = "Bash(git push *)", "Bash(gh repo *)"
PROJECT_SETTINGS = ".claude/settings.json"


def user_settings() -> Path:
    return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"


def allow(*rules: str) -> str:
    return json.dumps({"permissions": {"allow": list(rules)}})


def pre_approve_for_the_user(*rules: str) -> Path:
    put(user_settings().parent, user_settings().name, allow(*rules))
    return user_settings()


def pre_approve_in_the_project(scratch: Scratch, *rules: str) -> Path:
    put(scratch.root, PROJECT_SETTINGS, allow(*rules))
    return scratch.root / PROJECT_SETTINGS


def pre_approve_locally(scratch: Scratch, *rules: str) -> Path:
    settings = {"permissions": {"deny": deny_rules(scratch.root), "allow": list(rules)}}
    put(scratch.root, SETTINGS, json.dumps(settings))
    return scratch.root / SETTINGS


def only_argv(scratch: Scratch) -> list[str]:
    (call,) = scratch.calls()
    return call["argv"]


@pytest.fixture
def scratch(tmp_path) -> Scratch:
    ready = build_scratch(tmp_path, iterations=1)
    install_stand_in(ready)
    return ready


@pytest.fixture
def pytest_check_scratch(tmp_path) -> Scratch:
    ready = build_scratch(tmp_path, iterations=1, check=PYTEST_CHECK)
    install_stand_in(ready)
    return ready


# --- What the worker may write ---------------------------------------------------------------


def test_the_worker_may_edit_its_step_files_and_the_progress_file_only(scratch):
    scratch.run()

    allowed = option_values(only_argv(scratch), "--allowedTools")
    assert allowed[: len(READ_TOOLS) + 2] == [
        *READ_TOOLS,
        f"Edit(/{WIDGET})",
        f"Edit(/.ai-work/{SLUG}/WIP.md)",
    ]
    assert not {"Edit", "Write"} & set(allowed)


def test_the_check_and_the_resolver_are_the_only_commands_the_worker_is_allowed(scratch):
    scratch.run()

    allowed = option_values(only_argv(scratch), "--allowedTools")
    commands = [rule for rule in allowed if rule.startswith("Bash(")]
    assert commands[0] == f"Bash({CHECK_COMMAND}:*)"
    assert len(commands) == 2


# --- What the worker does not inherit ---------------------------------------------------------


def test_pre_approvals_the_goal_does_not_need_are_denied_to_the_worker(scratch):
    pre_approve_for_the_user(PUSH, REPO_ADMIN)

    scratch.run()

    argv = only_argv(scratch)
    assert option_values(argv, "--disallowedTools") == [PUSH, REPO_ADMIN]
    assert "--strict-mcp-config" in argv


def test_a_worker_with_nothing_to_deny_gets_no_deny_list_but_still_no_servers(scratch):
    scratch.run()

    argv = only_argv(scratch)
    assert "--disallowedTools" not in argv
    assert "--strict-mcp-config" in argv


def test_the_project_and_local_pre_approvals_are_denied_after_the_users(scratch):
    pre_approve_for_the_user(PUSH)
    pre_approve_in_the_project(scratch, REPO_ADMIN)
    pre_approve_locally(scratch, "Bash(git add *)")

    scratch.run()

    denied = option_values(only_argv(scratch), "--disallowedTools")
    assert denied == [PUSH, REPO_ADMIN, "Bash(git add *)"]


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '{"permissions": []}', '{"permissions": {"allow": "Bash"}}', "{}"],
    ids=["unreadable", "not-an-object", "wrong-permissions", "wrong-allow", "no-rules"],
)
def test_a_settings_file_that_holds_no_readable_rules_denies_nothing(scratch, content):
    put(user_settings().parent, user_settings().name, content)

    scratch.run()

    assert "--disallowedTools" not in only_argv(scratch)


# --- What makes `run` refuse -----------------------------------------------------------------


@pytest.mark.parametrize(
    "rule",
    ["Bash", "Bash(*)", "Bash(uv run *)", "Edit", "Write", "Edit(src/**)"],
)
def test_a_pre_approval_the_worker_cannot_be_denied_is_refused_before_any_worker(
    pytest_check_scratch, rule
):
    source = pre_approve_for_the_user(rule)

    reply = pytest_check_scratch.run()

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "usage")
    assert rule in reply.doc["error"]["message"], reply.doc
    assert str(source) in reply.doc["error"]["message"], reply.doc
    assert pytest_check_scratch.calls() == []


@pytest.mark.parametrize(
    "pre_approve", [pre_approve_in_the_project, pre_approve_locally], ids=["project", "local"]
)
def test_a_refused_pre_approval_names_the_project_or_local_file_that_holds_it(
    pytest_check_scratch, pre_approve
):
    source = pre_approve(pytest_check_scratch, "Edit")

    reply = pytest_check_scratch.run()

    assert reply.exit == 4
    assert str(source) in reply.doc["error"]["message"], reply.doc
    assert pytest_check_scratch.calls() == []


@pytest.mark.parametrize("rule", ["Write(.ai-work/**)", "Read(~/notes/**)"])
def test_a_rule_that_grants_the_worker_nothing_is_not_refused(scratch, rule):
    pre_approve_for_the_user(rule)

    reply = scratch.run()

    assert reply.exit != 4, reply.doc
    assert len(scratch.calls()) == 1


# --- How each rule is treated ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "treatment"),
    [
        ("Bash(git push *)", Treatment.MIRROR),
        ("Bash(git add:*)", Treatment.MIRROR),
        ("Bash(gh repo delete)", Treatment.MIRROR),
        ("Bash", Treatment.REFUSE),
        ("Bash(*)", Treatment.REFUSE),
        ("Bash(:*)", Treatment.REFUSE),
        ("Bash(uv *)", Treatment.REFUSE),
        ("Bash(python3 scripts/*)", Treatment.REFUSE),
        ("Edit", Treatment.REFUSE),
        ("Edit(/src/**)", Treatment.REFUSE),
        ("MultiEdit", Treatment.REFUSE),
        ("NotebookEdit", Treatment.REFUSE),
        ("Write(/src/**)", Treatment.IGNORE),
        ("MultiEdit(src/**)", Treatment.IGNORE),
        ("Read(~/notes/**)", Treatment.IGNORE),
        ("WebFetch(domain:example.com)", Treatment.IGNORE),
        ("mcp__server__tool", Treatment.IGNORE),
    ],
)
def test_each_inherited_rule_is_mirrored_ignored_or_refused(rule, treatment):
    assert classify(rule, (PYTEST_CHECK, RESOLVER)) is treatment


def test_the_progress_file_outside_the_repository_is_allowed_by_its_absolute_path(tmp_path):
    repo, task = tmp_path / "repo", tmp_path / "elsewhere" / SLUG
    repo.mkdir()
    task.mkdir(parents=True)

    rules = _goal_run.writable_rules((WIDGET,), repo, task)

    assert rules == (f"Edit(/{WIDGET})", f"Edit(/{task.resolve()}/WIP.md)")
