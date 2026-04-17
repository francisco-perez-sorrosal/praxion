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
| `<instance-k>` | Multi-instance fan-out (1-indexed) | `2` |
| `<instance-total>` | Multi-instance fan-out total count | `3` |
| `<variant-label>` | Speculative-execution variant name | `sync-architecture` |
| `<alternative>` | Speculative-execution topic | `data-flow architecture` |

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

## Full-Tier Multi-Instance Fan-Out

Use when one agent role decomposes into N independent instances over disjoint file sets (e.g., three implementer instances for three independent modules in the same step group). All instances run concurrently in a single turn; coordinator merges fragment files after completion.

```markdown
You are the <agent-role> for the `<task-slug>` pipeline (tier: Full).

Task slug: <task-slug>
Instance: <instance-k> of <instance-total>
Step: <step-n>
Files (disjoint from other instances): <files>
Peers: instances <other-k> of <instance-total> operating on different file sets
Input: .ai-work/<task-slug>/WIP.md (your step only)
Deliverable: <deliverable> + .ai-work/<task-slug>/WIP_<agent-role>_<instance-k>.md fragment

<!-- Paste the per-agent checklist from rules/swe/swe-agent-coordination-protocol.md#delegation-checklists -->

Do NOT edit files outside your declared Files set; report [CONFLICT] if you must. Coordinator merges all <instance-total> fragment files into the canonical WIP.md after every instance completes.
```

Key distinction from the implementer ∥ test-engineer scaffold: there the parallel agents have **different roles** on the same step; here N instances of the **same role** operate on disjoint file sets within one step.

## Full-Tier Speculative Execution

Use when two or more instances of the same role explore **alternative approaches** in parallel and the coordinator synthesizes or selects from the outcomes. Reserved for decision points where the comparison itself is load-bearing — not routine work.

```markdown
You are the <agent-role> for the `<task-slug>` pipeline exploring alternative <alternative>.

Task slug: <task-slug>
Variant: <variant-label>
Peer variants: <other-variant-labels>
Deliverable: .ai-work/<task-slug>/<deliverable>__<variant-label>.md

<!-- Paste the per-agent checklist from rules/swe/swe-agent-coordination-protocol.md#delegation-checklists -->

Report: trade-offs in your approach, strong/weak points, explicit selection criteria you'd propose. Do NOT declare a winner — the coordinator compares variants and decides. Do NOT read peers' variant files; independent reasoning is the point of speculative execution.
```

Coordinator responsibility: after all variants complete, compare the per-variant deliverables and either select one (recording the rationale in an ADR) or synthesize a third approach that absorbs the best of each. Speculative execution is expensive (N × tokens) — justify with a note in the pipeline's SYSTEMS_PLAN.md.

## DRY Boundary

This reference defines **prompt structure only**. Every `<!-- Paste ... -->` marker points the main agent at the rule's Delegation Checklists as the single source of truth for per-agent deliverables. Copying the checklists here would duplicate them across two files — the rule is authoritative. Add new placeholders here only when a new delegation pattern emerges; add new deliverables to the rule, not here.
