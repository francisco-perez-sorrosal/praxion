# Research Findings: Praxion's Component-Selection Surface (internal ground truth)

## Research Goal

Establish, with measured numbers, exactly what Praxion puts in context today for skill/command/agent
*selection*, what it costs, where the current mechanisms (native listing, `disable-model-invocation`,
`skillOverrides`) succeed or fail, and where a code-mode / tool-search / routed-selection mechanism could
plug in — as ground truth for an external researcher covering Cloudflare "code mode" and Anthropic tool
search.

## Research Questions

1. How large is the selection surface (skill/command/agent descriptions + MCP tools), measured, with a
   distribution?
2. How does that surface reach context — session start, subagent inheritance, truncation, `disable-model-invocation`?
3. What has Praxion already decided or tried here (ADRs, the process-economy roadmap, tech-debt ledger)?
4. What MCP servers and structured indices already exist that a search mechanism could build on?
5. What evidence exists of selection failure (wrong/missed skill activation, listing truncation)?
6. Where could a "search + load" or routed-selection mechanism actually insert, given harness constraints
   and Praxion's Codex/Cursor export surfaces?

## Codebase Findings

### 1. Inventory and measured sizes

**Method.** `scripts/measure_token_budget.py` (stdlib-only, real-tokenizer when `ANTHROPIC_API_KEY` is set)
defines the selection surface mechanically: `listing_files()` globs `skills/*/SKILL.md`, `commands/*.md`,
`agents/*.md` (`_LISTING_GLOBS`, `measure_token_budget.py:400`); `measure_listing()`
(`measure_token_budget.py:452-483`) extracts only the `description:` frontmatter scalar/block from each
file, drops any file whose frontmatter contains `disable-model-invocation: true`, and joins the survivors
with `\n`. I ran this script directly and additionally reproduced its per-file logic in a small script
(`importlib` on `measure_token_budget.py`) to break the aggregate into a top-20 and a distribution — the
per-file breakdown is not a first-class output of the shipped script.

**Live measurement (2026-09-23, this worktree):**

```
$ python3 scripts/measure_token_budget.py
16,606 / 25,000 tokens (66.4%) — under budget
  basis: tokenizer over 9 files, 65,014 bytes
  listing: 9,243 tokens (tokenizer) over 128 files, 39,892 bytes
```

- **128 files glob-matched**: 63 `skills/*/SKILL.md` + 46 `commands/*.md` + 19 `agents/*.md`.
- **124 have parseable frontmatter description**; 4 do not (`agents/CLAUDE.md`, `agents/README.md`, and 2
  files under `commands/` with no `---` fence or empty description) — these are directory-catalog/config
  files the glob incidentally sweeps up, not selection-surface items.
- **35 of the 124 are excluded** by `disable-model-invocation: true` (found: 33 commands, 2 skills —
  `lens-fanout`, `onboard-project`; 0 agents).
- **89 active** (counted in the 9,243-token figure): 61 skills, 11 commands, 17 agents.

| Kind | Active count | Sum (bytes) | Mean (bytes) |
|---|---|---|---|
| skill | 61 | 26,842 | 440.0 |
| command | 11 | 1,012 | 92.0 |
| agent | 17 | 11,950 | 702.9 |

Active-description distribution (n=89, bytes): **min 26, max 1,948, mean 447.2, median 419**.

**Top 20 by description size** (active only; `[bytes] [kind] [path] — [first 80 chars]`):

