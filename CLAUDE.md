# Praxion

The operational infrastructure for the development philosophy in `~/.claude/CLAUDE.md`. This repo provides the skills, agents, rules, commands, and MCP servers that make the philosophy actionable across projects.

## Agent reading order

1. **CLAUDE.md** (this file) — Praxion-specific agent baseline
2. **`rules/**/*.md` without `paths:` frontmatter** — always-on conventions (coordination protocol, behavioral contract, ADR conventions, agent intermediate documents, model routing, memory protocol, git conventions)
3. **`rules/**/*.md` with `paths:` frontmatter** — load when matching files are touched (diagram conventions, coding style, dashboard conventions, PR conventions, etc.)
4. **`skills/<name>/SKILL.md`** — load when description matches the task
5. **`skills/<name>/references/*.md`** — on demand from the skill body
6. **`.ai-state/DESIGN.md`** — when reasoning about Praxion's system design
7. **`docs/architecture.md`** — when navigating the code-verified component map

## Build / test / lint

- `bash install.sh` — install plugin to `~/.claude` (registers rules, hooks, settings)
- `bash install.sh --check` — verify install without applying
- `python3 -m pytest tests/ -q` — Praxion's own tests
- `cd eval && PYTHONPATH=src python3 -m pytest -q` — eval framework tests
- `python3 -m pytest scripts/test_finalize_adrs.py -q` — ADR finalize tests
- `python3 scripts/sync_canonical_blocks.py --check` — verify shipped blocks are in sync
- `cd dashboard_app && ./node_modules/.bin/vitest run` — dashboard package tests
- `cd dashboard_app && ./node_modules/.bin/next build` — dashboard production build
- `scripts/praxion-dashboard start /path/to/project` — launch the read-only dashboard for a target project

## Frequent operations

What you'll most often be asked to do in this repo:

- **Craft or modify a component** (skill / rule / agent / command / hook) — load the matching `*-crafting` skill first, then run that skill's validator.
- **Update content shipped into managed projects** — edit `claude/canonical-blocks/<slug>.md`, run `python3 scripts/sync_canonical_blocks.py --write`, mirror the change in `commands/onboard-project.md` + `commands/new-project.md` (the sync-check is in *Build / test / lint* above).
- **Run an audit or roadmap pass** — `/sentinel` (coherence), `/project-metrics` (health), `/roadmap` (audit→roadmap; per `dec-092` Praxion does not carry a living `ROADMAP.md` instance — the cartographer regenerates on demand).
- **Work on the dashboard** — `dashboard_app/` (Next.js runtime over `.ai-state/`); its test + build commands are in *Build / test / lint* above.
- **Add or refine docs** — long-form Diátaxis-shaped docs under `docs/` (index: `docs/README.md`); component catalogs in `agents/README.md` / `skills/README.md` / `commands/README.md` / `rules/README.md`.

## Repository layout

| Path | Purpose |
|---|---|
| `agents/` | Subagent definitions; pipeline overview in `agents/README.md` |
| `commands/` | Slash commands; catalog in `commands/README.md` |
| `skills/` | Domain expertise + references; catalog in `skills/README.md` |
| `rules/` | Always-loaded + path-scoped conventions; catalog in `rules/README.md` |
| `hooks/` | Hook scripts |
| `claude/canonical-blocks/` | Source of truth for content shipped into managed projects (sync via `scripts/sync_canonical_blocks.py`) |
| `claude/aac-templates/` | Architecture-as-Code templates installed by `/onboard-project` |
| `dashboard_app/` | Active Next.js dashboard runtime reading `.ai-state/`, `.ai-work/`, and selected project-root artifacts through a server-only layer |
| `docs/` | Long-form human-facing documentation, Diátaxis-shaped (index in `docs/README.md`) |
| `.ai-state/` | Persistent project intelligence (committed) — `DESIGN.md`, `decisions/`, sentinel reports, tech-debt ledger |
| `.ai-work/` | Ephemeral pipeline intermediates (gitignored) |
| `tests/` | Test suites |
| `scripts/` | Operational scripts (install, sync, finalize) — see `scripts/CLAUDE.md` when working there |
| `eval/` | Out-of-band quality eval framework |
| `memory-mcp/` | Memory MCP server (when enabled) |

## Critical conventions

