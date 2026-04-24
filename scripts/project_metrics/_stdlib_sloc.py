"""Stdlib-only SLOC counter — fallback when ``scc`` is unavailable.

The graceful-degradation ADR row for ``scc`` promises a Python-stdlib SLOC
counting fallback. This module delivers that contract:

* Enumerate files via ``git ls-files`` (committed scope only — ignores
  untracked / .gitignored files to match what ``scc`` would see).
* Detect language by file extension using a small hand-curated mapping —
  the 15 or so extensions that cover >95% of typical projects.
* Count non-blank lines per file (the "Code" field in scc's output
  approximates non-blank; close enough for our purposes).
* Sum into per-language and repo-wide totals.

Binary files and files that fail UTF-8 decode are skipped. Files in
unrecognized extensions still contribute to ``sloc_total`` under a bucket
named ``"Other"`` but do not increment ``language_count`` (mirrors scc's
"Unrecognized" treatment).

This is called from ``aggregate.compose_aggregate`` when the ``scc``
namespace is absent or empty. Production data: it runs once per
``/project-metrics`` invocation on machines without ``scc`` installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

__all__ = ["compute_stdlib_sloc"]


# Extension → canonical language name. Keep small — this is a fallback, not
# a full language catalog. Unrecognized extensions fall into "Other" which
# counts lines but does not increment language_count.
_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
}

_GIT_LS_FILES_TIMEOUT_SECONDS = 30.0


def compute_stdlib_sloc(repo_root: Path | str) -> dict[str, Any]:
    """Return SLOC totals computed by stdlib + git — the scc fallback path.

    Return shape matches the subset of ``scc``'s namespace that
    ``aggregate.compose_aggregate`` consumes, so the caller can slot this
    into the same lookup paths.

    Keys:
      * ``sloc_total`` — sum of non-blank lines across all counted files
      * ``language_count`` — distinct recognized languages (excludes "Other")
      * ``file_count`` — files successfully read (skipped files excluded)
      * ``per_file_sloc`` — ``dict[path, int]`` of non-blank lines per file
      * ``language_breakdown`` — ``dict[lang, {"sloc": int, "file_count": int}]``
      * ``source`` — ``"stdlib_fallback"`` marker so downstream code can
        distinguish this path from scc's output
    """

    root = Path(repo_root)
    files = _list_tracked_files(root)
    per_file_sloc: dict[str, int] = {}
    language_breakdown: dict[str, dict[str, int]] = {}

    for rel in files:
        full = root / rel
        lang = _language_for(rel)
        sloc = _count_non_blank_lines(full)
        if sloc is None:
            continue  # binary or unreadable — skip silently
        per_file_sloc[rel] = sloc
        bucket = language_breakdown.setdefault(lang, {"sloc": 0, "file_count": 0})
        bucket["sloc"] += sloc
        bucket["file_count"] += 1

    recognized_langs = {lang for lang in language_breakdown if lang != "Other"}
    return {
        "sloc_total": sum(per_file_sloc.values()),
        "language_count": len(recognized_langs),
        "file_count": len(per_file_sloc),
        "per_file_sloc": per_file_sloc,
        "language_breakdown": language_breakdown,
        "source": "stdlib_fallback",
    }


def _list_tracked_files(repo_root: Path) -> list[str]:
    """Return git-tracked file paths relative to ``repo_root``.

    Empty list on non-zero git exit (non-repo, permissions, etc.) — the
    caller treats that as "no files to count" rather than propagating a
    failure. Matches the defensive posture of the rest of the stdlib floor.
    """

    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_LS_FILES_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _language_for(rel_path: str) -> str:
    """Map a file path to a canonical language name; ``"Other"`` when unknown."""

    ext = Path(rel_path).suffix.lower()
    return _EXTENSION_TO_LANGUAGE.get(ext, "Other")


def _count_non_blank_lines(path: Path) -> int | None:
    """Return the count of non-blank lines in ``path``.

    Returns ``None`` when the file cannot be read as UTF-8 (binary, encoding
    mismatch, missing, permission error). The caller treats ``None`` as
    "skip this file silently" — binary assets should not inflate SLOC.
    """

    try:
        with path.open("r", encoding="utf-8", errors="strict") as fh:
            return sum(1 for line in fh if line.strip())
    except (UnicodeDecodeError, OSError):
        return None
