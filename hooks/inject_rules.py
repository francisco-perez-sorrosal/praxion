#!/usr/bin/env python3
"""SessionStart hook: apply the per-project Praxion rules blacklist.

Reads `rules/_manifest.yaml` to determine each rule's delivery type
(`install: hook-deliver` vs `install: symlink`), reads the optional
per-project `.claude/praxion-rules.yaml` blacklist, and applies the
disable list through two complementary mechanisms:

1. `install: hook-deliver` rules — suppressed by filtering them out of
   the `additionalContext` payload returned to Claude Code at SessionStart.

2. `install: symlink` rules (path-scoped rules plus always-on rules
   delivered via global symlinks in `~/.claude/rules/`) — suppressed by
   reconciling glob patterns into `claudeMdExcludes` in the project's
   `.claude/settings.json`. Patterns use the portable shape
   `**/.claude/rules/<id>.md` so they match the user's absolute install
   path on any machine. Praxion-managed entries (identified by their
   `**/.claude/rules/` prefix) are recomputed every SessionStart;
   non-Praxion entries in `claudeMdExcludes` are preserved untouched.

Defense-in-depth: the `claudeMdExcludes` mechanism (#2) also covers
`install: hook-deliver` rules in the disable set, so a stale symlink left
in `~/.claude/rules/` by a prior install (e.g., when a rule's install
type flipped from `symlink` to `hook-deliver`) cannot bypass the
blacklist. The structural fix lives in the installer's
`sweep_stale_rule_symlinks` step; this is the runtime safety net.

Core rules (core: true in manifest) are never suppressible by either
mechanism — any attempt produces a stderr warning and is ignored.

Behavior contract:
- Fail-open: any internal error exits 0 with no output; never block SessionStart.
- Kill-switch: PRAXION_DISABLE_RULE_INJECTION=1 disables injection entirely.
- Backward-compatible: no project config → all rules loaded (no exclusions).
- Schema-guarded: version > 1 in project config → log warning and load all.
- Idempotent: settings.json is rewritten only when its `claudeMdExcludes`
  would actually change; otherwise no write happens.
- Auto-template: when Praxion is active in a project but neither
  `.claude/praxion-rules.yaml` nor `.claude/praxion-rules.yaml.example`
  exists, the shipped template is copied to `.claude/praxion-rules.yaml.example`
  so projects discover the mechanism without manual `cp`. Idempotent.

Visibility of misuse (turned silent no-ops into stderr warnings):
- `disable:` provided as a scalar (not a list) → warning, treated as empty.
- A pattern in `disable:` matching zero rule IDs → warning per pattern (typo guard).
- `version:` field with non-int value → warning, coerced to 1.
- `.claude/settings.json` malformed JSON → louder warning naming the
  consequence (reconciliation skipped, disable list not applied).
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
# When the memory MCP is disabled, the memory-protocol rule is inert (its body
# says "skip all memory operations"). Suppress its delivery structurally so
# opted-out projects do not pay its always-loaded token cost — the env var alone
# is sufficient, no per-project blacklist entry required.
MEMORY_MCP_DISABLE_FLAG = "PRAXION_DISABLE_MEMORY_MCP"
MEMORY_PROTOCOL_RULE_ID = "swe/memory-protocol"
SUPPORTED_SCHEMA_VERSION = 1

_INJECT_HEADER = "## Praxion Rules (auto-injected)\n\n"

# Frontmatter delimiter pattern for stripping YAML blocks from rule files.
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# Glob-pattern prefix Praxion uses for claudeMdExcludes entries it manages.
# Any entry starting with this prefix is recomputed on every SessionStart;
# any entry not starting with it is preserved as a user-managed exclusion.
_PRAXION_EXCLUSION_PREFIX = "**/.claude/rules/"


# -- Frontmatter stripping -----------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    """Remove leading YAML frontmatter block (--- ... ---) from a rule file."""
    stripped = _FRONTMATTER_RE.sub("", text, count=1)
    return stripped.lstrip("\n")


# -- YAML loading (stdlib fallback) --------------------------------------------


def _load_yaml(text: str) -> Any:
    """Parse YAML text; raises on malformed input.

    PyYAML is a hard dependency of Praxion (declared in plugin requirements).
    If it is genuinely absent, this raises RuntimeError and the caller treats
    the failure as fail-open (skip injection, exit 0). No stdlib fallback —
    a partial YAML parser would mis-handle the manifest and silently corrupt
    the disable contract, which is worse than not running.
    """
    if yaml is not None:
        return yaml.safe_load(text)
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


def _resolve_disable_globs(
    patterns: list[str], all_rule_ids: list[str]
) -> tuple[set[str], list[str]]:
    """Expand glob patterns against all manifest rule IDs using fnmatch.

    Returns a tuple of (disabled_ids, unmatched_patterns).
    `unmatched_patterns` is the subset of `patterns` that matched zero rule IDs,
    preserved in input order. The caller logs a warning per unmatched pattern so
    typos like `disable: [my/tpyo-rule]` are visible rather than silent no-ops.
    """
    disabled: set[str] = set()
    unmatched: list[str] = []
    for pattern in patterns:
        matched_any = False
        for rule_id in all_rule_ids:
            if fnmatch.fnmatch(rule_id, pattern):
                disabled.add(rule_id)
                matched_any = True
        if not matched_any:
            unmatched.append(pattern)
    return disabled, unmatched


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


# -- Symlink-rule exclusions via claudeMdExcludes -----------------------------


def _compute_symlink_exclusions(disable_set: set[str], rules: list[dict]) -> list[str]:
    """Compute portable claudeMdExcludes glob patterns for disabled rules.

    For each non-core rule_id in disable_set, produce a glob pattern of the
    form `**/.claude/rules/<id>.md` that matches the rule's installed symlink
    path on any user's machine — irrespective of home-directory layout.

    Both `install: symlink` and `install: hook-deliver` rules are covered:

    - For `install: symlink` rules, the exclusion is the primary suppression
      mechanism (Claude Code loads them as user-scope memory files via the
      symlink tree).
    - For `install: hook-deliver` rules, the additionalContext filter is the
      primary mechanism; the exclusion here is **defense-in-depth** against
      stale symlinks left by prior installs (when a rule's install type
      flipped from `symlink` to `hook-deliver` and the old symlink was never
      pruned). The `sweep_stale_rule_symlinks` step in the installer is the
      structural fix; this exclusion is the runtime safety net.

    Core rules are not included — they are non-disableable by design and are
    filtered out of `disable_set` upstream (`_filter_core_rules`).

    Returns a sorted list (deterministic order for idempotent settings writes).
    """
    rule_by_id = {r["id"]: r for r in rules if "id" in r}
    patterns: list[str] = []
    for rule_id in disable_set:
        rule = rule_by_id.get(rule_id)
        if rule is None:
            continue
        # Skip core rules defensively — they should already be filtered out
        # upstream, but this guard makes the function safe to call directly.
        if rule.get("core") is True:
            continue
        patterns.append(f"{_PRAXION_EXCLUSION_PREFIX}{rule_id}.md")
    return sorted(patterns)


def _apply_symlink_exclusions(cwd: Path, exclusions: list[str]) -> None:
    """Reconcile Praxion-managed claudeMdExcludes in <cwd>/.claude/settings.json.

    Reads the project's settings.json, replaces any existing entries whose
    pattern starts with `**/.claude/rules/` (Praxion-managed) with the new
    `exclusions` list, and preserves all other entries (user-managed). Skips
    the write when claudeMdExcludes would not actually change (idempotency).

    Fail-open: any exception is logged to stderr and swallowed — settings
    reconciliation is auxiliary and must never break SessionStart.
    """
    try:
        settings_path = cwd / ".claude" / "settings.json"
        existing: dict = {}
        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError) as exc:
                print(
                    f"[inject_rules] WARNING: could not parse {settings_path}:"
                    f" {exc}. Praxion-managed claudeMdExcludes reconciliation"
                    " skipped — the YAML disable list will NOT be applied until"
                    " the JSON is fixed. Validate with: python3 -c"
                    " 'import json,sys; json.load(open(sys.argv[1]))' .claude/settings.json",
                    file=sys.stderr,
                )
                return

        current = existing.get("claudeMdExcludes", [])
        if not isinstance(current, list):
            current = []

        preserved = [
            entry
            for entry in current
            if not (
                isinstance(entry, str) and entry.startswith(_PRAXION_EXCLUSION_PREFIX)
            )
        ]
        reconciled = preserved + exclusions

        if reconciled == current:
            return  # Idempotent: nothing to write.

        if reconciled:
            existing["claudeMdExcludes"] = reconciled
        else:
            # Empty after reconciliation — remove the key entirely so the file
            # stays minimal when no exclusions apply.
            existing.pop("claudeMdExcludes", None)

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        # sort_keys=False preserves the user's existing top-level key ordering;
        # claudeMdExcludes itself is already deterministically sorted in
        # _compute_symlink_exclusions, so the file content is still stable
        # across runs without alphabetizing unrelated user-managed keys.
        settings_path.write_text(
            json.dumps(existing, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"[inject_rules] Reconciled claudeMdExcludes in {settings_path}:"
            f" {len(exclusions)} Praxion-managed,"
            f" {len(preserved)} user-managed preserved",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"[inject_rules] claudeMdExcludes reconciliation skipped: {exc}",
            file=sys.stderr,
        )


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
            raw_version = project_cfg.get("version", 1)
            if not isinstance(raw_version, int):
                print(
                    f"[inject_rules] WARNING: 'version:' field has non-integer"
                    f" value {raw_version!r}; coercing to 1. Expected: 'version: 1'.",
                    file=sys.stderr,
                )
                version = 1
            else:
                version = raw_version
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
                if isinstance(raw_disable, list):
                    disable_patterns = list(raw_disable)
                elif "disable" in project_cfg:
                    # Present but malformed: scalar, dict, or null. Silent
                    # coercion would mask a typo (e.g., `disable: ml/*` instead
                    # of `disable: [ml/*]`), so surface it explicitly.
                    print(
                        f"[inject_rules] WARNING: 'disable:' must be a YAML list,"
                        f" got {type(raw_disable).__name__}: {raw_disable!r}."
                        " Treating as empty. Use the list form:"
                        " 'disable:\\n  - rule/id'",
                        file=sys.stderr,
                    )
                    disable_patterns = []
                else:
                    disable_patterns = []
    except ValueError as exc:
        print(
            f"[inject_rules] WARNING: {exc}; injecting all rules (fail open)",
            file=sys.stderr,
        )
        disable_patterns = []

    # Resolve glob patterns (e.g., ml/*) to concrete rule IDs. Warn for any
    # pattern that matched zero rules — catches typos like `disable: [my/tpyo]`.
    disable_set, unmatched_patterns = _resolve_disable_globs(
        disable_patterns, all_rule_ids
    )
    for pattern in unmatched_patterns:
        print(
            f"[inject_rules] WARNING: disable pattern {pattern!r} matched no"
            " rule in rules/_manifest.yaml — typo? Run `python3"
            " scripts/regenerate_rules_manifest.py` to see valid IDs.",
            file=sys.stderr,
        )

    # Memory MCP opt-out (env-driven, blacklist-independent): when the memory MCP
    # is disabled, memory-protocol is a no-op rule — suppress it so the project
    # does not pay its always-loaded cost. Non-core, so it survives the core
    # filter below and flows through the normal suppression path.
    if is_disabled(MEMORY_MCP_DISABLE_FLAG) and MEMORY_PROTOCOL_RULE_ID in all_rule_ids:
        disable_set.add(MEMORY_PROTOCOL_RULE_ID)

    # Remove core rules from disable set; warn for each attempted suppression.
    disable_set = _filter_core_rules(disable_set, rules)

    # Reconcile claudeMdExcludes in .claude/settings.json with the symlinked
    # rules in the disable set. Hook-deliver rules are handled below via the
    # additionalContext filter; the two mechanisms together give the YAML
    # uniform reach across all install types.
    symlink_exclusions = _compute_symlink_exclusions(disable_set, rules)
    _apply_symlink_exclusions(cwd, symlink_exclusions)

    # Build inject set: hook-deliver rules that are not suppressed.
    inject_rules = [
        r
        for r in rules
        if r.get("install") == "hook-deliver" and r.get("id") not in disable_set
    ]
    hook_deliver_rules = [r for r in rules if r.get("install") == "hook-deliver"]
    suppressed_hd_ids = [
        r["id"] for r in hook_deliver_rules if r.get("id") in disable_set
    ]
    # claudeMdExcludes now covers every non-core disabled rule regardless of
    # install type (defense-in-depth — see _compute_symlink_exclusions).
    exclusion_ids = sorted(disable_set)

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
    hd_suppressed_str = (
        ", ".join(sorted(suppressed_hd_ids)) if suppressed_hd_ids else "none"
    )
    exclusion_str = ", ".join(exclusion_ids) if exclusion_ids else "none"
    print(
        f"[inject_rules] Loaded {core_count} core rules;"
        f" injected {injected_count}/{total_hook_deliver} hook-deliver rules"
        f" (suppressed: {hd_suppressed_str});"
        f" claudeMdExcludes entries: {exclusion_str}",
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
