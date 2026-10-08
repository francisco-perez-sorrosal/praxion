"""The pure verdict core: classify one plan step from ground-truth evidence.

Tier-1 evidence (repository changes plus recorded tests) is the arbiter of
"done"; the WIP checkbox is a Tier-3 claim validated here, never trusted.
Tier-2 is a localization hint that never decides alone: ``agent_stop_seen`` says
whether an agent that wrote the step's files has since stopped (so a step with
changes but no stop may still be running), and ``last_write`` is the last file
that agent wrote (so a stopped step resumes from there; ``None`` when unknown).
Nothing in this module reads a file, runs a command or consults the clock:
the reconciler gathers the evidence and hands it in, so every verdict is a
function of its arguments alone.

Policy, in order:

1. A step that declares a check is decided by that check against the result
   recorded for it. A met check completes the step (unless a completion
   blocker applies); an unmet check, or no recorded result, never does, and
   a claim of completion cannot outrank it. A stopped agent's partial verdict
   names what the check lacks and says to run it and record its result. A
   check that cannot be read is surfaced to a human, and so is an ``Iterations:``
   value that cannot be read, whatever the check says.
2. A step that declares no check is decided by the file and test evidence.
3. A step not verified complete whose latest attempt is outstanding (started by
   the step-loop driver, not yet in the iteration ledger) is ``in-flight``
   whatever it was classified as, and never ``attempts-exhausted``: the cap
   judges an attempt only once it has ended. The verdict it would have had stays
   in the evidence.
4. A step that has used its fresh attempts (``ATTEMPT_CAP``) without being
   verified complete is routed to a human whatever it was classified as; the
   verdict it would have had stays in the evidence. A step whose attempt record
   cannot be read is routed to a human the same way (as `unknown`), because a
   count that cannot be read cannot be trusted to be below the cap. That covers
   an outstanding attempt while the iteration ledger holds a line that breaks its
   shape: that line may be the attempt's end, so the attempt cannot be read as
   still running either. A goal step (one with an ``Iterations:`` budget) has no
   count cap: it is routed to a human exactly when its ``Attempts:`` line carries
   the replan request the step-loop driver writes when the loop stalls.

``make_verdict`` is the only place a verdict dict is built, so the stamps
(``decided_by``, ``outcome_source``, ``attempt``) follow from its inputs.
``outcome_source`` is ``run`` when the deciding ``Result:`` line is the driver's
own run of the check and ``recorded`` otherwise; this module itself runs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from _loop_fields import (
    Attempt,
    AttemptCap,
    CheckOutcome,
    Met,
    NoResult,
    OutstandingAttempt,
    Unmet,
    UnreadableCheck,
    UnreadableIterations,
    request_cap,
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

# A step's declared check as the policy sees it: None when the step declares
# none, `UnreadableCheck` when it declares one that cannot be read, otherwise
# the outcome of judging the check against the recorded result.
DeclaredCheck = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    CheckOutcome, UnreadableCheck, None
]

_OUTCOME_TYPES = (Met, Unmet, NoResult)
_RECORDED = "recorded"  # a result some agent recorded; only read, never run here
_RUN = "run"  # the step-loop driver's own run of the check wrote the deciding line
# The verdicts that may replace an underlying one: the cap, and an outstanding attempt.
_OVERRIDES = ("attempts-exhausted", "in-flight")
_NEEDS_MARK_SUFFIX = "; WIP not marked COMPLETE — auto-mark on resume"


@dataclass(frozen=True)
class StepEvidence:
    """What was gathered about one step; ``files`` is already the attributable set.

    ``changed`` and ``unchanged`` partition ``files``: every file is in exactly
    one of them. ``earlier_declarers`` names every step that absorbed a shared
    file, when any. ``iterations`` is a goal step's ``Iterations:`` budget, the
    value that could not be read, or None for an ordinary step.
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
    iterations: int | UnreadableIterations | None = None

    def __post_init__(self) -> None:
        if sorted(self.changed + self.unchanged) != sorted(self.files):
            raise ValueError("changed and unchanged must partition the step's files")


@dataclass(frozen=True)
class UnreadableAttempts:
    """An attempt record that cannot be read; ``reason`` says how, ``source`` says where."""

    reason: str
    source: str = "the Attempts: line"


# What the policy knows of a step's attempts: nothing recorded, an ended count, a
# count whose attempt is still outstanding, or a line that could not be read.
AttemptRecord = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    Attempt, OutstandingAttempt, UnreadableAttempts, None
]


@dataclass(frozen=True)
class Decision:
    """A verdict with its evidence, before ``make_verdict`` stamps it.

    ``underlying`` is the verdict an override replaced: always set on
    ``attempts-exhausted``, set on ``in-flight`` when an outstanding attempt
    produced it, and never set on any other verdict.
    """

    verdict: str
    evidence: str
    resume_scope: list[str]
    needs_mark: bool = False
    underlying: str | None = None

    def __post_init__(self) -> None:
        capped_bare = self.verdict == "attempts-exhausted" and self.underlying is None
        if capped_bare or (self.underlying is not None and self.verdict not in _OVERRIDES):
            raise ValueError(
                "attempts-exhausted carries the verdict it replaced, and only it and an "
                "outstanding attempt's in-flight may"
            )


def classify_step(
    evidence: StepEvidence, check_outcome: DeclaredCheck, attempt: AttemptRecord
) -> dict[str, Any]:
    """The verdict dict for one step: check first, else files and tests, then the attempts."""
    decision = _read_attempts(evidence, _decide(evidence, check_outcome), attempt)
    return make_verdict(evidence, decision, check_outcome, attempt)


