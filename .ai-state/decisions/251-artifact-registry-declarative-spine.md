---
id: dec-251
title: Grow the artifact registry into a declarative production-gate spine
status: accepted
category: architectural
date: 2026-06-26
summary: Add per-artifact `production_gate` + `cleanup_policy` fields to artifact_registry.py so "which obligation has a gate, and what is it?" is one grep, drift-guarded but not auto-generated.
tags: [artifact-registry, production-gates, declarative-spine, drift-gate, gate-liveness]
made_by: agent
agent_type: systems-architect
branch: wave3-production-gates
pipeline_tier: full
affected_files:
  - scripts/artifact_registry.py
  - scripts/test_artifact_registry.py
dissent: The field is checked-not-read, so it risks becoming a second hand-maintained list that drifts — the value is documentation, which the cohort's sentinel checks deliver anyway.
---

## Context

The artifact-process-flow analysis (§0, §6, §8) names one root cause behind four of
five process clusters: **designed obligation without a production mechanism**. The most
load-bearing artifact obligations (criteria thread, calibration, spec archival, learnings
promotion) live in prose — a rule sentence or an agent-prompt line — with no gate, and on
Praxion's own disk several silently stop firing. The analysis's "one structural move that
subsumes many rows" (§6, §8) is to grow `scripts/artifact_registry.py` from a passive
drift-checker into a **declarative spine**: `activation` already lives on the `Artifact`
dataclass; add a `production_gate` (a pointer to the sentinel check / hook / producer that
makes the artifact exist or flags its absence) and a `cleanup_policy`. This does **not**
auto-generate gates — each is still hand-authored, exactly as `finalize_chain`, the rework
scripts, and the reconciler are. What it changes is *visibility*: the per-artifact gate
becomes one grep-able lookup instead of an obligation scattered across rules and prompts.

The registry today is *checked-against, not read-from*: four hard-coded consumer lists
(`build_doc_manifest._AI_WORK_FILES`, the dashboard's `CANONICAL_WORKSHOP_ARTIFACTS`,
`task_manifest._STANDARD_REQUIRED`, `precompact_state.PIPELINE_DOCS`) are parsed from
source text by `test_artifact_registry.py` and asserted equal to registry projections.
None imports the registry. The new fields must not perturb that contract.

## Decision

Add two fields to the frozen `Artifact` dataclass, each defaulted so existing rows and
all consumers remain valid:

- `production_gate: str = "none"` — a `"<kind>:<ref>"` convention string. `<kind>` is
  drawn from a module-level `_GATE_KINDS` frozenset (`sentinel`, `script`, `hook`,
  `producer`, `none`, `deferred`); `<ref>` is the concrete pointer (e.g.
  `sentinel:P06`, `script:check_spec_archival_gap.py`, `producer:verifier`,
  `hook:precompact_state.py`). `none` and `deferred` carry no ref.
- `cleanup_policy: str = "delete"` — drawn from a `_CLEANUP_POLICIES` frozenset
  (`delete`, `archive`, `block-if-active`, `consume-marker`). Declares, per artifact,
  what must happen before `.ai-work/` deletion — the declarative mirror of what
  `clean_work_safety.py` enforces procedurally today.

Both fields are **populated, not projected**: no projection helper
(`dashboard_artifacts`, `snapshot_artifacts`, `eval_required`, `eval_conditional`)
changes, so the six live drift assertions pass unchanged and the four consumers ignore
the new fields by construction. The drift gate is extended **additively** with
self-consistency tests (`production_gate` kind ∈ `_GATE_KINDS`; ref non-empty when the
kind requires one; `cleanup_policy` ∈ `_CLEANUP_POLICIES`; core artifacts carry a
non-`none` gate) plus a **canary** that feeds a bad gate kind and asserts the new test
bites (gate-liveness CODE-gate proof).

Wiring any consumer to *read* the new fields (so `clean_work_safety.py` derives its
policy from the registry, or a dashboard badge renders the gate) is explicitly a **future
step**, identical to the existing checked-not-read posture for the four consumers.

