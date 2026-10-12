# Context Review: startup-context-diet (Praxion-originated resident content)

Task slug: `startup-context-diet` · Lens: Praxion-originated resident content and a lean kernel · Date: 2026-10-11 · Praxion HEAD 6f5c538a (v0.50.0) · Read-only audit; nothing in the repo was changed. Scratch scripts are in the session scratchpad, not the repo.

## 0. Headline findings

1. **The budget guard measures with a stale tokenizer.** `scripts/measure_token_budget.py` pins `_MODEL = "claude-sonnet-4-5"` (line 97). The same `count_tokens` endpoint returns about 1.49x more tokens for `claude-sonnet-5-5`, `claude-opus-4-7` and `claude-opus-5` (coordination rule: 4,702 vs 6,992 / 6,996 / 6,990; `claude-opus-4-5`, `claude-opus-4-6`, `claude-sonnet-4-6` and `claude-haiku-4-5` all return 4,702). The T02 governed set reads **16,787 tokens (67% of 25,000)** on the script's ruler and **24,413 (97.7%, headroom 587)** on the current-generation ruler. The listing surface is 9,169 vs 14,268. The orchestrator's `/context` categories (user CLAUDE.md 3.9k, project CLAUDE.md 3.9k, rules 13.4k, MEMORY.md 8k) match the current-generation ruler within 1%; they are exact for today's model, not an overestimate. The earlier spike's 21,287-token subagent-inheritance figure also sits on that ruler (R2 below gives 21,348).
2. **Praxion-originated content is about 59% of the first request.** 50.6k of 85.8k tokens (R2); the rest is harness system prompt, tools and other plugins.
3. **Subagents inherit about 21.3k tokens (R2) of rules and CLAUDE.md per spawn, and most of it is orchestrator or ADR-author content they never use.** The orchestrator coordination rule alone is 7.0k (R2); the ADR rule is 3.6k, and only 4 of 17 agents author ADRs.
4. **MEMORY.md (8.0k, R2) is the largest single non-rule item and has the wrong shape.** It is a status log, not an index: 94 lines, 25 over 200 characters, one line of 563 tokens. 24 of 95 memory files were created in the last 11 days.
5. **Two ML rules fire in ordinary pipelines of any managed project.** `ml/eval-driven-verification` and `ml/gpu-budget-conventions` are path-scoped to `.ai-work/**/WIP.md`, `SYSTEMS_PLAN.md` and similar; they load in about 45% of Praxion sessions. Praxion's own `.claude/settings.json` already excludes them via `claudeMdExcludes`; managed projects such as `crvntx` have no such exclusion.
6. **Praxion's likec4 MCP server puts about 1.3k (R2) of instructions into every session of every project with the plugin enabled**, whether or not the project has a LikeC4 workspace.

**Rulers.** R1 = the ruler `measure_token_budget.py` uses (`claude-sonnet-4-5` via `count_tokens`; subtract the 7-token request overhead per call). R2 = the same endpoint with `claude-sonnet-5-5`. Both are VERIFIED by live API calls today. Unless stated, tables give R1 / R2.

## 1. Inventory of Praxion-originated resident items (main session, Praxion repo)

