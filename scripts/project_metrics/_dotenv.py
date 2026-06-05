"""Minimal stdlib ``.env`` loader for the metrics CLI entry point.

The metrics package is stdlib-only (no third-party imports), so it cannot use
``python-dotenv`` the way the eval harness does. This module provides the small
subset of that behavior the CLI needs: find the nearest ``.env`` from the
invocation cwd upward and merge its ``KEY=VALUE`` pairs into ``os.environ``
*without* overriding variables already set in the environment.

Loaded at the ``python -m scripts.project_metrics`` boundary (``__main__``) so an
operator can keep ``CLAUDE_CODE_OAUTH_TOKEN`` / ``ANTHROPIC_API_KEY`` in a
gitignored ``.env`` instead of passing them inline on every invocation. Because
``override`` defaults to ``False``, an explicit inline ``export`` still wins —
matching ``python-dotenv``'s default and the eval harness's documented contract.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["find_dotenv", "load_dotenv"]


def find_dotenv(start: Path | None = None, filename: str = ".env") -> Path | None:
    """Return the nearest ``filename`` searching ``start`` (default cwd) upward.

    Mirrors ``python-dotenv``'s ``find_dotenv(usecwd=True)``: walks from the
    current working directory toward the filesystem root and returns the first
    match, or ``None`` when no file is found.
    """

    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def load_dotenv(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Parse a ``.env`` file and merge it into ``os.environ``.

    Returns the parsed pairs. A missing file is a no-op (returns ``{}``).
    Malformed lines are skipped rather than raising, so a stray line never breaks
    a metrics run. With ``override=False`` (the default), a key already present
    in ``os.environ`` is left untouched.
    """

    dotenv_path = path or find_dotenv()
    if dotenv_path is None or not dotenv_path.is_file():
        return {}

    parsed: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        pair = _parse_line(raw_line)
        if pair is None:
            continue
        key, value = pair
        parsed[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return parsed


def _parse_line(raw_line: str) -> tuple[str, str] | None:
    """Parse one ``.env`` line into ``(key, value)`` or ``None`` to skip it.

    Handles blank lines, ``#`` comments, an optional ``export`` prefix, quoted
    values (single or double), and trailing inline comments on unquoted values.
    """

    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    if "=" not in line:
        return None

    key, _, raw_value = line.partition("=")
    key = key.strip()
    if not key:
        return None
    return key, _unquote(raw_value.strip())


def _unquote(value: str) -> str:
    """Strip surrounding quotes, or a trailing inline comment when unquoted."""

    if value and value[0] in {'"', "'"}:
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end != -1 else value[1:]

    comment_index = value.find(" #")
    if comment_index != -1:
        value = value[:comment_index].rstrip()
    return value
