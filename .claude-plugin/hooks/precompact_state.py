#!/usr/bin/env python3
"""Snapshot .ai-work/ pipeline state before context compaction.

Reads the first 20 lines of each pipeline document and writes a condensed
PIPELINE_STATE.md that the agent can re-read after compaction to restore
orientation. Exits 0 unconditionally -- must never block compaction.
"""

import sys
from pathlib import Path

PIPELINE_DOCS = [
    "WIP.md",
    "IMPLEMENTATION_PLAN.md",
    "LEARNINGS.md",
    "PROGRESS.md",
    "RESEARCH_FINDINGS.md",
    "SYSTEMS_PLAN.md",
    "VERIFICATION_REPORT.md",
    "IDEA_PROPOSAL.md",
    "SKILL_GENESIS_REPORT.md",
]

HEAD_LINES = 20


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
            "\n## Memory Obligation\n\n"
            "Before completing, call `remember()` if you discovered any "
            "gotcha, pattern, convention, or insight that future agents "
            "should know. The memory gate will block session completion "
            "and commits without `remember()` calls.\n"
        )

        output_path = ai_work / "PIPELINE_STATE.md"
        with open(output_path, "w") as f:
            f.write(state)

    except Exception:
        pass


if __name__ == "__main__":
    main()
