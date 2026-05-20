---
description: Retrofit Obsidian integration onto an already-Praxion-onboarded project (idempotent).
allowed-tools: [Bash(git:*), Bash(grep:*), Bash(find:*), Bash(test:*), Bash(ln:*), Bash(mkdir:*), Bash(command:*), Bash(jq:*), Bash(cat:*), Read, Write, Edit, Glob, Grep, AskUserQuestion, Task]
---

Retrofit Obsidian integration onto an **already-Praxion-onboarded** project. This is the standalone counterpart to `/onboard-project §Phase 8d` — run it when you skipped Obsidian integration during the original onboarding and now want to add it. All sub-steps are idempotent; already-installed surfaces are silently skipped.

## §Pre-flight

Run these checks before any writes. Abort on hard errors; warn and ask on soft signals.

**1. Confirm this is a Praxion-managed project.**

```bash
test -d .claude
```

If `.claude/` does not exist, print:

> `Error: .claude/ directory not found. This project has not been Praxion-onboarded yet.`
> `Run /onboard-project first, then re-run /onboard-project-obsidian.`

Abort.

**2. Detect plugin-source repo.**

```bash
test -f .claude-plugin/plugin.json
```

If the file exists, this is a plugin-source repository (e.g., Praxion itself). Plugin-source repos can legitimately want Obsidian integration applied manually — but `/onboard-project-obsidian` is a shipped command and runs in their context.

Use `AskUserQuestion` with `header: "Plugin-source repo detected"` and these two options:

| Option | Action |
|---|---|
| `Continue — apply Obsidian integration manually (I know what I'm doing)` | Proceed to §Phase 8d. |
| `Abort — I will apply the sub-steps by hand` | Print `Aborted.` and stop. |

If the user picks `Abort`, stop here.

**3. Confirm git repo (advisory).**

```bash
git rev-parse --is-inside-work-tree 2>/dev/null
```

If this fails, print a warning: `Note: not inside a git working tree — git add in §Exit will be skipped.` Continue anyway.

---

## §Phase 8d — Obsidian integration

> **Reviewer note:** This body mirrors `/onboard-project` §Phase 8d. If the two diverge, `/onboard-project` is authoritative.

**Why this phase exists.** Projects that use Obsidian as a vault inside the repository benefit from three surfaces: a `.gitignore` block that keeps workspace state files out of commits, a symlink from `.claude/skills/obsidian/` to the kepano-skills library so agents can navigate the vault, and a `permissions.deny` block in `.claude/settings.json` that mechanically blocks the dangerous `obsidian` CLI subcommands. Without these, an agent can inadvertently commit Obsidian workspace noise, miss vault-navigation tools, or be denied permissions silently without knowing why. Phase 8d installs all three idempotently.

**Action.** Run sub-steps 8d.1 through 8d.6 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8d.1 — `.gitignore` Obsidian block

**Predicate.** `grep -q '^# Obsidian$' .gitignore`. If present: skip with notice `8d.1: skipped (.gitignore Obsidian block already present)`.

**Action.** Append to `.gitignore` (create if absent):

```gitignore
# Obsidian
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache/
.obsidian/appearance.json
.obsidian/*.compat.json
.obsidian/hotkeys.json
```

Print: `8d.1: Obsidian .gitignore block appended`.

### Sub-step 8d.2 — Resolve `KEPANO_SKILLS_ROOT`

Resolve the kepano-skills path using this priority order:

1. **Marker file** (highest priority): `KEPANO_SKILLS_ROOT=$(cat "${HOME}/.config/praxion/obsidian-skills.path" 2>/dev/null)` — written by `./install.sh code` during kepano-skills installation.
2. **Env var fallback**: if the marker file is absent or empty, check `$KEPANO_SKILLS_ROOT` env var.
3. **Literal default**: if both are absent, use `${HOME}/.local/share/praxion/kepano-skills`.

After resolution, verify the path exists: `test -d "$KEPANO_SKILLS_ROOT"`. If it does not exist, warn:

> `kepano-skills not found at $KEPANO_SKILLS_ROOT. Run ./install.sh code first (from a Praxion checkout), then re-run this phase.`

Skip sub-steps 8d.3–8d.6. Print: `8d.2: kepano-skills resolution failed — skipping remaining sub-steps`.

If the path exists, continue. Print: `8d.2: kepano-skills resolved at ${KEPANO_SKILLS_ROOT}`.

### Sub-step 8d.3 — `.claude/skills/obsidian/` symlink

**Predicates (evaluated in order):**

1. `test -L .claude/skills/obsidian` — symlink already exists. Skip with notice `8d.3: skipped (.claude/skills/obsidian symlink already present)`.
2. `test -d .claude/skills/obsidian && ! test -L .claude/skills/obsidian` — a real directory exists (e.g., user copied the skills manually). Skip with notice `8d.3: skipped (.claude/skills/obsidian exists as a directory, not a symlink — manual install preserved)`.

**Action when neither predicate holds.** Create `.claude/skills/` directory if absent, then:

```bash
ln -s "${KEPANO_SKILLS_ROOT}" .claude/skills/obsidian
```

Print: `8d.3: .claude/skills/obsidian → ${KEPANO_SKILLS_ROOT} symlink created`.

### Sub-step 8d.4 — `.obsidian/` starter config (v1 no-op)

**Why this exists.** In v1, writing starter `.obsidian/` config (e.g., `app.json`, `community-plugins.json`) is deferred. Obsidian's plugin ecosystem is volatile and any config we write may conflict with the user's existing vault or community plugin set. The user's own Obsidian app manages `.obsidian/` after the vault opens.

**Action.** No-op. Print: `8d.4: .obsidian/ starter config — skipped in v1 (Obsidian manages this directory; no agent-written config needed)`.

