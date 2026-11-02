---
title: Reaching the Right Skill Without Paying for All of Them — Code Mode, Tool Search and Praxion's Selection Surface
type: independent-analysis
diataxis: explanation
audience: architect / maintainer
status: spike (research + ranked opportunity list; no implementation)
date: 2026-09-23
head_sha_analyzed: 29f9c7f1
author: Francisco Perez-Sorrosal (analysis run as a two-lens Spike with Claude Code — one external landscape lens, one internal measurement lens, collected independently and reconciled here)
companion: jev-typed-decisions-research.md
evidence: research-evidence/2026-09-23-codemode-jev/
verification_legend:
  VERIFIED: primary source fetched, file:line read, or number produced by a stated command
  SINGLE-SOURCE: one source, not independently confirmed
  ASSUMPTION: stated belief that shapes a recommendation; falsifier named where possible
---

# Reaching the Right Skill Without Paying for All of Them

> **Scope.** A Spike, not an implementation. The question: how can Praxion agents reach the *best* Praxion skills and commands without paying the name+description of every component in every context, and without the selection errors that large flat listings cause (context rot)? The starting point is Cloudflare's **Code Mode** ([blog](https://blog.cloudflare.com/code-mode/), [docs](https://developers.cloudflare.com/agents/tools/codemode/)); the survey covers every related 2025–2026 technique we could find from a primary or peer-reviewed source. The output is a ranked opportunity list, from measurements and cheap proofs up to structural changes, to feed later ideation and a `systems-architect` pass. The raw evidence dossiers the synthesis draws on are preserved under [`research-evidence/2026-09-23-codemode-jev/`](research-evidence/2026-09-23-codemode-jev/).

## 0. TL;DR

- **Code mode's real lesson is "context carries an index, not the library", not "write TypeScript".** Cloudflare, Anthropic and Vercel independently converged on the same architecture: the catalogue lives *outside* the context behind a tiny search/execute interface, and intermediate results never re-enter the context. Three vendors converging on one architecture is the strongest signal in the survey. Their 98.7–99.9% token cuts are each a single worked example, not a benchmark, so treat them as illustrative. VERIFIED (§2).
- **Removing candidates improves accuracy as well as cost.** This is the result that matters for Praxion. It comes from several places:
  - Anthropic's Tool Search Tool: tool-selection accuracy for Opus 4 rose 49% → 74%, and for Opus 4.5 79.5% → 88.1%, with 85% fewer tokens.
  - RAG-MCP: 13.6% → 43.1%.
  - An adaptive shortlist beat a fixed shortlist on Claude Sonnet 4.6: 87.1% → 93.1%.
  - Near-miss distractors hurt more than random noise.
  Every measured study points the same way. VERIFIED/SINGLE-SOURCE mix (§2.4).
- **Praxion's MCP tools are already solved; its skills, agents and commands are not.** Claude Code defers MCP tool schemas by default. Nothing in the harness defers *skills*. Praxion's selection listing is **9,243 tokens over 89 active entries** (61 skills, 11 commands, 17 agents), measured today. That is about 4.6× the ~2,000-token band the prior roadmap used as its truncation-free target. Every subagent spawn re-pays it. VERIFIED (§3).
- **The listing is not the biggest lever. Static preload is.** Agent-frontmatter `skills:` bodies total **240,647 tokens** across 17 agents. In 18,042 telemetry rows only 12 on-demand `Skill` tool calls appear, so at the agent layer skill content arrives by preload, not by progressive disclosure. Code mode's principle, applied to Praxion, first targets *preload*, then the listing. VERIFIED (§3.3).
- **The harness constraints are sharp:**
  - No hook can remove entries from the native skill listing. Hooks can only *add* context.
  - `disable-model-invocation: true` also blocks subagent preload and model-initiated `Skill` calls.
  - `skillOverrides` is documented with four states (`on` / `name-only` / `user-invocable-only` / `off`), but Praxion measured it as having no effect (td-197).
  - No state means "hidden from the listing, but loadable on demand". That missing state is exactly what a Praxion-side mechanism has to supply. VERIFIED (§3.2).
