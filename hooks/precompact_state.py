#!/usr/bin/env python3
"""Snapshot .ai-work/ pipeline state before context compaction.

Reads the first 30 lines of each pipeline document and writes a condensed
PIPELINE_STATE.md that the agent can re-read after compaction to restore
orientation. Exits 0 unconditionally -- must never block compaction.
"""

import sys
from pathlib import Path

# Ordered by pipeline flow so the snapshot reads as a narrative of the run.
# Each doc is snapshotted only if present (absent ones are skipped), so listing
# conditional/specialist artifacts here is free for pipelines that never produce them.
# SKILL_GENESIS_REPORT.md is intentionally absent: dec-186 moved it out of .ai-work/
# to .ai-state/skill_genesis_reports/, so it is no longer an in-flight pipeline doc.
PIPELINE_DOCS = [
    "TASK_BRIEF.md",
    "IDEA_PROPOSAL.md",
    "RESEARCH_FINDINGS.md",
    "INTERFACE_DESIGN.md",
    "TRANSACTIONS_DESIGN.md",
    "SYSTEMS_PLAN.md",
    "PRE_REFACTOR_PLAN.md",
    "IMPLEMENTATION_PLAN.md",
    "WIP.md",
    "PROGRESS.md",
    "LEARNINGS.md",
    "TEST_RESULTS.md",
    "VERIFICATION_REPORT.md",
    "REWORK_MANIFEST.md",
    "RECOVERY_LOG.md",
]

HEAD_LINES = 30


def _find_ai_work() -> Path | None:
    """Locate .ai-work/ by walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".ai-work"
        if candidate.is_dir():
            return candidate
    return None


def _head(path: Path, n: int) -> str:
    """Read first n lines of a file, return empty string on failure."""
    try:
        with open(path) as f:
            lines = []
            for _ in range(n):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
            return "".join(lines)
    except Exception:
        return ""


def main():
    try:
        # Consume stdin (hook payload) to avoid broken pipe
        sys.stdin.read()

        ai_work = _find_ai_work()
        if not ai_work:
            return

        sections = []
        # Scan task-scoped subdirectories for pipeline documents
        task_dirs = sorted(
            p for p in ai_work.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        if not task_dirs:
            # Fallback: check root for legacy flat layout
            task_dirs = [ai_work]

        for task_dir in task_dirs:
            slug = task_dir.name if task_dir != ai_work else "(root)"
            for doc_name in PIPELINE_DOCS:
                doc_path = task_dir / doc_name
                if not doc_path.exists():
                    continue
                content = _head(doc_path, HEAD_LINES)
                if content.strip():
                    header = f"{slug}/{doc_name}" if slug != "(root)" else doc_name
                    sections.append(f"## {header}\n\n```\n{content}```\n")

        if not sections:
            return

        state = "# Pipeline State Snapshot\n\n"
        state += "Pre-compaction snapshot of .ai-work/ documents (first "
        state += f"{HEAD_LINES} lines each).\n\n"
        state += "\n".join(sections)

        state += (
            "\n## Durable Learning Reminder\n\n"
            "Praxion has no curated-memory backend after dec-225 (no `remember()`/`recall()` "
            "tools). Capture cross-session insights in `.ai-work/<slug>/LEARNINGS.md` during "
            "the pipeline, or promote durable learnings to `.ai-state/` ADRs, archived specs, "
            "or project docs before task cleanup.\n"
        )

        output_path = ai_work / "PIPELINE_STATE.md"
        with open(output_path, "w") as f:
            f.write(state)

    except Exception:
        pass


if __name__ == "__main__":
    main()
