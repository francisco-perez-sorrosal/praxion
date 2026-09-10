"""Reusable contract assertion for sentinel residual rows.

Binds `SYSTEMS_PLAN.md § The Extraction Contract`'s residual-row shape (Conditional ·
Invocation · Verdict map · Spec pointer) to a machine check, so an extraction step
cannot silently produce a row that violates its own contract. Each extraction step
(AC13, DH05, DL06, T03, F11, P03) calls `assert_residual_row_contract` in its own test
and appends its `(check_id, script_name)` pair to `EXTRACTED_CHECKS` below, in the same
commit that collapses its row into the four-part template.

The budget binds the **verdict map** -- the Pass column with its three mandated
template parts (Conditional, Invocation, Spec pointer) stripped out -- at <=200 bytes,
not the Pass column as a whole: the template parts are fixed-format boilerplate whose
size tracks script-name length, not discipline, so a whole-column budget hands a
longer-named script arbitrarily more verdict-map room for a reason unconnected to
prose discipline. See `_verdict_map` for the extraction and the module-level comment
above `_VERDICT_MAP_MAX_BYTES` for the derivation.

`EXTRACTED_CHECKS` is append-only: entries are never removed or reordered, only added,
one per extraction step.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md§Pragmatism.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENTINEL_PATH = PROJECT_ROOT / "agents" / "sentinel.md"

# Derived, not fitted: the richest currently-extracted verdict map measures 108 bytes
# (DH05); 200 leaves headroom for a denser check (e.g. a seven-output-class classifier)
# while still representing a >=85% reduction against the smallest pre-extraction row
# (AC13, 1,481 bytes before extraction). See `test_every_extracted_row_satisfies_the_contract`
# for the measured margin on each live row.
_VERDICT_MAP_MAX_BYTES = 200

_DIMENSION_HEADING = re.compile(r"^###\s+(.+)$", re.M)
_TABLE_ROW = re.compile(r"^\|\s*(?P<id>[A-Za-z0-9]+)\s*\|.*\|\s*$", re.M)

# The three mandated template parts, in the order the Extraction Contract fixes them:
# an optional Conditional clause, a mandatory Invocation phrase, then (after the
# verdict map) a mandatory Spec pointer. Each is stripped from the Pass column in turn;
# what remains is the verdict map the byte budget actually polices.
_CONDITIONAL_RE = re.compile(r"^\s*Conditional on .*?\.\s")
_SPEC_POINTER_RE = re.compile(r"Spec \+ golden bad-cases:.*$")


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


def _pass_column(row: str) -> str:
    """Return the last (Pass/verdict) cell of a `| ID | Tp | Rule | Pass |` row.

    `_verdict_map` further strips this cell down to the part the byte budget actually
    binds. ID/Tp are trivially short and the Rule/claim column already carries its own
    separate <=120-char budget in the Extraction Contract's template, so this cell is
    the only place the mandated template parts and the verdict map they wrap can live.
    A literal `\\|` (e.g. a shell pipe inside a rule) is protected from the split.
    """
    protected = row.replace("\\|", "\x00")
    cells = [c.strip() for c in protected.strip().strip("|").split("|")]
    return cells[-1].replace("\x00", "\\|")


def _verdict_map(pass_column: str, check_id: str, script_name: str) -> str:
    """Strip the three mandated template parts from `pass_column`, returning the verdict map.

    The Conditional clause (optional) is stripped from the front if present; the
    Invocation phrase and the Spec pointer (both mandatory) are located by regex and
    removed. What remains is the verdict map -- the only part of the Pass column the
    200-byte budget polices.

    Raises AssertionError, not a silent skip, when the mandatory Invocation or Spec
    pointer cannot be located: a row whose mandated parts don't parse is exactly the
    drift this contract exists to catch, not a case to pass over.
    """
    residual = pass_column

    conditional_match = _CONDITIONAL_RE.match(residual)
    if conditional_match:
        residual = residual[conditional_match.end() :]

    invocation_re = re.compile(rf"Run `python3 scripts/{re.escape(script_name)}\.py[^`]*`\.")
    invocation_match = invocation_re.search(residual)
    assert invocation_match is not None, (
        f"{check_id}: cannot locate the mandatory `Run \\`python3 scripts/{script_name}.py "
        "...\\`.` invocation phrase in the mandated format -- the row is unparseable, not "
        "merely over budget"
    )
    residual = residual[: invocation_match.start()] + residual[invocation_match.end() :]

    spec_match = _SPEC_POINTER_RE.search(residual)
    assert spec_match is not None, (
        f"{check_id}: cannot locate the mandatory `Spec + golden bad-cases:` pointer -- "
        "the row is unparseable, not merely over budget"
    )
    residual = residual[: spec_match.start()] + residual[spec_match.end() :]

    return residual.strip()


def assert_residual_row_contract(sentinel_text: str, check_id: str, script_name: str) -> None:
    """Assert `check_id`'s row in `sentinel_text` satisfies the Extraction Contract's residual shape.

    Four checks, each binding a live consumer named in `SYSTEMS_PLAN.md § The Extraction
    Contract`: (a) the row sits under a `### <dimension>` heading and carries the literal
    `python3 scripts/<script_name>.py` invocation phrase -- the same phrase
    `_delegated_gates`, GL04 (`check_uninvoked_gate`) and GL05 (`check_ambient_import`) all
    key on; (b) the row names its canary sibling, `scripts/test_<script_name>.py`; (c) the
    verdict map -- the Pass column minus its three mandated template parts -- is at most
    200 bytes.
    """
    row = _find_row(sentinel_text, check_id)

    dimension = _dimension_heading_before(sentinel_text, row)
    assert dimension is not None, f"{check_id}: row is not under any `### <dimension>` heading"

    invocation = f"python3 scripts/{script_name}.py"
    assert invocation in row, f"{check_id}: row is missing the literal `{invocation}` phrase"

    canary_ref = f"scripts/test_{script_name}.py"
    assert canary_ref in row, f"{check_id}: row is missing its canary pointer `{canary_ref}`"

    verdict_map = _verdict_map(_pass_column(row), check_id, script_name)
    verdict_bytes = len(verdict_map.encode("utf-8"))
    assert verdict_bytes <= _VERDICT_MAP_MAX_BYTES, (
        f"{check_id}: verdict map is {verdict_bytes} bytes, exceeds the "
        f"{_VERDICT_MAP_MAX_BYTES}-byte budget (SYSTEMS_PLAN.md § The Extraction Contract) "
        "-- discipline that should be a JSON field is still prose"
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


# A well-formed Spec pointer tail, reused across fixtures below so each one differs only
# in the part it's testing.
_SPEC_TAIL = "Spec + golden bad-cases: `scripts/x.py` docstring; canary `scripts/test_x.py`."


def test_verdict_map_over_budget_is_rejected() -> None:
    """Canary: a verdict map past the 200-byte budget must fail, even with a well-formed,
    parseable Invocation and Spec pointer on either side of it.

    The padding sits in the verdict map, not the Rule column -- the budget is scoped to
    the part `_verdict_map` extracts, so padding the Rule column alone must not trip it
    (see the inverse guard below).
    """
    padding = "x" * 250
    text = (
        "### D\n\n"
        f"| X01 | A | rule | Run `python3 scripts/x.py --json`. {padding} scripts/test_x.py "
        f"{_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row with an over-budget verdict map must fail")


def test_padding_the_rule_column_alone_does_not_trip_the_budget() -> None:
    """Inverse guard: the 200-byte budget is scoped to the verdict map, not the whole row."""
    padding = "x" * 500
    text = (
        f"### D\n\n| X01 | A | {padding} | Run `python3 scripts/x.py --json`. "
        f"scripts/test_x.py {_SPEC_TAIL} |\n"
    )
    assert_residual_row_contract(text, "X01", "x")  # must not raise


def test_row_outside_any_dimension_heading_is_rejected() -> None:
    """Canary: a row with no preceding `### <dimension>` heading must fail the contract."""
    text = (
        f"| X01 | A | rule | Run `python3 scripts/x.py --json`. scripts/test_x.py {_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row with no preceding dimension heading must fail")


def test_well_formed_row_is_accepted() -> None:
    """Inverse guard: a row satisfying all mandated parts passes without raising."""
    text = (
        f"### D\n\n| X01 | A | rule | Run `python3 scripts/x.py --json`. verdict text here. "
        f"scripts/test_x.py {_SPEC_TAIL} |\n"
    )
    assert_residual_row_contract(text, "X01", "x")  # must not raise


def test_invocation_missing_mandated_format_is_rejected() -> None:
    """Canary: an invocation present as plain text -- satisfying the older literal-substring
    check -- but not wrapped in the mandated backtick + trailing-period format is
    unparseable by `_verdict_map`, and must fail rather than silently pass through.
    """
    text = (
        "### D\n\n"
        "| X01 | A | rule | Run python3 scripts/x.py --json without formatting; some verdict "
        f"text. scripts/test_x.py {_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("an invocation missing the mandated backtick format must fail")


def test_spec_pointer_missing_mandated_phrase_is_rejected() -> None:
    """Canary: a tail that satisfies the older canary-pointer literal check but never
    carries the literal `Spec + golden bad-cases:` phrase is unparseable by
    `_verdict_map`, and must fail rather than silently pass through.
    """
    text = (
        "### D\n\n"
        "| X01 | A | rule | Run `python3 scripts/x.py --json`. Some verdict text. See "
        "`scripts/x.py` docstring; canary scripts/test_x.py for details. |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row missing the mandated spec-pointer phrase must fail")


def test_totally_unparseable_pass_column_fails_not_skips() -> None:
    """Canary: a Pass column with no recognizable template structure at all must fail --
    not skip -- per `dec-378`'s "an unparseable row is exactly the drift this contract
    exists to catch" requirement, exercised on the degenerate no-structure case.
    """
    text = "### D\n\n| X01 | A | rule | Completely unrelated prose, no markers at all. |\n"
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a totally unparseable Pass column must fail, not silently pass")


# ---------------------------------------------------------------------------
# Extraction registry -- append-only. Each extraction of an `A`-typed sentinel check
# appends its own (check_id, script_name) pair here in the same commit that collapses
# its row into the four-part residual template.
# ---------------------------------------------------------------------------

EXTRACTED_CHECKS: list[tuple[str, str]] = [
    ("AC13", "check_architecture_projection"),
    ("DH05", "adr_health"),
    ("DL06", "check_adr_reciprocity"),
]


def test_every_extracted_row_satisfies_the_contract() -> None:
    """Every row registered in `EXTRACTED_CHECKS` still satisfies the residual contract."""
    sentinel_text = SENTINEL_PATH.read_text(encoding="utf-8")
    for check_id, script_name in EXTRACTED_CHECKS:
        assert_residual_row_contract(sentinel_text, check_id, script_name)
