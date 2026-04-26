---
description: Onboard an existing project to the Praxion ecosystem (gitignore, .ai-state/, hooks, settings, CLAUDE.md)
allowed-tools: [Bash(git:*), Bash(grep:*), Bash(find:*), Bash(test:*), Bash(ln:*), Bash(mkdir:*), Bash(command:*), Bash(jq:*), Bash(cat:*), Read, Write, Edit, Glob, Grep, AskUserQuestion, Task]
---

Onboard the **current existing** project to work cleanly with the Praxion plugin (`i-am`). This is the existing-project counterpart to `/new-project` (greenfield). The command runs phased, with `AskUserQuestion` gates between phases — each gate explains what's about to happen so you learn the shape, not just observe it. A one-way **Run all rest** option on every gate skips the remaining gates for users who have onboarded a project before.

## Sections

1. §Pre-flight — repo + plugin detection, no writes
2. §Flow — the nine sequential phases (Phase 0 pre-flight diagnostic + Phases 1–9 with writes)
3. §Phase Gates — gate definitions, escape hatch, format
4. §Phase 1 — `.gitignore` hygiene (canonical AI-assistants block)
5. §Phase 2 — `.ai-state/` skeleton
6. §Phase 3 — `.gitattributes` + merge driver registration
7. §Phase 4 — Git hooks (pre-commit + post-merge)
8. §Phase 5 — `.claude/settings.json` toggles
9. §Phase 6 — `CLAUDE.md` Praxion blocks (idempotent append)
10. §Phase 7 — Companion CLIs (advisory only)
11. §Phase 8 — Architecture Baseline (opt-in, default-yes — delegates to `systems-architect`)
12. §Phase 9 — Verification + handoff
13. §Agent Pipeline Block — canonical source of truth
14. §Compaction Guidance Block
15. §Behavioral Contract Block
16. §Idempotency Predicates — per-phase contracts

## §Pre-flight

Before any phase runs, gather facts. Pre-flight writes nothing — it produces a diagnostic report you print to chat so the user knows what you found.

1. **Git repo check.** `git rev-parse --git-dir`. If it fails, abort with: `This command must be run inside a git repository. Run 'git init' first if this is a new project.` Exit without writing.
2. **Project root.** `git rev-parse --show-toplevel`. All paths in subsequent phases are relative to this root.
3. **Plugin install scope.** Read `~/.claude/plugins/installed_plugins.json` (use `jq -r '.plugins["i-am@bit-agora"]'`). Three outcomes:
   - **User scope** — entry exists with `scope: "user"`. Capture `installPath` (used for hook resolution in §Phase 4).
   - **Project scope** — entry exists with `scope: "project"` and `projectPath` matching the current project root. Capture `installPath`.
   - **Not installed** — emit a warning: `The i-am plugin is not installed. Install it via 'claude plugin install i-am@bit-agora' or './install.sh code' from a Praxion checkout. The onboarding can still run, but git hooks (Phase 4) will be skipped because they need the plugin's scripts/.` Set a flag to skip Phase 4.
4. **Stack detection.** Probe for stack signals in the project root and capture which apply (used in §Phase 7 to recommend tooling):
   - Python: `pyproject.toml` OR `setup.py` OR `setup.cfg` OR `requirements.txt`
   - JavaScript/TypeScript: `package.json`
   - Rust: `Cargo.toml`
   - Go: `go.mod`
5. **Prior-onboarding signals.** Check for any of:
   - `## Agent Pipeline` heading in `CLAUDE.md` (re-onboard scenario — Phase 6 will skip the append)
   - `.ai-state/` directory exists with non-empty contents (re-onboard or pipeline-active)
   - `.git/hooks/post-merge` symlink pointing at `*/i-am/*/scripts/git-post-merge-hook.sh` (Phase 4 already done)
6. **Greenfield-shape check.** Detect whether the user has accidentally invoked `/onboard-project` on a freshly-scaffolded greenfield project that should run `/new-project` instead. The greenfield signature: `.git/` exists, `.gitignore` contains the AI-assistants header, `.claude/` is empty, AND there is no `src/`, `pyproject.toml`, `package.json`, `Cargo.toml`, or `go.mod` (no source code yet). If all conditions hold, abort with: `This directory looks like a freshly-scaffolded greenfield project (.git/ + AI-assistants .gitignore + empty .claude/ + no source tree). Run /new-project instead — it scaffolds the codebase via the agent pipeline AND applies the existing-project onboarding surfaces at end. /onboard-project is for projects that already have code.` Exit without writing.
7. **Print the pre-flight report** to chat. Format:
   ```
   Pre-flight report:
     project root:        <path>
     plugin scope:        user | project | not installed (flag: skip-phase-4)
     plugin install path: <path or n/a>
     stacks detected:     [python, javascript, ...] | none
     prior onboarding:    yes (CLAUDE.md heading found) | no | partial (<list>)
   ```

