#!/usr/bin/env python3
"""SessionStart and SubagentStart hook: apply the per-project Praxion rules blacklist.

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
- Spawns: a `SubagentStart` payload plans for the spawn instead. A recipient
  (a plugin role whose definition was read and keeps the instruction files is a
  split recipient, every other loader of them a whole recipient) in a managed
  scope receives the managed core units, impaired floor included, and never the
  session's other units. A whole recipient receives them whole. A split recipient
  receives each as its stored split (`claude/kernels/spawn_split.json`, without the
  text only the main session acts on) when the split's digests agree with the unit's
  body (its bytes as written, as the generator reads them), the bytes of
  `rules/_audience.yaml` and the stored text, else whole: one unit at a time, and a
  missing, unreadable or malformed artifact or audience manifest gives every unit
  whole, as does any failure taking the split. Only a split recipient in a managed
  scope reads either file. `Explore`, `Plan` and a spawn
  whose definition sets `omitClaudeMd` (this plugin's `agents/<role>.md` for
  `praxion:<role>`, else the project's `.claude/agents/<name>.md`, the start
  directory's before the managed root's, then the user's) receive nothing, and a
  definition that cannot be read, or that spells the flag other than the literal
  `true`, counts as a whole recipient. A spawn writes no file, logs no summary and gets
  no notice: its session did all three.

Visibility of misuse (turned silent no-ops into stderr warnings):
- `disable:` provided as a scalar (not a list) → warning, treated as empty.
- A pattern in `disable:` matching zero rule IDs → warning per pattern (typo guard).
- `version:` field with non-int value → warning, coerced to 1.
- `.claude/settings.json` malformed JSON → louder warning naming the
  consequence (reconciliation skipped, disable list not applied).
- A managed split recipient with no usable spawn split → warning; a unit whose stored
  split disagrees with its sources → warning naming the unit (each arrives whole).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import sysconfig
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
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
    AUDIENCE_MANIFEST_PATH,
    FRONTMATTER_RE,
    MANAGED_CORE_UNITS,
    PLUGIN_NAMESPACE,
    SPAWN_SPLIT_PATH,
    AgentKind,
    Delivery,
    DeliveryPart,
    Event,
    SpawnSplit,
    distrusted_units,
    parse_agent_kind,
    parse_spawn_split,
    plan_delivery,
    rule_body,
    spawn_units,
)

# -- Constants -----------------------------------------------------------------

DISABLE_FLAG = "PRAXION_DISABLE_RULE_INJECTION"
SLOT_FLAG = "--slot"
# Slot 1 is the one process of a slotted run that writes files and logs the summary.
EFFECTS_SLOT = 1
# Claude Code's user configuration directory: this variable, else ~/.claude.
CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
REINSTALL_FIX = "Reinstall the Praxion plugin, then start a new session."
# The harness's name for each event, as the payload carries it and the output must echo it.
EVENT_NAMES = {Event.SESSION: "SessionStart", Event.SUBAGENT: "SubagentStart"}
# The only text that sets the flag, as the commit gate reads it (`kernel_ledger_checks.OMIT_SET`):
# one reading of one fact, and any other spelling reads as inheriting, the safe direction.
_OMIT_SET = "true"
_OMIT_FLAG = re.compile(r"^omitClaudeMd:[ \t]*([^\s#]*)", re.MULTILINE)
# An agent name is a file name in an `agents/` directory, never a path out of it.
_AGENT_NAME = re.compile(r"\w[\w.-]*")

# `project_scope` manifest value delivered only inside a managed project.
_MANAGED_ONLY = "managed"


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

    The bytes are decoded as written, with no newline translation: the generator digests the
    same text (`scripts/kernel_spawn_split.py`), so a stored split's digest can match.
    Returns empty string on any I/O error.
    """
    if not rel_path:
        return ""
    rule_path = plugin_root / rel_path
    try:
        raw = rule_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"[inject_rules] WARNING: could not read rule file {rule_path}: {exc}",
            file=sys.stderr,
        )
        return ""
    return rule_body(raw)


def _natively_installed(unit_ids: Collection[str]) -> frozenset[str]:
    """The units Claude Code still loads from a user-scope rule link, so a hook copy
    would arrive twice: a link left from before the unit moved to hook delivery."""
    config_dir = _user_config_dir() if unit_ids else None
    if config_dir is None:
        return frozenset()
    return frozenset(
        unit_id for unit_id in unit_ids if _links_to_rule(config_dir / "rules", unit_id)
    )


def _user_config_dir() -> Path | None:
    """Claude Code's user configuration directory; None with no HOME and no passwd entry."""
    try:
        return Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
    except (RuntimeError, KeyError):
        return None


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


# -- Spawns: whether a spawn inherits the instruction files ---------------------


