---
id: dec-draft-93cfaad9
title: Outer-loop reverse barrier and provenance without a hook — driver layer, owning steps, pending accounting, verifier history checks
status: proposed
category: behavioral
date: 2026-09-28
summary: "Outer-loop tests split into scenario files and a drivers/ layer; each scenario test has one owning plan step (a new Read-only field) and failing tests owned by a later step are reported as pending= rather than fail=; the planner projects ACCEPTANCE_TESTS.md scenarios into a new additive acceptance: traceability key and coverage reads tests ∪ acceptance; the verifier proves declared sources, commit order (outer-loop tests before the first production commit) and coverage from the artifact and git history."
tags: [testing, acceptance-tests, reverse-barrier, provenance, traceability, verifier, implementation-planner, test-suite-refresh]
made_by: agent
agent_type: systems-architect
branch: worktree-acceptance-independence
pipeline_tier: full
affected_files:
  - agents/verifier.md
  - agents/implementer.md
  - agents/implementation-planner.md
  - skills/software-planning/references/document-templates.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/spec-driven-development/SKILL.md
  - skills/spec-driven-development/references/spec-format-guide.md
  - commands/sdd-coverage.md
  - scripts/spec_drift.py
affected_reqs: [REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-19]
---

## Context

dec-draft-752d9a05 places independent acceptance design before planning. The user ruled out a blocking hook for now (decision 6: contract plus verifiable provenance first) and fixed three enforcement surfaces:

- a `## Sources Read` section;
- a verifier check that outer-loop tests were committed before any production code;
- an `acceptance:` traceability key.

Three practical gaps remain once outer-loop tests exist before the plan:

- **Unbound interfaces.** A test for a new surface cannot call an interface that does not exist yet. The four-layer acceptance model answers this with a protocol-driver layer bound late. But if the implementer binds it, the reverse barrier (ImpossibleBench: read-only access stops test edits) is gone.
- **RED for the whole pipeline.** Outer-loop tests stay RED across many steps. The implementer's integration checkpoint says "fix every failure", and the `TEST_RESULTS.md` parser reads any failure as red.
- **Hidden coverage.** Consumers classify a requirement as UNTESTED when `tests:` is empty, which would hide requirements proven only from outside.

## Decision

1. **Driver layer.** Outer-loop files split by path:
   - drivers live in a `drivers/` directory under `tests/acceptance/` or `tests/e2e/`;
   - everything else there is a scenario file.

   The acceptance designer writes scenarios plus drivers. An unbound driver raises with the assumption's words, never its id. A driver-binding step (test-engineer, paired mode, planned before any production step) binds drivers to the designed interface. The implementer edits neither class.
2. **Owning step.** A new plan-step field, `**Read-only**:`, lists the outer-loop test nodes a step must turn green. It is kept off `**Files**:`, which the reconciler parses for git attribution. Each scenario node appears in exactly one step.
3. **Pending accounting.** `TEST_RESULTS.md`'s `Result:` line gains `pending=<n>`: failing outer-loop tests owned by a later step, excluded from `fail=`. `_step_schema.py` already ignores unknown tokens, so no parser change is needed. The final integration checkpoint must show `pending=0`. The implementer never fixes a pending test. A due test it cannot satisfy without contradicting the spec yields `[BLOCKED]` plus a Spec Question.
4. **Traceability.** `acceptance:` is additive. The planner writes it, projected from `ACCEPTANCE_TESTS.md § Scenarios` at initialization; the acceptance designer never touches `traceability.yml`. Fragment merge unions every list-valued key. A requirement is tested iff `tests ∪ acceptance` is non-empty. The archived matrix keeps its header, and `Test(s)` lists both kinds.
5. **Verifier checks** (Phase 4, PROMPT gates with golden bad-cases):
   - presence, or the skipped form with a specific reason;
   - `## Sources Read` within the three allowed classes;
   - `extract_spec.py --check` clean, with the digest accounted for;
   - commit order over ordered path classes (driver, scenario, inner-loop test, state/doc, production): the AD commit strictly precedes the first production commit; scenario edits after it only in recorded Spec-Question commits; driver edits only in commits touching no production path;
   - coverage: the partition of requirements into scenarios or not-black-box-testable, non-empty `acceptance:` where scenarios exist, and `pending=0`.

## Considered Options

### The directory rule alone

`testing-conventions.md` already makes the outer-loop directories read-only for the implementer.

- Pro: nothing new.
- Con: no way to bind unbound surfaces without breaking the rule.
- Con: intermediate steps cannot report honestly.
- Con: nothing proves order or non-editing.

### A `wip`/xfail marker on in-progress acceptance tests

- Pro: the familiar Cucumber `@wip` shape.
- Con: someone must remove the marker, which is an outer-loop edit.
- Con: it conflicts with dec-408's "`large` is the only marker".

### A dedicated provenance script

- Pro: deterministic.
- Con: the brief scopes one new script.
- Con: the verifier procedure is explicit enough to start with.
- Kept as a deferred trigger: promote it to a CODE gate if the dogfood shows misclassification.

### Driver layer + owning step + pending token + verifier checks (chosen)

## Consequences

- Positive:
    - Test-first order and non-editing are proven from history.
    - Intermediate runs stay honest.
    - Design knowledge in tests is confined to one file class that only a design-aware test-engineer step writes.
    - Old `traceability.yml` files stay valid.
    - Acceptance-only requirements are no longer reported as untested.
- Negative:
    - Two new fields: `Read-only:` in plans and `pending=` in results.
    - A git-history procedure in the verifier.
    - A path convention (`drivers/`) that managed projects must adopt for outer-loop tests.
    - `spec_drift.py` and `/sdd-coverage` change to read the new key.
