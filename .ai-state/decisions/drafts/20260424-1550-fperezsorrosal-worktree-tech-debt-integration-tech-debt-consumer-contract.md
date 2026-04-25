---
id: dec-draft-b63e3623
title: Tech-debt ledger consumer contract — single-line input on five agents (permission, not obligation)
status: proposed
category: behavioral
date: 2026-04-24
summary: Five existing consumer agents (systems-architect, implementation-planner, implementer, test-engineer, doc-engineer) gain a single prose line directing them to read the tech-debt ledger, filter by their owner-role, address in-scope items, and update status. Promethean, roadmap-cartographer, /project-metrics, and /project-coverage are explicitly excluded. The contract is framed as permission, not obligation, per dec-069.
tags: [tech-debt, ledger, consumer, agent-pipeline, permission-not-obligation]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
re_affirms: dec-069
affected_files:
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/doc-engineer.md
---

## Context

The ledger ADR (dec-draft-e8df5e0b) defines the destination. The producer ADR (dec-draft-e9a055bb) defines who fills it. This ADR defines who **reads** it — and how.

The user resolved that the consumer mechanism is a **single input-contract line per consumer agent**, not main-agent injection or a wiring layer. Five consumers were chosen: `systems-architect`, `implementation-planner`, `implementer`, `test-engineer`, `doc-engineer`. Three potential consumers are explicitly excluded:

- **`promethean`** — `IDEA_LEDGER_*.md` is speculative ideation; debt is grounded reality. Conflating them dilutes both surfaces.
- **`roadmap-cartographer`** — `ROADMAP.md` is strategic narration over a project-derived lens set; mechanizing a ledger feed turns strategy into backlog grooming. The cartographer MAY narrate ledger contents when a human auditor chooses; **no input contract**.
- **`/project-metrics` and `/project-coverage`** — both are signal sources only. By symmetry: `/project-metrics` produces metric reports for sentinel to read; `/project-coverage` regenerates `coverage.xml` and renders a terminal summary. Neither writes to the ledger and neither has a consumer-contract obligation.

The risk is that adding the contract line creates an implicit **mandate**: a future agent (or a future revision of an existing agent) could over-interpret "read the ledger" as "always process every open item on every run." That would degrade the consumer's own phase-budget discipline and produce noise. Dec-069 ratified the inverse principle for the verifier and the test-coverage skill: **adding a skill or contract to an agent does not imply a hard trigger; the agent judges each run**. This ADR carries that framing forward to the ledger consumers.

## Decision

### The Single Line — substance identical, role variant

Each of the five consumer agents gets one new prose line at its appropriate hook point. The substance is:

> **Tech-debt ledger awareness (permission, not obligation; per dec-069).** Read `.ai-state/TECH_DEBT_LEDGER.md`. Filter entries by `owner-role = <your-role>` and `location` overlapping the scope you are currently working on. Address items where possible within the current task by updating `status` (to `resolved` with `resolved-by`, or `in-flight`); leave out-of-scope items at `status = open` — do not delete. Non-action is a valid outcome and never produces a FAIL on its own.

The `<your-role>` value is filled per agent:

| Agent | `owner-role` value | Hook point |
|-------|-------------------|------------|
| systems-architect | `systems-architect` | Phase 4 (trade-off analysis) |
| implementation-planner | `implementation-planner` | Step decomposition |
| implementer | `implementer` | Task intake (after loading WIP.md) |
| test-engineer | `test-engineer` | Test design |
| doc-engineer | `doc-engineer` | Doc impact analysis at pipeline checkpoints |

Minor copy-edits to fit each agent's prose style are acceptable as long as the four substantive verbs (read, filter, address, update) and the explicit non-action escape clause are preserved.

### Why "permission, not obligation"

Dec-069 ratified, for the test-coverage skill at the verifier, that "the verifier reads the guidance, judges the current run, and either invokes the skill or doesn't. Non-invocation is a valid outcome and never produces a FAIL on its own." That framing is the right shape for the ledger consumer contract too:

- A consumer who has no in-scope items legitimately takes no action.
- A consumer working on a tight scope cannot reasonably be expected to absorb every open ledger item.
- Hard-trigger framing creates a self-reinforcing avoidance pattern — agents over-conservatively avoid the ledger to avoid scope creep.

The "permission, not obligation" frame preserves agent autonomy while giving the agent a cheap, consistent way to act on debt when it intersects naturally with current work.

### Explicit Exclusions

