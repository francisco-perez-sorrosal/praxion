---
id: dec-380
title: Sentinel check extraction contract — three destinations, no new file
status: accepted
category: behavioral
date: 2026-09-09
summary: A sentinel `A`-typed check row keeps a fixed four-part shape (Conditional · Invocation · Verdict map · Spec pointer) whose whole Pass column must parse against that shape, with the verdict map budgeted at ≤300 bytes; rationale moves to the script's module docstring, golden bad-cases to the canary test, and reporting discipline to the script's `--json` output — never to a new reference file.
tags: [sentinel, process-economy, test-topology, data-structures, roadmap-p2-1]
made_by: agent
agent_type: implementation-planner
branch: worktree-process-economy-p2-1
pipeline_tier: standard
affected_files:
  - agents/sentinel.md
  - tests/test_sentinel_row_contract.py
  - .pre-commit-config.yaml
  - fitness/tests/test_gate_canary_coverage.py
  - scripts/check_architecture_projection.py
  - scripts/adr_health.py
  - scripts/test_adr_health.py
  - scripts/check_adr_reciprocity.py
  - scripts/test_check_adr_reciprocity.py
  - scripts/check_agent_prompt_size.py
  - scripts/test_check_agent_prompt_size.py
  - scripts/check_doc_manifest_freshness.py
  - scripts/test_check_doc_manifest_freshness.py
  - scripts/check_agent_lifecycle_pairing.py
  - scripts/test_check_agent_lifecycle_pairing.py
  - scripts/test_strip_progress_mandate.py
  - hooks/promote_learnings.py
  - hooks/test_promote_learnings.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06]
re_affirmed_by: [dec-381]
superseded_in_part_by: [dec-382]
---

## Context

`agents/sentinel.md`'s check catalogue carries 78 mechanically-checkable (`A`-typed) rows
totalling 46,910 bytes; 58 of them (28,968 bytes) cite no script and instead spell out — in prose,
read by the sentinel on every sweep — the check's rationale, its golden bad-cases, and the
discipline for phrasing a finding (bounds, denominators, INFO-vs-WARN partitions). The roadmap
(`docs/independent-analysis/process-economy-roadmap.md` §6 P2.1) names this as the first slice of a
52-row programme and proposes `skills/ecosystem-audit/references/<dimension>.md` as the destination
for the displaced prose.

That proposed destination has already been tried, for this exact catalogue, and it forked: the `SH`
dimension already points at
`skills/spec-driven-development/references/sentinel-spec-checks.md`, whose SH04 still states the
rule `agents/sentinel.md`'s own SH04 was rewritten to correct, and which omits SH08 entirely.
Nothing binds the reference file to the row that points at it, so the two drifted — in the
direction of the reference file carrying the **wrong** contract, which is the failure mode a
sentinel loading it on demand cannot detect.

**Record provenance**: the systems-architect pre-computed this decision and its category judgment
but ran out of turns before writing the record; the implementation-planner authored the fragment
mid-pipeline from that judgment (hence `agent_type`). The contract then changed twice during
implementation — the budget was re-scoped and re-derived, then the guard was rewritten from
strip-based to parse-based after a `light-review` — leaving the fragment stale in its numbers, its
scope, its mechanism and its file list. A systems-architect audited and corrected it against the
shipped contract on 2026-09-10, and re-tested the category against what actually shipped (see
Consequences § Category). The decision itself is unchanged.

## Decision

Every extracted `A`-row keeps exactly four parts, in order, and no fifth: **Conditional** (the
substrate-presence gate and its skip discipline, as a single folded sentence), **Invocation** (the
literal `` `python3 scripts/<name>.py --json` `` phrase — read by three structural consumers, see
Consequences), **Verdict map** (which JSON key maps to which finding severity), and **Spec
pointer** (the literal phrase `` Spec + golden bad-cases: `scripts/<name>.py` docstring; canary
`scripts/test_<name>.py`. ``). The canonical row shape is:

```
Conditional on <path> present[ (<qualifier>)]; skip with a[n] <D>-dimension INFO note. Run
`python3 scripts/<name>.py --json`. <verdict map> Spec + golden bad-cases: `scripts/<name>.py`
docstring; canary `scripts/test_<name>.py`.
```

