#!/usr/bin/env python3
"""Find or remove the hooks earlier Praxion installers wrote into settings.json.

Before Praxion's hooks moved into the plugin's hooks.json, the installer
registered them in ~/.claude/settings.json, each as a command running a script
from the checkout's `.claude-plugin/hooks/` directory. That directory is the
ownership signature: users and other tools keep their own hooks in the same
`hooks` key, and those must never be reported or removed as Praxion's.

Usage: settings_hooks.py check|remove SETTINGS_JSON
  check   exit 0 if Praxion-owned hooks are present, 1 if not (or no file),
          2 if the file cannot be read as a JSON object.
  remove  delete only Praxion-owned hook entries, dropping matcher groups and
          events left empty, and the `hooks` key itself if nothing remains.
          Writes nothing when there is nothing to remove. Prints the count.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PRAXION_HOOKS_DIR_MARKER = "/.claude-plugin/hooks/"


def _is_praxion(hook: object) -> bool:
    command = hook.get("command", "") if isinstance(hook, dict) else ""
    return isinstance(command, str) and PRAXION_HOOKS_DIR_MARKER in command


def _groups(settings: dict) -> list[dict]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return [
        g
        for groups in hooks.values()
        if isinstance(groups, list)
        for g in groups
        if isinstance(g, dict)
    ]


def praxion_hook_commands(settings: dict) -> list[str]:
    """Commands of every Praxion-owned hook entry, in file order."""
    return [
        h["command"]
        for group in _groups(settings)
        for h in group.get("hooks", [])
        if _is_praxion(h)
    ]


def strip_praxion_hooks(settings: dict) -> tuple[dict, int]:
    """Return a copy without Praxion-owned hook entries, and how many were removed."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return dict(settings), 0

    removed = 0
    kept_events: dict = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            kept_events[event] = groups
            continue
        kept_groups = []
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                kept_groups.append(group)
                continue
            kept_entries = [h for h in entries if not _is_praxion(h)]
            removed += len(entries) - len(kept_entries)
            if kept_entries:
                kept_groups.append({**group, "hooks": kept_entries})
        if kept_groups:
            kept_events[event] = kept_groups

    stripped = {k: v for k, v in settings.items() if k != "hooks"}
    if kept_events:
        stripped["hooks"] = kept_events
    elif removed == 0:
        stripped["hooks"] = hooks
    return stripped, removed


def _read(path: Path) -> dict | None:
    """The settings object; {} for a missing file; None if unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("check", "remove"):
        print("usage: settings_hooks.py check|remove SETTINGS_JSON", file=sys.stderr)
        return 64
    mode, path = argv[0], Path(argv[1])
    settings = _read(path)
    if settings is None:
        print(f"cannot read {path} as a JSON object", file=sys.stderr)
        return 2
    if mode == "check":
        return 0 if praxion_hook_commands(settings) else 1

    stripped, removed = strip_praxion_hooks(settings)
    if removed:
        path.write_text(json.dumps(stripped, indent=2) + "\n", encoding="utf-8")
    print(f"removed {removed} Praxion hook entr{'y' if removed == 1 else 'ies'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
