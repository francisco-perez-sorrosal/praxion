# Praxion Onboarding — Core Phase Bodies

Always-on phase bodies for `skills/onboard-project/SKILL.md` — phases 0.5, 1, 2, 3, 4, 5, 5b, 6, 7, and 9. See [../SKILL.md](../SKILL.md) for §Pre-flight, §Flow, §Phase Gates, and §Idempotency Predicates.

## §Phase 0.5 — `CLAUDE.md` bootstrap (conditional)

**Runs only when `CLAUDE.md` is absent** (detected at §Pre-flight step 4d). When `CLAUDE.md` already exists, skip this phase entirely — no gate, no write — and proceed to §Flow. The common path is unchanged.

**Why this phase exists.** Phases 5b, 6, and 8d append Praxion blocks to `CLAUDE.md`. Without a `CLAUDE.md` to append to, those phases would skip and the user would silently lose the core onboarding payload (the Agent Pipeline, Behavioral Contract, Praxion Process, and Working-in-this-project guidance). This phase guarantees a `CLAUDE.md` exists before any block-append phase runs.

**Predicate.** `test -e CLAUDE.md` is true → skip the entire phase (Phase 6 will append to the existing file).

**Gate 0.5.** When `CLAUDE.md` is absent AND the `no-more-gates` flag is not set, fire `AskUserQuestion` with `header: "CLAUDE.md"`, `multiSelect: false`, and the Gate 0.5 headline from the gate map (two options: `Generate from codebase` (default) / `Minimal stub`). When `no-more-gates` is set, apply the default (`Generate from codebase`).

**Action (only when `CLAUDE.md` is absent).**

1. **Prefer `/init`** (when the user chose `Generate from codebase`). Invoke the official Claude `/init` command — it analyzes the codebase and writes a `CLAUDE.md` describing what actually exists. This mirrors `/new-project`'s greenfield step 9.

2. **Verify, then fall back — never leave the project without a `CLAUDE.md`.** After the `/init` attempt, check `test -e CLAUDE.md`:
   - If `/init` produced a `CLAUDE.md`, continue to §Flow.
   - **If `CLAUDE.md` is still absent** (`/init` could not be invoked in this execution context — it is a built-in command and may not be programmatically callable mid-command), generate it **inline**: analyze the codebase — project purpose (README / package metadata), primary stack (from §Pre-flight stack detection), entry points, and the build/test/lint/type-check commands (`pyproject.toml` / `package.json` / Makefile / the project's test gate) — and Write a concise `CLAUDE.md` at the project root with a one-paragraph description, a short structure note, and a `## Commands` section listing the *verified* commands. Keep it factual; do not invent. Leave a `# TODO:` for anything undeterminable. (This init-equivalent content is later enriched by Phase 6's §Project Essentials Block.)

3. **Minimal stub** (when the user chose `Minimal stub`). Write only:
   ```markdown
   # <project name>

   <!-- TODO: Describe this project — purpose, structure, and build/test/lint commands.
        Run /init for a codebase-aware version, or fill this in by hand. -->
   ```
   Derive `<project name>` from the directory name or package metadata. The Praxion blocks (Phase 6) still append cleanly onto the stub.

**Idempotency.** Guarded by `test -e CLAUDE.md` — a re-run after `CLAUDE.md` exists is a complete no-op. Phase 6's per-heading `grep` predicates independently prevent block duplication.

**§Phase 9 summary line.** `Phase 0.5: CLAUDE.md bootstrapped (/init | inline-generated | minimal stub)` or `skipped (CLAUDE.md already present)`.

## §Phase 1 — `.gitignore` hygiene

**Predicate.** Detect the block via `grep -q '^# AI assistants$' .gitignore`. If present, skip the phase entirely.

**Action.** If `.gitignore` does not exist, create it with the block. Otherwise append the block as a trailing section:

```gitignore
# AI assistants
.ai-work/
.ai-state/*.lock
.ai-state/**/*.lock
.ai-state/*.backup.json
.ai-state/observations.jsonl.1
.claude/settings.local.json
.claude/worktrees/
.env
.env.*
.env.local
tmp/
```

**Why each line:**

| Entry | What it excludes | Why |
|-------|------------------|-----|
| `.ai-work/` | Ephemeral pipeline scratch (per-task slug) | Deleted at pipeline end; never useful in history |
| `.ai-state/*.lock`, `.ai-state/**/*.lock` | Advisory file locks taken by `finalize_adrs.py`, merge drivers | Runtime-only — committing them masks real lock behavior |
| `.ai-state/*.backup.json` | Temporary local snapshots | Local recovery only |
| `.ai-state/observations.jsonl.1` | Local WAL rotation archive | Local WAL rotation archive — gitignored; rows are already in git history before rotation moves them. |
| `.claude/settings.local.json` | Per-machine Claude settings | Machine-specific |
| `.claude/worktrees/` | Worktree home for `EnterWorktree` | Each branch's own checkout |
| `.env`, `.env.*`, `.env.local` | Secrets | Never commit secrets |
| `tmp/` | Scratch working files | The always-loaded conventions direct every writer here ("temp files in `tmp/`"), so the protection has to exist — otherwise the instruction hands out a path one `git add -A` away from being committed |

**Separately:** if `.gitignore` *excludes* `.ai-state/` (line `.ai-state/` or `.ai-state` with no glob suffix), warn:

> `.ai-state/` is excluded but should be committed — it holds persistent project intelligence (ADRs, idea ledger, sentinel reports, tech-debt ledger). Remove the exclusion?

If the user agrees, remove that line. If they decline, proceed without changing it but note the choice in the Phase 8 summary.

## §Phase 2 — `.ai-state/` skeleton

**Canonical schemas.** TECH_DEBT_LEDGER schema (14 row fields + structural `dedup_key`), producer/consumer contracts, and dedup semantics: [`skills/software-planning/references/tech-debt-ledger.md`](../skills/software-planning/references/tech-debt-ledger.md) (summary + pointer in `rules/swe/agent-intermediate-documents.md` § `TECH_DEBT_LEDGER.md`). DECISIONS_INDEX format and calibration_log format: `rules/swe/agent-intermediate-documents.md`. The skeletons below are header-only seeds — agents populate rows over time per the canonical contracts. ADR fragment naming and lifecycle live in `rules/swe/adr-conventions.md`. The three `CONSULT_*.md` skeletons are the one exception to *brief*: the convening instructions cite `<file> § Column Definitions` as the schema, so each file **is** its own schema anchor and must ship with that section complete rather than pointing elsewhere.

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

  Living, append-only ledger of grounded debt findings. Producers (verifier, sentinel, orchestrator, architect-validator) append rows; consumers update `status` in place. Schema (14 row fields + structural `dedup_key`): [`skills/software-planning/references/tech-debt-ledger.md`](../skills/software-planning/references/tech-debt-ledger.md).

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

