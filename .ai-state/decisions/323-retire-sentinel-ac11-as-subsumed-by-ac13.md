---
id: dec-323
title: Retire sentinel AC11 as subsumed by AC13
status: accepted
category: behavioral
date: 2026-08-05
summary: 'Retire AC11 (model↔markdown agreement by title) from the sentinel AC dimension. Its designed structural filter never had a substrate, its primary MCP path is unreachable from the sentinel tool grant, and AC13 answers the same question by element id plus a published half AC11 could not see. AC10 and AC12 clauses of the superseded decision are re-affirmed.'
tags: [sentinel, architecture-completeness, aac, gate-liveness, check-retirement, likec4, false-positive]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: direct
dissent: 'AC13 binds element ids and never reads the Component name, so it cannot detect a §3a row whose human-readable name has drifted into inaccuracy — retiring the only check that looked at names trades a noisy signal for a permanent blind spot in the one column a human actually reads.'
supersedes: dec-112
re_affirms: dec-112
affected_files:
  - agents/sentinel.md
  - docs/aac-dac.md
re_affirmed_by:
  - dec-draft-2d56468e
---

## Context

The sentinel's Architecture Completeness dimension carried two checks comparing the LikeC4 model against the design doc. AC11 (introduced as one of a trio with AC10 and AC12) computed an LLM-judged symmetric diff of element **titles** against component names in architecture markdown. AC13, added later with `scripts/check_architecture_projection.py`, reconciles the model against `.ai-state/DESIGN.md` §3a deterministically by element **id**, and additionally reconciles §4's canonical-block rows against the shipped-block registry.

The catalog asserted the two were "deliberately distinct." Three pieces of evidence, gathered at `HEAD`, contradict that in practice:

1. **AC11's structural filter never had a substrate.** Its defining decision specified that model elements should appear in the markdown "when their `metadata.published = true` (or equivalent visibility tag)." The model carries **zero** `metadata` blocks — `grep -c 'metadata' docs/diagrams/architecture/src/architecture.c4` returns 0. The filter was never implementable, so AC11 shipped as an unfiltered diff over every element kind. On the current model that is 56 elements against 31 cited names: **25 reported orphans, all of them external actors, pipeline-document nodes, or agent nodes** — none of which §3a documents by contract. The false-positive rate is 25/25. The original decision anticipated this and accepted it, mitigated by "WARN-default severity (the operator triages)"; triaging 25 non-findings on every run is alert fatigue, not triage.

2. **AC11's primary path is unreachable by construction.** The sentinel's tool grant is `Read, Glob, Grep, Bash, Write` — no MCP tools. AC11's MCP `read-project-summary` path can never execute, so the rule's mandated fallback WARN (`validator-unable-to-query-likec4-mcp`) fires on 100% of runs, permanently.

3. **Title matching is the binding the design doc records rejecting.** `.ai-state/DESIGN.md` §3a's own inline contract states: *"The binding is by element id, not by title, because the two legitimately differ — a row reads 'Agent runtime / Pipeline' where the element reads 'Agent Pipeline'. Title matching would miss real drift and invent false drift on a rename."* AC11's advertised strength — tolerance for naming drift via title comparison — is the approach §3a was deliberately designed away from.

A fourth observation bears on the method rather than the implementation: **a symmetric diff is blind to anything missing from both sides.** The most consequential live model↔doc drift found while grounding this decision — three agent definitions on disk (`cicd-engineer`, `discipline-consultant`, `roadmap-cartographer`) absent from the model entirely, and a §3a row claiming "15 agent definitions on disk" against an actual 17 — is structurally invisible to AC11, because the three are missing from the model *and* the markdown. The check nominally responsible for model↔doc agreement could never have found it.

## Decision

**Retire AC11 from the sentinel's AC dimension.** Remove its table row, substrate trigger, tooling line, and Pass-2 batch clause from `agents/sentinel.md`; remove its bullet from the paired reader-facing list in `docs/aac-dac.md`. Both sites retain a short retirement note stating why, so the check is not re-added from first principles by a future author who rediscovers the gap it appeared to fill.

Do not renumber. AC12 and AC13 keep their ids; the dimension is AC01–AC10, AC12, AC13.

The AC10 and AC12 clauses of the superseded decision are **re-affirmed unchanged**; only its AC11 clause is reversed.

**Recorded alongside, not fixed here: AC12 carries the same latent defect.** AC12 invokes MCP `query-by-metadata` from the same tool-less agent. It is dormant rather than broken only because its substrate is unpopulated — 0 elements carry `metadata.req_ids`, 0 specs carry `architectural_elements:`. The day someone populates the bidirectional convention, AC12 hits the identical wall. `agents/sentinel.md` now says so at the tooling line.

### Why `behavioral` and not `architectural`

The canonical test asks the author to *name the component added, removed, or whose responsibility moved*. Retiring AC11 names none: the sentinel remains, `check_architecture_projection.py` remains, no boundary moves and no published contract changes. A check inside one component is a **feature inside one component**, which the category rule assigns to `behavioral`. The superseded decision that introduced AC10/AC11/AC12 is itself `category: behavioral`, which is the same call made the same way.

The rejected alternative *would* have been `architectural`: granting the sentinel the LikeC4 MCP tool adds an edge between two components.

## Considered Options

### Option A — Grant the MCP tool and add a structural filter

Add the LikeC4 MCP tool to the sentinel's grant and scope AC11's diff to `component`-kind elements. The MCP server ships with the plugin (`npx -y @likec4/mcp`), so this travels to managed projects rather than depending on a host install.

**Pros:** makes AC11 operable; preserves a recorded position; the filter is derivable from element kind without needing `metadata.published`.

