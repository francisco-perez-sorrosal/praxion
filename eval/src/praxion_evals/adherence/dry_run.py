"""``--dry-run``: the sessions a paid run would launch, printed and never started.

Each line is built through the same ``session_spec``/``build_argv``/``session_env`` path a paid
run uses, with the plugin copy a real run would make named, not made. This module is reached from
:mod:`~praxion_evals.adherence.cli` and never imports it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from praxion_evals.adherence import managed_fixture, tasks
from praxion_evals.adherence.axis import SessionArm, patched_paths
from praxion_evals.adherence.confinement import Confinement, settings_of
from praxion_evals.adherence.model import ArmBuild, Role, TaskSpec
from praxion_evals.adherence.session_launch import REAL_HOME, session_confinement
from praxion_evals.adherence.session_loop import (
    EXIT_COMPLETE,
    SANDBOX_PREFIX,
    Checkout,
    RunConfig,
    ordered_arms,
    session_env,
)
from praxion_evals.live.session import SandboxPaths, SessionSpec, build_argv


def print_dry_run(
    config: RunConfig, checkout: Checkout, planned: Mapping[Role, list[TaskSpec]]
) -> int:
    run_root = Path(tempfile.gettempdir()) / f"{SANDBOX_PREFIX}<run>"
    for role, role_tasks in planned.items():
        print(f"{role}: {len(role_tasks)} tasks (target {config.required_pairs})", file=sys.stderr)
        for index, task in enumerate(role_tasks):
            for arm in ordered_arms(config.arms, config.seed, task.task_id, config.axis):
                sandbox = SandboxPaths(run_root / role / f"{index:03d}-{arm}")
                copy = planned_copy(run_root, task, arm)
                confinement = session_confinement(
                    role,
                    copy,
                    run_root,
                    home=REAL_HOME,
                    token_file=config.session_oauth_token_file,
                    ambient=os.environ,
                )
                spec = _planned_spec(config, checkout, task, arm, sandbox, copy, confinement)
                env_names = sorted(session_env(config, sandbox.root, os.environ))
                line = {
                    "role": role,
                    "arm": arm,
                    "task_id": task.task_id,
                    "mode": task.mode,
                    "argv": build_argv(spec),
                    "env_names": env_names,
                    "env_switches": dict(_planned_switches(task)),
                }
                if confinement is not None:  # only a confined kit's line shows where it runs
                    line["places"] = _planned_places(run_root, sandbox, task, copy)
                    line["program_order"] = list(confinement.program_order)
                print(json.dumps(line))
    return EXIT_COMPLETE


def _planned_switches(task: TaskSpec) -> Mapping[str, str]:
    """The managed-only switches the task's launches add, which a real run reads off the built
    fixture; the dry run reads them off the directories the fixture is built from."""
    overlays = (tasks.OVERLAYS_DIR / name for name in tasks.kit_for(task.role).overlays)
    return managed_fixture.switches_planned((tasks.REPOS_DIR / task.fixture_id, *overlays))


def planned_copy(run_root: Path, task: TaskSpec, arm: SessionArm) -> Path:
    """Where a real run would put the arm's plugin copy; the dry run names it, never makes it.

    Spells the directory as ``session_arms.build_copy`` does; a test pins the two together.
    """
    cap = tasks.turn_cap_of(task)
    return run_root / task.role / (f"{arm}-cap{cap}" if cap else arm)


def _planned_places(
    run_root: Path, sandbox: SandboxPaths, task: TaskSpec, copy: Path
) -> dict[str, str]:
    return {
        "run_root": str(run_root),
        "plugin_copy": str(copy),
        "sandbox": str(sandbox.root),
        "scratch": str(tasks.scratch_dir(sandbox)),
        "home": str(sandbox.home),
        "tmp": str(sandbox.tmp),
        "slug": task.slug,
    }


def _planned_spec(
    config: RunConfig,
    checkout: Checkout,
    task: TaskSpec,
    arm: SessionArm,
    sandbox: SandboxPaths,
    copy: Path,
    confinement: Confinement | None,
) -> SessionSpec:
    """The spec a real run builds, with the plugin copy it would make named, not made.

    The role's tool line is read from the checkout's own definition, which every copy carries
    unchanged. The confinement is attached after the spec is built because the stand-in build
    names the checkout, not the copy the confinement protects.
    """
    cap = tasks.turn_cap_of(task)
    stand_in = ArmBuild(
        task.role, arm, checkout.path, cap, "dry-run", patched_paths(task.role, arm, cap)
    )
    spec = tasks.session_spec(
        task,
        stand_in,
        sandbox,
        model=config.model,
        effort=config.effort,
        max_budget_usd=config.session_budget_usd,
    )
    settings = None if confinement is None else settings_of(confinement)
    return replace(spec, plugin_dir=copy, add_dir=copy, settings=settings)
