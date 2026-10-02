---
id: dec-422
draft_id: dec-draft-0a4ae32a
title: A changed non-code file under .ai-state/ selects only the tests one hop away
status: accepted
category: behavioral
date: 2026-10-02
summary: "In Python test selection, a changed file under .ai-state/ that is not source code selects only the tests one hop away: those holding its path (suffix, glob or exact basename), holding a matching basename pattern, or declared for it. Nothing propagates from a production module that names it, so importers of that module and every test under a conftest.py importing it are no longer selected. A state file no test reaches directly is unaccounted for and widens to the full suite."
tags: [testing, test-selection, resolver, path-literal, ai-state, selection-size, never-under-select]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/_python_selection.py
  - scripts/test__python_selection.py
  - tests/declared-deps.toml
  - skills/testing-strategy/references/test-selection.md
affected_reqs: []
---

## Context

dec-406 derives test selection from four edge sources and reverse reachability; dec-411 already stopped basename patterns from propagating, because fan-out through production holders selected most of the suite. td-296 tracked the remaining size: the narrow median selection was 36% of the root pocket against a 25% trigger.

A spike traced the suite and found the main amplifier. `scripts/state_ledger_schema.py` names the ledger files under `.ai-state/`; `_ledger_triage_testkit.py` imports it and `scripts/conftest.py` imports that, so any `.ai-state/` change selected about 175 `scripts/` tests. Those tests exercise the schema against fixture ledgers under a temp directory. The live ledger is read by the production module at run time, never by them, so its content cannot change their outcome. Pipeline state commits change `.ai-state/` files on almost every pipeline boundary, so this one path dominated the median.

## Decision

1. A changed path under `.ai-state/` whose suffix is not a source suffix of any pocket ecosystem stops after the first hop of the reachability search. It selects the runnable tests among its direct dependents of every edge kind (layout, import, path-literal, declared) and its basename-pattern test holders, with the usual attribution. No dependent is expanded.
2. The accounting rule is unchanged: a state file that reached a test is accounted for; one that reached none is unmapped and widens to the full suite.
3. Source code under `.ai-state/`, and every path outside it, keep transitive reach.
4. The directory is a module constant (`STATE_DIR`), not a declared-deps entry kind: `.ai-state/` is the convention every Praxion-managed project shares, and a new entry kind would need a schema bump for one value.

Companion data edits, no decision of their own:

- The `rules/**/*.md` + `skills/**/*.md` entry of `tests/declared-deps.toml` was pruned from 53 test files to the 13 traced reading that corpus, with the evidence and the re-derivation route recorded beside the entry.
- The selection audit, run on this change, found the one test that read live state only through the fan-out: the ledger gate's live-tree check, which reads every top-level `.ai-state/*.md`. Its declared entry now names that glob instead of five files.

## Considered Options

### Hardcoded state directory, one hop (chosen)

- Pro: about 12 lines in `_reach`; closes the largest lever measured; the tests that read live state hold its path and stay selected.
- Con: the resolver now knows one Praxion directory name.

### A declared-deps "no fan-out" entry kind

- Pro: general; any project could mark its own live-state directories.
- Con: a schema bump and a parser change for one value Praxion's own convention already fixes.

### Drop production-held path literals

- Pro: td-296's original proposal; smaller selections everywhere.
- Con: measured by the spike at 34 real extra misses; the cost is the fan-out, not the literal.

### Cut conftest fan-out from literal-reached nodes

- Pro: addresses p90 as well as the median.
- Con: a conftest that reads a data file is a real dependency of every test using it; one real extra miss measured.

## Consequences

- Positive: measured over one 303-file tree with both edits, the narrow median drops from 34.2% to 12.7% on the spike's 50-commit window (ending `a79d4e04`) and from 24.4% to 8.9% on the recent one (ending `39ebc23d`), with the same number of widened runs (6 and 4). Figures in `skills/testing-strategy/references/test-selection.md` § Selection-Size Baseline.
- Positive: the guard is mechanical. The weekly selection audit (dec-420) traces every test's direct and child-process reads; a test that reads a live state file it does not hold or declare is reported as unselected.
- Negative: a test that reads live state through a production module, without holding the path, is no longer selected for that file until it holds the path or is declared. The audit reports it; until then the full suite at push backstops it.
- Negative: a state file only production code names now widens instead of selecting importers. That is the conservative direction.
- Reversal trigger: the selection audit reports an unselected read of a `.ai-state/` file whose fix is not a missing literal or declared entry, or state commits start widening more often than they did before.
