---
id: dec-draft-0f1596ea
title: Scope HTML authorship boundary to canonical surfaces; permit ephemeral user-requested HTML
status: accepted
category: architectural
date: 2026-07-29
summary: Agents may author HTML directly for ephemeral, explicitly-requested output with no MD backing, defaulting to .ai-work/<task-slug>/ or tmp/; a new pre-commit guard mechanically enforces the boundary for everything else.
tags: [html-output, prompting-ux, dashboard, authorship-boundary, rules, hooks]
made_by: user
pipeline_tier: lightweight
affected_files:
  - rules/writing/html-output-conventions.md
  - scripts/check_html_authorship.py
  - scripts/test_check_html_authorship.py
  - scripts/CLAUDE.md
  - .pre-commit-config.yaml
dissent: Ephemeral HTML with no committed backing can still leak into the repo if an agent forgets the .ai-work/tmp default and the user asks to keep it without going through the share_out path — the new pre-commit guard closes most of this gap mechanically, but a determined bypass (--no-verify) is still possible, same as any pre-commit-enforced convention.
---

## Context

A user-driven research pass (external prompting-technique research + an internal Praxion touchpoint audit, both via the `researcher` agent) surfaced `rules/writing/html-output-conventions.md`'s "Authorship Boundary" table: skill/agent/convention authors write MD only, never HTML — HTML is rendered by `dashboard_app/` or a pre-commit hook, never hand-authored. The rationale is sound for canonical, persistent artifacts (`VERIFICATION_REPORT.md`, `SENTINEL_REPORT_*.md`, etc.): a hand-authored HTML copy alongside an MD source drifts. `dec-145` had previously flagged and fixed exactly this drift once, for `.ai-state/metrics_reports/index.html` — verified during this ADR's follow-through work as already resolved (the file is no longer tracked in this repo), so the risk is real but not currently live.

The user asked to relax this boundary for a different case: when they explicitly ask for HTML output in-session (e.g. a chart, a plot, a richer table) to better understand a result, the responding agent should be able to author that HTML directly rather than being blocked by a rule written for a different problem (MD/HTML source-of-truth drift on *persistent* reports). A follow-up round refined the ephemeral-output location (prefer the active pipeline's `.ai-work/<task-slug>/` over a bare `tmp/`, since it shares that document's existing gitignored/cleaned-up-with-the-pipeline lifecycle) and closed the enforcement gap the initial version left advisory-only.

## Decision

The Authorship Boundary continues to govern canonical, persistent human-facing surfaces unchanged — MD is the single source of truth there, HTML is a rendered view only. A new, narrower exception permits an agent to author HTML directly for **ephemeral output the user explicitly requests in-session, with no persistent MD counterpart** — because there is no MD source for such output to drift out of sync with, the failure mode the boundary defends against does not apply. The exception is bounded by three mechanisms: (1) if the content already has or should have a canonical MD form, render that through the dashboard instead of hand-authoring a parallel copy; (2) ephemeral HTML defaults to `.ai-work/<task-slug>/` when a pipeline task slug is active, else `tmp/` — uncommitted either way — unless the user asks to keep it, at which point it becomes a deliberate `share_out: true` MD-sourced artifact rather than an orphaned file; (3) a new pre-commit hook (`scripts/check_html_authorship.py`) mechanically blocks any staged `.html` file with no `share_out: true` MD sibling and no explicit allowlist entry, closing the gap the original version of this ADR left as advisory-only.

## Considered Options

### A — Leave the boundary as strictly MD-only, no exception

**Pros:** Zero risk of reintroducing drift; simplest rule to hold.
**Cons:** Blocks a legitimate, explicitly-requested capability (agents rendering richer visual output — charts, plots, comparison tables — when a user asks for it) for no benefit, since the drift risk the rule guards against doesn't exist when there's no MD source to diverge from.

### B — Drop the boundary entirely for all agent-authored HTML

**Pros:** Maximally flexible.
**Cons:** Removes the boundary's real value for canonical surfaces too — nothing would stop an agent from hand-authoring a one-off HTML copy of `VERIFICATION_REPORT.md` instead of using the dashboard renderer, recreating the `dec-145`-flagged drift pattern by default rather than by exception.

### C (chosen) — Scope the boundary to canonical surfaces; carve out ephemeral, no-MD-backing, explicitly-requested output; enforce mechanically

**Pros:** Preserves the boundary's value where the drift risk is real; unblocks the capability where it isn't. The bounding conditions (no-MD-backing test, `.ai-work/`-or-`tmp/`-by-default, pre-commit guard) keep the exception from silently expanding into option B, and the guard means the boundary no longer depends solely on an agent remembering the rule.
**Cons:** Adds a judgment call ("does this have or deserve a canonical MD form?") rather than a bright-line rule — slightly harder to self-test than an unconditional prohibition. The guard is pre-commit-scoped, so it only catches the boundary at commit time, not at write time.

## Consequences

**Positive:** Agents can honor an explicit user request for richer HTML output (charts via `dataviz`, styled comparisons, plots) without a rule fight; the canonical-surface protection (and the concrete lesson from `dec-145`) stays intact; the enforcement gap the first version of this ADR left open is now closed by a mechanical guard instead of relying on agents reading and remembering an advisory rule.

**Negative:** The boundary is now conditional rather than absolute, which is a small amount of added interpretive surface for every future agent reading this rule. The guard is a pre-commit hook, not a `PreToolUse` write-time block — an agent can still *write* a stray `.html` file outside the ephemeral defaults; the guard only stops it from being *committed*, and only when pre-commit runs (skippable via `--no-verify`, same as every other hook in this repo's commit gate).

## Disconfirmation

- **Falsifier:** evidence that the exception itself was the wrong call — either the ephemeral case gets routinely abused (content that should have a canonical MD form keeps getting hand-authored as HTML instead, "no persistent MD backing" judged wrong in practice), or ephemeral output routinely needs to *become* persistent shortly after (showing the ephemeral framing was mistaken and a canonical path should have been used from the start). Either pattern would mean Option C's bounding conditions aren't actually distinguishing the cases they were designed to distinguish. (The guard script's own false-positive/false-negative liveness is a separate, narrower question — tracked in its own test suite, not this decision's falsifier.)
- **Steelmanned runner-up:** Option A (no exception) remains the simplest rule to hold and would have needed no guard at all — the guard's existence is itself evidence that Option C required more machinery than initially scoped, which is exactly the kind of complexity Option A avoids entirely.
- **Reversal trigger:** if `sentinel` or a future audit finds committed HTML with no MD source and no `share_out: true` frontmatter *despite* the guard being active (e.g., via `--no-verify` bypass or a gap in the guard's file-pattern matching), that is the signal to either harden the guard (a `PreToolUse` write-time check, not just pre-commit) or revert this exception.
