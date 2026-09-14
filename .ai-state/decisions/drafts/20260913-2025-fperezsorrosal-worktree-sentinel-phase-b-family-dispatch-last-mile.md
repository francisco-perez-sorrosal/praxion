---
id: dec-draft-34af7f36
title: The family envelope is additive — tool scripts join the dispatch table without a wrapper, and AC10 stays out
status: proposed
category: behavioral
date: 2026-09-13
summary: "run_check_families.py reads exactly six keys from a family payload, so any script whose --json already emits a dict can carry the envelope alongside its existing keys — no wrapper component, no broken consumer. On that basis clean_work_safety.py (P08) and measure_token_budget.py (T02) join the Family dispatch table as in-place adapters, DH01/DH06 become registered A rows because adr_health.py already computes both (removed-by-later decay class; status_edge_conflicts) which lets the _LEGACY_CITING_ROWS exemption be deleted outright, and aac_fence_validator.py (AC10) stays sentence-dispatched because its per-file positional contract is load-bearing for the CI dsl-validate job and the architect-validator allowlist while its value is the smallest in the set (333 B row, 2-file corpus)."
tags: [sentinel, process-economy, roadmap-p2-item3, byte-budget, gate-liveness, data-structures]
made_by: agent
agent_type: systems-architect
branch: worktree-sentinel-phase-b
pipeline_tier: standard
affected_files:
  - agents/sentinel.md
  - scripts/run_check_families.py
  - scripts/clean_work_safety.py
  - scripts/measure_token_budget.py
  - scripts/adr_health.py
  - scripts/aac_fence_validator.py
  - scripts/check_aac_golden_rule.py
  - tests/test_sentinel_check_triangle.py
  - tests/test_sentinel_row_contract.py
affected_reqs: [REQ-01, REQ-08, REQ-09, REQ-10, REQ-11, REQ-13]
---

## Context

Phase A of the sentinel last mile moved four scripts onto the Family dispatch table and left twelve behind —
19 rows and ~13.4 KB of catalogue row plus a 3.4 KB Phase-3 prose paragraph, still costing roughly twelve of the
twenty Bash calls a `/sentinel` sweep spends in Pass 1. The extraction contract itself is settled: dec-380 fixed the
four-part row shape and the three destinations (verdict map ≤300 B, rationale to the module docstring, golden
bad-cases to the canary), dec-382 added the two-part family form for table-dispatched rows, and dec-384's
`check_calibration_coverage.py` is the freshest exemplar. What was **not** settled is which of the twelve can join,
because three of them are not check scripts at all and two of the rows are legacy prose.

Three questions blocked the phase, each of which a prior survey answered by inspection rather than by instrument:

1. `aac_fence_validator.py` (AC10), `clean_work_safety.py` (P08) and `measure_token_budget.py` (T02) are **tools**,
   with consumers outside the sentinel. Wrapper script, in-place adapter, or leave them alone?
2. DH01 and DH06 sit in `_LEGACY_CITING_ROWS`, an exemption that narrows the row/registry/script triangle's Leg 1.
   Can `adr_health.py` actually compute what their prose asks, or is the exemption load-bearing?
3. `check_aac_golden_rule.py` emits JSON only under `--mode=audit`, and the row contract caps an Invocation's flag
   span at 20 characters.

## Decision

**1. The family envelope is additive, so a dict-emitting tool needs no wrapper.** `run_check_families.py` reads
exactly six keys from a family payload — `checks`/`check`, `findings`, `skipped`, `examined`, `bound`, `withheld`
(`_declared_checks`, `_field_for`, `aggregate_family`). For any script whose `--json` already emits a dict, those keys
are *added* beside the existing ones and every current consumer keeps reading its own keys unchanged. On that basis
`clean_work_safety.py` (P08) and `measure_token_budget.py` (T02) become in-place family adapters: their verdict
predicates ("≥3 SAFE dirs idle ≥14 days"; `over_by > 0`) move from sentinel prose into code with a canary, which is
dec-380's contract applied, not a new one. Confirmed by instrument that their consumers read by key lookup or import
the module rather than the CLI payload: `commands/clean-work.md` reads `task_dirs`/`summary`;
`check_token_ratchet.py` and `apply_skill_description_diet.py` both `import measure_token_budget`.

One exception to additivity is recorded here rather than discovered later: `check_gate_liveness.py`'s findings
already use `check` for the detector's *kind* (`forbidden-pattern`, `uninvoked-gate`, `ambient-import`,
`discarded-verdict`), which the runner would aggregate as if it were a check id. That family's adapter must **rename**
— `kind` takes the classification, `check` takes the GL id — and is the only breaking change in the batch.

**2. AC10 stays sentence-dispatched.** `aac_fence_validator.py` keeps its per-file positional contract with
load-bearing exit codes, because two surfaces outside the sentinel depend on exactly that shape:
`.github/workflows/architecture.yml:264` (`xargs -r -I {} python3 scripts/aac_fence_validator.py {}`) and the
architect-validator's CI allowlist `Bash(python3 scripts/aac_fence_validator.py:*)` (dec-275). Against that, AC10's
value is the smallest in the set — a **333-byte row**, the smallest of the eighteen, over an in-scope corpus of
**exactly two files** (`.ai-state/DESIGN.md`, `docs/architecture.md`), so **two** Bash calls, not twelve. A wrapper
would be a new component, a new canary and a new registry entry bought for two calls.

