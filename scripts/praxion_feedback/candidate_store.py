"""The PENDING.md candidate store: append / dedup / list / mark-filed.

`PENDING.md` is per managed project and git-committed, so it doubles as the
managed-side dedup memory. One `### <fp8>` block per candidate holds the full
fingerprint, the §5.2 field lines, a fenced evidence excerpt, and a `status`
(`pending | filed | dismissed`).

`append_candidate` owns the full dedup contract: it computes the fingerprint
itself from the raw `category`/`artifact_path`/`error` fields via
`fingerprint.compute_fingerprint`, then skips the append (no-op, returns None)
when that fingerprint already appears in either PENDING.md or UPSTREAM_ISSUES.md.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.praxion_feedback.fingerprint import compute_fingerprint

_SHORT_FINGERPRINT_LEN = 8

_PREAMBLE = (
    "# Pending Praxion Feedback\n\n"
    "Candidate ecosystem-defect reports awaiting `/report-praxion-issue`. "
    "This file is git-committed and mechanically sanitized at capture time.\n\n"
)

# Ordered §5.2 field lines carried straight into the stored block. `error` is
# excluded here -- it is written into a fenced block since it may be multiline.
_FIELD_ORDER = (
    "category",
    "artifact_path",
    "detected_by",
    "detection_point",
    "confidence",
    "expected",
    "observed",
    "reproduction_command",
    "environment",
    "regression_status",
)

# One candidate block: a "### " header through everything up to the next header
# or end-of-file.
_BLOCK_RE = re.compile(r"^### .*?(?=^### |\Z)", re.MULTILINE | re.DOTALL)
_FIELD_LINE_RE = re.compile(r"^- (\w+): (.*)$", re.MULTILINE)
_EVIDENCE_FENCE_RE = re.compile(r"```\n(.*?)\n```", re.DOTALL)

_PENDING_STATUS = "- status: pending"
_FILED_STATUS = "- status: filed"


def _format_block(fingerprint: str, fields: dict) -> str:
    lines = [f"### {fingerprint[:_SHORT_FINGERPRINT_LEN]}", "", f"- fingerprint: {fingerprint}"]
    lines.extend(f"- {key}: {fields.get(key, '')}" for key in _FIELD_ORDER)
    lines.append(_PENDING_STATUS)
    lines.extend(["", "```", str(fields.get("error", "")), "```", ""])
    return "\n".join(lines) + "\n"


def _is_duplicate(fingerprint: str, pending: Path, upstream: Path) -> bool:
    for path in (pending, upstream):
        if path.exists() and fingerprint in path.read_text():
            return True
    return False


def _append_block(pending: Path, block: str) -> None:
    if not pending.exists():
        pending.write_text(_PREAMBLE + block)
        return
    existing = pending.read_text()
    separator = "" if existing.endswith("\n") else "\n"
    pending.write_text(existing + separator + block)


def append_candidate(pending: Path, upstream: Path, fields: dict) -> str | None:
    """Append a fingerprinted candidate block; return its fingerprint or None.

    Returns None (no append) when the computed fingerprint already appears in
    PENDING.md or UPSTREAM_ISSUES.md -- one defect maps to at most one candidate.
    """
    fingerprint = compute_fingerprint(fields["category"], fields["artifact_path"], fields["error"])
    if _is_duplicate(fingerprint, pending, upstream):
        return None
    _append_block(pending, _format_block(fingerprint, fields))
    return fingerprint


def _parse_block(block: str) -> dict:
    data: dict[str, str] = dict(_FIELD_LINE_RE.findall(block))
    fence = _EVIDENCE_FENCE_RE.search(block)
    if fence is not None:
        data["error"] = fence.group(1)
        data.setdefault("evidence_excerpt", fence.group(1))
    return data


def list_pending(pending: Path) -> list[dict]:
    """Return the parsed field dicts of every still-`pending` candidate."""
    if not pending.exists():
        return []
    text = pending.read_text()
    return [
        parsed
        for block in _BLOCK_RE.findall(text)
        if (parsed := _parse_block(block)).get("status") == "pending"
    ]


def mark_filed(pending: Path, fingerprint: str, issue_url: str) -> None:
    """Flip the target candidate to `filed` with its issue URL, siblings intact."""
    if not pending.exists():
        return
    short = fingerprint[:_SHORT_FINGERPRINT_LEN]

    def _flip(match: re.Match[str]) -> str:
        block = match.group(0)
        if f"### {short}" not in block and fingerprint not in block:
            return block
        block = block.replace(_PENDING_STATUS, _FILED_STATUS)
        if "- issue_url:" not in block:
            block = block.replace(_FILED_STATUS, f"{_FILED_STATUS}\n- issue_url: {issue_url}")
        return block

    pending.write_text(_BLOCK_RE.sub(_flip, pending.read_text()))
