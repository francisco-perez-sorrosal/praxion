---
id: dec-409
draft_id: dec-draft-752d9a05
title: Independent acceptance-test design runs between the architect's spec phase and its design phase
status: accepted
category: architectural
date: 2026-09-28
summary: "A new test-engineer mode, acceptance-design (Opus), designs acceptance, boundary-integration and end-to-end tests from a linted spec extract (new scripts/extract_spec.py → SPEC_EXTRACT.md) after the architect's new spec mode and before its design phase, so no new design exists when the tests are designed; the implementer takes over unit tests; the planner plans from the design plus ACCEPTANCE_TESTS.md."
tags: [testing, acceptance-tests, test-design-independence, pipeline-stages, systems-architect, test-engineer, implementer, spec-extract, test-suite-refresh]
made_by: agent
agent_type: systems-architect
branch: worktree-acceptance-independence
pipeline_tier: full
affected_files:
  - scripts/extract_spec.py
  - scripts/artifact_registry.py
  - agents/test-engineer.md
  - agents/systems-architect.md
  - agents/CLAUDE.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-model-routing.md
  - skills/software-planning/references/coordination-details.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-16, REQ-17, REQ-18]
dissent: "Splitting the architect into a spec mode and a resumed design mode adds an orchestration hop and a mode to protect the main pass, when a base-commit read rule plus the Sources Read audit would already make any design leak visible after one uninterrupted architect spawn."
---

## Context

dec-408 made it policy that tests beyond the unit level are designed independently of the design, and that the implementer runs outer-loop tests but never edits them. It deferred the mechanics to this pipeline.

Today Praxion has temporal independence only. The test-engineer runs after the planner, reads `SYSTEMS_PLAN.md § Architecture` by instruction ("define expected interfaces from the architecture"), and receives design detail through planner-written steps. The WAL shows test-engineers grepping architecture sections. The ledger-triage plan handed a test step the design's grammar and the production modules to import.

Independent evidence converges on withholding the implementation or design from the test designer:

- Cleanroom certification teams.
- AgentCoder's separate test designer.
- Konstantinou et al.: LLM oracles copy actual behavior.
- ImpossibleBench: read-only test access stops test edits while keeping performance.

The user fixed eight decisions:

1. Black-box scope.
2. `INTERFACE_DESIGN.md` public-contract sections only.
3. The spec as a distinct first architect phase, plus `extract_spec.py`.
4. Lightweight gets temporal ordering only.
5. Opus for the stage.
6. Contract plus provenance, no hook.
7. One Spec-Question round.
8. The `ACCEPTANCE_TESTS.md` artifact.

Left open: where the stage sits relative to the architect's two phases, and how its spawn is counted.

## Decision

1. **Stage order (Standard/Full).** architect `Mode: spec` (Phase 1 only; the spec sections, then `extract_spec.py` until clean) → **test-engineer `Mode: acceptance-design`, per-spawn `opus`** → orchestrator commits the RED outer-loop tests (test-only) → at most one Spec-Question round, completed before design → architect resumed in `Mode: feature` (Phases 2–10, reading `ACCEPTANCE_TESTS.md`) → implementation-planner (plans from the design plus the tests).
2. **New component.** `scripts/extract_spec.py`, stdlib-only and 3.9-safe, rooted at `git rev-parse` or `--repo-root` (never `__file__`). Exit codes: 0 clean, 1 findings or stale, 2 input error.
   - Writes `SPEC_EXTRACT.md`: the Key Signals, Acceptance Criteria and Behavioral Specification verbatim, HTML comments stripped, with a body digest.
   - The file exists only when the spec is lint-clean: design-vocabulary findings in AC/REQ text block it and delete any stale copy. Findings in Key Signals are advisory.
   - Names the spec deliberately publishes are declared under `### Observable Surface` inside the Behavioral Specification. Only already-public or user-fixed names qualify.
3. **Inputs.** The acceptance designer reads only:
   - (A1) the extract;
   - (A2) `### Public Contract` subsections of `INTERFACE_DESIGN.md`;
   - (A3) repository content at the base commit.

   It declares everything it read under `## Sources Read`. `TASK_BRIEF.md` is forbidden because it carries scope and design hints; its Key Signals arrive through the extract. So are every other pipeline document, the ADR drafts and any working-tree file changed since base.
