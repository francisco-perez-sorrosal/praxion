---
id: dec-388
draft_id: dec-draft-15ec5a75
title: "A per-step mutation sensor: one stdlib runner owning the recipe, one bounded TEST_RESULTS line, one planner tag — sensor, never a gate"
status: accepted
category: architectural
date: 2026-09-20
summary: "Adds scripts/mutation_sensor.py, a stdlib-only, PATH-installed runner that encodes the P3.6 spike's eight-point mutmut recipe for the flat scripts/ layout, invokes mutmut 3.8.0 via uv run --with (no dependency change, uv.lock untouched), and prints one bounded line the producer copies verbatim into TEST_RESULTS.md. The TEST_RESULTS.md schema gains one optional line with two shapes (a reading and a reasoned refusal); IMPLEMENTATION_PLAN.md steps gain a planner-owned mutation: on tag with review:'s precedence and default-off zero cost; verifier Phase 10 gains three dispositions and still runs nothing. Totals come from mutmut export-cicd-stats' JSON and attribution from mutmut results' text — never from the carriage-return-rewritten progress line. Exit 0 on any survivor count, exit 2 with a closed reason code when the run cannot be trusted; v1 supports the flat-directory layout only."
tags: [process-economy, roadmap-p3-6, mutation-testing, test-results, verifier, coverage-gap, evidence-standard, quality-guard, sensor-not-gate]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p3-6-adopt
pipeline_tier: standard
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17, REQ-18, REQ-19, REQ-20]
re_affirms: dec-378
affected_files:
  - scripts/mutation_sensor.py
  - scripts/test_mutation_sensor.py
  - scripts/test_compose_handoff.py
  - scripts/test_check_test_results_shape.py
  - scripts/test_reconcile_pipeline_state.py
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/software-planning/references/document-templates.md
  - skills/software-planning/references/decomposition-guide.md
  - skills/testing-strategy/references/python-testing.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/verifier.md
  - .ai-state/DESIGN.md
  - .gitignore
dissent: "Tag-only means RISKY coverage is convention, not machinery: a planner that forgets to tag produces silence, and silence is indistinguishable from 'nothing survived' to every reader who does not also check the tag. The design accepts this deliberately — an auto-fire rule would need a 'does this step perform a world read' classifier that would be wrong by default on its first pipeline — and bounds it with a named reversal trigger (two consecutive Standard/Full pipelines with zero tagged steps converts the tag to an auto-signal with mutation: off as the escape hatch, a strictly additive change)."
---

## Context

Roadmap item P3.6 ran as a Spike (`process-economy-p3-6`) and decided **ADOPT, scoped**. The evidence was a
replay of a real verifier finding: at `913d87d8`, `scripts/_handoff_readiness.py` had 83 mutants, 68 killed and
**15 survivors, all 15 inside `dirty_paths()`** — the untested `git status --porcelain` read whose fail-open
defect the verifier caught as F1 by hand. The mutant that replaces that read with `None` passes the whole green
suite. At `c2edeb22` (post-rework) those 15 fall to 1, and the 1 is equivalent.

The same experiment found a **second miss of the same class, introduced by the fix for the first**: 49 of 52
post-rework survivors are in `scripts/_handoff_inputs.py`'s world reads (`_base_ref_candidates` 19,
`declared_files` 9, `_step_owned_paths` 8, `first_unfinished` 4, `artifact_names` 4, `recent_log` 3,
`resolve_base_ref` 2). `_base_ref_candidates` with its `symbolic-ref` read replaced by `None` passes every
test, because the fallback tuple masks a dead read exactly as `dirty_paths()` masked a dead status read. Filed
as `td-220`.

Cost is not the blocker: 44 s for 83 mutants, 133 s for 205 — 1.7–2.8 mutations/s, an order of magnitude under
the spike's 10-minute precondition, because the scope is one step's files against one step's tests.

