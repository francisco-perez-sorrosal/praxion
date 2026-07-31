# Verification Plan — Multidisciplinary Identities, Waves 1–2 + td-081

**Status**: pending execution. **Written**: 2026-07-31, by the session that built `td-081`.
**Delete this file** once `VERIFICATION_REPORT.md` is filed and its findings have durable homes —
it is a plan, not project intelligence, and it lives in `.ai-state/` only because `.ai-work/` is
gitignored and this must survive a merge.

> **Read this whole file before spawning anything.** The Appendix is not background; it is a catalogue
> of defect *shapes* found the hard way, and it is the highest-yield part of the plan.

---

## Why this matters

This is a **critical extensibility feature**. It ships to every Praxion-managed project through the
plugin, and its purpose is to let existing knowledge acquire standing to object to a decision. If it is
subtly broken, it is broken everywhere and silently — which is precisely the failure class the feature
was built to detect. Verify it accordingly.

## Independence — read before anything else

The prior session designed this, dispositioned its own consult, classified its own priors, and fixed the
gate a consult caught. **Every conclusion in its artifacts is a hypothesis, not a finding.** Treat the
`SYSTEMS_PLAN.md`, `DESIGN_INPUTS.md`, the `CONSULT_statistician.md` dispositions, and the ADRs as claims
to test. Where you agree, say so in one line and move on. **Your disagreements are the product.**

---

## Scope — three bodies of work

| # | Body | State | Artifacts |
|---|---|---|---|
| 1 | **Wave 1** | merged, released | `dec-298`–`dec-306`; the `discipline-consultant` agent; the parameterized registry; `CONSULT_LEDGER.md`; the `applied-statistics` and `evidence-appraisal` skills; model/effort routing; the dialogue protocol |
| 2 | **Wave 2** | merged, released **v0.19.0** | `dec-307` (inert plugin frontmatter stripped fleet-wide), `dec-308` (`CONSULT_COSTS.md`), `dec-309` (roster closed, zero disciplines); ledger rows `td-073`–`td-083` |
| 3 | **td-081** | **NOT MERGED** | branch `worktree-td-081-sealed-prior`, 9 commits, tip `3a9eb54`, base `1573c44` (= `main` = `origin/main` = `v0.19.0`); ff-only merge is clean. Adds `.ai-state/CONSULT_PRIORS.md`, 7 new fitness checks (10 → 17), a ninth classification column, draft ADR `dec-draft-2c51b2f6` |

**Orientation reading, in order**: `.ai-work/td-081-sealed-prior/SESSION_HANDOFF.md` (standalone, its
figures were verified not recalled) → `dec-304`, `dec-306`, `dec-309` → `dec-draft-2c51b2f6` →
`.ai-work/td-081-sealed-prior/SYSTEMS_PLAN.md` §Gate Specification and §AC-02.

---

## Phases, with model and effort per phase

| Phase | What | Model | Effort | Notes |
|---|---|---|---|---|
| **0** | Orientation, scope confirmation, gate inventory | session: **Opus 5 (1M)** | **max** (or `xhigh`) | Do not delegate. Build the gate inventory yourself; D1 depends on it being complete |
| **1** | Fan-out D1–D6, lens-independent | `i-am:verifier` × 6, **`opus`** | inherit | Never downgrade the verifier — `agent-model-routing.md` names it a hard quality cliff |
| **1b** | Structural triangle (parallel with 1) | `i-am:architect-validator`, **`opus`** | inherit | `--mode=on-demand`; code ↔ DSL ↔ ADR across `dec-298`–`dec-309` |
| **1c** | Ecosystem audit (parallel with 1) | `i-am:sentinel`, **`sonnet`** | inherit | Its routing row; catches artifact-level drift the dimensions miss |
| **2** | Synthesis + reconciliation | session: **Opus 5 (1M)** | **max** | Only here may lenses be compared. Re-derive any number before adopting it |
| **3** | Adversarial pass on *your own* report | `i-am:discipline-consultant`, **`opus`**, `Discipline: statistician`, difficulty `high-stakes` | inherit | Follow the sealed-prior protocol you are verifying — see Phase 3 below |
| **4** | Fixes for FAILs | `i-am:implementer`, **`sonnet`**; `tier: H` items → **`opus`** | inherit | Tell them: *commit first, report second* |
| **5** | Merge, finalize, release | session: **Opus 5 (1M)** | **high** sufficient | Mechanical but trap-dense; see Phase 5 |

