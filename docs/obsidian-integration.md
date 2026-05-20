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
- **Standalone retrofit** via `/onboard-project-obsidian` — run after the fact on any already-Praxion-onboarded project.

## Installation (machine-level)

Run once per developer machine from a Praxion checkout:

```bash
./install.sh code
```

`install.sh code` calls `scripts/install-obsidian-deps.sh`, which:

1. Clones [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) into `~/.local/share/praxion/kepano-skills` (override the destination via the `KEPANO_SKILLS_ROOT` environment variable).
2. Writes the resolved path to `~/.config/praxion/obsidian-skills.path` so the onboarding commands can locate it without requiring `KEPANO_SKILLS_ROOT` to be set in every shell.
3. Performs a soft check for the `obsidian` CLI. If Obsidian Desktop 1.12+ is absent, the script warns but exits 0 — all other install steps still complete.

**Prerequisite:** Obsidian Desktop 1.12+ must be installed separately. Praxion does not install Obsidian itself. Download from [obsidian.md](https://obsidian.md).

Verify machine-level state at any time:

```bash
./install.sh code --check
```

This prints the kepano-skills HEAD revision and whether the `obsidian` CLI is detected on PATH.

## Onboarding a project

Run inside an active Claude Code session in the project root:

```
/onboard-project
```

When the session reaches Gate 8d, pick `Install Obsidian integration (recommended)`. Sub-steps 8d.1–8d.6 run in order; each is independently idempotent.

| Sub-step | What it does |
|----------|-------------|
| 8d.1 | Appends the Obsidian per-user-state block to `.gitignore` (workspace files, cache, appearance, hotkeys) |
| 8d.2 | Resolves `KEPANO_SKILLS_ROOT` from the marker file or env var |
| 8d.3 | Creates `.claude/skills/obsidian/` → `$KEPANO_SKILLS_ROOT` symlink |
| 8d.4 | No-op in v1 (`.obsidian/` starter config deferred) |
| 8d.5 | Appends `## Obsidian Integration` block to project `CLAUDE.md` |
| 8d.5b | Writes eight `permissions.deny` entries to `.claude/settings.json` |
| 8d.6 | Prints install summary |

**Idempotency.** Re-running `/onboard-project` or `/onboard-project-obsidian` on a project that already has Phase 8d applied produces zero `git diff` — each sub-step's predicate detects the prior install and skips silently.

**Retrofit existing projects.** If you picked `Skip` at Gate 8d, run the standalone command at any time:

```
/onboard-project-obsidian
```

## Opt-out

### Before onboarding

- `/onboard-project` — pick `Skip` at Gate 8d.
- `/new-project` (bash entry point) — pass `--no-obsidian` flag, or set `PRAXION_NEW_PROJECT_NO_OBSIDIAN=1`.

### After onboarding (manual removal)

No automated uninstall exists for per-project surfaces. Remove four artifacts:

- **`.gitignore`** — delete the `# Obsidian` block (six lines starting with `.obsidian/workspace.json`).
- **`.claude/skills/obsidian/`** — `rm .claude/skills/obsidian` (symlink; use `rm`, not `rm -r`).
- **`CLAUDE.md`** — delete the `## Obsidian Integration` section.
- **`.claude/settings.json`** — remove the eight `Bash(obsidian ...)` entries from `permissions.deny`.

Or restore from a pre-onboarding commit: `git checkout <sha> -- .gitignore CLAUDE.md .claude/settings.json`, then `rm .claude/skills/obsidian`.

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
| "Obsidian not found" warning during `./install.sh code` | kepano-skills still clones; install [Obsidian Desktop 1.12+](https://obsidian.md), then `./install.sh code --relink` |
| kepano-skills missing when `/onboard-project` reaches Gate 8d | `./install.sh code` first, then `/onboard-project-obsidian` |
| `.obsidian/workspace.json` in `git status` | `.gitignore` block missing — run `/onboard-project-obsidian` (sub-step 8d.1 is idempotent) |
| Permission error on `obsidian eval`, plugin lifecycle, `theme:set`, or `delete --permanent` | Intentional — see [CLI agent allowlist](#cli-agent-allowlist). Use an allowed alternative or perform the action manually. |
| kepano-skills out of date | `./install.sh code --relink` (runs `git pull --ff-only` on the checkout) |

## Revision

| Operation | Command |
|-----------|---------|
| Show kepano revision + Obsidian presence | `./install.sh code --check` |
| Update kepano-skills to latest | `./install.sh code --relink` |
| Uninstall kepano-skills entirely | `./install.sh code --uninstall` |

Uninstall removes the kepano-skills checkout and the marker file. It does not touch per-project surfaces (`.gitignore` block, symlink, `CLAUDE.md` block, `settings.json` entries) — remove those manually if needed (see [Opt-out](#opt-out)).
