---
title: Praxion as a Personal Software Factory — Landscape, SDLC Coverage, Integration Seams, and the Sidecar Placement
type: independent-analysis
diataxis: explanation
audience: architect / maintainer
status: spike (analysis + design; no implementation)
date: 2026-09-02
head_sha_analyzed: 1b49cc5a
author: Francisco Perez-Sorrosal (analysis run as a five-lens Spike with Claude Code; §2.7 added from a sixth 2026-factory research pass)
verification_legend:
  VERIFIED: primary source fetched, file:line read, or reproduced in a scratchpad experiment
  SINGLE-SOURCE: one source, not independently confirmed
  ASSUMPTION: stated belief that shapes a recommendation; falsifier named where possible
---

# Praxion as a Personal Software Factory

> **Scope.** A Spike, not an implementation. Four questions, answered in order: (1) where Praxion stands versus state-of-the-art agentic SDLC scaffolds and "software factory" products; (2) which SDLC and software-factory capabilities it lacks, and why; (3) which integrations would be seamless from the management side of a managed project; (4) how one operator can use the full factory on a team repository that must stay Praxion-agnostic. Part IV is written to be decision-grade: a `systems-architect` can render ADR fragments from it and an `implementation-planner` can decompose it.

## 0. TL;DR

- **Position against the 2026 definition.** The 2026 agentic software factory (Factory 2.0, OpenAI's harness, Thoughtworks Radar vol. 34) is an *interconnected, agent-native, end-to-end, self-observing* system — not the 2004 product line. Measured against an 18-feature model of it (§2.7), Praxion — used by one operator — scores 7 first-class, 8 partial, 1 absent. It *exceeds* what the 2026 products give an individual on five features (feedback flywheel, decision-governance substrate, process calibration, cross-model review, scaffold self-audit) and trails on the five with the highest personal leverage (continuous/async operation, spend metering, tracker intake, delivery metrics, a non-invasive readiness wedge). It remains the only surveyed system that is a factory in the 2004 Greenfield & Short sense too — a generator that instantiates harnesses — which is exactly the "engineers build the factories that build the software" thesis, arrived at independently and shipped with no vendor.
- **Behind.** Praxion is single-user by construction, one generation behind on async / continuous-AI agents (its own substrate, Claude Code Routines, is unexploited), measures its process but not its delivery outcomes (no DORA keys), and under-claims its portability even though its skills layer already conforms to the Agent Skills open standard.
- **Coverage.** Against a 37-cell SDLC + factory + team + DORA model: 15 cells Full, 14 Partial, 5 Absent. The absents are incident/postmortem, WIP limits and flow, human onboarding of a bystander teammate, solo operation on a shared repo, and DORA four keys. Two precept/practice divergences stand out: DORA is taught in a skill and never computed; supply-chain attestation is recommended in a skill and never applied to Praxion's own release.
- **Seams.** The cheapest, highest-leverage integrations are the ones already three-quarters built: Linear or Jira via their GA remote MCP servers (a decision-grade Linear design exists since June), the hub reusable-workflow CI pattern (fleet-distributable today), and the Agent Skills conformance that makes 64 skills consumable unchanged by Codex, Cursor, Gemini CLI, Copilot, Kiro, OpenCode and Amp.
- **The team-repo problem is solvable without weakening the factory.** A *placement* axis on onboarding (`in-repo` today, `sidecar` new) keeps the `.ai-state/` path contract intact on disk and moves only its git ownership to a per-operator repository projected in by an excluded symlink. Every mechanic was reproduced in a scratchpad. Two bounded code blockers exist (the dashboard's path-containment guard and the worktree write guard) plus one prerequisite that hurts every team-repo onboarding today: Praxion's git hooks neither honour `core.hooksPath` nor chain with an existing hook manager.
- **Registered objection, relayed.** Thoughtworks Radar vol. 34 places spec-driven development at *Assess* and invokes the bitter lesson against large handcrafted rule sets. Praxion is one of the largest such sets surveyed. The counter-arguments are real (tier calibration, capped progressive disclosure, the harness-engineering thesis), but Praxion has no measurement that separates "the scaffold helps" from METR's "19% slower". Delivery metrics are the falsifier, and this analysis ranks them accordingly.

## 1. Method

Five research lenses ran in isolation (no lens read another's output) and were reconciled only here: external landscape (web, primary sources, live GitHub API reads on 2026-09-02), managed-project footprint (code-verified inventory of what onboarding writes), SDLC and software-factory coverage (capability model built before reading the repo), integration seams and portability, and Claude Code configuration facts (official docs). Seven git mechanics were reproduced in a scratchpad before being relied upon. Twelve peer-repository renames and status flags reported by the landscape lens were re-verified by direct GitHub API calls; all twelve matched. Claims carry the legend above; vendor benchmarks are quarantined as marketing.

## 2. Praxion versus the field

### 2.1 Two definitions of "software factory," and which one 2026 uses

There are two definitions of the noun, and the comparison depends entirely on which one is in play. The primary comparison in this document (§2.7) is against the **2026** definition; the 2004 one is retained only for the translation table (§2.7.1), which shows what carried forward and what did not.

- **The 2004 definition** (Greenfield & Short, *Software Factories*): a **product line** with explicit assets — a factory schema, a factory template, DSLs, patterns, tooling, and a variability model — that produce a family of similar applications *semi-automatically by deterministic generation from a formal model*. Praxion matches this sense: `.ai-state/` artifact contracts are the schema, skills/rules/agents/commands are the DSL layer, and `onboard-project`, canonical blocks, `sync_canonical_blocks.py` and `/upgrade-project` are the generator with drift detection. VERIFIED. It is the only surveyed system that does — but the referent has *inverted*: the family it produces is managed repositories with a shared agent environment, not applications with shared features.
- **The 2026 definition** (Factory 2.0, Sept 2026): "an interconnected, agent-native, end-to-end system" that "must improve over time by observing itself", a continuous feedback loop from signals (bugs, conversations, feedback, requirements) through work that is "built, tested, reviewed, secured, shipped, and monitored". Three things are load-bearing and absent from 2004: **agent-native** (the executing unit is a model-driven agent, not a generator), **end-to-end** (intake and monitoring are *inside* the factory boundary), and **self-observing** (the factory improves *itself*). OpenAI's companion framing names the engineered artifact — **the harness**, "the execution system that sits between a model and a task" — and Thoughtworks Radar vol. 34 supplies the vendor-neutral vocabulary (and, unusually, a *caution* list that lands on Praxion's own choices).

The framing that survives both: peers are harnesses for one project; Praxion is a factory that *builds* harnesses. That is under-claimed in Praxion's own positioning and is the right lens for the matrix below and the feature model in §2.7.

### 2.2 Comparison matrix (condensed)

Legend: ● first-class · ◐ partial · ○ absent. Praxion cells are marked from repo evidence; peer cells from primary sources fetched during the survey.

| Dimension | Praxion | Spec Kit | OpenSpec | BMAD | Superpowers | Conductor | Kiro | Factory.ai | GitHub Agent HQ | Claude Code |
|---|---|---|---|---|---|---|---|---|---|---|
| Specification model, REQ traceability | ● | ● | ● | ● | ◐ | ● | ● | ◐ | ◐ | ○ |
| Planning artifacts, decomposition | ● | ● | ◐ | ● | ● | ● | ● | ◐ | ◐ | ◐ |
| Multi-agent role pipeline | ● | ○ | ○ | ● | ● | ◐ | ○ | ● | ● | ● |
| Durable project state in repo | ● | ◐ | ◐ | ● | ◐ | ● | ● | ● | ◐ | ◐ |
| Decision governance (ADR lifecycle) | ● | ◐ | ○ | ◐ | ○ | ◐ | ○ | ○ | ○ | ○ |
| Verification / review gates | ● | ◐ | ◐ | ● | ● | ◐ | ◐ | ◐ | ● | ◐ |
| Learning loop to reusable artifacts | ● | ○ | ○ | ◐ | ◐ | ○ | ○ | ○ | ○ | ◐ |
| Self-audit of the scaffold | ● | ○ | ○ | ○ | ○ | ○ | ○ | ● (of the repo) | ○ | ○ |
| Architecture governance, fitness | ● | ○ | ○ | ◐ | ○ | ◐ | ○ | ○ | ○ | ○ |
| Async / continuous AI outside sessions | ◐ | ○ | ○ | ◐ | ○ | ○ | ◐ | ● | ● | ● |
| Team / multi-user model | ○ | ◐ | ◐ | ◐ | ◐ | ● | ● | ● | ● | ● |
| Assistant portability | ◐ | ● | ● | ● | ● | ● | ◐ | ● | ◐ | n/a |
| Metrics (DORA, calibration, cost) | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ● | ◐ | ◐ |
| Process calibration to task size | ● | ○ | ◐ | ● | ◐ | ○ | ○ | ◐ | ◐ | ◐ |

Live repository signals on 2026-09-02, VERIFIED by GitHub API: Superpowers 280,552 stars (larger than Claude Code's own repo; 14 harnesses), Spec Kit 132,956, OpenHands 85,917, ruflo 70,176, OpenSpec 66,976, goose 53,818, BMAD 52,582. Roo Code archived 2026-05-15 with no successor found; Plandex has had no push since 2025-10-03.

### 2.3 What the field converged on (≥3 independent adopters each)

1. The agent's durable context is a committed, human-readable repo artifact (Conductor, Kiro, Agent OS, Spec Kit, OpenSpec, AGENTS.md, Praxion). Praxion sits at the maximal end of a settled question. VERIFIED.
2. Progressive disclosure as the context-economy mechanism; the Agent Skills standard defines it normatively and 47 clients implement it. Praxion's metadata/body/references structure predates the standard. VERIFIED.
3. Worktree-per-agent isolation, now a shipped platform default in at least five products. VERIFIED.
4. Specify → plan → implement with human checkpoints; near-universal. The differentiator is what persists afterwards and whether ceremony scales down. VERIFIED.
5. Async agents triggered by schedule, webhook or repo event: seven independent implementations in twelve months, the fastest-moving dimension. VERIFIED.
6. An independent reviewer tier for agent-authored diffs; Praxion's *cross-model* gate is the aggressive end. VERIFIED.
7. Skills as the portable unit of capability; effectively a resolved standards question. VERIFIED.
8. Right-sizing process to the change; a convergence toward something Praxion already built. VERIFIED.
9. Feedforward/feedback control framing of the harness (Fowler, Thoughtworks, OpenAI's harness-engineering post): the environment, not the prompt, is the engineering artifact. VERIFIED.
10. Git-native, agent-queryable task state (Beads, Backlog.md, Vibe Kanban); emerging. SINGLE-SOURCE aggregated.

### 2.4 Where Praxion is ahead

- **A1 Decision governance.** 356 finalized ADRs with draft-to-finalize lifecycle, collision-safe fragments, bounded cross-reference rewrite, four relation types (supersede, re-affirm, retire, partial-supersede), generated index and retrieval-first discovery. No peer models decision supersession over time. With Thoughtworks vol. 34 naming *cognitive debt* as the headline risk of AI-accelerated codebases, this is arguably the most valuable unclaimed capability in the landscape. VERIFIED.
- **A2 Architecture governance as an enforced triangle** (LikeC4 model, code↔DSL↔ADR validator, fitness-function templates, design-target versus code-verified doc split). Fowler ranks the fitness harness as the middle maturity tier that the field is still working out. VERIFIED.
- **A3 Self-audit of the scaffold** (sentinel, `/eval-praxion`, measured token budget, gate-liveness checks that verify other gates). Zero peers audit their own scaffold; Factory audits the target repo instead. VERIFIED.
- **A4 Instrumented process calibration** — the only project that writes an observed row per task on ceremony weight, the correct instrument against METR's 43-point self-assessment error. VERIFIED.
- **A5 Automated learning loop** (`skill-genesis` harvest plus human disposition). Compound Engineering names the loop; Praxion ships it. VERIFIED.
- **A6 Factory, not harness** (see 2.1). VERIFIED.
- **A7 Cross-model review gate** with inverted privilege, failing open. Not observed in any peer. VERIFIED.
- Also unusual for the category (from the coverage lens): jidoka done properly (automation that declines is the tested path), truncation-aware ground-truth reconciliation, sealed-prior adversarial consults with per-challenge disposition, refreshable shipped assets with drift detection. VERIFIED.

### 2.5 Where Praxion is behind or absent

- **B1 Team / multi-user model — absent, and load-bearing.** Adopting Praxion commits metadata into a shared repo. Every product peer and Conductor among OSS peers is team-native. DORA's seventh capability, *quality internal platforms*, is the mechanism that turns individual AI productivity into organisational impact; Praxion stops at the individual. Part IV addresses this without adopting the field's answer (repo-shared scaffolding), because the constraint here is the opposite. VERIFIED.
- **B2 Async / continuous AI — one generation behind.** The self-healing CI loop is sophisticated for a repo-local system, but the pipeline assumes an interactive orchestrator. Claude Code Routines is Praxion's own substrate; the gap is unexploited platform capability. VERIFIED.
- **B3 Readiness — corrected.** The landscape lens flagged "no scored readiness model" as an assumption; it is refuted. `/project-metrics` already computes Factory's 8-pillar × 5-level score plus a separate Pillar 9 manageability sub-score, rendered on the dashboard. What survives is the *wedge*: a readiness run is non-invasive, and a team repo that will not accept scaffolding will accept a diagnosis. Today the report is persisted under `.ai-state/`, which presupposes onboarding. VERIFIED.
- **B4 Portability is a stated non-goal that became a liability** — mitigated by the fact that the skills layer is already standard-conformant (Part III). VERIFIED.
- **B5 No DORA metrics.** Praxion measures its own process, not delivery outcomes; it cannot answer "did the pipeline make delivery better?". VERIFIED.
- **B6 No distribution presence** (marketplace, installer). Distribution decides which conventions the ecosystem converges on. VERIFIED.
- **B7 Spec-first with archival, not spec-anchored.** Specs are date-stamped archives, not living contracts. OpenSpec's delta specs and Kiro's requirement↔task traceability are ahead. Climbing to spec-as-source is not recommended (Tessl's stalled engine, Böckeler's model-driven-development warning). VERIFIED.
- **B8 Cheap missing primitives:** standards discovery from an existing codebase (Agent OS), EARS requirement syntax (Kiro), a git-native task graph (Beads), sandboxed agent jobs with validated safe-outputs (gh-aw). SINGLE-SOURCE each.

### 2.6 Registered objection: the bitter lesson

Thoughtworks Radar vol. 34 suggests that handcrafting detailed rules for AI ultimately does not scale, and Böckeler's "false sense of control" finding points the same way. Praxion carries 25 rules, 64 skills, 19 agents and a 25k-token always-loaded budget. Three considerations cut the other way: tier calibration exists precisely to avoid the heavy path by default (the critique lands hardest on one-workflow tools such as Kiro and Spec Kit); progressive disclosure keeps the resident surface measured and capped; and DORA's capability model and OpenAI's harness-engineering post both argue the environment is where the leverage is. What is missing is evidence, not argument. The divergence between METR's 19%-slower RCT (experts, mature repos, solo workflow) and OpenAI's million-line zero-human-lines claim (purpose-built harness, greenfield) is not averageable; the reconciling variable is harness quality, which is Praxion's thesis and remains a hypothesis. Delivery metrics (§5, P2) are the falsifier.

The evidence has one further sting worth stating plainly, because it bears directly on *personal* use. METR's 2025 RCT is still the only randomized trial; its 2026 successor was redesigned and never produced a clean replication, and the circulated "1.4–2× faster" figure traces to a 2026 **self-report survey** — the exact measure the RCT showed wrong by 39 points in the same population. And DORA's own mechanism for converting individual AI productivity into organizational impact is *quality internal platforms* — an organizational construct. A personal factory is, by DORA's definition, the "localized pocket of productivity… lost in downstream chaos" the DORA lead warns about. This is the strongest independent argument that a personal factory has a ceiling no amount of harness quality removes, and it makes §2.7's tracker-intake and delivery-metric gaps (the operator's only bridges to the wider system) matter more, not less.

### 2.7 Praxion against the 2026 agentic software factory (personal-use lens)

The 2026 comparison is done against an 18-feature model built from three primary anchors (Factory 2.0, OpenAI's harness posts, Thoughtworks Radar vol. 34), each feature admitted only with **≥2 independent exhibitors**. The scores below weigh each feature by leverage *to one operator* running Praxion on their own and their employer's repositories — deliberately not the same as leverage to an org (org dashboards and seat rollups score low; autonomy, private memory, cost control, portability and readiness score high).

| # | 2026 feature | Praxion | Solo weight | The personal-use read |
|---|---|---|---|---|
| F1 | Signal-to-work intake from a tracker | ◐ | H | Loses: work on an employer repo *originates* in Jira/Linear; Praxion starts one step downstream, so every task begins with hand-transcription and its artifacts are invisible to the tracker colleagues read |
| F2 | Fleet mission control across repos | ◐ | M–H | Split: the org roll-up is worthless solo; the multi-repo session view is worth *more* solo (no teammate holds the other repos). Praxion has the hard half (per-repo depth), lacks the cheap half (roll-up); `/fleet-status` proposed, not built |
| F3 | Spec → plan → implement + checkpoints | ● | H | Exceeds: no product ships a *tier* system; Kiro and Spec Kit impose one ceremony weight. Solo, the ability to *skip* ceremony beats the ceremony — an org amortizes fixed overhead across ten people, one operator cannot |
| F4 | Committed structured agent context | ● | H | Exceeds: Praxion independently reached OpenAI's monolith→pointer-index lesson and went further (measured 25k budget, drift check, doc manifest). Caveat: Radar's *Agent instruction bloat* caution lands on 62 skills × 25 rules |
| F5 | Coordinator + role-specialized fleet | ● | H | Exceeds for an individual: Factory's droids are a hosted product, Claude Code agent teams a flagged research preview; Praxion's 19-agent pipeline is shipped, versioned, owned |
| F6 | Parallel agents + workspace isolation | ◐ | H | Loses on the axis that matters most solo: git-level isolation is strong, but every agent runs on the operator's laptop against one subscription — Cursor/Routines run with the laptop closed. Wall-clock *is* the solo constraint |
| F7 | Sandbox + permission/network boundary | ◐ | M–H | Loses, and it is the employer-facing loss: gh-aw's compile-time-validated write channel and Claude cloud's `403 host_not_allowed` are what a security-conscious employer asks for; Praxion's guards are behavioural (hooks), not architectural (sandbox) |
| F8 | The harness is the engineered artifact | ● | H | Exceeds: the strongest single alignment with the 2026 definition found — a factory that builds harnesses, Factory's own thesis, arrived at independently and shipped without a vendor |
| F9 | Standing agentic review tier | ● | H | Exceeds: no product gives an individual a *cross-vendor* review gate; GitHub's is Copilot, CodeRabbit single-vendor. With AI diffs carrying ~1.7× findings (§4-evidence), the solo operator with no colleague reviewing needs exactly this |
| F10 | Machine-checkable feedback sensors | ● | H | Exceeds: ~30 `check_*` gates, gate-liveness (gates that verify gates), sentinel, `/eval-praxion`. Gap: **mutation testing** (Radar Trial), the one sensor specifically for validating agent-written tests, is absent |
| F11 | Graduated autonomy + policy/audit/identity | ◐ | M solo / H employer | Mostly irrelevant solo; decisive on an employer repo: an employer asking "what did the agent do, under whose authority" gets a better answer from Claude Code's blunt "it appears as you" + admin kill-switch than from a JSONL log with no duration/cost/model |
| F12 | Spend metering and run ceilings | ◐ | H | Loses, and it undercuts Praxion's *own* best feature: the 5-tier calibrator is uninstrumented on cost — `observations.jsonl` carries no `duration_ms`/`tokens`/`model`, so the operator cannot answer "is Standard worth 4× Lightweight?". Cheapest of the five to close |
| F13 | Agent-queryable knowledge substrate | ●/◐ | H | Exceeds on decision knowledge (356 ADRs, four-relation lifecycle, retrieval-first `query_adrs.py`); loses on personal memory — `dec-225` removed the cross-session backend, so the one memory scope a solo operator actually spans (employer + personal repos) is empty |
| F14 | Portable packaging + model independence | ◐ | M–H | Under-claimed asset and the employer-portability insurance: the skills layer is already Agent Skills-conformant and travels if an employer mandates Copilot/Cursor; the agent/rule/command layers do not. The gap is distribution, not substance |
| F15 | Continuous AI (schedule/webhook/event) | ◐ | **HIGHEST** | The largest gap by personal leverage — **zero `schedule:` triggers across all 15 workflows** (VERIFIED); the self-healing loop is Continuous AI on the failure path only. One person's ceiling is wall-clock, and Routines (schedule/API/GitHub triggers, cloud execution) is *already paid for* on the operator's subscription. Seven products ship it |
| F16 | Feedback flywheel (factory improves itself) | ● | H | Exceeds, decisively: Radar has it at *Assess* (the industry is still evaluating); Praxion shipped it (harvest → human disposition → reusable skill). Solo, it substitutes for the team retrospective that does not exist |
| F17 | Agent-readiness scoring of the environment | ● | H | Ahead on *having* it at zero marginal cost; behind on the property that matters here — Factory's report is explicitly *non-invasive*, Praxion's persists under `.ai-state/` (presupposes onboarding). On a repo that won't accept scaffolding, a *diagnosis* is the only accepted first contact. Two live defects — see below |
| F18 | Delivery-outcome measurement over throughput | ○ | H | Absent, and the falsifier for the whole thesis: DORA metrics at *Adopt*, throughput-as-productivity at *Caution*; Praxion computes neither. Solo this is doubly acute — no colleague corrects a self-assessment error METR measured at 39 points |

**Five where personal leverage is highest and Praxion is behind** (this is the roadmap's spine): F15 continuous AI, F12 spend metering, F1 tracker intake, F18 delivery metrics, and the combined F17/F14 wedge (a non-invasive readiness run + a claimed portability story — one gap wearing two hats: arriving at a repo you don't own and delivering value without writing to it). **Five where Praxion already exceeds what 2026 products give an individual:** F16 feedback flywheel, F13 decision governance, F3 process calibration, F9 cross-model review, F10 + scaffold self-audit. The through-line: Praxion is strongest exactly where a solo operator has no team to substitute for the capability, and weakest exactly where the 2026 products lean on hosted infrastructure (cloud execution, org policy planes, tracker connectors) a personal user cannot build but can, in two of five cases, simply *turn on* (Routines, MCP).

Two 2026-specific defects surfaced that were not in the earlier landscape pass and feed the roadmap:

- **Readiness rubric drift.** Factory's published Agent Readiness rubric has moved (a Task-Discovery dimension and a reworked ninth pillar) while Praxion still ships `code_quality` and claims verbatim external comparability (`scripts/project_metrics/collectors/readiness/criteria.py` vs the "adopted verbatim" claim in `docs/agent-readiness.md`). The comparability claim is now stale. SINGLE-SOURCE (Factory docs, 2026-09-02).
- **Readiness is invasive where Factory's is non-invasive.** Praxion's readiness report writes under `.ai-state/`, which presupposes onboarding — contradicting the very wedge (a diagnosis a Praxion-agnostic team will accept) that the readiness capability is supposed to provide. This is the same insight as gap B3 in §2.5, now sharpened into a concrete P3 requirement: readiness must have a no-write mode.

#### 2.7.1 What translates from 2004 to 2026, and what does not

| 2004 element | 2026 upgrade | Portable? |
|---|---|---|
| Software product line (a family of similar applications) | A fleet of repositories under one harness — the family is *managed repos with a shared agent environment*, not applications with shared features | Portable, referent inverted |
| Factory schema (structured asset description) | The context-artifact contract — `.ai-state/` schemas, `AGENTS.md`/`CLAUDE.md` layouts, artifact inventories. Formal metamodel → filesystem-and-markdown convention a human *and* a model can read | Portable and **strengthened** — the schema became the product |
| Factory template (instantiable implementation) | The installable, versioned, drift-detected bundle — plugins + marketplaces, canonical blocks + `sync_canonical_blocks.py --check` + `/upgrade-project` | Portable and strengthened — re-synced, not instantiated once |
| DSLs driving deterministic model-driven generation | **Largely NOT portable.** Deterministic emission from a formal DSL → model-in-the-loop generation from natural-language specs. The DSL's *role* (bounding the generator) survives as skills and rules — but they *bias* a stochastic generator, they do not *emit* code | **Not portable in its generative form.** Falsifier: a shipped 2026 product whose primary code path is deterministic emission from a formal model — none found (Tessl's engine stalled). The surviving exception is DSL-for-*description* (LikeC4/AaC), used for validation, not generation |
| Patterns / reusable assets | Skills as the standardized unit under the Agent Skills open standard (directory + `SKILL.md` + progressive disclosure) | Portable and **decisively upgraded** — the cleanest 1:1 translation: prose-for-a-human → machine-loadable, token-metered, cross-vendor |
| Variability / feature model | Per-repo onboarding modes + capability profiles + readiness levels | Portable in *function*, not *form*: 2004 was closed-world (enumerate variation points); 2026 is open-world (onboarding *detects* the stack) |
| Schema completeness (complete enough to generate from) | — | **NOT portable.** 2026 assumes context is permanently partial; effort moves from *completing* the schema to *retrieving and disclosing* the right slice. OpenAI's monolith→pointer-index lesson is this in miniature |
| The factory as a vendor-delivered tooling suite | — | **NOT portable as an economic form.** A 2026 factory is assembled from open standards (`AGENTS.md`, `SKILL.md`, MCP) plus a model subscription; the vendor sells the *runtime and control plane*, not the factory. Praxion — 64 skills, 19 agents, no vendor — is direct evidence |

One-line summary: the schema survived and *became the product*; the DSL survived only as instruction, not as generator; the variability model went open-world; and the factory boundary widened to swallow intake and monitoring. Praxion sits on the portable side of every row except the two marked NOT portable — and it is not on the wrong side of those, it simply does not attempt deterministic generation, which is the correct 2026 stance.

## 3. SDLC and software-factory coverage

### 3.1 Grades

A 37-cell model (16 SDLC phases, 10 factory concerns, 5 team dimensions, 6 DORA capabilities) was built before reading the repo and then graded code-verified. Result: 15 Full, 14 Partial, 5 Absent.

| Absent cell | Classification | Evidence |
|---|---|---|
| Incident and postmortem loop | design-shape consequence, never decided | `skill-genesis` harvests `LEARNINGS.md`; nothing after merge feeds the loop |
| WIP limits and flow | unrecognised | no duration field anywhere; `observations.jsonl` (5,926 rows) carries identity and causality only |
| Human onboarding of a bystander teammate | neglect | every onboarding artifact is agent-facing |
| Solo operation on a shared repo | unexamined premise | commit-ness of `.ai-state/` is the substrate for `dec-NNN` stability |
| DORA four keys | deliberate boundary, undocumented | `scripts/project_metrics/schema.py:82-97` has SLOC, complexity, churn, truck factor, coverage; no deploy frequency, lead time, CFR or MTTR |

### 3.2 Top gaps by leverage for a personal factory on team repos

| # | Gap | Why missing | Smallest idiomatic fix (component family) |
|---|---|---|---|
| 1 | Private per-user placement of `.ai-state/` | unexamined premise; `dec-221` moved only disposable run artifacts out of tree | Part IV — placement axis on onboarding (skill + scripts + two guard edits) |
| 2 | No work-item ↔ REQ/ADR/PR binding beyond ephemeral `traceability.yml` | deliberate git-only substrate; the Linear analysis stalled at analysis | `work_item:` field in `TASK_BRIEF.md` and ADR frontmatter, propagated with the task slug (canonical block + schema); tracker MCP later |
| 3 | No per-task cost/duration telemetry | recent and accidental; `CONSULT_COSTS.md` is the only meter | add `duration_ms`, `model`, `tokens` to the `SubagentStop`/`Stop` rows in `hooks/capture_session.py` (hook, additive) |
| 4 | No human-facing artifact for a bystander teammate | audience blind spot | canonical block `what-is-ai-state.md` for `CONTRIBUTING.md` or `.ai-state/README.md` |
| 5 | No incident → learning-loop edge | loop grew from the inside out | `/postmortem` command reusing researcher/verifier and ledger writers |
| 6 | Ownership computed but never bound to routing (no CODEOWNERS) | solved for agents, never lifted to humans | script generating a CODEOWNERS draft from the existing `ownership` block; verifier names the owning human |
| 7 | DORA taught, never measured | metrics scoped to code health | offline `delivery_collector.py` computing lead time and deploy frequency from tags and merge commits; CFR/MTTR null with reason |
| 8 | SBOM/provenance recommended, never applied to Praxion's own release | skill library outran the dogfood | `actions/attest-build-provenance` in `release.yml` and as an opt-in `ci` sub-step |
| 9 | No fleet view across managed repos | per-project dashboard by construction; fleet-install pushes but nothing pulls | `/fleet-status` command reading each repo's newest metrics, sentinel log tail and open `td-` count |
| 10 | Andon has no persistent signal; no team-facing AI policy | state legible only inside the session | `AI_POLICY.md` canonical block; `.ai-state/LINE_STATUS.md` written on `[BLOCKED]`/verifier FAIL |

### 3.3 Precept/practice divergences found

- DORA taught (`skills/cicd/SKILL.md:236`) and offered as an audit lens, computed nowhere. VERIFIED.
- Supply-chain attestation recommended in the same skill; `release.yml` has no attestation step. VERIFIED.
- `rules/swe/vcs/pr-conventions.md:65` frames multi-user as future work while fragment-ADR author identity, semantic merge drivers and worktree isolation already ship; the three proposals it names do not exist. Framing is stale in both directions. VERIFIED.
- `docs/README.md` omits `multi-session.md`, `rework-dispatch.md`, `obsidian-integration.md` and `agent-readiness.md` (fixed alongside this document). VERIFIED.
- The idea ledger was last updated 2026-06-05 and the 2026-08-30 sentinel report does not flag it; whether ledger staleness is in sentinel's scope is unresolved. SINGLE-SOURCE.

## 4. Integration seams

### 4.1 Assistant portability

Praxion's `skills/<name>/SKILL.md` layout is conformant with the Agent Skills open standard (only `name` and `description` are required; `references/` matches the spec's layout), so the skills are drop-in for Gemini CLI extensions, GitHub Copilot (`.github/skills/`, since April 2026), Kiro, OpenCode, Amp, VS Code and Cursor. VERIFIED against agentskills.io. The Codex adapter is the deepest bridge (20 named hook wrappers, frontmatter-capsule agents, dynamic rules rescan) but the ADR finalize git hook is confirmed absent from the Codex install path; the Cursor adapter has no hooks, no worktrees and no finalize.

| Asset family | Cursor | Codex | Gemini CLI | Copilot | Kiro | OpenCode | Amp |
|---|---|---|---|---|---|---|---|
| Skills | faithful | faithful | faithful (spec) | faithful (spec) | faithful (spec) | faithful (spec) | faithful (spec) |
| Rules | faithful | faithful | absent (fold into `GEMINI.md`) | absent | lossy (`.kiro/steering`) | lossy (`AGENTS.md`) | absent |
| Commands | lossy | faithful | absent | absent | absent | absent | absent |
| Agents | lossy | lossy (capsule) | lossy-plausible (`agents/`) | lossy (`.github/agents`) | absent | lossy (`.opencode/agent`) | absent |
| Hooks | absent | mostly faithful | absent (exporter missing) | absent | structural mismatch | absent | absent |
| Worktrees, ADR finalize, model routing | absent | guard-only / absent / faithful | absent | absent | absent | absent | absent |

The portable fraction of Praxion is therefore the skills layer plus (via the AAIF-governed `AGENTS.md` standard) the Codex-targeted `AGENTS.md.tmpl`, which likely already serves Cursor, Amp, Devin and Jules with zero new code. SINGLE-SOURCE on the latter. The non-portable core is the agent pipeline, hooks and `.ai-state/` conventions — which is exactly the part that runs headless already (`claude -p` in the CI autofix workflow) and could run as a Routine.

### 4.2 Management-side integrations

| Integration | Seamlessness | Cheapest shape | Prerequisite |
|---|---|---|---|
| Linear | High — GA remote MCP, decision-grade design exists (`linear-integration-analysis.md`); Agent API still preview | MCP consumed by any supported assistant | opt-in per project; identity bridge issue ↔ task slug |
| Jira / Confluence | High mechanically, Medium fit — Atlassian remote MCP is GA on the same shape | MCP | a Jira issue-shape mapping (none exists) |
| GitHub Issues + Projects | High — already the substrate of issue-autofix and intake assessment | `gh` | none |
| GitHub Actions (own hub) | High — hub reusable workflows are production-hardened and fleet-installable | `workflow_call` hub + SHA-pinned caller | none |
| GitHub Agentic Workflows (gh-aw) | Medium — different paradigm, plausible as an extra host for narrow tasks | new workflow files | policy decision |
| Claude Code Routines | Medium — headless mode proven for autofix; no general scheduled-pipeline runner | cron + `claude -p` / Agent SDK | a runner that reads `WIP.md` and respects checkpoints |
| Cross-model review hub | High — ships today | caller | none |
| Slack (Claude Tag) | Medium — zero integration cost, no Praxion-aware surface | enable on workspace | Team/Enterprise tier |
| Observability (Phoenix/OTel) | Low-Medium — single-machine deployment documented | point the relay at a shared OTLP endpoint | collector in the trust boundary |
| Backstage / developer portal | Low — absent; `project_profile.yaml` rejected as host for an unrelated use (`dec-263`/`dec-241`) | `catalog-info.yaml` generator | design pass |
| GitLab CI, CodeRabbit/Graphite/Qodo, Notion | not researched | — | — |

Best leverage-to-cost: (1) Linear or Jira via MCP plus the `work_item:` field from §3.2, (2) recognising that Agent Skills and `AGENTS.md` conformance already carry Praxion to seven assistants, (3) the CI hub pattern as the vehicle for continuous AI.

## 5. The sidecar placement (decision-grade design)

### 5.1 Problem

One operator wants the full pipeline on a team repository whose other contributors do not use Praxion. Onboarding today writes about twenty surfaces; only `.git/hooks/*` and `.claude/settings.local.json` are local by construction. VERIFIED (footprint inventory). The repository must stay Praxion-agnostic, with `docs/architecture.md` and `DESIGN.md` the only tolerated exceptions.

### 5.2 Decision shape

`onboard-project` already resolves four modes. Placement is a second, orthogonal axis:

| Placement | Where durable state lives | Who sees Praxion |
|---|---|---|
| `in-repo` (today) | `.ai-state/` committed in the project | everyone who clones |
| `sidecar` (new) | a per-operator git repository outside the project, projected in by a symlink that the project excludes locally | only the operator |

The path contract `.ai-state/` is preserved on disk, so agents, hooks, scripts and the dashboard keep working unchanged; only the *git ownership* of those paths moves. This is the Data Structures First move: instead of teaching every consumer a relocated path, keep the path and change one thing about it.

### 5.3 Surface placement table

| Surface | in-repo | sidecar |
|---|---|---|
| `.gitignore` block | `.gitignore` | `.git/info/exclude` Praxion block; inherited by all worktrees (VERIFIED) |
| `.ai-state/` | committed | `<sidecar>/.ai-state/` + excluded symlink |
| `.gitattributes` merge drivers | project | sidecar's own `.gitattributes` and git config (needed only for multi-machine sync) |
| git hooks | `.git/hooks`, with chaining (prerequisite) | same; `post-checkout` additionally materialises symlinks in new worktrees (hook firing on `git worktree add` VERIFIED) |
| `.claude/settings.json` | committed | `<sidecar>/.claude/settings.local.json` + symlink; `.claude/` itself stays a real directory because Claude Code refuses worktrees when it is a symlink (VERIFIED, docs) |
| CLAUDE.md blocks | `CLAUDE.md` | `<sidecar>/CLAUDE.local.md` + symlink; loads last with highest precedence; `@~/…` imports are the documented cross-worktree pattern (VERIFIED, docs) |
| CI tier (workflows, labels, secrets) | opt-in | unavailable (GitHub-visible); local hook equivalents only |
| AaC tier (`architecture/`, `fitness/`, Block D) | opt-in | opt-in shadowed into the sidecar; Block D as a local pre-commit chain step |
| `docs/architecture.md` | committed | operator's choice: shared (committed; cites ADRs by id text, never by `.ai-state/` path) or shadowed |
| `.ai-state/DESIGN.md` | committed | private inside the sidecar; promotable |
| `.ai-work/` | gitignored per worktree | excluded per worktree (unchanged) |

### 5.4 The sidecar repository

```
${PRAXION_SIDECAR_ROOT:-~/.praxion/sidecars}/<project-id>/
  praxion-sidecar.yaml        # manifest
  .gitattributes              # merge drivers
  .ai-state/                  # byte-identical layout to in-repo placement
  CLAUDE.local.md
  .claude/settings.local.json
  docs/architecture.md        # only if shadowed
  architecture/  fitness/     # only if the AaC tier is shadowed
```

`<project-id>` is the sanitised, normalised origin URL (`github.com--acme--billing`), falling back to a path hash without a remote, so all clones and worktrees of a project share one sidecar. The manifest enumerates the legal states:

```yaml
schema: 1
project:
  origin: https://github.com/acme/billing
  roots: [/Users/me/work/billing]          # informational, machine-local
shadows:                                   # relpath -> kind
  .ai-state: dir
  CLAUDE.local.md: file
  .claude/settings.local.json: file
  docs/architecture.md: file               # optional
excludes: [.ai-work/, .claude/worktrees/, tmp/]
autocommit: on-finalize-and-stop           # | on-finalize | manual
remote:
  url: null                                # must share the project origin's trust boundary
  push: never                              # | on-autocommit
```

### 5.5 Mechanics, each verified

1. **Invisibility.** Shadows and excludes live in `.git/info/exclude`. `git status`, `git add -A` and `git commit -a` in the project never see them. `git add .ai-state/x` fails loudly (`pathspec is beyond a symbolic link`): fail-closed, never a silent leak. VERIFIED (scratchpad).
2. **Worktrees.** Excluded symlinks are absent from a fresh worktree; the existing multiplexed `post-checkout` hook gains a `link` step (fires on `git worktree add` with cwd set to the new worktree, VERIFIED), and the SessionStart banner hook re-runs `link` as self-heal. Reads through the symlink from inside a worktree work. VERIFIED.
3. **State git ownership.** A new helper, `scripts/_state_repo.py`, answers "which repository owns `.ai-state/`" (the project, unless `.ai-state` is a symlink whose realpath's toplevel differs). Its consumers are the only four stagers in the codebase — `finalize_adrs.py`, `reconcile_ai_state.py`, `reconcile_aac_surfaces.py`, onboarding Phase 9 — and `finalize_chain.sh`. Nothing in Praxion auto-commits today. VERIFIED (footprint §c). In sidecar placement `reconcile_ai_state.py` and squash-safety become no-ops (no branch-scoped state exists) and ADR promotion runs off the existing on-main backstop, which is already branch-independent. VERIFIED (`finalize_chain.sh` header).
4. **Autocommit for the sidecar only.** The project's commits remain human-owned. The sidecar is personal, unreviewed and linear, so the finalize chain commits it after rewriting state and the `Stop` hook commits residue (`chore(state): session <id>`).
5. **Two guards to teach** (the only real code blockers, both single-file): `hooks/worktree_guard.py` resolves symlinks and blocks writes whose git root differs from the session worktree — it must allow the designated state repo (a foreign repo by design, not the sibling-worktree hazard it exists for); `dashboard_app/src/server/artifacts/project-root.ts` requires realpath containment inside the project root and must accept the sidecar root as a second allowed root read from the manifest. VERIFIED (footprint §d).
6. **Hook chaining, a placement-independent prerequisite.** Onboarding never checks `core.hooksPath` (zero grep hits) and displaces an existing `pre-commit` hook by backing it up. In a husky, lefthook or pre-commit-framework repo Praxion's hooks silently never fire or silently replace the team's. Fix: detect `core.hooksPath`; install a local wrapper directory (`.git/praxion-hooks/`) whose scripts run the team's hook first and Praxion's second, point `core.hooksPath` at it locally, and let the SessionStart self-heal restore the chain when `npm install` re-points it. For an occupied `.git/hooks/pre-commit`, call the backed-up `.pre-praxion` hook first instead of shadowing it. VERIFIED (footprint §b).
7. **Promotion and absorption.** `promote` = `git subtree split --prefix=.ai-state` in the sidecar, `git subtree add --prefix=.ai-state` in the project (history preserved, VERIFIED), remove shadows and excludes, re-run onboarding in-repo. `absorb` is the inverse for a managed repo whose team wants Praxion out.
8. **Concurrency stance.** One shared state tree across worktrees replaces reconcile-at-merge with live sharing. Hot files are already lock-protected (`observations.lock` fcntl in `_hook_utils.py`; advisory locks in `finalize_tech_debt_ledger.py` and `finalize_adrs.py`), ADR drafts are collision-safe by filename, and `calibration_log.md` gets one row per task. Documented consequence: concurrent pipelines see each other's drafts immediately. Accepted for a personal factory; reversal trigger is two concurrent Standard pipelines on one project becoming routine.

### 5.6 Considered and rejected

- **In-tree but excluded, no external repo.** `git clean -fdx` deletes the entire intelligence tree; no history; worktrees still need a symlink to reach it, so the guard fixes remain and the safety is lost.
- **Orphan branch plus nested worktree in the project repo.** Refs leak on `push --all` or `--mirror`; the project's hooks fire on state commits; nested worktrees under pipeline worktrees confuse every root resolver.
- **`~/.claude/projects/<key>/` as state home.** Claude-Code-specific, machine-local, not versioned, invisible to the Codex and Cursor exports.
- **Bare repo with `core.worktree` pointing at the project (vcsh pattern).** Same guard fixes, harder to reason about, worktrees still need symlinks; dominated by the sidecar.

### 5.7 Open verifications for the implementing pipeline

- Claude Code's own worktree isolation "blocks an Edit that targets a path in the main checkout"; the sidecar is not the main checkout, but whether writes through the symlink need `permissions.additionalDirectories` in the local settings must be exercised, not assumed. ASSUMPTION.
- `.worktreeinclude` (Claude Code copies listed gitignored files into new worktrees) may cover `EnterWorktree`-created worktrees without the hook; it copies rather than links, so the hook remains the primary mechanism. SINGLE-SOURCE.
- Behaviour of `finalize_adrs.py`'s `git mv` and `_stage_path` when `--repo-root` is the sidecar: the scripts are parameterised, the composition in `finalize_chain.sh` is not. VERIFIED that the parameter exists; the composition change is the work.

### 5.8 Data boundary

On a work machine the sidecar root and any sidecar remote must sit inside the company boundary (the i-am scenario). `praxion-sidecar remote` refuses a host that differs from the project origin's host unless explicitly overridden, and the SessionStart banner prints the sidecar location so the operator always knows where project intelligence accumulates. Recommended default for the new-job scenario: no remote until the company's policy on personal engineering notes is known; the sidecar is then a local git repository under the work identity's home.

### 5.9 Tier and blast radius

Full tier when built: `scripts/praxion-sidecar` with tests, `scripts/_state_repo.py` with tests, four stager edits, `finalize_chain.sh`, `worktree_guard.py`, `project-root.ts`, `inject_worktree_banner.py`, the onboarding skill (placement axis across Phases 1–9), one canonical-block variant for `CLAUDE.local.md`, `docs/onboarding.md`. Hook chaining is a separable Lightweight prerequisite that improves every team-repo onboarding today.

## 6. Improvement roadmap

Ordered by leverage for the stated situation (a personal factory used on team repos), each with the tier it would take and the component family it belongs to.

| Priority | Improvement | Tier | Family | Why now |
|---|---|---|---|---|
| P0 | Hook chaining and `core.hooksPath` awareness in onboarding | Lightweight | skill + script | silently broken on every husky/pre-commit team repo today; prerequisite for P1 |
| P1 | Sidecar placement (§5) | Full | skill + scripts + two guard edits + canonical block | unblocks the user's job scenario; the field's B1 answered without imposing the tool |
| P2 | Delivery telemetry: duration/model/tokens on stop rows, then offline lead-time and deploy-frequency collector | Lightweight, then Standard | hook + metrics collector | the falsifier for the bitter-lesson objection; enables WIP/flow |
| P3 | Bystander artifacts: `what-is-ai-state.md` block, `AI_POLICY.md` block, non-invasive readiness run on an un-onboarded repo | Lightweight | canonical blocks + command flag | first-contact surface a Praxion-agnostic team will accept |
| P4 | `work_item:` field in `TASK_BRIEF.md` and ADR frontmatter, then Linear/Jira MCP consumption | Lightweight, then Standard | schema + canonical block + MCP | colleagues live in the tracker; 80% of the value is one propagated field |
| P5 | Continuous AI: a headless pipeline runner that reads `WIP.md`, respects checkpoints and is invocable from a Routine or the CI hub | Standard | script + workflow | seven peers ship it; Praxion's substrate already supports it |
| P6 | Portability: publish the Agent Skills conformance, add a Gemini CLI extension exporter and Copilot `.github/skills` layout to `install.sh` | Standard | install script + docs | turns an accidental asset into a claimed one |
| P7 | `/fleet-status`, `/postmortem`, CODEOWNERS draft from the ownership block | Lightweight each | commands + script | closes three of the five absent cells cheaply |
| P8 | Attestation in `release.yml` and as an opt-in `ci` sub-step; sentinel dimension for "skill advice not applied to Praxion" | Direct + Lightweight | workflow + sentinel check | dogfooding norm made mechanical |
| P9 | Watchlist refresh (applied with this analysis) and an industry-evidence section (DORA, METR, Thoughtworks) | Direct | `.ai-state` | keeps promethean and the cartographer grounded |
| P10 | Distribution: marketplace listing and an installer | Spike | — | value uncertain until P1–P3 make Praxion adoptable by a bystander |

## 7. Decisions recorded by this Spike and decisions left to the user

Recorded (see `.ai-work/factory-gap-analysis/LEARNINGS.md`, to be promoted to ADR fragments by the implementing pipeline): placement is an axis orthogonal to onboarding mode; the path contract `.ai-state/` is preserved and only git ownership moves; the sidecar autocommits while project commits stay human-owned; hook chaining is a prerequisite fixed independently of placement.

Left to the user: whether to run P0 and P1 as the next pipeline; the sidecar root and remote policy on the work machine; whether `docs/architecture.md` is shared or shadowed on the new job's repositories; whether P2 (delivery metrics) precedes P4 (tracker binding).

## Appendix A — Scratchpad experiment log (2026-09-02)

Two throwaway repositories, `team` and `sidecar`. Results: excluded symlink invisible to `git status --untracked-files=all`; `git add` through the symlink fails with `pathspec '.ai-state/DESIGN.md' is beyond a symbolic link`; `git add -A` stages nothing; sidecar commits normally; `post-checkout` fires on `git worktree add` with `$3=1` and cwd in the new worktree; the worktree inherits `.git/info/exclude` and reads through a re-created symlink; `git clean -fdxn` would remove only the symlink; `git subtree split --prefix=.ai-state` followed by `git subtree add` in `team` preserves both sidecar commits in the project's history.

## Appendix B — Watchlist deltas applied

Renames confirmed by GitHub API redirects: `block/goose` → `aaif-goose/goose`, `sst/opencode` → `anomalyco/opencode`, `ruvnet/claude-flow` → `ruvnet/ruflo`, `All-Hands-AI/OpenHands` → `OpenHands/OpenHands`, `ComposioHQ/agent-orchestrator` → `Untrivial-ai/agent-orchestrator`, `Wirasm/PRPs-agentic-eng` → `Wirasm/prp`. Roo Code archived 2026-05-15, no successor found. Plandex stale since 2025-10-03. Added peers: Superpowers, Spec Kit, OpenSpec, BMAD-METHOD, Agent OS, Conductor, Kiro, Factory.ai, Tessl, Beads, Backlog.md, Antigravity; standards: Agent Skills; new industry-evidence section: DORA 2025, METR, Thoughtworks Radar vol. 34, Böckeler on SDD, OpenAI harness engineering.

## Sources

Research fragments (ephemeral): the first pass in `.ai-work/factory-gap-analysis/` — `RESEARCH_FINDINGS_external-landscape.md` (71 tagged claims, live GitHub API), `RESEARCH_FINDINGS_managed-footprint.md`, `RESEARCH_FINDINGS_sdlc-coverage.md`, `RESEARCH_FINDINGS_integration-seams.md`, `RESEARCH_FINDINGS_claude-code-config.md` (code.claude.com docs), `SIDECAR_DESIGN_DRAFT.md`; the 2026-factory pass in `.ai-work/factory-2026/RESEARCH_FINDINGS.md` (the 18-feature model, the 2004→2026 translation, and the evidence appraisal behind §2.7 — Factory 2.0, OpenAI harness posts, Thoughtworks Radar vol. 34, DORA 2025 + AI Capabilities Model, METR 2025 RCT and its 2026 non-replication, CodeRabbit 470-PR study, all with fetch dates and evidence-class tags). Primary external sources are cited inside each fragment; the durable ones are transcribed into `.ai-state/LANDSCAPE_WATCHLIST.md`. Prior in-repo analyses built upon: `docs/context-prj-comparison-2026-05-12/`, `docs/independent-analysis/linear-integration-analysis.md`, `dec-221`, `dec-279`.
