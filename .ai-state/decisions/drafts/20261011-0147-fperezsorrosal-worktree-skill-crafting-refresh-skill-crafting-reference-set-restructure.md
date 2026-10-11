---
id: dec-draft-911fdeba
title: The skill-crafting reference set gains three pages and folds two into the content-guidance page
status: proposed
category: architectural
date: 2026-10-11
summary: "skills/skill-crafting gains description-optimization.md, evaluating-skills.md and scripts-for-agents.md; output-patterns.md and workflows.md are deleted and their content, with the entry page's multi-file design patterns, moves into content-and-development.md; script guidance moves to scripts-for-agents.md and the per-host field matrix to cross-agent-portability.md, leaving an entry page under 400 lines in the canonical topic order."
tags: [skill-crafting, progressive-disclosure, references, authoring-canon]
made_by: agent
agent_type: systems-architect
branch: worktree-skill-crafting-refresh
pipeline_tier: standard
affected_files:
  - skills/skill-crafting/SKILL.md
  - skills/skill-crafting/README.md
  - skills/skill-crafting/references/description-optimization.md
  - skills/skill-crafting/references/evaluating-skills.md
  - skills/skill-crafting/references/scripts-for-agents.md
  - skills/skill-crafting/references/content-and-development.md
  - skills/skill-crafting/references/output-patterns.md
  - skills/skill-crafting/references/workflows.md
  - skills/skill-crafting/references/cross-agent-portability.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-13]
supersedes:
superseded_by:
re_affirms:
re_affirmed_by:
dissent: "Keeping output-patterns.md and workflows.md as small single-topic pages would cost two links and keep the content page short."
---

## Context

The skill-crafting entry page was 423 lines (past the 400-line prompt-size warn line), taught the canon in an order that put layout before invocation modes, and lacked the evaluation, description-tuning and agent-facing script guidance the current canon grades as load-bearing. Two small pages (`output-patterns.md`, 85 lines; `workflows.md`, 48 lines) held patterns that belong with the content-type guidance, and the entry page carried about 95 lines of multi-file design patterns and a per-host field matrix that are reference depth, not entry-page guidance. No file outside the skill linked either small page or any moved heading.

## Decision

Add three reference pages: `description-optimization.md` (measured trigger-tuning loop and plugin-eval trigger cases), `evaluating-skills.md` (the open-standard `evals/evals.json` format and the `claude plugin eval` case layout, stated as not interchangeable) and `scripts-for-agents.md` (the agent-facing script contract, receiving the content page's executable-code section). Delete `output-patterns.md` and `workflows.md`; their paragraphs move verbatim into `content-and-development.md`, which also receives the entry page's design patterns and opens with a contents list. Move the per-host field matrix to `cross-agent-portability.md`. Rebuild the entry page in the order invocation modes, eval-first loop, degrees of freedom and gotchas, scripts, lifecycle, layout, validation, portability, checklist, with every reference page one hop away.

## Considered Options

### Keep the two small pages, link them from the content page

Smallest diff. Leaves three homes for content-pattern guidance and keeps two entry-page links to pages a reader reaches only for a template or a workflow example.

### Fold into content-and-development, add the three named pages (chosen)

One home per topic; the entry page drops roughly 140 lines; no page the brief does not name is created.

### A new patterns page for templates, workflows and design patterns

A cleaner topical split than an enlarged content page, but it adds a page the brief did not ask for and splits content-type choice from the patterns that realize it.

## Consequences

**Positive:** the entry page lands under 400 lines, removing a prompt-size warn; each topic has one home; the eval and description guidance a skill author needs is reachable in one hop.

**Negative:** `content-and-development.md` grows to roughly 400 lines (half the reference-page ceiling) and needs a contents list; two paths are retired.

## Disconfirmation

- **Falsifier:** an agent following the rebuilt skill (author-tester run or the plugin eval) misses template or workflow guidance it reached before, or reads `content-and-development.md` partially and misses a folded pattern.
- **Steelmanned runner-up:** a dedicated patterns page. It keeps each reference page under 200 lines, which suits partial reads, and separates "which content type" from "how to shape it".
- **Reversal trigger:** `content-and-development.md` passes 500 lines or a navigation observation shows agents not finding folded patterns; then split the patterns into their own page.
