---
description: Reconfigure or recover a marketplace-installed Praxion setup — symlink rules, CLI scripts, and optional context-hub MCP. Optional (auto-completes on first session).
allowed-tools: [Bash]
---

Most users will not need this command — Praxion auto-completes the setup on your first Claude Code session. Use this command only if auto-install was disabled (`PRAXION_DISABLE_AUTO_COMPLETE=1`), to reconfigure personal settings, or to recover from a corrupted install state.

The plugin body is already present; this command adds or refreshes the system-level surfaces the plugin mechanism does not cover natively: rules (auto-loaded by Claude Code globally), CLI scripts on `$PATH`, and optional context-hub MCP configuration.

## Procedure

1. **Resolve the plugin root.** Use the `CLAUDE_PLUGIN_ROOT` environment variable if set; otherwise locate the cached plugin directory at `~/.claude/plugins/cache/bit-agora/i-am/*/`.

2. **Invoke the installer's complete-install mode:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/bit-agora/i-am/*/ 2>/dev/null | head -1)}/install.sh" code --complete-install
   ```

   If neither resolution succeeds (plugin not installed), report: *"Praxion plugin not found. Run `claude plugin install i-am@bit-agora` first."*

3. **Relay the installer's interactive prompts.** The installer asks the user for consent separately on each system-level change (rules, scripts, context-hub MCP). Do not suppress, skip, or auto-answer these prompts — they are the user's signal that filesystem or `~/.claude.json` state is about to change.

4. **Summarize the outcome** once the installer exits: which surfaces were linked, which were skipped, and whether a new Claude Code session is needed to pick up the rules (always yes if rules were linked).

## Idempotence

The underlying operations are idempotent — running this command a second time is safe. Existing symlinks are replaced in place; `context-hub` MCP config is upserted, not duplicated.

## Reversal

To undo what this command did, run `/praxion-complete-uninstall` (or equivalently `install.sh code --complete-uninstall`). The plugin body itself is preserved; remove it separately with `claude plugin uninstall i-am`.

## When to use this vs. `./install.sh code`

- **`/praxion-complete-install`** — you installed via the marketplace (`claude plugin install i-am@bit-agora`) and don't have a local Praxion checkout. This command finds the plugin in its cache and finishes the setup from there.
- **`./install.sh code`** — you cloned Praxion. Run the full installer directly; `--complete-install` is unnecessary because the regular install flow already covers these surfaces.
