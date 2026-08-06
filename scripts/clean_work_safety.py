#!/usr/bin/env python3
"""Classify `.ai-work/<task-slug>/` directories by deletion safety.

`.ai-work/` is gitignored and a `rm -rf` of a task directory is irreversible.
Several artifacts must reach a durable home before deletion, and a few signal a
live pipeline that must not be deleted at all. This read-only scanner inspects
each task directory and classifies it so `/clean-work` can refuse, warn, or
proceed — replacing the prior "warn only when LEARNINGS.md exists" heuristic
that silently deleted unarchived verification, rework, recovery, and
traceability state.

Classification (per task directory):

    BLOCK  live/incomplete state — never delete without explicit override
           - WIP.md with an unchecked `- [ ]` step  (pipeline in flight)
           - REWORK_MANIFEST.md present              (rework may be open)
    WARN   durable-state handoff pending — confirm before deleting
           - LEARNINGS.md                            (merge to .ai-state/ first)
           - VERIFICATION_REPORT.md w/o a merged marker in LEARNINGS.md
           - traceability.yml / REQ-bearing SYSTEMS_PLAN.md (archive the spec)
           - RECOVERY_LOG.md                         (audit trail)
           - PRE_REFACTOR_PLAN.md without a [CONSUMED] marker
    SAFE   none of the above — deletable

The scanner mutates nothing. Deletion (and any `--force` override of a BLOCK)
is the caller's job; this script only reports.

Invocation:

    clean_work_safety.py                       # classify every task dir under cwd's .ai-work/
    clean_work_safety.py auth-flow pay-rework  # classify only these slugs
    clean_work_safety.py --json                # machine-readable verdicts
    clean_work_safety.py --repo-root PATH      # operate on PATH/.ai-work/ (worktree root)
    clean_work_safety.py --ai-work-root PATH   # point directly at a .ai-work/ dir (tests)
    clean_work_safety.py --dry-run             # accepted for interface symmetry; no-op (read-only)

Exit code: 1 when any task dir is BLOCK (the gate bites), else 0. An absent or
empty `.ai-work/` reports "nothing to clean" and exits 0.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _repo_root import resolve_repo_root as _resolve_repo_root
from _script_cli import configure_logging
from artifact_registry import cleanup_policy_for

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
AI_WORK_DIRNAME = ".ai-work"
# A SAFE task dir idle longer than this is a prime cleanup candidate (advisory only).
STALE_DAYS = 14

# An unchecked GitHub-flavoured task box anywhere in WIP.md means the pipeline
# still has work to do — the strongest "do not delete" signal.
UNCHECKED_STEP_RE = re.compile(r"^\s*[-*]\s+\[ \]", re.MULTILINE)
# A requirement id in SYSTEMS_PLAN.md is the prefix below followed by an
# uppercase-or-digit run (a bare number, or a domain segment then a number); that
# char class after the hyphen is what avoids matching prose like "REQ-uirements".
REQ_ID_RE = re.compile(r"\bREQ-[A-Z0-9]")
CONSUMED_RE = re.compile(r"\[CONSUMED\]")
# The marker the verifier/operator adds to LEARNINGS.md after folding a
# verification report's recurring patterns in — clears the verification warning.
VERIFICATION_MERGED_RE = re.compile(r"verification patterns merged", re.IGNORECASE)

logger = logging.getLogger("clean_work_safety")

# Registry cleanup_policy -> this scanner's severity class. Conservative by
# construction: an unknown or `archive` policy WARNs (never SAFE), so the
# one-way-door gate can only ever delete LESS than today.
_POLICY_SEVERITY: dict[str, str] = {
    "block-if-active": "block",
    "consume-marker": "warn",
    "archive": "warn",
    "delete": "safe",
}


def _severity_for(name: str) -> str:
    """Deletion severity class for an artifact, sourced from the registry's
    cleanup_policy. Conservative: an unknown/unregistered/`archive` policy WARNs
    (never SAFE), so the one-way-door gate can only ever delete LESS than today.
    """
    return _POLICY_SEVERITY.get(cleanup_policy_for(name) or "", "warn")


# -- Verdict model ------------------------------------------------------------


@dataclass(frozen=True)
class Reason:
    """One reason a task directory is not trivially safe to delete."""

    code: str  # stable machine key (e.g. "open-rework")
    blocker: str  # the artifact filename that triggered it
    severity: str  # "block" | "warn"
    remedy: str  # what to do before deleting


@dataclass(frozen=True)
class TaskVerdict:
    slug: str
    classification: str  # "BLOCK" | "WARN" | "SAFE"
    reasons: list[Reason] = field(default_factory=list)
    age_days: int | None = None  # days since the newest file's mtime; None if the dir has no files


# -- Content probes -----------------------------------------------------------


def _read(path: Path) -> str:
    """Return file text, or "" on any read failure (missing/binary/permission)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _has_unchecked_step(task_dir: Path) -> bool:
    wip = task_dir / "WIP.md"
    return wip.exists() and UNCHECKED_STEP_RE.search(_read(wip)) is not None


