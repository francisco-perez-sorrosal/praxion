"""The refactoring-mode task pool: tasks a role is asked only on the ``refactoring-delivery`` axis.

A role's pool is a directory of its own, ``fixtures/<role>/refactoring``, and never part of the
role's default plan. A template under ``templates/`` joins ``tasks.kit_for`` and with it every
default run, and a new template there changes the plan of the default pool and the template the
standing eval tests mutate; the pool is loaded and built here, through ``tasks``' own template
loader, variant mapping, ids and slugs, so a pool task is shaped exactly like a default one.

What marks a pool task is the words it is delegated in: the prompt names the refactoring step, and
the plan and the brief the role reads carry the same marker, which is what the axis measures.

A pool template also holds the grader's data, ``start/`` and ``end_states/``, and ``tasks``' loader
hands a session every file under a template directory. ``stage_pool_task`` is the staging that
keeps the answer key out of what the session can read.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from praxion_evals.adherence import tasks
from praxion_evals.adherence.checks_refactoring import MANIFEST
from praxion_evals.adherence.confinement import CONFINED_ROLES
from praxion_evals.adherence.model import KitMode, Role, TaskSpec
from praxion_evals.adherence.tasks import Template

POOL_DIRNAME = "refactoring"
PLAN_FILE = "IMPLEMENTATION_PLAN.md"
MARKER = "[Phase: Refactoring]"
MIN_POOL_TEMPLATES = 2
VARIANTS = ("ambiguity", "conflict", "early-stop")
_PLANT_TOKEN = "@@PLANT@@"
START_DIRNAME = "start"  # the starting tree: the scratch repository's whole content
ANSWER_DIRNAME = "end_states"  # the clean end state and one violating tree per checklist item


@dataclass(frozen=True)
class RefactoringPool:
    brief: str  # the input file the prompt points the role at
    prompt: str  # with ``{slug}`` and ``{brief}`` slots
    fixture_of: Mapping[str, str]  # template id -> the one ``fixtures/repos`` entry it runs in
    # A role with modes cannot plan a task without a covered mode, and ``pre-refactor`` is the
    # pool's label, not one of them: the covered mode the pool's tasks are shaped like.
    task_mode: KitMode | None = None


POOLS: Mapping[Role, RefactoringPool] = MappingProxyType(
    {
        "implementer": RefactoringPool(
            brief="WIP.md",
            prompt=(
                "Task slug: {slug}. Implement the current step in .ai-work/{slug}/{brief}; it "
                f"is a {MARKER} step, so restructure without changing behaviour. The plan and "
                "the learnings are in the same directory and the change goes in the repository "
                "you are in."
            ),
            fixture_of=MappingProxyType(
                {
                    "refactoring-extract-module": "ledger-cli",
                    "refactoring-extract-module-notes-service": "notes-service",
                }
            ),
        ),
        "test-engineer": RefactoringPool(
            brief="WIP.md",
            prompt=(
                "Task slug: {slug}. Mode: pre-refactor. Write the characterization tests for "
                f"the {MARKER} step assigned in .ai-work/{{slug}}/{{brief}}, before any structural "
                "change; the plan is in the same directory and the tests go in the repository "
                "you are in."
            ),
            fixture_of=MappingProxyType(
                {
                    "refactoring-characterize": "ledger-cli",
                    "refactoring-characterize-notes-service": "notes-service",
                }
            ),
            task_mode="paired",
        ),
    }
)


def pool_tasks(role: Role, seed: int) -> list[TaskSpec]:
    """Every task of the role's pool: each template's variants, in its one fixture."""
    pool = _pool_of(role)
    return [
        _make_task(role, pool, template, label, seed)
        for template in pool_templates(role)
        for label in VARIANTS
    ]


def planned_pool(role: Role, seed: int, count: int) -> list[TaskSpec]:
    """The role's pool in the seed's order, at most ``count`` tasks, each task once.

    One task of every template comes before any template repeats, so a run capped at two
    tasks still holds two templates; the pool is never mixed with the role's default tasks.
    """
    pool = _pool_of(role)
    per_template = [
        [
            _make_task(role, pool, template, label, seed)
            for label in tasks._rng(seed, role, template.template_id).sample(
                VARIANTS, len(VARIANTS)
            )
        ]
        for template in tasks._shuffled(pool_templates(role), seed, role)
    ]
    return list(tasks._round_robin(per_template))[:count]


def pool_templates(role: Role) -> tuple[Template, ...]:
    """The templates under ``fixtures/<role>/refactoring``, refused at load unless they hold.

    The pool holds at least ``MIN_POOL_TEMPLATES`` templates, exactly those it declares a fixture
    for, each with a brief that takes the plant and a brief and a plan that carry the marker.
    """
    pool = _pool_of(role)
    root = tasks.FIXTURES_DIR / role / POOL_DIRNAME
    found = tuple(tasks._load_template(path) for path in sorted(root.iterdir()) if path.is_dir())
    if len(found) < MIN_POOL_TEMPLATES:
        raise ValueError(
            f"{role} has {len(found)} refactoring templates, fewer than {MIN_POOL_TEMPLATES}"
        )
    if {t.template_id for t in found} != set(pool.fixture_of):
        raise ValueError(f"{role} refactoring templates differ from the {sorted(pool.fixture_of)}")
    for template in found:
        _require_marked(role, pool, template)
    return found


def stage_pool_task(task: TaskSpec, dest: Path, page_url: str | None = None) -> str:
    """Make ``dest`` a git repository holding the template's starting tree and plan inputs.

    The signature and the repository are ``tasks.build_scratch_repo``'s (the same helpers build
    the instruction file, the overlays and the one fixture commit), except that the tree comes
    from ``start/`` and only the template's plan inputs go under ``.ai-work/<slug>/``. Neither
    ``end_states/`` nor the grader's manifest is copied anywhere the session can read. Returns
    the commit the grader compares with.
    """
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} already holds files")
    template = next(t for t in pool_templates(task.role) if t.template_id == task.template_id)
    plan_inputs = _plan_inputs(template)
    start = _template_dir(task) / START_DIRNAME
    dest.mkdir(parents=True, exist_ok=True)
    tasks._copy_tree(start, dest, skip=frozenset({MANIFEST}))
    for overlay in tasks.kit_for(task.role).overlays:
        tasks._copy_tree(tasks.OVERLAYS_DIR / overlay, dest)
    tasks._write_instructions(task, dest)
    for name, text in plan_inputs:
        target = dest / tasks.AI_WORK / task.slug / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tasks._fill(text, task, page_url), encoding="utf-8")
    commit = tasks._commit_fixture(dest)
    if task.role in CONFINED_ROLES:  # as build_scratch_repo: no global ignore file in the sandbox
        tasks._git(dest, "config", "--local", "core.excludesFile", os.devnull)
    return commit


def manifest_path(task: TaskSpec) -> Path:
    """The grader's manifest in the task's template: it stays out of the staged repository."""
    return _template_dir(task) / START_DIRNAME / MANIFEST


def _template_dir(task: TaskSpec) -> Path:
    return tasks.FIXTURES_DIR / task.role / POOL_DIRNAME / task.template_id


def _plan_inputs(template: Template) -> tuple[tuple[str, str], ...]:
    """The inputs a session may read: everything but the two trees the loader also returns.

    A top-level ``start/`` or ``end_states/`` is the template's layout; the same grader data
    anywhere else among the inputs is a declared input that would leak, so the template is refused.
    """
    staged = []
    for name, text in template.inputs:
        path = PurePosixPath(name)
        if path.parts[0] in (START_DIRNAME, ANSWER_DIRNAME):
            continue
        if ANSWER_DIRNAME in path.parts or path.name == MANIFEST:
            raise ValueError(f"template {template.template_id} declares {name} as an input")
        staged.append((name, text))
    return tuple(staged)


def _pool_of(role: Role) -> RefactoringPool:
    pool = POOLS.get(role)
    if pool is None:
        raise ValueError(f"no refactoring pool is authored for {role} yet")
    return pool


def _require_marked(role: Role, pool: RefactoringPool, template: Template) -> None:
    inputs = dict(template.inputs)
    for name in (pool.brief, PLAN_FILE):
        text = inputs.get(name)
        if text is None:
            raise ValueError(f"{role} template {template.template_id} lacks {name}")
        if MARKER not in text:
            raise ValueError(f"{role} template {template.template_id}: {name} lacks {MARKER}")
    if _PLANT_TOKEN not in inputs[pool.brief]:
        raise ValueError(f"{role} template {template.template_id}: {pool.brief} lacks the plant")


def _make_task(
    role: Role, pool: RefactoringPool, template: Template, label: str, seed: int
) -> TaskSpec:
    fixture = pool.fixture_of[template.template_id]
    variant = tasks._variant_of(template, label)
    slug = tasks.task_slug(template.template_id, fixture)
    return TaskSpec(
        task_id=tasks.task_id(role, template.template_id, fixture, variant),
        role=role,
        template_id=template.template_id,
        fixture_id=fixture,
        variant=variant,
        slug=slug,
        main_prompt=pool.prompt.format(slug=slug, brief=pool.brief),
        seed=seed,
        project_convention=tasks.PILOT_CONVENTIONS.get(role),
        mode=pool.task_mode,
    )