Three structural facts constrain any shape this can take. The verifier is explicitly forbidden from *running*
anything (`agents/verifier.md` § Topology tier-appropriateness: "This is a document cross-check only"), so the
number must be computed elsewhere and read there. The `project_metrics` aggregate schema is frozen and
ADR-gated, and `dec-378` forbids adding a score column before the number has shown variance. And the flat
`scripts/` layout breaks mutmut's mutant-key check unless run with a specific eight-point recipe that took four
attempts to find — a recipe no future caller should have to rediscover.

This decision records the implementation shape. It does not re-decide adoption.

## Decision

**A new component, `scripts/mutation_sensor.py`** — stdlib-only, executable, linked onto `PATH` by
`install_claude.sh`'s existing `script_is_user_facing()` predicate (the `resolve_test_scope.py` path, not the
non-executable `check_test_results_shape.py` one). Interface:

```
mutation_sensor.py --targets <path.py> … --tests <path.py> … [--timeout S] [--json] [--debug]
```

It owns the spike's recipe so nothing else has to: cwd is the targets' directory; `source_paths` is the
explicit list of that directory's top-level `*.py`; `only_mutate` is the targets; test selection uses
**basenames** (mutmut's pytest cwd is `mutants/`); `pytest_add_cli_args = ["--no-cov"]`; the config is a
`[tool.mutmut]`-only `pyproject.toml` generated in that directory and removed with `mutants/` in a `finally`.
mutmut arrives as `uv run --project <the targets' git toplevel> --with mutmut==3.8.0` — **no `pyproject.toml`
dependency change and `uv.lock` untouched**. The project root is derived from the *targets'* directory, not the
runner's own location, so the runner can be pointed at a different checkout.

**Totals come from `mutmut export-cicd-stats` (a JSON file: killed/survived/total/no_tests/skipped/suspicious/
timeout/segfault); attribution comes from `mutmut results` text** (`<module>.x_<fn>__mutmut_<n>: <status>`).
The carriage-return-rewritten `⠏ 205/205 🎉 149 … 🙁 52` progress line inside a multi-hundred-KB debug log is
never parsed. The two sources cross-check each other; a disagreement is a refusal, not a published number.

**Exit 0 whenever the run completed, regardless of survivors. There is no exit 1** — a non-zero exit never
means "survivors found," which is the property that makes this a sensor and not a gate. Exit **2** with a
closed `ReasonCode` when the result cannot be trusted: `not-flat-layout` (v1 supports the flat-directory layout
only; packages are refused, not guessed at), `pyproject-present` (never clobber), `mutants-dir-present`,
`toolchain-missing`, `run-timeout`, `run-failed`.

**One optional line in the `TEST_RESULTS.md` step section, with two shapes:**

```
Mutation: survivors=<n> mutants=<m> [inconclusive=<n>] targets=[<a.py>, …] (<fn>: <k>, …[, +<j> more])
Mutation: unavailable reason=<code> (<detail>)
```

The runner prints the line; the producer copies stdout **verbatim**. Survivors count mutmut's `survived` **+**
`no tests` (a function no selected test exercises is a stronger F1 signal than a survivor); `timeout` and
`suspicious` are reported separately as `inconclusive` and never folded into either bucket. The line is
truncated to the top five functions and hard-capped at 240 bytes so it cannot push a green section past
`check_test_results_shape.py`'s 1,024-byte ceiling (`dec-386`).

**A planner-owned step tag `mutation: on`** in `IMPLEMENTATION_PLAN.md`, default absent = off, with `review:`'s
precedence model. The planner's guidance is to tag RISKY steps and any step whose `Files:` wrap a world read
(subprocess, git, filesystem, network, environment, clock). An untagged step invokes nothing — zero cost.

**Verifier Phase 10 gains three dispositions and still runs nothing:** survivors in a function that performs a
world read → `WARN` naming the functions plus a `TECH_DEBT_LEDGER` row (`class: coverage-gap`, the td-220
shape); a tagged step with no line → `WARN` (advisory during rollout, mirroring the missing-file case); a line
reading `unavailable` → recorded, no finding.

**No `project_metrics` column** — `dec-378` re-affirmed, not superseded.

## Considered Options

### A. One runner owning the recipe, a bounded document line, a planner tag (chosen)

- **Pro.** The recipe is encoded once, in code, where four attempts' worth of knowledge cannot decay into
  prose nobody rereads. The verifier's execution ban is satisfied structurally. Default cost is provably zero.
  The schema extension is invisible to both existing readers by construction, which is testable.
- **Con.** Two line shapes instead of one. RISKY coverage is convention rather than machinery.

### B. A `project_metrics` aggregate column (`mutation_score_pct`)

- **Pro.** Time-series shaped; one number per pipeline in a place people already look.
- **Con.** The aggregate schema is frozen at 16 columns and a column bump needs an ADR amendment — and
  `dec-378` names exactly this: a score column without a companion delta-detection mechanism is a self-graded
  log. The per-step number has not yet shown variance across pipelines; one spike's two data points are not
  variance. **Rejected, and dec-378 re-affirmed rather than worked around.**

### C. Auto-fire on RISKY steps, with `mutation: off` to suppress

- **Pro.** RISKY coverage becomes machinery, not convention; the failure mode where a planner forgets to tag
  disappears.
- **Con.** Requires a "does this step perform a world read" classifier — static detection of subprocess/open/
  `os.environ`/network/clock usage across a step's declared `Files:` — which is the genuinely hard part and
  would be wrong by default on its first pipeline. It also makes the default cost non-zero on every step.
  **Deferred, not rejected:** D-3's reversal trigger converts the tag to an auto-signal additively, since the
  field and its precedence already exist.

### D. Resolve scope from the topology `Tests: groups=[…]` field instead of explicit paths

- **Pro.** `RESEARCH_FINDINGS.md § 3` correctly observes the group id is the natural scope handle and needs no
  new field.
- **Con.** Couples the runner to the topology parser, breaks in a project with no `TEST_TOPOLOGY.md`, and —
  decisively — cannot point at a *different checkout*, which the `913d87d8` replay acceptance criterion
  structurally requires. The caller can still resolve group→files itself and pipe the result in.

### E. Parse the `mutmut run` progress line for totals (the shape the intake plan assumed)

- **Pro.** One fewer subprocess call.
- **Con.** That line is ANSI- and carriage-return-rewritten inside an 848 KB debug log; `export-cicd-stats`
  writes the same numbers as typed JSON, reading `.meta` files without re-running anything. This option was
  the intake's 7/10 open item; reading mutmut 3.8.0's own CLI surface closed it at design time.

## Consequences

**Positive.**

- The F1 class of miss gets a machine detector at seconds of cost, on the steps where it lives.
- `td-220` is closed by measurement, not by assertion: the acceptance criterion is the sensor's own reading
  (survivors 49 → a reading in which every remainder carries a proven equivalence-or-environment argument; a fixed count was rejected because equivalent mutants are not coverage debt and case-folding survivors vary with the filesystem), which is the only way a test
  written to close a coverage gap can be proven not to reproduce it.
- The recipe stops being tribal knowledge. A future caller runs one command.
- Zero always-loaded token cost — every prose landing site is a skill reference or an agent prompt.
- Rollback is deleting one script and three prose paragraphs; the schema line is optional and every reader
  ignores it.

**Negative / accepted.**

- A planner that never tags produces silence indistinguishable from a clean reading (see `dissent`).
- `survivors` is no longer byte-identical to mutmut's own 🙁 count, because `no tests` is folded in. The
  operator notes must say so.
- v1 refuses package layouts. Every managed project whose tests live in a `tests/` package beside a `src/`
  package gets `not-flat-layout` until an additive escalation ships.
- The runner writes into the working tree during a step (`pyproject.toml`, `mutants/`). Mitigated by the
  `finally`, by refusing when either already exists, and by adding `mutants/` to `.gitignore` — three layers,
  because a SIGKILL defeats the first.

## Disconfirmation

**Falsifier.** Name the component: `scripts/mutation_sensor.py` is added; `TEST_RESULTS.md` — an artifact with
named producers (implementer/test-engineer) and a named consumer (verifier) — gains a field in its published
schema; `IMPLEMENTATION_PLAN.md` gains a planner-owned tag; the responsibility "measure whether this step's
tests would notice the code being broken" moves from nobody to the step's canonical test-results writer. That
is what makes this `architectural` rather than `behavioral`. It adds **no** `DESIGN.md` §3a structural
component and no LikeC4 element — the script lives inside the existing `Scripts` (`tooling.scripts`) row whose
catalog is enumerated by filesystem scan, the same disposition `dec-351` took.

The decision is **wrong** if any of three things is observed: (a) the shipped runner, pointed at a `913d87d8`
scratch worktree, does *not* reproduce 15 survivors all in `dirty_paths` — then the runner does not encode the
recipe it claims to and the tool is not the spike's result, it is a different tool with the spike's name;
(b) the `Mutation:` line changes what either existing reader reports on a fixture — then the "backward-
compatible" claim is false and the schema extension must move to a separate artifact rather than into a
document two pipeline-critical parsers read; (c) after the td-220 fix, survivors in `_handoff_inputs.py` do not
fall from 49 to a set whose every member is provably equivalent or environmental — then either the sensor is not measuring what it claims or real-adapter tests do not close
this defect class, and in both cases the adoption evidence evaporates.

**Steelmanned runner-up.** Option C (auto-fire on RISKY) is the design that would actually be right if the
failure mode we fear is forgetfulness rather than cost. The whole justification for this feature is that a
*human reading a report* missed F1 twice — first the original, then the second instance inside the fix for the
first. A design whose firing condition is "the planner remembers to tag it" places the same fallible
judgement one layer up and calls the problem solved. The steelman is sharper still: the two misses on record
both occurred on steps that any sane RISKY heuristic would have flagged (`tier: H` rework of a world-reading
adapter), so the classifier C needs would not have had to be clever — `tier: H` alone would have caught both.
The counter that carries the day is narrow and empirical, not principled: C's cost is non-zero on every RISKY
step in every pipeline from day one, and this feature has exactly two data points. Shipping the cheap version
first and converting on evidence is the Incremental Evolution reading; shipping C first is the correct reading
if the evidence is already sufficient. Reasonable architects differ here.

**Reversal trigger.** Two consecutive Standard or Full pipelines complete with **zero** steps tagged
`mutation: on` → the convention is not firing, and the tag converts to an auto-signal (`tier: H` ∨
`review: force` ∨ world-read `Files:`) with `mutation: off` as the escape hatch. This is strictly additive:
the field, its precedence model and both line shapes already exist. Secondary trigger: if three tagged steps
in a row report `survivors=0` on code known to contain a world read, the sensor is under-reporting and D-4's
status accounting is the first thing to re-examine.

## Prior Decision

**Re-affirms `dec-378`** ("Simplification requires a measured cost and an executable guard"). Nothing in
dec-378 changes. This decision is a case where its constraint bites and is honoured rather than argued around:
dec-378's H4 finding is that a bare score column, once added to a frozen ADR-gated aggregate schema, becomes a
self-graded log unless a delta-detection companion ships with it. The obvious home for a mutation number is
exactly that column, and this design declines it — the number stays per-pipeline in `TEST_RESULTS.md` until it
has shown variance across pipelines. The measured cost dec-378 asks for is on record (44 s / 83 mutants,
133 s / 205 mutants, 1.7–2.8 mutations/s), and the executable guard is the runner itself plus the verifier's
Phase-10 disposition — not a log an agent grades itself against.
