"""Behavioral tests for `skills/skill-crafting/scripts/init_skill.py`.

The scaffold shares the validator's name check, so a rejected name never leaves a directory
behind, and it declares both invocation controls at their defaults so the choice is visible
from the first edit. Every scaffold lands under a pytest temp directory, never under `skills/`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
NAME = "fresh-skill"


def _load(module_name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        f"_{module_name}_under_test", SCRIPTS / f"{module_name}.py"
    )
    assert spec is not None, f"cannot load {module_name}"
    assert spec.loader is not None, f"cannot load {module_name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


init_skill = _load("init_skill")
validate = _load("validate")


def scaffold_text(tmp_path: Path) -> str:
    assert init_skill.init_skill(NAME, tmp_path) == 0
    return (tmp_path / NAME / "SKILL.md").read_text(encoding="utf-8")


def test_an_invalid_name_is_rejected_with_an_error_and_creates_no_directory(tmp_path, capsys):
    exit_code = init_skill.init_skill("Bad_Name", tmp_path)

    assert exit_code == 1
    assert capsys.readouterr().err.startswith("Error: ")
    assert list(tmp_path.iterdir()) == []


def test_a_name_with_consecutive_hyphens_gets_the_message_naming_that_defect(tmp_path, capsys):
    exit_code = init_skill.init_skill("fresh--skill", tmp_path)

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "consecutive hyphens" in err
    assert "lowercase" not in err
    assert list(tmp_path.iterdir()) == []


def test_each_broken_name_rule_is_reported_on_its_own_error_line(tmp_path, capsys):
    exit_code = init_skill.init_skill("A--" + "b" * 70, tmp_path)

    lines = capsys.readouterr().err.splitlines()
    assert exit_code == 1
    assert len(lines) == 3
    assert all(line.startswith("Error: ") for line in lines)


@pytest.mark.parametrize(
    ("key", "default"), [("disable-model-invocation", "false"), ("user-invocable", "true")]
)
def test_the_template_declares_each_invocation_control_at_its_default(tmp_path, key, default):
    frontmatter = scaffold_text(tmp_path).split("---", 2)[1].splitlines()

    assert f"{key}: {default}" in frontmatter


def test_the_template_explains_the_invocation_choices_in_its_own_section(tmp_path):
    text = scaffold_text(tmp_path)

    assert "\n## Invocation Mode\n" in text


def test_a_fresh_scaffold_validates_with_no_error_and_no_warning(tmp_path):
    assert init_skill.init_skill(NAME, tmp_path) == 0

    report = validate.check_skill(tmp_path / NAME)

    assert report.errors == ()
    assert report.warnings == ()
