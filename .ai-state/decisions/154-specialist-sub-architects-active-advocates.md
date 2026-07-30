---
id: dec-154
title: Specialist sub-architects are active quality advocates with standing — the orchestrator-mediated challenge loop
status: accepted
category: architectural
date: 2026-05-12
summary: A specialist sub-architect (interface-designer; candidate — context-engineer) is a quality advocate with standing, not a passive forward-only shadow. When an architectural decision constrains a materially-better design in the specialist's domain, the specialist MUST register the objection in a dedicated Architecture Challenges section of its output; the orchestrator routes a substantive challenge back to the systems-architect, who is obligated to re-evaluate and accept or reject with a reason; unresolved disagreement escalates to the user with both positions stated.
tags: [architecture, agent, pipeline, protocol, behavioral-contract, systems-architect, interface-designer, quality-advocacy, orchestrator]
made_by: agent
agent_type: systems-architect
branch: worktree-interface-design
pipeline_tier: full
re_affirmed_by:
  - dec-draft-94ea6d25
affected_files:
  - agents/interface-designer.md
  - agents/systems-architect.md
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/coordination-details.md
---

## Context

The `interface-designer` agent (see `dec-149`) is structurally a clone of `context-engineer`: a shadow advisor that runs concurrently with the researcher and systems-architect and flows information **forward only** — it never messages a concurrent agent, and that one-way constraint deliberately prevents thrash. `dec-151` draws the *default partition* of decision authority between the two: the systems-architect decides *that* an interface surface exists and its *role*; the interface-designer decides *what it looks like*.

A static partition alone is not enough. The interface-designer's whole reason to exist is design quality under taste — and design quality is sometimes **constrained by an architectural decision** that was made without weighing the interface consequence: the architect picks REST when a streaming/GraphQL surface would serve the consumer far better; the architect specs a multi-page flow when the interaction genuinely wants one canvas; the architect's service boundary forces an N+1-prone API shape. A purely forward-only shadow would *notice* the better design and **stay silent** — because the mechanism gives it no way to push back. That silence is the failure: a known-better design that nobody surfaces is exactly the quality loss the specialist was added to prevent.

The mechanism question is the hard part: concurrent agents cannot message each other, and re-introducing free back-and-forth would resurrect the thrash the forward-only model was designed to kill. The answer must be **orchestrator-mediated** — the same shape the pipeline already uses for the verifier's FAIL findings looping back to the implementer.

## Decision

A specialist sub-architect — initially the `interface-designer`; **`context-engineer` is named as a candidate** for the same standing (it is strictly forward-only today; whether it should gain this standing is a deliberate follow-up question, *not* re-litigated or implemented here) — is an **active quality advocate with standing**, layered on top of the default partition in `dec-151`:

1. **Default partition (unchanged).** The systems-architect owns *that* an interface surface exists and its *role* (subsystem ownership, data-flow fit, deployment-topology implications). The interface-designer owns *what it looks like* (resource/endpoint/tool model, error contract, pagination strategy, UI framework, component patterns, design tokens, interaction model, help-text structure, exit codes). Tiebreaker: changes-data-flow-or-topology → architect; changes-only-what-the-consumer-sees → designer.

2. **Standing to challenge — not optional.** When an architectural decision *constrains* a materially-better interface design, the interface-designer **must** register the objection. This is **not** optional politeness — for this agent, silence in the face of a known-better design is a **behavioral-contract violation** (the "Register Objection" behavior, with teeth). The challenge is written into a dedicated **`## Architecture Challenges`** section of `INTERFACE_DESIGN.md`, with sub-structure: *contested architectural decision* / *proposed alternative* / *quality rationale* / *blast-radius assessment* (what changes if the alternative is adopted — modules, topology, scope) / *recommendation* (adopt / adopt-with-modification / escalate).

3. **Architect's obligation to re-evaluate — not optional.** A substantive interface-designer challenge obligates the systems-architect to re-evaluate: engage with the proposed alternative and its quality rationale, then **accept or reject with a reason**. The architect may not wave it off. (A non-substantive challenge — one that contests a decision squarely inside the designer's own partition, or one with no quality rationale or blast-radius assessment — the orchestrator may decline to route; the designer should not have written it as a challenge.)

4. **Orchestrator-mediated loop — not agent-to-agent.** Concurrent agents cannot message each other, and the shadow model is forward-only by design. So the loop-back is **orchestrator-mediated**: the **main agent** reads the `## Architecture Challenges` section of `INTERFACE_DESIGN.md` and, for a substantive challenge, routes it back to the `systems-architect` for re-evaluation **before the implementation plan is finalized** — exactly the way the verifier's FAIL findings loop back to the implementer. The re-evaluated architect output (an updated `SYSTEMS_PLAN.md` decision, or a reasoned rejection) becomes the input the implementation-planner sequences.

