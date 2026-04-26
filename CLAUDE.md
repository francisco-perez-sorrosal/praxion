# Praxion

The operational infrastructure for the development philosophy defined in `~/.claude/CLAUDE.md`. This repo provides the skills, agents, rules, commands, and MCP servers that make the philosophy actionable across projects.

## How the Ecosystem Serves the Philosophy

See the mapping table in `~/.claude/CLAUDE.md` under "The Ecosystem as Philosophy's Implementation." This repo is where those components live — skills, agents, rules, commands, and MCP servers are all authored and maintained here.

## Working Here

- Load the matching crafting skill before modifying any component: `skill-crafting` for skills, `agent-crafting` for agents, `command-crafting` for commands, `rule-crafting` for rules
- **Never modify `~/.claude/plugins/cache/`** — edit source files in this repo; installed copies get overwritten on reinstall
- **Token budget**: Always-loaded content (CLAUDE.md files + rules) must stay under 25,000 tokens (~87,500 chars) as a failure-mode guardrail — the principle is that every always-loaded token must earn its attention share (applied in >30% of sessions, or unconditionally relevant). Prefer skills with reference files for procedural content; reserve rules for declarative domain knowledge.
- **Worktrees** use `.claude/worktrees/<name>/`. Pipeline worktrees via `EnterWorktree`; scratch worktrees via `/create-worktree`. Both share the same home. ADRs created in a pipeline land as fragments under `.ai-state/decisions/drafts/` and are promoted to stable `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`. PR-adjacent workflow conventions live in `rules/swe/vcs/pr-conventions.md` (path-scoped)
- **Onboarding artifacts dogfooding**: Praxion uses its own onboarding tools — Praxion's `.ai-state/`, `.gitattributes`, git hooks, and `CLAUDE.md` blocks are all results of the patterns `/onboard-project` applies to user projects. When updating `/onboard-project` or `/new-project`, verify the change still produces what Praxion itself has on disk (or, if the update is meant to evolve the contract, propose what changes Praxion's own state needs)
- See `README.md` for user-facing docs, `README_DEV.md` for contributor conventions, `skills/README.md` for the skill catalog, `docs/greenfield-onboarding.md` + `docs/existing-project-onboarding.md` for the two onboarding paths

## Session Protocol

At session start, call `session_start` on the memory MCP to load context about the user, project conventions, and past learnings (Recall). Store discoveries proactively during the session (Learn). Apply past insights to current tasks (Apply). This implements the Learning Loop from the global philosophy.

If `memories.assistant.name` is missing, pick a random name and store it immediately. Be curious about the user — learn their interests, background, and working style over time.

## Onboarding (Praxion → User Project)

Praxion ships **two onboarding paths** that converge on the same end state — `.gitignore` block, `.ai-state/` skeleton, `.gitattributes` + merge drivers, git hooks, `.claude/settings.json` toggles, three `CLAUDE.md` blocks (Agent Pipeline + Compaction Guidance + Behavioral Contract), opt-in architecture baseline:

- **Greenfield** (empty directory): `new_project.sh` + `/new-project` — bash entry validates prereqs and scaffolds, then `exec`s a Claude Code session that runs the seed pipeline (researcher → architect → planner → implementer + test-engineer → verifier) and chains to `/onboard-project` for the surfaces it doesn't cover. Companion doc: `docs/greenfield-onboarding.md`.
- **Existing project** (has code): `/onboard-project` — phased, gated, idempotent (9 phases, 8 gates with one-way Run-all-rest). Phase 8 optionally delegates to `systems-architect` in baseline-audit mode to produce `.ai-state/ARCHITECTURE.md` + `docs/architecture.md`. Companion doc: `docs/existing-project-onboarding.md`.

When working on Praxion's onboarding artifacts, the source-of-truth chain runs: `commands/onboard-project.md` (canonical CLAUDE.md blocks + idempotency predicates) → `commands/new-project.md` (mirror for greenfield) → `new_project.sh` (greenfield bootstrap). Changes to the canonical blocks must mirror across both commands for byte-identical output.

## Design Principles

- **Assistant-agnostic shared assets**: `skills/`, `commands/`, `agents/` at the repo root, reusable across tools
- **Assistant-specific config in subdirectories**: `claude/config/` for Claude, `cursor/config/` for Cursor
- **Progressive disclosure**: Skills load metadata at startup, full content on activation, reference files on demand — keeping token cost minimal

## Guiding Principles (Praxion-specific)

Extends `~/.claude/CLAUDE.md`. Four principles: **token budget first-class**, **measure before optimize**, **standards convergence as opportunity**, **curiosity over dogma**. Rationale: `README.md#guiding-principles` and `ROADMAP.md#guiding-principles-for-execution`.

## Behavioral Contract (applied)

Praxion enforces the four-behavior contract from the global philosophy (`~/.claude/CLAUDE.md`):

- **Surface Assumptions** before acting on them
- **Register Objection** when a request violates scope, structure, or evidence
- **Stay Surgical** — minimal scope, minimal blast radius
- **Simplicity First** — the smallest solution that achieves the behavior

Operationalized via the always-loaded `rules/swe/agent-behavioral-contract.md` rule, per-agent self-tests, and named failure-mode tags in verification reports. See `skills/software-planning/references/behavioral-contract.md`.

## Compaction Guidance

When compacting, always preserve: active pipeline stage and task slug, current WIP step number and status, acceptance criteria from the plan, and the list of modified files. The `PreCompact` hook snapshots pipeline documents to `.ai-work/PIPELINE_STATE.md` — re-read that file after compaction to restore orientation.

## Known Claude Code Limitations

Tracked here so they can be revisited when Claude Code releases fixes:

- **`isolation: "worktree"` on Agent tool creates nested worktrees** — when the session is already in a worktree (via `EnterWorktree`), agent worktrees nest inside it with opaque `agent-<hex>` names, fragmenting work. Workaround: never use `isolation: "worktree"`, rely on `EnterWorktree` + fragment files. Claude Code issues: [#27881](https://github.com/anthropics/claude-code/issues/27881) (nested creation), [#33045](https://github.com/anthropics/claude-code/issues/33045) (silent ignore for team agents). If these are fixed and worktree naming becomes controllable, reconsider the single-worktree policy in `swe-agent-coordination-protocol.md`
