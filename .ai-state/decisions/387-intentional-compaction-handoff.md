---
id: dec-387
draft_id: dec-draft-3695d2e9
title: "The phase-boundary handoff is the mechanism: a Tier-3 HANDOFF.md with verbatim user constraints and a readiness gate, plus a SessionStart(compact) safety net — Praxion sets no utilisation band"
status: accepted
category: architectural
date: 2026-09-18
summary: "Adds three components — commands/handoff.md, scripts/compose_handoff.py and hooks/inject_compaction_orientation.py — producing one new registered artifact (.ai-work/<slug>/HANDOFF.md) consumed by /resume-pipeline as Tier-3 orientation, carrying the user's operating constraints verbatim across boundaries and refusing to compose while a spawn is in flight or the step's files are dirty (--force stamps readiness: overridden). Praxion sets NO compaction threshold (user decision, pre-mortem gate 2026-09-18): forcing compaction at a token count gambles the orchestrator's judgement state on the harness summary and does not solve context rot; the threshold stays the operator's, docs/context-economy.md carries the 250k-p50 target and the verified control names, and context_baseline.py --band is an analysis flag. The SessionStart(source=compact) hook is a safety net for compactions Praxion did not choose; PostCompact, which has no decision control, records one telemetry row."
tags: [process-economy, compaction, handoff, hooks, sessionstart, postcompact, artifact-registry, resume-pipeline, context-economy, utilisation-band]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p3-1
pipeline_tier: standard
affected_files:
  - commands/handoff.md
  - scripts/compose_handoff.py
  - scripts/_handoff_readiness.py
  - scripts/_handoff_inputs.py
  - scripts/test_compose_handoff.py
  - hooks/inject_compaction_orientation.py
  - hooks/test_inject_compaction_orientation.py
  - scripts/context_baseline.py
  - scripts/test_context_baseline.py
  - scripts/reconcile_pipeline_state.py
  - docs/context-economy.md
  - hooks/hooks.json
  - hooks/precompact_state.py
  - hooks/capture_session.py
  - scripts/artifact_registry.py
  - commands/resume-pipeline.md
  - skills/hook-crafting/references/event-reference.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/references/artifact-inventory.md
  - .ai-state/DESIGN.md
affected_reqs: [REQ-01, REQ-02, REQ-02b, REQ-03, REQ-04, REQ-05, REQ-05b, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10]
dissent: "With no Praxion-set threshold there is no mechanical backstop: the whole mechanism now depends on a human remembering to run /handoff at a boundary, and an orchestrator that never does behaves exactly as the measured baseline did. The design accepts this deliberately — the alternative moves an irreversible act away from the person who can see the status line — but low uptake, not delivery failure, is the most likely way this decision turns out wrong. Secondarily: the restore's delivery is documented (SessionStart honours additionalContext) yet still unobserved here, since nothing in this repo has ever compacted."
---

