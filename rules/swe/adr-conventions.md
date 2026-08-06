---
core: true
load: always_on
install: symlink
---

## ADR Conventions

Architecture Decision Records live in `.ai-state/decisions/` as Markdown files with YAML frontmatter. They persist beyond `.ai-work/` cleanup and are committed to git.

### File Format

Pipeline-authored ADRs follow the **fragment-name-at-create, finalize-at-merge** path: the ADR lands as a fragment under `.ai-state/decisions/drafts/` with a collision-safe filename and a provisional `dec-draft-<hash>` id, then is promoted to a stable `<NNN>-<slug>.md` record at merge-to-main. The legacy NNN-at-create path survives only for manual, no-session ADRs (see [Finalized ADRs (post-merge)](#finalized-adrs-post-merge)).

#### Fragment Filename Schema

Pipeline-authored ADRs (systems-architect, implementation-planner, or any agent writing inside a Standard/Full-tier pipeline) land at:

```
.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md
```

**Frontmatter at creation**: `id: dec-draft-<8-char-hash>`, `status: proposed`. All other fields (see the [Frontmatter](#frontmatter) table) are populated as usual.

**Cross-reference convention within drafts**: draft-to-draft `supersedes`, `superseded_by`, `re_affirms`, and `re_affirmed_by` values use `dec-draft-<hash>` — never a speculative `dec-NNN`. The [Finalize Protocol](#finalize-protocol) rewrites these to `dec-NNN` atomically at merge-to-main.

For the identity-derivation pseudocode (`timestamp` / `user_slug` / `branch_slug` / `slug` / hash), the `sanitize` helper rules, the PII note, and the collision-avoidance fallback, see [`adr-authoring-protocols.md § Identity Derivation and Filename Construction`](../../skills/software-planning/references/adr-authoring-protocols.md#identity-derivation-and-filename-construction).

#### Finalized ADRs (post-merge)

After finalize runs at merge-to-main (see [Finalize Protocol](#finalize-protocol)), the ADR lives at:

```
.ai-state/decisions/<NNN>-<slug>.md
```

**Naming**: `<NNN>-<slug>.md` — zero-padded 3-digit sequence number, kebab-case slug. The `<NNN>` is assigned by the finalize script at merge-to-main, not at creation; pipeline-authored ADRs never pick their own `<NNN>`.

**Manual, no-session ADRs** (hand-authored with no session or agent involved) MAY be created directly at `.ai-state/decisions/<NNN>-<slug>.md`, the next `<NNN>` assigned by scanning existing filenames (ignoring `drafts/`) — deprecated for all agent- and pipeline-authored ADRs, orchestrator-authored ones included.

#### Frontmatter

The frontmatter schema is shared between draft and finalized ADRs. Only the `id` value format differs between the two stages (`dec-draft-<8-char-hash>` during draft; `dec-NNN` after finalize). Cross-reference fields (`supersedes`, `superseded_by`, `re_affirms`, `re_affirmed_by`) likewise carry `dec-draft-<hash>` values during the draft stage and `dec-NNN` values after finalize.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | `dec-draft-<8-char-hash>` in drafts; `dec-NNN` after finalize |
| `title` | string | Yes | Short decision title |
| `status` | string | Yes | `proposed` / `accepted` / `superseded` / `rejected` / `re-affirmation` / `retired` |
| `category` | string | Yes | `architectural` / `behavioral` / `implementation` / `configuration` |
| `date` | string | Yes | ISO 8601 date (`YYYY-MM-DD`) |
| `summary` | string | Yes | One-line description for index and scanning |
| `tags` | list | Yes | Lowercase topic tags for filtering |
| `made_by` | string | Yes | `agent` / `user` |
| `agent_type` | string | When agent | Which agent (e.g., `systems-architect`, `orchestrator`) |
| `branch` | string | Recommended on drafts | Sanitized authoring branch (`[a-z0-9-]+`). Lets `finalize_adrs.py` disambiguate hyphenated branches from slugs without sibling-prefix discovery — eliminates the single-fragment parsing ambiguity (td-017). Optional for backward compat; pre-existing fragments without it still parse via filename heuristics |
| `pipeline_tier` | string | No | `direct` / `lightweight` / `standard` / `full` / `spike` — the 5-tier calibration value (process weight actually used), never an execution-mode label ("no agent fan-out" notes belong in the calibration-log `Source` prose) |
| `affected_files` | list | No | Paths impacted by the decision |
| `affected_reqs` | list | No | REQ IDs linked to the decision |
| `supersedes` | string \| list | No | id(s) of the prior decision(s) this one replaces. A **list** when one decision replaces several — same reason `retired_by` is a list: a scalar silently under-records the rest |
| `superseded_by` | string | No | id of replacing decision |
| `re_affirms` | string | No | id of prior decision this ADR re-affirms without superseding |
| `re_affirmed_by` | list | No | ids of later ADRs that re-affirmed this decision |
| `retired_by` | list | When `retired` | ids of the decisions whose action removed this one's subject. A **list**, because one removal commonly strands several decisions and `superseded_by` (a string) cannot express that |
| `dissent:` | string | No | Machine-queryable companion to the `## Disconfirmation` body block; one-line strongest objection to the chosen option. Required when `category: architectural`. |

#### What makes a decision `architectural`

A decision is `architectural` **iff it changes what exists or what connects**:

- **internal** — it adds, removes, merges, or splits a component in any artifact family (skill, agent, rule, command, hook, script, MCP server, package, service); moves a responsibility from one component to another; or introduces or removes a boundary or abstraction between them.
- **published** — it changes a canonical block, a shipped template, or an onboard-contract phase.

If the component inventory and its boundaries are unchanged once the decision lands, it is **not** architectural — *however consequential the trade-off*.

**Falsifier — name the component added, removed, or whose responsibility moved.** If no such name exists, the category is wrong: process, policy, deliberation method, and features inside one component are `behavioral`, `implementation`, or `configuration`.

Source of truth for this test; other sites point here rather than restate it. Worked examples, evidence, and the measurement that calibrates it: [`adr-authoring-protocols.md` § The `architectural` Test](../../skills/software-planning/references/adr-authoring-protocols.md#the-architectural-test).

**Body sections** (after frontmatter):

1. **Context** -- what prompted the decision (problem, constraint, opportunity)
2. **Decision** -- what was decided (clear, direct statement)
3. **Considered Options** -- alternatives with pros/cons (subsections per option)
4. **Consequences** -- positive and negative outcomes
5. **Disconfirmation** -- **always-on for `category: architectural`**; three sub-items: (a) **Falsifier** — what evidence would make this decision wrong; (b) **Steelmanned runner-up** — the strongest case for the next-best option; (c) **Reversal trigger** — the future signal that should prompt revisiting. See `adr-authoring-protocols.md` for the creation-protocol step.
6. **Prior Decision** -- only when superseding; summarizes what changed and why

### Supersession Protocol

When a new ADR supersedes an existing one: set `supersedes`/`superseded_by` cross-references, flip the old ADR to `status: superseded`, and add a `## Prior Decision` section to the new ADR. `DECISIONS_INDEX.md` regenerates at finalize — never invoke the index script manually. Full step sequence: [`adr-authoring-protocols.md` § Supersession Protocol](../../skills/software-planning/references/adr-authoring-protocols.md#supersession-protocol).

### Re-affirmation Protocol

When a new ADR re-affirms an existing one *without* superseding it (a re-opening was considered and rejected for lack of new evidence): set `status: re-affirmation` + `re_affirms`, append `<new-id>` to the old ADR's `re_affirmed_by` (the old ADR stays `accepted`, no `superseded_by`), and add a `## Prior Decision` section naming the evidence a future supersession would require. Use only when a prior decision is challenged, re-examined, and found still correct — not routine acknowledgment. Full step sequence: [`adr-authoring-protocols.md` § Re-affirmation Protocol](../../skills/software-planning/references/adr-authoring-protocols.md#re-affirmation-protocol).

### Retirement Protocol

When a later decision's action **removed this decision's subject** rather than answering its question differently: set `status: retired` + `retired_by: [<ids>]`, and add a `## Prior Decision` section naming what was removed and by which decision. The removing decisions are **not** modified — they made no claim about this one. Retired records are preserved, never deleted, and **re-open** (back to `accepted`, `retired_by` cleared) if the subject returns. Use only when the question itself is gone; a decision answered differently is a supersession. Full step sequence and the supersession-vs-retirement test: [`adr-authoring-protocols.md` § Retirement Protocol](../../skills/software-planning/references/adr-authoring-protocols.md#retirement-protocol).

### Finalize Protocol

Finalize promotes drafts in `.ai-state/decisions/drafts/` to finalized `<NNN>-<slug>.md` records at merge-to-main. Invoked by the post-merge git hook and `/merge-worktree`; the protocol is **idempotent**, advisory-locked, and rewrites `dec-draft-<hash>` cross-references across a **bounded** walk scope (sibling ADR files; `.ai-state/DESIGN.md`, `.ai-state/TECH_DEBT_LEDGER.md`, `.ai-state/TECH_DEBT_RESOLVED.md`, `.ai-state/CONSULT_LEDGER.md`, and a project-root `ROADMAP.md`; every markdown file under `docs/`; in-flight `.ai-work/*/LEARNINGS.md` / `SYSTEMS_PLAN.md` / `IMPLEMENTATION_PLAN.md`; and `.ai-state/specs/SPEC_*` matching the current task slug — an explicit allowlist of named files and bounded subtrees, never an arbitrary repo sweep). The bounded scope is the contract — finalize never touches unrelated text. `DECISIONS_INDEX.md` regenerates last.

For the full step sequence (draft detection, NNN assignment, file rename + frontmatter `id:`/`status:` rewrites, the cross-reference-rewrite location table, concurrency safety, and exit codes), see [`adr-authoring-protocols.md § Finalize at Merge-to-Main`](../../skills/software-planning/references/adr-authoring-protocols.md#finalize-at-merge-to-main).

### Who Writes ADRs

| Agent | When | Scope | Destination |
|-------|------|-------|-------------|
| systems-architect | Phase 4 (trade-off analysis) | Decisions meeting the [`architectural` test](#what-makes-a-decision-architectural) — inventory, boundary, or published contract; lesser trade-offs are recorded at their true category | `.ai-state/decisions/drafts/` (fragment) |
| implementation-planner | Step decomposition | Decisions affecting step ordering, module structure, approach | `.ai-state/decisions/drafts/` (fragment) |
| interface-designer | Phase 4 (trade-off analysis) | Interface-layer decisions: UI framework / API paradigm / MCP tool decomposition / error format / pagination / component-pattern selection | `.ai-state/decisions/drafts/` (fragment) |
| orchestrator | Direct/Lightweight tier, no pipeline agent spawned | Any decision worth preserving during an interactive session | `.ai-state/decisions/drafts/` (fragment; preferred) |
| user | Manual (no session, no agent) | Any decision worth preserving | `.ai-state/decisions/drafts/` preferred; `<NNN>-<slug>.md` acceptable only for this manual path |

All ADR authors also record decisions in `LEARNINGS.md ### Decisions Made` using the structured format. While a pipeline is in flight, `LEARNINGS.md` carries `dec-draft-<hash>` references; finalize rewrites these to `dec-NNN` at merge-to-main.

### Agent Writing Protocol

The 7-step procedure agents follow when creating a fragment ADR (identity derivation, filename construction, fragment-id computation, frontmatter, cross-reference convention, LEARNINGS.md entry, no-manual-index-regen) lives in [`adr-authoring-protocols.md § ADR Creation Protocol`](../../skills/software-planning/references/adr-authoring-protocols.md#adr-creation-protocol-fragment-name-at-create) — the canonical procedural reference for ADR-creating agents (systems-architect, implementation-planner).

### Discovery Protocol

1. Read `.ai-state/decisions/DECISIONS_INDEX.md` for an overview of finalized ADRs
2. Grep for matching `category`, `tags`, or `affected_files` in the index table
3. For in-flight work, also scan `.ai-state/decisions/drafts/` — drafts are not indexed but are authoritative during the pipeline that authored them
4. Read full ADR files for matching decisions
5. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + `Glob .ai-state/decisions/drafts/*.md` + Grep frontmatter

### Linking to ADRs

Persistent files — `docs/`, `.ai-state/DESIGN.md`, READMEs — link the **finalized** record at `.ai-state/decisions/<NNN>-<slug>.md`, never a `drafts/<…>.md` fragment: a `drafts/` path stops resolving the moment the authoring pipeline merges. While a pipeline is in flight, cite an unfinalized ADR inline by its `dec-draft-<hash>` id (from the draft frontmatter), not by path — the id survives finalize as a rewritten `dec-NNN`; the path does not. (ADR-to-ADR cross-references use the frontmatter `id` form per the Supersession and Re-affirmation protocols above, not file-path links.)

### Consumption

| Consumer | Purpose |
|----------|---------|
| sentinel | DL01-DL05: validate ADR format, frontmatter, body, index consistency, frequency — for both draft and finalized ADRs |
| skill-genesis | Recurring decision patterns across features |
| verifier | Cross-reference `affected_reqs` against traceability matrix |
| systems-architect | Brownfield baseline for prior feature decisions |

### Relationship to LEARNINGS.md

- `LEARNINGS.md` is broader: gotchas, patterns, edge cases, tech debt, decisions
- ADR files are narrower: decisions only, persistent, human-browsable
- Decisions appear in both -- `LEARNINGS.md` is ephemeral; ADR files persist
- Draft-stage `dec-draft-<hash>` references in `LEARNINGS.md` are rewritten to `dec-NNN` at finalize alongside the ADR files themselves

### Migration — historical ADRs

Pre-existing finalized ADRs (those already at `.ai-state/decisions/<NNN>-<slug>.md` before the fragment scheme rolled out) remain **untouched**. Their filenames, `id: dec-NNN` frontmatter, and cross-references are preserved as-is. The fragment-name-at-create scheme applies only to newly authored ADRs from the rollout forward; no retroactive renumbering runs over historical records.
