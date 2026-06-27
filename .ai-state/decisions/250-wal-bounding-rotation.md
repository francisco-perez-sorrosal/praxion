---
id: dec-250
title: Bound the recovery WAL — best-effort rotate-and-archive to a gitignored segment + windowed cross-boundary read
status: accepted
category: architectural
date: 2026-06-26
summary: Implement the WAL size bound dec-248 assumed already existed — best-effort in-lock rotate-and-archive of observations.jsonl to a gitignored observations.jsonl.1, and a 7-day windowed reconciler read spanning the active file plus the one archived segment, so recovery stays correct and bounded across a rotation boundary.
tags: [pipeline, recovery, wal, observability, rotation, reconciliation, dec-248]
made_by: agent
agent_type: systems-architect
branch: wave2-criticals
pipeline_tier: standard
re_affirms: dec-248
affected_files:
  - hooks/_hook_utils.py
  - hooks/capture_memory.py
  - hooks/capture_session.py
  - scripts/reconcile_pipeline_state.py
  - .gitignore
  - .ai-state/DESIGN.md
dissent: A head-truncate-in-place design keeps the whole WAL in one file and needs no segment-stitching in the reader — strictly simpler on the read side; it loses here only because truncating a 10 MiB file under the append lock on every overflow is an O(size) rewrite on the hot hook path and permanently discards the truncated rows, whereas rotate-and-archive is an O(1) atomic rename whose archived rows are still in git history.
---

## Context

`dec-248` made `.ai-state/observations.jsonl` the recovery WAL (the Tier-2 localization journal for pipeline truncation recovery) and, in its Considered-Options-A rationale, asserted the WAL was "already hardened (fcntl locking, merge driver, toggle gate, **auto-rotation**)." The auto-rotation property **did not exist** — neither `hooks/capture_memory.py` nor `hooks/capture_session.py` contained any size check or rotation logic (the Wave-1 honesty sweep already corrected the *documentation* claim in `.ai-state/DESIGN.md` and flagged dec-248; this ADR supplies the missing *mechanism*). The file was 6.8 MB and growing, read **whole** on every recovery by `reconcile_pipeline_state.py:_read_wal()`. A future architect evaluating recovery reliability would trust a safety property that was not there, and recovery cost grew unbounded with the WAL.

One property keeps the read side simple: **rotation only relocates rows out of the working-tree active file — it never discards them.** Recovery durability rests on the local active file plus the archived `.1` segment within the reconciler's 7-day window. Rows already committed are also in git history, but that is best-effort — it depends on the commit cadence outpacing 10 MiB of growth between commits, not a per-row guarantee: a recent uncommitted tail can live only in the working tree, and after a rotation only in the gitignored `.1`.

## Decision

Implement the bound dec-248 assumed, in two complementary halves:

1. **Best-effort rotate-and-archive in the append path.** Move the duplicated `_append_observation` into `hooks/_hook_utils.py` and add, **inside the existing fcntl-locked critical section**, a size check: when `observations.jsonl` ≥ `OBSERVATIONS_MAX_BYTES` (10 MiB), `os.replace()` it to `observations.jsonl.1` (atomic rename; the next append creates a fresh active file). Any `OSError` is swallowed — rotation never blocks or raises, preserving the async-hook and graceful-no-`.ai-state` guarantees. A single archived segment is kept; the next rotation overwrites it.
2. **The archived segment is gitignored.** `.ai-state/observations.jsonl.1` is added to `.gitignore`. It never enters git and never touches the `merge=observations-jsonl` driver (which is keyed to the tracked active path only). No `.gitattributes` change, no second merge driver. The reconciler reads `.1` locally within its 7-day window, so gitignoring it costs nothing for recovery: the rows that matter are the recent local ones, and a loss that wipes `.1` (fresh clone, `git clean -x`) has already wiped the local `.ai-work/` pipeline state those hints would recover. Rows committed before rotation also remain in git history; rows not yet committed were never git-durable, with or without rotation.
3. **Windowed cross-boundary read in the reconciler.** `_read_wal` reads the active file **and** `observations.jsonl.1` when the segment's mtime is within the window, unions the rows, and filters by `timestamp >= now − max_age_days` (default 7, CLI `--max-age-days`). The slug-less backward correlation in `_correlate_agents` is untouched — it operates on the unioned row list, so a rotation that bisects an agent's lifetime (writes in `.1`, `agent_stop` in the active file) still joins.

## Considered Options

### Option A — Rotate-and-archive to a gitignored single segment + 2-file windowed read (CHOSEN)

- **Pros:** O(1) atomic rename off the hot append path; preserves rotated data; keeps the active file small so git diffs and the merge driver stay cheap; the gitignored segment dissolves the merge-driver-interaction question entirely; the windowed read bounds recovery cost unconditionally and stays correct across a boundary. Honors Simplicity First and Root-Causes-Over-Workarounds (the duplication is removed, not worked around).
- **Cons:** the reader must stitch 2 files (active + `.1`); a merge between a rotated and an un-rotated branch can transiently re-inflate the active file via the driver's union (correct, self-healing on the next append). Both accepted.