4. **Responsibility move.** The implementer owns unit and internal-integration tests (the inner loop) and the `tests:` traceability array. The test-engineer owns outer-loop design in acceptance-design mode. It keeps a paired mode for driver binding and for optional risky-logic, property and contract pairing. The architect gains a separately returnable spec phase.
5. **Tiers.** Lightweight: the orchestrator writes Key-Signal tests RED and commits them before any code, labelled temporal-only. Direct/Spike: nothing added. Standard/Full: the full stage. It may be skipped only through the skipped form of `ACCEPTANCE_TESTS.md` with a specific reason (all-Markdown deliverables, the dec-120 precedent).
6. **Spawn accounting: count, don't credit.** The acceptance designer is a charged spawn under the unchanged Standard ≤ 8 / Full ≤ 16 budgets, and `spawn_count.py` is unchanged. The offset comes from the ownership move: no paired test-engineer per behavioral step. Architect and Spec-Question resumes are light and therefore free. A lost resume is replaced by a charged fresh `Mode: feature` spawn.

**Activation:** yes. Honest uncertainty (resume reliability, spec churn) on a `category: architectural` decision. The DI sub-step was run; see Disconfirmation.

## Considered Options

### After the whole architect spawn (steelmanned runner-up)

- Pro: one architect context, no new mode and no resume hop.
- Pro: design-then-bind is the normal four-layer acceptance flow anyway.
- Pro: a base-commit read rule makes any working-tree `DESIGN.md` read an auditable violation.
- Con: on the main pass, the working-tree `DESIGN.md`, `docs/architecture.md`, ADR drafts and `## Architecture` all exist, so the barrier is contract-only where most tests are designed.
- Con: Boundary Assumptions reach only the planner after the design is fixed.
- Con: Spec Questions are answered by the author of a finished design.

### Parallel with design after a spec freeze

- Pro: shortest wall-clock.
- Con: needs the same architect split.
- Con: the design proceeds without the tests' declared needs.
- Con: reconciliation while both sides move.

### Spec authored before the architect by the orchestrator and the user

Excluded by user decision 3 and not re-opened.

### Between the spec phase and the design phase (chosen)

- Pro: the barrier holds by construction for the main pass.
- Pro: Boundary Assumptions become consumer-driven contracts the design satisfies or challenges.
- Pro: Spec Questions are answered before design.
- Pro: the same charged spawn count as the runner-up when the resume is light.
- Con: one resume hop and one new architect mode.
- Con: acceptance design sits serially between the two architect halves.

## Consequences

- Positive:
    - Outer-loop tests are designed from the spec alone, and the isolation is checkable from the artifact.
    - The in-tree design-document leak the research flagged is removed at its source.
    - The design is shaped by the tests' declared needs, which is the only lever against interface-mismatch rework.
    - The contradiction in the test-engineer's instructions ("from the spec" vs "interfaces from the architecture") disappears with the mode split.
- Negative:
    - The orchestration sequence grows by a resume and a commit.
    - The architect definition gains a mode (paired site: `agents/CLAUDE.md`).
    - The acceptance designer is one more charged spawn until the pairing reduction offsets it, which only the dogfood can confirm.
    - Spec authors must declare published names explicitly.
- Risks accepted:
    - The late Spec-Question path runs after design exists and is guarded by contract plus the Sources Read audit only.
    - The lint has known false negatives (single-word identifiers, paraphrase).

## Disconfirmation

- **Falsifier:** the split buys nothing if the post-merge dogfood (or the next two Standard/Full pipelines) shows either of these:
    - the architect's design phase amends REQ text after acceptance design for reasons not raised as Spec Questions (spec churn originating in the design, meaning the spec phase is not a real boundary);
    - the spec-to-design resume lands at or above 250k tokens or has to be replaced by a fresh spawn in most runs.

  The barrier-by-construction claim is also false if an audit finds a main-pass `## Sources Read` entry pointing at design text.
- **Steelmanned runner-up:** run acceptance design after the whole architect spawn with `SPEC_EXTRACT.md` as the only handed input, and require base-commit reads (`git show <base>:<path>`) for design documents. It is simpler to orchestrate, needs no architect mode, and keeps every leak visible in `## Sources Read`. The planner adds driver-binding steps in either shape, so interface mismatches are absorbed at the same layer.
- **Reversal trigger:** two consecutive Standard/Full pipelines hit either falsifier condition (design-originated spec churn, or a heavy or failed spec-to-design resume). Then move acceptance design to after the architect spawn, keep the extract as its only spec input, and add the base-commit read rule to the forbidden-input list.
