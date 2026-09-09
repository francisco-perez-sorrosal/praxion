#!/usr/bin/env python3
"""Retire the PROGRESS.md per-phase write mandate from every agent definition.

Removes the "## Progress Signals" block (the per-phase write instruction) from
all 17 `agents/*.md` bodies, plus the scattered PROGRESS.md-specific write
instructions and fragment-merge plumbing that referenced it elsewhere
(`agents/CLAUDE.md`, `rules/swe/swe-agent-coordination-protocol.md`,
`skills/software-planning/references/agent-pipeline-details.md`,
`skills/software-planning/references/coordination-details.md`).

The completion handshake (terminal marker + WIP.md checkbox) is untouched --
this script only removes PROGRESS.md as a *write target* and as a *fragment
type*, never the handshake's own verification logic.

Idempotent: re-running after a partial application only touches what remains.

Usage:
    python3 scripts/strip_progress_mandate.py          # apply
    python3 scripts/strip_progress_mandate.py --check  # verify, exit 1 if stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every agents/*.md body except the catalog files (CLAUDE.md, README.md).
AGENT_FILES = sorted(
    p for p in (REPO_ROOT / "agents").glob("*.md") if p.name not in {"CLAUDE.md", "README.md"}
)

# The "## Progress Signals" heading through (not including) the next "## "
# heading. Verified uniform in shape across all 17 agents before writing this
# regex (heading + 1-2 paragraphs + a fenced code block, no nested "### ").
PROGRESS_BLOCK_RE = re.compile(r"\n## Progress Signals\n.*?(?=\n## )", re.DOTALL)

# (relative path, old string, new string) -- scattered PROGRESS.md mentions
# outside the uniform "## Progress Signals" block. Each entry is applied with
# a single str.replace(old, new, 1); if `old` is absent the entry is skipped
# (already applied or never present), which is what makes re-runs safe.
SCATTERED_EDITS: list[tuple[str, str, str]] = [
    (
        "agents/CLAUDE.md",
        "Phase 1 (Input Assessment) detects the directive on intake and logs the mode to `PROGRESS.md`. When updating",
        "Phase 1 (Input Assessment) detects the directive on intake. When updating",
    ),
    (
        "agents/CLAUDE.md",
        "Phase 1 resolves the directive before any other work and logs the resolved discipline on the first `PROGRESS.md` line. When updating",
        "Phase 1 resolves the directive before any other work. When updating",
    ),
    (
        "agents/systems-architect.md",
        "Absent any directive, default to `feature` mode. Log the detected mode to `PROGRESS.md` as the very first phase-transition line so the choice is observable. Mode determines",
        "Absent any directive, default to `feature` mode. Mode determines",
    ),
    (
        "agents/systems-architect.md",
        "When skipped, log a single line to `PROGRESS.md`: `Phase 2.5: SKIP (mode=<name>)`. The skip is the documented no-op",
        "When skipped, this is the documented no-op",
    ),
    (
        "agents/discipline-consultant.md",
        "3. Log the resolved discipline to `PROGRESS.md` by **appending only — never read that file during Round 0.** "
        "It is a shared log carrying other agents' phase lines, including the compressed conclusions of the very draft "
        "you must not see yet, so reading it to orient is partial draft exposure by construction. Append blind (`>>`), "
        "or defer your first log line until `## Independent Reading` and `## Sources Read` are committed to disk. "
        "From Round 1 onward, read it freely.\n4. Load the row's `binds-to` skill(s)",
        "3. Load the row's `binds-to` skill(s)",
    ),
    (
        "agents/discipline-consultant.md",
        "reading it is partial draft exposure by construction, the same defect as reading `PROGRESS.md` to orient.",
        "reading it is partial draft exposure by construction.",
    ),
    (
        "agents/discipline-consultant.md",
        "**Do not edit the draft, the registry, or any file another agent owns.** Your writes are your own fragment and `PROGRESS.md`.",
        "**Do not edit the draft, the registry, or any file another agent owns.** Your writes are your own fragment.",
    ),
    (
        "agents/doc-engineer.md",
        "- `LEARNINGS_doc-engineer.md` — documentation-related discoveries\n- `PROGRESS_doc-engineer.md` — phase transition signals\n",
        "- `LEARNINGS_doc-engineer.md` — documentation-related discoveries\n",
    ),
    (
        "agents/implementation-planner.md",
        "Each agent writes to fragment files (`WIP_<agent-type>.md`, `LEARNINGS_<agent-type>.md`, `PROGRESS_<agent-type>.md`) per the",
        "Each agent writes to fragment files (`WIP_<agent-type>.md`, `LEARNINGS_<agent-type>.md`) per the",
    ),
    (
        "agents/implementation-planner.md",
        "merge `WIP_<agent>.md` fragments into canonical `WIP.md` (preserving batch structure), merge `LEARNINGS_<agent>.md` into topic sections, merge `PROGRESS_<agent>.md` in timestamp order. Delete fragment files after successful merge.",
        "merge `WIP_<agent>.md` fragments into canonical `WIP.md` (preserving batch structure), merge `LEARNINGS_<agent>.md` into topic sections. Delete fragment files after successful merge.",
    ),
    (
        "agents/implementer.md",
        "Same fragment naming for `LEARNINGS_implementer.md` and `PROGRESS_implementer.md`. The supervising agent merges fragments after all concurrent agents complete.",
        "Same fragment naming for `LEARNINGS_implementer.md`. The supervising agent merges fragments after all concurrent agents complete.",
    ),
    (
        "agents/test-engineer.md",
        "Same fragment naming for `LEARNINGS_test-engineer.md` and `PROGRESS_test-engineer.md`. The supervising agent merges fragments after all concurrent agents complete.",
        "Same fragment naming for `LEARNINGS_test-engineer.md`. The supervising agent merges fragments after all concurrent agents complete.",
    ),
    (
        "agents/roadmap-cartographer.md",
        "- **`.ai-work/<task-slug>/PROGRESS.md`** — append-only phase-transition log.\n",
        "",
    ),
    (
        "agents/roadmap-cartographer.md",
        "\n\nWrite a phase marker to `.ai-work/<task-slug>/PROGRESS.md` including the derived lens set.\n\n### Phase 2",
        "\n\n### Phase 2",
    ),
    (
        "agents/roadmap-cartographer.md",
        "\n\nWrite the final phase marker to `PROGRESS.md`.\n\n## Non-Interactive Mode",
        "\n\n## Non-Interactive Mode",
    ),
    (
        "rules/swe/swe-agent-coordination-protocol.md",
        "**and** the durable artifact agrees (step's `WIP.md` checkbox flipped; `PROGRESS.md` at its final phase). A missing or contradicted marker is a **suspected truncation**:",
        "**and** the durable artifact agrees (step's `WIP.md` checkbox flipped). A missing or contradicted marker is a **suspected truncation**:",
    ),
    (
        "rules/swe/swe-agent-coordination-protocol.md",
        "Monitor `.ai-work/<task-slug>/PROGRESS.md` for status; check output before proceeding with dependent work.",
        "Check output before proceeding with dependent work.",
    ),
    (
        "skills/software-planning/references/agent-pipeline-details.md",
        'Because every status signal (`WIP.md`, `PROGRESS.md`, the terminal marker) is authored by the agent itself, "agent died"',
        'Because every status signal (`WIP.md`, the terminal marker) is authored by the agent itself, "agent died"',
    ),
    (
        "skills/software-planning/references/agent-pipeline-details.md",
        "2. **Durable artifact agrees** — for a claimed `[COMPLETE]`, the step's `WIP.md` checkbox is flipped (`- [x]` / `[COMPLETE]`) and, where present, `PROGRESS.md`'s last phase line is the agent's final phase. A marker that contradicts the artifact is as suspect as a missing one.",
        "2. **Durable artifact agrees** — for a claimed `[COMPLETE]`, the step's `WIP.md` checkbox is flipped (`- [x]` / `[COMPLETE]`). A marker that contradicts the artifact is as suspect as a missing one.",
    ),
    (
        "skills/software-planning/references/agent-pipeline-details.md",
        "(so they survive a hard cut that drops `PROGRESS.md`). It tells you *which agent stopped* and *where it last wrote* — an accelerator, never the arbiter. `PROGRESS.md` and the chronograph's `get_pipeline_status` are weaker hints of the same kind.",
        "(so they survive a hard cut mid-work). It tells you *which agent stopped* and *where it last wrote* — an accelerator, never the arbiter. The chronograph's `get_pipeline_status` is a weaker hint of the same kind.",
    ),
    (
        "skills/software-planning/references/agent-pipeline-details.md",
        "When concurrent agents write to fragment files (`WIP_<agent>.md`, `LEARNINGS_<agent>.md`, `PROGRESS_<agent>.md`), the supervising agent",
        "When concurrent agents write to fragment files (`WIP_<agent>.md`, `LEARNINGS_<agent>.md`), the supervising agent",
    ),
    (
        "skills/software-planning/references/agent-pipeline-details.md",
        "4. Incorporate `LEARNINGS.md` entries from the merged worktree using the topic-section merge protocol above.\n5. Same for `PROGRESS.md` fragments.\n",
        "4. Incorporate `LEARNINGS.md` entries from the merged worktree using the topic-section merge protocol above.\n",
    ),
    (
        "skills/software-planning/references/coordination-details.md",
        "`## Independent Reading` plus an explicit `## Sources Read` list make the isolation checkable from the artifact itself, not merely asserted. **`PROGRESS.md` is append-only for the consultant during Round 0 and must not be read**: it is a shared log carrying other agents' phase lines, including compressed conclusions from the very draft isolation exists to withhold, so reading it to orient leaks the draft by construction rather than by carelessness. **`.ai-state/CONSULT_PRIORS.md` is off-limits too**",
        "`## Independent Reading` plus an explicit `## Sources Read` list make the isolation checkable from the artifact itself, not merely asserted. **`.ai-state/CONSULT_PRIORS.md` is off-limits too**",
    ),
    (
        "skills/software-planning/references/coordination-details.md",
        "- All three write to fragment files (`WIP_<agent-type>.md`, `LEARNINGS_<agent-type>.md`, `PROGRESS_<agent-type>.md`) to avoid document collisions.",
        "- All three write to fragment files (`WIP_<agent-type>.md`, `LEARNINGS_<agent-type>.md`) to avoid document collisions.",
    ),
    (
        "skills/software-planning/references/coordination-details.md",
        "| `LEARNINGS.md` | `LEARNINGS_<agent-type>.md` | `LEARNINGS_implementer.md`, `LEARNINGS_doc-engineer.md` |\n| `PROGRESS.md` | `PROGRESS_<agent-type>.md` | `PROGRESS_implementer.md`, `PROGRESS_doc-engineer.md` |\n",
        "| `LEARNINGS.md` | `LEARNINGS_<agent-type>.md` | `LEARNINGS_implementer.md`, `LEARNINGS_doc-engineer.md` |\n",
    ),
    (
        "skills/software-planning/references/coordination-details.md",
        "Fragment files are deleted after a successful merge. For the full per-document-type merge schemas and invariants (WIP, LEARNINGS, PROGRESS reconciliation), see",
        "Fragment files are deleted after a successful merge. For the full per-document-type merge schemas and invariants (WIP, LEARNINGS reconciliation), see",
    ),
    (
        "skills/software-planning/references/coordination-details.md",
        "- `LEARNINGS.md` topic-section merge with attribution preservation and deduplication policy.\n- `PROGRESS.md` timestamp-ordered append with duplicate detection.\n- Post-merge invariants for each document type.",
        "- `LEARNINGS.md` topic-section merge with attribution preservation and deduplication policy.\n- Post-merge invariants for each document type.",
    ),
]

# The whole "### PROGRESS.md Reconciliation" subsection in agent-pipeline-details.md,
# removed as a block (heading through the line before the next "### " heading).
PROGRESS_RECONCILIATION_RE = re.compile(
    r"\n### PROGRESS\.md Reconciliation\n.*?(?=\n### TEST_RESULTS\.md Reconciliation)",
    re.DOTALL,
)


def strip_progress_blocks() -> list[Path]:
    touched = []
    for path in AGENT_FILES:
        text = path.read_text(encoding="utf-8")
        new_text, n = PROGRESS_BLOCK_RE.subn("", text)
        if n:
            path.write_text(new_text, encoding="utf-8")
            touched.append(path)
    return touched


def strip_progress_reconciliation_section() -> bool:
    path = REPO_ROOT / "skills/software-planning/references/agent-pipeline-details.md"
    text = path.read_text(encoding="utf-8")
    new_text, n = PROGRESS_RECONCILIATION_RE.subn("", text)
    if n:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def apply_scattered_edits() -> list[tuple[str, str]]:
    """Returns list of (file, old_snippet_prefix) actually applied."""
    applied = []
    by_file: dict[str, str] = {}
    for rel, old, new in SCATTERED_EDITS:
        path = REPO_ROOT / rel
        if rel not in by_file:
            by_file[rel] = path.read_text(encoding="utf-8")
        text = by_file[rel]
        if old in text:
            by_file[rel] = text.replace(old, new, 1)
            applied.append((rel, old[:60]))
    for rel, text in by_file.items():
        (REPO_ROOT / rel).write_text(text, encoding="utf-8")
    return applied


# Surfaces beyond `agents/` that may mention PROGRESS.md. The original sweep
# scanned only agent definitions, so producer-side claims survived in user docs
# and in a canonical block shipped to every managed project -- two of them
# asserting the opposite of what the corresponding command says. These paths are
# scanned for any PROGRESS.md mention, and every legitimate one must be
# allowlisted below with the reason it is legitimate.
WIDER_SCAN_GLOBS = (
    "commands/*.md",
    "docs/*.md",
    "claude/canonical-blocks/*.md",
    "skills/*/SKILL.md",
    "skills/*/references/*.md",
)

# PROGRESS.md survives as an **orchestrator-owned hackathon journal**: the
# per-phase *agent* write mandate is what was retired. Each entry names a file
# permitted to mention it, and why.
WIDER_SCAN_ALLOWLIST: dict[str, str] = {
    # The hackathon spine's own definition: the orchestrator records skipped
    # stages and mid-task movement here, and the block names it as sole writer.
    "claude/canonical-blocks/hackathon-mode.md": "defines the orchestrator-owned journal",
    "skills/onboard-project/references/claude-md-blocks.md": "synced copy of the block above",
    # States that the agent no longer maintains the log -- a denial, not a mandate.
    "commands/skill-genesis.md": "documents the retirement",
    # Consumes orchestrator writes; the branch is live but narrow.
    "hooks/send_event.py": "reads the journal, never mandates a write",
    # A dashboard live-refresh example, not a write instruction.
    "rules/writing/html-output-conventions.md": "cites it as a polling example",
    # A record of what a past experiment observed. Factual history, like a
    # finalized ADR: describing a write that happened is not mandating one.
    "docs/multidisciplinary-identities-evidence.md": "historical experiment record",
    # The artifact inventory must list every artifact, including this one; its
    # entry names the orchestrator as sole writer and the hackathon-only scope.
    "skills/software-planning/references/artifact-inventory.md": "inventories it correctly",
}


def check_wider_surfaces() -> list[str]:
    """Flag PROGRESS.md mentions outside `agents/` that are not allowlisted.

    `--check` passed while five surfaces still promised producer-side behaviour
    no agent performs any more, because nothing outside `agents/` was scanned.
    """
    violations: list[str] = []
    for pattern in WIDER_SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in WIDER_SCAN_ALLOWLIST:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "PROGRESS.md" in text or "PROGRESS_" in text:
                violations.append(
                    f"{rel}: mentions PROGRESS.md but is not in WIDER_SCAN_ALLOWLIST; "
                    "PROGRESS.md is orchestrator-written in hackathon mode only"
                )
    return violations


def check() -> list[str]:
    """Returns a list of violation descriptions; empty means clean."""
    violations = []
    for path in AGENT_FILES:
        text = path.read_text(encoding="utf-8")
        if "## Progress Signals" in text:
            violations.append(f"{path}: still carries '## Progress Signals'")
        if "PROGRESS.md" in text or "PROGRESS_" in text:
            violations.append(f"{path}: still mentions PROGRESS.md/PROGRESS_")
    for rel, old, _new in SCATTERED_EDITS:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if old in text:
            violations.append(f"{rel}: stale snippet still present: {old[:60]!r}")
    reconciliation_path = (
        REPO_ROOT / "skills/software-planning/references/agent-pipeline-details.md"
    )
    if "### PROGRESS.md Reconciliation" in reconciliation_path.read_text(encoding="utf-8"):
        violations.append(
            f"{reconciliation_path}: '### PROGRESS.md Reconciliation' section still present"
        )
    violations.extend(check_wider_surfaces())
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only, do not write")
    args = parser.parse_args()

    if args.check:
        violations = check()
        if violations:
            print(f"FAIL: {len(violations)} stale PROGRESS.md mandate reference(s) remain:")
            for v in violations:
                print(f"  - {v}")
            return 1
        print("OK: no stale PROGRESS.md per-phase write mandate references found.")
        return 0

    touched_blocks = strip_progress_blocks()
    touched_section = strip_progress_reconciliation_section()
    applied_scattered = apply_scattered_edits()

    print(f"Removed '## Progress Signals' block from {len(touched_blocks)} agent file(s).")
    print(f"Removed '### PROGRESS.md Reconciliation' section: {touched_section}")
    print(f"Applied {len(applied_scattered)} scattered edit(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
