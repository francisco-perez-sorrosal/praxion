# Decision Tracking

AI-assisted development sessions produce many decisions -- architecture choices, implementation trade-offs, rejected alternatives, calibration judgments. Most are lost: buried in conversation transcripts, trapped in ephemeral documents, or visible only as unexplained code. This project captures decisions as structured Architecture Decision Records (ADRs) in `.ai-state/decisions/`, following the MADR format with YAML frontmatter for agent queryability and human browsability.

For the full format specification and agent protocol, see the [`adr-conventions.md`](../rules/swe/adr-conventions.md) rule.

## The Problem: Decision Loss

Before decision tracking, decisions were lost at five points in the pipeline:

| Loss Point              | Severity   | What Was Lost                                                                                                         |
| ----------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| Session boundary gap    | Critical   | Direct/Lightweight tier decisions never entered any document -- rationale existed only in the conversation transcript |
| LEARNINGS.md deletion   | High       | End-of-feature cleanup merged selectively; granular decisions fell through the cracks                                 |
| Spec archival scope     | Medium     | Only medium/large features got archived specs; small features with important decisions got nothing                    |
| Architect trade-offs    | Medium     | The systems-architect's trade-off analysis lived in ephemeral `SYSTEMS_PLAN.md` with no systematic path to permanence |
| Implicit code decisions | Low-Medium | Naming choices, data structure selections, error handling strategies -- visible in diffs but never documented         |

## ADR-Based Architecture

Decisions are captured as individual Markdown files in `.ai-state/decisions/`, each with YAML frontmatter for structured querying and a MADR body for human readability.

```
.ai-state/decisions/
  001-skill-wrapper-over-mcp-server.md
  002-otel-relay-architecture.md
  003-phoenix-isolated-venv.md
  ...
  DECISIONS_INDEX.md         # Auto-generated summary table
```

### Who Writes ADRs

| Agent | When | Scope |
|-------|------|-------|
| systems-architect | Trade-off analysis (Phase 4) | System boundaries, data model, technology selection, security |
| implementation-planner | Step decomposition | Step ordering, module structure, approach decisions |
| user | Direct tier or manual | Any decision worth preserving |

All ADR authors also record decisions in `LEARNINGS.md ### Decisions Made`. The implementer and test-engineer record decisions in `LEARNINGS.md` only -- they do not create ADR files (the planner/architect handle persistence).

### How ADRs Are Written

Agents create ADR files directly using the Write tool:

1. Scan `.ai-state/decisions/` for the highest existing sequence number
2. Create `.ai-state/decisions/<NNN+1>-<slug>.md` with frontmatter and MADR body
3. Record the same decision in `LEARNINGS.md ### Decisions Made`
4. Regenerate `DECISIONS_INDEX.md` via `python scripts/regenerate_adr_index.py`

No external CLI tool or API key is required -- the Write tool is sufficient.

### Reminder Hook

A lightweight `PreToolUse` hook (`adr_reminder.py`) checks at commit time whether staged files touch architectural paths (`agents/`, `rules/`, `skills/`, `src/`). If no ADR file has today's date, it emits a warning as a nudge. The hook never blocks commits -- it always exits 0.

## ADR File Format

Each ADR file has YAML frontmatter with required fields (`id`, `title`, `status`, `category`, `date`, `summary`, `tags`, `made_by`) and a MADR body with four sections:

1. **Context** -- what prompted the decision
2. **Decision** -- what was decided
3. **Considered Options** -- alternatives with pros/cons
4. **Consequences** -- positive and negative outcomes

Statuses: `proposed`, `accepted`, `superseded`, `rejected`.

Categories: `architectural`, `behavioral`, `implementation`, `configuration`.

When a decision supersedes a prior one, both ADR files get bidirectional pointers (`supersedes` / `superseded_by` fields) and the old ADR's status changes to `superseded`.

## Discovery and Index

`DECISIONS_INDEX.md` is an auto-generated table with columns: ID, Title, Status, Category, Date, Tags, and Summary. It provides a single-read overview for both humans and agents.

Agents discover decisions by:

1. Reading `DECISIONS_INDEX.md` for overview
2. Grepping for matching `category`, `tags`, or `affected_files`
3. Reading full ADR files for details
4. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + Grep frontmatter

## Ecosystem Consumption

Four downstream agents consume ADR files:

| Consumer          | How It Uses Decisions                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| sentinel          | DL01-DL05: validates ADR directory, frontmatter, body sections, index consistency, frequency   |
| skill-genesis     | Recurring decision patterns across features become candidates for rules or skills               |
| verifier          | Cross-references `affected_reqs` against the traceability matrix during post-implementation review |
| systems-architect | Reads prior feature decisions as brownfield baseline for new architecture work                   |
