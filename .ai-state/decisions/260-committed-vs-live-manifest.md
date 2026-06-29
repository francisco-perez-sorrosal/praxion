---
id: dec-260
title: Split the doc manifest into a committed-static durable index and a live .ai-work/ dimension
status: accepted
category: architectural
date: 2026-06-29
summary: Exclude volatile .ai-work/ from the committed doc_manifest.yaml (durable surfaces only), add a content-aware write, and wire a finalize-time regen — the live .ai-work/ dimension is owned by the dashboard's runtime workshops discovery, not the committed manifest.
tags: [doc-manifest, build-doc-manifest, finalize-chain, artifact-registry, determinism, dashboard, r12b]
made_by: agent
agent_type: systems-architect
branch: r12b-manifest-volatile-split
pipeline_tier: standard
affected_files:
  - scripts/build_doc_manifest.py
  - scripts/finalize_chain.sh
  - scripts/test_artifact_registry.py
  - scripts/test_build_doc_manifest.py
  - scripts/test_finalize_chain.py
  - .ai-state/doc_manifest.yaml
  - scripts/artifact_registry.py
  - scripts/CLAUDE.md
  - .ai-state/DESIGN.md
  - docs/architecture.md
dissent: Removing build_doc_manifest's registry read undoes dec-256/R18's "first reader" down-payment; if dec-259's clean_work_safety reader were later removed, the registry would revert to drift-checked-only and the spine principle would lose all live readers.
---

# Split the doc manifest into a committed-static durable index and a live `.ai-work/` dimension

## Context

The committed `.ai-state/doc_manifest.yaml` indexes volatile, gitignored `.ai-work/` state. `build_doc_manifest.py` walks **every** subdirectory of `.ai-work/` (no active-slug filter) and emits a surface per canonical pipeline artifact, grouping them into an `In-flight pipeline · transient` nav group. Because `.ai-work/` is gitignored but the manifest is committed, the manifest's `.ai-work/` content is a function of whatever transient local pipeline state happened to exist at generation time. Clinching evidence (orchestrator-captured in this worktree): a fresh regen yields **2** `.ai-work/` entries while the committed manifest carries **61** — proof the `.ai-work/` content churns with local state, not committed inputs.

This is the real blocker the R12b deferral (analysis §0.1) understated: §0.1 blamed only `generated_at` churn, but the deeper non-determinism is the volatile `.ai-work/` walk. R12b ("auto-regen the doc manifest") cannot be done safely until the volatile dimension is separated from the committed artifact.

Prior decisions in scope:
- **dec-251** — grew the artifact registry into a declarative production-gate spine (`production_gate` / `cleanup_policy` populated-not-projected), carrying a "populated but not read" dissent.
- **dec-256** (R18) — wired `build_doc_manifest._AI_WORK_FILES = dashboard_artifacts_ordered()`, calling it "the first consumer that **reads** the spine," explicitly to discharge dec-251's populated-not-read dissent; also added the `detection_gate` field and reclassified three rows.
- **dec-259** — wired `clean_work_safety` to read the registry's `cleanup_policy`, re-affirming the declarative-spine bet and discharging dec-256's reversal trigger.

Research (`RESEARCH_FINDINGS.md`) confirmed the three load-bearing assumptions: (A1) the manifest's `.ai-work/` entries are redundant — the dashboard's `workshops.ts` reads `.ai-work/` LIVE; the only committed-manifest consumer of them is a decorative, permanently-stale docs-nav group; (A2) the finalize chain is the correct regen home; (A3) the content-aware comparison already exists in the `--check` path.

## Decision

Reframe the committed `doc_manifest.yaml` as a **static index of durable surfaces only** (`docs/` + `.ai-state/` canonical files, finalized `dec-NNN` ADRs, specs, reports, root surfaces, API specs), and make its regeneration automatic and churn-free:

1. **Exclude `.ai-work/`** — remove the `.ai-work/` walk and the `_build_groups` `transient`/`pipeline-state` branch from `build_doc_manifest.py`. The committed manifest emits zero `.ai-work/` surfaces. The **live** `.ai-work/` dimension is owned entirely by the dashboard's runtime workshops view (`workshops.ts` reads the filesystem live; `files.ts:CANONICAL_WORKSHOP_ARTIFACTS` is its registry-checked contract).
2. **Content-aware write** — extract a shared `_strip_generated_at` helper (from the existing `--check` comparison) and skip `write_text` when the new manifest equals the existing one modulo `generated_at`. A no-op regen produces no diff.
3. **Finalize-time regen** — invoke `build_doc_manifest --root <root>` in `finalize_chain.sh`'s `_finalize_chain_run_on_main`, AFTER `finalize_adrs.py` and `finalize_tech_debt_ledger.py` (so it indexes the `dec-NNN` renames and ledger migrations finalize itself makes — a pre-commit gate runs too early), and ONLY when `.ai-state/doc_manifest.yaml` already exists (so projects that never opted in are not surprised by a new committed file). The regen is left unstaged and lands in the orchestrator's convergence commit, exactly like `DECISIONS_INDEX`.
4. **Drift-gate Option A** — remove `_AI_WORK_FILES`, the `from artifact_registry import dashboard_artifacts_ordered` import, and the three `bdm._AI_WORK_FILES` assertions; the `files.ts ↔ registry` live-discovery contract (`test_dashboard_workshop_matches_registry_dashboard_set`) is retained, plus a new behavioral `tmp_path` test asserting zero `.ai-work/` surfaces.