- **Recommendation: build the search layer yourself, as a plain meta-tool first, with no sandbox.** The first real proof is a **catalog router**: an index of the long tail, loaded on demand, with each body read from disk when needed. It needs no new infrastructure and runs today. The durable form is a small `praxion-catalog` MCP server with `search` and `get` over a generated manifest. Claude Code already defers its tools, so it costs almost nothing, and it ports to Codex. True code mode, meaning agents composing Praxion operations as code, fits Praxion's *procedures* (scripts), not its prose skills. The full ranking is in §6.
- **Measure first.** Praxion has never measured *selection accuracy*, and the sentinel says so itself. §6 therefore starts with a skill-selection golden eval and a live truncation sample. Without them, no later change can be shown to help.

## 1. The problem, stated as behaviour

Behaviour wanted: *when an agent works on a task, the skill guidance most relevant to that task is in its context, and little else is*. Two failure modes violate it:

1. **Cost:** irrelevant descriptions and preloaded bodies are paid in every session and every spawn. Praxion's own measurement puts always-loaded tokens at about ×(1+spawns) per pipeline (`docs/context-economy.md`; memory note on subagent inheritance).
2. **Selection error:** the right skill is missed or the wrong one fires. This happens through (a) *invisibility*, where listing truncation drops a description before the model sees it (measured in the process-economy roadmap as ~40 of 62 skills name-only in one session), or (b) *confusion*, where near-duplicate descriptions compete. The literature shows (b) grows with catalogue size and is worst for semantically similar distractors.

Code mode and tool search address both failure modes by the same move: shrink what is resident, and retrieve on demand.

## 2. External landscape (what the field has built)

### 2.1 Cloudflare Code Mode

