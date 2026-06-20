"""Tolerant YAML loader for per-project principles (`.ai-state/principles.yaml`).

Public API
----------
load_principles(principles_yaml_path: Path) -> list[dict]
    Returns a list of normalized principle dicts.  Never raises — absent, empty,
    or malformed input yields an empty list (or a list containing only a
    ``kind="malformed-yaml"`` note-dict that callers may use for logging).

scope_matches(scope: str | list[str], changed_files: list[str]) -> bool
    ``fnmatch``-based applicability check.  ``"*"`` matches any non-empty file
    list; a list of globs returns True when any glob matches any changed file.

The functions are pure and side-effect-free: no writes, no global state.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = frozenset({"advisory", "blocking"})
_DEFAULT_SEVERITY = "advisory"
_DEFAULT_SCOPE = "*"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_principles(principles_yaml_path: Path) -> list[dict]:
    """Load and normalize principles from a YAML file.

    Tolerant parser — absent, empty, or malformed input never raises.

    Parameters
    ----------
    principles_yaml_path:
        Path to the principles YAML file (typically
        ``.ai-state/principles.yaml``).

    Returns
    -------
    list[dict]
        Normalized principle dicts.  Each dict has:
        - ``id``: str
        - ``statement``: str
        - ``severity``: ``"advisory"`` | ``"blocking"``
        - ``scope``: str | list[str]  (default ``"*"`` when absent)
        - ``rationale``: str | None
        - ``_coerced_severity``: bool  (True if original value was unrecognised)

        Absent / empty file → ``[]``.
        Malformed YAML → ``[]`` plus one note-dict with
        ``kind="malformed-yaml"`` (callers may inspect but must not depend on
        its presence).
    """
    if not principles_yaml_path.exists():
        return []

    try:
        raw = principles_yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception:  # noqa: BLE001 — catch all load errors; fail-safe contract
        return [_malformed_note(principles_yaml_path)]

    if not data:
        return []

    raw_principles = data.get("principles") if isinstance(data, dict) else None
    if not raw_principles:
        return []

    return [_normalize(p) for p in raw_principles if isinstance(p, dict)]


def scope_matches(scope: str | list[str], changed_files: list[str]) -> bool:
    """Return True when *scope* applies to at least one of *changed_files*.

    Parameters
    ----------
    scope:
        A single glob string (``"*"`` = project-wide) or a list of globs.
    changed_files:
        Paths of files changed in the current diff.

    Returns
    -------
    bool
        True if any glob in *scope* matches any path in *changed_files*.
        False when *changed_files* is empty.
    """
    if not changed_files:
        return False

    globs = [scope] if isinstance(scope, str) else list(scope)

    for pattern in globs:
        if pattern == "*":
            return True
        for path in changed_files:
            if fnmatch.fnmatch(path, pattern):
                return True

    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize(raw: dict[str, Any]) -> dict:
    """Normalize a raw principle dict to the output contract shape."""
    severity_raw = raw.get("severity", _DEFAULT_SEVERITY)
    if severity_raw in _VALID_SEVERITIES:
        severity = severity_raw
        coerced = False
    else:
        severity = _DEFAULT_SEVERITY
        coerced = True

    return {
        "id": str(raw.get("id", "")),
        "statement": str(raw.get("statement", "")),
        "severity": severity,
        "scope": raw.get("scope", _DEFAULT_SCOPE),
        "rationale": raw.get("rationale") or None,
        "_coerced_severity": coerced,
    }


def _malformed_note(path: Path) -> dict:
    """Return a note-dict callers may use to log a malformed file."""
    return {
        "kind": "malformed-yaml",
        "message": f"Could not parse principles YAML at {path}; treating as absent.",
    }
