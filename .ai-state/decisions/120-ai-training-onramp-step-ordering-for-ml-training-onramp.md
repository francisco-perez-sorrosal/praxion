---
id: dec-120
title: ML training onramp step ordering — skills-first, no test-engineer pairing
status: accepted
category: implementation
date: 2026-05-03
summary: 13-step plan ordered skills → reference extensions → rules → rule edits → agent extensions → commands → onboarding → architecture docs. No test-engineer pairing (all deliverables are Markdown; verifier is the quality gate).
tags: [ml-training, implementation-plan, step-ordering, testing-strategy]
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
affected_files:
  - skills/ml-training/
  - skills/llm-training-eval/
  - skills/neo-cloud-abstraction/
  - commands/run-experiment.md
  - skills/onboard-project/SKILL.md
affected_reqs: []
re_affirms: dec-117
---

# ADR — Step ordering and test-pairing strategy for ML training onramp

## Context

The ML training onramp delivers 17 new files + 6 edits to existing files across skills, rules, commands, agents, and architecture docs. The implementation-planner must decide: (1) in what order to sequence the 13 steps, and (2) whether any step warrants test-engineer pairing.

Two ordering constraints are hard:
- Skills must exist before commands reference them (`/run-experiment` references `ml-training`, `llm-training-eval`, `neo-cloud-abstraction`)
- The verifier Phase 3a extension depends on the `llm-training-eval` schema reference (Step 2) for its activation logic and schema loading instruction
- `/onboard-project` Phase 8c depends on `operational-modes.md` (Step 1), the new rules (Step 7), and `/run-experiment` (Step 10) to provide accurate pointers

One architectural coupling applies: `gpu-compute-budgeting.md` is a `deployment` reference (Q2 resolution), not a `ml-training` reference. The step must update `deployment/SKILL.md`'s satellite listing in the same commit.

## Decision

**Step ordering:** skills-first (Steps 1–4), then small reference extensions + satellite edits (Steps 5–6), then new rules (Step 7), then rule edits (Step 8), then agent extension (Step 9), then commands (Steps 10–11), then onboard-project Phase 8c (Step 12), then architecture docs (Step 13).

**Test-engineer pairing:** none. All 13 deliverables are Markdown artifacts (skills, rules, commands, agent edits). No executable code is authored. The verifier agent is the quality gate; sentinel provides ongoing coverage.

## Considered Options

### Option 1 — Group by artifact type (all skills → all rules → all commands)

**Pros:** Conceptually clean; all rules written after all skills.

**Cons:** The "all rules" step becomes large (3 new + 2 edits = 5 files); produces forward references in rule bodies to commands that haven't been authored yet; the ML Experiment Mode addendum in `git-conventions.md` references experiment commit format that is fully defined only in `/run-experiment` — awkward when git-conventions is authored before the command exists.

### Option 2 — Skills-first, then extensions, then rules, then agents/commands, then onboarding (chosen)

**Pros:**
- Each step is a meaningful, independently releasable unit
- Skill cross-references are resolvable by the time rule bodies reference them
- Agent extensions come after their schema dependencies (llm-training-eval before verifier)
- Commands come after all skills they reference
- `/onboard-project` Phase 8c comes last among edits, because it needs the most dependencies (operational-modes, rules, run-experiment) in place for accurate pointers

**Cons:**
- Rules (Step 7) reference commands (Steps 10–11) that aren't authored yet — the rules' bodies may need to use future-tense or conditional phrasing ("see `/run-experiment` when authored")
- Mitigation: rules reference skill paths (`skills/neo-cloud-abstraction/`) rather than command names where possible; the `/run-experiment` pointer in Phase 8c callout is the only required command reference and that step explicitly depends on Step 10

### Option 3 — Test-engineer paired with every step

**Pros:** Formal BDD coverage.

**Cons:** This is a Markdown-only repo. Markdown content tests are verifier checks (AC list vs artifact content), not BDD test cases. A test-engineer writing tests for "does the SKILL.md have the right sections" would produce tests that duplicate what the verifier already does. The result is parallel overhead with no additional signal.

## Consequences

**Positive:**
- Dependency graph is respected at every step boundary — each step leaves a coherent intermediate state
- Verifier has a clean AC1-AC10 surface to validate against when invoked after Step 13
- Steps 5 and 6 are each one-sentence ("add X reference + update satellite listing") — surgical and independently reviewable

**Negative:**
- Step 7 (rules) may contain rule bodies that use forward-referencing ("see `/run-experiment`") to commands not yet authored — acceptable because the rules document conventions, not invoke the commands
- No automated test coverage during execution — the user reviews each step completion before advancing, and the verifier validates the final state

**Neutral:**
- 13 steps is within the 12-20 target; the step overview table makes all dependencies explicit

## Prior Decision

This ADR re-affirms `dec-117` (4 new skills + 2 reference extensions) — the step decomposition preserves the architect's skill/extension boundaries exactly. No new skill or extension is introduced beyond those decided by the architect + Q3 override.
