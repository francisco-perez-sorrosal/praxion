---
name: onboard-project
description: Onboard an existing project to the Praxion ecosystem (gitignore, .ai-state/, hooks, settings, CLAUDE.md)
allowed-tools: [Bash(git:*), Bash(grep:*), Bash(find:*), Bash(test:*), Bash(ln:*), Bash(mkdir:*), Bash(command:*), Bash(jq:*), Bash(cat:*), Bash(python3:*), Read, Write, Edit, Glob, Grep, AskUserQuestion, Task]
---


Onboard the **current existing** project to work cleanly with the Praxion plugin (`praxion`). This is the existing-project counterpart to `/new-project` (greenfield). The command runs phased, with `AskUserQuestion` gates between phases — each gate explains what's about to happen so you learn the shape, not just observe it. A one-way **Run all rest** option on every gate skips the remaining gates for users who have onboarded a project before.

## Sections

1. §Pre-flight — repo + plugin detection, no writes
2. §Flow — the nine sequential phases (Phase 0 pre-flight diagnostic + Phases 1–9 with writes)
3. §Phase Gates — gate definitions, escape hatch, format
4. §Idempotency Predicates — per-phase contracts

**Satellite files** (loaded on-demand):

- [references/phases-core.md](references/phases-core.md) -- always-on phase bodies: 0.5, 1, 2, 3, 4, 5, 5b, 6, 7, 9
- [references/phases-optional.md](references/phases-optional.md) -- opt-in phase bodies: 8, 8b, 8c, 8d, 8e
- [references/claude-md-blocks.md](references/claude-md-blocks.md) -- the 7 canonical `CLAUDE.md` block bodies
- [references/seed-pipeline.md](references/seed-pipeline.md) -- greenfield-only seed-pipeline content (from the retiring `/new-project` command)

## §Pre-flight

Before any phase runs, gather facts. Pre-flight writes nothing — it produces a diagnostic report you print to chat so the user knows what you found.

1. **Git repo check.** `git rev-parse --git-dir`. If it fails, abort with: `This command must be run inside a git repository. Run 'git init' first if this is a new project.` Exit without writing.
2. **Project root.** `git rev-parse --show-toplevel`. All paths in subsequent phases are relative to this root.
3. **Plugin install scope.** Read `~/.claude/plugins/installed_plugins.json` (use `jq -r '.plugins["praxion@bit-agora"]'`). Three outcomes:
   - **User scope** — entry exists with `scope: "user"`. Capture `installPath` (used for hook resolution in §Phase 4) and `version` (the live plugin version, used for drift detection in §Phase 3, §Phase 4, and the §Phase 9 onboard manifest). Capture `version` from the entry's `version` field, or fall back to the version segment of `installPath` (`.../praxion/<version>`).
   - **Project scope** — entry exists with `scope: "project"` and `projectPath` matching the current project root. Capture `installPath` and `version` as above.
   - **Not installed** — emit a warning: `The praxion plugin is not installed. Install it via 'claude plugin install praxion@bit-agora' or './install.sh code' from a Praxion checkout. The onboarding can still run, but git hooks (Phase 4) will be skipped because they need the plugin's scripts/.` Set a flag to skip Phase 4.
4. **Stack detection.** Probe for stack signals in the project root and capture which apply (used in §Phase 7 to recommend tooling):
   - Python: `pyproject.toml` OR `setup.py` OR `setup.cfg` OR `requirements.txt`
   - JavaScript/TypeScript: `package.json`
   - Rust: `Cargo.toml`
   - Go: `go.mod`