After printing, proceed to §Flow. The first phase gate (Gate 1) is the entry gate — it carries both the orientation overview and the Phase 1 specifics, so the user is not double-prompted before the first write.

## §Flow

Execute these phases in order. Each phase honors §Idempotency Predicates — re-running on an already-onboarded project must be a no-op for that phase.

| Phase | Action | Predicate (skip if already done) |
|-------|--------|----------------------------------|
| 1 | Append AI-assistants block to `.gitignore` | Block detected by `# AI assistants` header line |
| 2 | Create `.ai-state/` skeleton (4 files) | Each file's existence checked individually |
| 3 | Append `.gitattributes` entries + register merge drivers via `git config` | Entries detected by exact-line match; drivers detected via `git config --get` |
| 4 | Symlink pre-commit + post-merge hooks (skip if `skip-phase-4` flag) | Symlinks detected via `readlink` resolving to the plugin path |
| 5 | Write `.claude/settings.json` with chosen `PRAXION_DISABLE_*` flags | Existing keys preserved unless user explicitly chooses to override |
| 6 | Append Agent Pipeline + Compaction Guidance + Behavioral Contract blocks to `CLAUDE.md` | `## Agent Pipeline` heading detection per block |
| 7 | Print companion-CLI install commands (advisory) | None — purely informational |
| 8 | Architecture baseline — delegate to `systems-architect` in baseline mode → `.ai-state/ARCHITECTURE.md` + `docs/architecture.md` (+ optional ADR draft) | `test -e .ai-state/ARCHITECTURE.md` OR `test -e docs/architecture.md` (skip if either exists) OR user picks "Skip" at Gate 8 |
| 9 | Print summary + stage modified files (no commit) | None — terminal phase |

## §Phase Gates

The default §Flow runs end-to-end without pause. To let users *learn* the model rather than just *watch* it, fire an `AskUserQuestion` gate before each phase from 1–7. Phase 0 (pre-flight) and Phase 8 (terminal handoff) need no gate.

**Escape hatch (one-way).** Each gate offers `Continue` and `Run all rest`. If the user picks `Run all rest`, set an internal `no-more-gates` flag and skip every subsequent gate. The flag is one-way and persists until command exit.

**Fallback.** If `AskUserQuestion` is unavailable (tool error, headless invocation), print the headline as a chat message and proceed without blocking. Do not fail the onboarding because a gate cannot fire.

**Format.** Every gate uses these `AskUserQuestion` parameters:

- `header` — `"Next?"`
- `question` — the headline from the table below (verbatim, forward-looking)
- `multiSelect` — `false` for all gates (Gate 5 is a special multi-select on `PRAXION_DISABLE_*` toggles; Gate 8 is a special three-option pick — see below)
- `options`:
  - Two-option `Continue` / `Run all rest` — gates 1, 2, 3, 4, 6, 7
  - Multi-select toggles — Gate 5 (see §Phase 5)
  - Three-option `Run baseline now` (default) / `Skip` / `Run all rest` — Gate 8 (see §Phase 8)

**Gate map.** Gate 1 doubles as the entry gate — its headline carries both the high-level orientation and the Phase 1 specifics, so the user is not double-prompted before the first phase. Gates 2–8 fire one-per-phase as expected.

| Gate | Fires before phase | Headline |
|------|-------------------|----------|
| 1 | 1 (entry + phase 1) | `I'll walk you through 9 phases that turn this project into a Praxion-aware repo: gitignore hygiene, .ai-state/ skeleton, merge drivers, git hooks, .claude/settings.json toggles, CLAUDE.md blocks, optional CLI tools, an opt-in architecture baseline, and a verification handoff. First up — Phase 1 of 9: I append a Praxion AI-assistants block to your .gitignore. Without these entries, advisory locks, memory backups, per-machine settings, and worktrees can leak into commits. Idempotent — re-runs are no-ops. Continue?` |
| 2 | 2 | `Phase 2 of 9: I create the .ai-state/ skeleton — decisions/drafts/, DECISIONS_INDEX.md, TECH_DEBT_LEDGER.md, calibration_log.md. Each is created only if missing; existing files are never overwritten. Continue?` |
| 3 | 3 | `Phase 3 of 9: I add merge-driver entries to .gitattributes and run 'git config' to register Python-based semantic merge drivers for .ai-state/memory.json and .ai-state/observations.jsonl. Without these, concurrent edits get corrupted by line-based merge. Continue?` |
| 4 | 4 | `Phase 4 of 9: I install two git hooks — pre-commit (id-citation discipline) and post-merge (ADR finalize + tech-debt dedupe + squash-safety check). Without the post-merge hook, draft ADRs never promote to stable dec-NNN. Symlinks resolve to the plugin scripts so updates flow automatically. Continue?` |
| 5 | 5 | (Multi-select on PRAXION_DISABLE_* toggles — see §Phase 5 for option text) |
| 6 | 6 | `Phase 6 of 9: I append three blocks to CLAUDE.md — the Agent Pipeline (how to use Praxion's subagents), Compaction Guidance (what to preserve when the conversation compacts), and Behavioral Contract reminder. Each block is idempotent via heading detection. Continue?` |
| 7 | 7 | `Phase 7 of 9: I check whether chub (external API docs), scc (SLOC counter), and uv (Python tooling) are installed. I won't install anything — I'll print one-line install commands you can run later if useful. Continue?` |
| 8 | 8 | (Three-option pick — see §Phase 8 for the exact AskUserQuestion form. Default is `Run baseline now`. Headline: `Phase 8 of 9: Architecture baseline. I delegate to systems-architect in baseline mode to read your codebase and produce .ai-state/ARCHITECTURE.md (architect-facing, design-target) + docs/architecture.md (developer-facing, navigation guide). These docs become the architectural anchor for every future feature pipeline. Takes ~5–15 minutes for a medium project. Skip if you'd rather wait for your first feature pipeline to produce them. Pick:`) |

