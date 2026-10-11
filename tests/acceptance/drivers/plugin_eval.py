"""Driver for the `claude plugin eval` cases that probe whether a skill triggers.

Layout the runner reads (per `claude plugin eval --help`): `<repo>/evals/**/` case directories,
each holding a `prompt.md` and `graders/*.md`. A grader file is Markdown with YAML frontmatter.
A case probes a skill when one of its graders is `type: tool_used`, `tool: Skill`, with an
`input_match` regular expression that matches the `Skill` tool input naming that skill, bare
(`{"skill": "test"}`) and plugin-qualified (`{"skill": "praxion:test"}`).

A must-not-invoke case carries a zero ceiling on that grader (`min == max == 0`) and runs in both
arms (`arm == both`); `skill_grader_settings` exposes the three fields so a scenario can say so.

The repository root is found from this file's location, as the neighbouring drivers do; pass
`repo` to read a layout elsewhere. Nothing here imports the system under
test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

EVAL_DIR = "evals"
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class SkillGraderSettings:
    """The ceiling and arm of a case's `Skill` grader; `None` where the grader leaves it unset."""

    min: int | None
    max: int | None
    arm: str | None


def plugin_eval_cases(skill: str, repo: Path | None = None) -> list[Path]:
    """Every case directory under `<repo>/evals/` that probes whether `skill` triggers, sorted."""
    eval_root = (repo or REPO_ROOT) / EVAL_DIR
    if not eval_root.is_dir():
        return []
    return sorted(
        prompt.parent
        for prompt in eval_root.rglob("prompt.md")
        if _skill_grader(prompt.parent, skill) is not None
    )


def skill_grader_settings(case: Path, skill: str) -> SkillGraderSettings:
    """The `min`, `max` and `arm` of the case's grader on `skill`'s `Skill` tool call."""
    grader = _skill_grader(case, skill)
    if grader is None:
        raise AssertionError(f"{case} has no Skill grader naming {skill!r}")
    return SkillGraderSettings(grader.get("min"), grader.get("max"), grader.get("arm"))


def _skill_grader(case: Path, skill: str) -> dict | None:
    for path in sorted((case / "graders").glob("*.md")):
        grader = _frontmatter(path)
        if grader.get("type") == "tool_used" and grader.get("tool") == "Skill":
            if _names_skill(grader.get("input_match"), skill):
                return grader
    return None


def _names_skill(input_match: object, skill: str) -> bool:
    if not isinstance(input_match, str):
        return False
    try:
        pattern = re.compile(input_match)
    except re.error:
        return False
    return all(pattern.search(f'{{"skill": "{name}"}}') for name in (skill, f"praxion:{skill}"))


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    loaded = yaml.safe_load(text.split("---", 2)[1])
    return loaded if isinstance(loaded, dict) else {}