- **Token budget**: always-loaded content (CLAUDE.md files + always-on rules) stays under **25,000 tokens** (~87,500 chars). Adding to it requires `wc -c` measurement. The principle is that every always-loaded token must earn its attention share (applied in >30% of sessions, or unconditionally relevant). Prefer skills with reference files for procedural content; reserve rules for declarative domain knowledge.
- **Never modify `~/.claude/plugins/cache/`** — edit source files here; installed copies overwrite on reinstall.
- **No AI authorship** in commit messages — see `rules/swe/vcs/git-conventions.md`.
- **Build output to `/dev/null`**, temp files in `tmp/` (gitignored), debug prints prefixed `# DEBUG:` for grep-removal.
- **Praxion-specific principles** (extend `~/.claude/CLAUDE.md`): token budget first-class, measure before optimize, standards convergence as opportunity, curiosity over dogma. Full rationale in `README.md#guiding-principles`.
- **Assistant-agnostic shared assets** at repo root (`skills/`, `commands/`, `agents/`); assistant-specific config in subdirectories (`claude/config/`, `codex/config/`, `cursor/config/`).
- **Progressive disclosure** in skills (metadata at startup, body on activation, references on demand) is a load-bearing pattern — preserve it when crafting new skills.
- **Memory MCP disabled for Praxion** (`PRAXION_DISABLE_MEMORY_MCP=1`): skip `remember`, `recall`, `search`, `browse_index` calls. The protocol in `rules/swe/memory-protocol.md` applies when memory is available; here it is not.

## When NOT to use the full pipeline

Match process weight to task scale. The tier table + fast-path selector — Direct → Lightweight → Standard → Full, plus Spike (per-tier signals and process) — live in `rules/swe/swe-agent-coordination-protocol.md` § Process Calibration (always loaded). Default to the lower tier when uncertain — process can be added; overhead cannot be reclaimed.

## How to verify your work

- Run `pytest` over the relevant module(s) — behavior verification
- `python3 scripts/sync_canonical_blocks.py --check` — shipped-block drift
- `/sentinel` — ecosystem coherence audit
- For doc changes: render-time check via the dashboard; for HTML companions, browser preview
- Anthropic's "single highest-leverage" practice: pair every claim a doc makes with a verification path

## Claude-Code-specific machinery

**Component crafting**: load the matching skill before modifying any component — `skill-crafting`, `agent-crafting`, `command-crafting`, `rule-crafting`, `hook-crafting`.

**Worktrees**: `.claude/worktrees/<name>/`. Pipeline worktrees via `EnterWorktree`; scratch via `/create-worktree`. ADRs created in a pipeline land as fragments under `.ai-state/decisions/drafts/` and are promoted to `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`. PR-adjacent workflow conventions live in `rules/swe/vcs/pr-conventions.md` (path-scoped).

**Onboarding artifacts dogfooding**: Praxion uses its own onboarding tools — Praxion's `.ai-state/`, `.gitattributes`, git hooks, and `CLAUDE.md` blocks are all results of patterns `/onboard-project` applies to user projects. When updating `/onboard-project` or `/new-project`, verify the change still produces what Praxion has on disk (or, if evolving the contract, propose what changes Praxion's own state needs).

**Onboarding contract**: Praxion ships **two onboarding paths** converging on the same end state — `.gitignore` block, `.ai-state/` skeleton, `.gitattributes` + merge drivers, git hooks, `.claude/settings.json` toggles, three `CLAUDE.md` blocks (Agent Pipeline + Compaction Guidance + Behavioral Contract), opt-in architecture baseline:

- **Greenfield** (empty dir): `new_project.sh` + `/new-project` — bash entry validates prereqs and scaffolds, then `exec`s a Claude Code session that runs the seed pipeline and chains to `/onboard-project`. Companion: `docs/greenfield-onboarding.md`.
- **Existing project** (has code): `/onboard-project` — phased, gated, idempotent (10 phases, 9 gates). Phase 8 optionally produces `.ai-state/DESIGN.md` + `docs/architecture.md`; Phase 8b installs the AaC tier; Phase 8c scaffolds ML/AI training conventions when detected. Companion: `docs/existing-project-onboarding.md`.

Source-of-truth chain for canonical blocks: `commands/onboard-project.md` → `commands/new-project.md` → `new_project.sh`. Changes to canonical blocks must mirror across both commands for byte-identical output.

**Behavioral Contract (applied)**: Praxion enforces the four-behavior contract — Surface Assumptions, Register Objection, Stay Surgical, Simplicity First. Canonical text in `rules/swe/agent-behavioral-contract.md` (always loaded); deep dive in `skills/software-planning/references/behavioral-contract.md`. Operationalized via per-agent self-tests and named failure-mode tags in verification reports.

**Compaction Guidance**: When compacting, always preserve: active pipeline stage and task slug, current WIP step number and status, acceptance criteria from the plan, and the list of modified files. The `PreCompact` hook snapshots pipeline documents to `.ai-work/PIPELINE_STATE.md` — re-read after compaction to restore orientation.