| # | Item | Channel / when | R1 | R2 |
|---|---|---|---|---|
| 1 | `~/.claude/CLAUDE.md` (generated from `claude/config/CLAUDE.md.tmpl`, symlinked) | user memory, always, every project | 2,630 | 3,897 |
| 2 | `CLAUDE.md` (Praxion project) | project memory, always | 2,708 | 3,863 |
| 3 | `rules/CLAUDE.md` (symlinked as `~/.claude/rules/CLAUDE.md`; manifest `core: true`) | user rule, always, every project | 595 | 837 |
| 4 | `rules/swe/adr-conventions.md` | symlink, always | 2,496 | 3,554 |
| 5 | `rules/swe/agent-behavioral-contract.md` | symlink, always | 363 | 542 |
| 6 | `rules/swe/agent-intermediate-documents.md` | symlink, always | 1,123 | 1,670 |
| 7 | `rules/swe/swe-agent-coordination-protocol.md` | symlink, always | 4,695 | 6,985 |
| | **Subtotal: claudeMd surface (subagents inherit this)** | | **14,610** | **21,348** |
| 8 | `inject_rules.py`: `agent-model-routing` (967 / 1,357) + `git-conventions` (1,195 / 1,701) + header | SessionStart `additionalContext`; `hook-deliver`; not symlinked | 2,131 | 3,022 |
| 9 | `inject_decisions.py`: "Decision Context" (3,693 chars; soft cap 4,000) | SessionStart; top accepted ADRs scored on branch, tree and recent commits | 938 | 1,334 |
| 10 | Agent-type listing in the Agent tool: 17 `praxion:*` agents (description + tools) | main session | 3,273 | 5,018 |
| 11 | Skill listing: 72 model-invocable skills, full descriptions (35 are `disable-model-invocation` and hidden). The harness caps the listing at about 1% of the window (`/context` shows 10k), so the effective cost is min(this, cap) | main session | 6,865 | 10,580 |
| 12 | likec4 MCP server instructions (`plugin.json` `mcpServers.likec4`) | system prompt, any project with the plugin enabled | 941 | 1,332 |
| 13 | Auto-memory `MEMORY.md` (user, per project) | harness-loaded, always | 5,774 | 7,978 |
| | **Total resident, main session** | | **34,532** | **50,612** |

Per-turn and conditional injectors (all small; none is in the total):

| Hook | Fires | Size |
|---|---|---|
| `inject_process_framing.py` | `UserPromptSubmit`, every non-trivial, non-continuation prompt in a project with `.ai-state/`; text is "Use the tier selector... Carry the behavioral contract..." | 38 / 52 per prompt, cumulative |
| `inject_subagent_context.py` | `PreToolUse(Agent)`; the preamble is only for host-native agents (`Explore`, `Plan`, `general-purpose`) and praxion agents are skipped; worktree lines for any agent | about 81 tokens into the subagent prompt |
| `remind_task_brief.py`, `remind_turn_budget.py` (60% and 80% of `maxTurns`, once each), `remind_adr.py`, `remind_calibration.py` (commit gates) | tool events | one line each, conditional |
| `inject_compaction_orientation.py` | `SessionStart` matcher `compact` | conditional; not measured |
| `surface_praxion_feedback.py`, `heal_hook_chain.py`, `auto_complete_install.py`, `gate_sidecar_banner.sh` -> `inject_sidecar_banner.py` | `SessionStart` | 0 on the normal path: silent unless feedback is pending, hook chain unwired or install incomplete; the sidecar banner is skipped when `.ai-state` is a real directory |
| `send_event`, `capture_session`, `measure_context_surface`, `capture_observations` | async | no context |

Governed-set history (`.ai-state/token_budget_baseline.json`): bytes flat at 65.5-67.0k from 2026-09-07 to today. The always-loaded rules are not growing. The ratchet is suspended until 2026-11-30 by user decision.

### MEMORY.md detail (`~/.claude/projects/-Users-fperez-dev-praxion/memory/`)

- 94 index lines, 19,200 bytes, 95 files in the directory. Creation months: 2026-03 (1), 05 (6), 06 (7), 07 (6), 08 (10), 09 (41), 10 (24 in 11 days). Growth is now about 2 entries per day, each about 200 bytes.
- Line lengths: median 183 characters; 85 of 94 lines exceed 150; 25 exceed 200. Longest lines (tokens R2): Ralph loops programme 563 (1,225 chars, a running status log), commands->skills pipeline 155, Split amends acceptance criteria 136, likec4-diagram-craft status 146, Step-loop `Files:` globs 108, A Check runs without a shell 102.
- 16 lines are `project_*` status entries that accrete a history clause per update.
- Trial prune, measured: truncate every line to 150 characters at a word boundary: 5,774 -> 4,343 (R1), 7,978 -> 5,938 (R2). Also drop the 3 CLOSED/RETIRED lines: 4,190 / 5,742.
- Headroom to the harness load limit is a matter of weeks. I recall a 200-line / 25 KB cap in the Claude Code memory docs but did not re-fetch it today: ASSUMPTION. At 19.2 KB it has 5.8 KB of room, about 2-3 weeks at the current rate.
- The pattern generalizes: `sandbook` (a managed project) has an 11.8 KB `MEMORY.md`.

