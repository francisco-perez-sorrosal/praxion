---
id: dec-262
title: Tier is not execution mode — pipeline_tier semantics + orchestrator as Direct/Lightweight ADR author
status: accepted
category: behavioral
date: 2026-07-01
summary: Resolve the dec-133-class conflation by documenting that pipeline_tier is the 5-tier calibration value (process weight), not an execution-mode label; name the orchestrator as a sanctioned Direct/Lightweight ADR author; demote the NNN-at-create path to manual-user-only.
tags: [adr-conventions, calibration, tier, execution-mode, taxonomy, orchestrator, direct-tier, data-hygiene]
made_by: agent
agent_type: systems-architect
branch: worktree-direct-capture-contract
pipeline_tier: standard
affected_files:
  - rules/swe/adr-conventions.md
  - skills/spec-driven-development/references/calibration-procedure.md
  - .ai-state/decisions/133-drop-dev-prereleases.md
affected_reqs: [REQ-04, REQ-07]
re_affirms: dec-114
---

## Context

`dec-133` (drop PEP 440 dev pre-releases) carries `pipeline_tier: direct` in its frontmatter, while the calibration-log row for the identical task (`drop-pep440-dev-prereleases`, 2026-05-08) records `Recommended Tier: Standard, Actual Tier: Standard`. It is the one task in the whole corpus with both records, and they disagree. The calibration row's `Source` cell reads "direct-execution by main agent" — i.e. *no agent fan-out*, an execution-mode statement — which was conflated with the 5-tier `pipeline_tier` value. Five sibling ADRs also carry `pipeline_tier: direct` (`dec-092`, `dec-114`, `dec-165`, `dec-188`, `dec-203`).

Separately, the `Who Writes ADRs` table in `adr-conventions.md` draws its authorship dichotomy as user vs. pipeline-agent and never names the case that actually occurs at Direct/Lightweight tier: the interactive session (the orchestrator/main agent) writing an ADR on the user's behalf with no pipeline agent spawned. The frontmatter `agent_type` enumerates only pipeline agents, and the NNN-at-create path is described inconsistently ("legacy", "acceptable", "preferred elsewhere") across three co-located passages.

## Decision

Document the taxonomy distinction once, at the schema home, and close the authorship gap:

1. **`pipeline_tier` is the 5-tier calibration value** — the process weight actually used (`direct` / `lightweight` / `standard` / `full` / `spike`) — **not an execution-mode label**. "Direct execution" (no agent fan-out) is an orthogonal *execution-mode* axis; it belongs in the calibration-log `Source` cell or prose, never in `pipeline_tier`. Add this one-liner next to the `pipeline_tier` frontmatter row in `adr-conventions.md`, with a light echo at the calibration-procedure `Source`-field definition (where the conflation physically happened).
2. **Name the orchestrator as a Direct/Lightweight ADR author** — add a `Who Writes ADRs` row: orchestrator (Direct/Lightweight, no pipeline), `made_by: agent`, `agent_type: orchestrator`, `drafts/` fragment path preferred. `dec-114` is the existing precedent (`made_by: agent`, orchestrator). The post-commit finalize chain already promotes drafts landing on main — no new machinery.
3. **Demote the NNN-at-create path to manual-user-only** — the `drafts/` fragment scheme is preferred even at Direct tier (it avoids `<NNN>` collisions); the legacy NNN-at-create path survives only for a human authoring an ADR by hand outside any session.
4. **Data correction:** `dec-133` frontmatter `direct → standard` (matching its calibration row and 9-change scope); audit the five sibling `pipeline_tier: direct` ADRs against criterion (1) — flip only genuine conflations (a single-file / single-decision ADR is legitimately `direct`); backfill the two absent Standard calibration rows post-hoc-flagged.

## Considered Options

### Option A — Fold the taxonomy note into the main capture-contract ADR (rejected)
- **Pros:** one fewer fragment.
- **Cons:** the taxonomy fix changes for a different reason than the capture loop (a schema-field semantics clarification vs a leak-closing feedback loop) and serves a different future reader (someone auditing tier fields vs someone touching the nudge). Bundling them couples two independent concerns.

### Option B — Separate ADR for the taxonomy + orchestrator-authorship cluster (chosen)
- **Pros:** cohesive — all three edits are `adr-conventions.md` governance about ADR authorship and tier-field semantics at no-pipeline tiers; independently reusable; a clean home for D6.
- **Cons:** one extra small fragment.

### Option C — Introduce a new `execution_mode` frontmatter field
- **Pros:** makes the orthogonal axis first-class and machine-queryable.
- **Cons:** a new schema field for a low-value distinction; the axis is adequately captured in the calibration-log `Source` prose; violates Simplicity First (a field that would be populated rarely and read by nobody).

## Consequences

**Positive:**
- The dec-133-class conflation cannot recur — the schema home states the distinction explicitly.
- The orchestrator-authored Direct/Lightweight ADR case is named, resolving the `made_by`/`agent_type` gap (Finding 4.1) and the "preferred vs acceptable" ambiguity (Finding 4.2).
- The two systems of record (ADR frontmatter, calibration log) are reconciled for the one dual-record case and guarded against the next.

**Negative / accepted:**
- The sibling-ADR audit is judgment-dependent per ADR (the criterion is stated; most user-authored single-decision ADRs stay `direct`); over-correction risk is mitigated by flipping only ADRs with a contradicting calibration row.
- Adds a `Who Writes ADRs` row and a frontmatter note — a small always-loaded increase in `adr-conventions.md`, offset within the task's net-neutral token budget by the D8 consolidation.

## Prior Decision

Re-affirms `dec-114` (the tech-debt-ledger split ADR, itself `made_by: agent` / orchestrator at `pipeline_tier: direct`) as the precedent that the orchestrator is a legitimate ADR author outside a pipeline. `dec-114` is one of the five sibling ADRs audited under decision (4); its `pipeline_tier` is confirmed — the ledger-split was genuinely a single focused decision — so it stands as authored, and it anchors the new `Who Writes ADRs` orchestrator row rather than being corrected by it.
