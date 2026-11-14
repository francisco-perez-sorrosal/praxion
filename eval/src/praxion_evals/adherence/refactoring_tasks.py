"""The refactoring-mode task pool: tasks a role is asked only on the ``refactoring-delivery`` axis.

A role's pool is a directory of its own, ``fixtures/<role>/refactoring``, and never part of the
role's default plan. A template under ``templates/`` joins ``tasks.kit_for`` and with it every
default run, and a new template there changes the plan of the default pool and the template the
standing eval tests mutate; the pool is loaded and built here, through ``tasks``' own template
loader, variant mapping, ids and slugs, so a pool task is shaped exactly like a default one.

What marks a pool task is the words it is delegated in: the prompt names the refactoring step, and
the plan and the brief the role reads carry the same marker, which is what the axis measures.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from praxion_evals.adherence import tasks
from praxion_evals.adherence.model import Role, TaskSpec
from praxion_evals.adherence.tasks import Template

POOL_DIRNAME = "refactoring"
PLAN_FILE = "IMPLEMENTATION_PLAN.md"
MARKER = "[Phase: Refactoring]"
MIN_POOL_TEMPLATES = 2
VARIANTS = ("ambiguity", "conflict", "early-stop")
_PLANT_TOKEN = "@@PLANT@@"


@dataclass(frozen=True)
class RefactoringPool:
    brief: str  # the input file the prompt points the role at
    prompt: str  # with ``{slug}`` and ``{brief}`` slots
    fixture_of: Mapping[str, str]  # template id -> the one ``fixtures/repos`` entry it runs in


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
    )
