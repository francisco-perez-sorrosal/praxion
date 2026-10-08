"""Shared fixtures and builders for the step-loop driver's state unit tests.

Plan blocks, ledger records, reconciler verdicts and loop inputs, built from text and values so
no case writes a file, runs a process or mocks anything. Not a test module: the review-state
tests and the bound-and-stall tests both import it.
"""

from __future__ import annotations

from _plan_steps import parse_plan_steps
from _step_loop_action import next_action
from _step_loop_render import RequestKey
from _step_loop_state import LoopInputs
from iteration_ledger import IterationRecord

STEP = "Step "
IMPL = "**Assignee**: implementer"
OTHER = "**Assignee**: test-engineer"
FILES = "**Files**: `scripts/a.py`"
FORCED = "**review**: force"
RISKY = "tier: H"
OFF = "**review**: off"
ACCEPT = "verdict: accept"
REVISE = "verdict: revise"
PARTIAL = "verdict: [PARTIAL]"


def block(number, *lines, annotations=""):
    body = "".join(f"{line}\n" for line in lines)
    return f"### {STEP}{number}: Do it{annotations}\n\n{body}\n"


def steps_of(*blocks):
    return parse_plan_steps("## Steps\n\n" + "".join(blocks))


def one(*lines, number="1"):
    return steps_of(block(number, *lines))[0]


def rec(step, attempt=1, kind="implement", *, verdict="mismatch", stop="completed", round_=1):
    """A ledger record for `step`, its request id built the way the driver builds it."""
    key = RequestKey(step.id, attempt, kind, 1, None if kind == "implement" else round_)
    return IterationRecord(
        step=STEP + step.id,
        attempt=attempt,
        agent_id=f"agent-{attempt}",
        verdict=verdict,
        decided_by="check",
        test_result="Result: none",
        commit=None,
        stop_reason=stop,
        request=key.id,
        step_digest=step.digest,
    )


def verdict(step_id, word, claim="PENDING", evidence=""):
    return {"step": STEP + step_id, "verdict": word, "wip_claim": claim, "evidence": evidence}


def read(steps, attempts=None, records=(), verdicts=(), reviews=None, unnamed=()):
    return LoopInputs.read(steps, attempts or {}, records, verdicts, reviews, unnamed)


def act(steps, **given):
    return next_action(read(steps, **given))


def verified(step, attempt=1):
    return rec(step, attempt, verdict="verified-complete")


def reviewed(step):
    return rec(step, 1, "review", verdict="verified-complete", stop="completed")


def revised(step, *, ok=True):
    return rec(step, 1, "revise", verdict="verified-complete" if ok else "mismatch")


FORCED_STEP = one(IMPL, FILES, FORCED)
PLAIN_STEP = one(IMPL, FILES)
SECOND = one(IMPL, FILES, number="2")
PLAN = [FORCED_STEP, SECOND]  # step 2 keeps the budget wide enough for a review loop


def done(*ids):
    return [verdict(i, "verified-complete", "COMPLETE") for i in ids]
