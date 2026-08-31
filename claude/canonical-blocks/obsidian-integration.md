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
