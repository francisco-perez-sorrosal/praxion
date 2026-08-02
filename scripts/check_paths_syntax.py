#!/usr/bin/env python3
"""Static check for `paths:` frontmatter syntax in path-scoped rules.

Background — upstream issue anthropics/claude-code#16853 (open as of 2026-05-12)
documents that the `_9A()` CSV parser inside Claude Code expects a string and
mis-handles YAML block-list inputs: multi-entry `paths:` declarations of the form

    paths:
      - "**/*.py"
      - "**/*.pyi"

have been reported to fail at user-level (`~/.claude/rules/`), while inline
JSON-array form (`paths: ["**/*.py", "**/*.pyi"]`) and single-entry
brace-expansion (`paths: ["**/*.{py,pyi}"]`) work consistently. The reported
fault is silent — the rule simply does not inject on Read.

This script is a *static syntax* check: it does not verify whether a given rule
actually injects in a running Claude Code session — that requires the
interactive `/memory` command. What it does is read every `rules/**/*.md`,
parse the frontmatter `paths:` declaration, classify the syntax form, and flag
multi-entry YAML block-lists as AT_RISK with a suggested inline-array rewrite.

Usage:
    python3 scripts/check_paths_syntax.py            # human-readable report
    python3 scripts/check_paths_syntax.py --json     # machine-readable
    python3 scripts/check_paths_syntax.py --check    # exit 1 if AT_RISK found

Stdlib-only by design (no PyYAML dependency); the frontmatter parser is
sufficient for Praxion's rule shape (single `paths:` block, no nested YAML).

See `rules/swe/agent-behavioral-contract.md` and td-033 in
`.ai-state/TECH_DEBT_LEDGER.md` for context.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / "rules"


class SyntaxForm(StrEnum):
    """Surface form used by a `paths:` declaration in YAML frontmatter."""

    INLINE_ARRAY = "inline-array"  # paths: ["**/*.py", "**/*.pyi"]
    BLOCK_LIST_SINGLE = "block-list-single"  # paths:\n  - "**/*.py"
    BLOCK_LIST_MULTI = "block-list-multi"  # paths:\n  - "..."\n  - "..."
    SINGLE_STRING = "single-string"  # paths: "**/*.py"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PathsDecl:
    """A single rule file's `paths:` declaration, classified."""

    file: Path
    form: SyntaxForm
    entries: tuple[str, ...] = field(default_factory=tuple)

    @property
    def at_risk(self) -> bool:
        """True for forms reported as unreliable per upstream #16853 comments."""
        return self.form is SyntaxForm.BLOCK_LIST_MULTI

    @property
    def suggested_inline(self) -> str | None:
        """Inline-array rewrite for AT_RISK rows; None if not applicable."""
        if not self.at_risk:
            return None
        quoted = ", ".join(f'"{e}"' for e in self.entries)
        return f"paths: [{quoted}]"


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_INLINE_PATHS_RE = re.compile(r"^paths:\s*\[(.*)\]\s*$", re.MULTILINE)
_SINGLE_PATHS_RE = re.compile(r'^paths:\s*"([^"]+)"\s*$', re.MULTILINE)
_BLOCK_PATHS_RE = re.compile(r"^paths:\s*\n((?:\s+-\s+.*(?:\n|$))+)", re.MULTILINE)
_BLOCK_ENTRY_RE = re.compile(r'^\s+-\s+"?([^"\n]+)"?\s*$', re.MULTILINE)


def _extract_frontmatter(text: str) -> str | None:
    m = _FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def _parse_inline_entries(raw: str) -> tuple[str, ...]:
    """Parse the inside of `[ "a", "b" ]` into a tuple of strings."""
    # Conservative: strip quotes, split on comma, trim whitespace.
    parts = [p.strip().strip('"').strip("'") for p in raw.split(",")]
    return tuple(p for p in parts if p)


def classify(rule_path: Path) -> PathsDecl | None:
    """Read a rule file and classify its `paths:` declaration, if present."""
    try:
        text = rule_path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _extract_frontmatter(text)
    if fm is None or "paths:" not in fm:
        return None

    if m := _INLINE_PATHS_RE.search(fm):
        entries = _parse_inline_entries(m.group(1))
        return PathsDecl(rule_path, SyntaxForm.INLINE_ARRAY, entries)

    if m := _SINGLE_PATHS_RE.search(fm):
        return PathsDecl(rule_path, SyntaxForm.SINGLE_STRING, (m.group(1),))

    if m := _BLOCK_PATHS_RE.search(fm):
        entries = tuple(_BLOCK_ENTRY_RE.findall(m.group(0)))
        form = SyntaxForm.BLOCK_LIST_SINGLE if len(entries) <= 1 else SyntaxForm.BLOCK_LIST_MULTI
        return PathsDecl(rule_path, form, entries)

    return PathsDecl(rule_path, SyntaxForm.UNKNOWN)


def scan_rules() -> list[PathsDecl]:
    """Classify every `rules/**/*.md` with a `paths:` frontmatter field."""
    decls: list[PathsDecl] = []
    for md in sorted(RULES_DIR.rglob("*.md")):
        decl = classify(md)
        if decl is not None:
            decls.append(decl)
    return decls


def _render_human(decls: list[PathsDecl]) -> str:
    """Pretty terminal table; AT_RISK rows include a fix suggestion."""
    lines = [
        f"Scanned {len(decls)} path-scoped rules under {RULES_DIR.relative_to(REPO_ROOT)}/",
        "",
        f"{'STATUS':<8} {'FORM':<20} {'N':<3} FILE",
        f"{'-' * 8} {'-' * 20} {'-' * 3} {'-' * 40}",
    ]
    at_risk: list[PathsDecl] = []
    for d in decls:
        status = "AT_RISK" if d.at_risk else "OK"
        rel = d.file.relative_to(REPO_ROOT)
        lines.append(f"{status:<8} {d.form.value:<20} {len(d.entries):<3} {rel}")
        if d.at_risk:
            at_risk.append(d)

    if at_risk:
        lines.append("")
        lines.append(
            f"⚠️  {len(at_risk)} rule(s) use multi-entry YAML block-list "
            f"`paths:` — reportedly unreliable per anthropics/claude-code#16853."
        )
        lines.append("Suggested inline-array rewrites:")
        for d in at_risk:
            rel = d.file.relative_to(REPO_ROOT)
            lines.append(f"  {rel}")
            lines.append(f"    {d.suggested_inline}")
    else:
        lines.append("")
        lines.append("✅ All path-scoped rules use a reportedly-reliable `paths:` form.")
    return "\n".join(lines)


def _render_json(decls: list[PathsDecl]) -> str:
    payload = [
        {
            "file": str(d.file.relative_to(REPO_ROOT)),
            "form": d.form.value,
            "entries": list(d.entries),
            "at_risk": d.at_risk,
            "suggested_inline": d.suggested_inline,
        }
        for d in decls
    ]
    return json.dumps(
        {
            "scanned": len(decls),
            "at_risk_count": sum(1 for d in decls if d.at_risk),
            "rules": payload,
        },
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any AT_RISK rules are detected",
    )
    args = parser.parse_args()

    decls = scan_rules()
    if not decls:
        print(f"No path-scoped rules found under {RULES_DIR}", file=sys.stderr)
        return 0

    out = _render_json(decls) if args.json else _render_human(decls)
    print(out)

    if args.check and any(d.at_risk for d in decls):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
