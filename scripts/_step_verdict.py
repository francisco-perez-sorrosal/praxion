"""The pure verdict core: classify one plan step from ground-truth evidence.

Tier-1 evidence (repository changes plus recorded tests) is the arbiter of
"done"; the WIP checkbox is a Tier-3 claim validated here, never trusted.
Nothing in this module reads a file, runs a command or consults the clock:
the reconciler gathers the evidence and hands it in, so every verdict is a
function of its arguments alone.
"""

from __future__ import annotations

from typing import Any


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
    """Classify one step. Tier-1 (git + tests) is the arbiter — ground truth
    decides "done," NOT the WIP checkbox (which is Tier-3, validated here).
    ``files`` is already the *attributable* set (see ``attributable``);
    ``earlier_declarers`` names every step that absorbed a shared file, when any.
    """
    tier1 = {"files_changed": changed, "files_unchanged": unchanged, "tests": test_status}

    # No attributable files → we cannot tie this step to specific ground
    # truth. Never guess `verified-complete`; degrade to a human-surfaced verdict.
    if not files:
        verdict = "unknown" if claim == "COMPLETE" else "pending"
        evidence = _no_attributable_files_reason(claim, verdict, earlier_declarers or [])
        return _make_verdict(step_id, claim, verdict, tier1, tier2, evidence, [])

    tests_red = test_status == "red"

    # Tier-1 arbiter: all declared files changed AND suite not red → the work IS
    # done, regardless of the checkbox. If the checkbox disagrees, it just needs
    # marking — the died-before-checkbox case the whole design targets.
    if changed and not unchanged and not tests_red:
        if mutation_block is not None:
            # The escape is always a visible decision, never a silent pass.
            evidence = (
                f"{step_id}: mutation: on, {mutation_block}; restore the sensor "
                "(environment, network) and re-run it, or amend the plan to drop "
                "the tag with a recorded reason"
            )
            return _make_verdict(step_id, claim, "blocked", tier1, tier2, evidence, [])
        needs_mark = claim != "COMPLETE"
        evidence = f"all {len(changed)} declared file(s) changed; tests={test_status}" + (
            "; WIP not marked COMPLETE — auto-mark on resume" if needs_mark else ""
        )
        return _make_verdict(
            step_id, claim, "verified-complete", tier1, tier2, evidence, [], needs_mark=needs_mark
        )

    # Tier-1 does NOT confirm completion.
    if claim == "COMPLETE":
        # A [COMPLETE] claim ground truth contradicts — the truncation signature.
        scope = unchanged or files
        reason = (
            "tests red" if tests_red else f"{len(unchanged)} declared file(s) show no git change"
        )
        evidence = f"WIP=[COMPLETE] but {reason}: {', '.join(scope)}"
        return _make_verdict(step_id, claim, "mismatch", tier1, tier2, evidence, scope)

    # Honest not-complete claim — pending / partial / in-flight.
    return _classify_incomplete_claim(step_id, claim, tier1, tier2, changed, unchanged, files)


def _classify_incomplete_claim(
    step_id: str,
    claim: str,
    tier1: dict[str, Any],
    tier2: dict[str, Any],
    changed: list[str],
    unchanged: list[str],
    files: list[str],
) -> dict[str, Any]:
    """Classify a step whose claim is not COMPLETE and Tier-1 has not confirmed it:
    not-started (pending), stopped mid-work (partial), or still running (in-flight)."""
    if not changed:
        return _make_verdict(
            step_id, claim, "pending", tier1, tier2, "step not started (no file changes)", files
        )
    if tier2.get("agent_stop_seen"):
        last = tier2.get("last_write") or "?"
        evidence = (
            f"{len(changed)} file(s) changed; agent stopped after {last}; "
            f"remainder: {', '.join(unchanged)}"
        )
        return _make_verdict(step_id, claim, f"partial@{last}", tier1, tier2, evidence, unchanged)
    evidence = f"{len(changed)} file(s) changed, no terminal marker — possibly still running"
    return _make_verdict(step_id, claim, "in-flight", tier1, tier2, evidence, unchanged)


def _make_verdict(
    step_id: str,
    claim: str,
    verdict: str,
    tier1: dict[str, Any],
    tier2: dict[str, Any],
    evidence: str,
    resume_scope: list[str],
    *,
    needs_mark: bool = False,
) -> dict[str, Any]:
    """Construct a verdict dict satisfying the output contract.

    ``needs_mark`` is True for a ``verified-complete`` step whose checkbox was
    never flipped (the died-before-checkbox case) — the resume action is an
    auto-mark, not a re-spawn.
    """
    return {
        "step": step_id,
        "wip_claim": claim,
        "verdict": verdict,
        "needs_mark": needs_mark,
        "tier1": tier1,
        "tier2": tier2,
        "evidence": evidence,
        "resume_scope": resume_scope,
    }
