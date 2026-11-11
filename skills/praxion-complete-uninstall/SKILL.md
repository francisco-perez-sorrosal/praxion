---
name: praxion-complete-uninstall
description: Reverse /praxion-complete-install — check its state, then hand you the exact command to run in your own terminal to remove rule/script symlinks (and leftover state from earlier Praxion versions, if any). Plugin body is preserved.
allowed-tools: [Bash]
disable-model-invocation: true
---

<!-- LEGACY-CHUB-CLEANUP: when the shim is deleted, also drop this sentence and step 3 below's "legacy remnants" clause. -->
Check the system-level symlinks that `/praxion-complete-install` created, then hand you the exact `install.sh` command to remove them — including any leftover state from earlier Praxion versions — for you to run in your own terminal. The plugin body stays installed — run `claude plugin uninstall praxion` separately if you want to remove it too.

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
  echo "Praxion plugin not found — nothing to uninstall"
fi
```

   If it prints "Praxion plugin not found" (plugin not installed), stop there: there is nothing to uninstall.

2. **Summarize what the check reported:** which rule and script symlinks point at the plugin cache and would be removed, plus any leftover legacy remnants it warns about. `--check` is read-only — it never prompts and never writes.

3. **Hand the user the exact command to run in their own terminal:** <!-- LEGACY-CHUB-CLEANUP -->

   ```text
   "<resolved-plugin-root>/install.sh" code --complete-uninstall
   ```

   Substitute `<resolved-plugin-root>` with the path resolved in step 1. Each removal (rules, scripts, and — only if present — legacy remnants from earlier Praxion versions) is consent-gated behind its own prompt, and those prompts need an interactive terminal to answer. This skill's own Bash tool invocation has no TTY, so running `--complete-uninstall` from here would abort at the first prompt (stdin EOF), possibly after partial setup — never run it yourself; only run `--check`.

## Safety

Only symlinks that **point at the plugin cache** (`${CLAUDE_PLUGIN_ROOT}/...`) are removed. Rules or scripts from other sources in `~/.claude/rules/` or `~/.local/bin/` are left alone. The operation is safe to run even if the user has hand-installed other rule or script files.

## Idempotence

Safe to re-run. After the first run of the printed command, subsequent runs find nothing to remove and exit cleanly.
