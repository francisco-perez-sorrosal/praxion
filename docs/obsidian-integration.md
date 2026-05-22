---
diataxis: reference
audience: operator
---

# Obsidian integration

## What is Obsidian integration

Praxion's Obsidian integration lets a project repository double as an Obsidian vault. Agents gain access to [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) — a vault-navigation and note-manipulation library authored by Steph Ango (Obsidian CEO, MIT licence) — and can use the official [Obsidian CLI](https://obsidian.md) (shipped with Obsidian 1.12+) for file CRUD, search, and link analysis.

Git and GitHub remain the version-control and collaboration layer. Obsidian integration is purely additive: it layers vault tooling on top, not instead of, git.

The integration activates in two ways:

- **Default-on gate** in `/onboard-project` (Gate 8d) and `/new-project` — the operator picks `Install Obsidian integration (recommended)` or `Skip`.
- **Retrofit existing projects** via re-running `/onboard-project` — it is idempotent and re-enters Phase 8d to apply any missing sub-steps.

## Installation (machine-level)

Run once per developer machine from a Praxion checkout:

```bash
./install.sh code
```

`install.sh code` calls `scripts/install-obsidian-deps.sh`, which:

1. Runs `claude plugin marketplace add kepano/obsidian-skills` to register the kepano marketplace source.
2. Runs `claude plugin install obsidian@obsidian-skills` to install the plugin at user scope. If already installed, this step is skipped automatically.
3. Performs a soft check for the `obsidian` CLI. If Obsidian Desktop 1.12+ is absent, the script warns but exits 0 — all other steps still complete.