def _learnings_has_merge_marker(task_dir: Path) -> bool:
    learnings = task_dir / "LEARNINGS.md"
    return learnings.exists() and VERIFICATION_MERGED_RE.search(_read(learnings)) is not None


def _systems_plan_has_req(task_dir: Path) -> bool:
    plan = task_dir / "SYSTEMS_PLAN.md"
    return plan.exists() and REQ_ID_RE.search(_read(plan)) is not None


def _pre_refactor_unconsumed(task_dir: Path) -> bool:
    plan = task_dir / "PRE_REFACTOR_PLAN.md"
    return plan.exists() and CONSUMED_RE.search(_read(plan)) is None


# -- Classification -----------------------------------------------------------


def detect_reasons(task_dir: Path) -> list[Reason]:
    """Return every deletion-safety reason for one task directory, ordered by severity."""
    reasons: list[Reason] = []

    # BLOCK — live or incomplete pipeline state.
    if _has_unchecked_step(task_dir):
        if _severity_for("WIP.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "active-pipeline",
                    "WIP.md",
                    _severity_for("WIP.md"),
                    "pipeline has unchecked steps — finish or /resume-pipeline it, or pass --force",
                )
            )
    if (task_dir / "REWORK_MANIFEST.md").exists():
        if _severity_for("REWORK_MANIFEST.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "open-rework",
                    "REWORK_MANIFEST.md",
                    _severity_for("REWORK_MANIFEST.md"),
                    "rework worktrees may still be open — complete rework, or pass --force",
                )
            )

    # WARN — durable-state handoff pending.
    if (task_dir / "LEARNINGS.md").exists():
        if _severity_for("LEARNINGS.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "unmerged-learnings",
                    "LEARNINGS.md",
                    _severity_for("LEARNINGS.md"),
                    "merge insights into .ai-state/ ADRs/specs or project docs first",
                )
            )
    if (task_dir / "VERIFICATION_REPORT.md").exists() and not _learnings_has_merge_marker(task_dir):
        if _severity_for("VERIFICATION_REPORT.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "unmerged-verification",
                    "VERIFICATION_REPORT.md",
                    _severity_for("VERIFICATION_REPORT.md"),
                    "fold recurring patterns into LEARNINGS.md (add a "
                    "'### Verification Patterns Merged' marker) first",
                )
            )
    if (task_dir / "traceability.yml").exists():
        if _severity_for("traceability.yml") in ("block", "warn"):
            reasons.append(
                Reason(
                    "unarchived-traceability",
                    "traceability.yml",
                    _severity_for("traceability.yml"),
                    "render into an archived .ai-state/specs/SPEC_*.md matrix first",
                )
            )
    elif _systems_plan_has_req(task_dir):
        if _severity_for("SYSTEMS_PLAN.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "unarchived-spec",
                    "SYSTEMS_PLAN.md",
                    _severity_for("SYSTEMS_PLAN.md"),
                    "SYSTEMS_PLAN.md carries REQ ids — confirm the spec was archived "
                    "to .ai-state/specs/ first",
                )
            )
    if (task_dir / "RECOVERY_LOG.md").exists():
        if _severity_for("RECOVERY_LOG.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "recovery-audit",
                    "RECOVERY_LOG.md",
                    _severity_for("RECOVERY_LOG.md"),
                    "auto-recovery audit trail — preserve or summarize before deleting",
                )
            )
    if _pre_refactor_unconsumed(task_dir):
        if _severity_for("PRE_REFACTOR_PLAN.md") in ("block", "warn"):
            reasons.append(
                Reason(
                    "unconsumed-refactor",
                    "PRE_REFACTOR_PLAN.md",
                    _severity_for("PRE_REFACTOR_PLAN.md"),
                    "pre-refactor contract not marked [CONSUMED] — confirm td-NNN "
                    "transitions landed first",
                )
            )

    return reasons


def _newest_mtime(task_dir: Path) -> float | None:
    """Most recent file mtime under `task_dir`, or None when it holds no files."""
    mtimes = [p.stat().st_mtime for p in task_dir.rglob("*") if p.is_file()]
    return max(mtimes) if mtimes else None


