"""The adr-conventions kit: tasks that never state the rule, and fixtures that set its trap.

The drawn task list holds at least the target plus slack (24 at the defaults), no two sharing
both fixture and wording, every one from a managed fixture. No request holds a line of the moved
rule, a declared phrase of either governed check, any of the four `category` values or a
command; across the kit's fixtures both sorts of decision are asked for, at least one fixture of
each sort.

Every fixture is a managed project (a state directory, and a `CLAUDE.md` carrying every shipped
block but the hackathon and sidecar-placement blocks, since its state lives in the repository) on a named branch other than its default, under a git
identity a session can read, whose decision directory holds at least two records in the older
habit and a `DECISIONS_INDEX.md` listing them, holds no draft directory, and holds no file
carrying a line of the moved rule or a declared phrase. A record scripted with no model and
written as the rule says grades passed on both governed checks there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from tests.acceptance.drivers.decision_kit import (
    CATEGORY_VALUES,
    DECISION_CHECKS,
    DECISION_MOVE,
    DECISION_RULE,
    DecisionGrade,
    DecisionTask,
    build_decision_fixture,
    decision_tasks,
    declared_phrases,
    grade_decision_end_state,
    kit_payload,
    rule_lines,
)
from tests.acceptance.drivers.decision_records import (
    DECISIONS_DIR,
    DRAFTS_DIR,
    INDEX_FILE,
    branch_segment,
    conforming,
    fragment_name,
    leave,
    with_changes,
)
from tests.acceptance.drivers.move_eval import (
    MINIMUM_SLACK,
    TARGET_PAIRS,
    Declared,
    declare,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_BLOCKS = REPO_ROOT / "claude" / "canonical-blocks"
# A fixture is outside hackathon mode and keeps its state in the repository.
LEFT_OUT_BLOCKS = ("hackathon-mode.md", "sidecar-placement.md")
DEFAULT_BRANCHES = ("main", "master")
OLDER_HABIT_NAME = re.compile(r"\d{3,}-[a-z0-9][a-z0-9-]*\.md")
NUMBERED_ID = re.compile(r"dec-\d{3,}")
# A backtick; a dollar sign and a space; a slash opening a word, then a letter; or a program
# name standing as a whole word, then a space and an argument.
COMMAND = re.compile(
    r"`|\$ |(?:^|\s)/[A-Za-z]|\b(?:git|python|uv|bash|pytest|npm|make|praxion-[\w-]*) \S"
)


@dataclass(frozen=True)
class Kit:
    declared: Declared
    payload: dict
    tasks: tuple[DecisionTask, ...]


@pytest.fixture(scope="module")
def kit(tmp_path_factory: pytest.TempPathFactory) -> Kit:
    declared = declare(DECISION_MOVE, "as declared", tmp_path_factory.mktemp("decision-kit"))
    return Kit(declared, kit_payload(), decision_tasks(declared))


# -- The task list ----------------------------------------------------------------------------


def test_the_task_list_holds_at_least_the_target_plus_slack(kit):
    assert len(kit.tasks) >= TARGET_PAIRS + max(MINIMUM_SLACK, TARGET_PAIRS // 5)


def test_no_two_tasks_share_both_fixture_and_wording(kit):
    pairs = [(task.fixture, task.wording) for task in kit.tasks]

    assert len(set(pairs)) == len(pairs)


def test_every_task_comes_from_a_managed_fixture(kit):
    assert {task.fixture_kind for task in kit.tasks} == {"managed"}


def test_no_request_holds_a_line_of_the_moved_rule(kit):
    lines = rule_lines((REPO_ROOT / DECISION_RULE).read_text(encoding="utf-8"))

    quoted = [
        (t.task_id, line) for t in kit.tasks for line in lines if line in t.wording.casefold()
    ]

    assert quoted == [], quoted


def test_no_request_holds_a_declared_phrase_of_either_governed_check(kit):
    phrases = declared_phrases(kit.payload)

    carried = [
        (t.task_id, p) for t in kit.tasks for p in phrases if p.casefold() in t.wording.casefold()
    ]

    assert phrases, "the kit declares no phrase"
    assert carried == [], carried


def test_no_request_names_a_category_value(kit):
    values = re.compile(r"\b(" + "|".join(CATEGORY_VALUES) + r")\b", re.IGNORECASE)

    named = [(t.task_id, m.group(0)) for t in kit.tasks for m in values.finditer(t.wording)]

    assert named == [], named


def test_no_request_holds_a_command(kit):
    commands = [(t.task_id, m.group(0)) for t in kit.tasks if (m := COMMAND.search(t.wording))]

    assert commands == [], commands


def test_the_kits_fixtures_ask_for_decisions_of_both_sorts(kit):
    sorts_by_fixture = {(task.fixture, task.sort) for task in kit.tasks}

    assert {sort for _, sort in sorts_by_fixture} == {"architectural", "not architectural"}


# -- The fixtures -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixtures(kit, tmp_path_factory) -> dict[str, Path]:
    """One built project per distinct fixture of the kit, from the first task drawing it."""
    workspace = tmp_path_factory.mktemp("decision-fixtures")
    first = {task.fixture: task for task in reversed(kit.tasks)}
    return {
        name: build_decision_fixture(kit.declared, task, workspace / name)
        for name, task in sorted(first.items())
    }


def test_every_fixture_is_a_managed_project_with_every_shipped_block_but_hackathon_and_sidecar(
    fixtures,
):
    wrong = {name: _not_managed_as_shipped(root) for name, root in fixtures.items()}

    assert {name: why for name, why in wrong.items() if why} == {}


def test_every_fixture_is_on_a_named_branch_other_than_its_default(fixtures):
    branches = {name: _branch(root) for name, root in fixtures.items()}

    assert {n: b for n, b in branches.items() if not b or b in DEFAULT_BRANCHES} == {}, branches


def test_every_fixture_has_a_git_identity_a_session_can_read(fixtures):
    identities = {
        name: (_git(root, "config", "user.name"), _git(root, "config", "user.email"))
        for name, root in fixtures.items()
    }

    assert all(name and email for name, email in identities.values()), identities


def test_every_fixtures_decision_directory_holds_two_listed_older_habit_records(fixtures):
    counts = {name: len(_listed_older_habit_records(root)) for name, root in fixtures.items()}

    assert {name: n for name, n in counts.items() if n < 2} == {}, counts


def test_no_fixture_holds_a_draft_directory(fixtures):
    with_drafts = [name for name, root in fixtures.items() if (root / DRAFTS_DIR).exists()]

    assert with_drafts == []


def test_no_fixture_file_carries_a_line_of_the_moved_rule_or_a_declared_phrase(kit, fixtures):
    lines = rule_lines((REPO_ROOT / DECISION_RULE).read_text(encoding="utf-8"))
    needles = lines | {p.casefold() for p in declared_phrases(kit.payload)}

    carried = {name: _files_carrying(root, needles) for name, root in fixtures.items()}

    assert {name: hits for name, hits in carried.items() if hits} == {}


@pytest.mark.parametrize("check", DECISION_CHECKS)
def test_a_record_scripted_as_the_rule_says_grades_passed_in_every_fixture(
    kit, fixtures, tmp_path, check
):
    grades = {
        name: _graded_with_a_conforming_record(kit.declared, check, root, tmp_path / name)
        for name, root in fixtures.items()
    }

    assert {name: g for name, g in grades.items() if g.outcome != "passed"} == {}


# -- Helpers ----------------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    """Git as a session in the fixture would run it: no global or system configuration."""
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "ANTHROPIC_"))
    }
    env.update(HOME=str(root.parent / "sandbox-home"), GIT_CONFIG_GLOBAL=os.devnull)
    env.update(GIT_CONFIG_NOSYSTEM="1")
    result = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True)
    return result.stdout.strip()


def _branch(root: Path) -> str:
    return _git(root, "symbolic-ref", "--short", "HEAD")


def _not_managed_as_shipped(root: Path) -> list[str]:
    """What keeps `root` from being a managed project carrying every shipped block but the left-out."""
    claude_md = root / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8") if claude_md.is_file() else ""
    blocks = {p.name: p.read_text(encoding="utf-8").strip() for p in SHIPPED_BLOCKS.glob("*.md")}
    why = [
        f"lacks the {name} block"
        for name, block in blocks.items()
        if name not in LEFT_OUT_BLOCKS and block not in text
    ]
    why += [f"carries the {name} block" for name in LEFT_OUT_BLOCKS if blocks[name] in text]
    why += [] if (root / ".ai-state").is_dir() else ["has no state directory"]
    return why


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    return yaml.safe_load(text.split("\n---", 2)[0][4:]) or {}


def _listed_older_habit_records(root: Path) -> list[str]:
    """Records at the top of the decision directory named by a number and a slug, carrying a
    numbered id, no category and no disconfirmation, that the decision index lists."""
    index = root / INDEX_FILE
    listed = index.read_text(encoding="utf-8") if index.is_file() else ""
    records = sorted((root / DECISIONS_DIR).glob("*.md"))
    return [
        record.name
        for record in records
        if OLDER_HABIT_NAME.fullmatch(record.name)
        and NUMBERED_ID.fullmatch(str(_frontmatter(record).get("id", "")))
        and "category" not in _frontmatter(record)
        and "disconfirmation" not in record.read_text(encoding="utf-8").casefold()
        and (record.name in listed or str(_frontmatter(record)["id"]) in listed)
    ]


def _files_carrying(root: Path, needles: frozenset[str] | set[str]) -> list[tuple[str, str]]:
    files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts]
    return [
        (path.relative_to(root).as_posix(), needle)
        for path in files
        for needle in needles
        if needle in path.read_text(encoding="utf-8", errors="replace").casefold()
    ]


def _graded_with_a_conforming_record(
    declared: Declared, check: str, fixture: Path, end_state: Path
) -> DecisionGrade:
    """Copy the fixture, leave one draft fragment written as the rule says, and grade it.

    The fragment's user is the fixture's git user name in lower-case words joined by hyphens,
    and its branch is the fixture's branch segment.
    """
    shutil.copytree(fixture, end_state, symlinks=True)
    user = re.sub(r"[^a-z0-9]+", "-", _git(fixture, "config", "user.name").lower()).strip("-")
    name = fragment_name(user=user, branch=branch_segment(_branch(fixture)))
    leave(end_state, with_changes(conforming(), relpath=f"{DRAFTS_DIR}/{name}"))
    return grade_decision_end_state(declared, check, fixture, end_state)
