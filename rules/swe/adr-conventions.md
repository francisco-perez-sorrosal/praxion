---
core: true
load: always_on
install: symlink
---

## ADR Conventions

Architecture Decision Records live in `.ai-state/decisions/` as Markdown files with YAML frontmatter. They persist beyond `.ai-work/` cleanup and are committed to git.

### File Format

Pipeline-authored ADRs follow the **fragment-name-at-create, finalize-at-merge** path: they land as a fragment under `.ai-state/decisions/drafts/`, then promote to a stable `<NNN>-<slug>.md` record at merge-to-main (see [Fragment Filename Schema](#fragment-filename-schema) and [Finalized ADRs](#finalized-adrs-post-merge)). The legacy NNN-at-create path survives only for manual, no-session ADRs.

#### Fragment Filename Schema

Pipeline-authored ADRs land as `.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` with id `dec-draft-<8-char-hash>`; drafts cross-reference via `dec-draft-<hash>`, never a speculative `dec-NNN` — [Finalize](#finalize-protocol) rewrites at merge. Full construction: [`adr-authoring-protocols.md` § ADR Creation Protocol](../../skills/software-planning/references/adr-authoring-protocols.md#adr-creation-protocol-fragment-name-at-create).

#### Finalized ADRs (post-merge)

After finalize, the ADR lives at `.ai-state/decisions/<NNN>-<slug>.md`, `<NNN>` assigned by the finalize script — pipeline-authored ADRs never pick their own. Manual, no-session ADRs alone may self-assign directly. Detail: [`adr-authoring-protocols.md` § Who Creates ADRs](../../skills/software-planning/references/adr-authoring-protocols.md#who-creates-adrs).

#### Frontmatter

The frontmatter schema is shared between draft and finalized ADRs; only `id` and the cross-reference fields (`supersedes`, `superseded_by`, `re_affirms`, `re_affirmed_by`) differ in value form (`dec-draft-<hash>` during draft, `dec-NNN` after finalize).

Fields: `id`, `title`, `status`, `category`, `date`, `summary`, `tags`, `made_by`, `agent_type`, `branch`, `pipeline_tier`, `affected_files`, `affected_reqs`, `supersedes`, `superseded_by`, `re_affirms`, `re_affirmed_by`, `retired_by`, `supersedes_in_part`, `superseded_in_part_by`, `dissent`. Full table: [`adr-authoring-protocols.md` § Frontmatter Schema](../../skills/software-planning/references/adr-authoring-protocols.md#frontmatter-schema).

#### What makes a decision `architectural`

A decision is `architectural` **iff it changes what exists or what connects**:

- **internal** — it adds, removes, merges, or splits a component in any artifact family (skill, agent, rule, command, hook, script, MCP server, package, service); moves a responsibility from one component to another; or introduces or removes a boundary or abstraction between them.
- **published** — it changes a canonical block, a shipped template, or an onboard-contract phase.

If the component inventory and its boundaries are unchanged once the decision lands, it is **not** architectural — *however consequential the trade-off*.

**Falsifier — name the component added, removed, or whose responsibility moved.** If no such name exists, the category is wrong: process, policy, deliberation method, and features inside one component are `behavioral`, `implementation`, or `configuration`.

Source of truth for this test. Worked examples, evidence, and calibration: [`adr-authoring-protocols.md` § The `architectural` Test](../../skills/software-planning/references/adr-authoring-protocols.md#the-architectural-test).

**Body sections** (after frontmatter):

1. **Context** -- what prompted the decision (problem, constraint, opportunity)
2. **Decision** -- what was decided (clear, direct statement)
3. **Considered Options** -- alternatives with pros/cons (subsections per option)
4. **Consequences** -- positive and negative outcomes
5. **Disconfirmation** -- **always-on for `category: architectural`**; three required sub-items (Falsifier, Steelmanned runner-up, Reversal trigger) — full definitions in `adr-authoring-protocols.md`'s creation protocol (see [Agent Writing Protocol](#agent-writing-protocol) below).
6. **Prior Decision** -- only when superseding; summarizes what changed and why

### Relation Protocols

| Protocol | What changes | Fields touched |
|---|---|---|
| Supersession | Fully replaces old; old → `superseded` | `supersedes` / `superseded_by` |
| Re-affirmation | Affirms old unchanged; old stays `accepted` | `re_affirms` / `re_affirmed_by` |
| Retirement | Old subject removed, not re-decided; old → `retired` | `retired_by` |
| Partial-Supersession | Narrows some clauses of old; old stays non-terminal | `supersedes_in_part` / `superseded_in_part_by` |

Every relation adds a `## Prior Decision` section (to the new ADR, or for Retirement the old) explaining what changed and why; `DECISIONS_INDEX.md` regenerates at finalize — never invoke manually. Full step sequences and the supersession-vs-retirement / supersession-vs-partial tests: [`adr-authoring-protocols.md`](../../skills/software-planning/references/adr-authoring-protocols.md) §§ Supersession / Re-affirmation / Retirement / Partial-Supersession Protocol.

### Finalize Protocol

Finalize promotes drafts to finalized `<NNN>-<slug>.md` records at merge-to-main (post-merge git hook + `/merge-worktree`). It is **idempotent** and rewrites `dec-draft-<hash>` cross-references to `dec-NNN` across a **bounded citation net** — never an arbitrary repo sweep, never code; `DECISIONS_INDEX.md` regenerates last. Full step sequence: [`adr-authoring-protocols.md § Finalize at Merge-to-Main`](../../skills/software-planning/references/adr-authoring-protocols.md#finalize-at-merge-to-main).

### Who Writes ADRs

Only systems-architect, implementation-planner, interface-designer, orchestrator (Direct/Lightweight, no pipeline agent spawned), and the user (manual) create ADR fragments, always under `.ai-state/decisions/drafts/`. **The implementer authors no ADR** and may apply only mechanical corpus edits a plan step specifies — flip a `status:`, set a cross-reference field, or correct malformed frontmatter; a new record, rationale, or category judgement returns to the architect or planner.

All ADR authors record decisions in `LEARNINGS.md ### Decisions Made`; `dec-draft-<hash>` references there rewrite to `dec-NNN` at finalize. Full per-agent When/Scope/Destination table: [`adr-authoring-protocols.md` § Who Writes ADRs](../../skills/software-planning/references/adr-authoring-protocols.md#who-writes-adrs).

### Agent Writing Protocol

The fragment-creation procedure lives in [`adr-authoring-protocols.md § ADR Creation Protocol`](../../skills/software-planning/references/adr-authoring-protocols.md#adr-creation-protocol-fragment-name-at-create) — canonical for systems-architect and implementation-planner.

### Discovery Protocol

Retrieval-first. An ungated full `Read` of `DECISIONS_INDEX.md` is **forbidden** — it grows unbounded, running tens of thousands of tokens at a few hundred ADRs. Exception: a genuinely cross-cutting task a keyword scan would miss; say so when you take it.

1. **Pre-scan**: prefer `python3 scripts/query_adrs.py --paths <files>` (or `--staged`); otherwise `grep -in '<keyword>' .ai-state/decisions/DECISIONS_INDEX.md`, reading only matching rows via `offset`+`limit`
2. Also scan `.ai-state/decisions/drafts/` — not indexed but authoritative in-flight
3. Read full ADR files for matching decisions
4. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + `Glob .ai-state/decisions/drafts/*.md` + Grep frontmatter

### Linking to ADRs

Persistent files (`docs/`, `.ai-state/DESIGN.md`, READMEs) link the **finalized** record at `.ai-state/decisions/<NNN>-<slug>.md`, never a `drafts/<…>.md` fragment — a `drafts/` path stops resolving once the pipeline merges. Mid-pipeline, cite by `dec-draft-<hash>` id, not path — the id survives finalize as `dec-NNN`; the path does not. (ADR-to-ADR cross-references use the frontmatter `id` form, not file-path links.)

### Consumption

Consumer behavior lives at its own definition, not duplicated here: sentinel's DL0x checks, skill-genesis's pattern-harvest scope, verifier's `affected_reqs` cross-reference, systems-architect's brownfield baseline, `architect-validator`'s code↔DSL↔ADR triangle check.

### Relationship to LEARNINGS.md

`LEARNINGS.md` is broader (gotchas, patterns, edge cases, tech debt, decisions) and ephemeral; ADR files are narrower (decisions only) and persist. Decisions appear in both. Draft-stage `dec-draft-<hash>` references in `LEARNINGS.md` rewrite to `dec-NNN` at finalize alongside the ADR files themselves.

### Migration — historical ADRs

Pre-existing finalized ADRs keep their filenames, `dec-NNN` ids and cross-references; the fragment scheme applies only to newly authored records.
