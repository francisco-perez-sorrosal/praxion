"""A role's arms: the plugin copy each is built from, the proof that tells them apart and the
record of both.

The session loop (``session_loop``) conducts the run and owns its state. What happens here
returns values for the loop to fold in (a ``ProofRun`` carries the ledger, the verdicts and what
the loop must note); nothing here reads or writes the run's context or its results file.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from praxion_evals.adherence import arms
from praxion_evals.adherence.axis_runs import DEFAULT_RUN, AxisRun
from praxion_evals.adherence.model import (
    Arm,
    ArmBuild,
    Errored,
    NotBuilt,
    Role,
    Standard,
    TaskSpec,
)
from praxion_evals.adherence.session_launch import REAL_HOME, Launch, attempt
from praxion_evals.live.materialize import Materialization
from praxion_evals.live.spend import SpendLedger

Builds = dict[tuple[Arm, int | None], ArmBuild]  # (the arm whose copy, its early-stop cap)


def build_copy(
    role_dir: Path,
    original: Materialization,
    role: Role,
    arm: Arm,
    cap: int | None = None,
    record: AxisRun = DEFAULT_RUN,
) -> ArmBuild | NotBuilt:
    try:
        return record.build(
            original, role_dir / (f"{arm}-cap{cap}" if cap else arm), role, arm, cap
        )
    except (arms.ArmCopyError, OSError) as error:
        return NotBuilt(f"the {arm} copy could not be built: {error}")


def record_of(builds: Builds, verdicts: Mapping[Arm, arms.ArmVerdict]) -> dict[str, Any]:
    """What the results file keeps of a role's arms: per arm, whether it was built and proven."""
    per_arm: dict[str, Any] = {}
    for arm, outcome in verdicts.items():
        build = builds.get((arm, None))
        if isinstance(outcome, NotBuilt) or build is None:
            per_arm[arm] = {"built": False, "reason": getattr(outcome, "reason", "not built")}
        else:
            proof = {
                "first_request_tokens": outcome.first_request_tokens,
                "cross_checked": outcome.cross_checked,
            }
            per_arm[arm] = {
                "built": True,
                "proof": proof,
                "tree_digest": build.tree_digest,
                "patched": list(build.patched),
            }
    return per_arm


@dataclass(frozen=True)
class ProofRun:
    """What the proof sessions settled, for the loop to fold into the run's state: the spend, each
    arm's verdict, the model each session reported (in launch order) and the refusals."""

    ledger: SpendLedger
    verdicts: dict[Arm, arms.ArmVerdict]
    models: tuple[str | None, ...]
    refusals: tuple[str, ...]


def prove(
    launch: Launch,
    ledger: SpendLedger,
    role: Role,
    original: Materialization,
    builds: Builds,
    first_task: TaskSpec,
) -> ProofRun:
    """One proof session per built arm, all under one planted nonce, then one decision."""
    proof = launch.axis_run.proof
    template = launch.run_root / role / "proof-home"
    nonce = proof.prepare(original, template)
    proof_task = replace(first_task, variant=Standard(), main_prompt=proof.prompt)

    def copy_home(root: Path) -> None:
        shutil.copytree(template, root, symlinks=True, dirs_exist_ok=True)

    observed: dict[Arm, arms.ProofObservation | None] = {}
    verdicts: dict[Arm, arms.ArmVerdict] = {}
    models: list[str | None] = []
    refusals: list[str] = []
    for (arm, _), build in builds.items():
        ledger, done = attempt(
            launch,
            ledger,
            proof_task,
            build,
            copy_home,
            None,
            lambda evidence: proof.observe(evidence, REAL_HOME),
        )
        models.append(done.model)
        match done.result:
            case Errored(kind="launch_refused", detail=detail):
                refusals.append(f"{role} {arm} arm proof: {detail}")
                verdicts[arm] = NotBuilt(f"the proof launch was refused: {detail}")
            case Errored(detail=detail):
                verdicts[arm] = NotBuilt(f"the proof session failed: {detail}")
            case NotBuilt() as unobserved:
                verdicts[arm] = unobserved
            case arms.ProofObservation() as seen:
                observed[arm] = seen
    verdicts = {**verdicts, **proof.decide(nonce, observed)}
    return ProofRun(ledger, verdicts, tuple(models), tuple(refusals))
