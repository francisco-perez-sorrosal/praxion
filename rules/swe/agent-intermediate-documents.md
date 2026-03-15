## Agent Intermediate Documents

Agent documents live in two locations based on their lifecycle:

- **`.ai-work/`** — ephemeral pipeline intermediates (deleted after use)
- **`.ai-state/`** — persistent project intelligence (committed to git)

### `.ai-work/` — Ephemeral Pipeline Documents

```
<project-root>/
  .ai-work/
    IDEA_PROPOSAL.md
    RESEARCH_FINDINGS.md
    CONTEXT_REVIEW.md
    SYSTEMS_PLAN.md
    SPEC_DELTA.md
    SKILL_GENESIS_REPORT.md
    IMPLEMENTATION_PLAN.md
    WIP.md
    LEARNINGS.md
    VERIFICATION_REPORT.md
    PROGRESS.md
```

`PROGRESS.md` is an append-only log of agent phase-transition signals. Format: `[TIMESTAMP] [AGENT] Phase N/M: [phase-name] -- [summary] #label1 #key=value`

- Dot-prefixed — hidden by default in file browsers and `ls`
- Flat structure — all documents at directory root, no per-agent subdirectories
- Created on first use — agents create `.ai-work/` when writing their first document

Scope: **exclusively for agent coordination pipeline documents** — the outputs defined in the [SWE agent coordination protocol](swe-agent-coordination-protocol.md) rule.

Not stored here:
- Command scratch files or skill working files
- Project documentation or ADRs
- Build artifacts or tool caches

### `.ai-state/` — Persistent Project Intelligence

```
<project-root>/
  .ai-state/
    IDEA_LEDGER_*.md
    SENTINEL_REPORT_*.md
    SENTINEL_LOG.md
    specs/
      SPEC_<name>_YYYY-MM-DD.md
```

- Committed to git — versioned, shareable, accumulates value over time
- Created on first use — agents create `.ai-state/` when writing their first persistent document

`IDEA_LEDGER_*.md` — promethean's timestamped ideation records (sentinel baseline, implemented/pending/discarded ideas, future paths). Each run carries forward all previous entries.

`SENTINEL_REPORT_*.md` — timestamped audit reports (`SENTINEL_REPORT_YYYY-MM-DD_HH-MM-SS.md`). `SENTINEL_LOG.md` — append-only run summary table (timestamp, report file, health grade, finding counts, coherence grade).

`SPEC_<name>_YYYY-MM-DD.md` — archived behavioral specifications with traceability matrices. Created by the implementation-planner at end-of-feature for medium/large tasks.

Agents that update `.ai-state/`: promethean (idea ledger), sentinel (report, log), implementation-planner (spec archival). Artifact inventory is not stored here — it is derivable from the filesystem.

### Document Lifecycle

| Tier | Location | Documents | Lifetime |
|------|----------|-----------|----------|
| Ephemeral | `.ai-work/` | `IDEA_PROPOSAL.md`, `RESEARCH_FINDINGS.md`, `CONTEXT_REVIEW.md`, `SYSTEMS_PLAN.md`, `SPEC_DELTA.md`, `SKILL_GENESIS_REPORT.md`, `VERIFICATION_REPORT.md`, `PROGRESS.md` | Single pipeline run — delete after downstream consumption (merge `VERIFICATION_REPORT.md` patterns into `LEARNINGS.md` first) |
| Session-persistent | `.ai-work/` | `IMPLEMENTATION_PLAN.md`, `WIP.md`, `LEARNINGS.md` | Across sessions — merge learnings into permanent locations at feature end |
| Permanent | `.ai-state/` | `IDEA_LEDGER_*.md`, `SENTINEL_REPORT_*.md`, `SENTINEL_LOG.md`, `SPEC_*.md` | Project lifetime — committed to git, timestamped per run |

### Version Control and Cleanup

- **Never commit `.ai-work/`** — add to `.gitignore`. **Always commit `.ai-state/`**.
- Clean up with `rm -rf .ai-work/` after pipeline completion. Merge `LEARNINGS.md` into permanent locations first.

### Parallel Execution

When agents run concurrently within a pipeline (e.g., implementer + test-engineer on paired steps), each concurrent agent writes to a scoped fragment file instead of the canonical document:

| Canonical | Fragment Pattern | Example |
|-----------|-----------------|---------|
| `WIP.md` | `WIP_<agent-type>.md` | `WIP_implementer.md`, `WIP_test-engineer.md`, `WIP_doc-engineer.md` |
| `LEARNINGS.md` | `LEARNINGS_<agent-type>.md` | `LEARNINGS_implementer.md`, `LEARNINGS_doc-engineer.md` |
| `PROGRESS.md` | `PROGRESS_<agent-type>.md` | `PROGRESS_implementer.md`, `PROGRESS_doc-engineer.md` |

Agent types use the names from the [coordination protocol](swe-agent-coordination-protocol.md): `implementer`, `test-engineer`, `doc-engineer`, `cicd-engineer`, etc. Single-writer documents (`SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`, `CONTEXT_REVIEW.md`, etc.) are unaffected.

`CONTEXT_REVIEW.md` is cumulative and single-writer (context-engineer only). Each pipeline stage appends a new `## [Stage] Stage Review` section — the document grows as the pipeline progresses. Not subject to fragment patterns.

The supervising agent (implementation-planner or main agent) merges fragment files into canonical documents after concurrent agents complete. See the software-planning skill's [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md) for the full semantic reconciliation protocols.
