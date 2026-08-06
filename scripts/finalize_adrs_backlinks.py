"""Re-affirmation reciprocity for the ADR finalize protocol.

Owns one responsibility: the `re_affirms` / `re_affirmed_by` edge is
bidirectional by convention but only one half of it is written by hand -- the
re-affirming ADR names its target, the target rarely names it back. This
module self-heals the missing back-link when the re-affirming draft is
promoted, so the corpus never carries a one-way edge.

Kept apart from `finalize_adrs_crossrefs`: that module rewrites an id the
promotion *changed*, while this one adds an edge the promotion *revealed*.
Both touch sibling ADRs; they answer different questions.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import exists only for type checkers
    from finalize_adrs import DraftPlan

logger = logging.getLogger("finalize_adrs")

FRONTMATTER_RE_AFFIRMS_PATTERN = re.compile(r"^re_affirms:\s*(dec-\d+)\s*$", re.MULTILINE)
_REAFFIRMED_BY_FIELD_PATTERN = re.compile(r"^re_affirmed_by:\s*(.*)$")
_REAFFIRMED_BY_INLINE_PATTERN = re.compile(r"^\[(.*)\]$")
_REAFFIRMED_BY_ITEM_PATTERN = re.compile(r"^\s*-\s*(dec-\d+)\s*$")
_REAFFIRMED_BY_SCALAR_PATTERN = re.compile(r"^dec-\d+$")


def backfill_re_affirmed_by(decisions_dir: Path, plans: list[DraftPlan]) -> int:
    """Self-heal the reciprocal `re_affirmed_by` back-link (dec-070/DL06).

    For every newly finalized ADR whose frontmatter names `re_affirms:
    dec-NNN`, ensures the target ADR's `re_affirmed_by` list contains the new
    id -- backfilling it when missing. Returns the number of backfills.
    """
    backfilled = 0
    for plan in plans:
        match = FRONTMATTER_RE_AFFIRMS_PATTERN.search(plan.new_path.read_text(encoding="utf-8"))
        if match is None:
            continue
        target_id = match.group(1)
        candidates = list(decisions_dir.glob(f"{target_id.removeprefix('dec-')}-*.md"))
        if len(candidates) != 1:
            logger.warning(
                "finalize_adrs: %s re_affirms %s but target ADR not found; skipping backfill",
                plan.new_id,
                target_id,
            )
            continue
        if _ensure_re_affirmed_by_link(candidates[0], plan.new_id):
            backfilled += 1
            logger.info("backfilled re_affirmed_by: %s -> %s", target_id, plan.new_id)
    return backfilled


def _frontmatter_end_index(lines: list[str]) -> int | None:
    """Index of the closing `---`, or None when the frontmatter is not well formed.

    Well formed means an opening `---` on the first line and a closing one
    below it. Both halves matter and neither can be assumed: a file whose
    frontmatter was never closed (truncated, or mid-write) has no end to find,
    and a file with no *opening* delimiter has a first `---` that is a body
    horizontal rule -- inserting frontmatter fields above it would write YAML
    into prose. This is a corpus a git hook meets unattended, so an ADR-shaped
    filename is not proof of an ADR-shaped file.
    """
    if not lines or lines[0].rstrip("\n") != "---":
        return None
    return next((i for i in range(1, len(lines)) if lines[i].rstrip("\n") == "---"), None)


def _append_to_inline_value(
    path: Path, lines: list[str], field_idx: int, inline_value: str, new_id: str
) -> bool:
    """Append `new_id` to an inline `re_affirmed_by` value; True if written.

    Handles the malformed-but-unambiguous scalar (`re_affirmed_by: dec-090`)
    by coercing it to the list the convention specifies. Coercion rather than a
    skip because the two are not symmetric: adding a second id requires a list
    either way, so declining leaves the field just as malformed *and* drops the
    back-link this module exists to write. A value that is neither a list nor a
    single id is not interpretable, so that one is skipped -- never rewrite a
    field whose current content cannot be read.
    """
    inline_match = _REAFFIRMED_BY_INLINE_PATTERN.match(inline_value)
    if inline_match is not None:
        items = [x.strip() for x in inline_match.group(1).split(",") if x.strip()]
    elif _REAFFIRMED_BY_SCALAR_PATTERN.match(inline_value):
        logger.warning(
            "finalize_adrs: %s has a scalar re_affirmed_by (%s) where the "
            "convention specifies a list; coercing to a list to add %s",
            path,
            inline_value,
            new_id,
        )
        items = [inline_value]
    else:
        logger.warning(
            "finalize_adrs: %s has an unreadable re_affirmed_by value (%s); "
            "skipping back-link to %s -- fix the field and re-run finalize",
            path,
            inline_value,
            new_id,
        )
        return False

    if new_id in items:
        return False
    lines[field_idx] = f"re_affirmed_by: [{', '.join([*items, new_id])}]\n"
    path.write_text("".join(lines), encoding="utf-8")
    return True


def _ensure_re_affirmed_by_link(path: Path, new_id: str) -> bool:
    """Ensure `path`'s frontmatter `re_affirmed_by` list contains `new_id`.

    Creates the field (block-list style) if absent; appends without
    duplicating if present, in either block-list or inline-list style.
    Returns True if the file was modified.

    Malformed input is skipped with a warning rather than raised: this runs
    inside a non-blocking git hook, *after* promotion and cross-reference
    rewriting have already written to disk, so an exception here abandons the
    remaining back-links and the index regeneration that follows -- leaving a
    stale DECISIONS_INDEX.md behind a corpus that has already moved.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    end_idx = _frontmatter_end_index(lines)
    if end_idx is None:
        logger.warning(
            "finalize_adrs: %s has no well-formed frontmatter; skipping "
            "re_affirmed_by back-link to %s -- fix the file and re-run finalize",
            path,
            new_id,
        )
        return False
    field_idx = next(
        (i for i in range(1, end_idx) if _REAFFIRMED_BY_FIELD_PATTERN.match(lines[i])), None
    )

    if field_idx is None:
        lines[end_idx:end_idx] = ["re_affirmed_by:\n", f"  - {new_id}\n"]
        path.write_text("".join(lines), encoding="utf-8")
        return True

    inline_value = _REAFFIRMED_BY_FIELD_PATTERN.match(lines[field_idx]).group(1).strip()
    if inline_value:
        return _append_to_inline_value(path, lines, field_idx, inline_value, new_id)

    block_end = field_idx + 1
    existing = []
    while block_end < end_idx:
        item_match = _REAFFIRMED_BY_ITEM_PATTERN.match(lines[block_end])
        if not item_match:
            break
        existing.append(item_match.group(1))
        block_end += 1
    if new_id in existing:
        return False
    lines.insert(block_end, f"  - {new_id}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return True
