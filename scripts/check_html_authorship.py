#!/usr/bin/env python3
"""HTML authorship boundary checker.

Enforces the Authorship Boundary from ``rules/writing/html-output-conventions.md``:
every ``.html`` file must be either (a) an explicitly allowlisted ephemeral tool UI
with no MD source, or (b) a canonical ``share_out: true`` artifact rendered from a
same-directory, same-basename ``.md`` source (``report.html`` -> ``report.md``).

Missing sibling, sibling with no frontmatter, or ``share_out`` absent/false are all
violations -- HTML authorship outside the dashboard renderer must be traceable to a
canonical, opt-in Markdown source.

Escape hatch: add the path prefix to ``EXEMPT_PATH_PREFIXES`` below for standalone
tool UIs (ephemeral, user-requested, no-MD-backing HTML) per the rule's "Scope:
Canonical Surfaces, Not Ephemeral Output" section.

Exit codes: 0 clean, 1 violations found, 2 script error.

Usage:
    python3 scripts/check_html_authorship.py
    python3 scripts/check_html_authorship.py --files FILE [FILE ...]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# Standalone tool UIs with no MD source -- confirmed via `git ls-files "*.html"`.
EXEMPT_PATH_PREFIXES: tuple[str, ...] = ("scripts/praxion_parallel_ui_assets/",)

_FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _parse_frontmatter(text: str) -> dict[str, Any]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def is_exempt(rel_path_str: str) -> bool:
    return any(rel_path_str.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)


def _tracked_html_files(repo_root: Path) -> list[str]:
    """Git-tracked *.html paths, relative to repo_root -- excludes gitignored
    build output (node_modules/, .next/) that an unscoped rglob would catch."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "*.html"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in result.stdout.splitlines() if line]


def find_violation(html_path: Path, repo_root: Path) -> str | None:
    """Return a violation description, or None if the file satisfies the boundary."""
    abs_path = html_path if html_path.is_absolute() else (repo_root / html_path).resolve()
    try:
        rel_str = str(abs_path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel_str = str(abs_path).replace("\\", "/")

    if is_exempt(rel_str):
        return None

    sibling_md = abs_path.with_suffix(".md")
    if not sibling_md.is_file():
        return "no sibling .md source -- add one with `share_out: true` frontmatter, or allowlist in EXEMPT_PATH_PREFIXES"

    frontmatter = _parse_frontmatter(_read_text(sibling_md))
    if not frontmatter.get("share_out", False):
        return f"sibling `{sibling_md.name}` is missing `share_out: true` frontmatter"

    return None


def format_violations(files: list[Path], repo_root: Path) -> tuple[int, list[str]]:
    lines: list[str] = []
    total = 0
    for path in sorted(files):
        reason = find_violation(path, repo_root)
        if reason is None:
            continue
        try:
            display = path.relative_to(repo_root)
        except ValueError:
            display = path
        lines.append(f"{display}: {reason}")
        total += 1
    return total, lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        type=Path,
        default=None,
        help="Explicit file list (e.g., from pre-commit). Filtered to *.html. "
        "Omit entirely to scan every git-tracked *.html file in the repo.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()

    if args.files is not None:
        files = [f if f.is_absolute() else (repo_root / f) for f in args.files]
        files = [f for f in files if f.suffix == ".html" and f.is_file()]
    else:
        files = [repo_root / rel for rel in _tracked_html_files(repo_root)]

    total, detail_lines = format_violations(files, repo_root)

    if total == 0:
        print(f"scanned {len(files)} .html file(s); 0 violations.")
        return 0

    print("\n".join(detail_lines))
    print(f"\nscanned {len(files)} .html file(s); {total} violation(s).")
    print("")
    print("Rule: rules/writing/html-output-conventions.md (Authorship Boundary)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
