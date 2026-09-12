---
id: dec-381
title: Sentinel residual extraction uses family check scripts, bound by a row/registry/script triangle
status: accepted
category: behavioral
date: 2026-09-12
summary: The 55 script-less sentinel `A` rows are extracted into ~12 family scripts (N rows cite one `python3 scripts/<family>.py --json`, each row selecting its own `check` id from one keyed envelope) rather than one script per row; dec-380's four-part row template, its 300-byte verdict-map budget and its parse-don't-strip guard are re-affirmed unchanged, and the new drift mode a shared script creates is closed by a three-way equality between catalogue rows, `EXTRACTED_CHECKS` and each script's declared `CHECK_IDS`.
tags: [sentinel, process-economy, roadmap-p2-1, data-structures, testing]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p2-residual
pipeline_tier: standard
affected_files:
  - agents/sentinel.md
  - tests/test_sentinel_row_contract.py
  - .pre-commit-config.yaml
  - fitness/tests/test_gate_canary_coverage.py
  - scripts/check_adr_reciprocity.py
  - scripts/check_agent_lifecycle_pairing.py
  - scripts/check_architecture_projection.py
  - scripts/adr_health.py
  - .ai-state/decisions/380-sentinel-check-extraction-contract.md
re_affirms: [dec-380]
---

## Context

`dec-380` settled the shape of an extracted sentinel `A`-row (Conditional · Invocation · Verdict map ·
Spec pointer, verdict map ≤300 UTF-8 bytes, guard parses rather than strips) on a six-row pilot. It
left open the question the residual forces: **55 remaining script-less `A` rows, one script each, or
many rows per script?**

Two measurements decide it, and neither was available when `dec-380` was written.