**Relationship to dec-256/R18 (no supersession).** This removes the `build_doc_manifest → registry` read edge R18 introduced — but it does **not** regress dec-256's registry-as-read-source principle. That read existed *only* to walk `.ai-work/` for the committed manifest (the volatile dimension being removed). The registry's `dashboard=True` projection still governs the dashboard's live `.ai-work/` discovery via `files.ts`, and **dec-259's `clean_work_safety` reader independently preserves the "registry is genuinely read, not just drift-checked" property**. So this is a *coherence improvement* — the `.ai-work/` read moves to where `.ai-work/` actually lives (live runtime discovery) — not a backslide to drift-checked-only. The dec-256 relationship is recorded here in prose; no `supersedes`/`re_affirms` frontmatter link and no status flip, because this ADR's primary nature is a new decision (the volatile split), not a re-affirmation, and only one clause of dec-256 (the build_doc_manifest reader edge) is materially affected while its core stands.

**F11 disposition.** Sentinel F11 (manifest-staleness WARN) is retained at WARN as a belt-and-suspenders backstop. It already scopes its `git log` to `docs/ .ai-state/` (correct post-change) and now catches exactly what auto-regen cannot: `--no-verify` bypass, hook failure (e.g. PyYAML absent in a hook env), and direct hook-less commits. Downgrading to INFO would weaken a backstop that matters *more* now that auto-regen creates a freshness expectation. No `agents/sentinel.md` edit required.

## Considered Options

### Option 1 — Exclude `.ai-work/` entirely (chosen)

Committed manifest = durable surfaces only; live `.ai-work/` owned by the dashboard runtime.

- **Pros:** committed manifest is deterministic modulo `generated_at`; churn eliminated; the stale 61-entry snapshot stops being committed; producer sheds dead registry coupling; matches the existing "live state is read live" pattern (`workshops.ts`).
- **Cons:** the docs-nav "In-flight pipeline · transient" group disappears (stale-by-design; the workshops view is the real live surface); removes dec-256/R18's reader edge.

### Option 2 — Active-slug filter

Keep `_AI_WORK_FILES`; walk only the currently-active slug's `.ai-work/` artifacts into the committed manifest.

- **Pros:** preserves the docs-nav in-flight group; keeps the registry reader edge intact.
- **Cons:** the committed manifest still carries gitignored transient state that varies per pipeline (the active slug changes every run) → the same §0.1 non-determinism. Does not solve the real bug. A committed artifact and a volatile dimension are fundamentally incompatible.

### Option B (drift gate) — Keep `_AI_WORK_FILES` as a documented dead constant

Retain the constant + import, comment it "registry contract for workshops, not used in walk."

- **Pros:** fewer test deletions.
- **Cons:** dead code; `test_doc_manifest_and_dashboard_agree` becomes semantically misleading (asserts the manifest agrees with the dashboard on a `.ai-work/` list the manifest no longer indexes). Rejected in favor of Option A.

## Consequences

**Positive:**
- The committed manifest is a deterministic function of `docs/` + `.ai-state/`; no per-pipeline churn (HG4).
- Auto-regen wired at finalize keeps it fresh as durable surfaces change, including the `dec-NNN` renames finalize makes — closing R12b properly.
- The producer no longer imports the registry; the live `.ai-work/` concern is consolidated in the dashboard runtime where it belongs.
- Surgical downstream blast radius: the existence gate means onboarded projects without a manifest are untouched.

**Negative / accepted:**
- The dashboard `ManifestGroup.transient?: boolean` field and its nav conditional become dead-but-harmless (an unused optional field); cleanup deferred (not worth the dashboard build/test gate).
- The finalize regen depends on the hook environment having PyYAML; a bare hook `python3` warns non-blockingly and F11 backstops the resulting staleness.
- dec-256/R18's "first registry reader" edge is removed; the genuine-reader property now rests solely on dec-259's `clean_work_safety` reader (see `dissent:`).
- The registry's documented consumer count drops 4 → 3, requiring prose updates at six sites (registry docstring, drift-gate test docstring, `scripts/CLAUDE.md`, `DESIGN.md`, `docs/architecture.md`). The registry **data** is unchanged.

## Disconfirmation

- **Falsifier** — A manifest consumer that depends on `.ai-work/` surfaces for *correctness* (not the decorative docs-nav group) surfaces post-merge — e.g. an automated check or external tool parsing `doc_manifest.yaml` for pipeline-state entries. Research traced all consumers and found none; if one appears, it should be moved to live discovery, not have the walk restored.
- **Steelmanned runner-up** — Option 2 (active-slug filter): "Keep a single, current in-flight group in the committed docs nav so a reader of the committed manifest still sees live pipeline context, and keep the registry reader edge dec-256 paid for." The strongest case is continuity — nothing visibly disappears, and dec-256/R18 stays literally intact. It fails on the core bug: even one active slug is gitignored transient state in a committed file, so the manifest remains non-deterministic across pipelines; the continuity it preserves is precisely the stale-by-design artifact we are removing.
- **Reversal trigger** — If the dashboard later grows a genuine need to surface in-flight pipeline artifacts through the **committed** manifest (rather than live runtime discovery), revisit — but that need is better served by extending the live workshops view than by re-committing volatile state. Separately, if dec-259's `clean_work_safety` registry reader is ever removed, re-examine whether the registry has any remaining genuine reader before treating the spine principle as upheld.

## Prior Decision

This ADR does not supersede or re-affirm any prior decision via frontmatter. It removes the `build_doc_manifest → registry` read edge introduced by **dec-256** (R18) while leaving dec-256's core decision (the `detection_gate` field, the three reclassified rows, registry-as-read-source) intact. The "registry is genuinely read" property dec-256 established remains upheld by **dec-259** (`clean_work_safety` reads `cleanup_policy`). A future ADR would need to show that *all* genuine registry readers have been removed — leaving it drift-checked-only again — before the spine principle (dec-251 / dec-256 / dec-259) could be considered reversed.