- **Mechanism.** MCP tool schemas become a typed TypeScript API. The model writes code against that API, and a V8 isolate spawned per snippet (the Worker Loader) runs it. Only the final result returns to the model. Credentials are passed as pre-authorised **bindings**, never raw keys. The stated rationale is that models have seen far more real TypeScript than synthetic tool-call JSON, and that N chained calls collapse into one round trip. ([Code Mode, 2025-09-26](https://blog.cloudflare.com/code-mode/); the first post is qualitative only.)
- **Follow-up: two tools for the whole API.** Cloudflare's API MCP server exposes 2,500+ endpoints through `search()` and `execute()`. `search()` runs model-written JS over a typed OpenAPI representation that never enters the context. The cost is ~1,000 tokens whatever the catalogue size, against ~244K for per-endpoint tools and ~1.17M for the raw spec, which Cloudflare reports as a 99.9% cut. The sandbox has no filesystem, no environment and no outbound network by default, with OAuth 2.1 downscoping. ([Code Mode MCP, 2026-02-20](https://blog.cloudflare.com/code-mode-mcp/); SDK docs mark `codemode.search()`/`describe()` **experimental**.) VERIFIED as vendor claims; single worked example.

### 2.2 Anthropic: code execution with MCP, and advanced tool use

- **Filesystem-of-tools** ([2025-11-04](https://www.anthropic.com/engineering/code-execution-with-mcp)). MCP servers are presented as a directory of typed modules. The agent lists and reads only what it needs, or calls a `search_tools(detail_level)` function. The sandbox filters data before it reaches the model and can tokenise PII. One workflow went from 150,000 to 2,000 tokens (−98.7%, single example). Anthropic states the burden plainly: agent-generated code needs "sandboxing, resource limits, and monitoring".
- **Advanced tool use** ([2025-11-24](https://www.anthropic.com/engineering/advanced-tool-use)):
  - **Tool Search Tool** (`defer_loading`, regex and BM25 variants): −85% tokens (72K → 8.7K on 50+ tools), and **accuracy up**: Opus 4 49% → 74%, Opus 4.5 79.5% → 88.1%. Recommended above ~10K tokens of definitions or 10+ tools.
  - **Programmatic Tool Calling** (the model writes Python that orchestrates tools in a sandbox): −37% tokens on complex research tasks, with *modest* accuracy gains (25.6% → 28.5%; 46.5% → 51.2%).
  - **Tool Use Examples**: 72% → 90% on complex parameter handling.
- **What the comparison shows.** Code mode's advantage is **cost**. The large **accuracy** gain comes from *removing candidates* (Tool Search), not from writing code. Praxion's selection problem is mainly an accuracy-and-visibility problem, so the search half of code mode is the half to take first. VERIFIED (primary source, as reported).

### 2.3 Claude Code's own mechanisms, and the missing one

- **MCP tools are deferred by default.** Only names and server instructions are resident. `ENABLE_TOOL_SEARCH` takes `true`, `false` or `auto:N` (default: defer past 10% of the window). A community measurement hid ~40K tokens across 88 tools. ([docs](https://code.claude.com/docs/en/agent-sdk/tool-search)) VERIFIED. **This covers MCP tools only**: not skills, commands or agent types.
- **Skills use a three-tier disclosure:** description, then body, then bundled files ([Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills); the [agentskills.io](https://github.com/agentskills/agentskills) standard is adopted by ~40 products). The tiering works *once a skill is selected*. **The listing tier itself does not scale.**
- **Listing limits.** The [official skills page](https://code.claude.com/docs/en/skills), fetched today, documents:
  - a **1,536-character cap per entry** on combined `description` + `when_to_use`, truncating the tail;
  - a post-compaction re-attach budget of 5,000 tokens per skill and 25,000 in total, with the oldest skills dropped first;
  - the `disable-model-invocation`, `user-invocable` and `skillOverrides` states.

  It does **not** state the combined listing budget. The "~1% of the context window, least-used dropped first, ~15–25 skills before truncation" figures come from ≥5 consistent community bug reports and from Praxion's own earlier citation. Treat the exact figures as SINGLE-SOURCE/reverse-engineered. Praxion's own session did show heavy name-only rendering in practice, so that effect is VERIFIED.
- **Skill search is proposed, not shipped.** [anthropics/claude-code#20143](https://github.com/anthropics/claude-code/issues/20143) asks for a `skill_search(task, context)` modelled on Tool Search. Nothing from Anthropic commits to it. Academic prototypes of exactly this, BM25 `search_skills` returning top-k bodies, appear in 2026 preprints (arXiv:2609.00549, arXiv:2607.25032; abstract-level only).

### 2.4 Research on retrieval and context rot (numbers)

| Source | Type | Finding relevant to Praxion |
|---|---|---|
| [Chroma — Context Rot](https://research.trychroma.com/context-rot) (2025-07) | Vendor research, replication kit published | All 18 frontier models degrade monotonically with input length, even on length-invariant tasks. Distractors that are semantically close but irrelevant do the most damage |
| [RAG-MCP](https://arxiv.org/abs/2505.03275) (2025-05) | Preprint | Retrieval before listing: >50% fewer prompt tokens, and **selection accuracy 13.62% → 43.13%** |
| [ToolRet](https://aclanthology.org/2025.findings-acl.1258/) (ACL Findings 2025) | Peer-reviewed | Strong general IR models are **poor at tool retrieval**; retrieving tools is a different skill from retrieving text. Bears on the choice of retriever: curated trigger vocabulary + BM25 is a sound default, and an off-the-shelf embedding is not automatically better |
| [LongFuncEval](https://arxiv.org/abs/2505.10570) (2025-05) | Preprint | Accuracy drops 7–85% as the catalogue grows, 7–91% as tool-response length grows, and 13–40% as the conversation lengthens |
| [How Many Tools Should an Agent See?](https://arxiv.org/abs/2605.24660) (2026-05) | Preprint | Adaptive shortlists (~7 tools on average) match a fixed 50-tool shortlist's coverage. With **Claude Sonnet 4.6, accuracy rises 87.1% → 93.1%** against a fixed 5-tool list. Fixed-size listings are the weak baseline |
| [Tool-Use Tax](https://arxiv.org/html/2605.00136) (2026-05) | Preprint | Near-miss distractor tools hurt more than random ones |
| [MCP-Zero](https://arxiv.org/abs/2506.01056) (2025-06) | Preprint | The model *requests* a capability ("I need a tool that…") and a hierarchical router serves it. Claims −98% tokens with accuracy preserved; single preprint |

Four independent traditions converge: vendor measurements, peer-reviewed IR, academic tool-use benchmarks and context-rot studies. All say **fewer, better-targeted candidates beat a flat catalogue on accuracy as well as cost**. That clears the bar of ≥2 independent traditions converging. The *magnitudes* vary by setup and should not be carried over to Praxion without measuring.

### 2.5 The counter-positions (read these before building)

- **"You don't need code mode"** ([Speakeasy](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2)). A `search → describe → execute` meta-tool over ordinary tool calling gives 96% input-token and 90% total-token cuts, up to 160×, **with no sandbox**. The cost is 2–3× more tool calls. Single vendor.
- **Instability is the real problem** ([Ronacher](https://lucumr.pocoo.org/2025/12/13/skills-vs-mcp/)). His argument: MCP descriptions drift under you, and deferred loading can't fix "too long to load eagerly, too short to actually explain". He prefers self-authored, versioned skills. *For Praxion this cuts in its favour*: the catalogue is first-party and versioned, so the index can be **generated from source on every change** and can't drift the way third-party MCP schemas do.
- **CLI-first** ([Zechner](https://mariozechner.at/posts/2025-08-15-mcp-vs-cli/), Pi agent). With tool design held constant, MCP and CLI tools perform about the same. CLI wins on portability and on letting the shell trim output (`| grep`, `| head`). This is the filesystem-of-tools idea reached earlier from a different starting point. It supports "Praxion procedures as a discoverable CLI" (§5.3).
- **Protocol direction** ([MCP roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/), [progressive-disclosure WG](https://github.com/modelcontextprotocol/progressive-disclosure-wg/issues/18)). The proposal makes `tools/list` non-exhaustive and adds `tools/resolve {names} → {tools}`. It is not ratified. If it lands, deferral becomes a protocol feature for every client. Watch it; don't wait on it.

### 2.6 Security and operations

- A sandbox is necessary but not sufficient. Every vendor pairs isolation with resource limits and monitoring.
- Code mode enlarges what a *prompt injection* can do: one generated program can chain several side effects before any gate sees an intermediate step. This is a class-level risk; no named exploit against Cloudflare or Anthropic code mode was found.
- The debugging story is the gap in all the evidence. A tool call is a discrete, replayable event. A generated program needs its code *and* every intermediate response captured before it can be replayed. None of the vendors documents observability as thoroughly as it documents token savings. For Praxion this matters because its observability (the WAL, the chronograph) is built on discrete events.

## 3. Praxion's selection surface, measured

### 3.1 Inventory (VERIFIED — `python3 scripts/measure_token_budget.py`, 2026-09-23)

| Kind | Files | Active (not `disable-model-invocation`) | Bytes (active) | Mean bytes |
|---|---|---|---|---|
| skills | 63 | 61 | 26,842 | 440 |
| commands | 46 | 11 (33 hidden, +2 non-component files) | 1,012 | 92 |
| agents | 19 | 17 | 11,950 | **703** |
| **Listing total** | 128 | **89** | 39,892 | **9,243 tokens** |

- **Agents are the most expensive entries.** The five largest entries in the whole surface are all agents: `roadmap-cartographer` 1,948 B, `agentic-transactions-architect` 1,749 B, `interface-designer` 1,307 B, `sentinel` 1,098 B, `discipline-consultant` 757 B. Several carry `<example>` blocks inside the description.
- **The skill description diet (P1.12) has a ceiling.** 57 of 62 descriptions stayed above the ≤300-character target because "preserve trigger nouns" outranked the cap.
- **Existing index precedents.** No skill, command or agent index exists. Rules have `rules/_manifest.yaml` (generated), docs have `.ai-state/doc_manifest.yaml`, and ADRs have `scripts/query_adrs.py`.

### 3.2 How it reaches context, and what cannot be changed from Praxion

| Channel | Mechanism | Praxion lever today |
|---|---|---|
| Session listing | Native scan of `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md` frontmatter | Only by deleting, merging or relocating files, or with `disable-model-invocation` |
| Subagent spawn | Each spawn re-renders the listing, **plus** inherits 21,287 tokens of always-loaded rules, **plus** its `skills:` preloads | Frontmatter `skills:` lists |
| Agent-type enum | `agents/*.md` descriptions double as the `subagent_type` choices | Agent description length |
| Hook-delivered context | `SessionStart` / `UserPromptSubmit` stdout and `additionalContext` | **Can add, cannot remove.** dec-167 got *physical* exclusion for rules only because rules can be moved out of the native load path |

Hard constraints (VERIFIED against [official docs](https://code.claude.com/docs/en/skills) today and Praxion's records):

- `disable-model-invocation: true` removes the description *and* blocks preload into subagents *and* blocks Claude-initiated invocation. P1.12 rejected it for skills for exactly this reason.
- `skillOverrides` is documented with `name-only` and `user-invocable-only` states, but td-197 found it **inert on two independent instruments** at the time. The docs now describe the setting in detail, so a **cheap re-test on the current Claude Code version** is worth doing (§6 M3). If it now works, `name-only` becomes a free way to cut listing size for low-traffic skills.
- **No native state means "not in the listing, but model-loadable on demand".** Any search-then-load design has to supply it from outside the harness.

### 3.3 Preload is the elephant

Figures from the process-economy roadmap (VERIFIED there):

- Preloaded skill bodies total **240,647 tokens** across 17 agents, more than the 136,976 tokens of the agent definitions themselves.
- `external-api-docs` (5,156 tokens) is preloaded by 9 of 17 agents.
- The four interface-design skills are each preloaded by 5 agents.
- The implementer preloads 4.2× its own body.
- Resident context per spawn reaches 81,166 tokens for the systems-architect and 76,047 for the implementer.
- Only **12** `Skill` tool calls appear in **18,042** WAL rows.

The listing (9,243 tokens) is under 12% of a typical spawn's resident context. **Preload is where code mode's "index, not library" principle pays most.**

### 3.4 Selection-failure evidence

- **Invisibility (quantified).** In one session ~40 of 62 skills rendered name-only. The roadmap target of "62/62 visible in a 200k session" is still open.
- **Confusion (not measured).** The sentinel's latest report says its semantic pass, including "skill-description activation quality", *was not performed*. No log records a misfire. That points to the problem being unmeasured, not absent.
- **Near-miss clusters exist**, and the literature says these hurt most:
  - `api-design` / `api-design-craft` / `agentic-interface-design` / `api-documentation`
  - `roadmap-planning` / `roadmap-synthesis`
  - `testing-strategy` / `test-coverage`
  - `llm-prompt-engineering` / `agent-evals` / `llm-training-eval`
  - `software-design-principles` / `beautiful-code` / `refactoring`
  - `data-modeling` / `data-structure-design`

  ASSUMPTION: some of these pairs cause mis-selection. Falsifier: the golden eval in §6 M1 shows no confusion between them.

## 4. Reconciliation: where the two lenses meet

| External finding | Praxion fact | Consequence |
|---|---|---|
| Tool Search raises accuracy by removing candidates | 89 flat entries, near-miss clusters, truncation | The *accuracy* case for search applies to Praxion, not only the cost case |
| Tool Search is MCP-only | Praxion's pain is skills, agents and preload | MCP deferral already works for Praxion's own MCP servers. The skill problem needs a Praxion-built mechanism |
| Code mode's gain is cost; its accuracy gain is modest | Skills are *prose documents*, not callable functions | Skills don't need a sandbox. **Praxion's scripts and procedures** are the natural code-mode surface (§5.3) |
| Speakeasy: a meta-tool gets most of the savings without a sandbox | likec4's 18-tool discover → read → filter MCP is an in-repo precedent | A `search`/`get` meta-tool is the right first form |
| Ronacher: descriptions drift | Praxion's catalogue is first-party and versioned; `regenerate_rules_manifest.py` is the pattern | Generate the index from source in pre-commit. Drift becomes a CI failure, not a silent decay |
| ToolRet: general IR is weak at tool retrieval | Descriptions were already dieted around "trigger nouns" | BM25 over curated trigger vocabulary is the principled default. Add a reranker only if the eval demands it |
| Programmatic calling keeps intermediates out of context | Praxion already practises this for ADRs: the Discovery Protocol *forbids* a full `DECISIONS_INDEX.md` read and routes through `query_adrs.py` | **Praxion already applies code mode to one corpus**, ADRs. The move is to generalise that proven pattern to skills, commands and agents |

That last row is the key insight: Praxion doesn't need to import a foreign idea. The retrieval-first ADR Discovery Protocol *is* the search-then-read pattern, already accepted and enforced. Skills and preloads are the corpora it hasn't been applied to yet.

## 5. Design space for Praxion

### 5.1 Hierarchical disclosure: the catalog router (filesystem-of-tools, no code)

The mechanism:

- Keep a small **core** set natively listed: the skills most tasks need. The count would be set by the eval; ASSUMPTION ~15–20.
- Add one always-listed **`praxion-catalog`** skill. Its description names the domains it covers, and its body is a compact generated index of the long tail: id, a one-line trigger, and the path to the body.
- Agents read the body of whichever skill they select, and the reference files beneath it, with `Read`. That is Anthropic's `ls`/`cat` progressive disclosure, using a tool every agent already has.
- Subagent frontmatter keeps only the core preloads, plus an instruction to consult the catalogue.

Costs and caveats:

- A skill read via `Read` does not get the `Skill` lifecycle: no compaction re-attach, no `allowed-tools`, and no brace-form `${CLAUDE_PLUGIN_ROOT}` substitution *inside that body*. The catalogue body itself is loaded as a skill, so it gets substitution and can hand out absolute paths.
- Relocating long-tail skills out of `skills/` to get *physical* exclusion (the dec-167 analogue) changes the plugin layout and the Codex/Cursor exports. That is an architectural decision.

### 5.2 Meta-tool: a `praxion-catalog` MCP server (search / get)

Two tools, mirroring Cloudflare's shape and Speakeasy's argument:

- `search(query, kind?, k?)`: BM25 over a generated manifest (id, kind, triggers, summary, size, section anchors). It returns ids and one-line summaries.
- `get(id, section?)`: returns a body or a single *section*, so section-level retrieval sits below today's whole-file tier.

Properties:

- Claude Code defers MCP tools, so the resident cost is a name and a line of server instructions.
- Codex has an MCP bridge (`codex/config/manage-codex-mcp.py`), so this is the **most portable** mechanism. Cursor has no skills concept, and MCP is its only route.
- On its own it adds discovery and does *not* shrink the native listing. It pays off when combined with §5.1 relocation, or when it replaces preloads.

### 5.3 True code mode: Praxion procedures as a typed, discoverable API

Code mode fits **function-shaped** capabilities: Praxion's ~dozens of `scripts/*.py`, including `query_adrs`, `measure_token_budget`, `reconcile_pipeline_state`, the ledger checks and the metrics collectors. It also fits the procedure-heavy parts of commands. Expose them as one `praxion` CLI (or Python package) with self-describing subcommands (`praxion --help`, `praxion adr search …`). Agents then compose operations in a single Bash call with shell filtering, and only the result enters the context. This is the Zechner/CLI form of code mode. It needs **no new sandbox**, because Claude Code's permission model and Bash are the execution boundary, and it keeps Praxion's commands and skills from restating procedure in prose. Risks: prompt-injected composition (mitigated by read-only defaults and the existing gates), and discoverability depends on good `--help` text, which is itself a small "index".

### 5.4 Adaptive shortlist injection (behavioural nudge)

A `UserPromptSubmit` hook runs BM25, or a cheap classifier, over the manifest and injects "likely relevant: skill A, skill B, skill C (why)" as context. This matches the adaptive-shortlist result in arXiv:2605.24660. It **does not remove** listing tokens. It raises the prior on the right skills, which targets *confusion* and truncation-driven *invisibility*. It is cheap to try, and the eval can measure it directly. Jev's Choice primitive (≤255 options) or Haiku with structured output are candidate rankers; see the companion report.

### 5.5 Consolidation (reduce the denominator)

- Merge near-miss clusters and retire the 12 zero-evidence skills already identified by P1.12b but never executed.
- Tighten the agent descriptions, where the top 5 are all agents, by moving `<example>` blocks out of `description`.

This is the cheapest lever and the one the literature favours most directly: *fewer near-miss distractors*.

## 6. Ranked opportunities (low-hanging → elaborate)

Each item names the behaviour it changes, its proof, and its guard. "Tier" means the Praxion process tier the build would need.

### Tier 0: instruments (nothing can be shown to help without these)

| # | Item | What it proves | Effort |
|---|---|---|---|
| **M1** | **Skill-selection golden eval.** 40–80 real task prompts, each labelled with the skill(s) and agent that *should* be engaged, drawn from calibration-log rows and past pipelines. Run under `eval/` with a trajectory metric: was the right skill activated or preloaded, and were wrong ones pulled in? Report per near-miss cluster | Baseline selection accuracy and confusion pairs. Every later item is measured against this | Lightweight |
| **M2** | **Live truncation sample.** Run `/skill-doctor` in a fresh 200k session, and in a spawned subagent if possible. Record which entries render name-only | Confirms or refutes the 4.6× over-band risk *today* | Direct |
| **M3** | **Re-test `skillOverrides`** (`name-only`, `user-invocable-only`) on the current Claude Code version, with a control, per td-197's method | If it now works, a free listing lever appears. If not, file it upstream | Direct |
| **M4** | **`scripts/regenerate_skills_manifest.py`**, mirroring `regenerate_rules_manifest.py`: id, kind, description, trigger nouns, bytes/tokens, `disable-model-invocation`, section anchors, preloaded-by. Checked in pre-commit | The corpus every later mechanism needs. Drift fails CI | Lightweight |

### Tier 1: low-hanging (days, reversible, no new component)

| # | Item | Expected effect | Guard |
|---|---|---|---|
| **E1** | **Agent description diet.** Move `<example>` blocks and prose out of the 6 largest agent descriptions (~8 KB → ~2 KB). The agent body still holds them | ~1,500 tokens off every session's and spawn's listing | Agent-routing checks in M1 stay green |
| **E2** | **Execute the P1.12b consolidation.** Retire or merge the 12 zero-evidence skills and the worst near-miss pairs from M1 | Fewer entries *and* fewer distractors | M1 accuracy must not drop, and a merged skill's triggers must still route |
| **E3** | **Catalog-router pilot for one agent** (§5.1). Replace, for example, the implementer's heavy preloads with core plus the catalogue index plus on-demand `Read` | Tests whether just-in-time loading holds quality for the agent with the largest preload multiplier. Tens of thousands of tokens per spawn | Paired A/B on M1 plus an existing Praxion eval task. Revert if quality drops |
| **E4** | **Shortlist hint hook** (§5.4) in shadow mode: log the would-inject shortlist, then compare it with what was actually used | Cheap measurement of how well a retriever over the M4 manifest agrees with real selection | Advisory only, no injection until it measures well |

### Tier 2: structural (needs an architectural ADR; Standard tier)

| # | Item | Expected effect | Constraint / decision |
|---|---|---|---|
| **S1** | **`praxion-catalog` MCP server** (`search`, `get(id, section)`) over the M4 manifest, BM25 first | Near-zero resident cost (MCP deferral), section-level loads, Codex-portable | A new component, so an architectural ADR. Same shape as likec4 |
| **S2** | **Preload → just-in-time** across all agents: keep only truly always-needed preloads and point everything else at S1 or the router | Targets the 240,647-token preload line, which is the largest lever | Per-agent quality gate through M1 and agent evals. Some preloads (the behavioural contract, coding style) should stay |
| **S3** | **Physical relocation of the long tail** out of the native scan path (the dec-167 analogue for skills), served only via S1 or the router | Actually shrinks the native listing, not just adds to it | Plugin layout, `install.sh` Codex/Cursor exports, `${CLAUDE_PLUGIN_ROOT}` substitution, and the user's `/name` autocomplete for relocated skills. **The single largest decision** in this report |
| **S4** | **Shortlist injection live** (E4 promoted): inject the top-k with reasons when shadow agreement clears a threshold set from M1 | Attacks confusion and invisibility together (arXiv:2605.24660) | Adds tokens per prompt, so it must net out positive on M1 |

### Tier 3: elaborate (Full tier or a programme)

| # | Item | Why it's elaborate |
|---|---|---|
| **X1** | **`praxion` CLI as a code-mode surface** (§5.3): typed, self-describing subcommands over Praxion's scripts, so agents compose operations in one call and commands stop restating procedure | Cross-cutting: touches scripts, commands and agent prompts. Needs a stability contract for the CLI itself (Ronacher's point, applied to ourselves) |
| **X2** | **Section-addressable skills**: stable section anchors in every SKILL.md and reference, so `get(id, section)` returns a few hundred tokens instead of a whole body | Touches all ~63 skills and the skill-crafting conventions. Needs validator support |
| **X3** | **Capability requests** (MCP-Zero style): agents state the capability they need, and the catalogue resolves it hierarchically (domain → skill → section) | Research-grade. Worth it only if S1 plus S4 leave a measurable gap on M1 |
| **X4** | **Programmatic tool calling for heavy agents** (sentinel, roadmap-cartographer): analysis runs in scripts and only findings return | Overlaps process-economy Phase 2's "sentinel checks as scripts". Coordinate with that item rather than duplicating it |

### Watch items (don't build; re-check each release)

- `anthropics/claude-code#20143` (native skill search). If it ships, S1 and S3 may become unnecessary.
- MCP `tools/resolve` and non-exhaustive `tools/list` ratification.
- Whether `skillOverrides` starts working (M3), and whether a "hidden but loadable" skill state appears.
- The `ENABLE_TOOL_SEARCH` defaults, and deferral of HTTP-transport MCP tools (community issue #40314).

## 7. What must survive

- **The behavioural contract and always-on rules** stay always-loaded. They are *constraints*, not *capabilities*, and retrieval must never gate them.
- **Deterministic CODE gates** stay deterministic.
- **Progressive disclosure inside skills** (body → references) is the proven part. Keep it and extend it downward to sections (X2).
- **Portability.** Any mechanism must degrade to today's behaviour when the MCP server or hook is absent (the sentinel "TT idiom": skip with INFO).

## 8. Open questions

1. Does the harness truncate the *agent-type* list and the *commands* list under the same budget as skills, or separately? (M2 can answer this empirically.)
2. How does a subagent spawned with no invocation history rank skills for LRU-style truncation? Does every spawn see the *same* arbitrary truncation?
3. Does quality hold when an agent reads a skill body via `Read` instead of the `Skill` tool? (E3 measures this.)
4. Is BM25 over trigger nouns enough, or does M1 show confusion that needs a reranker? (Links to the Jev and Haiku arms in the companion report.)
5. Code mode versus meta-tool versus deferral: no shared head-to-head benchmark exists. If S1 and X1 both get built, Praxion's M1 plus cost collector could produce the first on a real catalogue.

## 9. Sources

Primary and official: [Cloudflare Code Mode](https://blog.cloudflare.com/code-mode/) · [Cloudflare Code Mode MCP](https://blog.cloudflare.com/code-mode-mcp/) · [Cloudflare codemode SDK](https://developers.cloudflare.com/agents/tools/codemode/) · [Cloudflare search+execute guide](https://developers.cloudflare.com/agents/model-context-protocol/guides/build-codemode-openapi-mcp-server/) · [Anthropic — code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) · [Anthropic — advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use) · [Anthropic — Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) · [Claude Code skills docs](https://code.claude.com/docs/en/skills) · [Claude Code tool search](https://code.claude.com/docs/en/agent-sdk/tool-search) · [Claude Code hooks](https://code.claude.com/docs/en/hooks) · [OpenAI tool search](https://developers.openai.com/api/docs/guides/tools-tool-search) · [OpenAI programmatic tool calling](https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling) · [MCP roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/) · [MCP progressive-disclosure WG #18](https://github.com/modelcontextprotocol/progressive-disclosure-wg/issues/18) · [agentskills](https://github.com/agentskills/agentskills) · [claude-code#20143](https://github.com/anthropics/claude-code/issues/20143)

Research: [Chroma Context Rot](https://research.trychroma.com/context-rot) · [RAG-MCP](https://arxiv.org/abs/2505.03275) · [ToolRet (ACL Findings 2025)](https://aclanthology.org/2025.findings-acl.1258/) · [LongFuncEval](https://arxiv.org/abs/2505.10570) · [MCP-Zero](https://arxiv.org/abs/2506.01056) · [How Many Tools Should an Agent See?](https://arxiv.org/abs/2605.24660) · [Tool-Use Tax](https://arxiv.org/html/2605.00136) · [Prompt-injection design patterns](https://arxiv.org/pdf/2506.08837)

Practitioner and vendor (quarantined as single-vendor claims): [Speakeasy dynamic toolsets](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2) · [GitHub MCP dynamic toolsets](https://github.com/github/github-mcp-server/issues/275) · [Vercel AI SDK](https://vercel.com/blog/ai-sdk-5) · [goose](https://block.github.io/goose/) · [Smithery Toolbox](https://smithery.ai/server/@smithery/toolbox) · [Composio](https://docs.composio.dev/docs/native-tools-vs-mcp) · [Zechner — MCP vs CLI](https://mariozechner.at/posts/2025-08-15-mcp-vs-cli/) · [Ronacher — Skills vs Dynamic MCP Loadouts](https://lucumr.pocoo.org/2025/12/13/skills-vs-mcp/) · [Microsoft — prompts become shells](https://www.microsoft.com/en-us/security/blog/2026/05/07/prompts-become-shells-rce-vulnerabilities-ai-agent-frameworks/)

Internal: `scripts/measure_token_budget.py` (run 2026-09-23) · `docs/context-economy.md` · `docs/independent-analysis/process-economy-roadmap.md` · `.ai-state/decisions/167-hook-delivered-blacklist-mechanism.md` · `.ai-state/TECH_DEBT_RESOLVED.md` (td-197) · `.ai-state/calibration_log.md` (P1.12 rows) · `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-09-14_07-59-49.md` · `skills/likec4-querying/references/mcp-tool-recipes.md` · `rules/_manifest.yaml`