**First, operational cost is per script, not per row.** Every check script costs a source file, a
canary test file, a `.pre-commit-config.yaml` entry, and makes the literal `python3 scripts/<x>.py`
phrase a live gate for three structural consumers (`fitness/tests/test_gate_canary_coverage.py::_delegated_gates`,
`check_gate_liveness.py`'s GL04 and GL05). Fifty-five of those is not tractable; the pilot's own
cost — six rows for 19 spawns and 21 commits — is the evidence.

**Second, `dec-380`'s template has a fixed floor that makes one-script-per-row byte-negative for most
of the residual.** Measured against `RESIDUAL_ROWS.md` (55 rows, 14,700 bytes of Pass column):
17 rows exceed 300 B and total 10,967 B; 29 rows are at or under 100 B and total only 1,653 B. The
template floor is `179 + 3·len(script_name)` bytes of Pass column before the verdict map — roughly
254 B for a realistically-named script. Extracting all 55 rows nets about −1,000 B: the ~6.4 KB won
on the 17 large rows is spent back by ~5.0 KB of growth on the 29 small ones. The extraction
programme therefore cannot be justified on bytes alone, and a design that ignores this inverts its
own purpose.

## Decision

**Family script per dimension cluster.** N catalogue rows cite one
`` `python3 scripts/<family>.py --json` ``; the script emits **one envelope** whose `findings[]`
entries each carry a `check` id and a `severity`, and each row's verdict map selects only its own id.
Approximately ten new family scripts plus two extensions of existing scripts cover 53 of the 55 rows;
two rows (`T01`, `T04`) are recorded `leave-as-is`.

`dec-380`'s contract is **re-affirmed unchanged** and needs no amendment to permit this:
`EXTRACTED_CHECKS` already registers `(check_id, script_name)` pairs with no uniqueness constraint on
the script name, and both the Invocation and the Spec pointer name the *script*, not the check.

Three things are added.

**1. The keyed envelope, for new family scripts only.** `dec-380`'s singular envelope is lifted to
mappings keyed by check id:

```json
{"script": "...", "checks": ["DL01", "..."],
 "skipped":  {"DL01": null, "SH01": {"reason": "substrate-absent", "path": ".ai-state/specs/"}},
 "examined": {"DL01": {"adrs": 380}, "SH01": null},
 "findings": [{"check": "DL02", "entity": "...", "severity": "fail", "message": "..."}],
 "info": {...}, "withheld": [...], "bound": {"DL01": "..."}}
```

`skipped` is keyed **per check**, not per script, because a family's checks have different substrates.
A script-scope `skipped` would collapse "the specs walk could not run" into "the family skipped" —
re-creating one scope up exactly the collapse `dec-380`'s tagged union exists to prevent. The union's
value shape mirrors `scripts/check_adr_reciprocity.py::_skipped_report` verbatim.

**A narrow exemption, stated rather than discovered later:** a script is **flat** iff it declares
`CHECK_ID` and **keyed** iff it declares `CHECK_IDS`. The keyed obligation binds *new* family scripts.
A pre-existing script may declare `CHECK_IDS` to register re-pointed rows while keeping its
established output contract — which is what lets `scripts/adr_health.py` absorb the `DH02`/`DH04` rows
as a zero-code re-point instead of a breaking rewrite that four other rows consume. Same spirit as
`dec-380`'s `T03` exemption: the obligation follows the promise the row makes.

**2. `CHECK_IDS`, a literal module-level tuple.** Literal so the contract test reads it with
`ast.literal_eval` **without importing** the script; a dynamically-computed value fails the parse by
design.

**3. The row/registry/script triangle.** A shared script creates a drift mode single-row scripts did
not have. `tests/test_sentinel_row_contract.py` gains a three-way set equality, per script named in
`EXTRACTED_CHECKS`, between: (a) the catalogue rows citing `python3 scripts/<f>.py`, (b) the
`EXTRACTED_CHECKS` entries whose `script_name` is `<f>`, and (c) the `CHECK_IDS` declared in
`scripts/<f>.py`. All three legs parse; none enumerates. Leg (a) is scoped to scripts already in
`EXTRACTED_CHECKS`, because the catalogue carries ~20 pre-`dec-380` rows citing scripts in legacy
shape that an unscoped leg would fail on immediately. Each leg carries its own canary, and
`test_no_unbounded_quantifier_escapes_the_verdict_slot`'s property is preserved and widened to scan
every pattern the module builds rather than only `_row_pattern("x")`.

Finally, the programme is **tiered and measurement-gated**: families with a non-positive byte delta
run first; families that grow the file buy determinism knowingly and say so; and the single largest
family (twelve `C`/`N`/`S` conformance rows, estimated +2,880 B) ships only if a measured file-size
threshold is met after the preceding batch. `agents/sentinel.md` may never be larger at a batch
boundary than it was before that batch.

## Considered Options

### One script per row (55 scripts)

Rejected on measured cost. It produces an identical row-byte outcome — the template floor is charged
per row either way — for 4.5× the artifacts (55 files, 55 canaries, 55 pre-commit entries, 165
gate-consumer edges), and it cannot reach `agents/sentinel.md` Phase 3's stated 15–20-turn target,
which requires roughly one Bash call per dimension rather than one per check.

### Family script with a flat, script-scope envelope

Rejected. A single `skipped` for a script whose checks read different substrates makes "this check's
substrate is absent" and "this check ran and found nothing" indistinguishable — the precise failure
`dec-380` names when it forbids a boolean `skipped`. Preserving that property at check granularity is
the whole reason the envelope is keyed.

### An array of `dec-380` envelopes, one per check

Defensible and rejected on ergonomics: every consumer must iterate to find one check, and `script`
and `withheld` duplicate N times for no gain. The keyed form is the same information with one lookup.

### Registering rows without a `CHECK_IDS` declaration (registry as sole source of truth)

Rejected: it leaves leg (b) of the triangle unprovable. A row could point at a check its script never
emits, and nothing would notice — the exact class of silent enforcement loss `dec-380`'s Consequences
already flags as this contract's standing risk.

## Consequences

**Positive.** Twelve artifacts instead of fifty-five. Substrate walks amortise (one
`skills/*/SKILL.md` read serves six verdicts). The triangle converts `EXTRACTED_CHECKS`'s
append-only-by-convention status — today a row could cite a script with no registry entry and no test
would notice — into a mechanical equality, closing latent debt that predates this decision. Every
extracted row's verdict becomes deterministic and CI-tested rather than improvised per sweep.

**Negative / risk.** A family script has a larger blast radius: a bug in a six-row script reddens six
rows at once. Mitigated structurally by the per-check `skipped`/`examined` pair — a broken substrate
degrades one check, not the family — and by one canary per check id inside the family's canary file.
A family file can also approach the 800-line ceiling; `check_artifact_conformance` (twelve checks) is
the candidate, and the triangle makes a split mechanical if it crosses.

**The honest byte claim, stated so it is not inherited wrongly.** `≈5–7 KB` holds **only for the 17
rows above 300 B**. Across all 55 the net is approximately −1,000 B before dispatch-block deletions.
Any future citation of this programme's payoff must say which band it is talking about. The
programme's defensible value is (a) deterministic, CI-tested verdicts and (b) fewer Phase 3 turns —
not a governed-budget token win, since these bytes are sentinel-resident rather than always-loaded.

**`dec-380`'s own falsifier is inherited, not reset.** That record names a seventh-or-later extracted
check whose verdict map is irreducibly over 300 B as the signal to re-derive the budget as a function
of output-class count. This programme extracts fifty-three more checks and is where that falsifier
will fire if it is going to. If it does: record it and re-derive; do not raise the flat number.

**Category**: `behavioral`. Applying the falsifier in `rules/swe/adr-conventions.md` — *name the
component added, removed, merged, split, or whose responsibility moved* — yields no component name.
Ten new `scripts/check_*.py` files land inside `Scripts` (`tooling.scripts`), a single Built component
in `.ai-state/DESIGN.md` §3a whose file catalog is enumerated by filesystem scan; `dec-351` set that
precedent explicitly ("Adds no §3a structural component … the new script lives inside the existing
`Scripts` row") and `dec-380` applied it to the six pilot scripts. The `A`-row → script delegation
boundary was not introduced here either — `agents/sentinel.md` carries 26 `python3 scripts/…`
invocations today. The published half does not fire: no canonical block, shipped template, or
onboard-contract phase changes. What this record decides is which *shape* of script a row delegates
to and what binds the two — a convention, which is `behavioral`. Consequently
`.ai-state/DESIGN.md` and `docs/architecture.md` require no update.

## Prior Decision

This record **re-affirms `dec-380`** rather than superseding or partially superseding it. Everything
`dec-380` decided stands unchanged and in force: the four-part row template and its order, the
≤300-byte verdict-map budget in UTF-8 bytes, the parse-don't-strip whole-column guard, the routing of
displaced content by kind (rationale → module docstring, golden bad-cases → canary, reporting
discipline → `--json` field), and the refusal of a new reference file or skill.

What this record adds is the case `dec-380` did not contemplate, because its pilot had no instance of
it: a script emitting **more than one** check. The singular `check` key moves into each finding, a
`script` + `checks[]` pair names the script's declared surface, and the four scalar envelope fields
become mappings keyed by check id — a shape for a new case, not a narrowing of the old one, which is
why the relation is re-affirmation and not partial supersession. `dec-380`'s single-check envelope
remains the contract for every single-check script, including all six pilots, which are not retrofitted.