def make_verdict(
    evidence: StepEvidence,
    decision: Decision,
    check_outcome: DeclaredCheck,
    attempt: AttemptRecord,
) -> dict[str, Any]:
    """Build the verdict dict, the only constructor of it, and stamp it.

    ``decided_by`` is always present: ``none`` exactly when the verdict before
    any override is ``pending``, else ``check`` when the step declares a
    check (readable or not), else ``fallback``. ``outcome_source`` appears only
    when a check outcome decided. ``attempt`` appears only when a count is
    recorded, ended or outstanding. Optional keys are omitted, never null.
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
        verdict["outcome_source"] = _outcome_source(check_outcome)
    if isinstance(attempt, (Attempt, OutstandingAttempt)):
        verdict["attempt"] = attempt.count
    return verdict


def _outcome_source(outcome: CheckOutcome) -> str:
    by_step_loop = isinstance(outcome, (Met, Unmet)) and outcome.by_step_loop
    return _RUN if by_step_loop else _RECORDED


def _decided_by(decision: Decision, check_outcome: DeclaredCheck) -> str:
    if (decision.underlying or decision.verdict) == "pending":
        return "none"
    return "fallback" if check_outcome is None else "check"


def _read_attempts(evidence: StepEvidence, decision: Decision, attempt: AttemptRecord) -> Decision:
    """A step not verified complete is in flight while its attempt is outstanding, and
    goes to a human at the cap (a goal step: at its published stall) or on an unreadable
    record."""
    if decision.verdict == "verified-complete" or attempt is None:
        return decision
    if isinstance(attempt, OutstandingAttempt):
        return _outstanding(decision, attempt)
    if isinstance(attempt, UnreadableAttempts):
        return _unreadable_attempts(evidence, decision, attempt)
    if evidence.iterations is None:
        cap = request_cap(AttemptCap())  # an ordinary step's bound
        return _exhausted(decision, attempt, cap) if attempt.count >= cap else decision
    if isinstance(evidence.iterations, UnreadableIterations):
        return decision  # already `unknown`: no count is judged against a bound nobody can read
    return _stalled(decision, attempt, evidence.iterations) if attempt.replan else decision


def _outstanding(decision: Decision, attempt: OutstandingAttempt) -> Decision:
    """The attempt has started and not ended, so no reading of its result is final yet."""
    evidence = (
        f"attempt {attempt.count} is outstanding under request {attempt.request} (started, "
        f"no ledger record yet); underlying verdict {decision.verdict}: {decision.evidence}"
    )
    return Decision("in-flight", evidence, decision.resume_scope, underlying=decision.verdict)


def _unreadable_attempts(
    evidence: StepEvidence, decision: Decision, attempt: UnreadableAttempts
) -> Decision:
    if decision.verdict in HUMAN_VERDICTS:
        return decision  # already surfaced to a person, with a more specific reason
    text = (
        f"{evidence.step_id}: {attempt.source} cannot be read ({attempt.reason}); fix it so "
        f"the count can be trusted; underlying verdict {decision.verdict}: {decision.evidence}"
    )
    return Decision("unknown", text, decision.resume_scope)


def _exhausted(decision: Decision, attempt: Attempt, cap: int) -> Decision:
    replan = (
        f"replan requested: {attempt.replan}" if attempt.replan else "no replan request recorded"
    )
    evidence = (
        f"{attempt.count} fresh attempt(s) used (cap {cap}) without verified completion; "
        f"{replan}; underlying verdict {decision.verdict}: {decision.evidence}"
    )
    return Decision(
        "attempts-exhausted", evidence, decision.resume_scope, underlying=decision.verdict
    )


def _stalled(decision: Decision, attempt: Attempt, iterations: int) -> Decision:
    """A goal step is spent when the driver has published its stall, never by its count."""
    evidence = (
        f"{attempt.count} of {iterations} iteration(s) used and the loop stalled without "
        f"verified completion; replan requested: {attempt.replan}; underlying verdict "
        f"{decision.verdict}: {decision.evidence}"
    )
    return Decision(
        "attempts-exhausted", evidence, decision.resume_scope, underlying=decision.verdict
    )


def _decide(evidence: StepEvidence, check_outcome: DeclaredCheck) -> Decision:
    if isinstance(evidence.iterations, UnreadableIterations):
        return _decide_unreadable_iterations(evidence, evidence.iterations)
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
    return _name_the_check(_decide_unclaimed(evidence), outcome)


def _name_the_check(decision: Decision, outcome: Unmet | NoResult) -> Decision:
    """A stopped agent's partial verdict also says what the check still lacks and
    that running it is part of the remainder, even when every file already changed."""
    if not decision.verdict.startswith("partial@"):
        return decision
    first = "finish the remainder, then run" if decision.resume_scope else "run"
    text = (
        f"{decision.evidence}; {_why_unmet(outcome)}; resume: {first} the step's check "
        "command and record its Result: line last in the step's TEST_RESULTS section"
    )
    return Decision(decision.verdict, text, decision.resume_scope)


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


def _decide_unreadable_iterations(evidence: StepEvidence, value: UnreadableIterations) -> Decision:
    text = (
        f"the step's Iterations: value cannot be read ({value.text!r} is no whole number of at "
        f"least 1), so its bound is unknown — WIP claim={evidence.claim}; surfaced for human "
        "verification"
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
            f"remainder: {', '.join(unchanged) or 'none'}"
        )
        return Decision(f"partial@{last}", text, unchanged)
    text = f"{len(changed)} file(s) changed, no terminal marker — possibly still running"
    return Decision("in-flight", text, unchanged)
