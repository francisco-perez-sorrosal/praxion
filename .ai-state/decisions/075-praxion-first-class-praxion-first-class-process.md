---
id: dec-075
title: Praxion-as-First-Class — process-driven development with universal rule-inheritance
status: proposed
category: architectural
date: 2026-04-27
summary: Three-layer enforcement (canonical L2 block + L3 hooks + existing L1 rules) makes Praxion's process the default mode and propagates the behavioral contract to every subagent including host-native ones.
tags: [process, rule-inheritance, hooks, subagents, behavioral-contract, channel-c, channel-b, l2-block]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hooks/inject_subagent_context.py
  - hooks/inject_process_framing.py
  - hooks/hooks.json
  - hooks/inject_memory.py
  - commands/onboard-project.md
  - commands/new-project.md
  - skills/hook-crafting/references/output-patterns.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-14, REQ-15]
---

## Context

Praxion's development process — the tier selector, SDD, three-document model, behavioral contract, agent pipeline, learning loop, ADR conventions, memory protocol — is the operational expression of the philosophy in `~/.claude/CLAUDE.md`. When a user works in a Praxion-managed project, this process must be the default mode, not a feature the user opts into; and Praxion's universal rules must reach every subagent the orchestrator spawns, including host-native subagents (Explore, Plan, general-purpose) that do not load CLAUDE.md and have no `skills:` frontmatter.

Two technical realities constrain the design:

1. **Subagents do not load CLAUDE.md.** Confirmed via official Claude Code docs and GitHub issues #6825, #8395 (closed as not-planned). Praxion-native agents codify rule content in their system-prompt body by author discipline; host-native agents do not.
2. **`SubagentStart` `additionalContext` is silently ignored.** The current `inject_memory.py` SubagentStart code path has been inert in production. The hook-crafting skill's `output-patterns.md:13` lists SubagentStart as supporting `additionalContext` — this contradicts official docs and is wrong.

Channel A (plugin install) propagates hooks universally; Channel B (onboarding) propagates canonical CLAUDE.md blocks at L2; Channel C (per-event hook injection) propagates universally via Channel A. `PreToolUse(Agent)` with `updatedInput.prompt` modification is the only mechanism that can inject context into a subagent's prompt before it sees anything. `UserPromptSubmit` `additionalContext` is the only mechanism for orchestrator-level per-prompt reinforcement.

## Decision

Implement three-layer enforcement of the principle:

