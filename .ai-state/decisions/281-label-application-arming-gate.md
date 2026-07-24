---
id: dec-281
title: Label application (ecosystem-feedback) is the HITL arming gate for issue autofix
status: accepted
category: architectural
date: 2026-07-24
summary: >-
  A maintainer applying the ecosystem-feedback label is the human-in-the-loop
  arming gate for P5 issue autofix — enforced by three independent layers
  (GitHub label-permission model + non-Bot actor guard + payload gate) and
  positioned as defense-in-depth, not the sole control.
tags: [ci-cd, autofix, github-actions, issues-event, security, hitl, arming-gate, loop-prevention, self-healing-loop]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
branch: feat-self-healing-p5
affected_files:
  - .github/workflows/issue-autofix.yml
affected_reqs: [REQ-01, REQ-02, REQ-05]
dissent: >-
  If maintainers rubber-stamp the label without reading the issue, the human gate
  collapses to auto-arming and the whole HITL premise is fiction — a stronger,
  action-explicit arming signal would not depend on maintainer diligence.
---

## Context

P5's trigger is `on: issues, types: [labeled]`. Anyone can open a GitHub issue;
if merely opening an issue armed the fixer, every opened issue would become agent
fuel — a prompt-injection and spam surface at scale (brief §7). A human-in-the-loop
gate is required between "issue exists" and "agent triages/fixes it." The design
question: what *is* that gate, and how strong is it?

The `ecosystem-feedback` label is already reserved for exactly this: the P4
sidecar's `render.py` structurally refuses to emit it (`RESERVED_MAINTAINER_LABEL`),
so a managed-project auto-filed issue never arrives pre-armed. Only a Praxion
maintainer adds it.

## Decision

**Label application is the arming gate.** The workflow runs only when
`github.event.label.name == 'ecosystem-feedback'` **and**
`github.event.sender.type != 'Bot'`. This is enforced by **three independent
layers**:

1. **GitHub's permission model** — applying a label to an issue requires triage
   or write access; a random external user cannot arm the agent.
2. **Actor guard** (`sender.type != 'Bot'`) — the agent authenticates as
   `claude[bot]`; if it ever applied a label, the re-triggered `issues.labeled`
   event would carry a Bot sender and be filtered. This also breaks the
   agent-self-arms-a-loop vector.
3. **Payload gate** (`label.name == 'ecosystem-feedback'`) — the agent applies
   only `needs-adr`/`triage:invalid`/`duplicate`; those carry different names and
   are filtered, so the agent's own labeling cannot re-trigger a fix cycle.

Crucially, the gate is **defense-in-depth, not the sole control**: an armed issue
still passes through template-validation, dedup, reproduction, and deny-by-default
classification, all backstopped by the P2 cross-model gate and the human merge
gate. The arming label lowers the injection/spam surface; it does not by itself
authorize a merge.

## Considered Options

### Option 1 — Label-as-arming-gate (adopted)

- **Pros:** zero new secrets; no bespoke approval UI; uses GitHub's native trust
  model; the arming action is a single auditable event (a named user applying a
  named label); composes with the existing P4 `RESERVED_MAINTAINER_LABEL`
  invariant.
- **Cons:** strength depends on maintainer discipline (the falsifier).

### Option 2 — Auto-arm on issue open (no human gate)

- **Rejected:** turns every opened issue into agent fuel — the exact
  injection/spam surface the gate exists to remove.

### Option 3 — Dedicated `/autofix-approve` slash-command arming

- **Rejected for v1** as heavier than needed (a bespoke command + comment-parsing
  trigger), but retained as the reversal path if rubber-stamping proves real.

## Consequences

- **Positive:** minimal, native, auditable; the loop-prevention layers fall out
  of the same gate (actor + payload) so no separate loop-break machinery is
  needed for the `issues` event.
- **Negative:** a careless maintainer can arm an unreviewed issue — but the
  triage-first pipeline + budget cap + human merge contain the blast radius.
- **Neutral:** the gate is a *rate limiter* by construction (a human must act per
  issue), which is why the daily budget cap can be modest.

## Disconfirmation

- **Falsifier:** maintainers rubber-stamp `ecosystem-feedback` (bulk-apply without
  reading), collapsing the HITL gate to effective auto-arming. Observable as a
  high proportion of armed issues that triage immediately rejects as
  invalid/duplicate/needs-adr, or a security incident traced to an armed-but-
  unvetted issue.
- **Steelmanned runner-up (action-explicit arming):** a gate that does not depend
  on maintainer diligence — e.g., requiring an explicit `/autofix-approve` comment
  or a two-maintainer approval, or a precondition `triage:reproduced` label — makes
  the human intent *unforgeable and legible*, closing the rubber-stamp hole the
  label gate leaves open. For a workflow that grants an agent write access on the
  strength of one click, a costlier-but-deliberate arming signal is defensible.
- **Reversal trigger:** measured rubber-stamping (per above) or any armed-issue
  security incident → move to a stronger arming gate: an action-explicit
  `/autofix-approve` command, a required-precondition label, or two-maintainer
  approval. Revisit in P6's metrics window.
- **Activation:** design-synthesis lens sweep — no full sweep (the decision is
  largely forced by the `on: issues` trigger shape and is well-grounded by brief
  §7 + seed 4); security stakes warranted the explicit three-layer analysis and
  the Tier-A Disconfirmation above. Tier-B cross-model challenge not invoked — the
  research brief already provides multi-source grounding.