## Where to find more

- `README.md` — first-contact narrative, install, project pitch, full Guiding Principles rationale
- `README_DEV.md` — contributor conventions, dev workflow
- `docs/README.md` — long-form Diátaxis-shaped documentation index
- `docs/architecture.md` — code-verified Praxion architecture (developer-facing)
- `.ai-state/DESIGN.md` — design-target architecture (architect-facing)
- `agents/README.md`, `skills/README.md`, `commands/README.md`, `rules/README.md` — component catalogs
- `.ai-state/decisions/DECISIONS_INDEX.md` — auto-generated ADR index

## Known Claude Code Limitations

Tracked here so they can be revisited when Claude Code releases fixes. Each entry is the working summary; full diagnostic detail lives in the linked issue and the `td-NNN` tech-debt-ledger row.

- **`isolation: "worktree"` on the Agent tool nests worktrees** when the session is already in one (opaque `agent-<hex>` names; fragmented work). Workaround: never pass `isolation: "worktree"` — use `EnterWorktree` + fragment files (the single-worktree policy in `swe-agent-coordination-protocol.md`). Issues [#27881](https://github.com/anthropics/claude-code/issues/27881) (nested creation), [#33045](https://github.com/anthropics/claude-code/issues/33045) (silent ignore for team agents); revisit the policy if both are fixed.
- **Shipped `Explore` subagent crashes during init in many-skill sessions** (Claude Code 2.1.136) — `Agent(subagent_type="Explore", ...)` throws a JS error before the agent starts; not prompt-size dependent; input context is billed with no output (orphaned-tool-start). Workaround: use `i-am:researcher` for substantive code surveys, `find`/`grep` via Bash for narrow lookups; reserve shipped `Explore` for quick single-file lookups only, and expect occasional failures. Tracked as `td-021` (upstream report drafted); same root-cause family as [#38868](https://github.com/anthropics/claude-code/issues/38868).
- **Path-scoped rules (`paths:` frontmatter) inject on Read, not on Write/Edit/MultiEdit** (verified 2026-05-12) — an agent that *creates* a new file without first reading a matching sibling misses that file type's conventions (`coding-style.md` for a new `.py`/`.ts`, `readme-style.md`/`diagram-conventions.md` for a new doc, `pr-conventions.md` for a new `.github/*.md`, etc.). The one verified gap in the rules-as-guardrails surface; moderate severity — agents usually read a directory before working there, which incidentally loads the rule. **Upstream stance is now settled (2026-05-12 re-check):** [#23478](https://github.com/anthropics/claude-code/issues/23478) closed `NOT_PLANNED` 2026-03-14 and feature request [#38487](https://github.com/anthropics/claude-code/issues/38487) closed `NOT_PLANNED` 2026-04-30 — Claude Code has **explicitly declined** to load path-scoped rules on Write/Edit. The mitigation is therefore **permanent**: the `implementer`/`doc-engineer`/`test-engineer` prompts carry a "read a sibling first" instruction; `rules/CLAUDE.md` notes the caveat and `skills/rule-crafting/SKILL.md` carries the full mitigation. [#16853](https://github.com/anthropics/claude-code/issues/16853) remains open with a useful syntactic workaround signal — multi-entry YAML-list `paths:` may fail under the `_9A()` CSV parser, while inline-array (`paths: ["**/*.py", ...]`) and single-entry brace-expansion (`paths: ["**/*.{py,pyi}"]`) work consistently; `scripts/check_paths_syntax.py` flags at-risk Praxion rule files. Tracked as `td-033`. Windows variant [#21858](https://github.com/anthropics/claude-code/issues/21858) closed `COMPLETED` 2026-03-24 — the existing Windows caveat in `docs/existing-project-onboarding.md` stays in place as historical guidance, no further action.
- **Subagent `Write` to `.ai-work/<task-slug>/` can be denied by the sandbox** while the main agent's `Write` to the same path succeeds (observed 2026-05-14 with `i-am:systems-architect` writing `SYSTEMS_PLAN.md`). The architect agent has `Write` in its tools whitelist and the target resolves inside the session worktree (so `worktree_guard.py` allows it); the denial appears to be Claude Code's per-tool permission prompt that the main agent had already auto-allowed for this session but the subagent cannot answer interactively. Workaround: when a subagent reports a Write denial for `.ai-work/`, the main agent should place the file from the subagent's returned content — the same pipeline contract is honored, just routed through the orchestrator. Distinct from `td-034` (subagent writes resolve to the wrong tree); same root-cause family in that subagent settings/permission inheritance differs from the orchestrator session. Tracked as `td-035`.
