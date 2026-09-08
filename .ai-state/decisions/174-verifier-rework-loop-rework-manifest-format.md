---
id: dec-174
title: REWORK_MANIFEST.md uses a markdown table with one fenced JSON block per row
status: accepted
category: architectural
date: 2026-05-14
summary: Verifier writes REWORK_MANIFEST.md as a human-scannable markdown table plus per-row fenced JSON blocks (one block per worktree), giving the main agent a parseable structured contract without sacrificing human review.
tags: [verifier, rework, manifest, interface-design, agentic-contract]
made_by: agent
agent_type: interface-designer
branch: worktree-verifier-rework-loop
pipeline_tier: standard
affected_files:
  - agents/verifier.md
  - commands/resume-rework.md
---

## Context

The verifier ends a rework-eligible pipeline by emitting a contract file the main agent reads to spawn N rework worktrees. The contract has three readers in tension:

1. **Main agent** — needs structured, parseable rows (worktree name, target agent, recommended tier, severity, finding cluster).
2. **The user** — needs to scan the manifest and approve / veto rework worktrees before any worktree is created.
3. **Future verifier runs** — must dedup against existing entries to support re-verify idempotency.

A pure-JSON file (`REWORK_MANIFEST.json`) is parseable but opaque to humans. A pure markdown table is scannable but introduces parsing fragility (column splits, escapes, multi-line cells). The receiving main agent is an LLM, not a strict parser, but the format must still be hard to misuse.

## Decision

Author `REWORK_MANIFEST.md` as a hybrid:

- **Section 1 — Summary table** (human-scannable; one row per proposed rework worktree). Columns: `#`, `Worktree`, `Agent`, `Severity`, `Tier`, `Class`, `Headline`.
- **Section 2 — Per-row JSON blocks** (machine-parseable; one fenced `json` block per row, in the same order, addressed by `id`). Each block is the authoritative source; the table is rendered from it.

The verifier always writes both halves; consumers (main agent) parse the JSON blocks and ignore the table. Per-row fenced JSON is preferred over a single top-level JSON array because:

- It survives partial writes — a half-written 4th row does not invalidate rows 1–3.
- It diffs cleanly in PRs (one row, one block).
- It makes the table-to-block mapping obvious to a human reading the file top-to-bottom.

### Manifest row schema (the fenced JSON block)

| key | type | required | semantics |
|-----|------|----------|-----------|
| `id` | string | yes | `rw-<8-char-hash>` derived from `sha1(report_id + cluster_signature)[:8]`; stable across re-runs (idempotency key) |
| `worktree_name` | string | yes | suggested kebab-case slug; main agent may override |
| `target_agent` | enum | yes | `systems-architect` or `implementation-planner` (the only two routable agents) |
| `severity` | enum | yes | `critical` / `important` / `suggested` — sentinel-aligned |
| `recommended_tier` | enum | yes | `direct` / `lightweight` / `standard` / `full` — from the SWE coordination tier table |
| `class` | enum | yes | `architecture` / `implementation` — directly determines `target_agent` |
| `headline` | string | yes | one-line summary (≤80 chars) for the user-facing table |
| `finding_refs` | string[] | yes | report-local anchors (`#fail-3`, `#warn-1`) — never `REQ-`/`AC-` (id-citation-discipline) |
| `td_refs` | string[] | optional | `td-NNN` rows in the tech-debt ledger this cluster maps to |
| `confidence` | enum | yes | `high` / `medium` / `low` — verifier's confidence in its own classification |
| `dedup_against` | string[] | optional | rework-worktree slugs already existing on disk this row deduplicates against |
| `notes` | string | optional | free-form sentence; never load-bearing |

`confidence: low` is the verifier's explicit way to register an objection in-band: when set, the headline must read `"Verifier uncertain — review classification"` and the main agent surfaces a one-liner to the user before creating the worktree.

## Considered Options

### Option A — Pure JSON file (`REWORK_MANIFEST.json`)

Pros: trivially parseable; no markdown-fragility risk; smallest schema surface.

Cons: opaque to the user; user must run `jq` to review the manifest before approving worktree creation; breaks the conversation-as-interface principle (user can't scan a file the system is acting on).

Rejected: the human-in-the-loop step is core to the feature design (`user opens a fresh Claude Code session per worktree`). A file the user can't read at-a-glance violates the contract.

### Option B — Pure markdown table

Pros: maximally human-readable; conforms to existing `.md`-everywhere convention.

Cons: parsing fragility (escapes in `Headline`, multi-line `notes`, schema drift between rows); idempotency dedup requires column-by-column comparison; adding optional fields requires a column add (high cost to evolve).

Rejected: parsing fragility is the dominant risk — the main agent is an LLM, but the contract should be hard-to-misuse, not LLM-tolerated.

### Option C — Markdown table + one top-level JSON array

Pros: human-scannable + parseable; single block; conventional.

Cons: top-level array means a partial-write or single-row corruption invalidates the whole file; row IDs are not visually anchored to their block (the user reads "row 3" but the JSON shows them all together at the bottom); diffs collapse multi-row changes into one block.

Rejected: per-row blocks (Option D) preserves the same benefits with cleaner failure semantics and diffability.

### Option D — Markdown table + per-row fenced JSON blocks (chosen)

Pros: each row reads top-to-bottom (table-row → JSON-block); diffs are per-row; partial writes localize damage; user can read or skim either layer.

Cons: format is slightly bespoke; producers must keep the two halves in sync (mitigated: verifier renders the table FROM the JSON blocks, not the other way around — single source of truth in the JSON).

**Chosen** — best Bloch trade: minimal surface area (one file, not two), hard-to-misuse (table can never drift from JSON because table is rendered from JSON), names matter (the JSON keys are the interface).

## Consequences

**Positive:**
- Idempotency: `id` is a hash of report-id + cluster signature, so re-verify produces the same row, and `dedup_against` lets the verifier downgrade a re-emission to a no-op when a matching worktree already exists.
- The verifier's classification confidence becomes a first-class field (`confidence: low`) rather than buried in `notes` — Register Objection compatibility.
- Future evolution: optional fields (`td_refs`, `dedup_against`, `notes`) can be added without table-column changes.

**Negative:**
- Verifier must implement table-from-JSON rendering (one helper function).
- Two readers exist in the codebase (user reads table; main agent reads JSON blocks). A test must enforce the table is in-sync with the JSON.

**Mitigation:**
- A self-check phase at verifier write-time renders the table from the JSON immediately, then re-parses it to confirm round-trip. Fail fast (write-time) is the Bloch path.