- `.ai-state/praxion_feedback/PENDING.md` (header-only skeleton) — the managed-project-side capture ledger for the healing sidecar (`/report-praxion-issue`, a Praxion-origin ecosystem-defect reporting channel). The reporter script and the command are plugin-global (no per-project copy needed); the SessionStart advisory hook ships with the plugin via `hooks/hooks.json` (already registered — no additional per-project wiring required). This skeleton is the entire per-project install footprint for the sidecar.

  **Predicate (skip if present).** If `.ai-state/praxion_feedback/PENDING.md` already exists, skip — never overwrite (the project may already hold captured candidates).

  **Action.** Create `.ai-state/praxion_feedback/` if missing, then write:
  ```markdown
  # Pending Praxion Feedback

  Candidate ecosystem-defect reports awaiting `/report-praxion-issue`. This file is git-committed and mechanically sanitized at capture time.
  ```

- **The three consult ledgers** — `.ai-state/CONSULT_LEDGER.md`, `.ai-state/CONSULT_COSTS.md`, `.ai-state/CONSULT_PRIORS.md`.

  **Why these ship.** The discipline-consult mechanism's *producer* is plugin-global: `agents/discipline-consultant.md`, `commands/consult.md`, and the convening rules all install with the plugin, so any managed project can convene a consult on day one. Its convener is then instructed to append rows to these three files, and to read their `## Column Definitions` as the schema. Without the skeletons the producer ships and the consumer does not — the convener is told to append to files that do not exist, and the schema pointer in its own instructions dangles. These are the entire per-project install footprint for the mechanism; nothing else is copied.

  **Predicate (skip if present).** Each file is checked individually with `test -e`. An existing file is never overwritten — it already holds committed observations, and these ledgers are append-only.

  **Action.** For each of the three missing files, write the skeleton below verbatim. Header-only — **never seed an example row.** These files are read as data series; a fabricated row is indistinguishable from an observation and permanently contaminates every count computed over them.

  `.ai-state/CONSULT_LEDGER.md`:
  ```markdown
  # Consultation Disposition Ledger

  Append-only. One row per dispositioned discipline-consultant challenge. **Single writer: the convener** — the party that spawned the consultant (the systems-architect in pipeline mode, the orchestrator under `/consult`). The consultant never writes this file; it authors only its own `CONSULT_<discipline>.md` fragment.

  **Append new rows as the last row of the data table below — never after the `## Column Definitions` section.** No row is ever edited or deleted. A disposition revisited later is appended as a new row; both remain part of the record.

  | timestamp | task-slug | discipline | stage | challenge-id | claim | decision-at-stake | disposition | rationale-ref | model | difficulty |
  |---|---|---|---|---|---|---|---|---|---|---|

  ## Column Definitions

  - **timestamp** — ISO 8601 UTC of the disposition, `YYYY-MM-DDTHH:MM:SSZ`.
  - **task-slug** / **discipline** / **stage** — the consult's identity triple, and the join key to the two sibling ledgers. `(task-slug, discipline)` alone is not unique: one discipline may attach at two stages within a single task, and those are two independent consults.
  - **challenge-id** — the `### CH-NN` id from the consultant's `CONSULT_<discipline>.md` fragment.
  - **claim** — the challenge's one-line falsifiable claim. Escape any literal `|` as `\|`.
  - **decision-at-stake** — the decision that claim would change, copied from the challenge's own field.
  - **disposition** — exactly one of `switch-now` | `defer-with-rationale` | `dismiss-with-rationale`.
  - **rationale-ref** — where the disposition's reasoning lives. **The target must be durable**: an ADR id, a tech-debt row, or a section of a committed document — **never** a path under `.ai-work/`, which is deleted at pipeline cleanup and would leave the reasoning unrecoverable while the row still *looks* recorded. Each disposition has a durable home: `switch-now` → the ADR or committed section it changed; `defer-with-rationale` → a tech-debt row when residual risk remains, else the plan section stating the deferral and its trigger; `dismiss-with-rationale` → a `wontfix` tech-debt row when the reasoning is worth keeping. The dismissal case is the one most often skipped and the one that costs most — why an objection does not apply *here* is exactly the constraint a later agent would otherwise re-derive from scratch.
  - **model** — the model tier that ran the consult.
  - **difficulty** — the difficulty hint used: `routine` | `standard` | `high-stakes`.
  ```

  `.ai-state/CONSULT_COSTS.md`:
  ```markdown
  # Consultation Cost Series

  Append-only. One row per consult spawn, written at disposition time alongside that consult's `CONSULT_LEDGER.md` rows. **Single writer: the convener.** Kept separate from the ledger because the ledger's grain is one row per challenge, and cost is a property of the consult.

  **Append new rows as the last row of the data table below — never after the `## Column Definitions` section.** No row is ever edited or deleted. A consult re-spawned on a loop-back appends a *second* row for the same triple rather than mutating the first; aggregation sums rows per triple.

  | timestamp | task-slug | discipline | stage | tokens | model | difficulty | notes |
  |---|---|---|---|---|---|---|---|

  ## Column Definitions

  - **timestamp** — ISO 8601 UTC; matches this consult's `CONSULT_LEDGER.md` rows.
  - **task-slug** / **discipline** / **stage** — the join key to `CONSULT_LEDGER.md`; the triple is the consult's identity.
  - **tokens** — the aggregate subagent token count the harness surfaces to the convener at that consult's completion. Digits only, no separators. A **raw observation**, never a derived or price-weighted figure.
  - **model** — the tier that actually ran the consult. Load-bearing: tokens without a tier cannot be re-priced, and an all-`opus` numerator over a mixed-tier denominator is a biased comparison. Must equal the `model` on this consult's ledger rows.
  - **difficulty** — `routine` | `standard` | `high-stakes`. Must equal the `difficulty` on this consult's ledger rows.
  - **notes** — free text: provenance, loop-back increments, anything a later reader needs. Escape any literal `|` as `\|`.

  **No `cost_usd` column.** A dollar figure decays with every price change and would inject a derivation into a file of raw observations. `tokens` + `model` is durable and re-priceable in a single pass.

  **Not recorded here.** A spawn that never became a consult (blocked at discipline resolution) produces no cost row — folding a resolution failure into the cost distribution would contaminate it.
  ```

  `.ai-state/CONSULT_PRIORS.md`:
  ```markdown
  # Consultation Prior Register

  Append-only, two tables written at two moments. **Single writer: the convener.** The consultant never writes this file and never reads it — it is the convener's compressed statement of the concerns it already held about the very draft the consultant's independent first round is kept away from, which is what makes "did the consult surface anything new?" answerable at all.

  `## Sealed Priors` is written **and committed before the spawn** — the seal is the commit, not the working-tree write. `## Challenge Classification` is written at disposition time, alongside that consult's `CONSULT_LEDGER.md` rows.

  **Append new rows as the last row of the table they belong to — never after a prose section.** No row is ever edited or deleted.

  ## Sealed Priors

  | timestamp | task-slug | discipline | stage | prior-id | source | concern |
  |---|---|---|---|---|---|---|

  ## Challenge Classification

  | timestamp | task-slug | discipline | stage | challenge-id | classification | matched-prior-id | seal-witness | prompt-areas |
  |---|---|---|---|---|---|---|---|---|

  ## Column Definitions

  **`## Sealed Priors`** — written before the spawn:

  - **timestamp** — ISO 8601 UTC of the seal write; must be *earlier* than this consult's ledger rows.
  - **task-slug** / **discipline** / **stage** — the consult's identity triple; the join key to the sibling ledgers.
  - **prior-id** — `P-01`, `P-02`, … unique within the triple. The reserved value `NONE` is the explicit empty declaration; when present it must be the only row for the triple.
  - **source** — `lens` (surfaced by the pass over the discipline's bound skill) | `prior` (already held before that pass). Recording provenance costs one column and lets a later reader separate what the lens found from what the convener knew anyway.
  - **concern** — one line naming the element of the draft and the property at issue, not the topic — specific enough that a reader can judge whether a given challenge is the same concern. **One concern = one `challenge-obligations` clause of the bound skill, failing at one identified site**: two sites failing one clause are two rows; one site failing two clauses is two rows. Escape any literal `|` as `\|`.

  **`## Challenge Classification`** — written at disposition:

  - **timestamp** — matches this consult's `CONSULT_LEDGER.md` rows.
  - **task-slug** / **discipline** / **stage** — the same triple.
  - **challenge-id** — the `### CH-NN` id; the same value the ledger row carries.
  - **classification** — `novel` | `matched`. `matched` means the sealed list already held this concern.
  - **matched-prior-id** — the `P-NN` when `matched`; **empty** when `novel`. Must resolve to a `Sealed Priors` row of the same triple.
  - **seal-witness** — the consultant's `**Round-0 HEAD:**` sha, transcribed verbatim.
  - **prompt-areas** — how many attack areas the spawn prompt explicitly enumerated; `0` when it named none. The convener writes both the spawn prompt and the sealed list, and prompt specificity moves the novelty rate without touching either — so the series records it to stratify on it rather than be silently confounded by it.

  The two enums are deliberately **disjoint** (`{lens, prior}` vs `{novel, matched}`) so a `grep` can tell the two tables apart on a single cell match, with no parser.
  ```

- `.ai-state/principles.yaml` — the eight dimensions of beautiful code seeded as advisory project principles, from `${PLUGIN_INSTALL_PATH}/claude/project-baseline/principles.yaml.tmpl`.

  **Why this ships.** The project-principles mechanism's *consumers* are plugin-global: the implementation-planner threads matching principles into step acceptance criteria (Phase 1b) and the verifier gates them per severity (Phase 4.5) — both activate the moment `.ai-state/principles.yaml` exists and is non-empty, in any managed project. Without a seed, the mechanism ships and stays silent: the dimensions engraved in the philosophy and the `beautiful-code` skill never become an active gate in the project's own pipeline. The seed's eight rows are all `severity: advisory` (WARN, never FAIL), and the file belongs to the project from the moment it lands — edit statements, narrow scopes to the project layout, promote rows to `blocking`, or delete rows that do not apply.

  **Predicate (skip if present).** If `.ai-state/principles.yaml` already exists, skip — never overwrite: the project may have edited statements, narrowed scopes, or promoted severities, and those decisions are the project's own.

  **Action.** Copy `${PLUGIN_INSTALL_PATH}/claude/project-baseline/principles.yaml.tmpl` to `.ai-state/principles.yaml`, stripping the leading template-doc comment block (the lines from `# -- template-doc` through the first `# ---` divider); keep the retained header comments — they document ownership and the consumer contract for the project's readers. If the plugin install path was not detected at pre-flight (skip-phase-4 flag set), skip this sub-step and emit: `Skipping principles.yaml seed — install the plugin and re-run /onboard-project. Without it, the beautiful-code dimensions are documented but never gate this project's pipeline.` Print on success: `Phase 2: .ai-state/principles.yaml seeded (8 advisory principles — the beautiful-code dimensions; edit freely, it is yours)`.

Do NOT create `.ai-state/observations.jsonl` — that is written on first use by the observability hook. Pre-creating it confuses the semantic merge driver.

## §Phase 3 — `.gitattributes` + merge driver registration

**Why this phase exists.** Line-based merge corrupts structured data. `.ai-state/observations.jsonl` (event log) is a merge-conflict target when concurrent edits land — the semantic merge driver reconciles it at the JSONL level instead. The full `.ai-state/` safety contract at PR time, including merge policy and the squash-merge ban for `.ai-state/`-touching branches, lives in `rules/swe/vcs/pr-conventions.md`.

**Predicate (version-aware).** Detect the `.gitattributes` entry via exact-line `grep -qF '.ai-state/observations.jsonl merge=observations-jsonl' .gitattributes`. Detect driver registration via `git config --get merge.observations-jsonl.driver`. The registration is **stale** (and must be re-registered, not skipped) when the registered command contains `/praxion/` but its path is NOT the live `${PLUGIN_INSTALL_PATH}` captured at pre-flight — see [shared-procedures.md § Version-aware staleness comparison rationale](shared-procedures.md#-version-aware-staleness-comparison-rationale) for why a full-path comparison is required.

**Cross-version cleanup.** Read the prior onboard manifest `.ai-state/.praxion-onboard.json` if present (written by §Phase 9 of an earlier run). For every merge driver named in its `artifacts.merge_drivers` that is NOT in the current expected set (`observations-jsonl` only), the feature was retired between versions: `git config --unset merge.<name>.driver` (ignore failure if already absent) and delete its `.gitattributes` line. Example: a project onboarded by an older version carries `.ai-state/memory.json merge=memory-json`; the `memory-json` driver was dropped, so onboarding must remove both the git-config entry and the `.gitattributes` line rather than leaving a `.gitattributes` mapping to a driver that no longer exists. Only touch Praxion-managed entries (driver value contains `/praxion/` or `merge_driver_`); never remove a user's own driver.

**Action.**

1. **Append to `.gitattributes`** (create the file if missing):
   ```gitattributes
   # Praxion semantic merge drivers — see rules/swe/agent-intermediate-documents.md
   .ai-state/observations.jsonl merge=observations-jsonl
   ```

2. **Register (or re-register) the driver in this repo's `git config`**. Run this whenever the driver is absent OR the predicate flagged a stale `/praxion/` path — `git config` overwrites in place, upgrading a stale-version pin to the live install path:
   ```bash
   git config merge.observations-jsonl.driver "python3 ${PLUGIN_INSTALL_PATH}/scripts/merge_driver_observations.py %O %A %B"
   ```
   `${PLUGIN_INSTALL_PATH}` is the value captured in §Pre-flight. If the plugin was not detected (skip-phase-4 flag is set), still write `.gitattributes` but emit a warning: `Merge driver not registered — run 'git config merge.observations-jsonl.driver "..."' manually after installing the plugin. Without this, .ai-state/observations.jsonl will be corrupted by line-based merge on first concurrent edit.`

3. **Conflict check.** If `git config --get merge.observations-jsonl.driver` already returns a value that does NOT contain `praxion` and is NOT empty, refuse to overwrite. Print: `merge.observations-jsonl.driver is already set to '<value>' — refusing to overwrite. Remove the existing driver manually if you want Praxion's, or leave as-is.`

## §Phase 4 — Git hooks

**Why these hooks.** The pre-commit hook enforces id-citation discipline — committed code must not reference ephemeral pipeline ids (`REQ-NN`, `AC-NN`, `Step N`, draft ADR hashes). Rationale, exempt paths, and escape hatch live in `rules/swe/id-citation-discipline.md`.

Three finalize hooks (post-merge, post-commit, post-checkout) all symlink to a single multiplexed dispatcher (`scripts/git-finalize-hook.sh`) that reads `basename($0)` and dispatches to the matching entry point in `scripts/finalize_chain.sh`. The trio is state-driven: each entry point gates on "are we on main with drafts present?" so draft ADRs landing on main via any path eventually promote — fast-forward merges (post-merge), direct commits / non-ff merges / rebases / cherry-picks (post-commit), branch switch / fresh clone / reset (post-checkout). Single-trigger coverage misses real cases (a branch reset to main, a fresh clone with drafts on main, a fast-forward pull) where drafts otherwise sit in `decisions/drafts/` indefinitely.

Composition per trigger: `post-merge` runs `reconcile_ai_state.py` (when `.ai-state/` was touched), `finalize_adrs.py --all` and `finalize_tech_debt_ledger.py --all` (when on main with drafts), then `check_squash_safety.py` (always, as a non-blocking diagnostic). `post-commit` and `post-checkout` run only the on-main finalize subset. All steps are non-blocking — a hook cannot abort a completed git operation.

**Skip condition.** If §Pre-flight set the `skip-phase-4` flag (plugin not installed), skip this phase entirely and emit: `Skipping Phase 4 — install the plugin and re-run /onboard-project to install hooks.`

**Predicate (version-aware).** Detect existing symlinks via `readlink .git/hooks/<name>` and check whether the target contains `/praxion/`. The user-project pre-commit hook is written inline and resolves the plugin path at run time, so it is version-independent and never goes stale; the three finalize hooks (`post-merge`, `post-commit`, `post-checkout`) all share `git-finalize-hook.sh` as their target. A finalize-hook symlink is **stale** (must be re-pointed, not skipped) when its target contains `/praxion/` but is NOT `${PLUGIN_INSTALL_PATH}/scripts/git-finalize-hook.sh` — see [shared-procedures.md § Version-aware staleness comparison rationale](shared-procedures.md#-version-aware-staleness-comparison-rationale) for why a full-path comparison is required. Each hook that already points at the live target is skipped; absent, stale, or legacy (`git-post-merge-hook.sh` from older versions) hooks are (re-)installed without prompting.

**Action.**

1. **Pre-commit hook** — symlink `.git/hooks/pre-commit` to a *user-project-tailored* hook script. Praxion's own repo uses a `.pre-commit-config.yaml` (the `pre-commit` framework) for its author gates including the shipped-artifact-isolation check (Praxion-author-specific). For user projects, write a tailored hook directly into `.git/hooks/pre-commit` (executable) that runs only `check_id_citation_discipline.py`:
   ```bash
   #!/usr/bin/env bash
   # Praxion commit gate (installed by /onboard-project).
   #
   # 1. ruff pin coherence — blocks when the ruff pinned in
   #    .pre-commit-config.yaml differs from the one this project installs.
   #    Two independently-versioned ruffs formatting the same files never
   #    converge: the hook reformats on commit, you reformat back, and the
   #    commit will not settle. Runs FIRST so the version mismatch is named
   #    rather than presenting as a confusing reformat loop. No-ops on a repo
   #    with no ruff hook. Rationale: rules/swe/vcs/git-conventions.md.
   # 2. id-citation-discipline — blocks commits that reference ephemeral
   #    pipeline ids (REQ-*, AC-*, Step N) in committed source code.
   #    Rationale: rules/swe/id-citation-discipline.md.
   set -eo pipefail
   REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
   [ -z "$REPO_ROOT" ] && exit 0
   PLUGIN_ROOT="$(jq -r '.plugins["praxion@bit-agora"][0].installPath' "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null)"

   PIN_CHECK="${PLUGIN_ROOT}/scripts/check_ruff_pin_drift.py"
   [ -f "$PIN_CHECK" ] && python3 "$PIN_CHECK" --repo-root "$REPO_ROOT"

   CHECK="${PLUGIN_ROOT}/scripts/check_id_citation_discipline.py"
   [ ! -f "$CHECK" ] && exit 0
   STAGED="$(git diff --cached --name-only --diff-filter=ACMR || true)"
   [ -z "$STAGED" ] && exit 0
   # shellcheck disable=SC2086
   python3 "$CHECK" --repo-root "$REPO_ROOT" --files $STAGED
   ```
   `chmod +x .git/hooks/pre-commit` after writing. Resolving the plugin path at hook-run time means plugin upgrades (different install paths) flow automatically.

   **If `.git/hooks/pre-commit` already exists and is NOT a Praxion hook**, back it up to `.git/hooks/pre-commit.pre-praxion` and warn the user. Do not silently overwrite a non-Praxion hook.

   **If it already exists and IS a Praxion hook, the hook BODY can still be stale.** Runtime `PLUGIN_ROOT` resolution keeps the *script paths* fresh; it does nothing for checks added to the hook after this project was onboarded. Those arrive only by editing the installed file. Apply a content-aware top-up, mirroring §Phase 8b.3's predicate style:

   | Predicate | Action |
   |---|---|
   | Hook does NOT contain `check_ruff_pin_drift` | Insert the `PIN_CHECK` stanza (the two lines above the `CHECK=` assignment) and report `4: pre-commit hook topped up (ruff pin coherence)` |
   | Hook already contains it | Skip with `4: pre-commit hook current` |

   **Insert; do not regenerate.** §Phase 8b.3 *appends* a Block D fragment to this same file, so rewriting the hook wholesale would silently delete Block D from every project that installed the AaC tier. Add the missing stanza in place and leave everything else untouched.

   When adding a future check to this hook, add its predicate row here in the same pass — otherwise already-onboarded projects never receive it, which is the defect this table exists to prevent.

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

## §Phase 5 — `.claude/settings.json` toggles + `permissions.allow` baseline

The Praxion plugin auto-fires hooks on `SessionStart`, `Stop`, `SubagentStart`, `SubagentStop`, `PreToolUse`, `PostToolUse`, `PreCompact`. Some are heavyweight: observability ships events to a localhost Phoenix instance. Users opt out via a `PRAXION_DISABLE_*` env var in `.claude/settings.json`.

This phase owns `.claude/settings.json`. It has two independently-predicated sub-steps: the observability **toggle** (5a) and the **`permissions.allow` baseline** (5b). Evaluate each predicate separately — a project onboarded by an older version already carries the toggle, and a phase-level skip would strand it without the permissions baseline forever.

### Sub-step 5a — observability toggle

**Predicate.** Read `.claude/settings.json` if it exists. If `PRAXION_DISABLE_OBSERVABILITY` is already set (any value), skip **this sub-step** (not the phase — 5b still runs) but report the current value in Phase 9. If the file exists but the key is missing, merge it in using the user's choice below; never overwrite a key the user has already set.

**Gate 5 — toggle picker.** Use `AskUserQuestion` with `multiSelect: true`, header `"Praxion features"`, question `"Should the observability hook be ENABLED in this project? It ships Claude Code events to a localhost Phoenix instance — useful for trace inspection but requires Phoenix to be running. Leave unchecked to disable."`, and this option:

| Option label | Description |
|--------------|-------------|
| `Observability events` | Ship Claude Code events to a localhost Phoenix instance via `send_event.py` (trace inspection) **and** to the local `.ai-state/observations.jsonl` WAL, which lets `/resume-pipeline` localize a partially-completed step when recovering a context-truncated agent. Truncation recovery works without this (Tier-1 git+tests alone); enabling it adds `partial@<file>` localization precision. Phoenix is needed only for trace *visualization* — events drop silently to Phoenix if it is not running, but the WAL (and recovery) are unaffected. |

**Mapping** unchecked option to env var (Praxion uses negative `DISABLE` semantics — `"1"` disables, `"0"` enables):

| Unchecked option | Env var written | Value |
|------------------|-----------------|-------|
| Observability | `PRAXION_DISABLE_OBSERVABILITY` | `"1"` |

Checked option writes `PRAXION_DISABLE_OBSERVABILITY` to `"0"`.

**Action.** Write `.claude/settings.json` (creating `.claude/` if needed):

```json
{
  "env": {
    "PRAXION_DISABLE_OBSERVABILITY": "<value>"
  }
}
```

If `.claude/settings.json` already exists with other keys (e.g., `permissions`, `model`), merge `env` non-destructively — preserve all existing top-level keys and pre-existing `env.*` entries.

### Sub-step 5b — `permissions.allow` baseline

**Why this sub-step exists.** A spawned subagent has no way to answer an interactive permission prompt. When one fires, the subagent's tool call is simply denied — and the pipeline stalls mid-run, with a failure that reads like a path or sandbox problem rather than a missing permission. The main session never sees it, because the orchestrator *can* answer the prompt. The baseline below pre-approves the one call that provably hits this, so a managed project's first pipeline does not fail on a prompt nobody can answer.

**Predicate.** A subset check, so a project onboarded under an older (smaller) entry set gains the missing entries on re-run:
```bash
jq -e --argjson req '["Write(.ai-work/**)"]' \
  '($req - (.permissions.allow // [])) | length == 0' \
  .claude/settings.json 2>/dev/null
```
If exit 0 (no required entry missing): skip with notice `5b: skipped (permissions.allow baseline already present)`.

**Action.** Read `.claude/settings.json` (create `{"permissions":{}}` if absent) and merge `permissions.allow` non-destructively:
- Preserve all existing top-level keys.
- Preserve the existing `permissions.deny` array (§Phase 8d sub-step 8d.5b writes it and preserves `allow` reciprocally, so the two compose in either order).
- Never remove or rewrite an entry the user added. `unique` dedupes, so the merge is idempotent.

```bash
jq '.permissions.allow = ((.permissions.allow // []) + ["Write(.ai-work/**)"] | unique)' \
  .claude/settings.json > .claude/settings.json.tmp && \
  mv .claude/settings.json.tmp .claude/settings.json
```

**Why each entry:**

| Entry | What it pre-approves | Why |
|-------|----------------------|-----|
| `Write(.ai-work/**)` | Subagent writes into the ephemeral pipeline scratch tree | Every pipeline agent writes its artifact here (`SYSTEMS_PLAN.md`, `WIP.md`, `VERIFICATION_REPORT.md`, …). Denied, the agent has no fallback and the stage is lost. The path is gitignored and deleted at pipeline cleanup, so the grant covers nothing durable and nothing shipped. |

**Why the list is one entry.** Each entry is a standing grant the user is never asked about again, so the bar is a denial that is both *observed* and *unanswerable-by-design*. Only `Write(.ai-work/**)` clears it. Writes to `.ai-state/` are committed project intelligence and should stay promptable; `Bash(...)` grants are never installed on a user's behalf; and `Edit` under `.ai-work/` has not been observed to fail, so pre-approving it would be a guess. Extend this list when a real denial is observed and the entry can be justified in one line — never in anticipation.

Print: `5b: permissions.allow baseline written to .claude/settings.json`.

### Optional: Rule Blacklist Configuration

Praxion rules are categorized into core (always-loaded, non-disableable) and disableable (every other rule — hook-deliver and symlinked alike). The per-project `.claude/praxion-rules.yaml` disable list reaches both delivery channels uniformly: hook-deliver rules are filtered from `additionalContext` at SessionStart; symlinked rules get `claudeMdExcludes` entries reconciled into `.claude/settings.json`. To customize which rules your project inherits, create an optional `.claude/praxion-rules.yaml` file:

```yaml
version: 1
disable:
  - swe/agent-model-routing    # Example: disable if your team has a different model routing strategy
  - ml/*                       # Example: disable entire category
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

**Predicate.** `PRAXION_HACKATHON_MODE=1` present under `.env` in `.claude/settings.json` — skip **Gate 5b and the six-artifact write-set below** if already set (fully idempotent re-run). This predicate does **not** gate Sub-step 5b.t, which declares its own independent predicate (stamp `mode == "hackathon"` ∧ resolved mode `promote`) — the teardown must remain reachable precisely when hackathon mode is installed.

**Gate 5b.** When the `no-more-gates` flag is not set, fire `AskUserQuestion` with `header: "Hackathon mode"`, `multiSelect: false`, and the headline from the gate map. When `--hackathon` was passed to the command, auto-default to `Enable hackathon mode` without prompting. When `no-more-gates` is set, apply the default (`Skip — keep full ceremony`). When the user picks `Enable hackathon mode`, run the six-artifact write-set below. When the user picks `Skip — keep full ceremony`, skip Phase 5b entirely.

**Six-artifact write-set.** When enabled, write these six artifacts idempotently (each guarded by its own predicate):

1. **`.claude/settings.json` env key** — add `"PRAXION_HACKATHON_MODE": "1"` to the `env` block (merge non-destructively; never overwrite other keys). **Predicate:** `PRAXION_HACKATHON_MODE` key present in `.claude/settings.json` env block.

2. **`## Hackathon Mode` CLAUDE.md block** — append the §Hackathon Mode Block verbatim to `CLAUDE.md`. **Predicate:** `grep -q '^## Hackathon Mode$' CLAUDE.md`. (`CLAUDE.md` is guaranteed present — §Phase 0.5 bootstraps it before Phase 1.)

3. **`.claude/praxion-rules.yaml` hackathon preset** — merge the three hackathon rule IDs into `.claude/praxion-rules.yaml`. **Predicate:** `grep -q 'hackathon' .claude/praxion-rules.yaml 2>/dev/null` (skip if already present; idempotent re-run never duplicates entries).
   - **If the file does not exist**, create it with:
     ```yaml
     # Hackathon mode preset — saves ~3,500 tokens (ambient, every session)
     disable:
       - swe/agent-model-routing
       - swe/vcs/git-conventions
     ```
   - **If the file already exists**, read it and append the two rule IDs as new list items under the existing `disable:` key (do not emit a second `disable:` block and do not emit `version:`). If no `disable:` key is present yet, add one. Never overwrite or remove existing entries — only add the two missing IDs (skip any that are already listed).

4. **`scripts/praxion-hackathon` wrapper** — copy `claude/aac-templates/praxion-hackathon.sh.tmpl` from the plugin install path to `scripts/praxion-hackathon` and `chmod +x`. Adjust the `PRAXION_DIR` path for the project's `.claude/` directory. **Predicate:** `test -f scripts/praxion-hackathon`.

5. **`.claude/hackathon-directive.md`** — copy `claude/aac-templates/hackathon-directive.md.tmpl` from the plugin install path to `.claude/hackathon-directive.md`. **Predicate:** `test -f .claude/hackathon-directive.md`.

6. **`.claude/hackathon-settings.json`** — copy `claude/aac-templates/hackathon-settings.json.tmpl` from the plugin install path to `.claude/hackathon-settings.json`. **Predicate:** `test -f .claude/hackathon-settings.json`.

**If the plugin install path was not detected** (skip-phase-4 flag set), skip artifacts 4, 5, and 6 and emit: `Skipping hackathon wrapper and settings files — install the plugin and re-run /onboard-project Phase 5b. Artifacts 1–3 (env var, CLAUDE.md block, praxion-rules preset) were written.`

**Phase 5b in the §Phase 9 summary.** Report per-artifact: `Phase 5b: hackathon mode enabled — PRAXION_HACKATHON_MODE=1, ## Hackathon Mode appended, praxion-rules preset added, scripts/praxion-hackathon written, .claude/hackathon-directive.md written, .claude/hackathon-settings.json written` (or `skipped (user chose Skip)` / `skipped (already enabled)`).

### Sub-step 5b.t — Hackathon teardown

**Predicate.** Entire sub-step fires only when the resolved mode is `promote` (hackathon → fully managed); skipped in every other mode, including plain `existing` re-runs of an already-fully-managed project.

**Why this exists.** §Phase 5b installs six artifacts. Today's documented graduation path names only three of them and is gated by nothing — the other three (`scripts/praxion-hackathon`, `.claude/hackathon-directive.md`, `.claude/hackathon-settings.json`) are silently orphaned. Sub-step 5b.t is the *inverse* of §Phase 5b's install: it removes all six, not a subset, and it never uses a recursive delete.

**Enumerate-before-remove.** Before touching anything, build the full removal list — all six install-side artifacts, named explicitly so none can be silently dropped:

1. `PRAXION_HACKATHON_MODE` env key in `.claude/settings.json`
2. `## Hackathon Mode` block in `CLAUDE.md`
3. the hackathon preset entries in `.claude/praxion-rules.yaml`
4. `scripts/praxion-hackathon`
5. `.claude/hackathon-directive.md`
6. `.claude/hackathon-settings.json`

**Template-compare, then remove or skip.** For each of the six, compare the artifact's *current on-disk content* against the template it was installed from (the same canonical source §Phase 5b's install-side reads: `claude/aac-templates/*.tmpl` for artifacts 4–6; the exact literal value/heading/entry for artifacts 1–3). Two outcomes:

- **Matches the template (unmodified since install)** — remove it. Artifacts 1 and 3 are surgical edits (delete the env key / the hackathon entries from `praxion-rules.yaml`, preserving every other key), never a whole-file delete. Artifact 2 removes only the `## Hackathon Mode` section from `CLAUDE.md` (heading through the next `##` heading), never the whole file. Artifacts 4–6 are individually-named single-file deletes (`scripts/praxion-hackathon`, `.claude/hackathon-directive.md`, `.claude/hackathon-settings.json`) — **never a recursive directory removal**, since this is a one-way door acting on a user's repo and a bulk directory delete could not distinguish a hand-added sibling file from the template's own tree.
- **Diverged from the template (hand-edited since install)** — **skip that artifact and warn**: `5b.t: skipped <artifact> — content diverges from the installed template; remove it manually if you no longer need it.` Never force-remove a diverged artifact.

**Action order.** Evaluate and report all six before writing anything (parallels §Phase 5b's own atomic style): print the per-artifact remove/skip decision, then apply the removes, then continue to §Phase 6 onward with the remaining capability profile (per the Mode × Phase Matrix's `existing` column, since `promote` inherits it in full except this sub-step).

**Reporting in the §Phase 9 summary.** `5b.t: promoted from hackathon — removed N of 6 hackathon artifacts (M skipped, diverged from template — see warnings above)`.

## §Phase 6 — `CLAUDE.md` Praxion blocks

**Predicate — one classification mechanism per block class, never two for the same heading.** The seven canonical `CLAUDE.md` blocks split into exactly two classes:

- **Four refreshable blocks** (`REFRESHABLE_SLUGS`: Agent Pipeline, Compaction Guidance, Behavioral Contract, Praxion Process) — versioned payload, unconditional on every run. These delegate their skip/refresh decision entirely to `refresh_claude_blocks.py`'s own absent/current/stale/modified classification (see **Action** below). There is no separate heading-check predicate for them anywhere in this skill.
- **Three conditional/templated blocks** (Hackathon Mode, Project Essentials, Obsidian Integration) — either mode-conditional or placeholder-filled per project, so a stable hash comparison is impossible. Each is guarded by its own independent heading-grep, and each is written by exactly one phase:
  - `## Hackathon Mode` — written by §Phase 5b; predicate: `grep -q '^## Hackathon Mode$' CLAUDE.md`.
  - `## Working in this project` (Project Essentials) — written by this phase; predicate: `grep -q '^## Working in this project$' CLAUDE.md`.
  - `## Obsidian Integration` — written by §Phase 8d; predicate: `grep -q '^## Obsidian Integration$' CLAUDE.md`. This phase reads (never writes) that same predicate purely to decide whether to mention the block as already present in its own summary line — it is not a second write path.

**Action.**

`CLAUDE.md` is guaranteed to exist — §Phase 0.5 bootstrapped it before Phase 1 (via `/init`, an inline codebase-aware generation, or a minimal stub). In the rare event it is still absent (e.g. §Phase 0.5 ran in a degraded, gate-less mode and its inline fallback did not fire), create it via §Phase 0.5's inline fallback now rather than skipping.
   - Refresh the four core blocks by delegating to the plugin-shipped script — plugin path resolved as `${PLUGIN_INSTALL_PATH}` per §Phase 4's resolution pattern:
     ```bash
     python3 "${PLUGIN_INSTALL_PATH}/scripts/refresh_claude_blocks.py" --apply --repo-root .
     ```
     Per-block classification drives the action: `absent` → appends the current canonical block; `stale` → silently replaces the live body with the current canonical body (self-heals — mirrors §Phase 4's stale-symlink precedent); `modified` → leaves the file untouched and prints a one-line pointer to `/refresh-claude-blocks` for the interactive disposition loop; `current` → no-op. If the plugin install path was not detected at pre-flight (skip-phase-4 flag set), skip this sub-step and emit: `Skipping canonical block refresh — install the plugin and re-run /onboard-project, or use /refresh-claude-blocks once installed.`
   - The §Project Essentials Block verbatim, appended at the end of the file with one blank line separating from preceding content (guarded by the `## Working in this project` predicate above)

3. **Fill the §Project Essentials Block placeholders** (skip this step whenever the predicate above skipped the Project Essentials append — the block is already present and presumably already filled).
   - Replace `<typecheck command>` / `<test command>` / `<lint command>` / `<build command>` per [shared-procedures.md § Stack command resolution](shared-procedures.md#-stack-command-resolution) (includes the Rust branch).
   - Replace `<list 3–5 of this project's most common task intents>` with a ≤5-bullet list of what an agent is most often asked to do here, derived from the codebase shape and the README.

## §Phase 7 — Companion CLIs (advisory)

**Predicate.** None — purely informational, idempotent by nature.

**Action.** For each of `chub`, `scc`, `uv`, run `command -v <name>`. For each MISSING tool that is RELEVANT given the stack detected in §Pre-flight, print one-line install guidance. Do NOT run the install — print the command and let the user execute it.

| Tool | Relevant when | Why useful | Install (print, do not run) |
|------|---------------|------------|----------------------------|
| `chub` | Always | Curated docs for 600+ external libraries; used by the `external-api-docs` skill to avoid hallucinated SDK signatures | `npm install -g @aisuite/chub` |
| `scc` | Any stack | Fast SLOC counter used by `/project-metrics`; without it, metrics fall back to a stdlib counter that misses language detail | `brew install scc` (macOS) or `go install github.com/boyter/scc/v3@latest` |
| `uv` | Python detected | Fast Python package manager; required for `pytest -q` in Praxion's metrics flow | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `cargo-nextest` | Rust detected | Process-per-test runner recommended by the `testing-strategy` Rust leaf and the `rust-development` skill for large local suites and CI; plain `cargo test` remains fine for a small crate | `cargo install cargo-nextest --locked` |

Do not recommend tools the user already has, and do not recommend `uv` if no Python signal was detected in §Pre-flight, or `cargo-nextest` if no Rust signal was detected. **No Rust package-manager row exists here** — Cargo ships bundled with the toolchain (installed via `rustup`, pinned by `rust-toolchain.toml` when Phase 8e installs one), so there is no separate package-manager binary to recommend the way `uv` fills that role for Python.

**Agentic transactions (opt-in):** If your managed project will implement agentic payments or trading, the `agentic-transactions-architect` agent and the `agentic-transactions` skill are available as Praxion-internal pipeline capabilities — activate them by including `transaction`, `payment`, or `trading` context in your task description.


## §Phase 9 — Verification + handoff

**Predicate.** None — terminal phase.

**Action.**

1. **Print the change summary** — group by phase, list every file modified and every `git config` setting written. Use this format:
   ```
   Onboarding complete. Changes:
     Phase 0.5: CLAUDE.md bootstrapped (/init | inline-generated | minimal stub) — or omitted when CLAUDE.md was already present
     Phase 1: .gitignore (appended 10 lines, AI-assistants block)
     Phase 2: .ai-state/ skeleton (list the entries actually created this run)
     Phase 3: .gitattributes (appended 1 line), git config (1 merge driver registered)
     Phase 4: .git/hooks/pre-commit (new), .git/hooks/{post-merge,post-commit,post-checkout} (symlinks)
     Phase 5: .claude/settings.json (PRAXION_DISABLE_OBSERVABILITY env var; permissions.allow baseline) — or 'skipped' per sub-step
     Phase 6: CLAUDE.md (appended Agent Pipeline + Compaction + Behavioral Contract + Praxion Process + Working-in-this-project blocks)
     Phase 7: companion CLIs — chub missing (install: ...), scc missing (install: ...)
     Phase 8: architecture baseline produced — .ai-state/DESIGN.md + docs/architecture.md (+ N ADR draft(s))
     Phase 8b: AaC tier — fence seed, fitness/, Block D, architecture.yml, docs/diagrams/ (or skipped per sub-step)
     Phase 8c: ML scaffold — .ai-state/experiments/, .gitignore block, gpu_budget.yaml, program.md (or skipped per sub-step)
     Phase 8d: Obsidian integration — .gitignore Obsidian block, obsidian@obsidian-skills plugin verified, CLAUDE.md ## Obsidian Integration block, .claude/settings.json deny entries (or skipped per sub-step)
     Phase 8e: code-quality baseline — .editorconfig, per-stack linter/formatter/type-check config (Rust: rustfmt.toml, Cargo.toml [lints]/[workspace.lints] policy, rust-toolchain.toml — when Cargo.toml detected), .pre-commit-config.yaml, CONTRIBUTING.md, .github/dependabot.yml, ci-autofix caller/policy, labels manifest + reconciler caller (or skipped per sub-step)
     Phase 9: .ai-state/.praxion-onboard.json (onboard manifest — version <version>, artifact inventory)
   ```
   Also report any cross-version cleanup performed in Phase 3 (e.g. `removed retired merge driver 'memory-json' + its .gitattributes line`) and any stale-pin upgrades in Phase 3/4 (e.g. `re-pointed finalize hooks from praxion/0.6.0 to praxion/0.8.0`).
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

3. **Write the onboard manifest** `.ai-state/.praxion-onboard.json` (overwrite each run — it is the single record of what version onboarded this project and what artifacts it installed, consumed by §Phase 3 / §Phase 4 drift detection and cross-version cleanup on the next run). Record only **shareable** fields — never the machine-specific `installPath` (it is resolved live from `installed_plugins.json` at every hook/driver run, so it must not be committed):
   ```json
   {
     "plugin": "praxion@bit-agora",
     "onboarded_with_version": "<version captured at pre-flight>",
     "onboarded_at": "<ISO 8601 UTC timestamp>",
     "scope": "user | project",
     "mode": "<'full' or 'hackathon' — see below>",
     "artifacts": {
       "hooks": ["pre-commit", "post-merge", "post-commit", "post-checkout"],
       "merge_drivers": ["observations-jsonl"],
       "gitattributes": [".ai-state/observations.jsonl merge=observations-jsonl"],
       "ci_autofix": {
         "caller": ".github/workflows/ci-autofix.yml",
         "policy": ".github/autofix-policy.yml",
         "hub_sha": "<resolved 40-hex hub commit SHA>"
       },
       "praxion_feedback": ".ai-state/praxion_feedback/PENDING.md",
       "consult_ledgers": [".ai-state/CONSULT_LEDGER.md", ".ai-state/CONSULT_COSTS.md", ".ai-state/CONSULT_PRIORS.md"],
       "principles": ".ai-state/principles.yaml"
     }
   }
   ```
   List only artifacts actually installed this run (omit hooks if Phase 4 was skipped; omit `ci_autofix` if Phase 8e was skipped or its caller/policy predicate already hit; omit `praxion_feedback`, `principles`, and any `consult_ledgers` entry whose Phase 2 predicate already hit — those files pre-existed). If the plugin version could not be captured at pre-flight (skip-phase-4 flag), write `"onboarded_with_version": "unknown"` and emit a one-line note.

   **The `mode` field is additive-only** (REQ-06 / AC-7 / AC-8): write `"full"` for a fully-managed onboard/re-onboard/promote run, `"hackathon"` for a hackathon-mode onboard. A stamp written before this field existed has no `mode` key at all — every reader (this phase's own re-run, §Pre-flight's prior-onboarding detection, `references/detection.md`'s state predicates) must treat an **absent `mode` key as `"full"`** for back-compat, never as `"hackathon"` — a project onboarded before this field existed must not silently read as hackathon-managed.

   Add `.ai-state/.praxion-onboard.json` to the staged set.

4. **Stage modified files**: run `git add` with the explicit list of files this command touched (built up through phases 1–6, plus `.ai-state/.praxion-onboard.json`). Do NOT run `git add -A`. Do NOT commit. The user reviews staging and decides.
