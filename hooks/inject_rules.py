#!/usr/bin/env python3
"""SessionStart hook: apply the per-project Praxion rules blacklist.

Reads `rules/_manifest.yaml` to determine each rule's delivery type
(`install: hook-deliver` vs `install: symlink`), reads the optional
per-project `.claude/praxion-rules.yaml` blacklist, and applies the
disable list through two complementary mechanisms (their helpers live in
`_rule_blacklist`):

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

A disabled rule's resident (a hook-deliver rule whose frontmatter names the
disabled rule's path in `resident_of:`) is suppressed with it, so an opt-out
keeps its reach when a rule is split into a path-scoped body and an
always-loaded one-line projection.

Core rules (core: true in manifest) are never suppressible by either
mechanism — any attempt produces a stderr warning and is ignored.

Behavior contract:
- Fail-open: any internal error exits 0 with no output; never block SessionStart.
- Slots: `--slot N` (1-based) plans the whole delivery (`_rule_delivery`) and
  prints its Nth self-labelled part, nothing past the plan; only slot 1 writes
  files and logs, so parallel slots never race. No argument: the whole plan as one
  JSON under one header.
- Impaired floor: the kill switch, a missing PyYAML, a missing, unreadable or
  malformed manifest, and any failure applying it (a damaged row) still deliver
  `MANAGED_CORE_UNITS` to a managed scope and no unit to an unmanaged one; an
  unavailable manifest is reported to the session in either scope.
- No double delivery: a managed-only unit still linked at user scope (`<config>/rules/
  <id>.md`, a link left from before a relink) loads natively, so the hook skips it.
- Backward-compatible: no project config → all rules loaded (no exclusions).
- Schema-guarded: version > 1 in project config → log warning and load all.
- Idempotent: settings.json is rewritten only when its `claudeMdExcludes`
  would actually change; otherwise no write happens.
- Auto-template: when the start directory belongs to a managed project (see
  `_project_scope.scope_of`) whose root has neither `.claude/praxion-rules.yaml`
  nor `.claude/praxion-rules.yaml.example`, the shipped template is copied to the
  root's `.claude/praxion-rules.yaml.example` so projects discover the mechanism
  without manual `cp`. Nothing is written in an unmanaged directory or into a
  subdirectory of a managed project. Idempotent.
- Blacklist reach: a user-written `.claude/praxion-rules.yaml` is read from the
  start directory, else from the managed root; a subdirectory's own list wins.
- Project scope: a hook-deliver rule whose manifest row says
  `project_scope: managed` is delivered only in a managed scope; any other
  value, or none, reads as `every`.

Visibility of misuse (turned silent no-ops into stderr warnings):
- `disable:` provided as a scalar (not a list) → warning, treated as empty.
- A pattern in `disable:` matching zero rule IDs → warning per pattern (typo guard).
- `version:` field with non-int value → warning, coerced to 1.
- `.claude/settings.json` malformed JSON → louder warning naming the
  consequence (reconciliation skipped, disable list not applied).
"""

from __future__ import annotations

import json
import os
import re
import sys
import sysconfig
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from _hook_utils import is_disabled
from _project_scope import Managed, ProjectScope, scope_of
from _rule_blacklist import (
    add_residents_of_disabled,
    apply_symlink_exclusions,
    blacklist_directory,
    blacklist_path,
    compute_disable_set,
    compute_symlink_exclusions,
    disable_patterns,
    ensure_template_present,
)
from _rule_delivery import (
    MANAGED_CORE_UNITS,
    AgentKind,
    Delivery,
    DeliveryPart,
    Event,
    plan_delivery,
)

# -- Constants -----------------------------------------------------------------

DISABLE_FLAG = "PRAXION_DISABLE_RULE_INJECTION"
SLOT_FLAG = "--slot"
# Slot 1 is the one process of a slotted run that writes files and logs the summary.
EFFECTS_SLOT = 1
# Claude Code's user configuration directory: this variable, else ~/.claude.
CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
REINSTALL_FIX = "Reinstall the Praxion plugin, then start a new session."

# `project_scope` manifest value delivered only inside a managed project.
_MANAGED_ONLY = "managed"

