"""Assess a ``refactoring-delivery`` session: the role's default checks, then this axis's own.

The axis adds one mechanical outcome per item of the role's refactoring checklist, graded from
the repository the session left and never from what it says, and one outcome for whether the
skill reached the role the way its arm delivers it, read from the session's own transcript.
``extend`` takes the result of the default assessment, so this module imports nothing from
``axis_runs``, which composes the two.

The catalog entries below depart from the catalog's canary pattern: a mechanical check there
carries a ``violation`` builder, and these carry none. Their canaries are the committed
``end_states/<item>`` trees of each pool template and the end-state scenarios that grade them.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from praxion_evals.adherence import arms, checks_refactoring, refactoring_arms, refactoring_tasks
from praxion_evals.adherence.model import (
    CheckErrored,
    CheckOutcome,
    EarlyStop,
    Failed,
    Measured,
    NotApplicable,
    NotBuilt,
    Passed,
    Role,
    RuleRef,
    SessionEvidence,
    SessionSetup,
    SessionStatus,
    TaskSpec,
)
from praxion_evals.adherence.results import CatalogEntry
from praxion_evals.adherence.tasks import scratch_dir
from praxion_evals.live.session import SandboxPaths

SKILL = "skills/refactoring/SKILL.md"
ARRIVAL = "refactoring-delivery: the skill reached the role its arm's way"
ARRIVAL_SECTION = "Entry Points"
# The implementer's items are the skill's checklist; the test-engineer's are its pre-refactor rule.
ITEM_SECTIONS: Mapping[Role, str] = {
    "implementer": "Verification Checklist",
    "test-engineer": "Gotchas",
}
STOPPED_EARLY = "the task stopped the role early"


def item_name(item: str) -> str:
    return f"refactoring: {item}"


def item_names(role: Role) -> tuple[str, ...]:
    return tuple(item_name(item) for item, _ in checks_refactoring.CHECKLISTS[role])


def catalog_entries(role: Role) -> tuple[CatalogEntry, ...]:
    """The axis's own entries: the role's checklist items, then the arrival."""
    return (
        *(_entry(name, ITEM_SECTIONS[role]) for name in item_names(role)),
        _entry(ARRIVAL, ARRIVAL_SECTION),
    )


def _entry(name: str, section: str) -> CatalogEntry:
    return CatalogEntry(
        name, "mechanical", RuleRef(SKILL, section), common=False, golden_bad_case=None
    )


def extend(
    default: SessionStatus,
    evidence: SessionEvidence,
    task: TaskSpec,
    setup: SessionSetup,
    real_home: Path | None,
) -> SessionStatus:
    """``default`` with the axis's outcomes added; a session that was not measured stays as it is."""
    if not isinstance(default, Measured):
        return default
    added = {**_end_state(evidence, task), ARRIVAL: _arrival(evidence, setup, real_home)}
    return Measured.for_checks(
        [*default.outcomes, *added],
        {**default.outcomes, **added},
        default.first_request_tokens,
        default.setup,
        default.role_return,
        default.kernel_rows,
        default.role_ending,
    )


def _end_state(evidence: SessionEvidence, task: TaskSpec) -> dict[str, CheckOutcome]:
    names = item_names(task.role)
    if isinstance(task.variant, EarlyStop):
        return dict.fromkeys(names, NotApplicable(STOPPED_EARLY))
    try:
        grade = checks_refactoring.grade_workspace(
            task.role,
            scratch_dir(SandboxPaths(evidence.sandbox)),
            evidence.role_return or "",
            manifest=refactoring_tasks.manifest_path(task),
        )
    except Exception as error:  # a crashed grader is that session's infrastructure, not the run's
        return dict.fromkeys(names, CheckErrored(f"{type(error).__name__}: {error}"))
    failed = {item_name(item) for item in grade.failed}
    errored = {item_name(item): why for item, why in grade.errored.items()}
    return {name: _outcome(name, failed, errored) for name in names}


def _outcome(name: str, failed: set[str], errored: Mapping[str, str]) -> CheckOutcome:
    if name in errored:
        return CheckErrored(f"the repository's tests reached no verdict: {errored[name]}")
    if name in failed:
        return Failed("the repository the session left does not hold this item")
    return Passed()


def _arrival(
    evidence: SessionEvidence, setup: SessionSetup, real_home: Path | None
) -> CheckOutcome:
    if real_home is None:
        return CheckErrored(
            "the session's record is read against the real home, and none was given"
        )
    seen = refactoring_arms.observe_delivery(evidence, real_home)
    if isinstance(seen, NotBuilt):
        return CheckErrored(seen.reason)
    verdict = arms.decide_delivery_proof({setup.arm: seen})[setup.arm]
    return Failed(verdict.reason) if isinstance(verdict, NotBuilt) else Passed()
