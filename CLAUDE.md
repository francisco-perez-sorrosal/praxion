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
| `streamlit_app/` | Legacy Streamlit dashboard retained temporarily as a migration reference until retirement |
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

Match process weight to task scale. Tier table from `rules/swe/swe-agent-coordination-protocol.md`:

| Tier | Signals | Process |
|---|---|---|
| Direct | Single-file fix, config, doc, typo | Fix → verify → commit; no agents |
| Lightweight | 2–3 files, single behavior | Optional researcher; inline acceptance criteria |
| Standard | 4–8 files, architectural decisions | Full pipeline (researcher → architect → planner → implementer ∥ test-engineer → verifier) |
| Full | 9+ files, cross-cutting | Standard + parallel execution + context-engineer shadowing |
| Spike | Exploratory | Timeboxed researcher; decision in `LEARNINGS.md` |

Default to the lower tier when uncertain — process can be added; overhead cannot be reclaimed.

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

Tracked here so they can be revisited when Claude Code releases fixes:

- **`isolation: "worktree"` on Agent tool creates nested worktrees** — when the session is already in a worktree (via `EnterWorktree`), agent worktrees nest inside it with opaque `agent-<hex>` names, fragmenting work. Workaround: never use `isolation: "worktree"`, rely on `EnterWorktree` + fragment files. Claude Code issues: [#27881](https://github.com/anthropics/claude-code/issues/27881) (nested creation), [#33045](https://github.com/anthropics/claude-code/issues/33045) (silent ignore for team agents). If these are fixed and worktree naming becomes controllable, reconsider the single-worktree policy in `swe-agent-coordination-protocol.md`.
- **Shipped `Explore` subagent crashes during init in many-skill sessions** (Claude Code 2.1.136, observed 2026-05-08) — `Agent(subagent_type="Explore", ...)` returns `undefined is not an object (evaluating 'K.length')` before the agent starts. Reproducible with a minimal 50-word prompt — not prompt-size dependent. Failure mode is a silent JS crash inside the bundled CLI: orphaned-tool-start in chronograph (input context billed, no output). Same root-cause family as upstream [#38868](https://github.com/anthropics/claude-code/issues/38868) (CLOSED on 2.1.83) which surfaced as "Prompt is too long" — our variant is a hard JS exception with no recoverable error. Workaround: prefer `i-am:researcher` (Praxion) for substantive code inventory and codebase research; reserve shipped `Explore` only for quick single-file lookups, and even then expect occasional failures. Use `find`/`grep` via Bash directly when neither agent is warranted. Tracked as `td-021`; upstream report drafted via `i-am:upstream-stewardship`.
- **Path-scoped rules (`paths:` frontmatter) inject on Read, not on Write/Edit/MultiEdit** (verified 2026-05-12 against `code.claude.com/docs/en/memory` + GitHub issues) — an agent that *creates* a new file via `Write` without first reading a matching sibling misses that file type's conventions: a new `.py`/`.ts` misses `coding-style.md`; a new doc misses `readme-style.md`/`diagram-conventions.md`/`html-output-conventions.md`/`aac-dac-conventions.md`; a new `.github/*.md` misses `pr-conventions.md`; new files miss `id-citation-discipline.md`, `staleness-policy.md`. This is the one verified finding that touches Praxion's rules-as-guardrails guarantee surface directly. Moderate severity — agents usually read a directory before working in it, which incidentally loads the rule — real for greenfield file creation. Mitigation: the `implementer`/`doc-engineer`/`test-engineer` prompts carry a "read an existing sibling before creating a new file" instruction; `skills/rule-crafting/SKILL.md` documents the symptom and full mitigation; `rules/CLAUDE.md` notes the caveat next to the `paths:` convention. Claude Code issues: [#23478](https://github.com/anthropics/claude-code/issues/23478), [#38487](https://github.com/anthropics/claude-code/issues/38487) (feature request — load path-scoped rules on Write/Edit), [#16853](https://github.com/anthropics/claude-code/issues/16853). Windows variant: per [#21858](https://github.com/anthropics/claude-code/issues/21858), `paths:` in `~/.claude/rules/` is ignored on Windows (closed-as-stale, not confirmed fixed; not reproduced on macOS/Linux) — Windows users should keep path-scoped rules under a project-level `.claude/rules/` (noted in `docs/existing-project-onboarding.md`). Tracked as `td-033`; if Claude Code resolves #38487 the agent-prompt mitigation can be relaxed.