**Prerequisite:** Obsidian Desktop 1.12+ must be installed separately. Praxion does not install Obsidian itself. Download from [obsidian.md](https://obsidian.md).

Verify machine-level state at any time:

```bash
./install.sh code --check
```

This prints whether `obsidian@obsidian-skills` is installed at user scope and whether the `obsidian` CLI is detected on PATH.

## Onboarding a project

Run inside an active Claude Code session in the project root:

```
/onboard-project
```

When the session reaches Gate 8d, pick `Install Obsidian integration (recommended)`. Sub-steps 8d.1–8d.6 run in order; each is independently idempotent.

| Sub-step | What it does |
|----------|-------------|
| 8d.1 | Appends the Obsidian per-user-state block to `.gitignore` (workspace files, cache, appearance, hotkeys) |
| 8d.2 | Verifies `claude` CLI is present on PATH |
| 8d.3 | Verifies `obsidian@obsidian-skills` marketplace plugin is installed at user scope |
| 8d.4 | Pins link-safety keys in `.obsidian/app.json` (`useMarkdownLinks: true`, `alwaysUpdateLinks: false`), merged non-destructively |
| 8d.5 | Appends `## Obsidian Integration` block to project `CLAUDE.md` |
| 8d.5b | Writes ten `permissions.deny` entries to `.claude/settings.json` |
| 8d.6 | Prints install summary |

**Idempotency.** Re-running `/onboard-project` on a project that already has Phase 8d applied produces zero `git diff` — each sub-step's predicate detects the prior install and skips silently.

**Retrofit existing projects.** If you picked `Skip` at Gate 8d, re-run `/onboard-project` — it is idempotent and will enter Phase 8d to apply any missing sub-steps.

## Opt-out

### Before onboarding

- `/onboard-project` — pick `Skip` at Gate 8d.
- `/new-project` (bash entry point) — pass `--no-obsidian` flag, or set `PRAXION_NEW_PROJECT_NO_OBSIDIAN=1`.

### After onboarding (manual removal)

No automated uninstall exists for per-project surfaces. Remove four artifacts:

- **`.gitignore`** — delete the `# Obsidian` block (six lines starting with `.obsidian/workspace.json`).
- **`.obsidian/app.json`** — remove the `useMarkdownLinks` and `alwaysUpdateLinks` keys (or delete the file if Obsidian created nothing else in it).
- **`CLAUDE.md`** — delete the `## Obsidian Integration` section.
- **`.claude/settings.json`** — remove the ten `Bash(obsidian ...)` entries from `permissions.deny`.

To remove the machine-level plugin as well:

```bash
./install.sh code --uninstall
```

This runs `claude plugin uninstall obsidian@obsidian-skills`. See `rules/swe/plugin-install-conventions.md` for the general plugin lifecycle convention.

## CLI agent allowlist

The `obsidian` CLI shipped with Obsidian 1.12+ exposes approximately 115 subcommands. Praxion restricts which subcommands agents may invoke by writing `permissions.deny` entries into `.claude/settings.json`. The harness rejects any blocked `Bash(obsidian ...)` call at the tool-permission layer — the block is mechanical, not prose-only.

**Prose-only policies fail silently.** An agent reading a "do not call X" instruction can still call X. A `permissions.deny` entry causes the harness to reject the invocation before it executes, regardless of what the agent decided. This is why the restriction lives in `settings.json` rather than only in `CLAUDE.md`.

### Allowed

File CRUD (`read`, `create`, `append`, `prepend`, `delete` without `--permanent`), search (`search`, `search:context`), link analysis (`backlinks`, `links`, `unresolved`, `orphans`, `deadends`), `outline`, `tags`, `tag`, `properties`, `base:query`, templates (`template:read`, `template:insert`), daily notes (`daily`, `daily:read`, `daily:append`), `unique`, and read-only diagnostics (`publish:list`, `publish:status`, `sync:status`, `sync:history`, `sync:read`).

### Denied (mechanically enforced)

| Subcommand | Reason |
|------------|--------|
| `obsidian eval` (any args) | Executes arbitrary JavaScript in the Obsidian renderer — remote code execution risk |
| `obsidian plugin:install` | Plugin lifecycle commands expose OS-level attack surface |
| `obsidian plugin:enable` | Same as above |
| `obsidian plugin:disable` | Same as above |
| `obsidian plugin:uninstall` | Same as above |
| `obsidian theme:set` | Theme code runs with full app privileges |
| `obsidian theme:install` | Same as above |
| `obsidian delete --permanent` | Bypasses Obsidian's trash; operation is unrecoverable |
| `obsidian move` | Link integrity (not security): moving a tracked file through Obsidian can rewrite link bodies across the repo and hides the move from git — use `git mv` |
| `obsidian rename` | Link integrity (not security): same as `move` — renames go through `git mv` so git tracks them and link conventions stay intact |

The plugin-lifecycle risk is not theoretical. The [PhantomPulse RAT](https://www.elastic.co/security-labs/phantom-in-the-vault) is a publicly documented instance of malware distributed as an Obsidian plugin — an illustration of why `plugin:install` and `plugin:enable` are blocked at the harness level rather than left to agent discretion.

The in-context rationale for agents (shorter form of this table) lives in the `## Obsidian Integration` block appended to your project's `CLAUDE.md` by Phase 8d.5.

## Querying ADRs with Bases

Praxion ships `.ai-state/decisions/decisions.base` — an Obsidian Bases file defining declarative views over the finalized ADRs in `.ai-state/decisions/`. It is the one net-new capability the integration adds beyond the existing dashboard and sentinel: a single query definition consumed by both humans (GUI tables) and agents (CLI JSON), where each of those tools otherwise hardcodes its own query logic.

**As a user (GUI).** Click `decisions.base` in Obsidian. It renders as interactive tables with a view dropdown — **All ADRs**, **Superseded**, **By category**, **Obsidian-tagged**. Sort by clicking a column header; click a row to open the ADR's markdown.

**As an agent (CLI).**

```bash
obsidian base:query vault=<vault> path=".ai-state/decisions/decisions.base" view="Superseded" format=json
```

Returns the matching rows as JSON. This replaces "grep every ADR file, parse each one's YAML, filter in code" with one declarative call — the `.base` is the spec, the CLI runs it. `base:query` is on the allowlist (read-only).

**Caveats.**

- `base:query` needs Obsidian running (it is a remote control for the GUI app) — it is **not** a headless/CI replacement for Praxion's Python scripts (sentinel, `finalize_adrs.py`). Use it in interactive sessions; keep the scripts canonical for CI.
- Obsidian rewrites `.base` files to its canonical form on GUI interaction (strips comments, adds `sort`/`columnSize` state). Edit views in the GUI or hand-edit the YAML — do not rely on comments persisting.

**Extending the pattern.** The same approach applies to any frontmatter-bearing `.ai-state/` artifact — a `.base` over `sentinel_reports/` for a health timeline, or one over a per-row tech-debt ledger for a priority kanban. Each is a `.base` file plus the views you want.

## Link safety

Because the repository doubles as a vault, Obsidian's default link behavior would let vault tooling corrupt project-artifact links — the standard Markdown `[text](path)` links and ADR id cross-references that Praxion's docs and cross-reference validators depend on. Two default behaviors are the risk:

1. **New-link format.** Obsidian's default (`useMarkdownLinks: false`) makes any link it authors a `[[wikilink]]` — a form Praxion does not use and its validators do not resolve.
2. **Auto link-rewrite.** With "Automatically update internal links" enabled, renaming or moving a file makes Obsidian rewrite link bodies across other files.

Phase 8d closes both, on two layers:

- **`.obsidian/app.json` (sub-step 8d.4)** pins `useMarkdownLinks: true` and `alwaysUpdateLinks: false`, merged non-destructively and committed so every clone inherits them. New links are Markdown-form; Obsidian never auto-rewrites links on rename.
- **`permissions.deny` (sub-step 8d.5b)** blocks `obsidian move` and `obsidian rename`, so file renames go through `git mv` — git tracks the rename and no link bodies are silently rewritten. This is a backstop independent of the `app.json` setting (a clone whose `app.json` was altered is still protected at the tool-permission layer).

Registering the repository as a vault is otherwise passive — Obsidian does not modify files merely by having the folder in its registry. These two layers constrain the *write path* (link authoring and rename) that is the only way vault tooling could change link bodies.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Obsidian not found" warning during `./install.sh code` | Plugin still installs; install [Obsidian Desktop 1.12+](https://obsidian.md), then `./install.sh code --relink` (runs `claude plugin update obsidian@obsidian-skills`) |
| Plugin not installed when `/onboard-project` reaches Gate 8d | `./install.sh code` first, then re-run `/onboard-project` |
| `.obsidian/workspace.json` in `git status` | `.gitignore` block missing — re-run `/onboard-project` (sub-step 8d.1 is idempotent) |
| Permission error on `obsidian eval`, plugin lifecycle, `theme:set`, or `delete --permanent` | Intentional — see [CLI agent allowlist](#cli-agent-allowlist). Use an allowed alternative or perform the action manually. |
| Plugin out of date | `./install.sh code --relink` (runs `claude plugin update obsidian@obsidian-skills`) |

## Revision

| Operation | Command |
|-----------|---------|
| Show plugin status + Obsidian presence | `claude plugin list` |
| Update plugin to latest | `./install.sh code --relink` (runs `claude plugin update obsidian@obsidian-skills`) |
| Uninstall plugin | `./install.sh code --uninstall` (runs `claude plugin uninstall obsidian@obsidian-skills`) |

Uninstall removes the marketplace plugin from user scope. It does not touch per-project surfaces (`.gitignore` block, `CLAUDE.md` block, `settings.json` entries) — remove those manually if needed (see [Opt-out](#opt-out)).
