---
id: dec-255
title: Single living IDEA_LEDGER.md, retiring the per-run timestamped copy-forward scheme
status: accepted
category: behavioral
date: 2026-06-27
summary: promethean updates one living .ai-state/idea_ledgers/IDEA_LEDGER.md in place instead of emitting a new timestamped file that copies forward all prior entries.
tags: [idea-ledger, promethean, producer-contract, waste-pruning, copy-forward]
made_by: user
branch: wave4a-waste-pruning
pipeline_tier: standard
affected_files:
  - agents/promethean.md
  - .ai-state/idea_ledgers/IDEA_LEDGER.md
  - scripts/build_doc_manifest.py
  - skills/software-planning/references/artifact-inventory.md
  - rules/swe/agent-intermediate-documents.md
---

## Context

`promethean` produced one `IDEA_LEDGER_<timestamp>.md` per run, each **carrying forward all prior
entries** from the previous file. The process-flow analysis (finding C1 / R7) found 7 files where 6
were fully obsolete copy-forwards: every run duplicated the prior ledger, then either inlined or
pointed back to it. The live store accreted near-identical files whose only durable delta was the
newest run's additions — pure copy-forward waste, and a confusing "which file is current?" surface.

## Decision

**One living `.ai-state/idea_ledgers/IDEA_LEDGER.md`, updated in place.** `promethean` reads it,
adds the run's new clusters under **Pending** (and Discarded / Future Paths as needed), and writes
back to the **same file** — no new timestamped per-run file. The migration promoted the newest
(`IDEA_LEDGER_2026-06-05`) to `IDEA_LEDGER.md`; the six older files were removed from the working
tree (retained in git history); the in-file pointers that named a `IDEA_LEDGER_<timestamp>.md`
resolve to git history.

Two `build_doc_manifest.py` discovery patterns assumed the timestamp suffix
(`IDEA_LEDGER_*.md` glob; `^IDEA_LEDGER_.*` renderer regex). Both were widened to
`IDEA_LEDGER*.md` / `^IDEA_LEDGER.*` so the living file is discovered while any legacy timestamped
file still matches during transition.

## Considered Options

### Option A — Single living file, in-place update (CHOSEN)

- **Pros:** ends the copy-forward duplication; one unambiguous current file; the full history is in
  git; the shipped-artifact-isolation gate (which forbids citing a specific `IDEA_LEDGER_<date>`)
  is satisfied naturally by the date-less name.
- **Cons:** the single file grows over time and must be curated by `promethean` (prune shipped
  ideas) rather than archived per run; git history, not a filename timestamp, carries per-run
  provenance.

### Option B — Keep timestamped per-run with copy-forward (status quo)

- **Pros:** each run is a self-dated snapshot.
- **Cons:** the copy-forward waste the analysis flagged; 6 of 7 files obsolete; ambiguous current
  file. Rejected.

### Option C — Timestamped per-run, no copy-forward (each file only new ideas)

- **Pros:** no duplication; each file is a clean per-run delta.
- **Cons:** no single consolidated view — a reader must stitch N files to see the standing backlog;
  trades copy-forward waste for read-time fragmentation. Rejected in favour of the living file.

## Consequences

**Positive:**
- The idea-ledger directory holds one file; no per-run accretion; the standing backlog reads in one place.
- `promethean`'s contract is simpler (read-update-write one path) and its three doc surfaces agree.

**Negative / costs:**
- The living file needs occasional curation (drop shipped ideas) — a `promethean` responsibility,
  not an automated one; left uncurated it accumulates stale pending entries.
- Per-run provenance moves from the filename to git history; a reader wanting "what did the
  2026-04-30 run propose?" consults `git log`, not a live file.