## Considered Options

### A — `production_gate` as a single `"<kind>:<ref>"` convention string (chosen)

- **Pros:** maximally grep-able (the analysis's whole thesis — "one grep"); matches the
  file's existing idioms (plain-`str` flags, helper projections, self-consistency tests);
  zero new imports; the kind set is enforced by a frozenset + one self-test that mirrors
  the existing `test_eval_flags_imply_eval_tier`.
- **Cons:** weakly typed (a typo in `<ref>` is not caught beyond non-emptiness); the
  `kind:ref` split is a convention, not a type.

### B — A nested frozen `ProductionGate(kind, ref)` dataclass / `StrEnum` kind

- **Pros:** strongly typed; kind typos impossible.
- **Cons:** more ceremony for an internal-only, checked-not-read field; the drift test
  parses consumers by source-regex, so the typing buys nothing at the consumer boundary;
  over-builds for a 24-row registry. Rejected on Simplicity First.

### C — Do not grow the schema; ship only the cohort's sentinel checks

- **Pros:** zero registry change; the production gates (R3/R4/R9/R13) deliver the actual
  enforcement on their own.
- **Cons:** the central analysis recommendation (§8 — "the one structural move that
  subsumes many rows") goes unrealized; "which obligations have a gate" stays scattered
  across rules and prompts with no single lookup. The cohort would close individual gaps
  but not the *visibility* gap that lets them re-open silently. Rejected — but see
  Disconfirmation: this is the genuine runner-up.

## Consequences

**Positive:** one grep (`grep production_gate scripts/artifact_registry.py`) answers
"which artifact has a gate and what is it" across the whole pipeline; the drift test keeps
the answer honest the same way it keeps the four consumer lists honest; the field gives
the cohort's four new gates a single registration home; `cleanup_policy` makes the
lifecycle policy (analysis Theme C) declarative ahead of any Wave-4 retention wiring.

**Negative / accepted:** the field is checked-not-read, so it adds a maintenance surface
that must be kept in sync by hand (mitigated by the drift test's self-consistency
assertions); it is documentation with teeth, not enforcement — the enforcement is each
referenced gate, not the pointer.

## Disconfirmation

**Falsifier.** If, two waves on, no consumer reads `production_gate`, no human greps it
to answer a real question, and its rows drift out of sync with the actual gates (the
drift test catching kind-validity but not ref-accuracy), then the field is dead
documentation and should be removed — the cohort's sentinel checks were carrying the
whole value.

**Steelmanned runner-up (Option C — ship only the gates).** The production gates are the
load-bearing deliverables; each closes a concrete gap with its own gate-liveness proof.
The registry field adds nothing *enforcing* — it cannot make an obligation fire; only the
sentinel check / script / producer it points at can. A `"<kind>:<ref>"` string is itself
a small prose obligation (keep the ref accurate) of exactly the kind the analysis warns
about — so the spine risks reproducing the disease it diagnoses. Under Simplicity First,
shipping four real gates and leaving the registry a pure drift-checker is the smaller,
safer move; the "one grep" benefit is marginal when the cohort is only seven artifacts.

**Why chosen anyway.** The analysis is explicit and repeated (§0 closing, §6 footer, §8)
that the durable fix is the spine, not just the gates — because gates that aren't visible
in one place are exactly the ones that re-open silently (the disk proved this for spec
archival and calibration). The field's drift cost is bounded by keeping it a single
self-tested string (Option A, not B), and its reversal is cheap (drop two defaulted
fields). The genuine uncertainty is ref-accuracy drift, which the reversal trigger below
monitors.

**Reversal trigger.** A future sentinel/GL pass finds ≥2 `production_gate` refs pointing
at a check/script/producer that no longer exists (ref-rot the drift test didn't catch) →
either strengthen the drift test to resolve refs, or drop the field per the falsifier.
