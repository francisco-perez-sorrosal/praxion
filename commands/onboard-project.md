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
7. §Phase 4 — Git hooks (pre-commit + post-merge + post-commit + post-checkout)
8. §Phase 5 — `.claude/settings.json` toggles
9. §Phase 5b — Hackathon mode gate: write six artifacts when enabled (opt-in, default-skip)
10. §Phase 6 — `CLAUDE.md` Praxion blocks (idempotent append)
11. §Phase 7 — Companion CLIs (advisory only)
12. §Phase 8 — Architecture Baseline (opt-in, default-yes — delegates to `systems-architect`)
13. §Phase 8b — AaC Tier Install (opt-in, default-skip — fence seed, fitness scaffold, hook block, workflow, diagrams)
14. §Phase 8c — ML/AI Training Scaffold (opt-in, default-skip; default-yes when ML signals detected)
15. §Phase 8d — Obsidian integration (opt-in, default-yes)
16. §Phase 9 — Verification + handoff
17. §Agent Pipeline Block — canonical source of truth
18. §Compaction Guidance Block
19. §Behavioral Contract Block
20. §Praxion Process Block
21. §Hackathon Mode Block — installed only when Phase 5b enables hackathon mode
22. §Project Essentials Block
23. §Obsidian Integration Block — installed only when Phase 8d runs
24. §Idempotency Predicates — per-phase contracts

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
4b. **ML signal detection.** Probe for ML/AI training signals and set an `ml_signals_detected` flag (used to set Gate 8c's default and skip Phase 8c when absent). Signals:
   - `test -f train.py` OR `test -f prepare.py` → Python training entry point detected
   - `grep -qE 'torch|jax|tensorflow' pyproject.toml requirements.txt setup.py Pipfile 2>/dev/null` → ML framework dependency declared
   - `test -f program.md` → project-local ML meta-prompt present
   Set `ml_signals_detected=true` if ANY of these succeeds; `ml_signals_detected=false` otherwise. Record in pre-flight report.
4c. **Diagram-toolchain probes.** Probe both diagram toolchain binaries and record their presence in the pre-flight report. Do NOT block onboarding on missing binaries.
   - `command -v likec4 >/dev/null 2>&1` → record `likec4` present/absent; if present, capture `likec4 --version`
   - `command -v d2 >/dev/null 2>&1` → record `d2` present/absent; if present, capture `d2 --version`
   If either is missing AND the project contains `**/diagrams/*.c4` files (or the user opts into Phase 8 architecture baseline), emit in the pre-flight report: "Install LikeC4 + D2 for architectural diagram regeneration — see `docs/architecture-diagrams.md`."
5. **Prior-onboarding signals.** Check for any of:
   - `## Agent Pipeline` heading in `CLAUDE.md` (re-onboard scenario — Phase 6 will skip the append)
   - `.ai-state/` directory exists with non-empty contents (re-onboard or pipeline-active)
   - `.git/hooks/post-merge`, `.git/hooks/post-commit`, and `.git/hooks/post-checkout` symlinks all pointing at `*/i-am/*/scripts/git-finalize-hook.sh` (Phase 4 already done)
6. **Plugin-source-repo guard.** Detect whether the user has invoked `/onboard-project` on a Claude Code plugin source repo (Praxion itself, or any plugin in development that ships skills/agents/rules/commands). The signal is the existence of `.claude-plugin/plugin.json` at the project root. Plugin source repos curate their own `CLAUDE.md`, `.ai-state/` skeleton, and onboarding artifacts as the **canonical** sources of those patterns; running `/onboard-project` against them would either duplicate content under conflicting headings (the repo's bespoke sections plus newly-injected blocks like `## Agent Pipeline` / `## Praxion Process`) or skew bespoke sections from their downstream-injected counterparts as edits land in only one of the two locations. If `test -e .claude-plugin/plugin.json` succeeds AND the environment variable `PRAXION_ALLOW_SELF_ONBOARD` is not set to `1`, abort with: `This project root contains .claude-plugin/plugin.json — it looks like a Claude Code plugin source repo, not a consumer project. Plugin source repos curate their own CLAUDE.md and .ai-state/ as canonical sources of the onboarding patterns; running /onboard-project would either duplicate content under conflicting headings or skew bespoke sections from their downstream-injected counterparts. If you genuinely want to onboard this repo (rare — only useful for divergent forks), set PRAXION_ALLOW_SELF_ONBOARD=1 in the environment and re-run.` Exit without writing. **Override:** if `PRAXION_ALLOW_SELF_ONBOARD=1` is set, print a single-line warning to chat (`Self-onboard override active — proceeding on plugin source repo at <project-root>.`) and continue.
7. **Greenfield-shape check.** Detect whether the user has accidentally invoked `/onboard-project` on a freshly-scaffolded greenfield project that should run `/new-project` instead. The greenfield signature: `.git/` exists, `.gitignore` contains the AI-assistants header, `.claude/` is empty, AND there is no `src/`, `pyproject.toml`, `package.json`, `Cargo.toml`, or `go.mod` (no source code yet). If all conditions hold, abort with: `This directory looks like a freshly-scaffolded greenfield project (.git/ + AI-assistants .gitignore + empty .claude/ + no source tree). Run /new-project instead — it scaffolds the codebase via the agent pipeline AND applies the existing-project onboarding surfaces at end. /onboard-project is for projects that already have code.` Exit without writing.
8. **Print the pre-flight report** to chat. Format:
   ```
   Pre-flight report:
     project root:        <path>
     plugin scope:        user | project | not installed (flag: skip-phase-4)
     plugin install path: <path or n/a>
     stacks detected:     [python, javascript, ...] | none
     ml signals:          detected (train.py|torch/jax/tensorflow|program.md) | none
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
| 4 | Symlink pre-commit + the three finalize hooks (post-merge, post-commit, post-checkout) (skip if `skip-phase-4` flag) | Symlinks detected via `readlink` resolving to the plugin path |
| 5 | Write `.claude/settings.json` with chosen `PRAXION_DISABLE_*` flags | Existing keys preserved unless user explicitly chooses to override |
| 5b | Hackathon mode gate: write six artifacts when enabled | `PRAXION_HACKATHON_MODE=1` present in `.claude/settings.json` env (skip if already set); or user picks `Skip — keep full ceremony` (default) at Gate 5b |
| 6 | Append Agent Pipeline + Compaction Guidance + Behavioral Contract + Praxion Process blocks to `CLAUDE.md` (+ `## Hackathon Mode` when Phase 5b enabled it) | `## Agent Pipeline` heading detection per block |
| 7 | Print companion-CLI install commands (advisory) | None — purely informational |
| 8 | Architecture baseline — delegate to `systems-architect` in baseline mode → `.ai-state/DESIGN.md` + `docs/architecture.md` (+ optional ADR draft) | `test -e .ai-state/DESIGN.md` OR `test -e docs/architecture.md` (skip if either exists) OR user picks "Skip" at Gate 8 |
| 8b | AaC tier install — fence seed, `fitness/` scaffold, golden-rule Block D, `architecture.yml` workflow, `docs/diagrams/` scaffold | User picks "Skip AaC" (default) at Gate 8b; or per-sub-step predicates (see §Phase 8b) |
| 8c | ML/AI training scaffold — experiment tracking config, checkpoint `.gitignore` block, GPU budget declaration, `program.md` template, mode callout | No ML signals detected (skip) OR user picks "Skip" at Gate 8c; per-sub-step predicates (see §Phase 8c) |
| 8d | Obsidian integration — `.gitignore` Obsidian block, verify `obsidian@obsidian-skills` plugin install, `CLAUDE.md` Obsidian Integration block, `settings.json` deny entries | User picks "Skip" at Gate 8d; per-sub-step predicates (see §Phase 8d) |
| 9 | Print summary + stage modified files (no commit) | None — terminal phase |

## §Phase Gates

The default §Flow runs end-to-end without pause. To let users *learn* the model rather than just *watch* it, fire an `AskUserQuestion` gate before each phase from 1–7. Phase 0 (pre-flight) and Phase 9 (terminal handoff) need no gate.

**Escape hatch (one-way).** Each gate offers `Continue` and `Run all rest`. If the user picks `Run all rest`, set an internal `no-more-gates` flag and skip every subsequent gate. The flag is one-way and persists until command exit.

**Fallback.** If `AskUserQuestion` is unavailable (tool error, headless invocation), print the headline as a chat message and proceed without blocking. Do not fail the onboarding because a gate cannot fire.

**Format.** Every gate uses these `AskUserQuestion` parameters:

- `header` — `"Next?"`
- `question` — the headline from the table below (verbatim, forward-looking)
- `multiSelect` — `false` for all gates (Gate 5 is a special multi-select on `PRAXION_DISABLE_*` toggles; Gate 8 is a special three-option pick — see below)
- `options`:
  - Two-option `Continue` / `Run all rest` — gates 1, 2, 3, 4, 6, 7
  - Multi-select toggles — Gate 5 (see §Phase 5)
  - Two-option `Enable hackathon mode` / `Skip — keep full ceremony` (default: Skip) — Gate 5b (see §Phase 5b); gate is suppressed (auto-default Skip) when `no-more-gates` flag is set; auto-default Enable when `--hackathon` was passed
  - Three-option `Run baseline now` (default) / `Skip` / `Run all rest` — Gate 8 (see §Phase 8)
  - Three-option `Skip AaC` (default) / `Install AaC tier` / `Run all rest` — Gate 8b (see §Phase 8b)
  - Three-option `Skip ML scaffold` (default for non-ML) / `Run ML scaffold` / `Run all rest` — Gate 8c (see §Phase 8c); default is `Run ML scaffold` when ML signals detected
  - Three-option `Install Obsidian integration (default)` / `Skip` / `Run all rest` — Gate 8d (see §Phase 8d)

**Gate map.** Gate 1 doubles as the entry gate — its headline carries both the high-level orientation and the Phase 1 specifics, so the user is not double-prompted before the first phase. Gates 2–8 fire one-per-phase as expected. Gate 5b fires between Phase 5 and Phase 6.

| Gate | Fires before phase | Headline |
|------|-------------------|----------|
| 1 | 1 (entry + phase 1) | `I'll walk you through 9 phases that turn this project into a Praxion-aware repo: gitignore hygiene, .ai-state/ skeleton, merge drivers, git hooks, .claude/settings.json toggles, CLAUDE.md blocks, optional CLI tools, an opt-in architecture baseline, and a verification handoff. First up — Phase 1 of 9: I append a Praxion AI-assistants block to your .gitignore. Without these entries, advisory locks, memory backups, per-machine settings, and worktrees can leak into commits. Idempotent — re-runs are no-ops. Continue?` |
| 2 | 2 | `Phase 2 of 9: I create the .ai-state/ skeleton — decisions/drafts/, DECISIONS_INDEX.md, TECH_DEBT_LEDGER.md, calibration_log.md, plus a static redirect stub at .ai-state/metrics_reports/index.html that points to praxion-dashboard for interactive charts (the METRICS_REPORT_*.md files in the same directory are available for offline reading). Each is created only if missing; existing files are never overwritten. Continue?` |
| 3 | 3 | `Phase 3 of 9: I add merge-driver entries to .gitattributes and run 'git config' to register Python-based semantic merge drivers for .ai-state/memory.json and .ai-state/observations.jsonl. Without these, concurrent edits get corrupted by line-based merge. Continue?` |
| 4 | 4 | `Phase 4 of 9: I install four git hooks — pre-commit (id-citation discipline) and three finalize hooks (post-merge, post-commit, post-checkout) all sharing one multiplexed dispatcher. The trio guarantees that draft ADRs landing on main via any path — ff merge, direct commit, rebase, fresh clone, branch reset — eventually promote to stable dec-NNN. Symlinks resolve to the plugin scripts so updates flow automatically. Continue?` |
| 5 | 5 | (Multi-select on PRAXION_DISABLE_* toggles — see §Phase 5 for option text) |
| 5b | 5b | (Two-option pick — `Enable hackathon mode` / `Skip — keep full ceremony` (default: Skip). Headline: `Phase 5b: Hackathon mode. I can install the six hackathon mode artifacts: set PRAXION_HACKATHON_MODE=1 in .claude/settings.json, append the ## Hackathon Mode block to CLAUDE.md, add the hackathon preset to .claude/praxion-rules.yaml, and create scripts/praxion-hackathon, .claude/hackathon-directive.md, and .claude/hackathon-settings.json. Hackathon mode replaces the 5-tier selector with a flexible-entry Hackathon Spine and relaxes test/SDD/ADR ceremony. All six installs are idempotent. Skip if you want the full Praxion ceremony. Pick:`) |
| 6 | 6 | `Phase 6 of 9: I append five blocks to CLAUDE.md — the Agent Pipeline (how to use Praxion's subagents), Compaction Guidance (what to preserve when the conversation compacts), Behavioral Contract reminder, Praxion Process (the tier-driven pipeline principle + rule-inheritance obligation), and Working in this project (your verification commands + frequent operations + how corrections become durable rules — I fill the project-specific bits from your config). Each block is idempotent via heading detection. (If Phase 5b enabled hackathon mode, the ## Hackathon Mode block was already appended.) Continue?` |
| 7 | 7 | `Phase 7 of 9: I check whether chub (external API docs), scc (SLOC counter), and uv (Python tooling) are installed. I won't install anything — I'll print one-line install commands you can run later if useful. Continue?` |
| 8 | 8 | (Three-option pick — see §Phase 8 for the exact AskUserQuestion form. Default is `Run baseline now`. Headline: `Phase 8 of 9: Architecture baseline. I delegate to systems-architect in baseline mode to read your codebase and produce .ai-state/DESIGN.md (architect-facing, design-target) + docs/architecture.md (developer-facing, navigation guide). These docs become the architectural anchor for every future feature pipeline. Takes ~5–15 minutes for a medium project. Skip if you'd rather wait for your first feature pipeline to produce them. Pick:`) |
| 8b | 8b | (Three-option pick — see §Phase 8b for the exact AskUserQuestion form. Default is `Skip AaC`. Headline: `Phase 8b: AaC tier install. I can install the Architecture-as-Code surfaces for this project: fence-region examples in your architecture docs, fitness/ scaffold for architectural fitness tests, a golden-rule pre-commit block, a .github/workflows/architecture.yml CI workflow, and a docs/diagrams/ directory stub. All five installs are idempotent — re-running is safe. The AaC convention requires the i-am plugin to be installed for enforcement to fire. Sentinel-only surfaces (traceability convention, sentinel AC dimension) need no per-project install. Pick:`) |
| 8c | 8c | (Three-option pick — see §Phase 8c for the exact AskUserQuestion form. Default is `Skip ML scaffold` for non-ML projects; default is `Run ML scaffold` when ML signals are detected. Headline: `Phase 8c: ML/AI training scaffold. I detected signals that this is an ML/AI training project. I can scaffold: experiment tracking config (.ai-state/experiments/), checkpoint directory entries in .gitignore, compute-budget declaration (.ai-state/gpu_budget.yaml), and a program.md template at repo root. All scaffolding is idempotent. Pick:`) |
| 8d | 8d | (Three-option pick — see §Phase 8d for the exact AskUserQuestion form. Default is `Install Obsidian integration`. Headline: `Phase 8d: Obsidian integration. I can wire this project for Obsidian vault-as-repo: a .gitignore Obsidian block, a check that the obsidian@obsidian-skills marketplace plugin is installed at user scope, an ## Obsidian Integration block in CLAUDE.md, and permissions.deny entries in .claude/settings.json blocking the dangerous obsidian CLI subcommands. All installs are idempotent. Pick:`) |

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
- `.ai-state/metrics_reports/index.html` — copy from `${PLUGIN_INSTALL_PATH}/claude/aac-templates/metrics-viewer.html.tmpl`. This is a static redirect stub that points users to `praxion-dashboard` for interactive metrics charts, trend history, and sentinel health sparkline. Co-locating the stub with the data means a bookmarked `index.html` still resolves to something helpful even when the dashboard is not running.

  **Predicate (skip if present).** If `.ai-state/metrics_reports/index.html` already exists in the user project, skip — never overwrite a customized stub. Re-pulling the latest is a deliberate user action (delete the file, re-run).

  **Action.** Create `.ai-state/metrics_reports/` if missing, then `cp ${PLUGIN_INSTALL_PATH}/claude/aac-templates/metrics-viewer.html.tmpl .ai-state/metrics_reports/index.html`. If the plugin install path was not detected at pre-flight (skip-phase-4 flag set), also skip this sub-step and emit: `Skipping metrics redirect stub copy — install the plugin and re-run /onboard-project. Without it, .ai-state/metrics_reports/ has data but no pointer page.`

  **Note:** The interactive metrics viewer lives in the dashboard. Launch it with `praxion-dashboard start <project-path>` or `/dashboard` in Claude Code, then open the Metrics tab. Offline reading is available via the `METRICS_REPORT_*.md` files in the same directory.

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

**Why these hooks.** The pre-commit hook enforces id-citation discipline — committed code must not reference ephemeral pipeline ids (`REQ-NN`, `AC-NN`, `Step N`, draft ADR hashes). Rationale, exempt paths, and escape hatch live in `rules/swe/id-citation-discipline.md`.

Three finalize hooks (post-merge, post-commit, post-checkout) all symlink to a single multiplexed dispatcher (`scripts/git-finalize-hook.sh`) that reads `basename($0)` and dispatches to the matching entry point in `scripts/finalize_chain.sh`. The trio is state-driven: each entry point gates on "are we on main with drafts present?" so draft ADRs landing on main via any path eventually promote — fast-forward merges (post-merge), direct commits / non-ff merges / rebases / cherry-picks (post-commit), branch switch / fresh clone / reset (post-checkout). Single-trigger coverage misses real cases (a branch reset to main, a fresh clone with drafts on main, a fast-forward pull) where drafts otherwise sit in `decisions/drafts/` indefinitely.

Composition per trigger: `post-merge` runs `reconcile_ai_state.py` (when `.ai-state/` was touched), `finalize_adrs.py --all` and `finalize_tech_debt_ledger.py --all` (when on main with drafts), then `check_squash_safety.py` (always, as a non-blocking diagnostic). `post-commit` and `post-checkout` run only the on-main finalize subset. All steps are non-blocking — a hook cannot abort a completed git operation.

**Skip condition.** If §Pre-flight set the `skip-phase-4` flag (plugin not installed), skip this phase entirely and emit: `Skipping Phase 4 — install the plugin and re-run /onboard-project to install hooks.`

**Predicate.** Detect existing symlinks via `readlink .git/hooks/<name>` and check whether the target contains `/i-am/`. The pre-commit hook target ends in `git-pre-commit-hook.sh`; the three finalize hooks (`post-merge`, `post-commit`, `post-checkout`) all share `git-finalize-hook.sh` as their target. Each individual hook that is already a correct Praxion symlink is skipped; the others install. Legacy targets (`git-post-merge-hook.sh` from older versions) count as Praxion-managed and are upgraded to the new symlink target without prompting.

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

2. **Finalize hooks (post-merge, post-commit, post-checkout)** — symlink all three `.git/hooks/<name>` entries to the plugin's multiplexed dispatcher:
   ```bash
   for hook in post-merge post-commit post-checkout; do
     ln -sf "${PLUGIN_INSTALL_PATH}/scripts/git-finalize-hook.sh" ".git/hooks/${hook}"
   done
   ```
   The dispatcher reads `basename($0)` to determine which trigger fired and dispatches to the matching entry point in `finalize_chain.sh`. Together the three hooks cover every path that lands draft ADRs on `main` — fast-forward merges (post-merge), direct commits / non-ff merges / rebases / cherry-picks (post-commit), branch switch / fresh clone (post-checkout). Without all three, draft ADRs that arrive on main via paths that don't fire `post-merge` (or that landed without a textbook merge event) silently sit in `decisions/drafts/` indefinitely.

   The dispatcher is state-driven: each entry point gates on `on_main && drafts_present` before invoking `finalize_adrs.py --all` and `finalize_tech_debt_ledger.py --all`. `post-merge` additionally runs `reconcile_ai_state.py` (when `.ai-state/` was touched) and `check_squash_safety.py` (always, as a diagnostic). All steps are non-blocking — a hook cannot abort a completed git operation.

   Same conflict-handling rule as pre-commit: if any of the three hooks already exists and is NOT a Praxion-managed file, back it up to `.git/hooks/<name>.pre-praxion`. Detect Praxion-managed files by symlink target (canonical) or by grepping for `finalize_chain` / `finalize_adrs` / `reconcile_ai_state` (legacy copies from older versions).

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

### Optional: Rule Blacklist Configuration

Praxion rules are categorized into core (always-loaded, non-disableable) and disableable (every other rule — hook-deliver and symlinked alike). The per-project `.claude/praxion-rules.yaml` disable list reaches both delivery channels uniformly: hook-deliver rules are filtered from `additionalContext` at SessionStart; symlinked rules get `claudeMdExcludes` entries reconciled into `.claude/settings.json`. To customize which rules your project inherits, create an optional `.claude/praxion-rules.yaml` file:

```yaml
version: 1
disable:
  - swe/memory-protocol    # Example: disable if your team uses different memory strategy
  - ml/*                   # Example: disable entire category
```

**Action (idempotent).** If the project does not already have `.claude/praxion-rules.yaml.example`, copy Praxion's template into the project so the user has a starting point to edit:

```bash
# Skip if either path already exists in the project (.example or live config)
[ -f .claude/praxion-rules.yaml.example ] || [ -f .claude/praxion-rules.yaml ] || \
  cp "$CLAUDE_PLUGIN_ROOT/claude/config/praxion-rules.yaml.example" .claude/praxion-rules.yaml.example
```

The user can then rename `.example` to `.claude/praxion-rules.yaml` and uncomment entries in the `disable:` list to activate them (or keep `.example` for reference and author a fresh `praxion-rules.yaml` from scratch).

See [`docs/rules-taxonomy.md`](../docs/rules-taxonomy.md) for the complete reference on rule categories, token accounting, and disable-list configuration. A project with no `.claude/praxion-rules.yaml` loads all rules identically to the original behavior — backward compatible, opt-out default.

## §Phase 5b — Hackathon mode gate

**Predicate.** `PRAXION_HACKATHON_MODE=1` present under `.env` in `.claude/settings.json` — skip the entire phase if already set (fully idempotent re-run).

**Gate 5b.** When the `no-more-gates` flag is not set, fire `AskUserQuestion` with `header: "Hackathon mode"`, `multiSelect: false`, and the headline from the gate map. When `--hackathon` was passed to the command, auto-default to `Enable hackathon mode` without prompting. When `no-more-gates` is set, apply the default (`Skip — keep full ceremony`). When the user picks `Enable hackathon mode`, run the six-artifact write-set below. When the user picks `Skip — keep full ceremony`, skip Phase 5b entirely.

**Six-artifact write-set.** When enabled, write these six artifacts idempotently (each guarded by its own predicate):

1. **`.claude/settings.json` env key** — add `"PRAXION_HACKATHON_MODE": "1"` to the `env` block (merge non-destructively; never overwrite other keys). **Predicate:** `PRAXION_HACKATHON_MODE` key present in `.claude/settings.json` env block.

2. **`## Hackathon Mode` CLAUDE.md block** — append the §Hackathon Mode Block verbatim to `CLAUDE.md`. **Predicate:** `grep -q '^## Hackathon Mode$' CLAUDE.md`. When `CLAUDE.md` does not exist, print: `No CLAUDE.md found — run /init to generate one, then re-run /onboard-project.` and skip this artifact.

3. **`.claude/praxion-rules.yaml` hackathon preset** — merge the three hackathon rule IDs into `.claude/praxion-rules.yaml`. **Predicate:** `grep -q 'hackathon' .claude/praxion-rules.yaml 2>/dev/null` (skip if already present; idempotent re-run never duplicates entries).
   - **If the file does not exist**, create it with:
     ```yaml
     # Hackathon mode preset — saves ~3,500 tokens (ambient, every session)
     disable:
       - swe/agent-model-routing
       - swe/memory-protocol
       - swe/vcs/git-conventions
     ```
   - **If the file already exists**, read it and append the three rule IDs as new list items under the existing `disable:` key (do not emit a second `disable:` block and do not emit `version:`). If no `disable:` key is present yet, add one. Never overwrite or remove existing entries — only add the three missing IDs (skip any that are already listed).

4. **`scripts/praxion-hackathon` wrapper** — copy `claude/aac-templates/praxion-hackathon.sh.tmpl` from the plugin install path to `scripts/praxion-hackathon` and `chmod +x`. Adjust the `PRAXION_DIR` path for the project's `.claude/` directory. **Predicate:** `test -f scripts/praxion-hackathon`.

5. **`.claude/hackathon-directive.md`** — copy `claude/aac-templates/hackathon-directive.md.tmpl` from the plugin install path to `.claude/hackathon-directive.md`. **Predicate:** `test -f .claude/hackathon-directive.md`.

6. **`.claude/hackathon-settings.json`** — copy `claude/aac-templates/hackathon-settings.json.tmpl` from the plugin install path to `.claude/hackathon-settings.json`. **Predicate:** `test -f .claude/hackathon-settings.json`.

**If the plugin install path was not detected** (skip-phase-4 flag set), skip artifacts 4, 5, and 6 and emit: `Skipping hackathon wrapper and settings files — install the plugin and re-run /onboard-project Phase 5b. Artifacts 1–3 (env var, CLAUDE.md block, praxion-rules preset) were written.`

**Phase 5b in the §Phase 9 summary.** Report per-artifact: `Phase 5b: hackathon mode enabled — PRAXION_HACKATHON_MODE=1, ## Hackathon Mode appended, praxion-rules preset added, scripts/praxion-hackathon written, .claude/hackathon-directive.md written, .claude/hackathon-settings.json written` (or `skipped (user chose Skip)` / `skipped (already enabled)`).

## §Phase 6 — `CLAUDE.md` Praxion blocks

**Predicate.** Six independent heading checks (five core blocks + Obsidian Integration when Phase 8d ran):

- `## Agent Pipeline` heading present → skip the Agent Pipeline append
- `## Compaction Guidance` heading present → skip the Compaction Guidance append
- `## Behavioral Contract` heading present → skip the Behavioral Contract append
- `## Praxion Process` heading present → skip the Praxion Process append
- `## Working in this project` heading present → skip the Project Essentials append
- `## Obsidian Integration` heading present → skip the Obsidian Integration append (Phase 8d appends this block; Phase 6 honors the predicate for re-runs)

**Action.**

1. **If `CLAUDE.md` does NOT exist**, do not create it directly. Print: `No CLAUDE.md found at the project root. Run /init to generate one from the codebase, then re-run /onboard-project to append the Praxion blocks.` Skip the rest of Phase 6.

2. **If `CLAUDE.md` exists**, append (in this order, each guarded by its predicate):
   - The §Agent Pipeline Block verbatim
   - The §Compaction Guidance Block verbatim
   - The §Behavioral Contract Block verbatim
   - The §Praxion Process Block verbatim
   - The §Project Essentials Block verbatim

   Append at the end of the file with one blank line separating from preceding content.

3. **Fill the §Project Essentials Block placeholders** (skip this step whenever step 2's predicate skipped the Project Essentials append — the block is already present and presumably already filled). Inspect the project's config (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, CI workflows, the README) and:
   - replace `<typecheck command>` / `<test command>` / `<lint command>` / `<build command>` with the project's actual commands — omit a numbered step (and renumber) when the project has no such command; never invent one;
   - replace `<list 3–5 of this project's most common task intents>` with a ≤5-bullet list of what an agent is most often asked to do here, derived from the codebase shape and the README.

   If a value is genuinely undeterminable, leave the placeholder with an inline `# TODO:` note so the user fills it.

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

- `test -e .ai-state/DESIGN.md` (architect-facing doc already present — likely a re-run on a fully-onboarded project, or a greenfield-followed-by-onboard sequence where `/new-project`'s seed pipeline already produced it)
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
   - `.ai-state/DESIGN.md` — architect-facing design-target document. Use the `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` template. Sections: System Overview, System Context (L0 — LikeC4+D2 `c4` block + committed SVG reference), Components (L1 — LikeC4+D2 `c4` block + committed SVG reference + table), Data Flow, Quality Attributes (testing, observability, deployment current state), Open Questions / Known Gaps. Mark unverified-by-code claims with section ownership tags so future updates can supersede cleanly.
   - `docs/architecture.md` — developer-facing navigation guide. Use the `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` template. Filter `.ai-state/DESIGN.md` to the **Built** components only — every component name and file path must resolve on disk (verify with `Glob` or `ls`). Skip components that exist only in the design-target document.
4. **Outputs (optional, agent's call).**
   - One ADR draft under `.ai-state/decisions/drafts/` if the baseline reading surfaces a load-bearing architectural invariant worth preserving (e.g., a one-way module dependency, a layer boundary, a data-flow constraint). The ADR is *only* warranted when the invariant is non-obvious from the code; do not write a ceremonial "architecture is now baselined" ADR.
5. **Anti-instructions.**
   - Do NOT produce `SYSTEMS_PLAN.md` — there is no feature in scope for a baseline audit, and a SYSTEMS_PLAN without a feature is anti-pattern.
   - Do NOT invent components that don't exist on disk. Every component table row and SVG reference must be code-verified.
   - Do NOT exceed L1 detail in C4 diagrams (≤10 nodes per `rules/writing/diagram-conventions.md`). Use LikeC4 DSL for C4-architectural views; Mermaid for sequence/state/ER/flowchart. L2 internals are deferred to feature-pipeline updates.
   - Do NOT modify any source code, tests, or non-architecture documentation.

The architect operates in a fresh context window (`Task` tool spawn) and reports completion when both docs are written. The main agent reads the produced docs at completion to confirm shape, then proceeds to Phase 9.

**If the architect fails or times out**, emit a clear warning: `Phase 8 skipped — systems-architect did not complete the baseline audit. Architecture docs were not produced. Re-run /onboard-project to retry, or run a feature pipeline whose first stage will produce them.` Proceed to Phase 8b.

## §Phase 8b — AaC Tier Install (opt-in, default-skip)

**Why this phase exists.** Phase 8 produces architecture docs. Phase 8b installs the AaC enforcement layer: fence-region examples in those docs, fitness tests for architectural invariants, a golden-rule pre-commit block, CI workflow, and a diagram directory stub. All five surfaces are idempotent and independent — each sub-step is guarded by its own predicate so re-runs produce zero `git diff`. Sentinel-only surfaces (traceability convention, sentinel AC dimension) need no per-project install — the AaC convention and sentinel agent are global.

Note: AaC enforcement via Block D requires the `i-am` plugin to be installed. If the plugin is absent, the golden-rule hook block silently exits 0 — same behavior as Phase 4's id-citation check.

**Gate 8b — three-option AskUserQuestion.** Use `AskUserQuestion` with `header: "Next?"`, `multiSelect: false`, the Gate 8b headline from the gate map, and these three options:

| Option label | Description |
|---|---|
| `Skip AaC (recommended for existing projects)` | **Default.** No AaC scaffolding installed. Phase 9 verification handoff runs normally. Re-run `/onboard-project` later when ready — all sub-steps are idempotent. |
| `Install AaC tier` | Run all five sub-steps (8b.1–8b.5). Each is independently idempotent; already-installed surfaces are silently skipped. |
| `Run all rest` | Skip remaining gates; default the AaC choice to `Skip AaC` (matches the existing-project principle "extend existing patterns; do not impose"). |

When the `no-more-gates` flag is set (user previously picked `Run all rest`), default to `Skip AaC` without prompting.

**Action when "Install AaC tier" is chosen.** Run sub-steps 8b.1 through 8b.5 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8b.1 — Fence seed

**Predicate.** At least one of `**/ARCHITECTURE.md` or `docs/architecture.md` exists AND does NOT already contain the string `aac:generated` or `aac:authored`.

- If no architecture doc exists: skip silently. Phase 8 (if run) will produce one; a future feature pipeline may produce one. Re-running Phase 8b after an architecture doc exists will complete this sub-step.
- If an architecture doc exists but already contains `aac:generated` or `aac:authored` markers: skip with notice `8b.1: skipped (fence regions already present)`.

**Action.** For each architecture doc found (prefer `docs/architecture.md`; also process `**/ARCHITECTURE.md` if different from the first), append the following commented example stanza at the end of the file using `Edit`:

```markdown
<!-- AaC fence example — see rules/writing/aac-dac-conventions.md for the full convention.
     Replace this comment with real fence regions as you document components.

aac:authored id=example-component
This is a human-authored rationale paragraph. The agent reads this and preserves it.
aac:end

aac:generated id=example-component
<!-- agent-generated content lands here; never edit manually -->
aac:end
-->
```

Print: `8b.1: fence example appended to <filename> — edit the stanza to wrap real prose`.

### Sub-step 8b.2 — Fitness scaffold

**Predicate.** `fitness/` directory does NOT exist. If it exists: skip with notice `8b.2: skipped (fitness/ already present)`. Individual files within the scaffold are also checked — if a target file exists, skip that file and continue with others.

**Action.** Create `fitness/` and `fitness/tests/` directories. Copy from Praxion's AaC templates (in the plugin install path):

| Source template | Destination |
|---|---|
| `claude/aac-templates/fitness-import-linter.cfg.tmpl` | `fitness/import-linter.cfg` |
| `claude/aac-templates/fitness-test-meta-citation.py.tmpl` | `fitness/tests/test_meta_citation.py` |
| `claude/aac-templates/fitness-test-starter.py.tmpl` | `fitness/tests/test_starter.py` |
| `claude/aac-templates/fitness-conftest.py.tmpl` | `fitness/tests/conftest.py` |
| `claude/aac-templates/fitness-README.md.tmpl` | `fitness/README.md` |

Also create an empty `fitness/tests/__init__.py` (skip if exists). Templates are read from the Praxion repo (use `Read` on the template path relative to the plugin install path). Write each destination with `Write`.

Print: `8b.2: fitness/ scaffolded — read fitness/README.md and the architectural-fitness-functions skill to author your first invariant`.

### Sub-step 8b.3 — Block D append (pre-commit hook)

**Predicate.** `.git/hooks/pre-commit` exists AND does NOT contain the string `Block D` or `check_aac_golden_rule`.

- If `.git/hooks/pre-commit` does not exist: skip with notice `8b.3: skipped (no pre-commit hook — run Phase 4 first, then re-run Phase 8b)`.
- If `Block D` or `check_aac_golden_rule` is already present: skip with notice `8b.3: skipped (Block D already present)`.

**Action.** Read `.git/hooks/pre-commit`. Append the Block D fragment from `claude/aac-templates/precommit-block-d.sh.frag` using `Edit`. The fragment uses `${PLUGIN_ROOT}` resolution (mirrors Phase 4's `check_id_citation_discipline.py` pattern) and invokes `python3 ${PLUGIN_ROOT}/scripts/check_aac_golden_rule.py --mode=gate`. Appending AFTER existing checks ensures AaC failure does not mask id-citation failures.

Print: `8b.3: Block D appended to .git/hooks/pre-commit`.

### Sub-step 8b.4 — Workflow render

**Predicate.** `.github/workflows/architecture.yml` does NOT exist.

- If exists: skip with notice `8b.4: skipped (.github/workflows/architecture.yml already present)`.

**Action.** Create `.github/workflows/` directory if missing. Read `claude/aac-templates/architecture.yml.tmpl`. Perform placeholder substitution:

| Placeholder | Derivation | Default |
|---|---|---|
| `{{PROJECT_PATHS_DIAGRAMS}}` | Detected `<doc-dir>/diagrams/` from sub-step 8b.5 or `docs/diagrams/` | `docs/diagrams/` |
| `{{PROJECT_PATHS_ARCHITECTURE_DOCS}}` | Fixed | `**/ARCHITECTURE.md` |
| `{{PROJECT_PYTHON_VERSION}}` | `requires-python` lower bound from `pyproject.toml`, or fallback | `3.13` |
| `{{PROJECT_PLUGIN_DIR}}` | Plugin install scope; `.` works for user-installed plugins | `.` |

After substitution, validate the result parses as valid YAML. If YAML parsing fails, abort this sub-step with: `8b.4: skipped — architecture.yml template substitution produced invalid YAML; check pyproject.toml requires-python value`. Continue with 8b.5.

Write the validated YAML to `.github/workflows/architecture.yml` using `Write`.

Print: `8b.4: .github/workflows/architecture.yml written`.

### Sub-step 8b.5 — Diagrams scaffold

**Predicate.** `docs/diagrams/` does NOT exist (or `<doc-dir>/diagrams/` if pre-flight detected a non-default doc dir). Per the forward-binding constraint on `<doc-dir>/diagrams/`, a top-level `architecture/` directory is NEVER created.

- If `docs/diagrams/` exists: skip with notice `8b.5: skipped (docs/diagrams/ already present)`.

**Action.** Create `docs/` if missing. Create `docs/diagrams/`. If the directory is otherwise empty (no `.c4`, `.d2`, `.svg`, or other files), write `docs/diagrams/.gitkeep` (0-byte placeholder so git commits the directory). If the directory already contains files (user has `.c4` sources), do not write `.gitkeep`.

Print: `8b.5: docs/diagrams/ created` (with `.gitkeep` appended if the placeholder was written).

**Verification handoff.** After all five sub-steps complete, print the final-state checklist:

```
AaC tier install summary:
  8b.1 fence seed:        <installed | skipped (reason)>
  8b.2 fitness/:          <installed | skipped (reason)>
  8b.3 Block D:           <installed | skipped (reason)>
  8b.4 architecture.yml:  <installed | skipped (reason)>
  8b.5 docs/diagrams/:    <installed | skipped (reason)>
```

Phase 9 verification handoff lists every staged file across all phases — Phase 8b's surfaces are included in that enumeration.

## §Phase 8c — ML/AI Training Scaffold (opt-in; default-yes when ML signals detected)

**Why this phase exists.** ML/AI training projects require scaffolding that general software projects do not: experiment tracking directories, checkpoint gitignore entries, compute-budget declarations, and a `program.md` meta-prompt. Phase 8c detects whether the project is ML-flavored and applies idempotent scaffolding so the first `/run-experiment` invocation finds the infrastructure already in place. It also surfaces the three operational modes (A/B/C) so the user knows how to configure their backend before dispatching a run.

**Detection signals.** Phase 8c fires when ANY of the following signals is present in the project root:

1. `train.py` or `prepare.py` exists at the project root
2. `pyproject.toml` (or `requirements.txt`, `setup.py`, `Pipfile`) declares `torch`, `jax`, or `tensorflow` as a dependency
3. `program.md` exists at the project root (recognized ML meta-prompt artifact)

When none of these signals is detected, skip Phase 8c entirely and emit: `Phase 8c: skipped (no ML training signals detected — train.py, torch/jax/tensorflow dependency, or program.md)`.

**Gate 8c — three-option AskUserQuestion.** Use `AskUserQuestion` with `header: "Next?"`, `multiSelect: false`, the Gate 8c headline from the gate map, and these three options:

| Option label | Description |
|---|---|
| `Run ML scaffold` | **Default when ML signals detected.** Run all five sub-steps (8c.1–8c.5). Each is independently idempotent; already-present scaffolding is silently skipped. |
| `Skip ML scaffold` | **Default when no ML signals detected.** Skip Phase 8c entirely. Re-run `/onboard-project` later when ready — all sub-steps are idempotent. |
| `Run all rest` | Skip remaining gates; default the ML scaffold choice to `Run ML scaffold` when signals detected, `Skip ML scaffold` otherwise; run autonomously through Phase 9. |

When the `no-more-gates` flag is set (user previously picked `Run all rest`), default to `Run ML scaffold` if signals were detected in §Pre-flight, `Skip ML scaffold` otherwise.

**Action when "Run ML scaffold" is chosen.** Run sub-steps 8c.1 through 8c.5 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8c.1 — Experiment tracking directory

**Predicate.** `.ai-state/experiments/` does NOT exist. If it exists: skip with notice `8c.1: skipped (.ai-state/experiments/ already present)`.

**Action.** Create `.ai-state/experiments/` directory. Write `.ai-state/experiments/README.md`:

```markdown
# Experiment Tracking Directory

Experiment tracking artifacts live here — MLflow or W&B run metadata, artifact references,
and run-tag index entries. Generated content; committed selectively. See
`skills/experiment-tracking/SKILL.md` for tracker configuration and run conventions.
```

Print: `8c.1: .ai-state/experiments/ created`.

### Sub-step 8c.2 — Checkpoint `.gitignore` block

**Predicate.** `grep -q '# ML training checkpoints' .gitignore` is true. If detected: skip with notice `8c.2: skipped (checkpoint .gitignore block already present)`.

**Action.** Append to `.gitignore` (create if absent):

```gitignore
# ML training checkpoints (Praxion-managed)
runs/
checkpoints/
*.pt
*.bin
*.safetensors
wandb/
mlruns/
```

Print: `8c.2: checkpoint .gitignore block appended`.

### Sub-step 8c.3 — GPU budget declaration

**Predicate.** `test -e .ai-state/gpu_budget.yaml` is true. If file exists: skip with notice `8c.3: skipped (.ai-state/gpu_budget.yaml already present)`.

**Action.** Ask the user: `What is the project-level GPU hours budget per experiment? (Examples: 2.0 for a short validation run; 8.0 for an overnight run; 0 to declare later and enforce per-step)` Wait for input. Write `.ai-state/gpu_budget.yaml`:

```yaml
# GPU hours budget per experiment run (project-level default).
# Individual WIP.md steps may override this value via gpu_hours_budget: <float>.
# Convention: rules/ml/gpu-budget-conventions.md
gpu_hours_budget: <user-provided or 0>
```

Print: `8c.3: .ai-state/gpu_budget.yaml written (gpu_hours_budget: <value>)`.

### Sub-step 8c.4 — `program.md` scaffold

**Predicate.** `test -e program.md` at repo root is true. If `program.md` exists: skip with notice `8c.4: skipped (program.md already exists — user-authored meta-prompt preserved)`.

**Action.** Write `program.md` at the project root:

```markdown
# Program

<!-- program.md is the project-local meta-prompt for this experiment loop.
     It guides the autonomous training cycle. Praxion recognizes it as an
     artifact category alongside CLAUDE.md. See skills/ml-training/SKILL.md
     for the vocabulary and artifact types this file governs. -->

## Goal

[Describe the training objective: model architecture, dataset, target metric threshold]

## Hypothesis Space

[What configurations or architecture changes will this loop explore?]

## Simplicity Criterion

[What is the simplest run that would confirm the hypothesis? Start here.]

## Tracker

mlflow  # or: wandb

## Autonomy Contract

[How much should /run-experiment decide autonomously vs. pause for human input?]

## Current Run

[Leave empty — /run-experiment populates this section]

## History

[Summarize past runs, key results, and what changed between them]
```

Print: `8c.4: program.md scaffold written — fill in Goal and Hypothesis Space before running /run-experiment`.

### Sub-step 8c.5 — Operational modes callout

**Predicate.** None — always runs when Phase 8c fires.

**Action.** Print the operational modes summary:

```text
ML scaffold complete. Your project supports three operational modes:

  Mode A — Co-located owned GPU (Mac M-series, RTX, on-prem):
            set backend: local in .ai-state/neo_cloud_backend.yaml

  Mode B — Co-located rented GPU (SSH'd into an H100 box):
            same config as Mode A; SSH into the box with Praxion installed first

  Mode C — Separated cloud (SkyPilot or RunPod direct):
            set backend: skypilot or backend: runpod-direct

Full walkthrough: skills/ml-training/references/operational-modes.md

Next steps:
  1. Edit program.md — describe your training goal and tracker preference
  2. Run /run-experiment to dispatch a training run
  3. Run /check-experiment to monitor an in-flight or completed run
```

Conventions for tracker config, run-tag mapping, and experiment log format:
`rules/ml/experiment-tracking-conventions.md` and `skills/experiment-tracking/SKILL.md`.
Compute budget conventions: `rules/ml/gpu-budget-conventions.md` and
`skills/deployment/references/gpu-compute-budgeting.md`.

Print: `8c.5: operational modes callout printed`.

**Verification handoff.** After all five sub-steps complete, print the final-state checklist:

```text
ML scaffold summary:
  8c.1 .ai-state/experiments/:  <created | skipped (reason)>
  8c.2 checkpoint .gitignore:   <appended | skipped (reason)>
  8c.3 .ai-state/gpu_budget.yaml: <written (value) | skipped (reason)>
  8c.4 program.md:              <scaffolded | skipped (reason)>
  8c.5 mode callout:            printed
```

Phase 9 verification handoff lists every staged file across all phases — Phase 8c's surfaces are included in that enumeration.

## §Phase 8d — Obsidian Integration (opt-in, default-yes)

**Why this phase exists.** Projects that use Obsidian as a vault inside the repository benefit from four surfaces: a `.gitignore` block that keeps workspace state files out of commits, the `obsidian@obsidian-skills` marketplace plugin (installed at user scope via `./install.sh code`) so agents can navigate the vault, a link-safety config in `.obsidian/app.json` that pins Markdown-form links and disables auto link-rewrite so vault tooling cannot corrupt project-artifact links, and a `permissions.deny` block in `.claude/settings.json` that mechanically blocks the dangerous `obsidian` CLI subcommands. Without these, an agent can inadvertently commit Obsidian workspace noise, miss vault-navigation tools, rewrite project links into wikilink form, or be denied permissions silently without knowing why. Phase 8d verifies all four idempotently.

**Gate 8d — three-option AskUserQuestion.** Use `AskUserQuestion` with `header: "Next?"`, `multiSelect: false`, the Gate 8d headline from the gate map, and these three options:

| Option label | Description |
|---|---|
| `Install Obsidian integration (recommended)` | **Default.** Run all sub-steps (8d.1–8d.6). Each is independently idempotent; already-installed surfaces are silently skipped. |
| `Skip` | Skip Phase 8d entirely. Re-run `/onboard-project` later when ready — all sub-steps are idempotent. |
| `Run all rest` | Skip remaining gates; default the Obsidian choice to `Install Obsidian integration`; run autonomously through Phase 9. |

When the `no-more-gates` flag is set (user previously picked `Run all rest`), default to `Install Obsidian integration` without prompting.

**Action when "Install Obsidian integration" is chosen.** Run sub-steps 8d.1 through 8d.6 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8d.1 — `.gitignore` Obsidian block

**Predicate.** `grep -q '^# Obsidian$' .gitignore`. If present: skip with notice `8d.1: skipped (.gitignore Obsidian block already present)`.

**Action.** Append to `.gitignore` (create if absent):

```gitignore
# Obsidian
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache/
.obsidian/appearance.json
.obsidian/*.compat.json
.obsidian/hotkeys.json
```

Print: `8d.1: Obsidian .gitignore block appended`.

### Sub-step 8d.2 — Verify `claude` CLI present

**Predicate.** `command -v claude >/dev/null 2>&1`. If absent:

> `claude CLI not found — run install.sh code on the operator machine, then re-run this phase.`

Skip sub-steps 8d.3–8d.6. Print: `8d.2: claude CLI not found — skipping remaining sub-steps`.

If present, continue. Print: `8d.2: claude CLI found`.

### Sub-step 8d.3 — Verify marketplace plugin installed

**Predicate.** `claude plugin list 2>/dev/null | grep -q "obsidian@obsidian-skills"`. If the plugin is present: skip with notice `8d.3: skipped (obsidian@obsidian-skills already installed at user scope)`.

**Action when plugin is absent.** Warn:

> `Obsidian skills plugin not installed — run ./install.sh code, then re-run /onboard-project`

Skip sub-steps 8d.4–8d.6. Print: `8d.3: obsidian@obsidian-skills not installed — skipping remaining sub-steps`.

If the plugin is found, print: `8d.3: obsidian@obsidian-skills verified at user scope`.

### Sub-step 8d.4 — `.obsidian/app.json` link-safety config

**Why this exists.** Because the repository doubles as a vault, Obsidian's default link behavior would let vault tooling corrupt project-artifact links. New links default to `[[wikilink]]` form (Praxion uses Markdown `[text](path)` links and ADR id cross-references), and "Automatically update internal links" can rewrite link bodies across files on rename/move. Pinning two keys in `.obsidian/app.json` closes both vectors. Only these two keys are written, merged non-destructively — all other `.obsidian/app.json` keys (and the rest of `.obsidian/`) stay Obsidian-managed. `app.json` is committed (the `.gitignore` block from 8d.1 ignores workspace/cache/appearance/hotkeys, not `app.json`), so every clone inherits the safe defaults.

**Predicate.** Both keys already set to the safe values:
```bash
jq -e '(.useMarkdownLinks == true) and (.alwaysUpdateLinks == false)' \
  .obsidian/app.json 2>/dev/null
```
If exit 0 (both already pinned): skip with notice `8d.4: skipped (.obsidian/app.json link-safety keys already pinned)`.

**Action.** Create `.obsidian/` if absent, then merge the two keys into `.obsidian/app.json` (create `{}` if absent), preserving all existing keys:
```bash
mkdir -p .obsidian
[ -f .obsidian/app.json ] || echo '{}' > .obsidian/app.json
jq '.useMarkdownLinks = true | .alwaysUpdateLinks = false' \
  .obsidian/app.json > .obsidian/app.json.tmp && \
  mv .obsidian/app.json.tmp .obsidian/app.json
```

Print: `8d.4: .obsidian/app.json link-safety keys pinned (useMarkdownLinks=true, alwaysUpdateLinks=false)`.

### Sub-step 8d.5 — Append `## Obsidian Integration` block to `CLAUDE.md`

**Predicate.** `grep -q '^## Obsidian Integration$' CLAUDE.md`. If present: skip with notice `8d.5: skipped (## Obsidian Integration block already in CLAUDE.md)`.

**Action.** If `CLAUDE.md` does not exist, print: `No CLAUDE.md found — run /init first, then re-run /onboard-project.` and skip. Otherwise, append the §Obsidian Integration Block verbatim from this command's body. Append at the end of the file with one blank line separating from preceding content.

Print: `8d.5: ## Obsidian Integration block appended to CLAUDE.md`.

### Sub-step 8d.5b — Write `permissions.deny` to `.claude/settings.json`

**Predicate.** Check whether all required deny entries are already present — a subset check, so re-running on a project onboarded under an older (smaller) entry set still adds the missing entries:
```bash
jq -e --argjson req '[
  "Bash(obsidian eval*)",
  "Bash(obsidian plugin:install*)",
  "Bash(obsidian plugin:enable*)",
  "Bash(obsidian plugin:disable*)",
  "Bash(obsidian plugin:uninstall*)",
  "Bash(obsidian theme:set*)",
  "Bash(obsidian theme:install*)",
  "Bash(obsidian delete --permanent*)",
  "Bash(obsidian move*)",
  "Bash(obsidian rename*)"
]' '($req - (.permissions.deny // [])) | length == 0' \
  .claude/settings.json 2>/dev/null
```
If exit 0 (no required entry missing): skip with notice `8d.5b: skipped (permissions.deny obsidian entries already present)`.

**Action.** Read `.claude/settings.json` (create `{"permissions":{}}` if absent). Merge `permissions.deny` non-destructively:
- Preserve all existing top-level keys.
- Preserve the existing `permissions.allow` array.
- Add the ten deny entries below. The `jq` merge is idempotent (`unique` dedupes), so entries already present are not duplicated — and entries missing from an older install are added on re-run.

Deny entries:

```json
"Bash(obsidian eval*)",
"Bash(obsidian plugin:install*)",
"Bash(obsidian plugin:enable*)",
"Bash(obsidian plugin:disable*)",
"Bash(obsidian plugin:uninstall*)",
"Bash(obsidian theme:set*)",
"Bash(obsidian theme:install*)",
"Bash(obsidian delete --permanent*)",
"Bash(obsidian move*)",
"Bash(obsidian rename*)"
```

Use `jq` to perform the merge:

```bash
jq '.permissions.deny = ((.permissions.deny // []) +
  ["Bash(obsidian eval*)",
   "Bash(obsidian plugin:install*)",
   "Bash(obsidian plugin:enable*)",
   "Bash(obsidian plugin:disable*)",
   "Bash(obsidian plugin:uninstall*)",
   "Bash(obsidian theme:set*)",
   "Bash(obsidian theme:install*)",
   "Bash(obsidian delete --permanent*)",
   "Bash(obsidian move*)",
   "Bash(obsidian rename*)"]
  | unique)' .claude/settings.json > .claude/settings.json.tmp && \
  mv .claude/settings.json.tmp .claude/settings.json
```

Print: `8d.5b: permissions.deny Obsidian CLI block written to .claude/settings.json`.

**Security note.** Eight of the denied subcommands are blocked for security: `obsidian eval` executes arbitrary JavaScript in the Obsidian renderer (remote code execution risk); the plugin lifecycle commands expose OS-level attack surface; `theme:set`/`theme:install` run theme code with app privileges; `obsidian delete --permanent` bypasses the trash and is unrecoverable. The remaining two — `move` and `rename` — are blocked for **link integrity**, not security: renaming or moving a tracked file through Obsidian can rewrite link bodies across the repo and hides the rename from git. Renames go through `git mv` instead. The `*` wildcard after each subcommand blocks all argument forms. Live end-to-end verification (actually calling a denied subcommand and observing the harness reject it) is deferred to first use in a Claude Code session with this `settings.json` applied.

### Sub-step 8d.6 — Print summary

Print:

```text
Obsidian integration install complete:
  obsidian@obsidian-skills plugin: verified at user scope (run: claude plugin list | grep obsidian-skills)
  .obsidian/app.json: link-safety keys pinned (or already present)
  CLAUDE.md: ## Obsidian Integration block appended (or already present)
  .claude/settings.json: permissions.deny Obsidian CLI block written (or already present)

CLI allowlist policy: obsidian file CRUD, search, link analysis, properties, tags, and
read-only diagnostics are ALLOWED. Dangerous subcommands (eval, plugin lifecycle, theme:set,
delete --permanent) are DENIED for security; file move/rename are DENIED for link integrity
(use git mv). Link safety: .obsidian/app.json pins Markdown-form links and disables Obsidian's
auto link-rewrite, so vault tooling cannot corrupt project-artifact links.

See docs/obsidian-integration.md for installation, configuration, troubleshooting, and the
full allowlist rationale.
```

**Verification handoff.** After all sub-steps complete, the summary above serves as the handoff. Phase 9 verification handoff lists every staged file across all phases — Phase 8d's surfaces are included in that enumeration.

## §Phase 9 — Verification + handoff

**Predicate.** None — terminal phase.

**Action.**

1. **Print the change summary** — group by phase, list every file modified and every `git config` setting written. Use this format:
   ```
   Onboarding complete. Changes:
     Phase 1: .gitignore (appended 10 lines, AI-assistants block)
     Phase 2: .ai-state/ skeleton (4 new entries)
     Phase 3: .gitattributes (appended 2 lines), git config (2 merge drivers registered)
     Phase 4: .git/hooks/pre-commit (new), .git/hooks/{post-merge,post-commit,post-checkout} (symlinks)
     Phase 5: .claude/settings.json (4 PRAXION_DISABLE_* env vars)
     Phase 6: CLAUDE.md (appended Agent Pipeline + Compaction + Behavioral Contract + Praxion Process + Working-in-this-project blocks)
     Phase 7: companion CLIs — chub missing (install: ...), scc missing (install: ...)
     Phase 8: architecture baseline produced — .ai-state/DESIGN.md + docs/architecture.md (+ N ADR draft(s))
     Phase 8b: AaC tier — fence seed, fitness/, Block D, architecture.yml, docs/diagrams/ (or skipped per sub-step)
     Phase 8c: ML scaffold — .ai-state/experiments/, .gitignore block, gpu_budget.yaml, program.md (or skipped per sub-step)
     Phase 8d: Obsidian integration — .gitignore Obsidian block, obsidian@obsidian-skills plugin verified, CLAUDE.md ## Obsidian Integration block, .claude/settings.json deny entries (or skipped per sub-step)
   ```
   For each skipped phase (idempotency hit OR user opt-out), print `Phase N: skipped (<reason>)` instead.

2. **Print verification next-steps** verbatim:
   ```
   Verify the onboarding:
     1. Run /sentinel for an ecosystem health baseline (writes .ai-state/sentinel_reports/SENTINEL_REPORT_<timestamp>.md).
     2. Run 'git status' to review staged work — every file this command modified is staged for review.
     3. Run /co to commit (the git-conventions rule will write a precise commit message), or unstage and review individually.

   Resources:
     - docs/existing-project-onboarding.md (companion guide to this command — open it in the Praxion repo for the full walkthrough)
     - rules/swe/swe-agent-coordination-protocol.md (how the agent pipeline works)
   ```

3. **Stage modified files**: run `git add` with the explicit list of files this command touched (built up through phases 1–6). Do NOT run `git add -A`. Do NOT commit. The user reviews staging and decides.

## §Agent Pipeline Block

<!-- canonical-source: claude/canonical-blocks/agent-pipeline.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Agent Pipeline

Follow the **Understand, Plan, Verify** methodology. For multi-step work (Standard/Full tier), delegate to specialized agents in pipeline order. Each pipeline operates in an ephemeral `.ai-work/<task-slug>/` directory (deleted after use); permanent artifacts go to `.ai-state/` (committed to git).

1. **researcher** → `.ai-work/<slug>/RESEARCH_FINDINGS.md` — codebase exploration, external docs
2. **systems-architect** → `.ai-work/<slug>/SYSTEMS_PLAN.md` + ADR drafts under `.ai-state/decisions/drafts/` (promoted to stable `<NNN>-<slug>.md` once on `main` by the finalize hook chain — post-merge / post-commit / post-checkout, all sharing one dispatcher) + `.ai-state/DESIGN.md` (architect-facing) + `docs/architecture.md` (developer-facing)
3. **implementation-planner** → `.ai-work/<slug>/IMPLEMENTATION_PLAN.md` + `WIP.md` — step decomposition
4. **implementer** + **test-engineer** (concurrent, on disjoint file sets) → code + tests — execute steps from the plan
5. **verifier** → `.ai-work/<slug>/VERIFICATION_REPORT.md` — post-implementation review

**Independent audits.** The `sentinel` agent runs outside the pipeline and writes timestamped `.ai-state/sentinel_reports/SENTINEL_REPORT_<timestamp>.md` plus an append-only `.ai-state/sentinel_reports/SENTINEL_LOG.md`. Trigger it for ecosystem health baselines (before first ideation, after major refactors).

**From PoC to production.** The feature pipeline is one milestone of many. The full journey: baseline audit (`/sentinel`) → CI/CD setup (`cicd-engineer` agent) → deployment (`deployment` skill) → first release (`/release`) → ongoing decisions captured as ADRs in `.ai-state/decisions/` → cross-session memory in `.ai-state/memory.json` (when memory MCP is enabled).

Always include expected deliverables when delegating to an agent. The agent coordination protocol rule has full delegation checklists.
```

The block is **self-contained** — no cross-references to files that exist only in the Praxion repo. The previous version pointed at `docs/getting-started.md#journey-poc-to-production`, which dangled in every onboarded project.

## §Compaction Guidance Block

<!-- canonical-source: claude/canonical-blocks/compaction-guidance.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Compaction Guidance

When this conversation compacts, always preserve: the active pipeline stage and task slug, the current WIP step number and status, acceptance criteria from the systems plan, and the list of files modified in the current step. The Praxion `PreCompact` hook snapshots in-flight pipeline documents to `.ai-work/<slug>/PIPELINE_STATE.md` — re-read that file after compaction to restore orientation.
```

## §Behavioral Contract Block

<!-- canonical-source: claude/canonical-blocks/behavioral-contract.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Behavioral Contract

Four non-negotiable behaviors for any agent (including Claude itself) writing, planning, or reviewing code:

- **Surface Assumptions** — state your interpretation up front and surface gap-filling assumptions as you make them; a plausible default never *feels* like ambiguity. Pause when one is load-bearing and hard to reverse.
- **Register Objection** — when a request violates scope, structure, or evidence, state the conflict with a reason before complying or declining.
- **Stay Surgical** — touch only what the change requires; if scope grew, stop and re-scope instead of expanding silently.
- **Simplicity First** — prefer the smallest solution that meets the behavior; every line, file, or dependency must earn its place.

Self-test: did I state my assumptions, flag conflicts with reasons, stay in scope, and pick the simplest path?
```

## §Praxion Process Block

<!-- canonical-source: claude/canonical-blocks/praxion-process.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Praxion Process

Apply Praxion's tier-driven pipeline for non-trivial work. Use the tier selector from `rules/swe/swe-agent-coordination-protocol.md`: Direct (single-file fix/typo) or Lightweight (2–3 files) may skip the full pipeline; Standard or Full tier work requires researcher → systems-architect → implementation-planner → implementer + test-engineer → verifier.

**Rule-inheritance corollary.** When delegating to any subagent — Praxion-native or host-native (Explore, Plan, general-purpose) — carry the behavioral contract into every delegation prompt. Host-native subagents do not load CLAUDE.md; the orchestrator is the only delivery path.

**Orchestrator obligation.** Every delegation prompt must name the task slug, expected deliverables, and the behavioral contract (Surface Assumptions · Register Objection · Stay Surgical · Simplicity First).
```

## §Hackathon Mode Block

<!-- canonical-source: claude/canonical-blocks/hackathon-mode.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Hackathon Mode

This project is in **hackathon mode** (`PRAXION_HACKATHON_MODE=1` in `.claude/settings.json`).
The mode applies to every agent and command in this project until the env var is removed
and this block is deleted (see "To exit" below).

### Process — the Hackathon Spine

In hackathon mode the 5-tier selector (Direct/Lightweight/Standard/Full/Spike) is REPLACED
by the **Hackathon Spine** — a pipeline you ENTER, MOVE AROUND IN, and EXIT. The spine has
a fixed ORDER but not a fixed MEMBERSHIP:

    promethean → researcher → systems-architect → implementation-planner
      → (implementer ∥ test-engineer) → verifier

**Entry by natural language.** You declare where to start in plain language; the main
agent infers the entry point:
- "ideate / explore options for X"          → enter at promethean
- "research how X works"                    → enter at researcher
- "design X / work out the approach"        → enter at systems-architect
- "I have the approach — plan and build X"  → enter at implementation-planner
- "fix this typo / implement X exactly so"  → enter at implementer

Everything UPSTREAM of the entry point is SKIPPED — including systems-architect and
implementation-planner. There is no separate "Direct" path: a trivial fix is just
"enter at implementer."

**Ambiguous entry → the main agent ASKS.** If your prompt does not make the entry point
clear, the main agent asks one short question ("start from ideation, or go straight to
planning/implementation?") — it does not silently pick a default.

**Free mid-task movement.** At any point you may move the work to a different stage
("go back and research this properly," "this needs a real design — move it to the
architect," "skip ahead and just build it"). User-driven movement is unbounded — it is
your call. The orchestrator re-routes and records the movement in PROGRESS.md.

**Worktree policy by entry point.** The spine maps entry points onto Praxion's existing
worktree isolation rule: entering at `promethean`, `researcher`, or `systems-architect`
→ the main agent creates a worktree (`EnterWorktree`) before spawning any agent (same as
a Standard/Full pipeline). Entering at `implementation-planner` or `implementer` → the
user decides; on-the-fly, no-worktree work in the current checkout is allowed (mirrors
Direct/Lightweight). If mid-task movement crosses into a worktree-requiring stage, the
orchestrator creates the worktree at that transition and records it in PROGRESS.md.

**Creative-blocker signal.** If an agent hits a genuine design dead-end (the current
approach is exhausted and fresh ideation is needed — NOT "this is hard," NOT "I need more
research"), it appends a `CREATIVE-BLOCKER: <desc> #blocker` line to
`.ai-work/<slug>/PROGRESS.md`, STOPS at that stage, and surfaces it to you. YOU decide
whether to move the work back to ideation. The agent does not auto-loop.

To run a single task at full 5-tier ceremony instead, say so explicitly; that one task
yields back to the normal selector.

### The verifier — default-on, skippable

The verifier runs by DEFAULT as the implementation harness, whatever entry point you
chose. It is skippable ONLY if you explicitly say so ("skip verification on this one").
When the verifier is skipped, the main agent tells you at task end exactly what process
was (not) applied.

### Skipping the architect — the main agent may HOLD

When you direct "just implement X" (entry at implementer, skipping the architect and
planner), the main agent complies — UNLESS it has a genuinely strong, well-founded reason
to believe skipping design is a real mistake. It HOLDS and asks you only when the task:
- touches a SECURITY-SENSITIVE surface (auth, authorization, secrets, trust-boundary input);
- carries DATA-LOSS RISK (schema migration, destructive data operation);
- is VISIBLY FAR BEYOND your framing (many files / multiple subsystems / cross-cutting
  structural change that no incremental step can absorb).
For minor or speculative doubts, it complies silently. The bar to hold is "a really good
motive," not "a doubt."

### Skipped rigor is recorded — the safety net is transparency

Because you can skip the architect, the planner, and the verifier, and move freely
mid-task, the safety net is that NONE of it is invisible:
- Every skipped stage is recorded in PROGRESS.md and in the VERIFICATION_REPORT.md header
  (or, if the verifier was skipped, a one-line terminal note at task end).
- Every mid-task movement is recorded in PROGRESS.md.
A reviewer or a graduation audit can always reconstruct exactly what process was applied
to any change.

### Discovery is full-strength — only delivery ceremony is relaxed

When promethean and researcher run, they run at FULL depth: unbounded internet research,
multi-source synthesis, idea ledgers. External web research via `WebSearch`/`WebFetch` is
unbounded — those are TOOLS, unaffected by `--disable-slash-commands`. A wrapper-launched
researcher loses skill auto-trigger only — invoke `/external-api-docs` explicitly for
curated API docs; raw web access is always available. The relaxation below applies ONLY
to the delivery ceremony, NEVER to discovery.

### The Behavioral Contract still applies — in every mode

Hackathon mode is NOT license to skip the four-behavior contract. Every agent that
writes, plans, or reviews code still honors:
- **Surface Assumptions** — list assumptions before acting; ask when ambiguity could
  produce the wrong artifact.
- **Register Objection** — when a request violates scope, structure, or evidence, state
  the conflict with a reason before complying or declining. Silent agreement is a violation.
- **Stay Surgical** — touch only what the change requires; re-scope rather than silently expand.
- **Simplicity First** — prefer the smallest solution that meets the behavior.
The architect's Surface Assumptions and Registered Objections sections are MANDATORY
even in the slim SYSTEMS_PLAN shape.

### Launching for full context trimming

Start sessions with the `praxion-hackathon` wrapper (`scripts/praxion-hackathon`). It
adds `--disable-slash-commands` (skills resolve only via explicit `/name`) and
`--effort low`. A plain `claude` launch still gets hackathon mode (env var + this block)
but NOT the skill-surface token trim. To resume, use `praxion-hackathon --resume`.

### SDD ceremony — OFF by default

- Do NOT add a `## Behavioral Specification` section to `SYSTEMS_PLAN.md`.
- Do NOT initialize `traceability.yml`.
- Do NOT archive specs to `.ai-state/specs/` at end-of-feature.
- Acceptance Criteria stays — write 3-7 testable AC bullets, no REQ IDs. If the architect
  was skipped, the planner emits light ACs; if the planner was also skipped, the verifier
  derives what to check from the diff.

### ADR ceremony — deferred by default

- Do NOT auto-write ADR fragments under `.ai-state/decisions/drafts/`.
- IF the user explicitly says "write an ADR for X" — use the direct-tier path
  (`.ai-state/decisions/<NNN>-<slug>.md`, no fragment, no draft lifecycle).
- The `remind_adr.py` hook's advisory warning is silenced; its check still runs.

### Test discipline — RELAXED

- Implementer writes production code AND a happy-path smoke test in the same step.
- test-engineer is invoked only on explicit request (property/contract/integration suites).
- Tests still run; `pytest` failures still surface honestly — but a red test is a WARN,
  not a FAIL, and does NOT gate the verifier or the pipeline. A happy-path smoke test is
  still expected; its ABSENCE for new behavior is also a WARN.

### Slim artifact shapes

- **Architect (`SYSTEMS_PLAN.md`):** Surface Assumptions, Registered Objections, Goals &
  Non-Goals, Context (1 para), Architecture (Overview, Components, Data Flow if
  non-trivial), Acceptance Criteria, Risks (top 3), Out-of-scope. Skip: Behavioral
  Specification, ADR fragment, tech-debt sweep, Tier-2 Stakeholder Review, DESIGN.md /
  docs/architecture.md updates.
- **Planner (`IMPLEMENTATION_PLAN.md`):** numbered steps + file paths + per-step
  acceptance. WIP.md and LEARNINGS.md still produced. No traceability.yml, no REQ IDs,
  no paired test-engineer step required. Coarser decomposition (3-5 steps for 4-8 files
  is fine). If the architect was skipped, add a short top-level "what 'done' means" list.
- **Verifier (`VERIFICATION_REPORT.md`):** Phases 1, 2, 3 (AC), 5 (lint/typecheck),
  5.5 (Behavioral Contract), 10 (test status), 12 (report). Auto-skip 4, 7, 8, 9, 11.
  FAIL: lint/typecheck/behavioral-contract failure. WARN (not FAIL): a failing or
  absent test. The report header records the entry point and the skipped stages.

### To exit hackathon mode

Set `PRAXION_HACKATHON_MODE=0`, delete this `## Hackathon Mode` block from `CLAUDE.md`,
remove the `hackathon` preset from `.claude/praxion-rules.yaml`, and stop launching via
the `praxion-hackathon` wrapper. Subsequent sessions resume the full 5-tier process.
```

This block is installed into the user project's `CLAUDE.md` by Phase 5b **only when hackathon mode is enabled**. It is guarded by `grep -q '^## Hackathon Mode$' CLAUDE.md` (Phase 5b artifact 2 predicate). When installed, it activates the Hackathon Spine in the project's agent sessions. The fence is kept byte-identical to `claude/canonical-blocks/hackathon-mode.md` by `scripts/sync_canonical_blocks.py`.

## §Project Essentials Block

<!-- canonical-source: claude/canonical-blocks/project-essentials.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Working in this project

This `CLAUDE.md` is the **index**; `docs/` and the skills it points to are the **library** — read the index, follow the links the task needs. When I correct you, propose a durable rule for review (a memory entry, a `CLAUDE.md` or rule edit, or a skill note) so the correction outlasts this session.

### Verification

After every change, run these in order — fix at each step before moving on:

1. `<typecheck command>`
2. `<test command>`
3. `<lint command>`
4. `<build command>`

### Frequent operations

You'll most often be asked to:

- `<list 3–5 of this project's most common task intents>`
```

The fenced content above is a **template** — `/onboard-project` Phase 6 appends it and then fills the `<placeholders>` from the project's config (see §Phase 6 Action step 3); `/new-project` fills them at scaffold time. The fence is kept byte-identical to `claude/canonical-blocks/project-essentials.md` by `scripts/sync_canonical_blocks.py`; the `<placeholders>` are intentional and must survive the sync.

## §Obsidian Integration Block

<!-- canonical-source: claude/canonical-blocks/obsidian-integration.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Obsidian Integration

This project is configured for **Obsidian integration**: the vault lives inside the project repository, and the agent has access to kepano/obsidian-skills for vault navigation and note manipulation. Kepano skills are discovered automatically once `obsidian@obsidian-skills` is installed at user scope. If the plugin is absent from a session, run `./install.sh code` in your Praxion checkout first.

### CLI Allowlist

The `obsidian` CLI is available for file CRUD, search, link analysis, properties, tags, outline, structured queries (`base:query`), templates, and read-only sync/publish diagnostics.

**Allowed subcommands include:** `read`, `create`, `append`, `prepend`, `delete` (without `--permanent`), `search`, `search:context`, `backlinks`, `links`, `unresolved`, `orphans`, `deadends`, `outline`, `tags`, `tag`, `properties`, `base:query`, `daily`, `daily:read`, `daily:append`, `template:read`, `template:insert`, `unique`, `publish:list`, `publish:status`, `sync:status`, `sync:history`, `sync:read`.

**Denied subcommands — blocked at the tool-permission layer:**

| Subcommand | Reason |
|---|---|
| `obsidian eval` (any args) | Executes arbitrary JavaScript in the renderer — remote code execution risk |
| `obsidian plugin:install`, `plugin:enable`, `plugin:disable`, `plugin:uninstall` | Plugin lifecycle commands expose OS-level attack surface |
| `obsidian theme:set`, `theme:install` | Theme code runs with full app privileges |
| `obsidian delete --permanent` | Bypasses Obsidian's trash; operation is unrecoverable |
| `obsidian move`, `rename` | Renaming/moving a tracked file through Obsidian can rewrite link bodies across the repo and hides the rename from git. Use `git mv` so git tracks the rename and project link conventions stay intact. |

**Why you may see permission errors:** The denied subcommands above are enforced mechanically via `.claude/settings.json` `permissions.deny` rules written by the onboarding step. If a `Bash(obsidian ...)` call is rejected by the harness, check this list — the subcommand is intentionally blocked, not broken. Use an allowed alternative or ask the user to perform the operation manually.

### Link safety

Because the repository doubles as a vault, Obsidian's default link behavior is pinned so vault tooling cannot corrupt project-artifact links (standard Markdown `[text](path)` links and ADR id cross-references). The onboarding step writes two keys into `.obsidian/app.json` (merged non-destructively, committed so every clone inherits them):

- `useMarkdownLinks: true` — any link Obsidian authors uses Markdown `[text](path)` form, never `[[wikilink]]` (which Praxion's docs and cross-reference validators do not use).
- `alwaysUpdateLinks: false` — Obsidian never auto-rewrites links across files when a file is renamed or moved.

This is why `move`/`rename` are denied above: file renames go through `git mv`, so git tracks them and no link bodies are silently rewritten.

### Opt-out

Obsidian integration can be skipped by passing `--no-obsidian` to `/onboard-project` or `/new-project`. To retrofit integration later, re-run `/onboard-project` — it is idempotent on Phase 8d.

### Reference

See `docs/obsidian-integration.md` for installation, configuration, troubleshooting, and the full allowlist rationale.
```

This block is installed into the user project's `CLAUDE.md` by Phase 8d sub-step 8d.5. It is guarded by `grep -q '^## Obsidian Integration$' CLAUDE.md`. The fence is kept byte-identical to `claude/canonical-blocks/obsidian-integration.md` by `scripts/sync_canonical_blocks.py`.

## §Idempotency Predicates — per-phase contracts

| Phase | Predicate (skip if true) |
|-------|--------------------------|
| 1 | `grep -q '^# AI assistants$' .gitignore` |
| 2 | Per-file: `test -e .ai-state/<file>` for each of the four targets — skip files individually |
| 3 | `grep -qF '.ai-state/memory.json merge=memory-json' .gitattributes` AND `git config --get merge.memory-json.driver` returns a value containing `i-am` AND same for `observations-jsonl` |
| 4 | `readlink .git/hooks/pre-commit` resolves to a Praxion-shipped file (or the file is a script containing `check_id_citation_discipline`) AND each of `readlink .git/hooks/{post-merge,post-commit,post-checkout}` resolves to a path containing `/i-am/` (target ending in `git-finalize-hook.sh`, or the legacy `git-post-merge-hook.sh` for the post-merge slot only) |
| 5 | All four `PRAXION_DISABLE_*` keys present under `.env` in `.claude/settings.json` (any value) |
| 5b | Entire phase: `PRAXION_HACKATHON_MODE=1` present under `.env` in `.claude/settings.json`; or user picks `Skip — keep full ceremony` at Gate 5b. Per-artifact: 5b.1 — `PRAXION_HACKATHON_MODE` key present in `.claude/settings.json` env; 5b.2 — `grep -q '^## Hackathon Mode$' CLAUDE.md`; 5b.3 — `grep -q 'hackathon' .claude/praxion-rules.yaml 2>/dev/null`; 5b.4 — `test -f scripts/praxion-hackathon`; 5b.5 — `test -f .claude/hackathon-directive.md`; 5b.6 — `test -f .claude/hackathon-settings.json` |
| 6 | `grep -q '^## <heading>$' CLAUDE.md` per block — checked individually for each of the five: `## Agent Pipeline`, `## Compaction Guidance`, `## Behavioral Contract`, `## Praxion Process`, `## Working in this project` (plus `## Hackathon Mode` if Phase 5b was enabled) |
| 7 | None — phase 7 is advisory and always runs |
| 8 | `test -e .ai-state/DESIGN.md` OR `test -e docs/architecture.md` (skip phase if either doc exists — covers re-runs and greenfield-followed-by-onboard); also skipped if the user picks `Skip` at Gate 8 |
| 8b | User picks `Skip AaC` (or `Run all rest`) at Gate 8b — skips entire phase. Per-sub-step: 8b.1 — arch doc contains `aac:generated` or `aac:authored`; 8b.2 — `test -d fitness/`; 8b.3 — `grep -q 'check_aac_golden_rule\|Block D' .git/hooks/pre-commit`; 8b.4 — `test -e .github/workflows/architecture.yml`; 8b.5 — `test -d docs/diagrams/` |
| 8c | No ML signals detected (skip entire phase). User picks `Skip ML scaffold` at Gate 8c — skips entire phase. Per-sub-step: 8c.1 — `test -d .ai-state/experiments/`; 8c.2 — `grep -q '# ML training checkpoints' .gitignore`; 8c.3 — `test -e .ai-state/gpu_budget.yaml`; 8c.4 — `test -e program.md`; 8c.5 — none (always prints) |
| 8d | User picks `Skip` at Gate 8d — skips entire phase. Per-sub-step: 8d.1 — `grep -q '^# Obsidian$' .gitignore`; 8d.2 — `command -v claude >/dev/null 2>&1` (if absent, skip 8d.3–8d.6); 8d.3 — `claude plugin list 2>/dev/null | grep -q "obsidian@obsidian-skills"` (if absent, skip 8d.4–8d.6); 8d.4 — `jq -e '(.useMarkdownLinks == true) and (.alwaysUpdateLinks == false)' .obsidian/app.json` exits 0 (both link-safety keys pinned); 8d.5 — `grep -q '^## Obsidian Integration$' CLAUDE.md`; 8d.5b — all required deny entries present (subset check: `jq -e --argjson req '[...]' '($req - (.permissions.deny // [])) | length == 0' .claude/settings.json`) |
| 9 | None — terminal phase always runs |

**Re-running the command** on an already-onboarded project should print mostly `skipped (already onboarded)` lines in Phase 9's summary. The only writes on a clean re-run come from Phase 7 (which writes nothing — only prints) and Phase 9 (which only stages changed files). Phase 8 is naturally idempotent — once `.ai-state/DESIGN.md` exists, any subsequent re-run skips. Future *updates* to architecture docs come from feature pipelines (`systems-architect` updates them in Phase 4 of the agent pipeline), not from re-running `/onboard-project`.

**Test for idempotency**: run `/onboard-project`, accept all gates, then re-run `/onboard-project`. The second run should produce zero `git diff` output and zero new `git config` entries. If either runs, the predicate for that phase has a bug.