# Frontmatter delimiter pattern for stripping YAML blocks from rule files.
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


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


class ManifestUnavailableError(Exception):
    """The manifest cannot be read, so no hook-delivered rule reaches the session."""

    def __init__(self, reason: str, fix: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.fix = fix


def _load_manifest(plugin_root: Path) -> list[dict]:
    """Read and parse rules/_manifest.yaml into its list of rule dicts.

    Raises:
        ManifestUnavailableError: the manifest is missing, unparseable, or malformed.
    """
    manifest_path = plugin_root / "rules" / "_manifest.yaml"
    if not manifest_path.exists():
        raise ManifestUnavailableError(f"manifest not found at {manifest_path}", REINSTALL_FIX)
    if yaml is None:
        raise ManifestUnavailableError(
            f"the hook interpreter `{sys.executable}` cannot import PyYAML",
            _pyyaml_fix(sys.executable, externally_managed=_externally_managed()),
        )
    try:
        data = _load_yaml(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManifestUnavailableError(f"could not parse manifest: {exc}", REINSTALL_FIX) from exc
    if not isinstance(data, dict):
        raise ManifestUnavailableError("manifest is not a YAML mapping", REINSTALL_FIX)
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise ManifestUnavailableError("manifest 'rules' is not a list", REINSTALL_FIX)
    return rules


def _externally_managed() -> bool:
    """PEP 668: the interpreter's stdlib carries an EXTERNALLY-MANAGED marker."""
    return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists()


def _pyyaml_fix(executable: str, *, externally_managed: bool) -> str:
    """The remedy that works for this interpreter — pip refuses a PEP 668 one."""
    on_path = "put a python3 that has PyYAML (e.g. a virtualenv's bin/) first on PATH"
    if externally_managed:
        return f"`{executable}` is externally managed, so pip will refuse; {on_path}, then start a new session."
    return (
        f"Install it for that interpreter (`{executable} -m pip install pyyaml`) "
        f"or {on_path}, then start a new session."
    )


def _unavailable_notice(exc: ManifestUnavailableError, scope: ProjectScope) -> str:
    """Log the skip and word it for the session — stderr alone reaches neither the
    model nor the user, so the rules would vanish silently. An unmanaged scope gets
    it too: it is a diagnostic, not a unit, and its header is what the eval observer
    keys on; a managed scope is told the core procedures that still arrive."""
    print(f"[inject_rules] WARNING: {exc.reason}; skipping rule injection", file=sys.stderr)
    loaded = (
        "Only Praxion's managed core procedures were loaded this session; its other"
        " hook-delivered rules were NOT"
        if isinstance(scope, Managed)
        else "Praxion's hook-delivered rules were NOT loaded this session"
    )
    return (
        "## Praxion rule injection skipped\n\n"
        f"{loaded}: {exc.reason}. "
        f"{exc.fix} Tell the user if their work depends on those conventions."
    )


# -- Project blacklist loading -------------------------------------------------


def _load_project_config(directory: Path) -> dict | None:
    """Read .claude/praxion-rules.yaml from a directory.

    Returns parsed dict, or None if the file is missing (empty disable list).
    Raises ValueError on malformed YAML (caller handles fail-open).
    """
    config_path = blacklist_path(directory)
    if not config_path.exists():
        return None
    try:
        data = _load_yaml(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"malformed praxion-rules.yaml: {exc}") from exc
    return data if isinstance(data, dict) else {}


# -- Rule body reading ---------------------------------------------------------


def _read_rule_body(plugin_root: Path, rel_path: str) -> str:
    """Read a rule file and strip its frontmatter.

    Returns empty string on any I/O error.
    """
    if not rel_path:
        return ""
    rule_path = plugin_root / rel_path
    try:
        raw = rule_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"[inject_rules] WARNING: could not read rule file {rule_path}: {exc}",
            file=sys.stderr,
        )
        return ""
    return _strip_frontmatter(raw)


def _natively_installed(unit_ids: Collection[str]) -> frozenset[str]:
    """The units Claude Code still loads from a user-scope rule link, so a hook copy
    would arrive twice: a link left from before the unit moved to hook delivery."""
    if not unit_ids:
        return frozenset()
    try:
        config_dir = Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
    except (RuntimeError, KeyError):  # no HOME and no passwd entry: no user scope to link from
        return frozenset()
    return frozenset(
        unit_id for unit_id in unit_ids if _links_to_rule(config_dir / "rules", unit_id)
    )


def _links_to_rule(user_rules: Path, unit_id: str) -> bool:
    """Whether `<user rules>/<id>.md` is a live link into any checkout's `rules/<id>.md`
    (the installer links from whichever checkout ran it; a dangling link loads nothing)."""
    link = user_rules / f"{unit_id}.md"
    try:
        return (
            link.is_symlink()
            and link.is_file()
            and link.resolve().as_posix().endswith(f"/rules/{unit_id}.md")
        )
    except (OSError, RuntimeError):  # a link loop resolves to nothing
        return False


# -- additionalContext emitter -------------------------------------------------


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


def _drain_stdin() -> str:
    """Read and discard stdin so the hook framework never SIGPIPEs on its write end."""
    try:
        return sys.stdin.read()
    except OSError:
        return ""


def _resolve_plugin_root() -> Path:
    """Resolve the plugin root from CLAUDE_PLUGIN_ROOT, or two levels above this file."""
    plugin_root_str = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root_str:
        return Path(plugin_root_str)
    return Path(__file__).resolve().parent.parent


def _resolve_cwd(raw_payload: str) -> Path:
    """Parse the SessionStart JSON payload on stdin and resolve the working directory."""
    try:
        payload = json.loads(raw_payload) if raw_payload.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return Path(payload.get("cwd") or os.getcwd())


def _resolve_disable_patterns(config_dir: Path) -> list[str]:
    """Load the project's raw `disable:` patterns, failing open on any malformed input.

    Returns an empty list for a missing config or malformed YAML, and whatever
    `disable_patterns` keeps of a parsed one. Each fail-open path emits a stderr
    warning except the plain-missing-config case (backward compat).
    """
    try:
        project_cfg = _load_project_config(config_dir)
    except ValueError as exc:
        print(
            f"[inject_rules] WARNING: {exc}; injecting all rules (fail open)",
            file=sys.stderr,
        )
        return []
    return [] if project_cfg is None else disable_patterns(project_cfg)


def _hook_delivered_units(rules: list[dict], plugin_root: Path) -> tuple[dict[str, str], set[str]]:
    """The hook-deliver rows' bodies in manifest order, and the ids of the managed-only ones.

    Only the exact value `managed` restricts delivery; an unreadable or unknown
    value reads as `every`, so a damaged row never silently drops a rule.
    """
    rows = [r for r in rules if r.get("install") == "hook-deliver" and "id" in r]
    units = {r["id"]: _read_rule_body(plugin_root, r.get("path", "")) for r in rows}
    return units, {r["id"] for r in rows if r.get("project_scope") == _MANAGED_ONLY}


def _log_injection_summary(
    rules: list[dict], units: Mapping[str, str], delivery: Delivery, disable_set: set[str]
) -> None:
    """Emit the stderr observability summary line for this SessionStart run;
    `disable_set` (sorted) doubles as the claudeMdExcludes entry list."""
    core_count = sum(1 for r in rules if r.get("core") is True)
    suppressed = sorted(unit_id for unit_id in units if unit_id in disable_set)
    exclusion_str = ", ".join(sorted(disable_set)) if disable_set else "none"
    print(
        f"[inject_rules] Loaded {core_count} core rules;"
        f" injected {len(delivery.unit_ids())}/{len(units)} hook-deliver rules"
        f" (suppressed: {', '.join(suppressed) or 'none'});"
        f" claudeMdExcludes entries: {exclusion_str}",
        file=sys.stderr,
    )


# -- Delivery: one plan, printed whole or one slot at a time --------------------


def _floor_delivery(plugin_root: Path, scope: ProjectScope, notice: str | None) -> Delivery:
    """The impaired injection's delivery: the managed core units, read without the manifest."""
    units = {unit.unit_id: _read_rule_body(plugin_root, unit.path) for unit in MANAGED_CORE_UNITS}
    return Delivery(notice, units, _plan_session(units, set(units), scope, set()))


def _plan_session(
    units: Mapping[str, str], managed_only: set[str], scope: ProjectScope, disable_set: set[str]
) -> tuple[DeliveryPart, ...]:
    native = _natively_installed(managed_only)  # an `every` unit keeps its linked copy
    event, agent = Event.SESSION, AgentKind.INHERITING  # a session's agent kind is moot
    return plan_delivery(units, managed_only, scope, event, agent, disable_set, native)


def _manifest_delivery(
    rules: list[dict], plugin_root: Path, cwd: Path, scope: ProjectScope, *, effects: bool
) -> Delivery:
    """The delivery the manifest and the project blacklist decide; `effects` lets it write."""
    # A managed root gets the blacklist template, so projects discover the mechanism.
    if effects:
        ensure_template_present(scope, plugin_root)

    # Read project blacklist; missing = empty disable list (backward compat).
    # Malformed YAML is fail-open; schema version > 1 is fail-open.
    all_rule_ids = [r["id"] for r in rules if "id" in r]
    patterns = _resolve_disable_patterns(blacklist_directory(cwd, scope))
    disable_set = compute_disable_set(patterns, rules, all_rule_ids)
    disable_set = add_residents_of_disabled(disable_set, rules, plugin_root)

    # claudeMdExcludes covers the linked rules in the disable set, the plan the
    # hook-deliver ones: together the YAML reaches every install type.
    if effects:
        apply_symlink_exclusions(cwd, compute_symlink_exclusions(disable_set, rules))

    units, managed_only = _hook_delivered_units(rules, plugin_root)
    delivery = Delivery(None, units, _plan_session(units, managed_only, scope, disable_set))
    if effects:
        _log_injection_summary(rules, units, delivery, disable_set)
    return delivery


def _session_delivery(raw: str, *, effects: bool) -> Delivery:
    plugin_root = _resolve_plugin_root()
    cwd = _resolve_cwd(raw)
    scope = scope_of(str(cwd))

    # Kill switch: opt-out env var disables injection, all but the managed core units.
    if is_disabled(DISABLE_FLAG):
        print(
            "[inject_rules] Rule injection disabled by PRAXION_DISABLE_RULE_INJECTION;"
            " only the managed core units are delivered",
            file=sys.stderr,
        )
        return _floor_delivery(plugin_root, scope, None)

    # An unavailable manifest is non-fatal but never silent; one that cannot be applied (a
    # damaged row) is the same impaired case, so it never costs a managed scope its core units.
    try:
        rules = _load_manifest(plugin_root)
        return _manifest_delivery(rules, plugin_root, cwd, scope, effects=effects)
    except ManifestUnavailableError as exc:
        return _floor_delivery(plugin_root, scope, _unavailable_notice(exc, scope))
    except Exception as exc:
        failure = ManifestUnavailableError(f"could not apply manifest: {exc!r}", REINSTALL_FIX)
        return _floor_delivery(plugin_root, scope, _unavailable_notice(failure, scope))


def _requested_slot(argv: list[str]) -> int | None:
    """The slot after `--slot`, or None for no arguments (the whole plan); ValueError otherwise."""
    if not argv:
        return None
    if len(argv) == 2 and argv[0] == SLOT_FLAG and argv[1].isdigit() and int(argv[1]) > 0:
        return int(argv[1])
    raise ValueError(f"expected no arguments or `{SLOT_FLAG} N` (N >= 1), got {argv!r}")


def main(argv: list[str] | None = None) -> None:
    raw = _drain_stdin()
    try:
        slot = _requested_slot(sys.argv[1:] if argv is None else argv)
    except ValueError as exc:
        print(f"[inject_rules] WARNING: {exc}; nothing injected", file=sys.stderr)
        return

    delivery = _session_delivery(raw, effects=slot in (None, EFFECTS_SLOT))
    if slot is None:
        text = delivery.whole_text()
    else:
        texts = delivery.slot_texts()
        text = texts[slot - 1] if slot <= len(texts) else ""
    if text:
        _emit_additional_context(text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fault tolerance: never block SessionStart on any unhandled exception.
        print(f"[inject_rules] ERROR: unhandled exception: {exc}", file=sys.stderr)
        sys.exit(0)
