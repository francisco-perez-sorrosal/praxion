---
name: onboard-project
description: >
  Bring a project into the Praxion ecosystem — detect its current state and install
  the managed-project contract (gitignore block, .ai-state/ skeleton, git hooks,
  merge drivers, settings toggles, CLAUDE.md blocks) plus optional capability tiers
  (architecture baseline, code-quality, CI autofix, Architecture-as-Code, ML
  conventions, Obsidian). Handles four modes over one idempotent engine: new
  (empty directory), existing (any prior state), hackathon (minimal, promotable),
  and promote (hackathon → fully managed). Safe to re-run; nothing is committed.
when_to_use: >
  Invoked by the user via /praxion:onboard-project, or handed off from the
  scripts/onboard-project entry script. Never auto-invoked.
argument-hint: "[new|existing|hackathon|promote] [--yes] [--with aac,ci] [--without obsidian] [--check]"
arguments:
  mode:
    description: "Entry mode: new | existing | hackathon | promote. Omit to auto-detect from directory state."
    required: false
  with:
    description: "Comma-separated capability IDs to install: arch, quality, ci, aac, ml, obsidian, observability."
    required: false
  without:
    description: "Comma-separated capability IDs to skip. Applied after --with."
    required: false
  yes:
    description: "Accept all detected defaults; ask nothing."
    required: false
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Task]
---


Onboard a project to work cleanly with the Praxion plugin (`praxion`) — one phase engine covering all four entry states (`new`, `existing`, `hackathon`, `promote`; see §Mode × Phase Matrix). Detection (§Pre-flight) computes a correct default for nearly everything; the command fires at most three `AskUserQuestion` gates (§Phase Gates) — mode confirm, build intent, and a single capability Profile — rather than pausing once per phase.

## Sections