def _agent_kind(agent_type: object, plugin_root: Path, cwd: Path, scope: ProjectScope) -> AgentKind:
    """The spawn's kind; a definition that is absent or cannot be read counts as a whole
    recipient. Only a `praxion:<role>` type has a plugin definition, and a flag reading of
    None means that definition was not read (absent, unreadable or without frontmatter)."""
    name = agent_type if isinstance(agent_type, str) else None
    candidates = _definition_candidates(name, plugin_root, cwd, scope) if name else ()
    omits = _omits_claude_md(candidates)
    plugin_definition_read = (
        omits is not None and name is not None and name.startswith(f"{PLUGIN_NAMESPACE}:")
    )
    return parse_agent_kind(name, omits, plugin_definition_read)


def _definition_candidates(
    agent_type: str, plugin_root: Path, cwd: Path, scope: ProjectScope
) -> tuple[Path, ...]:
    """Where the spawn's definition may be, first match winning: this plugin's
    `agents/<role>.md` for `praxion:<role>`; for a bare name the project's
    `.claude/agents/<name>.md` (the start directory's, then the managed root's), then the
    user's; none for another plugin's agent, a host-native one, or a name that is no file name."""
    namespace, separator, name = agent_type.rpartition(":")
    if not _AGENT_NAME.fullmatch(name):
        return ()
    if separator:
        return (plugin_root / "agents" / f"{name}.md",) if namespace == PLUGIN_NAMESPACE else ()
    roots = [cwd, *([scope.root] if isinstance(scope, Managed) and scope.root != cwd else [])]
    user_dir = _user_config_dir()
    homes = [*(root / ".claude" for root in roots), *([user_dir] if user_dir else [])]
    return tuple(home / "agents" / f"{name}.md" for home in homes)


def _omits_claude_md(candidates: tuple[Path, ...]) -> bool | None:
    """Whether the first definition present sets `omitClaudeMd`; None when none is present or
    the first one that may be cannot be read. Reading is the existence test: a stat that fails
    on an unreadable parent is then an unreadable definition, never an escaping error."""
    for definition in candidates:
        try:
            text = definition.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            continue
        except (OSError, UnicodeDecodeError):
            return None
        return _sets_omit_flag(text)
    return None


def _sets_omit_flag(definition: str) -> bool | None:
    """Whether the frontmatter's `omitClaudeMd` is the literal true, the last duplicate
    winning as in YAML; None with no frontmatter."""
    frontmatter = FRONTMATTER_RE.match(definition)
    if frontmatter is None:
        return None
    written = _OMIT_FLAG.findall(frontmatter.group(0))
    return bool(written) and written[-1] == _OMIT_SET


# -- Spawns: the text a split recipient receives ----------------------------------


def _received_units(
    units: Mapping[str, str], plugin_root: Path, scope: ProjectScope, audience: Audience
) -> Mapping[str, str]:
    """The text each unit reaches `audience` as: a managed split recipient's stored split
    where the artifact is trusted for that unit, anyone else's the unit's body, the artifact
    unread (an unmanaged spawn receives no unit)."""
    if audience.agent is not AgentKind.SPLIT_RECIPIENT or not isinstance(scope, Managed):
        return units
    # The split only shortens a delivery: a failure the parser did not foresee costs the
    # spawn its split, never its units, on the manifest path and the impaired floor alike.
    try:
        return _split_units(units, plugin_root)
    except Exception as exc:
        print(
            f"[inject_rules] WARNING: could not apply the spawn split: {exc!r};"
            " the core units arrive whole",
            file=sys.stderr,
        )
        return units


def _split_units(units: Mapping[str, str], plugin_root: Path) -> Mapping[str, str]:
    """Each unit's stored split where the artifact is trusted for it, else its body; a warning
    for no usable artifact and one naming each unit whose split its sources no longer trust."""
    split = _parsed_split(_read_bytes(plugin_root / SPAWN_SPLIT_PATH))
    manifest = _read_bytes(plugin_root / AUDIENCE_MANIFEST_PATH)
    if split is None or manifest is None:
        print(
            f"[inject_rules] WARNING: no usable spawn split under {plugin_root}"
            f" ({SPAWN_SPLIT_PATH}, {AUDIENCE_MANIFEST_PATH}); the core units arrive whole",
            file=sys.stderr,
        )
        return units
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    for unit_id in distrusted_units(units, split, manifest_sha):
        print(
            f"[inject_rules] WARNING: the spawn split of {unit_id} disagrees with its sources"
            " (stale or edited; regenerate with scripts/generate_kernels.py); it arrives whole",
            file=sys.stderr,
        )
    return spawn_units(units, split, manifest_sha)


