---
title: Praxion Process Economy — Best-in-Class Against Modern Agentic Pipelines by Spending Less
type: independent-analysis
diataxis: explanation
audience: architect / maintainer
status: spike (analysis + roadmap; no implementation)
date: 2026-09-07
head_sha_analyzed: 55964a73
author: Francisco Perez-Sorrosal (analysis run as a five-lens Spike with Claude Code; orchestrator priors recorded before any lens result and scored at synthesis)
verification_legend:
  VERIFIED: primary source fetched, file:line read, or number produced by a stated command
  SINGLE-SOURCE: one source, not independently confirmed
  ASSUMPTION: stated belief that shapes a recommendation; falsifier named where possible
---

# Praxion Process Economy — Best-in-Class Against Modern Agentic Pipelines by Spending Less

> **Scope.** A Spike, not an implementation. The 2026-09-02 analysis ([personal-software-factory-analysis.md](personal-software-factory-analysis.md)) scored Praxion against the 2026 agentic software factory on *capabilities* and registered, in its §2.6, the bitter-lesson objection it did not act on. This document acts on it. It compares Praxion's **process economy** — context spent, ceremony required, artifacts produced, machinery maintained per unit of delivered quality — against what modern agentic pipelines and harnesses do to keep or raise quality while spending less, and it produces a **simplification-first roadmap** of surgical interventions, each with the cost it removes and the quality guard that must survive it. Capability additions that make Praxion best-in-class come second, and only where they *also* reduce burden.

## 0. TL;DR