**Cons:** rebuilds title matching, which §3a explicitly rejects as both missing real drift and inventing false drift — the repaired check would be *wrong by the design doc's own reasoning*. Adds an `npx`/Node dependency to an agent that currently needs none, so a check that "runs" in a Node-less environment is a new liveness hazard. Leaves two overlapping checks over one substrate, the weaker of which still cannot see the published half. Buys reachability for a method that is dominated.

### Option B — Retire AC11 as subsumed by AC13 (chosen)

**Pros:** removes a permanent WARN and 25 standing false positives without weakening coverage (residual demonstrated empty below); leaves one deterministic check where there were two overlapping ones, the surviving one being strictly stronger on the shared question and broader on the published half; reduces `agents/sentinel.md` by 2 net lines against an over-warn-band file.

**Cons:** reverses a recorded position, which is only legitimate because the position was recorded before the evidence in Context was available. Nothing then checks §3a Component names at all (see Disconfirmation).

### Option C — Leave AC11 in place and document the noise

**Pros:** changes nothing; no risk of removing coverage that turns out non-empty.

**Cons:** an Important finding stands indefinitely, and every future sentinel run spends operator attention on 25 known non-findings. Alert fatigue on a check catalog is corrosive precisely because it teaches readers to skim the dimension where the real findings will also appear.

### The subsumption argument — residual is empty

| AC11 nominally catches | Covered by |
|---|---|
| Model component absent from the design doc | AC13 `element-without-row`, by id — strictly stronger |
| Design-doc component absent from the model | AC13 `unknown-element` + `row-without-element` |
| Non-structural elements (agents, documents, external actors) absent from §3a | Not drift by contract — §3a is structural-only. This class is 25/25 of AC11's current output |
| `docs/architecture.md` names against the model | AC09 (developer guide ⊆ design doc) composed with AC13 (design doc ↔ model), transitively; plus AC06 against the module glob |
| Title-level divergence where the id binding is correct | Explicitly sanctioned by §3a, not drift |
| §4 canonical-block rows against the shipped-block registry | AC11 cannot see this at all; AC13 covers it |

## Consequences

**Positive.** One permanent WARN and 25 recurring false positives removed. The AC dimension's model↔doc question now has exactly one answer-holder, deterministic and id-bound. `agents/sentinel.md` shrinks despite gaining a rationale note. The latent AC12 instance is now documented at its own call site rather than waiting to surprise whoever populates the traceability convention.

**Negative.** No check reads §3a's human-readable `Component` column any more. AC13 validates the `Element` id; AC02 validates internal consistency within §3; neither asks whether the name a human reads is an accurate description. This is a real gap — see Disconfirmation for why it is not a *new* one.

**Neutral.** The retirement notes at both sites cost ~10 lines of prose. That is the deliberate price of not having this re-litigated: the evidence that makes retirement correct (an absent metadata substrate, a tool grant, a rejected binding) is not recoverable by reading the check catalog alone.

## Disconfirmation

Included voluntarily. The schema requires this block only for `category: architectural`, but retiring a check is the exact shape of change where "did this make the score better without the system improving?" must be answerable from the record.

**Falsifier.** A model↔design-doc drift lands that AC13 passes and a title-based symmetric diff would have caught — specifically, a §3a row whose `Element` id is correct while its `Component` name has become wrong, or a modelled component absent from §3a that AC13 fails to report. Either instance falsifies the residual-empty claim in Considered Options and warrants re-opening. The cheapest place to watch for it is the next few AC13 runs against a renamed component.

**Steelmanned runner-up.** Option A is stronger than the noise it currently produces suggests. AC11 is the only check in the catalog that ever compared *names*, and names are the interface a human reads — a §3a row reading "Agent runtime / Pipeline" for an element that has since become a message bus is invisible to every remaining check, and would stay invisible for as long as the id holds. A title diff scoped to structural elements and downgraded to Suggested would surface exactly that, and the MCP dependency is real but ships with the plugin. The reason it still loses: the case is an argument for a *name-accuracy* check, which is a different check with a different comparison, and building it as a repaired AC11 would import the correspondence semantics that generate the false positives. If the gap proves costly, the right response is a new check, not this one restored.

**Reversal trigger.** Someone populates the bidirectional traceability convention, activating AC12 and forcing a Bash-reachable LikeC4 reader into the sentinel anyway. At that point the cost of giving the sentinel model access is already paid, and a filtered, id-bound check over the non-structural element kinds becomes cheap to add. Revisit then — as a new check with its own falsifier, not as AC11 restored.

## Prior Decision

The superseded decision introduced AC10, AC11 and AC12 as a trio of conditional-activation checks extending the AC dimension, and is itself a re-affirmation of the bidirectional-traceability decision that AC12 depends on.

**What changed:** only its AC11 clause. Two facts unavailable when it was written have since become measurable — that no model would carry the `metadata.published` filter its AC11 specified, and that the sentinel's tool grant excludes the MCP path AC11 was built around. A third arrived later still: AC13 shipped a deterministic answer to the same question, bound by id, over a structural filter derived from the model's own shape. Its own record notes it was originally numbered AC11 and renumbered on collision with the check named here — the overlap was visible at authoring time and resolved by renumbering rather than by reconciling the two.

**What did not change:** the AC10 fence-integrity clause and the AC12 traceability-orphan clause stand as written, along with the conditional-activation idiom the trio established and the dependency on the bidirectional convention. Hence both `supersedes` and `re_affirms` point at the same decision, and it keeps its existing status: most of it remains in force.

**What a future re-opening would require:** an instance of the Falsifier above — a real model↔doc drift that AC13 passes and a title diff would have caught.