## 2. Per-item purpose, plausible need and duplication

### Usage evidence and its limits

Source: `.ai-state/observations.jsonl(.1)`, 2026-08-07 to 2026-10-11, 119 session ids, 68 with main-session tool use. Limits: (a) nearly all rows are `project: praxion` (102 of 124 session starts), so this is self-hosting evidence from a pipeline-heavy repo, not managed-project telemetry; (b) counts include subagent rows inside the session; (c) the path-scoped trigger is a Read, and the WAL records only 317 Reads, so I used Read, Edit and Write paths as a proxy. Treat the numbers as an upper bound for Praxion and an unknown for other projects.

Share of the 68 sessions: main session spawned an Agent 62%; any `agent_start` 69%; touched `.ai-work/` 78%; touched `.ai-state/` 51%; touched `.ai-state/decisions` 35%; a Bash call classified `commit` 57%; any `gate_fire` 50%; any `skill_activation` 31% (26 rows in total); `EnterWorktree` 7%; WebFetch or WebSearch 26%.

### Always-on rules and CLAUDE.md sections (R1 tokens; R2 is about x1.45)

| Item | Purpose | Plausible need | Duplicated at |
|---|---|---|---|
| Behavioral contract rule (363) | The four non-negotiable behaviors | 100%, constraint; 14 of 17 agent prompts cite it by path | user CLAUDE.md "Behavioral Contract" (76), project CLAUDE.md "Behavioral Contract (applied)", canonical block `behavioral-contract` (224, shipped to managed projects), `inject_process_framing` (every prompt), `inject_subagent_context` preamble, the coordination rule, `skills/software-planning/references/behavioral-contract.md` |
| Coordination protocol (4,695): Process Calibration 1,010; Coordination Pipeline table 1,405; Proactive Agent Usage 683; Conversation Checkpoints 503; Delegation Checklists 225; Pipeline Isolation 186; Agent Selection 171; others about 500 | Orchestrator's tier selection, spawn rules, handshake, checkpoints | Main session: about 62% (spawn sessions); tier selector applies to any non-trivial prompt. Subagents: about 0%, since they cannot spawn and the rule addresses "the main agent" | Delegation text in user CLAUDE.md Methodology (about 120); tier selector in `inject_process_framing`, canonical blocks `praxion-process` (216) and `agent-pipeline` (177), and `coordination-details.md` / `agent-pipeline-details.md` deep-dives (most rows are already pointers) |
| ADR conventions (2,496): File Format 1,085 (mostly pointers plus the `architectural` test), Relation Protocols 281, Who Writes 225, Discovery 227 | ADR authorship and retrieval discipline | 35% of Praxion sessions touch decisions; authors are 4 of 17 agents plus the orchestrator | Canonical in `skills/software-planning/references/adr-authoring-protocols.md`, which the rule links on nearly every section; the Discovery Protocol is also needed by readers |
| Agent intermediate documents (1,123) | `.ai-work/` vs `.ai-state/`, slug convention, cleanup | 78% touch `.ai-work`; subagents write there but receive the slug in the prompt | Canonical trees in `artifact-inventory.md`; the slug convention is also in `coordination-details.md` |
| `rules/CLAUDE.md` (595): Conventions 205, Token Budget 241, Installation 47, Modifying Rules 48 | Authoring guidance for the Praxion `rules/` tree | Only when editing Praxion rules; 0% in other projects. Already auto-loads on demand as a subdirectory `CLAUDE.md` when `rules/` is touched | Token budget text is restated in project `CLAUDE.md` "Critical conventions" and the `rule-crafting` skill; "Modifying Rules" duplicates project CLAUDE.md "Component crafting" |
| `git-conventions` (1,195; hook-delivered): Staging Discipline 510, Commit Format 220, Scope 171 | Commit hygiene | 57% have a commit; staging and "no AI authorship" are safety-adjacent | "No AI authorship" appears in user CLAUDE.md, project CLAUDE.md, the behavioral-contract rule and this rule (4 sites); the commit-process canonical block duplicates the procedure |
| `agent-model-routing` (967; hook-delivered): Tier Table 656 | Orchestrator passes `model:` per spawn | 62% | The same agent-to-model mapping lives in each agent's frontmatter `model:`; the long form is in `skills/agent-crafting/references/model-routing-policy.md` (two sources of truth) |
| User CLAUDE.md (2,630): Principles 1,253 (nine principles; Context Engineering 230, Balanced Coupling 293, Data Structures First 212, Structural Beauty 141); Methodology 635; Ecosystem 311; Operating Conventions 185; Learning Loop 74; Personal 65 | Worldview and workflow, every project | Unconditional, but depth for Data Structures, Beauty and Coupling lives in three named skills; the Ecosystem section says components are "never enumerated" and then characterizes them | Build output to `/dev/null` and `tmp/` also in project CLAUDE.md; Behavioral Contract section is a pointer to the rule; Learning Loop is a pointer |
| Project CLAUDE.md (2,708): Claude-Code-specific machinery 596; Frequent operations 397; Critical conventions 395; Build/test/lint 384; Reading order 203; Layout 174; Where to find more 163; Known limitations 131; Obsidian 110; How to verify 101 | Praxion repo baseline | Build/test/lint and critical conventions are needed; the rest is navigation | Reading order restates load semantics already in `rules/CLAUDE.md` and `rule-crafting`; "Behavioral Contract (applied)" and "Compaction Guidance" duplicate the rule and the canonical block; token budget appears again |