# Intentional compaction: a Tier-3 phase-boundary handoff with a readiness gate, a SessionStart(compact) safety net, and no Praxion-set band

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
   **`.ai-work/<slug>/HANDOFF.md`** — one file per slug, rewritten in place at each boundary, with a fixed
   eight-section schema (§0 Preflight, §1 State, §2 Next action, §3 Decisions & assumptions, **§4 Operating
   constraints from the user**, §5 Corrections in force, §6 Do not re-inherit, §7 Start here) and a closed `boundary`
   enum. The mechanical sections are computed from disk and git; the judgement sections are the orchestrator's existing
   phase-transition checkpoint digest, so the practice invents no new content. **§4–§6 are carried forward verbatim**
   when the boundary advances — §4 holds the user's standing ask-before list and session-scoped instructions, which
   exist nowhere else on disk and are exactly what a lost window loses. An unparseable existing handoff is refused,
   never overwritten.
   The composer is also a **readiness gate** (`ReadinessVerdict = Ready | Blocked(reasons) | Overridden(reasons)`): it
   refuses to write when the WAL shows an `agent_start` without its `agent_stop` for this session, or when
   `git status --porcelain` intersects the current step's declared `Files:`, or when the WAL is missing, unparseable
   or carries no `session_id`-bearing rows (`wal-unreadable`: a refusal gate that reports ready because it could not
   look is fail-open; added at light-review, 2026-09-18). `--force` overrides and stamps
   `readiness: overridden` into the header, so the next window learns it inherited a non-quiescent tree. A further
   proposed condition — a detached test suite still running — is **not adopted**: the `nohup` + done-file practice has
   no contracted path, so a gate checking it would be checking a file nobody is obliged to produce; the composer
   instead reports an advisory line when `dec-386`'s `.ai-work/<slug>/logs/step-<N>.log` was written in the last 60s.
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
3. **Praxion sets no utilisation band** (user decision at the pre-mortem gate, 2026-09-18 — this reverses the first two
   drafts of this ADR, which argued only about *which* control should carry a 500k threshold). No `env` entry, no
   `settings.json` edit, nothing propagated to managed projects. The rationale is the user's and is recorded because it
   overturns the design's own reasoning: forcing a compaction at a token count is not a Praxion event and does not
   solve context rot — at the moment of compaction the orchestrator's **judgement state** (the user's standing
   instructions, the corrections in force, the pending checkpoint decision, the spawns in flight) is handed to the
   harness summariser and gambled. The plan on disk survives; the stitches do not. The mechanism is therefore the
   orchestrator **preparing a handoff at a phase boundary when the session is long enough**, with item 1's guarantees
   strong enough that the next window continues without re-stitching. The trigger stays **human** — the operator reads
   the status line and picks the boundary — because no hook or agent can read its own utilisation, and a machine
   trigger on the wrong axis is worse than none.
   What ships instead: `docs/context-economy.md` carries the measured baseline, the **target** (orchestrator context at
   spawn below 250k p50 over the next three pipelines), and one paragraph stating that the threshold is the
   **operator's own to lower**, naming the four verified controls (`CLAUDE_CODE_AUTO_COMPACT_WINDOW`,
   `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `/autocompact`, `--autocompact`) so an operator who wants one sets it correctly.
   `scripts/context_baseline.py --band <tokens>` survives as the **analysis** flag that makes that choice informed.
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
| Band (any Praxion-set value) | ≈200k / 500,000 tokens / `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`, carried by `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `/autocompact` or `--autocompact` | **All rejected** (user, 2026-09-18). Each answers "when should the window be cut" when the question is "how does the next window inherit the judgement state". Compaction at a token count gambles the user's standing instructions, the corrections in force and the in-flight spawns on the harness summary — the plan survives, the stitches do not — and it moves an irreversible decision from the person watching the status line to the party that cannot read utilisation at all. Their verified names and semantics are retained **as documentation** for an operator lowering their own threshold |
| Band value, as analysis | 500,000 tokens as a **counterfactual** | **Retained** in `context_baseline.py --band` and in the doc: it would have compacted 7/21 main sessions and 0/297 subagents, which is how an operator weighs setting their own, and it anchors the 250k-p50 target |
| Continuity guarantee | Handoff carries pipeline learnings only (§3 digest, §5 corrections, §6 do-not-re-inherit) | Rejected as insufficient once the band was retired: nothing carried what the *user* had said, which is the half that dies with the window |
| Continuity guarantee | **Add §4 Operating constraints from the user, carried verbatim** | **Chosen**: the ask-before list and session-scoped instructions travel byte-for-byte across boundaries |
| Readiness | Compose whenever asked | Rejected: a handoff written over a half-finished state presents a false boundary with the authority of a generated document |
| Readiness | **Block on unstopped spawn or dirty step files; `--force` stamps `overridden`** | **Chosen**: two mechanically decidable conditions, each fixable by one operator action, with the override recorded in the artifact rather than in memory |
| Readiness | Report `ready` when the WAL cannot be read | **Rejected at light-review**: a gate whose purpose is refusal must fail closed; `wal-unreadable` is the third blocking reason, with the same `--force` override |
| Readiness | Also block on a running detached test suite | **Not adopted**: no contracted path for the done-file convention, so the check could never honestly fire; downgraded to an advisory line over `dec-386`'s canonical log path |
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

**Positive.** The orchestrator gains a reset ritual whose mechanical half is computed rather than retyped, and whose
judgement half now includes the user's own standing constraints — so a new window continues the work instead of
re-negotiating it. The ritual can refuse itself when the moment is not a boundary. Compaction becomes observable for
the first time — one WAL row per event, with its trigger. Praxion changes no setting and no environment variable, so
nothing here alters how any session behaves until an operator runs `/handoff`. A fresh window can
resume from one artifact plus the slug, with ground truth — not the artifact — deciding what is done. Every number in
the design is reproducible by one script, so the after-state is measurable with the instrument that measured the
before-state. Always-loaded cost is ≈0: the command's description is excluded from the listing surface by
`disable-model-invocation: true`, and every prose edit lands in on-demand references, not in `rules/` or a `CLAUDE.md`.

