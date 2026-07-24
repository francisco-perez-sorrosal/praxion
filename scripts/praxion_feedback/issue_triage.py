"""Mechanical §5.2 template validator and dedup-signature builder that gates
the fixer agent (SYSTEMS_PLAN.md § Architecture › Components, workflow step 6:
"Mechanical template-validate + dedup").

`parse_sections` / `missing_required_sections` / `extract_fingerprint` /
`dedup_signature` all run on the already-sanitized issue body -- deterministic
and judgment-free, entirely before any agent spend. The workflow step this
module backs is a cheap rejection filter in front of the LLM: a malformed or
duplicate issue must never reach the fixer.

`REQUIRED_SECTIONS` is every `render.SECTION_HEADINGS` entry except the two
machine-only sections (`Fingerprint`, `Capture Provenance`) -- populated by the
automated reporter CLI, never by a human filing manually in the browser (the
shipped issue template tells a manual filer to leave them blank). Deriving the
required set from `SECTION_HEADINGS` rather than a hand-typed parallel list
keeps the two in lock-step as render.py's schema evolves.

Reversal trigger: if human filings of log-less defects get false-rejected in
practice, move `Evidence Excerpt (sanitized)` to the tolerated-absent set.
"""

from __future__ import annotations

import hashlib
import re

from scripts.praxion_feedback.render import SECTION_HEADINGS

#: Machine-only §5.2 sections, tolerated-absent for a human filing.
_MACHINE_ONLY_SECTIONS = frozenset({"Fingerprint", "Capture Provenance"})

#: Every §5.2 heading a human filer must populate, in `SECTION_HEADINGS` order.
REQUIRED_SECTIONS = tuple(
    heading for heading in SECTION_HEADINGS if heading not in _MACHINE_ONLY_SECTIONS
)

# A `## <heading>` line; the heading text is trimmed by the caller rather than
# in the pattern, so trailing whitespace on the heading line can't make the
# match fail. Requires a space/tab right after "##" so a "### " sub-heading
# (three hashes) never matches as a top-level §5.2 section.
_SECTION_HEADING_RE = re.compile(r"^##[ \t]+(.+)$", re.MULTILINE)


def parse_sections(body: str) -> dict[str, str]:
    """Parse `body`'s `## <heading>` sections into heading -> stripped content.

    A heading absent from `body` is absent from the returned dict. The last
    matched heading's content runs to the end of the string (EOF-terminated) --
    there is no trailing `##` boundary to close it.
    """
    matches = list(_SECTION_HEADING_RE.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[heading] = body[start:end].strip()
    return sections


def missing_required_sections(body: str) -> tuple[str, ...]:
    """Return every required heading that is absent or blank in `body`.

    An empty tuple means the filing is template-valid. Machine-only sections
    (`Fingerprint`, `Capture Provenance`) are never checked here -- their
    absence never contributes to this result.
    """
    sections = parse_sections(body)
    return tuple(heading for heading in REQUIRED_SECTIONS if not sections.get(heading, ""))


def extract_fingerprint(body: str) -> str | None:
    """Return the parsed `Fingerprint` section content, or `None` if absent/blank."""
    fingerprint = parse_sections(body).get("Fingerprint", "")
    return fingerprint or None


def dedup_signature(body: str) -> str:
    """Return a stable dedup key for `body`.

    Prefers the parsed `Fingerprint` verbatim -- a machine-captured filing
    already carries a stable dedup key computed by `fingerprint.py` at capture
    time. Falls back to a deterministic hash of the raw body for a human
    filing with no `Fingerprint` section, so deduping still works without one.
    """
    fingerprint = extract_fingerprint(body)
    if fingerprint is not None:
        return fingerprint
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
