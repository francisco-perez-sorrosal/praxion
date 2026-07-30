# SPEC: Multidisciplinary Consulting Identities (Wave 1 — `statistician`)

**Task slug**: `multidisciplinary-identities`
**Feature**: Add a discipline-parameterized adversarial consultant agent, a data-only discipline registry that makes identity N+1 structurally free, one new knowledge skill (`applied-statistics`), a gated four-round dialogue protocol bounded at one loop-back, and a countable disposition ledger
**Tier**: Full
**Pipeline branch**: `worktree-multidisciplinary-identities`
**Start date**: 2026-07-29
**End date**: 2026-07-30
**Archived**: 2026-07-30
**Status**: Implemented and verified — all 16 steps complete; verifier verdict **FAIL on one record-keeping finding** (this spec's absent REQ→test mapping, now reconstructed below), with **17/18 ACs PASS and zero unmet acceptance criteria**. The one WARN (AC15, a cost envelope discharged by structural argument) was closed by measurement on 2026-07-30 — see §17.12 of the evidence dossier. AC13 (two disciplines concurrently) remains **deferred, not failed**: untestable at a one-discipline roster, tracked as `td-070`
**ADRs**: `dec-303` (peer not lens), `dec-302` (parameterized agent + registry + runtime binding; re-affirms `dec-243`), `dec-301` (model/effort routing; re-affirms `dec-076`), `dec-298` (dialogue protocol; re-affirms `dec-154`), `dec-299` (disposition ledger), `dec-300` (selection tiers + Wave-1 scope fence)
**Evidence base**: [`docs/multidisciplinary-identities-evidence.md`](../../docs/multidisciplinary-identities-evidence.md) (committed; §9.1 extensibility criterion, §10 dialogue protocol, §11 selection model, §15 Wave-A outcomes, §16 binding user rulings)

## Feature Summary

Praxion already owns most of the domain expertise a multidisciplinary reviewer would bring; what it lacks is a
**voice with standing to object**. This feature adds exactly one new party — a `discipline-consultant` agent
parameterized by a `Discipline: <name>` spawn directive — whose roster lives as a **data table in a skill
reference file** and whose discipline knowledge binds at **runtime through the `Skill` tool`**, so adding
discipline N+1 changes zero always-loaded bytes, zero rule files, zero agent files, zero `plugin.json` entries,
zero `tools:`/`skills:` entries, and touches at most two files. Wave 1 ships one discipline, `statistician`,
whose binding is the single genuinely-new knowledge artifact (`applied-statistics`).

The consultant is **adversarial-only**: it challenges, never decides, and authors no ADR fragments — which is
what distinguishes it from the two existing decision-authority sub-architects. Dialogue is gated (never
always-on), runs four rounds (isolate → challenge → disposition → reconcile) bounded at one orchestrator-mediated
loop-back reusing the existing challenge-loop mechanism, and terminates on **dispositions recorded**, not on
absence of visible disagreement. Every challenge is dispositioned in the existing
`switch-now`/`defer-with-rationale`/`dismiss-with-rationale` vocabulary and lands as one row in a new append-only
`.ai-state/CONSULT_LEDGER.md`, which is the initiative's own falsifier and the calibration loop the authored
trigger table needs to beat random selection. The extensibility criterion and the disposition counter are both
treated as **health guards with verifiable requirements** (REQ-16, REQ-17), enforced by a committed fitness test
rather than by prose.

## Requirements

- **REQ-01 — peer, not lens.** When a discipline is added to the registry, the system records it in the discipline registry only and does not add an entry to `skills/software-planning/references/design-synthesis.md`'s Lens Catalog, so the closed-catalog protocol is not re-entered through a differently-named door and no supersession is incurred.
- **REQ-02 — lens-collision is declared, not remembered.** When a registry row is written and its `lens-collision` field is empty or absent, the committed fitness test fails, so a discipline sharing an existing lens's owning artifact cannot ship without its collision being stated.
- **REQ-03 — discipline parameterization resolves from the registry.** When the consultant is spawned with a `Discipline: <name>` directive whose value matches a registry row, the system resolves that row, loads its `binds-to` skill, and logs the resolved discipline on its first `PROGRESS.md` phase line, so one agent definition serves N disciplines with an auditable selection.
- **REQ-04 — the registry is the authored trigger table.** When a convener evaluates whether to convene a discipline, it matches task signals against the registry's `fires-when` predicate column, and no `paths:`-less rule file or `CLAUDE.md` names any discipline, so Tier-1 selection stays bounded and authored while costing zero always-loaded bytes.
- **REQ-05 — knowledge binds at runtime, not at frontmatter.** When a discipline's bound skill is not listed in the consultant's `skills:` frontmatter, the consultant loads it through the `Skill` tool, and the `skills:` and `tools:` frontmatter values remain byte-identical across every discipline addition, so a gap discipline costs two files rather than three and the prompt cache is never invalidated.
- **REQ-06 — difficulty routing is generic.** When a consultant is spawned, the convener maps the registry row's `difficulty-hint` (`routine`/`standard`/`high-stakes`) to a per-spawn `model` (`sonnet`/`opus`/`opus`) and adds the `ultrathink` keyword to the spawn prompt for `high-stakes` only, so difficulty-keyed heterogeneity exists without a per-discipline routing row.
- **REQ-07 — routing dimensionality is unchanged.** When this feature lands, `rules/swe/agent-model-routing.md` gains exactly one tier-table row and no effort column, and the consultant definition declares no `effort:` frontmatter, so the prior 1D-routing decision holds and no unimplementable per-spawn effort parameter is specified.
- **REQ-08 — round 0 is isolated and the isolation is checkable.** When the consultant produces `## Independent Reading`, it has read neither `SYSTEMS_PLAN.md`, nor `IMPLEMENTATION_PLAN.md`, nor any sibling `CONSULT_*.md`, and it records the sources it did read in a `## Sources Read` section, so correlation collapse is prevented and the prevention is verifiable from the artifact.
- **REQ-09 — every challenge names a decision and a test.** When the consultant writes a `## Challenges` entry, that entry carries a falsifiable claim, the named decision it would change, the test that would settle it, and a calibrated confidence; an entry lacking the decision is not written, so decorative expertise is filtered mechanically.
- **REQ-10 — every challenge is dispositioned.** When the orchestrator routes challenges back, the convener records exactly one of `switch-now`/`defer-with-rationale`/`dismiss-with-rationale` with a rationale for each, so silent dismissal remains a behavioural-contract violation and zero challenges are left unanswered.
- **REQ-11 — one loop-back, then stop or escalate.** When a challenge is not resolved after one orchestrator-mediated re-evaluation round, the system escalates to the user with both positions stated rather than opening a second consult round for the same discipline and task, so the termination condition is explicit and bounded.
- **REQ-12 — reconciliation is single-owner and per-challenge.** When N consultant fragments exist, one party merges them and adjudicates each challenge individually, and no blended narrative summary replaces the per-challenge dispositions, so the aggregation step does not average challenges away.
- **REQ-13 — one ledger row per challenge, one writer.** When a challenge is dispositioned, the convener appends exactly one row to `.ai-state/CONSULT_LEDGER.md` carrying timestamp, task slug, discipline, stage, challenge id, claim, decision-at-stake, disposition, rationale reference, model, and difficulty; the consultant never writes the ledger, so there is no write race under concurrent instances and the four-writer tech-debt contract stays untouched.
- **REQ-14 — silence is caught separately from ratios.** When a `CONSULT_*.md` carries a non-empty `## Challenges` section with no recorded disposition, sentinel `P07` emits a finding; when the section is absent or every challenge carries a disposition, `P07` passes, so an un-reconciled challenge cannot vanish by leaving no ledger row.
- **REQ-15 — self-nomination is auditable.** When an agent nominates a consultant, it cites the triggering signal and the decision at stake, so a bad nomination surfaces as a dismissed challenge and is counted rather than being invisible. **Nominators are gated by the registry's `attaches-to` field, not by this requirement**: at Wave 1 that is `researcher` and `systems-architect` only. `implementation-planner` and `verifier` are **consumers**, not nominators — they read and check `CONSULT_<discipline>.md` but never convene one. The two roles are deliberately distinct, and conflating them would imply four live nomination paths where the registry permits two.
- **REQ-16 — extensibility criterion (health guard).** When a discipline is added to the registry, the change touches **≤2** files and produces **0** byte delta in every `paths:`-less rule file and every `CLAUDE.md`, **0** new `agents/*.md` files, **0** `.claude-plugin/plugin.json` entries, **0** consultant `tools:` entries, **0** consultant `skills:` entries, and **0** new pipeline stages; and when any of these is violated — including a registry discipline name appearing in the consultant's `description:`, in a `paths:`-less rule, or in a `CLAUDE.md` — the committed fitness test `fitness/tests/test_discipline_registry_invariants.py` fails, so the criterion is asserted rather than documented.
- **REQ-17 — disposition counter (health guard).** When at least one consultation has completed, a dismiss rate per discipline is derivable from `.ai-state/CONSULT_LEDGER.md` by a `grep` and a count with no parser, and the ledger exists before or in the same change as the first discipline's registry row, so the initiative's falsifier is measurable from day one rather than retrofitted.
- **REQ-18 — Wave-1 scope fence.** When the consultant is spawned with a `Discipline:` value absent from the registry, it writes no challenges and returns `[BLOCKED]` naming the unresolvable value; and when a recurring "we needed a discipline X here" signal appears, the system records it for human disposition rather than instantiating a new discipline, so the roster stays bounded and open-ended self-selection — the mechanism the literature predicts will fail — is never entered. **Clause 2 shipped 2026-07-30** (`td-067`), deliberately as the *recording* half only: `agents/skill-genesis.md` gains a fourth triage leaf that captures a recurring "we needed a specialist voice here" signal into a `## Discipline-Gap Signals` report section for human disposition, and is explicitly forbidden from proposing a discipline or drafting a registry row. That split is what the requirement's own wording asks for — *records it … rather than instantiating a new discipline* — and it keeps `dec-300`'s Tier-3 identity-genesis deferral intact: genesis remains gated, recording does not. Recording had to ship first, because the Tier-3 gate is denominated in evidence that nothing was collecting. Clause 1 (`[BLOCKED]` on an unresolvable discipline) is live-proven.

## Acceptance Criteria

- [ ] **AC1 (gating):** no `CONSULT_*.md` exists for a task with no load-bearing specialist claim in scope; the consultant is never spawned unconditionally at a phase boundary. → REQ-04
- [ ] **AC2 (parameterization):** a `Discipline: statistician` spawn resolves the registry row, loads `applied-statistics` via the `Skill` tool, and logs the discipline to `PROGRESS.md`. → REQ-03, REQ-05
- [ ] **AC3 (fail loud):** an unknown `Discipline:` value produces `[BLOCKED]` with the value named, and zero challenges. → REQ-18
- [ ] **AC4 (isolation checkable):** `## Sources Read` is present and excludes `SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`, and every sibling `CONSULT_*.md`. → REQ-08
- [ ] **AC5 (challenge shape):** every `## Challenges` entry carries claim + decision-at-stake + settling test + confidence. → REQ-09
- [ ] **AC6 (zero undispositioned):** every challenge carries one of the three vocabulary values with a rationale. → REQ-10
- [ ] **AC7 (one loop-back):** at most one re-evaluation round per task; non-convergence escalates rather than iterating. → REQ-11
- [ ] **AC8 (single-owner adjudication):** per-challenge dispositions present; no blended summary substituting for them. → REQ-12
- [ ] **AC9 (countability):** `.ai-state/CONSULT_LEDGER.md` has one row per challenge; dismiss rate derivable by `grep`+count. → REQ-13, REQ-17
- [ ] **AC10 (extensibility asserted):** `fitness/tests/test_discipline_registry_invariants.py` passes on the shipped tree, and **fails** on a canary tree where a registry discipline name is injected into the consultant `description:` (gate-liveness proof — the test must bite before it is trusted). → REQ-16
- [ ] **AC11 (generic description):** the consultant `description:` contains no registry discipline name. → REQ-16
- [ ] **AC12 (budget):** total always-loaded content stays under 25,000 tokens; the measured rules-budget delta is ~330 tok (14.3% of the 2,309-tok headroom), reported separately from the ~344-tok skill/agent listing-pool delta. → REQ-07, REQ-16
- [ ] **AC13 (multi-instance):** two concurrent disciplines write `CONSULT_<a>.md` and `CONSULT_<b>.md` with no shared-file write and no cross-read during round 0. → REQ-08, REQ-13 — **DEFERRED, not failed** (`td-070`): untestable by construction at a one-discipline roster. Becomes testable the moment a second registry row ships, and should be exercised as the *first* act of Wave 2 rather than assumed.
- [ ] **AC14 (methodological framing):** no registry row, agent body line, or skill line frames a discipline sociodemographically; framing is procedure-shaped. → REQ-01
- [x] **AC15 (cost envelope):** a convened consultation stays within ≤3× baseline routine / ≤6× high-stakes total pipeline cost, bounded by the 2–3 concurrent cap and the one-round bound. → REQ-06, REQ-11 — **MEASURED 2026-07-30** (`docs/multidisciplinary-identities-evidence.md` §17.12): observed **1.255×** against ≤3× and **1.466×** at the 3-concurrent cap against ≤6×, on a deliberately conservative (small) denominator. Previously discharged by structural argument; `n`=1 `standard` consult, no `high-stakes` consult observed.
- [ ] **AC16 (no knowledge duplication):** `skills/applied-statistics/` covers pre-collection power/sample-size planning, inferential statistics for evals (multiple comparisons, bootstrap CIs on pass@k, judge agreement, non-determinism variance), confounding and Simpson's paradox in metric trends, and **derived** tolerance bands; it cross-references rather than restates `skills/performance-architecture/references/benchmarking.md § Statistical Rigor`. → REQ-05
- [ ] **AC17 (sentinel self-reference):** `agents/sentinel.md` check `BC03`'s enumerated agent list and its literal count are updated in the same change as the new agent, and `P07`'s scope covers `CONSULT_*.md`. → REQ-14
- [ ] **AC18 (registry completeness):** every registry row has all seven fields populated, `lens-collision` included. → REQ-02, REQ-16

## Traceability Matrix

| REQ | Behaviour | ADR | Primary artifact | Verifying AC |
|---|---|---|---|---|
| REQ-01 | Peer, not lens; methodological framing | `dec-303` | `agents/discipline-consultant.md` | AC14 |
| REQ-02 | `lens-collision` declared per row | `dec-303` | `discipline-registry.md` | AC18 |
| REQ-03 | `Discipline:` directive resolution | `dec-302` | `agents/discipline-consultant.md`, `agents/CLAUDE.md` | AC2 |
| REQ-04 | Registry `fires-when` = Tier-1 table | `dec-302`, `dec-300` | `discipline-registry.md` | AC1 |
| REQ-05 | Runtime `Skill`-tool binding; fixed frontmatter | `dec-302` | `agents/discipline-consultant.md` | AC2, AC16 |
| REQ-06 | Generic difficulty→model policy | `dec-301` | `rules/swe/agent-model-routing.md`, `discipline-registry.md` | AC15 |
| REQ-07 | 1D routing preserved; no `effort:` | `dec-301` | `rules/swe/agent-model-routing.md` | AC12 |
| REQ-08 | Round-0 isolation + `## Sources Read` | `dec-298` | `CONSULT_<discipline>.md` schema | AC4, AC13 |
| REQ-09 | Challenge carries decision + test | `dec-298` | `CONSULT_<discipline>.md` schema | AC5 |
| REQ-10 | Disposition obligation | `dec-298` | `coordination-details.md`, `agents/systems-architect.md` | AC6 |
| REQ-11 | One loop-back, then escalate | `dec-298` | `coordination-details.md` | AC7, AC15 |
| REQ-12 | Single-owner, per-challenge adjudication | `dec-298` | `agents/systems-architect.md` | AC8 |
| REQ-13 | One ledger row per challenge, one writer | `dec-299` | `.ai-state/CONSULT_LEDGER.md` | AC9, AC13 |
| REQ-14 | `P07` presence gate extended | `dec-299` | `agents/sentinel.md` | AC17 |
| REQ-15 | Self-nomination cites signal + decision | `dec-300` | nominators: `agents/researcher.md`, `agents/systems-architect.md`; consumers (read/check, never nominate): `agents/implementation-planner.md`, `agents/verifier.md` | AC6 |
| **REQ-16** | **Extensibility criterion (health guard)** | `dec-302` | `fitness/tests/test_discipline_registry_invariants.py` | AC10, AC11, AC12, AC18 |
| **REQ-17** | **Disposition counter (health guard)** | `dec-299` | `.ai-state/CONSULT_LEDGER.md` | AC9 |
| REQ-18 | Wave-1 scope fence; no self-instantiation | `dec-300`, `dec-303` | `agents/discipline-consultant.md`, `agents/skill-genesis.md` (deferred path) | AC3 |

### Test coverage (reconstructed at verification, 2026-07-30)

The matrix above is the **design-time** REQ→ADR→artifact mapping authored by the architect. The
**as-built** REQ→test mapping was never captured: the pipeline's `traceability.yml` shipped with 18 of
19 `tests:` arrays empty, the implementer's fragment was never merged into it, and no test-engineer
fragment was ever written. The verifier reconstructed the mapping below by reading the shipped tree and
`fitness/tests/test_discipline_registry_invariants.py` function by function — **not** by grepping test
names for REQ ids, which correctly contain none. It is rendered here because `.ai-work/` is deleted at
pipeline end and this is the only durable home.

| Bucket | Count | REQs |
|---|---|---|
| Test-covered — an automated regression test would catch a regression | **3** | REQ-02, REQ-05, REQ-16 |
| Partially test-covered — one clause tested, others not | **5** | REQ-04, REQ-13, REQ-14, REQ-17, REQ-18 |
| Code present, no test, live-demonstrated once (Step 15) | **6** | REQ-03, REQ-08, REQ-09, REQ-10, REQ-12, REQ-18 clause 1 |
| Code present, no test, no live exercise | **4** | REQ-01, REQ-06, REQ-07, REQ-15 |
| Prose only — no test, no live exercise | **1** | REQ-11 |
| **No implementation at all** | **1** | REQ-18 clause 2 — the skill-genesis recording path |

**Honest reading.** REQ-16 (the extensibility health guard) is armoured — seven assertions including a
live canary. REQ-02 and REQ-05 are solid. Everything else rests on prose plus the single Step-15 smoke
test. That distribution is *defensible* for a feature whose behaviour is mostly LLM-interpreted contract
— a fitness test cannot assert that an agent genuinely refrained from reading a file, which is why
Round-0 isolation is evidenced by the artifact's `## Sources Read` rather than by a unit test — but it is
materially weaker than an unpopulated `traceability.yml` communicated, which was nothing at all.

Known gap carried forward as tech debt: **REQ-18 clause 2 has no implementation** — nothing records a
recurring "we needed discipline X here" signal, so the Tier-3 deferral has no data-collection path
feeding it. Filed rather than silently closed.

## Key Decisions (Cross-Reference)

| Decision | ADR | One-line |
|---|---|---|
| Peer, not lens; Lens Catalog untouched | `dec-303` | Verified precedent + mechanical difference; deferred collision becomes a required registry field plus a reversal trigger |
| One parameterized agent; roster as data; runtime binding | `dec-302` | Re-affirms `dec-243` — a consultant gives *any* skill standing to object without a per-domain agent |
| Model axis real, effort axis not settable per spawn | `dec-301` | Re-affirms `dec-076` — both its 2D re-open triggers verified un-fired; `ultrathink` is the disclosed fallback |
| Four rounds, one loop-back, adjudicate per challenge | `dec-298` | Re-affirms `dec-154` — same orchestrator-mediated loop, heavier disposition obligation (no decision authority) |
| Dedicated single-writer append-only ledger | `dec-299` | Four-writer tech-debt contract preserved; a dismissed challenge is not debt |
| Tier 1 + Tier 2 ship, Tier 3 gated | `dec-300` | Proposing new routes before the existing route has one measured disposition breeds uncalibrated routers |

## Registered Objections (carried, not resolved)

1. **Ruling 3 as literally stated is not implementable.** Per-instance reasoning-effort selection has no
   Agent-tool per-invocation parameter; per-subagent thinking is explicitly absent and `thinking.budget_tokens`
   is forbidden on routed Opus. The ruling's *intent* is complied with via per-spawn `model` + `ultrathink`;
   the gap is disclosed in `dec-301` rather than papered over.
2. **Hand-authored routing remains untested against a random baseline.** Every validated router in the retrieved
   literature is learned or model-scored. Tier 1 is *analogous to* a validated mechanism, not an instance of one.
   The falsifier should be measured on **variance as well as mean** accepted-challenge rate. Only the ledger can
   retire this.
3. **The evidence for domain-expert labels specifically is weak, and the one study isolating persona content
   measured its worst regression on *coding*.** The design is deliberately shaped so the structural benefit (a
   bounded independent read plus a forced disposition) survives even if the discipline label proves inert; nobody
   has measured the persona tax at frontier tier, and that is the binding uncertainty.
4. **The consultant scores ~1.5/3 on `dec-243`'s earns-its-place test** (passes the conflicting-seam part, fails
   hand-forward decision authority by design, partially meets blast radius). Stated rather than claimed as a
   clean pass; what resolves it is that `dec-243` evaluated a different role shape and its own `dissent:` names
   the residue this design fills.

