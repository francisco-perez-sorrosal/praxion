---
id: dec-draft-6a94ce05
title: Per-consult cost series lives in a sibling append-only side-record, not a twelfth ledger column
status: proposed
category: architectural
date: 2026-07-31
summary: td-071 resolved by .ai-state/CONSULT_COSTS.md -- one row per consult (tokens + model + difficulty), single-writer convener, append-only, with a cross-file fitness gate that fails when a post-boundary consult has no cost row.
tags: [consult-ledger, instrumentation, cost, gate-liveness, tech-debt, discipline-consultant, ac15]
made_by: agent
agent_type: systems-architect
branch: worktree-wave2-multidisciplinary
pipeline_tier: standard
affected_files:
  - .ai-state/CONSULT_COSTS.md
  - .ai-state/CONSULT_LEDGER.md
  - fitness/tests/test_discipline_registry_invariants.py
  - skills/software-planning/references/coordination-details.md
  - commands/consult.md
  - agents/CLAUDE.md
  - rules/swe/agent-intermediate-documents.md
  - .ai-state/DESIGN.md
  - docs/multidisciplinary-identities-evidence.md
dissent: A hand-appended series with no automatic capture is a series-shaped artifact rather than a series -- if the convener stops writing rows the file decays into a false record of completeness, which is strictly worse than the honest "unmeasured" label wontfix would have preserved.
re_affirms: dec-299
---

# Per-consult cost series lives in a sibling append-only side-record, not a twelfth ledger column

## Context

`td-071` recorded that nothing accumulates a per-consult cost series. `.ai-state/observations.jsonl` carries no token or cost fields and `.ai-state/CONSULT_LEDGER.md` has 11 columns with no cost column, so AC15's cost envelope — measured in `docs/multidisciplinary-identities-evidence.md` §17.12 — rests on figures that existed only because agent completions surfaced them in one 2026-07-30 session and were hand-transcribed. The ledger row states the consequence: AC15 stays a one-observation measurement forever and the envelope can never be characterised as a distribution. Two `statistician` challenges are formally blocked on it (CH-04 "n=1 bounds no tail, and a ceiling gate is a claim about the tail"; CH-05 "the 3×/6× thresholds are asserted rather than derived"), both dispositioned `defer-with-rationale` citing `td-071` by id.

Three facts constrain the design space, each verified during the research pass ahead of this decision:

1. **Enriching the hook payload is dead on arrival.** No `usage` / `cost` / `token` field exists in the Claude Code hook payload for `Stop`, `SubagentStop` or `PostToolUse` — confirmed against the vendor's Common Input Fields table and corroborated by the fact that this repo's four `observations.jsonl` writers read exactly the documented field set and no more. The code is not discarding a field; the field is not sent.
2. **A ragged twelfth ledger column breaks a live gate.** `fitness/tests/test_discipline_registry_invariants.py::check_ledger_row_has_eleven_columns` asserts exact equality against an 11-tuple, and `test_every_real_ledger_row_has_exactly_eleven_columns` runs it against the shipped file. A twelfth column is a coordinated change across the schema line, the § Column Definitions block, the fitness tuple and its canary — not a free append.
3. **The convener already sees the number, at exactly the moment it writes the ledger row.** Every subagent completion surfaces a usage block to the orchestrating session. §17.12's figures came from there. The quantity is visible and then discarded; what is missing is a durable home, not a capture mechanism.

## Decision

Record the series in a **sibling append-only side-record, `.ai-state/CONSULT_COSTS.md`** — one row per consult spawn, eight columns `timestamp | task-slug | discipline | stage | tokens | model | difficulty | notes`, written by the **convener only**, at the **same Round-2 seam** at which it appends that consult's `CONSULT_LEDGER.md` rows. The ledger's documented 11-column contract, its single-writer rule and its append-only rule are untouched; the new file inherits the latter two verbatim.

Three sub-decisions carry most of the weight:

**The grain, not the file location, is the primary reason.** The ledger is one row per dispositioned *challenge*; cost is a property of the *consult*. A cost column would repeat one value across all six rows of a six-challenge consult — precisely the clustering the ledger's own § Falsifier already had to teach readers around ("challenges raised within one consult share a consultant, a draft, and a convener, so they are a cluster rather than independent observations"). Putting a numeric aggregate at the clustered grain invites the summation error that file spends a paragraph preventing.

