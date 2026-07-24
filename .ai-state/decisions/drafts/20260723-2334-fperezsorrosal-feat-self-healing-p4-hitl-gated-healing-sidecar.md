---
id: dec-draft-ebf8352b
title: HITL-gated healing sidecar — no unattended cross-repo issue filing in v1
status: proposed
category: architectural
date: 2026-07-23
summary: The managed-project→Praxion healing sidecar files ecosystem-defect issues only through an explicit human-in-the-loop gate riding the operator's own `gh` auth in v1 — no unattended cross-repo filing, no PAT, no GitHub App — because the outward-facing, hard-to-retract action of opening an issue on a foreign repo demands deliberate human authority (dec-014's stance) and because the false-positive rate of auto-captured candidates is unmeasured; the reversal trigger is a sustained low false-positive rate in the PENDING.md candidate stream, which then justifies auto-filing a whitelisted category subset via a minimal-permission GitHub App (never a wide PAT).
tags: [self-healing-loop, healing-sidecar, upstream-stewardship, hitl, cross-repo, issue-filing, github-app, auth, sanitization, fingerprint, ecosystem-feedback]
made_by: agent
agent_type: systems-architect
branch: feat-self-healing-p4
pipeline_tier: standard
affected_files:
  - .github/ISSUE_TEMPLATE/ecosystem-defect.md
  - scripts/report_praxion_issue.py
  - commands/report-praxion-issue.md
  - .ai-state/praxion_feedback/PENDING.md
  - commands/onboard-project.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]
dissent: "If capture precision is high, an Issues:Write-only GitHub App filing whitelisted mechanical categories (hooks/scripts) would close the healing loop faster and avoid a candidate backlog that never gets filed — the dec-014 'user must remember' failure mode. We hold HITL-only because that precision is unmeasured today; auto-filing on an unproven rate risks spamming the upstream tracker with false ecosystem-defect reports, an asymmetric downside a human dismissal cheaply avoids."
---

## Context

The self-healing loop (brief §3) closes when a *Praxion-origin* ecosystem defect observed inside a
managed project flows back to the Praxion repo as a filed issue, gets triaged/fixed (Subsystem C,
P5), and returns to the fleet via the block-refresh manifest (`dec-271`) and version-pin bumps. The
**healing sidecar** (Subsystem B, brief §5) is that return edge: managed project → Praxion.

Three facts constrain the filing-authority design:

1. **Auth reality (brief §2.4, [V]).** A workflow's default `GITHUB_TOKEN` **cannot** file
   cross-repo. The least-privilege long-term instrument is a GitHub App minting short-lived
   installation tokens; a fine-grained PAT would need `Issues: Write` + transitively `Contents:
   Read` per target. But in an interactive session a human operator is already present with their
   own authenticated `gh` — filing through it adds **zero new secrets** to managed repos.

2. **Outward-facing, hard-to-retract action.** Opening an issue on a foreign repo is visible,
   creates upstream triage load, and — once P5 ships — a filed issue that a maintainer labels
   `ecosystem-feedback` *arms an autofix agent*. This is precisely the class of action the agent
   behavioral contract reserves for a deliberate human gate.

3. **Established precedent.** `dec-014` chose a Skill + Command + Tracker composition for
   `/report-upstream` and explicitly rejected an autonomous agent because *"filing upstream issues
   should be deliberate, not autonomous."* The sidecar is an instance of that same stack with the
   target fixed to the Praxion repo (brief §5.0 reuse map); its filing authority should inherit the
   same stance.

`dec-273` (P1 hub distribution) already forward-linked to this decision: it rejected a GitHub App
for *workflow distribution* but named it "the correct future instrument for the healing sidecar's
cross-repo issue **filing** — a distinct problem," and set a reversal trigger of "if the healing
sidecar needs unattended cross-repo issue filing." This ADR resolves that distinct problem for v1.

## Decision

**The healing sidecar files only through an explicit human-in-the-loop gate, riding the operator's
own `gh` auth. v1 has no unattended cross-repo filing path — no PAT in managed repos, no GitHub
App, no CI-automated filing.**

Concretely:

- **Capture is autonomous; filing is not.** Praxion capture points (agents, hooks, commands, sentinel/
  verifier findings with plugin-origin root cause) append a *candidate* to
  `.ai-state/praxion_feedback/PENDING.md` — a mechanically-sanitized, fingerprinted record. Appending
  a candidate is not filing.
- **Session-start surfacing, not auto-dispatch.** When `PENDING.md` is non-empty the orchestrator
  surfaces an advisory notice at session start; it never files on its own.
- **The human gate is the filing authority.** `/report-praxion-issue` runs the deduplicate → render →
  sanitize (judgment pass) → security-gate → **confirm** → file → track pipeline, and `gh issue
  create -R <praxion-repo>` executes only after the operator approves the final title/body/labels —
  through the operator's already-authenticated `gh`.
