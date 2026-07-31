# Verification Report — Multidisciplinary Identities, Waves 1–2 + td-081

**Verdict: FAIL** — 8 FAIL, 19 WARN.

**Merge-blocker set, stated once:** FAIL-1, FAIL-3, FAIL-4, FAIL-5, FAIL-7 — all five are now fixed
(commits `516669e`, `d3b2a1e`). Merge is recommended, because **merging also repairs a defect that is
live on `main` today** (FAIL-2).

**The FAIL/WARN criterion, stated because an earlier draft applied it without one.** *FAIL* = the
mechanism does not do what an artifact claims it does, and the claim is load-bearing for a decision
someone would make from it. *WARN* = a real defect whose correction changes no decision now. This rule
is applied retroactively in this revision; under it, W17 (a shipped doc publishing a ratio its own data
contradicts) is the same class as FAIL-7 and would have been a FAIL had its ratio been decision-bearing
— it is not, because the ratio is withdrawn entirely rather than corrected.

**Vantage.** Every command ran in the worktree
`/Users/fperez/dev/praxion/.claude/worktrees/td-081-sealed-prior`, branch `worktree-td-081-sealed-prior`,
base `1573c44` (= `main` = `origin/main` = `v0.19.0`). `.ai-state/` is worktree-scoped; where a claim
concerns the canonical checkout, a git tag, or the plugin cache, the report says so.

**Method.** Phase 0 orientation and gate inventory built by the orchestrator from ground truth. Phase 1:
six lens-independent `verifier` spawns (D1–D6, `opus`) plus `architect-validator` and `sentinel`, none
permitted to read a sibling's fragment. Phase 2 synthesis. Phase 3: a `statistician`
`discipline-consultant` convened against **this report**, under the sealed-prior protocol the report
itself verifies — seven priors sealed at `37df0f3` before the spawn, nine challenges returned, **all nine
dispositioned `switch-now`**. This revision is the result; §8 records what the consult changed.

**Scope of the re-derivation claim.** Every number in §2–§5 was re-derived by the orchestrator before
adoption. **The summary counts were not**, and in the first draft they were wrong (15 WARN against a
table of 19; three merge blockers in the header against five in the plan). That is corrected here and the
claim is now scoped rather than universal.

---

## 1. What lens independence did and did not buy

Two corrections that would not exist under a cross-reading design, and one that would:

| # | A lens said | Ground truth | Informative? |
|---|---|---|---|
| 1 | D3: no `0.19.0` in the plugin cache ⇒ *"discipline #2 is still unreleased ⇒ Wave-2 deferrals must stay closed"* | The **`v0.19.0` tag ships it** (5 `evidence-appraisal` files, both registry rows). Only this **workstation's install** is stale | **Yes** — a cache listing is evidence about an install, not a release; a roster-policy conclusion cannot rest on it |
| 2 | D3: *"the mechanism ships but its integrity gates do not"* | The gates **do** ship; they resolve `project_root` to the **plugin's own tree** | **Yes** — the corrected finding is strictly stronger |
| 3 | D4: **2** ADRs fail `yaml.safe_load` | **15** | **No, as originally presented** — see below |

**Correction adopted from the consult (CH-08).** The first draft headed this section *"what independence
bought"* and offered the third row as three independent derivations converging. It is not.
`yaml.safe_load` is deterministic; running it three times is **one derivation with three witnesses**, and
agreement among deterministic re-runs carries no information about whether the operationalization matches
the real consumers. The only potentially informative datum in that set was D4's discrepant **2**, because
a different result from the same deterministic operation implies a different *rule* — and that rule was
never identified. It was discarded in a parenthetical and the majority adopted. What actually settles the
number is that the 15 is correct on its own terms, not that three parties said it.

**Consequence, also adopted.** Four D4 outputs previously listed in §4 as verified PASSes — *ADR
reciprocity 13/13; `## Disconfirmation` non-vacuous 13/13; `dissent:` fields real objections 13/13;
`DECISIONS_INDEX` 309/309* — came from the arm whose sole mechanical output was wrong by 7.5×, and three
of the four are LLM judgments. They are **moved to §6 as unverified pending re-derivation**.

**The methodological catch that did hold.** The neutering recipe the orchestrator supplied D1 silently
no-ops: `fitness/` has no `__init__.py`, so pytest imports the module as
`tests.test_discipline_registry_invariants` while a naive `import fitness.tests.…` creates a *second*
module object under PEP-420. D1 detected this **via the sanity control the prompt mandated**. Reproduced:

```
NEUTER_FN=check_registry_row_shape ... -p neuter_plugin
# [neuter] check_registry_row_shape patched_in=['tests.test_…', 'fitness.tests.test_…']
# 2 failed, 98 passed
```

Without the control, D1 would have reported **zero reds for all 17 checks** and concluded the entire gate
set was uncanaried. **But read as data, that is a detection rate of 1/1 among lenses that were
controlled, and D2–D6 had no comparable control** (CH-06) — see §6.

---

## 2. FAIL findings

### FAIL-1 — `G6` failed open on a timezone offset. `[CRITICAL — FIXED]`

`_TIMESTAMP_RE` was applied **only to ledger rows**, and G6's scope comparison is lexical. Same instant,
two representations, against a witness sealed at `05:25:00Z`:

```
inject P-02 at 2026-07-31T05:00:00Z       -> "present in the working file but not sealed: ['P-02']"   CAUGHT
inject P-02 at 2026-07-31T07:00:00+02:00  -> None                                                      ACCEPTED
```

`07:00+02:00` **is** `05:00Z`. The cheat `dec-draft-2c51b2f6` §Q2 names — a convener appending a
fabricated prior after reading the challenges — evaded the check entirely.

`55ae665` did not fix this class; it **moved** it, from *git-date vs row-timestamp* to *row-timestamp vs
row-timestamp*, because its canaries supplied both sides in one representation.