## §Phase 1 — `.gitignore` hygiene

**Predicate.** Detect the block via `grep -q '^# AI assistants$' .gitignore`. If present, skip the phase entirely.

**Action.** If `.gitignore` does not exist, create it with the block. Otherwise append the block as a trailing section:

```gitignore
# AI assistants
.ai-work/
.ai-state/*.lock
.ai-state/**/*.lock
.ai-state/*.backup.json
.ai-state/*.pre-forget.json
.claude/settings.local.json
.claude/worktrees/
.env
.env.*
.env.local
```

**Why each line:**

| Entry | What it excludes | Why |
|-------|------------------|-----|
| `.ai-work/` | Ephemeral pipeline scratch (per-task slug) | Deleted at pipeline end; never useful in history |
| `.ai-state/*.lock`, `.ai-state/**/*.lock` | Advisory file locks taken by `finalize_adrs.py`, merge drivers | Runtime-only — committing them masks real lock behavior |
| `.ai-state/*.backup.json` | Snapshots taken before destructive memory ops | Local recovery only |
| `.ai-state/*.pre-forget.json` | Pre-`forget()` memory snapshots | Local recovery only |
| `.claude/settings.local.json` | Per-machine Claude settings | Machine-specific |
| `.claude/worktrees/` | Worktree home for `EnterWorktree` | Each branch's own checkout |
| `.env`, `.env.*`, `.env.local` | Secrets | Never commit secrets |

**Separately:** if `.gitignore` *excludes* `.ai-state/` (line `.ai-state/` or `.ai-state` with no glob suffix), warn:

> `.ai-state/` is excluded but should be committed — it holds persistent project intelligence (ADRs, idea ledger, sentinel reports, tech-debt ledger). Remove the exclusion?

If the user agrees, remove that line. If they decline, proceed without changing it but note the choice in the Phase 8 summary.

## §Phase 2 — `.ai-state/` skeleton

**Canonical schemas.** The full TECH_DEBT_LEDGER schema (15 fields, producer/consumer contracts, dedup semantics), DECISIONS_INDEX format, and calibration_log format are defined in `rules/swe/agent-intermediate-documents.md`. The skeletons below are header-only seeds — agents populate rows over time per the canonical contracts. ADR fragment naming and lifecycle live in `rules/swe/adr-conventions.md`.

**Predicate.** Each file's existence is checked individually. Existing files are never overwritten.

**Action.** Create:

- `.ai-state/decisions/drafts/` (directory only — no `.gitkeep`; the directory is committed when its first ADR draft lands)
- `.ai-state/decisions/DECISIONS_INDEX.md` (header-only):
  ```markdown
  # Decisions Index

  Auto-generated by `scripts/finalize_adrs.py` at merge-to-main. Drafts under `decisions/drafts/` are excluded from this index by construction.

  | id | title | status | category | date | summary |
  |----|-------|--------|----------|------|---------|
  ```
- `.ai-state/TECH_DEBT_LEDGER.md` (header + empty schema row):
  ```markdown
  # Tech Debt Ledger

  Living, append-only ledger of grounded debt findings. Producers (verifier, sentinel) append rows; consumers update `status` in place; rows are never deleted. Schema and producer/consumer contracts live in the agent intermediate documents rule.

  | id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |
  |----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|------------|--------|-------------|-------|-----------|
  ```
