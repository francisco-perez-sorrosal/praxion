---
id: dec-draft-c556ea55
title: Adopt Obsidian Shape B as default-on integration for Praxion-managed projects
status: proposed
category: architectural
date: 2026-05-19
summary: Shape B (Praxion repo as Obsidian vault, kepano/obsidian-skills in .claude/skills/) is the default-on integration shape for /onboard-project and /new-project; opt-out via --no-obsidian.
tags: [obsidian, onboarding, integration, shape-b, kepano]
made_by: agent
agent_type: systems-architect
branch: worktree-obsidian-shape-b-onboarding
pipeline_tier: standard
affected_files:
  - install.sh
  - scripts/install-obsidian-deps.sh
  - claude/canonical-blocks/obsidian-integration.md
  - commands/onboard-project.md
  - commands/new-project.md
  - commands/onboard-project-obsidian.md
  - new_project.sh
  - docs/obsidian-shape-b.md
---

## Context

The research findings in `.ai-work/obsidian-integration-research/RESEARCH_FINDINGS.md` (synthesis + CLI addendum) map four integration architectures (Shape A, A+, B, C, plus a hypothetical Shape E for Headless Sync) against Praxion's artifact inventory and operator workflows. Shape B — treating the Praxion repo (or any Praxion-managed project) as an Obsidian vault, with `kepano/obsidian-skills` dropped into `.claude/skills/` so agents are vault-fluent on first run — emerges as the lowest-friction, highest-value first step. The Obsidian CEO (Steph Ango / kepano) shipped the official skill package, which dissolves the "is this a sanctioned pattern" question and makes the integration a first-party endorsement.

Praxion's onboarding pipeline already has a default-on / opt-out shape for analogous integrations: the AaC tier install (Phase 8b), the ML/AI training scaffold (Phase 8c), the hackathon mode gate (Phase 5b). Adding Shape B as a new Phase 8d follows the established pattern.

The user explicitly pre-decided that Shape B should be default-on with `--no-obsidian` opt-out for managed projects, and that Praxion itself should adopt Shape B as part of this PR (dogfood).

## Decision

Adopt Obsidian Shape B as the **default-on** Praxion-managed-project integration. The opt-out is `--no-obsidian` on `/onboard-project` and `/new-project` (plus `PRAXION_NEW_PROJECT_NO_OBSIDIAN=1` env var for headless `new_project.sh`). A new Phase 8d in the existing onboarding flow installs the per-project surfaces (gitignore block, kepano-skills link, CLAUDE.md block). A standalone `/onboard-project-obsidian` command allows retrofit on already-onboarded projects.

Defer Shape A (`.ai-state/` as a separate vault), Shape A+ (TECH_DEBT_LEDGER migration to per-row notes), Shape C (cross-pipeline memory vault), and the hypothetical Shape E (Headless Sync) — each can be revisited if Shape B proves sticky and the next layer's value becomes clear.

## Considered Options

### Option 1 — Shape B, default-on (chosen)

- **Pros:** Lowest cost (a `.gitignore` block + one symlink + one CLAUDE.md heading); highest reach (every onboarded project gets it); aligns with the kepano-skills strategic anchor; opt-out is one flag for operators who don't want it.
- **Cons:** Every onboarded project gets a `## Obsidian Integration` heading even if its owner doesn't use Obsidian. The block is small and removable.

### Option 2 — Shape B, opt-in (default-skip)

- **Pros:** Maximal operator consent — Shape B only lands when someone explicitly asks for it.
- **Cons:** Reduces reach drastically; most operators never discover Shape B exists. Contradicts the pre-decided constraint and the research's "lowest-friction first step" recommendation.

### Option 3 — Shape A (`.ai-state/` as separate vault), opt-in

- **Pros:** Narrower surface (only `.ai-state/` is opened in Obsidian); no agent-write concerns; pure view layer.
- **Cons:** Operator has to open a separate vault separately from their project; agents don't gain Obsidian-fluency benefits; doesn't solve the "agents write vault-grade markdown by default" goal.

### Option 4 — Shape C (cross-pipeline memory vault), as v1

- **Pros:** Addresses the "every session starts from zero" failure mode.
- **Cons:** Requires new agent code, new schema, vault curation strategy, junk-note avalanche mitigation. High cost; deferred.

### Option 5 — No integration

- **Pros:** No new surface; nothing to maintain.
- **Cons:** Forgoes the kepano-skills value that costs ~0 to claim. Misses the strategic-signal alignment.

## Consequences

**Positive:**

- Every Praxion-managed project gets Obsidian-vault-fluent agents by default — researcher fragments, ADR drafts, LEARNINGS.md all become vault-grade Markdown without per-project effort.
- The Praxion install + onboarding chain absorbs the new integration through the existing additive-phase pattern (Phase 8d alongside 8b, 8c). No agent pipeline changes.
- Operators who don't use Obsidian opt out with one flag; the block in their CLAUDE.md is small and removable.
- Dogfood pass against Praxion itself validates the procedure end-to-end before any other operator runs it.

**Negative:**

- Carries the upstream-churn risk of any community dependency (mitigated by Decision B's fetch-at-install + marker file).
- Operators on hostile environments (no network at install time, no Obsidian Desktop) see warnings and continue without Shape B; some will not understand why their project lacks the integration. Mitigated by `--check` mode diagnostic and `/onboard-project-obsidian` retrofit.
- Carries the named risk that an agent could invoke `obsidian eval` despite a prose allowlist — addressed by Decision C (CLI allowlist policy).
