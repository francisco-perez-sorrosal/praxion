---
id: dec-draft-d9c4bdb9
title: Claude fixes / Cursor reviews — a foreign-model, non-generative review gate on every agent-authored fix PR
status: proposed
category: architectural
date: 2026-07-22
summary: The self-healing loop's second model family (Cursor-brokered, non-Anthropic) reviews every Claude-authored fix PR as an independent, NON-GENERATIVE gate — it emits a JSON verdict {approve|request-changes, findings[]}, marks the PR draft on request-changes, and never counter-fixes. Supersedes v1's Cursor-first-failover hypothesis (never itself an ADR), because self-preference bias is causal and stronger in larger models, and a non-generative gate captures the cross-model-diversity benefit without the popularity-trap cost of reconciling two fixers' output.
tags: [ci-cd, self-healing-loop, cross-model-review, cursor, code-review, gate, non-generative-gate, model-diversity, security, prompt-injection]
made_by: agent
agent_type: systems-architect
branch: feat-self-healing-p2
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-cross-model-review.yml
  - .github/workflows/cross-model-review.yml
  - claude/project-baseline/ci-autofix/cross-model-review.yml.tmpl
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-09, REQ-12]
dissent: "Embedding a second vendor (Cursor) as a mandatory non-generative gate doubles the CI secret surface and adds a foreign-model dependency whose defect-catch value is unproven until P6; same-family self-review or no gate is cheaper and the human merge gate already backstops every fix — accepted because self-preference bias is causal/stronger in larger models and the forfeit-if-unused credits make cross-family review nearly free."
---

## Context

The self-healing loop (brief `self-healing-loop-implementation-brief.md`) authors fixes with a
single model family: Claude (`claude-code-action`, Opus, SHA-pinned), which opens a `ci-autofix/`
(P0, `dec-272`) or `issue-autofix/` (P5) PR, never a direct push. P1
(`dec-273`) distributed that fixer as a hub reusable workflow. The open architectural
question P2 answers: **who, if anyone, independently reviews an agent-authored fix before a human
merges it, and in what role?**

Three research findings shape the answer (brief §2.1, `RESEARCH_CROSS_MODEL.md`):

1. **Self-preference bias is real and causal** — a model's ability to recognize its own output
   predicts how much it overrates it, and larger models show it *more*, not less
   (arXiv:2410.21819); a 2026 companion extends this to monitoring: models under-flag violations in
   transcripts they believe are their own (arXiv:2603.04582). This is the direct argument that a
   *different model family* should review work another family produced.
2. **Naive multi-model composition backfires** — consensus voting amplifies shared errors (the
   "popularity trap"); heterogeneous agent teams can underperform their best single member by up to
   37.6% when a diversity-aware aggregation step is missing. The clean way to capture diversity
   *without* an aggregation problem is a **non-generative gate**: the second model judges, it does
   not produce a rival artifact that must be reconciled.
3. **Cursor makes cross-family review buildable today** (brief §2.2, `RESEARCH_CURSOR.md`, VERIFIED):
   headless `agent -p "<prompt>" --output-format json --model <m>`, `--list-models`, per-invocation
   model pinning, `CURSOR_API_KEY` auth, official GitHub Actions install recipe. Cursor brokers many
   non-Anthropic families (GPT, Gemini, its own Composer) under one key — so `reviewer_family`
   selects the *model*, not a second secret.

v1's leading hypothesis — Cursor as the *first fixer* with Claude failover — is rejected as the
primary design: failover is a cost/availability pattern, not a diversity pattern, and under it most
fixes would receive **zero** cross-model review (Anthropic rarely fails). The prepaid, forfeit-if-
unused Cursor credits find a better home spending on *every* fix's review (steady, predictable) than
on *rare* failover fixing (bursty). Provider redundancy survives only as a documented manual
`provider: cursor` break-glass flip, not an automated path.

## Decision

**Claude fixes; a Cursor-brokered non-Anthropic model reviews every agent-authored fix PR as an
independent, non-generative gate.** Concretely, the P2 hub `reusable-cross-model-review.yml`:

1. Triggers on `pull_request` (never `pull_request_target`) for agent-authored branches
   (`ci-autofix/*`, `issue-autofix/*`), and optionally all PRs, per policy
   `review.cross_model_gate` (`all-prs` | `agent-prs` | `off`). The gate decision (branch-prefix +
   policy) lives in the hub, read from the caller's `autofix-policy.yml`, keeping the caller thin
   (consistent with `dec-273`).
2. Resolves the reviewer model **at run time** via `agent --list-models`, selecting a model whose
   family matches `review.reviewer_family` (default `gpt`) and is **never the fixer's family**
   (`claude`) and **never a hardcoded ID** (Cursor model IDs churn).
3. Runs a **gate-only** review — the reviewer receives the PR diff (and the fixer PR body, which
   already carries the root-cause summary and the failed-run link) as sanitized **DATA**, and is
   instructed to output a JSON verdict `{verdict: approve|request-changes, findings[]}` and to
   **NOT propose a rewritten fix**. Non-generativity is enforced *structurally*, not by prompt
   alone: the review job holds **no `contents: write`**, no `id-token: write`, no write tools, and
   runs no git/commit/PR step — any local edit a foreign model makes is inert and dies with the
   ephemeral runner. *(O1 update, live-verified P2: the headless `cursor-agent -p` call must pass
   `--force` to bypass Cursor's workspace-trust confirmation prompt — without it the CLI blocks in
   the TTY-less runner and exits non-zero with zero bytes. This reverses O1's original "omit
   `--force`" conclusion but not its principle: `--force` does not compromise non-generativity
   because the security boundary is the read-only-plus-PR token scope above, not the CLI flag — an
   edit the flag would permit has nowhere to land.)*