5. **Escalation path.** If the architect and the designer cannot converge after the re-evaluation round, the orchestrator **escalates to the user** with both positions stated (the contested decision, the architect's reasoning, the designer's alternative + quality rationale + blast-radius). The user decides. The loop is bounded: one orchestrator-mediated re-evaluation round, then either convergence or user escalation — never an open ping-pong.

This is encoded in two places: a tight addition to `dec-151` ("the default partition") that references this ADR, and this ADR itself (the standing + the obligation + the orchestrator-mediated loop + the escalation). The always-loaded `swe-agent-coordination-protocol.md` rule carries only the trigger and a one-line pointer; the loop's procedure lives in `skills/software-planning/references/coordination-details.md` (not always-loaded) — mirroring how `context-engineer` shadowing's deep-dive is handled today.

## Considered Options

### Option 1 — Keep the strict forward-only shadow model; the designer flags better designs only in its own output, no loop-back

Rejected — a flagged-but-never-routed challenge has no path to actually change the architecture; the architect, if no longer running, never sees it; the planner sequences against a design the specialist knows is worse. The standing is hollow without the loop.

### Option 2 — Allow direct interface-designer ↔ systems-architect back-and-forth (relax the concurrency / forward-only constraint)

Rejected — re-introduces the thrash the forward-only model was built to prevent (two agents revising each other's documents mid-flight, unbounded), and agents structurally cannot message each other while concurrent anyway. The orchestrator-mediated, bounded loop gets the benefit (the challenge actually reaches the architect) without the cost (no open ping-pong, the orchestrator gates it, one round then escalate).

### Option 3 (chosen) — Active quality advocate with standing, orchestrator-mediated bounded loop, user escalation on non-convergence

Layered on the default partition. The designer *must* register the objection (contract behavior with teeth); the architect *must* re-evaluate (engage, accept/reject with reason); the orchestrator routes the challenge back before the plan is finalized (the verifier-FAIL-loops-to-implementer shape); non-convergence escalates to the user. Bounded — one round, then converge or escalate.

- **Pro**: design quality has a real path to override a suboptimal architectural constraint; the architect's load is *reduced* (it doesn't have to be an interface expert — it gets an expert challenge it must engage); the loop reuses an existing, understood pattern (verifier→implementer); bounded and orchestrator-gated, so no thrash.
- **Con**: one more orchestrator-mediated round in the pipeline when a challenge fires (latency — accepted; substantive interface-vs-architecture conflicts are rare and high-leverage); the "substantive vs non-substantive challenge" line needs the orchestrator's judgment (mitigated by the explicit `## Architecture Challenges` sub-structure — a challenge missing a quality rationale or blast-radius is by definition non-substantive).

## Consequences

**Positive:**
- The interface-designer's standing is real: a known-better design reaches the architect and, if unresolved, the user — not just a buried note.
- "Register Objection" gets teeth for this agent: silence in the face of a known-better design is a contract violation, not a discretionary call.
- The architect is obligated to engage (accept/reject with a reason) — no silent dismissal; the audit trail is in `SYSTEMS_PLAN.md` and `INTERFACE_DESIGN.md`.
- The loop reuses the verifier→implementer orchestrator-mediated shape — no new coordination primitive; the always-loaded cost is one trigger line + a pointer.
- Bounded: one re-evaluation round, then converge or escalate to the user — no open ping-pong, no thrash.
- The default partition (`dec-151`) is preserved intact — this is a layer on top, not a rewrite of the boundary.

**Negative / accepted:**
- One more orchestrator-mediated round when a challenge fires — accepted; rare and high-leverage.
- The orchestrator must judge "substantive vs non-substantive" — mitigated by the explicit `## Architecture Challenges` sub-structure (no quality rationale / no blast-radius → non-substantive → don't route).
- If the architect is no longer running when the challenge surfaces, the orchestrator re-spawns the systems-architect for the re-evaluation round (a small extra spawn — accepted; it's the same pattern as re-spawning the implementer for a verifier FAIL).

**Open / candidate (not implemented here):**
- Whether `context-engineer` should gain the same standing (it is strictly forward-only today). Named as a candidate; a deliberate follow-up question. Do **not** redesign `context-engineer` on the strength of this ADR — it is recorded as a candidate, nothing more.

## Prior Decision

This ADR **layers on** `dec-151` (the `interface-designer` ↔ `systems-architect` boundary) — that ADR's default partition is unchanged and is the substrate this protocol sits on; `dec-151` gets a tight addition naming its partition "the default partition" and pointing here for the active dynamic. It pairs with `dec-149` (the agent shape — the agent this standing applies to) and is consistent with the behavioral-contract rule (`rules/swe/agent-behavioral-contract.md` — "Register Objection: state the conflict with a reason before complying or declining. Silent agreement is a contract violation"): this ADR makes that behavior non-discretionary for the interface-designer and gives it a concrete channel (`## Architecture Challenges`) and a concrete routing protocol (orchestrator-mediated, bounded, user-escalation-on-non-convergence). No frontmatter changes to the behavioral-contract rule. Recorded in `LEARNINGS.md ### Decisions Made` by the implementation-planner.