def classify(task_dir: Path, now: float | None = None) -> TaskVerdict:
    """Classify one task directory as BLOCK / WARN / SAFE, with its idle age."""
    now = time.time() if now is None else now
    reasons = detect_reasons(task_dir)
    if any(r.severity == "block" for r in reasons):
        classification = "BLOCK"
    elif reasons:
        classification = "WARN"
    else:
        classification = "SAFE"
    newest = _newest_mtime(task_dir)
    age_days = int((now - newest) // 86400) if newest is not None else None
    return TaskVerdict(
        slug=task_dir.name,
        classification=classification,
        reasons=reasons,
        age_days=age_days,
    )


def scan_task_dirs(
    ai_work_root: Path, slugs: list[str], now: float | None = None
) -> list[TaskVerdict]:
    """Classify task-scoped subdirectories of `ai_work_root`.

    Hidden entries and the root-level `PIPELINE_STATE.md` snapshot file are not
    task directories and are skipped. When `slugs` is non-empty, only those
    directories are classified.
    """
    if not ai_work_root.is_dir():
        return []
    dirs = sorted(p for p in ai_work_root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if slugs:
        wanted = set(slugs)
        dirs = [d for d in dirs if d.name in wanted]
    return [classify(d, now) for d in dirs]


# -- Rendering ----------------------------------------------------------------


def _is_stale_safe(v: TaskVerdict) -> bool:
    """A SAFE dir idle past the threshold — a prime cleanup candidate."""
    return v.classification == "SAFE" and v.age_days is not None and v.age_days >= STALE_DAYS


def _summary_counts(verdicts: list[TaskVerdict]) -> dict[str, int]:
    counts = {"total": len(verdicts), "block": 0, "warn": 0, "safe": 0, "stale_safe": 0}
    for v in verdicts:
        counts[v.classification.lower()] += 1
        if _is_stale_safe(v):
            counts["stale_safe"] += 1
    return counts


def render_text(verdicts: list[TaskVerdict], ai_work_root: Path) -> str:
    if not verdicts:
        return f"Nothing to clean: no task directories under {ai_work_root}/"
    lines: list[str] = []
    for v in verdicts:
        age = f"idle {v.age_days}d" if v.age_days is not None else "empty"
        stale = "  ← stale; prime cleanup candidate" if _is_stale_safe(v) else ""
        lines.append(f"{ai_work_root.name}/{v.slug}    {v.classification}  ({age}){stale}")
        for r in v.reasons:
            lines.append(f"      [{r.severity}] {r.code}: {r.blocker} — {r.remedy}")
    c = _summary_counts(verdicts)
    lines.append("")
    lines.append(
        f"{c['total']} task dir(s): {c['block']} BLOCK, {c['warn']} WARN, {c['safe']} SAFE "
        f"({c['stale_safe']} stale, idle ≥{STALE_DAYS}d)"
    )
    return "\n".join(lines)


def render_json(verdicts: list[TaskVerdict], ai_work_root: Path) -> str:
    payload = {
        "ai_work_root": str(ai_work_root),
        "task_dirs": [asdict(v) for v in verdicts],
        "summary": _summary_counts(verdicts),
    }
    return json.dumps(payload, indent=2, sort_keys=False)


# -- CLI ----------------------------------------------------------------------


def resolve_ai_work_root(repo_root: Path, override: str | None) -> Path:
    """Resolve the `.ai-work/` directory to scan."""
    if override:
        return Path(override).resolve()
    return repo_root / AI_WORK_DIRNAME


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="clean_work_safety",
        description=(
            "Classify .ai-work/<slug>/ directories as BLOCK / WARN / SAFE for "
            "deletion. Read-only; exit 1 when any BLOCK is present."
        ),
    )
    parser.add_argument(
        "slugs",
        nargs="*",
        help="task slugs to classify; omit to scan every task directory",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        help=(
            "worktree root whose .ai-work/ to scan; resolved from "
            "`git rev-parse --show-toplevel` when omitted"
        ),
    )
    parser.add_argument(
        "--ai-work-root",
        metavar="PATH",
        help="point directly at a .ai-work/ directory (overrides --repo-root; for tests)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON verdicts")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="accepted for interface symmetry; this scanner is read-only (no-op)",
    )
    parser.add_argument("--verbose", action="store_true", help="enable DEBUG logging")
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    ai_work_root = resolve_ai_work_root(repo_root, args.ai_work_root)
    verdicts = scan_task_dirs(ai_work_root, args.slugs)
    output = (
        render_json(verdicts, ai_work_root) if args.json else render_text(verdicts, ai_work_root)
    )
    print(output)
    return 1 if any(v.classification == "BLOCK" for v in verdicts) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("clean_work_safety: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
