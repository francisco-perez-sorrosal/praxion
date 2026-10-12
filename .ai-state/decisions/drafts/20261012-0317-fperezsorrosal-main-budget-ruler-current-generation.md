---
id: dec-draft-0b5f22b8
title: The always-loaded budget counts on the current-generation tokenizer and keeps its 25,000 ceiling
status: accepted
category: behavioral
date: 2026-10-11
summary: "scripts/measure_token_budget.py counts with claude-sonnet-5-5, the ruler /context uses, instead of claude-sonnet-4-5, which read 65% of the ceiling while the models in use saw 94%; the 25,000 ceiling stays (user decision). Samples and the frozen listing ceiling name their ruler; a ceiling frozen on another ruler is not compared, a recording ratchet run re-freezes it at today's reading with a note and a read-only run skips it. This repository's listing ceiling re-froze from 9,243 to 14,268 and the governed set reads 24,729 tokens."
tags: [token-budget, tokenizer, ruler, ratchet, listing-ceiling, startup-context, gate]
made_by: user
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/measure_token_budget.py
  - scripts/test_measure_token_budget.py
  - .ai-state/token_budget_baseline.json
  - rules/CLAUDE.md
  - skills/rule-crafting/SKILL.md
affected_reqs: []
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
---

## Context

The budget gate counted real tokens, which was the whole point of its design, but on the tokenizer of the model generation it was written against. Current models count the same bytes about half again higher. The startup-context spike measured the gap: the governed set read 16,197 tokens (65% of 25,000) on the gate's ruler and 23,581 to 24,729 on the rulers the models actually use. The guard had been reporting headroom that did not exist, and every always-loaded addition since had been admitted against it. Phase 0 added a report-only `--model` reading; the ceiling itself was left as a user decision.

## Decision

- `_MODEL` is `claude-sonnet-5-5`, the tokenizer `/context` reports with. `_LEGACY_RULER` names the previous one for baselines recorded before this change.
- The ceiling stays at 25,000. The headroom this leaves, 271 tokens today, is the intended pressure: every always-loaded addition now fails the gate until Phase 3 moves procedure out of residency. Raising the ceiling to preserve the old reading would have kept the number and lost its meaning.
- Every sample and the frozen listing ceiling carry a `ruler`. A ceiling frozen on another ruler is never compared to today's reading: a recording `ratchet()` run (the commit gate) re-freezes it at today's listing on the current ruler and says so in a note; a read-only run skips the comparison with a note. Managed projects therefore re-base themselves on their next commit after the plugin update, with no manual step and no false block.
- `--model` keeps giving a report-only reading on any other ruler, refused alongside `--ratchet`.

## Considered Options

### Keep the old ruler and treat `--model` as the honest side reading

Rejected: the gate would keep admitting content against a reading one third too low, and every reader would have to remember which number is real.

### Switch the ruler and raise the ceiling to about 37,000

Rejected: it preserves the old verdicts, which were the problem. The ceiling was set as a real-token attention guardrail; the diet's purpose is to go down, so the tight ceiling is the ratchet wanted.

### Switch the ruler and keep 25,000 (chosen)

Pros: the number means what it says; the pressure lands exactly where Phase 3 is aimed; managed projects re-base without a manual step. Cons: no always-loaded addition can land before Phase 3 without an equal removal, which is the intended behaviour and the strongest objection.

## Consequences

- This repository reads 24,729 of 25,000 (98.9%) on the gating ruler; the listing ceiling re-froze from 9,243 to 14,268.
- Readings on `claude-opus-5-5` run about 1,150 tokens lower than on `claude-sonnet-5-5` for the same bytes; the gate pins one ruler so the ceiling has one meaning.
- The byte-based trend of the ratchet is untouched: bytes need no ruler, which is why the trend compared bytes in the first place.
- The next generation change is a visible re-freeze in the baseline diff, never silent headroom.
