# Startup-payload ablations (orchestrator, 2026-10-11, Claude Code on Opus 5.5, 1M window)

Method: real first-request input tokens (`input + cache_creation + cache_read` from `claude -p
"Reply with the single word ok." --output-format json`), one variable changed per run, plus
headless `/context` for category weights. Script: scratchpad `ablate/run.sh`. Headless runs have
claude.ai connectors disabled (an API key takes precedence), so they read lower than interactive.

| Config | Real tokens | Δ vs baseline | Reads as |
|---|---|---|---|
| Interactive session, Praxion repo (this session's first request) | 85,759 | +17,771 | claude.ai connectors (Gmail, Calendar, Zapier, Claude Docs + its long server instructions), Chrome, interactive-mode extras, the user message |
| **Headless baseline, Praxion repo** | **67,988** | — | |
| Empty directory (same user settings, plugins, hooks) | 54,577 | −13,411 | Praxion-repo-specific: auto-memory MEMORY.md + project CLAUDE.md + repo-specific hook output |
| Auto-memory off (`autoMemoryEnabled:false`) | 59,270 | −8,718 | MEMORY.md index alone |
| Skills off (`--disable-slash-commands`) | 62,709 | −5,279 | skill listing (capped; /context shows ~10k estimate) |
| Praxion plugin disabled (global rules + user CLAUDE.md still load) | 53,913 | −14,075 | Praxion plugin: agent listing, its listing share, hook injections, its MCP servers |
| Other plugins disabled (Praxion only) | 66,292 | −1,696 | other plugins; small because the listing is capped and Praxion refills the budget |
| No MCP servers (`--strict-mcp-config`) | 65,239 | −2,749 | MCP names + server instructions (deferred schemas mostly not billed) |
| Harness floor (empty dir, `--setting-sources ""`) | 15,812 | −52,176 | system prompt + built-in tools, no user memory, no plugins |
| `--bare` | 1,610 | — | not a usable floor (strips tools and system prompt) |

Even with only Praxion enabled, 17 of 89 Praxion listing entries render name-only (`/context`
"< 20" tokens); with all plugins, 38 of 89 on a 1M-window model and 72 of 89 on a
200K-window model (Haiku 4.5: listing budget 2.2k, resident context 46.5k = 23% of the window
before any work). The listing is budget-capped, so trimming it buys
*visibility*, not tokens.

## Attribution of the 67,988-token headless baseline (Praxion repo)

| Block | Tokens (real, or `/context` estimate where marked) | Controlled by |
|---|---|---|
| Harness floor (system prompt + tools) | ~15.8k | Anthropic |
| User CLAUDE.md (generated from Praxion's template) | ~3.9k est | Praxion (installer) |
| Always-on global rules (symlinked into `~/.claude/rules/`) | ~13.4k est | Praxion (installer) |
| Project CLAUDE.md (Praxion repo) | ~3.9k est | project |
| Auto-memory MEMORY.md (Praxion repo) | 8.7k | harness + assistant-written content |
| Praxion plugin (agents ~4.6k, listing share, SessionStart injections ~4.4k, MCP) | 14.1k | Praxion (plugin) |
| Other plugins | 1.7k | user |
| MCP servers (names + instructions) | 2.7k | user/plugins |
| Interactive-only extras (connectors etc.) | +17.8k | user (claude.ai) |

Praxion-attributable at startup (installer + plugin + project CLAUDE.md): **~35k of 68k headless**,
**~44k with MEMORY.md**. Harness floor ~16k. User-side connectors ~18k (interactive only).

## Per-spawn startup (first request of this spike's subagents)

| Agent | Model | First-request tokens |
|---|---|---|
| researcher (×3) | sonnet / opus | 49,948 – 50,001 |
| context-engineer | sonnet | 63,469 |

Every spawn re-pays ~50-63k before its first action; this spike's four spawns paid ~213k of
startup between them.

## Listing use vs listing cost (observation WAL, 2026-09-25 → 2026-10-11)

- 18,240 WAL rows, 67 main sessions. **9 `Skill` activations in total, all by the main agent,
  7 distinct skills** (agent-crafting ×3, goal-disambiguation ×2, command-crafting,
  hook-crafting, web-ui-design, artifact-design). No subagent ever called `Skill` — subagents
  get guidance by frontmatter preload.
- So ~89 Praxion listing entries are re-paid in every session and spawn, while about one
  activation lands every seven sessions. Caveat: guidance also arrives by preload and by
  `Read` of a SKILL.md, which this count does not see.

## Probes resolving harness-lens open questions (orchestrator, Claude Code 2.1.296)

- **Deferred tools are not billed.** `ENABLE_TOOL_SEARCH=false` raises the real first request
  from 67,988 to **109,842** (+41,854). The harness's tool deferral already saves ~42k; the
  `/context` "(deferred)" rows are informational. (`/context` also under-reports the eager core
  tools as "24" tokens; the ~16k harness floor is system prompt + core tools.)
- **Skill `paths:` does not withhold the listing entry.** A throwaway plugin with one
  `paths: ["**/*.zzqq"]` skill and one plain skill, in an empty directory with no matching file:
  the model listed both, descriptions verbatim (n=2, Sonnet 5.5). `paths:` gates auto-loading,
  not visibility — it is not a conditional-listing lever.
- **A subagent sees the skill listing only if it has the `Skill` tool.** `--agents` probe: the
  agent with `tools: [Read, Skill]` listed both probe skills; the one with `tools: [Read]` said
  NONE. Among Praxion agents only `discipline-consultant` declares `Skill`, so the other 16 do not
  pay the listing per spawn.
- **`omitClaudeMd` + a plugin `SubagentStart` hook compose.** Throwaway plugin with two agents
  (`tools: Read`, one with `omitClaudeMd: true`) and a `SubagentStart` hook injecting a marker,
  spawned from the Praxion repo with normal settings (Praxion's own hooks also active). Omit
  agent: **2,385** first-request tokens, saw the hook marker, did **not** see the Agent
  Behavioral Contract section or the MEMORY.md index. Full agent: **31,985** tokens, saw all
  three. So "drop everything inherited, re-inject a role-specific kernel by hook" is mechanically
  available to a plugin today (hook strings are capped at 10,000 chars each; several hooks may
  inject).