**Budget: ≤300 bytes, binding the verdict map alone** — the Pass column with the three mandated
template parts parsed out — not the whole row and not the whole Pass column. A whole-row budget is
unsatisfiable (the Rule column carries its own separate ≤120-char budget); a whole-Pass-column
budget rations verdict-map room by script-name length, which tracks naming rather than prose
discipline. The ceiling is derived from the largest check in the pilot (P03, seven output classes:
a WARN naming `agent_id`/`agent_type`/`session_id`, three `info.*` counts, and `unmatched_stops`
split three ways) — estimated at 227 bytes, measured at 265 — plus margin. The intermediate
200-byte ceiling was abandoned because it falls 27 bytes short of that estimate and three of the
six rows would have failed it.

The guard **parses rather than strips**: one `re.fullmatch` over the entire Pass column, which must
decompose into `Conditional? + Invocation + verdict map + Spec pointer` in that exact order with
nothing left over. Anything unassignable to a named part — a reordered part, a fifth part, prose
parked after the Spec pointer — is a parse failure, not a silent zero. The predecessor strip-based
guard (remove recognised parts by regex, measure the leftover) was found by `light-review` to admit
a 986-byte Pass column that the whole-column guard it replaced would have rejected: it was weaker
than its own predecessor. Parse-don't-strip is what closes that.

Displaced content is routed by *kind*, to a destination that is already executed and therefore
cannot silently fork from the row without a test going red:

| Kind | Destination |
|---|---|
| Rationale, derivation, prior-defect history | the script's module docstring |
| Golden bad-case, inverse guard | the canary test (`scripts/test_<name>.py`) |
| Reporting discipline (bounds, denominators, INFO/WARN partitions) | a field in the script's `--json` output |

No new reference file and no new skill. The `--json` envelope for checks whose reporting discipline
requires it carries `check`, `skipped` (a tagged union — `null` when the check ran, otherwise
`{reason, path}` — never a boolean, so "could not run" and "ran and found nothing" cannot
collapse into the same empty-`findings` shape), `examined` (mandatory and non-empty when the check
ran), `findings[]` (each carrying its own `severity`), `info.*`, `withheld`, and `bound` (the
PASS-statement the sentinel must reproduce verbatim).

## Considered Options

### `skills/ecosystem-audit/references/<dimension>.md` (the roadmap's own proposal)

Rejected on three measured grounds: (1) the pattern has already run in this repo, for this
catalogue, and forked in the dangerous direction (see Context); (2) a plugin-distributed agent's
`Read` resolves against the *consumer's* working directory, not the plugin cache
(`skills/agent-crafting/SKILL.md` § Plugin agent self-containment) — a reference under
`agents/references/` would fail silently for a plugin install; (3) adding a `skills:` frontmatter
entry to `agents/sentinel.md` to reach a reference file would *preload* its body into every
sentinel run, trading a resident-prose cost for a resident-skill cost — the exact lever the
roadmap's own W2 analysis names as the largest single always-resident cost. Reference files remain
the correct destination for the 48 `L` (LLM-judgment) rows, which have no script and no test to
bind them; that split is `defer-with-rationale`, a separate task.

### One flat `A`-row template applied uniformly, ignoring content kind

Rejected: collapsing rationale, golden-cases, and reporting discipline into one undifferentiated
"see the script" pointer loses the binding property that motivates the whole extraction — a
docstring is read by whoever *changes* the check, a canary is *run* by CI, and a JSON field
*cannot* drift from the number it qualifies. A single pointer to "the script" recreates the SH
reference file's failure mode one level down, inside the script itself, with no test distinguishing
stale rationale from a stale golden-case.

## Consequences