4b. **ML signal detection.** Probe for ML/AI training signals and set an `ml_signals_detected` flag (used to set Gate 8c's default and skip Phase 8c when absent). Signals:
   - `test -f train.py` OR `test -f prepare.py` → Python training entry point detected
   - `grep -qE 'torch|jax|tensorflow' pyproject.toml requirements.txt setup.py Pipfile 2>/dev/null` → ML framework dependency declared
   - `test -f program.md && grep -qiE 'train|checkpoint|epoch|gpu|loss|dataset|ml-training' program.md` → project-local ML meta-prompt present (content-gated: a bare `program.md` with no training vocabulary is **not** an ML signal — the filename is generic enough that mere existence would false-positive on non-ML projects)
   Set `ml_signals_detected=true` if ANY of these succeeds; `ml_signals_detected=false` otherwise. Record in pre-flight report.
4c. **Diagram-toolchain probes.** Probe both diagram toolchain binaries and record their presence in the pre-flight report. Do NOT block onboarding on missing binaries.
   - `command -v likec4 >/dev/null 2>&1` → record `likec4` present/absent; if present, capture `likec4 --version`
   - `command -v d2 >/dev/null 2>&1` → record `d2` present/absent; if present, capture `d2 --version`
   If either is missing AND the project contains `**/diagrams/*.c4` files (or the user opts into Phase 8 architecture baseline), emit in the pre-flight report: "Install LikeC4 + D2 for architectural diagram regeneration — see `docs/architecture-diagrams.md`."
4d. **`CLAUDE.md` presence.** `test -e CLAUDE.md` → record present/absent. When absent, §Phase 0.5 bootstraps a `CLAUDE.md` before Phase 1 so the block-append phases (5b, 6, 8d) always have a target. Record in the pre-flight report.
5. **Prior-onboarding signals.** Check for any of:
   - `## Agent Pipeline` heading in `CLAUDE.md` (re-onboard scenario — Phase 6 delegates the four core blocks to `refresh_claude_blocks.py`'s absent/current/stale/modified classification instead of a binary append-or-skip)
   - `.ai-state/` directory exists with non-empty contents (re-onboard or pipeline-active)
   - `.git/hooks/post-merge`, `.git/hooks/post-commit`, and `.git/hooks/post-checkout` symlinks all pointing at the **live** `${PLUGIN_INSTALL_PATH}/scripts/git-finalize-hook.sh` (Phase 4 already done). A symlink pointing at a *different* `/praxion/<version>/` path is a stale pin from a prior plugin version — Phase 4 will re-point it, so record it as "needs upgrade", not "already done".
6. **Plugin-source-repo guard (G1) and greenfield-shape guard.** Both predicates, abort messages, and rationale are specified once in [references/detection.md](references/detection.md) — apply them here rather than restating them. This step's job is to run detection.md's two hard guards, in order, before any phase runs.
7. **Print the pre-flight report** to chat. Format:
   ```
   Pre-flight report:
     project root:        <path>
     plugin scope:        user | project | not installed (flag: skip-phase-4)
     plugin install path: <path or n/a>
     stacks detected:     [python, javascript, ...] | none
     ml signals:          detected (train.py|torch/jax/tensorflow|program.md) | none
     CLAUDE.md:           present | absent (will bootstrap before Phase 1 — see §Phase 0.5)
     prior onboarding:    yes (CLAUDE.md heading found) | no | partial (<list>)
   ```

After printing: **if `CLAUDE.md` is absent, run §Phase 0.5 (CLAUDE.md bootstrap) before §Flow** — it guarantees a `CLAUDE.md` exists so the block-append phases (5b, 6, 8d) never silently skip the Praxion payload. When `CLAUDE.md` is present, §Phase 0.5 is a complete no-op. Then proceed to §Flow. The first phase gate (Gate 1) is the entry gate — it carries both the orientation overview and the Phase 1 specifics, so the user is not double-prompted before the first write.

## §Flow

Execute these phases in order. Each phase honors §Idempotency Predicates — re-running on an already-onboarded project must be a no-op for that phase.

| Phase | Action | Predicate (skip if already done) |
|-------|--------|----------------------------------|
| 0.5 | **(conditional — only when `CLAUDE.md` is absent)** Bootstrap a `CLAUDE.md` so the block-append phases have a target: prefer `/init`, else generate an init-equivalent `CLAUDE.md` inline from the codebase | `test -e CLAUDE.md` (present → skip the entire phase, no gate, no write) |
| 1 | Append AI-assistants block to `.gitignore` | Block detected by `# AI assistants` header line |
| 2 | Create the `.ai-state/` skeleton (files enumerated in §Phase 2) | Each file's existence checked individually |
| 3 | Append `.gitattributes` entries + register merge drivers via `git config`; clean up retired drivers | Entries detected by exact-line match; drivers detected via `git config --get`; **version-aware** — a `/praxion/` driver pinned to a non-live path is re-registered, not skipped |
| 4 | Symlink pre-commit + the three finalize hooks (post-merge, post-commit, post-checkout) (skip if `skip-phase-4` flag) | Symlinks detected via `readlink`; **version-aware** — a finalize-hook target pinned to a non-live `/praxion/<version>/` path is re-pointed, not skipped (pre-commit is runtime-resolving, never stale) |
| 5 | Write `.claude/settings.json`: chosen `PRAXION_DISABLE_*` flags (5a) + the `permissions.allow` baseline (5b) | Evaluated per sub-step, never phase-wide (see §Phase 5); existing keys preserved unless the user explicitly overrides |
| 5b | Hackathon mode gate: write six artifacts when enabled | `PRAXION_HACKATHON_MODE=1` present in `.claude/settings.json` env (skip if already set); or user picks `Skip — keep full ceremony` (default) at Gate 5b |
| 6 | Refresh Agent Pipeline + Compaction Guidance + Behavioral Contract + Praxion Process blocks via `refresh_claude_blocks.py --apply`, then append the Project Essentials block, to `CLAUDE.md` (+ `## Hackathon Mode` when Phase 5b enabled it) | `refresh_claude_blocks.py`'s own absent/current/stale/modified classification for the four core blocks (no heading-check); `## Working in this project` heading detection for Project Essentials |
| 7 | Print companion-CLI install commands (advisory) | None — purely informational |
| 8 | Architecture baseline — delegate to `systems-architect` in baseline mode → `.ai-state/DESIGN.md` + `docs/architecture.md` (+ optional ADR draft) | `test -e .ai-state/DESIGN.md` OR `test -e docs/architecture.md` (skip if either exists) OR user picks "Skip" at Gate 8 |
| 8b | AaC tier install — fence seed, `fitness/` scaffold, golden-rule Block D, `architecture.yml` workflow, `docs/diagrams/` scaffold | User picks "Skip AaC" (default) at Gate 8b; or per-sub-step predicates (see §Phase 8b) |
| 8c | ML/AI training scaffold — experiment tracking config, checkpoint `.gitignore` block, GPU budget declaration, `program.md` template, mode callout | No ML signals detected (skip) OR user picks "Skip" at Gate 8c; per-sub-step predicates (see §Phase 8c) |
| 8d | Obsidian integration — `.gitignore` Obsidian block, verify `obsidian@obsidian-skills` plugin install, `CLAUDE.md` Obsidian Integration block, `settings.json` deny entries | User picks "Skip" at Gate 8d; per-sub-step predicates (see §Phase 8d) |
| 8e | Code-quality baseline — universal `.editorconfig` + pre-commit config + `CONTRIBUTING.md` + per-detected-stack linter/formatter/type-check config + dependency-scanning config + ci-autofix caller/policy installed from canonical assets (never overwriting existing config) | User picks "Skip" at Gate 8e; per-sub-step predicates (see §Phase 8e) |
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
  - Two-option `Generate from codebase` / `Minimal stub` (default: `Generate from codebase`) — Gate 0.5 (conditional; fires before Gate 1 only when `CLAUDE.md` is absent)
  - Two-option `Continue` / `Run all rest` — gates 1, 2, 3, 4, 6, 7
  - Multi-select toggles — Gate 5 (see §Phase 5)
  - Two-option `Enable hackathon mode` / `Skip — keep full ceremony` (default: Skip) — Gate 5b (see §Phase 5b); gate is suppressed (auto-default Skip) when `no-more-gates` flag is set; auto-default Enable when `--hackathon` was passed
  - Three-option `Run baseline now` (default) / `Skip` / `Run all rest` — Gate 8 (see §Phase 8)
  - Three-option `Skip AaC` (default) / `Install AaC tier` / `Run all rest` — Gate 8b (see §Phase 8b)
  - Three-option `Skip ML scaffold` (default for non-ML) / `Run ML scaffold` / `Run all rest` — Gate 8c (see §Phase 8c); default is `Run ML scaffold` when ML signals detected
  - Three-option `Install Obsidian integration (default)` / `Skip` / `Run all rest` — Gate 8d (see §Phase 8d)
  - Three-option `Install code-quality baseline (default)` / `Skip` / `Run all rest` — Gate 8e (see §Phase 8e)

**Gate map.** Gate 0.5 (conditional) fires before Gate 1 **only when `CLAUDE.md` is absent** — it confirms how the bootstrap creates the missing `CLAUDE.md`; when `CLAUDE.md` is present it does not fire at all (zero added friction on the common path). Gate 1 doubles as the entry gate — its headline carries both the high-level orientation and the Phase 1 specifics, so the user is not double-prompted before the first phase. Gates 2–8 fire one-per-phase as expected. Gate 5b fires between Phase 5 and Phase 6.

| Gate | Fires before phase | Headline |
|------|-------------------|----------|
| 0.5 | before 1 (only when `CLAUDE.md` is absent) | `No CLAUDE.md found. The Praxion blocks (Phase 6) need a CLAUDE.md to live in. I'll create one — "Generate from codebase" runs /init (or generates an init-equivalent CLAUDE.md inline if /init cannot be invoked here) so it describes your actual code; "Minimal stub" writes just a header you fill in later. Pick:` |
| 1 | 1 (entry + phase 1) | `I'll walk you through 9 phases that turn this project into a Praxion-aware repo: gitignore hygiene, .ai-state/ skeleton, merge drivers, git hooks, .claude/settings.json toggles, CLAUDE.md blocks, optional CLI tools, an opt-in architecture baseline, and a verification handoff. First up — Phase 1 of 9: I append a Praxion AI-assistants block to your .gitignore. Without these entries, advisory locks, temporary snapshots, per-machine settings, and worktrees can leak into commits. Idempotent — re-runs are no-ops. Continue?` |
| 2 | 2 | `Phase 2 of 9: I create the .ai-state/ skeleton — decisions/drafts/, DECISIONS_INDEX.md, TECH_DEBT_LEDGER.md, calibration_log.md, plus a static redirect stub at .ai-state/metrics_reports/index.html that points to praxion-dashboard for interactive charts (the METRICS_REPORT_*.md files in the same directory are available for offline reading). Each is created only if missing; existing files are never overwritten. Continue?` |
| 3 | 3 | `Phase 3 of 9: I add a merge-driver entry to .gitattributes and run 'git config' to register a Python-based semantic merge driver for .ai-state/observations.jsonl. Without this, concurrent edits get corrupted by line-based merge. Continue?` |
| 4 | 4 | `Phase 4 of 9: I install four git hooks — pre-commit (id-citation discipline) and three finalize hooks (post-merge, post-commit, post-checkout) all sharing one multiplexed dispatcher. The trio guarantees that draft ADRs landing on main via any path — ff merge, direct commit, rebase, fresh clone, branch reset — eventually promote to stable dec-NNN. Symlinks resolve to the plugin scripts so updates flow automatically. Continue?` |
| 5 | 5 | (Multi-select on PRAXION_DISABLE_* toggles — see §Phase 5 for option text) |
| 5b | 5b | (Two-option pick — `Enable hackathon mode` / `Skip — keep full ceremony` (default: Skip). Headline: `Phase 5b: Hackathon mode. I can install the six hackathon mode artifacts: set PRAXION_HACKATHON_MODE=1 in .claude/settings.json, append the ## Hackathon Mode block to CLAUDE.md, add the hackathon preset to .claude/praxion-rules.yaml, and create scripts/praxion-hackathon, .claude/hackathon-directive.md, and .claude/hackathon-settings.json. Hackathon mode replaces the 5-tier selector with a flexible-entry Hackathon Spine and relaxes test/SDD/ADR ceremony. All six installs are idempotent. Skip if you want the full Praxion ceremony. Pick:`) |
| 6 | 6 | `Phase 6 of 9: I refresh four blocks in CLAUDE.md via a shipped version manifest — the Agent Pipeline (how to use Praxion's subagents), Compaction Guidance (what to preserve when the conversation compacts), Behavioral Contract reminder, and Praxion Process (the tier-driven pipeline principle + rule-inheritance obligation) — appending each if absent, silently updating it if stale, and leaving it untouched (with a pointer to /refresh-claude-blocks) if you've customized it. I also append Working in this project (your verification commands + frequent operations + how corrections become durable rules — I fill the project-specific bits from your config), idempotent via heading detection. (If Phase 5b enabled hackathon mode, the ## Hackathon Mode block was already appended.) Continue?` |
| 7 | 7 | `Phase 7 of 9: I check whether chub (external API docs), scc (SLOC counter), and uv (Python tooling) are installed. I won't install anything — I'll print one-line install commands you can run later if useful. Continue?` |
| 8 | 8 | (Three-option pick — see §Phase 8 for the exact AskUserQuestion form. Default is `Run baseline now`. Headline: `Phase 8 of 9: Architecture baseline. I delegate to systems-architect in baseline mode to read your codebase and produce .ai-state/DESIGN.md (architect-facing, design-target) + docs/architecture.md (developer-facing, navigation guide). These docs become the architectural anchor for every future feature pipeline. Takes ~5–15 minutes for a medium project. Skip if you'd rather wait for your first feature pipeline to produce them. Pick:`) |
| 8b | 8b | (Three-option pick — see §Phase 8b for the exact AskUserQuestion form. Default is `Skip AaC`. Headline: `Phase 8b: AaC tier install. I can install the Architecture-as-Code surfaces for this project: fence-region examples in your architecture docs, fitness/ scaffold for architectural fitness tests, a golden-rule pre-commit block, a .github/workflows/architecture.yml CI workflow, and a docs/diagrams/ directory stub. All five installs are idempotent — re-running is safe. The AaC convention requires the praxion plugin to be installed for enforcement to fire. Sentinel-only surfaces (traceability convention, sentinel AC dimension) need no per-project install. Pick:`) |
| 8c | 8c | (Three-option pick — see §Phase 8c for the exact AskUserQuestion form. Default is `Skip ML scaffold` for non-ML projects; default is `Run ML scaffold` when ML signals are detected. Headline: `Phase 8c: ML/AI training scaffold. I detected signals that this is an ML/AI training project. I can scaffold: experiment tracking config (.ai-state/experiments/), checkpoint directory entries in .gitignore, compute-budget declaration (.ai-state/gpu_budget.yaml), and a program.md template at repo root. All scaffolding is idempotent. Pick:`) |
| 8d | 8d | (Three-option pick — see §Phase 8d for the exact AskUserQuestion form. Default is `Install Obsidian integration`. Headline: `Phase 8d: Obsidian integration. I can wire this project for Obsidian vault-as-repo: a .gitignore Obsidian block, a check that the obsidian@obsidian-skills marketplace plugin is installed at user scope, an ## Obsidian Integration block in CLAUDE.md, and permissions.deny entries in .claude/settings.json blocking the dangerous obsidian CLI subcommands. All installs are idempotent. Pick:`) |
| 8e | 8e | (Three-option pick — see §Phase 8e for the exact AskUserQuestion form. Default is `Install code-quality baseline`. Headline: `Phase 8e: Code-quality baseline. Using the stack I detected, I install the conventions that keep code consistent and that agent-readiness checks for: a universal .editorconfig; your language's linter + formatter config (Python → [tool.ruff] in pyproject.toml; JS/TS → biome.json, or eslint.config.mjs + prettierrc.json for frameworks; Rust → rustfmt.toml + Cargo.toml [lints] tables + rust-toolchain.toml); a static type-check config ([tool.mypy] or strict tsconfig.json); a .pre-commit-config.yaml wiring linter + formatter + a secret scanner; and a CONTRIBUTING.md filled from your project's commands. All sourced from Praxion's canonical baseline assets and idempotent — I never overwrite an existing config. Pick:`) |


## §Idempotency Predicates — per-phase contracts

| Phase | Predicate (skip if true) |
|-------|--------------------------|
| 1 | `grep -q '^# AI assistants$' .gitignore` |
| 2 | Per-file: `test -e .ai-state/<file>` for every target listed in §Phase 2 — skip files individually, never as a phase |
| 3 | `grep -qF '.ai-state/observations.jsonl merge=observations-jsonl' .gitattributes` AND `git config --get merge.observations-jsonl.driver` returns a value containing `praxion` |
| 4 | `readlink .git/hooks/pre-commit` resolves to a Praxion-shipped file (or the file is a script containing `check_id_citation_discipline`) AND each of `readlink .git/hooks/{post-merge,post-commit,post-checkout}` resolves to a path containing `/praxion/` (target ending in `git-finalize-hook.sh`, or the legacy `git-post-merge-hook.sh` for the post-merge slot only) |
| 5 | Per-sub-step, never phase-level: 5a — `PRAXION_DISABLE_OBSERVABILITY` key present under `.env` in `.claude/settings.json` (any value); 5b — every required allow entry present (subset check: `jq -e --argjson req '[...]' '($req - (.permissions.allow // [])) \| length == 0' .claude/settings.json`) |
| 5b | Entire phase: `PRAXION_HACKATHON_MODE=1` present under `.env` in `.claude/settings.json`; or user picks `Skip — keep full ceremony` at Gate 5b. Per-artifact: 5b.1 — `PRAXION_HACKATHON_MODE` key present in `.claude/settings.json` env; 5b.2 — `grep -q '^## Hackathon Mode$' CLAUDE.md`; 5b.3 — `grep -q 'hackathon' .claude/praxion-rules.yaml 2>/dev/null`; 5b.4 — `test -f scripts/praxion-hackathon`; 5b.5 — `test -f .claude/hackathon-directive.md`; 5b.6 — `test -f .claude/hackathon-settings.json` |
| 6 | `refresh_claude_blocks.py`'s own absent/current/stale/modified classification for the four core blocks (`## Agent Pipeline`, `## Compaction Guidance`, `## Behavioral Contract`, `## Praxion Process` — no heading-check predicate); `grep -q '^## Working in this project$' CLAUDE.md` for the Project Essentials block (plus `## Hackathon Mode` if Phase 5b was enabled) |
| 7 | None — phase 7 is advisory and always runs |
| 8 | `test -e .ai-state/DESIGN.md` OR `test -e docs/architecture.md` (skip phase if either doc exists — covers re-runs and greenfield-followed-by-onboard); also skipped if the user picks `Skip` at Gate 8 |
| 8b | User picks `Skip AaC` (or `Run all rest`) at Gate 8b — skips entire phase. Per-sub-step: 8b.1 — arch doc contains `aac:generated` or `aac:authored`; 8b.2 — `test -d fitness/`; 8b.3 — `grep -qe check_aac_golden_rule -e 'Block D' .git/hooks/pre-commit` (repeated `-e` rather than an alternation: a pipe inside a table cell is either a cell delimiter or, escaped, renders as a bare `|` — and BRE and ERE read the escaped and unescaped forms in opposite directions, so no single alternation is correct both as authored and as rendered); 8b.4 — `test -e .github/workflows/architecture.yml`; 8b.5 — `test -d docs/diagrams/` |
| 8c | No ML signals detected (skip entire phase). User picks `Skip ML scaffold` at Gate 8c — skips entire phase. Per-sub-step: 8c.1 — `test -d .ai-state/experiments/`; 8c.2 — `grep -q '# ML training checkpoints' .gitignore`; 8c.3 — `test -e .ai-state/gpu_budget.yaml`; 8c.4 — `test -e program.md`; 8c.5 — none (always prints) |
| 8d | User picks `Skip` at Gate 8d — skips entire phase. Per-sub-step: 8d.1 — `grep -q '^# Obsidian$' .gitignore`; 8d.2 — `command -v claude >/dev/null 2>&1` (if absent, skip 8d.3–8d.6); 8d.3 — `claude plugin list 2>/dev/null | grep -q "obsidian@obsidian-skills"` (if absent, skip 8d.4–8d.6); 8d.4 — `jq -e '(.useMarkdownLinks == true) and (.alwaysUpdateLinks == false)' .obsidian/app.json` exits 0 (both link-safety keys pinned); 8d.5 — `grep -q '^## Obsidian Integration$' CLAUDE.md`; 8d.5b — all required deny entries present (subset check: `jq -e --argjson req '[...]' '($req - (.permissions.deny // [])) | length == 0' .claude/settings.json`) |
| 9 | None — terminal phase always runs |

**Re-running the command** on an already-onboarded project should print mostly `skipped (already onboarded)` lines in Phase 9's summary. The only writes on a clean re-run come from Phase 7 (which writes nothing — only prints) and Phase 9 (which only stages changed files). Phase 8 is naturally idempotent — once `.ai-state/DESIGN.md` exists, any subsequent re-run skips. Future *updates* to architecture docs come from feature pipelines (`systems-architect` updates them in Phase 4 of the agent pipeline), not from re-running `/onboard-project`.

**Test for idempotency**: run `/onboard-project`, accept all gates, then re-run `/onboard-project`. The second run should produce zero `git diff` output and zero new `git config` entries. If either runs, the predicate for that phase has a bug.
