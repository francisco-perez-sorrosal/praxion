# Existing-Project Onboarding

Reference for the `/onboard-project` slash command — the entry point that retrofits an **existing repository** (one that already has code) with the Praxion ecosystem's surfaces. This is the existing-project counterpart to [Greenfield Project Onboarding](greenfield-onboarding.md), which uses `new_project.sh` + `/new-project` to scaffold from an empty directory.

> **Two onboarding paths.** Pick by what's in the directory you start from:
>
> | Starting point | Path | User-facing doc |
> |----------------|------|-----------------|
> | Empty directory | `new_project.sh` + `/new-project` | [greenfield-onboarding.md](greenfield-onboarding.md) |
> | Existing project with code | `/onboard-project` | this doc |
>
> Both paths converge on the same end state. The greenfield path actually ends by chaining to `/onboard-project` for the remaining surfaces — there's a single source of truth for what "Praxion-onboarded" means.

## Contents

- [Prereqs](#prereqs)
- [How to run it](#how-to-run-it)
- [The nine phases](#the-nine-phases)
- [What gets created](#what-gets-created)
- [Architecture baseline (Phase 8)](#architecture-baseline-phase-8)
- [Idempotency contract](#idempotency-contract)
- [Troubleshooting](#troubleshooting)
- [Limits and known issues](#limits-and-known-issues)

## Prereqs

- `claude` binary on PATH — install Claude Code from `https://claude.com/product/claude-code`
- The current directory is a git repository (`git init` if not, before running the command)
- The `i-am` plugin installed in the user-scope plugin registry (`./install.sh code` from a Praxion checkout, or `claude plugin install i-am@bit-agora`). Project-scope installs are also detected. Without the plugin, the command still runs but **Phase 4 (git hooks) is skipped** — the hooks need the plugin's `scripts/` directory to resolve.
- Optional: `jq` on PATH (the pre-commit hook uses it to resolve the plugin install path at hook-run time). Most package managers ship it; install via `brew install jq` on macOS.

## How to run it

Inside an active Claude Code session in your project root:

```
/onboard-project
```

The command runs phased — each phase pauses with an `AskUserQuestion` gate that explains *what* is about to happen and *why* before any write occurs. Pick **Continue** to proceed phase-by-phase, or **Run all rest** to skip remaining gates and run autonomously (the choice is one-way for this command run; useful when you've onboarded a project before and want it to play through).

If `AskUserQuestion` is unavailable (headless invocation, tool error), the gates degrade to printed headlines and the command proceeds without blocking.

## The nine phases

| Phase | Action | Files / settings touched | Idempotent |
|-------|--------|--------------------------|-----------|
| 0 | **Pre-flight** — diagnostic only | none (prints report) | n/a |
| 1 | **`.gitignore` hygiene** — append the canonical 10-line AI-assistants block | `.gitignore` | yes (header detection) |
| 2 | **`.ai-state/` skeleton** — create `decisions/drafts/`, `DECISIONS_INDEX.md`, `TECH_DEBT_LEDGER.md`, `calibration_log.md` | `.ai-state/` (4 entries) | yes (per-file existence check) |
| 3 | **`.gitattributes` + merge drivers** — append entries; register Python merge drivers via `git config` | `.gitattributes`, `.git/config` | yes (line + git config check) |
| 4 | **Git hooks** — install pre-commit (id-citation discipline) + post-merge (ADR finalize, tech-debt dedupe, squash-safety) | `.git/hooks/pre-commit`, `.git/hooks/post-merge` | yes (symlink target check) |
| 5 | **`.claude/settings.json` toggles** — multi-select: enable memory MCP injection, memory gate, memory MCP, observability | `.claude/settings.json` | yes (key presence check) |
| 6 | **`CLAUDE.md` blocks** — idempotently append Agent Pipeline + Compaction Guidance + Behavioral Contract | `CLAUDE.md` | yes (per-block heading detection) |
| 7 | **Companion CLIs** — print install commands for `chub`, `scc`, `uv` if missing and stack-relevant | none (advisory) | yes (always advisory) |
| **8** | **Architecture baseline (opt-in, default-yes)** — delegate to `systems-architect` in baseline mode → produces `.ai-state/ARCHITECTURE.md` + `docs/architecture.md` (+ optional ADR draft) | `.ai-state/ARCHITECTURE.md`, `docs/architecture.md` | yes (skip if either doc exists OR user picks Skip at Gate 8) |
| 9 | **Verification + handoff** — print summary, stage modified files (no commit) | git index | n/a (terminal) |

The command never auto-commits. After Phase 9, `git status` shows every file modified by the run staged for review. Use `/co` to commit (the [git-conventions rule](../rules/swe/vcs/git-conventions.md) writes a precise message) or unstage and review individually.

## What gets created

### Phase 1 — `.gitignore` (canonical 10-line block)

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

| Entry | What it excludes |
|-------|------------------|
| `.ai-work/` | Ephemeral pipeline scratch (per-task slug); deleted at pipeline end |
| `.ai-state/*.lock`, `.ai-state/**/*.lock` | Advisory file locks taken by `finalize_adrs.py`, merge drivers — runtime-only |
| `.ai-state/*.backup.json` | Snapshots taken before destructive memory ops; local recovery only |
| `.ai-state/*.pre-forget.json` | Pre-`forget()` memory snapshots |
| `.claude/settings.local.json` | Per-machine Claude settings — never committed |
| `.claude/worktrees/` | Worktree home for `EnterWorktree`; each branch's own checkout |
| `.env`, `.env.*`, `.env.local` | Secrets — never commit |

If your `.gitignore` excludes `.ai-state/` (the directory itself), the command warns: `.ai-state/` holds persistent project intelligence (ADRs, idea ledger, sentinel reports, tech-debt ledger) and should be committed. You can keep the exclusion if you have a strong reason — the command notes the choice in Phase 8's summary.

### Phase 2 — `.ai-state/` skeleton

Four new entries, each created only if missing:

- `.ai-state/decisions/drafts/` — empty directory; first ADR draft lands here when the systems-architect agent runs
- `.ai-state/decisions/DECISIONS_INDEX.md` — header-only Markdown table (auto-regenerated by `scripts/finalize_adrs.py` at merge-to-main)
- `.ai-state/TECH_DEBT_LEDGER.md` — header + empty 15-field schema row (living, append-only ledger of grounded debt findings)
- `.ai-state/calibration_log.md` — header + empty schema row (append-only tier-selection log used by `sentinel`)

`.ai-state/memory.json` and `.ai-state/observations.jsonl` are NOT pre-created — they're written on first use by the memory MCP server and the observability hook respectively. Pre-creating them confuses the semantic merge drivers.

### Phase 3 — `.gitattributes` + merge driver registration

Two new lines appended to `.gitattributes`:

```gitattributes
# Praxion semantic merge drivers
.ai-state/memory.json merge=memory-json
.ai-state/observations.jsonl merge=observations-jsonl
```

And two `git config` entries registered for this repo:

```
merge.memory-json.driver = python3 <plugin-install-path>/scripts/merge_driver_memory.py %O %A %B
merge.observations-jsonl.driver = python3 <plugin-install-path>/scripts/merge_driver_observations.py %O %A %B
```

Without these, the first concurrent edit to `.ai-state/memory.json` corrupts it via line-based merge. The drivers parse the JSON / JSONL structurally and reconcile concurrent additions cleanly. **Local merges only** — GitHub PR squash-merges bypass `.gitattributes` (the `check_squash_safety.py` post-merge script warns if squash erased `.ai-state/`).

### Phase 4 — Git hooks

Two hooks installed under `.git/hooks/`:

- **`pre-commit`** — *not* a symlink to a plugin script; the command writes a small bash file directly that resolves the plugin install path at hook-run time (so plugin upgrades flow automatically) and runs `scripts/check_id_citation_discipline.py` against staged files. Blocks commits that reference ephemeral pipeline IDs (`REQ-NN`, `AC-NN`, `Step N`) in committed source code per [id-citation-discipline rule](../rules/swe/id-citation-discipline.md).
- **`post-merge`** — symlink to the plugin's `scripts/git-post-merge-hook.sh`. Chains: `reconcile_ai_state.py` → `finalize_adrs.py` (promote draft ADRs to stable `dec-NNN`) → `finalize_tech_debt_ledger.py` (dedupe rows by `dedup_key`) → `check_squash_safety.py` (warn if squash erased `.ai-state/`).

If a non-Praxion hook already exists at `.git/hooks/pre-commit` or `post-merge`, it's backed up to `<name>.pre-praxion` and the user is warned — the command never silently overwrites a non-Praxion hook.

### Phase 5 — `.claude/settings.json` toggles

Multi-select via `AskUserQuestion`. The command writes (or merges into) `.claude/settings.json`:

```json
{
  "env": {
    "PRAXION_DISABLE_MEMORY_INJECTION": "0",
    "PRAXION_DISABLE_MEMORY_GATE": "0",
    "PRAXION_DISABLE_MEMORY_MCP": "0",
    "PRAXION_DISABLE_OBSERVABILITY": "0"
  }
}
```

Negative semantics: `"1"` disables, `"0"` enables. Each unchecked option becomes `"1"`; each checked becomes `"0"`. The four toggles:

| Toggle | What you gain | Cost |
|--------|---------------|------|
| Memory MCP injection (SessionStart) | Auto-loaded project context every session | ~3–5k tokens at session start |
| Memory gate (Stop hook) | Forces `remember()` calls when substantive work happens | Can feel intrusive on quick fixes |
| Memory MCP server itself | Persistent cross-session memory under `.ai-state/memory.json` | Hooks fire on every event; some session overhead |
| Observability events | Trace inspection via localhost Phoenix | Phoenix must be running, else events drop silently |

If `.claude/settings.json` already has other top-level keys (`permissions`, `model`, etc.), they're preserved — only the `env.PRAXION_DISABLE_*` keys are touched.

### Phase 6 — `CLAUDE.md` blocks

Three independent appends, each guarded by heading detection:

- `## Agent Pipeline` — describes the 5-stage pipeline (researcher → systems-architect → implementation-planner → implementer + test-engineer → verifier), independent audits via `sentinel`, and the PoC-to-production journey. Self-contained — no cross-references to Praxion-internal docs that don't exist in your project.
- `## Compaction Guidance` — what to preserve when the conversation compacts (active task slug, current WIP step, acceptance criteria, modified files).
- `## Behavioral Contract` — Surface Assumptions / Register Objection / Stay Surgical / Simplicity First.

If `CLAUDE.md` doesn't exist, the command instructs you to run `/init` first (which analyzes your codebase and produces a tailored `CLAUDE.md`), then re-run `/onboard-project` to append the blocks. The command never authors `CLAUDE.md` itself — `/init` is better at that.

### Phase 7 — Companion CLIs (advisory)

The command checks for `chub` (external API docs CLI), `scc` (SLOC counter), and `uv` (Python tooling). For each missing tool that's stack-relevant, prints the install command — but does NOT run it. You decide. `uv` is only recommended when Python signal is detected in pre-flight (`pyproject.toml`, `setup.py`, `requirements.txt`, etc.).

### Phase 8 — Architecture Baseline (opt-in, default-yes)

This is the slowest and most consequential phase. See [Architecture baseline (Phase 8)](#architecture-baseline-phase-8) below for the full picture. In short: the command delegates to the `systems-architect` agent in **baseline-audit mode** — read the existing codebase, produce both architecture documents from the as-built state.

**Outputs (when "Run baseline now" is chosen):**

- `.ai-state/ARCHITECTURE.md` — architect-facing design-target document. Holds the architectural intent: System Overview, System Context (L0 Mermaid), Components (L1 Mermaid + table), Data Flow, Quality Attributes, Open Questions. Future feature pipelines update this incrementally — `systems-architect` re-reads it in Phase 4 of every Standard-tier feature.
- `docs/architecture.md` — developer-facing navigation guide. Filtered to **Built** components only (every name and path code-verified via `Glob`/`ls`). New developers read this first to orient on the codebase.
- *Optional* — one ADR draft under `.ai-state/decisions/drafts/` if the baseline reading surfaces a non-obvious load-bearing invariant (e.g., a one-way module dependency, a layer boundary). The architect is instructed NOT to write ceremonial ADRs — only invariant-pinning ones.

### Phase 9 — Verification + handoff

Prints a per-phase summary listing every file touched and every `git config` entry written. Stages those files only — never `git add -A`. Tells you to run `/sentinel` for an ecosystem health baseline (now meaningful since `.ai-state/ARCHITECTURE.md` exists for sentinel's coherence dimension to read), then `/co` to commit.

## Architecture baseline (Phase 8)

<details>
<summary>Why this phase exists, and when to skip it</summary>

`.ai-state/ARCHITECTURE.md` and `docs/architecture.md` are first-class artifacts in the Praxion ecosystem — sentinel's coherence audit reads them, future feature pipelines update them, Memory MCP context recall benefits from them. **Without them, every future agent runs context-poor on the codebase shape.** The greenfield path (`/new-project`) gets these for free via the seed pipeline; existing-project onboarding needs the same treatment, which is the whole point of Phase 8.

**Skipping is acceptable when:**

- You're onboarding a small, throwaway project (single script, prototype) where architectural docs are overhead.
- You'll run a Standard-tier feature pipeline immediately after onboarding — its `systems-architect` stage will produce the docs as a byproduct.
- You want lean onboarding and don't plan to run `/sentinel` immediately afterward (sentinel's coherence dimension is the main consumer that needs the docs upfront).

**Skipping is the wrong call when:**

- You want `/sentinel` to give a clean baseline today.
- You want Memory MCP recall to know about the codebase structure from session 1.
- The project is non-trivial (>10 source files) — the architectural snapshot pays off across many future feature pipelines.

</details>

<details>
<summary>What the systems-architect does in baseline mode</summary>

The `/onboard-project` command delegates to `systems-architect` via the `Task` tool with these explicit directives:

- **Mode**: baseline-audit, no specific feature scope. Read the codebase, describe the as-built state. Do *not* produce a `SYSTEMS_PLAN.md` (no feature in scope).
- **Inputs**: project root + the language/framework signals detected in pre-flight.
- **Required outputs**: `.ai-state/ARCHITECTURE.md` + `docs/architecture.md`. Both code-verified — every Mermaid node and table row resolves on disk.
- **Optional output**: at most one ADR draft, only when a load-bearing invariant is detected in the code. No ceremonial ADRs.
- **Anti-instructions**: no `SYSTEMS_PLAN.md`, no L2 internals (≤10 nodes per Mermaid per `rules/writing/diagram-conventions.md`), no source-code edits, no test edits, no doc edits outside the two architecture files.

The architect runs in a fresh context window and reports completion. The main `/onboard-project` agent reads the produced docs to confirm shape, then proceeds to Phase 9.

</details>

<details>
<summary>Time cost and accuracy expectations</summary>

| Codebase size | Approximate baseline time | Initial accuracy |
|---------------|--------------------------|------------------|
| Small (≤50 source files) | 2–5 minutes | High — architect can hold the whole shape in context |
| Medium (50–500 files) | 5–15 minutes | Good — main components mapped, minor modules might be coalesced |
| Large (500+ files) | 15–30 minutes | Adequate — top-level structure correct, detailed coupling inferred from imports |

Initial accuracy is **not** intended to be perfect. The baseline is the *seed*; future feature pipelines refine it as `systems-architect` re-reads and updates the docs. Section ownership rules in the templates prevent regressions when the architect re-runs.

</details>

<details>
<summary>What if Phase 8 fails or times out?</summary>

If the architect agent fails or hits a timeout, `/onboard-project` emits a clear warning and proceeds to Phase 9. Architecture docs are not produced. You can:

1. Re-run `/onboard-project` — Phase 8's predicate skips already-existing docs, so a re-run only re-fires Phase 8 if both docs are still absent.
2. Run a feature pipeline whose first stage produces them (any Standard-tier feature delegates to `systems-architect` which writes both docs).
3. Run `/sentinel` first to capture an ecosystem health baseline without the architecture docs, then circle back to architecture later.

The key principle: a failed baseline does not block onboarding. The other 8 phases land regardless.

</details>

## Idempotency contract

Every write phase has a predicate that makes re-runs no-ops. Reference: `commands/onboard-project.md` § Idempotency Predicates.

| Phase | Predicate (skip if true) |
|-------|--------------------------|
| 1 | `grep -q '^# AI assistants$' .gitignore` |
| 2 | Per-file `test -e .ai-state/<file>` (skip files individually) |
| 3 | `.gitattributes` line present AND `git config --get merge.memory-json.driver` returns a value containing `i-am` |
| 4 | `readlink .git/hooks/post-merge` resolves to a Praxion path AND pre-commit content contains `check_id_citation_discipline` |
| 5 | All four `PRAXION_DISABLE_*` keys present in `.claude/settings.json` |
| 6 | `## Agent Pipeline` heading present in `CLAUDE.md` (per-block check) |
| 8 | `test -e .ai-state/ARCHITECTURE.md` OR `test -e docs/architecture.md` (covers re-runs and greenfield-followed-by-onboard); also skipped if user picks `Skip` at Gate 8 |

**Test for idempotency:** run `/onboard-project`, accept all gates, then re-run. The second run should produce zero `git diff` output and zero new `git config` entries. If either runs, the predicate has a bug — file an issue against `commands/onboard-project.md`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Command aborts: "This command must be run inside a git repository." | Current directory is not a git repo | Run `git init` first |
| Command aborts: "This directory looks like a freshly-scaffolded greenfield project..." | Pre-flight detected greenfield signature (no source code, AI-assistants `.gitignore` present, empty `.claude/`) | Run `/new-project` instead — it does the full greenfield scaffold then chains to `/onboard-project` |
| Phase 4 skipped with "install the plugin and re-run" | Plugin not detected in `~/.claude/plugins/installed_plugins.json` | Install the plugin: `claude plugin install i-am@bit-agora` (or `./install.sh code` from a Praxion checkout), then re-run `/onboard-project` |
| Phase 3 emits "merge.memory-json.driver is already set..." | A non-Praxion driver is registered for that file pattern | Remove the existing driver: `git config --unset merge.memory-json.driver`, then re-run Phase 3 (or accept the existing driver and skip — Praxion's reconciliation will degrade) |
| Phase 4 backs up `pre-commit.pre-praxion` | A non-Praxion pre-commit hook was already in place | Decide: merge the two hook bodies manually, or restore the original (`mv .git/hooks/pre-commit.pre-praxion .git/hooks/pre-commit`) and skip Praxion's pre-commit |
| Pre-commit hook fails with "command not found: jq" | `jq` not on PATH; the hook uses it to resolve plugin install path | Install `jq` (`brew install jq` on macOS, `apt install jq` on Debian/Ubuntu) — the hook degrades to an no-op exit 0 if `jq` is unavailable but the id-citation check is then skipped |
| Phase 6 prints "No CLAUDE.md found..." | The project has no project-level `CLAUDE.md` yet | Run `/init` to generate one from the codebase, then re-run `/onboard-project` |
| Re-run produces a non-empty `git diff` after phase 8 | An idempotency predicate has a bug | File an issue with the affected phase number and the diff |

## Limits and known issues

- **Plugin install scope is auto-detected but not auto-installed.** If the plugin isn't installed, Phase 4 is skipped and the command tells you to install it. The command does not invoke `./install.sh code` for you — that runs outside the Claude Code session and may prompt for system-level confirmations.
- **Pre-commit hook bash script is written, not symlinked.** Praxion's repo-level `scripts/git-pre-commit-hook.sh` runs the *shipped-artifact-isolation* check — a Praxion-author concern that doesn't apply to user projects. The `/onboard-project` command writes a tailored hook script directly into `.git/hooks/pre-commit` that runs only `check_id_citation_discipline.py`. The hook script resolves the plugin install path at hook-run time so plugin upgrades flow automatically; you don't need to re-run `/onboard-project` after a plugin upgrade.
- **Project-scope plugin install requires manual driver re-registration.** If you switch a project from user-scope to project-scope plugin install (or vice versa), the `git config merge.*.driver` paths will point at the old install location. Re-run `/onboard-project` to re-register.
- **Multi-user team mode is partially supported.** The `git config` driver registration is per-clone, so each developer who clones the repo needs to run `/onboard-project` once on their machine. The committed `.gitattributes` declares which driver applies, but the driver implementation is per-clone (not committed).
- **Stack-specific tailoring is intentionally absent in the appended `## Agent Pipeline` block.** The block is stack-neutral — Python, Node, Rust, Go projects all get the same wording. Phase 7 surfaces stack-specific CLI recommendations (`uv` only for Python). If you want stack-specific guidance in `CLAUDE.md`, add it manually after running `/init` — `/onboard-project` won't touch what `/init` produced.
