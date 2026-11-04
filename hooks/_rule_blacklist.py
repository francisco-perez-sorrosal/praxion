"""The per-project Praxion rules blacklist, as `inject_rules.py` applies it.

Where a project's `.claude/praxion-rules.yaml` is read from, which rule ids its
`disable:` patterns name (core rules never, a disabled rule's resident always),
how a disabled linked rule is excluded through `claudeMdExcludes`, and where the
shipped template is seeded. Reading the YAML stays with the injector's other
reader; everything here works on parsed values and the plugin's rule files.

Every message keeps the `[inject_rules]` prefix: these are the injector's
warnings, and the eval observer and the routing acceptance test grep for it.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import sys
from pathlib import Path

from _project_scope import Managed, ProjectScope

SUPPORTED_SCHEMA_VERSION = 1

# Glob-pattern prefix Praxion uses for claudeMdExcludes entries it manages.
# Any entry starting with this prefix is recomputed on every SessionStart;
# any entry not starting with it is preserved as a user-managed exclusion.
_PRAXION_EXCLUSION_PREFIX = "**/.claude/rules/"

# A resident file names the rule it stands for in a top-level `resident_of:` frontmatter key.
# Local copy of scripts/_resident_of.py::resident_parent — the injector runs from copies that
# carry only rules/, lib/ and hooks/ — held equal to it by a parity test in test_inject_rules.py.
_RESIDENT_OF_KEY = re.compile(r"""^["']?resident_of["']?\s*:\s*(.*?)\s*$""")
_FRONTMATTER_DELIMITER = "---"


# -- Where the blacklist lives ---------------------------------------------------


def blacklist_path(directory: Path) -> Path:
    return directory / ".claude" / "praxion-rules.yaml"


def blacklist_directory(cwd: Path, scope: ProjectScope) -> Path:
    """The directory whose user-written blacklist applies: the start directory when
    it has one, else the managed root (a subdirectory's own list wins)."""
    if isinstance(scope, Managed) and not blacklist_path(cwd).exists():
        return scope.root
    return cwd


def ensure_template_present(scope: ProjectScope, plugin_root: Path) -> None:
    """Copy the shipped blacklist template into the managed root's .claude/ if absent.

    Idempotent. Writes only at `Managed.root`: nothing happens in an unmanaged
    directory, and a subdirectory session leaves the subdirectory alone. Skips
    when EITHER `.claude/praxion-rules.yaml.example` OR
    `.claude/praxion-rules.yaml` already exists at the root. Fail-safe: any
    exception is logged and swallowed (template placement is auxiliary; never
    breaks SessionStart).
    """
    if not isinstance(scope, Managed):
        return
    try:
        claude_dir = scope.root / ".claude"
        example_path = claude_dir / "praxion-rules.yaml.example"
        if example_path.exists() or blacklist_path(scope.root).exists():
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


# -- What the blacklist disables -------------------------------------------------


def disable_patterns(project_cfg: dict) -> list[str]:
    """A parsed blacklist's `disable:` patterns, failing open on any malformed shape.

    Returns an empty list for an unsupported schema version or a non-list
    `disable:` value, and skips any entry that is not a string; each emits a
    stderr warning.
    """
    version = _resolve_schema_version(project_cfg)
    if version > SUPPORTED_SCHEMA_VERSION:
        print(
            f"[inject_rules] Schema version {version} is not supported by "
            "this version of Praxion; falling back to no suppression",
            file=sys.stderr,
        )
        return []  # Fail open: inject all (no suppression)

    raw_disable = project_cfg.get("disable", [])
    if isinstance(raw_disable, list):
        skipped = [entry for entry in raw_disable if not isinstance(entry, str)]
        if skipped:  # a bare `-` line reads as null, which no rule id can match
            print(
                f"[inject_rules] WARNING: 'disable:' entries {skipped!r} are not rule ids"
                " or globs; skipped",
                file=sys.stderr,
            )
        return [entry for entry in raw_disable if isinstance(entry, str)]
    if "disable" in project_cfg:
        # Present but malformed: scalar, dict, or null. Silent coercion would
        # mask a typo (e.g., `disable: ml/*` instead of `disable: [ml/*]`), so
        # surface it explicitly.
        print(
            f"[inject_rules] WARNING: 'disable:' must be a YAML list,"
            f" got {type(raw_disable).__name__}: {raw_disable!r}."
            " Treating as empty. Use the list form:"
            " 'disable:\\n  - rule/id'",
            file=sys.stderr,
        )
    return []


def _resolve_schema_version(project_cfg: dict) -> int:
    """Extract and validate the project config's `version:` field, coercing bad shapes to 1."""
    raw_version = project_cfg.get("version", 1)
    if isinstance(raw_version, int):
        return raw_version
    print(
        f"[inject_rules] WARNING: 'version:' field has non-integer"
        f" value {raw_version!r}; coercing to 1. Expected: 'version: 1'.",
        file=sys.stderr,
    )
    return 1


def compute_disable_set(
    patterns: list[str], rules: list[dict], all_rule_ids: list[str]
) -> set[str]:
    """Resolve glob patterns to rule IDs, warn on typos, and strip core rules.

    Combines glob resolution (`_resolve_disable_globs`) with core-rule
    protection (`_filter_core_rules`) — the two steps that turn raw YAML
    patterns into the final, safe-to-apply set of suppressed rule IDs.
    """
    disable_set, unmatched_patterns = _resolve_disable_globs(patterns, all_rule_ids)
    for pattern in unmatched_patterns:
        print(
            f"[inject_rules] WARNING: disable pattern {pattern!r} matched no"
            " rule in rules/_manifest.yaml — typo? Run `python3"
            " scripts/regenerate_rules_manifest.py` to see valid IDs.",
            file=sys.stderr,
        )
    return _filter_core_rules(disable_set, rules)


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


def _filter_core_rules(disable_set: set[str], rules: list[dict]) -> set[str]:
    """Remove core rules from the disable set, emitting a warning for each.

    Returns the filtered disable set (core rules removed).
    """
    core_ids = {r["id"] for r in rules if r.get("core") is True}
    attempted_core = disable_set & core_ids
    for rule_id in sorted(attempted_core):
        print(
            f"[inject_rules] WARNING: cannot disable core rule '{rule_id}' — kept loaded",
            file=sys.stderr,
        )
    return disable_set - core_ids


# -- Residents: a disabled rule takes its one-line projection with it --------------


def add_residents_of_disabled(
    disable_set: set[str], rules: list[dict], plugin_root: Path
) -> set[str]:
    """Add to the disable set every hook-deliver resident whose parent rule is in it.

    A path-scoped rule keeps its always-loaded one-line projection as a separate
    rule, so the blacklist's id globs would otherwise miss it and an opt-out
    would silently regain the session-start text. A core resident stays loaded,
    like any core rule; a core parent never reaches the disable set.
    """
    if not disable_set:
        return disable_set
    residents = {
        rule["id"]
        for rule in rules
        if rule.get("install") == "hook-deliver"
        and rule.get("core") is not True
        and "id" in rule
        and _read_resident_parent_id(plugin_root, rule) in disable_set
    }
    return disable_set | residents


def _read_resident_parent_id(plugin_root: Path, rule: dict) -> str | None:
    """The id of the rule this manifest row stands for as a resident, or None.

    A rule's id is its path minus `rules/` and `.md`. Fail-open: an unreadable
    file is treated as no resident, so it stays injected.
    """
    rel_path = rule.get("path", "")
    if not rel_path:
        return None
    try:
        text = (plugin_root / rel_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"[inject_rules] WARNING: could not read rule file {plugin_root / rel_path}: {exc}",
            file=sys.stderr,
        )
        return None
    parent_path = resident_parent(text)
    if parent_path is None:
        return None
    return parent_path.removeprefix("rules/").removesuffix(".md")


def resident_parent(text: str) -> str | None:
    """The rule path a file's frontmatter names in `resident_of`, or None when it names none."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != _FRONTMATTER_DELIMITER:
        return None
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip() == _FRONTMATTER_DELIMITER), None
    )
    if closing is None:  # never closed: not frontmatter
        return None
    for line in lines[1:closing]:
        match = _RESIDENT_OF_KEY.match(line)
        if match:
            return match.group(1).strip("\"'") or None
    return None


# -- Linked rules: suppressed through claudeMdExcludes -----------------------------


def compute_symlink_exclusions(disable_set: set[str], rules: list[dict]) -> list[str]:
    """Compute portable claudeMdExcludes glob patterns for disabled rules.

    For each non-core rule_id in disable_set, produce a glob pattern of the
    form `**/.claude/rules/<id>.md` that matches the rule's installed symlink
    path on any user's machine — irrespective of home-directory layout. Both
    install types are covered: the primary suppression for a linked rule, the
    defense-in-depth the injector's docstring describes for a hook-deliver one.

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


def apply_symlink_exclusions(cwd: Path, exclusions: list[str]) -> None:
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
            if not (isinstance(entry, str) and entry.startswith(_PRAXION_EXCLUSION_PREFIX))
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
        # compute_symlink_exclusions, so the file content is still stable
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
