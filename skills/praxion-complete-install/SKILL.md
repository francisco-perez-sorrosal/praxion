---
name: praxion-complete-install
description: Reconfigure or recover a marketplace-installed Praxion setup — check its state, then hand you the exact command to run in your own terminal to symlink rules and CLI scripts and bring ~/.claude/CLAUDE.md to the installed version (it may ask for your personal values; leftover state from earlier Praxion versions is removed, if any). Optional (auto-completes on first session).
allowed-tools: [Bash]
disable-model-invocation: true
---

Most users will not need this skill — Praxion auto-completes the setup on your first Claude Code session. Use this skill only if auto-install was disabled (`PRAXION_DISABLE_AUTO_COMPLETE=1`), to reconfigure personal settings, or to recover from a corrupted install state.

<!-- LEGACY-CHUB-CLEANUP: when the shim is deleted, also drop this sentence and step 3 below's "legacy remnants" clause. -->
The plugin body is already present; this skill checks the system-level surfaces the plugin mechanism does not cover natively — rules (auto-loaded by Claude Code globally), CLI scripts on `$PATH`, and the global instructions file `~/.claude/CLAUDE.md` — then hands you the exact `install.sh` command that adds or refreshes them, including removing leftover state from earlier Praxion versions if any is found, for you to run in your own terminal.

The command brings `~/.claude/CLAUDE.md` to the installed version as well as linking the rules and scripts. When it cannot read your earlier values back from the current file, it asks in your terminal for your personal values (username, email, GitHub URL), offering the git-derived defaults. A `CLAUDE.md` that is your own regular file, or a link outside the plugin cache that your own `install.sh code` set up, is left untouched, and the closing report says so.

## Procedure

1. **Resolve the plugin root and run the read-only health check.** One block does both: it takes the root Claude Code substituted for the plugin-root token, else the install path the plugin registry records for Praxion, and runs the check from there. Text that was not substituted is only ever data to it, and it never lists the plugin cache.

```bash
root=$(cat <<'PRAXION_ROOT'
${CLAUDE_PLUGIN_ROOT}
PRAXION_ROOT
)
[ -d "$root" ] || root=$(python3 - <<'PY'
import json, os

registry = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
try:
    with open(registry, encoding="utf-8") as f:
        plugins = json.load(f)["plugins"]
    entries = [e for key, listed in plugins.items() if key.startswith("praxion@") for e in listed]
    entries.sort(key=lambda e: e.get("scope") != "user")
    print(next(e["installPath"] for e in entries
               if isinstance(e.get("installPath"), str) and os.path.isdir(e["installPath"])))
except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
    pass
PY
)
if [ -n "$root" ]; then
  echo "Praxion plugin root: $root"
  "$root/install.sh" code --check
else
  echo "Praxion plugin not found. Run: claude plugin install praxion@bit-agora"
fi
```

   If it prints "Praxion plugin not found" (plugin not installed), stop there: the person installs it first with the command it printed.

2. **Summarize what the check reported:** which rules and scripts are linked or missing, plus any leftover legacy remnants it warns about. `--check` is read-only — it never prompts and never writes.

3. **Hand the user the exact command to run in their own terminal:** <!-- LEGACY-CHUB-CLEANUP -->

   ```text
   "<resolved-plugin-root>/install.sh" code --complete-install
   ```

   Substitute `<resolved-plugin-root>` with the root the block printed. Each change this makes (rules, scripts, the instructions file, and — only if present — legacy remnants from earlier Praxion versions) is consent-gated behind its own prompt, and those prompts need an interactive terminal to answer. This skill's own Bash tool invocation has no TTY, so running `--complete-install` from here would abort at the first prompt (stdin EOF), possibly after partial setup — never run it yourself; only run `--check`. The command closes with a report naming what it set up, what it left alone and what it could not do.

## Idempotence

The underlying operations are idempotent — running the printed command a second time is safe. Existing symlinks are replaced in place.

## Reversal

To undo the rule and script links the printed command sets up, run `/praxion-complete-uninstall` (or equivalently `install.sh code --complete-uninstall`, in your own terminal). It leaves `~/.claude/CLAUDE.md` as it is. The plugin body itself is preserved; remove it separately with `claude plugin uninstall praxion`.

## When to use this vs. `./install.sh code`

- **`/praxion-complete-install`** — you installed via the marketplace (`claude plugin install praxion@bit-agora`) and don't have a local Praxion checkout. This skill finds the installed plugin and gives you the command to finish the setup from there.
- **`./install.sh code`** — you cloned Praxion. Run the full installer directly in your terminal; `--complete-install` is unnecessary because the regular install flow already covers these surfaces.
