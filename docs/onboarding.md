---
diataxis: how-to
audience: developer
---

# Project Onboarding

How to bring a project into the Praxion ecosystem — one command, one engine, four modes. `onboard-project` replaces the former two-path split (`new_project.sh` + `/new-project` for greenfield, `/onboard-project` for existing projects): detection now resolves the mode for you, so there is nothing left to choose between.

## Contents

- [What onboarding does](#what-onboarding-does)
- [Pick your entry](#pick-your-entry)
- [Quick start](#quick-start)
- [The phase list](#the-phase-list)
- [Modes in depth](#modes-in-depth)
- [Hackathon → full promotion](#hackathon--full-promotion)
- [Re-running and upgrading](#re-running-and-upgrading)
- [Troubleshooting](#troubleshooting)
- [Limits](#limits)
- [Design decisions](#design-decisions)

## What onboarding does

One phase engine, parameterized by mode, installs a fixed end-state contract onto disk. Every write is idempotent — re-running the command on an already-onboarded project produces zero diff.

| Lands on disk | Why |
|---|---|
| `.gitignore` AI-assistants block | Excludes `.ai-work/`, lock files, `.env*`, `.claude/settings.local.json` from version control |
| `.ai-state/` skeleton (decisions, tech-debt ledger, calibration log, consult ledgers) | Persistent project intelligence — the durable memory the agent pipeline reads and writes |
| `.gitattributes` + `merge.observations-jsonl.driver` `git config` entry | Structural JSONL merge for `.ai-state/observations.jsonl` — prevents line-based merge corruption |
| `.git/hooks/{pre-commit,post-merge,post-commit,post-checkout}` | id-citation discipline gate + the finalize chain (ADR promotion, tech-debt dedupe, squash-safety warning) |
| `.claude/settings.json` toggles + `permissions.allow` baseline | Observability opt-in/out; the standing grant that keeps subagent `.ai-work/` writes from stalling on an unanswerable permission prompt |
| Four canonical `CLAUDE.md` blocks (Agent Pipeline, Compaction Guidance, Behavioral Contract, Praxion Process) + Project Essentials | The always-loaded context that makes every future Claude Code session Praxion-aware |
| *Opt-in*: architecture baseline, code-quality baseline, CI autofix, Architecture-as-Code tier, ML/AI conventions, Obsidian integration | Selected via the capability Profile (§Pick your entry) |

Nothing is ever committed. Every phase stages its own changes; you review and commit with `/co`.

## Pick your entry

You do not choose an entry point — `onboard-project` detects the directory's state and resolves exactly one of four modes. The 6 detected states collapse to 3 base modes plus `promote`:

| Detected state | Resolved mode | What happens |
|---|---|---|
| `empty` | `new` | Minimal scaffold (`git init`, `.gitignore`, empty `.claude/`), then hands off to the seed pipeline — builds an app from scratch |
| `code-no-git` | `existing` | `git init` offered as the first gated action, then the retrofit flow |
| `git-no-praxion` | `existing` | Retrofit flow — the common case for "I have a repo, make it Praxion-aware" |
| `partially-managed` | `existing` | Retrofit flow; already-present surfaces are skipped by their idempotency predicates |
| `fully-managed` | `existing` (no-op) | Re-run confirms everything is current and exits without launching Claude |
| `hackathon-managed` | `hackathon` (or `promote` with `--full` / `--mode promote`) | Minimal-ceremony flow, or the mechanical graduation path |

An explicit `--mode` overrides detection and fails fast (exit `2`) if it contradicts the detected state (for example, `--mode new` against a non-empty directory).

## Quick start

Two equivalent invocations, same as before the unification — only the binary name changed (`new-project` → `onboard-project`; `install.sh code` still symlinks the entry into `~/.local/bin/`):

```bash
# Create a new project
onboard-project my-app

# Onboard the project you're standing in (existing repo)
cd ~/dev/acme-api && onboard-project
```

Already in a Claude Code session inside a project? Invoke the skill directly:

```
/praxion:onboard-project
```

See what would change without writing anything:

```bash
onboard-project --check
```

## The phase list

Phase identifiers are preserved verbatim from the two prior surfaces — `0.5, 1–7, 5b, 6, 7, 8, 8b–8e, 9`, plus two new ids (`0s` greenfield seed, `5b.t` hackathon teardown). Everything user-facing speaks **capability IDs** instead; the mapping below is the single join point.

| Capability | Phases | Writes | Idempotency predicate | Runs in |
|---|---|---|---|---|
| `core` | `0.5, 1, 2, 3, 4, 6, 7, 9` | gitignore block, `.ai-state/` skeleton, gitattributes + merge driver, git hooks, CLAUDE.md blocks | Per-phase — see [`SKILL.md` §Idempotency Predicates](../skills/onboard-project/SKILL.md#idempotency-predicates--per-phase-contracts) | every mode, always on |
| `observability` | `5` | `.claude/settings.json` `env.PRAXION_DISABLE_OBSERVABILITY` | Key present, any value | every mode |
| `0s` (seed pipeline) | `0s` | the app itself — delegates to the full agent pipeline | n/a — implied by `new` mode | `new` only |
| `5b` / `5b.t` | `5b`, `5b.t` | six hackathon artifacts / their removal | `PRAXION_HACKATHON_MODE` key presence; teardown fires only under `promote` | `5b`: `hackathon`; `5b.t`: `promote` |
| `arch` | `8` | `.ai-state/DESIGN.md`, `docs/architecture.md` | Either file exists → skip | `new` (mechanically skipped — the seed pipeline already wrote them), `existing` (default-on) |
| `quality` | `8e.1`–`8e.7` | `.editorconfig`, pre-commit config, per-stack linter/formatter/type config, `CONTRIBUTING.md` | Per-sub-step file/config presence | `new`, `existing` (default = stack detected) |
| `ci` | `8e.8`, `8e.9` | CI-autofix + cross-model-review + label-reconcile callers | Per-sub-step | opt-in only (`--profile all` or explicit `--with ci`) |
| `aac` | `8b` | `fitness/` scaffold, golden-rule pre-commit block, `architecture.yml` workflow, `docs/diagrams/` | Per-sub-step | opt-in only |
| `ml` | `8c` | `program.md`, `.ai-state/experiments/`, checkpoint `.gitignore` block, `.ai-state/gpu_budget.yaml` | Per-sub-step; whole phase skipped if no ML signals and not selected | default-on when ML signals detected |
| `obsidian` | `8d` | Obsidian `.gitignore` block, `CLAUDE.md` block, `.obsidian/app.json` link-safety pins, `permissions.deny` entries | Per-sub-step; whole phase skipped if `claude` CLI or the marketplace plugin is absent | detection-gated |

Full per-phase detail (writes, predicates, sub-steps) lives in [`skills/onboard-project/references/phases-core.md`](../skills/onboard-project/references/phases-core.md) and [`phases-optional.md`](../skills/onboard-project/references/phases-optional.md) — this table is the navigation layer, not a restatement.

## Modes in depth

### `new` — empty directory

Runs the **seed pipeline** ([`references/seed-pipeline.md`](../skills/onboard-project/references/seed-pipeline.md)): the bash entry scaffolds `.git/`, the AI-assistants `.gitignore` block, and an empty `.claude/`, then hands off to a Claude Code session. That session asks one question (what to build — default is a mini coding agent with a web UI), runs the full Standard-tier agent pipeline (researcher → systems-architect → implementation-planner → implementer ∥ test-engineer → verifier), generates the default app (Python + `uv` + Claude Agent SDK + FastAPI), and produces a per-run `onboarding_for_mushi_busy_ppl.md` trail map.

The default app is prose-specified, not templated: the pipeline mandates an `external-api-docs` lookup of the current Claude Agent SDK and `uv` docs at run time, so generated code matches the SDK release on your machine — not a version baked into training data. Full rationale: [`dec-053`](../.ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md).

**The `claude-desktop` editor caveat.** `--editor claude-desktop` (or `PRAXION_NEW_PROJECT_EDITOR=claude-desktop`) launches `Claude.app` and copies the project path to the clipboard. Anthropic ships no documented CLI flag or URL scheme to point the desktop app at a folder — so you click **Select folder** in the app and paste. macOS only.

**Illustrative end-to-end transcript** (actual output depends on the installed Claude Code version and the just-fetched SDK docs):

```text
$ onboard-project my-app
→ Scaffolded my-app at /Users/you/code/my-app. Launching Claude Code...

[Claude Code session starts]

Claude: What would you like to build? Press enter for the default
        (mini coding agent with web UI), or describe your own project.
> [enter]

Claude: Before I build, here's how this works:

        You don't call Praxion subagents by name. You write tasks in plain
        English, and Claude (the orchestrator) routes the work to specialists:
          • researcher — explores docs, libraries, external APIs
          • systems-architect — module shape, dependency direction
          • implementation-planner — decomposes into small steps
          • implementer + test-engineer — code + tests in parallel
          • verifier — checks acceptance criteria
        You speak English, Claude delegates. No /command memorization required.

Claude: [researcher] Fetching Claude Agent SDK + uv + FastAPI docs via context-hub ...
        [systems-architect] Module shape: src/agent/{core,tools,prompts}, src/web/{app},
          tests/. One-way dependency src/agent → src/web.
          → Wrote .ai-work/<slug>/SYSTEMS_PLAN.md, .ai-state/DESIGN.md,
            docs/architecture.md, and one ADR draft in .ai-state/decisions/drafts/
            for the dependency rule.
        [implementation-planner] 4 steps: (1) pyproject+env, (2) agent core+tools,
          (3) web app+static, (4) smoke test.
        [implementer ∥ test-engineer] Step 2: src/agent/*.py + tests/test_agent.py.
          [implementer ∥ test-engineer] Step 3: src/web/app.py + streaming assertions.
        [verifier] Layer isolation ✓ safe-list frozenset at module scope ✓ smoke green ✓.

Claude: Running test gate: uv sync && uv run pytest -q
        1 passed in 0.34s

Claude: Now running /init so CLAUDE.md reflects the actual codebase, then
        appending the Praxion canonical blocks and running the onboard-project
        skill for the remaining surfaces (git hooks, merge drivers, settings) ...

Claude: Generated onboarding_for_mushi_busy_ppl.md (trail map for busy people).
        Scaffold staged. Run /co to make the first commit (or /cop for commit+push).
```

### `existing` — retrofit

The default flow, and the common case: `.gitignore`, `.ai-state/`, `.gitattributes`/hooks, settings, `CLAUDE.md` blocks land on an already-populated repo, plus the architecture baseline (delegates to `systems-architect` in baseline-audit mode) and stack-detected quality tooling. Opt-in tiers you can add explicitly with `--with`:

```bash
onboard-project --with aac,ci --without obsidian
```

### `hackathon` — minimal, promotable

`onboard-project my-app --hackathon` (or `--mode hackathon` on an existing repo) installs the invariant `core` surfaces plus six hackathon artifacts, skipping every opt-in tier. See [Hackathon → full promotion](#hackathon--full-promotion).

## Hackathon → full promotion

Passing `--hackathon` writes six artifacts: `PRAXION_HACKATHON_MODE=1` in `.claude/settings.json`, the `## Hackathon Mode` `CLAUDE.md` block, the `.claude/praxion-rules.yaml` preset, and the launch trio `scripts/praxion-hackathon` + `.claude/hackathon-directive.md` + `.claude/hackathon-settings.json`.

**Worked example** — create, work through the wrapper, graduate out:

```bash
# 1 — Scaffold and seed a hackathon project
onboard-project url-shortener-poc --hackathon
```

```bash
# 2 — Work through the wrapper
cd url-shortener-poc
./scripts/praxion-hackathon
```

The wrapper launches Claude with the skill surface trimmed and the hackathon directive appended. You describe what you need in plain English, and the orchestrator enters the **Hackathon Spine** at the stage it infers:

| You say… | Spine enters at… |
|---|---|
| "Ideate a few options for link-expiry" | `promethean` |
| "I have the approach — plan and build the redirect endpoint" | `implementation-planner` |
| "Fix the off-by-one in the base62 encoder" | `implementer` |

The verifier still runs by default — say "skip verification" to opt out. The behavioral contract is never relaxed.

**3 — Graduate out mechanically** when the PoC becomes a real project:

```bash
onboard-project --full          # from inside the project
# or, before entering: onboard-project --mode promote
```

This is now a mechanical path, not a manual checklist. `--full` fires **Sub-step 5b.t** — enumerate-before-remove of all six hackathon artifacts (each template-compared and skipped-with-warning if you've diverged from it, never a blind delete) — then runs the full phase set (the opt-in Profile you select at G3), then flips the stamp's `mode` field to `"full"`. If you promoted a project by hand before this path existed, check for orphaned artifacts yourself: the old manual procedure named only three of the six (the settings.json flag, the CLAUDE.md block, and the rules preset) and silently left the launch trio behind.

```
$ cd ~/dev/hack-demo && onboard-project --full

Praxion onboarding · plugin 0.23.0
  Directory   ~/dev/hack-demo
  Praxion     hackathon mode, onboarded 2026-08-24 with 0.22.0
  Mode        promote — hackathon → fully managed

  - hackathon             removed all 6 hackathon artifacts (was: 3 documented, 3 orphaned)
  + arch                  .ai-state/DESIGN.md · docs/architecture.md
  + quality               .editorconfig · pre-commit · CONTRIBUTING.md

Promoted hack-demo to fully-managed Praxion 0.23.0.
```

## Re-running and upgrading

Every phase's write is gated by an idempotency predicate — re-running `onboard-project` on an already-onboarded project produces zero `git diff` and zero new `git config` entries. A clean re-run resolves "nothing to do" at the bash layer and **never launches a Claude session** — the biggest perceived-performance win over the old two-command flow, which walked every phase and gate to reach the same conclusion.

Use `onboard-project` again to **add** a capability you skipped (`onboard-project --with aac`) or to promote out of hackathon mode (`--full`).

Use `/upgrade-project` (wrapping `scripts/upgrade_project_pins.sh`) instead when the **plugin version changed** and you need version-pinned surfaces (finalize-hook symlinks, the merge-driver `git config` entry, CI-autofix caller SHAs) re-pointed at the live install — a narrower, gate-free operation than a full re-run.

Use `/refresh-claude-blocks` when you only need the four refreshable `CLAUDE.md` canonical blocks brought current.

## Troubleshooting

The bash layer uses distinct exit codes for each failure so you can diagnose without reading the source:

| Exit | Symptom | Cause | Fix |
|---|---|---|---|
| `2` | "Usage error: ..." on stderr | Missing/invalid argument, invalid project name, or `--mode` contradicts the detected state | Check the flag or project-name regex (`^[A-Za-z0-9][A-Za-z0-9._-]*$`); run `onboard-project --help` |
| `3` | "Claude Code CLI not found on PATH" | Claude Code is not installed | `npm install -g @anthropic-ai/claude-code`, then re-run |
| `4` | "the 'praxion' plugin is not installed" | `~/.claude/plugins/installed_plugins.json` has no `praxion@bit-agora` entry | `/plugin marketplace add bit-agora/praxion` then `/plugin install praxion`, or `./install.sh code` from a Praxion checkout |
| `5` | "'git' not found in PATH" | git is not installed | Install git (`brew install git`, `apt install git`, ...) |
| `6` | "already exists and is not empty" | `<target-dir>/<project-name>` is a non-empty path | Pick a different name/target, or `cd` into it and run `onboard-project` with no positional |
| `7` | "Refusing to onboard: this is a Praxion plugin source repository" | `.claude-plugin/plugin.json` exists at the target and `PRAXION_ALLOW_SELF_ONBOARD` is unset | Intentional dogfooding? Re-run with `PRAXION_ALLOW_SELF_ONBOARD=1 onboard-project` |
| `8` | (only with `--check`) "Pending: ... needs work" | `--check` found drift or an incomplete onboard | Run `onboard-project` (no `--check`) to apply, or `--check --json` for machine output |

**Two Claude-side failure modes** the bash layer cannot detect:

| Symptom | Cause | Fix |
|---|---|---|
| Claude session starts but the `onboard-project` skill never fires | Plugin registered but skill files are not linked into the active config | Re-run `./install.sh --relink code` to refresh plugin links |
| The launcher's detected state and the skill's own Phase 0 re-detection disagree | Directory state changed between the bash launcher running and the Claude session starting (rare — e.g., a concurrent `git init`) | Not an error: Phase 0 always re-runs the same predicates and uses its own result when it disagrees, printing why. If the result still looks wrong, re-run `onboard-project` from a clean state |

Also refusable at the shape-guard boundary: `onboard-project` on a `git-no-praxion` state that looks like a freshly-scaffolded-but-abandoned greenfield project (empty `.claude/`, AI-assistants `.gitignore`, no source tree) is refused with a pointer to run `onboard-project <project-name> <target-dir>` instead — running the seed pipeline over what looks like an empty scaffold, rather than silently treating it as "existing."

## Limits

- **Claude Code CLI only** as the pipeline-driving surface. Running the seed pipeline inside Cursor's AI assistant or Claude Desktop's chat is not supported — the bash entry `exec`s a `claude` CLI process. (The *editor* that opens to view files while the pipeline runs is independent — `--editor` covers Cursor, VS Code, and Claude.app.)
- **Default app is Python only** (`uv` + `claude-agent-sdk` + FastAPI). No JS/TS or other-language variant in the default branch.
- **Custom-app branch tailors only L1 + L2** of the seed pipeline's lesson ladder; L3–L7 stay generic Praxion-ecosystem lessons.
- **The bash integration test (`tests/onboard_project_test.sh`) is single-file**, run manually — not yet wired into CI.
- **Plugin install check is user-scope only.** Project-scope plugin installs are also detected, but the bash layer's own prereq check only reads the user-scope registry path.

## Design decisions

- [`dec-053`](../.ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md) — prompt-over-template discipline for the seed pipeline's default app.
- [`dec-054`](../.ai-state/decisions/054-separate-new-cc-project-from-install.md) — separating project scaffolding from plugin installation.
- [`dec-055`](../.ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md) — hybrid bash + Claude-session orchestration (deterministic prereqs in bash, conversational flow in Claude).
- `dec-draft-ec94fa61` — unifying the two onboarding commands into one user-invocable skill plus one entry script.
- `dec-draft-6bebc4d4` — preserving onboarding phase identifiers verbatim across the migration.
- `dec-draft-25d94017` — one idempotency mechanism and one embedding site for the seven canonical `CLAUDE.md` blocks.
- `dec-draft-c4713004` — persisting the onboarding mode in the onboard stamp and making hackathon promotion mechanical.

(The four `dec-draft-*` ids above finalize to `dec-NNN` records under `.ai-state/decisions/` at merge-to-main; look them up by title in [`DECISIONS_INDEX.md`](../.ai-state/decisions/DECISIONS_INDEX.md) once finalized.)
