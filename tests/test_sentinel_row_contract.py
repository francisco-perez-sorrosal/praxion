"""Reusable contract assertion for sentinel residual rows.

Binds `SYSTEMS_PLAN.md § The Extraction Contract`'s residual-row shape (Conditional ·
Invocation · Verdict map · Spec pointer, budget <=400 bytes) to a machine check, so an
extraction step cannot silently produce a row that violates its own contract. Each
extraction step (AC13, DH05, DL06, T03, F11, P03) calls `assert_residual_row_contract`
in its own test and appends its `(check_id, script_name)` pair to `EXTRACTED_CHECKS`
below, in the same commit that collapses its row into the four-part template.

`EXTRACTED_CHECKS` is append-only: entries are never removed or reordered, only added,
one per extraction step.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md§Pragmatism.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENTINEL_PATH = PROJECT_ROOT / "agents" / "sentinel.md"

# The contract's own budget: a row past this is a signal that discipline which should be
# a JSON field is still prose.
_MAX_ROW_BYTES = 400

_DIMENSION_HEADING = re.compile(r"^###\s+(.+)$", re.M)
_TABLE_ROW = re.compile(r"^\|\s*(?P<id>[A-Za-z0-9]+)\s*\|.*\|\s*$", re.M)


def _find_row(sentinel_text: str, check_id: str) -> str:
    """Return the full `| <check_id> | ... |` table-row line for `check_id`.

    Raises AssertionError (not a lookup failure) when absent -- a missing row is itself
    a contract violation, not a caller error.
    """
    for match in _TABLE_ROW.finditer(sentinel_text):
        if match.group("id") == check_id:
            return match.group(0)
    raise AssertionError(f"{check_id}: no `| {check_id} | ... |` row found in agents/sentinel.md")


def _dimension_heading_before(sentinel_text: str, row: str) -> str | None:
    """Return the nearest `### <dimension>` heading preceding `row`, or None if none precedes it."""
    offset = sentinel_text.index(row)
    headings = [m for m in _DIMENSION_HEADING.finditer(sentinel_text) if m.start() < offset]
    return headings[-1].group(1) if headings else None


def assert_residual_row_contract(sentinel_text: str, check_id: str, script_name: str) -> None:
    """Assert `check_id`'s row in `sentinel_text` satisfies the Extraction Contract's residual shape.

    Three checks, each binding a live consumer named in `SYSTEMS_PLAN.md § The Extraction
    Contract`: (a) the row sits under a `### <dimension>` heading and carries the literal
    `python3 scripts/<script_name>.py` invocation phrase -- the same phrase
    `_delegated_gates`, GL04 (`check_uninvoked_gate`) and GL05 (`check_ambient_import`) all
    key on; (b) the row names its canary sibling, `scripts/test_<script_name>.py`; (c) the
    row is at most 400 bytes.
    """
    row = _find_row(sentinel_text, check_id)

    dimension = _dimension_heading_before(sentinel_text, row)
    assert dimension is not None, f"{check_id}: row is not under any `### <dimension>` heading"

    invocation = f"python3 scripts/{script_name}.py"
    assert invocation in row, f"{check_id}: row is missing the literal `{invocation}` phrase"

    canary_ref = f"scripts/test_{script_name}.py"
    assert canary_ref in row, f"{check_id}: row is missing its canary pointer `{canary_ref}`"

    row_bytes = len(row.encode("utf-8"))
    assert row_bytes <= _MAX_ROW_BYTES, (
        f"{check_id}: row is {row_bytes} bytes, exceeds the {_MAX_ROW_BYTES}-byte budget "
        "(SYSTEMS_PLAN.md § The Extraction Contract) -- discipline that should be a JSON "
        "field is still prose"
    )


# ---------------------------------------------------------------------------
# Own canary: prove the helper actually bites, before anything depends on it
# ---------------------------------------------------------------------------


def test_row_missing_invocation_phrase_is_rejected() -> None:
    """Canary: a row that never names its script's invocation must fail the contract."""
    text = "### D\n\n| X01 | A | rule | Run something else. scripts/test_x.py, 400b budget |\n"
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row without the literal invocation phrase must fail")


def test_row_missing_canary_pointer_is_rejected() -> None:
    """Canary: a row that never names its canary sibling must fail the contract."""
    text = "### D\n\n| X01 | A | rule | Run `python3 scripts/x.py --json`. |\n"
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row without the canary pointer must fail")


def test_row_over_budget_is_rejected() -> None:
    """Canary: a row past the 400-byte budget must fail even with both phrases present."""
    padding = "x" * 500
    text = (
        f"### D\n\n| X01 | A | {padding} | Run `python3 scripts/x.py --json`. scripts/test_x.py |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row over the 400-byte budget must fail")


def test_row_outside_any_dimension_heading_is_rejected() -> None:
    """Canary: a row with no preceding `### <dimension>` heading must fail the contract."""
    text = "| X01 | A | rule | Run `python3 scripts/x.py --json`. scripts/test_x.py |\n"
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row with no preceding dimension heading must fail")


def test_well_formed_row_is_accepted() -> None:
    """Inverse guard: a row satisfying all three parts passes without raising."""
    text = "### D\n\n| X01 | A | rule | Run `python3 scripts/x.py --json`. scripts/test_x.py |\n"
    assert_residual_row_contract(text, "X01", "x")  # must not raise


# ---------------------------------------------------------------------------
# Extraction registry -- append-only. Each extraction of an `A`-typed sentinel check
# appends its own (check_id, script_name) pair here in the same commit that collapses
# its row into the four-part residual template.
# ---------------------------------------------------------------------------

EXTRACTED_CHECKS: list[tuple[str, str]] = []


def test_every_extracted_row_satisfies_the_contract() -> None:
    """Every row registered in `EXTRACTED_CHECKS` still satisfies the residual contract."""
    sentinel_text = SENTINEL_PATH.read_text(encoding="utf-8")
    for check_id, script_name in EXTRACTED_CHECKS:
        assert_residual_row_contract(sentinel_text, check_id, script_name)
