# Research Findings (harness-native lens): Startup-context levers in Claude Code

**Date / version**: 2026-10-11; installed Claude Code 2.1.296 (changelog head 2026-10-09). Task slug `startup-context-diet`, lens `harness-native`.
**Tags**: VERIFIED = official page fetched today (`code.claude.com/docs/en/*.md`, `platform.claude.com/docs/en/*.md`, GitHub issue via `gh`); PROBED = measured by me today with `claude -p --agents` on 2.1.296 (n=1 per arm, API-key auth, cwd = Praxion repo); SINGLE-SOURCE; ASSUMPTION.
**Scope note**: descriptive, not prescriptive. "Who controls" is the key column: **plugin** (Praxion's `plugin.json`, skills/, agents/, hooks/, `.mcp.json`) vs **project settings** (`.claude/settings*.json`, which `onboard-project` can write) vs **user settings** (`~/.claude/*`, which `install.sh` writes) vs **harness only**.

## Research Goal
Map every native Claude Code / Anthropic-platform mechanism (Oct 2026) that shrinks or shapes the resident context of a session and of each subagent, and say who can pull each lever.

## Headline findings
1. **A plugin cannot ship rules, cannot set `skillOverrides`/listing budget, and cannot toggle individual components.** Plugin standard layout = manifest, skills, commands, agents, hooks, MCP, LSP, output-styles, workflows, themes, monitors, bin, settings; plugin `settings.json` honors only `agent` and `subagentStatusLine` (plugins/manifest-reference.md, plugins/components.md; VERIFIED). Praxion's always-on rules therefore reach sessions only through user-scope files (`install.sh` symlinks into `~/.claude/rules/`) or SessionStart hook injection. This is the structural reason the 13.4k rules block exists at user scope.
2. **The "hidden but loadable skill" tier already exists and is `disable-model-invocation: true`** (description not in the listing, zero resident cost, user `/name` loads it). Claude Code staff confirmed this on 2026-08-17 in #75376 (closed COMPLETED). Cost: the *model* cannot load such a skill either, and it cannot be preloaded into a subagent. A "model-loadable but unlisted" state does not exist; all native skill-search requests (#20143, #84666, #43816, #67448) are closed NOT_PLANNED.
3. **`omitClaudeMd: true` (>=2.1.271) is a plugin-agent-supported, subagent-specific baseline cut, and it is big.** PROBED: a subagent with `omitClaudeMd` started at **~2.8K tokens** vs **~32.4K** for the same agent without it (both `tools: [Read]`). It removes user CLAUDE.md, project CLAUDE.md, unscoped rules, **and the MEMORY.md index**; git status stays. It is all-or-nothing (no "keep rules, drop memory").
4. **Docs and behaviour diverge on subagent auto-memory**: docs say the main conversation's auto memory "isn't loaded" into subagents; PROBED subagent quoted a MEMORY.md entry verbatim and token arithmetic matches (see Divergence Map).
5. **Caching makes the dollar cost of a 60-90K resident prefix small; the case for dieting is attention/adherence and latency, not spend** (arithmetic below). Anthropic's own docs frame it that way: "Longer files consume more context and reduce adherence"; "Bloated CLAUDE.md files cause Claude to ignore your actual instructions".
6. **Praxion's `rules/CLAUDE.md` statement "path-scoped rules inject on Read, not Write/Edit" is stale as of 2.1.288 (2026-10-02)**: path-scoped rules and nested CLAUDE.md now also load on Write/Edit, and (2.1.293) on single-file `cat/head/tail/sed -n/grep` Bash reads. Lazy channels are more reliable than when Praxion's mitigation was designed.

## Mechanism table

| Mechanism | What it changes | Default | Limit | Who controls | Source / tag |
|---|---|---|---|---|---|
| CLAUDE.md (managed / user / project / local) | Concatenated into a user-message block after the system prompt, root -> cwd order | all eager | <=4 MiB loaded, larger skipped; docs target <200 lines/file; startup warning for large files and (since 2.1.281) combined set; each CLAUDE.md, rule and `@import` counts as a file | user/project/local files; managed. **Not plugin** | memory.md VERIFIED |
| Ancestor vs descendant CLAUDE.md | Ancestors (cwd upward) eager; **subdirectories under cwd are lazy**: load on first Read/Write/Edit (2.1.288) or single-file Bash read (2.1.293) of a file there | ancestors eager, descendants lazy | summarized away by /compact, reload on demand | project layout | memory.md, changelog VERIFIED |
| `@imports` | Expanded **eagerly at launch**; "helps organization but doesn't reduce context" | eager | depth 4; outside-cwd imports need one-time approval | file author | memory.md VERIFIED |
| HTML block comments | Stripped from CLAUDE.md before injection (code fences preserved) | on | - | file author | memory.md VERIFIED |
| `.claude/rules` / `~/.claude/rules` **without** `paths:` | Loaded at launch at `.claude/CLAUDE.md` priority; re-injected after /compact | eager | counts toward large-instructions warning | user/project files. **Plugin cannot ship rules** | memory.md, context-window.md VERIFIED |
| rules **with** `paths:` | Load when Read/Write/Edit (or single-file Bash read) touches a match; live in message history so /compact drops them and they reload on demand | lazy | 1,000 expanded patterns / 4 MiB per rule; only `paths` is read from rule frontmatter | same | memory.md, context-window.md, changelog 2.1.288 VERIFIED |
| `claudeMdExcludes` | Skips CLAUDE.md / rules by absolute-path glob; arrays merge across layers; managed cannot be excluded | none | user-scope-file exclusion by a project setting is not shown in docs (example excludes ancestor and rules dirs) | user/project/local/managed settings | memory.md VERIFIED; project-excluding-user-rules = ASSUMPTION |
| "Project instructions" mode, value `managed-only` | At launch loads only managed CLAUDE.md + auto memory; drops user/project/local CLAUDE.md, `.claude/rules`, AGENTS.md; nested + path-scoped still lazy | `claude-md-or-agents-md` | read only from user settings / `--settings` / managed (ignored in project and local files) | user or managed | memory.md VERIFIED |
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` | No CLAUDE.md, user/project/auto memory | off | all-or-nothing | env | env-vars.md VERIFIED |
| Auto-memory `MEMORY.md` | Index loaded each session; topic files never at start | on | **first 200 lines or 25 KB**; truncation warning with line count (2.1.268); `autoMemoryEnabled`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`, `autoMemoryDirectory` | user/project settings, env | memory.md, changelog VERIFIED |
| Skills listing | Name + description for every model-invocable skill, every turn; **not re-injected after /compact** | on | budget **1% of the model's context window** (`skillListingBudgetFraction`, default 0.01; or `SLASH_COMMAND_TOOL_CHAR_BUDGET` chars); overflow drops descriptions of least-used skills first, names always kept; per-entry `description`+`when_to_use` cap **1,536 chars** (`skillListingMaxDescChars`) | project/user/local settings. **Not plugin** | skills.md, settings-reference.md VERIFIED |
| `disable-model-invocation: true` | Description absent from listing, zero resident cost; `/name` still works; blocks model invocation and subagent preload; model told to ask the user to run it | false | binary | **skill author = plugin can pull** | skills.md, context-window.md, #75376 VERIFIED |
| `user-invocable: false` | Hides from `/` menu only; description stays resident | true | - | skill author | skills.md VERIFIED |
| `skillOverrides` `on / name-only / user-invocable-only / off` | `name-only` = listed without description; `user-invocable-only` = hidden from model; `off` = hidden entirely | `on` | **"Plugin skills are not affected by skillOverrides"; manage via /plugin** | user/project/local/managed settings; non-plugin skills only | skills.md VERIFIED |
| Skill `paths:` frontmatter | "loads the skill automatically only when working with files matching"; docs do not say whether the **listing entry** is withheld until a match | - | listing effect UNKNOWN | skill author | skills.md SINGLE-SOURCE; effect = open question |
| Nested `<subdir>/.claude/skills/` | Not loaded at startup; load on first Read/Edit in subtree | lazy | project layout only | project | skills.md VERIFIED |
| `/skill-doctor`, `/doctor` | Per-skill listing cost and never-invoked skills (>=2.1.261) | - | bundled/enterprise skills excluded | user | skills.md, changelog VERIFIED |
| Plugin enable/disable | `enabledPlugins` per scope; `defaultEnabled` in manifest (default true; user entry persists across updates) | per plugin | **whole-plugin granularity; no per-skill/agent/hook toggle**; enabling skills/agents/hooks appends content, never invalidates cache; MCP-bearing plugin follows MCP cache rules | project/user/local/managed settings; plugin author via `defaultEnabled` | settings-reference.md, manifest-reference.md, prompt-caching.md VERIFIED |
| Agent-type listing | Custom agent names + descriptions appear in the main session (visible in #100813 reports as "agent-type listing") | on | size not documented; `permissions.deny: ["Agent(name)"]` removes | settings; agent author (description length) | #100813 SINGLE-SOURCE; deny rule: sub-agents.md VERIFIED |
| MCP tool search | MCP tool defs deferred; only names + server `instructions` resident; `ENABLE_TOOL_SEARCH` unset/true/auto/auto:N/false; per-server `alwaysLoad` (`false` defers all, 2.1.287) | deferred | `auto` = 10% of window; **server instructions and up-front tool descriptions capped at 4,096 chars as of 2.1.296** (docs page still says 2,048); tool descriptions loaded via search cut at 16,384 (2.1.295); `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` | env; **plugin MCP author controls instruction text** | mcp.md + changelog 2.1.295/296 VERIFIED |
| Deferred tool schemas (billing) | API: "the API excludes deferred tools from the system-prompt prefix"; discovered defs appended as `tool_reference`; counted as input tokens "like any other tool definition" once loaded; cache preserved | - | >=1 non-deferred tool; prefix untouched | harness | platform tool-search-tool.md VERIFIED. Implication (ASSUMPTION): the `/context` "System tools (deferred) 12.4k / MCP (deferred) 5.9k" rows are not billed until discovered |
| Hook `additionalContext` / stdout (SessionStart, UserPromptSubmit, PostToolUse, SubagentStart) | Wrapped in `<system-reminder>`; SessionStart before first prompt; **SubagentStart can inject into a subagent** | - | **10,000 chars per string, not raisable**; over -> written to a file, model gets path + first 2,000 chars; multiple hooks all delivered | **plugin hooks** | hooks.md VERIFIED |
| Output styles | Replace the coding section of the full system prompt unless `keep-coding-instructions`; do not apply to non-fork subagents | none | newer models already use the shorter prompt | plugin (`output-styles/`), user | output-styles.md VERIFIED |
| `--bare` / `CLAUDE_CODE_SIMPLE=1` | Minimal prompt; no hooks, skills, commands, subagents, plugins, MCP, auto memory, CLAUDE.md; Bash/Read/Edit only | off | needs API key | CLI/env | cli-reference.md, env-vars.md VERIFIED |
| `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` | Short system prompt with abbreviated tool descriptions; **already default on Sonnet 5.5 / Opus 5.5 class models** | model-dependent | - | env | env-vars.md VERIFIED (matches the 2.1k system-prompt row) |
| `includeGitInstructions:false` / `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` | Drops built-in commit/PR instructions (Bash tool text) **and** the git-status snapshot, subagents included except Explore/Plan | true | one switch for both | user/project/local | settings-reference.md, sub-agents.md VERIFIED |
| Auto-compact window | `/autocompact`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (100K-1M), `autoCompactWindow` setting; **per-subagent `autoCompactWindow` frontmatter (2.1.296)**; native-1M models compact at ~967K | window - buffer | min 100K | user/env; agent frontmatter | env-vars.md, model-config.md, changelog VERIFIED; plugin-agent support of the new field SINGLE-SOURCE |

## Subagent-inheritance table

| Component | Non-fork subagent | `omitClaudeMd: true` | Fork (`/subtask`, interactive default >=2.1.232) | Source / tag |
|---|---|---|---|---|
| System prompt | Agent's own body + env details; **not** the Claude Code system prompt | same | identical to main (reuses parent cache) | sub-agents.md VERIFIED |
| User/project/local CLAUDE.md, `@imports` | **Inherited in full** | dropped (managed still loads) | inherited | sub-agents.md VERIFIED; PROBED |
| Unscoped rules (`~/.claude/rules`, `.claude/rules`) | **Inherited** (rides in the CLAUDE.md block) | dropped (PROBED: coordination-protocol text absent) | inherited | PROBED; docs say "project rules" |
| Auto-memory MEMORY.md | Docs: not loaded. **PROBED: loaded** (verbatim entry quoted; ~8K in the 32.4K total) | dropped | inherited | Divergence, see map |
| Git status snapshot | Inherited (Explore/Plan skip); only `includeGitInstructions:false` removes it | still present (PROBED) | inherited | sub-agents.md VERIFIED; PROBED |
| Skills listing | Not seen by a `tools:[Read]` agent (PROBED). Docs list no listing; #100813 says subagents "do receive it" (probably those with the `Skill` tool) | n/a | inherited | PROBED + #100813; **open for agents that include `Skill`** |
| Agent-type listing | Not seen by a `tools:[Read]` agent (PROBED); sibling roster only with `SendMessage` | same | inherited | PROBED; sub-agents.md VERIFIED |
| `skills:` frontmatter | **Full bodies injected at start**, first 32 distinct names (2.1.295: each once); cannot name a `disable-model-invocation` skill; does *not* restrict `Skill` tool access | unchanged by `omitClaudeMd` (ASSUMPTION) | n/a | sub-agents.md, changelog 2.1.295 VERIFIED |
| MCP + built-in tools | All, narrowed by `tools`/`disallowedTools`; background agents get a reduced built-in set + all MCP | same | same as main | sub-agents.md VERIFIED |
| Hooks | Settings, managed and **plugin hooks all apply inside subagents**; `SubagentStart` can add context | same | same | sub-agents.md, hooks.md VERIFIED |
| Output style | Not applied | - | applied | sub-agents.md VERIFIED |
| `memory:` field | Adds that agent's own `MEMORY.md` (first 200 lines/25 KB) + read/write instructions | - | - | sub-agents.md VERIFIED |
| Plugin agents | Support `omitClaudeMd`, `skills`, `memory`, `tools`, `disallowedTools`, `model`, `effort`, `maxTurns`, `background`, `isolation`, `experimental.cacheTtl`; **ignore `hooks`, `mcpServers`, `permissionMode`, `initialPrompt`** | supported | - | plugins/components.md VERIFIED |
| Prompt-cache TTL | Separate cache; **5-minute TTL** even on subscription ("everything else" bucket); override `subagentPromptCacheTtl`, `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`, agent `experimental.cacheTtl: 1h` (>=2.1.248) | same | shares parent's | prompt-caching.md VERIFIED |

**Measured subagent first-request sizes (PROBED, Sonnet 5.5, Praxion repo, `tools:[Read]`)**: no-omit **32,404 / 32,422** tokens (probe 1 and probe 2); omit **2,804 / 2,822** tokens. Main headless first request same run: **66,945** (55,843 create + 11,102 read), consistent with the brief's 67,988. A third-agent-type sharing 1,743 tokens of prefix with the first (cache_read) shows identical system-prompt+tool prefixes hit the same cache across agents and sessions.

**Is there a smaller inherited baseline?** Yes, three native knobs: (a) `omitClaudeMd` (cuts ~29.6K here), (b) `tools`/`disallowedTools` without `Skill`/MCP (avoids listing and deferred-tool surface), (c) built-in Explore/Plan already skip CLAUDE.md and git status. Not available: keep-rules-drop-memory, per-file CLAUDE.md selection for subagents, dropping git status for non-Explore agents, a subagent-specific rules set. A `SubagentStart` plugin hook can *add* role-specific context (<=10K chars), which pairs with `omitClaudeMd` to replace "everything" with "role-relevant slice" (design option; mechanism VERIFIED, combination not tested).

## Caching note (prices VERIFIED from platform pricing page today)

Per-MTok: **Sonnet 5.5** in $2 / 5m-write $2.50 / 1h-write $4 / read $0.10. **Opus 5.5** $4 / $5 / $8 / $0.20. **Haiku 5.5** $0.10 / $0.125 / $0.20 / $0.01 (prompts <=100K; above 100K $0.50 / $0.625 / $1 / $0.05). **Fable 5.1** $10 / $12.50 / $20 / $0.25. All 4.6+ models except Haiku 5.5 include the full 1M window at standard pricing (no long-context premium).

Mechanics (prompt-caching.md VERIFIED): prefix match is exact; order is system prompt + tool defs -> project context (CLAUDE.md, memory, unscoped rules) -> conversation. Editing CLAUDE.md mid-session does not apply and does not invalidate; skills, plugin enable/disable (non-MCP), output-style change, permission mode, spawning a subagent keep the cache. Invalidators: model switch, effort change (not on Sonnet 5.5/Opus 5.5/Haiku 5.5/Fable 5.1), fast mode, MCP set change without tool search, bare tool deny rule without tool search, `/compact` (conversation layer; reloads project context from disk), Claude Code upgrade. Main-conversation TTL: 1h on subscription within plan usage, 5m on API key/credits/cloud (`promptCacheTtl` / `CLAUDE_CODE_PROMPT_CACHE_TTL`). Cache is effectively per machine+directory (system prompt embeds memory paths; working dir announced), parallel sessions in the same directory share it.

Arithmetic for the static prefix (S = 60K and 90K tokens, the brief's 68K-86K measured range sits between):

| | S = 60K Sonnet 5.5 | S = 90K Sonnet 5.5 | S = 60K Opus 5.5 | S = 90K Opus 5.5 |
|---|---|---|---|---|
| First turn, 5m write | 60,000 x $2.50/M = **$0.150** | **$0.225** | x $5/M = **$0.300** | **$0.450** |
| First turn, 1h write | x $4/M = $0.240 | $0.360 | x $8/M = $0.480 | $0.720 |
| Each later warm turn (read) | x $0.10/M = **$0.0060** | **$0.0090** | x $0.20/M = **$0.0120** | **$0.0180** |
| Cold turn (TTL expired / uncached) | x $2/M = $0.120 | $0.180 | x $4/M = $0.240 | $0.360 |
| 100-turn session, always warm | 0.150 + 99 x 0.006 = **$0.74** | 0.225 + 99 x 0.009 = **$1.12** | **$1.49** | **$2.23** |

Reading: the *entire* resident prefix costs about $0.7-$2.2 per 100-turn session; removing 30K of it saves roughly $0.37-$0.75 per such session (Sonnet/Opus). Output tokens ($10/$20 per MTok) and tool results dominate. A cold first turn is also latency (uncached prefill), which is the user-visible cost.

Per subagent spawn: each spawn pays a fresh write of its own prefix (5m TTL, separate from parent). Measured 32.4K: Sonnet **$0.081** (write) + $0.0032 per later turn; Opus **$0.162** + $0.0065/turn. With `omitClaudeMd` (2.8K): Sonnet **$0.007**, Opus **$0.014** -> saves **$0.074 (Sonnet) / $0.148 (Opus) per spawn when the cache is cold**. At the Standard cap of 16 spawns that is $1.2-$2.4, at the Full cap of 32 it is $2.4-$4.7 per pipeline, *if* each spawn is cache-cold. Same-agent-type spawns within 5 minutes read the identical prefix (reads at 10%/5%), so real savings are lower; the 240,647 preload tokens in the prior spike add `skills:` bodies on top (not measured here). These are list-price estimates; subscription users see usage-limit effects, not dollars.

**Cost vs quality**: cache arithmetic says 60-90K resident tokens is cheap in dollars (~7-9% of a 1M window; ~30-45% of a 200K window). The documented harms are non-monetary: adherence ("files over 200 lines ... may reduce adherence", memory.md), attention budget / context rot (Anthropic engineering post, Sep 29 2025: "smallest possible set of high-signal tokens"; "n^2 pairwise relationships"), and cold-turn latency. Note Anthropic's best-practices rule of thumb is *per CLAUDE.md file* (~200 lines), while Praxion's always-on rules measured 13.4k tokens (brief) against a combined CLAUDE.md+rules+memory block of ~29K; `rules/swe/*.md` totals ~90 KB on disk, of which only the unscoped subset is resident.

## Platform features for long sessions (VERIFIED, platform docs)
- **Context editing** (beta header `context-management-2025-06-27`): `clear_tool_uses_20250919` (default trigger 100,000 input tokens, keep 3 tool uses, optional `clear_at_least`, `exclude_tools`) and `clear_thinking_20251015`. Server-side; clearing invalidates the cached prefix, hence `clear_at_least`. API-level; Claude Code does not expose it to plugins (no setting found).
- **Memory tool** (`memory_20250818`) pairs with context editing: Claude is warned before clearing and can save to files. Claude Code's equivalent is auto-memory + CLAUDE.md.
- **Compaction**: server-side `compact_20260112` is "the primary strategy" per the docs; in Claude Code, `/compact` and auto-compact re-inject CLAUDE.md, unscoped rules, MEMORY.md, up to 5 recent files, and invoked-skill bodies (5,000 tokens each, 25,000 total, oldest dropped first); path-scoped rules and nested CLAUDE.md reload on demand; **the skill listing is not re-injected**; SessionStart hooks matching source `compact` re-run (context-window.md VERIFIED). Implication: anything that must survive compaction should be unscoped (or a `compact`-source SessionStart injection).
- **1M window**: Fable, Sonnet 5+, Haiku 5.5, Opus 4.6+ (and Sonnet 4.6) support 1M; included at standard price except Haiku 5.5 (tiered at 100K). Native-1M models auto-compact at ~967K; `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` holds to 200K. Skills-listing budget scales with the window (1% = ~10K at 1M, ~2K at 200K), so the listing "diet" is window-dependent.

## Anthropic published guidance (VERIFIED)
- Best-practices: "Keep it concise. For each line, ask: 'Would removing this cause Claude to make mistakes?' If not, cut it"; exclude "anything Claude can figure out by reading code", "file-by-file descriptions", "long explanations or tutorials"; use skills for domain knowledge "only relevant sometimes"; hooks for must-always rules (CLAUDE.md is advisory). Costs page: "Move instructions from CLAUDE.md to skills ... Aim to keep CLAUDE.md under 200 lines"; `/doctor` proposes trims; `/doctor prompt-audit` (2.1.283) flags instructions written for older models and conflicts.
- Memory docs: "Imports ... don't reduce its context cost"; path-scoped rules are the sanctioned conditional channel; CLAUDE.md is delivered as a user message, "no guarantee of strict compliance".
- Engineering blog "Effective context engineering for AI agents" (2025-09-29): attention budget, context rot, smallest set of high-signal tokens, hybrid of upfront CLAUDE.md + just-in-time retrieval (glob/grep), compaction, note-taking, sub-agents returning 1,000-2,000-token summaries. (Vendor guidance; tier 1 for what Anthropic recommends, not independent evidence of effect size.)
- Tool-search API doc: 55K tokens of definitions for a five-server setup, "typically reduces this by over 85 percent"; selection accuracy degrades past 30-50 tools (vendor claim, SINGLE-SOURCE).

## Levers Praxion lacks (a plugin cannot close these)
| Gap | Detail | Upstream |
|---|---|---|
| Ship rules from a plugin | No rules component; rules must be user-scope files or hook-injected (<=10K chars/string) | none found; not requested here |
| Plugin-set skill visibility | `skillOverrides` ignores plugin skills; plugin `settings.json` honors only `agent`, `subagentStatusLine`; no `skillListingBudgetFraction` from a plugin; no per-component toggle | none found |
| "Hidden but model-loadable" skill / native skill search | Only binary `disable-model-invocation`; no search tool | #20143, #43816, #67448, #84666 closed NOT_PLANNED; #75376 answered with `disable-model-invocation` (closed COMPLETED); #36023, #33825 closed DUPLICATE |
| Lazy user-scope CLAUDE.md / unscoped rules | Only nested CLAUDE.md, `paths:` rules, nested skills are lazy; user-scope file always eager; `@import` eager | none found |
| Finer subagent baseline | `omitClaudeMd` is all-or-nothing; git status unremovable per agent; no subagent-specific rules set | none found (omitClaudeMd shipped 2.1.271) |
| Skill-listing reliability | Listing can reach the model late or never in interactive sessions (2.1.295) | #100813 OPEN (2026-10-10); related #87281, #74990 (post-compaction drop) |
| `paths:` effect on skill listing | Undocumented whether it withholds the listing entry | docs gap |
| Project-level control of a user's global setup | `managed-only` instruction mode is user/managed-only (ignored from project settings) | by design |

Levers a **project** could pull via `onboard-project`-written `.claude/settings*.json`: `skillListingBudgetFraction`, `skillListingMaxDescChars`, `skillOverrides` (non-plugin skills only), `claudeMdExcludes`, `includeGitInstructions`, `autoMemoryEnabled`, `permissions.deny: ["Agent(name)"]`, `enabledPlugins` (whole plugin), env block (`ENABLE_TOOL_SEARCH`, `CLAUDE_CODE_*`). Levers **only the user/installer** can pull: `~/.claude/rules` placement, user CLAUDE.md, the `managed-only` instruction mode, user-scope `skillOverrides`.

## Divergence Map
| Claim | Source A (tier) | Source B (tier) | Handling |
|---|---|---|---|
| Subagent gets main auto-memory | memory.md & sub-agents.md: "isn't loaded" (1, official docs) | PROBED 2.1.296: verbatim MEMORY.md entry quoted by `probe-full2`, token total matches (n=2 runs, `--agents`-defined agent, -p mode) | Treat behaviour as authoritative for sizing; re-probe with a plugin-installed agent in an interactive session before relying. [certainty: med - reproducible twice but one invocation path] |
| MCP instruction/tool-description cap | mcp.md & env-vars.md: 2,048 (1) | changelog 2.1.296: default raised to 4,096; 2.1.295: 16,384 for search-loaded descriptions (1) | Docs lag the changelog; use 4,096. [certainty: high - changelog dated 2026-10-08/09] |
| Path-scoped rules load only on Read | Praxion `rules/CLAUDE.md` (internal) | memory.md + changelog 2.1.288/293 (1) | Internal note is stale. [certainty: high] |
| Subagent receives skills/agent listing | brief: "plus its own listing" | PROBED: absent for `tools:[Read]` agents; #100813: subagents receive it (tier 4 bug report) | Likely depends on the `Skill` tool; Praxion agents mostly omit `Skill` (only `discipline-consultant` lists it), so the listing is probably not paid per spawn. [certainty: low - untested with `Skill`] |
| Sonnet 5.5 cache-read price | changelog 2.1.284: $0.20 | pricing page + changelog 2.1.296: $0.10 | Use $0.10. [certainty: high] |

## Changed since 2026-09-23 (changelog 2.1.281 -> 2.1.296; VERIFIED)
- 2.1.281: large-CLAUDE.md startup notice now counts files together; `--add-dir` CLAUDE.md/rules no longer double-sent in headless/SDK.
- 2.1.283: `/doctor prompt-audit`.
- 2.1.284: Sonnet 5.5 default (1M, $2/$10); MEMORY.md sanitization.
- 2.1.286: subagents with worktree isolation no longer load project CLAUDE.md twice.
- 2.1.287: MCP `alwaysLoad:false` defers all server tools; folder CLAUDE.md no longer attached twice after resume/compact; Opus 4.7+/Fable 1M default on Bedrock/Vertex/Foundry.
- **2.1.288: path-scoped rules and nested CLAUDE.md load on Write/Edit too; InstructionsLoaded carries `agent_id`/`agent_type`.**
- 2.1.290-293: Read `allow_large` option (2.1.296); path rules/nested CLAUDE.md load on single-file Bash reads (2.1.293); skill listing shows both names when folder != name; mods `isDeferred`.
- 2.1.295: **subagents preload at most 32 skills, each once**; search-loaded MCP descriptions cut at 16,384; async SessionStart hook context no longer re-added on every resume.
- **2.1.296: MCP descriptions/instructions default 2,048 -> 4,096; subagent frontmatter `autoCompactWindow`; Sonnet 5.5 cache reads priced $0.10.**
- Earlier relevant (Aug 1 - Sep 22): 2.1.252/261 `/skill-doctor`; 2.1.265 fixed SubagentStart context and preloaded skills leaving the prefix on later turns (cache); 2.1.267-268 mid-session MCP/plugin tools arrive as deferred definitions (cache-stable); **2.1.271 `omitClaudeMd`** (custom + plugin agents); 2.1.277 AGENTS.md read directly; 2.1.280 `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH`; 2.1.247 Sonnet 5 compacts at ~967K; 2.1.222 clearer refusal for `disable-model-invocation` skills.

## Open Questions / unverified
1. Does skill `paths:` withhold the listing entry until a match? (docs silent; testable with `/context` before/after.)
2. Does a subagent *with* the `Skill` tool receive the skills listing (#100813 says yes)? Not probed.
3. Does `omitClaudeMd` strip user-scope rules in an interactive session with a plugin-installed agent, and do `SubagentStart` plugin hooks still fire and inject? (Probe 2: omit agent listed only gitStatus; probe 1: omit agent mentioned a "process active" message; inconsistent self-reports, not token-verified.)
4. Whether `claudeMdExcludes` in project settings can drop `~/.claude/rules/*` files (docs example shows ancestor/rules-dir excludes only).
5. Do the `/context` "deferred" rows (12.4K + 5.9K) correspond to billed tokens? API doc says deferred defs are outside the prefix; Claude Code's `/context` estimate was not cross-checked against `usage`.
6. `autoCompactWindow` in plugin-agent frontmatter: field list in plugins/components.md predates 2.1.296.
7. Server-side compaction (`compact_20260112`) details and thresholds not fetched (not a plugin lever).
8. Effect sizes for quality (adherence vs resident size) are not established by these sources; they are vendor guidance, not measurements. Other lenses cover empirical evidence.

## Sources (all fetched 2026-10-11)
- [Memory](https://code.claude.com/docs/en/memory.md): load order, lazy subdirs, imports, rules, MEMORY.md caps, AGENTS.md, claudeMdExcludes.
- [Skills](https://code.claude.com/docs/en/skills.md): listing budget, 1,536-char cap, skillOverrides, disable-model-invocation, compaction re-attach.
- [Subagents](https://code.claude.com/docs/en/sub-agents.md): inheritance, frontmatter, omitClaudeMd, preload, fork.
- [Plugin components](https://code.claude.com/docs/en/plugins/components.md) and [manifest reference](https://code.claude.com/docs/en/plugins/manifest-reference.md): layout, plugin agent fields, plugin settings keys.
- [Settings reference](https://code.claude.com/docs/en/settings-reference.md), [env vars](https://code.claude.com/docs/en/env-vars.md), [CLI reference](https://code.claude.com/docs/en/cli-reference.md): budget, git, bare, MCP length.
- [MCP](https://code.claude.com/docs/en/mcp.md): tool search, instructions cap. [Hooks](https://code.claude.com/docs/en/hooks.md): additionalContext 10,000-char cap, SubagentStart.
- [Prompt caching](https://code.claude.com/docs/en/prompt-caching.md), [context window](https://code.claude.com/docs/en/context-window.md), [costs](https://code.claude.com/docs/en/costs.md), [best practices](https://code.claude.com/docs/en/best-practices.md), [model config](https://code.claude.com/docs/en/model-config.md), [output styles](https://code.claude.com/docs/en/output-styles.md), [changelog](https://code.claude.com/docs/en/changelog.md).
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing.md), [tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool.md), [context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing.md).
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (2025-09-29).
- GitHub: [#75376](https://github.com/anthropics/claude-code/issues/75376), [#20143](https://github.com/anthropics/claude-code/issues/20143), [#84666](https://github.com/anthropics/claude-code/issues/84666), [#43816](https://github.com/anthropics/claude-code/issues/43816), [#67448](https://github.com/anthropics/claude-code/issues/67448), [#100813](https://github.com/anthropics/claude-code/issues/100813).
- Probe artifacts (scratch, not committed): `/private/tmp/claude-501/-Users-fperez-dev-praxion/b4da2e82-a25e-45c1-8855-0425f72ad3ed/scratchpad/probe/` (`probe_out.json`, `probe2_out.json`; sessions `1e3f8839-...`, `61978829-...` under `~/.claude/projects/-Users-fperez-dev-praxion/`).
- Fetched pages contained no agent-directed instructions.
