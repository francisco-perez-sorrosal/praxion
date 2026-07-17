---
id: dec-270
title: Agent-pipeline canonical block becomes a minimal pointer
status: accepted
category: architectural
date: 2026-07-16
summary: Restructure the agent-pipeline canonical block from a ~658-token process mirror to a ~205-token pointer (universal framing + prose pointer to the coordination rule and software-planning skill + absolute docs URL); relocate the PoC-to-production journey into the software-planning skill; resolves td-002.
tags: [canonical-blocks, onboarding, token-budget, context-engineering, claude-md, tech-debt]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - claude/canonical-blocks/agent-pipeline.md
  - commands/onboard-project.md
  - commands/new-project.md
  - hooks/test_onboard_praxion_block.py
  - skills/software-planning/SKILL.md
dissent: A no-Praxion collaborator loses the only in-repo narrative of the maintainer's pipeline, and the pointer assumes the coordination rule and skill surfaces stay installed and discoverable wherever the pipeline actually runs.
re_affirmed_by:
  - dec-271
---

## Context

The `agent-pipeline` canonical block — appended to every managed project's `CLAUDE.md` by `/onboard-project` Phase 6 and `/new-project` — had grown to 2,367 bytes (~658 tokens by the bytes/3.6 convention), 2.6x the ~250-token per-block budget enforced by `hooks/test_onboard_praxion_block.py`, and was the only block xfailed against that budget (tracked as td-002 since 2026-04-27). A context-engineer audit established three findings:

1. **Double-loading on Praxion-installed machines.** The block's pipeline-stage list, "Recognized pipeline branches" paragraph, and "Independent audits" paragraph are near-verbatim duplicates of the always-on symlinked coordination-protocol and intermediate-documents rules. ~70-80% of the block was redundant with context already loaded in every session.
2. **Inert for the no-Praxion audience.** For collaborators, CI, or Codex sessions without the plugin, the named subagents do not exist; the `adapt-claude-to-agents` skill explicitly strips this content when generating `AGENTS.md.tmpl`.
3. **Structural growth driver.** Every new pipeline capability was being mirrored into the block as a side effect of unrelated feature commits (the pre-refactor branch paragraph arrived this way). The block violated the budget from its first commit (~505 tokens) and grew ~30% since.

The 250-token budget itself was sized for the Praxion Process block and generalized to all blocks by the test — but the three sibling blocks were trimmed to fit (145-244 tokens), while agent-pipeline never was.

## Decision

Restructure the block as a **minimal pointer** (~738 bytes / ~205 conservative tokens):

- Keep the universally-true framing: tier-driven pipeline, Understand/Plan/Verify methodology, the `.ai-work/<task-slug>/` (ephemeral) vs `.ai-state/` (permanent) split, and the state-expected-deliverables delegation reminder.
- Replace the agent roster, branch mechanics, and audit paragraphs with a prose pointer: the coordination protocol rule and `software-planning` skill carry the detail. The pointer names surfaces in prose, never repo-relative paths (which dangle in onboarded projects).
- Add one absolute URL to the Praxion GitHub repository for human readers wanting the full process narrative.
- Relocate the "From PoC to production" journey paragraph — the only content present in no always-loaded rule — into the `software-planning` skill's End of Feature section.
- Remove the stale xfail; the token-budget test now enforces the block like its siblings.

## Considered Options

### Option A — Trim in place (~231 tokens)

Keep the numbered 5-agent list for standalone readability; collapse the three trailing paragraphs into a pointer sentence. Pros: preserves a self-contained narrative for no-Praxion readers. Cons: still ~90% of budget; still restates the roster the installed rules already load, so the structural redundancy and drift risk survive.

### Option B — Minimal pointer (~205 tokens) — chosen

Pros: eliminates double-loading; one source of truth for pipeline knowledge; nothing left to mirror, so the growth anti-pattern dies; degrades gracefully (inert but not misleading) without Praxion. Cons: loses the standalone roster narrative (recovered via the harness's native agent-description injection where agents exist, and the docs URL where they don't).

### Option C — Wontfix, raise or remove the budget

Pros: no change contract. Cons: the always-loaded cost is unearned (redundant when installed, inert when not); raising the ceiling does not stop the mirror-into-block growth habit.

## Consequences

**Positive:** ~450 always-loaded tokens returned per session in every managed project (the block was 45% of the five-block payload); block content can no longer drift from the coordination rule; the budget test is green across all four blocks with no xfail escape hatch.

**Negative:** already-onboarded projects keep the old block until refreshed — Phase 6's per-heading idempotency predicate skips existing `## Agent Pipeline` headings and no refresh mechanism exists (tracked as td-055); sessions with the plugin's agents but without the always-on rules (partial installs) rely on the harness's native agent-description injection plus the pointer rather than in-file detail.

## Disconfirmation

- **Falsifier:** managed-project pipeline sessions on Praxion-installed machines demonstrably lose pipeline fidelity after the trim — e.g., orchestrators stop delegating in pipeline order or misplace `.ai-work/`/`.ai-state/` artifacts at a rate the fat block's presence previously prevented.
- **Steelmanned runner-up:** Option A keeps CLAUDE.md self-documenting for every reader with zero dependence on rule installation or harness agent-listing behavior, at only ~26 tokens over the pointer's cost of losing narrative; if CLAUDE.md is valued as human documentation first and LLM context second, A is the better trade.
- **Reversal trigger:** the coordination-protocol rule stops being always-loaded in managed projects (e.g., a future plugin packaging change drops the rules symlink/injection path), leaving the pointer dangling with no in-context pipeline knowledge behind it.
