"""A graded session carries its task's own mode, not one re-derived from a slug.

A pool task's slug is spelled by no kit, so ``mode_of_slug`` reads it as modeless while the task
(and the record of the run) says ``paired``; the launch hands the task's mode to the evidence.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praxion_evals.adherence import grade, refactoring_tasks, session_launch, tasks
from praxion_evals.adherence.axis_runs import DEFAULT_RUN
from praxion_evals.adherence.model import ROLES
from tests.test_adherence_grade import SLUG, _evidence, repo  # noqa: F401  (repo is a fixture)

SEED = 0


@pytest.mark.parametrize("role", ROLES)
def test_a_default_tasks_mode_is_the_one_its_slug_resolves_to(role):
    for task in tasks.generate(role, SEED, tasks.list_size(role)):
        assert task.mode == tasks.mode_of_slug(role, task.slug), task.task_id


def test_a_pool_task_of_the_test_engineer_is_paired_though_its_slug_resolves_to_no_mode():
    task = refactoring_tasks.pool_tasks("test-engineer", SEED)[0]

    assert task.mode == "paired"
    assert tasks.mode_of_slug("test-engineer", task.slug) is None


def test_the_mode_given_to_the_evidence_is_the_one_it_carries(repo, tmp_path):  # noqa: F811
    task = refactoring_tasks.pool_tasks("test-engineer", SEED)[0]

    evidence = _evidence(
        repo,
        tmp_path,
        {"role": "test-engineer"},
        role="test-engineer",
        slug=task.slug,
        mode="paired",
    )

    assert evidence.facts.mode == "paired"


def test_a_mode_left_out_is_resolved_from_the_slug_as_before(repo, tmp_path):  # noqa: F811
    evidence = _evidence(repo, tmp_path, slug=SLUG)

    assert evidence.facts.mode is None


def test_the_launch_hands_the_graders_the_tasks_own_mode(monkeypatch, tmp_path):
    task = refactoring_tasks.pool_tasks("test-engineer", SEED)[0]
    seen = {}
    monkeypatch.setattr(grade, "evidence_from_recording", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(grade, "kernel_adopted", lambda *_: False)
    build = SimpleNamespace(arm="full", copy_root=tmp_path / "copy")
    run = SimpleNamespace(stdout="", exit_code=0, timed_out=False)

    session_launch._evidence(
        SimpleNamespace(judge=None, axis_run=DEFAULT_RUN),
        task,
        build,
        None,
        tmp_path / "sandbox",
        run,
        "abc",
    )

    assert seen["mode"] == "paired"
