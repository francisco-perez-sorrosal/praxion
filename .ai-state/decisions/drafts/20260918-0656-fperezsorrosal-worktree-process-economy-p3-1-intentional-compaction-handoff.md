---
id: dec-draft-3695d2e9
title: "Intentional compaction: a Tier-3 phase-boundary handoff, a 500k-token harness band, and a SessionStart(compact) orientation restore"
status: proposed
category: architectural
date: 2026-09-18
summary: "Adds three components — commands/handoff.md, scripts/compose_handoff.py and hooks/inject_compaction_orientation.py — producing one new registered artifact (.ai-work/<slug>/HANDOFF.md) consumed by /resume-pipeline as Tier-3 orientation; the utilisation band is pinned at 500,000 tokens by CLAUDE_CODE_AUTO_COMPACT_WINDOW (fires on 7/21 measured main sessions, 0/297 subagents) and documented once in docs/context-economy.md; the restore fires on SessionStart(source=compact) — the documented additionalContext seam — injecting a role-neutral ≤1 KiB position-and-pointers block, while PostCompact, which has no decision control, is used only to record one compaction telemetry row."
tags: [process-economy, compaction, handoff, hooks, sessionstart, postcompact, artifact-registry, resume-pipeline, context-economy, utilisation-band]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p3-1
pipeline_tier: standard
affected_files:
  - hooks/hooks.json
  - hooks/precompact_state.py
  - hooks/capture_session.py
  - scripts/artifact_registry.py
  - commands/resume-pipeline.md
  - .claude/settings.json
  - skills/hook-crafting/references/event-reference.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/references/artifact-inventory.md
  - .ai-state/DESIGN.md
affected_reqs: [REQ-01, REQ-03, REQ-04, REQ-05, REQ-05b, REQ-06, REQ-08]
dissent: "The restore's delivery is documented but still unobserved: SessionStart is on the harness's additionalContext supported-event list, yet no compaction has ever occurred in 21 main sessions or 297 subagents, so the seam has never run in this repo. The design ships behind a live-dogfood acceptance criterion rather than deferring; a second, smaller objection is that keeping PostCompact for a telemetry row adds a registration whose value depends on a band that may never fire."
---

# Intentional compaction: a Tier-3 phase-boundary handoff, a 50% harness-enforced band, and a 1 KiB PostCompact restore

Activation: fired — structural (≈15 files; hooks + scripts + commands + knowledge/docs) + novelty (no precedent for
intentional compaction in this repo); lens set = Developer, Test, Operations, Simplicity, Performance, Testability
(Security inspected and dismissed: no new trust boundary, secret, or network call); convergence = stable. Tier-B
cross-model challenge does not fire: not security, not one-way-door, not user-visible-breaking — the whole change
reverts by deleting files and one `hooks.json` block.

## Context

Roadmap item P3.1 named Praxion's highest-leverage under-build: it writes every artifact a fresh-window handoff
practice needs and never uses them to reset a window. The measurement pass
(`.ai-work/process-economy-p3-1/BASELINE.md`, 21 main sessions / 297 subagent transcripts) both confirmed and narrowed
the premise:

- **No compaction has ever occurred** — 0 `isCompactSummary` rows in either corpus, on 1M windows. The existing
  `PreCompact` snapshot (`hooks/precompact_state.py` → `.ai-work/PIPELINE_STATE.md`) has therefore never had a reader.
- **Subagents already start fresh** (the pointer return contract). The window that never resets is the
  *orchestrator's*: it spawns implementers at p50 318k, the verifier at p50 377k, and ends at p50 ≈420k, with 48% of
  its visible content being tool results (81% of those Bash).
- **No hook or agent can read its own utilisation.** A prose "hand off at 50%" is structurally unenforceable; the only
  enforcement surfaces are the harness's autocompact controls and an in-window turn/step budget that no mechanism
  reads.

