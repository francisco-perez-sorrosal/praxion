"""Spec parsing and amendment application for SYSTEMS_PLAN.md.

Parses the ``## Behavioral Specification`` section, extracting each
``### REQ-NN: Title`` block with its When/and/the system/so that body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SPEC_SECTION_RE = re.compile(r"^## Behavioral Specification\s*$", re.MULTILINE)
REQ_HEADING_RE = re.compile(r"^### (REQ-\d+):\s*(.+)$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^## ", re.MULTILINE)
NEXT_H3_RE = re.compile(r"^### ", re.MULTILINE)


@dataclass(frozen=True)
class ParsedReq:
    """A single requirement parsed from a behavioral specification."""

    req_id: str
    title: str
    full_text: str
    body: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ParsedSpec:
    """The full behavioral specification section."""

    requirements: list[ParsedReq]
    section_start: int
    section_end: int


def parse_spec(path: Path) -> ParsedSpec | None:
    """Parse the Behavioral Specification section from a SYSTEMS_PLAN.md file.

    Returns ``None`` when the file does not exist or has no
    ``## Behavioral Specification`` section.
    """
    if not path.is_file():
        return None

    content = path.read_text(encoding="utf-8")

    section_match = SPEC_SECTION_RE.search(content)
    if section_match is None:
        return None

    section_start = section_match.start()
    section_body_start = section_match.end()

    # Find where this section ends (next ## heading or EOF)
    next_h2 = NEXT_H2_RE.search(content, section_body_start)
    section_end = next_h2.start() if next_h2 else len(content)

    section_text = content[section_body_start:section_end]

    requirements = _parse_requirements(section_text, section_body_start)

    return ParsedSpec(
        requirements=requirements,
        section_start=section_start,
        section_end=section_end,
    )


def get_req_by_id(spec: ParsedSpec, req_id: str) -> ParsedReq | None:
    """Look up a single requirement by ID."""
    for req in spec.requirements:
        if req.req_id == req_id:
            return req
    return None


def apply_amendment(path: Path, req_id: str, new_full_text: str) -> bool:
    """Replace a single REQ block in-place in the file.

    Re-reads the file and re-locates the REQ by heading pattern to be
    resilient to edits between parse and apply.

    Returns ``True`` on success, ``False`` when the REQ is not found.
    """
    if not path.is_file():
        return False

    content = path.read_text(encoding="utf-8")

    # Find the spec section
    section_match = SPEC_SECTION_RE.search(content)
    if section_match is None:
        return False

    section_body_start = section_match.end()
    next_h2 = NEXT_H2_RE.search(content, section_body_start)
    section_end = next_h2.start() if next_h2 else len(content)

    # Find the target REQ heading within the section
    target_pattern = re.compile(rf"^### {re.escape(req_id)}:\s*.+$", re.MULTILINE)
    heading_match = target_pattern.search(content, section_body_start, section_end)
    if heading_match is None:
        return False

    req_start = heading_match.start()

    # Find where this REQ block ends: next ### heading or section end
    next_heading = NEXT_H3_RE.search(content, heading_match.end())
    if next_heading and next_heading.start() < section_end:
        req_end = next_heading.start()
    else:
        req_end = section_end

    # Ensure new_full_text ends with a newline for clean separation
    amended_text = new_full_text.rstrip() + "\n\n"

    new_content = content[:req_start] + amended_text + content[req_end:]
    path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_requirements(section_text: str, base_offset: int) -> list[ParsedReq]:
    """Parse all REQ blocks from the text of the Behavioral Specification section."""
    requirements: list[ParsedReq] = []

    headings = list(REQ_HEADING_RE.finditer(section_text))
    for i, match in enumerate(headings):
        req_id = match.group(1)
        title = match.group(2).strip()

        # Block extends from this heading to the next REQ heading (or section end)
        block_start = match.start()
        if i + 1 < len(headings):
            block_end = headings[i + 1].start()
        else:
            block_end = len(section_text)

        full_text = section_text[block_start:block_end].rstrip()
        body = section_text[match.end() : block_end].strip()

        requirements.append(
            ParsedReq(
                req_id=req_id,
                title=title,
                full_text=full_text,
                body=body,
                start_offset=base_offset + block_start,
                end_offset=base_offset + block_end,
            )
        )

    return requirements
