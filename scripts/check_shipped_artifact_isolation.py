#!/usr/bin/env python3
"""Shipped-artifact isolation checker.

Scans shipped artifact surfaces (rules/, skills/, agents/, commands/,
claude/config/) for references to specific ``.ai-state/`` or ``.ai-work/``
entries -- concrete ADR IDs, spec-tied REQ IDs, dated SPEC filenames, dated
SENTINEL_REPORT / IDEA_LEDGER filenames, and direct paths into
``.ai-state/decisions/``. Those references dangle once the plugin is
installed into a user's project.

Rationale lives in ``rules/swe/shipped-artifact-isolation.md``.

Escape hatch: add ``<!-- shipped-artifact-isolation:ignore -->`` on the same
line as an intentional reference. Test fixture trees under
``**/tests/fixtures/**`` are excluded wholesale -- their purpose is to mimic
real ``.ai-state/`` shapes.

Exit codes: 0 clean, 1 violations found, 2 script error.

Usage:
    python3 scripts/check_shipped_artifact_isolation.py
    python3 scripts/check_shipped_artifact_isolation.py --files FILE [FILE ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SHIPPED_ROOTS = (
    "rules",
    "skills",
    "agents",
    "commands",
    "claude/config",
    "claude/canonical-blocks",
)

IGNORE_MARKER = "<!-- shipped-artifact-isolation:ignore -->"

EXCLUDED_PATH_FRAGMENTS = ("/tests/fixtures/",)

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "adr-upper",
        re.compile(r"\bADR-\d+\b"),
        "uppercase-ADR ID (e.g., ADR-038); use a `dec-NNN` placeholder or state the rationale inline",
    ),
    (
        "dec-specific",
        re.compile(r"\bdec-\d{2,}\b"),
        "specific ADR ID (e.g., dec-042); use a `dec-NNN` placeholder or state the rationale inline",
    ),
    (
        "req-spec-tied",
        re.compile(r"\bREQ-[A-Z]{2,}-\d+\b"),
        "spec-tied REQ ID (e.g., REQ-DDL-15); describe the behavior inline instead",
    ),
    (
        "sentinel-dated",
        re.compile(r"\bSENTINEL_REPORT_\d{4}-\d{2}-\d{2}"),
        "specific SENTINEL_REPORT timestamp; use `YYYY-MM-DD_HH-MM-SS` placeholder",
    ),
    (
        "idea-ledger-dated",
        re.compile(r"\bIDEA_LEDGER_\d{4}-\d{2}-\d{2}"),
        "specific IDEA_LEDGER timestamp; use a `YYYY-MM-DD` placeholder",
    ),
    (
        "spec-dated",
        re.compile(r"\bSPEC_[A-Za-z_]+_\d{4}-\d{2}-\d{2}\.md\b"),
        "specific SPEC filename (e.g., SPEC_auth_2026-03-01.md); use `YYYY-MM-DD` placeholder",
    ),
    (
        "decision-path",
        re.compile(r"\.ai-state/decisions/\d+-[a-z]"),
        "direct path into a specific .ai-state/decisions/ entry; cite the path shape only",
    ),
)


def is_excluded(path: Path) -> bool:
    path_str = str(path).replace("\\", "/")
    return any(fragment in path_str for fragment in EXCLUDED_PATH_FRAGMENTS)


def iter_shipped_files(shipped_roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in shipped_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if path.is_file() and not is_excluded(path):
                files.append(path)
    return files


def scan_file(path: Path) -> list[tuple[int, str, str, str]]:
    findings: list[tuple[int, str, str, str]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return findings

    for line_no, line in enumerate(content.splitlines(), start=1):
        if IGNORE_MARKER in line:
            continue
        for name, pattern, description in PATTERNS:
            if pattern.search(line):
                findings.append((line_no, name, description, line.rstrip()))
    return findings


def filter_to_shipped(files: list[Path], repo_root: Path) -> list[Path]:
    shipped_root_paths = [(repo_root / root).resolve() for root in SHIPPED_ROOTS]
    out: list[Path] = []
    for candidate in files:
        abs_path = candidate if candidate.is_absolute() else (repo_root / candidate).resolve()
        if abs_path.suffix != ".md" or not abs_path.is_file():
            continue
        if is_excluded(abs_path):
            continue
        if any(_is_under(abs_path, root) for root in shipped_root_paths):
            out.append(abs_path)
    return out


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def format_findings(files: list[Path], repo_root: Path) -> tuple[int, list[str]]:
    lines: list[str] = []
    total = 0
    for path in sorted(files):
        findings = scan_file(path)
        if not findings:
            continue
        try:
            display = path.relative_to(repo_root)
        except ValueError:
            display = path
        lines.append("")
        lines.append(f"{display}:")
        for line_no, name, description, text in findings:
            snippet = text.strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            lines.append(f"  [{name}] line {line_no}: {description}")
            lines.append(f"    > {snippet}")
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
        help="Explicit file list (e.g., from pre-commit). Filtered to shipped surfaces.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()

    if args.files:
        files = filter_to_shipped(list(args.files), repo_root)
    else:
        shipped_roots = [repo_root / root for root in SHIPPED_ROOTS]
        files = iter_shipped_files(shipped_roots)

    total, detail_lines = format_findings(files, repo_root)

    if total == 0:
        print(f"scanned {len(files)} shipped file(s); 0 violations.")
        return 0

    print("\n".join(detail_lines))
    print(f"\nscanned {len(files)} shipped file(s); {total} violation(s).")
    print("")
    print("Rule:          rules/swe/shipped-artifact-isolation.md")
    print("Escape hatch:  add `<!-- shipped-artifact-isolation:ignore -->` on the same line")
    print("               when the reference is intentional (e.g., a migration note).")
    print("Test fixtures: files under **/tests/fixtures/** are already excluded.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
