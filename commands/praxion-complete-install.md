---
description: Reconfigure or recover a marketplace-installed Praxion setup — check its state, then hand you the exact command to run in your own terminal to symlink rules and CLI scripts (and remove leftover state from earlier Praxion versions, if any). Optional (auto-completes on first session).
allowed-tools: [Bash]
disable-model-invocation: true
---

Most users will not need this command — Praxion auto-completes the setup on your first Claude Code session. Use this command only if auto-install was disabled (`PRAXION_DISABLE_AUTO_COMPLETE=1`), to reconfigure personal settings, or to recover from a corrupted install state.

<!-- LEGACY-CHUB-CLEANUP: when the shim is deleted, also drop this sentence and step 3 below's "legacy remnants" clause. -->
The plugin body is already present; this command checks the system-level surfaces the plugin mechanism does not cover natively — rules (auto-loaded by Claude Code globally) and CLI scripts on `$PATH` — then hands you the exact `install.sh` command that adds or refreshes them, including removing leftover state from earlier Praxion versions if any is found, for you to run in your own terminal.

## Procedure

1. **Resolve the plugin root.** Use the `CLAUDE_PLUGIN_ROOT` environment variable if set; otherwise locate the cached plugin directory at `~/.claude/plugins/cache/bit-agora/praxion/*/`.

   If neither resolution succeeds (plugin not installed), report: *"Praxion plugin not found. Run `claude plugin install praxion@bit-agora` first."*

2. **Run the read-only health check:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/bit-agora/praxion/*/ 2>/dev/null | head -1)}/install.sh" code --check
   ```

   Summarize what it reports: which rules and scripts are linked or missing, plus any leftover legacy remnants it warns about. `--check` is read-only — it never prompts and never writes.

3. **Hand the user the exact command to run in their own terminal:** <!-- LEGACY-CHUB-CLEANUP -->

   ```text
   "<resolved-plugin-root>/install.sh" code --complete-install
   ```

   Substitute `<resolved-plugin-root>` with the path resolved in step 1. Each change this makes (rules, scripts, and — only if present — legacy remnants from earlier Praxion versions) is consent-gated behind its own prompt, and those prompts need an interactive terminal to answer. This command's own Bash tool invocation has no TTY, so running `--complete-install` from here would abort at the first prompt (stdin EOF), possibly after partial setup — never run it yourself; only run `--check`.

## Idempotence

The underlying operations are idempotent — running the printed command a second time is safe. Existing symlinks are replaced in place.

## Reversal

To undo what the printed command sets up, run `/praxion-complete-uninstall` (or equivalently `install.sh code --complete-uninstall`, in your own terminal). The plugin body itself is preserved; remove it separately with `claude plugin uninstall praxion`.

## When to use this vs. `./install.sh code`

- **`/praxion-complete-install`** — you installed via the marketplace (`claude plugin install praxion@bit-agora`) and don't have a local Praxion checkout. This command finds the plugin in its cache and gives you the command to finish the setup from there.
- **`./install.sh code`** — you cloned Praxion. Run the full installer directly in your terminal; `--complete-install` is unnecessary because the regular install flow already covers these surfaces.