- **L1 (already-loaded rules)**: existing always-loaded rules in `~/.claude/rules/` carry the declarative invariants (behavioral contract, agent-intermediate-documents, ADR conventions, memory protocol). No new always-loaded rule is added.
- **L2 (canonical block in onboarded projects' CLAUDE.md)**: a new `§Praxion Process` block is added to `commands/onboard-project.md` Phase 6 and byte-identically mirrored to `commands/new-project.md`. The block names the principle, the rule-inheritance corollary, the trivial-vs-non-trivial threshold, and the obligation to carry the contract into delegation prompts. Self-contained, ~250 tokens, references the coordination protocol rule rather than duplicating its content.
- **L3 (per-event hooks)**: two new hook scripts are added.
  - `hooks/inject_subagent_context.py` (`PreToolUse` matcher `Agent|Task`) injects a compact ~180-character preamble into every subagent's `prompt` via `updatedInput`. Praxion-native (`i-am:*`) subagents are skipped by default (their bodies already encode the contract); host-native subagents (`Explore`, `Plan`, `general-purpose`) always receive the injection. Opt-in `PRAXION_INJECT_NATIVE_SUBAGENTS=1` enables universal injection.
  - `hooks/inject_process_framing.py` (`UserPromptSubmit`) emits a compact ~120-character `additionalContext` reminder when (a) the project has `.ai-state/`, (b) the prompt is not a continuation, (c) the prompt is not a short-reply, (d) `PRAXION_DISABLE_PROCESS_INJECT` is unset. Otherwise fast-skips silently.

Companion hygiene work:

- The dead `SubagentStart` branch in `hooks/inject_memory.py` is removed; `inject_memory.py` is deregistered from `SubagentStart` in `hooks/hooks.json` (the `send_event.py` and `capture_session.py` SubagentStart registrations remain — those are observational hooks that work as intended).
- `skills/hook-crafting/references/output-patterns.md` is corrected: SubagentStart is removed from the additionalContext-supporting events list; a note is added pointing readers to `PreToolUse(Agent)` for subagent context injection.

## Considered Options

### Option A — Document the principle, no enforcement

Adds the §Praxion Process block to `CLAUDE.md` but no hooks. The orchestrator gains a standing instruction; subagents (especially host-native) gain nothing. The rule-inheritance corollary is stated but not delivered.

**Pros**: cheapest in tokens and engineering effort.
**Cons**: rule-inheritance gap remains; host-native subagents still produce non-conforming artifacts.

### Option B — Hook-only enforcement, no canonical block

Adds `PreToolUse(Agent)` and `UserPromptSubmit` hooks. No L2 block. Hooks ship via Channel A (plugin) so coverage is universal. The orchestrator does not see the principle stated in its loaded surface — only the per-prompt reminder.

**Pros**: zero token-budget impact; universal across install paths and project states.
**Cons**: operators reading their `CLAUDE.md` see no statement of the principle; the standing instruction is missing; reinforcement is dynamic-only.

### Option C — Three-layer enforcement (selected)

L1 already-loaded rules + L2 canonical block + L3 hooks. Each layer has a distinct job: L1 governs declarative invariants, L2 establishes the standing instruction, L3 reinforces per-event and reaches host-native subagents. The layers are not redundant — they are complementary.

**Pros**: complete coverage; closes the rule-inheritance gap; matches the existing "rules + skills + commands + hooks" mental model.
**Cons**: two new hook scripts to maintain; ~250 tokens of always-loaded budget consumed (sub-1% of 25k).

### Option D — L1-only via global CLAUDE.md update

Adds the principle to `claude/config/CLAUDE.md.tmpl` (Layer 1). Reaches every session for full-install operators, including non-Praxion projects.

**Pros**: simple to implement (template edit only).
**Cons**: excludes marketplace-only operators in non-onboarded projects; floods every non-Praxion session with Praxion-specific content (noise); does not reach subagents.

## Consequences

**Positive**:

- Every host-native subagent (Explore, Plan, general-purpose) receives the behavioral contract before it begins work — closing the rule-inheritance gap.
- Every onboarded project's `CLAUDE.md` carries the principle as a standing instruction; the operator reads it once at project entry.
- The dead `inject_memory.py` SubagentStart code path is removed; future hook-authors are not misled.
- The hook-crafting skill is corrected; no future agent design assumes SubagentStart additionalContext support.
- All three layers ship via established propagation channels (Channel A for hooks, Channel B for canonical block, existing rules for L1) — no new infrastructure needed.

**Negative**:

- ~250 tokens of always-loaded budget consumed at L2 (acceptable: 22.7k → ~22.95k of 25k).
- Per-spawn latency on Agent tool calls: ~50 ms (Python startup + filesystem stat). Negligible for sequential pipelines; visible in dense fan-out scenarios (mitigation: per-session caching of `.ai-state/` detection — deferred to implementer).
- UserPromptSubmit hook fires on every prompt; gate complexity is a maintenance surface (mitigation: gates are simple and unit-testable).
- A second-order risk: Praxion-native agent bodies could drift over time and lose contract content; the conditional-skip in `PreToolUse(Agent)` would silently miss this drift. Mitigation: sentinel staleness audits; opt-in `PRAXION_INJECT_NATIVE_SUBAGENTS=1` for belt-and-suspenders.

**Operational**:

- All new hooks are sync with declared timeouts; all return exit 0 unconditionally on internal error (existing project convention).
- Opt-out env vars (`PRAXION_DISABLE_SUBAGENT_INJECT`, `PRAXION_DISABLE_PROCESS_INJECT`) follow the existing `PRAXION_DISABLE_*` pattern.
- The §Praxion Process block follows the byte-identical-mirror contract between `commands/onboard-project.md` and `commands/new-project.md`.
- Total always-loaded surface is re-measured after the change; failure to stay under 25k blocks the merge.
