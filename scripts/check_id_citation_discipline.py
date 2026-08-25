#!/usr/bin/env python3
"""ID citation discipline checker (inbound isolation).

Scans code files (Python, TS, JS, Rust, Go, etc.) for references to ephemeral
pipeline identifiers — REQ-*, AC-*, EC-X.X.X, Step N, test_req{NN}_* /
test_ac{NN}_* function naming, class Test*Req{NN}* / class Test*Ac{NN}*
class naming, and dec-draft-<hash> citations. Those identifiers live in
documents that get deleted with .ai-work/ or renamed at ADR finalize, so
in-code citations dangle the moment the pipeline cleans up or promotes.

This is the inbound counterpart to
``scripts/check_shipped_artifact_isolation.py``: that script prevents shipped
artifacts from citing ``.ai-state/`` entries; this script prevents code from
citing ephemeral ``.ai-work/`` entries.

Rationale lives in ``rules/swe/id-citation-discipline.md``.

Escape hatch: add ``id-citation-discipline:ignore`` on the same line as an
intentional reference (comment syntax varies by language — the check only
requires the literal substring to be present on the line).

Exempt paths (teaching materials handled by shipped-artifact-isolation):
  rules/, skills/, agents/, commands/, claude/config/
Exempt paths (pipeline/history/docs state):
  .ai-work/, .ai-state/, docs/, CHANGELOG.md, ROADMAP.md
Exempt paths (test fixtures/data):
  **/tests/fixtures/**, **/testdata/**

Exit codes: 0 clean, 1 violations found, 2 script error.

Usage:
    python3 scripts/check_id_citation_discipline.py
    python3 scripts/check_id_citation_discipline.py --files FILE [FILE ...]
    python3 scripts/check_id_citation_discipline.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".rb",
        ".sh",
        ".swift",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
    }
)

EXEMPT_PATH_PREFIXES = (
    ".ai-work/",
    ".ai-state/",
    "docs/",
    "rules/",
    "skills/",
    "agents/",
    "commands/",
    "claude/config/",
    "cursor/config/",
)

EXEMPT_FILENAMES = frozenset(
    {
        "CHANGELOG.md",
        "ROADMAP.md",
        # Installer scripts use "Step N — <phase>" as user-facing progress
        # UI labels; those are not pipeline-citation metadata.
        "install.sh",
        "install_claude.sh",
        "install_cursor.sh",
    }
)

# Specific files exempted because they describe the forbidden patterns as
# part of their own documentation (detector scripts). Without this, each
# detector would flag its own pattern strings and block every commit.
EXEMPT_EXACT_PATHS = frozenset(
    {
        "scripts/check_id_citation_discipline.py",
        "scripts/check_shipped_artifact_isolation.py",
        # Test fixtures for the detectors themselves necessarily contain the
        # forbidden patterns as test inputs — same self-referential exemption
        # logic as the detector scripts above.
        "tests/test_check_id_citation_discipline.py",
        # The pipeline-recovery reconciler PARSES "Step N" labels out of WIP.md /
        # IMPLEMENTATION_PLAN.md — the step number is its input grammar, not a
        # citation to an ephemeral spec — and its tests use "Step 1" as fixture
        # data. Same self-referential exemption as the detector scripts above.
        "scripts/reconcile_pipeline_state.py",
        "scripts/test_reconcile_pipeline_state.py",
    }
)

EXCLUDED_PATH_FRAGMENTS = (
    "/tests/fixtures/",
    "/testdata/",
    "/test_fixtures/",
    "/__pycache__/",
    "/.git/",
    # Sibling git worktrees. `.claude/worktrees/<name>/` holds a SEPARATE
    # checkout of this same repository, usually at a different commit. Scanning
    # it reports violations that are not in this checkout's tree, vanish when
    # the worktree is removed, and never appear in CI (a fresh clone has no
    # worktrees) — so the gate's result would depend on how many worktrees the
    # operator happens to have open. Each worktree is scanned by its own run.
    "/.claude/worktrees/",
    # Vendored dependency trees — never scan third-party library code.
    "/.venv/",
    "/venv/",
    "/vendor/",
    "/node_modules/",
    "/.tox/",
    "/dist/",
    "/build/",
    "/.cache/",
    "/htmlcov/",
    "/.mypy_cache/",
    "/.pytest_cache/",
    "/.ruff_cache/",
    "/site-packages/",
)

IGNORE_MARKER = "id-citation-discipline:ignore"

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "req-id",
        re.compile(r"\bREQ-[A-Z0-9][A-Z0-9\-]*\b"),
        "REQ identifier (e.g., REQ-SG-01) — describe behavior inline; "
        "REQ→test mapping belongs in .ai-work/<slug>/traceability.yml",
    ),
    (
        "ac-id",
        re.compile(r"\bAC-\d+\b"),
        "AC identifier (e.g., AC-14) — acceptance criteria live only in "
        "ephemeral SYSTEMS_PLAN.md; describe behavior inline",
    ),
    (
        "ec-id",
        re.compile(r"\bEC-\d+\.\d+(?:\.\d+)*\b"),
        "EC identifier (e.g., EC-3.2.4) — ephemeral criterion from "
        "SYSTEMS_PLAN.md; describe behavior inline",
    ),
    (
        "step-ref",
        re.compile(r"\bStep \d+[a-z]?\b"),
        "Step reference (e.g., Step 4c) — pipeline-local, deleted with "
        ".ai-work/; remove or rephrase without the step number",
    ),
    (
        "test-req-name",
        re.compile(r"\bdef test_req\d+"),
        "test function name with REQ prefix — name after the behavior "
        "(e.g., test_expired_token_returns_401)",
    ),
    (
        "test-ac-name",
        re.compile(r"\bdef test_ac\d+"),
        "test function name with AC prefix — name after the behavior",
    ),
    (
        "class-req-name",
        re.compile(r"\bclass Test\w*Req\d+\w*"),
        "test class name with Req{NN} in the identifier — name after the behavioral "
        "concept (e.g., TestSecretRedaction)",
    ),
    (
        "class-ac-name",
        re.compile(r"\bclass Test\w*Ac\d+\w*"),
        "test class name with Ac{NN} in the identifier — name after the behavioral concept",
    ),
    (
        "draft-adr-id",
        re.compile(r"\bdec-draft-[0-9a-f]{8}\b"),
        "draft ADR id — drafts/ fragments are renamed at finalize; cite the "
        "finalized dec-NNN instead, or mark a fixture literal with the ignore marker",
    ),
)


_SHEBANG_INTERPRETERS = ("bash", "sh", "zsh", "dash", "ksh")
_SHEBANG_PATTERNS = tuple(re.compile(rf"\b{shell}\b") for shell in _SHEBANG_INTERPRETERS)


def is_bash_shebang(path: Path) -> bool:
    """Return True if `path`'s first line is a bash/sh-family shebang.

    Extensionless executable scripts (e.g., `scripts/dispatch-reworks`) escape
    the extension-based corpus selection. Shebang detection brings them back
    into scope so id-citation violations in bash scripts are not silently
    skipped on commit.
    """
    try:
        with path.open("rb") as f:
            first_line = f.readline(256)
    except OSError:
        return False
    try:
        text = first_line.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return False
    if not text.startswith("#!"):
        return False
    return any(pattern.search(text) for pattern in _SHEBANG_PATTERNS)


def is_excluded_path(path: Path) -> bool:
    path_str = str(path).replace("\\", "/")
    return any(fragment in path_str for fragment in EXCLUDED_PATH_FRAGMENTS)


def is_exempt_by_path(rel_path: Path) -> bool:
    rel_str = str(rel_path).replace("\\", "/")
    if rel_str in EXEMPT_EXACT_PATHS:
        return True
    if rel_str in EXEMPT_FILENAMES:
        return True
    for prefix in EXEMPT_PATH_PREFIXES:
        if rel_str == prefix.rstrip("/") or rel_str.startswith(prefix):
            return True
    return False


def iter_code_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for ext in CODE_EXTENSIONS:
        for path in repo_root.rglob(f"*{ext}"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(repo_root)
            except ValueError:
                continue
            if is_exempt_by_path(rel) or is_excluded_path(path):
                continue
            files.append(path)

    # Second pass: extensionless executable shell scripts identified by shebang.
    # Heuristic: only executable files are scanned in full-repo mode to keep
    # false positives down (most extensionless text files are not scripts).
    seen = {f.resolve() for f in files}
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix:
            continue
        if path.resolve() in seen:
            continue
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            continue
        if is_exempt_by_path(rel) or is_excluded_path(path):
            continue
        if not os.access(path, os.X_OK):
            continue
        if not is_bash_shebang(path):
            continue
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
                break  # one pattern report per line keeps output readable
    return findings


def filter_files(explicit_files: list[Path], repo_root: Path) -> list[Path]:
    out: list[Path] = []
    for candidate in explicit_files:
        abs_path = candidate if candidate.is_absolute() else (repo_root / candidate).resolve()
        if not abs_path.is_file():
            continue
        # Accept recognized code extensions OR extensionless files with a
        # bash/sh-family shebang. Explicit user-passed paths (e.g., from
        # pre-commit's staged-files list) override the executable-bit
        # heuristic used in full-repo scans.
        if abs_path.suffix not in CODE_EXTENSIONS and not is_bash_shebang(abs_path):
            continue
        try:
            rel = abs_path.relative_to(repo_root)
        except ValueError:
            continue
        if is_exempt_by_path(rel) or is_excluded_path(abs_path):
            continue
        out.append(abs_path)
    return out


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
        help="Explicit file list (e.g., from pre-commit). Filtered to code surfaces.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()

    if args.files:
        files = filter_files(list(args.files), repo_root)
    else:
        files = iter_code_files(repo_root)

    total, detail_lines = format_findings(files, repo_root)

    if total == 0:
        print(f"scanned {len(files)} code file(s); 0 id-citation violations.")
        return 0

    print("\n".join(detail_lines))
    print(f"\nscanned {len(files)} code file(s); {total} violation(s).")
    print("")
    print("Rule:           rules/swe/id-citation-discipline.md")
    print("Remediation:    /decontaminate-ids  (or the id-decontamination skill)")
    print("Escape hatch:   add `id-citation-discipline:ignore` on the same line")
    print("                when the reference is truly intentional.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
