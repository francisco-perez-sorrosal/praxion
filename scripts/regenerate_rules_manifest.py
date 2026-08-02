#!/usr/bin/env python3
"""Generate (or validate) rules/_manifest.yaml from rule file frontmatter.

Walks rules/**/*.md, reads YAML frontmatter, and emits rules/_manifest.yaml
with the canonical ordering and schema expected by inject_rules.py and
lib/install_shared.sh.

Usage:
    python3 scripts/regenerate_rules_manifest.py          # regenerate manifest
    python3 scripts/regenerate_rules_manifest.py --check  # exit 1 if drift
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RULES_DIR = REPO_ROOT / "rules"
MANIFEST_PATH = RULES_DIR / "_manifest.yaml"

DRIFT_MESSAGE = "Manifest drift detected. Run: python3 scripts/regenerate_rules_manifest.py"

# Core rule IDs that MUST carry core: true in frontmatter.
EXPECTED_CORE_IDS = frozenset(
    {
        "swe/agent-behavioral-contract",
        "swe/swe-agent-coordination-protocol",
        "swe/agent-intermediate-documents",
        "swe/adr-conventions",
        "CLAUDE",
    }
)

# Blacklistable always-loaded rules in canonical injection order.
# This order drives additionalContext concatenation in inject_rules.py.
# Any rule whose frontmatter declares `install: hook-deliver` MUST appear in
# this list — _validate_hook_deliver_coverage() enforces this at check time.
HOOK_DELIVER_ORDER = [
    "swe/memory-protocol",
    "swe/agent-model-routing",
    "swe/vcs/git-conventions",
]

MANIFEST_HEADER = (
    "# AUTO-GENERATED. Do not edit by hand.\n"
    "# Regenerate with: python3 scripts/regenerate_rules_manifest.py\n"
    "#\n"
    "# Schema version: 1\n"
)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a markdown file. Returns {} if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return yaml.safe_load("\n".join(lines[1:i])) or {}
    return {}


def _should_skip(rule_path: Path) -> bool:
    """Return True for README.md and files under any references/ directory."""
    if rule_path.name == "README.md":
        return True
    return any(part == "references" for part in rule_path.parts)


def _build_rule_record(rule_path: Path, fm: dict[str, Any]) -> dict[str, Any]:
    """Build one manifest rule record from path + frontmatter."""
    rule_id = str(rule_path.relative_to(RULES_DIR).with_suffix(""))
    record: dict[str, Any] = {
        "id": rule_id,
        "path": str(rule_path.relative_to(REPO_ROOT)),
        "load": str(fm.get("load", "path_scoped")),
        "core": bool(fm.get("core", False)),
        "install": str(fm.get("install", "symlink")),
        "chars": len(rule_path.read_text(encoding="utf-8")),
    }
    if paths_value := fm.get("paths"):
        record["paths"] = paths_value
    return record


def _collect_rules() -> list[dict[str, Any]]:
    """Walk rules/** and build records for all non-skipped rule files."""
    records = []
    for rule_path in sorted(RULES_DIR.rglob("*.md")):
        if _should_skip(rule_path):
            continue
        fm = _parse_frontmatter(rule_path.read_text(encoding="utf-8"))
        records.append(_build_rule_record(rule_path, fm))
    return records


def _validate_core_rules(records: list[dict[str, Any]]) -> list[str]:
    """Verify expected core rules carry core: true. Return error messages."""
    by_id = {r["id"]: r for r in records}
    errors = []
    for core_id in sorted(EXPECTED_CORE_IDS):
        if core_id not in by_id:
            errors.append(f"ERROR: core rule '{core_id}' not found in rules directory")
        elif not by_id[core_id].get("core", False):
            errors.append(
                f"ERROR: core rule {by_id[core_id]['path']} missing 'core: true' frontmatter"
            )
    return errors


def _validate_hook_deliver_coverage(records: list[dict[str, Any]]) -> list[str]:
    """Verify every install: hook-deliver rule appears in HOOK_DELIVER_ORDER.

    Catches the footgun where a new hook-deliver rule is added without updating
    the canonical injection-order list — without this check, the new rule
    would fall through to the path-scoped section of the manifest and lose
    its stable injection position.
    """
    declared = {r["id"] for r in records if r.get("install") == "hook-deliver" and "id" in r}
    ordered = set(HOOK_DELIVER_ORDER)
    missing = declared - ordered
    if not missing:
        return []
    return [
        f"ERROR: hook-deliver rule '{rid}' is not in HOOK_DELIVER_ORDER in"
        f" scripts/regenerate_rules_manifest.py. Add it in the desired"
        f" injection position (manifest order drives additionalContext order)."
        for rid in sorted(missing)
    ]


def _ordered_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return records in canonical manifest order:
    1. Core rules (alphabetical by id)
    2. Hook-deliver rules in stable injection order
    3. Path-scoped rules (alphabetical by id)
    """
    by_id = {r["id"]: r for r in records}
    core_rules = sorted((r for r in records if r.get("core")), key=lambda r: r["id"])
    hook_rules = [by_id[rid] for rid in HOOK_DELIVER_ORDER if rid in by_id]
    path_scoped = sorted(
        (r for r in records if not r.get("core") and r["id"] not in HOOK_DELIVER_ORDER),
        key=lambda r: r["id"],
    )
    return core_rules + hook_rules + path_scoped


def _render_doc(records: list[dict[str, Any]], include_timestamp: bool) -> str:
    """Serialize manifest records to YAML string.

    Schema: {version, generated_at?, rules}. The `categories` block was
    removed (it was written but consumed nowhere — inject_rules.py uses
    fnmatch directly on user patterns, so `ml/*`, `writing/*`, `swe/vcs/*`
    work without a categories alias table).
    """
    doc: dict[str, Any] = {"version": 1}
    if include_timestamp:
        doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["rules"] = _ordered_records(records)
    buf = io.StringIO()
    yaml.dump(doc, buf, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return buf.getvalue()


def _stable_body(content: str) -> str:
    """Strip volatile lines (header comments, generated_at) for comparison."""
    return "".join(
        ln
        for ln in content.splitlines(keepends=True)
        if not ln.startswith("#") and not ln.startswith("generated_at:")
    )


def _all_validation_errors(records: list[dict[str, Any]]) -> list[str]:
    """Aggregate every structural validation that must pass before the manifest
    is considered well-formed. Runs all validators so the user sees every
    error at once rather than discovering them one-at-a-time."""
    return _validate_core_rules(records) + _validate_hook_deliver_coverage(records)


def run_generate() -> int:
    """Regenerate rules/_manifest.yaml and write to disk."""
    records = _collect_rules()
    if errors := _all_validation_errors(records):
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    content = MANIFEST_HEADER + _render_doc(records, include_timestamp=True)
    MANIFEST_PATH.write_text(content, encoding="utf-8")
    print(f"Manifest written: {MANIFEST_PATH.relative_to(REPO_ROOT)} ({len(records)} rules)")
    return 0


def run_check() -> int:
    """Compare generated manifest with on-disk manifest. Exit 1 on drift."""
    records = _collect_rules()
    if errors := _all_validation_errors(records):
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    if not MANIFEST_PATH.exists():
        print(DRIFT_MESSAGE, file=sys.stderr)
        return 1
    # Compare without volatile lines so timestamps don't trigger false drift.
    generated = _render_doc(records, include_timestamp=False)
    on_disk = _stable_body(MANIFEST_PATH.read_text(encoding="utf-8"))
    if generated.strip() != on_disk.strip():
        print(DRIFT_MESSAGE, file=sys.stderr)
        return 1
    print("Manifest is up to date.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Check for drift and exit 1 if found (does not write).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return run_check() if args.check else run_generate()


if __name__ == "__main__":
    sys.exit(main())
