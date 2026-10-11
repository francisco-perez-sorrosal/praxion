"""Shape checks for the plugin trigger-eval suite shipped under `evals/`.

`claude plugin eval` runs the suite live; these tests pin only what the files can show: where the
cases live, that each skill has its cases, that every case loads under the runner's rules, and the
two invariants a trigger case depends on -- a scored grader (a case whose graders are all indicators
is scored on the indicator) and, for a must-not-invoke case, a zero ceiling scored in both arms.
Cases are found through the driver the acceptance scenarios use, so the two cannot disagree about
what counts as a case.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.acceptance.drivers.plugin_eval import (
    EVAL_DIR,
    REPO_ROOT,
    plugin_eval_cases,
    skill_grader_settings,
)

PROMPT_KEYS = {"description", "tags", "allowed_tools", "max_turns", "expected_outcome"}

# (skill, case directory name)
SHOULD_TRIGGER = [
    ("test", "test-runs-what-a-change-needs"),
    ("skill-crafting", "skill-crafting-user-invoked-argument"),
]
MUST_NOT_INVOKE = [
    ("test", "test-near-miss-test-design"),
    ("co", "co-commit-message-request"),
]
EXPECTED = SHOULD_TRIGGER + MUST_NOT_INVOKE
CASE_IDS = [name for _, name in EXPECTED]


def _case(skill: str, name: str) -> Path:
    return next(case for case in plugin_eval_cases(skill) if case.name == name)


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def _graders(case: Path) -> list[dict]:
    return [_frontmatter(path) for path in sorted((case / "graders").glob("*.md"))]


def test_suite_lives_under_evals_outside_every_skills_directory() -> None:
    prompts = sorted((REPO_ROOT / EVAL_DIR).rglob("prompt.md"))
    relatives = [prompt.relative_to(REPO_ROOT).parts for prompt in prompts]

    assert relatives, "no eval case found"
    assert all("skills" not in parts for parts in relatives)
    assert not list((REPO_ROOT / "skills").rglob("prompt.md"))


@pytest.mark.parametrize("skill", sorted({skill for skill, _ in EXPECTED}))
def test_each_skill_has_exactly_its_cases(skill: str) -> None:
    found = {case.name for case in plugin_eval_cases(skill)}

    assert found == {name for s, name in EXPECTED if s == skill}


@pytest.mark.parametrize(("skill", "name"), EXPECTED, ids=CASE_IDS)
def test_case_prompt_carries_the_frontmatter_the_runner_and_authors_need(
    skill: str, name: str
) -> None:
    frontmatter = _frontmatter(_case(skill, name) / "prompt.md")

    assert PROMPT_KEYS <= set(frontmatter)
    assert frontmatter["tags"] == ["skill-triggering"]
    assert frontmatter["allowed_tools"] == ["Read", "Glob", "Grep", "Skill"]
    assert frontmatter["max_turns"] == 8


@pytest.mark.parametrize(("skill", "name"), EXPECTED, ids=CASE_IDS)
def test_case_prompt_is_phrased_as_a_user_request_that_never_names_the_skill(
    skill: str, name: str
) -> None:
    body = _body(_case(skill, name) / "prompt.md")

    assert body.strip()
    assert f"/{skill}" not in body
    assert f"`{skill}`" not in body


@pytest.mark.parametrize(("skill", "name"), EXPECTED, ids=CASE_IDS)
def test_case_has_a_scored_grader_on_the_final_answer(skill: str, name: str) -> None:
    scored = [
        grader
        for grader in _graders(_case(skill, name))
        if grader["type"] == "regex" and grader.get("target", "last_message") == "last_message"
    ]

    assert scored
    assert all(re.compile(grader["pattern"]) for grader in scored)


@pytest.mark.parametrize(("skill", "name"), MUST_NOT_INVOKE, ids=[n for _, n in MUST_NOT_INVOKE])
def test_must_not_invoke_case_has_a_zero_ceiling_scored_in_both_arms(skill: str, name: str) -> None:
    settings = skill_grader_settings(_case(skill, name), skill)

    assert (settings.min, settings.max, settings.arm) == (0, 0, "both")


@pytest.mark.parametrize(("skill", "name"), SHOULD_TRIGGER, ids=[n for _, n in SHOULD_TRIGGER])
def test_should_trigger_case_leaves_the_skill_grader_a_plugin_fired_indicator(
    skill: str, name: str
) -> None:
    settings = skill_grader_settings(_case(skill, name), skill)

    assert (settings.min, settings.max, settings.arm) == (None, None, None)


@pytest.mark.parametrize(("skill", "name"), EXPECTED, ids=CASE_IDS)
def test_skill_grader_matches_the_bare_and_plugin_qualified_name_and_no_other_skill(
    skill: str, name: str
) -> None:
    case = _case(skill, name)
    skill_grader = next(
        g for g in _graders(case) if g["type"] == "tool_used" and g["tool"] == "Skill"
    )
    pattern = re.compile(skill_grader["input_match"])

    assert pattern.search(f'{{"skill":"{skill}"}}')
    assert pattern.search(f'{{"skill":"praxion:{skill}"}}')
    assert not pattern.search(f'{{"skill":"{skill}-other"}}')
    assert not pattern.search('{"skill":"unrelated"}')


def test_eval_results_are_gitignored() -> None:
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert f"{EVAL_DIR}/results/" in lines
