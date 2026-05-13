## ADR Conventions

Architecture Decision Records live in `.ai-state/decisions/` as Markdown files with YAML frontmatter. They persist beyond `.ai-work/` cleanup and are committed to git.

### File Format

ADRs authored during a pipeline follow the **fragment-name-at-create, finalize-at-merge** path: the ADR lands as a fragment file under `.ai-state/decisions/drafts/` with a collision-safe filename and a provisional `dec-draft-<hash>` id, and is promoted to a stable `<NNN>-<slug>.md` finalized record at merge-to-main. The legacy NNN-at-create path is retained only for direct-tier user-authored ADRs that bypass a pipeline (see [Finalized ADRs (post-merge)](#finalized-adrs-post-merge) below).

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

**Direct-tier user-authored ADRs** (no pipeline, no agent involvement) MAY still be created directly at `.ai-state/decisions/<NNN>-<slug>.md` with the next sequential `<NNN>` assigned by scanning existing filenames (ignoring `drafts/`). This legacy path exists for simplicity when a human writes a one-off decision outside a pipeline; it is deprecated for all agent-authored and pipeline-authored ADRs.

#### Frontmatter

The frontmatter schema is shared between draft and finalized ADRs. Only the `id` value format differs between the two stages (`dec-draft-<8-char-hash>` during draft; `dec-NNN` after finalize). Cross-reference fields (`supersedes`, `superseded_by`, `re_affirms`, `re_affirmed_by`) likewise carry `dec-draft-<hash>` values during the draft stage and `dec-NNN` values after finalize.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | `dec-draft-<8-char-hash>` in drafts; `dec-NNN` after finalize |
| `title` | string | Yes | Short decision title |
| `status` | string | Yes | `proposed` / `accepted` / `superseded` / `rejected` / `re-affirmation` |
| `category` | string | Yes | `architectural` / `behavioral` / `implementation` / `configuration` |
| `date` | string | Yes | ISO 8601 date (`YYYY-MM-DD`) |
| `summary` | string | Yes | One-line description for index and scanning |
| `tags` | list | Yes | Lowercase topic tags for filtering |
| `made_by` | string | Yes | `agent` / `user` |
| `agent_type` | string | When agent | Which agent (e.g., `systems-architect`) |
| `branch` | string | Recommended on drafts | Sanitized authoring branch (`[a-z0-9-]+`). Lets `finalize_adrs.py` disambiguate hyphenated branches from slugs without sibling-prefix discovery — eliminates the single-fragment parsing ambiguity (td-017). Optional for backward compat; pre-existing fragments without it still parse via filename heuristics |
| `pipeline_tier` | string | No | `direct` / `lightweight` / `standard` / `full` / `spike` |
| `affected_files` | list | No | Paths impacted by the decision |
| `affected_reqs` | list | No | REQ IDs linked to the decision |
| `supersedes` | string | No | id of prior decision (`dec-draft-<hash>` in drafts; `dec-NNN` after finalize) |
| `superseded_by` | string | No | id of replacing decision (same id-form rule) |
| `re_affirms` | string | No | id of prior decision this ADR re-affirms without superseding (same id-form rule) |
| `re_affirmed_by` | list | No | ids of later ADRs that re-affirmed this decision (same id-form rule) |

**Body sections** (after frontmatter):

1. **Context** -- what prompted the decision (problem, constraint, opportunity)
2. **Decision** -- what was decided (clear, direct statement)
3. **Considered Options** -- alternatives with pros/cons (subsections per option)
4. **Consequences** -- positive and negative outcomes
5. **Prior Decision** -- only when superseding; summarizes what changed and why

### Supersession Protocol

When a new ADR supersedes an existing one:

1. Set `supersedes: <target-id>` in the **new** ADR frontmatter (`dec-draft-<hash>` while both are drafts, `dec-NNN` when the target is finalized)
2. Set `superseded_by: <new-id>` in the **old** ADR frontmatter (same id-form rule)
3. Change the old ADR status to `superseded`
4. Add a `## Prior Decision` section in the new ADR body
5. `DECISIONS_INDEX.md` regenerates automatically at finalize — do not manually invoke the index-regeneration script

### Re-affirmation Protocol

When a new ADR re-affirms an existing one without superseding it (a re-opening was considered and rejected for lack of new evidence):

1. Set `status: re-affirmation` on the **new** ADR (signals meta-decision — a decision *about* another decision)
2. Set `re_affirms: <target-id>` in the **new** ADR frontmatter (same draft-vs-finalized id-form rule as Supersession)
3. Append `<new-id>` to the **old** ADR's `re_affirmed_by` list (create the list if absent)
4. **Do not** change the old ADR's status — it stays `accepted`; no `superseded_by` is set
5. Add a `## Prior Decision` section in the new ADR body explaining what was considered and why the prior decision still holds; name the evidence that would be required to justify a future supersession
6. `DECISIONS_INDEX.md` regenerates automatically at finalize

Use re-affirmation only when a prior decision is challenged, re-examined, and found still correct — not as routine acknowledgment. (Rationale: [`adr-authoring-protocols.md` § Re-affirmation Protocol](../../skills/software-planning/references/adr-authoring-protocols.md#re-affirmation-protocol).)

### Finalize Protocol

Finalize promotes drafts in `.ai-state/decisions/drafts/` to finalized `<NNN>-<slug>.md` records at merge-to-main. Invoked by the post-merge git hook and `/merge-worktree`; the protocol is **idempotent**, advisory-locked, and rewrites `dec-draft-<hash>` cross-references across a **bounded** walk scope (sibling ADR files, in-flight `.ai-work/*/LEARNINGS.md` / `SYSTEMS_PLAN.md` / `IMPLEMENTATION_PLAN.md`, and `.ai-state/specs/SPEC_*` matching the current task slug — never an arbitrary repo sweep). The bounded scope is the contract; finalize never rewrites unrelated text. `DECISIONS_INDEX.md` regenerates as the last step.

For the full step sequence (draft detection, NNN assignment, file rename + frontmatter `id:`/`status:` rewrites, the cross-reference-rewrite location table, concurrency safety, and exit codes), see [`adr-authoring-protocols.md § Finalize at Merge-to-Main`](../../skills/software-planning/references/adr-authoring-protocols.md#finalize-at-merge-to-main).

### Who Writes ADRs

| Agent | When | Scope | Destination |
|-------|------|-------|-------------|
| systems-architect | Phase 4 (trade-off analysis) | Significant trade-offs: system boundaries, data model, technology selection, security | `.ai-state/decisions/drafts/` (fragment) |
| implementation-planner | Step decomposition | Decisions affecting step ordering, module structure, approach | `.ai-state/decisions/drafts/` (fragment) |
| interface-designer | Phase 4 (trade-off analysis) | Interface-layer decisions: UI framework / API paradigm / MCP tool decomposition / error format / pagination / component-pattern selection | `.ai-state/decisions/drafts/` (fragment) |
| user | Direct tier or manual | Any decision worth preserving | `.ai-state/decisions/drafts/` preferred; `<NNN>-<slug>.md` acceptable for direct-tier, no-pipeline authoring |

All ADR authors also record decisions in `LEARNINGS.md ### Decisions Made` using the structured format. While a pipeline is in flight, `LEARNINGS.md` carries `dec-draft-<hash>` references; finalize rewrites these to `dec-NNN` at merge-to-main.

### Agent Writing Protocol

The 7-step procedure agents follow when creating a fragment ADR (identity derivation, filename construction, fragment-id computation, frontmatter, cross-reference convention, LEARNINGS.md entry, no-manual-index-regen) lives in [`adr-authoring-protocols.md § ADR Creation Protocol`](../../skills/software-planning/references/adr-authoring-protocols.md#adr-creation-protocol-fragment-name-at-create) — the canonical procedural reference for ADR-creating agents (systems-architect, implementation-planner).

### Discovery Protocol

1. Read `.ai-state/decisions/DECISIONS_INDEX.md` for an overview of finalized ADRs
2. Grep for matching `category`, `tags`, or `affected_files` in the index table
3. For in-flight work, also scan `.ai-state/decisions/drafts/` — drafts are not indexed but are authoritative during the pipeline that authored them
4. Read full ADR files for matching decisions
5. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + `Glob .ai-state/decisions/drafts/*.md` + Grep frontmatter

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
