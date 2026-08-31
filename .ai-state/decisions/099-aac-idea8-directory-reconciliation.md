---
id: dec-099
title: Idea 8 directory premise reconciled — `.c4` source lives at `<doc-dir>/diagrams/`, not `architecture/` at project root
status: re-affirmation
category: architectural
date: 2026-04-30
summary: 'Forward-binding constraint: when Idea 8 (onboarding-aware AaC tier) is later implemented, it scaffolds <doc-dir>/diagrams/ per dec-094, not a top-level architecture/ directory. v1 introduces no directory changes; this ADR records the constraint so future implementations cannot silently re-introduce the conflict.'
tags: [aac, onboarding, directory-structure, reconciliation, forward-binding, idea-8]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/seed-pipeline.md
  - scripts/onboard-project
re_affirms: dec-094
re_affirmed_by:
  - dec-113
---

## Context

The promethean's Idea 8 (onboarding-aware AaC tier) is **deferred to v1.2**. Its premise as written assumes a top-level `architecture/` directory at the project root scaffolded by `/onboard-project` Phase 8b. **However**, `dec-094` (commit-both diagram source DSL + rendered SVG) — already finalized — mandates `<doc-dir>/diagrams/<name>.c4` as the canonical DSL location. `rules/writing/diagram-conventions.md` re-states this. The two are incompatible: a future Idea 8 implementation that reads only the original IDEA_PROPOSAL.md would silently re-introduce a directory structure that contradicts established convention.

This v1 SYSTEMS_PLAN identifies the conflict during architect-stage trade-off analysis. Idea 8 is **not** in v1 scope, so the conflict cannot be resolved by code changes here. The right response is to record the reconciliation as an ADR — a forward-binding constraint that the future architect handling Idea 8 must read as part of their brownfield baseline.

## Decision

**`.c4` source files live at `<doc-dir>/diagrams/<name>.c4`** (per `dec-094`). Rendered `.d2` and `.svg` outputs commit alongside their source. **No separate `architecture/` directory is introduced at the project root.**

When Idea 8 ships (v1.2), `/onboard-project` Phase 8b and `/new-project` (greenfield) and `new_project.sh` (greenfield bootstrap) **scaffold `<doc-dir>/diagrams/`** (typically `docs/diagrams/`) — not `architecture/`. The Phase 8b prompt language must explicitly use the `<doc-dir>/diagrams/` path.

This ADR re-affirms `dec-094` rather than superseding any decision; it is a *meta-decision* — a decision about what a future decision (Idea 8 implementation) must respect.

**v1 actions:** none. No directory is created or modified. This ADR's only present-tense effect is to be **discoverable** by the future architect via the standard ADR discovery protocol (`DECISIONS_INDEX.md` scan for tags `idea-8`, `onboarding`, `directory-structure`).

## Considered Options

### Option 1 — Resolve in v1 by editing the IDEA_PROPOSAL or idea-ledger entry

**Pros:** Fixes the wording at source.

**Cons:** v1 is not the right place to edit Idea 8's idea-ledger entry — that is the future architect's brownfield input. Idea-ledger entries are not retroactively rewritten as understanding evolves; the trail of past thinking is itself evidence. Rejected.

### Option 2 — Don't record; rely on the future architect to read `dec-094` independently

**Pros:** No ADR overhead now.

**Cons:** Idea 8's IDEA_PROPOSAL premise is explicit ("scaffolds `architecture/` directory"). The future architect, reading the idea-ledger entry, sees `architecture/` as the named premise. Without this ADR cross-cutting their reading, they may default to the named premise and re-introduce the conflict. The whole point of ADRs is durable cross-cutting decisions; this is one. Rejected.

### Option 3 — Record as a forward-binding ADR (chosen)

**Pros:** Persistent, discoverable record. The future architect's `Phase 1 — Input Assessment` (in `agents/systems-architect.md`) instructs them to scan `DECISIONS_INDEX.md` for matching tags before designing. This ADR's tags (`onboarding`, `directory-structure`, `idea-8`) ensure they find it. Re-affirmation status signals "this isn't a new decision, it's a binding constraint inherited from `dec-094`".

**Cons:** ADR overhead for a decision with no v1 action. Mitigated because the discovery cost is low (single grep) and the alternative (silent re-introduction) is high-cost (rework + breaking dec-094).

### Option 4 — Add as a comment/note in `commands/onboard-project.md` directly

**Pros:** Co-located with the future implementation surface.

**Cons:** v1 does not edit `commands/onboard-project.md` (Idea 8 is deferred). Adding a forward-looking comment to a command file the user is not yet implementing is preemptive scope expansion. Rejected.

## Consequences

**Positive:**

- Future architect handling Idea 8 has a discoverable, machine-tagged constraint that prevents silent re-introduction of the `architecture/` directory.
- Re-affirmation chain (this ADR re_affirms `dec-094`) makes the lineage explicit.
- v1 takes no action — minimum scope.

**Negative:**

- ADR records a constraint, not a v1 action; readers may find it and wonder "what changed?" The body explains: nothing changed in v1; this is a forward-binding constraint.
- A future maintainer who supersedes `dec-094` with a different storage scheme must also reconcile this ADR's constraint with the new scheme.

**Operational:**

- The future architect (Idea 8 v1.2 pipeline) finds this ADR via the standard discovery protocol.
- The Idea 8 idea-ledger entry, when advanced from "Pending" to "In flight", should reference this ADR id (`dec-NNN` after finalize) in the entry's note field.
- No v1 file edits.

## Prior Decision

`dec-094` established the canonical `<doc-dir>/diagrams/<name>.c4` storage convention. This ADR re-affirms it specifically as a constraint on future onboarding work — the re-affirmation is intentional, the prior decision is not changed.
