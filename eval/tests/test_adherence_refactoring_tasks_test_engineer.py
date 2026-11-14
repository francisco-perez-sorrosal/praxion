"""The test-engineer's refactoring pool: two ``pre-refactor`` templates, planned nowhere by default."""

from __future__ import annotations

import re
import shutil

import pytest

from praxion_evals.adherence import refactoring_tasks as pool
from praxion_evals.adherence import tasks
from praxion_evals.adherence.model import ROLE_MODES

SEED = 0
ROLE = "test-engineer"
POOL_TEMPLATES = {
    "refactoring-characterize": "ledger-cli",
    "refactoring-characterize-notes-service": "notes-service",
}
MARKER = re.compile(r"\[\s*phase\s*:\s*refactoring\s*\]", re.IGNORECASE)
PLAN_HEADING = re.compile(r"^### Step \d+: .*\[Phase: Refactoring\]", re.MULTILINE)


@pytest.fixture
def pool_dir(tmp_path, monkeypatch):
    clone = tmp_path / "fixtures"
    shutil.copytree(tasks.FIXTURES_DIR, clone)
    monkeypatch.setattr(tasks, "FIXTURES_DIR", clone)
    return clone / ROLE / pool.POOL_DIRNAME


def test_the_pool_holds_two_pre_refactor_templates_with_the_marker_in_their_plan_headings() -> None:
    templates = pool.pool_templates(ROLE)

    assert {t.template_id for t in templates} == set(POOL_TEMPLATES)
    for template in templates:
        inputs = dict(template.inputs)
        assert PLAN_HEADING.search(inputs["IMPLEMENTATION_PLAN.md"]), template.template_id
        assert MARKER.search(inputs["WIP.md"]), template.template_id


def test_each_pool_task_is_delegated_in_pre_refactor_mode_with_the_marker() -> None:
    planned = pool.pool_tasks(ROLE, SEED)

    assert {t.template_id for t in planned} == set(POOL_TEMPLATES)
    assert all(POOL_TEMPLATES[t.template_id] == t.fixture_id for t in planned)
    assert all(MARKER.search(t.main_prompt) for t in planned)
    assert all("Mode: pre-refactor" in t.main_prompt for t in planned)
    assert all(f".ai-work/{t.slug}/WIP.md" in t.main_prompt for t in planned)
    assert len({t.task_id for t in planned}) == len(planned)


def test_a_pool_of_one_template_is_refused(pool_dir) -> None:
    shutil.rmtree(sorted(pool_dir.iterdir())[-1])

    with pytest.raises(ValueError, match="1 refactoring templates, fewer than 2"):
        pool.pool_templates(ROLE)


def test_the_roles_modes_and_default_plan_are_untouched_by_the_pool() -> None:
    modes = ROLE_MODES[ROLE]
    default_ids = {t.template_id for t in tasks.kit_for(ROLE).templates}
    planned = tasks.generate(ROLE, SEED, tasks.list_size(ROLE))

    assert modes.covered == ("acceptance-design", "paired")
    assert modes.unmeasured == ("pre-refactor",)
    assert not default_ids & set(POOL_TEMPLATES)
    assert not any(MARKER.search(t.main_prompt) for t in planned)