Two harness contracts the first draft of this decision assumed were verified against the live documentation (fetched
2026-09-18 by the orchestrator via `curl`) **before** implementation, and one of them was falsified: `PostCompact`
carries **no decision control and no `additionalContext`** (`hooks.md:1056`; its stdin does carry `trigger` and
`compact_summary`, `hooks.md:3093`), while `SessionStart` honours `additionalContext` (`hooks.md:1055`) and fires with
`source: "compact"` after auto *and* manual compaction (`hooks.md:310, 1133, 1152`). The autocompact surface likewise
has two controls, not one: a lower-only percentage `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` that explicitly applies to main
conversations and subagents (`env-vars.md:196`), and an absolute-token `CLAUDE_CODE_AUTO_COMPACT_WINDOW`
(100,000–1,000,000, capped at the model's context window) that takes precedence over `/autocompact`, `--autocompact`
and the `autoCompactWindow` setting (`env-vars.md:214`; `model-config.md:683–715`).
- The largest subagent peak ever recorded is 439,364 tokens (44% of a 1M window), so any band at or above 50% is
  invisible to every agent type.

The design question was therefore not "should we hand off" but: at what value does a band bite without damaging
windows that already reset, what shape must a handoff artifact have to be resumable *and* untrusted, and what should a
`PostCompact` hook actually inject given Praxion's own analysis measured `PIPELINE_STATE.md` at ~9,600 tokens of
mostly-stale multi-slug snapshot.

## Decision

Three components are added and one existing consumer is extended.

1. **`commands/handoff.md`** (new command, `disable-model-invocation: true`) over **`scripts/compose_handoff.py`**
   (new deterministic engine, stdlib, importing the already-pure `reconcile_pipeline_state.reconcile()`), producing
   **`.ai-work/<slug>/HANDOFF.md`** — one file per slug, rewritten in place at each boundary, with a fixed seven-section
   schema (§0 Preflight, §1 State, §2 Next action, §3 Decisions & assumptions, §4 Corrections in force, §5 Do not
   re-inherit, §6 Start here) and a closed `boundary` enum. The mechanical sections are computed from disk and git; the
   judgement sections are the orchestrator's existing phase-transition checkpoint digest, so the practice invents no
   new content. §4–§5 are carried forward verbatim when the boundary advances; an unparseable existing handoff is
   refused, never overwritten.
2. **`hooks/inject_compaction_orientation.py`** (new hook, registered on **`SessionStart` with `matcher: "compact"`**
   plus an in-script `source` check) injecting a **role-neutral ≤1,024-byte** `additionalContext` block: task slug,
   current `WIP.md` step, next action, and the pointer set to re-read on demand — position and pointers, never the
   snapshot's content. One slug is elaborated (newest `WIP.md` mtime); the block carries no orchestration verb so the
   same text is correct in a main window and in a subagent window; every failure path consumes stdin, prints nothing,
   and exits 0. It is registered as its own matcher-scoped block, not appended to the nine-script `SessionStart` chain.
   **`PostCompact` is kept for the one thing it can do**: a branch in `hooks/capture_session.py` appends a single
   `compaction` observation row carrying `trigger` and `len(compact_summary)` — never the summary body. That row is the
   first first-class signal that a compaction happened at all; `BASELINE.md` had to establish "it never has" by
   scraping 318 transcripts. `skills/hook-crafting/references/event-reference.md:88`, which described `PostCompact` as
   "State restoration after compression" and seeded the falsified assumption, is corrected in the same change.
3. **The band is 500,000 tokens**, carried by **`CLAUDE_CODE_AUTO_COMPACT_WINDOW=500000`** as an `env` entry in
   Praxion's own `.claude/settings.json` (dogfood; no prose in the enforcement loop) and explained **once** in
   `docs/context-economy.md` together with its precedence chain (env var > `/autocompact` > `--autocompact` >
   `autoCompactWindow`, all capped at the model window). The absolute form is chosen over the verified percentage form
   precisely because a token threshold above a smaller model's window is **inert** while a percentage rescales — 50% of
   a 200k window is 100k, which would compact subagents mid-step. It is still not propagated into managed projects by
   onboarding, for a changed reason: propagation is now harmless rather than harmful, but harmless is not justified
   without evidence, and the onboarding contract is out of this task's scope. The band is the tail backstop; the
   phase-boundary handoff is the mechanism.
4. **`HANDOFF.md` is Tier-3 evidence.** `/resume-pipeline` gains one step — read the handoff for orientation, then run
   the reconciler and act only on its verdicts. Where the handoff disagrees with a Tier-1 verdict, the verdict wins and
   the disagreement is reported. The artifact is registered in `scripts/artifact_registry.py`
   (`snapshot=True`, `dashboard=False`, `production_gate="script:compose_handoff.py"`, `cleanup_policy="delete"`),
   added to `precompact_state.PIPELINE_DOCS`, and listed in the artifact-inventory reference.

The guard is `scripts/context_baseline.py` (promoted from the pipeline's `baseline/` scripts): machine-local, stdlib,
read-only, `--json`, per agent type per pipeline slug, with `--band <pct>` reporting the counterfactual — how many past
windows the band would have compacted, split main vs. per agent type.

## Considered Options

| Axis | Option | Verdict |
|---|---|---|
| Band value | ≈200k — reaches subagents | Rejected: compacting a subagent trades a solved problem (they start fresh) for an expensive one (a compacted implementer loses its working set); would fire on ~35% of implementers and every architect |
| Band value | **500,000 tokens (≈50% of the 1M window)** | **Chosen**: fires on 7/21 main sessions, 0/297 subagents; targets the only window that never resets |
| Band value | `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` (clamp every window to 200k) | Rejected: indiscriminate — solves an orchestrator problem by compacting 87 implementer windows routinely |
| Band mechanism | `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (percentage, lower-only, explicitly main + subagents) | Verified to exist, rejected as the instrument: a percentage rescales with the model window, so one value cannot be safe on both 1M and 200k models |
| Band mechanism | **`CLAUDE_CODE_AUTO_COMPACT_WINDOW` (absolute tokens, capped at the model window)** | **Chosen**: same counterfactual, and above-window values are inert rather than aggressive; takes documented precedence over the interactive and settings forms |
| Band mechanism | `/autocompact 500k` / `--autocompact` | Rejected as the carrier: per-user and per-launch, unshareable, and overridden by the env var anyway — retained in the doc as the per-session escape hatch |
| Band placement | env-documented only / shipped `settings.json` only | Rejected: the first leaves enforcement to the operator's memory; the second leaves the value unexplained. Chosen: **both**, with distinct roles (settings = enforcement, doc = single explanation) |
| Handoff | Prose-only section in `coordination-details.md` | Rejected: unprovable (AC-1 needs a fixture pipeline), and re-types the mechanical half into the window it is meant to close |
| Handoff | **Composer script + thin command** | **Chosen**: testable, cannot drift from the reconciler (it *is* the reconciler), 0 listing tokens |
| Handoff | `--write-handoff` flag on `/resume-pipeline` | Rejected: makes one command the writer and reader of the same artifact and overloads `--dry-run` |
| Handoff shape | One file per boundary (as the hand-written prototypes did) | Rejected: a second file is a second source of truth about position — the defect the reconciler exists to correct |
| Restore | Inject `PIPELINE_STATE.md` as-is (the roadmap's literal wording) | Rejected on measured cost (~9,600 tokens, mostly stale slugs) |
| Restore | **≤1 KiB position + pointers** | **Chosen**: the files survive compaction; only orientation is lost |
| Restore | Extend `PreCompact` only, keep relying on CLAUDE.md prose | Rejected: leaves the mechanism prose-only, which is the under-build the item exists to close |
| Restore event | `PostCompact` (the roadmap's, the brief's and this decision's first assumption) | **Falsified by the live docs**: no decision control, no `additionalContext` |
| Restore event | **`SessionStart` with `matcher: "compact"` + in-script `source` check** | **Chosen**: the documented `additionalContext` seam, and it fires after manual and auto compaction alike |
| `PostCompact` | Drop it from the design | Rejected: it is the only event that reports a compaction happened, with its trigger — keeping it as a one-row telemetry sink makes the band's firing observable for the first time |
| `PreCompact` snapshot | Extend with a `TEST_RESULTS.md` tail (the brief's suggestion) | Rejected on the independent context review's evidence: the shared `_head(30)` surfaces the *earliest* step of a multi-run file, so a head snapshot restores the wrong step, and a `_tail()` sibling for one file is a second truncation strategy. `PIPELINE_DOCS` gains only `HANDOFF.md` |
| Subagent restore | Branch on an undocumented payload field | Rejected: an unverifiable branch. Chosen: one role-neutral block, correct in both contexts |
| Canonical prose | Trim the shipped `Compaction Guidance` block now | Rejected this pipeline: it is the only live restore path until the hook's delivery is evidenced; trimming is a follow-up gated on that evidence |

## Consequences

**Positive.** The orchestrator's window gains a harness-enforced ceiling and a documented reset ritual whose mechanical
half is computed rather than retyped. Compaction becomes observable for the first time — one WAL row per event, with
its trigger. A fresh window can
resume from one artifact plus the slug, with ground truth — not the artifact — deciding what is done. Every number in
the design is reproducible by one script, so the after-state is measurable with the instrument that measured the
before-state. Always-loaded cost is ≈0: the command's description is excluded from the listing surface by
`disable-model-invocation: true`, and every prose edit lands in on-demand references, not in `rules/` or a `CLAUDE.md`.

**Negative.** Three new components, one new artifact and two hook registrations to maintain, against a roadmap line
that claimed "zero new artifacts, zero new machinery" — the claim does not survive contact with the requirement that
the handoff be testable. The band does nothing for 14 of 21 measured sessions by design. The in-window cadence (one
window per phase; ~8 spawn-cycles inside a long implementation phase) is prose and therefore unenforceable —
deliberately not a tier spawn budget, which is a separate, user-gated Phase-2 item. And while the restore's event
contract is now *documented*, it remains *unobserved* in this repo, because nothing has ever compacted here (see
Disconfirmation).

## Disconfirmation

**Falsifier.** Name the component: `hooks/inject_compaction_orientation.py`, `commands/handoff.md` and
`scripts/compose_handoff.py` are added; `.ai-work/<slug>/HANDOFF.md` is a new artifact with a named producer and a named
consumer; `/resume-pipeline` gains a consumption step; `hooks/capture_session.py` gains a new event branch. That is what
makes this `architectural` rather than `behavioral`. The decision is **wrong** if either of two things is observed:
(a) the live dogfood shows no orientation block arriving on `SessionStart(source=compact)` despite the documented
contract — then the restore half is unbuildable as designed and should collapse to the `PreCompact` snapshot plus the
existing prose, with the telemetry row kept; (b) three consecutive pipelines run with the handoff available and the
orchestrator's context at spawn does **not** drop below the 250k p50 target — then the handoff is ceremony, not
economy, and its command should be retired rather than kept as an unused surface.

One assumption in this decision's own first draft has already been falsified this way, before any code was written:
`PostCompact` was assumed to be the restore seam by the roadmap, the brief and the draft alike, and the live docs say
otherwise. The design absorbed the correction by moving the seam rather than by weakening the claim — which is the
behaviour the falsifier above is asking for on the remaining two.

**Steelmanned runner-up** (argued as if it were the recommendation). *Do not build a handoff artifact at all. Set the
band to 20% and let the harness compact everything, orchestrator and subagents alike.* The case is strong and mostly
evidence-backed: compaction is a first-party summarizer that already preserves the conversation's own reasoning, it
needs no new component, no new artifact, no registry row, and no operator ritual — and rituals that depend on an
operator remembering to run a command at a boundary are exactly the kind of prose obligation this roadmap phase exists
to delete. The `PreCompact` snapshot plus the existing CLAUDE.md guidance already tell the agent what to preserve, so
the marginal value of a seventh hand-authored document is unproven, while its marginal cost — a command, a script, a
registry row, an inventory row, two reference edits and a test suite — is certain. On this account P3.1 reduces to one
`settings.json` line, and the 439,364-token subagent outlier is a feature of the argument, not a bug: if a window is
large enough to hurt, let the harness shrink it. What defeats it is narrower than it looks: a compacted implementer
does not merely lose prose, it loses the *file-level working set* of a step it was mid-way through, and the
completion-handshake machinery already exists precisely because agents that lose state mid-step produce
verified-complete claims that are false. The runner-up's cost lands on the one population that already resets for
free, to fix a window it does not touch. But it wins outright on simplicity, and if the dogfood in (a) above fails, it
is the design to fall back to — not a patched version of this one. Note that the event correction *strengthens* the
runner-up's simplicity case, since the "one settings line" it argues for is now one **token-denominated** settings line
whose failure mode on any other model is inertness rather than harm.

**Reversal trigger.** Revisit when any of: (1) the dogfood records no orientation block on
`SessionStart(source=compact)`; (2) `/handoff` is invoked in fewer than 2 of the next 4 Standard pipelines (an unused
command is a retirement candidate, not a default); (3) the `compaction` telemetry rows show the band firing at a
threshold other than 500,000 (something in the precedence chain is overriding the env var) — or show it never firing
across three pipelines whose peaks `context_baseline.py` puts above 500k (the enforcement is not reaching the session);
(4) the harness ships a programmatic utilisation read, which would make the prose in-window cadence enforceable and
this decision's division of labour obsolete.
