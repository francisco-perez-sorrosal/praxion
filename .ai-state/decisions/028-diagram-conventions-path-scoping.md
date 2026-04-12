---
id: dec-028
title: Narrow `rules/writing/diagram-conventions.md` path-scope from `**/*.md` to doc-authoring surfaces
status: accepted
category: configuration
date: 2026-04-12
summary: 'Replace `paths: "**/*.md"` with a narrower list (docs/, README, ARCHITECTURE, SYSTEM_DEPLOYMENT, .ai-state/, design docs) to reclaim ~2,584 chars on non-documentation sessions'
tags: [token-budget, path-scoping, rules, diagram-conventions]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/writing/diagram-conventions.md
---

## Context

`rules/writing/diagram-conventions.md` is a ~2,664-char rule whose `paths:` frontmatter is currently `**/*.md`. The Claude Code rule loader treats `**/*.md` as "every markdown session," which is effectively "always-loaded" — the rule loads whenever any `.md` file is edited, which in a Praxion session is almost all the time.

The rule's content is narrowly applicable: Mermaid syntax, node-count limits, decomposition strategy, diagram-type selection. It drives decisions only when authoring or reviewing diagrams, which happens in a small set of documentation-authoring surfaces (`docs/**`, `README.md`, `**/ARCHITECTURE.md`, `**/SYSTEM_DEPLOYMENT.md`, `.ai-state/**`, design documents under `.ai-work/**`). It does not drive decisions when editing skill definitions, agent prompts, rule files, source code, or ADRs.

The Phase 1 principles-embedding work (`dec-027`) needs ~320 chars of always-loaded headroom. The current always-loaded total is 52,130 chars against a 52,500-char ceiling (99.3% utilization, ~370 chars headroom). Adding the principles block without reclaiming budget elsewhere crosses the ceiling. Narrowing this rule's `paths:` glob is the largest available reclamation lever in always-loaded content, and it does not remove the rule itself — it scopes the rule to the sessions where it drives decisions.

## Decision

Replace the current frontmatter

```yaml
paths:
  - "**/*.md"
```

with the narrower list

```yaml
paths:
  - "docs/**"
  - "README.md"
  - "**/README.md"
  - "**/ARCHITECTURE.md"
  - "**/SYSTEM_DEPLOYMENT.md"
  - ".ai-state/**"
  - ".ai-work/**/architecture*.md"
  - ".ai-work/**/design*.md"
```

No change to the rule's body content. The rule continues to load — but only during sessions that match one of the narrower globs. Non-matching sessions (most code edits, skill/agent/command authoring, ADR updates) no longer pay the ~2,664-char cost.

Expected budget impact: always-loaded total drops to ~49,546 chars (94.4% utilization) on non-documentation sessions. On doc-authoring sessions (where one of the globs matches), the rule still loads and the utilization is equivalent to pre-change.

## Considered Options

### Option 1 — Keep `paths: "**/*.md"`

Status quo.
**Pros:** No change; no risk of misconfiguration.
**Cons:** The rule is effectively always-loaded, consuming ~2,664 chars on every session regardless of whether diagrams are being authored. Burns budget against the 15,000-token ceiling with no corresponding benefit for 90%+ of sessions.

### Option 2 — Narrow `paths:` to documentation-authoring surfaces (chosen)

The 8-glob list above.
**Pros:** Reclaims ~2,584 chars on non-documentation sessions. Rule still loads exactly when it drives decisions. Unblocks `dec-027` principles embedding. Pattern is consistent with how other `paths:`-scoped rules behave.
**Cons:** Skill-crafting sessions occasionally author Mermaid diagrams inside skill definitions; those sessions lose automatic rule-load. Mitigated by manually consulting `rules/writing/diagram-conventions.md` when authoring diagrams in skills. The frequency is low enough that the manual-consult cost is acceptable relative to the budget reclaimed.

### Option 3 — Delete the rule entirely

Remove the rule; fold diagram conventions into the `doc-management` or `skill-crafting` skills.
**Pros:** Frees the full ~2,664 chars; eliminates the rule-vs-skill ambiguity.
**Cons:** Conventions would no longer load automatically on documentation sessions. Requires pre-existing skill knowledge to consult. Higher implementation cost (folding content into an appropriate skill) for marginal extra headroom. Rejected.

## Consequences

**Positive:**

- Non-documentation sessions reclaim ~2,584 chars of always-loaded budget.
- `dec-027` principles embedding fits under the 52,500-char ceiling after this reclamation.
- The rule still drives decisions in every session that authors or reviews a diagram-bearing document.
- Pattern is re-applicable: future oversized always-loaded rules can be narrowed to their decision-driving surfaces.

**Negative:**

- Skill authoring occasionally involves flow diagrams (mermaid snippets inside `SKILL.md` files). Those sessions no longer auto-load the diagram conventions; the author must consult the rule manually (it remains in the filesystem and can be read on demand).
- The `paths:` globs encode a judgment about which surfaces authoring happens on; if a new documentation surface is added (e.g., `design-notes/`), the rule won't load there until the globs are updated.
- A future supersession widening scope would invalidate the `dec-027` budget assumption; a change to this ADR must be weighed against the principles block's headroom.

**Operational:**

- Edit to `rules/writing/diagram-conventions.md` frontmatter only; body unchanged.
- Verification: open a code-editing session (no `.md` files touched) and confirm the rule does not appear in the always-loaded set; open a documentation session (edit any of the globbed surfaces) and confirm it does.
- The `skills/rule-crafting` skill's Token Budget section already recommends `paths:` scoping for content not needed on every session; this ADR is a direct application of that recommendation.
