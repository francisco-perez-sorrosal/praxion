"""Fingerprints of the instruction text this change must move, never cut.

The frozen fixtures under `tests/acceptance/fixtures/kernel_pilot/` were taken
with these functions from the files as they stood before the change, so the
scenarios compare like with like without reading git history:

- every paragraph of every section of every rule, of the user-level template and
  of the project `CLAUDE.md` (a section is a heading's own text, up to the next
  heading of any level);
- which rules were always loaded (no `paths:` in their frontmatter);
- each Cursor export file's digest;
- the length of the host-native preamble;
- each pilot agent's definition with its universal-block lines and any
  `omitClaudeMd` line set aside.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import (
    PROJECT_INSTRUCTIONS,
    USER_TEMPLATE,
    frontmatter,
    markdown_sections,
    paragraphs,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kernel_pilot"
_DIRECTORY_GUIDES = {"README.md", "CLAUDE.md"}


def digest(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()[:16]


def instruction_sources(root: Path) -> list[str]:
    rules = sorted(
        str(p.relative_to(root))
        for p in (root / "rules").rglob("*.md")
        if p.name not in _DIRECTORY_GUIDES
    )
    return [*rules, USER_TEMPLATE, PROJECT_INSTRUCTIONS]


def always_loaded_rules(root: Path) -> list[str]:
    return [
        rel
        for rel in instruction_sources(root)
        if rel.startswith("rules/") and "paths" not in frontmatter((root / rel).read_text())
    ]


def section_fingerprints(text: str) -> dict[str, list[str]]:
    """Paragraph digests per section, keyed by heading and its occurrence."""
    seen: dict[str, int] = {}
    prints: dict[str, list[str]] = {}
    for section in markdown_sections(text):
        seen[section.heading] = seen.get(section.heading, 0) + 1
        key = f"{'#' * section.level} {section.heading} [{seen[section.heading]}]"
        prints[key] = [digest(p) for p in paragraphs(section.body, shortest=1)]
    return prints


def paragraph_digest(wording: str) -> str:
    """The digest a section fingerprint records for this one paragraph of text."""
    (paragraph,) = paragraphs(wording, shortest=1)
    return digest(paragraph)


def lost_paragraphs(root: Path, frozen: dict[str, dict[str, list[str]]]) -> list[str]:
    """Every frozen paragraph no longer present, word for word, in its own section."""
    lost = []
    for rel, sections in frozen.items():
        path = root / rel
        current = section_fingerprints(path.read_text()) if path.is_file() else {}
        for key, prints in sections.items():
            remaining = set(current.get(key, []))
            lost += [
                f"{rel} :: {key} :: paragraph {i + 1}"
                for i, p in enumerate(prints)
                if p not in remaining
            ]
    return lost


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _span_at(lines: list[str], index: int, span: list[str]) -> bool:
    """Whether `span` starts at `lines[index]`: whole lines, except the last one, matched by prefix.

    The last line of a block may carry a role's own sentence after the block's text (the
    discipline-consultant's self-test line does), so it is recognised by its prefix.
    """
    window = lines[index : index + len(span)]
    return len(window) == len(span) and window[:-1] == span[:-1] and window[-1].startswith(span[-1])


def definition_without_blocks(text: str, block_texts: list[str]) -> str:
    """An agent definition minus each universal block (a run of one or more lines) and the omitClaudeMd key.

    A block's last line is taken out by prefix, so a role sentence that follows the
    block's text on that line goes with it, as it did in the layout the fixtures froze.
    """
    lines = text.splitlines()
    for block in block_texts:
        span = block.splitlines()
        if not span:
            continue
        kept: list[str] = []
        index = 0
        while index < len(lines):
            if _span_at(lines, index, span):
                index += len(span)
            else:
                kept.append(lines[index])
                index += 1
        lines = kept
    return "\n".join(line for line in lines if not line.lstrip().startswith("omitClaudeMd:"))