- `.ai-state/calibration_log.md` (header):
  ```markdown
  # Calibration Log

  Append-only log of tier selections (Direct / Lightweight / Standard / Full / Spike). Used by `sentinel` to analyze tier-selection accuracy over time.

  | timestamp | task | signals | recommended-tier | actual-tier | source | retrospective |
  |-----------|------|---------|------------------|-------------|--------|---------------|
  ```

Do NOT create `.ai-state/memory.json` or `.ai-state/observations.jsonl` — those are written on first use by the memory MCP and the observability hook respectively. Pre-creating them confuses semantic merge drivers.

## §Phase 3 — `.gitattributes` + merge driver registration

**Why this phase exists.** Line-based merge corrupts structured data. `.ai-state/memory.json` (curated knowledge) and `.ai-state/observations.jsonl` (event log) are merge-conflict targets when concurrent edits land — the semantic merge drivers reconcile them at the JSON / JSONL level instead. The full `.ai-state/` safety contract at PR time, including merge policy and the squash-merge ban for `.ai-state/`-touching branches, lives in `rules/swe/vcs/pr-conventions.md`.

**Predicate.** Detect entries via exact-line `grep -qF '.ai-state/memory.json merge=memory-json' .gitattributes` and the analogous line for observations. Detect driver registration via `git config --get merge.memory-json.driver` and `git config --get merge.observations-jsonl.driver`.

**Action.**

1. **Append to `.gitattributes`** (create the file if missing):
   ```gitattributes
   # Praxion semantic merge drivers — see rules/swe/agent-intermediate-documents.md
   .ai-state/memory.json merge=memory-json
   .ai-state/observations.jsonl merge=observations-jsonl
   ```

2. **Register the drivers in this repo's `git config`**:
   ```bash
   git config merge.memory-json.driver "python3 ${PLUGIN_INSTALL_PATH}/scripts/merge_driver_memory.py %O %A %B"
   git config merge.observations-jsonl.driver "python3 ${PLUGIN_INSTALL_PATH}/scripts/merge_driver_observations.py %O %A %B"
   ```
   `${PLUGIN_INSTALL_PATH}` is the value captured in §Pre-flight. If the plugin was not detected (skip-phase-4 flag is set), still write `.gitattributes` but emit a warning: `Merge drivers not registered — run 'git config merge.memory-json.driver "..."' manually after installing the plugin. Without this, .ai-state/memory.json will be corrupted by line-based merge on first concurrent edit.`

3. **Conflict check.** If `git config --get merge.memory-json.driver` already returns a value that does NOT contain `i-am` and is NOT empty, refuse to overwrite. Print: `merge.memory-json.driver is already set to '<value>' — refusing to overwrite. Remove the existing driver manually if you want Praxion's, or leave as-is.` Same logic for observations.

## §Phase 4 — Git hooks

**Why these hooks.** The pre-commit hook enforces id-citation discipline — committed code must not reference ephemeral pipeline ids (`REQ-NN`, `AC-NN`, `Step N`, draft ADR hashes). Rationale, exempt paths, and escape hatch live in `rules/swe/id-citation-discipline.md`. The post-merge hook chains four operations that keep `.ai-state/` consistent across local merges: `reconcile_ai_state.py` (memory.json + observations.jsonl reconciliation), `finalize_adrs.py` (promote draft ADRs to stable `dec-NNN`), `finalize_tech_debt_ledger.py` (dedupe rows by `dedup_key`), `check_squash_safety.py` (warn if squash erased `.ai-state/`). Without the post-merge hook, draft ADRs never promote.

**Skip condition.** If §Pre-flight set the `skip-phase-4` flag (plugin not installed), skip this phase entirely and emit: `Skipping Phase 4 — install the plugin and re-run /onboard-project to install hooks.`

**Predicate.** Detect existing symlinks via `readlink .git/hooks/<name>` and check whether the target contains `/i-am/` and ends in `git-pre-commit-hook.sh` or `git-post-merge-hook.sh` respectively. If either is already a Praxion symlink, skip that hook.

**Action.**