### Cross-surface duplication, worst cases

- **The behavioral contract exists at 7 sites.** The only copy that has to be resident is the rule (363). The managed-project block (224) is justified for teammates who lack the global install; it is redundant for the author's own machine, where the rule is already global.
- **Tier selector and delegation obligations exist at 5 sites** (coordination rule, per-prompt hook, two canonical blocks, user CLAUDE.md Methodology).
- **Token budget text exists at 3 sites** (`rules/CLAUDE.md`, project CLAUDE.md, `rule-crafting`).
- **The model-routing table is duplicated by agent frontmatter.**
- **Contradiction to verify (ASSUMPTION):** the canonical `praxion-process` block says host-native subagents "do not load CLAUDE.md"; `agent-crafting` says subagents inherit `claudeMd` (measured 21,287). Both can be true by agent type (Explore and Plan are reported to skip it), but the orchestrator's ablations should settle it, because it decides whether per-project blocks are the only path to host-native agents.

## 3. Subagent inheritance

Each spawn receives: the claudeMd surface (items 1-7, 14,610 R1 / 21,348 R2); its own body; its `skills:` preload bodies (full `SKILL.md`, no references). The hook-delivered rules (item 8) are not inherited, since `SessionStart` does not fire for subagents. That is a Praxion-doc claim (`agent-crafting`), SINGLE-SOURCE, but it is consistent with the earlier spike's 21,287 figure, which equals the claudeMd surface and excludes item 8. The skill and agent listings are likely present in subagents too; I did not verify this (ASSUMPTION). Native-subagent prompt additions are about 81 tokens.

### Per-agent table for today's tree (R2; R1 sums below)

