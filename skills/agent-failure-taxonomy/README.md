# Agent Failure Taxonomy

A classification rubric for the runtime failure modes of agentic AI applications, seeded from the Microsoft AI Red Team taxonomy. Names a failure once observed and routes it to a mitigation owner.

## When to Use

- Classifying or diagnosing an **observed** agent failure ("the agent did something it shouldn't — what category is this?").
- Running a **design-time failure-mode review** of an agentic app's architecture (which modes apply, is each mitigated?).
- Recording a failure in a verification report, incident note, or ADR with a *named* mode rather than "weird behavior."

Not for: building the defenses (that is `agent-runtime-guardrails`), or Claude Code plugin-ecosystem security (that is `context-security-review`).

## Activation

Description-match on diagnosis/classification language — "classify an agent failure," "name what went wrong," "failure-mode review," "agent compromise / memory poisoning / excessive agency / tool abuse." Distinct from `agent-runtime-guardrails` (prevention) and `context-security-review` (plugin ecosystem).

## Skill Contents

- `SKILL.md` — the 14-mode rubric (mode · pillar · what it is · runtime signal · primary mitigation), the classification workflow, consumers, and boundaries.
- `references/mitigation-checklist.md` — expanded per-mode detail, the four-cluster design-time/build-time checklist, and a worked classification example.

## Related Skills

- `agent-runtime-guardrails` — prevention (builds the un-bypassable layer the rubric's mitigation column points to).
- `observability` — the OTel agent-span trajectory the rubric reads to spot a failure's shape.
- `agent-evals` — outcome gating (goal misalignment caught by an eval gate).
- `context-security-review` — the plugin-ecosystem security surface (distinct from the runtime-app surface here).
