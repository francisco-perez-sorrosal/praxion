"""Staging a pool task: the starting tree and the plan inputs, never the grader's answer key."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from praxion_evals.adherence import axis_runs, tasks
from praxion_evals.adherence import refactoring_tasks as pool
from praxion_evals.adherence.checks_refactoring import MANIFEST

SEED = 0
POOL_ROLES = tuple(pool.POOLS)


def _first_task_of_each_template(role: str):
    seen: dict[str, object] = {}
    for task in pool.pool_tasks(role, SEED):
        seen.setdefault(task.template_id, task)
    return list(seen.values())


EVERY_TEMPLATE = [
    pytest.param(task, id=f"{task.role}:{task.template_id}")
    for role in POOL_ROLES
    for task in _first_task_of_each_template(role)
]


def _template_dir(task) -> Path:
    return tasks.FIXTURES_DIR / task.role / pool.POOL_DIRNAME / task.template_id


def _files(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` outside ``.git``, by relative path."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _git(root: Path, *args: str) -> str:
    return tasks._git(root, *args)


@pytest.fixture
def pool_dir(tmp_path, monkeypatch):
    clone = tmp_path / "fixtures"
    shutil.copytree(tasks.FIXTURES_DIR, clone)
    monkeypatch.setattr(tasks, "FIXTURES_DIR", clone)
    return clone


@pytest.mark.parametrize("task", EVERY_TEMPLATE)
def test_the_workspace_holds_the_starting_tree_and_the_plan_inputs_on_one_commit(task, tmp_path):
    dest = tmp_path / "scratch"

    commit = pool.stage_pool_task(task, dest)

    start = _template_dir(task) / pool.START_DIRNAME
    held = _files(dest)
    for path in sorted(start.rglob("*")):
        relative = path.relative_to(start).as_posix().removesuffix(tasks.TEMPLATE_SUFFIX)
        if path.is_file() and relative != MANIFEST:
            assert held[relative] == path.read_bytes(), relative
    plan_dir = f"{tasks.AI_WORK}/{task.slug}/"
    assert {pool.PLAN_FILE, task_brief(task)} <= {
        name.removeprefix(plan_dir) for name in held if name.startswith(plan_dir)
    }
    assert _git(dest, "rev-list", "--count", "HEAD").strip() == "1"
    assert _git(dest, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert _git(dest, "rev-parse", "HEAD").strip() == commit
    assert _git(dest, "status", "--porcelain") == ""


def task_brief(task) -> str:
    return pool.POOLS[task.role].brief


@pytest.mark.parametrize("task", EVERY_TEMPLATE)
def test_no_file_of_an_end_state_or_the_manifest_is_anywhere_under_the_workspace(task, tmp_path):
    dest = tmp_path / "scratch"
    pool.stage_pool_task(task, dest)

    template_dir = _template_dir(task)
    start_files = _files(template_dir / pool.START_DIRNAME)
    answers = _files(template_dir / pool.ANSWER_DIRNAME)
    # An end-state file the starting tree already holds is no leak; one it changes or adds is.
    differing = {
        data
        for relative, data in answers.items()
        if start_files.get(relative.split("/", 1)[1]) != data
    }
    walked = list(dest.rglob("*"))

    assert differing, "the template holds no end state that differs from its start"
    assert not [p for p in walked if pool.ANSWER_DIRNAME in p.relative_to(dest).parts]
    assert not [p for p in walked if p.name == MANIFEST]
    assert not [p for p in walked if p.is_file() and p.read_bytes() in differing]


@pytest.mark.parametrize("task", EVERY_TEMPLATE)
def test_a_staged_input_leaves_no_token_unfilled(task, tmp_path):
    dest = tmp_path / "scratch"
    pool.stage_pool_task(task, dest)

    plan_dir = dest / tasks.AI_WORK / task.slug
    assert all("@@" not in path.read_text(encoding="utf-8") for path in plan_dir.rglob("*.md"))


@pytest.mark.parametrize("role", POOL_ROLES)
def test_the_instruction_file_states_the_convention_as_the_default_staging_does(role, tmp_path):
    task = _first_task_of_each_template(role)[0]
    pool.stage_pool_task(task, tmp_path / "scratch")

    template = (tasks.REPOS_DIR / task.fixture_id / tasks.INSTRUCTIONS_TEMPLATE).read_text()
    expected = template.replace("@@CONVENTION@@", task.project_convention.text)
    assert (tmp_path / "scratch" / tasks.INSTRUCTIONS_FILE).read_text() == expected


@pytest.mark.parametrize("task", EVERY_TEMPLATE)
def test_a_confined_roles_repository_points_git_at_no_global_ignore_file(task, tmp_path):
    dest = tmp_path / "scratch"
    pool.stage_pool_task(task, dest)

    local = subprocess.run(
        ["git", "-C", str(dest), "config", "--local", "--get", "core.excludesFile"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert task.role in tasks.CONFINED_ROLES
    assert local.stdout.strip() == os.devnull


@pytest.mark.parametrize(
    "extra",
    ["notes/end_states/clean/a.py", "notes/refactoring.toml"],
)
def test_a_template_that_declares_grader_data_as_an_input_is_refused(extra, pool_dir, tmp_path):
    task = _first_task_of_each_template("implementer")[0]
    declared = pool_dir / task.role / pool.POOL_DIRNAME / task.template_id / extra
    declared.parent.mkdir(parents=True, exist_ok=True)
    declared.write_text("leak", encoding="utf-8")
    dest = tmp_path / "scratch"

    with pytest.raises(ValueError, match="declares"):
        pool.stage_pool_task(task, dest)

    assert not dest.exists()


def test_a_destination_that_already_holds_files_is_refused(tmp_path):
    task = _first_task_of_each_template("implementer")[0]
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "stale.txt").write_text("x")

    with pytest.raises(FileExistsError):
        pool.stage_pool_task(task, tmp_path / "scratch")


def test_the_new_axis_stages_a_pool_task_and_the_default_axis_keeps_its_staging():
    assert axis_runs.axis_run("refactoring-delivery").stage is pool.stage_pool_task
    assert axis_runs.DEFAULT_RUN.stage is tasks.build_scratch_repo