def _read_bytes(path: Path) -> bytes | None:
    """The file's bytes, or None when it cannot be read; raw bytes, as the generator digests
    the audience manifest, so no newline translation separates the two digests."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def _parsed_split(raw: bytes | None) -> SpawnSplit | None:
    """The artifact, or None for one that is absent, not UTF-8 or not the schema."""
    if raw is None:
        return None
    try:
        return parse_spawn_split(raw.decode("utf-8"))
    except (UnicodeDecodeError, RecursionError):  # JSON nested past the parser's depth
        return None


# -- additionalContext emitter -------------------------------------------------


def _emit_additional_context(context: str, event: Event) -> None:
    """Emit additionalContext JSON for the event's hook contract."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": EVENT_NAMES[event],
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


def _parse_payload(raw_payload: str) -> dict:
    """The hook's JSON payload on stdin; anything that is not a JSON object reads as empty."""
    try:
        payload = json.loads(raw_payload) if raw_payload.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


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


@dataclass(frozen=True)
class Audience:
    """Who a delivery is planned for: the main session, or a spawn of one kind."""

    event: Event
    agent: AgentKind = AgentKind.WHOLE_RECIPIENT  # a session's agent kind is moot


SESSION = Audience(Event.SESSION)


def _floor_delivery(
    plugin_root: Path, scope: ProjectScope, audience: Audience, notice: str | None
) -> Delivery:
    """The impaired injection's delivery: the managed core units, read without the manifest."""
    bodies = {unit.unit_id: _read_rule_body(plugin_root, unit.path) for unit in MANAGED_CORE_UNITS}
    units = _received_units(bodies, plugin_root, scope, audience)
    return Delivery(notice, units, _plan(units, set(units), scope, set(), audience))


def _plan(
    units: Mapping[str, str],
    managed_only: set[str],
    scope: ProjectScope,
    disable_set: set[str],
    audience: Audience,
) -> tuple[DeliveryPart, ...]:
    native = _natively_installed(managed_only)  # an `every` unit keeps its linked copy
    return plan_delivery(
        units, managed_only, scope, audience.event, audience.agent, disable_set, native
    )


def _manifest_delivery(
    rules: list[dict],
    plugin_root: Path,
    cwd: Path,
    scope: ProjectScope,
    audience: Audience,
    *,
    effects: bool,
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

    bodies, managed_only = _hook_delivered_units(rules, plugin_root)
    units = _received_units(bodies, plugin_root, scope, audience)
    delivery = Delivery(None, units, _plan(units, managed_only, scope, disable_set, audience))
    if effects:
        _log_injection_summary(rules, units, delivery, disable_set)
    return delivery


def _planned_delivery(
    plugin_root: Path, cwd: Path, scope: ProjectScope, audience: Audience, *, effects: bool
) -> Delivery:
    # Kill switch: opt-out env var disables injection, all but the managed core units.
    if is_disabled(DISABLE_FLAG):
        print(
            "[inject_rules] Rule injection disabled by PRAXION_DISABLE_RULE_INJECTION;"
            " only the managed core units are delivered",
            file=sys.stderr,
        )
        return _floor_delivery(plugin_root, scope, audience, None)

    # An unavailable manifest is non-fatal but never silent; one that cannot be applied (a
    # damaged row) is the same impaired case, so it never costs a managed scope its core units.
    try:
        rules = _load_manifest(plugin_root)
        return _manifest_delivery(rules, plugin_root, cwd, scope, audience, effects=effects)
    except ManifestUnavailableError as exc:
        notice = _unavailable_notice(exc, scope)
    except Exception as exc:
        failure = ManifestUnavailableError(f"could not apply manifest: {exc!r}", REINSTALL_FIX)
        notice = _unavailable_notice(failure, scope)
    return _floor_delivery(plugin_root, scope, audience, notice)


def _requested_delivery(payload: dict, slot: int | None) -> tuple[Event, Delivery]:
    """The event the payload names and its delivery; a spawn's carries no notice and writes
    nothing, since its session has already reported and written."""
    plugin_root = _resolve_plugin_root()
    cwd = Path(payload.get("cwd") or os.getcwd())
    scope = scope_of(str(cwd))
    if payload.get("hook_event_name") != EVENT_NAMES[Event.SUBAGENT]:
        effects = slot in (None, EFFECTS_SLOT)
        return Event.SESSION, _planned_delivery(plugin_root, cwd, scope, SESSION, effects=effects)
    spawn = Audience(
        Event.SUBAGENT, _agent_kind(payload.get("agent_type"), plugin_root, cwd, scope)
    )
    delivery = _planned_delivery(plugin_root, cwd, scope, spawn, effects=False)
    return Event.SUBAGENT, replace(delivery, notice=None)


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

    event, delivery = _requested_delivery(_parse_payload(raw), slot)
    if slot is None:
        text = delivery.whole_text()
    else:
        texts = delivery.slot_texts()
        text = texts[slot - 1] if slot <= len(texts) else ""
    if text:
        _emit_additional_context(text, event)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fault tolerance: never block a session or a spawn on any unhandled exception.
        print(f"[inject_rules] ERROR: unhandled exception: {exc}", file=sys.stderr)
        sys.exit(0)