1. **Pre-commit hook** — symlink `.git/hooks/pre-commit` to a *user-project-tailored* hook script. Praxion ships `scripts/git-pre-commit-hook.sh` which runs the shipped-artifact-isolation check (Praxion-author-specific). For user projects, write a tailored hook directly into `.git/hooks/pre-commit` (executable) that runs only `check_id_citation_discipline.py`:
   ```bash
   #!/usr/bin/env bash
   # Praxion id-citation-discipline check (installed by /onboard-project).
   # Blocks commits that reference ephemeral pipeline ids (REQ-*, AC-*, Step N)
   # in committed source code. Rationale: rules/swe/id-citation-discipline.md.
   set -eo pipefail
   REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
   [ -z "$REPO_ROOT" ] && exit 0
   PLUGIN_ROOT="$(jq -r '.plugins["i-am@bit-agora"][0].installPath' "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null)"
   CHECK="${PLUGIN_ROOT}/scripts/check_id_citation_discipline.py"
   [ ! -f "$CHECK" ] && exit 0
   STAGED="$(git diff --cached --name-only --diff-filter=ACMR || true)"
   [ -z "$STAGED" ] && exit 0
   # shellcheck disable=SC2086
   python3 "$CHECK" --repo-root "$REPO_ROOT" --files $STAGED
   ```
   `chmod +x .git/hooks/pre-commit` after writing. Resolving the plugin path at hook-run time means plugin upgrades (different install paths) flow automatically.

   **If `.git/hooks/pre-commit` already exists and is NOT a Praxion hook**, back it up to `.git/hooks/pre-commit.pre-praxion` and warn the user. Do not silently overwrite a non-Praxion hook.

2. **Post-merge hook** — symlink `.git/hooks/post-merge` to the plugin's universally-useful post-merge script:
   ```bash
   ln -sf "${PLUGIN_INSTALL_PATH}/scripts/git-post-merge-hook.sh" .git/hooks/post-merge
   ```
   The script chains `reconcile_ai_state.py` → `finalize_adrs.py` → `finalize_tech_debt_ledger.py` → `check_squash_safety.py`. All four are universally useful: ADR draft promotion, tech-debt row dedupe, post-merge memory/observations reconciliation, squash-erasure warning. Same conflict-handling rule as pre-commit: if a non-Praxion hook is in place, back it up to `.git/hooks/post-merge.pre-praxion`.

   `chmod +x` is implicit on a symlink target that is already executable.

## §Phase 5 — `.claude/settings.json` toggles

The Praxion plugin auto-fires hooks on `SessionStart`, `Stop`, `SubagentStart`, `SubagentStop`, `PreToolUse`, `PostToolUse`, `PreCompact`. Some are heavyweight: memory MCP injection ships project context to the model, observability ships events to a localhost Phoenix instance, the memory gate blocks `Stop` if no `remember()` calls fired during a substantive session. Users opt out via four `PRAXION_DISABLE_*` env vars in `.claude/settings.json`.

**Predicate.** Read `.claude/settings.json` if it exists. If the four keys are all already set (any value), skip the phase but report current values in Phase 8. If the file exists but is missing some keys, merge in the missing ones using the user's choices below; never overwrite a key the user has already set.

**Gate 5 — multi-select toggle picker.** Use `AskUserQuestion` with `multiSelect: true`, header `"Praxion features"`, question `"Which features should be ENABLED in this project? Each adds runtime overhead — leave a feature unchecked to disable it. Defaults below match Praxion's own dogfooding choice (everything off for safety; opt in deliberately)."`, and these four options:

| Option label | Description |
|--------------|-------------|
| `Memory MCP injection (SessionStart)` | Auto-load project context into every session via `inject_memory.py`. Enables cross-session memory but the injected context costs ~3–5k tokens at session start. |
| `Memory gate (Stop hook)` | Block session completion if substantive work happened with zero `remember()` calls. Forces learning capture; can feel intrusive on quick fixes. |
| `Memory MCP server itself` | The actual `mcp__plugin_i-am_memory__*` tool surface. Disable to skip persistent memory entirely (no `.ai-state/memory.json` writes). |
| `Observability events` | Ship Claude Code events to a localhost Phoenix instance via `send_event.py`. Useful for trace inspection; requires Phoenix to be running otherwise events are silently dropped. |

**Mapping** unchecked options to env vars (Praxion uses negative `DISABLE` semantics — `"1"` disables, `"0"` enables):

| Unchecked option | Env var written | Value |
|------------------|-----------------|-------|
| Memory MCP injection | `PRAXION_DISABLE_MEMORY_INJECTION` | `"1"` |
| Memory gate | `PRAXION_DISABLE_MEMORY_GATE` | `"1"` |
| Memory MCP server | `PRAXION_DISABLE_MEMORY_MCP` | `"1"` |
| Observability | `PRAXION_DISABLE_OBSERVABILITY` | `"1"` |

Checked options write the corresponding `PRAXION_DISABLE_*` to `"0"`.

**Action.** Write `.claude/settings.json` (creating `.claude/` if needed):

```json
{
  "env": {
    "PRAXION_DISABLE_MEMORY_INJECTION": "<value>",
    "PRAXION_DISABLE_MEMORY_GATE": "<value>",
    "PRAXION_DISABLE_MEMORY_MCP": "<value>",
    "PRAXION_DISABLE_OBSERVABILITY": "<value>"
  }
}
```

If `.claude/settings.json` already exists with other keys (e.g., `permissions`, `model`), merge `env` non-destructively — preserve all existing top-level keys and pre-existing `env.*` entries.

