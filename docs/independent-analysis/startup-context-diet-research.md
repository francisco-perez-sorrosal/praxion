---
title: Scoping Every Resident Token — What Praxion Loads at Session Start, and How to Load Less Without Losing Guidance
type: independent-analysis
diataxis: explanation
audience: architect / maintainer
status: spike (research + measured ablations + ranked roadmap; no implementation)
date: 2026-10-11
head_sha_analyzed: 6f5c538a
claude_code_version: 2.1.296
author: Francisco Perez-Sorrosal (analysis run as a four-lens Spike with Claude Code — harness-native, research-literature and practitioner lenses collected independently, an internal corpus audit, and orchestrator ablations; reconciled here)
predecessor: skill-selection-code-mode-research.md (2026-09-23, uncommitted in the codemode-jev-research worktree)
evidence: research-evidence/2026-10-11-startup-context-diet/
verification_legend:
  MEASURED: real first-request input tokens from `claude -p --output-format json`, or a stated script, run 2026-10-11
  PROBED: a throwaway plugin or agent built to answer one harness question, run 2026-10-11
  VERIFIED: primary source fetched 2026-10-11
  SINGLE-SOURCE: one source, not independently confirmed
  ASSUMPTION: belief that shapes a recommendation; falsifier named where possible
---

# Scoping Every Resident Token

> **Scope.** A Spike. The question: what technique should Praxion adopt so that a new Claude Code session, and every subagent it spawns, starts with far less resident context — without losing the guidance that context exists to provide — for Praxion itself and for the projects it manages? The starting point is the 2026-09-23 code-mode spike (skill selection). This spike widens the lens to the **whole startup payload** and to the **quality** effect of what is resident, measures it by ablation, and checks every candidate lever against the harness as it ships today. The four evidence dossiers, the ablation script and the raw measurements are preserved under [`research-evidence/2026-10-11-startup-context-diet/`](research-evidence/2026-10-11-startup-context-diet/).

## 0. TL;DR

- **Where the 86K goes (MEASURED).** This repo's interactive first request is **85,759 tokens**. About 16K is the harness floor (system prompt and core tools), about 18K is the user's claude.ai connectors, about 2K is other plugins, and **about 50.6K (59%) is Praxion**: always-on rules and the two CLAUDE.md files (21.3K), the skill listing (10.6K, capped), the auto-memory index (8.0K), the agent listing (5.0K), hook injections (4.4K) and the likec4 MCP instructions (1.3K). In a managed project Praxion contributes about 38.5K before the project's own CLAUDE.md, and almost none of it is specific to that project.
- **The multiplier is the subagent.** Every spawn re-pays about **29.6K** of inherited CLAUDE.md, rules and MEMORY.md (PROBED), plus its own body and skill preloads: 28–56K per spawn before its first action. This spike's own four spawns paid about 213K of startup between them. A Standard pipeline (≤16 spawns) carries about 470K inherited tokens; a Full one (≤32) close to 1M.
- **Dollars are not the argument; attention is.** Caching makes the whole resident prefix cost about $0.7–$2.2 per 100-turn session (VERIFIED prices). The case for a diet is quality, cold-turn latency, window share on 200K models (resident context is **23% of a Haiku 4.5 window** before any work, and 72 of 89 Praxion skills lose their descriptions there), and the spawn multiplier.
- **What the evidence says, in two lines.** (1) Guidance that does not apply to the task is not free: it changes behaviour and costs quality or effort, and near-miss distractors hurt most — supported by ≥2 independent traditions. (2) Loading guidance on demand **fails at the trigger**: models often don't fetch what they need (Vercel: skill never invoked in 56% of cases; Praxion: 9 `Skill` activations in 67 main sessions, none ever by a subagent). A resident rule is not a followed rule either: the one controlled Claude Code study found a trivial always-applicable MUST rule followed only 55–68% of the time, decaying through the session.
- **So the best technique is not "retrieve more" — it is "scope, then push".** Give every unit of guidance an explicit **audience** (main session or a subagent role), **scope** (which projects) and **trigger** (always, file path, tool event, prompt intent, manual), and let *deterministic* channels deliver it at that moment: the harness's path-scoped loading (which since 2.1.288 also fires on Write/Edit), Praxion's hook bus (SessionStart, SubagentStart, Pre/PostToolUse, UserPromptSubmit) and enforcing gates. What stays resident is a small **kernel of constraints plus a routed index** whose every row says when to read its target. Model-initiated retrieval (skills, catalogue search, code mode) is kept for optional depth, never for guidance that must apply.
- **The single largest lever is available today (PROBED).** An agent with `omitClaudeMd: true` starts at **2,385 tokens instead of 31,985**, and a plugin `SubagentStart` hook still injects into it. "Drop the inherited rulebook, inject a role kernel" is mechanically ready for all 17 Praxion agents.
- **Code mode is the wrong tool for this question.** The harness already defers tool schemas: disabling tool search raises the first request from 67,988 to **109,842** tokens (MEASURED). Praxion's startup problem is *instructions and catalogues*, not tool definitions. Code mode's lasting idea — the context carries an index, not the library — survives as the routed index; its retrieval half inherits the trigger problem.
- **Projected effect (arithmetic on measured items; §8).** Praxion's main-session share falls from about 50.6K to about 29K in this repo, from 38.5K to about 21K in a managed project and to about 16K in a non-managed one; each spawn sheds about 23–27K. With the user-side connector toggle, this repo's first request goes from 85.8K to roughly 46K.
- **Gate everything on two instruments that don't exist yet:** a real-token startup-payload probe (the current budget guard counts with a stale tokenizer and reads 67% of its ceiling when the truth is **97.7%**), and a conditional-adherence eval that scores rule-following and trigger reliability per rule. No external study measured a process corpus like Praxion's; the magnitudes must be Praxion's own.