```
1948  agent    agents/roadmap-cartographer.md
1749  agent    agents/agentic-transactions-architect.md
1307  agent    agents/interface-designer.md
1098  agent    agents/sentinel.md
 757  agent    agents/discipline-consultant.md
 664  agent    agents/architect-validator.md
 621  skill    skills/software-design-principles/SKILL.md
 618  skill    skills/data-structure-design/SKILL.md
 605  skill    skills/python-development/SKILL.md
 587  skill    skills/deployment/SKILL.md
 562  skill    skills/multi-perspective-analysis/SKILL.md
 560  skill    skills/roadmap-synthesis/SKILL.md
 560  agent    agents/context-engineer.md
 559  skill    skills/evidence-appraisal/SKILL.md
 551  skill    skills/observability/SKILL.md
 546  skill    skills/experiment-tracking/SKILL.md
 545  skill    skills/performance-architecture/SKILL.md
 541  skill    skills/web-ui-design/SKILL.md
 541  skill    skills/neo-cloud-abstraction/SKILL.md
```

(`skills/lens-fanout/SKILL.md`, 723 bytes, ranks in the top-6 by raw size but is excluded from the active
listing by `disable-model-invocation: true`.)

**Reading**: agents are the most expensive per-item (mean 702.9 B vs. skills' 440.0 B), and the five
largest single entries in the whole surface are all agents — `roadmap-cartographer` alone is ~2 KB, more
than 4× the median skill. Commands are cheap on average (92 B) only because 33 of 44 are already hidden via
`disable-model-invocation`; the 11 that remain visible average about the same as a terse skill line.

**A methodology gotcha worth flagging**: naive `grep -l "disable-model-invocation: true"` over-counts. It
matched `skills/command-crafting/SKILL.md`, but that file's frontmatter does *not* set the flag — the
string appears in prose (a documentation table explaining the flag, `command-crafting/SKILL.md:89`). Only
`measure_token_budget.py`'s frontmatter-fence-scoped regex (`_DISABLE_MODEL_INVOCATION_RE` applied to
`_frontmatter_block()`'s output, not the whole file) gives the correct count (2 skills, not 3). Any future
selection-surface tooling should reuse this parsing, not re-derive it by grep.

### 2. How the surface reaches context

**Session-start listing.** This is native Claude Code behavior, not a Praxion hook: the harness scans
`skills/*/SKILL.md`, `commands/*.md`, `agents/*.md` frontmatter at session start (and the `agents/*.md`
descriptions double as the enum the `Agent` tool's `subagent_type` parameter validates against). Praxion has
**no interception point** for this scan today — contrast with rules, where `dec-167` (`.ai-state/decisions/167-hook-delivered-blacklist-mechanism.md`)
built a **hook-delivered Channel 2** (`hooks/inject_rules.py`, `SessionStart`, reads
`.claude/praxion-rules.yaml`) specifically because native Claude Code has no per-project rule-filtering
mechanism and the team wanted *physical* (not merely behavioral) token exclusion. No equivalent channel
exists for skills/commands/agents; the only two levers that physically remove an entry from the listing
are file-level (delete/rename/merge the file) or frontmatter-level (`disable-model-invocation: true`).

**Subagent inheritance.** Per `docs/context-economy.md` and the process-economy roadmap
(`docs/independent-analysis/process-economy-roadmap.md:111-113`, VERIFIED from a live spawn's `claudeMd`
system block): every subagent spawn inherits the symlinked always-loaded rule corpus
(`~/.claude/CLAUDE.md`, `rules/CLAUDE.md`, `CLAUDE.md`, and the 4 native-symlinked always-loaded rules) —
measured at **21,287 tokens** — but *not* the two `install: hook-deliver` (Channel 2) rules, which is a
documented gap (`W10` in the roadmap: "Hook-delivered rules never reach subagents"). Separately, and
additively, **each subagent also re-renders its own copy of the skill/command/agent listing** at spawn,
because each subagent is itself a fresh Claude Code context. The roadmap's mean-resident-context-per-spawn
figure makes the composition explicit: `47,054 tokens = inherited (21,287) + listing + agent-definition body
+ preloaded skills:` bodies (systems-architect 81,166; implementer 76,047; verifier 75,232; sentinel
74,449). **The listing is paid once per spawn, not once per pipeline** — a Standard pipeline's 5+ spawns pay
it 5+ times (the roadmap's headline: "every always-loaded token is paid ~7× per Standard pipeline" folds the
listing into that multiplier, alongside the rules corpus).

**Listing truncation.** Per Claude Code's own docs (`skills.md § "Skill descriptions are cut short"`, cited
in the roadmap, fetched 2026-09-06 — I did not re-fetch it myself this pass, so treat the *mechanism*
description as SINGLE-SOURCE from that prior citation): Claude Code caps *combined skill descriptions* at
roughly 1% of the context window in characters and drops entries — least-used first — beyond that cap;
whether a name-only (post-truncation) skill can still auto-activate is undocumented. At the time of the
roadmap's original measurement (skills alone: 35,886 characters across 62 skills, pre-diet), **~40 of 62
Praxion skills were rendered as bare names, invisible to description-based activation, in the very session
that produced the finding**. The 1% target the roadmap set for a truncation-free listing is **~2,000
tokens** (`measure_token_budget.py --listing-ceiling`, default 2,000, "~1% of a 200k-token context window,"
`measure_token_budget.py:76-78`). **Today's measured listing is 9,243 tokens — 4.6× that target.** The
description diet (`P1.12`, executed 2026-09-08, see below) cut the raw skill-description text meaningfully,
but the *combined* listing (skills + commands + agents, all three counted together in the one 9,243-token
figure) still sits well above the 1% band Claude Code is documented to start dropping entries at. I could
not directly re-observe *which* skills are currently name-only in a live 200k-token session (that requires
sampling an actual running session's rendered listing, out of scope for a Bash-only research pass) — this
is an **open question**, not a re-confirmed number: the risk is live and structurally likely (size exceeds
the documented threshold), but the exact current drop-count needs a fresh live sample, ideally via the
native `/skill-doctor` command (see below).

**`skillOverrides` (settings.json) is confirmed inert.** `td-197` (`.ai-state/TECH_DEBT_RESOLVED.md:27`,
resolved 2026-09-11) records that `measure_token_budget.py` previously credited a `skillOverrides:
name-only` block in `settings.json` as reducing 12 skills to name-only in the listing (reporting 7,936
tokens); this was shown **inert on two independent instruments** — the harness does not actually honor it —
and removing the credit moved the honest reading to 9,243 tokens with *zero change to what the harness
renders*. The lesson recorded in the resolution: "an instrument that reads the same configuration as the
thing it measures cannot independently confirm the configuration took effect." **Any new selection mechanism
must be validated against the actual rendered listing (or a live session sample), never against a
configuration file's stated intent.**

**`disable-model-invocation` — works for commands, was tried and rejected for skills.** For *commands*, this
flag is a clean, verified, zero-side-effect lever: 33 of 44 commands already use it (side-effecting or
user-only commands — commits, releases, deploys — per `command-crafting/SKILL.md:161`), and a command's only
consumer is a human typing `/name`, so removing its description from model context costs nothing. For
*skills*, the P1.12 slice (`.ai-state/calibration_log.md:110`, 2026-09-08) explicitly **ruled out**
`disable-model-invocation` as a listing-reduction lever: "it also blocks subagent preload + Skill calls."
Unlike a command, a skill has two other consumers besides model-initiated auto-activation — an agent's
frontmatter `skills:` preload list, and an explicit `Skill` tool call — and the flag disables the skill
system-wide, not just from the initial listing. **This is the sharpest mechanical constraint for any
search-then-load design**: Claude Code today has no primitive that means "invisible to the always-loaded
listing scan, but still preloadable/invocable on demand" — that's exactly the gap a code-mode/tool-search
layer would need to fill.

### 3. Prior decisions and the process-economy roadmap

No ADR exists yet under any of `progressive-disclosure`+`token-budget`, `tool search`, or `code execution`
tags that directly proposes a skill-search or code-mode mechanism (`query_adrs.py --grep` and `--tags`
checked; closest architectural precedent is `dec-167`, the rules-only hook-delivered blacklist, above).

The load-bearing prior artifact is **`docs/independent-analysis/process-economy-roadmap.md`** (Spike,
2026-09-07, `head_sha_analyzed: 55964a73`) — an internal five-lens study of exactly this problem space.
Key figures it established (all VERIFIED against a stated command in the source document):

- Skill+command+agent listing (ungoverned, pre-diet): **~16,713 tokens** (skills 35,886 chars, commands
  10,585, agents 12,316).
- Preloaded `skills:` bodies across all 17 agent frontmatters: **240,647 tokens** — larger than the
  136,976 tokens of the 17 agent definitions themselves. The implementer preloads 4.2× its own body size;
  four interface-design skills are each preloaded by 5 agents; `external-api-docs` (5,156 tokens) is
  preloaded by 9 of 17 agents. Only **12 of 18,042 WAL rows** were `Skill` tool invocations — i.e.
  **preload, not on-demand `Skill`-tool loading, is overwhelmingly the actual delivery path** for skill
  content today, which the roadmap calls out as progressive disclosure "not happening at the agent layer."
  This is directly relevant to any search-based design: a search mechanism competes with a preload habit
  that is already deeply embedded in agent frontmatter.
- W3 ("Skill discovery is silently truncated") is the finding already summarized above.
- The roadmap's own P0.2/P1.12 execution history (calibration log) is the ground truth for "what was
  already tried": P1.12 (2026-09-08) ran a description diet across all 62 `SKILL.md` files and 2 command
  flags; it attempted `skillOverrides: name-only` for 12 skills (later shown inert, td-197 above); it moved
  the honest listing from ~11,336 → 9,243 tokens (not the originally claimed 8,043, corrected 2026-09-11).
  **57 of 62 descriptions remained over the ≤300-char diet target** because a "preserve trigger nouns" rule
  outranked the character cap — the diet has a documented ceiling of its own. A skill-retirement candidate
  list (12 zero-evidence skills) was produced but **not executed** — left as a standing, unactioned option
  (`.ai-state/calibration_log.md:111`, `SKILL_RETIREMENT_CANDIDATES.md`, referenced but not present in this
  worktree — it was ephemeral `.ai-work/` output from that prior pipeline and has presumably been cleaned
  up).
- The roadmap names `/skill-doctor` (Claude Code **v2.1.252+**, a *native* harness command, not a Praxion
  command — confirmed by its absence from `commands/*.md` in this repo) as the one piece of tooling that
  supplies "exactly the per-skill cost telemetry Praxion lacks" (per-skill context cost, unused-skill
  detection, truncation state). Praxion's own `CLAUDE.md:32` already tells operators to run it alongside
  `sentinel`, but no automated check currently calls it (confirmed: `.ai-state/calibration_log.md:133`
  records it as "a session-only info command with no docs page; cannot be scheduled").
- The roadmap's own quality-metrics table (§8) sets an explicit target: **"Skills with a visible
  description in a 200k-window session: ~22 of 62 measured → 62 of 62 target,"** gated on `/skill-doctor`
  and the P1.12 check — i.e. Praxion's own roadmap already names full-listing-visibility as an open,
  unclosed target, not a solved problem.

### 4. Existing MCP servers and structured indices

- **`task-chronograph-mcp`** (in-repo, Praxion-built): 3 tools (`get_pipeline_status`, `get_agent_events`,
  `report_interaction`, `task_chronograph_mcp/server.py:305-340`) — observability/telemetry, unrelated to
  component selection.
- **likec4** (third-party MCP, config-registered, not built by Praxion): **18 tools**
  (`skills/likec4-querying/references/mcp-tool-recipes.md`), already organized exactly in the
  discover→read→filter shape a skill-search mechanism would need: `list-projects`, `read-project-summary`,
  `search-element` (Discovery); `read-element`, `read-view` (Read); `find-relationships`,
  `query-graph` (Relationships); `query-by-metadata`, `query-by-tags`, `query-by-tag-pattern` (Filtering);
  `batch-read-elements` (Bulk). This is a **working in-repo precedent** for the "search + targeted fetch"
  pattern (as opposed to "list everything upfront") that a `praxion-skills` MCP server would replicate for
  skill/command/agent selection — `search-element`/`query-by-tags` are structurally analogous to a
  hypothetical `search_skills(query|tags)`.
- **No skill/command/agent search index exists.** `skills/README.md`, `commands/README.md`,
  `agents/README.md` are human-facing prose catalogs, not structured data. `rules/_manifest.yaml`
  (auto-generated, `scripts/regenerate_rules_manifest.py`) *does* exist for rules and carries exactly the
  fields a search index would want — `id`, `path`, `load`, `core`, `install`, `chars` per rule — but there
  is **no equivalent generator for skills, commands, or agents** (`ls scripts/*manifest*.py` returns only
  rule- and doc-manifest generators; `scripts/apply_skill_description_diet.py` exists for the P1.12 diet but
  produces no persisted index). `.ai-state/doc_manifest.yaml` (schema v2, auto-generated,
  `scripts/build_doc_manifest.py`) indexes long-form **documentation surfaces** (README, `docs/*.md`) for
  the dashboard, not skills/commands/agents. **This is a clean, low-cost insertion point**: a
  `scripts/regenerate_skills_manifest.py` mirroring `regenerate_rules_manifest.py`'s shape (id, path,
  description, byte/token size, `disable-model-invocation` state, `staleness_sensitive_sections`) would give
  any downstream search tool (MCP server or hook) a machine-readable corpus to index against, without first
  having to re-parse 128 frontmatter blocks itself.

### 5. Selection-failure evidence

- **Listing truncation (already covered above)** is the one *quantified* selection-failure mode in the
  corpus: ~40 of 62 skills silently name-only in the session that discovered it; roadmap target of "62 of 62
  visible" still open per the quality-metrics table.
- **The sentinel explicitly flags its own blind spot here.** The most recent sentinel report
  (`.ai-state/sentinel_reports/SENTINEL_REPORT_2026-09-14_07-59-49.md:45,64`) records the listing surface at
  "9,243 / 9,243 ceiling — at ratchet ceiling" (i.e., sitting exactly at the frozen no-regression floor, not
  the lower 1%-of-window target) and separately states that a **full-corpus semantic pass — "skill-description
  activation quality" among the named dimensions — was NOT performed this run** ("reasoning-effort and
  turn-budget tradeoff... the largest coverage gap in this run"). In other words: Praxion's own coherence
  auditor does not currently check whether skill descriptions actually cause correct activation; it checks
  only the aggregate token size against a frozen ceiling.
- I found no `LEARNINGS.md` or ADR entry in this worktree recording a concrete "wrong skill fired" or
  "agent missed an obviously-relevant skill" incident — the failure mode documented in the corpus is
  *invisibility* (truncation dropping a description before the model ever sees it), not *misfire* (model
  saw a description and picked wrong). Absence of misfire evidence should not be read as absence of the
  problem — it is more likely unmeasured, per the sentinel's own admitted coverage gap.

### 6. Concrete insertion points

| Mechanism | Files / harness features involved | Constraints |
|---|---|---|
| **`praxion-skills` MCP server (search + load)** | New in-repo MCP server (pattern precedent: `task-chronograph-mcp/`, tool-shape precedent: likec4's `search-element`/`query-by-tags`); would need a source index — either generated fresh (`scripts/regenerate_skills_manifest.py`, mirroring `rules/_manifest.yaml`'s shape) or built by scanning `skills/*/SKILL.md` + `commands/*.md` + `agents/*.md` at server start | MCP tools are *deferred by default* in current Claude Code (`skills/mcp-crafting/SKILL.md:49` — tool search is on, schemas not loaded upfront), so registering the server itself is cheap; but it does **not** remove the native listing scan — skill/command/agent descriptions still render at session start regardless of whether an MCP server also exists. An MCP layer can supplement discovery (search a corpus the native listing dropped) but cannot, by itself, suppress the native listing's token cost. Cross-platform: MCP is the *one* mechanism that ports cleanly to Codex (`codex/config/manage-codex-mcp.py` already manages Codex MCP registration) and is a plausible route for Cursor too (Cursor has no Agent-Skills concept at all — `install.sh cursor` exports only *rules*, per `rules/CLAUDE.md`); an MCP-based search layer is more portable than any Claude-Code-native fix. |
| **SessionStart/UserPromptSubmit hook injecting only top-k relevant skills** | Direct precedent: `hooks/inject_rules.py` (`dec-167` Channel 2) already does exactly this pattern for *rules* — reads a project manifest, computes what should load, delivers via `additionalContext`. A skill equivalent would need a `hooks/inject_skills.py` and a routing signal (keyword match against a generated skill manifest, or an embedding index) | This is a **behavioral suppression, not physical exclusion**, on the skill side — Claude Code's own listing scan of `skills/*/SKILL.md` still happens independently; a hook can only *add* context (`additionalContext`), not remove the native listing's tokens. To get physical exclusion the way `dec-167` did for rules, the skill would need to *not exist* as a native-format file (e.g., stored elsewhere and materialized/symlinked only when selected) — a much larger structural change, and one that breaks the plugin's static `skills: ["./skills/"]` glob registration (`skills/CLAUDE.md`). |
| **Agent-frontmatter `skills:` preload** (already in use) | `agents/*.md` frontmatter, all 17 agents | Already the dominant delivery path today (240,647 tokens preloaded vs. 12 `Skill`-tool calls in 18,042 WAL rows, per the roadmap) — this is evidence *against* relying on preload lists as the long-term selection mechanism: it is static per-agent-type, not per-task, and it is already the single largest cost line in the whole pipeline. Any new mechanism competes with — and should probably aim to replace — this pattern, not add to it. |
| **Skill consolidation / retirement** | The already-produced-but-unexecuted candidate list from P1.12b (12 zero-evidence skills, WAL-cross-referenced) | Cheapest available lever, zero new machinery, purely a disposition decision left to the user (per the calibration log: "12 zero-evidence candidates, PROPOSED NOT EXECUTED"). Reduces the denominator directly rather than adding a routing layer on top of it. |
| **`disable-model-invocation` widening** | `commands/*.md` (already 33/44), `skills/*/SKILL.md` (2/63, deliberately not widened further per the P1.12 rejection) | Verified working for commands; explicitly rejected for skills for the reason above (kills preload + `Skill`-tool access, not just listing visibility) — not a viable lever without harness support for a "hidden from listing, still loadable" state. |
| **Manifest generation as a prerequisite for any of the above** | `scripts/regenerate_rules_manifest.py` (existing pattern to copy), `.ai-state/doc_manifest.yaml`/`scripts/build_doc_manifest.py` (existing pattern for docs) | No code risk — this is additive tooling with a direct in-repo template. Whatever selection mechanism is chosen (MCP search, hook injection, consolidation) needs *some* structured corpus to search or route against; today none exists for skills/commands/agents, only for rules and docs. |

## Comparative Analysis

Not applicable in the strict library/framework sense — this is an architecture-insertion-point question, not
a library selection. The table above (§6) substitutes for a comparative matrix: each row names the
mechanism, its precedent, and its binding constraint.

## Divergence Map

No cross-source conflicts found. The two quantitative sources that overlap — `measure_token_budget.py`'s
live output (9,243 tokens, 2026-09-23) and the process-economy roadmap's own historical figures — agree:
the roadmap's corrected P1.12 outcome (9,243, corrected 2026-09-11 per `td-197`) is exactly what the script
reports today, eleven days later, meaning the listing has been static at the ratchet ceiling since the
correction (also independently confirmed by the 2026-09-14 sentinel report reading the identical figure).
One internal document (`CLAUDE.md:32`) still names `/skill-doctor` as if it were schedulable at sentinel
cadence; the calibration log (2026-09-20) already corrected this in Praxion's own records ("a session-only
info command with no docs page; cannot be scheduled") — not a live divergence, just a not-yet-propagated
correction in a second file. Worth a one-line fix in `CLAUDE.md` but out of this research task's scope.

## Open Questions

- **Is the listing currently truncated, and by how much?** Size (9,243 tokens) exceeds the documented ~1%
  (~2,000-token) truncation-risk band by 4.6×, but I could not directly sample a live session's rendered
  listing to count current drops. Recommend running `/skill-doctor` (native command) in a fresh session as
  the fastest way to get a current, first-party truncation count — this was exactly the roadmap's own P0.2
  recommendation, seemingly still unexecuted as scheduled telemetry.
- **Does the ~1% truncation cap apply separately to skills, commands, and agents, or to the combined
  listing?** The one cited source (`skills.md § "Skill descriptions are cut short"`) speaks only of "skill
  descriptions" — whether commands and the agent-type enum share the same budget or have independent (or no)
  truncation behavior is unconfirmed from the sources checked in this pass.
- **Whether the harness exposes any programmatic hook into the listing-render step** (as opposed to only
  `additionalContext` injection after the fact) is unconfirmed — this is the crux fact that determines
  whether a hook-based mechanism can ever achieve *physical* (not just behavioral) skill-listing reduction
  the way `dec-167` achieved it for rules. Worth a direct check against current Claude Code hook-event docs
  before committing to a design.

## Sources

- `scripts/measure_token_budget.py` (read + executed) — canonical listing/budget instrument, this pass's
  primary measurement tool.
- `docs/context-economy.md` — subagent-inheritance and spawn-context baseline figures.
- `skills/skill-crafting/references/context-engineering-foundations.md` — progressive-disclosure/attention-budget
  framing shared across all `*-crafting` skills.
- `skills/mcp-crafting/SKILL.md` §"Before You Build" and §"Code Execution with MCP (Emerging)" — current
  tool-search/deferred-loading behavior and the Anthropic code-execution-with-MCP pattern already documented
  in-repo.
- `docs/independent-analysis/process-economy-roadmap.md` — the load-bearing prior internal study; source of
  the W3 truncation finding, the preload-vs-Skill-tool imbalance, and the P0.2/P1.12 execution history.
- `.ai-state/decisions/167-hook-delivered-blacklist-mechanism.md` (dec-167) — the only existing precedent for
  physical, hook-delivered context exclusion (rules only, not skills).
- `.ai-state/TECH_DEBT_RESOLVED.md:27` (td-197) — `skillOverrides` inertness, resolved.
- `.ai-state/calibration_log.md` (rows 2026-09-07/08/11/20) — P1.12 execution history, the disable-model-invocation-for-skills
  rejection, and the `/skill-doctor` scheduling correction.
- `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-09-14_07-59-49.md` — current listing-ceiling reading and
  the sentinel's admitted semantic-activation coverage gap.
- `skills/likec4-querying/references/mcp-tool-recipes.md` — in-repo precedent for a search-then-fetch MCP
  tool shape.
- `rules/_manifest.yaml` / `scripts/regenerate_rules_manifest.py` — precedent structured-index generator (no
  skills/commands/agents equivalent exists).
- `codex/config/manage-codex-mcp.py`, `codex/config/export-codex-skills.py` — Codex export surface;
  constrains any mechanism to also work through (or be replicated by) the Codex bridge.
- `rules/CLAUDE.md` (Installation section) — confirms Cursor export carries rules only, no skills concept.
