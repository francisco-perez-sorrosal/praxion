"""CLI entry point for decision-tracker: write and extract subcommands."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from decision_tracker.schema import (
    Decision,
    ExtractedDecision,
    HookOutput,
    PendingDecisions,
)

DECISIONS_FILENAME = ".ai-state/decisions.jsonl"
PENDING_FILENAME = ".ai-work/.pending_decisions.json"
GIT_COMMIT_PATTERN = re.compile(r"git\s+(?:.*\s+)?commit")

CATEGORY_CHOICES: list[str] = [
    "architectural",
    "behavioral",
    "implementation",
    "configuration",
    "calibration",
]


# ---------------------------------------------------------------------------
# Write subcommand
# ---------------------------------------------------------------------------


def _handle_write(args: argparse.Namespace) -> None:
    """Record a single decision from an agent's direct call."""
    from decision_tracker.log import append_decision

    decision = Decision(
        status="documented",
        category=args.category,
        decision=args.decision,
        rationale=args.rationale,
        alternatives=args.alternatives or None,
        affected_reqs=args.affected_reqs or None,
        affected_files=args.affected_files or None,
        made_by="agent",
        agent_type=args.agent_type,
        source="agent",
        pipeline_tier=args.tier,
        session_id=args.session_id,
        branch=args.branch,
        commit_sha=args.commit_sha,
    )

    log_path = Path(args.cwd) / DECISIONS_FILENAME
    append_decision(log_path, decision)
    print(f"decision-tracker: recorded decision {decision.id}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Extract subcommand
# ---------------------------------------------------------------------------


def _handle_extract(_args: argparse.Namespace) -> None:
    """Extract decisions from a hook payload (stdin)."""
    # Consume ALL stdin to avoid broken pipe
    raw_stdin = sys.stdin.read()

    # Check for missing API key early
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _emit_hook_output(HookOutput(status="skipped", message="ANTHROPIC_API_KEY not set"))
        sys.exit(0)

    try:
        _run_extraction(raw_stdin)
    except SystemExit:
        raise
    except Exception as exc:
        _emit_hook_output(HookOutput(status="error", message=str(exc)))
        sys.exit(0)


def _run_extraction(raw_stdin: str) -> None:
    """Core extraction logic, separated for testability."""
    from decision_tracker.dedup import deduplicate
    from decision_tracker.extractor import extract_decisions
    from decision_tracker.log import read_recent
    from decision_tracker.tier import detect_tier, is_gating_tier
    from decision_tracker.transcript import get_last_commit_timestamp, read_transcript

    payload = json.loads(raw_stdin)
    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command", "")

    if not GIT_COMMIT_PATTERN.search(command):
        sys.exit(0)

    cwd = Path(payload.get("cwd", "."))
    session_id = payload.get("session_id")
    log_path = cwd / DECISIONS_FILENAME
    pending_path = cwd / PENDING_FILENAME

    # Check for pending decisions from a prior blocked commit
    if pending_path.is_file():
        _handle_pending(pending_path, log_path)
        return

    # Read transcript scoped since last commit for this session
    transcript_path_str = payload.get("transcript_path", "")
    transcript_text = ""
    if transcript_path_str:
        since = get_last_commit_timestamp(log_path, session_id or "")
        transcript_text = read_transcript(Path(transcript_path_str), since_timestamp=since)

    # Get staged diff
    diff_result = subprocess.run(
        ["git", "diff", "--staged"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    diff_text = diff_result.stdout

    # Detect tier
    tier = detect_tier(cwd)

    # Extract decisions via LLM
    candidates = extract_decisions(transcript_text, diff_text)

    # Convert ExtractedDecision -> Decision
    git_branch = _detect_branch(cwd)
    git_sha = _detect_commit_sha(cwd)
    decisions = [
        _to_decision(ed, session_id=session_id, branch=git_branch, commit_sha=git_sha, tier=tier)
        for ed in candidates
    ]

    # Deduplicate against recent log
    existing = read_recent(log_path)
    novel = deduplicate(decisions, existing)

    if not novel:
        _emit_hook_output(
            HookOutput(
                status="no_decisions",
                tier=tier,
                message="No novel decisions found.",
            )
        )
        sys.exit(0)

    if is_gating_tier(tier):
        _gate_decisions(novel, tier, session_id, pending_path)
    else:
        _auto_approve_decisions(novel, log_path, tier)


def _handle_pending(pending_path: Path, log_path: Path) -> None:
    """Process a pre-existing pending decisions file."""
    from decision_tracker.log import append_decision

    raw = json.loads(pending_path.read_text(encoding="utf-8"))
    pending = PendingDecisions.model_validate(raw)

    unresolved = [d for d in pending.decisions if d.status == "pending"]
    if unresolved:
        # Re-present for review
        _emit_hook_output(
            HookOutput(
                status="review_required",
                count=len(unresolved),
                tier=pending.tier,
                decisions=[d.model_dump(exclude_none=True) for d in unresolved],
                message=f"{len(unresolved)} decisions still pending review.",
            )
        )
        sys.exit(2)

    # All resolved: append to log (both approved and rejected for audit trail)
    resolved = [d for d in pending.decisions if d.status in ("approved", "rejected")]
    for decision in resolved:
        append_decision(log_path, decision)
    pending_path.unlink()

    approved_count = sum(1 for d in resolved if d.status == "approved")
    rejected_count = sum(1 for d in resolved if d.status == "rejected")
    _emit_hook_output(
        HookOutput(
            status="auto_logged",
            count=len(resolved),
            tier=pending.tier,
            message=f"Review complete: {approved_count} approved, {rejected_count} rejected.",
        )
    )
    sys.exit(0)


def _gate_decisions(
    novel: list[Decision],
    tier: str,
    session_id: str | None,
    pending_path: Path,
) -> None:
    """Write pending file and exit with gating code."""
    # Mark decisions as pending review — _handle_pending checks for this status
    for d in novel:
        d.status = "pending"  # type: ignore[assignment]

    pending = PendingDecisions(
        tier=tier,  # type: ignore[arg-type]
        session_id=session_id,
        decisions=novel,
    )
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(pending.model_dump_json(indent=2), encoding="utf-8")

    _emit_hook_output(
        HookOutput(
            status="review_required",
            count=len(novel),
            tier=tier,  # type: ignore[arg-type]
            decisions=[d.model_dump(exclude_none=True) for d in novel],
            message=f"{len(novel)} decisions extracted. Review required.",
        )
    )
    sys.exit(2)


def _auto_approve_decisions(
    novel: list[Decision],
    log_path: Path,
    tier: str,
) -> None:
    """Auto-approve and log decisions for non-gating tiers."""
    from decision_tracker.log import append_decision

    for decision in novel:
        decision.status = "auto-approved"
        append_decision(log_path, decision)

    _emit_hook_output(
        HookOutput(
            status="auto_logged",
            count=len(novel),
            tier=tier,  # type: ignore[arg-type]
            decisions=[d.model_dump(exclude_none=True) for d in novel],
            message=f"{len(novel)} decisions auto-logged.",
        )
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decision(
    extracted: ExtractedDecision,
    *,
    session_id: str | None,
    branch: str | None,
    commit_sha: str | None,
    tier: str,
) -> Decision:
    """Convert an ExtractedDecision to a Decision with hook metadata."""
    return Decision(
        status="documented",
        category=extracted.category,
        question=extracted.question,
        decision=extracted.decision,
        rationale=extracted.rationale,
        alternatives=extracted.alternatives,
        made_by=extracted.made_by,
        confidence=extracted.confidence,
        affected_files=extracted.affected_files,
        source="hook",
        session_id=session_id,
        branch=branch,
        commit_sha=commit_sha,
        pipeline_tier=tier,  # type: ignore[arg-type]
    )


def _detect_branch(cwd: Path) -> str | None:
    """Get the current git branch, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except OSError:
        pass
    return None


def _detect_commit_sha(cwd: Path) -> str | None:
    """Get the current HEAD commit SHA, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except OSError:
        pass
    return None


def _emit_hook_output(output: HookOutput) -> None:
    """Write structured hook output as JSON to stderr."""
    print(output.model_dump_json(exclude_none=True), file=sys.stderr)


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with write and extract subcommands."""
    parser = argparse.ArgumentParser(prog="decision-tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- write subcommand --
    write_parser = subparsers.add_parser("write", help="Record a decision directly")
    write_parser.add_argument("--decision", required=True, help="The decision text")
    write_parser.add_argument(
        "--category",
        required=True,
        choices=CATEGORY_CHOICES,
        help="Decision category",
    )
    write_parser.add_argument("--agent-type", required=True, help="Agent writing the decision")
    write_parser.add_argument("--rationale", default=None, help="Why this choice was made")
    write_parser.add_argument(
        "--alternatives", nargs="*", default=None, help="Alternatives considered"
    )
    write_parser.add_argument("--affected-reqs", nargs="*", default=None, help="REQ IDs affected")
    write_parser.add_argument(
        "--affected-files", nargs="*", default=None, help="File paths affected"
    )
    write_parser.add_argument("--tier", default=None, help="Pipeline tier")
    write_parser.add_argument("--session-id", default=None, help="Claude Code session ID")
    write_parser.add_argument("--branch", default=None, help="Git branch")
    write_parser.add_argument("--commit-sha", default=None, help="Git commit SHA")
    write_parser.add_argument("--cwd", default=".", help="Project directory (default: .)")

    # -- extract subcommand --
    subparsers.add_parser("extract", help="Extract decisions from hook payload on stdin")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "write":
        _handle_write(args)
    elif args.command == "extract":
        _handle_extract(args)


if __name__ == "__main__":
    main()