- **`promethean`** — speculative ideation surface; mechanical debt feed dilutes the "flying high" purpose.
- **`roadmap-cartographer`** — strategic narration; mechanical feed turns strategy into backlog. May narrate ledger when a human auditor chooses; not via input contract.
- **`/project-metrics`** — signal source; sentinel reads its outputs. Not a writer, not a reader.
- **`/project-coverage`** — design-parallel to `/project-metrics`. Not a writer, not a reader.

These exclusions are documented here so future contributors do not "obviously" add the contract line to additional agents during pipeline expansion.

### Status-update obligation

The contract uses "address items where possible…by updating `status`" — the verb `update` is non-optional **when the agent acts on a row**. If a consumer addresses a ledger item, it MUST update `status` to `resolved` (with `resolved-by`) or `in-flight`. Action without status update is a contract violation. Non-action is fine; partial action without status update is not.

This obligation is the single most important behavioral commitment in the contract. Sentinel TD05 (defined in dec-draft-e9a055bb) audits status-update discipline by surfacing stale `in-flight` rows and `open` rows in resolved-feature areas. The audit is the enforcement loop.

## Considered Options

### Option 1: Single-line contract on five agents, "permission, not obligation" framing (chosen)

Five consumer agents, one line each, dec-069 framing.

**Pros.** Smallest possible scope. Reuses an existing successful framing pattern. Consumer set matches the work domains best positioned to act on debt.

**Cons.** Five prompt surfaces to keep in sync (mitigated by identical substance). Five hook points to choose well.

### Option 2: Main-agent injection (rejected — user-resolved)

Main agent reads ledger and injects relevant rows into subagent prompts.

**Pros.** Subagents stay simpler.

**Cons.** Main agent gains a wiring responsibility. Cross-cutting concern handled in the wrong place. User explicitly rejected this.

### Option 3: Hard-trigger contract (rejected)

Each consumer must process every owner-role-matched open item.

**Pros.** Predictable behavior.

**Cons.** Defeats agent autonomy; creates a noise-producing loop on every pipeline. Inconsistent with dec-069's ratified philosophy.

### Option 4: Promethean/roadmap-cartographer also consume (rejected — user-resolved)

Add the contract line to all consumers including ideation and roadmap surfaces.

**Pros.** "Universal" consumption.

**Cons.** Conflates surfaces; user explicitly rejected this. Each surface has its own definition of "an item" that does not match ledger semantics.

## Consequences

**Positive:**
- Debt is routed to agents that can act on it, at the moments they are best positioned to act. The systems-architect sees structural debt during trade-off analysis; the implementer sees per-file debt during task intake; the test-engineer sees coverage-gap debt during test design.
- The "permission, not obligation" frame keeps the contract cheap. A consumer with no in-scope items spends ~5 tokens reading the ledger header and moves on.
- The status-update obligation gives the ledger a true consumer-side feedback loop. Resolution is observable.
- Excluding promethean, cartographer, `/project-metrics`, `/project-coverage` keeps each surface focused on its actual purpose.

**Negative:**
- Status-update discipline is the load-bearing behavioral commitment. If consumers act-without-updating habitually, the ledger degrades to append-only noise. Mitigation: sentinel TD05 surfaces this trend; the contract line itself names the obligation.
- Five prompt surfaces is more text to maintain than a centralized injection point. Acceptable cost for the autonomy gain.
- Hook-point selection is sensitive: too early in an agent's flow and the consumer reads before knowing scope; too late and resolution work happens after most decisions. The hook points named above are chosen to balance these (after the agent has scope clarity but before final output).

## Prior Decision Referenced (re-affirmation)

This ADR **re-affirms dec-069** in a different context. Dec-069 ratified "permission, not obligation" for skill-list inclusion at the verifier. This ADR carries the same framing forward for input-contract inclusion at five consumer agents. The principle is identical; the surface is different. We are not superseding dec-069 — we are extending the principle's reach by re-affirming it in a new location.

`re_affirms: dec-069` is set in this ADR's frontmatter; finalize will append this ADR's id to dec-069's `re_affirmed_by` list.

## Prior Decisions Referenced

- **dec-draft-e8df5e0b** (Tech-debt ledger as living artifact) — defines the ledger this ADR's consumers read.
- **dec-draft-e9a055bb** (Tech-debt producers — verifier + sentinel) — defines the producers; sentinel TD05 in that ADR is the enforcement loop for this ADR's status-update obligation.
- **dec-069** (Verifier loads test-coverage skill at its own discretion) — re-affirmed by this ADR. Establishes the "permission, not obligation" framing that this consumer contract carries forward.
- **dec-013** (Layered duplication prevention; no new agent) — sets the precedent for solving cross-cutting concerns by extending existing agents. This ADR adds one prose line to each of five existing agents — no new agent.
