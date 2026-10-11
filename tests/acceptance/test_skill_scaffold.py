"""A freshly scaffolded skill makes its invocation mode a visible choice and validates clean."""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.skill_pages import frontmatter
from tests.acceptance.drivers.skill_validator import scaffold, validate

NAME = "fresh-skill"


@pytest.fixture
def scaffolded(tmp_path):
    run = scaffold(NAME, tmp_path)
    skill_md = tmp_path / NAME / "SKILL.md"
    assert run.exit_code == 0, run.describe()
    assert skill_md.is_file(), run.describe()
    return tmp_path / NAME


def frontmatter_lines(skill_dir) -> list[str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    return text.split("---", 2)[1].splitlines()


@pytest.mark.parametrize(
    ("key", "default"), [("disable-model-invocation", False), ("user-invocable", True)]
)
def test_the_scaffold_declares_each_invocation_control_explicitly_at_its_default(
    scaffolded, key, default
):
    declared = [ln for ln in frontmatter_lines(scaffolded) if ln.startswith(f"{key}:")]
    meta = frontmatter((scaffolded / "SKILL.md").read_text(encoding="utf-8"))

    assert declared, f"the scaffold's frontmatter does not declare {key}"
    assert meta.get(key) is default, f"{key} is {meta.get(key)!r}, not its default {default!r}"


@pytest.mark.parametrize(
    ("choice", "patterns"),
    [
        (
            "when to make the skill user-only",
            (
                r"disable-model-invocation|user[- ]only",
                r"side[- ]effect|only the user|user[- ]only",
            ),
        ),
        ("when to hide the skill from the menu", (r"user-invocable", r"menu")),
        (
            "how the choice changes the description's reader",
            (r"description", r"reader|listing|model"),
        ),
    ],
)
def test_the_scaffold_explains_each_invocation_choice(scaffolded, choice, patterns):
    text = (scaffolded / "SKILL.md").read_text(encoding="utf-8").replace("`", "")

    assert all(re.search(p, text, re.IGNORECASE) for p in patterns), (
        f"the scaffold gives no guidance on {choice}"
    )


def test_a_fresh_scaffold_validates_with_no_error_and_no_warning(scaffolded):
    run = validate(scaffolded)

    assert run.exit_code == 0, run.describe()
    assert not run.errors(), run.describe()
    assert not run.warnings(), run.describe()


def test_the_scaffold_rejects_a_name_with_consecutive_hyphens_naming_that_defect(tmp_path):
    run = scaffold("fresh--skill", tmp_path)
    naming = [e for e in run.errors() if re.search(r"consecutive hyphen", e, re.IGNORECASE)]

    assert run.exit_code != 0, run.describe()
    assert not (tmp_path / "fresh--skill").exists(), "the scaffold created the rejected skill"
    assert naming, f"no error names consecutive hyphens; {run.describe()}"
    assert not [e for e in naming if re.search(r"lowercase|leading|trailing|uppercase", e, re.I)], (
        f"the message blames rules the name does not break: {naming}"
    )