| Agent | Model | Description | Body | Preload | Preload skills | Spawn total (inherit 21,348 + body + preload) |
|---|---|---|---|---|---|---|
| agentic-transactions-architect | opus | 672 | 6,117 | 15,467 | agentic-transactions, mcp-crafting, agentic-sdks | 42,932 |
| architect-validator | opus | 316 | 6,800 | 0 | none | 28,148 |
| cicd-engineer | sonnet | 190 | 3,382 | 6,055 | cicd | 30,785 |
| context-engineer | sonnet | 223 | 6,180 | 23,068 | skill-crafting, rule-crafting, agent-crafting | 50,596 |
| discipline-consultant | sonnet | 309 | 4,633 | 3,067 | multi-perspective-analysis | 29,048 |
| doc-engineer | haiku-4-5 | 199 | 6,793 | 14,870 | doc-management, web-ui-design, api-documentation | 43,011 |
| implementation-planner | sonnet | 175 | 17,758 | 13,310 | software-planning, data-structure-design | 52,416 |
| implementer | sonnet | 160 | 9,910 | 14,490 | software-planning, code-review, refactoring | 45,748 |
| interface-designer | opus | 519 | 5,808 | 25,053 | web-ui-design, tui-design, agentic-interface-design, api-design-craft, api-design, api-documentation | 52,209 |
| promethean | opus | 202 | 7,789 | 23,916 | software-planning, web-ui-design, tui-design, agentic-interface-design, api-design-craft | 53,053 |
| researcher | sonnet | 140 | 9,075 | 5,087 | claude-ecosystem | 35,510 |
| roadmap-cartographer | opus | 832 | 6,823 | 10,720 | roadmap-synthesis, roadmap-planning | 38,891 |
| sentinel | sonnet | 426 | 34,715 | 0 | none | 56,063 |
| skill-genesis | sonnet | 223 | 7,962 | 17,552 | skill-crafting, rule-crafting | 46,862 |
| systems-architect | opus | 185 | 18,280 | 11,147 | claude-ecosystem, data-structure-design | 50,775 |
| test-engineer | sonnet | 212 | 12,381 | 14,490 | software-planning, code-review, refactoring | 48,219 |
| verifier | opus | 147 | 20,135 | 9,272 | code-review, context-security-review | 50,755 |
| **Sums** | | 5,018 | 184,541 | **207,564** | | |

- **Preload sum for today's tree: 207,564 (R2) / 145,138 (R1)** across 17 agents. The spike's 240,647 does not reproduce on either ruler.
- **What changed since 2026-09-23:** `external-api-docs` (5,156 tokens, preloaded by 9 of 17 agents, about 46k) was dropped from the agent preloads (commits 039f6ef1 / 7c5904b0, 2026-09-23) and the skill was retired in 2c770d63. Implementer preload is now 14,490 (R2), down from 27,138. Agent bodies sum to 128,042 (R1) vs 136,976 then. The commands->skills migration (dec-449) moved 44 workflows to skills; 35 skills are user-only and hidden from the model listing, so the listing is 72 entries.
- **Most-preloaded bodies (R2 tokens x agents):** `software-planning` 7,250 x 4; `web-ui-design` 6,134 x 3; `rule-crafting` 10,387 x 2 (the largest single `SKILL.md`); `skill-crafting` 7,165 x 2; `data-structure-design` 6,060 x 2; `claude-ecosystem` 5,087 x 2; the `api-*`/`tui`/`agentic-interface` family is preloaded 9 times in total. The WAL still shows 26 `skill_activation` rows against 817 `agent_start` rows, so on-demand use remains rare; agents get skills by preload.
- **Standard-tier pipeline bill (16 spawns):** 16 x 21,348 = 341,568 R2 tokens of inherited rules and CLAUDE.md, before bodies and preloads. Most of it is cache reads, so the effect is chiefly attention and quality, not price.

## 4. Managed-project angle

Measured one: `/Users/fperez/dev/crvntx` (has `.ai-state/`, the four canonical blocks, and `.claude/praxion-rules.yaml.example` only, so no active blacklist). Ten local repos carry `.ai-state/`.