## Post-Ship Follow-ups (tracked)

1. **Tier-3 identity genesis** — one triage leaf + one `Type:` enum value + one Recommended-Delegations row in
   `agents/skill-genesis.md`, routing to `context-engineer`. Gate: ≥20 ledger rows across ≥2 disciplines with
   the discipline-#2 criterion satisfied **per discipline, not pooled** (revised 2026-07-30,
   `dec-304`: there is no longer a single "threshold" to be under — see
   `docs/multidisciplinary-identities-evidence.md` §17.4). **Deadlock watch:** fewer than five rows after two
   calendar quarters reopens the tier question rather than silently freezing the roster.
2. **Portable distillation reference** for managed projects (generic design rules + round structure + selection
   pattern, zero project-specific numbers) — same gate.
3. **Leave-One-Out audit** of the introspective disposition ratio — same-task runs with and without the
   consultant, sampled rather than per-task. The ledger is the cheap daily instrument; LOO is what keeps it honest.
4. **Ledger promotion to a collector-plus-report shape** if the roster reaches ≥4 disciplines or a rate-over-time
   series is needed that a `grep` cannot produce. Existing rows migrate; nothing restarts.
5. **`performance-engineer`'s escalation relationship** must be written before that discipline ships (the lens is
   the cheap always-fires default; the consultant is the gated escalation).
6. **`agents/implementation-planner.md` at 526 lines** is past sentinel `T03`'s FAIL threshold of 500 with **no
   ledger row**; this feature absorbs its hook at net +0 lines. A ledger writer (verifier or sentinel) should file
   the row — the architect is a consumer and cannot.
7. **Pre-existing drift noted, out of scope:** `rules/README.md` says the model-tier table covers "13 agents"
   (it has 16); `agents/README.md`'s Plugin Registration block omits `agentic-transactions-architect`.
