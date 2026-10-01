---
id: dec-draft-394f2685
title: Slash-less wildcard literals select only their test holders and account only for data files
status: proposed
category: behavioral
date: 2026-09-29
summary: "In Python test selection, a slash-less string literal with a wildcard and at least one letter or digit outside its wildcards becomes a basename pattern. It selects only holders that are themselves runnable test modules, directly from a changed file, and nothing propagates from a holder; it is attributed path-literal and suppresses the unmapped-path widen only when the changed file is a data file. A source file (extension in the per-ecosystem SOURCE_SUFFIXES table) reached only through such a pattern widens as if the literal did not exist. A wildcard literal with no letter or digit outside its wildcards (*, .*, *.*, [a-z]*) is ignored."
tags: [testing, test-selection, resolver, path-literal, widening, never-under-select]
made_by: agent
agent_type: systems-architect
branch: worktree-selection-gaps-dogfood
pipeline_tier: standard
affected_files:
  - scripts/_python_selection.py
  - scripts/_test_inventory.py
  - skills/testing-strategy/references/test-selection.md
affected_reqs: [REQ-04, REQ-05, REQ-06, REQ-07, REQ-10]
---

## Context

dec-406 made test selection derived: four edge sources, reverse reachability, and a widen to the full suite for any changed path that reaches no test. One of the sources is path literals. A slash-less literal was filed as an exact basename before the wildcard check, so a pattern such as `*.md` never matched anything (td-291). When nothing else mapped the file, the resolver widened, which was loud but correct. When anything else mapped it, the pattern's reader was dropped without a trace.

Taken literally, the ledger remedy ("treat a slash-less wildcard literal as a basename glob") runs into two problems:

- **Reach.** Praxion holds `"*"` in 34 modules, `"*.md"` in 33 and `"*.py"` in 8. A glob that joins the ordinary path-literal edge set fires at every node the reachability search visits, and every intermediate node there is a Python module. So a `*.py` holder would become a dependent of almost every change.
- **Safety.** A match that counts as covering the changed file suppresses the `unmapped-path` backstop. A pattern that matches most files, or matches code, would switch the backstop off for changes whose real readers are unknown.

The user settled the intent in the spec (SQ-01): the reader is always selected; the match accounts for the changed file only when that file is a data file, not source code of a pocket ecosystem ("data files narrow, code widens"). A literal made only of `*` and `?` names no file. At the architecture checkpoint the user widened that last rule: a wildcard literal needs a letter or digit outside its wildcards, so the regex `".*"` (held by two modules here) and `*.*` cannot account for every dotfile or every file with an extension. Re-measurement before merge then led to a late Spec Question (SQ-02), and the user restricted pattern readers to test holders with no propagation; see Consequences.

## Decision

1. **Literal classes.** Each string constant, normalized, falls into exactly one class:
   - ignored: empty, `.`, or a wildcard literal with no letter or digit outside its wildcards (`*`, `**`, `?`, `.*`, `*.*`; letters inside a bracket class do not count, so `[a-z]*` is ignored too)
   - exact basename: no slash and no wildcard (unchanged)
   - basename pattern: no slash, has a wildcard and a letter or digit outside it (new)
   - path suffix: has a slash, no wildcard (unchanged)
   - path glob: has a slash and a wildcard (unchanged)
2. **Test holders only, no propagation.** A basename pattern selects its holder only when the holder is a runnable test module, and only for a *changed* path whose basename matches it, at the `path-literal` rank. The holder is never expanded, so no test is selected because it reaches a holder, and a production module holding a pattern selects nothing through it. The other literal classes keep their current transitive behavior.
3. **Data-only accounting.** A changed path counts as accounted for when it reaches a test. The exception is a source-code path: it counts only if it still reaches a test with its basename-pattern readers removed. Source code means a file whose suffix is in `SOURCE_SUFFIXES`, a per-ecosystem table in `scripts/_test_inventory.py` (python, typescript including `.vue` and `.svelte`, rust, go, jvm). The same table feeds the JS test-name convention and the native module-graph suffix set.
4. **Selection is the union.** The tests a basename pattern reaches are always selected, with `via: path-literal` and `because: <changed path>`, whether or not the changed path is accounted for.

## Considered Options

### Option A: basename patterns join the transitive path-literal edge set; accounting filters out pattern edges on source nodes everywhere in the search

- Pro: uniform with the other literal classes; there is one kind of path-literal edge.
- Con: every visited Python module runs every pattern, and matches `*.py` / `test_*.py` / `*.*` holders. That inflates selection for nearly every Python change, while the selection-size trigger already fires (median 36% vs 25%, td-296).
- Con: the edge means "the holder reads files named like this". An intermediate module's *text* did not change, so the holder's input did not change either. The extra tests are over-selection with no evidence behind them.
- Con: accounting needs an edge filter keyed by node kind across the whole search, which adds complexity to every step of the search.

### Option B: first-hop basename patterns with data-only accounting (chosen)

- Pro: patterns match only against changed paths, so the cost and reach are bounded by the change set.
- Pro: accounting is one check on the changed path (re-run the reach without its own pattern readers, only for source paths that have any), and it is exactly REQ-10's "as if the literal did not exist".
- Con: slash-less patterns behave differently from slash-containing globs, which stay transitive.

### Option C: the ledger's literal remedy, filing slash-less wildcards into the existing path-glob list

- Pro: smallest diff.
- Con: transitive and blind to accounting. A source file reached only by `*.py` would narrow instead of widen (violates REQ-10), and the reach problem from Option A applies unchanged.

## Consequences

- Positive: td-291 is closed without widening the blast radius of patterns beyond the files that actually changed. The backstop still fires for code. REQ-07 keeps a stray `"*"` from covering everything.
- Negative: data files matched by regex-shaped literals could get false readers. The main case was `".*"` held by `hooks/remind_adr.py` and `scripts/measure_token_budget.py`, which as a glob matches every dotfile basename. The user closed it at the architecture checkpoint: a wildcard literal needs at least one letter or digit outside its wildcards, so `.*` and `*.*` are ignored like a lone `*`. A regex literal that does carry a letter or digit can still act as a pattern; the integration-checkpoint and scheduled audits (`audit_tests.py`) are the backstop, and a recurring miss is the reversal signal below.
- Negative: slash-less patterns and slash-containing globs differ in reach. The published contract states it (`skills/testing-strategy/references/test-selection.md`).
- Negative, then narrowed: as first designed, a pattern's first hop reached any holder and the search continued through named edges from it. Re-measured before merge, that raised the median narrow selection from 36% to 82% of the root pocket's test files, because `*.md` is held by 35 production scripts and most changes here touch Markdown. The user chose to narrow it: a pattern selects only holders that are themselves test modules and never propagates from them (measured 37%). A test that reads files by pattern still runs; a production script's tests do not run merely because the script globs the changed file's type.
- Neutral: selection sizes move (markdown changes select the `*.md` holders that are tests). They are re-measured with the published baseline method before this decision is considered settled, and the result feeds td-296.

Activation: fired. Tier standard; blast radius of at least 5 files across the selection scripts and the published contract; two plausible paths (A vs B). Lens set: simplicity, performance, testability, safety (never-under-select). Convergence: B dominates on simplicity and performance, ties on testability, and is equal on safety for the changed-file semantics REQ-10 fixes; A wins only on uniformity. Converged on B.

**Reversal triggers:**
- The audit records a `missed` failure traced to a data file that a basename pattern accounted for. Revisit with a Spec Question about regex-shaped literals.
- The re-measured median narrow selection rises by more than 5 points of the corpus. Revisit whether `*.md`-class patterns should account at all.
