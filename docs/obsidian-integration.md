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
| 8d.4 | No-op in v1 (`.obsidian/` starter config deferred) |
| 8d.5 | Appends `## Obsidian Integration` block to project `CLAUDE.md` |
| 8d.5b | Writes eight `permissions.deny` entries to `.claude/settings.json` |
| 8d.6 | Prints install summary |

**Idempotency.** Re-running `/onboard-project` on a project that already has Phase 8d applied produces zero `git diff` — each sub-step's predicate detects the prior install and skips silently.

**Retrofit existing projects.** If you picked `Skip` at Gate 8d, re-run `/onboard-project` — it is idempotent and will enter Phase 8d to apply any missing sub-steps.

## Opt-out

### Before onboarding

- `/onboard-project` — pick `Skip` at Gate 8d.
- `/new-project` (bash entry point) — pass `--no-obsidian` flag, or set `PRAXION_NEW_PROJECT_NO_OBSIDIAN=1`.

### After onboarding (manual removal)

No automated uninstall exists for per-project surfaces. Remove three artifacts:

- **`.gitignore`** — delete the `# Obsidian` block (six lines starting with `.obsidian/workspace.json`).
- **`CLAUDE.md`** — delete the `## Obsidian Integration` section.
- **`.claude/settings.json`** — remove the eight `Bash(obsidian ...)` entries from `permissions.deny`.

To remove the machine-level plugin as well:

```bash
./install.sh code --uninstall
```

This runs `claude plugin uninstall obsidian@obsidian-skills`. See `rules/swe/plugin-install-conventions.md` for the general plugin lifecycle convention.

## CLI agent allowlist

The `obsidian` CLI shipped with Obsidian 1.12+ exposes approximately 115 subcommands. Praxion restricts which subcommands agents may invoke by writing `permissions.deny` entries into `.claude/settings.json`. The harness rejects any blocked `Bash(obsidian ...)` call at the tool-permission layer — the block is mechanical, not prose-only.

**Prose-only policies fail silently.** An agent reading a "do not call X" instruction can still call X. A `permissions.deny` entry causes the harness to reject the invocation before it executes, regardless of what the agent decided. This is why the restriction lives in `settings.json` rather than only in `CLAUDE.md`.

### Allowed

File CRUD (`read`, `create`, `append`, `prepend`, `move`, `rename`, `delete` without `--permanent`), search (`search`, `search:context`), link analysis (`backlinks`, `links`, `unresolved`, `orphans`, `deadends`), `outline`, `tags`, `tag`, `properties`, `base:query`, templates (`template:read`, `template:insert`), daily notes (`daily`, `daily:read`, `daily:append`), `unique`, and read-only diagnostics (`publish:list`, `publish:status`, `sync:status`, `sync:history`, `sync:read`).

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

The plugin-lifecycle risk is not theoretical. The [PhantomPulse RAT](https://www.elastic.co/security-labs/phantom-in-the-vault) is a publicly documented instance of malware distributed as an Obsidian plugin — an illustration of why `plugin:install` and `plugin:enable` are blocked at the harness level rather than left to agent discretion.

The in-context rationale for agents (shorter form of this table) lives in the `## Obsidian Integration` block appended to your project's `CLAUDE.md` by Phase 8d.5.

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