| Praxion-originated item in a managed project | R1 | R2 |
|---|---|---|
| Global: user CLAUDE.md + `rules/CLAUDE.md` + 4 symlinked core rules | 11,902 | 17,485 |
| Hook-delivered rules (`agent-model-routing`, `git-conventions`) | 2,131 | 3,022 |
| Four canonical blocks inside the project `CLAUDE.md` (Agent Pipeline 177 + Behavioral Contract 198 + Compaction Guidance 122 + Praxion Process 216) | 713 | 1,058 |
| Agent listing + skill listing + likec4 MCP instructions | 11,079 | 16,930 |
| **Praxion-originated, before any of the project's own content** | **about 25.8k** | **about 38.5k** |

- `crvntx`'s own `CLAUDE.md` is 2,202 (R1) / 3,093 (R2); `test-agent` 1,864 / 2,648; `wasmer-sdk-mcp` (hackathon block) 3,579 / 5,111; `sandbook` 4,575 / 6,435. Optional blocks measured in `claude/canonical-blocks/`: hackathon-mode 2,438 / 3,468; obsidian-integration 904 / 1,265; sidecar-placement 338 / 448; commit-process 345 / 472; testing 316 / 411.
- **Nothing in this payload is specific to what the project does.** The global rules, listings and MCP instructions arrive identically in a project with no `.ai-state/`. About 100 other directories under `/Users/fperez/dev` carry no `.ai-state/` but still receive the global CLAUDE.md, all five symlinked rules and the likec4 instructions. Only the hook-delivered pair is blacklistable.
- **The `praxion-rules.yaml` blacklist cannot reach the big rules.** The five symlinked rules are `core: true` ("non-disableable"), including `rules/CLAUDE.md`. The only per-project levers today are path-scoped rules and `claudeMdExcludes`.
- The `hook-deliver` channel already exists, is manifest-driven, supports a per-project blacklist, and does not reach subagents. Gating it on `.ai-state/` existence is the missing piece for non-managed projects.
- Finding 5 in section 0 shows managed-project exposure: the two ML rules match `.ai-work/**/WIP.md` and friends and load in ordinary pipelines unless excluded.
- Memory growth generalizes: `sandbook`'s `MEMORY.md` is 11.8 KB.

## 5. Proposed lean kernel

### What must stay always-resident (constraints, not conveniences)

| Keep | Size R1 / R2 | Why |
|---|---|---|
| `agent-behavioral-contract.md` | 363 / 542 | The stance; 14 agent prompts cite it by path; subagents depend on inheriting it |
| Tier selector (Process Calibration table, Pipeline Isolation, Delegation Depth) | about 1,300 / 1,887 | Every non-trivial main-session prompt needs it; keep for the orchestrator only |
| Compressed user CLAUDE.md | about 1,500 / 2,200 | Worldview, response style, safety conventions |
| Project CLAUDE.md essentials (build/test, critical conventions, never edit plugin cache, no AI authorship) | about 2,000 / 2,900 | Per-repo identity |
| A 4-line git kernel (one logical change; stage named files, never `-A`; no secrets; no AI authorship) | about 250 / 350 | Safety-adjacent; a late advisory cannot undo a bad `git add` |

### Ranked moves (savings x safety)

Savings are tokens removed from resident context. "Main" = the main session; "Spawn" = each subagent spawn. R2 savings are measured where noted and otherwise scaled by about 1.45. Risk: L = low, M = medium, H = high.

