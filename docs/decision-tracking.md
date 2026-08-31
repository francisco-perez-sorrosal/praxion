---
diataxis: explanation
audience: developer
---

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
  drafts/                    # In-flight, pipeline-authored ADRs (pre-finalize)
    20260830-1200-fperez-adr-living-view-slug.md
  DECISIONS_INDEX.md         # Auto-generated summary table (finalized records only)
```

### Who Writes ADRs

| Agent | When | Scope |
|-------|------|-------|
| systems-architect | Trade-off analysis (Phase 4) | System boundaries, data model, technology selection, security |
| implementation-planner | Step decomposition | Step ordering, module structure, approach decisions |
| interface-designer | Trade-off analysis (Phase 4) | Interface-layer decisions: UI framework, API paradigm, MCP tool decomposition, error format |
| orchestrator | Direct/Lightweight tier, no pipeline agent spawned | Any decision worth preserving during an interactive session |
| user | Manual (no session, no agent) | Any decision worth preserving |

All ADR authors also record decisions in `LEARNINGS.md ### Decisions Made`. The implementer and test-engineer record decisions in `LEARNINGS.md` only -- they do not create ADR files (the planner/architect/designer/orchestrator handle persistence).

### How ADRs Are Written

Pipeline-authored ADRs (systems-architect, implementation-planner, interface-designer, or the orchestrator inside a Standard/Full-tier pipeline) follow **fragment-name-at-create, finalize-at-merge**:

1. Write the ADR as a fragment at `.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` with a provisional `id: dec-draft-<8-char-hash>` and `status: proposed`
2. Record the same decision in `LEARNINGS.md ### Decisions Made`, citing the `dec-draft-<hash>` id
3. Do **not** invoke `scripts/regenerate_adr_index.py` manually -- `DECISIONS_INDEX.md` regenerates automatically at finalize

At merge-to-main, `scripts/finalize_adrs.py` (invoked by the post-merge git hook or `/merge-worktree`) promotes each draft to `.ai-state/decisions/<NNN>-<slug>.md`, assigns the sequence number, rewrites `dec-draft-<hash>` cross-references to `dec-NNN` across the bounded citing surface, and regenerates the index.

Manual, no-session ADRs (hand-authored with no session or agent involved) may skip the draft stage and be created directly at `.ai-state/decisions/<NNN>-<slug>.md` -- this path is deprecated for pipeline-authored ADRs. See [`adr-conventions.md`](../rules/swe/adr-conventions.md) for the full schema and finalize protocol.

No external CLI tool or API key is required -- the Write tool is sufficient.

### Reminder Hook

A lightweight `PreToolUse` hook (`adr_reminder.py`) checks at commit time whether staged files touch architectural paths (`agents/`, `rules/`, `skills/`, `src/`). If no ADR file has today's date, it emits a warning as a nudge. The hook never blocks commits -- it always exits 0.

## ADR File Format

Each ADR file has YAML frontmatter with required fields (`id`, `title`, `status`, `category`, `date`, `summary`, `tags`, `made_by`) and a MADR body with four sections plus a conditional fifth:

1. **Context** -- what prompted the decision
2. **Decision** -- what was decided
3. **Considered Options** -- alternatives with pros/cons
4. **Consequences** -- positive and negative outcomes
5. **Disconfirmation** -- always-on for `category: architectural`; falsifier, steelmanned runner-up, reversal trigger

Statuses: `proposed`, `accepted`, `superseded`, `rejected`, `re-affirmation`, `retired`.

Categories: `architectural`, `behavioral`, `implementation`, `configuration`.

When a decision supersedes a prior one, both ADR files get bidirectional pointers (`supersedes` / `superseded_by` fields) and the old ADR's status changes to `superseded`. Re-affirmation and retirement follow parallel protocols -- see [`adr-conventions.md`](../rules/swe/adr-conventions.md) for the full set.

## Discovery and Index

`DECISIONS_INDEX.md` is an auto-generated table (columns: ID, Title, Status, Category, Date, Tags, Summary) covering **finalized** records only -- it regenerates automatically at merge-to-main finalize and is never hand-edited or manually invoked.

Discovery is retrieval-first, not index-first. An ungated full `Read` of `DECISIONS_INDEX.md` is forbidden once the corpus grows past a keyword scan's blind spot -- the index has no upper bound and can run to tens of thousands of tokens. Agents discover decisions by:

1. **Pre-scan**: prefer `python3 scripts/query_adrs.py --paths <files>` (or `--staged`) when the file scope is known -- it matches `affected_files` frontmatter and defaults to the current streamline (accepted + re-affirmation); otherwise `grep -in '<keyword>' .ai-state/decisions/DECISIONS_INDEX.md` per scope keyword (tags, category, affected paths, feature terms), reading only matching rows via `offset`+`limit`
2. For in-flight work, also scan `.ai-state/decisions/drafts/` -- drafts are not indexed but are authoritative during the pipeline that authored them
3. Read full ADR files for matching decisions
4. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + `Glob .ai-state/decisions/drafts/*.md` + Grep frontmatter

## Ecosystem Consumption

See [`adr-conventions.md § Consumption`](../rules/swe/adr-conventions.md#consumption) for the authoritative, per-consumer table (sentinel's DL0x range, skill-genesis, verifier, systems-architect, and `architect-validator`'s code↔DSL↔ADR triangle check) -- kept there to avoid duplicating a table that drifts whenever a consumer's check set changes.