- **The cost is real, measured, and multiplied.** The governed always-loaded budget sits at 24,542 of 25,000 tokens (98.2%), but the true always-resident surface is ~41,300 tokens once the skill, command and agent *listing* (~16,700 tokens, outside every instrument until this audit) is counted. Subagents inherit the symlinked always-loaded set — 21,287 tokens measured from a live spawn — so **every always-loaded token is paid ~7× per Standard pipeline**, contradicting the `agent-crafting` skill's claim that they inherit nothing. The surface grew +25.6% in the 117 days since the last budget pass; at +43 tokens/day the ceiling breaches in ~11 days. VERIFIED (§3).
- **The biggest single lever is not the rules — it is preloaded skills.** Agent frontmatter `skills:` bodies total 240,647 tokens across 17 agents, more than the 136,976 tokens of agent definitions they serve; the implementer preloads 4.2× its own size, and the four interface-design skills are preloaded by five agents each. Only 12 `Skill` tool calls appear in 18,000 telemetry rows: preload is the delivery path, progressive disclosure is not happening at the agent layer. Three frontmatter edits (12 YAML lines) remove ~36,000 tokens per Standard pipeline. VERIFIED (§3, §6 P1.1).
- **Discovery is silently broken for most skills.** Claude Code caps combined skill descriptions at 1% of the context window and drops the least-used first. Praxion's 62 descriptions alone are 35,886 characters; in the session that produced this document ~40 of 62 Praxion skills appeared as bare names, invisible to description-based activation. VERIFIED (§5 W3).
- **The field converges on a shape Praxion exceeds by an order of magnitude on every axis but one.** Fifteen peers: one small always-on file with a numeric ceiling (200–500 lines; measured peers ship 195 B – 8.9 KB against Praxion's 93.5 KB), everything else glob- or description-gated, ≤3–4 artifacts per change, one pre-implementation human gate, nothing persisted that the codebase already states. The one axis Praxion is *ahead* on is the documented scale-down: only BMAD of 15 peers has a tier system. Praxion's problem is not the tiers — it is that 65% of logged tasks ran at Standard or Full and the designed 5-spawn Standard pipeline ran 28–48 spawns in four real sessions. VERIFIED (§2, §3).
- **The evidence inverts the burden of proof.** The only effect that reaches significance in the literature is *cost* (+20–23% inference cost from repository context files, p<0.001); every measured *quality* effect is null and underpowered. Imperative instructions are measurably followed (1.6–2.5× tool-use lift); repository overviews are measurably inert for navigation. On-demand context beat always-on on process endpoints. The burden therefore sits on the ceremony to show payoff, not on its removal. Praxion's own instruments cannot carry that burden today: 0 of 85 calibration rows ever recorded an over-heavy tier and 0 of 77 consult challenges were dismissed — two zero-variance, self-graded instruments. VERIFIED (§4).
- **Bookkeeping dominates version control.** 665 of 1,252 commits in 120 days (53.1%) change nothing but `.ai-state/`; the six most-churned files in the repository are all `.ai-state/` artifacts; `PROGRESS.md` is written by every agent at every phase and read by nothing. VERIFIED (§3).
- **What must survive** is exactly what the evidence says works: the tier system, the deterministic check layer (22 `check_*` scripts, 39 tests, 8 fitness tests — the thing that *licenses* deleting prose), the criteria-anchored verifier and the step-scoped light-review, the behavioural contract, the tech-debt ledger (83.7% closure), and the ADR corpus as a constraint on later decisions (13 re-affirmations, one documented regression catch). The roadmap touches none of these except to make them cheaper to run.
- **The roadmap** (§6) has four phases: **Phase 0** instruments and corrections (no cut until one budget number exists and gates can be observed), **Phase 1** mechanical high-confidence cuts (−48% always-loaded, −33% per-spawn resident context, ~−154,000 tokens per Standard pipeline, 12 YAML lines for the largest item), **Phase 2** structural economies (sentinel checks as scripts, an ADR gate and rate default, a spawn budget per tier, the WAL out of git, a skill-description diet), **Phase 3** the compete items that also reduce burden (intentional compaction at phase boundaries, pipeline-as-code, continuous AI, silence-on-success). Six decisions are left to the user (§10), the first being whether the seven-principle philosophy prose is compressed — the one item with no quality guard.

## 1. Method

Five research lenses ran in isolation (no lens read another's output) and were reconciled only here: a **practice canon** of 20 process-economy practices admitted only with ≥2 independent exhibitors (22 primary sources, fetched 2026-09-06); a **peer process-shape** survey of 15 pipelines plus a native-platform subsumption inventory (Claude Code / Agent SDK / Agent Skills / Codex docs, fetched 2026-09-06/07); an **internal cost audit** with every token counted by the real tokenizer and every number carrying its command; an **evidence appraisal** grading 22 external claims by design and transfer, plus Praxion's own telemetry; and a **context-artifact audit** by the context-engineer classifying every always-loaded section and the seven largest agent definitions. A sixth vantage point was the orchestrator's 14 hypotheses, written from the baseline numbers *before* any lens result and scored at synthesis: 9 confirmed, 3 partial, 1 refuted, 1 confirmed-with-flag (§11).

Two lens-independence catches worth recording: the cost audit re-derived the baseline's "19.5% process commits" by diff content rather than message prefix and found 53.1%; the context audit found the baseline had double-counted the hook-delivered rules as additional to the measured budget. Both corrections are applied below.

One consult nomination was declined. The evidence lens nominated a `statistician` consult on whether the roadmap may cite Praxion's own telemetry as a quality guard. The lens had already answered it (both candidate instruments are Type-I-blind), the roadmap adopts the answer as a rule (§9, principle 4), and convening a ~165,000-token consult to re-derive it inside a Spike about ceremony would be the wrong signal. Recorded in the task's `LEARNINGS.md` and the calibration row.

Claims carry the legend above. Vendor throughput claims are quarantined. Every quantitative claim resolves to a file, a command, or a cited source (roadmap-synthesis grounding protocol).

## 2. Praxion versus modern agentic pipelines on process economy

### 2.1 The practice canon, and where Praxion stands

Twenty practices were admitted (each with the cost it reduces *and* the quality mechanism it substitutes — a practice with no substitute is cost-cutting, not economy). Condensed mapping; the full table with exhibitors and evidence class is in the practice-canon fragment (§12).

| # | Practice (exhibitors) | Praxion |
|---|---|---|
| P01 | Instruction-file minimalism (Anthropic, Thoughtworks, OpenAI, HumanLayer) | **OVER-BUILDS** — 98.2% of its own ceiling; 10 SessionStart injectors |
| P02 | Progressive disclosure / just-in-time retrieval (Anthropic, Thoughtworks, Manus) | **CONFORMS** in the skill layer (62 `SKILL.md` ≤418 lines, median 195; 2.4 MB of references on demand); one deviation: 117 sibling→sibling reference links against the one-level-deep rule |
| P03 | Sub-agent isolation + distilled returns (Anthropic, HumanLayer, Willison) | CONFORMS — "pointer, not a payload, ≤15 lines" |
| P04 | Research → plan → implement, one reviewable plan (Anthropic, HumanLayer, Böckeler) | CONFORMS in shape, **OVER-BUILDS in artifacts** — 19 named documents per run vs the canon's 2–3 |
| P05 | Intentional compaction with a utilisation target (HumanLayer, Anthropic, Cognition, Manus) | **UNDER-BUILDS** — reactive `PreCompact` snapshot only; no phase-boundary fresh-window protocol |
| P06 | Machine-checkable verification as the primary gate (Anthropic, OpenAI, Thoughtworks, UIUC/Princeton) | **CONFORMS (exceeds)** — 22 `check_*` scripts, 39 tests, 8 fitness tests, three independent auditors |
| P07 | Adversarial fresh-context review of the diff (Anthropic, HumanLayer, Every) | CONFORMS (marginal over-build: four independent gap-finders) |
| P08 | Minimal-scaffold hypothesis (SWE-agent team, UIUC, Anthropic) | **OVER-BUILDS** — 541 KB of agent prompts; `sentinel.md` 120 KB |
| P09 | Tool / choice-surface minimalism (Anthropic, HumanLayer, Thoughtworks) | OVER-BUILDS (weakest verdict) — ~127 named affordances |
| P10 | CLI over protocol surface (Thoughtworks, Anthropic) | CONFORMS — 151 CLI scripts, one in-repo MCP server |
| P11 | Prompt-prefix stability for cache economy (Manus, Anthropic) | UNDER-BUILDS (unmeasured) |
| P12 | Externalise state to files (Manus, Anthropic, Huntley) | CONFORMS; one over-build: a 9.1 MB WAL committed and re-dirtied every session |
| P13 | Effort tiering (Anthropic, Böckeler) | **CONFORMS in design, UNDER-PERFORMS in practice** — 65% of logged tasks at Standard/Full |
| P14 | Feedback flywheel (Every, Thoughtworks, Anthropic) | CONFORMS (exceeds) — but see §4 on the adopt half |
| P15 | Model-tier routing (Thoughtworks, Anthropic, HumanLayer) | CONFORMS |
| P16 | Curated shared instruction repository (Thoughtworks *Adopt*, Anthropic, OpenAI) | CONFORMS (exceeds) — canonical blocks + sync check |
| P17 | Sandboxed / permission-scoped autonomy (Anthropic, OpenAI, Thoughtworks) | CONFORMS |
| P18 | Fan-out over disjoint units with isolated checkouts (Anthropic, OpenAI, Thoughtworks) | CONFORMS — on the small, role-specific side of the Radar boundary |
| P19 | Silence on success, verbosity on failure (HumanLayer, Manus, Anthropic) | UNDER-BUILDS — `TEST_RESULTS.md` is a full-run artifact |
| P20 | Evaluation-driven authoring of agent assets (Anthropic, Thoughtworks) | PARTIALLY CONFORMS — `eval/` exists; no baseline ties any instruction to a measured delta |

The structural point that governs the whole roadmap: **P06 is what licenses P01.** Anthropic's prescription — *if Claude already does something correctly without the instruction, delete it or convert it to a hook* — is only available to a project that has the hooks and checks. Praxion has them. Much of what the always-loaded rules assert in prose is already enforced deterministically by `finalize_adrs.py`, `adr_health.py`, `check_state_ledgers`, `check_id_citation_discipline` and the sentinel. The prose is a second, advisory copy of machinery that already fails closed. VERIFIED (practice-canon fragment, §Notes on three verdicts).

### 2.2 What the lightest credible pipelines keep

Six shapes have ≥3 independent peers converging (peer-process fragment §A.2, all VERIFIED against primary repos/docs on 2026-09-04/07):

1. **A small always-on file with a numeric ceiling.** Claude Code: "target under 200 lines per CLAUDE.md file"; Cursor: "keep rules under 500 lines"; Factory: 80,000 chars initial load, enforced; Kiro: one domain per file; Every: "ten specific rules you follow beat 100 generic ones"; Devin: "short content". Measured peer surfaces: Agent OS 195 B, BMAD 1,523 B, OpenSpec ~1.3 KB, Spec Kit 2,346 B, Superpowers 8,873 B. Praxion: 93,532 B / 24,542 tokens across 9 files.
2. **Conditional loading is the default** (path globs, description gating, manual, auto) — four vendors independently. Praxion uses two of the four mechanisms and keeps 7 rules unconditional.
3. **Three or four artifacts per change is the ceiling; one is viable** (OpenSpec 4, Kiro 3, Spec Kit 3–4, Conductor 2, BMAD Quick Flow 1). Praxion names 19.
4. **Exactly one human gate, always "review the plan before any code"** (OpenSpec, Conductor, Kiro, Claude Code plan mode).
5. **Do not persist what can be derived** — the sharpest convergence: Claude Code auto-memory "skips anything it can derive from the codebase, such as architecture, file paths, or debugging fixes"; `/doctor` trims "directory layouts, dependency lists, and architecture overviews"; Factory forbids "stale inventories". Praxion carries `DESIGN.md` (180,804 B) and `docs/architecture.md` (93,824 B), both largely derivable component maps, at 118 and 79 commits in 120 days.
6. **Explicit scale-down is rare, and its absence is a named cost.** Only BMAD ships a trigger-driven tier system; Spec Kit's answer is "leave the tool". **This cuts for Praxion's five tiers**, which are a genuine differentiator — and against their use.

mini-SWE-agent satisfies all six by shipping ~100 lines of Python and scores >74% on SWE-bench Verified — the strongest single data point that heavy scaffolding is not the source of capability. The transfer caveat (§4) is that SWE-bench measures none of the outcomes Praxion's governance targets; it licenses "harness complexity buys little," not "governance is worthless."

### 2.3 What the platform has subsumed

Praxion hand-builds several mechanisms that Claude Code now ships natively (peer-process fragment §B, docs fetched 2026-09-06/07, version numbers from the docs pages). Ranked by deletable footprint; none is a recommendation until §6:

| Praxion mechanism | Native feature | Overlap | Portability cost of leaning on it |
|---|---|---|---|
| Worktree guard + banner + `/create-worktree` + `/merge-worktree` (~62,874 B, 2 hooks, 2 commands) | `--worktree` / `EnterWorktree` / `isolation: worktree`, four built-in isolation checks, sweep, locking, `.worktreeinclude` | **FULL** for guard and banner (native is a strict superset); `/merge-worktree`'s finalize + reconciliation stays Praxion-specific | Claude-only; the native check is also the source of the recorded heredoc/`sh -c` false positives, so friction stays |
| `inject_rules.py` (63,184 B incl. tests, 597 lines) | `.claude/rules/` + `paths:` + `claudeMdExcludes` — already the substrate Praxion runs on | PARTIAL; the `hook-deliver` path is the redundant half — and it has a defect: hook-delivered rules never reach subagents (§5 W10) | Low |
| Cross-session learning store (designed-but-absent after `dec-225`) | Auto-memory: four typed memories, 200-line index, per-subagent `memory:` | HIGH for a *personal* store; machine-local and ungitted, so it cannot be the team-shared loop | High; user decision (§10) |
| Orchestrator-mediated mechanical fan-out (26,507 B always-loaded rule + 84,907 B references) | `Workflow` tool: deterministic `agent()`/`parallel()`/`pipeline()`/`phase()`, results kept out of context, resumable | PARTIAL→HIGH for mechanics, NONE for judgment; **structural blocker: no mid-run user input**, so Conversation Checkpoints must sit at workflow boundaries | High; Claude-only |
| Skill validation + review surface | `claude plugin validate` (v2.1.233+), `/skill-doctor` (v2.1.252+ — per-skill context cost, unused skills), `/code-review --fix`, `/security-review`, `/simplify` | PARTIAL→HIGH; `/skill-doctor` supplies exactly the per-skill cost telemetry Praxion lacks | Low; additive |
| Compaction state (`precompact_state.py`) | `PreCompact` **and** `PostCompact` with `additionalContext`; plan-mode plan re-injected from disk | PARTIAL; `PostCompact` is a strictly better restore point | Low |

Two things the platform has **not** subsumed and which the roadmap protects: the calibration governance (reminders + coverage check — no native analogue in 15 peers) and the tier system itself. The asymmetry that matters: the mechanisms with the largest deletable footprint (worktrees, rule delivery, memory, workflows) are the least portable; skills — where Praxion has 3.2 MB invested — are the one fully portable asset (Agent Skills standard, ~47 clients). Every simplification that moves logic *out of* a skill *into* a Claude-only feature spends portability.

## 3. The cost ledger — measured

Every figure below was produced by the cost-audit or context-review lens with the real tokenizer (API key present) or a stated command; commands are in the fragments (§12).

### 3.1 Resident context

| Surface | Measured | Source |
|---|---|---|
| Governed always-loaded set (9 files) | **24,542 / 25,000 tokens (98.2%)**, 93,532 B | `python3 scripts/measure_token_budget.py` |
| Skill + command + agent description listing (ungoverned) | **~16,713 tokens** (skills 35,886 chars, commands 10,585, agents 12,316) | frontmatter `description:` over `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md` |
| True always-resident (orchestrator) | **~41,300 tokens** | context-review §Projected Totals |
| What a subagent inherits at spawn | **21,287 tokens** — `~/.claude/CLAUDE.md`, `rules/CLAUDE.md`, `CLAUDE.md`, and the four symlinked rules; *not* the two `install: hook-deliver` rules | measured from the context-engineer's own spawn (`claudeMd` system block) |
| Mean resident context per spawn before the first tool call | **47,054 tokens** (inherited 21,287 + listing + definition + preloaded skills); systems-architect 81,166; implementer 76,047; verifier 75,232; sentinel 74,449 | cost-audit CC1; context-review §2 |
| Preloaded `skills:` bodies, all 17 agents | **240,647 tokens** vs 136,976 tokens of agent definitions; implementer 27,138 (4.2× its 6,431-token body); the four interface skills (12,045 tokens) preloaded by 5 agents each; `external-api-docs` (5,156) by 9 of 17 | cost-audit CC1 |
| `Skill` tool invocations in the WAL | **12 of 18,042 rows** | `tool_name == "Skill"` |
| Agent definitions | 17 files, **541,187 B**; `sentinel.md` 120,012 B / 31,971 tokens (24,064 of them a 127-row check catalogue, 56 of whose 78 `A`-typed checks have no script) | `wc -c agents/*.md`; context-review §2.1 |
| Growth since the 2026-05-12 "net ≤ 0" budget pass | always-loaded **+25.6%** (+163 B/day ≈ +43 tokens/day, 117 days); agent corpus **+62.9%** | `git cat-file -s` series, context-review §1b |
| Headroom at that rate | **~11 days** | 458 tokens / 43 per day |
| Two live instruments disagree | gate 24,542 (9 files) vs `hooks/measure_context_surface.py` 41,216 (14 files — it counts 7 plugin-cache duplicates), written to the WAL in 23 consecutive sessions, unnoticed | evidence §B.7; context-review C3 |

### 3.2 Pipeline shape

| Item | Designed | Observed | Source |
|---|---|---|---|
| Standard-tier spawns | 5 minimum (researcher → architect → planner → implementer → verifier), 270,279 tokens resident | **28–48 spawns** in four real sessions; one session paid **2,258,592 tokens** of resident context before any delegation prompt or tool result | coordination protocol §Process Calibration; WAL sessions `fd3ecaaa`, `9b74ea5c`, `dee467d0`, `ffb26673` |
| Tool calls per spawn | — | ≈49 (11,832 attributable rows / 241 spawns); Bash 58% of all rows | cost-audit CC2 |
| Tier distribution, 85 logged rows | selector says "default lower" | Standard 31 · Full 22 · Lightweight 21 · Direct 6 · Spike 2 → **65% Standard/Full**; Direct under-logged (no enforcing hook) | `.ai-state/calibration_log.md` |
| Artifacts named per run | ≤3–4 (peers) | **19** in the `.ai-work/<slug>/` inventory; `PROGRESS.md` written by all 17 agents every phase, read by no script or agent (`reconcile_pipeline_state.py` parses `WIP.md` only; `discipline-consultant.md:103` forbids reading it) | `rules/swe/agent-intermediate-documents.md`; cost-audit CC6 |
| Load-bearing artifacts confirmed | — | `TASK_BRIEF` (verifier rubric, `check_p06_task_brief.py`), `WIP` (reconciler), `TEST_BASELINE` (verifier Phase 10), `LEARNINGS` (harvest), `VERIFICATION_REPORT` (rework path) | cost-audit CC6 reader analysis |

### 3.3 Governance and bookkeeping

| Item | Measured | Source |
|---|---|---|
| ADR corpus | **375** finalized, all dated within 180 days; **11.7/week** over 90 days; mean 7,379 B ≈ 1,940 tokens; `## Considered Options` = 21% of the corpus | `.ai-state/decisions/` |
| `architectural` share | **68%** (255). Hand-test of the 21 architectural ADRs among the 40 most recent against the rule's own falsifier ("name the component added, removed, or whose responsibility moved"): **57% clear pass, 29% borderline, 14% clear fail** → 36–110 of 255 plausibly over-categorised, each costing a mandatory `## Disconfirmation` block (mean 1,455 B) | cost-audit CC5; `rules/swe/adr-conventions.md` |
| ADR machinery | **8,504 LOC** (58% tests); 56 file-touches in 90 days; churn×complexity hot-spots #2 (`finalize_adrs.py`), #3 (`adr_health.py`), #5 (`test_finalize_adrs.py`) | `METRICS_REPORT_2026-09-07` |
| `DECISIONS_INDEX.md` | **184,311 B ≈ 48,500 tokens**; regenerated 105× in 120 days; canonical access pattern is "do not read this" | Discovery Protocol; cost-audit CC5 |
| Commits touching only `.ai-state/` | **665 / 1,252 (53.1%)** in 120 days; 271 of them wear `feat`/`fix`/`docs` prefixes | `git log --since='120 days ago' --name-only` |
| Most-churned files | #1 `TECH_DEBT_LEDGER.md` 159, #2 `observations.jsonl` 146, #3 `doc_manifest.yaml` 136, #4 `DESIGN.md` 118, #5 `DECISIONS_INDEX.md` 105, #6 `calibration_log.md` 86; the top *product* file (`agents/sentinel.md`) is #10 at 56 | cost-audit CC8 |
| Observations WAL | 8.68 MB, 18,042 rows; ~413 KB / 862 rows added per session; 146 commits, net `+50,532 / −59,882` (rewritten, not appended); **no `duration_ms`, `tokens`, `model`, and no `Read`/`Grep`/`Glob` events**; one analytical reader whose output artifact (`RECOVERY_LOG.md`) has never existed | cost-audit CC5; evidence §B.5, §B.8 |
| Duplicated canonical text | behavioural contract at **12 sites**, task-slug at 12, model-routing pointers at 16, return contract at 5, delegation checklists at 3; **5 of 7 have no sync mechanism**, 1 has an LLM-judged WARN (sentinel EC06) that reads a generated, gitignored file | cost-audit CC4 |
| Hooks | 55 files; SessionStart chain **3,660 ms**, 8 of 10 hooks emit 0 bytes on the canonical path; every-tool-call hooks cost ≤ the bare-interpreter baseline (their own work ≈ 0 ms; ~70% of 5.4 CPU-hours is the pyenv shim) and are `async: true`; the five Bash commit gates fast-skip in bash and are "the best-engineered layer in the system" | cost-audit CC3 |
| Injection hooks | ~4,500 tokens/session total, gated, capped, fail-open; `inject_process_framing` 35 tokens/prompt; `remind_task_brief` stderr-only (0 tokens) | context-review §1d |

**Reading.** The injection layer is not the problem and the hook layer is mostly well-built; the cost is in the static artifacts (always-loaded prose, preloaded skills, agent prompts), in the pipeline's *use* (spawn count, tier drift, reader-less artifacts) and in the bookkeeping the pipeline leaves in git.

## 4. What the evidence supports — and what it does not

The evidence lens graded 22 external claims (fetched 2026-09-07) and Praxion's own telemetry. The findings that carry decision weight:

**Transfers, in order of weight.**

1. **Instructions bite; overviews do not.** Gloaguen et al., *Evaluating AGENTS.md* ([arXiv 2602.11988](https://arxiv.org/abs/2602.11988)): benchmark ablation, 4 models, SWE-bench + a 138-instance benchmark of repositories with developer-committed context files. Tools *named* in a context file are used 1.6–2.5× more; repository overviews produce no navigation gain; context files give **no quality gain at +20–23% cost (p<0.001)**. Directly transferable: Praxion's imperative surfaces (contract, protocols, rules) are the class shown to work; `DESIGN.md` and `docs/architecture.md` are the class shown *not* to work for navigation (they remain human-facing and ADR-traceability substrate — the claim removed is "the agent navigates better because of them"). VERIFIED.
2. **On-demand beats always-on on process endpoints.** *Do Context Files Help Coding Agents?* ([arXiv 2607.27250](https://arxiv.org/html/2607.27250v1)): 288 runs, Claude Code + Codex, equivalence-bounded null on correctness (MDE ≈ 30 pp — a 10 pp effect would be invisible), but selective context cut cache-creation tokens (p=0.012) and blind full-suite test runs 3.67 → 2.44 → 1.67. Supports **relocation to on-demand, not deletion**. VERIFIED (secondary endpoints, unadjusted for multiplicity).
3. **Intelligence-yes, actions-no for multi-agent.** Anthropic (multi-agent systems ≈15× the tokens of a chat; "most coding tasks involve fewer truly parallelizable tasks than research") and Cognition ("writes stay single-threaded, additional agents contribute intelligence rather than actions") converge from opposed commercial incentives; MAST ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657), 1,600+ traces, κ=0.88) names inter-agent misalignment and task verification as structural failure families. Endorses Praxion's researcher/reviewer/consultant fan-out; indicts its parallel-implementer pattern — for which Praxion's own retrospectives record shared-index sweeps and stash races and no retrospective credits a quality gain. VERIFIED.
4. **The oracle is what separates good gates from bad.** SWR-Bench ([arXiv 2509.01494](https://arxiv.org/html/2509.01494v1)): open-ended LLM code review reaches F1 19.4% at best. *Bias in the Loop* ([arXiv 2604.16790](https://arxiv.org/html/2604.16790v1)): LLM-judge verdicts flip on authority cues (60.99% → 78.12%) and verbosity with the code unchanged. Praxion's evidenced gates (verifier, light-review) are criteria-anchored with an executable test suite; its unmeasured gates (prose conformance, consult adjudication) sit in the low-precision regime. VERIFIED.

**Does not transfer, and should stop being cited as if it did.** METR's 2025 RCT has no scaffolding arm and its 2026 follow-up reversed the point-estimate sign while declaring itself unreliable — citing "19% slower" against ceremony is a double appraisal error (the watchlist entry is corrected in this Spike). The Radar's bitter-lesson line is informed opinion, not a finding; the 2026-09-02 analysis was right to log it as an objection. SWE-bench results (mini-SWE-agent, Agentless, the leaderboard census) license "the model, not the scaffold, is the dominant term" — not "governance is worthless": the benchmark contains no measurement of decision durability, regression prevention across months, or cross-session knowledge.

**Praxion's own data — the payoff table** (evidence fragment §B.10, all counts from repo artifacts):

| Mechanism | Verdict | Evidence |
|---|---|---|
| Intra-step light-review | **evidenced** — best cost/yield in the repo | ≥5 named defect catches in 8 mentions, sonnet-tier, RISKY-gated |
| Full verifier | **evidenced** | 2 of 2 surviving reports carry FAILs incl. one blocking (55 failing tests in CI scope); 5 retrospectives credit a specific catch |
| Tech-debt ledger | **evidenced** | 149 of 178 rows terminal (83.7% closure) |
| Behavioural contract / Register Objection | **evidenced** — cheapest evidenced mechanism per token | multiple retrospectives record objections that changed the outcome |
| Ground-truth re-derivation (never trust checkboxes) | **evidenced** | repeatedly the highest-yield practice in the log; independently prescribed by the judge-bias paper |
| ADR corpus as a constraint | **evidenced, read path disproportionate** | 13 `re-affirmation` records; dec-319's falsifier firing on its own closing commit; 19 "per dec-" commits vs 375 records |
| Discipline consultant | **evidenced with a confound** | 64/77 switch-now, **0 dismissals**; ≈19,600 tokens per dispositioned challenge; 70% of challenges were about the consult machinery itself; no inter-rater check (`td-102`) |
| Calibration log | **plausible-unmeasured as a calibration instrument; evidenced as a learning journal** | 0/85 rows ever used `over-calibrated`/`under-calibrated`; 93% match against CA02's 60% threshold — cannot fire; the prose is a skill-genesis harvest source |
| Sentinel | evidenced for finding generation; unmeasured for resolution | 509 findings / 53 runs; grade B → B while the corpus grew ~10×; finding identity not logged |
| Observability WAL | **no evidence of payoff** | one reader, no output ever produced; a wrong budget number sat in it for 23 sessions |
| `skill-genesis` adopt loop | **no evidence of payoff** | 15 proposals, 3 runs, 68 days, **0 dispositioned** |
| Non-blocking commit reminders | **no evidence of payoff — because unobservable**, not because useless | 0 WAL rows, 0 calibration mentions record a fire; every gate is a fail-open printer |
| Truncation-recovery machinery | no evidence for the machinery; evidenced for the discipline | `RECOVERY_LOG.md` exists nowhere; both documented recoveries were manual |
| Parallel implementers | **no evidence of payoff, and the only mechanism the external evidence predicts against** | documented index races; no credited quality gain |

The joint reading: *the cost of context is measured and significant; the benefit is unmeasured and, where measured, indistinguishable from zero.* That does not prove the benefit is zero. It means the burden of proof sits on the ceremony — and it means no simplification in §6 may cite the calibration log's retrospective or the consult ledger as its quality guard until those instruments have variance. Guards must be executable checks, evals, or read-frequency telemetry.

## 5. Weaknesses

Each weakness names its measured cost (§3), the quality property it currently guards, and the roadmap items that address it.

### W1. The always-loaded set is priced at ×1 and paid at ×7
The `agent-crafting` skill states that subagents "do not inherit rules or CLAUDE.md" (`skills/agent-crafting/SKILL.md:151`); a live spawn shows 21,287 tokens of exactly that content. The claim is the stated justification for the agent corpus's sizing and for restating rule content inside agent prompts; it also hides the blast radius of every always-loaded addition. Half of what every spawn inherits is two documents (coordination protocol 6,790 tokens, ADR conventions 4,514). Guards: behavioural contract, tier selector, artifact paths. → P0.3, P1.2–P1.5.

### W2. Preloaded skills, not rules, are the largest lever — and they bypass progressive disclosure
240,647 tokens of skill bodies are injected by frontmatter into every spawn of their agents; 12 demand-loads in 18,042 rows. The interface quartet is preloaded by the implementer, verifier, promethean, interface-designer and doc-engineer while a dedicated `interface-designer` agent exists for that domain. Guard: domain expertise at the step that needs it — which description-match activation provides on relevance. → P1.1.

### W3. Skill discovery is silently truncated
Claude Code caps combined skill descriptions at ~1% of the context window in characters, drops the least-used first, and does not document whether a name-only skill can still auto-activate ([skills.md § "Skill descriptions are cut short"](https://code.claude.com/docs/en/skills.md), fetched 2026-09-06). Praxion's 62 descriptions total 35,886 chars; ~40 of 62 were name-only in this session. The discovery stage of Praxion's load-bearing pattern is failing for most of the corpus, invisibly. Guard: skill activation by relevance. → P0.2, P1.12.

### W4. Artifact and spawn overshoot
19 named artifacts per run against a peer ceiling of 3–4; `PROGRESS.md` write-only; the designed 5-spawn Standard pipeline observed at 28–48 spawns with no budget, cap or warning; 65% of logged work at the two heaviest tiers. Guards: stage separation, handoff artifacts the verifier and reconciler actually read. → P1.7, P2.3, P2.4.

### W5. Governance rate and machinery outrun their read path
11.7 ADRs/week; 68% `architectural` with 14–43% plausibly mis-categorised, each carrying a mandatory Disconfirmation block; 8,504 LOC of machinery that is the most-churned code in the repo; a 48,500-token index whose access rule is "don't". The corpus *does* constrain later decisions (13 re-affirmations, one regression catch) — the mechanism earns its keep; its rate and its read path do not. → P2.2.

### W6. Bookkeeping dominates version control and the WAL cannot answer its own question
53.1% of commits touch only `.ai-state/`; the WAL is 12% of commits, carries no cost fields, records no reads, and has one reader whose output has never existed. → P0.4, P0.5, P2.5.

### W7. Zero-variance instruments are being used as quality guards
0/85 calibration errors, 0/77 consult dismissals, a 93% match rate against a 60% alarm, a budget hook wrong by 68% for five weeks. The instruments exist to detect exactly the failure the roadmap is about and cannot record it. → P0.1, P0.6, P2.6, P2.8.

### W8. Canonical text is copied, not pointed, and synced by an LLM
Seven canonical texts at 3–16 sites; 5 with no sync; sentinel EC06 exists solely to police one duplicate and reads a gitignored generated file. → P1.5, P2.10. (Registered objection, from the context audit: the ~1,750 tokens of agent-body boilerplate — contract line ×13, PROGRESS instruction ×11, task-slug ×10 — is *correctly* duplicated because plugin agents must be self-contained; do not consolidate that part.)

### W9. Growth has no ratchet
The last budget pass (2026-05-12, "relocate-don't-delete") succeeded and the surface reflated by a quarter in four months. A ceiling check cannot see a trend. → P0.2.

### W10. Hook-delivered rules never reach subagents
`agent-model-routing.md` and `git-conventions.md` are `install: hook-deliver`; SessionStart does not fire for subagents; 15 agent prompts cite the routing rule they structurally cannot receive, and the commit-authoring implementer never sees the staging discipline. → P1.6.

## 6. Improvement roadmap

Conventions: **Cost removed** cites §3; **Guard** names the executable check, eval, or telemetry that would catch a regression in the behaviour the removed text bought — never a self-graded log (§4); **Conf** H = mechanical, behaviour preserved by construction · M = judgment, guarded by a named check · L = judgment, no guard exists; **Tier** is the calibration tier the implementing task would take. Items are ordered within a phase by (cost removed × confidence). Dependencies are explicit; nothing in Phase 1 lands before P0.1–P0.3.

### Phase 0 — Instruments and corrections (no simplification is measured until these land)

| ID | Intervention | Artifact touched | Cost removed / gap closed | Guard | Conf | Tier |
|---|---|---|---|---|---|---|
| **P0.1** | One budget number: `hooks/measure_context_surface.py` imports `always_loaded_files()` and `count_tokens()` from `scripts/measure_token_budget.py`; de-duplicate plugin-cache copies | 1 hook | A 68%-wrong instrument in every session since 2026-09-02 | test asserting hook figure == gate figure | H | Direct |
| **P0.2** | Bring the listing under governance + install the ratchet: `measure_token_budget.py` reports skill/command/agent description tokens as a second line item; add a trailing-30-day growth check that fails when byte delta exceeds a budgeted allowance; report `/skill-doctor`'s per-skill cost and truncation state at sentinel cadence | 1 script, sentinel catalogue | 16,713 ungoverned tokens; a ceiling breach ~11 days out | the checks themselves; sentinel T-dimension | H | Lightweight |
| **P0.3** | Correct the inheritance model: `agent-crafting/SKILL.md § Constraints` — subagents inherit all `CLAUDE.md` files and every symlinked rule, not hook-delivered rules, parent skills, or history; add the multiplier corollary. Amend `CLAUDE.md § Critical conventions` — no *MCP* memory tools exist; the harness `memory:` directory is live. Strike `10-dimension` from the routing table | 2 skill/CLAUDE sections, 1 rule word | The false premise under which the agent corpus was sized; a live contradiction that disables the recall arm of the learning loop | new sentinel EC check asserting the inheritance claim against a live spawn record | H | Direct |
| **P0.4** | Cost and read telemetry: capture `SubagentStop` usage fields (tokens, duration, model) into the existing `agent_stop` rows; add `Read\|Grep\|Glob` (file path only) to the observation matcher; add one `gate_fire` observation call in `_hook_utils` invoked from each commit gate's exit path | `capture_memory.py`, `_hook_utils.py`, 5 gates | Closes F12 (still open since 2026-09-02), the read-back gap, and makes every gate falsifiable (today: 0 recorded fires, 0 evidence either way) | `project_metrics` collector reads the new fields; a test per emitter | H | Lightweight |
| **P0.5** | The WAL leaves git: `.ai-state/observations.jsonl` gitignored (path unchanged so readers keep working); a Stop hook emits one compact committed row per session to `.ai-state/observations_summary.jsonl` (session, spawns by agent type, tokens, duration) | `.gitignore`, 1 hook, dashboard reader | 146 commits / 120 d, a rewrite footprint, the documented worktree-merge race; without this, P0.4's `Read` events would balloon a committed file | `reconcile_pipeline_state.py` tests (local WAL); dashboard empty-state | M | Lightweight |
| **P0.6** | Calibration verdict with variance: the retrospective's first token becomes a required enum (`correct` / `over-calibrated` / `under-calibrated`) written by the **verifier** (or, at Direct/Lightweight, by the pre-commit digest) — not by the agent that chose the tier; `check_calibration_coverage.py` validates the enum | verifier output contract, 1 check, log header | An instrument that has never recorded the error it exists to detect (0/85) | the check; sentinel CA02 becomes able to fire | M | Lightweight |
| **P0.7** | Eval baseline for the context layer: one `/eval-praxion` scenario set (5 seeded tasks: spawn selection, UI-touching step, ADR authoring, commit staging, a Lightweight fix) run at HEAD before Phase 1 and after each slice | `eval/` scenarios | P20 — every cut below becomes a measured delta instead of a reasoned guess | the baseline | M | Standard |

### Phase 1 — Mechanical, high-confidence cuts (each lands as its own small task; ~−154,000 tokens per Standard pipeline in total, 80% from the first eight)

| ID | Intervention | Artifact touched | Cost removed | Guard | Conf | Tier |
|---|---|---|---|---|---|---|
| **P1.1** | Trim `skills:` preloads: implementer −{`web-ui-design`, `tui-design`, `agentic-interface-design`, `api-design-craft`}; verifier − the same four; systems-architect −{`mcp-crafting`, `communicating-agents`, `agentic-sdks`} with the three named in its Phase 3 conditional ("if the design introduces an agent or MCP surface, load …"); name the four interface skills in the implementer's language-context section | 12 YAML lines + 2 prose lines | **−36,278 tokens per Standard pipeline** (implementer ×2 24,090; verifier 12,045; architect 12,143) — the highest tokens-per-line ratio in the audit | P0.7 UI-step scenario; verifier Phase 5 convention check; sentinel AC dimension for the architect | H (implementer, verifier) / M (architect) | Direct |
| **P1.2** | Relocate the ADR frontmatter table, fragment schema, four relation protocols and finalize prose from `rules/swe/adr-conventions.md` into `software-planning/references/adr-authoring-protocols.md`; keep the `architectural` test and a 4-row relation table + pointer. **Ships together with** an explicit citation of the protocols file in `systems-architect.md` and `implementation-planner.md` (today neither cites it — reachability gap) | 1 rule, 1 reference, 2 agent lines | −2,250 tokens × 7 = **−15,750 per pipeline** | `scripts/adr_health.py`, sentinel DL/DH dimensions, `test_finalize_adrs.py` validate every written ADR regardless of where the schema is documented | H | Lightweight |
| **P1.3** | Relocate both directory trees from `rules/swe/agent-intermediate-documents.md` into `software-planning/references/artifact-inventory.md`; keep the lifecycle distinction, the task-slug convention, "never commit `.ai-work/`", the fragment-file rule (~350 tokens) | 1 rule, 1 reference | −1,300 × 7 = **−9,100** | sentinel C-dimension; `check_p05` handoff-doc check | H | Direct |
| **P1.4** | Coordination-protocol diet: the 11 conditional rows of the pipeline-rules table become one *artifact-presence* trigger sentence + existing pointer each; `Available Agents` → two columns (output path · Bg-Safe — the Purpose column is the harness listing); `Proactive Agent Usage` keeps the 6 ordering bullets, drops the 13 that restate a single agent's description; `Conversation Checkpoints` keeps names + firing conditions, procedure moves to `coordination-details.md` | 1 rule, 1 reference | −2,450 × 7 = **−17,150** | sentinel X-dimension + `validate_references.py --strict`; P0.7 spawn-selection scenario; every checkpoint *name* and *trigger* stays resident | M | Lightweight |
| **P1.5** | CLAUDE.md pair diet (excluding the Principles — §10 D1): delete the deliverables block (its footnote already names the authority) **and retire sentinel EC06 with it**; the Behavioural Contract section → one sentence naming the rule; delete `## When NOT to use the full pipeline` (the selector is resident); repository layout → the 5 non-obvious rows; onboarding-contract and Obsidian blocks → two lines + pointers to `docs/onboarding.md` / `docs/obsidian-integration.md`; Learning Loop → 4 lines, delete the removed-backend clause; Ecosystem table → 3 bullets; `rules/CLAUDE.md § Token Budget` history → `rule-crafting` | `CLAUDE.md.tmpl`, `CLAUDE.md`, `rules/CLAUDE.md`, sentinel catalogue | ≈ −1,900 × 7 = **−13,300**; one `L`-typed sentinel check retired from every sweep | `sync_canonical_blocks.py --check`; sentinel BC dimension; the Obsidian deny-list is enforced by `.claude/settings.json`, not prose | H | Lightweight |
| **P1.6** | Fix hook-deliver reachability: `agent-model-routing.md` keeps only the Tier Table resident (routing is an orchestrator-only decision, so hook delivery is correct) — delete the 15 agent-frontmatter comments pointing to a rule subagents cannot see; cite `git-conventions.md § Staging Discipline` from the implementer's commit sub-step (+20 tokens) | 1 rule, 15 agent lines, 1 agent line | −1,350 (orchestrator); closes a real gap for the commit-authoring agent | model-routing sentinel check; commit-gate hooks | H | Direct |
| **P1.7** | Retire the `PROGRESS.md` write mandate: remove the Progress Signals block from all 17 agent definitions and the `PROGRESS_<agent>.md` fragment-merge plumbing; the completion handshake stays exactly what the reconciler already implements (terminal marker + `WIP.md` checkbox); background spawns rely on native task notifications | 17 agents, reconciliation reference, `agent-pipeline-details.md:208` | One write per phase per agent across every pipeline; ~11 × 150-token duplicated instruction blocks | `reconcile_pipeline_state.py` tests (unchanged inputs); completion-handshake clause rewritten to name `WIP.md` only | H | Lightweight |
| **P1.8** | Drop `memory: user` from the agents that never write memory (after P0.3 resolves the contradiction; P0.4 telemetry shows which types persist — expected: keep on sentinel, skill-genesis, promethean, researcher) | ≤13 agent frontmatter lines | −4,478 × ~5 spawns = **−22,390 per pipeline** | re-add on evidence from the memory-write telemetry | M | Direct |
| **P1.9** | Agent-body relocations: verifier `§ Phase 12.5 Rework Manifest` + `§ Rework Worktree Spawn` → `software-planning/references/rework-manifest.md` (keep trigger + column names); verifier `§ With Skill-Genesis` → one line; systems-architect `§ Phase 2.5 Pre-Refactor` → keep the entry test, point to `coordination-details.md` | 2 agents, 1–2 references | ≈ −5,150 per relevant spawn | sentinel P and PR dimensions | M | Lightweight |
| **P1.10** | Delete the duplicate worktree guard and banner (`worktree_guard.py`, `inject_worktree_banner.py`, tests; ~56 KB) in favour of the native isolation checks; keep `/merge-worktree`'s finalize + `.ai-state/` reconciliation and the tier→isolation policy row | 2 hooks + tests, `hooks.json` | 2 hooks, ~56 KB maintained code; one fewer subprocess pair per Write/Edit | native four-check isolation (cannot be turned off); note: the recorded heredoc/`sh -c` false positives are native and remain | H | Lightweight |
| **P1.11** | SessionStart chain: guard the 8 zero-emitting hooks behind cheap shell pre-checks (the pattern `commit_gate.sh` already uses) or fold them into one dispatcher process; run hooks with a non-shim interpreter path | `hooks.json`, 1 wrapper | 3.7 s → <1 s per session start; ~70% of every-call hook CPU (pyenv shim) | hook tests; gate-liveness checks | H | Lightweight |
| **P1.12** | Skill-description diet: every `description` cut to name + trigger clause (target ≤300 chars; per-skill hard cap is 1,536); `skillOverrides: name-only` for skills that are only ever reached by agent preload or a command; retire or merge the 10 skills never preloaded, never named, and (after P0.4) never read; set `disable-model-invocation: true` on the side-effecting commands (removes their descriptions from model context at zero behavioural cost) | 62 `SKILL.md` frontmatter, ≤15 commands, settings | ~−2,500 tokens × 7; **restores description-based discovery for the whole corpus** (W3) | `/skill-doctor` before/after; P0.7 spawn-selection scenario; a check that the listing fits the 1% budget of a 200k window | M | Lightweight |

Projected after Phase 1 (context-review §Projected Totals): governed always-loaded **24,590 → ~13,500 tokens (54% of ceiling, ~26 months of headroom at the observed growth rate)**; true always-resident 41,303 → ~27,700; Standard-pipeline resident context **422,499 → 281,432 (−33%)**, mean per spawn 70,417 → 46,905; sentinel sweep 74,449 → ~44,300.

### Phase 2 — Structural economies (Standard tier each; sequenced after Phase 0's telemetry has one month of data)

| ID | Intervention | Cost removed | Quality property preserved → guard | Conf |
|---|---|---|---|---|
| **P2.1** | **Sentinel checks as scripts.** Write `scripts/check_<id>.py` for the 56 script-less `A`-typed rows (start with the six largest: P03, F11, DL06, T03, DH05, AC13 ≈ 40% of the saving); each row's Pass column becomes `Run scripts/check_X.py --json`; move rationale into docstrings; then split the residual `L` catalogue into `skills/ecosystem-audit/references/<dimension>.md` so a scoped sweep loads only its lens | −12,000 tokens per sweep from scripting, further ~−6,000 from the split; `sentinel.md` 31,971 → ~14,000 tokens | every `A` verdict becomes deterministic and testable → one canary test per script asserting its golden bad-case fires (`test_check_p06_task_brief.py` pattern); `gate-liveness.md`; sentinel V04 | H |
| **P2.2** | **ADR economy.** (a) A mechanical `architectural` gate in `check_adr_frontmatter_promotion.py`: the category requires a named component path (in `affected_files` or a new `component:` field) or is downgraded — no Disconfirmation block without it; (b) default **one ADR per pipeline** — the load-bearing decision; other decisions go to `LEARNINGS.md ### Decisions Made` and the ledger, promotable later; (c) an ADR body budget (≤ ~900 tokens; `Considered Options` as a 3-row table); (d) declare the finalize/relation machinery feature-complete — no new relation types without a re-affirmation-rate argument; (e) `query_adrs.py` is the read interface; the index stays generated-only | 36–110 Disconfirmation blocks avoided going forward (mean 1,455 B each); 11.7/week → a rate the read path can absorb; the #2/#3/#5 churn hot-spots stop growing | decisions still constrain later work → re-affirmation rate and "per dec-" citations per month as the read-back metric (13 and 19 today); `adr_health.py`; DH01–06 | M |
| **P2.3** | **Spawn budget per tier** in the coordination protocol: Standard ≤ 8 spawns, Full ≤ 16, with the orchestrator reading the running count from P0.4 telemetry and re-tiering (or splitting the task) above budget; **action-parallelism off by default** — a single implementer in sequence, parallel spawns only for intelligence (research lenses, review, consult), parallel implementers only on disjoint file sets with pathspec-scoped commits and an explicit calibration note | The 28–48-spawn sessions; 2.26M resident tokens in one session; documented index races | stage separation and independent review remain → spawn count per task slug in the summary WAL; verifier PASS rate; P0.6 enum | M |
| **P2.4** | **Artifact floor per tier.** Standard mandates `TASK_BRIEF`, `SYSTEMS_PLAN`, `IMPLEMENTATION_PLAN` with `WIP` checkboxes merged into it, `LEARNINGS`, `TEST_BASELINE`, `VERIFICATION_REPORT`; conditional on an artifact-presence trigger: `SPEC_DELTA`, `CONTEXT_REVIEW`, `INTERFACE_DESIGN`, `TRANSACTIONS_DESIGN`, `TEST_RESULTS` (test-engineer paired steps only); Full-only: `traceability.yml`, spec archival | 19 → 6 mandated documents at Standard; the "repetitive with each other" overlap Böckeler names | verifier rubric sourced from the plan's acceptance criteria (unchanged); `reconcile_pipeline_state.py` reads the merged plan; `check_p06` | M |
| **P2.5** | **Bookkeeping load.** `doc_manifest.yaml` regenerated at finalize/release only (136 touches / 120 d); ledger row prose capped by schema (rows >2 KB today); `DECISIONS_INDEX.md` regenerated at finalize only (already) — target: commits touching only `.ai-state/` **< 25%** | 53.1% of commits | durable intelligence still committed → `check_state_ledgers`; manifest freshness check at release | H |
| **P2.6** | **Calibration log identity** (user decision D2): keep the retrospective as the learning journal it demonstrably is; the P0.6 enum becomes the instrument; retire CA02 as written (it cannot fire) in favour of a check on the enum distribution | 25,000 tokens of prose stops masquerading as a measurement | tier accuracy becomes measurable → CA02 rewritten over the enum | M |
| **P2.7** | **Learning-loop adopt path** (user decision D3): either `/skill-genesis-review` runs at sentinel cadence (or as a Routine) and each report carries a disposition deadline, or the harvest is retired | 3 opus-tier harvests with 0 dispositions | the flywheel (a differentiator) actually turns → proposals dispositioned per month | M |
| **P2.8** | **Consult ledger falsifier.** The verifier re-reads a random 10 of the 64 `switch-now` challenges blind to the disposition and records agree/disagree (n=10, wide but non-degenerate); the "non-degenerate dismissal rate" criterion's reversal clause is honoured | 1.16M tokens across 7 consults with an unmeasured hit rate | consult value becomes falsifiable → inter-rater agreement (closes `td-102`) | M |
| **P2.9** | **Architecture documents as views** (user decision D4): stop mandating a full `DESIGN.md` + `docs/architecture.md` update per pipeline; partition per subsystem so a pipeline updates only its partition; generate the component map from the LikeC4 model (AaC already exists) — the prose keeps rationale and "conventions that differ from tool defaults", the classes the evidence says are read | 118 + 79 commits / 120 d; ~45k + ~23k tokens no agent can read whole | code↔DSL↔ADR consistency → `architect-validator` triangle check; P0.4 read-frequency per partition | M |
| **P2.10** | **Single-source the canonical texts.** Extend `sync_canonical_blocks.py` to the behavioural contract (12 sites) and the task-slug / return-contract paragraphs, or replace copies with pointers; retire EC06 (done in P1.5) | 5 of 7 duplicated texts with no sync | conventions reachable everywhere → `sync_canonical_blocks.py --check` | H |

### Phase 3 — Compete: best-in-class items that also reduce burden

| ID | Intervention | Why it is best-in-class *and* an economy | Guard |
|---|---|---|---|
| **P3.1** | **Intentional compaction with a utilisation band.** Each phase transition (research → architecture → planning → implementation) becomes a fresh-window handoff seeded solely by the upstream artifact; a stated utilisation band (e.g. hand off before ~50%); `PostCompact` restores `.ai-work/` state. Praxion already writes every handoff artifact the practice needs and never uses them to reset the window (P05 — the highest-leverage under-build per unit of effort) | Context-rot evidence (Claude models show the largest focused-vs-full gap); zero new artifacts, zero new machinery | tokens per phase from P0.4; verifier PASS rate |
| **P3.2** | **Pipeline-as-code.** Encode the *mechanical* fan-out (parallel research lenses, verify-per-finding, multiplicity fan-out) as `Workflow` scripts, one per checkpoint-bounded stage, so intermediate results stay in script variables and the always-loaded coordination rule shrinks to tier selector + checkpoint names + pointer. Keep the prose protocol as the portable (Codex/Cursor) fallback | Harness-engineering thesis made literal: the orchestration becomes a program, not a 26 KB instruction; deterministic and resumable | completion-handshake semantics preserved in the script; `resume-pipeline` |
| **P3.3** | **Continuous AI for the audits.** Sentinel, `/project-metrics`, `/skill-doctor`, and `/skill-genesis-review` on a schedule — Routines (Claude-only, preview) or gh-aw (vendor-neutral); the self-healing loop already covers the failure path | Seven peers ship it; the operator's ceiling is wall-clock; the audits stop competing with interactive sessions for context | `SENTINEL_LOG.md` cadence; P2.7 dispositions |
| **P3.4** | **Silence on success.** Implementer and test-engineer contracts default test invocations to failures-only output; `TEST_RESULTS.md` records failures and counts, full output only on red | P19; HumanLayer's 4,000-lines-of-passing-tests failure is the shape of today's `TEST_RESULTS.md` | verifier reads counts + failures; `TEST_BASELINE` discrimination unchanged |
| **P3.5** | **Cost dashboard.** From P0.4/P0.5: tokens per tier, per agent, per pipeline; the calibration selector's "is Standard worth 4× Lightweight?" becomes answerable (F12) | The one instrument that separates "the scaffold helps" from "19% slower" | the metrics report |
| **P3.6** | **Mutation testing as the sensor for agent-written tests** (Radar *Trial*; F10 gap) — opt-in per project | The only sensor built for validating agent-authored tests; complements, not replaces, the verifier | mutation score in the metrics report |
| **P3.7** | **Native subsumptions of lower priority**: run `claude plugin validate` beside `validate.py`; `/skill-doctor` at sentinel cadence; auto-memory as the personal store (D5); `PostCompact` restore | Zero-maintenance capability; each is additive | existing validators |
| — | Delivery metrics (DORA keys) — the prior roadmap's P2, unchanged, cross-referenced here | The falsifier for the whole thesis | — |

### Sequencing

Phase 0 first and whole (one to two weeks of Lightweight tasks; P0.7 is the single Standard task). Phase 1 in slices, each measured by P0.7 before the next: P1.1 → P1.2+P1.3+P1.6 → P1.4+P1.5 → P1.7+P1.8+P1.9 → P1.10+P1.11 → P1.12. Phase 2 after one month of P0.4 data (P2.1 and P2.5 can start earlier — they need no telemetry). Phase 3 after Phase 2's spawn budget and artifact floor are live, since compaction handoffs and pipeline-as-code encode the *new* shape, not the old one. Every slice appends a calibration row with the P0.6 enum and a before/after line from `measure_token_budget.py`.

## 7. Deprecation and cleanup

| Item | Reason | Replacement |
|---|---|---|
| `PROGRESS.md` per-phase write mandate + `PROGRESS_<agent>.md` merge plumbing | write-only across the whole system | terminal marker + `WIP.md` checkbox (already what the reconciler reads) |
| `hooks/measure_context_surface.py` divisor and 14-file basis | wrong by 68% for 23 sessions | import from the authority (P0.1) |
| Sentinel EC06 | polices a duplicate that P1.5 deletes | none needed |
| Sentinel CA02 as written | 93% vs a 60% threshold — cannot fire | enum-distribution check over P0.6 |
| `worktree_guard.py`, `inject_worktree_banner.py` | native isolation is a strict superset | native checks; keep `/merge-worktree` semantics |
| 15 agent-frontmatter comments citing `agent-model-routing.md` | the rule is hook-delivered; subagents never receive it | delete; routing stays orchestrator-only |
| `10-dimension` in the routing table | the sentinel forbids restating its size; it has 22 | strike the word |
| `skills/mcp-crafting/references/v1-legacy.md` | the one genuine orphan in 237 reference files | delete |
| `capture_memory.py` filename | legacy name after `dec-225`; rename when P0.4 touches the registration sites anyway | `capture_observations.py` |
| The METR "19% slower" citation as an anti-ceremony argument | no scaffolding arm; 2026 follow-up reversed and unreliable | cite both or neither (watchlist corrected) |
| **Not deprecated** — the non-blocking commit reminders, the truncation-recovery script, the consult mechanism, the sentinel | "no evidence of payoff" here means *unobservable*, not useless; deleting on absence of evidence would be the inference error §4 warns about | P0.4 makes them observable; revisit with data |

## 8. Quality metrics

| Metric | Now | After Phase 1 | Target (Phase 2–3) | How measured |
|---|---|---|---|---|
| Governed always-loaded tokens | 24,542 (98.2%) | ~13,500 (54%) | ≤ 15,000 with a growth check | `measure_token_budget.py` |
| True always-resident incl. listing | ~41,300 | ~27,700 | ≤ 25,000 | P0.2 second line item |
| 30-day growth of the always-loaded set | +43 tok/day | — | ≤ 0 net per quarter | P0.2 ratchet |
| Skills with a visible description in a 200k-window session | ~22 of 62 | — | 62 of 62 | `/skill-doctor`; P1.12 check |
| Resident context per Standard pipeline (6 spawns) | 422,499 | 281,432 | ≤ 250,000 | context-review method; P0.4 actuals |
| Spawns per Standard pipeline | 28–48 observed | — | ≤ 8 (Full ≤ 16) | P0.4/P0.5 summary rows |
| Mandated artifacts at Standard | 19 named | 18 | 6 | artifact inventory |
| Commits touching only `.ai-state/` | 53.1% | — | < 25% | `git log --name-only` |
| ADRs per week / `architectural` share | 11.7 / 68% | — | rate the read path absorbs; share = falsifier pass rate | `adr_health.py`; re-affirmation count |
| Calibration rows with a non-`correct` enum | 0 / 85 | — | non-zero, written by the verifier | P0.6 |
| Gate fire/block events observable | 0 | — | every gate | P0.4 `gate_fire` rows |
| Agent spawns with tokens/duration/model | 0 / 3,492 | — | 100% | P0.4 |
| `sentinel.md` tokens | 31,971 | 31,971 | ≤ 14,000 | `wc -c` / tokenizer |
| Skill-genesis proposals dispositioned | 0 / 15 | — | all, within one cadence | P2.7 |
| Verifier PASS rate; light-review catch rate | evidenced, uncounted | — | unchanged or better while the above fall | P0.7 baseline; calibration enum |

## 9. Guiding principles for execution

1. **Burden of proof on the ceremony.** Cost is measured and significant; benefit is unmeasured. A mechanism that cannot show a reader, a fire, or a catch is a relocation candidate — but *absence of evidence* is grounds to instrument, not to delete (§7, last row).
2. **Relocate before delete; instruction before overview.** The evidence supports moving content from always-loaded to on-demand (cache tokens, test runs) and keeping imperative text; it does not support deleting conventions. Overviews and inventories go first; contracts and triggers stay resident.
3. **Price everything at ×7.** A token added to a symlinked always-loaded file is paid by the orchestrator and by every spawn. The `agent-crafting` correction (P0.3) is the highest-leverage zero-token change in this document.
4. **A quality guard is executable or it is not a guard.** No simplification cites the calibration retrospective, the consult ledger, or any self-graded log as its guard until P0.6/P2.8 give them variance. Guards are `check_*` scripts, tests, eval scenarios, or read/fire telemetry.
5. **One number per measurement.** Four mutually inconsistent budget bases have now coexisted in this repository. Import, never reimplement (P0.1); bring every ungoverned surface under the same instrument (P0.2).
6. **Intelligence in parallel, actions in sequence.** Fan out research, review and consults; keep writes single-threaded unless file sets are provably disjoint (P2.3).
7. **Protect the differentiators by making them cheaper, not rarer.** Tiers, deterministic checks, the verifier and light-review, the behavioural contract, the ledger, and ADRs-as-constraint survive every phase; the roadmap changes their cost, their rate, and their read path.
8. **Portability is spent, not free.** Skills are the portable asset; each native-feature adoption (worktrees, workflows, memory) is recorded with what stays portable (§2.3).
9. **A ratchet, not a pass.** The last budget pass reflated by a quarter in four months. Growth checks, not ceiling checks.

## 10. Decisions left to the user

| # | Decision | What the evidence says | What the roadmap recommends |
|---|---|---|---|
| **D1** | Compress the seven-principle philosophy prose in `~/.claude/CLAUDE.md` (1,268 tokens × 7; four principles are essays that already end in a skill pointer) | No check, test, or eval can detect a degradation in design judgment — the only `L`-confidence item in the plan | Present, do not action by agent. If compressed: 2 lines + pointer each, worldview prose preserved in `docs/philosophy.md` |
| **D2** | Is the calibration log a calibration instrument or a learning journal? | It has never recorded a tier error and its prose is the richest learning source in the repo | Both, split: enum by the verifier (instrument), prose retained (journal); retire CA02 as written |
| **D3** | Is `skill-genesis` abandoned or blocked? | 0/15 dispositioned in 68 days | Schedule the review (P2.7) for one cadence; retire the harvest if still 0 |
| **D4** | Do `DESIGN.md` and `docs/architecture.md` become partitioned, generated views? | Overviews are inert for agent navigation; both are among the six most-churned files | Yes for the component map (LikeC4 → generated); prose keeps rationale |
| **D5** | Personal learning store on native auto-memory, or team-shared via committed artifacts? | Auto-memory is machine-local and ungitted; `LEARNINGS.md` + skill-genesis is the shareable half | Both: auto-memory for gotchas (already live, 43 entries), committed skills for the shareable half |
| **D6** | Pipeline-as-code on the `Workflow` tool (Claude-only, no mid-run input) or keep the prose protocol as canonical? | Deterministic, resumable, results out of context; checkpoints must sit at workflow boundaries | Adopt for mechanical fan-out only; prose remains the portable canonical form |
| **D7** | ADR rate default: one per pipeline, others to `LEARNINGS`/ledger? | 11.7/week, 375 in 180 days, read path at 48.5k tokens | Yes, with the mechanical `architectural` gate |
| **D8** | Retire or instrument the observability WAL? | 12% of commits, no cost fields, one reader with no output | Instrument (P0.4) and move out of git (P0.5); retire if still unread after a quarter |

## 11. Orchestrator priors, scored

Recorded before any lens result (`.ai-work/process-economy-roadmap/ORCHESTRATOR_HYPOTHESES.md`), scored at synthesis: **confirmed** H1 (always-loaded is pipeline procedure — and priced ×7, not ×1), H2 (agent prose belongs in references — but preloaded skills are the bigger lever), H3 (ADR rate and machinery), H5 (artifact overshoot; `TEST_BASELINE` corrected to load-bearing), H8 (philosophy prose — flagged L, deferred to D1), H9 (Standard over-shaped — the deeper fact is spawn count), H10 (duplication, worse than assumed), H11 (architecture docs, weakly evidenced), H12 (sentinel as prose catalogue), H14 (no baseline); **partial** H4 (WAL storage cost confirmed, per-call cost re-attributed to interpreter startup), H6 (hook no-ops confirmed, dispatcher is second to a non-shim interpreter), H13 (Workflow tool, with a structural blocker); **refuted** H7 (reminder injections are cheap, stderr-only, and protected by two lenses). Three findings were in no prior: the hidden listing surface and its truncation, the growth ratchet, and the false inheritance claim.

## 12. Methodology footer

- **Lenses** (ephemeral, `.ai-work/process-economy-roadmap/`): `RESEARCH_FINDINGS_practice-canon.md` (20 practices, 22 sources fetched 2026-09-06, 5 canon-internal contradictions), `RESEARCH_FINDINGS_peer-process.md` (15 peers, 16-row subsumption table, 7-entry divergence map), `RESEARCH_FINDINGS_cost-audit.md` (8 cost centres, 24-row cost ledger, 9 measurement gaps; all tokens by tokenizer), `RESEARCH_FINDINGS_evidence.md` (22 external claims graded, 14-row payoff table, 8 measurement gaps with cheapest instruments), `CONTEXT_REVIEW.md` (5 surfaces, 8 contradictions, 28-item consolidation plan with per-item guards), plus `BASELINE.md`, `ORCHESTRATOR_HYPOTHESES.md`, `SYNTHESIS_NOTES.md`, `TASK_BRIEF.md`.
- **Isolation**: no lens read a sibling; the orchestrator's priors were written before any result; two baseline errors were caught by lens re-derivation (process-commit share; hook-payload double count) and one open question was closed by the orchestrator during the wait (skill-listing truncation rule, docs fetched 2026-09-06).
- **Declined**: one `statistician` consult nomination (§1).
- **Side effect corrected**: the cost audit's hook timing appended 32 synthetic rows (`session_id: costaudit-test`) to `.ai-state/observations.jsonl`; removed before this document was written.
- **Grounding**: every number resolves to a command, file, or URL with fetch date; vendor throughput claims quarantined (Every's time-to-ship, Huntley's "$297", Anthropic's +90.2% internal eval).

### Decision log (this Spike)

- Praxion's process economy is compared against *practices and shapes*, not product features (the 2026-09-02 analysis owns the feature comparison).
- Simplification proposals require a measured cost and an executable guard; self-graded logs are not guards until they have variance.
- The tier system, deterministic checks, verifier/light-review, behavioural contract, ledger and ADRs-as-constraint are protected; the roadmap reduces their cost, not their presence.
- No production change was made; ADR fragments are left to the implementing pipeline (as in the 2026-09-02 Spike).

## Sources

Primary sources are cited inside each lens fragment with fetch dates and evidence class; the durable ones are transcribed into `.ai-state/LANDSCAPE_WATCHLIST.md` (industry-evidence section updated by this Spike). Load-bearing external sources: [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents); [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system); [Anthropic — Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents); [Claude Code — Best practices](https://code.claude.com/docs/en/best-practices), [Skills](https://code.claude.com/docs/en/skills), [Subagents](https://code.claude.com/docs/en/sub-agents), [Memory](https://code.claude.com/docs/en/memory), [Worktrees](https://code.claude.com/docs/en/worktrees), [Workflows](https://code.claude.com/docs/en/workflows), [Hooks](https://code.claude.com/docs/en/hooks); [Claude — Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [Manus — Context engineering for AI agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus); [Cognition — Don't build multi-agents](https://cognition.com/blog/dont-build-multi-agents); [HumanLayer — ace-fca](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md) and [Skill issue: harness engineering](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents); [Thoughtworks Radar vol. 34 — Agent instruction bloat](https://www.thoughtworks.com/radar/techniques/agent-instruction-bloat), [Progressive context disclosure](https://www.thoughtworks.com/radar/techniques/progressive-context-disclosure), [Spec-driven development](https://www.thoughtworks.com/radar/techniques/spec-driven-development); [Böckeler — Understanding SDD](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) and [Context engineering for coding agents](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html); [OpenAI / Codex — AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md); [mini-SWE-agent](https://github.com/SWE-agent/mini-SWE-agent); [Agentless (arXiv 2407.01489)](https://arxiv.org/abs/2407.01489); [Chroma — Context rot](https://www.trychroma.com/research/context-rot); [Evaluating AGENTS.md (arXiv 2602.11988)](https://arxiv.org/abs/2602.11988); [Do context files help coding agents? (arXiv 2607.27250)](https://arxiv.org/html/2607.27250v1); [MAST (arXiv 2503.13657)](https://arxiv.org/abs/2503.13657); [SWR-Bench (arXiv 2509.01494)](https://arxiv.org/html/2509.01494v1); [Bias in the Loop (arXiv 2604.16790)](https://arxiv.org/html/2604.16790v1); [Dissecting the SWE-Bench leaderboards (arXiv 2506.17208)](https://arxiv.org/abs/2506.17208); [METR 2025 RCT](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) and [METR 2026 design update](https://metr.org/blog/2026-02-24-uplift-update/); peer repositories and docs for Superpowers, Spec Kit, OpenSpec, BMAD-METHOD, Conductor, Kiro, Agent OS, gh-aw, OpenHands, Factory.ai, Cursor, Devin (fetched 2026-09-04/07). Prior in-repo analyses built upon: [personal-software-factory-analysis.md](personal-software-factory-analysis.md) (2026-09-02), [`docs/context-prj-comparison-2026-05-12/`](../context-prj-comparison-2026-05-12/README.md), `dec-092`, `dec-225`, `dec-248`, `dec-319`, `dec-352`, `td-080`, `td-102`.
