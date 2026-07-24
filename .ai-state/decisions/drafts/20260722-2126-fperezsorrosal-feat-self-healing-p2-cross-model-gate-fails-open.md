---
id: dec-draft-d140854d
title: The cross-model review gate fails open — reviewer unavailability never blocks a fix
status: proposed
category: architectural
date: 2026-07-22
summary: Any Cursor error, timeout, malformed/unparseable output, or no-model-of-family condition degrades the cross-model review gate to "review unavailable" — the workflow labels the PR cross-model-review:unavailable, comments once, and exits 0. The gate never blocks a fix; the human merge gate is the backstop. A distinct cross-model-review:misconfigured outcome (reviewer_family == fixer family) also exits 0 but stays loud so operators fix the config rather than silently losing cross-model coverage.
tags: [ci-cd, self-healing-loop, cross-model-review, cursor, fail-open, resilience, gate, security, availability]
made_by: agent
agent_type: systems-architect
branch: feat-self-healing-p2
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-cross-model-review.yml
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
affected_reqs: [REQ-04, REQ-08, REQ-11]
dissent: "Fail-open means a defect the gate would have caught can merge whenever the gate is down, silently trading safety for availability; a fail-closed gate on sensitive_paths tiers would be safer — accepted because a review gate that can block a fix becomes an outage vector, no Cursor quota-exhaustion exit signature is published to special-case, and the human merge gate remains the true backstop."
---

## Context

The P2 cross-model review gate (`dec-draft-d9c4bdb9`) inserts a second vendor, Cursor, into the
self-healing loop's PR path. That vendor's reliability is only partly knowable in advance
(`RESEARCH_CURSOR.md`):

- **No `--max-turns` / budget-cap flag exists** (VERIFIED) — a hung review can only be bounded
  externally (`timeout-minutes`).
- **No documented quota-exhaustion exit code or error string** (UNVERIFIED — none found anywhere)
  and **no usage/quota REST API** — a workflow cannot distinguish "out of credits" from any other
  non-zero exit. Credits also **do not roll over** month-to-month, so exhaustion is a *normal*,
  expected monthly condition, not an exceptional one.
- The reviewer's contract is a JSON verdict elicited from a **foreign model** with no schema-
  constrained output mode via the CLI (`--output-format json` wraps Cursor's envelope, not the
  agent's answer) — malformed/unparseable output is a routine, expected failure mode.

The architectural question: when the reviewer cannot produce a verdict, does the gate **block** the
fix (fail-closed) or **wave it through with a label** (fail-open)?

## Decision

**The gate fails open.** Any of {non-zero Cursor exit, `timeout-minutes` kill, malformed/unparseable
JSON verdict, no model matching `reviewer_family` available from `--list-models`} degrades
identically to "review unavailable": the workflow applies label `cross-model-review:unavailable`,
posts **one** explanatory comment, and **exits 0**. It never marks the PR a draft, never closes it,
never blocks merge. The human merge gate — which every fix already passes through — is the backstop.
`review.on_unavailable` in `autofix-policy.yml` is `fail-open` (the only P2 value; `fail-closed` is
reserved, not implemented).

Because no quota-exhaustion signature is published, **all** failure causes collapse to the same
degraded path — the design does not try to special-case exhaustion. Cost is bounded upstream by the
job `timeout-minutes` (there is no native turn cap to rely on).

**One outcome is carved out as distinct-but-still-fail-open:** if `review.reviewer_family` resolves
to the fixer's own family (`claude`), the review would be same-family and worthless
(`dec-draft-d9c4bdb9`). This is an operator *misconfiguration*, not a runtime unavailability, so it
gets its own loud label `cross-model-review:misconfigured` and a comment naming the exact conflict —
but it **still exits 0**, because a config error must not become the one thing that blocks a fix
either. The distinct label ensures the operator *sees and fixes* it rather than silently receiving
no cross-model coverage behind a generic "unavailable."

## Considered Options

### A. Fail open — unavailability labels + proceeds to the human gate (chosen)
- **Pros:** the review gate can never become a CI outage vector — a Cursor incident, a monthly
  credit exhaustion, or a foreign-model JSON hiccup pauses *review*, never *fixing*; matches the
  P0/P1 posture that the loop degrades gracefully; the human merge gate already gates every fix, so
  fail-open removes no *final* safety, only an *advisory* signal; requires no (non-existent)
  quota-exhaustion detection contract.
- **Cons:** a real defect the gate would have caught can merge during a gate outage if a human
  rubber-stamps the unavailable PR; the safety signal is only as strong as its availability.

### B. Fail closed — block/draft the PR until a verdict is produced
- **Pros:** no fix merges without a cross-model verdict; strongest possible enforcement.
- **Cons:** turns every Cursor incident and every monthly credit exhaustion into a **fix pipeline
  stall** — the gate becomes an availability dependency for the very self-healing it is meant to
  assist; with no published exhaustion signature, the workflow cannot even tell operators *why* it
  is blocking; inverts the loop's purpose (unblock CI) into a new blocker.

### C. Fail closed only for `sensitive_paths` tiers, fail open otherwise (hybrid)
- **Pros:** blocks only the highest-risk changes when review is down; lower-risk fixes still flow.
- **Cons:** the sensitive-path **tripwire already drafts** those PRs for mandatory human review
  (P0), so a fail-closed gate on top is redundant with the existing human gate on exactly that
  tier; adds branching complexity for a case already covered. Held as the documented fallback the
  falsifier below would promote — not built in P2.

## Consequences

- **Positive:** the two-vendor embed adds *zero* new ways to stall the fix pipeline; monthly credit
  forfeiture (a certainty, not an edge case) is a non-event; the design needs no unpublished exit-
  code contract; misconfiguration is loud and distinct, not silently swallowed.
- **Negative / cost:** the gate's protective value is contingent on its uptime — a defect can slip
  through during an outage if the human under-scrutinizes an `unavailable` PR; P6 must measure how
  often the gate is actually down and whether any slipped defect correlates with downtime (the
  falsifier).
- **Activation:** honest-uncertainty gate fired (fail-open trades a real, if bounded, safety
  property for availability) → Tier-A Disconfirmation is mandatory. Tier-B NOT invoked — the human
  merge gate caps the downside (no fix reaches `main`/default unreviewed by a human regardless), so
  this is not a one-way-door decision.

## Disconfirmation

- **Falsifier:** over P6's window, a defect that an *available* gate would plausibly have caught
  merges while the gate was down, and this happens **more than rarely** — evidence that fail-open's
  contingent-on-uptime protection has a real, recurring hole. That promotes Option C (fail-closed on
  `sensitive_paths` tiers only).
- **Steelmanned runner-up:** **Option C (hybrid fail-closed on sensitive tiers).** It wins if the
  gate's downtime turns out to be non-trivial *and* correlates with slipped defects on exactly the
  high-risk paths — then blocking that narrow tier when review is unavailable buys real safety at a
  bounded availability cost, and the sensitive-path set is small enough that stalls are rare.
- **Reversal trigger:** P6 metrics show gate downtime is both frequent and defect-correlated on
  sensitive paths → set `on_unavailable: fail-closed` for the `sensitive_paths` tier only (Option
  C), never fleet-wide fail-closed (Option B stays rejected — a gate that can stall all fixing
  contradicts the loop's purpose). Independently, if Cursor ships a published quota-exhaustion exit
  signature, the degraded path can distinguish exhaustion from error for better operator telemetry
  without changing the fail-open contract.
