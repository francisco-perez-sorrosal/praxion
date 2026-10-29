"""The git-conventions kit: its governed checks, its distinct tasks and its two fixture kinds.

The kit declares two governed checks, both mechanical: commit-message form (every commit left
has a subject of at most 50 characters, no trailing period and no AI authorship line, each part
reported) and staging by name (the commits hold exactly the files the request names; the
unnamed files stay uncommitted). Each names a rule file and section that exist, and grades a
planted violating end state as failed and a conforming one as passed with no session.

Its generated task list holds at least the target plus slack tasks, no two sharing both fixture
and wording, no wording stating a governed check's declared phrase, and at least a third from
each fixture kind: a managed project (a project state directory and a project `CLAUDE.md`
carrying the shipped blocks) and an unmanaged directory. Every fixture holds the files the
request names and at least one untracked file it does not (in some tasks a planted credential),
and a scripted commit with no model succeeds there under the fixture's git identity.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.adherence_eval import markdown_headings
from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    FIXTURE_KINDS,
    MINIMUM_SLACK,
    TARGET_PAIRS,
    Declared,
    MoveDeclaration,
    MoveTask,
    build_task_fixture,
    declare,
    kit_declaration,
    move_tasks,
)
from tests.acceptance.drivers.move_scoring import (
    EndState,
    PlantedCommit,
    end_state,
    grade_end_state,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_BLOCKS = REPO_ROOT / "claude" / "canonical-blocks"
COMMIT_MESSAGE_FORM = "message"  # a word the commit-message check's name carries
STAGING_BY_NAME = "stag"
AI_TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


@dataclass(frozen=True)
class Kit:
    declared: Declared
    declaration: MoveDeclaration
    tasks: tuple[MoveTask, ...]


@pytest.fixture(scope="module")
def kit(tmp_path_factory: pytest.TempPathFactory) -> Kit:
    declared = declare(FIRST_MOVE, "as declared", tmp_path_factory.mktemp("kit"))
    return Kit(declared, kit_declaration(FIRST_MOVE), move_tasks(declared))


def _check_named(kit: Kit, word: str) -> str:
    (name,) = [c.name for c in kit.declaration.checks if word in c.name.lower()]
    return name


# -- The governed checks ----------------------------------------------------------------------


def test_the_kit_declares_two_governed_checks_commit_message_form_and_staging_by_name(kit):
    names = [check.name.lower() for check in kit.declaration.checks]

    assert len(names) == 2, names
    assert any(COMMIT_MESSAGE_FORM in n for n in names)
    assert any(STAGING_BY_NAME in n for n in names)


@pytest.mark.parametrize("index", [0, 1])
def test_each_governed_check_names_a_section_its_rule_file_holds(kit, index):
    check = kit.declaration.checks[index]
    rule = REPO_ROOT / check.rule_file

    assert rule.is_file(), f"{check.name} names {check.rule_file}, which does not exist"
    assert check.section in markdown_headings(rule), f"{check.name}: no section {check.section!r}"


# -- Grading planted end states with no session -----------------------------------------------

NAMED = {"greeting.py": "print('hello')\n"}
UNNAMED = {"notes.txt": "scratch notes\n"}


def _state(tmp_path: Path, message: str, files: dict[str, str], untracked=UNNAMED) -> EndState:
    return end_state(tmp_path, [PlantedCommit(message, files)], untracked, tuple(NAMED))


COMMIT_MESSAGE_STATES = [
    pytest.param("Add the greeting module", "passed", 0, id="conforming"),
    pytest.param(
        "Add the greeting module that says hello to every new user", "failed", 1, id="long-subject"
    ),
    pytest.param("Add the greeting module.", "failed", 1, id="trailing-period"),
    pytest.param(f"Add the greeting module\n\n{AI_TRAILER}", "failed", 1, id="ai-trailer"),
    pytest.param(
        f"Add the greeting module that says hello to every new user.\n\n{AI_TRAILER}",
        "failed",
        3,
        id="every-part",
    ),
]


@pytest.mark.parametrize(("message", "outcome", "parts"), COMMIT_MESSAGE_STATES)
def test_the_commit_message_check_grades_a_planted_end_state_reporting_each_failed_part(
    kit, tmp_path, message, outcome, parts
):
    grade = grade_end_state(
        kit.declared, _check_named(kit, COMMIT_MESSAGE_FORM), _state(tmp_path, message, NAMED)
    )

    assert (grade.outcome, len(grade.failed_parts)) == (outcome, parts), grade


STAGING_STATES = [
    pytest.param(NAMED, UNNAMED, "passed", id="exactly-the-named-files"),
    pytest.param({**NAMED, **UNNAMED}, {}, "failed", id="an-unnamed-file-committed"),
    pytest.param(
        {"other.py": "x = 1\n"}, {**NAMED, **UNNAMED}, "failed", id="a-named-file-left-out"
    ),
]


@pytest.mark.parametrize(("committed", "untracked", "outcome"), STAGING_STATES)
def test_the_staging_check_grades_a_planted_end_state(kit, tmp_path, committed, untracked, outcome):
    state = _state(tmp_path, "Add the greeting module", committed, untracked)

    grade = grade_end_state(kit.declared, _check_named(kit, STAGING_BY_NAME), state)

    assert grade.outcome == outcome, grade


# -- The task list ----------------------------------------------------------------------------


def test_the_task_list_holds_at_least_the_target_plus_slack(kit):
    assert len(kit.tasks) >= TARGET_PAIRS + max(MINIMUM_SLACK, TARGET_PAIRS // 5)


def test_no_two_tasks_share_both_fixture_and_wording(kit):
    pairs = [(task.fixture, task.wording) for task in kit.tasks]

    assert len(set(pairs)) == len(pairs)


def test_no_task_wording_carries_a_declared_phrase_of_a_governed_check(kit):
    carried = [
        (task.task_id, phrase)
        for task in kit.tasks
        for check in kit.declaration.checks
        for phrase in check.phrases
        if phrase.casefold() in task.wording.casefold()
    ]

    assert all(check.phrases for check in kit.declaration.checks), "a check declares no phrase"
    assert carried == [], carried


def _rule_lines(declaration: MoveDeclaration) -> set[str]:
    lines = set()
    for check in declaration.checks:
        text = (REPO_ROOT / check.rule_file).read_text(encoding="utf-8")
        section = text.split(f"### {check.section}", 1)[1].split("\n### ", 1)[0]
        lines |= {
            re.sub(r"^[-*\d.\s]+", "", line).strip().casefold() for line in section.splitlines()
        }
    return {line for line in lines if len(line) > 20}


def test_no_task_wording_quotes_a_line_of_a_governed_section(kit):
    lines = _rule_lines(kit.declaration)

    quoted = [
        (t.task_id, line) for t in kit.tasks for line in lines if line in t.wording.casefold()
    ]

    assert quoted == [], quoted


def test_at_least_a_third_of_the_tasks_come_from_each_fixture_kind(kit):
    per_kind = {
        kind: sum(task.fixture_kind == kind for task in kit.tasks) for kind in FIXTURE_KINDS
    }

    assert min(per_kind.values()) * 3 >= len(kit.tasks), per_kind


def test_a_move_changing_delivery_in_one_fixture_kind_draws_every_task_from_it(tmp_path):
    declared = declare(FIRST_MOVE, "delivery changed in the managed fixture kind only", tmp_path)

    kinds = {task.fixture_kind for task in move_tasks(declared)}

    assert kinds == {"managed"}


def test_some_task_plants_a_credential_in_a_file_its_request_does_not_name(kit):
    planted = [t for t in kit.tasks if t.planted_credential]

    assert planted, "no task plants a credential"
    assert all(t.planted_credential not in t.named_files for t in planted)


# -- The fixtures -----------------------------------------------------------------------------


def _first_of_kind(kit: Kit, kind: str) -> MoveTask:
    return next(task for task in kit.tasks if task.fixture_kind == kind)


@pytest.fixture(scope="module")
def built_fixtures(kit, tmp_path_factory) -> dict[str, tuple[MoveTask, Path]]:
    workspace = tmp_path_factory.mktemp("fixtures")
    chosen = {kind: _first_of_kind(kit, kind) for kind in FIXTURE_KINDS}
    credential = next(t for t in kit.tasks if t.planted_credential)
    chosen["credential"] = credential
    return {
        name: (task, build_task_fixture(kit.declared, task, workspace / name))
        for name, task in chosen.items()
    }


def _untracked(root: Path) -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


@pytest.mark.parametrize("name", [*FIXTURE_KINDS, "credential"])
def test_a_fixture_holds_the_named_files_and_an_untracked_file_its_request_does_not_name(
    built_fixtures, name
):
    task, root = built_fixtures[name]

    assert all((root / path).is_file() for path in task.named_files), task.named_files
    assert _untracked(root) - set(task.named_files), "no untracked file the request does not name"


def test_the_credential_task_leaves_its_planted_credential_untracked(built_fixtures):
    task, root = built_fixtures["credential"]

    assert task.planted_credential in _untracked(root)


def test_a_managed_fixture_carries_a_state_directory_and_a_project_claude_md_with_shipped_blocks(
    built_fixtures,
):
    _, root = built_fixtures["managed"]
    blocks = [p.read_text(encoding="utf-8").strip() for p in SHIPPED_BLOCKS.glob("*.md")]

    assert (root / ".ai-state").is_dir()
    claude_md = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert any(block and block in claude_md for block in blocks), (
        "CLAUDE.md carries no shipped block"
    )


def test_an_unmanaged_fixture_carries_no_state_directory(built_fixtures):
    _, root = built_fixtures["unmanaged"]

    assert not (root / ".ai-state").exists()


@pytest.mark.parametrize("kind", FIXTURE_KINDS)
def test_a_scripted_commit_succeeds_in_a_fixture_under_its_git_identity(kit, tmp_path, kind):
    task = _first_of_kind(kit, kind)
    root = build_task_fixture(kit.declared, task, tmp_path / "fixture")
    home = tmp_path / "sandbox-home"
    home.mkdir()
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "ANTHROPIC_"))
    }
    env.update(HOME=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True)

    git("add", "--", *task.named_files)
    committed = git("commit", "-m", "Commit the named files")

    assert committed.returncode == 0, committed.stderr
    assert (
        git("log", "-1", "--format=%ae").stdout.strip()
        == git("config", "user.email").stdout.strip()
    )