| Rank | Move | Best placement | Save main R1 / R2 | Save per spawn R1 / R2 | Risk | Risk detail |
|---|---|---|---|---|---|---|
| 1 | Stop symlinking `rules/CLAUDE.md` globally | Repo-local only: it already loads on demand as a subdirectory CLAUDE.md when `rules/` is read | 595 / 837 (also every non-Praxion project) | 595 / 837 | L | `regenerate_rules_manifest.py` `EXPECTED_CORE_IDS` and the T02 file set must change; the project CLAUDE.md cites its Token Budget section |
| 2 | Cap `MEMORY.md` lines and prune status history | A <=110-character line rule in the memory-writing guidance plus `/clean-auto-memory`; move run-state histories (the Ralph loops line is 563 tokens) into the linked file | 1,431 / 2,040 (measured, 150-char cap); 1,584 / 2,236 with CLOSED lines dropped; about 2,500 / 3,500 at 100 chars (estimate) | 0 | L | The link target keeps the detail. The user owns the memory; the durable fix is a writing rule or check, not a one-off prune |
| 3 | Make the coordination protocol orchestrator-only | `hook-deliver` (already exists), gated on `.ai-state/`; leave a <=1,300-token tier kernel for the main session. Keep the dispatch tables in `coordination-details.md` | 0 in managed projects; 4,695 / 6,985 in non-managed ones | 4,695 / 6,985 (full), 3,402 / 5,105 (if a kernel stays symlinked) | M | Relies on `SessionStart` re-firing after `compact` (matcher `""` should cover it; verify). Subagents lose the return-contract row; two agent prompts state it and the native preamble covers the rest. Needs an ablation of pipeline handshake behavior |
| 4 | Shrink `adr-conventions` to a kernel | Keep header, Who Writes, Agent Writing Protocol, Discovery, Linking (733 / 1,058); move File Format, Relation Protocols, Finalize, Consumption, Migration to `adr-authoring-protocols.md`, which the rule already links | 1,770 / 2,503 | 1,770 / 2,503 | L-M | The rule calls itself the "source of truth" for the `architectural` test; that test must move with an updated pointer. 13 of 17 agents never author ADRs; the 4 authors reach the skill reference anyway |
| 5 | Compress the Principles section of the user CLAUDE.md | Same file, one sentence per principle, each pointing to its skill. Trial text measured | 962 / 1,423 (measured: 1,268 -> 306 R1; 1,867 -> 444 R2) | 962 / 1,423, and every non-Praxion project | M | The user values the worldview; the effect on behavior is unmeasured. Gate with a paired behavior eval before accepting. Context Engineering and Behavior-Driven carry the most behavioral weight; keep them whole |
| 6 | Register the likec4 MCP server at project scope only | Onboarding writes `.mcp.json` where `docs/diagrams/` holds a LikeC4 model; remove from `plugin.json` | 941 / 1,332 plus 20 deferred tool names | 0 | L-M | `likec4-diagramming` skill and Praxion's own diagram flow need the server in this repo; installer and onboarding contract change |
| 7 | Trim the four longest agent descriptions (roadmap-cartographer 832, agentic-transactions-architect 672, interface-designer 519, sentinel 426 R2) to about 200 each | Same files | about 1,100 / 1,600 (estimate) | 0 | L | Descriptions are the delegation trigger; keep the trigger phrases |
| 8 | Trim project CLAUDE.md: drop Reading order (203), the "Behavioral Contract (applied)" and "Compaction Guidance" paragraphs (duplicated by the rule and the block), compress Known limitations and Obsidian to one line each | `CLAUDE.md` (the `## Structure` section is not touched by this proposal) | about 500 / 750 (estimate) | about 500 / 750 | L | Navigation moves to `docs/README.md`; Praxion repo only |
| 9 | Replace the `agent-model-routing` table with a deterministic default | `inject_subagent_context.py` (the single `updatedInput` emitter) sets `model` from the target agent's frontmatter when the orchestrator omits it; the override policy stays in `model-routing-policy.md` | 967 / 1,357 | 0 (already not inherited) | M | The Agent tool's model enum lacks a Haiku 4.5 pin (memory note), so `doc-engineer` needs a special case; the hook is a stronger guarantee than the rule |
| 10 | Split `git-conventions`: 4-line kernel resident, the rest injected on first `git add`/`commit` by `commit_gate.sh` | PreToolUse trigger | about 900 / 1,300 | 0 | M | A PreToolUse reminder arrives after the model wrote the command, so keep the kernel resident |
| 11 | Cap or trigger `inject_decisions` | Lower `ADR_SOFT_CAP` from 4,000 to about 1,500 characters, or run `query_adrs.py --paths` on the first Edit of a file | about 450-940 / 650-1,330 | 0 | M | Decisions are called "hard constraints"; the value of broad session-start injection vs path-matched is untested |
| 12 | Fire `inject_process_framing` once per session (and after compaction) | Hook | 38 / 52 x (N-1) prompts | 0 | L-M | Per-prompt recency reinforcement might help; test before removing |
| 13 | Path-scope `agent-intermediate-documents` to `.ai-work/**` and `.ai-state/**` | Rule `paths:` | 1,123 / 1,670 where those paths are not read | same | M | Path-scoped rules load on Read, not Write; agents that create `.ai-work` files without a prior Read miss it (documented gap). 78% of Praxion sessions touch `.ai-work`, so the saving is smaller than it looks |
| 14 | Remove the two ML rules' pipeline-document globs (`.ai-work/**/WIP.md`, `SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`, ...) | Edit `paths:` in `ml/eval-driven-verification` (2,366 chars) and `ml/gpu-budget-conventions` (1,565 chars); keep ML-specific globs | about 900-1,000 / 1,300-1,450 in ~45% of managed-project sessions | same | L | ML projects keep `train.py`, `runs/**`, `program.md`; confirm ML pipelines do not depend on the `.ai-work` trigger |
| 15 | Reduce agent preloads | Keep one anchor skill per agent; move the rest to a "read when needed" pointer; evaluate with `agent-evals` | none | 3k-12k per spawn on average (up to about 100k of the 207k roster total) | H | Praxion-evidence is that skills arrive by preload; quality loss is plausible. Needs per-agent evals first. Largest lever, riskiest |
| 16 | Skill listing diet (names + trigger-only descriptions) | `description:` frontmatter | up to about 6k R2 (10,580 -> about 4-5k; estimate) | maybe 0 | M | Scope of the prior spike; the harness already truncates at about 1% of the window, so discoverability is partly lost now |
| 17 | Merge the four canonical blocks | One 300-token block in `claude/canonical-blocks/` | 0 | about 400 / 600 per managed project | L-M | `sync_canonical_blocks.py` and `block-history.json` consumers |
| 18 | Fix the ruler | `measure_token_budget.py`: make `_MODEL` configurable, default to the model in use, report both rulers; T02 ceiling to be re-based | 0 | 0 | L | This reveals the guard has 587 tokens of headroom, so Rank 1-5 moves become necessary before further additions; the ratchet suspension ends 2026-11-30 |