- **Security-sensitive Praxion defects never file a public issue.** The `/report-upstream`
  responsible-disclosure path is preserved verbatim: a Praxion defect with security implications
  routes to private vulnerability reporting, not a public `ecosystem-defect` issue.

## Considered Options

### Option A — HITL-gated filing on the operator's `gh` auth (chosen)
- **Pros:** zero new secrets in any managed repo; the human whose credential files the issue is the
  human who approved it (auth and gate reinforce each other); inherits `dec-014`'s validated
  "deliberate not autonomous" stance verbatim; maximal reuse of the shipped `/report-upstream` stack;
  no operated-service surface; trivially reversible — auto-filing can be added later behind a measured
  gate without unwinding anything.
- **Cons:** a human must act on every candidate, so the healing loop's return edge has human latency;
  candidates can accumulate unfiled (the `dec-014` "user must remember" failure mode, mitigated but
  not eliminated by session-start surfacing).

### Option B — GitHub App auto-filing a whitelisted category subset now (steelmanned runner-up)
- **Pros:** an `Issues: Write`-only App on the Praxion repo, minting short-lived installation tokens,
  could auto-file high-precision mechanical categories (`hooks`, `scripts`) with no human latency —
  closing the loop faster and eliminating the unfiled-backlog risk; it is the *correct* least-privilege
  instrument (brief §2.4) and the one `dec-273` already anticipated.
- **Cons:** requires standing up an operated service (webhook/token-minting infra, availability, its
  own security surface) — disproportionate for P4; and, decisively, **the candidate false-positive rate
  is unmeasured** (P6 has not run). Auto-filing on an unproven precision rate risks flooding the Praxion
  tracker with false ecosystem-defect reports; each false issue is upstream noise and a latent P5 arming
  target. The downside is asymmetric: a false HITL candidate costs one cheap human dismissal; a false
  auto-filed issue costs upstream triage and pollutes the fix machinery.

### Option C — Fine-grained PAT with `Issues: Write` in each managed repo
- **Pros:** simplest mechanism that enables cross-repo filing without a human; no service to operate.
- **Cons:** puts a **long-lived, wide-allowlist credential in every managed repo** — the exact
  anti-pattern brief §2.4 and `dec-273` warn against; blast radius scales with the fleet; still
  auto-files on an unmeasured precision rate. Rejected outright — if unattended filing is ever
  justified, the App (Option B), not a PAT, is the instrument.

## Consequences

- **Positive:** the sidecar ships as a thin adaptation of an already-hardened, already-audited stack
  with no new trust surface in managed repos; the arming risk for P5 is bounded by a human gate on the
  filing side and a maintainer-label gate on the consumption side (defense in depth); the design
  forward-links cleanly to an App-based auto-filing upgrade without rework, gated on measured evidence.
- **Negative / cost:** the return edge of the healing loop carries human latency and a possible
  unfiled-candidate backlog; the false-positive rate that would justify automation must be *measured*
  (via the PENDING.md candidate stream + `UPSTREAM_ISSUES.md` outcomes), which is itself deferred work
  (P6). Until then the loop closes at human speed by design.

## Disconfirmation

- **Falsifier:** over a sustained window the PENDING.md candidate stream shows a **low false-positive
  rate** (captured candidates are, on human review, overwhelmingly genuine shipped-artifact defects) —
  **and** an unfiled-candidate backlog demonstrably delays fixes reaching the fleet. Both together
  falsify "the human gate is worth its latency" for the high-precision mechanical categories.
- **Steelmanned runner-up (Option B):** if capture precision is high, a minimal-permission GitHub App
  auto-filing only `hooks`/`scripts` candidates (deterministic, path-attributable, low-judgment) — never
  `agents`/`skills`/`blocks` (judgment-heavy) — closes the loop faster, removes the backlog failure mode,
  uses the correct least-privilege auth instrument, and keeps a human in the loop exactly where judgment
  is actually needed (the ambiguous categories) rather than uniformly. The case is strong *once precision
  is a measured quantity rather than an assumption.*
- **Reversal trigger:** a **sustained low false-positive rate in PENDING.md candidates** (measured over
  P6's window) promotes Option B from runner-up to design — auto-file a **whitelisted category subset**
  via a minimal-permission GitHub App minting short-lived installation tokens (**never a wide PAT**),
  keeping HITL for the non-whitelisted categories and for anything the sanitizer flags. This is the same
  App `dec-273` Option C reserved for exactly this problem.

## Prior Decision

This ADR does **not** supersede or re-affirm any decision. It **applies** `dec-014`'s "deliberate not
autonomous" filing stance to a new surface (the Praxion-targeted sidecar) and **resolves** the distinct
cross-repo-filing-auth problem that `dec-273` explicitly deferred to the sidecar. Both are cited as
context, not amended: `dec-014` remains the composition precedent, `dec-273` remains the workflow-
distribution decision whose Option-C forward-link this ADR now grounds with a concrete reversal trigger.
