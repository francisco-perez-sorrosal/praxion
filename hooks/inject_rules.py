#!/usr/bin/env python3
"""SessionStart hook: inject hook-delivered rules into additionalContext.

Reads rules/_manifest.yaml to determine which rules use hook-deliver
installation, reads an optional per-project .claude/praxion-rules.yaml
blacklist, and injects the non-suppressed rule bodies as additionalContext.

Core rules (core: true in manifest) are never suppressible — any attempt
to disable them produces a stderr warning and is silently ignored.

Behavior contract:
- Fail-open: any internal error exits 0 with no output; never block SessionStart.
- Kill-switch: PRAXION_DISABLE_RULE_INJECTION=1 disables injection entirely.
- Backward-compatible: no project config → all hook-deliver rules injected (AC-01).
- Schema-guarded: version > 1 in project config → log warning and inject all.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from _hook_utils import is_disabled

# -- Constants -----------------------------------------------------------------

DISABLE_FLAG = "PRAXION_DISABLE_RULE_INJECTION"
SUPPORTED_SCHEMA_VERSION = 1

_INJECT_HEADER = "## Praxion Rules (auto-injected)\n\n"

# Frontmatter delimiter pattern for stripping YAML blocks from rule files.
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


# -- Frontmatter stripping -----------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    """Remove leading YAML frontmatter block (--- ... ---) from a rule file."""
    stripped = _FRONTMATTER_RE.sub("", text, count=1)
    return stripped.lstrip("\n")


# -- YAML loading (stdlib fallback) --------------------------------------------


def _load_yaml(text: str) -> Any:
    """Parse YAML text; raises on malformed input."""
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback: not used in production (PyYAML is always present in Praxion)
    raise RuntimeError("PyYAML not available")


# -- Manifest loading ----------------------------------------------------------


def _load_manifest(plugin_root: Path) -> list[dict] | None:
    """Read and parse rules/_manifest.yaml.

    Returns the list of rule dicts, or None if the manifest is missing/unreadable.
    """
    manifest_path = plugin_root / "rules" / "_manifest.yaml"
    if not manifest_path.exists():
        print(
            f"[inject_rules] WARNING: manifest not found at {manifest_path}; "
            "skipping rule injection",
            file=sys.stderr,
        )
        return None
    try:
        data = _load_yaml(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(
            f"[inject_rules] WARNING: could not parse manifest: {exc}; "
            "skipping rule injection",
            file=sys.stderr,
        )
        return None
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        print(
            "[inject_rules] WARNING: manifest 'rules' is not a list; "
            "skipping rule injection",
            file=sys.stderr,
        )
        return None
    return rules


# -- Project blacklist loading -------------------------------------------------


def _load_project_config(cwd: Path) -> dict | None:
    """Read .claude/praxion-rules.yaml from the project directory.

    Returns parsed dict, or None if the file is missing (empty disable list).
    Raises ValueError on malformed YAML (caller handles fail-open).
    """
    config_path = cwd / ".claude" / "praxion-rules.yaml"
    if not config_path.exists():
        return None
    try:
        data = _load_yaml(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"malformed praxion-rules.yaml: {exc}") from exc
    return data if isinstance(data, dict) else {}


# -- Glob resolution -----------------------------------------------------------


def _resolve_disable_globs(patterns: list[str], all_rule_ids: list[str]) -> set[str]:
    """Expand glob patterns against all manifest rule IDs using fnmatch."""
    disabled: set[str] = set()
    for pattern in patterns:
        for rule_id in all_rule_ids:
            if fnmatch.fnmatch(rule_id, pattern):
                disabled.add(rule_id)
    return disabled


# -- Core protection -----------------------------------------------------------


def _filter_core_rules(disable_set: set[str], rules: list[dict]) -> set[str]:
    """Remove core rules from the disable set, emitting a warning for each.

    Returns the filtered disable set (core rules removed).
    """
    core_ids = {r["id"] for r in rules if r.get("core") is True}
    attempted_core = disable_set & core_ids
    for rule_id in sorted(attempted_core):
        print(
            f"[inject_rules] WARNING: cannot disable core rule"
            f" '{rule_id}' — kept loaded",
            file=sys.stderr,
        )
    return disable_set - core_ids


# -- Rule body reading ---------------------------------------------------------


def _read_rule_body(plugin_root: Path, rule: dict) -> str:
    """Read a rule file and strip its frontmatter.

    Returns empty string on any I/O error.
    """
    rel_path = rule.get("path", "")
    if not rel_path:
        return ""
    rule_path = plugin_root / rel_path
    try:
        raw = rule_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"[inject_rules] WARNING: could not read rule file {rule_path}: {exc}",
            file=sys.stderr,
        )
        return ""
    return _strip_frontmatter(raw)


# -- additionalContext emitter -------------------------------------------------


def _ensure_template_present(cwd: Path, plugin_root: Path) -> None:
    """Copy the shipped blacklist template into the project's .claude/ if absent.

    Idempotent. Skips when EITHER `.claude/praxion-rules.yaml.example` OR
    `.claude/praxion-rules.yaml` already exists. Fail-safe: any exception
    is logged and swallowed (template placement is auxiliary; never breaks
    SessionStart).
    """
    try:
        claude_dir = cwd / ".claude"
        example_path = claude_dir / "praxion-rules.yaml.example"
        live_path = claude_dir / "praxion-rules.yaml"
        if example_path.exists() or live_path.exists():
            return
        template_src = plugin_root / "claude" / "config" / "praxion-rules.yaml.example"
        if not template_src.is_file():
            return
        claude_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_src, example_path)
        print(
            f"[inject_rules] Created blacklist template at {example_path}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"[inject_rules] Template placement skipped: {exc}",
            file=sys.stderr,
        )


def _emit_additional_context(context: str) -> None:
    """Emit additionalContext JSON for the SessionStart hook contract."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