4. On `approve`: posts the findings as a PR comment, labels `cross-model-review:approved` +
   `reviewed-by:<family>` (audit trail), leaves the PR mergeable. On `request-changes`: posts
   findings, labels `cross-model-review:changes-requested` + `reviewed-by:<family>`, and **marks the
   PR a draft** — it never auto-closes and never counter-fixes.
5. **Praxion is caller #1**: a same-repo caller reviews Praxion's own `ci-autofix/*` PRs before any
   managed project adopts the gate (dogfood first).

Fail-open behavior on reviewer error/timeout/malformed output is the companion decision
`dec-draft-d140854d` (this ADR presumes it).

## Considered Options

### A. Claude fixes / non-Anthropic model reviews as a non-generative gate (chosen)
- **Pros:** captures the self-preference-bias mitigation (cross-family judgment) with zero
  aggregation problem (the gate judges, it does not produce a rival fix); spends the forfeit-if-
  unused credits on *every* PR, predictably; the reviewer needs no write privilege at all, so it is
  the least-privileged possible embed of a second vendor; degrades cleanly to "review unavailable"
  and is fully policy-tunable/removable per repo.
- **Cons:** doubles the CI secret surface (`CURSOR_API_KEY` joins the Claude token); adds a foreign-
  model dependency; defect-catch value is unproven until P6 measures gate catch-rate vs noise; a
  foreign model reliably emitting parseable JSON is the load-bearing brittleness.

### B. Cursor-first fixer with Claude failover (v1's hypothesis, rejected)
- **Pros:** spends credits on the scarce-supply *fixing* role; keeps provider redundancy automated.
- **Cons:** failover is not a diversity mechanism — most fixes get zero cross-model review; credits
  sit idle between rare Anthropic outages then forfeit; no self-preference-bias mitigation on the
  common path. Retained only as a manual `provider: cursor` break-glass flip.

### C. Same-family (Claude) second-pass review
- **Pros:** one vendor, one secret, no Cursor dependency.
- **Cons:** the exact failure mode the evidence names — self-preference bias is *causal* and
  *stronger* in larger models; a Claude reviewing Claude systematically under-flags. Defeats the
  purpose.

### D. No independent gate — human merge is the only review
- **Pros:** simplest; zero new surface.
- **Cons:** forfeits the credits entirely and leans the full defect-catch burden on a human who is
  reviewing an agent's output with no second-model signal. The human gate stays as the backstop
  regardless; this option is "backstop only."

## Consequences

- **Positive:** every fix — managed-project or Praxion-origin (P5) — is authored by one family and
  independently judged by another before a human merges; the reviewer is maximally least-privileged
  (no write anything); the design forward-links to P5 (Praxion issue autofix reviewed by the same
  gate) and P6 (catch-rate/noise/cost metrics feed the first-party evidence the field lacks); it
  builds directly on `dec-272` (whose Consequences already named "a non-Anthropic model
  reviews") and `dec-273` (the hub+caller distribution shape) without rework.
- **Negative / cost:** a second vendor's key in every adopting repo; a foreign-model dependency and
  its JSON-parse brittleness (mitigated by fail-open, `dec-draft-d140854d`); the review-prompt step
  is the highest-risk element (a defect-focused, gate-only JSON verdict must be elicited from a
  foreign model) — flagged `tier: H` for the implementation planner; unproven catch-rate until P6.
- **Activation:** honest-uncertainty gate fired (catch-rate unproven; two-vendor complexity vs
  unmeasured benefit) → Tier-A Disconfirmation below is mandatory and the steelmanned runner-up
  (Option B) is argued genuinely. Tier-B cross-model challenge NOT invoked — the decision is
  reversible via policy (`cross_model_gate: off`, `provider.fixer: cursor` break-glass) and its
  reversal trigger, so stakes are not one-way-door / user-visible-breaking.

## Disconfirmation

- **Falsifier:** over P6's 60–90-day window the gate's catch-rate is ≈ 0 while its false-positive
  (spurious `request-changes`) rate is high — i.e. it drafts good PRs and catches nothing — **or**
  evidence emerges that same-family review performs equivalently to cross-family on code-review
  defect-miss-rate specifically (no study isolates this today; P6 is Praxion's first-party test).
- **Steelmanned runner-up:** **Option B (Cursor-first fixer + Claude failover).** It wins the moment
  Anthropic availability becomes the binding constraint (sustained outages/limits pause *all* fixing
  under the chosen design, whereas B keeps fixing via Cursor), **or** the credit volume dwarfs review
  need so badly that spending it on the scarce fixing role returns more than reviewing every PR.
  Under B the credits buy provider redundancy — a real, if different, value — and a single vendor
  removes the two-secret surface entirely.
- **Reversal trigger:** sustained Anthropic outages that repeatedly pause the fixer, **or** Cursor
  ships a verified quota API + turn caps that make it the *safer* fixer (bounded cost, observable
  exhaustion) — either promotes Option B and flips `provider.fixer` to `cursor` as the automated
  path. Independently, if P6 shows the gate is pure noise, revert to Option D (human-gate-only) by
  setting `cross_model_gate: off` fleet-wide.
