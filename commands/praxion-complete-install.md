---
description: Reconfigure or recover a marketplace-installed Praxion setup — symlink rules and CLI scripts, and offer to remove leftover state from earlier Praxion versions. Optional (auto-completes on first session).
allowed-tools: [Bash]
disable-model-invocation: true
---

Most users will not need this command — Praxion auto-completes the setup on your first Claude Code session. Use this command only if auto-install was disabled (`PRAXION_DISABLE_AUTO_COMPLETE=1`), to reconfigure personal settings, or to recover from a corrupted install state.

<!-- LEGACY-CHUB-CLEANUP: when the shim is deleted, also drop this sentence and steps 3 below's "legacy remnants" clause. -->
The plugin body is already present; this command adds or refreshes the system-level surfaces the plugin mechanism does not cover natively: rules (auto-loaded by Claude Code globally) and CLI scripts on `$PATH`. It also offers to remove leftover state from earlier Praxion versions, if any is found.

## Procedure

1. **Resolve the plugin root.** Use the `CLAUDE_PLUGIN_ROOT` environment variable if set; otherwise locate the cached plugin directory at `~/.claude/plugins/cache/bit-agora/praxion/*/`.

2. **Invoke the installer's complete-install mode:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/bit-agora/praxion/*/ 2>/dev/null | head -1)}/install.sh" code --complete-install
   ```

   If neither resolution succeeds (plugin not installed), report: *"Praxion plugin not found. Run `claude plugin install praxion@bit-agora` first."*

3. **Relay consent, in whichever form the installer gives it.** <!-- LEGACY-CHUB-CLEANUP --> When `install.sh` runs on an interactive terminal, it prompts for consent separately on each system-level change (rules, scripts, and — only if present — legacy remnants from earlier Praxion versions); relay those prompts to the user and do not suppress, skip, or auto-answer them. When run through this command's Bash tool invocation, stdin is not a TTY, so the installer takes its non-interactive branch instead: it changes nothing and prints the exact manual commands for any remnants it found. In that case, relay those printed commands to the user verbatim rather than claiming a prompt appeared.

4. **Summarize the outcome** once the installer exits: which surfaces were linked, which were skipped, and whether a new Claude Code session is needed to pick up the rules (always yes if rules were linked).

## Idempotence

The underlying operations are idempotent — running this command a second time is safe. Existing symlinks are replaced in place.

## Reversal

To undo what this command did, run `/praxion-complete-uninstall` (or equivalently `install.sh code --complete-uninstall`). The plugin body itself is preserved; remove it separately with `claude plugin uninstall praxion`.

## When to use this vs. `./install.sh code`

- **`/praxion-complete-install`** — you installed via the marketplace (`claude plugin install praxion@bit-agora`) and don't have a local Praxion checkout. This command finds the plugin in its cache and finishes the setup from there.
- **`./install.sh code`** — you cloned Praxion. Run the full installer directly; `--complete-install` is unnecessary because the regular install flow already covers these surfaces.