**The field set records raw observations, not derivations.** `tokens` + `model` rather than `cost_usd`: a dollar figure is a point-in-time claim that decays with every price change, and writing one would force the convener to apply a price table — injecting a derivation into a file of observations. `model` is load-bearing rather than decorative: `dec-306`'s entire correction was that raw tokens are a biased proxy because §17.12's numerator was all-`opus` while its denominator was mixed, so tokens without a tier reproduce the defect `dec-306` just fixed. `difficulty` is included because AC15 carries a *different envelope per class* (≤3× routine, ≤6× high-stakes) and an observation with no class cannot be assigned to an envelope. `duration_ms`, `tool_uses` and a challenge count are excluded — the first two serve no live claim, the third is derivable from the file being joined against.

**The gate is what makes a manual write acceptable.** Because two files are written by one party at one moment, a deterministic cross-file check is possible: every consult in `CONSULT_LEDGER.md` timestamped at or after a documented series boundary must have at least one `CONSULT_COSTS.md` row carrying its `(task-slug, discipline, stage)` triple, with a positive-integer `tokens` cell and `model`/`difficulty` agreeing with the ledger. The boundary (`2026-07-31T01:00:00Z`, the first round hour after the last pre-adoption ledger row) exempts the four existing consults, three of whose figures are unrecoverable — without it the gate would be red on arrival and would be skip-listed, which `rules/swe/gate-liveness.md` treats as equivalent to no gate.

## Considered Options

### A — a twelfth column on `CONSULT_LEDGER.md`

Rejected on grain first (above) and on coordination cost second: it breaks `check_ledger_row_has_eleven_columns` and forces four synchronized edits. It would *not* break `scripts/finalize_adrs.py` (text substitution, column-agnostic) nor the documented column-anchored grep recipes — so the objection is genuinely about grain, not about fragility.

### B — sibling per-consult side-record (**chosen**)

Grain matches the quantity. Zero churn on the 11-column contract and its gate. Costs one new `.ai-state/` artifact and one producer clause in the three places a convener reads.

### C — wire Claude Code's OpenTelemetry export

The `claude_code.api_request` event genuinely carries `cost_usd`, `input_tokens`, `output_tokens` and `model`, correlatable by `prompt.id` — which also appears on hook payloads as `prompt_id`. Rejected now for three reasons.

It is not one env var: `CLAUDE_CODE_ENABLE_TELEMETRY=1` yields an unattributed firehose, and turning it into *"cost of the `statistician` consult on task X at stage `architecture`"* needs a `prompt.id` → consult join key that **nothing currently produces** — the same manual act this decision already asks of the convener, plus a collector, retention and an aggregation script on top.

Praxion's Phoenix is the wrong shape and the wrong reliability class: `.ai-state/DESIGN.md` wires it as an OTLP **traces** sink fed by the Chronograph MCP server, while `claude_code.api_request` rides the logs/metrics exporters; and `.ai-state/SYSTEM_DEPLOYMENT.md` classes it *"Non-critical (external, optional) … pipeline degrades gracefully without it."* A measurement series whose characteristic defect is *silent non-accumulation* must not have an optional, degrade-gracefully component as its producer — that hides `td-071` behind a service boundary instead of fixing it.

And it is Praxion-local infrastructure; each managed project would need its own collector.

Forward compatibility is preserved deliberately: `tokens` + `model` is a subset of the OTel attribute set, so an OTel-backed producer can later write this schema, or a superset of it, without re-deriving it.

### D — `wontfix`: close `td-071`, downgrade the AC15 claim permanently

Argued in full under Disconfirmation. Rejected because the coverage gate makes the manual step's omission CI-visible within one consult, which answers the only strong objection to B.

## Consequences

**Positive.** Per-consult cost becomes recoverable after the fact, and the series is priceable from one file with `grep | cut | awk`. `td-071` resolves. CH-04's stated blocker — *"no cost series accumulates, so n cannot grow"* — is dissolved for the numerator; both CH-04 and CH-05 become revisitable rather than permanently blocked. The ledger's 11-column contract, its fitness gate and every documented falsifier recipe are unchanged. No onboarding change, no service, no env var: the file is lazily created by the convener on first use exactly as `CONSULT_LEDGER.md` is. Always-loaded cost is one filename line (+18 chars).

**Negative, and stated rather than papered over.**

*The series is the numerator only.* AC15 is a ratio, and its denominator — non-consult pipeline agent cost — is not knowable at the Round-2 seam, because the verifier, sentinel and skill-genesis spawns that dominate §17.12's denominator have not happened yet. Even a rich consult-cost series therefore cannot regenerate §17.12's ratio as a distribution. This is tracked as a new tech-debt row rather than bundled here; a per-spawn series is a materially larger design with no single natural writer.

