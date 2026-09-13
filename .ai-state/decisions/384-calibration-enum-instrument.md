---
id: dec-384
draft_id: dec-draft-86806483
title: The calibration instrument is the Retrospective enum, computed by a script; the tier-match check is retired
status: accepted
category: behavioral
date: 2026-09-13
summary: "Roadmap decision D2 as implemented: the calibration log's Retrospective enum (correct / over-calibrated / under-calibrated, [pending] as a non-verdict) is the sole calibration-accuracy instrument, its distribution is computed by scripts/check_calibration_coverage.py as sentinel family checks CA02 and CA03 rather than counted by the LLM, and the retired Recommended-vs-Actual tier-match check (CA02 as first written) is not brought back: it was self-graded by the agent that chose the tier and its 60% alarm could not fire against a 93% match rate. The retrospective prose stays the learning journal."
tags: [process-economy, roadmap-p2-6, calibration, sentinel, family-row, tech-debt]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/check_calibration_coverage.py
  - scripts/test_check_calibration_coverage.py
  - agents/sentinel.md
  - tests/test_sentinel_row_contract.py
  - .ai-state/calibration_log.md
affected_reqs: []
---

## Context

The process-economy roadmap (`docs/independent-analysis/process-economy-roadmap.md` §10 D2, settled) split the
calibration log into two things: the Retrospective enum written by the verifier at Standard/Full (the instrument) and
the retrospective prose (the journal). P0.6 shipped the enum and the cutover-dated validator; commit cd6a3fdb
(2026-09-07) rewrote sentinel CA02 from a Recommended-vs-Actual tier-match rate to an enum-distribution analysis, but
left it L-tier — the sentinel read the last 20 rows and counted by hand — and deleted the tier-match check without
saying why (`td-184` b). Measured on 2026-09-13: the 2026-09-12 sentinel run counted 6/20 under-calibrated by hand;
the script counts 7/20 on the next day's window; three rows on 2026-09-08 carried the token `well-calibrated`, which
the validator reported and nothing acted on; `[pending]` is sanctioned by the calibration procedure but was absent
from the script's enum list. CA02 cost 785 B / 222 tokens and CA03 866 B / 219 tokens of the sentinel definition.

## Decision

- The Retrospective enum is the only calibration-accuracy instrument. Its distribution over the last 20 post-cutover
  rows is computed by `scripts/check_calibration_coverage.py` (`CHECK_IDS = ("CA02", "CA03")`) and reported through
  the sentinel's Family dispatch table; CA02 and CA03 take the dec-382 family-row form and are registered in
  `EXTRACTED_CHECKS`, so the Triangle binds row, registry and script.
- Verdict tokens are `correct`, `over-calibrated`, `under-calibrated`. `[pending]` is a sanctioned non-verdict
  (not counted in the denominator, not a violation). Any other token is a non-canonical finding per row. Shares are
  over classified rows; the 25% band and the zero-variance alarm are unchanged from the L-tier wording; the check
  skips below 5 classified rows.
- The Recommended-vs-Actual tier-match check is retired and not replaced. Reason: `Recommended Tier` and
  `Actual Tier` are both written by the orchestrator that chose the tier, so a match is self-graded; the live rate was
  93% against a 60% alarm, so the check could not fire; the enum is written by the verifier at Standard/Full (an agent
  that read the finished plan and diff) and is the non-self-graded signal `td-184` asked for.
- The retrospective prose after the em-dash stays free text — the journal is not an instrument and is not parsed.

## Considered Options

### Keep the tier-match clause alongside the enum distribution (td-184's first remedy)

- Pro: no signal is deleted.
- Con: it is self-graded and structurally cannot alarm at the observed match rate; carrying a dead check costs
  sentinel bytes and a reader's trust in the dimension.

### Leave CA02 as an L-tier row

- Pro: no code.
- Con: the count is done by the LLM each run (two runs a day apart disagreed by one row on overlapping windows) and
  the row is the most expensive in the CA dimension; every other CA check is already a family row.

### Mechanise CA02 and CA03 as family checks over the existing script (chosen)

- Pro: deterministic count; one script already owns the log's parsing; the family form drops the row bytes; CA03 was
  already dispatched by sentence to the same script and joins the table for free.
- Con: two more registry entries and canaries to maintain; the envelope change nests the script's old flat JSON keys
  under `info` (the in-process hook consumer and CI's human mode are unaffected).

## Consequences

- Positive: calibration accuracy is measurable by a script with canaries and a mutation-probed 25% clause;
  `td-184` closes on both halves (the cutoff had already been moved to 2026-09-07); the enum list matches the
  procedure; the three non-canonical rows are normalised (`fd4fd78b`).
- Negative: the tier-match history in old sentinel reports is no longer comparable with new CA02 findings; the
  window of 20 rows is a fixed constant, not derived from the log's rate.
- Cost: the script and its test grow (declared limit: file-size ceiling 800 lines in `rules/swe/coding-style.md`);
  `agents/sentinel.md` shrinks by the difference between two prose rows and two family rows plus one table row
  (measured at commit time in the calibration row).
