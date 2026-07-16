---
id: dec-268
title: Realize the eval-ledger lazy-run producer mechanism (helper + skill step); flip EVAL_LOG.md to optional-lazy
status: accepted
category: architectural
date: 2026-07-16
summary: Make the eval_ledger/EVAL_LOG.md producer operational as a stdlib helper + a named agent-evals skill step — the mechanism dec-263 blessed in design — decoupled from the deferred archetype feature and from onboarding; flip the artifact state future-designed → optional-lazy. Re-affirms dec-263.
tags: [eval-ledger, agent-evals, eval-log, producer, future-designed, optional-lazy, roadmap-2-2, efficacy-measurement, gate-liveness]
made_by: agent
agent_type: systems-architect
branch: worktree-efficacy-measurement
pipeline_tier: standard
affected_files:
  - skills/agent-evals/scripts/append_eval_log.py
  - tests/test_append_eval_log.py
  - skills/agent-evals/SKILL.md
  - skills/agent-evals/references/run-ledger-schema.md
  - skills/software-planning/references/artifact-inventory.md
affected_reqs: [REQ-06, REQ-07, REQ-08, REQ-09, REQ-10]
re_affirms: dec-263
dissent: Building a producer mechanism ahead of any live Praxion invoker (Praxion self-eval uses the separate praxion_eval_reports log) risks the inverse gate-liveness smell — a wired producer nothing in-repo calls; if the archetype feature slips indefinitely, the helper is exercised only by its own canary test.
---

## Context

`.ai-state/eval_ledger/EVAL_LOG.md` is an append-only, one-row-per-kept-run leaderboard whose
schema (11 columns) is defined in `skills/agent-evals/references/run-ledger-schema.md` and whose
read-only consumers are built and live: the `/scores` command and the dashboard eval panel
(dec-223). Its lifecycle state is `future-designed`: the producer is *designed* but never wired,
so `/scores` reads emptiness on every project.

`dec-263` (accepted) governs this artifact directly. It retired the *onboarding-producer*
expectation (onboarding will not emit `EVAL_LOG.md`), re-affirmed dec-217's lazy-run design as
"already correct," and named "implementing the deferred agentic-eval archetype loop"
(dec-231/dec-216) as the trigger that carries the producer. Critically, dec-263 conflates two
things: the producer **mechanism** (the append itself) and the producer **invoker** (the eval
loop that decides to keep a run). ROADMAP 2.2 asks to wire the ledger so kept runs leave evidence.

## Decision

Realize the producer **mechanism** now, decoupled from both onboarding and the deferred
archetype feature:

1. **Add a stdlib helper** `skills/agent-evals/scripts/append_eval_log.py` co-located with the
   schema it implements (Balanced Coupling): it ensures `.ai-state/eval_ledger/` exists, writes
   the canonical 11-column header + separator on first write, and appends exactly one
   schema-conformant row (short-prefix `prompt_hash`/`dataset_sha`/`git_sha` at 8/8/7 chars,
   `store_uri` verbatim — backend-invariant, no credentials).
2. **Name the producer step** in `skills/agent-evals/SKILL.md` and `run-ledger-schema.md`
   § Dual Lifecycle: "when a run is kept (the same event that writes project-root
   `EVAL_RESULTS.md`), append a row via `append_eval_log.py`." This gives the built consumers
   (`/scores`, dashboard) a **named producer** (gate-liveness).
3. **Flip the lifecycle state** `future-designed → optional-lazy` in
   `skills/software-planning/references/artifact-inventory.md`. `optional-lazy` (absence = feature
   not adopted) is correct, not `active` (absence = a gap): a project running no eval loop
   legitimately has no ledger.

Onboarding is **not** touched (dec-263 re-affirmed). The agentic-eval archetype feature
(dec-231) stays deferred — when it lands it will *invoke* this helper rather than build its own.
Praxion's own `/eval-praxion` (separate `praxion_eval_reports/PRAXION_EVAL_LOG.md`) is out of
scope and unchanged.

## Considered Options

### A — Standalone helper + operational skill step; flip to optional-lazy (CHOSEN)
- Pros: gives the built, live consumers a real named producer; zero onboarding surface; honors
  dec-263; the mechanism is tested (canary) and invocable by any eval loop, present or future.
- Cons: no *live Praxion invoker* yet (Praxion self-eval writes a different log), so the helper
  is exercised in-repo only by its test until a managed project or the archetype feature calls it.

### B — Wire the producer into `/onboard-project` (Phase 8f output)
- Pros: every managed project would get a populated ledger by construction.
- Cons: directly contradicts dec-263 (which retired exactly this); emits a ledger for projects
  that run no evals — the producer-with-no-consumer anti-pattern dec-263 rejected.

### C — Defer entirely until the archetype feature lands
- Pros: strictly minimal; no risk of an early mechanism.
- Cons: leaves `/scores` + dashboard permanently reading emptiness; forfeits ROADMAP 2.2; the
  mechanism dec-263 blessed as "already correct in design" stays un-realized indefinitely.

## Consequences

- **Positive:** the two live consumers get a named, tested producer; the debt closes without
  onboarding surface or shipping the deferred feature; the mechanism-vs-invoker distinction is
  recorded so the archetype-feature author reuses this helper instead of rebuilding it.
- **Negative / constraint:** the helper has no live in-repo invoker until adoption; mitigated by
  the `optional-lazy` state (honest "no adoption yet"), the live consumers, and the canary test.
- **Gate-liveness:** satisfies "a named producer for every consumer" for `/scores` + dashboard;
  the helper ships a canary (a known-bad row it rejects) proving the CODE gate bites.

## Disconfirmation

- **Falsifier:** if the schema evolves such that a correct append requires knowing the active
  backend (an `if backend == s3` branch reaches the row), the helper's backend-invariance is
  violated and the "mechanism decoupled from feature" premise is wrong — the invariance self-test
  in `run-ledger-schema.md` guards this.
- **Steelmanned runner-up (Option C):** if the archetype feature is genuinely imminent, building
  the helper now risks a second author reshaping it to fit the feature's real call site,
  making this pass churn; deferring would let the feature define the producer against its actual
  invoker in one coherent design.
- **Reversal trigger:** revisit if the archetype-eval feature (dec-231) is scheduled and its
  design would materially reshape the producer signature — at which point this mechanism folds
  into that feature's producer decision (superseding this ADR), and the `optional-lazy` state may
  advance as adoption lands.

## Prior Decision

This ADR **re-affirms dec-263**: onboarding remains a non-producer of `EVAL_LOG.md`, and the
agentic-eval archetype feature stays deferred. It does **not** supersede dec-263 — it realizes
the lazy-run producer *mechanism* dec-263 explicitly called "already correct," making the
distinction between the producer mechanism (built here) and its eventual invoker (the deferred
feature or a managed project's eval loop) explicit for future readers.
