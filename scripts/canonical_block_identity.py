#!/usr/bin/env python3
"""Shared body-normalization, hashing, and extraction primitives for the
canonical CLAUDE.md block refresh mechanism.

``normalize_block_body`` is the **single normalization producer and
consumer both import** — the history-manifest generator
(``sync_canonical_blocks.py --write-history``) and the runtime classifier
(``refresh_claude_blocks.py``) must never each implement their own
whitespace handling. If the two ever diverge, a stale-but-unmodified block
misclassifies as locally customized (fails safe, but defeats the whole
refresh mechanism) — so any change to normalization semantics must be made
here, in one place, for both consumers to pick up.

Three primitives:

* ``normalize_block_body`` / ``hash_block_body`` — canonicalize a block's
  body text and hash it, so a block's on-disk shape (leading blank-line
  separator, trailing whitespace, extra trailing newlines) never affects
  its identity.
* ``REFRESHABLE_SLUGS`` — the closed set of block slugs eligible for
  refresh: the unconditional, byte-identical blocks. Conditional or
  template-filled blocks are excluded by membership, not by runtime
  classification.
* ``extract_live_body`` — pulls a block's live body out of a target
  CLAUDE.md by heading, bounded by the next top-level heading or EOF.
"""

from __future__ import annotations

import hashlib

REFRESHABLE_SLUGS: frozenset[str] = frozenset(
    {
        "agent-pipeline",
        "compaction-guidance",
        "behavioral-contract",
        "praxion-process",
    }
)

_SECTION_HEADING_PREFIX = "## "


def normalize_block_body(text: str) -> str:
    """Canonicalize a block body for identity comparison.

    Strips trailing whitespace from every line, drops leading and trailing
    blank lines, and collapses the result to exactly one trailing newline.
    Idempotent — normalizing an already-normalized body is a no-op.
    """
    lines = [line.rstrip() for line in text.splitlines()]

    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()

    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def hash_block_body(text: str) -> str:
    """Return the sha256 hex digest of the body's normalized form."""
    normalized = normalize_block_body(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_live_body(claude_md_text: str, heading: str) -> str | None:
    """Extract a block's live body from a target CLAUDE.md.

    ``heading`` is the literal heading line (e.g. ``"## Agent Pipeline"``).
    Extraction runs from the first line matching ``heading`` exactly through
    the next line starting with ``"## "`` (a top-level heading) or EOF.
    Returns ``None`` when the heading is absent. When the heading appears
    more than once, the first occurrence wins deterministically.
    """
    lines = claude_md_text.splitlines(keepends=True)

    start_index = next((i for i, line in enumerate(lines) if line.rstrip("\n") == heading), None)
    if start_index is None:
        return None

    end_index = next(
        (
            i
            for i in range(start_index + 1, len(lines))
            if lines[i].startswith(_SECTION_HEADING_PREFIX)
        ),
        len(lines),
    )
    return "".join(lines[start_index:end_index])
