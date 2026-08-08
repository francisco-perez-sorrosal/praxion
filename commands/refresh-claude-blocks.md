---
description: Refresh this project's onboarded CLAUDE.md canonical blocks against the currently installed praxion plugin, with an interactive disposition loop for locally customized blocks
argument-hint: "[--check | --apply]"
allowed-tools: [Bash(scripts/refresh_claude_blocks.py:*), Bash(jq:*), Bash(git:*), Read, AskUserQuestion]
disable-model-invocation: true
---

# Refresh canonical CLAUDE.md blocks

Reconcile the four refresh-eligible canonical blocks this project's `CLAUDE.md`
carries (`## Agent Pipeline`, `## Compaction Guidance`, `## Behavioral
Contract`, `## Praxion Process`) against the version shipped by the
**currently installed** praxion plugin. Each block is classified `current` /
`stale` / `absent` / `modified` by hashing its live body against a
plugin-shipped history manifest — no in-file marker, no `.git` history lookup
against Praxion's own repo required.

- `absent` and `stale` blocks are safe to change automatically — `absent` gets
  the canonical block appended, `stale` gets replaced in place. No confirmation
  needed; these carry no local customization by definition.
- `modified` blocks are never touched automatically — a bespoke local
  paragraph must never be silently clobbered. This command shows the diff and
  asks you to decide, per block.

Run this after upgrading the praxion plugin, or any time `/onboard-project`
reports a block needs attention.

## Arguments

- (none) or `--check` — classify and report only. Mutates nothing.
- `--apply` — auto-apply `absent`/`stale`, then run the interactive
  disposition loop for any `modified` block.

## Process

### 1. Resolve the plugin path

Get the live praxion install path from `installed_plugins.json` — the script must
be invoked from the installed plugin, never a repo-relative Praxion path,
since this command runs against arbitrary user projects:

```bash
PLUGIN_ROOT="$(jq -r '.plugins["praxion@bit-agora"][0].installPath' "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null)"
```

If that is null/empty, tell the user the praxion plugin is not installed and
stop — there is nothing to refresh *from*. (Install via
`claude plugin install praxion@bit-agora` or `./install.sh code` from a Praxion
checkout.)

### 2. Classify

Run the script in `--json` mode against the current project:

```bash
python3 "$PLUGIN_ROOT/scripts/refresh_claude_blocks.py" --json
```

Parse the resulting `{slug: classification}` dict. If every eligible block is
already `current`, report that and stop — nothing to do.

### 3. Auto-apply safe actions

If `--apply` was passed (or no argument — `--apply` is the default action for
this command; `--check` reports only), run:

```bash
python3 "$PLUGIN_ROOT/scripts/refresh_claude_blocks.py" --apply
```

This appends each `absent` block's current canonical body and replaces each
`stale` block's body in place. It never mutates a `modified` block — for each
one, it prints a unified diff (canonical vs. live) plus a pointer to this
command. Report to the user which blocks were appended and which were
replaced.

If invoked with `--check`, skip this step and go straight to reporting the
classification (see Step 5) — `--check` never mutates.

### 4. Disposition loop for modified blocks

For each block classified `modified` (surfaced by Step 3's `--apply` output,
or by Step 2's classification when running `--check`), read the block's live
span from the target `CLAUDE.md` (heading line through the next `## ` heading
or end of file) and its current canonical body from
`$PLUGIN_ROOT/claude/canonical-blocks/<slug>.md`. Show the diff already
printed by `--apply`, then ask via `AskUserQuestion`:

- **Replace with canonical** — replace the block's live span in `CLAUDE.md`
  with the current canonical body (use `Edit`; this is the only step in this
  command that touches file content, and it happens only on explicit
  confirmation).
- **Keep local** — leave the block as-is; this is a permanent decision, not
  revisited on the next run unless the local content changes.
- **Skip** — leave the block as-is for now; revisit next time this command
  runs.

Never apply "Replace with canonical" without this explicit per-block
confirmation — this is the customization-protection guarantee the underlying
script enforces structurally and this command must not bypass.

### 5. Report the outcome

Summarize: how many blocks were `current` already, how many were auto-applied
(`absent`/`stale`, broken down), and for each `modified` block what the user
chose. If any `CLAUDE.md` changes were made, remind the user to review and
commit — this command never commits for you.

## Notes

- **Idempotent.** Re-running after a full disposition pass reports every
  eligible block `current` (or `modified` for blocks where "Keep local" was
  chosen — those stay `modified` by design; that is not drift, it's an
  honored customization).
- **Refuses on a plugin source repo.** The underlying script mirrors the
  self-onboard guard already applied by `/onboard-project` and
  `/new-project` — it refuses to run against a Claude Code plugin source
  repo unless `PRAXION_ALLOW_SELF_ONBOARD=1` is set.
- **Scope is fixed.** Only the four refresh-eligible blocks above are ever
  classified or touched. The template-filled `## Working in this project`
  section and conditional blocks like `## Obsidian Integration` are out of
  scope by design and untouched by this command.
- This is the interactive counterpart to `/onboard-project` Phase 6, which
  runs the same script in `--apply` mode non-interactively (auto-applying
  `absent`/`stale`, skipping `modified` blocks with a pointer back to this
  command).
