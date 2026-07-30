---
diataxis: explanation
audience: developer
---

# Multidisciplinary Identities — Evidence Dossier

Permanent evidence base for the initiative that adds role-oriented, multidisciplinary consulting
identities (statistician, performance engineer, reliability engineer, formalist, …) to the Praxion
agent pipeline, so that existing pipeline agents can improve their output through structured
dialogue with domain specialists.

**Status:** evidence base — settled. Design conclusions in [§8](#8-design-space) and
[§9](#9-recommended-architecture-hypothesis) are a **proposed hypothesis** at intake, subject to
supersession by the pipeline that consumes this dossier.

**Why this file exists.** Pipeline research intermediates live in `.ai-work/<task-slug>/`, which is
gitignored and deleted at pipeline cleanup. Any research that must survive has to be promoted to a
committed artifact. This file is that promotion for the intake research; the pipeline's own findings
are promoted through ADR fragments, `.ai-state/DESIGN.md`, and the archived SDD spec.

**Provenance.** Produced 2026-07-29 in an interactive orchestrator session, from (a) primary-source
reading of the paper in [§3](#3-primary-source), (b) adjacent-literature retrieval, and (c) direct
measurement of this repository. Every quantitative claim about Praxion in [§7](#7-praxion-internal-analysis)
was measured, not estimated; the commands are recorded alongside the numbers.

---

## 1. The question

Can Praxion improve the output quality of its existing pipeline agents (researcher,
systems-architect, implementation-planner, implementer, test-engineer, verifier) by introducing
distinct disciplinary identities that these agents consult and argue with, and if so:

1. Should each identity be a new **agent**, a new **skill** attached to existing agents, or something else?
2. Which identities should exist **first**?
3. How is an identity **selected** — by the user, by the orchestrator, or automatically?
4. How does the **dialogue** work, and how does its output re-enter the pipeline?

---

## 2. Executive summary of findings

1. The originating paper endorses the idea but its causal evidence supports **conversational
   structure**, not **expertise labels**. Build for the structure; treat the labels as a cheap rider.
2. The most useful finding in the paper is a **negative** one: reasoning models learn to diverge but
   not to reconcile. Engineered synthesis is the value-add, because models do not supply it.
3. The persona literature is only apparently contradictory. Resolved, it yields four hard design
   rules: personas help *reasoning* not *recall*; value comes from diversity **plus correct
   selection**; identities must be **methodological, never sociodemographic**; and synergy appears
   only at **frontier model tier**.
4. **Automatic identity selection is the single riskiest requirement.** The strongest negative result
   in the literature targets exactly that mechanism. A three-tier selection model
   ([§11](#11-identity-selection-model)) delivers automation without the failure mode.
5. The dominant risk is already catalogued and quantified: ~42% of multi-agent failures are
   specification/design issues, explicitly including *ambiguous role definitions* and *duplicate
   agent roles*. Adding N fuzzy identities to a 16-agent pipeline is that failure mode by construction.
6. Praxion has **four existing precedents** that make this an extension rather than an invention, and
   **two governance constraints** that bound it — one of which is an arithmetic constraint on the
   always-loaded token budget that eliminates the most obvious design option.
7. Three of the four first-wave identities need **no new knowledge at all**. Praxion already owns the
   expertise; what it lacks is a dissenting *voice*. This reframes the initiative from "add six
   domains" to "give existing knowledge standing to object," and drops the cost by roughly 6×.

---

## 3. Primary source

[Reasoning Models Generate Societies of Thought](https://arxiv.org/html/2601.10825v1) — Junsol Kim,
Shiyang Lai, Nino Scherrer, Blaise Agüera y Arcas, James Evans (Google Paradigms of Intelligence;
University of Chicago; Santa Fe Institute). arXiv:2601.10825v1, January 2026.

**Thesis (abstract, verbatim):**

> "Here we show that enhanced reasoning emerges not from extended computation alone, but from the
> implicit simulation of complex, multi-agent-like interactions—a society of thought—which enables
> the deliberate diversification and debate among internal cognitive perspectives characterized by
> distinct personality traits and domain expertise."

The mechanism is a **single model**, not a deployed multi-agent system. Four conversational
behaviours are annotated in reasoning traces: question-answering sequences, perspective shifts,
perspective conflicts, and reconciliation.

### 3.1 Claims separated by evidence strength

Conflating these tiers is the main way to misread the paper into building the wrong system.

| Claim | Evidence type | Scope | Strength |
|---|---|---|---|
| Reasoning models exhibit far more internal perspective and expertise diversity than instruction-tuned peers — question-answering +34.5pp (DeepSeek-R1 vs V3), +45.9pp (QwQ vs Qwen-2.5-32B-IT); perspective shifts +21.3pp / +37.8pp; reconciliation +19.1pp / +34.4pp; expertise cosine-distance +0.179 | Correlational, LLM-as-judge annotation over 8,262 problems (BBH, GPQA, MATH-hard, MMLU-Pro, MUSR, IFEval) | Between model classes | Moderate — judge speaker-attribution accuracy is only 69–82% against the human-debate ground truth, degrading with speaker count |
| Steering a single sparse-autoencoder feature (a "discourse marker for surprise, realization, or acknowledgment", feature 30939, layer 15 of DeepSeek-R1-Llama-8B) **causes** accuracy to move: +10 steering 27.1% → 54.8%; −10 steering → 23.8% | Causal, mechanistic intervention | One feature, one layer, one 8B distill, Countdown arithmetic (1,024 problems) | Strong but narrow |
| Pre-fine-tuning on multi-agent **dialogue** traces accelerates RL convergence vs monologue traces — 38% vs 28% at step 40 (Qwen-2.5-3B); 40% vs 18% at step 150 (Llama-3.2-3B) | Causal, controlled | 3B models, simple tasks | Moderate |
| Personality-trait diversity rises on most Big-Five axes (neuroticism β=+0.567, agreeableness β=+0.297, openness β=+0.110, extraversion β=+0.103) but conscientiousness diversity **falls** | Correlational | Between model classes | Moderate; the conscientiousness result is contrary to the authors' own expectation |

**What the paper does not establish.** It never demonstrates that *hand-assigned domain-expert
labels* improve outcomes. The causal lever is conversational turn-taking structure. The diversity
finding is a comparison between model classes, not an intervention on personas. Any design that
depends on the label carrying the benefit is unsupported by this paper.

### 3.2 The paper is pro-multi-agent (corrects a common misreading of the abstract)

The abstract's emphasis on a single model self-organizing invites the inference that explicit
multi-agent architectures are discouraged. The Discussion states the opposite:

> "A growing trend in AI involves agentic architectures that deploy multiple agents engaged in more
> complex configurations than single-channel debate, including hierarchy, complex networks and even
> entire institutions of interacting agents… Our work suggests the importance of exploring
> alternative structures, but also **inhabiting them with diverse perspectives, personalities, and
> specialized expertise** that drive complementarity and collective success in the human social world."

And on framing:

> "Understanding how diversity and social scaffolding interact could shift how we conceptualize large
> language models, from solitary problem-solving entities toward collective reasoning architectures,
> where intelligence arises not merely from scale but the structured interplay of distinct voices."

> "principles governing effective group collaboration may offer valuable insights for interpreting
> and engineering reasoning behaviours in language models."

### 3.3 The reconciliation deficit — the most actionable finding

From the RL training results:

> "Reconciliation behaviour shows little increase, suggesting that individual approaches **compete
> rather than forming an effective ensemble**."

Models spontaneously learn to *diverge*; they do not learn to *converge*. Divergence is free,
synthesis is not. This identifies precisely where engineered scaffolding adds value that the model
will not supply on its own, and it is the design justification for making reconciliation a
**mandatory, single-owner** step rather than an emergent outcome of debate
([§10](#10-dialogue-protocol)).

A secondary observation in the same results — perspective shifts *decrease* after ~step 160 as the
model reaches answers with fewer shifts — supports treating deliberation as **cost to be gated**,
not a good to be maximized.

### 3.4 Task-difficulty dependence

Conversational behaviour activates preferentially on harder problems (GPQA, hard MATH) and is
minimal on routine classification. Design implication: identity consultation must be **gated by
difficulty/stakes**, never always-on. This aligns with the pre-existing honest-uncertainty gate in
`skills/multi-perspective-analysis/SKILL.md`.

---

## 4. Adjacent literature

| Source | Finding | Design implication |
|---|---|---|
| [When "A Helpful Assistant" Is Not Really Helpful](https://aclanthology.org/2024.findings-emnlp.888/) — Zheng et al., EMNLP Findings 2024 | 162 roles × 2,410 factual questions × 4 LLMs: adding a persona does **not** improve accuracy, sometimes degrades it. **But** aggregating the oracle-best persona per question improves accuracy significantly, while *automatically identifying* it performs **no better than random**. | The value is diversity **plus selection**. Selection must be external and deterministic, not model-guessed. This is the load-bearing constraint on [§11](#11-identity-selection-model). |
| [Better Zero-Shot Reasoning with Role-Play Prompting](https://aclanthology.org/2024.naacl-long.228/) — Kong et al., NAACL 2024 | Role-play prompting substantially lifts zero-shot reasoning: AQuA 53.5% → 63.8%; Last Letter 23.8% → 84.2% (ChatGPT). | Role framing functions as an implicit reasoning trigger. Positive, but on *reasoning*, not recall. |
| [Unleashing the Emergent Cognitive Synergy in LLMs (Solo Performance Prompting)](https://aclanthology.org/2024.naacl-long.15/) — Wang et al., NAACL 2024 | Multi-persona self-collaboration reduces factual hallucination and helps knowledge-intensive and reasoning tasks; **fine-grained multiple personas beat a single or fixed-count persona**; cognitive synergy **emerged only in GPT-4**, absent in GPT-3.5-turbo and Llama2-13B-chat. | Run identities at frontier tier only. Matches Praxion's existing quality-cliff guard ("deep scientific or math reasoning — do not downgrade below Opus"). Also supports a *roster* of specific identities over one generic "expert". |
| [Persona is a Double-edged Sword](https://arxiv.org/html/2408.08631v1) — 2024 | Persona conditioning can degrade reasoning and amplify bias, particularly with sociodemographic attributes; ensembling role-play with neutral prompts mitigates. | Identities must be **methodological** ("apply power analysis before claiming a regression"), never **sociodemographic** ("you are a 45-year-old statistician"). |
| [Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657) — Cemri et al., NeurIPS 2025 Datasets & Benchmarks | 1,600+ annotated traces across 7 frameworks, inter-annotator κ=0.88, 14 failure modes in 3 categories. **~42% specification/system-design** (incl. *ambiguous role definitions*, *duplicate agent roles*, poor decomposition, missing termination conditions), ~37% inter-agent misalignment, ~21% task verification. | The dominant risk of this initiative, quantified. Mandates sharp non-overlapping role boundaries, explicit termination conditions, and a verification step on identity output. |
| [MetaGPT](https://arxiv.org/pdf/2308.00352) / ChatDev | SOP-encoded role companies work, but sequential chat creates bottlenecks and costs frequently exceed $10/task; authors note LLMs "lack the nuanced expertise required in software engineering, which hampers their ability to simulate other SE-specific roles." | Bound the dialogue rounds. Do not assume an identity label confers real expertise — bind it to a knowledge artifact. |
| [SPOQ: Specialist Orchestrated Queuing](https://arxiv.org/abs/2606.03115) — Carbowitz & Kumar, June 2026 | Wave-based topological dispatch (critical-path ratio 1.03–1.11, up to 14.3× speedup), dual validation gates (defects 0.34 → 0.20/task; test pass 91.25% → 99.75%), three-tier model hierarchy, human-as-an-agent (residual defects 0.47 → 0.03/task). | **Near-miss on this thesis.** Its "specialists" are *model tiers*, not disciplines. All four mechanisms already have Praxion analogues (parallel execution; pre-mortem + verifier; agent-model-routing; conversation checkpoints). Evidence for Praxion's existing machinery, not for domain identities. |
| [Rigorous Benchmarking in Reasonable Time](https://dl.acm.org/doi/10.1145/2491894.2464160) — Kalibera & Jones, ISMM 2013 | Systems performance evaluation routinely lacks statistical rigor; provides a cookbook for repetition levels, variance estimation, and confidence intervals. | Grounding text for the `statistician` identity. |

### 4.1 The persona paradox, resolved

Zheng (personas do not help) and Kong (role-play helps a lot) appear to contradict. They do not once
two axes are separated:

- **Task type.** Role-play acts as a reasoning scaffold. It helps multi-step reasoning; it does
  nothing for factual recall, which is what Zheng measured.
- **Persona content.** Methodological framing supplies a procedure. Sociodemographic framing supplies
  a stereotype, and measurably imports bias.

Both papers are correct within their scope. The synthesis is the four design rules in
[§2](#2-executive-summary-of-findings), item 3.

---

## 5. What the evidence does and does not license

**Licensed.** Structured, gated, bounded deliberation among methodologically-distinct perspectives at
frontier tier, with mandatory single-owner reconciliation and deterministic selection.

**Not licensed.** (a) Expecting a gain from the expertise *label* itself. (b) Free-form model
self-selection over an open-ended identity space. (c) Always-on consultation. (d) Unbounded
multi-round debate. (e) Sociodemographic persona framing. (f) Assuming an identity label confers
expertise absent a bound knowledge artifact.

---

## 6. Open questions the evidence does not answer

Carried forward as the research agenda for the pipeline consuming this dossier:

1. Does *domain* diversity add anything beyond *conversational* structure in an agentic software
   pipeline? No source isolates these.
2. Is one round of challenge the right bound, or does a second round pay for itself?
3. Does a bounded authored trigger table actually beat random selection? Zheng refutes open-ended
   self-selection; nobody has tested bounded routing.
4. What is the measured accept/defer/dismiss distribution for identity challenges? This is the
   initiative's own falsifier and has no external prior.
5. Does the reconciliation-deficit finding transfer from single-model traces to orchestrated
   multi-agent pipelines?

---

## 7. Praxion internal analysis

### 7.1 Existing precedents — this is an extension, not an invention

| Precedent | Location | What it supplies |
|---|---|---|
| **Domain-expert shadow sub-architect** | `agents/interface-designer.md`, `agents/agentic-transactions-architect.md` | A peer-to-architect identity, conditional on scope, that writes `<DOMAIN>_DESIGN.md`, authors ADR fragments, does not write production code, and runs at Opus tier |
| **Orchestrator-mediated challenge loop** | `## Architecture Challenges` section + coordination protocol pipeline rules | A bounded, one-round dialogue channel from a specialist back to the architect — already built and already load-bearing |
| **Lens sweep + lens-independence discipline** | `skills/software-planning/references/design-synthesis.md` (Lens Catalog), `skills/multi-perspective-analysis/` | Five lenses (Security, Performance, Simplicity, Testability, Blast-radius), each pointing at an owning artifact; isolate → reconcile → gate discipline with a documented correlation-collapse rationale |
| **Mode-directive parameterization** | `agents/CLAUDE.md` § Architect Invocation Modes | One agent, three behaviours, selected by a `Mode:` string in the spawn prompt — the precedent for parameterizing an agent instead of cloning it |
| **Disposition vocabulary** | `skills/software-planning/references/disposition-vocabulary.md` | `switch-now` / `defer-with-rationale` / `dismiss-with-rationale`, already shared across the CIS and rework loops, with silent dismissal already a behavioral-contract violation |
| **Proposal-then-disposition harvesting** | `agents/skill-genesis.md` + `/skill-genesis-review` | The pattern for open-ended discovery that surfaces *proposals* for user disposition rather than instantiating silently |

### 7.2 Governance constraints

**Constraint 1 — the lens catalog is closed by policy.** `design-synthesis.md` states: *"No new
lenses. If a future need arises for a lens not in this table, file an ADR supersession rather than
editing this reference to introduce one."* Any identity that behaves as a design lens therefore
requires an **ADR supersession**, not an edit. This is a required deliverable, not a footnote.

**Constraint 2 — the always-loaded token budget is nearly spent.** Measured 2026-07-29 on this
repository:

```
81,687 bytes across: ~/.claude/CLAUDE.md, CLAUDE.md, rules/CLAUDE.md,
  and all rules/**/*.md lacking `paths:` frontmatter
  (adr-conventions, agent-behavioral-contract, agent-intermediate-documents,
   agent-model-routing, swe-agent-coordination-protocol, vcs/git-conventions)
= 22,691 tokens @ 3.6 bytes/token  (20,422 @ 4.0)
Budget: 25,000  →  headroom ≈ 2,309 tokens
```

### 7.3 The marginal-cost measurement that decides the design

Agent `description` fields are always-loaded, because the orchestrator needs them in-context to
delegate. Skill descriptions are likewise loaded at startup under progressive disclosure. Measured
across this repository:

| Surface | Count | Total | Mean each | Notes |
|---|---|---|---|---|
| Agent descriptions | 16 | 11,375 chars ≈ 3,160 tok | 711 chars ≈ **197 tok** | Domain-shadow agents are far above mean: `agentic-transactions-architect` 1,801 chars ≈ **500 tok**; `interface-designer` 1,337 chars ≈ **371 tok** — precise trigger conditions are verbose |
| Skill descriptions | 56 | 28,612 chars ≈ 7,948 tok | 511 chars ≈ **142 tok** | |

The relevant comparison is against the **domain-shadow** agents, not the mean, because a discipline
identity needs comparably precise triggers. Six discipline agents at 371–500 tokens each is
**2,200–3,000 tokens** — consuming 95–130% of the entire remaining headroom.

> [!IMPORTANT]
> This is an arithmetic constraint, not a stylistic preference. "One agent per discipline" is
> eliminated by measurement before any qualitative argument is needed.

### 7.4 Gap analysis — which disciplines are genuinely missing

Verified by grepping the repository for statistical, invariant, and reliability vocabulary across
`skills/`, `rules/`, and `agents/`.

| Discipline | Owning artifact today | Verdict |
|---|---|---|
| Performance | `skills/performance-architecture/` (+ it is already a lens) | Knowledge present. Missing: **standing to object**. |
| Security | `skills/context-security-review/` (+ already a lens) | Knowledge present. |
| Testability | `skills/testing-strategy/`, `skills/test-coverage/` (+ already a lens) | Knowledge present. |
| Reliability / failure modes | `skills/observability/`, `skills/agent-failure-taxonomy/`, `skills/agent-runtime-guardrails/`, `skills/deployment/` | Knowledge present, scattered. Missing: an adversarial reliability voice. |
| Invariants / formal reasoning | `skills/architectural-fitness-functions/` (invariants *as tests*), `skills/testing-strategy/` (property-based mechanics, invariant examples) | Partial. Nobody **derives** the invariant set from a design. |
| **Applied statistics / experiment design** | **None** | **Genuine gap.** Statistical vocabulary appears only as incidental single mentions across 23 files. `performance-architecture/references/benchmarking.md` covers CIs, coefficient of variation, percentiles, and 30+ iterations — solid for microbenchmarks. Absent everywhere: power/sample-size planning *before* collection; inferential statistics for evals (multiple comparisons across N benchmarks, bootstrap CIs on pass@k, judge agreement κ, non-determinism variance); confounding and Simpson's paradox in churn/complexity/coverage trends; **derived** rather than asserted tolerance bands. |
| Queueing / scaling laws | None | Genuine but narrower gap (Little's Law, Universal Scalability Law, Amdahl contention, Fermi estimation). |
| Cost / token economics | `skills/multi-perspective-analysis/references/heterogeneous-orchestration.md` | Partial. |

**The statistics gap lands on a self-identified project weakness.** `ROADMAP.md` W7 reads
*"Measurement blind spots: activity is instrumented, efficacy is not."* The `statistician` identity is
the artifact that closes W7, which makes it the best-grounded first identity independent of the
external literature.

---

## 8. Design space

Three options, evaluated against the three stated requirements (help existing agents; support
dialogue; be automatically selectable) and the measured constraints.

| Option | Dialogue possible? | Always-loaded cost | MAST specification risk |
|---|---|---|---|
| **A. N new agents**, one per discipline, on the shadow-sub-architect template | Yes | ~2,200–3,000 tok — **exceeds headroom** | **High** — N roles with overlapping boundaries is the top failure category |
| **B. N new skills**, injected into existing agents via `skills:` frontmatter | **No** | ~850 tok for 6 | Low |
| **C. One parameterized consultant agent + discipline bindings** | Yes | **~500 tok total** | Low — one sharply-defined role |

**Why B fails, and the failure is conceptual not mechanical.** A skill loaded into the architect's
context *is the architect thinking with better knowledge*. There is no second party, so there is
nothing to disagree. The paper's mechanism requires voices **in tension**; a better-informed
monologue is not a society of thought. B is the cheapest option and it does not meet the requirement.

**Why A fails.** Measurement ([§7.3](#73-the-marginal-cost-measurement-that-decides-the-design)) plus
the MAST specification-risk category.

---

## 9. Recommended architecture (hypothesis)

**Status: proposed.** The consuming pipeline may supersede this.

**One new agent — a discipline-parameterized adversarial consultant.** Selected by a
`Discipline: <name>` directive in the spawn prompt, mirroring the existing `Mode:` precedent. Opus
floor, per both the quality-cliff guard and SPP's frontier-only synergy. Read-only on production
code; writes only its consult artifact and ADR fragments. Shadows the researcher and
systems-architect stages exactly as the two existing sub-architects do.

**The discipline roster lives inside the agent body, not in the always-loaded surface.** This is the
load-bearing move: agent bodies load only when spawned, so adding discipline #7 later costs **zero**
always-loaded tokens.

**Discipline bindings reuse existing skills wherever they exist.** Only genuine knowledge gaps get a
new skill. First wave therefore needs exactly one new skill (applied statistics).

**One new command** — a user-invocable `/consult`-style entry point, so a human can convene an
identity mid-session. Commands cost nothing always-loaded, and this is the human half of the dialogue
requirement.

Marginal always-loaded cost: **~500 tokens (~22% of remaining headroom)**, versus 95–130% for
Option A.

Working name for the agent in this dossier is deliberately left open; naming is a low-stakes
decision for the architecture stage.

---

## 10. Dialogue protocol

Four rounds, bounded. This is where the reconciliation deficit
([§3.3](#33-the-reconciliation-deficit--the-most-actionable-finding)) is engineered away.

| Round | Action | Discipline enforced |
|---|---|---|
| **0 — Isolate** | Consultant reads the *same source materials* as researcher and architect, with **no access to their draft**. Writes its consult fragment. | Lens independence during collection. Sharing the architect's framing here produces correlation collapse — an N× cost for a correlated opinion. |
| **1 — Challenge** | Consultant now reads `SYSTEMS_PLAN.md` / `IMPLEMENTATION_PLAN.md` and populates a challenges section. Each challenge must carry a **falsifiable claim** and **the decision it would change**. | A challenge that changes no decision is dropped. This is the mechanical filter against decorative expertise. |
| **2 — Disposition** | Orchestrator carries challenges back. The architect must respond in the existing vocabulary: `switch-now` / `defer-with-rationale` / `dismiss-with-rationale`. | Silent dismissal is already a behavioral-contract violation, so the obligation to answer is pre-enforced. Deferred challenges already have a tech-debt-ledger path. |
| **3 — Reconcile, then stop** | Bounded at one loop-back, matching the existing challenge loops. Reconciliation is owned by **one party (the architect)**, never negotiated between peers. | Direct answer to "individual approaches compete rather than forming an effective ensemble", and to MAST's inter-agent-misalignment and missing-termination-condition modes. |

Surviving challenges flow into surfaces that already exist: the ADR `## Disconfirmation` body block
and the `dissent:` frontmatter field. A statistician's objection becomes a **recorded falsifier**,
which is exactly what that field is for.

"Isolate, then dialogue" resolves an apparent conflict between two Praxion doctrines:
lens-independence forbids agents seeing each other's work *during collection*, while the dialogue
requirement demands engagement. Both hold if independence governs round 0 and dialogue governs rounds
1–2. Contradictions that survive that sequence mark genuine ambiguity rather than anchoring, and are
the highest-value signal the pipeline can produce.

---

## 11. Identity selection model

Requirement: identities managed by the agents themselves, optionally user-proposed, ideally
auto-identified by orchestrators or specialist agents.

> [!WARNING]
> This requirement collides with the strongest negative result in the literature. Zheng et al. found
> that oracle-best persona selection helps significantly while **automatic identification performs no
> better than random**. Implemented as free-form model self-selection over an open-ended persona
> space, auto-identification is specifically predicted to fail.

Three tiers deliver the automation without the failure mode. None is free-form guessing.

| Tier | Mechanism | Selector | Why it survives the Zheng result |
|---|---|---|---|
| **1 — Trigger table** | Authored signal→discipline predicates evaluated at intake and at phase transitions | Orchestrator, mechanically | Routing over a **bounded** roster with authored predicates, not persona-guessing over an open space. Different mechanism from what Zheng refuted. |
| **2 — Self-nomination** | A specialist agent convenes a consultant, **citing the triggering signal and the decision at stake** | researcher / systems-architect / implementation-planner / verifier | Auditable and falsifiable. A bad nomination surfaces as a dismissed challenge and is countable. |
| **3 — Identity genesis** | Recurring "we needed an X here" signals harvested from `LEARNINGS.md` and consult artifacts; a **new** discipline is *proposed* for user disposition | `skill-genesis` → `/skill-genesis-review` | Open-ended discovery lands as a proposal, never a silent instantiation. Reuses existing machinery. |

User override remains available at every tier through the `/consult`-style command. Tier 1 gives
day-one automation; tier 3 is where "ideally automatically identified" lives safely.

**Instrumentation is mandatory from day one.** The accept/defer/dismiss ratio per discipline is
mechanically countable from the artifacts and is the initiative's own falsifier
([§13](#13-falsifiers)). Shipping the selection tiers without the counter would make the value
question permanently unanswerable — which is itself the W7 failure mode this initiative claims to fix.

---

## 12. Identity roster

Selection criteria, applied strictly: **(a)** fills a gap rather than duplicating an owning artifact;
**(b)** can change a decision the pipeline actually makes; **(c)** produces **falsifiable** claims;
**(d)** recurs often enough to earn attention.

### 12.1 Wave 1 — four identities, one new skill

| # | Identity | Attaches to | Fires when | Knowledge binding |
|---|---|---|---|---|
| 1 | **statistician** — experiment design and inference | researcher; architect (acceptance thresholds); test-engineer; verifier (is the evidence sufficient?); metrics and eval commands | A numeric claim, threshold, tolerance band, benchmark comparison, eval result, or metric trend is about to become load-bearing | **NEW skill** — applied statistics |
| 2 | **performance-engineer** | architect; implementer | Latency, throughput, or scale is a stated requirement, or a hot path changes | Existing `performance-architecture` |
| 3 | **reliability-engineer** — partial failure, idempotency, blast radius | architect; cicd-engineer; planner | Retries, concurrency, external calls, hooks, migrations — anything with an at-least-once delivery story | Existing `observability` + `agent-failure-taxonomy` + `deployment` |
| 4 | **formalist** — invariants, state-space, concurrency correctness | architect (→ fitness functions); planner (step-ordering safety); test-engineer (→ property-based tests) | Concurrent or distributed state, a protocol, an ordering guarantee, or a "cannot happen" claim | Existing `architectural-fitness-functions` + `testing-strategy` |

Three of four require **no new knowledge**. This is the finding that makes the initiative cheap: the
expertise exists, the standing to object does not.

### 12.2 Wave 2 — gated on Wave 1 evidence

| Identity | Gap | Why it waits |
|---|---|---|
| queueing-modeler | Little's Law, Universal Scalability Law, capacity/saturation modelling, Fermi estimation | Real gap, narrower trigger surface |
| cost-economist | Token economics, cost-per-decision, tier ROI | Partially covered by `heterogeneous-orchestration.md` |
| cognitive-ergonomist | Human error, alarm fatigue, cognitive load | Overlaps `web-ui-design` / `tui-design` |
| data-steward | Privacy, retention, lineage, consent | Project-dependent; may warrant a dedicated agent instead |

### 12.3 Graduation rule

Follow the precedent already set by `agentic-transactions-architect`, which exists as a dedicated
agent because its domain is deep, recurrent, and authors ADRs constantly. A discipline **graduates**
from a consultant binding to its own agent when it crosses an evidence threshold — sustained task
recurrence with a high accepted-challenge rate, plus regular ADR-fragment authorship. This gives a
cheap on-ramp with an evidence-gated promotion path, and means agent-description tokens are never
paid for a discipline that has not earned them.

---

## 13. Registered objections

Recorded per the Register Objection clause of the behavioral contract — stated with reasons rather
than silently absorbed.

1. **"Mathematician" as a literal identity fails criterion (a).** Too broad to trigger reliably: it
   spans formal logic, numerical analysis, optimization, and probability, which route to three
   different disciplines. The decision-changing core is invariants and state-space reasoning, which
   is `formalist` — sharper, and testable by counterexample.
2. **"Physicist" as a literal identity fails criteria (a) and (c).** Its distinctive software
   contributions decompose almost entirely: stochastic modelling → statistician; conservation,
   invariants, and scaling → formalist; order-of-magnitude estimation → performance-engineer. The
   genuine non-decomposable residue is queueing theory and scaling laws, promoted to Wave 2 as
   `queueing-modeler`. Literal names remain available as cheap aliases, but **trigger conditions must
   be the methodological ones** — MAST identifies ambiguous role definitions as the top failure
   source, and "physicist" is maximally ambiguous.
3. **Automatic identity selection is the riskiest requirement**, mitigated but not eliminated by the
   three-tier model in [§11](#11-identity-selection-model). Tier 1 is untested against a random
   baseline. This is open question 3 in [§6](#6-open-questions-the-evidence-does-not-answer).
4. **The evidence for domain-expert labels specifically is weak.** The strong evidence is for
   conversational structure. The recommended architecture is deliberately shaped so the structural
   benefit is captured even if the expertise labels prove inert — but this should be stated plainly
   rather than assumed away.

---

## 14. Falsifiers

The initiative should be **deleted, not tuned**, if:

1. Across ~10 Standard/Full tasks, identity challenges are dispositioned `dismiss-with-rationale` at
   a high rate — the identities are producing decoration, not decisions.
2. Tier-1 trigger-table selection performs no better than random discipline assignment on
   accepted-challenge rate.
3. The measured cost per accepted challenge exceeds the existing design-synthesis cost envelope
   (≤3× baseline routine, ≤6× high-stakes).
4. Consult rounds systematically fail to terminate within the one-loop-back bound — MAST's
   missing-termination-condition mode, observed live.

---

## 15. Citations

- [Reasoning Models Generate Societies of Thought](https://arxiv.org/html/2601.10825v1) — Kim, Lai, Scherrer, Agüera y Arcas, Evans (arXiv:2601.10825v1, Jan 2026)
- [When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of LLMs](https://aclanthology.org/2024.findings-emnlp.888/) — Zheng et al., EMNLP Findings 2024
- [Better Zero-Shot Reasoning with Role-Play Prompting](https://aclanthology.org/2024.naacl-long.228/) — Kong et al., NAACL 2024
- [Unleashing the Emergent Cognitive Synergy in Large Language Models: Multi-Persona Self-Collaboration](https://aclanthology.org/2024.naacl-long.15/) — Wang et al., NAACL 2024
- [Persona is a Double-edged Sword](https://arxiv.org/html/2408.08631v1) — arXiv:2408.08631, 2024
- [Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657) — Cemri et al., NeurIPS 2025 Datasets & Benchmarks
- [MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework](https://arxiv.org/pdf/2308.00352)
- [SPOQ: Specialist Orchestrated Queuing for Multi-Agent Software Engineering](https://arxiv.org/abs/2606.03115) — Carbowitz & Kumar, June 2026
- [Rigorous Benchmarking in Reasonable Time](https://dl.acm.org/doi/10.1145/2491894.2464160) — Kalibera & Jones, ISMM 2013
