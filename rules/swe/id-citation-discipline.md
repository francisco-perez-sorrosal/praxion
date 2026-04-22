---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.rs"
  - "**/*.go"
  - "**/*.java"
  - "**/*.kt"
  - "**/*.rb"
  - "**/*.sh"
  - "**/*.swift"
  - "**/*.cs"
  - "**/*.cpp"
  - "**/*.c"
  - "**/*.h"
  - "**/*.hpp"
---

## Identifier Citation Discipline

Committed code and tests must not reference identifiers whose source document has a shorter lifespan than the code itself. Pipeline-local and feature-local identifiers (`REQ-NN`, `AC-NN`, step numbers) belong in pipeline documents and archived specs — never in function names, docstrings, comments, or test bodies.

This is the inward-facing parallel of [`shipped-artifact-isolation.md`](shipped-artifact-isolation.md): that rule prevents shipped artifacts from referencing this project's `.ai-state/` entries; this rule prevents this project's code from referencing ephemeral `.ai-work/` entries.

### Identifier Lifecycle Table

| ID shape | Source document | Lifecycle | May appear in code? |
|----------|-----------------|-----------|---------------------|
| `REQ-NN` | `SYSTEMS_PLAN.md` (in-pipeline) / archived SPEC (post-archive) | Ephemeral during pipeline; frozen-per-feature after archive | **Never** |
| `AC-NN` | `SYSTEMS_PLAN.md` § Acceptance Criteria | Always ephemeral (no archive path) | **Never** |
| `Step N` / `Step 7.8` | `IMPLEMENTATION_PLAN.md`, `WIP.md` | Pipeline-local, always ephemeral | **Never** |
| `dec-draft-<hash>` | `.ai-state/decisions/drafts/` | Mid-pipeline only (rewritten at finalize) | **Never** |
| `dec-NNN` | `.ai-state/decisions/<NNN>-<slug>.md` | Persistent, committed to git | **Yes** (in comments, when citing architectural rationale) |
| Sentinel check IDs (`F07`, `T03`, `EC06`) | `agents/sentinel.md` | Part of the agent definition (persistent) | **Yes** (in sentinel code) |

Rule of thumb: **if the identifier lives in a document that gets deleted with `.ai-work/`, or in a document that is frozen-read-only per-feature, it does not belong in code.**

### Why This Exists

Three failure modes are prevented:

1. **Dangling references.** `AC-03` in a docstring points to `SYSTEMS_PLAN.md` — a file deleted at pipeline cleanup. Six months later a reader has no way to resolve it.
2. **Ambiguous references.** `REQ-03` in a test name points to whichever archived SPEC owns that REQ — but test files get refactored, features merge and split, and "which spec's REQ-03?" becomes unanswerable.
3. **Ecosystem contamination.** Praxion-built pipelines operate on user projects. If the agents embed these identifiers as habit, every downstream project inherits the dangling-reference pattern.

### What to Do Instead

**For behavioral traceability (REQ → test mapping):**

Praxion uses a **two-layer external mechanism**, not in-code citations:

- **During the pipeline** — the implementer and test-engineer append entries to an ephemeral traceability file at `.ai-work/<task-slug>/traceability.yml` as they produce code. Parallel execution uses fragment files (`traceability_implementer.yml`, `traceability_test-engineer.yml`) that the planner reconciles into the canonical `traceability.yml` at batch merge.
- **At end-of-feature archive** — the implementation-planner renders the reconciled `traceability.yml` into the archived SPEC's Traceability Matrix section (Markdown table). The ephemeral YAML then gets deleted with `.ai-work/`. The matrix survives in the persistent archived SPEC as the historical record.
- **Post-archive** — readers consult the archived SPEC's matrix. Tooling consumes it too: `/sdd-coverage` reads either `traceability.yml` (pipeline in flight) or the archived SPEC matrix (post-archive).

See [`skills/spec-driven-development/SKILL.md`](../../skills/spec-driven-development/SKILL.md) for the YAML schema and matrix rendering protocol.

**For naming conventions:**

Test function names **describe the behavior under test** — matching the existing `testing-conventions.md` rule. Never prefix test names with IDs:

| Use | Avoid |
|-----|-------|
| `test_rejects_empty_input` | `test_req03_rejects_empty_input` |
| `test_session_expired_returns_401` | `test_req01_session_expired_returns_401` |
| `test_draft_finalizes_to_next_nnn` | `test_ac03_draft_finalizes_to_next_nnn` |
| `test_tool_input_summary_truncates_at_4kb` | `test_req31_tool_input_summary_truncation` |

**For docstrings and comments:**

Describe behavior, constraints, or intent. Do not embed REQ/AC/step references. A docstring is prose for human readers; a reader without access to the archived SPEC cannot resolve the identifier, and a reader with access does not need it — the matrix already holds the mapping.

### Narrow Exceptions (and their reasons)

- **ADR citations (`dec-NNN`)** — allowed in comments when the code implements a decision whose rationale is non-obvious and the ADR is worth pointing at. Cite only finalized ADRs, never draft identifiers.
- **Sentinel check IDs** — allowed inside sentinel's own implementation (`agents/sentinel.md` references, test files for sentinel logic). The check IDs are part of sentinel's contract, not pipeline-local identifiers.
- **Teaching material** — skills, rules, and project documentation may use illustrative placeholders (`REQ-01`, `AC-NN`, `dec-NNN`) to teach conventions. These are placeholder shapes, not references to concrete entries. See `shipped-artifact-isolation.md` for the broader placeholder-vs-reference distinction.

### Self-Test Before Committing Code

- Does any function name, docstring, comment, or test body contain `REQ-`, `AC-`, or `Step N` patterns?
- If yes — is the identifier sourced from `.ai-work/` (always ephemeral) or an archived SPEC (feature-frozen)? Both answers require removal.
- Rewrite the site to describe behavior instead. Put the traceability link in `.ai-work/<task-slug>/traceability.yml` if the pipeline is active, or leave it to the archived SPEC matrix if the feature is already archived.

### Enforcement

The sentinel and the `check_shipped_artifact_isolation.py` pair currently enforce outbound isolation. Inbound enforcement (this rule) is taught here and applied by implementer/test-engineer self-review and the verifier's convention compliance phase. A mechanical check — parallel to the outbound one — can be added when violation rates justify it.
