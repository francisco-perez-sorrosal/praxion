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

### 9.1 Extensibility requirement (user-mandated, non-negotiable)

Multidisciplinarity is a **goal of this initiative, not a side effect of it**. Whatever is built must
make adding identity N+1 cheap and safe, indefinitely. Stated below as a measurable acceptance
criterion, because "flexible" is the class of goal that erodes silently unless it is verifiable.

> [!NOTE]
> **Corrected 2026-07-30 at the Wave A/B gate.** The first version of this criterion demanded a flat
> `0` always-loaded delta *and* permitted a new skill for genuine knowledge gaps. Those two rows are
> **jointly unsatisfiable**, because a skill's `description` frontmatter is itself always-loaded
> (~142 tok mean) — so the criterion as originally written would have failed `statistician`, the very
> first identity requested. The defect was conflating two different costs. The corrected form below
> separates them.

**The distinction that fixes it: structural cost vs knowledge cost.**

- **Structural cost** is what adding a discipline demands of the *machinery* — rule edits, manifest
  entries, catalog rows, new agent files, pipeline stages. This must be **exactly zero**. It is pure
  friction with no compensating value, it is mechanically checkable, and it is what actually decays
  extensibility as N grows.
- **Knowledge cost** is what a genuinely new domain contributes — one skill carrying expertise Praxion
  does not yet own. This is **irreducible and legitimate**. Demanding it be zero is incoherent: the
  only way to add new knowledge for free is to not add knowledge. It is budgeted and tracked, not
  asserted away.

### Cost classes

| Cost class | When it applies | Threshold |
|---|---|---|
| **One-time machinery** | Built once, for the first discipline | ≤1,100 always-loaded tok, charged against headroom at design time (Wave A measured ≈925–1,050) |
| **Per-discipline — binding-only** | The discipline's expertise is already owned by an existing skill (e.g. performance, reliability, invariants) | **0** always-loaded bytes. A roster entry inside the consultant body only |
| **Per-discipline — genuine gap** | The discipline brings knowledge Praxion does not own (e.g. applied statistics) | **≤1 skill `description`** (~120–160 tok) and **zero** bytes in every other always-loaded surface |

### Structural invariants — apply to every class, no exceptions

| Invariant | Threshold |
|---|---|
| Always-loaded **rule** files changed | **0** |
| New agent files | **0** |
| `.claude-plugin/plugin.json` edits | **0** |
| Catalog/README rows or agent-count strings changed | **0** |
| Consultant `tools:` list changes | **0** — a mid-session `tools` mutation invalidates the entire prompt cache (`tools` → `system` → `messages`), so the tool list must be discipline-independent by construction |
| Pipeline stages added | **0** |
| Files touched | **≤2** — the roster entry, plus at most one new skill for a gap discipline |

### Extensibility runway

The corrected criterion yields a concrete, checkable forward budget rather than an aspiration:
with ~2,309 tok of headroom and ~1,050 tok of one-time machinery, roughly **1,259 tok remain** —
about **8 further gap disciplines** at ~150 tok each, and an **unbounded** number of binding-only
disciplines. Any design whose per-discipline cost is structural rather than knowledge-shaped burns
that runway for nothing.

### Model and effort routing must be generic, not per-discipline

A consequence of parameterizing the consultant by model tier *and* reasoning effort: the
difficulty→tier mapping must live as **one generic policy**, not one row per discipline. A design that
adds a per-discipline row to `rules/swe/agent-model-routing.md` (an always-loaded surface) converts
routing into a **structural** per-discipline cost and fails the invariants above. The roster entry may
carry a model/effort *hint*; the *policy* that interprets it stays generic and is written once.

Two design consequences follow. The architect should treat these as constraints, not options.

1. **The roster is data, not structure.** Discipline definitions must live in a single enumerable
   registry inside the consultant's own body (or one bound reference file) — never spread across
   always-loaded rules, and never one-file-per-discipline in a location that must be separately
   registered. A design that requires touching `plugin.json`, a catalog README, and an always-loaded
   rule table per discipline has failed this criterion regardless of how elegant it looks at N=1.
2. **Enforce the criterion mechanically rather than documenting it.** This is a natural
   architectural fitness function (see `skills/architectural-fitness-functions/`): an invariant test
   asserting that a discipline addition touches zero always-loaded surface. Encoding it as a test is
   what prevents extensibility from regressing the first time someone adds a discipline in a hurry.