*The gate catches omission, not falsehood.* A convener could write a plausible fabricated token count and the gate would pass. This residual is identical in kind to the one the ledger already carries on `claim` and `rationale-ref`, and inherent to any hand-recorded observation.

*Managed projects have no gate.* `fitness/` is Praxion's own tier and does not ship with the plugin, so elsewhere the recording is instruction-only. Accepted because AC15 is Praxion's criterion about Praxion's feature. If a managed project's series is ever cited as evidence, the gate must be ported to a shipped `scripts/check_consult_cost_coverage.py` with its own canary.

*Two categoricals are denormalized.* `model` and `difficulty` also live in the ledger. Deliberate: a cost series that needs a second-file join to be priced has a hidden dependency, which is the class of decay `td-071` is about. The duplication risk is converted into an assertion — the gate checks the copies agree.

## Disconfirmation

**Falsifier.** The decision is wrong if, six months on, `.ai-state/CONSULT_COSTS.md` holds few enough rows that the series still cannot characterise a distribution — while the coverage gate is green. That combination is the specific, observable signature of the failure: green means every consult that *ran* was recorded, so a thin file with a green gate says the consult rate is the binding constraint, not the instrumentation, and this artifact bought nothing. It is also falsified, differently, if the gate ever goes red at merge and is resolved by adding the file to a skip list rather than by writing the missing row — a skip-listed gate is the dead-gate failure this design's series boundary exists to prevent.

**Steelmanned runner-up — option D, `wontfix`.** The strongest case against building anything is not that the series is worthless; it is that a *manual* series is a series-shaped artifact rather than a series, and that a decayed series is worse than an honest gap. §17.12 currently carries an unusually clean self-report: *"Nothing is accumulating this series… Today's figures exist only because agent completions surfaced them in-session."* That sentence is accurate, and its accuracy is what makes AC15's `n=1` limit legible to every future reader. Replace it with *"a series accumulates in `.ai-state/CONSULT_COSTS.md`"* and the claim's epistemic status now depends on a human remembering a step at the end of every consult — while the prose reads as though it depends on instrumentation. That is a strictly worse failure mode than the current one, because it fails *silently and flatteringly* rather than loudly and honestly. The runner-up also has the better simplicity argument: the consult rate is low (four consults, ever), so even a perfectly-maintained series would take a long time to bound a tail, and CH-05's derivation is blocked on a loss function that no amount of data supplies. Closing `td-071` as `wontfix` with a tombstone, and leaving §17.12's honest limit in place, costs one ledger row and zero maintenance.

The counter that decides it: the coverage gate converts the decay mode from *invisible* to *a red CI test naming the missing triple, within one consult*. The steelman's core premise — that nobody will notice when the convener stops writing — is the premise the gate falsifies. What the steelman gets right and this decision concedes is the second half: the file must never be read as more instrumented than it is, which is why the scope limit is written into the file itself, into §17.12's replacement text, and into a dedicated debt row.

**Reversal trigger.** Revisit when any of these fires: (i) the gate goes red and the proposed remedy is a skip-list entry rather than a missing row; (ii) a currency-denominated or cache-aware cost figure is needed, at which point option C's OTel path becomes the upgrade and this schema is its forward-compatible subset; (iii) AC15's *denominator* gains a per-spawn series, at which point the two should be reconciled into one instrument rather than left as siblings; (iv) a managed project's consult-cost series is cited as evidence, which requires porting the gate out of `fitness/`.

## Prior Decision

Re-affirms `dec-299` (*Disposition counter is a dedicated append-only `.ai-state/CONSULT_LEDGER.md`, single writer = the convener, shipped as a prerequisite*), without superseding it. `dec-299` rejected extending the tech-debt ledger, rejected a metrics-report triple as over-built, and rejected extra `calibration_log.md` rows because "a third row shape would make the falsifier need a parser" — and it chose a dedicated single-writer append-only file for exactly the reason repeated here. This decision applies the same reasoning one level down: a per-consult quantity gets its own dedicated single-writer append-only file rather than being folded into a per-challenge one, and its reading recipe stays `grep`-and-`cut`. `dec-299`'s ledger schema, its single-writer rule and its 11 columns are unchanged; nothing about it is re-opened. A future supersession would need evidence that the two grains should in fact share a file — most plausibly, the ledger moving to a per-consult grain, which would make a cost column natural rather than clustered.