Spawn directive: pass `model:` explicitly on **every** spawn. Omitting it silently falls through to the
session model and defeats the routing policy.

---

## Phase 1 — the six dimensions

Fan out one agent per dimension. **Lens-independence is mandatory**: no agent reads another's fragment
during collection. Reconcile only at Phase 2. Each writes
`.ai-work/<slug>/VERIFICATION_<dimension>.md`.

### D1 — Gate liveness and reachability  *(highest value; start here)*

Enumerate **every** gate the initiative added across all three bodies of work — fitness checks,
`check_*`/`validate_*` scripts, hooks, sentinel checks, CI jobs. For each, answer four questions with
evidence:

- **(a) Does it exist and pass?**
- **(b) Does it BITE?** Prove it by **neutering the check** — stub its body to return the empty/`None`
  success value — and record which tests go red. **Per check, and count.** Do *not* mutate inputs
  instead: a mutation malformed in a second, unrelated dimension gets rejected before reaching the check
  under test, and this project shipped two gates that passed for exactly that reason. **A check whose
  neutering reddens zero tests has no canary** — that is how `td-083` was found.
- **(c) Does it actually RUN in CI on the change class it polices?** `pyproject.toml` sets
  `testpaths = ["tests","scripts"]`, so a bare `pytest` collects **zero** tests from `fitness/`.
  `test.yml` runs bare `pytest` on every PR and cannot see them; `architecture.yml` can, but only on its
  `paths:` filter. `dec-308`'s cost gate had run in CI **exactly once** — on the PR that introduced it.
  Check every other gate for that shape.
- **(d) Does its output have a NAMED CONSUMER?** `gate-liveness.md` clause 6, added this wave. A correct
  advisory gate nobody reads is this initiative's most repeated defect.

### D2 — Documented-versus-actual divergence

Every documented contract checked against the code or data implementing it. Known instances, all real:

- The `dedup_key` formula in `tech-debt-ledger.md` does **not** reproduce the keys on `td-071`/`td-072`,
  and nothing validates the derivation (`td-077`).
- Both consult files told their single writer to append at end-of-file — outside the parsed table, where
  every parser is blind (`td-079`).
- `CONSULT_PRIORS.md`'s own recipes computed the pooled rate its prose forbids (diverging 0.73 vs 0.46).

Hunt the rest: column counts, schemas, resolution orders, single-writer rules, append-only claims, the
registry row schema, every "N columns" assertion, every `grep` recipe published for a human to run.

### D3 — Shipped-versus-repo  *(the extensibility question)*

What does a managed project on `v0.19.0` **actually receive**? Verify against the version-nested plugin
cache (`~/.claude/plugins/cache/bit-agora/i-am/<VERSION>/`), **not** the repo — a committed doc claimed
`evidence-appraiser` "SHIPPED" while the `v0.18.0` tag carried neither the skill nor its registry row
(`td-073`).

Check: registry rows, both skills, agent frontmatter post-`dec-307`, `commands/consult.md`, the three
paired contract sites, onboarding scaffolding. Then **state plainly which parts of the mechanism do not
reach managed projects** — `fitness/` is Praxion-only, so *every* gate in D1 may be Praxion-only.

**Is this feature actually extensible for its users, or only for Praxion?** That question is why this
dimension exists; answer it explicitly rather than by implication.

### D4 — ADR coherence

`dec-298`–`dec-309` plus `dec-draft-2c51b2f6`. Check supersession and re-affirmation reciprocity;
dangling `dec-draft-` ids anywhere; claims a later ADR falsified that an earlier one still asserts;
`## Disconfirmation` present and non-vacuous on every `category: architectural`; `dissent:` fields that
are real objections rather than restatements; reversal triggers that could actually fire.

Known and pre-existing: `dec-306`'s `dissent:` is not strict-YAML-parseable — harmless only because the
ADR tooling parses frontmatter by regex rather than `yaml.safe_load`.

### D5 — Acceptance criteria, re-derived