### Combined effect (arithmetic on the table; estimates marked above)

- **Subagent kernel** (moves 1, 3, 4, 5, 8): 14,610 -> about 6,100 (R1), 21,348 -> about 8,900 (R2). That is -58% per spawn. At 16 spawns the inherited rules fall from about 342k to about 142k (R2).
- **Main session** (moves 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 14): 34,532 -> about 24,700 (R1), 50,612 -> about 36,600 (R2): about -28%. With move 3 in a non-managed project: a further 4.7k / 7.0k. The preloads (move 15) and skill listing (move 16) are the two remaining large levers and carry the most quality risk.
- **Order of work by savings x safety:** 18, 1, 2, 14, 4, 6, 7, 8, then 3 and 5 behind evals, then 9-13, with 15 and 16 last.

## 6. Open items and assumptions to settle in synthesis

1. Which tokenizer the orchestrator's session actually uses: R2 matches `/context`; Opus 4.5/4.6 and Sonnet 4.5/4.6 would match R1. (VERIFIED for the `count_tokens` endpoint; the session model itself is not.)
2. Whether `SessionStart` rule injection survives `compact` and is absent in subagents: SINGLE-SOURCE (Praxion docs and consistent measurement; not ablated).
3. Whether Explore and Plan agents load CLAUDE.md (conflicting Praxion statements): ASSUMPTION.
4. The MEMORY.md harness load cap (200 lines / 25 KB): ASSUMPTION, recalled from docs, not re-fetched.
5. Usage evidence is Praxion-self-hosting only; managed-project session behavior is unmeasured.
6. Quality effect of any cut is unmeasured here. Moves 3, 5, 9, 12 and 15 need a paired behavior eval (`agent-evals` / `/eval-praxion`) before landing.
