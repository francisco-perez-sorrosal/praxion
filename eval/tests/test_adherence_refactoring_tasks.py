"""The refactoring pool: marked tasks of its own, planned nowhere by default."""

from __future__ import annotations

import re
import shutil

import pytest

from praxion_evals.adherence import refactoring_tasks as pool
from praxion_evals.adherence import role_kits, tasks
from praxion_evals.adherence.model import ROLES

SEED = 0
ROLE = "implementer"
POOL_TEMPLATES = {
    "refactoring-extract-module": "ledger-cli",
    "refactoring-extract-module-notes-service": "notes-service",
}
MARKER = re.compile(r"\[\s*phase\s*:\s*refactoring\s*\]", re.IGNORECASE)
PLAN_HEADING = re.compile(r"^### Step \d+: .*\[Phase: Refactoring\]", re.MULTILINE)


@pytest.fixture
def pool_dir(tmp_path, monkeypatch):
    clone = tmp_path / "fixtures"
    shutil.copytree(tasks.FIXTURES_DIR, clone)
    monkeypatch.setattr(tasks, "FIXTURES_DIR", clone)
    return clone / ROLE / pool.POOL_DIRNAME


def test_the_pool_holds_the_two_implementer_templates() -> None:
    assert {t.template_id for t in pool.pool_templates(ROLE)} == set(POOL_TEMPLATES)


def test_each_template_carries_the_marker_in_its_plan_heading_and_its_brief() -> None:
    for template in pool.pool_templates(ROLE):
        inputs = dict(template.inputs)

        assert PLAN_HEADING.search(inputs["IMPLEMENTATION_PLAN.md"]), template.template_id
        assert MARKER.search(inputs["WIP.md"]), template.template_id


def test_each_pool_task_is_delegated_with_the_marker_in_its_templates_fixture() -> None:
    planned = pool.pool_tasks(ROLE, SEED)

    assert {t.template_id for t in planned} == set(POOL_TEMPLATES)
    assert all(MARKER.search(t.main_prompt) for t in planned)
    assert all(POOL_TEMPLATES[t.template_id] == t.fixture_id for t in planned)
    assert len({t.task_id for t in planned}) == len(planned)


def test_a_pool_task_reads_the_brief_and_slug_the_default_tasks_do() -> None:
    task = pool.pool_tasks(ROLE, SEED)[0]

    assert f".ai-work/{task.slug}/WIP.md" in task.main_prompt
    assert task.slug == tasks.task_slug(task.template_id, task.fixture_id)
    assert task.project_convention == tasks.PILOT_CONVENTIONS[ROLE]


def test_a_pool_of_one_template_is_refused(pool_dir) -> None:
    shutil.rmtree(sorted(pool_dir.iterdir())[-1])

    with pytest.raises(ValueError, match="1 refactoring templates, fewer than 2"):
        pool.pool_templates(ROLE)


def test_a_template_the_pool_does_not_declare_is_refused(pool_dir) -> None:
    shutil.copytree(pool_dir / "refactoring-extract-module", pool_dir / "refactoring-extra")

    with pytest.raises(ValueError, match="differ from"):
        pool.pool_templates(ROLE)


@pytest.mark.parametrize("name", ["WIP.md", "IMPLEMENTATION_PLAN.md"])
def test_a_template_whose_input_lacks_the_marker_is_refused(pool_dir, name) -> None:
    path = pool_dir / "refactoring-extract-module" / name
    path.write_text(path.read_text(encoding="utf-8").replace(pool.MARKER, ""), encoding="utf-8")

    with pytest.raises(ValueError, match=f"{name} lacks"):
        pool.pool_templates(ROLE)


def test_a_role_without_a_pool_is_refused() -> None:
    with pytest.raises(ValueError, match="no refactoring pool"):
        pool.pool_tasks("sentinel", SEED)


def test_the_default_implementer_kit_gains_no_refactoring_template_or_marker() -> None:
    kit = tasks.kit_for(ROLE)

    assert not any("refactoring" in t.template_id for t in kit.templates)
    assert not MARKER.search(role_kits.ROLE_KITS[ROLE].prompt)


@pytest.mark.parametrize(
    "role", [r for r in ROLES if r in role_kits.ROLE_KITS or r in tasks.MODED_KITS]
)
def test_no_default_plan_lists_a_refactoring_task_or_a_marked_prompt(role: str) -> None:
    planned = tasks.generate(role, SEED, tasks.list_size(role))

    assert not any("refactoring" in t.template_id or MARKER.search(t.main_prompt) for t in planned)
