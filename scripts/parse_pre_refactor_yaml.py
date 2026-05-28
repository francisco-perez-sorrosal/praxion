"""Parse the structured YAML blocks inside a `PRE_REFACTOR_PLAN.md`.

The orchestrator's mediation contract needs a deterministic, fail-loud parser
for the `## Verifier Bypass Criteria` and `## Loop-Back Conditions` sections.
Each section must contain exactly one fenced ```yaml ... ``` block whose body
is a non-empty list — anything else is a structured error the orchestrator
surfaces back to the user.

Precedent: ``scripts/rework_manifest.py`` ships the same pattern (pure
functions, no I/O outside `parse`, stdlib + a single third-party dep).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

# The two sections the orchestrator's mechanical evaluator reads.
_BYPASS_HEADING = "## Verifier Bypass Criteria"
_LOOPBACK_HEADING = "## Loop-Back Conditions"

# Match a fenced ```yaml ... ``` block; capture the body.
_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)

ErrorId = Literal[
    "missing-section",
    "missing-yaml-block",
    "malformed-yaml",
    "empty-list",
]


@dataclass
class PreRefactorYamlError(Exception):
    """Structured error raised by :func:`parse` on any failure shape."""

    error_id: ErrorId
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.error_id}: {self.detail}" if self.detail else self.error_id


def parse(path: Path) -> dict[str, list]:
    """Parse a `PRE_REFACTOR_PLAN.md`, returning the two structured blocks.

    Returns ``{"bypass": [...], "loopback": [...]}`` on success.
    Raises :class:`PreRefactorYamlError` with one of the four ``error_id``
    values on any failure.
    """
    text = path.read_text(encoding="utf-8")
    return {
        "bypass": _parse_section(text, _BYPASS_HEADING),
        "loopback": _parse_section(text, _LOOPBACK_HEADING),
    }


def _parse_section(text: str, heading: str) -> list:
    """Extract the first ```yaml``` block in ``heading``'s section and parse it."""
    section_body = _extract_section(text, heading)
    if section_body is None:
        raise PreRefactorYamlError("missing-section", detail=heading)
    yaml_body = _extract_yaml_block(section_body)
    if yaml_body is None:
        raise PreRefactorYamlError("missing-yaml-block", detail=heading)
    parsed = _parse_yaml_block(yaml_body, where=heading)
    if not isinstance(parsed, list) or not parsed:
        raise PreRefactorYamlError("empty-list", detail=heading)
    return parsed


def _extract_section(text: str, heading: str) -> str | None:
    """Return the body of a level-2 section, or ``None`` if missing.

    The body runs from immediately after the heading line to the next
    level-2 heading (``## ``) or end-of-file.
    """
    pattern = re.compile(
        rf"^{re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def _extract_yaml_block(section_body: str) -> str | None:
    """Return the body of the first fenced ```yaml``` block, or ``None``."""
    match = _YAML_BLOCK_RE.search(section_body)
    return match.group(1) if match else None


def _parse_yaml_block(yaml_body: str, where: str) -> object:
    """Parse a YAML body string; raise the structured error on syntax failure."""
    try:
        return yaml.safe_load(yaml_body)
    except yaml.YAMLError as exc:
        raise PreRefactorYamlError("malformed-yaml", detail=f"{where}: {exc}") from exc
