"""Extension-to-toolchain registry shared by the language-dispatch hooks.

Single source of truth for "which formatter serves this file extension, how is
it resolved on this machine, and what argv does it take". Consumed by the
PostToolUse formatter (``format_code.py``) and available to the commit-time
quality gate (``check_code_quality.py``) so tool resolution is not re-derived
per hook.

Legal-state invariant: a registry entry is either complete or absent -- there
is no partially-populated row. ``LangTool.resolve()`` returns a full argv
*prefix* or ``None``; ``None`` means "this tool is not reachable on this
machine", never an error. Every consumer treats an unreachable tool as a
silent no-op, so a missing toolchain can never block agent execution.

The module-level ``_assert_registry_is_legal()`` call enforces the invariant at
import time, making a malformed row a loud failure in tests rather than a
silent misdispatch at runtime.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Bound on the `git diff --cached` lookup in staged_files(). Matches the
# commit-gate hook's existing git timeout.
GIT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class LangTool:
    """One extension's formatting toolchain.

    Attributes:
        extension: The file suffix this row serves, including the leading dot.
        tool_name: Human-readable tool name, used in hook report messages.
        resolve: Returns the tool's argv prefix, or None when unreachable.
        build_format_argv: Maps (resolved prefix, file path) to a format argv.
    """

    extension: str
    tool_name: str
    resolve: Callable[[], list[str] | None]
    build_format_argv: Callable[[Sequence[str], str], list[str]]


def _resolve_ruff() -> list[str] | None:
    """Resolve a ruff invocation prefix, preferring a bare binary on PATH."""
    if shutil.which("ruff"):
        return ["ruff"]
    if shutil.which("uv"):
        return ["uv", "run", "ruff"]
    if shutil.which("pixi"):
        return ["pixi", "run", "ruff"]
    return None


def _build_ruff_format_argv(prefix: Sequence[str], file_path: str) -> list[str]:
    """Build the `ruff format <file>` argv from a resolved prefix."""
    return [*prefix, "format", file_path]


LANG_TOOLS: dict[str, LangTool] = {
    ".py": LangTool(
        extension=".py",
        tool_name="ruff",
        resolve=_resolve_ruff,
        build_format_argv=_build_ruff_format_argv,
    ),
}


def _assert_registry_is_legal() -> None:
    """Reject any partially-populated registry row at import time."""
    for key, entry in LANG_TOOLS.items():
        assert key.startswith("."), f"registry key {key!r} must start with '.'"
        assert entry.extension == key, (
            f"registry key {key!r} disagrees with entry.extension {entry.extension!r}"
        )
        assert entry.tool_name, f"registry entry {key!r} has an empty tool_name"
        assert callable(entry.resolve), f"registry entry {key!r} has a non-callable resolve"
        assert callable(entry.build_format_argv), (
            f"registry entry {key!r} has a non-callable build_format_argv"
        )


_assert_registry_is_legal()


def tool_for(file_path: str) -> LangTool | None:
    """Return the registry row serving `file_path`, or None when unhandled."""
    for extension, entry in LANG_TOOLS.items():
        if file_path.endswith(extension):
            return entry
    return None


def staged_files(extension: str) -> list[str]:
    """Return staged, non-deleted files carrying `extension`.

    Returns an empty list when git is unavailable or the command fails -- a
    consumer that finds no staged files is expected to no-op silently.
    """
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=d",
            "--",
            f"*{extension}",
        ],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]