### Option B — Head-truncate-in-place (the steelmanned runner-up)

- **Pros:** keeps the entire WAL in one file → the reconciler needs no segment-stitching at all; a single-file reader is strictly simpler. For a team that values a one-file invariant over append-path cost, this is defensible.
- **Cons (why it loses):** truncating a 10 MiB file on overflow is a read-whole-file + rewrite under the append lock — an O(size) operation on the hot async-hook path the rotate design avoids with an O(1) rename. It **permanently discards** the truncated rows (rotate-and-archive's rows survive in git history *and* a local `.1`). And the whole-file rewrite produces a large git diff every overflow, stressing the merge driver. Rejected against Simplicity First *on the hot path* and against data-preservation.

### Option C — git-track the archived segment

- **Pros:** `.1` would be shared across clones/worktrees.
- **Cons:** needs its own merge driver (or risks line-merge corruption), doubles the git footprint, and the rename shows as a delete+add. Pointless for recovery: the reconciler reads `.1` **locally** within its window, so tracking it in git adds no recovery benefit (recovery is a local-working-tree operation) while duplicating state. Rejected.

## Consequences

**Positive:**
- The recovery safety property dec-248 depends on now actually exists; the Built claim in `DESIGN.md` becomes true.
- Recovery cost is bounded: the active file is ≤ ~10 MiB by the rotation bound, and the read is time-windowed across at most 2 files.
- Zero VCS-config change (no `.gitattributes`/merge-driver churn), so `/onboard-project` Phase 3 parity is preserved.
- The duplicated append helper is unified, removing a silent-drift hazard.

**Negative / costs:**
- The reconciler reads 2 files instead of 1 (bounded, mtime-pruned).
- The size bound is "eventually small on a linear history," not "never large": a merge with a long-un-rotated branch re-inflates the active file until the next append re-triggers rotation. The windowed read — not rotation — is what bounds recovery cost unconditionally.
- A `.gitignore` addition may need mirroring into the onboarding canonical block for downstream parity (flagged to the planner).
- *Durability scope — clarified by the 2026-06-26 Wave-1–3 audit-remediation pass.* This ADR originally framed the design around "every event is committed to git history before rotation can move it." That is a commit-cadence convention, not an enforced invariant — an external audit (`docs/independent-analysis/wave-1-3-external-audit.md`, EA-01) showed an uncommitted tail can rotate into the gitignored `.1`. The prose above now states the real guarantee (local active file + archived `.1` within the 7-day window). The **decision is unchanged** — only the over-strong durability rationale was corrected. The Reversal trigger (numbered segments / always-read-`.1`) already anticipated the sparse-commit case.

## Disconfirmation

- **Falsifier (what would make this wrong):** if rotation cadence were far faster than assumed — e.g., a WAL writing fast enough that two rotations occur *within* a 7-day recovery window — the single overwritten `.1` could drop an in-window row, and the design would need numbered segments (`.1`, `.2`, …) or a larger threshold. The guard is that at 10 MiB and the observed ~11K-events/month peak, a rotation period is months, ≫ the 7-day window. A measured rotation interval shorter than the window is the falsifier to watch.
- **Steelmanned runner-up (Option B, head-truncate-in-place):** the cheapest reader is the one that never stitches. A single-file WAL with periodic head-truncation keeps `_read_wal` exactly as it is today and removes an entire class of boundary-correctness reasoning. If append-path cost proved negligible (small files, rare overflow) and discarding old rows were acceptable (they are reconstructable from git), head-truncate would be the simpler whole-system choice.
- **Reversal trigger:** if recovery is observed missing current-session events *because* a rotation landed mid-session and the mtime-prune wrongly skipped `.1` (a window/clock edge), or if the re-inflation-on-merge proves to keep the active file persistently large in practice, revisit: either always read `.1` regardless of mtime, or move to numbered segments with an explicit retention count. Conversely, if a future harness bounds the WAL at the platform level, retire rotation and keep only the windowed read.

## Prior Decision

This ADR **re-affirms `dec-248`** — its reliability hierarchy, WAL-as-Tier-2-hint design, the deterministic reconciler, and auto-resume-with-audit are correct and **unchanged**. It does not supersede dec-248: no decision of dec-248 is reversed. What it corrects is a *factual error* in dec-248's Considered-Options-A rationale — the claim that the WAL already had "auto-rotation." That property never existed; this ADR supplies it, making dec-248's Tier-2 dependency actually safe. dec-248 stays `accepted` and gains this ADR in its `re_affirmed_by`. A future supersession of either would require evidence that windowed-rotate is the wrong shape (see Reversal trigger), not merely that the premise was once mis-stated.
