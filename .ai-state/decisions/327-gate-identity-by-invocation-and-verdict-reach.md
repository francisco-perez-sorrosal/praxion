---
id: dec-327
title: Identify gates by invocation shape; mechanise verdict-reach on one surface only
status: accepted
category: implementation
date: 2026-08-06
summary: Gate-set discovery keys on what runs a script, not what it is named; the discarded-verdict check ships for hook registrations alone, the two wider formulations having measured a 100% false-positive rate.
tags: [gate-liveness, detector, canary-coverage, false-positives, scope-fidelity]
made_by: agent
agent_type: orchestrator
branch: fleet-quality-remediation
pipeline_tier: lightweight
affected_files:
  - scripts/check_gate_liveness.py
  - scripts/test_check_gate_liveness.py
  - fitness/tests/test_gate_canary_coverage.py
  - rules/swe/gate-liveness.md
---

## Context

Two ledger rows converge on one defect. `td-131`: the Gate Liveness rule states seven
clauses and the detector mechanises three, so a remediation session found six instances of
a single shape — *a correct signal that never reaches a decision* — and the detector caught
none. `td-129`: the canary-coverage meta-test and the `uninvoked-gate` check both identify a
gate by a `check_*`/`validate_*` **filename**, while `scripts/sync_canonical_blocks.py` is a
real pre-commit gate whose `--check` mode blocks a commit. Its `sync_*` name placed it
outside both, so neither its invocation nor its canary coverage was ever asserted.

`td-131` sketched three mechanically decidable shapes for a fourth check. The premise worth
testing was not whether they were implementable but whether they would fire on correct code:
a detector that does trains its readers to ignore every row it emits, which costs more than
the defect it names.

## Decision

**Two changes, one principle: a gate is what something *runs* with its exit code
load-bearing, and its verdict must be able to reach a decision.**

1. **Gate identity by invocation shape.** `fitness/tests/test_gate_canary_coverage.py`
   unions a third discovery route onto the filename glob and the sentinel-dispatch set:
   any Python script a `.pre-commit-config.yaml` `entry:` runs. `check_gate_liveness.py`'s
   `uninvoked-gate` adds hook guards and gates (`hooks/*_gate.py`, `*_guard.py`, `*_gate.sh`)
   to its **candidate-gate inventory** — a scope distinct from `ambient-import`'s exclusion
   of `hooks/` as **call sites**, which stands unchanged and is correct for its own reason
   (a hook resolves its own interpreter). One exclusion had been standing in for both.
   `sync_canonical_blocks.py` is **not** renamed: a rename relocates the boundary and
   touches every invocation site without removing the accident.

2. **`discarded-verdict`, scoped to hook registrations only.** A gate with a findings exit
   of 1 registered in `hooks/hooks.json` under an event whose contract blocks only at exit 2,
   routed neither through `commit_gate.sh --blocking` nor exiting 2 itself, computes a
   verdict nothing can act on. This is one of `td-131`'s three sketched shapes — "an
   invocation whose exit code is swallowed" — narrowed to the single surface where it is
   decidable with no false positives. The other two are **not** implemented.

