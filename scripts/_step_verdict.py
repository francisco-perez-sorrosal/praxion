"""The pure verdict core: classify one plan step from ground-truth evidence.

Tier-1 evidence (repository changes plus recorded tests) is the arbiter of
"done"; the WIP checkbox is a Tier-3 claim validated here, never trusted.
Nothing in this module reads a file, runs a command or consults the clock:
the reconciler gathers the evidence and hands it in, so every verdict is a
function of its arguments alone.

Policy, in order:

1. A step that declares a check is decided by that check against the result
   recorded for it. A met check completes the step (unless a completion
   blocker applies); an unmet check, or no recorded result, never does, and
   a claim of completion cannot outrank it. A check that cannot be read is
   surfaced to a human.
2. A step that declares no check is decided by the file and test evidence.
3. A step that has used its fresh attempts (``ATTEMPT_CAP``) without being
   verified complete is routed to a human whatever it was classified as; the
   verdict it would have had stays in the evidence.

``make_verdict`` is the only place a verdict dict is built, so the stamps
(``decided_by``, ``outcome_source``, ``attempt``) follow from its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from _loop_fields import (
    ATTEMPT_CAP,
    Attempt,
    CheckOutcome,
    Met,
    NoResult,
    Unmet,
    UnreadableCheck,
)

# Every verdict word. `partial` is written `partial@<last write>` in a verdict.
VERDICT_WORDS = (
    "verified-complete",
    "mismatch",
    "partial",
    "in-flight",
    "unknown",
    "pending",
    "blocked",
    "attempts-exhausted",
)

# Verdicts no auto-resume may act on: a person decides what happens next.
HUMAN_VERDICTS = ("unknown", "blocked", "attempts-exhausted")

# What a verdict says decided it; `none` means nothing happened to decide on.
DECIDED_BY_WORDS = ("check", "fallback", "none")

# A step's declared check as the policy sees it: None when the step declares
# none, `UnreadableCheck` when it declares one that cannot be read, otherwise
# the outcome of judging the check against the recorded result.
DeclaredCheck = Union[CheckOutcome, UnreadableCheck, None]  # noqa: UP007 -- runtime value, 3.9 floor

_OUTCOME_TYPES = (Met, Unmet, NoResult)
_RECORDED = "recorded"  # the reconciler only reads results; a driver that runs commands says `run`
_NEEDS_MARK_SUFFIX = "; WIP not marked COMPLETE — auto-mark on resume"


@dataclass(frozen=True)
class StepEvidence:
    """What was gathered about one step; ``files`` is already the attributable set.

    ``earlier_declarers`` names every step that absorbed a shared file, when any.
    """

    step_id: str
    claim: str
    files: list[str]
    changed: list[str]
    unchanged: list[str]
    test_status: str
    tier2: dict[str, Any]
    earlier_declarers: list[str] = field(default_factory=list)
    mutation_block: str | None = None


@dataclass(frozen=True)
class Decision:
    """A verdict with its evidence, before ``make_verdict`` stamps it.

    ``underlying`` is the verdict a cap override replaced; it is set exactly
    when the verdict is ``attempts-exhausted``.
    """

    verdict: str
    evidence: str
    resume_scope: list[str]
    needs_mark: bool = False
    underlying: str | None = None

    def __post_init__(self) -> None:
        if (self.verdict == "attempts-exhausted") != (self.underlying is not None):
            raise ValueError("attempts-exhausted carries the verdict it replaced, and only it does")


def classify_step(
    evidence: StepEvidence, check_outcome: DeclaredCheck, attempt: Attempt | None
) -> dict[str, Any]:
    """The verdict dict for one step: check first, else files and tests, then the cap."""
    decision = _decide(evidence, check_outcome)
    if (
        attempt is not None
        and attempt.count >= ATTEMPT_CAP
        and decision.verdict != "verified-complete"
    ):
        decision = _exhausted(decision, attempt)
    return make_verdict(evidence, decision, check_outcome, attempt)


def make_verdict(
    evidence: StepEvidence,
    decision: Decision,
    check_outcome: DeclaredCheck,
    attempt: Attempt | None,
) -> dict[str, Any]:
    """Build the verdict dict, the only constructor of it, and stamp it.

    ``decided_by`` is always present: ``none`` exactly when the verdict before
    any cap override is ``pending``, else ``check`` when the step declares a
    check (readable or not), else ``fallback``. ``outcome_source`` appears only
    when a check outcome decided. ``attempt`` appears only when one is
    recorded. Optional keys are omitted, never null.
    """
    decided_by = _decided_by(decision, check_outcome)
    verdict: dict[str, Any] = {
        "step": evidence.step_id,
        "wip_claim": evidence.claim,
        "verdict": decision.verdict,
        "needs_mark": decision.needs_mark,
        "tier1": {
            "files_changed": evidence.changed,
            "files_unchanged": evidence.unchanged,
            "tests": evidence.test_status,
        },
        "tier2": evidence.tier2,
        "evidence": decision.evidence,
        "resume_scope": decision.resume_scope,
        "decided_by": decided_by,
    }
    if decided_by == "check" and isinstance(check_outcome, _OUTCOME_TYPES):
        verdict["outcome_source"] = _RECORDED
    if attempt is not None:
        verdict["attempt"] = attempt.count
    return verdict


def _decided_by(decision: Decision, check_outcome: DeclaredCheck) -> str:
    if (decision.underlying or decision.verdict) == "pending":
        return "none"
    return "fallback" if check_outcome is None else "check"


def _exhausted(decision: Decision, attempt: Attempt) -> Decision:
    replan = (
        f"replan requested: {attempt.replan}" if attempt.replan else "no replan request recorded"
    )
    evidence = (
        f"{attempt.count} fresh attempt(s) used (cap {ATTEMPT_CAP}) without verified completion; "
        f"{replan}; underlying verdict {decision.verdict}: {decision.evidence}"
    )
    return Decision(
        "attempts-exhausted", evidence, decision.resume_scope, underlying=decision.verdict
    )


def _decide(evidence: StepEvidence, check_outcome: DeclaredCheck) -> Decision:
    if check_outcome is None:
        return _decide_by_files(evidence)
    if isinstance(check_outcome, UnreadableCheck):
        return _decide_unreadable_check(evidence, check_outcome)
    return _decide_by_check(evidence, check_outcome)


# ---------------------------------------------------------------------------
# The check path
# ---------------------------------------------------------------------------


def _decide_by_check(evidence: StepEvidence, outcome: CheckOutcome) -> Decision:
    """A readable declared check decides; a claim never outranks it."""
    if isinstance(outcome, Met):
        return _confirmed(evidence, "declared check met by the result recorded for the step")
    if evidence.claim == "COMPLETE":
        scope = evidence.unchanged or evidence.files
        return Decision("mismatch", f"WIP=[COMPLETE] but {_why_unmet(outcome)}", scope)
    return _decide_unclaimed(evidence)


def _why_unmet(outcome: Unmet | NoResult) -> str:
    if isinstance(outcome, Unmet):
        return "check unmet: " + "; ".join(item.render() for item in outcome.unmet)
    return outcome.reason


def _decide_unreadable_check(evidence: StepEvidence, check: UnreadableCheck) -> Decision:
    text = (
        f"the step's declared check cannot be read ({check.reason}): {check.line} — "
        f"WIP claim={evidence.claim}; surfaced for human verification"
    )
    return Decision("unknown", text, [])


# ---------------------------------------------------------------------------
# The fallback path: file and test evidence, for a step that declares no check
# ---------------------------------------------------------------------------


def _decide_by_files(evidence: StepEvidence) -> Decision:
    """Tier-1 (git + tests) is the arbiter — ground truth decides "done,"
    NOT the WIP checkbox (which is Tier-3, validated here)."""
    # No attributable files → we cannot tie this step to specific ground
    # truth. Never guess `verified-complete`; degrade to a human-surfaced verdict.
    if not evidence.files:
        verdict = "unknown" if evidence.claim == "COMPLETE" else "pending"
        reason = _no_attributable_files_reason(evidence.claim, verdict, evidence.earlier_declarers)
        return Decision(verdict, reason, [])

    tests_red = evidence.test_status == "red"
    # All declared files changed AND suite not red → the work IS done,
    # regardless of the checkbox. If the checkbox disagrees, it just needs
    # marking — the died-before-checkbox case the whole design targets.
    if evidence.changed and not evidence.unchanged and not tests_red:
        basis = (
            f"all {len(evidence.changed)} declared file(s) changed; tests={evidence.test_status}"
        )
        return _confirmed(evidence, basis)

    if evidence.claim == "COMPLETE":
        # A [COMPLETE] claim ground truth contradicts — the truncation signature.
        scope = evidence.unchanged or evidence.files
        reason = (
            "tests red"
            if tests_red
            else f"{len(evidence.unchanged)} declared file(s) show no git change"
        )
        return Decision("mismatch", f"WIP=[COMPLETE] but {reason}: {', '.join(scope)}", scope)

    return _decide_unclaimed(evidence)


def _no_attributable_files_reason(claim: str, verdict: str, earlier_declarers: list[str]) -> str:
    """Evidence text when a step has no attributable file -- names every
    earlier declarer that absorbed one, distinct from a genuinely file-less
    step."""
    surfaced = "; surfaced for human verification" if verdict == "unknown" else ""
    if earlier_declarers:
        return (
            f"every declared file is also declared by {', '.join(earlier_declarers)} "
            f"(earlier) — WIP claim={claim}{surfaced}"
        )
    if verdict == "unknown":
        return (
            "step declares no Files: and cannot be tied to git changes — "
            f"WIP claim={claim}{surfaced}"
        )
    return "step not started and declares no Files:"


# ---------------------------------------------------------------------------
# Shared by both paths
# ---------------------------------------------------------------------------


def _confirmed(evidence: StepEvidence, basis: str) -> Decision:
    """The work is done: complete, unless a completion blocker applies."""
    if evidence.mutation_block is not None:
        # The escape is always a visible decision, never a silent pass.
        text = (
            f"{evidence.step_id}: mutation: on, {evidence.mutation_block}; restore the sensor "
            "(environment, network) and re-run it, or amend the plan to drop "
            "the tag with a recorded reason"
        )
        return Decision("blocked", text, [])
    needs_mark = evidence.claim != "COMPLETE"
    return Decision(
        "verified-complete", basis + (_NEEDS_MARK_SUFFIX if needs_mark else ""), [], needs_mark
    )


def _decide_unclaimed(evidence: StepEvidence) -> Decision:
    """Classify a step whose claim is not COMPLETE and whose completion nothing has
    confirmed: not-started (pending), stopped mid-work (partial), or still running (in-flight)."""
    changed, unchanged = evidence.changed, evidence.unchanged
    if not changed:
        return Decision("pending", "step not started (no file changes)", evidence.files)
    if evidence.tier2.get("agent_stop_seen"):
        last = evidence.tier2.get("last_write") or "?"
        text = (
            f"{len(changed)} file(s) changed; agent stopped after {last}; "
            f"remainder: {', '.join(unchanged)}"
        )
        return Decision(f"partial@{last}", text, unchanged)
    text = f"{len(changed)} file(s) changed, no terminal marker — possibly still running"
    return Decision("in-flight", text, unchanged)


# ---------------------------------------------------------------------------
# Transitional entry point for the reconciler's present call shape
# ---------------------------------------------------------------------------


def _classify_step(
    *,
    step_id: str,
    claim: str,
    files: list[str],
    changed: list[str],
    unchanged: list[str],
    test_status: str,
    tier2: dict[str, Any],
    earlier_declarers: list[str] | None = None,
    mutation_block: str | None = None,
) -> dict[str, Any]:
    """The legacy verdict: no check, no attempt, and no ``decided_by`` key yet.

    The reconciler calls this until it reads checks and attempts itself; the
    verdict it returns is the one it has always returned.
    """
    evidence = StepEvidence(
        step_id=step_id,
        claim=claim,
        files=files,
        changed=changed,
        unchanged=unchanged,
        test_status=test_status,
        tier2=tier2,
        earlier_declarers=earlier_declarers or [],
        mutation_block=mutation_block,
    )
    verdict = classify_step(evidence, None, None)
    del verdict["decided_by"]
    return verdict
