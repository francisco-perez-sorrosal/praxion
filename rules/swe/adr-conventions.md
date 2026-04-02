## ADR Conventions

Architecture Decision Records live in `.ai-state/decisions/` as Markdown files with YAML frontmatter. They persist beyond `.ai-work/` cleanup and are committed to git.

### File Format

**Naming**: `<NNN>-<slug>.md` -- zero-padded 3-digit sequence number, kebab-case slug (e.g., `001-otel-relay-architecture.md`). Assign the next sequential number by scanning existing filenames.

**Frontmatter** (between `---` delimiters):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | `dec-NNN` matching the filename number |
| `title` | string | Yes | Short decision title |
| `status` | string | Yes | `proposed` / `accepted` / `superseded` / `rejected` |
| `category` | string | Yes | `architectural` / `behavioral` / `implementation` / `configuration` |
| `date` | string | Yes | ISO 8601 date (`YYYY-MM-DD`) |
| `summary` | string | Yes | One-line description for index and scanning |
| `tags` | list | Yes | Lowercase topic tags for filtering |
| `made_by` | string | Yes | `agent` / `user` |
| `agent_type` | string | When agent | Which agent (e.g., `systems-architect`) |
| `pipeline_tier` | string | No | `direct` / `lightweight` / `standard` / `full` / `spike` |
| `affected_files` | list | No | Paths impacted by the decision |
| `affected_reqs` | list | No | REQ IDs linked to the decision |
| `supersedes` | string | No | `dec-NNN` of prior decision |
| `superseded_by` | string | No | `dec-NNN` of replacing decision |

**Body sections** (after frontmatter):

1. **Context** -- what prompted the decision (problem, constraint, opportunity)
2. **Decision** -- what was decided (clear, direct statement)
3. **Considered Options** -- alternatives with pros/cons (subsections per option)
4. **Consequences** -- positive and negative outcomes
5. **Prior Decision** -- only when superseding; summarizes what changed and why

### Supersession Protocol

When a new ADR supersedes an existing one:

1. Set `supersedes: dec-NNN` in the **new** ADR frontmatter
2. Set `superseded_by: dec-MMM` in the **old** ADR frontmatter
3. Change the old ADR status to `superseded`
4. Add a `## Prior Decision` section in the new ADR body
5. Regenerate `DECISIONS_INDEX.md`

### Who Writes ADRs

| Agent | When | Scope |
|-------|------|-------|
| systems-architect | Phase 4 (trade-off analysis) | Significant trade-offs: system boundaries, data model, technology selection, security |
| implementation-planner | Step decomposition | Decisions affecting step ordering, module structure, approach |
| user | Direct tier or manual | Any decision worth preserving |

All ADR authors also record decisions in `LEARNINGS.md ### Decisions Made` using the structured format.

### Agent Writing Protocol

1. Scan `.ai-state/decisions/` for the highest existing NNN
2. Create the ADR file at `.ai-state/decisions/<NNN+1>-<slug>.md` using the Write tool
3. Record the same decision in `LEARNINGS.md ### Decisions Made`
4. Run `python scripts/regenerate_adr_index.py` or write `DECISIONS_INDEX.md` directly

### Discovery Protocol

1. Read `.ai-state/decisions/DECISIONS_INDEX.md` for overview
2. Grep for matching `category`, `tags`, or `affected_files` in the index table
3. Read full ADR files for matching decisions
4. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + Grep frontmatter

### Consumption

| Consumer | Purpose |
|----------|---------|
| sentinel | DL01-DL05: validate ADR format, frontmatter, body, index consistency, frequency |
| skill-genesis | Recurring decision patterns across features |
| verifier | Cross-reference `affected_reqs` against traceability matrix |
| systems-architect | Brownfield baseline for prior feature decisions |

### Relationship to LEARNINGS.md

- `LEARNINGS.md` is broader: gotchas, patterns, edge cases, tech debt, decisions
- ADR files are narrower: decisions only, persistent, human-browsable
- Decisions appear in both -- `LEARNINGS.md` is ephemeral; ADR files persist