## 1. The problem, stated as behaviour

Behaviour wanted: *when an agent — the main session or a spawned subagent — works on a task, the guidance that applies to that task is in its context at the moment it acts, and little else is.* Three failure modes violate it:

1. **Off-task residency.** Guidance for situations that are not happening (ADR authoring during a typo fix, orchestration rules inside an implementer, ML rules inside a web project) sits in every request. The literature says this is not inert (§4).
2. **Invisibility.** Guidance that *does* apply is missing: a skill whose description was truncated out of the capped listing, a skill the model never thought to load, a rule that decayed out of attention by turn 40.
3. **Multiplication.** Whatever is resident in the main session's inherited channel is paid again in every spawn.

Diets that fix (1) by moving content behind model-initiated retrieval make (2) worse. The design has to fix (1) and (3) *without* creating (2).

## 2. Where the tokens go (MEASURED)

### 2.1 Ablations

One variable changed per run; real first-request input tokens (`input + cache_creation + cache_read`) from `claude -p "Reply with the single word ok." --output-format json`; Claude Code 2.1.296, Opus 5.5, 1M window. Headless runs have claude.ai connectors disabled, so they read lower than interactive. Script: [`ablation-run.sh`](research-evidence/2026-10-11-startup-context-diet/ablation-run.sh).

| Config | Real tokens | Δ | Reads as |
|---|---|---|---|
| Interactive session, Praxion repo | 85,759 | +17,771 | claude.ai connectors (Gmail, Calendar, Zapier, Claude Docs and its long server instructions), Chrome, interactive extras |
| **Headless baseline, Praxion repo** | **67,988** | — | |
| Empty directory, same user setup | 54,577 | −13,411 | repo-specific: MEMORY.md, project CLAUDE.md, repo hook output |
| Auto-memory off | 59,270 | −8,718 | the MEMORY.md index |
| Skills off (`--disable-slash-commands`) | 62,709 | −5,279 | the skill listing (budget-capped) |
| Praxion plugin disabled (global rules still load) | 53,913 | −14,075 | agent listing, Praxion's listing share, hook injections, Praxion MCP |
| Other plugins disabled | 66,292 | −1,696 | small: the listing is capped and Praxion refills it |
| No MCP servers | 65,239 | −2,749 | MCP names and server instructions |
| Tool search off (`ENABLE_TOOL_SEARCH=false`) | **109,842** | **+41,854** | what deferral already saves |
| Harness floor (empty dir, `--setting-sources ""`) | 15,812 | −52,176 | system prompt and core tools |

### 2.2 Praxion's share, item by item

From the internal audit ([`CONTEXT_REVIEW.md`](research-evidence/2026-10-11-startup-context-diet/CONTEXT_REVIEW.md) §1), counted with the current-generation tokenizer, which matches `/context` within 1%:

| Item | Channel | Tokens | Inherited by spawns? |
|---|---|---|---|
| `swe-agent-coordination-protocol` | global rule (symlink) | 6,985 | yes |
| `adr-conventions` | global rule | 3,554 | yes |
| user CLAUDE.md (generated from Praxion's template) | user memory | 3,897 | yes |
| project CLAUDE.md (Praxion repo) | project memory | 3,863 | yes |
| `agent-intermediate-documents` | global rule | 1,670 | yes |
| `rules/CLAUDE.md` (authoring notes for the rules tree, globalised by the installer) | global rule | 837 | yes |
| `agent-behavioral-contract` | global rule | 542 | yes |
| SessionStart: `agent-model-routing` + `git-conventions` | hook | 3,022 | no |
| SessionStart: decision context | hook | 1,334 | no |
| Agent listing (17 agents) | harness | 5,018 | no |
| Skill listing (72 model-invocable) | harness, capped at 1% of window | 10,580 | only agents with the `Skill` tool |
| likec4 MCP server instructions | plugin MCP | 1,332 | — |
| MEMORY.md index | harness | 7,978 | **yes** (PROBED; the docs say no) |
| **Total** | | **50,612** | ~29.6K |

### 2.3 Per spawn

- Inherited: the CLAUDE.md surface (21.3K) plus MEMORY.md (8.0K). PROBED: the same agent starts at 31,985 tokens normally and 2,385 with `omitClaudeMd`.
- Plus the agent's body (3K–35K; sentinel is 34.7K) and its `skills:` preloads (0–25K; the roster totals **207,564**, down from 240,647 at the prior spike because `external-api-docs` was retired).
- Observed this spike: researcher spawns started at about 50.0K, the context-engineer at 63.5K.
- A subagent receives the skill listing **only if it has the `Skill` tool** (PROBED). Only `discipline-consultant` declares it, so the listing is mostly a main-session cost.

### 2.4 Managed and non-managed projects

- A measured managed project (`crvntx`) receives about **38.5K** Praxion-originated tokens before its own CLAUDE.md: global CLAUDE.md and rules 17.5K, hook rules 3.0K, four canonical blocks 1.1K, listings and MCP instructions 16.9K. Nothing in it is specific to that project.
- About 100 directories under `~/dev` have no `.ai-state/` and still receive the global CLAUDE.md, every symlinked rule and the likec4 instructions. Praxion taxes every Claude Code session on the machine.
- The per-project blacklist (dec-167, `.claude/praxion-rules.yaml`) reaches only the two hook-delivered rules; the five symlinked rules are `core: true`.
- Two ML rules (`ml/eval-driven-verification`, `ml/gpu-budget-conventions`) are path-scoped to pipeline documents (`.ai-work/**/WIP.md`, `SYSTEMS_PLAN.md`…) and load in about 45% of ordinary pipeline sessions in any managed project.

### 2.5 Usage against cost

- 9 `Skill` activations across 67 main sessions (2026-09-25 → 10-11), 7 distinct skills, **zero by subagents**. Over the longer window, 26 activations against 817 agent spawns. Skills reach agents by preload, not by choice.
- On a 1M window, 38 of 89 Praxion listing entries render name-only; on a 200K window (Haiku 4.5), 72 of 89, with resident context at 46.5K (23% of the window).
- `MEMORY.md` is a status log, not an index: 94 lines, 85 over 150 characters, one line of 563 tokens; growing about two entries a day; about three weeks from the harness's 25 KB load cap.

### 2.6 The ruler is wrong

`scripts/measure_token_budget.py` counts with the `claude-sonnet-4-5` tokenizer. Current models (Sonnet 5.5, Opus 4.7+, Opus 5.x) count the same text about **1.49×** higher. The governed always-loaded set reads 16,787 of 25,000 tokens (67%) on the script's ruler and **24,413 (97.7%, 587 tokens of headroom)** on the ruler the model actually uses. The guard has been reporting comfortable headroom that does not exist.

## 3. What the harness allows (October 2026)

The full mechanism and inheritance tables are in [`RESEARCH_FINDINGS_harness-native.md`](research-evidence/2026-10-11-startup-context-diet/RESEARCH_FINDINGS_harness-native.md). The parts that decide the design:

| Lever | What it does | Who can pull it |
|---|---|---|
| `omitClaudeMd: true` (agent frontmatter, ≥2.1.271) | Subagent skips user/project CLAUDE.md, unscoped rules and the MEMORY.md index; git status stays; all-or-nothing | **Plugin** (works for plugin agents; PROBED) |
| `SubagentStart` hook `additionalContext` | Injects into the subagent's start; composes with `omitClaudeMd` (PROBED) | **Plugin** |
| SessionStart / UserPromptSubmit / Pre/PostToolUse `additionalContext` | Appends to the conversation (cache-safe); 10,000 chars per string, overflow becomes a file path + 2K preview the model is not told to read; plugin hooks also run inside subagents | **Plugin** |
| Rules with `paths:` | Load when Read, **Write or Edit** (2.1.288) or a single-file Bash read (2.1.293) touches a match; summarised away at compaction, reload on next match | **Installer** (plugins cannot ship rules) |
| Nested `CLAUDE.md` below cwd | Lazy, same triggers | project layout |
| Skill `paths:` | Gates auto-activation only; **does not withhold the listing entry** (PROBED) | plugin |
| `disable-model-invocation: true` | Description leaves the listing; model cannot load it, cannot be preloaded | plugin |
| `skillOverrides` | Hides or name-onlys skills — **"Plugin skills are not affected"** (explains td-197) | user/project settings, non-plugin skills |
| `skillListingBudgetFraction`, `skillListingMaxDescChars` | Listing budget (default 1% of window) and per-entry cap | user/project settings |
| `enabledPlugins` per project, `defaultEnabled`, `dependencies` | Whole-plugin profiles per project | **Installer / onboarding** |
| `claudeMdExcludes` | Skip CLAUDE.md and rule files by glob (symlinks match since 2.1.239) | any settings layer |
| `disableClaudeAiConnectors`, `disabledMcpServers` | Drop claude.ai connectors per project, or individual servers | project/user settings |
| `autoMemoryEnabled`, MEMORY.md 200 lines / 25 KB | Index loaded every session (and, in practice, into subagents) | settings; content is assistant-written |
| Tool search (default on) | Deferred schemas are not billed (MEASURED +41.9K when off) | harness |

**Levers a plugin lacks:** shipping rules, setting listing visibility for its own skills, a "hidden but model-loadable" skill state (native skill search, #20143 and three siblings, closed NOT_PLANNED), lazy user-scope CLAUDE.md, a finer subagent baseline than all-or-nothing, removing anything with a hook.

**Stale Praxion knowledge found:** `rules/CLAUDE.md`, `docs/claude-code-limitations.md` and `rule-crafting` still say path-scoped rules inject on Read only (fixed upstream in 2.1.288). td-197's null result was by design. The MCP instruction cap is now 4,096 characters (docs page still says 2,048).

## 4. What the evidence says

Full evidence table, appraisal and divergence map: [`RESEARCH_FINDINGS_research-literature.md`](research-evidence/2026-10-11-startup-context-diet/RESEARCH_FINDINGS_research-literature.md). Claims Praxion may make, with their support:

| # | Claim | Support | ≥2 traditions |
|---|---|---|---|
| L1 | Resident guidance is not inert: agents act on it, changing behaviour and cost | ETH AGENTS.md study (uv used 1.6×/task when mentioned vs <0.01), Tsinghua, Codex runtime study | yes |
| L2 | Guidance that doesn't apply costs quality or effort | ETH (+20–23% cost, more steps), Tsinghua (even *already satisfied* constraints reduce task performance, incl. Sonnet 4.5), SkillsBench (4+ skills +5.9 pp vs +18.6 for 2–3; "comprehensive" −2.9 pp), SkillReducer (pruning +2.8%) | yes; magnitudes small-to-moderate |
| L3 | Joint compliance collapses with the number of instructions that all apply at once, and with conflicts | IFScale, ManyIFEval, Eliav, Instruction Stacking Collapse, Control Illusion | yes — **but every study makes all instructions apply to every output**; Praxion's rules are conditional |
| L4 | Length alone degrades reasoning even with perfect retrieval | Du (EMNLP 2025), Levy (ACL 2024), NoLiMa (ICML 2025), Chroma | yes; magnitude at 60–90K on 2026 frontier models unmeasured, and pure lookup may be near-free there |
| L5 | Near-miss distractors do disproportionate damage | Chroma, First Drop of Ink, single-agent-with-skills | yes |
| L6 | LLM-generated guidance doesn't help | ETH, SkillsBench | yes |
| L7 | Curated, focused procedural guidance helps — when it reaches the model | SkillsBench (+16.2 pp), Dynamic Cheatsheet, Memp, ACE, Vercel | yes |
| L8 | **On-demand loading fails at the trigger** | Vercel (56% never invoked), skills-in-the-wild (gains vanish under realistic retrieval), SkillsBench (Codex neglects skills), Spence (~50–55% baseline activation), Praxion telemetry | yes |
| L9 | Flat selection degrades with catalogue size; one routing level restores most of it, a second never helps | Li, He, RAG-MCP | yes for direction |
| L11b | A resident rule is not a reliably followed rule | McMillan (1,650 Claude Code sessions: 55–68% compliance with a trivial MUST rule, decaying across the session; CLAUDE.md size 25–500 lines made no difference), consistent with IFScale per-instruction <100% and reminder studies | partial |
| L12 | Sub-agent isolation helps parallel, read-heavy work and hurts sequential coupled work | Anthropic, Google/MIT | yes |
| L13 | What a sub-agent should inherit | **no study** | — |
| L14 | Lexical compression is a safe lever for rules | none; the one RCT on instructions backfires at high ratios | no |

Three reconciliations shape the design:

- **Resident vs on-demand (Vercel vs ETH).** Vercel's winner was an 8 KB *index of pointers* resident in AGENTS.md (100% vs 53–79% for an on-demand skill); ETH's losers were *overview prose*. Resident pointers plus deterministic delivery of bodies satisfies both. The variable that decides is trigger reliability (L8).
- **Shorter vs more detailed (SkillReducer vs ACE).** Prune off-task breadth; never summarise on-task detail ("brevity bias", "context collapse"). A kernel is a *scoping* exercise, not a compression one.
- **Isolation (Anthropic vs Cognition).** Readers and reviewers isolate well; writers need the decisions their siblings made. A lean spawn must still carry the project's non-standard practices and the task's decisions.

The practitioner lens ([`RESEARCH_FINDINGS_practitioner-patterns.md`](research-evidence/2026-10-11-startup-context-diet/RESEARCH_FINDINGS_practitioner-patterns.md)) converges on the same shape from the field: a kernel plus a routed index whose rows say *when* to read (Anthropic, HumanLayer, Osmani, Vercel, Shankar — "a bare path is often ignored; pitch why and when"); every unit gets an explicit activation mode (always / glob / description / manual across six harnesses); enforceable prose becomes hooks or configuration (four traditions, and harness vendors themselves are moving policy from prompts into feature flags); skill bodies load lazily (8 of 9 skill-adopting harnesses audited from source); and hard per-surface byte budgets (Codex 32 KiB, Windsurf 6K/12K chars). Böckeler's framing is the useful one: classify context by **who decides to load it** — the model (never certain), the human, or the agent software (deterministic).

## 5. Reconciliation: why "scope, then push"

| Finding | Praxion fact | Consequence |
|---|---|---|
| Off-task guidance costs quality (L2, L5) | 21.3K of rules and CLAUDE.md, mostly orchestrator- or ADR-author content, in every spawn | Scope by **audience**: subagents should not inherit the orchestrator's rulebook |
| On-demand fails at the trigger (L8) | 9 skill activations in 67 sessions; subagents never call `Skill` | Anything that *must* apply cannot depend on the model choosing to load it: deliver it **deterministically** |
| Residency ≠ adherence; compliance decays (L11b) | Rules are resident at session start and read once | Deliver procedures **at the point of use** (the moment of `git commit`, the write into `.ai-state/decisions/`) — cheaper *and* fresher |
| Resident index beats both kitchen-sink and pure pull (Vercel) | The listing is a capped, truncated index; MEMORY.md is a log | Keep a resident **routed index** with triggers; keep the listing legible |
| Harness lazy channels got more reliable (2.1.288/293) | Praxion's mitigation was designed for Read-only loading | Path-scoped rules are now a sound deterministic channel |
| `omitClaudeMd` + `SubagentStart` compose (PROBED) | Praxion already owns the hook bus (dec-167, `inject_rules.py`) | A per-role kernel replaces the inherited rulebook with no new infrastructure class |
| Tool schemas already deferred (+41.9K when off) | Praxion's surplus is instructions, not tools | Code mode and catalogue search are second-order here |
| No study measures a conditional process corpus (all lenses) | Praxion has eval infrastructure and a WAL | Praxion must measure its own adherence and trigger reliability |

Stated as one principle: **every resident token must name its audience, its scope and its trigger; the kernel is what has all three set to "always"; everything else is pushed by something deterministic, and only optional depth is pulled by the model.**

## 6. The design for Praxion

Six components, each implementable today by the plugin, the installer or onboarding. None needs a harness feature that doesn't exist.

### 6.1 Lean spawns: `omitClaudeMd` plus a per-role kernel

- Every Praxion agent sets `omitClaudeMd: true`.
- A new `SubagentStart` injector delivers a **role kernel** generated from a manifest: the behavioural contract (always), the slice of rules that role uses (ADR authoring for the four ADR authors; the intermediate-documents contract for writers; nothing about tier selection or spawn budgets), and, for roles that write code, a **project slice** (the project's build/test/lint commands and non-standard practices, extracted from its CLAUDE.md).
- Budget: ≤10,000 characters per hook string; a role needing more uses two injections or points at a file *with a trigger*.
- Measured headroom: 29.6K inherited → an estimated 3–7K kernel. Savings about 23–27K per spawn.
- Guard against Cognition's failure: the delegation prompt already carries the task brief and slug; writer kernels keep the project slice; a paired eval decides each role.
- **Process awareness is a hard requirement, not a casualty.** A spawned agent must know the Praxion process as it applies to its role. Today it inherits the *orchestrator's* playbook (tier table, spawn budget, checkpoints), which it cannot act on, while its own part of the process lives in its agent body. The role kernel therefore carries that role's slice of the process: the behavioural contract and its self-test, the intermediate-documents contract (where to write, the task slug, fragments), the return contract and completion markers, ADR fragment rules for the four authors, staging and commit rules for writers. It is generated from the same rule sources, so it cannot drift from them. The eval adds a process-adherence check per role: the right paths, the marker, the contract self-test. Agents opt in one at a time; without the flag an agent keeps today's full inheritance.
- **Today's alignment is uneven (scan of `agents/*.md`, 2026-10-11).** 14 of 17 agents point at the behavioural contract by path and rely on the inherited rule for its content; `promethean`, `roadmap-cartographer` and `skill-genesis` don't mention it. Six agents state the completion markers themselves. `researcher`, `verifier`, `sentinel` and `context-engineer` get the return contract only from the inherited coordination rule, or from whatever the orchestrator writes into the brief. A naive `omitClaudeMd` would cut real alignment.
- **Four layers per spawn:**
  1. **Shared Praxion core** (every agent, ~1–2K): the contract and self-test; artifact locations and slug discipline; the return contract; boundary discipline; commit hygiene.
  2. **Role steps:** the agent body, plus the role-specific rules now buried in shared files (ADR fragments for authors, ledger-writer rules, test-first for writers).
  3. **Project slice.**
  4. **Task slice:** the delegation prompt, whose checklist `inject_subagent_context.py` can enforce instead of relying on the orchestrator's memory.

  Gates enforce inside subagents throughout.
- **Additive first, subtractive later.** Step one injects the shared core and the role slice *on top of* today's inheritance (about 1–2K extra per spawn, zero alignment risk). That makes alignment explicit and testable, and it fills today's gaps. Only when the per-role process-adherence eval shows the kernel alone suffices does an agent switch to `omitClaudeMd`.
- **Portability.** `omitClaudeMd` and `SubagentStart` are Claude Code mechanisms. The Codex agent export must drop the unknown field (verify `export-codex-agents.py`), and Codex and Cursor keep today's behaviour.
- Next lever after this lands: the preload roster (207,564 tokens). Replace multi-skill preloads with one anchor skill plus pointer rows that say when to read the rest.

### 6.2 Constitution vs procedures in the main session

Split every always-on rule into what must be resident (constraints and the routing index) and what is procedure, then move each procedure to the trigger that predicts its need:

| Procedure | Trigger | Channel |
|---|---|---|
| ADR file format, relation protocols, finalize | Write/Edit under `.ai-state/decisions/` | path-scoped rule (now fires on Write) |
| Intermediate-document trees and lifecycle | Read/Write under `.ai-work/`, `.ai-state/` | path-scoped rule, one resident line |
| Git staging and commit detail | `git add` / `git commit` | PreToolUse injection; a 4-line kernel stays resident because a late reminder cannot undo a bad `git add` |
| Delegation checklists, model routing | Agent spawn | `inject_subagent_context.py` (already the single `updatedInput` emitter) sets `model` from agent frontmatter and appends the checklist to the spawn prompt; the resident routing table disappears |
| Decision context | First Edit of a file | `query_adrs.py --paths` on PostToolUse instead of a broad SessionStart block |
| Anything a gate already enforces | — | delete the prose; leave a one-line pointer to the gate |

What stays resident in the main session: the behavioural contract, a ~1.9K tier kernel (Process Calibration, Pipeline Isolation, Delegation Depth), a compressed user CLAUDE.md (one sentence per principle, each pointing at its skill; Context Engineering and BDD kept whole), project essentials, the git kernel, and the routed index.

### 6.3 Project gating

Move every non-constitutional rule from the `~/.claude/rules/` symlink set to the hook bus (dec-167's channel), gated on the project having `.ai-state/`. Non-managed directories stop paying for Praxion's process. Hook-delivered rules are not inherited by subagents, which is exactly what §6.1 wants. Two things to verify before landing: SessionStart re-fires on `compact` (Praxion's matcher `""` should cover it), and hook failure is loud (extend `heal_hook_chain.py`), because a dropped hook silently drops guidance.

### 6.4 A legible catalogue

The skill listing is capped, so trimming it buys **visibility**, not tokens.

- Consolidate the near-miss clusters the prior spike named (`api-*`, `roadmap-*`, `testing-strategy`/`test-coverage`, `data-modeling`/`data-structure-design`…). The literature says confusability, not count alone, is the damage.
- Trim the four longest agent descriptions (2.5K → about 0.8K).
- Register the likec4 MCP server only where a LikeC4 workspace exists.
- Later, split the plugin into a **core plus domain packs** (design, ML, transactions, diagrams, language toolchains) enabled per project by `onboard-project` writing `enabledPlugins`. It is the only native lever that removes listing entries, agents and MCP instructions per project, and it maps onto Codex and Cursor exports.

### 6.5 Memory hygiene

`MEMORY.md` should be what the harness designed it to be: one-line pointers, ≤120 characters each, with status histories kept in the topic files. Praxion can ship the convention and a check (a Stop or SessionStart warning when the index passes a token or line-length threshold). Estimated −3.5K in the main session, and in every spawn until §6.1 lands.

### 6.6 Instruments first

- **Real-token startup probe** (`measure_startup_payload`): the ablation method of §2.1 as a script. It measures the main session and every agent type through `--agents` or the plugin agents, writes a baseline under `.ai-state/`, and feeds the ratchet. It sits alongside the fixed `measure_token_budget.py` (current tokenizer, both rulers reported, T02 ceiling re-based) and Claude Code's own `claude plugin details` Always-on figure.
- **Conditional-adherence and trigger-reliability eval.** 30–60 rule-triggering tasks (commit, ADR authoring, tier selection, delegation, worktree, diagram, `.ai-work` documents), each scored per rule, in two arms (today's payload vs the lean one). Log `InstructionsLoaded` events into the WAL so every task records *whether the right guidance arrived*. Power: paired designs; Khatri's analysis puts unpaired detection of 10 pp at 120–200 tasks, so claim "no regression within a bound", not "improvement".

### 6.7 What this means for managed projects

Everything above ships through the plugin and the installer, so managed projects inherit it on upgrade. `onboard-project` gains three optional, project-scoped settings it can write: `enabledPlugins` (packs), `claudeMdExcludes` (for teams that don't want the global rules), and `disableClaudeAiConnectors` / `disabledMcpServers` (a developer's personal connectors cost about 18K per interactive session). The activation-mode manifest of §6.2 becomes the single source of truth from which the Cursor rule types (Always / Auto Attached / Agent Requested / Manual) and the Codex AGENTS.md (32 KiB cap) are exported.

## 7. Where code mode and catalogue search fit

The prior spike's ranking (catalog router, `praxion-catalog` MCP, `praxion` CLI) stays valid for **selection**, but it is second-order for **startup**:

- The tool-schema half of code mode is already done by the harness (MEASURED: 41.9K saved by default deferral).
- Search-then-load is model-initiated retrieval, which is exactly where L8 says the benefit leaks. Use it for the long tail of optional depth, after the deterministic channels carry everything that must apply.
- The durable lesson — *the context carries an index, not the library* — is the routed index of §6.2, which is resident on purpose.
- The `praxion` CLI (procedures as composable scripts) remains the right home for code mode, as a way to keep procedure out of prose.

## 8. Projected effect (arithmetic, not measurement)

Main session, Praxion repo (current-generation tokenizer):

| Item | Now | After | Move |
|---|---|---|---|
| coordination protocol | 6,985 | ~1,900 | tier kernel; rest at point of use |
| adr-conventions | 3,554 | ~1,060 | kernel; rest path-scoped |
| intermediate documents | 1,670 | ~400 | one line + path rule |
| `rules/CLAUDE.md` | 837 | 0 | stop globalising |
| behavioural contract | 542 | 542 | keep |
| user CLAUDE.md | 3,897 | ~2,500 | principles compressed (measured trial) |
| project CLAUDE.md | 3,863 | ~3,100 | duplicates removed |
| hook rules (routing + git) | 3,022 | ~350 | routing made deterministic; git kernel |
| decision context | 1,334 | ~300 | path-triggered |
| agent listing | 5,018 | ~3,400 | description diet |
| skill listing | 10,580 | ~10,000 | capped; more of it visible |
| likec4 instructions | 1,332 | 1,332 | kept here; 0 in projects without LikeC4 |
| MEMORY.md | 7,978 | ~4,500 | hygiene |
| **Praxion total** | **50,612** | **~29,300** | **−42%** |

- **This repo, interactive:** 85.8K → about 64K; about 46K with connectors disabled for dev repos.
- **Managed project:** Praxion's 38.5K → about 21K. Core-plus-packs could take another 5K or more off the listing.
- **Non-managed project:** about 37K → about 16K, mostly listings.
- **Per spawn:** −23K to −27K, roughly half of a typical 50K spawn. A Standard pipeline carries about 370–430K fewer resident tokens, a Full one about 0.75–0.86M fewer.
- **Dollars:** about $0.07 (Sonnet) to $0.15 (Opus) per cold spawn and cents per session. The point is attention, latency and headroom.

These are estimates over measured items. The probe in §6.6 replaces them with measurements.

## 9. Roadmap (low-hanging → structural)

### Phase 0: hygiene (Direct / Lightweight; reversible; days)

| # | Item | Effect | Guard |
|---|---|---|---|
| H1 | Make `measure_token_budget.py` report the current-tokenizer reading **next to** today's; do not switch the gate yet | Truth: 97.7% of budget, not 67% | Switching the gate's basis trips the ratchet's basis-mismatch guard and leaves 587 tokens of headroom, so the ceiling is a user decision, taken separately |
| H2 | Stop symlinking `rules/CLAUDE.md` globally | −0.8K everywhere, every spawn | `regenerate_rules_manifest.py` core set; T02 file set. In this repo it still lazy-loads as a nested CLAUDE.md when `rules/` is touched; the Cursor and Codex exporters read `rules/` from the repo, not from `~/.claude/rules/` |
| H3 | MEMORY.md convention (≤120-char pointer lines, history in topic files) plus a check | −3.5K main and per spawn | Shorten, never drop, feedback entries; pointers keep their trigger words |
| H6 | Correct stale knowledge: path rules load on Write/Edit (2.1.288); td-197 explained; MCP cap 4,096 | Mitigations sized correctly | Docs only. Keep the "read a sibling first" mitigation: Cursor ignores rule globs, and Codex routes path rules through its own bridge |
| H7 | (User) `disableClaudeAiConnectors` or `disabledMcpServers` in dev repos | −17.8K interactive | Per-project choice |

**Status (2026-10-11, startup-hygiene batch):** H1, H2, H3, H6 and H7 are done. Measured on real first requests (headless, this repo), the session start fell from 67,988 to 64,603 tokens (−3,385), and the same saving applies to every subagent spawn. H2 is recorded as an ADR that partially supersedes dec-167 and dec-168. The lean-spawn prerequisite, a per-agent map of the process guidance each subagent must receive, is drafted in [`subagent-alignment-map.md`](subagent-alignment-map.md).

Two items were moved **out** of Phase 0 after a process-safety check (2026-10-11):

- **The ML rules' pipeline-document globs stay.** They deliberately load eval-driven verification and GPU-budget guidance when an ML pipeline writes `SYSTEMS_PLAN.md`, `WIP.md` or `VERIFICATION_REPORT.md` (dec-116, dec-119, dec-217); the Codex rules bridge reads the same globs. The safe version is an opt-out: `onboard-project` writes `claudeMdExcludes` for non-ML projects, as Praxion's own `.claude/settings.json` already does. Phase 3's project-kind gating replaces both.
- **Agent-description trimming waits for a routing check (Phase 1).** The descriptions are also exported verbatim to Codex agent definitions, and `roadmap-cartographer`'s `<example>` blocks disambiguate it from the `roadmap-planning` skill, a near-miss pair. The saving (~1.6K) does not justify an unmeasured routing change.

### Phase 1: instruments (Lightweight → Standard)

- I1, the real-token startup probe.
- I2, the conditional-adherence and trigger-reliability eval (§6.6).

Nothing below lands without I1 showing the saving and I2 showing no regression.

### Phase 2: lean spawns (Standard; architectural ADR)

The ADR covers a new `SubagentStart` injector and a role-kernel manifest.

1. **Pilot.** Two read-mostly agents (researcher, verifier): `omitClaudeMd` plus a role kernel, A/B on I2 and the existing agent evals.
2. **Writers.** implementer and test-engineer, with the project slice.
3. **Preloads.** One anchor skill per agent plus triggered pointers; the 207K roster is the next lever.

### Phase 3: constitution/procedure split and project gating (Standard → Full; architectural ADR)

Rule delivery moves from symlinks to the hook bus.

1. **Activation-mode manifest.** Classify every resident unit by audience, scope and trigger, extending `rules/_manifest.yaml` so it also exports to Cursor and Codex.
2. **Kernel and point-of-use injectors.** Enforceable prose goes into gates.
3. **Project gating.** Gate on `.ai-state/`.
4. **Deterministic model routing.** Handled in `inject_subagent_context.py`.

### Phase 4: catalogue (Full; only after measurement)

1. Near-miss consolidation.
2. Core-plus-packs with onboarding-written `enabledPlugins`.
3. A capped `UserPromptSubmit` pointer hook (≤3 pointers, never bodies), only if I2 shows trigger failures for moved content.
4. The prior spike's catalogue MCP, only if a measured gap remains.

### Watch items

- #100813: the skill listing arriving late or never in interactive sessions.
- Any upstream "hidden but loadable" skill state or subagent-specific rules.
- The docs/behaviour divergence on subagent MEMORY.md, which could be fixed upstream in either direction.

## 10. What must survive, risks, open questions

**Must survive:**
- The behavioural contract resident for every agent, inside every role kernel too.
- Deterministic gates stay deterministic.
- Progressive disclosure inside skills.
- Graceful degradation: with the hooks absent (Codex, Cursor, a broken install), behaviour falls back to today's, never to nothing.

**Compatibility facts (verified 2026-10-11):**
- **AGENTS.md.** Claude Code reads `AGENTS.md` only when no `CLAUDE.md` exists in the working directory or above it. Praxion and its managed projects have a `CLAUDE.md`, so the generated `AGENTS.md` is never loaded twice.
- **Cursor.** `export-cursor-rules.py` exports every rule from the repo's `rules/` with `alwaysApply: false` and strips the `paths:` frontmatter.
- **Codex.** The rules bridge skips `CLAUDE.md`, reads `paths:` to route rules, and exports agent descriptions verbatim.

Changes to the Claude install (symlinks, hooks) therefore don't reach Codex or Cursor. Changes to rule frontmatter or agent descriptions do.

**Risks:**

| Risk | Mitigation |
|---|---|
| A dropped or failing hook silently removes guidance | Fail-loud hook-chain check; trigger-reliability metric in I2 |
| 10,000-char overflow turns into a file path the model is not told to read | Budget per string in CI |
| Writer subagents lose the decisions their siblings made | Project slice and task brief in the kernel; role-by-role A/B |
| Path-scoped content is summarised away at compaction | It reloads on the next match; anything that must persist stays in the kernel |
| Over-eager prompt-intent injection accumulates in history | Cap; pointers only; shadow mode first |
| Underpowered eval | Paired design; claim bounded non-regression only |

**Open questions:**
1. Does `omitClaudeMd` behave identically in an interactive session with a plugin-installed agent (probed headless only)?
2. Does `inject_rules.py` re-fire on compaction in practice?
3. How many rules are concurrently applicable per action in real Praxion sessions — the quantity IFScale actually bears on?
4. Does a point-of-use reminder beat session-start residency on adherence, given the measured decay?
5. Does `claudeMdExcludes` in project settings reach user-scope rule files?

## 11. Sources

All fetched 2026-10-11 unless noted; full lists with tiers and appraisal are in the four evidence files.

**Harness (T1):** [memory](https://code.claude.com/docs/en/memory) · [skills](https://code.claude.com/docs/en/skills) · [sub-agents](https://code.claude.com/docs/en/sub-agents) · [hooks](https://code.claude.com/docs/en/hooks) · [plugins reference](https://code.claude.com/docs/en/plugins-reference) · [prompt caching](https://code.claude.com/docs/en/prompt-caching) · [context window](https://code.claude.com/docs/en/context-window) · [settings](https://code.claude.com/docs/en/settings-reference) · [env vars](https://code.claude.com/docs/en/env-vars) · [MCP](https://code.claude.com/docs/en/mcp) · [best practices](https://code.claude.com/docs/en/best-practices) · [changelog](https://code.claude.com/docs/en/changelog) · [pricing](https://platform.claude.com/docs/en/about-claude/pricing) · [tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) · [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) · [Prompt caching is everything](https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/) · [Steering Claude Code](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more)

**Research:** [Evaluating AGENTS.md (ETH)](https://arxiv.org/abs/2602.11988) · [AGENTS.md efficiency (ICSE JAWs)](https://arxiv.org/abs/2601.20404) · [Two-agent context-file ablation](https://arxiv.org/abs/2607.27250) · [Instruction adherence in coding-agent config files](https://arxiv.org/abs/2605.10039) · [IFScale](https://arxiv.org/abs/2507.11538) · [ManyIFEval](https://arxiv.org/abs/2509.21051) · [AgentIF](https://arxiv.org/abs/2505.16944) · [Instruction Stacking Collapse](https://arxiv.org/abs/2608.02639) · [Paradoxical Interference](https://arxiv.org/abs/2601.22047) · [Control Illusion](https://arxiv.org/abs/2502.15851) · [Context Length Alone Hurts](https://arxiv.org/abs/2510.05381) · [Same Task, More Tokens](https://arxiv.org/abs/2402.14848) · [NoLiMa](https://arxiv.org/abs/2502.05167) · [Chroma Context Rot](https://www.trychroma.com/research/context-rot) · [First Drop of Ink](https://arxiv.org/abs/2605.10828) · [Prompt Design at Scale](https://arxiv.org/abs/2607.19257) · [SkillsBench](https://arxiv.org/abs/2602.12670) · [Single-agent with skills](https://arxiv.org/abs/2601.04748) · [Agentic skills in the wild](https://arxiv.org/abs/2604.04323) · [SkillSeek](https://arxiv.org/abs/2609.38822) · [Progressive disclosure limits](https://arxiv.org/abs/2607.17598) · [SkillReducer](https://arxiv.org/abs/2603.29919) · [ACE](https://arxiv.org/abs/2510.04618) · [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952) · [Scaling agent systems](https://arxiv.org/abs/2512.08296) · [Harness Engineering (11 harnesses)](https://arxiv.org/abs/2609.00006) · [Survey of Context Engineering](https://arxiv.org/abs/2507.13334)

**Practitioners and harnesses:** [Vercel — AGENTS.md vs skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) · [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) · [HumanLayer — CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md) · [Horthy — ACE-FCA](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md) · [Böckeler](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html) · [Osmani](https://addyosmani.com/blog/agents-md/) · [Shankar](https://blog.sshh.io/p/how-i-use-every-claude-code-feature) · [Vincent — Superpowers](https://blog.fsck.com/2025/10/09/superpowers/) · [Spence — skill activation](https://scottspence.com/posts/measuring-claude-code-skill-activation-with-sandboxed-evals) · [Breunig](https://www.dbreunig.com/2025/06/26/how-to-fix-your-context.html) · [Lance Martin](https://rlancemartin.github.io/2025/06/23/context_engineering/) · [Cognition](https://cognition.com/blog/dont-build-multi-agents) · [Zechner — pi](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/) · [Ronacher — codemode](https://lucumr.pocoo.org/2026/10/6/codemode/) · [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) · [Cursor rules](https://cursor.com/docs/context/rules) · [Kiro steering](https://kiro.dev/docs/steering/) · [OpenHands keyword skills](https://docs.openhands.dev/usage/prompting/microagents-keyword) · [Gemini CLI](https://geminicli.com/docs/cli/gemini-md/)

**Internal:** [`MEASUREMENTS.md`](research-evidence/2026-10-11-startup-context-diet/MEASUREMENTS.md) · [`CONTEXT_REVIEW.md`](research-evidence/2026-10-11-startup-context-diet/CONTEXT_REVIEW.md) · `scripts/measure_token_budget.py` · `hooks/inject_rules.py` · `hooks/hooks.json` · `.ai-state/observations.jsonl` · `.ai-state/decisions/167-hook-delivered-blacklist-mechanism.md` · the predecessor spike (`.claude/worktrees/codemode-jev-research/docs/independent-analysis/skill-selection-code-mode-research.md`, uncommitted)
