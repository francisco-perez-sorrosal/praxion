---
id: dec-draft-f9172fe4
title: Canary coverage is enforced per check via call-graph matching, additively over the file-level rule
status: proposed
category: architectural
date: 2026-07-31
summary: The canary-coverage meta-test gains an AST pass requiring each module-level check_* function to be called by a canary-named test; the file-level rule is retained unchanged, and one check equals one named function.
tags: [gate-liveness, canary, scope-fidelity, fitness, meta-test]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-integrity-and-overlay
pipeline_tier: full
affected_files:
  - fitness/tests/test_gate_canary_coverage.py
  - fitness/tests/test_discipline_registry_invariants.py
dissent: >
  Requiring a canary to CALL its check makes coverage exact but also makes it impossible to
  credit a canary that drives a check through the CLI or through a wrapper, which is how
  several script gates are legitimately exercised; a name-based relation would credit those
  and cost nothing, at the price of being a convention rather than a proof.
---

# Canary coverage is enforced per check via call-graph matching, additively over the file-level rule

## Context

`fitness/tests/test_gate_canary_coverage.py` answers "does this *file* contain a
canary-named test", returning one boolean per file. A new check added to a file that already
carries canaries is therefore invisible to it — which is the normal way checks get added.
The failure was observed concretely: a six-check gate specification shipped with eleven
canaries and one check uncanaried; the meta-test stayed green, and the gap was found only by
stubbing each check in turn and watching which produced zero reddened tests.

Upstream of that, five gates in `fitness/tests/test_discipline_registry_invariants.py`
assert inline in a test body with no extractable function at all, so they are invisible not
merely to canary coverage but to enumeration itself — the per-check remedy cannot see a
check that has no definition to discover.

This is the scope-fidelity clause applied to the meta-gate: its computed unit (files) is
narrower than its documented purpose (gates bite).

## Decision

**The coverage unit becomes the check, additively.**

- `gates_without_canary()` keeps its file-level rule **unchanged**. Gate files that define
  no `check_*` / `validate_*` function are evaluated exactly as today.
- When a gate file defines module-level `check_*` / `validate_*` functions, each such
  function additionally requires **at least one canary-named test that calls it**. Findings
  are reported as `<relpath>::<check_name>`.
- The coverage relation is **call-graph**, resolved by AST — a canary "exercises" the check,
  which is checkable, rather than "names" it, which is not enforceable without dictating test
  names.
- **Call detection resolves both `name(...)` and `module.name(...)` forms.** This is a
  correctness requirement, not an optimisation: a matcher handling only bare names reports
  `scripts/check_gate_liveness.py::check_forbidden_pattern` as uncovered, when its canary
  drives it as `gl.check_forbidden_pattern(tmp_path)`. Measured across every gate file
  before the extraction work, the true state was **19 of 19 discoverable checks covered**;
  a `Name`-only matcher would have manufactured a violation on the first real gate it
  examined. Re-measured after the extraction landed: **27 of 27 covered** (23 in
  `test_discipline_registry_invariants.py`, 2 in `test_consult_append_only.py`, 1 in
  `test_meta_citation.py`, 1 in `check_gate_liveness.py`), still zero uncovered.
- The search scope for a covering canary is the gate file itself (fitness convention) plus
  the existing `_canary_candidates()` siblings (script and hook convention), reusing the
  current resolver rather than introducing a second one.

**One check equals one named function.** The five inline-asserting gates are extracted into
named module-level functions. Extraction is by *defect class*, not by test: one of the five
bundles two distinct concerns and yields two checks, for six in total. Bundling them behind
one name would reproduce the same defect one level down — a check whose canary exercises only
one of its branches.

## Considered Options

### Option A — Replace the file-level rule with the per-check rule (rejected)

Cleaner conceptually: one unit, no dual mechanism. Rejected because most script and hook
gates express their check as `main()` and define no `check_*` function at all; replacing the
rule would silently drop them from coverage entirely, trading a narrow blind spot for a wide
one. The additive form preserves every currently-enforced obligation and only adds.

### Option B — Name-based matching (canary name must contain the check name) (rejected)