Do **not** trust recorded PASSes. Re-derive `AC13` (two disciplines concurrently), `AC15` (cost envelope
— note it instruments the **numerator only**, `td-076`), and `td-081`'s `AC-01` (boundary exempts
pre-adoption consults by construction, no skip-list), `AC-02` (seal verifiable; classification
contestable by a stranger; result recorded and **not** interpreted), `AC-03`.

**Run `AC-03` as an actual stranger.** Using only the committed `.ai-state/CONSULT_PRIORS.md` and
`.ai-state/CONSULT_LEDGER.md`, compute the novelty rate and form your own view on each of the three
`matched` classifications (`CH-03`→`P-01`, `CH-04`→`P-02`, `CH-05`→`P-06`). **If you would have
classified any differently, that is a finding about the mechanism**, not a quibble — the whole design
rests on a stranger being able to contest a classification.

### D6 — The canary/reality gap  *(novel dimension; three defects hid here)*

Every defect that escaped a canary in this work shared one shape: **the canary supplied both sides of a
comparison from one source, and reality supplied them from two.**

The worked instance: `G6` compared a git commit date in the committer's **local offset** (`-07:00`)
against row timestamps in **UTC** (`Z`). String-compared, a row seventeen minutes *older* read as newer,
every sealed prior was exempted as a "later re-seal", and the gate reported eight priors as deleted from
a **byte-identical** file. Its canary passed throughout, because it supplied both dates in one
representation.

So: find every comparison in this initiative where one operand comes from **git, the filesystem, a hook,
or an external tool** and the other from a **human-authored file or a test fixture**. For each, ask
whether the fixture can even *express* the mismatch. Report every site where it cannot.

### Optional stretch — only if D1–D6 complete cleanly

Run `td-084`'s replication: two further `statistician` spawns against the same draft at the same HEAD, to
put a first bound on between-spawn variance. **`G4` currently forecloses recording it** (it asserts
`seal-witness` agreement across a triple's rows) — which is itself the finding.

---

## Phase 3 — adversarial pass on your own conclusions

Convene **one** `discipline-consultant` (`Discipline: statistician`, difficulty `high-stakes`, `opus`)
against **your verification report** — not against the initiative.

Follow the sealed-prior protocol you are verifying, which both tests your conclusions and produces the
series' **second sealed observation** (worth considerably more than the first, since `n=1` licenses
nothing):

1. Declare the intent to convene in `PROGRESS.md` **before** loading the skill.
2. Run the `applied-statistics` lens over your own report; write each surfaced concern as a
   `## Sealed Priors` row (`source: lens`).
3. **Commit `.ai-state/CONSULT_PRIORS.md` alone.** That commit is the seal.
4. Spawn. The consultant records `**Round-0 HEAD:**`, which must resolve to your seal commit.
5. Round 2: disposition **all** challenges on the merits and write them down **before** computing any
   rate — the guard `dec-309` established. Append ledger + cost rows, observe the gate red, then classify.

Prohibit the consultant from reading `.ai-state/CONSULT_PRIORS.md` at any round: it is both draft
exposure and the scorecard.

---

## Deliverables

- `.ai-work/<slug>/VERIFICATION_REPORT.md` — PASS/FAIL/WARN per dimension; **every finding carries a
  reproduction command and the decision it changes**.
- `REWORK_MANIFEST.md` if any FAIL.
- A tech-debt row per accepted-but-deferred finding. **`rationale-ref` must never point into
  `.ai-work/`.**
- An explicit statement of **what you could not verify, and why**.

---

## Phase 5 — merge, finalize, release

Proceed only when D1–D6 are PASS/WARN with FAILs fixed or dispositioned.

1. **Full suite from the worktree**: `python3 -m pytest tests/ scripts/ fitness/ -q` — baseline
   **2026 passed, 0 failed**, ~110s, so allow a generous timeout. Plus
   `python3 scripts/sync_canonical_blocks.py --check`.
2. **Merge ff-only** into the canonical checkout:
   `git -C /Users/fperez/dev/praxion merge --ff-only worktree-td-081-sealed-prior`
   The post-merge hook runs `finalize_adrs.py`, promoting `dec-draft-2c51b2f6` to the next `dec-NNN` and
   rewriting cross-references.
