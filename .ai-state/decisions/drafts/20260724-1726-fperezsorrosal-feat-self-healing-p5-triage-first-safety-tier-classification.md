---
id: dec-draft-f96c42a4
title: Triage-first, deny-by-default safety-tier classification for issue autofix
status: proposed
category: architectural
date: 2026-07-24
summary: >-
  The P5 fixer classifies a defect mechanical (→ issue-autofix PR) only when the
  fix has bounded blast radius, test-checkable correctness, and decides no design
  question; everything else — and any touch of governance-bearing surfaces — routes
  to needs-adr. A deny-by-default trust boundary so an issue is never a license to
  redesign.
tags: [ci-cd, autofix, github-actions, safety-tier, classification, trust-boundary, governance, self-healing-loop, needs-adr]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
branch: feat-self-healing-p5
affected_files:
  - .github/workflows/issue-autofix.yml
affected_reqs: [REQ-10, REQ-11, REQ-12, REQ-13]
dissent: >-
  A conservative boundary routes genuinely-simple behavioral fixes to humans
  unnecessarily, blunting the loop's value; a fix-first-escalate-on-failure agent
  would heal more defects end-to-end.
---

## Context

The self-healing loop's promise is that Praxion fixes its own reported defects.
The danger is scope: an issue describing a defect can invite the agent to
*redesign* — to change an agent's protocol, a rule, a skill's methodology, or a
governance-bearing contract — under the banner of "fixing a bug." Brief §6 states
the constraint directly: "an issue is not a license to redesign." The design
question: where is the boundary between what the automated fixer may change (open
a PR) and what it must route to human judgment (`needs-adr`), and how is that
boundary made resistant to a persuasive issue body?

## Decision

**Triage-first, deny-by-default classification.** After validating and reproducing,
the agent classifies a defect **mechanical** — and opens an `issue-autofix/*` PR —
**iff all three hold**: (a) the fix has a *bounded blast radius*, (b) its
correctness is *checkable by an existing or trivially-added test*, and (c) it
*decides no design question*. It **must** classify **behavioral/architectural**
(→ root-cause analysis comment + `needs-adr`, no PR) whenever **any** of:

- the candidate fix would touch `.ai-state/decisions/`, `agents/`, `rules/`, a
  skill's `SKILL.md` core, the behavioral contract, or any public/semantic
  contract or template *shape*;
- reproduction failed (the defect could not be confirmed);
- the correct fix is ambiguous or requires choosing among alternatives.

This yields a **three-level structure**: **architectural surface → `needs-adr`**
(never auto-fixed) · **sensitive-but-mechanical → fix + auto-draft** (the P1
`.github/`/`scripts/`/`hooks/` tripwire) · **ordinary mechanical → fix**. Under
uncertainty the agent escalates (favors `needs-adr`) — the boundary is a trust
boundary on the automation's self-modification authority, so it fails toward human
judgment.

## Considered Options

### Option 1 — Deny-by-default mechanical/behavioral boundary (adopted)

- **Pros:** bounds automated change to *defect-scale*, not *design-scale*; keeps a
  human on every behavioral change; naturally conservative; the escalation
  criteria are legible and auditable (a fixed surface list, not a vibe).
- **Cons:** some genuinely-simple behavioral fixes are routed to humans
  unnecessarily (false-negative on "mechanical").

### Option 2 — Fix-first, escalate only on failure

- **Rejected:** lets the agent attempt behavioral/architectural fixes, exactly the
  "issue is a license to redesign" failure mode; a plausible-but-wrong redesign
  can pass a shallow test and reach the merge gate as a large diff.

### Option 3 — Path-allowlist only (fix iff diff stays within N whitelisted dirs)

- **Rejected as too blunt:** a one-line change inside a whitelisted dir can still
  be a design decision; a path list captures *where* but not *whether a design
  question is being decided*. The adopted boundary uses path-surface as one
  necessary escalation trigger, not the whole test.

## Consequences

- **Positive:** the automation's authority is capped at mechanical defects;
  governance-bearing surfaces (decisions, agents, rules, skills, contracts) are
  structurally off-limits to auto-fix; conservative under ambiguity.
- **Negative:** lower end-to-end heal rate than a fix-everything agent; some
  trivial behavioral fixes cost a human triage.
- **Neutral:** mis-classification that *under*-escalates is contained by the
  sensitive-path tripwire + P2 gate + human merge; *over*-escalation costs only a
  human triage — an asymmetric risk profile that favors the conservative default.

## Disconfirmation

- **Falsifier:** over P6's window, `needs-adr` is applied to a large majority of
  armed issues whose fixes a human then judges trivially mechanical (the boundary
  is too conservative and the loop delivers little end-to-end healing), OR an
  auto-opened "mechanical" PR is repeatedly found to have decided a design
  question that slipped the escalation criteria (the boundary is too permissive).
- **Steelmanned runner-up (fix-first):** most reported defects *are* mechanical,
  the P2 cross-model gate + human merge already stand between any PR and `main`,
  and a conservative gate wastes the loop's whole value by shunting fixable defects
  to a human queue. A fix-first agent that opens a draft PR for *anything* it can
  reproduce — behavioral included — and lets the review gates catch over-reach,
  would heal more and cost less human triage, converting the human role from
  "classify every defect" to "review the diffs that actually appear."
- **Reversal trigger:** P6 metrics showing (a) a high `needs-adr` rate on
  defects humans deem mechanical *and* (b) a low over-reach rate on the PRs that
  do open → loosen the boundary (allow a bounded class of behavioral fixes as
  auto-draft PRs, still gated). Conversely, any over-reach incident → tighten.
- **Activation:** design-synthesis lens sweep partially run (Security + Simplicity
  lenses) given the governance/trust-boundary stakes; honest-uncertainty gate
  fires on *where exactly* the line sits, so the steelman above argues the
  fix-first rival genuinely. Tier-B cross-model challenge not invoked — the
  asymmetric-risk argument and brief §6/§7 grounding make the conservative default
  well-supported; P6 metrics are the empirical arbiter, per the reversal trigger.
