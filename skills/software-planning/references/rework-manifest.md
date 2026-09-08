# Rework Manifest & Rework Worktree Spawn

Full procedure for the verifier's Phase 12.5 (`REWORK_MANIFEST.md` emission: clustering, row-ID computation, dedup, format, the `VERIFIER_FINDINGS.md` template) and the main-agent-facing protocol for spawning one rework worktree per manifest row. Back to [SKILL.md](../SKILL.md). Trigger condition, the `REWORK_MANIFEST.md` column names, and the `rw-<hash>` id rule stay resident in [`agents/verifier.md` § Phase 12.5](../../../agents/verifier.md).

## Phase 12.5 — Rework Manifest Emission

**Trigger condition:** Only execute this phase when operating in pipeline mode AND the completed `VERIFICATION_REPORT.md` contains one or more FAIL or WARN findings. On a clean run (all PASS findings), skip this phase entirely — do NOT write `REWORK_MANIFEST.md` and do NOT mention rework in your stdout summary.

### Clustering algorithm

Cluster the FAIL/WARN findings into rework worktrees using smell-class first, then file-locality within each class. This produces deterministic, blast-radius-bounded clusters.

1. **Bucket by smell-class**: assign each finding to either `architecture` (design violations, boundary failures, coupling issues) or `implementation` (code-quality violations, test failures, contract breaches). Findings with mixed evidence default to `architecture`.
2. **Group by file-locality within each class**: within each bucket, merge findings whose `location` file-sets overlap (share at least one file path). Disjoint file-sets become separate rows.
3. **One row per cluster**: each cluster becomes one `REWORK_MANIFEST.md` row with a unique worktree name derived from the primary file and smell-class.

### Row ID computation

For each cluster, compute the row ID using `scripts/rework_manifest.py:compute_row_id(report_id, cluster_signature)` where:
- `report_id` is the verifier report identifier (e.g., `<task-slug>-<ISO-date-hour>`)
- `cluster_signature` is a sorted, comma-joined list of the cluster's finding anchor IDs (e.g., `#fail-1,#fail-2`)

Do NOT restate the SHA1 formula here — `scripts/rework_manifest.py` is the single source of truth. The row ID is stable across re-runs given the same inputs.

### Dedup check

Before finalising each row, scan `.claude/worktrees/` for directory names matching this row's ID. If a prior worktree exists with that ID:
- Set `dedup_against: [<prior-worktree-name>]` in the row's JSON
- Downgrade `severity` from `critical` or `important` to `suggested`
- Set `notes` to indicate this is a re-emission

### Manifest format

`REWORK_MANIFEST.md` uses a hybrid markdown table + per-row fenced JSON format. The JSON is authoritative; the table is a human-readable projection.

Write the manifest as follows:

1. **Header block** — one-line summary: `Generated: <ISO> by verifier (report <report_id>). Source: [VERIFICATION_REPORT.md](...). <N> rework worktrees proposed.`
2. **Markdown table** — rendered from the row dicts using `scripts/rework_manifest.py:render_table_from_rows(rows)`. Columns: `#`, `Worktree`, `Agent`, `Severity`, `Tier`, `Class`, `Headline`.
3. **Per-row JSON blocks** — immediately after the table, one fenced ```` ```json ```` block per row containing the full row dict.

**Write-time round-trip self-check:** after rendering, call `scripts/rework_manifest.py:parse_json_blocks()` on the rendered text and assert the result equals the original row list. If the assertion fails, emit a three-part error (see Error grammar below) and do not write the manifest.

**Row dict schema** (all fields required):

```json
{
  "id": "rw-<8-hex>",
  "worktree_name": "<kebab-case-slug>",
  "target_agent": "systems-architect",
  "severity": "critical | important | suggested",
  "recommended_tier": "direct | lightweight | standard | full",
  "class": "architecture | implementation",
  "headline": "<one-sentence description of the cluster>",
  "finding_refs": ["#fail-1", "#fail-2"],
  "td_refs": ["td-NNN"],
  "confidence": "high (>80%) | medium (40–80%) | low (<40%)",
  "dedup_against": [],
  "notes": ""
}
```

`target_agent` is always `systems-architect` — routing through the architect first is invariant (all reworks route through systems-architect regardless of class).

The `confidence` field is the verifier's in-band Register-Objection signal: `low` means the verifier's finding evidence is weak and the user should scrutinise before spawning a rework worktree. The three-tier vocabulary (`high (>80%) | medium (40–80%) | low (<40%)`) is defined in [`skills/multi-perspective-analysis/references/calibrated-confidence.md`](../../multi-perspective-analysis/references/calibrated-confidence.md) — apply GRADE downgrade factors when evidence quality is limited.

### VERIFIER_FINDINGS.md template

The main agent writes one `VERIFIER_FINDINGS.md` per rework worktree. Its content derives from the corresponding manifest row. The file must contain exactly these seven sections in order:

```markdown
# Rework: <headline>

## Problem

<What is broken, with specific file references and evidence from the cluster>

## Scope

### In scope
- <files and functions directly involved>

### Out of scope
- <adjacent concerns that belong to other rework worktrees>