3. **Stage the finalize output BY NAME.** The hook stages only the rename; content rewrites stay
   **unstaged**. `git add` each file explicitly — never `-A`. Then commit.
4. **Grep for surviving `dec-draft-2c51b2f6`** across `.ai-state/` and `docs/`. That allowlist has been
   short **three separate times** (`CONSULT_LEDGER.md`, `CONSULT_COSTS.md`, `CONSULT_PRIORS.md`). If one
   dangles: fix the allowlist **and** add a sibling regression test, then re-run.
5. **Confirm the doc manifest regenerated from the CANONICAL checkout**, not a worktree — a worktree
   lives under `.claude/`, which the generator excludes, silently dropping every doc.
6. **Push, then release**: `/i-am:release` (or
   `gh workflow run release.yml --ref main -f increment=auto`). Watch it to green.
7. **Verify the tag ships what it claims.** This is the `td-073` lesson and it is not optional. Confirm
   the new tag's tree contains `.ai-state/CONSULT_PRIORS.md` and the updated fitness checks, and that
   `python3 scripts/check_release_staleness.py` reports **in sync** — run it **after `git pull`**,
   because it resolves the last tag reachable from local HEAD and will otherwise report against the
   previous release.
8. **Update the external marketplace manifest** to the new version. Its `version` field is Claude Code's
   cache key; divergence breaks resolution.
9. **Append a `.ai-state/calibration_log.md` row.**
10. **Delete this file** and remove the merged worktree.

---

## Appendix — the standard, and the traps

### The standard

1. **Verify, don't relay.** Re-derive every number. In the prior session this overturned a subagent's
   decisive negative, two of the orchestrator's own published claims, and the plan's own canary count.
2. **Prove every gate fails** — neuter the check, per check, counting.
3. **Record what you did not do.** `defer` → ledger row; `dismiss` worth remembering → tombstone.
4. **Disposition before computing.** Fix dispositions on the merits and write them down before
   calculating anything they affect.

### Traps — every one of these fired

- **Truncated subagent returns.** Four in the prior session. A return without a terminal marker
  (`[COMPLETE]`/`[BLOCKED]`/`[PARTIAL]`) is a **suspected truncation**: re-derive from git + tests, do
  **not** re-run from scratch. Every time, the work was done and only the report was missing. Instruct
  agents to **commit first, report second**.
- **`.ai-state/` is worktree-scoped.** Three wrong-vantage errors, including a subagent concluding
  `observations.jsonl` had zero consultant records "across all 20,056 lines" while querying a different
  checkout. **Always ask which tree a command ran in.**
- **Never a bare `git stash`** (`td-078` — it destroyed uncommitted orchestrator work). Stage by
  pathspec, never `git add -A`. Leave `.ai-state/observations.jsonl` and `uv.lock` **unstaged**.
- **If a formatter rewrites a file, `git add` its output** — do not re-Edit. `ruff-format` fires on the
  fitness file on most commits.
- **Append rows to their data table, not EOF.** Both consult files carry prose sections after their
  tables; a gate now catches this.
- **`rules/**` edits require `python3 scripts/regenerate_rules_manifest.py`** in the same commit.
- **Always-loaded budget**: 84,926 bytes ≈ 23,590 tokens against a 25,000 ceiling — ~1,410 headroom.
  Prefer skill/reference placement over a new always-loaded rule.
- **Four contract sites move together**: `agents/discipline-consultant.md`, `agents/CLAUDE.md`,
  `skills/software-planning/references/coordination-details.md`, `commands/consult.md`.

### Standing facts worth knowing before you start

- **Zero dismissals across 14 challenges, two consults.** `dec-304` standing condition (a) is unmet.
  Do not manufacture one. Whether that streak means the `fires-when` predicate is well-targeted or the
  convener is agreeable is exactly what this instrument cannot yet distinguish — and is a legitimate
  finding to sharpen.
- **The first observation is one consult, novel 4/7, rate 0.57.** At `n`=1 this licenses no verdict in
  either direction, and `dec-306`'s Falsifier is **instrumented for the post-boundary series, not live**.
- **The measured delta is framing + standing jointly**, never standing alone. Arm B (a generic agent
  holding the same skill) is named and unbuilt; it is what would separate them.