Cheap, no AST, and credits canaries that drive a check indirectly. Rejected because it is a
naming convention masquerading as a proof: a test named `test_flags_registry_row_shape` would
satisfy it while asserting something else entirely, and enforcing the convention would
dictate test names in a way `rules/swe/testing-conventions.md` explicitly rejects (names
describe behaviour, not identifiers).

### Option C — Ship the per-check rule without extracting the inline gates (rejected)

Half the value at a third of the cost. Rejected because the inline gates are the population
the rule most needs to reach — they have never been observed to fail, and four of them still
have not. Shipping the rule while leaving them undiscoverable would let the meta-test report
full coverage over a population that excludes the least-verified members.

### Option D — Extract the inline gates without upgrading the meta-test (rejected)

Makes them enumerable but not obligated. The next check added to that file would be invisible
again on the next pass.

## Consequences

**Positive.**

- A check added to an already-canaried file is now visible to the meta-test — closing the
  normal way checks get added.
- The relation is exact rather than heuristic: a canary either calls the check or does not,
  and the answer is derivable from the source.
- Zero red on landing. Measured across `fitness/tests/test_*.py`, `scripts/check_*.py`,
  `scripts/validate_*.py`, `hooks/*_gate.py`, `hooks/*_guard.py` and `hooks/remind_*.py`, all
  19 discoverable checks were already covered once attribute calls resolve — 27 of 27 after
  the extraction work landed. The rule becomes load-bearing for the six newly extracted
  checks and every future one, not for a backlog.
- The policy skip set (`_SKIP_GATE_STEMS`, `_SKIP_FITNESS_FILES`) is **not** applied to the
  check-level pass. Every entry in it was excused because the file already carries a canary
  somewhere, which is exactly the reasoning this unit exists to distrust. Verified at
  authoring time that none of the excused stems declares a module-level `check_*` function,
  so dropping the exclusion adds no obligation today and makes adding one non-free.
- Extraction makes the five previously-inline gates reachable by the neutering proof, which
  is the only way to demonstrate that four of them bite at all.

**Negative / accepted.**

- A dual mechanism: files with checks are evaluated one way, files without another. Mitigated
  by the rule being additive and by the file-level path being literally unchanged code.
- A canary that drives its check through the CLI or through a wrapper is not credited, and
  its author must either add a direct call or restructure. This is a real cost paid by
  script gates whose canaries exercise `main()`; today none of them define `check_*`
  functions, so none are affected, but that is a fact about the present corpus rather than a
  guarantee.
- The gate file grows by roughly 140 lines in a file already 3.8× over the size ceiling.
  Accepted deliberately; a split is recommended separately and is not this change.

## Disconfirmation

**Falsifier.** If a check is ever found to have a passing per-check coverage entry while
neutering it reddens zero tests, the call-graph relation is not measuring what it claims —
a canary can call a check and assert nothing about its return. Symmetrically, if the rule
produces a false violation for a legitimately-exercised check in a form the matcher does not
resolve (a call through `getattr`, a partial, a parametrized dispatch table), the exactness
claim is overstated and the matcher needs either broadening or an explicit waiver route.

**Steelmanned runner-up.** Option B — name-based matching — is stronger than it appears.
Call-graph exactness buys precision the meta-test does not obviously need: its purpose is to
*prompt* an author to write a canary, not to certify that the canary is good, and canary
adequacy has already been shown to be independent of canary count (a check with four
reddening tests still failed open). A convention that costs no AST and credits indirect
exercise may be the better instrument for a prompt. Call-graph matching wins here only
because it is provable and because the extraction work makes direct calls the natural shape
in the one file that carries most of the checks.

**Reversal trigger.** Revisit when any of: (a) a legitimate check is exercised through a
call form the matcher cannot resolve, forcing either a waiver mechanism or a broader
relation; (b) script gates begin defining `check_*` functions exercised only through
`main()`, which makes the accepted cost above concrete rather than theoretical; or (c) a
check with satisfied per-check coverage is shown by neutering not to bite, which would move
the whole enforcement question from coverage to adequacy.
