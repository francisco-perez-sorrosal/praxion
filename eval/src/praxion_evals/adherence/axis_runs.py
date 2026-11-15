"""What differs between axes when a run is conducted, held as one value per axis.

The run's loop, launch and arm module read an ``AxisRun`` where each used to call the default
axis's function, so a second axis overrides one field at a time instead of branching in them.
``DEFAULT_RUN`` holds in every field the function that runs today for ``inherited-context``;
``refactoring-delivery`` is that record with its own name, positions, plan, staging, assessment,
catalog and refusals.

Imports nothing from ``session_launch``, ``session_arms``, ``session_loop`` or ``cli`` at run
time: they import this module, and the types it needs from them come in under TYPE_CHECKING.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, assert_never

from praxion_evals.adherence import (
    arms,
    grade,
    refactoring_arms,
    refactoring_assess,
    refactoring_tasks,
    results,
    tasks,
)
from praxion_evals.adherence.axis import DEFAULT_AXIS, POSITIONS, Axis, Positions
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.model import (
    Arm,
    ArmBuild,
    EarlyStop,
    NotBuilt,
    Role,
    SessionEvidence,
    SessionSetup,
    SessionStatus,
    TaskSpec,
)
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.live.materialize import Materialization, install_user_scope

if TYPE_CHECKING:
    from praxion_evals.adherence.session_loop import RunConfig


Observation = arms.ProofObservation | arms.DeliveryObservation


@dataclass(frozen=True)
class ArmProof:
    """How an axis proves its arms: the role's task, the proof home's preparation (returns what
    the decision needs), the reading of a proof session and the verdict per arm."""

    prompt: str
    prepare: Callable[[Materialization, Path], str]
    observe: Callable[[SessionEvidence, Path], Observation | NotBuilt]
    # Each axis decides over its own observations and arms, so the mapping is left open.
    decide: Callable[[str, Mapping[Any, Any]], dict[Any, arms.ArmVerdict]]


@dataclass(frozen=True)
class AxisRun:
    axis: Axis
    positions: Positions
    plan: Callable[[Role, int, int], list[TaskSpec]]  # (role, seed, wanted): never more than exist
    stage: Callable[[TaskSpec, Path, str | None], str]  # (task, dest, page_url): starting commit
    build: Callable[[Materialization, Path, Role, Arm, int | None], ArmBuild]
    proof: ArmProof
    # (evidence, task, setup, judge, real_home)
    assess: Callable[
        [SessionEvidence, TaskSpec, SessionSetup, JudgeClient | None, Path | None], SessionStatus
    ]
    catalog: Callable[[Role], tuple[results.CatalogEntry, ...]]
    refusals: Callable[[RunConfig], tuple[str, ...]]


def plan_producible(role: Role, seed: int, wanted: int) -> list[TaskSpec]:
    return tasks.generate(role, seed, min(wanted, tasks.producible_task_count(role, seed)))


def assess_session(
    evidence: SessionEvidence,
    task: TaskSpec,
    setup: SessionSetup,
    judge: JudgeClient | None,
    real_home: Path | None,
) -> SessionStatus:
    """C3 is named only for a task that planted a gap or a conflict: without one it passes vacuously."""
    names = [
        check.name
        for check in check_catalog(task.role)
        if not (check.name == "C3" and isinstance(task.variant, EarlyStop))
    ]
    return grade.grade(evidence, names, judge, setup, real_home=real_home)


def catalog_entries(role: Role) -> tuple[results.CatalogEntry, ...]:
    return tuple(results.catalog_entry(check) for check in check_catalog(role))


def assess_refactoring_session(
    evidence: SessionEvidence,
    task: TaskSpec,
    setup: SessionSetup,
    judge: JudgeClient | None,
    real_home: Path | None,
) -> SessionStatus:
    default = assess_session(evidence, task, setup, judge, real_home)
    return refactoring_assess.extend(default, evidence, task, setup, real_home)


def refactoring_catalog_entries(role: Role) -> tuple[results.CatalogEntry, ...]:
    return (*catalog_entries(role), *refactoring_assess.catalog_entries(role))


def no_refusals(config: RunConfig) -> tuple[str, ...]:
    del config
    return ()


def refuse_calibration(config: RunConfig) -> tuple[str, ...]:
    """A calibration runs the default axis's full arm against itself, so no other axis has one."""
    if not config.calibration:
        return ()
    return (
        f"--calibration measures the full arm of the {DEFAULT_AXIS} axis against itself;"
        f" it takes no --axis {config.axis}",
    )


def prepare_delivery_home(original: Materialization, template: Path) -> str:
    """The proof home is a task's home with no nonce planted: that proof reads the role's record."""
    install_user_scope(original.root, template)
    return ""


def delivery_proof_decision(
    nonce: str, observed: Mapping[Any, arms.DeliveryObservation | None]
) -> dict[Any, arms.ArmVerdict]:
    del nonce
    return arms.decide_delivery_proof(observed)


DEFAULT_RUN = AxisRun(
    axis=DEFAULT_AXIS,
    positions=POSITIONS[DEFAULT_AXIS],
    plan=plan_producible,
    stage=tasks.build_scratch_repo,
    build=arms.build_arm,
    proof=ArmProof(
        prompt=arms.proof_prompt(),
        prepare=arms.prepare_proof_home,
        observe=arms.observe_proof,
        decide=arms.decide_proof,
    ),
    assess=assess_session,
    catalog=catalog_entries,
    refusals=no_refusals,
)


def axis_run(axis: Axis) -> AxisRun:
    match axis:
        case "inherited-context":
            return DEFAULT_RUN
        case "refactoring-delivery":
            return replace(
                DEFAULT_RUN,
                axis=axis,
                positions=POSITIONS[axis],
                plan=refactoring_tasks.planned_pool,
                stage=refactoring_tasks.stage_pool_task,
                build=refactoring_arms.build_refactoring_copy,
                proof=ArmProof(
                    prompt=refactoring_arms.PROOF_PROMPT,
                    prepare=prepare_delivery_home,
                    observe=refactoring_arms.observe_delivery,
                    decide=delivery_proof_decision,
                ),
                assess=assess_refactoring_session,
                catalog=refactoring_catalog_entries,
                refusals=refuse_calibration,
            )
        case _:
            assert_never(axis)