## §Phase 6 — `CLAUDE.md` Praxion blocks

**Predicate.** Three independent heading checks:

- `## Agent Pipeline` heading present → skip the Agent Pipeline append
- `## Compaction Guidance` heading present → skip the Compaction Guidance append
- `## Behavioral Contract` heading present → skip the Behavioral Contract append

**Action.**

1. **If `CLAUDE.md` does NOT exist**, do not create it directly. Print: `No CLAUDE.md found at the project root. Run /init to generate one from the codebase, then re-run /onboard-project to append the Praxion blocks.` Skip the rest of Phase 6.

2. **If `CLAUDE.md` exists**, append (in this order, each guarded by its predicate):
   - The §Agent Pipeline Block verbatim
   - The §Compaction Guidance Block verbatim
   - The §Behavioral Contract Block verbatim

   Append at the end of the file with one blank line separating from preceding content.

## §Phase 7 — Companion CLIs (advisory)

**Predicate.** None — purely informational, idempotent by nature.

**Action.** For each of `chub`, `scc`, `uv`, run `command -v <name>`. For each MISSING tool that is RELEVANT given the stack detected in §Pre-flight, print one-line install guidance. Do NOT run the install — print the command and let the user execute it.

| Tool | Relevant when | Why useful | Install (print, do not run) |
|------|---------------|------------|----------------------------|
| `chub` | Always | Curated docs for 600+ external libraries; used by the `external-api-docs` skill to avoid hallucinated SDK signatures | `npm install -g @aisuite/chub` |
| `scc` | Any stack | Fast SLOC counter used by `/project-metrics`; without it, metrics fall back to a stdlib counter that misses language detail | `brew install scc` (macOS) or `go install github.com/boyter/scc/v3@latest` |
| `uv` | Python detected | Fast Python package manager; required for `pytest -q` in Praxion's metrics flow | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Do not recommend tools the user already has, and do not recommend `uv` if no Python signal was detected in §Pre-flight.

## §Phase 8 — Architecture Baseline (opt-in, default-yes)

**Templates.** The architect doc uses `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` (architect-facing design target — full section ownership tags). The developer doc uses `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` (filtered to Built components only — every name and path code-verified). The agent's full standing contract is in `agents/systems-architect.md`; this phase invokes a *baseline-audit subset* of that contract, with the directives below as the diff.

**Predicate.** Skip the phase entirely if either of these holds:

- `test -e .ai-state/ARCHITECTURE.md` (architect-facing doc already present — likely a re-run on a fully-onboarded project, or a greenfield-followed-by-onboard sequence where `/new-project`'s seed pipeline already produced it)
- `test -e docs/architecture.md` (developer-facing doc already present — same provenance)

When skipped via predicate, emit: `Phase 8: skipped (architecture docs already exist — produced by the seed pipeline or a prior /onboard-project run)`. Skipping is idempotent and does not block Phase 9.

**Why this phase exists.** Praxion's `sentinel` coherence audits, future feature pipelines (`systems-architect` updates these docs incrementally), and Memory MCP context recall all benefit from an architectural baseline. Without it, the existing-project onboarding is half-complete from the agent ecosystem's perspective — every future agent runs context-poor on the codebase shape. Greenfield (`/new-project`) gets this for free via the seed pipeline; existing-project needs the same treatment, which is what this phase delivers.

**Gate 8 — three-option AskUserQuestion.** Use `AskUserQuestion` with `header: "Next?"`, `multiSelect: false`, the headline from the gate map, and these three options:

| Option label | Description |
|--------------|-------------|
| `Run baseline now (recommended)` | Default. Delegate to `systems-architect` in baseline-audit mode. ~5–15 minutes for a medium project (under 500 source files); longer for large repos. Produces real, code-verified content — both architecture docs |
| `Skip — first feature pipeline will produce these` | Skip Phase 8 entirely. Future Standard-tier feature pipelines will create the docs when `systems-architect` runs for the first time. Acceptable if you want lean onboarding and are not running `/sentinel` immediately afterward |
| `Run all rest` | Skip remaining gates, default the architecture-baseline choice to `Run baseline now`, and run autonomously through Phase 9. Honors users who have onboarded a project before and trust the recommended defaults |

**Action when "Run baseline now" is chosen.**

Delegate to `systems-architect` via the `Task` tool. The delegation prompt MUST include all of these directives:

1. **Mode.** `Baseline-audit mode — no specific feature scope. Read the existing codebase and produce architecture docs that describe the as-built state, not a future design target.`
2. **Inputs.** Point the agent at the project root. Tell it which language/framework signals were detected in §Pre-flight (Python, JavaScript, Rust, Go, etc.) so it scopes the codebase scan correctly.
3. **Outputs (required).**
   - `.ai-state/ARCHITECTURE.md` — architect-facing design-target document. Use the `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` template. Sections: System Overview, System Context (L0 mermaid), Components (L1 mermaid + table), Data Flow, Quality Attributes (testing, observability, deployment current state), Open Questions / Known Gaps. Mark unverified-by-code claims with section ownership tags so future updates can supersede cleanly.
   - `docs/architecture.md` — developer-facing navigation guide. Use the `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` template. Filter `.ai-state/ARCHITECTURE.md` to the **Built** components only — every component name and file path must resolve on disk (verify with `Glob` or `ls`). Skip components that exist only in the design-target document.
4. **Outputs (optional, agent's call).**
   - One ADR draft under `.ai-state/decisions/drafts/` if the baseline reading surfaces a load-bearing architectural invariant worth preserving (e.g., a one-way module dependency, a layer boundary, a data-flow constraint). The ADR is *only* warranted when the invariant is non-obvious from the code; do not write a ceremonial "architecture is now baselined" ADR.
5. **Anti-instructions.**
   - Do NOT produce `SYSTEMS_PLAN.md` — there is no feature in scope for a baseline audit, and a SYSTEMS_PLAN without a feature is anti-pattern.
   - Do NOT invent components that don't exist on disk. Every Mermaid node and table row must be code-verified.
   - Do NOT exceed L1 detail in mermaid diagrams (≤10 nodes per `rules/writing/diagram-conventions.md`). L2 internals are deferred to feature-pipeline updates.
   - Do NOT modify any source code, tests, or non-architecture documentation.

The architect operates in a fresh context window (`Task` tool spawn) and reports completion when both docs are written. The main agent reads the produced docs at completion to confirm shape, then proceeds to Phase 9.

**If the architect fails or times out**, emit a clear warning: `Phase 8 skipped — systems-architect did not complete the baseline audit. Architecture docs were not produced. Re-run /onboard-project to retry, or run a feature pipeline whose first stage will produce them.` Proceed to Phase 9.

## §Phase 9 — Verification + handoff

**Predicate.** None — terminal phase.

**Action.**

1. **Print the change summary** — group by phase, list every file modified and every `git config` setting written. Use this format:
   ```
   Onboarding complete. Changes:
     Phase 1: .gitignore (appended 10 lines, AI-assistants block)
     Phase 2: .ai-state/ skeleton (4 new entries)
     Phase 3: .gitattributes (appended 2 lines), git config (2 merge drivers registered)
     Phase 4: .git/hooks/pre-commit (new), .git/hooks/post-merge (symlink)
     Phase 5: .claude/settings.json (4 PRAXION_DISABLE_* env vars)
     Phase 6: CLAUDE.md (appended Agent Pipeline + Compaction + Behavioral Contract blocks)
     Phase 7: companion CLIs — chub missing (install: ...), scc missing (install: ...)
     Phase 8: architecture baseline produced — .ai-state/ARCHITECTURE.md + docs/architecture.md (+ N ADR draft(s))
   ```
   For each skipped phase (idempotency hit OR user opt-out), print `Phase N: skipped (<reason>)` instead.

2. **Print verification next-steps** verbatim:
   ```
   Verify the onboarding:
     1. Run /sentinel for an ecosystem health baseline (writes .ai-state/SENTINEL_REPORT_<timestamp>.md).
     2. Run 'git status' to review staged work — every file this command modified is staged for review.
     3. Run /co to commit (the git-conventions rule will write a precise commit message), or unstage and review individually.

   Resources:
     - docs/existing-project-onboarding.md (companion guide to this command — open it in the Praxion repo for the full walkthrough)
     - rules/swe/swe-agent-coordination-protocol.md (how the agent pipeline works)
   ```

3. **Stage modified files**: run `git add` with the explicit list of files this command touched (built up through phases 1–6). Do NOT run `git add -A`. Do NOT commit. The user reviews staging and decides.

## §Agent Pipeline Block

This is the canonical source of truth. The identical block lives in `commands/new-project.md` § Agent Pipeline Block — if you change one, mirror the change to the other so both produce byte-identical `CLAUDE.md` sections.

```markdown
## Agent Pipeline

Follow the **Understand, Plan, Verify** methodology. For multi-step work (Standard/Full tier), delegate to specialized agents in pipeline order. Each pipeline operates in an ephemeral `.ai-work/<task-slug>/` directory (deleted after use); permanent artifacts go to `.ai-state/` (committed to git).

1. **researcher** → `.ai-work/<slug>/RESEARCH_FINDINGS.md` — codebase exploration, external docs
2. **systems-architect** → `.ai-work/<slug>/SYSTEMS_PLAN.md` + ADR drafts under `.ai-state/decisions/drafts/` (promoted to stable `<NNN>-<slug>.md` at merge-to-main by the post-merge hook) + `.ai-state/ARCHITECTURE.md` (architect-facing) + `docs/architecture.md` (developer-facing)
3. **implementation-planner** → `.ai-work/<slug>/IMPLEMENTATION_PLAN.md` + `WIP.md` — step decomposition
4. **implementer** + **test-engineer** (concurrent, on disjoint file sets) → code + tests — execute steps from the plan
5. **verifier** → `.ai-work/<slug>/VERIFICATION_REPORT.md` — post-implementation review

**Independent audits.** The `sentinel` agent runs outside the pipeline and writes timestamped `.ai-state/SENTINEL_REPORT_<timestamp>.md` plus an append-only `.ai-state/SENTINEL_LOG.md`. Trigger it for ecosystem health baselines (before first ideation, after major refactors).

**From PoC to production.** The feature pipeline is one milestone of many. The full journey: baseline audit (`/sentinel`) → CI/CD setup (`cicd-engineer` agent) → deployment (`deployment` skill) → first release (`/release`) → ongoing decisions captured as ADRs in `.ai-state/decisions/` → cross-session memory in `.ai-state/memory.json` (when memory MCP is enabled).

Always include expected deliverables when delegating to an agent. The agent coordination protocol rule has full delegation checklists.
```

The block is **self-contained** — no cross-references to files that exist only in the Praxion repo. The previous version pointed at `docs/getting-started.md#journey-poc-to-production`, which dangled in every onboarded project.

## §Compaction Guidance Block

```markdown
## Compaction Guidance

When this conversation compacts, always preserve: the active pipeline stage and task slug, the current WIP step number and status, acceptance criteria from the systems plan, and the list of files modified in the current step. The Praxion `PreCompact` hook snapshots in-flight pipeline documents to `.ai-work/<slug>/PIPELINE_STATE.md` — re-read that file after compaction to restore orientation.
```

## §Behavioral Contract Block

```markdown
## Behavioral Contract

Four non-negotiable behaviors for any agent (including Claude itself) writing, planning, or reviewing code in this project:

- **Surface Assumptions** — list assumptions before acting; ask when ambiguity could produce the wrong artifact.
- **Register Objection** — when a request violates scope, structure, or evidence, state the conflict with a reason before complying or declining. Silent agreement is a contract violation.
- **Stay Surgical** — touch only what the change requires; if scope grew, stop and re-scope instead of silently expanding.
- **Simplicity First** — prefer the smallest solution that meets the behavior; every added line, file, or dependency must earn its place.

Self-test: did I state assumptions, flag conflicts with reasons, stay inside declared scope, and choose the simplest path?
```

## §Idempotency Predicates — per-phase contracts

| Phase | Predicate (skip if true) |
|-------|--------------------------|
| 1 | `grep -q '^# AI assistants$' .gitignore` |
| 2 | Per-file: `test -e .ai-state/<file>` for each of the four targets — skip files individually |
| 3 | `grep -qF '.ai-state/memory.json merge=memory-json' .gitattributes` AND `git config --get merge.memory-json.driver` returns a value containing `i-am` AND same for `observations-jsonl` |
| 4 | `readlink .git/hooks/pre-commit` resolves to a Praxion-shipped file (or the file is a script containing `check_id_citation_discipline`) AND `readlink .git/hooks/post-merge` resolves to a path containing `/i-am/` |
| 5 | All four `PRAXION_DISABLE_*` keys present under `.env` in `.claude/settings.json` (any value) |
| 6 | `grep -q '^## Agent Pipeline$' CLAUDE.md` (per block — checked individually for the three blocks) |
| 7 | None — phase 7 is advisory and always runs |
| 8 | `test -e .ai-state/ARCHITECTURE.md` OR `test -e docs/architecture.md` (skip phase if either doc exists — covers re-runs and greenfield-followed-by-onboard); also skipped if the user picks `Skip` at Gate 8 |
| 9 | None — terminal phase always runs |

**Re-running the command** on an already-onboarded project should print mostly `skipped (already onboarded)` lines in Phase 9's summary. The only writes on a clean re-run come from Phase 7 (which writes nothing — only prints) and Phase 9 (which only stages changed files). Phase 8 is naturally idempotent — once `.ai-state/ARCHITECTURE.md` exists, any subsequent re-run skips. Future *updates* to architecture docs come from feature pipelines (`systems-architect` updates them in Phase 4 of the agent pipeline), not from re-running `/onboard-project`.

**Test for idempotency**: run `/onboard-project`, accept all gates, then re-run `/onboard-project`. The second run should produce zero `git diff` output and zero new `git config` entries. If either runs, the predicate for that phase has a bug.
