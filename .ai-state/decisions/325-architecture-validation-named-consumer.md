---
id: dec-325
title: Name the verifier as the required reader of ARCHITECTURE_VALIDATION.md
status: accepted
category: behavioral
date: 2026-08-06
summary: The architect-validator's non-FAIL findings get a named consumer (the verifier, via its existing specialist-artifact review) rather than being routed to the debt ledger or the artifact being retired.
tags: [architect-validator, verifier, gate-liveness, aac, pipeline-contract]
made_by: agent
agent_type: orchestrator
branch: fleet-quality-remediation
pipeline_tier: standard
affected_files:
  - agents/architect-validator.md
  - agents/verifier.md
dissent: Naming a reader that most pipelines never invoke may satisfy the gate-liveness clause on paper while leaving the findings just as unread in practice.
---

## Context

`architect-validator` produces `.ai-work/<task-slug>/ARCHITECTURE_VALIDATION.md` with three
finding sections and an overall verdict. Its **FAIL** findings are additionally appended to
`.ai-state/TECH_DEBT_LEDGER.md`, which is read by several agents and survives pipeline cleanup.
Its **WARN**, **PASS** and verdict content exist only in the report — and no agent, command,
rule, or skill reads that file. A sweep of the shipped surface returns four mentions, all
producer-side: two catalog rows describing the agent, one architecture-conventions mention, and
the ledger reference that covers precisely the FAIL path that already works.

The report then dies at `rm -rf .ai-work/<task-slug>/`. A managed project runs a structural
validator and the non-blocking half of its output evaporates.

This is the gate-liveness clause *A named consumer for every gate output*, which is explicit
that the defect is the missing reader and **not** the advisory posture: a gate may be correctly
and deliberately advisory and still need a named consumer. What fails is sound advisory design
*plus* no reader named anywhere.

Two facts constrain the fix. First, the verifier already has a **Specialist Design Review
(conditional)** step that reads exactly this class of artifact — `INTERFACE_DESIGN.md`,
`TRANSACTIONS_DESIGN.md`, `CONSULT_<discipline>.md` — from the same task-slug directory, so an
extension point exists. Second, in `--mode=pre-merge` the CI harness invokes the agent with an
allowlist that grants no `Write` tool, so in that mode the report is not a file at all; the
findings are the action's structured output and the exit code is the gate.

## Decision

Name the consumer per mode, in the producer's own definition, and wire the pipeline one.

- **Pipeline / `--mode=on-demand`** — the **verifier** is the required reader. When
  `ARCHITECTURE_VALIDATION.md` is present under the task slug, the verifier reads it in its
  existing Specialist Design Review step and carries unresolved structural findings into
  `VERIFICATION_REPORT.md`. Absence is not a finding: the validator is not a standard pipeline
  stage, so most runs legitimately have no report.
- **`--mode=pre-merge`** — the consumer is the invoking CI job's verdict and the PR review
  surface. The producer now says so, and says that a harness granting no `Write` yields the
  report as structured output rather than a file.
- **Anything that must outlive cleanup still goes to the ledger.** That boundary is unchanged;
  the verifier's read is what gives the non-FAIL half a decision point before the directory is
  deleted.

## Considered Options

### Option A — Name the verifier as the required reader (chosen)

- **Pro** — uses an extension point that already exists and already reads sibling artifacts from
  the same directory, so the change is one conditional clause on each side rather than a new
  mechanism.
- **Pro** — the verifier's report is itself consumed and its patterns are harvested into
  `LEARNINGS.md` before cleanup, so the findings reach a surface that survives.
- **Pro** — preserves the advisory posture the gate-liveness rule explicitly protects. Nothing
  becomes blocking.
- **Con** — the verifier only runs at Standard/Full tier, and the validator is most often run
  standalone or in CI, so the wired path covers the *minority* of invocations.

### Option B — Route non-FAIL findings to the tech-debt ledger

- **Pro** — the ledger is unambiguously consumed and persistent; zero new contract.
- **Con** — most WARNs are not debt. `no LikeC4 model present` is the documented bootstrap state
  for every project that has not adopted LikeC4; filing it as debt would open an unactionable row
  on every run in every such project and degrade a ledger whose value depends on every row being
  a real, grounded finding.
- **Con** — it conflates two distinct signals: "there is drift" and "the check did not run".

### Option C — Retire the artifact

- **Pro** — removes the unread surface outright; the FAIL path already works without it.
- **Con** — the report is the agent's only human-readable output and the only place the
  *reasoning* behind a ledger row lives. In pre-merge mode a PR reviewer would be left with an
  exit code and no explanation.

## Consequences

**Positive**

- The non-FAIL half of the validator's output has a named reader and a decision point.
- The producer's definition stops promising a file in a mode that cannot write one.
- The verifier gains structural-drift context it otherwise re-derives or misses; the two agents'
  boundary is unchanged, since the verifier still owns behavior and the validator still owns
  structure.

**Negative**

- The verifier gains one more conditional input, marginally widening an already broad agent.
- Coverage is partial by construction: standalone runs outside a pipeline still have no reader
  beyond the human who invoked them. This is accepted rather than solved.

## Disconfirmation

**Falsifier.** Sample real runs after this lands: if `ARCHITECTURE_VALIDATION.md` files are
produced but `VERIFICATION_REPORT.md` never cites one — because the validator is essentially
always invoked outside a verifier-bearing pipeline — then the named consumer is ceremonial and
the decision was wrong. The honest fix then is Option C for the pipeline path, keeping the
report only for the pre-merge surface where a human actually reads it.

**Steelmanned runner-up (Option B).** The ledger is the only consumer in this system with a
proven readership and a lifetime longer than a pipeline. A WARN that means *the check did not
run* — `validator-unable-to-query-likec4-mcp`, `import-linter-config-not-found` — is not a
bootstrap state at all; it is a silent coverage hole that makes a `PASS_WITH_WARNINGS` verdict
read as an all-clear. That specific subclass has a genuine claim to a durable row, and routing
it there would need no new reader at all. Option A was chosen over it only because the WARN set
is currently undifferentiated: until the report separates "clean" from "not checked", routing
all of it to the ledger buys durability at the cost of a ledger full of bootstrap noise.

**Reversal trigger.** Revisit if either holds: the report grows a machine-readable split between
*checked-and-clean* and *not-checked* (at which point the not-checked subclass should go to the
ledger per the steelman, and this decision narrows to the remainder), or the validator becomes a
standard pipeline stage rather than a per-PR/on-demand one (at which point the verifier's read
stops being a minority path and the coverage objection dissolves).
