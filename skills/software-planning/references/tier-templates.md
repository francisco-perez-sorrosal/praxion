# Tier-Prompt Scaffolds

Parametric scaffolds for the main agent to construct **delegation prompts** at Standard, Full, and Lightweight tiers. The scaffolds are a **shell**; per-agent deliverables live in the authoritative [Delegation Checklists](../../../rules/swe/swe-agent-coordination-protocol.md#delegation-checklists). The main agent substitutes placeholders and pastes the checklist payload — no content is duplicated here.

**Placeholder convention:** angle-bracket tokens (inherited from `[Phase: <Name>]` in [SKILL.md](../SKILL.md)). The main agent substitutes each token before sending the prompt; subagents never see angle-bracket forms.

## Placeholder Reference

| Placeholder | Substitution site | Example |
|---|---|---|
| `<task-slug>` | Every prompt (path scoping) | `auth-flow` |
| `<tier>` | Prompt preamble | `Standard`, `Full` |
| `<phase-name>` | Phase-delegated steps | `Refactoring` |
| `<step-n>` | implementer/test-engineer prompts | `3` |
| `<deliverable>` | `produce <deliverable>` clauses | `SYSTEMS_PLAN.md` |
| `<input-artifact>` | `read <input-artifact>` clauses | `RESEARCH_FINDINGS.md` |
| `<parallel-peer-agent>` | Full-tier parallel blocks | `test-engineer` |

## Standard-Tier Sequential Scaffold

Use when the pipeline flows one agent at a time (e.g., architect → planner).

```markdown
You are the <agent-role> for the `<task-slug>` pipeline (tier: <tier>).

Task slug: <task-slug>
Phase: <phase-name>
Input: .ai-work/<task-slug>/<input-artifact>
Deliverable: .ai-work/<task-slug>/<deliverable>

<!-- Paste the per-agent checklist from rules/swe/swe-agent-coordination-protocol.md#delegation-checklists -->

Report back: path of <deliverable>, acceptance-criteria pass/fail table, open questions.
```

Example (architect → planner): `<task-slug>` = `payment-api`, `<tier>` = `Standard`, `<input-artifact>` = `SYSTEMS_PLAN.md`, `<deliverable>` = `IMPLEMENTATION_PLAN.md`.

## Full-Tier Parallel Scaffold (implementer ∥ test-engineer)

Use when the planner assigns paired steps with disjoint file sets. Spawn both instances in the same turn; each receives the same slug but distinct step numbers and fragment files.

```markdown
You are the <agent-role> for the `<task-slug>` pipeline (tier: Full).

Task slug: <task-slug>
Step: <step-n>
Parallel peer: <parallel-peer-agent> (disjoint file set)
Input: .ai-work/<task-slug>/WIP.md (your step only)
Deliverable: <deliverable> + .ai-work/<task-slug>/WIP_<agent-role>.md fragment

<!-- Paste the per-agent checklist from rules/swe/swe-agent-coordination-protocol.md#delegation-checklists -->

Do NOT edit files outside your declared Files set; report [CONFLICT] if you must.
```

## Lightweight Snippet

Lightweight delegates at most one agent (researcher). No scratch file; acceptance criteria inline.

```markdown
You are the researcher for a Lightweight task.

Goal: <one-sentence question>
Scope: <files or APIs in bounds>
Done when: <inline acceptance criterion>

<!-- Paste the researcher checklist from rules/swe/swe-agent-coordination-protocol.md#delegation-checklists -->

Return findings in your response (no file); cite paths.
```

## DRY Boundary

This reference defines **prompt structure only**. Every `<!-- Paste ... -->` marker points the main agent at the rule's Delegation Checklists as the single source of truth for per-agent deliverables. Copying the checklists here would re-open dec-022 (re-affirmed by dec-049). Add new placeholders here only when a new delegation pattern emerges; add new deliverables to the rule, not here.
