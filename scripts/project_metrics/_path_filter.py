"""Shared path-filter for project-source vs ecosystem-noise discrimination.

Several collectors (``git``, ``scc``, ``lizard``) walk the working tree or
git history and emit per-file dicts. Without filtering, those dicts are
polluted by ecosystem directories (``.ai-state/``, ``.ai-work/``, build
caches, virtualenvs) that are not part of the project's source code. The
metrics those collectors feed -- churn, change entropy, ownership, SLOC,
CCN -- become misleading when ecosystem files dominate the input.

This module provides a single shared exclusion list so every collector
filters consistently, plus tool-specific helpers for emitting CLI flags
to the underlying tools that already support directory exclusion (``scc
--exclude-dir``, ``lizard --exclude``). Defense in depth: collectors
also post-filter the resulting dicts so a tool that ignored the flag
(or a future collector that adds a new dict-shaped field) still produces
clean output.

The exclusion set is intentionally a **hardcoded default**, not a
runtime CLI flag. Adding a flag is a one-line follow-up if a project
needs an override; the simpler default keeps the contract stable across
runs and makes trend deltas comparable.
"""

from __future__ import annotations

from typing import TypeVar

__all__ = [
    "DEFAULT_EXCLUDED_DIRS",
    "is_excluded_path",
    "filter_path_dict",
    "scc_exclude_dir_args",
    "lizard_exclude_args",
]


# ---------------------------------------------------------------------------
# DEFAULT_EXCLUDED_DIRS -- single source of truth.
#
# Entries are POSIX-style paths. Single-component entries (``.ai-state``)
# match anywhere in the path. Multi-component entries (``.claude/worktrees``)
# match a contiguous component sequence. Order is irrelevant; the matcher
# scans every entry.
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        # Praxion ecosystem state directories -- not project source
        ".ai-state",
        ".ai-work",
        ".claude/worktrees",
        ".trees",
        ".cursor",
        # Git internals (scc already defaults to excluding .git, but other
        # collectors do not; explicit defense in depth)
        ".git",
        # Python ecosystem caches and virtualenvs
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        # Build outputs
        "dist",
        "build",
        "htmlcov",
        # JS/TS dependency tree
        "node_modules",
    }
)


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Path predicate -- the core filter.
# ---------------------------------------------------------------------------


def is_excluded_path(path: str, *, excluded: frozenset[str] | None = None) -> bool:
    """Return True when ``path`` falls under any excluded directory.

    Matches at component boundaries -- a file literally named ``.ai-state``
    in the project root is not falsely matched against the excluded
    directory ``.ai-state``, because matching looks for the full component
    sequence followed by either a path separator or the end of the path.

    Multi-component exclusions (``.claude/worktrees``) match when the
    component sequence appears contiguously in ``path``. Single-component
    exclusions (``.venv``) match when any single component equals them.

    Path separators are normalized to forward slash (POSIX style), so
    Windows-shaped paths from a hypothetical caller still classify
    correctly. Leading ``./`` is stripped so ``./foo/.ai-state/bar`` and
    ``foo/.ai-state/bar`` classify identically.
    """

    if not path:
        return False
    excluded_set = DEFAULT_EXCLUDED_DIRS if excluded is None else excluded
    normalized = path.replace("\\", "/")
    # Strip the literal leading "./" prefix only -- not arbitrary "."/"/"
    # characters, which would corrupt a path that starts with a dotfile
    # like ".ai-state/foo".
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts:
        return False
    for entry in excluded_set:
        entry_parts = entry.split("/")
        n = len(entry_parts)
        if n == 0:
            continue
        for i in range(len(parts) - n + 1):
            if parts[i : i + n] == entry_parts:
                return True
    return False


# ---------------------------------------------------------------------------
# Dict filter -- shape-preserving wrapper around is_excluded_path.
# ---------------------------------------------------------------------------


def filter_path_dict(
    mapping: dict[str, T],
    *,
    excluded: frozenset[str] | None = None,
) -> dict[str, T]:
    """Return a new dict with excluded keys removed; original is not mutated.

    The collectors emit per-file dicts (``churn_90d``, ``ownership``,
    ``per_file_sloc``, ``files``). Each can be cleaned by passing it
    through this helper. Iteration order is preserved -- Python 3.7+
    dicts are insertion-ordered, and this helper iterates in that order.
    """

    return {
        key: value for key, value in mapping.items() if not is_excluded_path(key, excluded=excluded)
    }


# ---------------------------------------------------------------------------
# Tool-specific flag emitters -- so call sites stay declarative.
# ---------------------------------------------------------------------------


def scc_exclude_dir_args(*, excluded: frozenset[str] | None = None) -> list[str]:
    """Return ``["--exclude-dir", "<csv>"]`` for the scc CLI.

    scc accepts ``--exclude-dir`` as a comma-separated list of directory
    *names* (matched anywhere in the tree, not anchored paths). Multi-
    component entries (``.claude/worktrees``) cannot be expressed via this
    flag; they are handled by the post-filter pass. scc's own defaults
    (``.git, .hg, .svn``) are preserved -- this helper extends rather than
    replaces them.
    """

    excluded_set = DEFAULT_EXCLUDED_DIRS if excluded is None else excluded
    single_component = sorted(entry for entry in excluded_set if "/" not in entry)
    if not single_component:
        return []
    return ["--exclude-dir", ",".join(single_component)]


def lizard_exclude_args(*, excluded: frozenset[str] | None = None) -> list[str]:
    """Return repeated ``--exclude <pattern>`` argv for the lizard CLI.

    Lizard's ``--exclude`` takes a glob pattern matched against file
    paths. The helper emits one ``--exclude`` flag per excluded entry
    using the ``*/<entry>/*`` pattern shape, which matches files
    anywhere under a directory whose path ends with ``<entry>``.
    Multi-component entries are emitted with internal slashes preserved
    so ``.claude/worktrees`` becomes ``*/.claude/worktrees/*``.
    """

    excluded_set = DEFAULT_EXCLUDED_DIRS if excluded is None else excluded
    args: list[str] = []
    for entry in sorted(excluded_set):
        args.extend(["--exclude", f"*/{entry}/*"])
    return args
