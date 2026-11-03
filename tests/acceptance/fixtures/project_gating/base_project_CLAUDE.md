## Agent Pipeline

This project follows Praxion's tier-driven agent pipeline (Direct → Lightweight → Standard → Full, plus exploratory Spike) under the **Understand, Plan, Verify** methodology. Ephemeral pipeline artifacts live in `.ai-work/<task-slug>/` (deleted after use); permanent decisions and design docs live in `.ai-state/` (committed to git).

When Praxion's assistant tooling is active, its agent coordination protocol rule and `software-planning` skill carry the full agent roster, delegation checklists, and pipeline-branch handling. Always include expected deliverables when delegating to an agent.

Human-readable process overview: [Praxion documentation](https://github.com/francisco-perez-sorrosal/praxion#readme).


## Behavioral Contract

Four non-negotiable behaviors for any agent (including Claude itself) writing, planning, or reviewing code:

- **Surface Assumptions** — state your interpretation upfront and surface each gap-filling assumption as you make it, unconditionally — a plausible default never *feels* like ambiguity. Pause before acting only when a surfaced assumption is load-bearing and hard to reverse, or could produce the wrong artifact.
- **Register Objection** — when a request violates scope, structure, or evidence: state the conflict with a reason before complying or declining. Silent agreement is a contract violation.
- **Stay Surgical** — touch only what the change requires; if scope grew, stop and re-scope instead of silently expanding.
- **Simplicity First** — prefer the smallest solution that meets the behavior; every added line, file, or dependency must earn its place.

Self-test: did I state my assumptions, flag conflicts with reasons, stay in scope, and pick the simplest path?


1. Run `git status` and `git diff --staged` (or `git diff` if nothing staged)
2. Analyze the changes to understand their purpose and scope
3. **Quality gate**: If any staged or changed files are source code (not docs or config), detect the project's formatters and linters from config files (`pyproject.toml`, `package.json`, etc.) and run them on the changed code files: format, then lint in fix mode, then type check if configured. If violations remain after auto-fix, stop and present them before proceeding. Re-stage any files modified by formatters.
4. **Single vs multiple commits**: If the diff clearly mixes distinct targets (e.g. `feat` + `fix`, `docs` + `refactor`, `test` + `chore`), treat as multiple logical tasks. Otherwise, proceed with one commit.
5. **When splitting**:
   - Group changes by logical task (by file and/or by diff hunks). Prefer grouping by file when files have a single clear purpose; use partial staging (`git add -p` or file subsets) when one file contains unrelated edits.
   - For each group in a sensible order (e.g. fix before feat, code before docs): stage only that group, craft a conventional commit message for that type, create the commit. Repeat until all changes are committed.
6. **When not splitting**: Stage files if needed (prefer specific files over `git add -A`), craft the commit message following our commit conventions, create the commit.


## Compaction Guidance

When this conversation compacts, always preserve: the active pipeline stage and task slug, the current WIP step number and status, acceptance criteria from the systems plan, and the list of files modified in the current step. The Praxion `PreCompact` hook snapshots in-flight pipeline documents to `.ai-work/PIPELINE_STATE.md` (one consolidated snapshot at the `.ai-work/` root, with a per-task-slug section for each active pipeline) — re-read that file after compaction to restore orientation.


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

Obsidian integration can be skipped with `onboard-project --without obsidian` (the legacy `--no-obsidian` flag is accepted for one release with a deprecation warning). To retrofit integration later, re-run `onboard-project --with obsidian` — Phase 8d is idempotent.

### Reference

See `docs/obsidian-integration.md` for installation, configuration, troubleshooting, and the full allowlist rationale.


## Praxion Process

Apply Praxion's tier-driven pipeline for non-trivial work. Use the tier selector from `rules/swe/swe-agent-coordination-protocol.md`: Direct (single-file fix/typo) or Lightweight (2–3 files) may skip the full pipeline; Standard or Full tier work requires researcher → systems-architect → implementation-planner → implementer + test-engineer → verifier.

**Rule-inheritance corollary.** When delegating to any subagent — Praxion-native or host-native (Explore, Plan, general-purpose) — carry the behavioral contract into every delegation prompt. Host-native subagents do not load CLAUDE.md; the orchestrator is the only delivery path.

**Orchestrator obligation.** Every delegation prompt must name the task slug, expected deliverables, and the behavioral contract (Surface Assumptions · Register Objection · Stay Surgical · Simplicity First).


## Working in this project

This `CLAUDE.md` is the **index**; `docs/` and the skills it points to are the **library** — read the index, follow the links the task needs. When I correct you, propose a durable rule for review (a `CLAUDE.md` or rule edit, or a skill note) so the correction outlasts this session.

### Verification

After every change, run these in order — fix at each step before moving on:

1. `<typecheck command>`
2. `<test command>`
3. `<lint command>`
4. `<build command>`

### Frequent operations

You'll most often be asked to:

- `<list 3–5 of this project's most common task intents>`


## Praxion Sidecar Placement

This project onboarded with `--placement sidecar`: Praxion's project intelligence lives
**outside** this repository, in a separate git-tracked sidecar repository at
`~/.praxion/sidecars/<sidecar-id>`. The state mount at `<project>/.praxion-state` is a real
`git worktree` of that sidecar; `.ai-state/`, this file, and `.claude/settings.local.json`
are symlinks into it, excluded via `.git/info/exclude` — **your commits in this repository
never include Praxion state**.

`docs/architecture.md`, when shared, cites ADRs by **id text** (e.g. `dec-NNN`), never by
an `.ai-state/` path — a path reference would dangle for anyone without sidecar access.

`.ai-state/` (a directory shadow) accepts a direct `Write`/`Edit`; `CLAUDE.local.md`, a shadowed
`CLAUDE.md`, and `.claude/settings.local.json` (file shadows) load through their links but refuse
a direct tool write — edit those three at their mount path instead (`.praxion-state/<name>`).

Run `praxion-sidecar doctor` to confirm the mount and shadow projection are intact. See
`docs/onboarding.md#placement` for the full placement model.


## Testing

Tests are selected from the change, never listed by hand: a resolver derives the tests a diff needs from the test layout, imports, path literals, and `tests/declared-deps.toml` — and widens to the full suite whenever it cannot account for a changed file.

- **Layout** — `<layout>`: `<source file>` is tested by `<test file>`.
- **Selected run** (after every change): `/test`, or `resolve_test_scope.py --changed-from <base branch> | sh -e` — covers every commit since `<base branch>` plus uncommitted and untracked edits.
- **Before committing** (working tree only): `resolve_test_scope.py | sh -e` — no arguments selects just the uncommitted and untracked changes.
- **Full run** (before handing work off; CI runs it on every push): `<full run>`.
- **Non-code dependencies** — when a test reads a file no code names (a fixture, a generated artifact), declare the pair in `tests/declared-deps.toml`; a change to that file then selects the test.
- **Outer loop is read-only** — the implementer runs `tests/acceptance/` and `tests/e2e/` but never edits them; a failing outer-loop test is fixed in production code or raised with its author.