1. §Pre-flight — repo + plugin detection, no writes
2. §Flow — the nine sequential phases (Phase 0 pre-flight diagnostic + Phases 1–9 with writes)
3. §Capability IDs — the user-facing vocabulary; the single join point to internal phase ids
4. §Mode × Phase Matrix — which phases run under `new` / `existing` / `hackathon` (`promote` inherits `existing`)
5. §Phase Gates — the three surviving gates (G1/G2/G3), fallback behavior
6. §Idempotency Predicates — per-phase contracts

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
4b. **ML signal detection.** Probe for ML/AI training signals and set an `ml_signals_detected` flag (used to derive the `ml` capability's default in the Profile, G3, and skip Phase 8c when absent). Signals:
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

After printing: **if `CLAUDE.md` is absent, run §Phase 0.5 (CLAUDE.md bootstrap) before §Flow** — it guarantees a `CLAUDE.md` exists so the block-append phases (5b, 6, 8d) never silently skip the Praxion payload. When `CLAUDE.md` is present, §Phase 0.5 is a complete no-op. Then proceed to §Flow: resolve the capability Profile (G3, §Phase Gates) once, before any write, and run every phase whose owning capability (§Capability IDs) the Profile selected.

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
| 5b | Hackathon mode gate: write six artifacts when enabled | `PRAXION_HACKATHON_MODE=1` present in `.claude/settings.json` env (skip if already set); or mode is not `hackathon`/`promote` |
| 5b.t | Hackathon teardown: remove the six hackathon artifacts (enumerate-before-remove, template-compared) — see [references/phases-core.md § Sub-step 5b.t](references/phases-core.md) | Fires only when mode is `promote`; skipped in every other mode |
| 6 | Refresh Agent Pipeline + Compaction Guidance + Behavioral Contract + Praxion Process blocks via `refresh_claude_blocks.py --apply`, then append the Project Essentials block, to `CLAUDE.md` (+ `## Hackathon Mode` when Phase 5b enabled it) | `refresh_claude_blocks.py`'s own absent/current/stale/modified classification for the four core blocks (no heading-check); `## Working in this project` heading detection for Project Essentials |
| 7 | Print companion-CLI install commands (advisory) | None — purely informational |
| 8 | Architecture baseline — delegate to `systems-architect` in baseline mode → `.ai-state/DESIGN.md` + `docs/architecture.md` (+ optional ADR draft) | `test -e .ai-state/DESIGN.md` OR `test -e docs/architecture.md` (skip if either exists) OR `arch` not selected in the Profile (G3) |
| 8b | AaC tier install — fence seed, `fitness/` scaffold, golden-rule Block D, `architecture.yml` workflow, `docs/diagrams/` scaffold | `aac` not selected in the Profile (G3); or per-sub-step predicates (see §Phase 8b) |
| 8c | ML/AI training scaffold — experiment tracking config, checkpoint `.gitignore` block, GPU budget declaration, `program.md` template, mode callout | No ML signals detected AND `ml` not selected in the Profile (G3); per-sub-step predicates (see §Phase 8c) |
| 8d | Obsidian integration — `.gitignore` Obsidian block, verify `obsidian@obsidian-skills` plugin install, `CLAUDE.md` Obsidian Integration block, `settings.json` deny entries | `obsidian` not selected in the Profile (G3); per-sub-step predicates (see §Phase 8d) |
| 8e | Code-quality baseline — universal `.editorconfig` + pre-commit config + `CONTRIBUTING.md` + per-detected-stack linter/formatter/type-check config + dependency-scanning config + ci-autofix caller/policy installed from canonical assets (never overwriting existing config) | `quality`/`ci` not selected in the Profile (G3); per-sub-step predicates (see §Phase 8e) |
| 9 | Print summary + stage modified files (no commit) | None — terminal phase |

## §Capability IDs — the user-facing vocabulary

Phase identifiers stay verbatim **internally** — the `## §Phase N` headings in `references/phases-core.md`/`references/phases-optional.md`, `contract.py`'s heading grammar, and `upgrade_project_pins.sh`'s lock-step comments are unchanged. Everything the *user* sees — CLI flags, the Profile checkboxes (Gate G3 below), progress lines, the run summary, `argument-hint` — speaks capability IDs instead. This table is published **once**, here, as the single join point between the two vocabularies; no other file restates it.

| Capability ID | Phases | Default derivation |
|---|---|---|
| `core` | `0.5, 1, 2, 3, 4, 6, 7, 9` | Always on, not selectable — the invariant end-state contract |
| `observability` | `5` | On — the `PRAXION_DISABLE_*` toggle written by Phase 5's observability sub-step |
| `arch` | `8` | On; off if `.ai-state/DESIGN.md` or `docs/architecture.md` already exists |
| `quality` | `8e.1, 8e.2, 8e.3, 8e.4, 8e.5, 8e.6, 8e.7` | On; off if no stack detected |
| `ci` | `8e.8, 8e.9` | Off by default — the only capability with out-of-band prerequisites (two `gh secret set` calls); on only under `--profile all` |
| `aac` | `8b` | Off; on under `--profile all` |
| `ml` | `8c` | On iff ML signals detected (§Pre-flight step 4b) |
| `obsidian` | `8d` | Detection-gated — on only when both the `claude` CLI and the `obsidian@obsidian-skills` marketplace plugin are present |

Two phase ids are deliberately not covered above because they are not user-selectable — they are mode-implied, not capability-selected: `0s` (seed pipeline — implied by `new` mode) and `5b`/`5b.t` (hackathon install/teardown — implied by `hackathon`/`promote` mode).

## §Mode × Phase Matrix

Four modes over one phase engine: `new` (empty dir, seeded via [references/seed-pipeline.md](references/seed-pipeline.md)), `existing` (retrofit — the default flow above), `hackathon` (minimal install, promotable), `promote` (hackathon → fully managed). `run` = always runs; `dflt-Y`/`dflt-N` = the capability's derived default from §Capability IDs; `skip` = phase not offered in this mode. **`promote` inherits the `existing` column in full, except 5b.t (teardown) fires only under `promote`.**

| Phase | `new` | `existing` | `hackathon` |
|---|---|---|---|
| 0 (pre-flight) | run | run | run |
| 0s (seed pipeline) | run | skip | skip |
| 0.5 (`CLAUDE.md` bootstrap) | run | run | run |
| 1–4 (`core`) | run | run | run |
| 5 (`observability`) | run | run | run |
| 5b (hackathon install) | dflt-N | dflt-N | run |
| 5b.t (hackathon teardown) | skip | run *iff* mode is `promote` | skip |
| 6, 7 (`core`) | run | run | run |
| 8 (`arch`) | skip¹ | dflt-Y | skip |
| 8b (`aac`) | dflt-N | dflt-N | skip |
| 8c (`ml`) | dflt = ML signals | dflt = ML signals | skip |
| 8d (`obsidian`) | dflt = detection | dflt = detection | skip |
| 8e.1–8e.7 (`quality`) | dflt = stack detected | dflt = stack detected | skip |
| 8e.8–8e.9 (`ci`) | dflt-N | dflt-N | skip |
| 9 (`core`) | run | run | run |

¹ The `0s` seed pipeline's own architect step already writes `.ai-state/DESIGN.md` + `docs/architecture.md`, so `arch`'s default-derivation rule (off when either file exists) makes this skip mechanical, not hardcoded.

## §Phase Gates

Three gates total, in every mode — replacing the 25 old per-phase pauses (14 from the former per-phase table above, 11 from the former `/new-project` seed pipeline) and the one-way escape hatch that used to skip the remaining ones. A gate that carries no decision earns no interruption; detection (§Pre-flight) already computes a correct default for everything except three genuinely open questions.

**Fallback.** If `AskUserQuestion` is unavailable (tool error, headless invocation), print the gate's headline as a chat message, apply the stated default, and proceed without blocking. Do not fail the onboarding because a gate cannot fire.

### G1 — Mode confirm

**Fires when:** detection (§Pre-flight / [references/detection.md](references/detection.md)) is ambiguous between two states, or a hackathon/promote state is detected with no `--mode`/`--full`/`--hackathon` flag supplied. Suppressed by unambiguous detection, `--yes`, or an explicit `--mode`.
**Form:** 2–3 option `AskUserQuestion`, default = the detected mode. When hackathon state is detected with no flag, the options are `Promote to fully managed` (default) and `Stay in hackathon mode (refresh only)`.

### G2 — Build intent

**Fires when:** mode is `new` and neither `--brief` nor `--yes` was supplied.
**Form:** free-text `AskUserQuestion`, "What would you like to build?" — default (no answer given) is a mini coding agent (Claude Agent SDK + web UI). Bypass with `--brief "<text>"` or `--yes`.

### G3 — Profile

**Fires when:** always, unless `--yes`, `--profile`, `--with`, or `--without` was given. Fires once, before any write.
**Form:** one `AskUserQuestion` multiSelect, pre-checked from detection per the §Capability IDs derivation rules above — `core` is not offered (always on); every other capability row shows its default checkbox state and the detection evidence that produced it.

## §Idempotency Predicates — per-phase contracts

| Phase | Predicate (skip if true) |
|-------|--------------------------|
| 1 | `grep -q '^# AI assistants$' .gitignore` |
| 2 | Per-file: `test -e .ai-state/<file>` for every target listed in §Phase 2 — skip files individually, never as a phase |
| 3 | `grep -qF '.ai-state/observations.jsonl merge=observations-jsonl' .gitattributes` AND `git config --get merge.observations-jsonl.driver` returns a value containing `praxion` |
| 4 | `readlink .git/hooks/pre-commit` resolves to a Praxion-shipped file (or the file is a script containing `check_id_citation_discipline`) AND each of `readlink .git/hooks/{post-merge,post-commit,post-checkout}` resolves to a path containing `/praxion/` (target ending in `git-finalize-hook.sh`, or the legacy `git-post-merge-hook.sh` for the post-merge slot only) |
| 5 | Per-sub-step, never phase-level: 5a — `PRAXION_DISABLE_OBSERVABILITY` key present under `.env` in `.claude/settings.json` (any value); 5b — every required allow entry present (subset check: `jq -e --argjson req '[...]' '($req - (.permissions.allow // [])) \| length == 0' .claude/settings.json`) |
| 5b | Entire phase: `PRAXION_HACKATHON_MODE=1` present under `.env` in `.claude/settings.json`; or mode is not `hackathon`/`promote`. Per-artifact: 5b.1 — `PRAXION_HACKATHON_MODE` key present in `.claude/settings.json` env; 5b.2 — `grep -q '^## Hackathon Mode$' CLAUDE.md`; 5b.3 — `grep -q 'hackathon' .claude/praxion-rules.yaml 2>/dev/null`; 5b.4 — `test -f scripts/praxion-hackathon`; 5b.5 — `test -f .claude/hackathon-directive.md`; 5b.6 — `test -f .claude/hackathon-settings.json` |
| 5b.t | Entire phase: mode is not `promote` (skip). See [references/phases-core.md § Sub-step 5b.t](references/phases-core.md) for the per-artifact template-compare-then-skip-or-remove predicate. |
| 6 | `refresh_claude_blocks.py`'s own absent/current/stale/modified classification for the four core blocks (`## Agent Pipeline`, `## Compaction Guidance`, `## Behavioral Contract`, `## Praxion Process` — no heading-check predicate); `grep -q '^## Working in this project$' CLAUDE.md` for the Project Essentials block (plus `## Hackathon Mode` if Phase 5b was enabled) |
| 7 | None — phase 7 is advisory and always runs |
| 8 | `test -e .ai-state/DESIGN.md` OR `test -e docs/architecture.md` (skip phase if either doc exists — covers re-runs and greenfield-followed-by-onboard); also skipped if `arch` was not selected in the Profile (G3) |
| 8b | `aac` not selected in the Profile (G3) — skips entire phase. Per-sub-step: 8b.1 — arch doc contains `aac:generated` or `aac:authored`; 8b.2 — `test -d fitness/`; 8b.3 — `grep -qe check_aac_golden_rule -e 'Block D' .git/hooks/pre-commit` (repeated `-e` rather than an alternation: a pipe inside a table cell is either a cell delimiter or, escaped, renders as a bare `|` — and BRE and ERE read the escaped and unescaped forms in opposite directions, so no single alternation is correct both as authored and as rendered); 8b.4 — `test -e .github/workflows/architecture.yml`; 8b.5 — `test -d docs/diagrams/` |
| 8c | No ML signals detected AND `ml` not selected in the Profile (G3) — skips entire phase. Per-sub-step: 8c.1 — `test -d .ai-state/experiments/`; 8c.2 — `grep -q '# ML training checkpoints' .gitignore`; 8c.3 — `test -e .ai-state/gpu_budget.yaml`; 8c.4 — `test -e program.md`; 8c.5 — none (always prints) |
| 8d | `obsidian` not selected in the Profile (G3) — skips entire phase. Per-sub-step: 8d.1 — `grep -q '^# Obsidian$' .gitignore`; 8d.2 — `command -v claude >/dev/null 2>&1` (if absent, skip 8d.3–8d.6); 8d.3 — `claude plugin list 2>/dev/null | grep -q "obsidian@obsidian-skills"` (if absent, skip 8d.4–8d.6); 8d.4 — `jq -e '(.useMarkdownLinks == true) and (.alwaysUpdateLinks == false)' .obsidian/app.json` exits 0 (both link-safety keys pinned); 8d.5 — `grep -q '^## Obsidian Integration$' CLAUDE.md`; 8d.5b — all required deny entries present (subset check: `jq -e --argjson req '[...]' '($req - (.permissions.deny // [])) | length == 0' .claude/settings.json`) |
| 9 | None — terminal phase always runs |

**Re-running the command** on an already-onboarded project should print mostly `skipped (already onboarded)` lines in Phase 9's summary. The only writes on a clean re-run come from Phase 7 (which writes nothing — only prints) and Phase 9 (which only stages changed files). Phase 8 is naturally idempotent — once `.ai-state/DESIGN.md` exists, any subsequent re-run skips. Future *updates* to architecture docs come from feature pipelines (`systems-architect` updates them in Phase 4 of the agent pipeline), not from re-running `/onboard-project`.

**Test for idempotency**: run `/onboard-project`, accept the Profile (G3), then re-run `/onboard-project`. The second run should produce zero `git diff` output and zero new `git config` entries. If either runs, the predicate for that phase has a bug.