**Negative.** Three new components, one new artifact and two hook registrations to maintain, against a roadmap line
that claimed "zero new artifacts, zero new machinery" — the claim does not survive contact with the requirement that
the handoff be testable. **There is now no mechanical backstop at all**: an orchestrator that never runs `/handoff`
behaves exactly as before, and nothing in Praxion will stop it — that is the accepted cost of leaving an irreversible
act with the human, and it is the top row of the plan's risk table. The trigger heuristic (one window per phase; ~8
spawn-cycles inside a long implementation phase) is prose and unenforceable by construction — deliberately not a tier
spawn budget, which is a separate, user-gated Phase-2 item. `--force` can still produce a handoff over a
non-quiescent tree; the artifact records that, but a reader who ignores the header is not protected. And while the
restore's event contract is now *documented*, it remains *unobserved* in this repo, because nothing has ever compacted
here (see Disconfirmation).

## Disconfirmation

**Falsifier.** Name the component: `hooks/inject_compaction_orientation.py`, `commands/handoff.md` and
`scripts/compose_handoff.py` are added; `.ai-work/<slug>/HANDOFF.md` is a new artifact with a named producer and a named
consumer; `/resume-pipeline` gains a consumption step; `hooks/capture_session.py` gains a new event branch. That is what
makes this `architectural` rather than `behavioral`. The decision is **wrong** if any of three things is observed:
(a) the live dogfood shows no orientation block arriving on `SessionStart(source=compact)` despite the documented
contract — then the safety net is unbuildable as designed and should collapse to the `PreCompact` snapshot plus the
existing prose, with the telemetry row kept; (b) three consecutive pipelines run with the handoff available and the
orchestrator's context at spawn does **not** drop below the 250k p50 target — then the handoff is ceremony, not
economy, and its command should be retired rather than kept as an unused surface; (c) handoffs *are* written but the
next window still re-asks what it was already told — a user restating an operating constraint that §4 was supposed to
carry is direct evidence that the continuity guarantee does not hold, and the section list, not the operator, is at
fault.

This decision has already been falsified twice, both times before any code was written, which is the cheapest place
for it to happen: `PostCompact` was assumed by the roadmap, the brief and the first draft to be the restore seam (the
live docs say it has no `additionalContext`), and the utilisation band was assumed by all three to be the mechanism
(the user's pre-mortem reading is that it gambles the judgement state rather than preserving it). Both times the design
moved rather than the claim weakening. The falsifiers above ask for the same discipline on what is left.

**Steelmanned runner-up** (argued as if it were the recommendation; note that the user's decision has since removed
the band half of it, which is recorded below rather than rewritten away). *Do not build a handoff artifact at all. Set
the band to 20% and let the harness compact everything, orchestrator and subagents alike.* The case is strong and mostly
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
is the design to fall back to — not a patched version of this one. **The user's 2026-09-18 decision took the
runner-up's band half off the table and left its handoff-scepticism standing**, which sharpens rather than settles it:
with no threshold to fall back on, the runner-up now reads "build nothing and let the harness compact whenever it
compacts", and the only thing refuting that is whether §4's verbatim constraints and the readiness gate actually spare
the next window the re-stitching. That is falsifier (c), and it is the honest live question about this design.

**Reversal trigger.** Revisit when any of: (1) the dogfood records no orientation block on
`SessionStart(source=compact)`; (2) `/handoff` is invoked in fewer than 2 of the next 4 Standard pipelines (an unused
command is a retirement candidate, not a default — and with no mechanical prompt, low uptake is the predicted failure);
(3) the `compaction` telemetry rows show unplanned compactions continuing to hit sessions that had a boundary
available, i.e. the human trigger is not firing in practice and the question of a *user-set* threshold returns to the
user; (4) `--force` appears in more handoffs than it does not, which would mean the readiness conditions are wrong
about what a boundary is; (5) the harness ships a programmatic utilisation read, which would make the trigger heuristic
mechanisable and this decision's division of labour obsolete.