**3. DH01 and DH06 become registered A rows, and `_LEGACY_CITING_ROWS` is deleted.** `adr_health.py` already computes
both: DH01 is the `removed-by-later` decay class (line 752, and `--only removed-by-later` already filters on it, the
module docstring calling it "the highest-value output"), and DH06 is the top-level `status_edge_conflicts` list
(line 571, five shapes with dispositions), both present in the live payload. Registering them empties the exemption,
and a measured probe of the whole catalogue — every row citing a registered script, minus that script's registry
entries — returns `adr_health: ['DH01', 'DH06']` and nothing else. With the exemption's only members registered, the
allowlist and its staleness test are removed rather than left empty: Leg 1 becomes unconditional, which is strictly
stronger than an exemption plus a guard on the exemption.

**4. EC07's table Invocation is `` `python3 scripts/check_aac_golden_rule.py --mode=audit --json` ``.** The flag span
is exactly 20 characters against `_INVOCATION_FLAGS_MAX_CHARS = 20` and the quantifier is `{0,20}`; executing the
contract's own regex confirms the match. `--mode=audit` is mandatory — bare `--json` prints nothing, and `--help`
states JSON is audit-mode only.

**Category — `architectural` falsifier applied.** Name the component added, removed, or whose responsibility moved.
No script is added (the wrapper is explicitly declined), none removed, none merged or split, and no boundary or
abstraction is introduced: the adapters are in place, TT07 is a check inside an existing script, and the
verdict-predicate relocation from row prose into code is dec-380's already-decided contract being applied to more
scripts. The one deletion — `_LEGACY_CITING_ROWS` — removes a *scope exemption* inside an existing test, not a
component. Category is therefore **behavioral**, not architectural, however consequential the AC10 trade-off felt.

## Considered Options

### A wrapper family script per tool (`check_<x>.py` importing and adapting)

Uniform, and the only shape that works for `aac_fence_validator.py`. Rejected for P08 and T02 because the additive
envelope achieves the same dispatch for zero new components, and rejected for AC10 on price: it would be a new
component, canary and registry entry bought for two Bash calls and 569 bytes, the worst ratio in the batch.

### In-place adapters for all three tools, including AC10

Rejected: giving `aac_fence_validator.py` a corpus-walking `--json` mode adds a second responsibility to a script whose
single-file shape two independent surfaces (CI `xargs`, architect-validator allowlist) depend on. The coupling cost
lands on surfaces this pipeline does not own.

### Keep DH01/DH06 as L-tier prose and shrink the allowlist

Rejected on evidence: both are already computed mechanically by `adr_health.py`, so leaving them to LLM judgment
spends sweep turns on a question a script has already answered — and they are the two largest single-row savings in
the DH block (−353 B and −775 B).

### Empty `_LEGACY_CITING_ROWS` but keep it and its staleness test

Rejected on Simplicity First: an empty frozenset plus ~25 lines of vacuously-green test is ceremony, and the probe
shows nothing else needs the exemption. If a future row genuinely cannot take either row form, the allowlist returns
**with its staleness test in the same commit**.

## Consequences

**Positive.** Projected `agents/sentinel.md` ≈90,176 B against today's exactly 100,993 B (−8,478 B of converted rows,
−3,326 B of Phase-3 prose, +987 B of new table rows, +≈250 B for a TT07 row) — measured, not divided. The runner's
reach goes 19 families / 62 checks → 29 / 80. Twelve per-script Bash calls fold into one `--table` call, with AC10's
two per-file calls the deliberate residue. Every converted verdict predicate gains a canary; the P08 golden bad-case
pair already exists at `tests/fixtures/sentinel/stale_slug_advisory/`.

**Negative / accepted.** AC10 stays the one sentence-dispatched check, so Phase 3 keeps two Bash calls it could in
principle lose. `check_gate_liveness.py`'s `check`→`kind` rename is breaking inside that script's own payload.
`adr_health.py` grows while already past its size and complexity ceilings (td-171, td-203 stay `open`); the mitigation
is `review: force` and a <50-line `classify()`, not a restructure. EC07's Invocation sits at exactly 20/20 flag
characters with zero headroom.

## Disconfirmation

- **Falsifier.** If a P08 or T02 consumer parses the `--json` payload with a **closed** schema (rejecting unknown
  keys) rather than by key lookup, the envelope is not additive and those two need wrappers after all. Re-check by
  running `/clean-work`'s classify step and the token-ratchet gate once after the change.
- **Steelmanned runner-up.** Wrap all three tools uniformly. It is genuinely better on one axis — one rule for the
  reader ("a check script is a check script"), no tool acquiring a second audience, and AC10 joins the table like
  everything else. It loses on measurement: three new components and three new canaries to buy what two added keys
  buy for free, plus two Bash calls.
- **Reversal trigger.** Re-open the AC10 decision when the in-scope architecture-markdown corpus passes ~5 files —
  at that point the per-file call cost overtakes the wrapper's cost. Re-open the flag-budget decision the moment EC07
  needs a second flag: at 20/20 characters the row form breaks, and either `_INVOCATION_FLAGS_MAX_CHARS` moves (a
  decision, cited) or EC07 returns to sentence dispatch.