# -- Main logic ----------------------------------------------------------------


def main() -> None:
    # Drain stdin — the hook framework can SIGPIPE if stdin is left unread.
    try:
        raw = sys.stdin.read()
    except OSError:
        raw = ""

    # Kill switch: opt-out env var disables injection entirely.
    if is_disabled(DISABLE_FLAG):
        print(
            "[inject_rules] Rule injection disabled by PRAXION_DISABLE_RULE_INJECTION",
            file=sys.stderr,
        )
        return

    # Resolve plugin root and working directory.
    plugin_root_str = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root_str:
        plugin_root = Path(plugin_root_str)
    else:
        # Fallback: derive from hook file location (two levels up from hooks/).
        plugin_root = Path(__file__).resolve().parent.parent

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())

    # Locate and parse manifest; missing manifest is non-fatal.
    rules = _load_manifest(plugin_root)
    if rules is None:
        return  # warning already emitted; exit 0 (non-fatal)

    # Praxion is active in this project — ensure the user-facing template
    # exists in .claude/ so projects discover the blacklist mechanism
    # without manual cp or running /onboard-project. Idempotent.
    _ensure_template_present(cwd, plugin_root)

    all_rule_ids = [r["id"] for r in rules if "id" in r]

    # Read project blacklist; missing = empty disable list (backward compat).
    # Malformed YAML is fail-open; schema version > 1 is fail-open.
    disable_patterns: list[str] = []
    try:
        project_cfg = _load_project_config(cwd)
        if project_cfg is not None:
            version = project_cfg.get("version", 1)
            if not isinstance(version, int):
                version = 1
            if version > SUPPORTED_SCHEMA_VERSION:
                print(
                    f"[inject_rules] Schema version {version} is not supported by "
                    "this version of Praxion; falling back to no suppression",
                    file=sys.stderr,
                )
                # Fail open: inject all (no suppression)
                disable_patterns = []
            else:
                raw_disable = project_cfg.get("disable", [])
                disable_patterns = (
                    list(raw_disable) if isinstance(raw_disable, list) else []
                )
    except ValueError as exc:
        print(
            f"[inject_rules] WARNING: {exc}; injecting all rules (fail open)",
            file=sys.stderr,
        )
        disable_patterns = []

    # Resolve glob patterns (e.g., ml/*) to concrete rule IDs.
    disable_set = _resolve_disable_globs(disable_patterns, all_rule_ids)

    # Remove core rules from disable set; warn for each attempted suppression.
    disable_set = _filter_core_rules(disable_set, rules)

    # Build inject set: hook-deliver rules that are not suppressed.
    inject_rules = [
        r
        for r in rules
        if r.get("install") == "hook-deliver" and r.get("id") not in disable_set
    ]
    hook_deliver_rules = [r for r in rules if r.get("install") == "hook-deliver"]
    suppressed_ids = [r["id"] for r in hook_deliver_rules if r.get("id") in disable_set]

    core_count = sum(1 for r in rules if r.get("core") is True)

    # Concatenate rule bodies in manifest order under a single H2 header.
    bodies: list[str] = []
    for rule in inject_rules:
        body = _read_rule_body(plugin_root, rule)
        if body:
            bodies.append(body)

    # Emit observability summary to stderr.
    injected_count = len(inject_rules)
    total_hook_deliver = len(hook_deliver_rules)
    suppressed_str = ", ".join(sorted(suppressed_ids)) if suppressed_ids else "none"
    print(
        f"[inject_rules] Loaded {core_count} core rules; "
        f"injected {injected_count}/{total_hook_deliver} blacklistable rules "
        f"(suppressed: {suppressed_str})",
        file=sys.stderr,
    )

    if not bodies:
        return

    context = _INJECT_HEADER + "\n\n".join(bodies)
    _emit_additional_context(context)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fault tolerance: never block SessionStart on any unhandled exception.
        print(f"[inject_rules] ERROR: unhandled exception: {exc}", file=sys.stderr)
        sys.exit(0)
