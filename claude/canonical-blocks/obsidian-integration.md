## Obsidian Integration

This project is configured for **Obsidian integration**: the vault lives inside the project repository, and the agent has access to kepano/obsidian-skills for vault navigation and note manipulation. Kepano skills are discovered automatically once `obsidian@obsidian-skills` is installed at user scope. If the plugin is absent from a session, run `./install.sh code` in your Praxion checkout first.

### CLI Allowlist

The `obsidian` CLI is available for file CRUD, search, link analysis, properties, tags, outline, structured queries (`base:query`), templates, and read-only sync/publish diagnostics.

**Allowed subcommands include:** `read`, `create`, `append`, `prepend`, `move`, `rename`, `delete` (without `--permanent`), `search`, `search:context`, `backlinks`, `links`, `unresolved`, `orphans`, `deadends`, `outline`, `tags`, `tag`, `properties`, `base:query`, `daily`, `daily:read`, `daily:append`, `template:read`, `template:insert`, `unique`, `publish:list`, `publish:status`, `sync:status`, `sync:history`, `sync:read`.

**Denied subcommands — blocked at the tool-permission layer:**

| Subcommand | Reason |
|---|---|
| `obsidian eval` (any args) | Executes arbitrary JavaScript in the renderer — remote code execution risk |
| `obsidian plugin:install`, `plugin:enable`, `plugin:disable`, `plugin:uninstall` | Plugin lifecycle commands expose OS-level attack surface |
| `obsidian theme:set`, `theme:install` | Theme code runs with full app privileges |
| `obsidian delete --permanent` | Bypasses Obsidian's trash; operation is unrecoverable |

**Why you may see permission errors:** The denied subcommands above are enforced mechanically via `.claude/settings.json` `permissions.deny` rules written by the onboarding step. If a `Bash(obsidian ...)` call is rejected by the harness, check this list — the subcommand is intentionally blocked, not broken. Use an allowed alternative or ask the user to perform the operation manually.

### Opt-out

Obsidian integration can be skipped by passing `--no-obsidian` to `/onboard-project` or `/new-project`. To retrofit integration later, re-run `/onboard-project` — it is idempotent on Phase 8d.

### Reference

See `docs/obsidian-integration.md` for installation, configuration, troubleshooting, and the full allowlist rationale.