## Evidence

- <file:line> — <description> — from [VERIFICATION_REPORT.md#finding-anchor]
(one bullet per finding in the cluster; no findings from other clusters)

## Success Criteria

- [ ] <checkable condition 1>
- [ ] <checkable condition 2>

## Ledger Links

- td-NNN — <debt description> — [TECH_DEBT_LEDGER.md#td-NNN]

## Suggested Tier

`<tier>` — <one-sentence rationale>

## Provenance

- Source report: [VERIFICATION_REPORT.md](<relative-path>)
- Parent worktree: <parent-worktree-name>
- Parent task slug: <task-slug>
- Rework ID: `<rw-hash>`
- Verifier confidence: `<high | medium | low>`
- Generated: <ISO timestamp>
```

The `## Evidence` section must be a **filtered subset** — only the findings belonging to this cluster. Do not copy findings from other clusters into a rework's Evidence section.

**Success-Criteria test-target derivation.** When a Success Criterion nominates a pytest target, derive it from `grep -rn '<changed-file-basename>' tests/` — the consumer test that imports or reads the changed file, not the tests near it by directory or topical proximity. For test fixtures specifically, the consumer is the test that opens or imports the fixture; routing-layer tests near the fixture's *topic* do not constitute the consumer and will report green on a broken fixture. When grep returns multiple consumers, list them all; when it returns none, say so explicitly in the criterion (`no consumer test exists — verification by inspection`).

### Disposition vocabulary pointer

After writing `REWORK_MANIFEST.md`, surface this one-liner to the user:

> Rework manifest written. For each row, choose a disposition (`switch-now`, `defer-with-rationale`, or `dismiss-with-rationale`) — see [`disposition-vocabulary.md`](disposition-vocabulary.md).

### Clean-run behavior

When all findings are PASS, skip this phase entirely. Do not write `REWORK_MANIFEST.md`. Do not mention rework worktrees in your stdout summary.

### Error grammar for write failure

If writing `REWORK_MANIFEST.md` fails, emit a three-part error to stderr:

```
Cannot write REWORK_MANIFEST.md to .ai-work/<task-slug>/.
[What went wrong]: <specific error, e.g., "directory does not exist", "round-trip self-check failed">
[Why]: <root cause>
[How to fix]: <exact action — e.g., "create .ai-work/<task-slug>/ before invoking the verifier", "inspect the finding anchors in VERIFICATION_REPORT.md for malformed JSON characters">
```

## Rework Worktree Spawn Behavior

This section documents the main-agent-facing protocol for spawning rework worktrees from a `REWORK_MANIFEST.md`. The user may read this to understand what the main agent will do after a FAIL verification.

**One worktree per row**: for each row in `REWORK_MANIFEST.md`, the main agent invokes `EnterWorktree(name: <rework-slug>)` to spawn exactly one rework worktree. No batching; one call per row.

**`VERIFIER_FINDINGS.md` write contract**: inside each rework worktree, the main agent writes a `VERIFIER_FINDINGS.md` containing the seven required sections, populated from the row's payload. This file is the primary handoff artifact that `/resume-rework` discovers.

**`VERIFICATION_REPORT.md` snapshot**: the parent worktree's `VERIFICATION_REPORT.md` is snapshotted (copied) into each rework worktree at `.ai-work/<rework-slug>/parent-VERIFICATION_REPORT.md`. This gives the rework session read-only access to the full verification context without depending on the parent worktree's lifecycle.

**`td-NNN` status flip**: for each `td-NNN` reference in the manifest row's `td_refs` field, the main agent flips the ledger row from `open` to `in-flight`. The row's `notes` field is updated with the suffix `// in-flight via rework worktree <name>` per [`skills/software-planning/references/tech-debt-ledger.md`](tech-debt-ledger.md) § Producer overlays → **orchestrator** (consumer-only).

**User-facing one-liner**: after all rework worktrees are created, the main agent surfaces a message to the user: "Created N rework worktrees. To dispatch all reworks at once, run `scripts/dispatch-reworks` from the project root (or `/dispatch-reworks` as a slash command). Default mode (`--bg`) starts headless background sessions — monitor them with `claude agents` from a fresh terminal pane outside the orchestrator session; macOS notifications fire when each session completes. Add `--terminals` to open each rework in its own visible terminal window instead (you'll press Enter in each to start). Use `--dry-run` first to preview the dispatch plan. The full user workflow — monitoring, handling mid-rework prompts, troubleshooting — is documented in `docs/rework-dispatch.md`." This gives the user the next concrete action.

**Parent cleanup gating**: parent `.ai-work/<parent-slug>/` cleanup is gated on rework completion. Before cleanup, the main agent surfaces the count of open rework worktrees — emitting a status line of the form: "X reworks open. Parent cleanup deferred." If any rework remains in flight (its worktree not yet merged to main), the parent pipeline directory is preserved. The user can override with explicit confirmation.

**Resolution path**: when a rework worktree merges back to main, `scripts/finalize_tech_debt_ledger.py` (invoked by the post-merge git hook) flips the linked `td-NNN` row from `in-flight` to `resolved`, citing the merge commit in `resolved-by`.