Extensibility already appears at three distinct levels in the proposed design, and all three must be
preserved: **roster** (add a binding — §9), **discovery** (tier-3 identity genesis proposes new
disciplines from harvested signals — §11), and **promotion** (the graduation rule moves a proven
discipline to a dedicated agent — §12.3). The roster level is the one this criterion governs.

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
([§14](#14-falsifiers)). Shipping the selection tiers without the counter would make the value
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

**Revised 2026-07-30** (`dec-306`, §17.13). The roster below is filtered by a criterion that did
not exist when it was first drafted: **a discipline earns a consultant only when its errors are silent.** A
lens and a consultant deliver identical knowledge; the consultant's only marginal contribution is *standing
to object*. Where a wrong answer is caught by ordinary feedback — a benchmark, a profiler, a cost bill — the
knowledge belongs in a lens's owning skill, delivered free on every pass, and gating it behind a spawn makes
it *less* available rather than more rigorous.

| Identity | Gap | Status |
|---|---|---|
| **evidence-appraiser** | Source provenance, study-design-vs-claim-strength, external validity and transfer, citation drift, vendor-claim quarantine | **MERGED 2026-07-30 on `main`; NOT YET RELEASED** as discipline #2, bound to `evidence-appraisal`. Corrected 2026-07-30 (Wave 2) — this row previously read "SHIPPED", which was false with respect to what installed copies receive: the `v0.18.0` tag tree carries `skills/applied-statistics` but not `skills/evidence-appraisal`, and its registry carries zero `evidence-appraiser` rows. A managed project on `v0.18.0` therefore resolves `Discipline: evidence-appraiser` to `[BLOCKED]` — fail-loud, as designed, but not the advertised behaviour. `scripts/check_release_staleness.py` detected this correctly and is CI-wired; it is advisory, and nothing consumed its output (`td-073`). Errors are silent: a misread import propagates carrying the authority of a number. Charter is concrete — the first live consult declined to verify the coefficients its own analysis rested on, recording them as *relayed* |
| ~~queueing-modeler~~ | Little's Law, Universal Scalability Law, capacity/saturation modelling, Fermi estimation | **REMOVED.** `performance-architecture/references/capacity-planning.md` already contains Little's Law and back-of-envelope estimation, and the Performance lens delivers it unconditionally. A consultant here would duplicate free knowledge at spawn cost |
| ~~performance-engineer~~ | Order-of-magnitude estimation, saturation reasoning | **REMOVED.** Same reason, plus it was the named `lens-collision` instance. Performance errors surface through measurement, so the silence criterion excludes it. The lens was strengthened instead — `performance-architecture` gained the agent-era dimension (token budget, context efficiency, spawn cost, pipeline wall-clock), which it did not previously carry |
| ~~cost-economist~~ | Token economics, cost-per-decision, tier ROI | **EXCLUDED 2026-07-31** (dec-309). Absorbed by the Performance lens: `performance-architecture/references/agent-era-performance.md` covers token budget, spawn cost, and cost-per-useful-outcome, and states at line 63 that per-spawn cost is unrecoverable unless captured at the time — verbatim the argument `td-071` makes. Gating that knowledge behind a spawn subtracts availability. The Wave-2 consult explicitly left this candidate untouched: where the absorbed-by-lens finding holds, Type-II cost is near zero because the knowledge is delivered anyway |
| cognitive-ergonomist | Human error, alarm fatigue, cognitive load | **DEFERRED 2026-07-31** (dec-309) — not refused. Its exclusion rests on a claim that agent-facing ergonomics errors surface through sentinel's token-budget dimension, Agent Readiness LLM-judged criteria, and eval scores; that surfacing claim is **asserted, not measured**. The prior 'overlaps the context-engineer agent' rationale was checked and found weak — one incidental hit for cognitive-ergonomics vocabulary in `agents/context-engineer.md` — and is no longer relied on |
| data-steward | Privacy, retention, lineage, consent | **DEFERRED under unmeasured Type-II risk 2026-07-31** (dec-309). It **passes** the silence criterion: retention, consent, and lineage violations produce no signal until an audit or breach. The Wave-2 draft's rejection was withdrawn under challenge — it estimated Praxion's decision surface by an artifact grep, which can only find decisions someone already recognised as decisions, so that surface is **unestimated, not thin**. Remains the concrete motivating instance for the project-local overlay (`td-064` / `dec-305`) |

**A non-`none` `lens-collision` value is now read as a design signal**, not a documentation chore: it asks
first whether the discipline should exist at all, and only then what its escalation relationship would be.

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
   a high rate — the identities are producing decoration, not decisions. **This is a judgment call on
   a reported estimate, not a threshold test** (revised 2026-07-30, §17.11): read the dismiss rate with
   its Wilson interval per §17.4, over distinct consults rather than challenge rows. No number is
   pre-registered here, because a single number cannot both mark "delete the initiative" and "do not
   expand it" without the two verdicts colliding at the boundary — which is precisely the defect the
   first live consult found in the earlier form of this falsifier.
2. Tier-1 trigger-table selection performs no better than random discipline assignment on
   accepted-challenge rate.
3. The measured cost per accepted challenge exceeds the existing design-synthesis cost envelope
   (≤3× baseline routine, ≤6× high-stakes).
4. Consult rounds systematically fail to terminate within the one-loop-back bound — MAST's
   missing-termination-condition mode, observed live.

---

## 15. Wave A outcomes — the premise is under threat

Recorded 2026-07-30 at the Wave A/B gate. Three agents ran in isolation (external-evidence
researcher at Opus, internal-surface researcher, context-engineer), each forbidden from reading
sibling fragments during collection. Fragments live in gitignored `.ai-work/multidisciplinary-identities/`
(~144 KB); this section is their durable reconciliation.

### 15.1 Confirmed threat to the premise

[Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?](https://aclanthology.org/2024.acl-long.331/)
— Wang, Wang, Su, Tong, Song, ACL 2024 (arXiv:2402.18272). **Verified independently at orchestrator
level, not relayed on trust:**

> "A single-agent LLM with strong prompts can achieve almost the same best performance as the best
> existing discussion approach on a wide range of reasoning tasks and backbone LLMs."

> "The multi-agent discussion performs better than a single agent only when there is no
> demonstration in the prompt."

**Praxion is demonstration-dense by construction** — skills, rules, and agent bodies are largely
worked examples. This paper's boundary condition therefore lands squarely on Praxion's own
configuration, and it predicts a *small or null* gain from adding a discussing party.

Consequence: [§8](#8-design-space) is incomplete. It evaluated A (N agents), B (N skills), and C
(parameterized consultant) but **never evaluated Option D — no new party, stronger architect
context**. B was dismissed for lacking dialogue; D1 says dialogue may not pay here. The null option
deserved a seat and did not get one.

### 15.2 Partially confirmed: expert personas can damage accuracy

[Expert Personas Improve LLM Alignment but Damage Accuracy: Bootstrapping Intent-Based Persona
Routing with PRISM](https://arxiv.org/abs/2603.18507) — Hu, Rostami, Thomason, 19 Mar 2026.

**Confirmed at orchestrator level:** the paper exists and its title asserts the directional claim —
expert personas improve alignment but damage accuracy.

**Not confirmed at orchestrator level:** the specific figures reported by the research lens (MMLU
71.6% → 68.0%/66.3%; MT-Bench Coding −0.65; routed 73.5 > always-on 72.2 > random 70.5; gate/effect
correlation r=0.65). The abstract page did not expose them. These remain **agent-sourced and
unverified** — treat as medium confidence pending a full-text read.

The MT-Bench *Coding* regression, if it holds, is the most uncomfortable single datum for this
initiative: coding is Praxion's domain.

### 15.3 Convergences reached independently (strongest signals)

| Finding | Reached by | Why it counts |
|---|---|---|
| Always-loaded budget is **GO**, but the cost is higher than [§9](#9-recommended-architecture-hypothesis) claimed — one-time wiring ≈925–1,050 tok; Wave-1 total ≈640–790 tok (30–34% of headroom) | both internal lenses, independently | The ~500 tok figure in §9 conflated two budget ledgers. Corrected. |
| Per-discipline **recurring** cost genuinely can be **0** always-loaded tokens | context-engineer (by construction) + internal researcher (by git archaeology: `Mode:` #2 cost 0 bytes; #3 cost 4 lines only because it added a new *artifact type*) | Two independent methods, same answer. §9.1's N+1 criterion is achievable. |
| **Isolate-then-dialogue is correct** | external lens (Anthropic Tier-1 docs independently name *anchoring* as the failure independence prevents) + context-engineer (`context: fork` inherits the full parent conversation and mechanically breaks Round-0 isolation) | Convergent, and `context: fork` is now disqualified as a cheaper substrate. |
| **Agent teams are disqualified** as the dialogue substrate | external lens (three Tier-1 blockers: `skills:` frontmatter **silently dropped** for teammates — which would kill the discipline→skill bindings entirely; no nested teams — which would kill Tier-2 self-nomination; body appended not replaced) + context-engineer | Convergent. Subagent topology stands. |
| The accept/defer/dismiss counter is **a prerequisite, not a postscript** | external lens (PRISM's gate beats random *because* it correlates with measured persona effect — the counter is the router's calibration loop) + internal lens (no countable persistent artifact exists today; `switch-now` persists via ADRs but `defer`/`dismiss` land only in ephemeral prose) | Elevates the counter from falsifier to **precondition**. Must ship first. |

### 15.4 Unresolved contradiction — lens or peer?

The two lenses that could not see each other **directly contradict** on a load-bearing point:

| Lens | Verdict on the closed Lens Catalog |
|---|---|
| context-engineer | **CRITICAL** — `performance-engineer` duplicates the existing Performance lens *today*. Requires a Wave-1 ADR supersession, not a deferred one. |
| internal-surface | Lens Catalog **needs no edit** — the consultant is architecturally a *shadow sub-architect*, not a lens. Conflation risk flagged explicitly. |

The underlying question is genuinely architectural: **is a disciplinary consultant a *lens* (an
evaluation criterion applied to options) or a *peer* (an agent with standing to object)?** The answer
determines whether Wave 1 carries an ADR supersession. Unadjudicated at the gate — a disagreement
surviving isolation marks real ambiguity, not noise.

### 15.5 Answered questions and their design consequences

| Q | Verdict | Consequence |
|---|---|---|
| Q1 domain vs conversational diversity | **PARTIAL — and disconfirming.** No source ablates role content with structure held fixed. The nearest evidence is negative (§15.2). Critically: **every diversity result that pays varies the *backbone*** — the axis §9's single-Opus floor forecloses. | §9's Opus floor is right for *capability* (SPP's frontier-only synergy) but it eliminated **model heterogeneity**, which is the diversity axis with actual evidence behind it. Reopen. |
| Q2 one round or two | **ANSWERED — one round, possibly generous.** A sequential-probability-ratio governor stops at 1.01 average rounds reaching 97.0% vs 99.0% for fixed-5 rounds at 3.7× the calls. Controlled depth coefficient 0.019 (n.s.) vs agent-count 0.066 (p<0.001). | Value is in **breadth (independent perspectives)**, not **depth (dialogue rounds)**. Gate *before* round 0 — conformity harm fires at first exposure (K=2). |
| Q3 bounded routing vs random | **ANSWERED with a caveat.** Guided routing over a bounded roster beats random, replicated. **But every validated router is learned or model-scored — hand-authored routing remains untested.** | The [§13](#13-registered-objections) objection **stands**. Tier-1's authored trigger table is still unvalidated; the counter is what would calibrate it. |
| Q4 reconciliation deficit transfer | **ANSWERED — transfers, and dominates.** Five 2026 sources converge: *"selector quality may be a more impactful design lever than generator diversity."* Judge 0.810 / vote 0.496 / **synthesis 0.179** (g=3.86); oracle gap 32.3pp. | Invest in **synthesis quality**, not roster size. Synthesis is the weakest link by a large margin. |
| Q5 agent teams | **ANSWERED — no.** See §15.3. | Subagent + orchestrator-mediated dialogue confirmed. |

### 15.6 Additional internal findings

- **Pre-existing debt:** `agents/implementation-planner.md` is already **526 lines, past its own
  sentinel FAIL threshold of 500**, before this task touches it. `systems-architect.md` (472) and
  `researcher.md` (319) are in WARN.
- **No harness to extend:** the `Mode:` directive has **zero** test, hook, or sentinel validation —
  pure prompt convention. A `Discipline:` directive must have validation *built*, not inherited.
- **Insertion surface is larger than mapped:** 18 one-time points, including `adr-conventions.md`'s
  "Who Writes ADRs" table, the pipeline Mermaid diagram, hardcoded agent-count strings in
  `docs/architecture.md`, and sentinel's own self-referential name list. 11+ sentinel checks implicated.
- **Tier-3 identity genesis is not free:** `skill-genesis`'s triage schema has **no "new discipline"
  slot**. [§11](#11-identity-selection-model)'s "reuses existing machinery" was aspirational.
- **§9.1 is internally inconsistent:** its "new skill only when a genuine knowledge gap" row and its
  "0 always-loaded token delta" row are **jointly unsatisfiable** for a gap discipline such as
  `statistician`, because a new skill's `description` is itself always-loaded (~142 tok). The
  criterion must separate **one-time** from **per-discipline recurring** cost.
- **Clean:** no shipped-artifact-isolation violation; no canonical-block mirroring required.
- **Placement (Q12):** split verdict — this dossier stays in `docs/` (Praxion-specific numbers do not
  transfer); a distilled, portable reference belongs under
  `skills/multi-perspective-analysis/references/` since that surface ships to managed projects.

### 15.7 Revised recommendation

The evidence no longer supports building Option C on faith. It supports **testing it against the null
first**, at small cost:

1. **Phase 0 becomes a comparison, not a build.** Run both arms on the same real decisions —
   *Arm D*: architect with an applied-statistics skill injected and a strong prompt (no new party).
   *Arm C*: architect plus a separate statistician consultant using the dialogue protocol.
   Measure decision changes, accepted-challenge rate, and cost. This directly tests D1 inside
   Praxion's own demonstration-dense configuration, which is exactly where the external evidence is
   silent — and it is what the `statistician` identity would itself demand.
2. **Ship the disposition counter before the roster.** Q3 + Q4 make it the calibration loop, not the
   report card.
3. **Reopen backbone heterogeneity.** Per Q1, model diversity is the axis with evidence; Praxion
   already owns the machinery in `heterogeneous-orchestration.md`.
4. **Spend on synthesis, not on more identities.** Q4's effect size (g=3.86) says the selector
   dominates the generators.
5. **Fix §9.1's inconsistency** and adjudicate §15.4 before any artifact is written.

---

## 16. User rulings at the Wave A/B gate

Recorded 2026-07-30. These are **binding decisions**, made by the user after reading the Wave A
digest. They supersede the corresponding proposals in [§9](#9-recommended-architecture-hypothesis),
[§12](#12-identity-roster), and [§15.7](#157-revised-recommendation). Downstream stages honor them
and do not re-litigate them; a stage that believes a ruling is structurally unsafe registers an
objection with a reason rather than silently deviating.

| # | Ruling | Supersedes |
|---|---|---|
| 1 | **Peer, not lens** — the consultant is a parameterizable *peer* (shadow sub-architect with standing to object), not an evaluation lens | Resolves the §15.4 contradiction in favour of the internal-surface lens. The closed Lens Catalog needs **no** Wave-1 supersession |
| 2 | **Parameterized/configurable agent** — Option C proceeds. Option D (no new party) is **not** adopted as the build path | §15.7 item 1 (A/B-first) |
| 3 | **Heterogeneity opens on two axes — model *and* reasoning effort** — selected by task difficulty, using frontier-lab published model-selection guidance | §9's single-Opus floor; §2 item 3 |
| 4 | **One identity only: `statistician`** | §12.1's four-identity Wave 1 |
| 5 | **Fix §9.1 before designing** — done; see the corrected criterion | §15.7 item 5 |
| 6 | **Multi-instance by design** — the mechanism must support **N concurrent consultant instances, each configured with a different discipline**, not one-discipline-at-a-time | Extends §9; see §16.3 |
| 7 | **Scope amendment — a second, binding-only discipline ships alongside `statistician`** (reliability-shaped; knowledge already owned per §7.4). Costs one registry row and **0** always-loaded bytes | Amends ruling 4. Makes AC13 (§17.5) testable and converts the N+1 property from a fitness-test assertion into an empirical demonstration |
| 8 | **Effort axis resolves as model-parameter + in-context `ultrathink` directive** — accepted *with* the stated limitation that the effort half is a prompt convention, not mechanically assertable | Confirms ruling 3's fallback after the architect's verified objection |
| 9 | **Implementation bounded to Milestones 0–1** (steps 1–3: mechanism spike, disposition ledger, extensibility fitness test), then stop for review | Bounds the first implementation wave to the cheapest evidence-producing slice |

**Ruling 4 dissolves the §15.4 conflict entirely for Wave 1.** The CRITICAL finding was specifically
that `performance-engineer` duplicates the existing Performance lens. With `performance-engineer`
deferred, no Wave-1 discipline collides with the Lens Catalog. The collision becomes a **deferred
condition**: any future discipline whose name matches an existing lens must either bind to that lens's
owning artifact as a peer, or carry an ADR supersession. Record this as a reversal trigger.

### 16.1 The reasoning-model-era argument — verified, and stronger than first summarized

The user's rationale for overriding [§15.1](#151-confirmed-threat-to-the-premise) is that the 2024
null result predates strong reasoning models, and that the primary paper's format-over-content finding
is the relevant evidence for the 2025–2026 model generation. **Verified at orchestrator level:**

> "Notably, both conditions are trained on identical problems and correct answers, yet
> conversation-fine-tuned models consistently improve faster and reach higher asymptotic accuracy."
> — Results, Reinforcement Learning Experiments

The controls are genuine. The monologue arm generates "standard chain-of-thought traces for the 'same
problems' with correct answers, where a single voice reasons within `<think> … </think>` tags"; the
dialogue arm has personas "engage in turn-taking dialogue where they build on, question, and correct
each other's reasoning." **Identical problems, identical correct answers — only the format varies.**

This is a controlled format-vs-content experiment, and dialogue wins on *both* convergence speed and
the ceiling. It also corrects an earlier paraphrase in this dossier's own §3.1, which reported faster
convergence "without changing asymptotic performance" — the paper's own wording says **higher
asymptotic accuracy**. Format is not merely an accelerant; it raises the ceiling. That materially
strengthens ruling 2.

### 16.2 The load-bearing assumption, stated so it can fail

The paper is explicit that it does **not** claim transfer to deployed multi-agent systems:

> "Without deploying separate models prompted to interact with one another, we suggest that
> behaviourally similar conversations between diverse perspectives occur and are leveraged within
> reasoning models."

So ruling 2 rests on an **inference**: that the value of dialogue format transfers from
*intra-model* (one model's trace) to *inter-agent* (separate agents in a pipeline). The paper's
Discussion encourages exactly this exploration ([§3.2](#32-the-paper-is-pro-multi-agent-corrects-a-common-misreading-of-the-abstract))
but does not test it.

The competing hypothesis must be named so the bet is falsifiable rather than an article of faith:

> **Substitution hypothesis.** If reasoning models *already* internally simulate a society of thought,
> an external society may be redundant — and stronger reasoning models would make explicit multi-agent
> deliberation *less* valuable, not more.

Evidence against pure substitution, and therefore for the bet: the internal society is **incomplete**
— [§3.3](#33-the-reconciliation-deficit--the-most-actionable-finding)'s reconciliation deficit shows
internal perspectives "compete rather than forming an effective ensemble." That is a concrete
mechanism by which external structure adds what the internal society lacks: enforced, single-owner
synthesis. It is also corroborated independently by Wave A's Q4 finding that selector quality
dominates generator diversity.

**Falsifier for ruling 2 specifically:** if the consultant's challenges are dispositioned
`dismiss-with-rationale` at a high rate while the architect's unaided output with the same knowledge
injected is indistinguishable in quality, the substitution hypothesis holds and the external party
should be removed in favour of Option D. The disposition counter is what makes this measurable — which
is why Wave A ranked it a prerequisite, not a report card.

### 16.3 Multi-instance concurrency (ruling 6) — the best-evidenced axis in the design

The mechanism must be able to run **several consultant instances at once, each parameterized to a
different discipline**, and must not assume a single consultant per task. Wave 1 ships one discipline
(`statistician`), but the *mechanism* must not foreclose N.

> **Attribution withdrawn 2026-07-30** (`evidence-appraiser` consult, §17.14). The coefficients below
> **name no source anywhere in this repository** — §18's citation list contains no candidate, no section
> attributes them to an identifier, and the only upstream was a Wave A research fragment under `.ai-work/`,
> which is gitignored and has been deleted. The claim is therefore **permanently unre-appraisable**: a
> reader cannot check it, and neither can we. It is retained below as a record of what was believed at
> design time, **not** as evidence. Two further defects were upheld: this dossier's own verification
> convention (§15.1, §15.2) was applied to weaker claims and skipped here; and the depth coefficient
> measures *peer-visible debate rounds*, a construct our protocol contains **zero** of — so it is silent
> on the one-loop-back bound rather than confirming it, an objection `dec-298`'s own `dissent:` field had
> already registered independently.

~~**This is the axis with the strongest empirical support of anything in this dossier.**~~ Wave A's Q2
reported, in what was described as a controlled comparison, an **agent-count** coefficient of 0.066
(p<0.001) against a **dialogue-depth** coefficient of 0.019 (not significant) — *source unidentified*.
The design conclusion it was used to support (breadth of independent perspectives over depth of argument)
is unchanged, because the multi-instance design and the one-round bound each rest on independent grounds:
the sequential-probability-ratio result and the ICML self-consistency result in §10, and the termination
and conformity arguments that do not depend on these coefficients at all. **What changes is the stated
evidence base, not the design.** The one-round bound should be described as *defensible on termination
grounds*, never as *confirmed by measurement*.

Design constraints that follow:

| Constraint | Requirement |
|---|---|
| **Fragment isolation** | Each instance writes `CONSULT_<discipline>.md` — never a shared canonical file. This is Praxion's existing parallel-execution fragment pattern; no new convention is needed |
| **Lens independence holds *across* instances** | During round 0, no instance may read a sibling's fragment. Concurrent consultants that can see each other collapse into one correlated opinion at N× the cost — the exact failure the isolate/reconcile discipline exists to prevent |
| **Single-owner reconciliation still holds** | The architect merges N fragments. Consultants never negotiate with each other. Q4's finding that selector quality dominates generator diversity (g=3.86) means the merge is where quality is won, and it must not be distributed |
| **Concurrency cap** | 2–3 concurrent instances, matching Praxion's existing multiplicity guidance, bounded by the design-synthesis cost envelope (≤3× baseline routine, ≤6× high-stakes) |
| **Composes with ruling 3** | Per-instance model *and* effort selection turns a multi-instance fan-out into the established Haiku-proposer / Opus-aggregator recipe already documented in `skills/multi-perspective-analysis/references/heterogeneous-orchestration.md` — cheap proposers, frontier aggregator |
| **No effect on §9.1** | Instances are a **runtime** concern; disciplines are a **registry** concern. Running three consultants costs three spawns, not three roster edits, and adds zero always-loaded bytes |

**Objection registered against a plausible misreading of ruling 6:** "more identities" is not
free quality. Q2's agent-count result was measured at small N, and MAST's inter-agent-misalignment
category (~37% of failures) scales with participant count. The cap is load-bearing, and the trigger
gate must still fire per discipline — three consultants convened because three triggers fired is
breadth; three convened by default is cost.

---

## 17. Roadmap (Wave C outcome)

Recorded 2026-07-30. The detailed step decomposition lives in
`.ai-work/multidisciplinary-identities/IMPLEMENTATION_PLAN.md` (565 lines), which is **gitignored and
deleted at pipeline cleanup**. This section is its durable form: enough to reconstruct intent and
re-derive the steps if the working plan is gone.

**Shape:** 16 steps across 7 milestones (0–6), test baseline clean at 573 tests passing.

### 17.1 Milestones

| Milestone | Steps | Purpose |
|---|---|---|
| **0 — Foundation** | 1 | Prove the load-bearing mechanism before anything is built |
| **1 — Instrumentation** | 2–3 | Ship the disposition ledger and the extensibility fitness test **before any discipline exists** |
| **2 — Mechanism skeleton** | 4–6 | The parameterized consultant, always-loaded wiring, manifest registration — still **zero** disciplines bound |
| **3 — Knowledge gap** | 7–8 | The `applied-statistics` skill + catalog entry + a duplication check against existing benchmarking material |
| **4 — Bind `statistician`** | 9 | The registry stops being empty; the mechanism becomes *spawnable* |
| **5 — Protocol + selection** | 10–13 | Dialogue procedure, `Discipline:` directive contract, Tier-2 self-nomination, sentinel self-reference |
| **6 — Entry point + proof** | 14–16 | `/consult` command, **end-to-end live smoke test**, documentation flipped to `Built` |

**Milestone A (the milestone that matters):** a usable, proven, documented `statistician` consultation
— reached at step 16, not step 9. Spawnable ≠ verified-usable, and the plan keeps those distinct.

### 17.2 Load-bearing ordering

1. **Step 1 is a falsification spike, not a build step.** The design's "identity N+1 is structurally
   free" property rests on a subagent invoking the `Skill` tool at runtime to load a plugin skill it
   does not declare in `skills:`. That mechanism is **unverified** — `agent-crafting` documents that
   agents do not *inherit* skills, but says nothing about dynamic invocation. It is the initiative's
   **only genuine one-way door**; a FAIL blocks every downstream step and requires an architect
   loop-back rather than a workaround.
2. **Instrumentation precedes the roster.** The ledger and the fitness test land at steps 2–3, before
   any discipline artifact exists. Both Wave A lenses converged that the disposition counter is the
   router's *calibration loop*, not a report card; and a fitness test landed early cannot be
   retro-fitted around later files.
3. **Documentation catch-up is a step, not a footnote.** Step 16 flips `docs/architecture.md` to
   `Built`, including the hardcoded agent-count strings the architect flagged.

### 17.3 RISKY steps (`tier: H` / `review: force`)

| Step | Why |
|---|---|
| 1 | One-way door — the mechanism either holds or the design changes |
| 4 | Touches three always-loaded rule files plus a new agent and `plugin.json` in one atomic commit, to avoid leaving a sentinel FAIL window open between commits |
| 11 | Five files across four pipeline-agent boundaries |
| 12 | Sentinel self-reference (count bump + scope extension) — flagged twice by the architect as the easiest insertion point to silently miss |

### 17.4 Wave 2 phase gates — reported estimates and standing conditions

> **Revised 2026-07-30**, after the mechanism's first live consult challenged this very table. The
> `statistician` consult raised six defects in the original binary form; the repair is recorded in
> §17.11 with its full reasoning. The short version: **at n=10 a binary pass/fail gate on this
> statistic cannot distinguish the cases the decision turns on**, so the discipline-#2 gate is now a
> *reported estimate with an interval plus standing conditions*, not an automatic threshold. Earlier
> revisions of this table stated "dismiss rate not >60% over ≥10 challenges spanning ≥3 tasks"; that
> form is superseded and should not be cited.

| Gate | Criterion | Unlocks |
|---|---|---|
| **Discipline #2** | **Reported, not automatic.** Compute the dismiss rate for `statistician` as `k/n` with a Wilson 95% interval, where **`n` is the number of distinct consults** (`task-slug` values), not the number of challenge rows — challenges cluster within a consult and are not independent observations. Report the interval alongside the point estimate; a human dispositions it. **Two standing conditions gate the report's informativeness**, both of which must hold before the number is read as evidence at all: (a) **all three disposition values** (`switch-now` / `defer-with-rationale` / `dismiss-with-rationale`) have been observed at least once — a ledger with no dismissals is equally consistent with a well-calibrated router and with a convener who never adjudicates; (b) `n` ≥ 3 distinct consults. **No pre-registration burden**: because nothing is decided automatically, the estimate may be read at any time without inflating an error rate | A second registry row |
| **Tier-3 identity genesis** | ≥20 ledger rows across ≥2 disciplines, with the discipline-#2 criterion satisfied **per discipline, not pooled** — a pooled rate lets one discipline's failure be concealed by another's volume (4 rows at 90% pooled with 16 at 30% reads as 42%, comfortably healthy, while one of the two is exactly the decoration §14 exists to catch). **Deadlock watch:** fewer than 5 rows after two calendar quarters *reopens* the tier question rather than silently freezing the roster | One triage leaf + one enum value + one delegation row in the harvest agent |
| **Ledger promotion** | ≥4 active disciplines, **or** a demonstrated need for a rate-over-time series that `grep` cannot produce | Collector-plus-report shape; existing rows migrate |
| **Leave-One-Out audit** | Ongoing and **sampled**, not per-task: same-task runs with and without the consultant | Keeps the disposition ratio honest. A disagreeing LOO result **demotes the ratio from falsifier to indicator** — this is the surviving form of the Option-D comparison from §15.7, preserved as a continuing audit rather than a blocking pre-build gate |
| **Portable distillation** | Same gate as Tier-3 | A generic, Praxion-number-free reference for managed projects |
| **`performance-engineer` escalation relationship** | Must be written **before** that discipline ships | Unblocks the one discipline that collides with an existing lens (§16 ruling 1's deferred condition) |

### 17.5 Known limitation and two registered objections

**AC13 cannot be exercised end-to-end in Wave 1.** The multi-instance acceptance criterion requires two
*different* disciplines running concurrently, and ruling 4 ships only one. Recorded as a scoped
verifier WARN rather than silently dropped. This is a direct, benign collision between ruling 4
(statistician only) and ruling 6 (multi-instance by design) — the mechanism is built for N and tested
at N=1.

The cheapest route to closing it, if desired: bind **one additional binding-only discipline** with no
lens collision (reliability-shaped knowledge already exists per §7.4). Per §9.1 that costs **one
registry row and zero always-loaded bytes** — which would simultaneously make AC13 testable and serve
as the *empirical proof* that identity N+1 is free. It widens Wave 1 beyond ruling 4, so it is a user
decision, not a planning one.

**Objections registered by the planner:**

1. "Tier-2 self-nomination is separately gated" was re-read as *sequenced later*, not *evidence-gated*
   — literal evidence-gating would contradict the selection-tiers ADR. Correct reading; the
   orchestrator's instruction was the loose one.
2. AC13's untestability was documented rather than dropped (above).

### 17.6 Project-local disciplines — deferred with a recorded path

The registry lives in a **shipped** skill reference, so a managed project cannot add its own discipline
without editing an installed file. Since the requirement includes identities "optionally proposed by
the praxion users," this is a genuine gap along a *different* extensibility axis than N+1: extensibility
for **users**, not for Praxion. Deferred deliberately rather than resolved at planning stage, with the
concrete path recorded — a project-local overlay consulted before the shipped registry.

**Wave-2 update (2026-07-31): the spike was redesigned but not run.** `dec-305` designed the overlay;
its load-bearing half — a project binding *its own* skill to a project-local discipline — stayed
unproven, and a consult found the Wave-1 probe would not have licensed the decision because that probe
used a **project-scope agent** while the consultant is a **plugin subagent**, so a PASS would not
transfer. Wave 2 redesigned it. Four findings are recorded here so the design survives `.ai-work/`
cleanup:

1. **The gap is narrower than framed.** Plugin subagent → *plugin*-scope skill already works and is
   verified in the installed cache. The single open cell is **plugin subagent × project-scope skill**.
2. **The registry-union half is not gated at all.** A subagent inherits the session cwd, so reading a
   project-local overlay file needs no new mechanism. Only `binds-to` naming a *project* skill is
   unproven.
3. **No release is required to run it.** `claude --plugin-dir ./my-plugin` loads a plugin directly
   without installation, and `/plugin marketplace add ./my-marketplace` works from a local directory.
   A throwaway plugin therefore yields a genuine plugin subagent at zero cost to Praxion's release
   train — which removes the reason the spike kept being postponed.
4. **The self-hosting trap is avoided structurally**, by running outside Praxion so no `i-am` copy
   participates. Note the cache's `gitCommitSha` in `installed_plugins.json` is **wrong** here (a
   `0.7.1`-era sha recorded against a `0.18.0` install), so any precondition check must `diff` trees,
   never compare shas.

Not run this wave: a spike executed poorly is worse than none — that is the entire lesson of the
Wave-1 attempt this redesign replaces. It is ready to run and is the prerequisite for `td-064`, which
the roster decision (`dec-309`) made more load-bearing by naming `data-steward` as the
discipline whose decision surface most plausibly lives in a managed project rather than in Praxion.

### 17.7 Step 1 spike outcome — mechanism 1 CONFIRMED after a two-round probe

Run 2026-07-30. Step 1 was ordered first precisely so the binding assumption could be falsified
cheaply. Round 1 failed to confirm it and left the load-bearing question open; round 2, run from a
fresh session with a purpose-built probe agent, **confirmed mechanism 1**. Both rounds are recorded
below — round 1 because its intermediate negative is what motivated the probe, and because two of its
findings (no listing on existing Praxion agents; `Skill` absent from all 16 agents' allowlists) still
stand.

| Question | Result |
|---|---|
| Is `Skill` invocable inside *a* subagent, resolving a plugin namespace, with content genuinely loading? | **Proven** — distinctive verbatim lines quoted from two different plugin skills by a `general-purpose` agent (which holds all tools *and* a full skills listing) |
| Does static `skills:` frontmatter injection work? | **Confirmed** — full skill bodies arrive verbatim in the agent's context |
| Does a **custom plugin agent** receive an available-skills **listing**? | **NO** — a probe on an existing Praxion agent reported neither listing nor tool |
| Does a custom plugin agent receive the `Skill` **tool**? | **Only if explicitly declared.** Tools are a strict allowlist — and **zero of Praxion's 16 agents declare `Skill`**; every one uses static `skills:` frontmatter |
| Can an agent holding `Skill` but receiving **no listing** invoke a skill by a name it was *told*? | **Resolved in round 2 — see below.** The premise turned out to be false: a custom agent declaring `tools: Read, Skill` *does* receive a full listing, and invocation succeeds either way |

**Why it cannot be resolved in-session.** Agents load at session start, so a newly authored agent file
is not spawnable until a restart. The `Skill` tool's own contract states the name must come *"from the
listing"* and warns against guessing — and a custom agent has no listing. Whether the tool nonetheless
resolves from the plugin registry decides whether the "identity N+1 is structurally free" property
holds as designed.

**The methodological point worth preserving:** had the roadmap begun with the ledger and fitness test,
`fitness/tests/test_discipline_registry_invariants.py` would have been written asserting *"0 consultant
`skills:` entries"* — an invariant encoding a binding mechanism that may not exist. The test would have
passed while protecting the wrong design. Cheap falsification first is what prevented that.

#### Three candidate binding mechanisms

The design degrades under a negative result; it does not die.

| Mechanism | Status | Cost profile |
|---|---|---|
| **1. Runtime `Skill` invocation** (the design's choice) | **VERIFIED for custom agents** (round 2, 2026-07-30) | Ideal — only the active discipline's knowledge loads per consultation |
| **2. Static `skills:` frontmatter listing all disciplines** | Works today, proven | **0** always-loaded tokens (frontmatter never reaches the orchestrator's context), so the N+1 guarantee *survives on the always-loaded ledger* — but every consultation loads every discipline's body. Tolerable at N=2, serious context pollution by N=8. Contradicts REQ-16 as currently written |
| **3. Orchestrator-injected skill content in the spawn prompt** | Works today | Keeps per-consultation loading selective; shifts binding work to the orchestrator and weakens prompt-cache reuse |

#### Round 2 — the probe verdict: `WORKS`

Run 2026-07-30 from a genuinely fresh session (a restart was required; `--continue` / `--resume`
restores the conversation but keeps the agent registry captured at the original session start, so a
newly authored agent stays invisible — observed directly). The probe agent was a throwaway declaring
`tools: Read, Skill` and **no** `skills:` frontmatter, spawned once.

| Probe question | Observed result |
|---|---|
| Does a custom agent with `tools: Read, Skill` receive an available-skills listing? | **YES** — ~95 entries, beginning `digitalocean-ai` and `plugin-dev:create-plugin`; both target skills present verbatim |
| Is `Skill` among its granted tools? | **YES** |
| Does runtime invocation of a plugin-namespaced skill succeed? | **YES** — `i-am:testing-strategy` returned `Launching skill: i-am:testing-strategy`, resolving to `~/.claude/plugins/cache/bit-agora/i-am/0.16.0/skills/testing-strategy` |
| Did the content genuinely load? | **YES** — distinctive verbatim line quoted: *"**Coverage theater.** Chasing a line coverage target (e.g., 90%) incentivizes testing trivial code (getters, framework glue) while ignoring complex logic that is hard to cover."* |
| Second skill, to rule out a fluke | **YES** — `i-am:multi-perspective-analysis` loaded, distinctive HARD-gate line quoted |
| Is the `i-am:` namespace prefix required? | **Optional** — bare `testing-strategy` resolved to the same skill (deduplicated against the already-loaded body rather than erroring) |

**Verdict recorded as `WORKS`.** The probe's own return header self-labelled `FAILS`, which is a
mislabel worth preserving as a lesson: it graded itself against its *precondition* ("no listing
present") rather than against the *research question* ("can a `skills:`-less agent invoke a
plugin-namespaced skill at runtime"). The precondition was violated; the research question was
answered affirmatively, twice, with content proof. **The violated precondition strengthens the design
rather than weakening it** — granting the `Skill` tool also supplies the listing, so a consultant does
not depend on being told a name it cannot verify. There is no branch of this result in which the
design receives less capability than REQ-16 assumes.

**Residual risk, bounded.** Invocation was proven for skills *present in the listing*. If a
discipline's skill were ever absent from a consultant's listing, name-only invocation is still
untested. Not a realistic concern for a Praxion-shipped skill, and cheap to re-probe if it arises.

**Consequence for the roadmap:** mechanism 1 is the binding mechanism. REQ-16 stands unamended, no
architect loop-back is required, and steps 2–3 proceed as planned — step 3's
`fitness/tests/test_discipline_registry_invariants.py` may now legitimately assert *"0 consultant
`skills:` entries"*, since the mechanism that invariant protects is confirmed to exist.

#### Secondary finding — worktree project-agent discovery: INDETERMINATE

The brief asked which copy of the probe resolved: user scope (`~/.claude/agents/`) or worktree project
scope (`.claude/agents/` under `.claude/worktrees/…`). This matters beyond the probe, since every
Standard/Full Praxion pipeline runs inside a worktree.

**Unresolved.** The two copies were byte-identical, so content could not disambiguate them. A marker
was then added to the project-scope copy and the probe re-spawned; it reported `MARKER ABSENT` — but
that is *confounded*, because agent bodies are snapshotted at session start and the marker was written
afterwards. `MARKER ABSENT` is therefore consistent with both "user scope won" and "project scope won
but the body is cached". What *is* established: `skill-probe` appeared in the session's agent registry
while both copies existed, so it was discovered from at least one scope.

Cheap decisive follow-up, if the answer is ever needed: place the agent in **one** scope only, start a
fresh session, and check whether it appears in the registry. Untested here because both copies were
slated for deletion.

### 17.8 Milestones 0–1 executed — two findings worth keeping

Committed 2026-07-30 (`974bca1`). Steps 1–3 done; full fitness suite green at 22 tests.

**Finding 1 — agent bodies are snapshotted at session start, and that settles an open design choice.**
While attempting to disambiguate which probe copy resolved, a marker was added to one copy and the
agent re-spawned; the marker read as **absent**, but the signal is confounded — an agent's *body* is
captured at session start, so "absent" is equally consistent with "the other copy won" and with "this
copy won but its cached body was used." Correctly recorded as indeterminate rather than inferred.

The incidental finding matters more than the question it failed to answer. [§9.1](#91-extensibility-requirement-user-mandated-non-negotiable)
permitted the discipline roster to live **either** in the consultant's own body **or** in one bound
reference file. Those options are now demonstrably *not* equivalent: a roster in the **agent body**
would require a **session restart per discipline added**, which is a far worse per-discipline cost than
tokens and would silently violate the spirit of the N+1 criterion. The architecture's choice of a
separate `discipline-registry.md`, read at runtime, keeps roster edits **live**. That choice was made on
other grounds; this finding retroactively confirms it, and forecloses the body-resident alternative.

**Finding 2 — the ledger's falsifier recipe was defective on arrival, in the unsafe direction.**
The first form was an unanchored literal match (`grep -F '| statistician |'`). Stress-testing against a
synthetic ledger showed it also matches rows belonging to *other* disciplines whose free-text cells
happen to contain the name — returning 3 rows for a discipline that had 2. That inflates the
denominator and therefore **deflates** the computed dismiss rate, biasing the discipline-expansion gate
(§17.4, then stated as "dismiss rate not >60%" — since revised, see §17.11) toward *passing*. A falsifier
that errs toward permitting expansion is worse than no falsifier, because it carries the authority of a
measurement.

Corrected to a column-anchored form (`grep -E '^\|[^|]*\|[^|]*\| *<discipline> *\|'`), verified to
return 2 where the unanchored form returned 3. The rationale is recorded in the ledger itself so the
anchor is not "simplified away" by a future editor who reads it as noise.

There is a fitting symmetry here: the initiative's first measurement instrument shipped with a
measurement-validity defect, caught only by adversarial testing rather than by the happy-path check its
author ran. That is precisely the failure mode the `statistician` identity exists to catch — and an
argument for the discipline being worth having.

**Residual risk carried forward.** The step-1 spike used a **project-scope** probe agent, not the real
**plugin-namespaced** consultant. The pre-mortem anticipated this before the probe ran: step 1 is
necessary, not sufficient, and **step 15's end-to-end smoke test against the real shipped artifacts is
the load-bearing second checkpoint**. Skipping it under time pressure would leave the binding mechanism
unverified in its actual deployed form.

### 17.9 Milestone 2 executed — the consultant exists

Committed 2026-07-30 (`8ab77c0`), 9 files. Steps 4–6 done and independently reviewed.

**Measured against the guards.** Always-loaded delta **+1,300 B / +361 tok** against a predicted
~1,188 B / ~330 tok — a ~9% overshoot, disclosed rather than trimmed to fit; total ≈**23,052 of
25,000**, leaving ~1,948 tok. `plugin.json` ↔ `agents/*.md` parity 17/17. Consultant `description:`
216 tok and discipline-free. Canonical suite **595 passed** against a 573 baseline, no regressions.

**Independent light-review: PASS on all six dimensions**, including the check that mattered most —
whether live assertion #3's glob genuinely covers every always-loaded surface. The reviewer
cross-validated the glob against `rules/_manifest.yaml`'s `always_on` entries rather than merely
reading the code, and found an exact match. Its two over-inclusions (`rules/README.md`, subtree
`CLAUDE.md` files) **err safe rather than silent** — the failure mode that would matter is a glob that
*misses* a file, leaving the zero-cost property unguarded while showing green.

#### Process finding: manifest regeneration is missing from the plan

Editing any always-loaded rule invalidates `rules/_manifest.yaml`, and the pre-commit
`rules-manifest-drift` gate blocks the commit until it is regenerated. **No step in the
implementation plan says to do this**, and Step 4 touched three rule files. It surfaced only because
the gate fired.

**Carry-forward rule: any step touching `rules/**/*.md` must regenerate the rules manifest in the same
commit.** Before running the generator from a worktree, note that it is safe to do so — it resolves
its root from `__file__` and has no `.claude` exclusion, unlike the doc-manifest generator, which
silently drops every entry when run from under `.claude/`. That asymmetry between two sibling
generators is itself worth remembering.

#### Both implementing agents truncated; ground-truth reconciliation resolved it

Step 4's return ended mid-sentence on the manifest registration; Step 5's ended mid-sentence on a test
re-run. Neither carried a terminal marker. Both naive readings fail: trusting the marker-less return
advances on unverified work, while re-running discards ~65 tool-calls of completed effort each.
Re-deriving from ground truth — files on disk, manifest parity, an actual test run — showed **both
steps had in fact completed**; only the reporting was cut. This is the completion-handshake rule
working as designed, and the reason it insists on the codebase rather than the checkboxes.

### 17.10 Milestones 3–6 executed — steps 7–14 complete

Committed 2026-07-30. Wave 1 is complete except Steps 15–16, which require a fresh session (see below).

**What exists on disk and is guarded:** the consultant agent, a registry with its first row
(`statistician`), the `applied-statistics` skill (1,047 lines, validator PASSED, cataloged), the
disposition ledger, the `/consult` entry point, the four-round dialogue protocol with the consult
template, selection Tiers 1–2 wired across four agents, sentinel `BC03`/`P07` extended with golden
fixtures, and 22 fitness tests of which 7 assert live invariants. Canonical suite **595 passed**
throughout; always-loaded surface ≈**23,052 of 25,000**.

#### The pattern worth preserving: four measurement-validity defects, three of which showed green

Every defect this pipeline caught was an **instrument reporting confidently while measuring the wrong
thing** — the class of error a test suite cannot detect because the suite is itself the instrument.

| Defect | Why it was invisible |
|---|---|
| The ledger's unanchored grep counted other disciplines' rows, inflating the denominator and **deflating** the dismiss rate | Biased the expansion gate toward *passing* — a falsifier failing unsafe. Author's own test used input where the name appeared only in its own column |
| A correction to `benchmarking.md` restated inference content the new skill owns, near-verbatim | Both artifacts *agreed*, so nothing looked wrong; agreement had been achieved by duplication rather than cross-reference, and duplicates drift |
| `P07`'s detection, if copied verbatim, would have grepped tokens that never occur in a consult file | Would have flagged **every** consult unconditionally — a gate that fires always looks healthier than one that never fires |
| The extensibility fitness test, had it landed before the spike, would have asserted an invariant protecting an unverified mechanism | Green, continuously, while guarding nothing |

Two were caught by an **independent reviewer of a different agent type** than the author; one by
**adversarial input** rather than happy-path verification; one by **ordering the cheapest falsifiable
check first**. None would have been caught by running the tests again.

Notably, the second was authored by the orchestrator and failed by a subagent's audit — which is the
case independent review exists for, and an argument against letting the party that made a decision also
certify it.

#### Design points confirmed in execution

- **The consultant authors no ADRs.** A late narrowing from the original proposal, and the sharper
  boundary: it gives the agent exactly one job (object), keeps decision authority undivided, and makes
  the distinction from the two existing sub-architects unambiguous — the *duplicate-agent-roles* failure
  mode, addressed structurally rather than by documentation.
- **Only recorded dispositions bind a downstream consumer.** An undispositioned challenge is an
  incomplete consult to flag, not an instruction to follow. Without this, a planner reading raw
  challenges would hand the consultant de-facto decision authority and break the adversarial-only
  boundary exactly where it matters.
- **Nomination is gated by the registry, not by the requirement.** Two agents nominate
  (`attaches-to`); two consume. Conflating the roles would imply four live nomination paths where two
  exist — corrected in the spec after the light review flagged it.
- **A generalization can pay for itself.** Holding `implementation-planner.md` at net +0 lines forced
  generalizing an interface-specific intake item into a class-level one, which simultaneously admitted
  the consult artifact and fixed a **pre-existing blind spot** — the transactions architect's output had
  never been listed since that agent shipped. A line budget produced a better design than an unbounded
  one would have.

#### Remaining: Steps 15–16, and why they were not run early

`agents/discipline-consultant.md` was created *during* the session that built it, and agents load at
session start — so it is not spawnable there. Step 15 (the end-to-end live proof) spawns exactly that
agent, and Step 16 flips `docs/architecture.md` to `Built`, a document carrying a **Built-only
contract**.

Running Step 16 early would document as built a component whose binding mechanism remains unproven in
its deployed form — the shortcut the whole verification discipline exists to prevent, and precisely the
residual risk the pre-mortem named *before* Step 1 ran: the spike used a **project-scope** probe agent,
not the real plugin-namespaced consultant. Step 15 is what closes it.

### 17.11 Steps 15–16 executed — the mechanism worked, and its first act was to break this document

Steps 15 and 16 ran on 2026-07-30 from a fresh session, after a Step 0 install-parity gate confirmed the
shipped plugin (v0.17.0) was `diff`-identical to repo HEAD. Both passed. The mechanism is proven live:
registry resolution, runtime `Skill` binding, Round-0 isolation, decision-naming challenges, convener
disposition, and the ledger's first rows — plus a fail-loud `[BLOCKED]` on an unresolvable discipline
that declined an obvious and available substitution.

**The finding that matters is not that it worked.** The consult's target was this document's own
discipline-expansion gate (§17.4), chosen because it is a genuine stopping rule plus threshold plus
sample-size claim. It raised **six** challenges, all six accepted, and the gate as written did not
survive them. Recorded here because a falsifier that gets quietly rewritten is no longer a falsifier.

| # | Defect in the original gate | Resolution |
|---|---|---|
| CH-01 | The denominator counted **challenges**, but challenges cluster within a consult — same consultant, same draft, and decisively the same **convener**, whose dismissal propensity is a rater effect. At ~3.3 challenges per consult and a plausible intra-cluster correlation of 0.3–0.5, "≥10 challenges spanning ≥3 tasks" had an effective n of **~5–6**, and the binding constraint was really the "≥3 tasks" floor. Three is not a sample | Denominator restated on the independent unit: **distinct consults** |
| CH-02 | At n=10, "pass iff dismiss rate ≤ 0.60" passes a discipline whose *true* rate is 0.70 **35%** of the time, and blocks one sitting exactly at the 0.60 bar **38%** of the time. The Wilson interval for 6/10 is [0.31, 0.83] — passing and failing observations overlap across nearly the whole decision-relevant range | Gate **demoted from binary pass/fail to a reported estimate with a Wilson interval**, dispositioned by a human |
| CH-03 | "≥10 challenges" was a floor, not a fixed evaluation point, so the gate was evaluated under unbounded optional stopping — and the party checking is the party who wants expansion. Simulated inflation was real but bounded (~+13 points of false-pass at a true 0.70) | **Dissolved by the demotion.** With nothing decided automatically, there is no error rate to inflate; the estimate is anytime-readable. Stated explicitly in §17.4 |
| CH-04 | 60% was **asserted, not derived**, and collided with §14 falsifier 1: if 60% was also the delete line, a discipline at 59% simultaneously survived deletion and unlocked expansion — one number doing two opposite jobs with no gap between them | **Dissolved by the demotion** (no threshold remains to derive). §14 falsifier 1 restated as an explicit judgment call on the reported interval |
| CH-05 | The gate was **one-sided**, so a ledger of ten `switch-now` rows and zero dismissals — maximally degenerate — passed cleanly, while §17.4's own prose demanded a "non-degenerate" distribution. A convener who never dismisses supplies no evidence the trigger predicate is *selective* | Two-sided standing condition added: **all three disposition values must have been observed** before the estimate is read as evidence |
| CH-06 | The Tier-3 gate reused the statistic without naming its aggregation unit, permitting one discipline's failure to be masked by another's volume | Tier-3 criterion stated **per discipline, not pooled** |

**Two things the consult endorsed rather than challenged**, worth recording because silence would be
ambiguous: the column-anchored `grep` recipe in `CONSULT_LEDGER.md` (and specifically its *direction* of
bias — an unanchored match inflates the denominator and therefore deflates the rate, biasing toward
passing; "a falsifier must fail safe" was applied correctly), and **instrumentation-before-roster**
(§17.2), which it called "the single most important statistical property of the whole plan" — deciding
the measurement before generating the data is what made all six of these defects free to fix.

**A defect the disposition pattern demonstrated by accident.** The convener dispositioned all six as
`defer-with-rationale` and none as `dismiss-with-rationale`. That set is itself maximally degenerate —
under the *old* one-sided gate it would have read as a 0% dismiss rate and passed cleanly; under the
revised criterion it correctly reads as **not yet informative**, because only one of three disposition
values has been observed and `n` = 1 consult. CH-05 was instantiated by the ledger's own first content
on the day the ledger was created. The dispositions were left as they stood: manufacturing a dismissal
to make the distribution look healthy would corrupt the counter the criterion reads.

**What did not change.** The one-loop-back bound, the disposition vocabulary, the single-writer ledger
rule, the anchored counting recipe's column anchoring, and the Wave-1 roster size are all untouched.
The revision narrows to the *shape of the expansion criterion* and its aggregation unit.

### 17.12 AC15 measured — the cost envelope, with one observation

AC15 states that a convened consultation stays within **≤3× baseline routine / ≤6× high-stakes total
pipeline cost**, bounded by the 2–3 concurrent cap and the one-round bound. Verification found it had
been discharged by **structural argument rather than measurement** — the exact defect this feature's own
consultant raised against the project's expansion gate (CH-04), reproduced inside the project's own
acceptance criteria. It is now measured.

**Observation window.** The 2026-07-30 closeout session, in which every agent spawn reported its token
usage. Cost is measured in subagent tokens, a proxy for spend rather than a currency figure.

| Spawn | Tokens |
|---|---|
| `statistician` consult (`standard` → `opus`) | 101,030 |
| `nonexistent-xyz` probe (blocked at resolution, pre-Round-0) | 64,794 |
| doc-engineer | 114,438 |
| verifier | 222,806 |
| sentinel | 163,288 |
| skill-genesis | 149,751 |

| Quantity | Tokens (raw) | Opus-equivalents (spend) |
|---|---|---|
| Consult spawns | 165,824 | 165,824 |
| Non-consult agents (denominator) | 650,283 | 293,424 |
| **Observed ratio** | 1.255× | **1.565×** against the ≤3× routine envelope |
| Headroom | 2.4× | **1.9×** |
| Break-even — consults before the routine envelope binds | 12.9 | **5.8** |

**PASS on the routine envelope.** But the currency matters, and the first version of this section got it
wrong — corrected 2026-07-30 after a `statistician` consult on this very measurement.

**Why tokens are the wrong unit here.** AC15 bounds *cost*, and the token proxy is biased in the direction
that flatters the verdict: the numerator is entirely tier-H (`opus`), while the denominator is a mix —
verifier `opus`, sentinel and skill-genesis `sonnet`, doc-engineer `haiku`. Weighting each agent by its
tier's relative list price (opus 1.0, sonnet ≈0.2, haiku ≈0.07) shrinks the denominator by more than half
and leaves the numerator untouched. The *excess over 1* — the only part of the ratio that is the consult's
cost — is roughly **2.2× larger** than first reported.

Two claims in the original text inverted under this correction and are withdrawn:

- *"A `standard` consult cost less than every other agent measured."* True in tokens, **false in spend**. In
  opus-equivalents the consult is the **second most expensive agent in the window**, behind only the
  verifier. That sentence was the section's reassurance and it pointed the wrong way.
- The break-even falls from ~12.9 consults to **~5.8**. That is the difference between an envelope that
  effectively cannot bind and one that plausibly can, given a design permitting 2–3 concurrent instances at
  two attaching stages.

**The high-stakes row is withdrawn as an observation.** It was arithmetic on the concurrency cap
(3 × a `standard` consult), presented in the same table with the same bolding under a shared "PASS on both."
It is a plug-in estimate *across treatment arms*: `high-stakes` adds `ultrathink` to the spawn prompt, which
acts directly on the quantity being measured, so three standard consults do not estimate three high-stakes
ones. Recorded separately: price-weighted, three concurrent *standard* consults would run ≈**2.03×** against
the ≤6× bound — informative, but not an observation of the high-stakes case, which remains **unmeasured**.

**The conservative-denominator argument is weaker than stated.** Choosing the closeout session rather than a
full pipeline holds the numerator fixed while shrinking the denominator — but in a genuinely smaller
pipeline both co-scale, and the binding scenario (a small `sonnet`-dominated pipeline with fan-out at both
attaching stages) was never computed. The framing was not wrong in direction; it was asserted rather than
derived.

**Limits, restated.** `n` = 1 consult, `standard` only. One session, one routing configuration. Opus-equivalents
use list-price ratios and ignore cache-read discounts — which would move the number further in the same
direction, since a fresh-context consult caches worse than a warm pipeline agent. The 3× and 6× thresholds
themselves remain **asserted, not derived**. The verdict survives every sensitivity constructed against it;
what changed is what the number licenses and how it is recorded.

**Nothing is accumulating this series.** `.ai-state/observations.jsonl` carries no token or cost fields,
and the ledger's 11-column schema has no cost column. Today's figures exist only because agent
completions surfaced them in-session. Recording an ongoing series is a schema decision on an append-only
file and is deliberately left open rather than resolved here.

### 17.13 The lens-versus-consultant criterion — and why performance is a lens

Writing the escalation relationship `dec-303` required before `performance-engineer` could ship exposed a
prior question the design had never answered: **what makes a discipline worth a consultant at all?**

Two facts settled it. First, a lens and a consultant deliver **identical knowledge** — Wave A established
this when it eliminated the skills-into-existing-agents option, because a skill read by the architect *is
the architect thinking with better knowledge*, with no second party to disagree. The consultant's entire
marginal contribution is **standing to object**. Second, the specific knowledge was already present:
`performance-architecture/references/capacity-planning.md` already contains Little's Law, back-of-envelope
estimation, and cost-performance modelling — exactly what §12.2 reserved for `queueing-modeler` and §13
routed to `performance-engineer`.

That inverts the usual framing. **Gating knowledge that improves every decision does not add rigor; it
subtracts availability.**

> **A discipline earns a consultant only when its errors are silent.** Otherwise the knowledge belongs in
> the owning artifact of a lens, delivered free and unconditionally.

The discriminator is whether the error surfaces through ordinary feedback. **Performance errors surface** —
benchmarks, profilers, latency graphs, cost bills falsify a wrong intuition, usually before it becomes
load-bearing. **Statistical errors do not** — an inadequate sample produces a number that looks correct
indefinitely, which is precisely how the first live consult found six defects in a gate its author believed
sound.

Three consequences, all applied: `performance-engineer` and `queueing-modeler` are removed from the roster;
the Performance lens is strengthened instead, gaining the agent-era dimension it did not carry (token budget
as a capacity constraint, context-window efficiency, spawn cost and fan-out, pipeline wall-clock, and the
measurement discipline each needs); and `evidence-appraiser` becomes discipline #2, with a boundary against
`statistician` written into both rows — *the statistician asks whether our analysis of our data is sound;
the appraiser asks whether their claim about their data licenses what we are doing with it.*

**The criterion's weakness is recorded rather than hidden.** "Would this error have surfaced?" is a
counterfactual, and counterfactuals are where motivated reasoning lives. A blunter rule — no consultant for
any domain that already owns a lens — is harder to game and reaches the same verdict here; it was rejected
only because it would exclude a security consultant on structural grounds rather than on merit. The ADR's
`dissent:` field carries this in full, along with the observation that a criterion which happens to justify
the one discipline already shipped and exclude the one a user proposed has the shape of a conclusion looking
for a rule.

**Discipline #2 shipped ahead of its own evidence gate**, knowingly. The gate reads *not yet informative*
(one consult, two of three disposition values). Because that gate was deliberately demoted from an automatic
threshold to an estimate a human adjudicates, a human choosing to ship is the mechanism working rather than
a bypass — but it is the risk the prior decision's reversal trigger named, so it is recorded here and in the
ADR rather than passed over.

### 17.14 AC13 exercised — two disciplines, concurrently, and what they found

`AC13` (two *different* disciplines running at once, each writing its own fragment, with no shared-file
write and no cross-read during round 0) was untestable through Wave 1 at a one-discipline roster. With
`evidence-appraiser` merged (§17.13) it was exercised on 2026-07-30 **against the working tree, not a
released plugin** — see the §12.2 correction: discipline #2 is on `main` but absent from `v0.18.0`, so
this exercise proves the mechanism, not the shipped artefact: a `statistician` and an
`evidence-appraiser` were spawned concurrently against **deliberately different targets**, chosen so the
run would also test whether the boundary written into their registry rows actually holds.

**AC13 verdict: PASS**, in the strong sense.

| Assertion | Observed |
|---|---|
| Separate fragment per discipline | `CONSULT_statistician.md` and `CONSULT_evidence-appraiser.md` |
| No cross-read during round 0 | Both `## Sources Read` sections declare the sibling fragment and `SYSTEMS_PLAN.md` unread |
| No shared-file write | Both appended to one `PROGRESS.md`; the four entries **interleave** (appraiser R0, statistician R0, statistician R1, appraiser R1) with no corruption |
| Single-writer ledger honoured | Neither touched `CONSULT_LEDGER.md` |

**The boundary held with zero overlap** — the stronger result. The statistician challenged the token
proxy, a plug-in estimate across treatment arms, denominator co-scaling, `n`=1 tail bounds, and underived
thresholds: all inferences on *our own* numbers. The appraiser challenged missing attribution, a skipped
verification convention, and a construct mismatch: all properties of an *imported* claim. Not one
challenge from either would have belonged in the other's fragment. The registry's one-line split —
*the statistician asks whether our analysis of our data is sound; the appraiser asks whether their claim
about their data licenses what we are doing with it* — is discriminating in practice, not just on paper.

**One degradation, declared rather than hidden.** The appraiser's `Skill`-tool binding **failed**
(`Unknown skill: i-am:evidence-appraisal`) because the skill was authored minutes earlier and the
installed plugin cache predates it. The consultant did not improvise: it reported the failure, loaded the
canonical in-repo source by direct read, and left the void/no-void call to the convener. This is the same
self-hosting staleness that halted the Wave-1 smoke test, and it exposes a real limit on the
"two files to add a discipline" claim — **two files are necessary but not sufficient until a release
ships them**, because the runtime binding resolves against the installed plugin, not the working tree. The
degradation does not void AC13, whose assertions concern the concurrency contract rather than the binding;
it is recorded as an AC2-adjacent caveat.

**Both consults found real defects, and both were dispositioned** — the statistician's correction to the
AC15 measurement is applied in §17.12; the appraiser's attribution withdrawal is applied in §15.5. Neither
changed a design decision. Both changed what this dossier is entitled to claim.

---

## 18. Citations

- [Reasoning Models Generate Societies of Thought](https://arxiv.org/html/2601.10825v1) — Kim, Lai, Scherrer, Agüera y Arcas, Evans (arXiv:2601.10825v1, Jan 2026)
- [When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of LLMs](https://aclanthology.org/2024.findings-emnlp.888/) — Zheng et al., EMNLP Findings 2024
- [Better Zero-Shot Reasoning with Role-Play Prompting](https://aclanthology.org/2024.naacl-long.228/) — Kong et al., NAACL 2024
- [Unleashing the Emergent Cognitive Synergy in Large Language Models: Multi-Persona Self-Collaboration](https://aclanthology.org/2024.naacl-long.15/) — Wang et al., NAACL 2024
- [Persona is a Double-edged Sword](https://arxiv.org/html/2408.08631v1) — arXiv:2408.08631, 2024
- [Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657) — Cemri et al., NeurIPS 2025 Datasets & Benchmarks
- [MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework](https://arxiv.org/pdf/2308.00352)
- [SPOQ: Specialist Orchestrated Queuing for Multi-Agent Software Engineering](https://arxiv.org/abs/2606.03115) — Carbowitz & Kumar, June 2026
- [Rigorous Benchmarking in Reasonable Time](https://dl.acm.org/doi/10.1145/2491894.2464160) — Kalibera & Jones, ISMM 2013
- [Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?](https://aclanthology.org/2024.acl-long.331/) — Wang, Wang, Su, Tong, Song, ACL 2024 (arXiv:2402.18272)
- [Expert Personas Improve LLM Alignment but Damage Accuracy (PRISM)](https://arxiv.org/abs/2603.18507) — Hu, Rostami, Thomason, Mar 2026