### Sub-step 8d.5 — Append `## Obsidian Integration` block to `CLAUDE.md`

**Predicate.** `grep -q '^## Obsidian Integration$' CLAUDE.md`. If present: skip with notice `8d.5: skipped (## Obsidian Integration block already in CLAUDE.md)`.

**Action.** If `CLAUDE.md` does not exist, print: `No CLAUDE.md found — run /init first, then re-run /onboard-project-obsidian.` and skip. Otherwise, append the §Obsidian Integration Block verbatim from this command's body. Append at the end of the file with one blank line separating from preceding content.

Print: `8d.5: ## Obsidian Integration block appended to CLAUDE.md`.

### Sub-step 8d.5b — Write `permissions.deny` to `.claude/settings.json`

**Predicate.** Check whether the eval deny entry is already present:
```bash
jq '.permissions.deny // [] | map(select(startswith("Bash(obsidian eval"))) | length > 0' \
  .claude/settings.json 2>/dev/null
```
If `true`: skip with notice `8d.5b: skipped (permissions.deny obsidian eval entry already present)`.

**Action.** Read `.claude/settings.json` (create `{"permissions":{}}` if absent). Merge `permissions.deny` non-destructively:
- Preserve all existing top-level keys.
- Preserve the existing `permissions.allow` array.
- Add the eight deny entries below. If any entry already exists in the deny array, do not duplicate it.

Deny entries:

```json
"Bash(obsidian eval*)",
"Bash(obsidian plugin:install*)",
"Bash(obsidian plugin:enable*)",
"Bash(obsidian plugin:disable*)",
"Bash(obsidian plugin:uninstall*)",
"Bash(obsidian theme:set*)",
"Bash(obsidian theme:install*)",
"Bash(obsidian delete --permanent*)"
```

Use `jq` to perform the merge:

```bash
jq '.permissions.deny = ((.permissions.deny // []) +
  ["Bash(obsidian eval*)",
   "Bash(obsidian plugin:install*)",
   "Bash(obsidian plugin:enable*)",
   "Bash(obsidian plugin:disable*)",
   "Bash(obsidian plugin:uninstall*)",
   "Bash(obsidian theme:set*)",
   "Bash(obsidian theme:install*)",
   "Bash(obsidian delete --permanent*)"]
  | unique)' .claude/settings.json > .claude/settings.json.tmp && \
  mv .claude/settings.json.tmp .claude/settings.json
```

Print: `8d.5b: permissions.deny Obsidian CLI block written to .claude/settings.json`.

**Security note.** The denied subcommands are blocked at the tool-permission layer. `obsidian eval` executes arbitrary JavaScript in the Obsidian renderer (remote code execution risk); the plugin lifecycle commands expose OS-level attack surface; `obsidian delete --permanent` bypasses the trash and is unrecoverable. The `*` wildcard after each subcommand blocks all argument forms. Live end-to-end verification (actually calling a denied subcommand and observing the harness reject it) is deferred to first use in a Claude Code session with this `settings.json` applied.

### Sub-step 8d.6 — Print summary

Print:

```text
Obsidian integration install complete:
  kepano-skills: ${KEPANO_SKILLS_ROOT}
  .claude/skills/obsidian/: symlink created (or already present)
  CLAUDE.md: ## Obsidian Integration block appended (or already present)
  .claude/settings.json: permissions.deny Obsidian CLI block written (or already present)

CLI allowlist policy: obsidian file CRUD, search, link analysis, properties, tags, and
read-only diagnostics are ALLOWED. Dangerous subcommands (eval, plugin lifecycle, theme:set,
delete --permanent) are DENIED via .claude/settings.json permissions.deny.

See docs/obsidian-integration.md for installation, configuration, troubleshooting, and the
full allowlist rationale.
```

---

## §Obsidian Integration Block

<!-- canonical-source: claude/canonical-blocks/obsidian-integration.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Obsidian Integration

This project is configured for **Obsidian integration**: the vault lives inside the project repository, and the agent has access to kepano/obsidian-skills for vault navigation and note manipulation. Kepano skills are discovered automatically from `$KEPANO_SKILLS_ROOT` (default: `~/.local/share/praxion/kepano-skills`). If that path is absent, run `./install.sh code` in your Praxion checkout first.

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

Obsidian integration can be skipped by passing `--no-obsidian` to `/onboard-project` or `/new-project`. To retrofit integration later, run `/onboard-project-obsidian`.

### Reference

See `docs/obsidian-integration.md` for installation, configuration, troubleshooting, and the full allowlist rationale.
```

---

## §Exit

Stage modified files and print a completion summary. Do **not** commit.

**Stage the surfaces that Phase 8d may have modified:**

```bash
git add .gitignore CLAUDE.md .claude/settings.json .claude/skills/obsidian 2>/dev/null || true
```

**Print summary** (one line per sub-step, showing ran/skipped):

```text
/onboard-project-obsidian complete.

Sub-steps run:
  8d.1 — .gitignore Obsidian block: [appended | skipped (already present)]
  8d.2 — kepano-skills resolution: [resolved at <path> | failed — sub-steps 8d.3–8d.6 skipped]
  8d.3 — .claude/skills/obsidian symlink: [created | skipped (symlink exists) | skipped (directory exists)]
  8d.4 — .obsidian/ starter config: skipped in v1
  8d.5 — CLAUDE.md ## Obsidian Integration block: [appended | skipped (already present)]
  8d.5b — .claude/settings.json permissions.deny: [written | skipped (already present)]
  8d.6 — Summary printed above.

Docs: docs/obsidian-integration.md
```

Files staged (if git repo detected). Review with `git diff --staged` before committing.
