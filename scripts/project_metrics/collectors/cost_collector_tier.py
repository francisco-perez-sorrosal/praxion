"""Cost collector -- the tier join: a pipeline slug to its calibration-log tier.

`parse_calibration_log` reads `.ai-state/calibration_log.md` into a
slug -> tier-tokens index; `resolve_tier` joins one slug against it. Slug ->
tier is not a function (a slug can carry several disagreeing rows), so the
join has three outcomes -- `TierResolved`, `TierAmbiguous`, `TierUnknown` --
and `_flatten_tier` renders each as the flat `(tier, tier_reason)` pair every
downstream table reads. Re-exported unchanged from `cost_collector`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# The calibration log is a pipe-table; columns are positional, matching
# `scripts/state_ledger_schema.py`'s own registration of this file.
_CALIBRATION_TASK_COLUMN = 1
_CALIBRATION_ACTUAL_TIER_COLUMN = 4
_CALIBRATION_MIN_COLUMNS = 5

_TIER_TOKEN_PATTERN = re.compile(r"[A-Za-z]+")
_KNOWN_TIERS = frozenset({"Direct", "Lightweight", "Standard", "Full", "Spike"})


@dataclass(frozen=True)
class TierResolved:
    """One row, or several agreeing rows, name the same tier."""

    tier: str
    rows: int


@dataclass(frozen=True)
class TierAmbiguous:
    """Several calibration rows for the same slug disagree on tier.

    A silent first-wins pick would fabricate a tier -- every disagreeing
    tier is listed, never just the first one seen.
    """

    tiers: list[str]
    rows: int


@dataclass(frozen=True)
class TierUnknown:
    """No calibration row joins this slug, or its tier cell does not parse."""

    reason: str


def _calibration_row_cells(line: str) -> list[str] | None:
    """Split one pipe-table line into stripped cells, or `None` when the
    line is not a table row at all."""

    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def parse_calibration_log(path: str) -> dict[str, list[str]]:
    """Build the slug -> tier-tokens index from `.ai-state/calibration_log.md`.

    The slug is the Task cell's first whitespace-delimited token (the only
    rule that holds uniformly across every observed row shape -- a
    sub-step qualifier after `/` or free prose after an em-dash both leave
    the pipeline slug as the leading token). The tier is the Actual Tier
    cell's leading alphabetic run, lower-cased comparisons never needed
    since the log itself capitalizes tier names consistently.
    """

    index: dict[str, list[str]] = {}
    # `errors="replace"` matches the WAL reader and the producing hook: one
    # bad byte degrades one cell, never the whole index.
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        cells = _calibration_row_cells(line)
        if cells is None or len(cells) < _CALIBRATION_MIN_COLUMNS:
            continue
        task_cell = cells[_CALIBRATION_TASK_COLUMN]
        if task_cell.lower() == "task" or set(task_cell) <= {"-"}:
            continue  # header or separator row
        tokens = task_cell.split()
        if not tokens:
            continue
        slug = tokens[0]
        match = _TIER_TOKEN_PATTERN.match(cells[_CALIBRATION_ACTUAL_TIER_COLUMN])
        if match is None:
            continue
        index.setdefault(slug, []).append(match.group(0))
    return index


def resolve_tier(
    slug: str, tier_index: dict[str, list[str]]
) -> TierResolved | TierAmbiguous | TierUnknown:
    """Join `slug` to a tier -- never a function, so three outcomes exist."""

    raw_tiers = tier_index.get(slug)
    if not raw_tiers:
        return TierUnknown(reason="no-calibration-row")

    known_tiers = [tier for tier in raw_tiers if tier in _KNOWN_TIERS]
    if not known_tiers:
        return TierUnknown(reason="unparsable-tier-cell")

    unique_tiers = sorted(set(known_tiers))
    if len(unique_tiers) == 1:
        return TierResolved(tier=unique_tiers[0], rows=len(known_tiers))
    return TierAmbiguous(tiers=unique_tiers, rows=len(known_tiers))


def _flatten_tier(resolution: TierResolved | TierAmbiguous | TierUnknown) -> tuple[str, str | None]:
    """Render a tier-join outcome as the flat `(tier, tier_reason)` pair every
    downstream consumer (buckets, tables, the Standard-vs-Lightweight cell) reads instead of the
    raw union."""

    if isinstance(resolution, TierResolved):
        return resolution.tier, None
    if isinstance(resolution, TierAmbiguous):
        return "ambiguous", ", ".join(resolution.tiers)
    return "unknown", resolution.reason