**The new check gets a named consumer, because it would otherwise be the seventh instance of
its own finding.** No sentinel GL id is allocated (`agents/sentinel.md` enumerates GL02/GL04/GL05
by name and was out of this change's scope), so the required reader is
`test_check_gate_liveness.py::test_the_live_repo_discards_no_gate_verdict`, a real-repo
assertion that reddens the root suite. Allocating a GL row later adds a second reader; it
does not replace this one.

## Considered Options

### A. Ship all three sketched shapes (rejected — measured)

Each was prototyped and run against the live repository before any code was written:

| Shape | Findings | True positives | Why rejected |
|---|---|---|---|
| CI step under `continue-on-error` with no `steps.<id>.*` reader | 2 | 0 | Both hand their verdict to a downstream reader **through a file**; modelling that needs step-level dataflow |
| Gate whose exit status is lost in a pipeline / `\|\|` suffix | 2 | 0 | One is `\|\| (echo … && exit 1)` — message-then-fail; the other an `xargs` where the gate *is* last |
| Gate writing a path a later gate overwrites in the same chain | unmeasurable | — | The finalize chain invokes through shell variables; no literal paths to correlate |
| Declared consumer naming a different module than the one written | 0 | 0 | Only four parseable claims repo-wide — too little signal to justify prose parsing |
| `subprocess.run` on a gate without `check=` | 0 | 0 | No grounded instance, and a large future false-positive surface |

A 100% false-positive rate on the two that fired is the finding, not a tuning problem.

### B. Rename `sync_canonical_blocks.py` to `check_canonical_blocks.py` (rejected)

Restores the filename convention and requires no detector change. But it touches every
invocation site, and the next gate named for what it *does* rather than what it *checks*
reproduces the gap immediately. It treats the symptom.

### C. Widen the meta-test to every gate including shell (rejected for now)

`scripts/diagram-regen-hook.sh` is a real pre-commit gate. Its canary exists at
`tests/test_diagram_regen_hook.sh` in `tN_*()` shell functions, which this meta-test's
`def test_*` canary contract cannot read. Grading it needs a second canary convention.
The `.py` restriction is kept and **stated with its reason in code**, which is the whole
difference from the prefix boundary it replaces: one residual is named, the other was silent.

### D. Chosen: invocation-shape identity + one narrowly-scoped verdict check

## Consequences

**Positive.** `sync_canonical_blocks.py` and `regenerate_rules_manifest.py` are now inside
the canary-coverage boundary; both already satisfied it, so the widening costs nothing today
and asserts what was previously only true by luck. An orphaned hook guard is now reportable.
`discarded-verdict` measures 0 findings with 0 false positives, and is false-positive-free
*by construction* — a hook with no exit-1 path has no verdict to discard, so a deliberately
advisory reminder is silent because of what it is, not an exemption carved for it.

**Negative.** Four of `td-131`'s five candidate shapes remain unmechanised; the rule is still
ahead of its enforcement, just less so. The shell-gate residual (option C) stays open.
`discarded-verdict` has one reader where the sibling checks have two.

**Neutral.** `rules/swe/gate-liveness.md` is **path-scoped**, not always-loaded — its
`paths:` frontmatter keeps it out of the always-loaded set, so this edit moves the budget by
zero. The rule needed no new clause: *existence is not operation* already names "a gate whose
failure prints as a non-blocking warning". This mechanises an existing clause rather than
adding one.

## Disconfirmation

**Category falsifier (the test that decided `implementation` over `architectural`).** Name the
component added, removed, or whose responsibility moved. None can be named: `check_discarded_verdict`
is a function inside an existing script, both gate-set predicates are input-set changes inside
two existing components, and no canonical block, shipped template, or onboard-contract phase
changes. The component inventory and its boundaries are identical before and after — so
however consequential the trade-off, the category is not `architectural`.

**Falsifier for the decision itself.** If the next two or three gate-liveness defects found in
this repository are verdicts discarded on a *CI* surface rather than a hook registration, the
scoping was wrong: the false-positive rate would have been the price of covering where the
defects actually live, and the correct response is to model file-mediated verdict transport
rather than to keep the narrow scope.

**Steelmanned runner-up (option B, rename).** The convention exists because it works: a reader
seeing `check_*` knows the exit code matters, and every discovery route in the repo — this
detector, the meta-test, the sentinel — gets it free. Deriving the set from invocation sites
means three routes to keep in sync instead of one convention to follow, and a gate invoked
from a surface none of the three parses is still invisible. The rename is one commit and
restores a single source of truth. It loses on one point only: it presumes every future gate
author knows the convention, and the instance that produced this row proves that presumption
already failed once.

**Reversal trigger.** Revisit if a fourth discovery route becomes necessary (a gate invoked
only from a workflow `run:` block, say), which would mean invocation-shape discovery is
accumulating routes faster than the convention accumulated exceptions. Revisit the scope of
`discarded-verdict` the first time it is observed firing on correct code.
