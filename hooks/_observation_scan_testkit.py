"""Source scan shared by the observation-log inventory tests.

Not a test module. The private-reader and writer-truth tests ask the same two
questions of the repository's Python sources: which modules are candidates, and
which of them import one submodule of the owner package. Both answers live here
so the two scans cannot drift apart.

Candidates come from `git ls-files`, so gitignored scratch space (pipeline notes,
probe copies of `hooks/`, a mutation sensor's working tree) never enters a scan.
The listing keeps untracked, unignored files so a new module is seen before it is
staged. A directory that is not a repository root is walked instead.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

OWNER_PACKAGE_PREFIX = "hooks/_observation_log/"

# Test modules and pytest conftest files are test support, not consumers.
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]+|conftest)\.py$")
_EXCLUDED_DIR_MARKERS = (
    ".venv/",
    "/plugins/cache/",
    "/.claude/worktrees/",
    "/node_modules/",
    "/.ai-work/",
    "/tmp/",
)
_OWNER_PACKAGE_NAME = "_observation_log"


def _git_listing(root: Path) -> list[str] | None:
    """Repo-relative `.py` paths git sees under a repository root, or None when
    `root` is not one (no git, no repository, or a subdirectory of one)."""
    try:
        prefix = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-prefix"],
            capture_output=True,
            text=True,
            check=True,
        )
        if prefix.stdout.strip():
            return None
        listing = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                "*.py",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return sorted(set(filter(None, listing.stdout.split("\0"))))


def _python_files(root: Path) -> list[str]:
    listed = _git_listing(root)
    if listed is None:
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py"))
    return [rel for rel in listed if (root / rel).is_file()]


def candidate_modules(root: Path) -> Iterator[tuple[str, Path]]:
    """(repo-relative path, path) of every non-test `.py` file outside the owner
    package and the excluded directories."""
    for rel in _python_files(root):
        if rel.startswith(OWNER_PACKAGE_PREFIX) or _TEST_FILE_RE.search(rel):
            continue
        if any(marker in f"/{rel}" for marker in _EXCLUDED_DIR_MARKERS):
            continue
        yield rel, root / rel


def _imports_submodule(tree: ast.AST, submodule: str) -> bool:
    """Whether any import in `tree`, at any depth, binds the owner package's
    `submodule` -- bare, `hooks.`-prefixed, relative, aliased, parenthesized."""
    tail = [_OWNER_PACKAGE_NAME, submodule]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[-2:] == tail:
                return True
            if parts[-1] == _OWNER_PACKAGE_NAME and any(a.name == submodule for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[-2:] == tail for a in node.names):
                return True
    return False


def importers_of(root: Path, submodule: str) -> tuple[frozenset[str], tuple[str, ...]]:
    """(candidate modules importing `submodule`, candidates that failed to
    parse). Only sources naming the owner package are parsed -- every static
    import form spells it."""
    importers, unparseable = set(), []
    for rel, path in candidate_modules(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if _OWNER_PACKAGE_NAME not in text:
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            unparseable.append(rel)
            continue
        if _imports_submodule(tree, submodule):
            importers.add(rel)
    return frozenset(importers), tuple(unparseable)