**Fixed** (`516669e`): G2 rejects non-canonical prior timestamps; G6 fails closed and validates both
sides (G2 never sees the witness commit's copy); two canaries added, each supplying two representations.
Neutering either check now reddens 5 tests, up from 4.

### FAIL-2 — On `main` today, the consult gates never run in CI at all. `[CRITICAL — merging repairs it]`

```
git show 1573c44:.github/workflows/architecture.yml | grep -c CONSULT   # 0
```

`architecture.yml` is CI's only path to `pytest fitness/tests/`; `pyproject.toml:79` sets
`testpaths = ["tests","scripts"]`, so `test.yml`'s bare `pytest` collects 1926 tests and **zero** from
`fitness/`. On the released state a `CONSULT_*.md` edit triggers the workflow that cannot see the gates
and not the one that can — while `coordination-details.md`, which **ships to every managed project**,
promises twice that *"omitting it fails `test_discipline_registry_invariants.py`."*

### FAIL-3 — `G5`/`G6`'s real-file arms could not run in CI. `[HIGH — FIXED]`

The `fitness-functions` job had no `with:` block, so `fetch-depth` defaulted to `1`; the seal-witness
commit was unreachable and the test skipped. `G5` additionally needs the `.ai-work/` fragment, which is
gitignored and never present in CI. `dec-draft-2c51b2f6` claims the cheat is caught *"by a test the
convener runs at Round 2 **and by CI thereafter**"* — the second half was false.
**Fixed** (`516669e`): `fetch-depth: 0`. G5 remains inherently local-window-only; the ADR must say so.

### FAIL-4 — 15 ADRs failed `yaml.safe_load`; 14 rendered a raw filename as their title. `[HIGH — 2 of 15 FIXED]`

`scripts/build_doc_manifest.py:132` does `except yaml.YAMLError: fm = {}` — silently. The pre-registered
belief was that the malformed `dissent:` is *"harmless because the ADR tooling parses by regex"*: true of
that tooling, irrelevant to the actual consumer. Damage was already committed to `doc_manifest.yaml`.
**Fixed** (`d3b2a1e`) for `dec-306`/`dec-309` by rephrasing rather than quoting, so every regex consumer
is untouched; 13 pre-existing → ledger.

### FAIL-5 — Two live dangling draft ids, and merging would have created a third. `[HIGH — FIXED]`

`tests/…:10` cited `dec-draft-5fbed7fd` (→ `dec-307`); `fitness/…:1158` cited `dec-draft-6a94ce05`
(→ `dec-308`); neither resolved.

**The obvious repair was wrong.** The first draft proposed widening `finalize_adrs.py`'s allowlist a
fifth time. That script carries an explicit NOTE deliberately excluding code, because
`rules/swe/id-citation-discipline.md` forbids `dec-draft-<hash>` in code outright. And a blanket detector
pattern would flag **21 legitimate files** (parsers that must contain the literal; synthetic fixtures).
**Fixed** (`d3b2a1e`) by correcting the citations. The real gap — the id-citation detector has no
`dec-draft-` pattern despite its own rule table listing it as never-allowed — is a ledger row, because a
sound detector needs design.

### FAIL-6 — The documented `dedup_key` formula reproduces 43 of 84 rows. `[MEDIUM — conclusion withdrawn]`

```
rows=84  reproduce=43  fail=41  (51.2% conforming)
```

**The first draft concluded "so the data is wrong, not the doc." That conclusion is withdrawn** (CH-09).
"Best of 56 variants" is a selection, not a result, and *"39 rows match none"* licenses only that the true
generator lies **outside the searched family**. The settling test — stratify the 41 on covariates the
ledger already carries — was run:

| stratum | conformance |
|---|---|
| first-seen 2026-04 | 100% (11 rows) |
| 2026-05 / 06 / 07 | 43.8% / 0% / 47.4% |
| orchestrator / verifier | 42.5% / 42.3% |
| sentinel / discipline-consultant / systems-architect | 80% / 80% / 100% |

That is broad scatter across producers and months, not concentration in a contiguous era — which by the
challenge's own decision rule supports **derivation unidentified**, not *data wrong*. Remediation
changes accordingly: do not rely on the documented formula for post-merge dedupe until the true generator
is identified. → ledger.

### FAIL-7 — The dossier asserted the opposite of what the cost series records. `[MEDIUM — FIXED]`

`docs/multidisciplinary-identities-evidence.md` read *"Nothing is accumulating this series"* while
`CONSULT_COSTS.md` held 3 rows, and contained **zero** occurrences of `CONSULT_COSTS`. `dec-308` claimed
§17.12 received replacement text; it did not, and `dec-308`'s own steelman quotes the false sentence.
This is `gate-liveness` clause 6 failing **in the wave that authored clause 6**. **Fixed** (`d3b2a1e`),
and `CONSULT_COSTS.md` gained the `## Named consumer` section it lacked.

### FAIL-8 — The feature is extensible for Praxion, not for its users. `[MEDIUM — design-level]`

- `fitness/tests/conftest.py:11` resolves `project_root` three levels up from the conftest — from the
  plugin cache, **the plugin's own root**. A managed project running the shipped suite would audit
  *Praxion's* files and report green about files it does not own.
- Nothing a managed project receives invokes that suite: `git grep -c CONSULT` over
  `onboard-project.md`, `new-project.md`, `new_project.sh`, `canonical-blocks/` → **zero**.
- `dec-305` (project-local registry overlay) is `accepted` with **zero** implementation.
- The marketplace manifest advertises `"version": "0.16.0"` against `plugin.json`'s `0.19.0`.

**A managed project cannot perform step one of "add a discipline."** Consequence is moderate now and
severe the moment `dec-305` lands — ship the overlay and a correctly-rooted templated gate together.

---

## 3. WARN findings (19)

| # | Finding | Disposition |
|---|---|---|
| W1 | **`AC-03` clause 2 is contestable in principle but was never contested by an uninstructed reader.** D5 disagreed with `CH-05`→`P-06`; so did the orchestrator — but the D5 brief said *"if you would have classified any differently, **that is a finding**"*, which raises P(disagreement) independently of correctness, and the orchestrator's agreement came **after** reading D5's verdict, so the two are anchored, not independent (CH-03). Recorded as **untested**, not PASS-demonstrated. | report + ledger (blind-classification test) |
| W2 | **The bias direction is the one the threat model did not anticipate.** Over-matching pushes the rate *down* — the convener flattering its own lens pass. Every stated defense constrains *when* priors are written; **none constrains how generously they are matched.** Sealed prior `P-03`, never matched by any challenge, predicted exactly this. | dossier + ledger |
| W3 | CI `paths:` omitted the five surfaces 5 of the 17 checks police. | **fixed** `516669e` |
| W4 | `CH-05`'s `rationale-ref` cited an ADR that never mentions `CH-05`; `td-084` existed. | **fixed** `d3b2a1e` |
| W5 | Classification `timestamp` documented to match the ledger's; live data 06:40 vs 06:10; no check reads the cell. | ledger |
| W6 | `td-071`/`td-072` still `open` while `dec-307`/`dec-308` record them resolved. | **fixed** `d3b2a1e` |
| W7 | Both architecture docs frozen at Wave-1 and **asymmetrically** — `evidence-appraiser` = 0 in each; neither is a superset of the other. | ledger |
| W8 | The DSL models `challenge_loop` (9 refs) but has no `discipline-consultant` element. | ledger |
| W9 | All four `aac:generated` fences claim `last-regen=2026-05-14`; last `.c4` commit is 2026-07-29. | ledger |
| W10 | **Five gates assert inline with no `check_*` function** — invisible to enumeration and to neutering; four have never been observed to fail. | ledger (extends `td-083`) |
| W11 | `_has_canary()` is file-level: 17 gates in one file, one canary satisfies it. | `td-083`, filed |
| W12 | GL02's documented golden bad-case returns 0 findings from its own detector. | ledger |
| W13 | GL02's exclusion is an absolute-path substring test — 1→0 findings on identical bytes. | ledger |
| W14 | Loop-scoped `pytest.skip` collapses the whole test; one skippable triple silences the rest. | ledger |
| W15 | **The zero-dismissal streak is 38 challenges / 6 consults, not 14 / 2 — and the correction runs *against* the reassuring reading** (CH-07). `P(0 dismissals \| true per-consult rate 0.3)` falls from **0.49** at n=2 to **0.12** at n=6. Bracket: **[0, 0.39]** clustered (`dec-304`'s mandated unit) / [0, 0.09] independent; the truth lies between, and the gap shows how much the unit choice is doing. `dec-304` condition (a) is an *existence* condition with no pre-registered `n` — an open-ended stopping rule on the initiative's own standing condition. | dossier + ledger |
| W16 | `CONSULT_PRIORS.md`'s "one concern" rule requires a `source: lens` row to name its `challenge-obligations` clause; **no gate enforces it**, and the eight pre-rule rows name none. `CH-07` is **not** discharged. | ledger |
| W17 | **The `AC15` cost ratio is withdrawn, not corrected** (CH-05). The first draft published 1.344×, computed over the very denominator the same sentence calls 48% invalid. `CONSULT_COSTS.md` says the denominator *"is not knowable at this writing seam and has no series."* A ratio whose denominator has no series is not a measurement at any value. | ledger — "not evaluable", per `td-076` |
| W18 | `CONSULT_COSTS.md` had no `## Named consumer` section. | **fixed** `d3b2a1e` |
| W19 | `CLAUDE.md` claims `tmp/` is gitignored; it is not. | ledger |

## 4. What PASSED — verified, with the population stated

- **The seal protocol works.** `cd128039e2…` is a commit of `CONSULT_PRIORS.md` **alone**, +8/−0; its tree
  holds exactly the 8 rows; the consultant's `**Round-0 HEAD:**` matches byte-for-byte; the seal precedes
  all three disposition commits. **Independently re-demonstrated in Phase 3**: this verification's own
  seal `37df0f3` was reproduced verbatim by a second consultant.
- **`AC-02`'s live red reproduced from git**: `112b5ba: G4 failures = 7 (RED)` → `c6a6f3a: 0 (GREEN)`.
- **All 17 `check_*` functions bite** — 33 reddened tests, zero uncanaried **over the population
  `check_*` functions**. That is *not* the population `gates`: W10 adds five inline assertions, four of
  which **have never been observed to fail** (CH-04). And the per-check distribution matters more than
  the sum — min 1, median 1, max 5 — because `G6` had four reddened tests, tied for the most of any
  `td-081` check, and FAIL-1 shows it **failed open anyway**. Canary count is not canary adequacy.
- **Baseline** `pytest tests/ scripts/ fitness/ -q` → **2026 passed, 0 failed**, 115.12s.
- **`td-079`'s stray-row fix is real and complete** across all three consult files.
- **The published novelty recipes run and are correct**; the pooled form is commented out and labelled.
- **`dec-307`'s frontmatter strip genuinely shipped** (`0.18.0` had `permissionMode`; `v0.19.0` has none).
- **Always-loaded budget** = 84,926 bytes ≈ 23,590 tokens against 25,000.
- **ff-only merge is clean.**

## 5. The estimand — recorded, not interpreted

One sealed consult, seven challenges. The classification rule **does not identify a single value**
(CH-02). All readings D5 derived, with Wilson 95% intervals:

| reading | value | Wilson 95% |
|---|---|---|
| convener's, as recorded | 4/7 = 0.571 | [0.25, 0.84] |
| splitting `CH-03` | 5/8 = 0.625 | — |
| D5's + orchestrator's reading of `CH-05` | 5/7 = 0.714 | [0.36, 0.92] |
| strict clause-anchor rule | 6/7 = 0.857 | [0.49, 0.97] |

**Rule ambiguity alone spans 0.57–0.86; sampling at n=7 adds ±0.3; the union is essentially the unit
interval.** The first draft published two of these joined by an arrow — correction notation, implying a
revision that settled. It did not. **n = 1 licenses no verdict in either direction.** A high rate is not
evidence the consultant is valuable; a low one is not evidence the falsifier fired. The quantity is
**framing + standing jointly**; arm B is named and unbuilt.

**A structural observation that belongs with the number.** `dec-306`'s Falsifier names
**`evidence-appraiser`**. The register holds **only `statistician`** rows, and both `evidence-appraiser`
consults are pre-boundary and exempt by construction. The instrument built to serve that falsifier has
zero rows for the discipline the falsifier names, and cannot acquire one until that discipline is
convened again — which has never happened in any session. This sharpens the draft ADR's own steelmanned
runner-up and belongs in its Consequences.

## 6. What could not be verified, and why

1. **Whether D2–D6 can detect anything.** Only D1 was given a mandatory positive control, and that
   control caught a silent no-op (§1). D2–D6's null results are from instruments whose sensitivity was
   never established (CH-06). Compounding it, **D2 and D6 were seeded with their own answer keys** —
   three named real instances for D2, the worked `G6` instance for D6 — so raw yield cannot be read as
   evidence a dimension was worth running; only a seeded-vs-novel split can, and it was not collected.
   D2 and D6 were also briefed as unbounded searches with no stopping rule.
2. **D4's four `13/13` judgments** — reciprocity, `## Disconfirmation` non-vacuity, `dissent:` substance,
   index consistency. Moved here from §4 (CH-08); three are LLM judgments from the arm whose sole
   mechanical output was wrong by 7.5×.
3. **A live GitHub Actions run.** FAIL-2/FAIL-3 derive from workflow YAML, `testpaths`, and a local
   shallow-clone reproduction. The branch has never been pushed; `td-081`'s gates have run in CI **zero**
   times.
4. **The dashboard render of degraded ADR titles** — no `node_modules` here.
5. **Whether `/plugin update` installs `0.19.0`** — cache read-only by instruction.
6. **Runtime `Skill`-tool binding of `evidence-appraisal`** — blocked on the stale install.
7. **Squash-merge unreachability of the seal witness** — reasoned, not exercised.
8. **`td-084`'s replication.** `G4` forecloses recording it, which is itself the finding — and is the half
   of `CH-05` that makes two readers call that challenge `novel`.
9. **Between-spawn variance, at every level.** n=1 spawn per lens; n=1 consult; n=1 spawn for the Phase-3
   consult itself.

## 7. Disposition plan — all 19 WARNs and 8 FAILs accounted for

- **Fixed in this branch (10):** FAIL-1, FAIL-3, FAIL-4 (2 of 15), FAIL-5, FAIL-7, W3, W4, W6, W18, and
  the `CH-05` `rationale-ref`.
- **Recorded in this report and the dossier (3):** W1, W2, W15 — the inferential findings. These change
  what the ADR's Consequences and the evidence dossier may claim, not what code does.
- **Tech-debt rows (the rest):** FAIL-6 (conclusion withdrawn, remediation changed), FAIL-8 (four rows),
  FAIL-4's 13 pre-existing records, W5, W7–W14, W16, W17, W19, plus the id-citation-detector gap, the
  inter-rater gap behind W1/W2, and the five per-lens detection controls CH-06 asks for.
- **Not discharged:** `CH-07` of the *prior* consult (W16) — its `switch-now` produced prose with no
  compliant instance and no gate.

## 8. What the Phase-3 consult changed

Nine challenges, **all nine `switch-now`, none dismissed**. It changed this report's headline counts,
withdrew two published point-estimates (the novelty-rate arrow and the `AC15` ratio), withdrew one
conclusion outright (FAIL-6's *"the data is wrong"*, after its settling test was run and pointed the
other way), demoted one PASS to untested (`AC-03` clause 2), moved four judgments from verified to
unverified, rescoped the "zero uncanaried" claim to its actual population, and reversed the *direction*
in which the zero-dismissal correction should be read.

**This extends the zero-dismissal streak to 47 challenges across 7 consults** — which is precisely what
`CH-07` is about, and the consult is therefore self-exemplifying. No dismissal was manufactured to break
it; every one of the nine was correct on the merits, and two of them (CH-03, CH-08) landed on sentences
the orchestrator wrote and was most confident in. That is the outcome the mechanism is for, and it is
also the outcome that makes the streak hardest to interpret.