**Positive**: the six-row pilot removes ≥11,000 bytes from `agents/sentinel.md` (AC-7) while every
check stays independently executable and CI-verified (AC-2); the contract is mechanically pinned
(`tests/test_sentinel_row_contract.py`'s whole-column parse plus its ≤300-byte verdict-map
assertion, `fitness/tests/test_gate_canary_coverage.py`'s `_delegated_gates` regex, and
`check_gate_liveness.py`'s GL04/GL05) rather than advisory, so the remaining 52 rows can follow it
without re-deriving the destination question. All six extracted rows pass: AC13 103, DH05 108,
DL06 67, F11 247, T03 253, P03 265 — all against the 300-byte ceiling. **The budget is in UTF-8
bytes, not characters**, and AC13 is the row where that distinction bites: its verdict map is 101
characters but 103 bytes, because a single em-dash (U+2014) costs 3 bytes. The other five are pure
ASCII, so their two counts coincide. Any future measurement of a row must use
`len(verdict_map.encode("utf-8"))`, as the assertion does — a character count silently understates
every row carrying an em-dash, and the residual-row template invites them.

**Negative / risk**: the literal `` python3 scripts/<name>.py `` phrase is now load-bearing for
canary-coverage discovery (`fitness/tests/test_gate_canary_coverage.py::_delegated_gates`) and gate
liveness (GL04/GL05) — a future row edit that *removes* rather than adds such a phrase can silently
shrink enforcement (this pipeline's own F11 step is gated by `verifier` light-review for exactly
this reason). The four-part template is a manual convention enforced by one contract test; a script
author who edits the row without re-reading the template can still regress it, bounded by the
whole-column parse and the ≤300-byte verdict-map assertion.

**Known weakness — the flat ceiling may be tracking the wrong variable.** The six measured margins
are **bimodal**: 67 / 103 / 108 against 247 / 253 / 265, with 139 bytes of empty space and no row
between. The low cluster is checks with one or two output classes; the high cluster, five or more.
That pattern suggests the verdict map's size is governed by the check's **number of output
classes** — an intrinsic property of what the check reports — and not by the prose discipline of
whoever wrote the row, which is the variable the budget is meant to bind. If so, a flat ceiling
will keep being wrong in both directions as the remaining 52 rows arrive: permissive for terse
two-class checks, and a false constraint on a genuinely richer check whose verdict map is
irreducible. **Six data points are not enough to change the contract now**, and the ceiling clears
the current worst case with 35 bytes of margin. The falsifier for the flat ceiling is a
seventh-or-later extracted check whose verdict map is irreducibly over 300 bytes at its true
output-class count — at which point the budget should be re-derived as a function of class count
rather than raised again as a flat number.

**Envelope adoption is partial as shipped, and correctly so.** This paragraph was corrected twice
during verification, both times narrowing an over-counted non-conformance rather than widening it.
First pass claimed four of six extracted checks emit a bare list of `{check, entity, severity,
message}` finding dicts (AC13, DH05, T03, F11), with only DL06 `check_adr_reciprocity.py` and P03
`check_agent_lifecycle_pairing.py` carrying the full `skipped`/`withheld` envelope. That count was
wrong: AC13 `check_architecture_projection.py` already emits `skipped`/`withheld` (lines 231, 311
in that script) — it was mis-assigned to the bare-list group by not re-reading the pre-existing
script before writing this paragraph. Real non-conformance was **1 of 6**: F11
`check_doc_manifest_freshness.py`'s row promises "skip with an F-dimension INFO note" but its
`--json` collapsed five distinct states (manifest absent, `generated_at` unparseable, git
unanswerable, no qualifying commit, genuinely fresh) into one bare `[]`, discarding the skip reason
its own `logger.info` call had just computed — a row making a promise its script could not keep.

That gap is now closed: F11 emits a `skipped` tagged union (`{"reason": ..., "detail": ...}`,
matching `check_adr_reciprocity.py::_skipped_report`'s shape) for the three states where the check
could not examine reality, and reserves `skipped: None, findings: []` for the two where it ran to
completion and found nothing. **Real non-conformance is now 0 of 6.** DH05 `adr_health.py` remains
a pre-existing script with its own established output contract (unchanged assessment — no defect
was ever claimed there). T03 `check_agent_prompt_size.py`'s bare-list shape is sound as-is: its row
carries no `Conditional` skip clause, so it owes no skip signal to collapse into an empty list in
the first place — an exemption the first pass stated correctly and this rework leaves untouched.
The envelope is therefore the shape for checks whose row promises a skip signal, not a universal
property of every extracted check.

**Category**: `behavioral` stands, re-tested against what shipped rather than inherited. Applying
the falsifier in `rules/swe/adr-conventions.md` — *name the component added, removed, merged,
split, or whose responsibility moved* — yields no component name. The six new `scripts/check_*.py`
files land inside `Scripts` (`tooling.scripts`), a single Built component in `.ai-state/DESIGN.md`
§3a; adding files within an existing surface is the worked example the test classifies as
`implementation`, not `architectural`. The `A`-row → script delegation boundary was **not**
introduced here: `agents/sentinel.md` carried 22 `python3 scripts/…` invocations before this
pipeline and carries 26 after, and the structural consumers that key on the phrase
(`_delegated_gates`, GL04, GL05) all predate it. Six checks crossing an existing boundary is
traffic across that boundary, not its introduction, and the responsibility split between the agent
definition and the script layer is unchanged in kind. The published half does not fire either:
`affected_files` touches no canonical block, shipped template, or onboard-contract phase. What this
record decides is the *shape and destination* of displaced prose — a convention governing how rows
are written, which is `behavioral`.

**Scope note**: this decision governs the residual-row shape for `A`-typed, script-backed checks
only. The 48 `L`-typed (LLM-judgment) rows keep the reference-file destination, unaffected by this
record.
