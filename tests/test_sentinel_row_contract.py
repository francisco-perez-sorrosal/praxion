"""Reusable contract assertion for sentinel residual rows.

Binds `SYSTEMS_PLAN.md § The Extraction Contract`'s residual-row shape (Conditional ·
Invocation · Verdict map · Spec pointer) to a machine check, so an extraction step
cannot silently produce a row that violates its own contract. Each extraction step
(AC13, DH05, DL06, T03, F11, P03) calls `assert_residual_row_contract` in its own test
and appends its `(check_id, script_name)` pair to `EXTRACTED_CHECKS` below, in the same
commit that collapses its row into the four-part template.

The budget binds the **verdict map** -- the Pass column with its three mandated
template parts (Conditional, Invocation, Spec pointer) parsed out, in their mandated
order, with nothing left over -- at <=300 bytes, not the Pass column as a whole: the
template parts are fixed-format boilerplate whose size tracks script-name length, not
discipline, so a whole-column budget hands a longer-named script arbitrarily more
verdict-map room for a reason unconnected to prose discipline.

`_verdict_map` parses rather than strips: the whole Pass column is matched in one
`re.fullmatch` against the ordered four-part shape, so any content that isn't part of
a recognized part -- trailing prose after the Spec pointer, a reordered part, a fifth
part -- fails the match instead of silently defaulting to zero. See `_row_pattern` for
the shape and the module-level comment above `_VERDICT_MAP_MAX_BYTES` for the budget's
derivation.

A verdict-map budget alone does not close the row: the two mandated template parts that
wrap it -- the Conditional's path slot and the Invocation's backtick span -- are each
themselves explicitly bounded (`_CONDITIONAL_PATH_MAX_CHARS`, `_INVOCATION_FLAGS_MAX_CHARS`),
so padding cannot grow the row by riding inside a part the verdict-map budget doesn't
measure. The Rule/claim cell carries its own separate `_RULE_MAX_CHARS` budget, asserted
directly rather than left as unenforced prose.

`EXTRACTED_CHECKS` is append-only: entries are never removed or reordered, only added,
one per extraction step.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md§Pragmatism.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENTINEL_PATH = PROJECT_ROOT / "agents" / "sentinel.md"

# Derived from a template-conforming measurement of the three live rows plus a
# realistic verdict map for the largest check still to be extracted (P03, seven output
# classes: WARN, three `info.*` counts, and `unmatched_stops` split three ways) --
# not fitted to whichever row happens to pass. Measured: AC13 103 b, DH05 108 b,
# DL06 67 b (all folded-sentence-conditional, the template this file's canaries now
# enforce). The budget is **UTF-8 bytes**, not characters: the assertion measures
# `len(verdict_map.encode("utf-8"))`. AC13 is the row where these differ -- 101
# characters, 103 bytes, on one em-dash. Every other extracted row is ASCII, so a
# `len()` on the str agrees there and silently disagrees on AC13. All six rows, in
# bytes: AC13 103, DH05 108, DL06 67, F11 247, T03 253, P03 265 -- all /300. A terse but faithful seven-class P03 verdict map -- naming the `agent_id`/
# `agent_type`/`session_id` fields the check's own golden bad-case requires on its WARN,
# plus the three `info.*` counts and the three `unmatched_stops` sub-keys, all as
# backticked JSON keys -- measures 227 b; 200 b (the prior ceiling) falls 27 b short of
# it. 300 b clears that estimate with 73 b (32%) of margin and is still a 5.6x
# (95.6%) reduction against P03's own pre-extraction size (6,837 b) and a 4.9x (79.7%)
# reduction against the smallest pre-extraction row (AC13, 1,481 b) -- decisively
# distinct from the 1,481-6,804-byte range these rows started in. (The "reduction
# against 1,481 b" framing alone does not discriminate: it stays true all the way up
# to 222 b, so it is cited here for context, not as the derivation's basis.)
_VERDICT_MAP_MAX_BYTES = 300

_DIMENSION_HEADING = re.compile(r"^###\s+(.+)$", re.M)
_TABLE_ROW = re.compile(r"^\|\s*(?P<id>[A-Za-z0-9]+)\s*\|.*\|\s*$", re.M)

# The Conditional's fixed shape -- a single sentence, `Conditional on <path> present`,
# optionally qualified by a parenthetical (e.g. "(either lifecycle stage)"), then
# `; skip with a(n) <D>-dimension INFO note.` -- per the folded-sentence template
# `SYSTEMS_PLAN.md § The Extraction Contract` now specifies (amended in this commit to
# match the three live rows, which never wrote the split two-sentence form). An open
# `.+? present` anchor is *not* a bound: a non-greedy quantifier still backtracks past
# arbitrary padding to find a later "present", so the path slot needs its own explicit
# ceiling, not just a closing phrase to search for -- see `_CONDITIONAL_PATH_MAX_CHARS`
# and `_row_pattern`.
_CONDITIONAL_PATH_MAX_CHARS = 80  # widest live path slot is DH05's two joined paths (50
# chars: "`.ai-state/decisions/` and `scripts/adr_health.py`"); other live rows: AC13 37,
# DL06 22, F11 29, P03 30. 80 leaves room for a realistic second joined path without
# leaving room for padding (SYSTEMS_PLAN.md's template joins at most two backticked paths
# with "and").
_CONDITIONAL_SHAPE = (
    rf"Conditional on .{{1,{_CONDITIONAL_PATH_MAX_CHARS}}}? present(?: \([^)]*\))?; "
    r"skip with an? [A-Za-z]+-dimension INFO note\.\s*"
)


_INVOCATION_FLAGS_MAX_CHARS = 20  # every live invocation carries exactly " --json" (7
# chars); 20 leaves room for a second short flag (e.g. " --json --strict") without
# leaving room for padding riding the open `[^\`]*` span a prior version of this pattern
# used.


def _row_pattern(script_name: str) -> re.Pattern[str]:
    """Build the whole-Pass-column parser for a row naming `script_name`.

    Anchored (via `fullmatch`, not `search`) to consume the entire column: an optional
    Conditional, the mandatory Invocation, the verdict map (captured -- its length is
    measured after the match, not constrained by the regex), then the mandatory Spec
    pointer, and nothing else. This is what turns "content the four-part template
    doesn't account for" into a parse failure instead of the open-ended `.*$` strip
    silently discarding it (dec-378's own "fails, not skips" property, extended from
    the mandatory parts to the column as a whole).
    """
    escaped = re.escape(script_name)
    invocation = rf"Run `python3 scripts/{escaped}\.py[^`]{{0,{_INVOCATION_FLAGS_MAX_CHARS}}}`\."
    spec_pointer = (
        rf"Spec \+ golden bad-cases: `scripts/{escaped}\.py` docstring; "
        rf"canary `scripts/test_{escaped}\.py`\."
    )
    return re.compile(
        rf"(?:{_CONDITIONAL_SHAPE})?{invocation}\s*(?P<verdict>.*?)\s*{spec_pointer}",
        re.DOTALL,
    )


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


def _row_cells(row: str) -> list[str]:
    """Split a `| ID | Tp | Rule | Pass |` row into its four cells.

    A literal `\\|` (e.g. a shell pipe inside a rule) is protected from the split.
    """
    protected = row.replace("\\|", "\x00")
    return [c.strip().replace("\x00", "\\|") for c in protected.strip().strip("|").split("|")]


def _pass_column(row: str) -> str:
    """Return the last (Pass/verdict) cell of `row`.

    `_verdict_map` further parses this cell down to the part the byte budget actually
    binds. ID/Tp are trivially short; the Rule/claim cell is checked separately by
    `assert_residual_row_contract` against `_RULE_MAX_CHARS`, so this cell is the only
    place the mandated template parts and the verdict map they wrap can live.
    """
    return _row_cells(row)[-1]


_RULE_MAX_CHARS = 120  # `SYSTEMS_PLAN.md § The Extraction Contract`'s residual row
# template: "<one-line claim, <=120 chars, unchanged from today>". Measured in
# characters, per the template's own wording -- unlike the verdict map, no live row sits
# close enough to the boundary for the chars-vs-bytes distinction to matter (widest live
# Rule column: P03 113 chars/bytes).


def _rule_column(row: str) -> str:
    """Return the third (Rule/claim) cell of `row`."""
    return _row_cells(row)[2]


def _verdict_map(pass_column: str, check_id: str, script_name: str) -> str:
    """Parse `pass_column` against the ordered four-part template, returning the verdict map.

    `re.fullmatch` demands the *entire* column decompose into Conditional? + Invocation
    + verdict map + Spec pointer, in that order, with nothing left over. Anything the
    parse cannot assign to a named part -- a missing mandatory part, parts out of
    order, or trailing content after the Spec pointer -- raises AssertionError instead
    of silently discarding it: an unparseable row is exactly the drift this contract
    exists to catch, not a case to pass over.
    """
    match = _row_pattern(script_name).fullmatch(pass_column)
    assert match is not None, (
        f"{check_id}: Pass column does not decompose into the mandated "
        "Conditional? + Invocation + verdict map + Spec pointer shape, in that exact "
        "order, with no content left over (SYSTEMS_PLAN.md § The Extraction Contract)"
    )
    return match.group("verdict").strip()


def assert_residual_row_contract(sentinel_text: str, check_id: str, script_name: str) -> None:
    """Assert `check_id`'s row in `sentinel_text` satisfies the Extraction Contract's residual shape.

    Five checks, each binding a live consumer named in `SYSTEMS_PLAN.md § The Extraction
    Contract`: (a) the row sits under a `### <dimension>` heading and carries the literal
    `python3 scripts/<script_name>.py` invocation phrase -- the same phrase
    `_delegated_gates`, GL04 (`check_uninvoked_gate`) and GL05 (`check_ambient_import`) all
    key on; (b) the row names its canary sibling, `scripts/test_<script_name>.py`; (c) the
    Rule/claim cell is at most `_RULE_MAX_CHARS`; (d) the verdict map -- the Pass column
    parsed down to its non-template residue -- is at most `_VERDICT_MAP_MAX_BYTES`.
    """
    row = _find_row(sentinel_text, check_id)

    dimension = _dimension_heading_before(sentinel_text, row)
    assert dimension is not None, f"{check_id}: row is not under any `### <dimension>` heading"

    invocation = f"python3 scripts/{script_name}.py"
    assert invocation in row, f"{check_id}: row is missing the literal `{invocation}` phrase"

    canary_ref = f"scripts/test_{script_name}.py"
    assert canary_ref in row, f"{check_id}: row is missing its canary pointer `{canary_ref}`"

    rule = _rule_column(row)
    assert len(rule) <= _RULE_MAX_CHARS, (
        f"{check_id}: Rule column is {len(rule)} chars, exceeds the {_RULE_MAX_CHARS}-char "
        "budget (SYSTEMS_PLAN.md § The Extraction Contract's residual row template)"
    )

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
    text = "### D\n\n| X01 | A | rule | Run something else. scripts/test_x.py, no invocation |\n"
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
    """Canary: a verdict map past the budget must fail, even with a well-formed,
    parseable Invocation and Spec pointer on either side of it.

    The padding sits in the verdict map, not the Rule column -- the budget is scoped to
    the part `_verdict_map` extracts, so a Rule column at its own legal maximum must not
    trip it (see the inverse guard below).
    """
    padding = "x" * 320
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


def test_full_length_rule_column_does_not_trip_the_verdict_map_budget() -> None:
    """Inverse guard: a Rule column at its own legal maximum (`_RULE_MAX_CHARS`) does not
    leak into the verdict-map budget -- the two budgets are scoped to different cells,
    not summed.
    """
    rule = "x" * _RULE_MAX_CHARS
    text = (
        f"### D\n\n| X01 | A | {rule} | Run `python3 scripts/x.py --json`. verdict text. "
        f"{_SPEC_TAIL} |\n"
    )
    assert_residual_row_contract(text, "X01", "x")  # must not raise


def test_rule_column_over_budget_is_rejected() -> None:
    """Canary (FAIL-2, Rule-column probe): a Rule/claim cell past `_RULE_MAX_CHARS` must
    fail. Previously unenforced -- the <=120-char budget existed only as prose in
    `SYSTEMS_PLAN.md:130`, and 1,500 bytes parked here was ACCEPTED.
    """
    padding = "x" * 500
    text = (
        f"### D\n\n| X01 | A | {padding} | Run `python3 scripts/x.py --json`. verdict text. "
        f"{_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError as exc:
        if "Rule column" not in str(exc):
            raise AssertionError(f"expected the Rule-column message, got: {exc}") from exc
        return
    raise AssertionError("a Rule column past the char budget must fail")


def test_conditional_path_over_budget_is_rejected() -> None:
    """Canary (FAIL-2, Conditional probe): a path slot past `_CONDITIONAL_PATH_MAX_CHARS`
    must fail the parse. The prior open `.+? present` anchor backtracked past arbitrary
    padding to find a later "present" and was ACCEPTED at 900 bytes; the explicit char
    ceiling turns that into a parse failure instead.
    """
    padding = "x" * 900
    text = (
        "### D\n\n"
        f"| X01 | A | rule | Conditional on {padding} present; skip with a D-dimension "
        f"INFO note. Run `python3 scripts/x.py --json`. verdict text here. {_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError as exc:
        if "does not decompose" not in str(exc):
            raise AssertionError(f"expected the parse-failure message, got: {exc}") from exc
        return
    raise AssertionError("a Conditional path past the char budget must fail")


def test_invocation_flags_over_budget_is_rejected() -> None:
    """Canary (FAIL-2, Invocation probe): a backtick span past
    `_INVOCATION_FLAGS_MAX_CHARS` must fail the parse. The prior open `[^\\`]*` span was
    ACCEPTED at 700 bytes; the explicit char ceiling turns that into a parse failure
    instead.
    """
    padding = "x" * 700
    text = (
        "### D\n\n"
        f"| X01 | A | rule | Run `python3 scripts/x.py --json {padding}`. verdict text here. "
        f"{_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError as exc:
        if "does not decompose" not in str(exc):
            raise AssertionError(f"expected the parse-failure message, got: {exc}") from exc
        return
    raise AssertionError("an Invocation backtick span past the char budget must fail")


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


def test_conditional_folded_sentence_is_accepted() -> None:
    """Inverse guard: the folded single-sentence Conditional the three live rows actually
    write -- `Conditional on <path> present; skip with a <D>-dimension INFO note.` --
    parses cleanly and contributes nothing to the verdict map.
    """
    text = (
        "### D\n\n"
        "| X01 | A | rule | Conditional on `some/path` present; skip with a D-dimension "
        f"INFO note. Run `python3 scripts/x.py --json`. verdict text here. {_SPEC_TAIL} |\n"
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


def test_content_after_spec_pointer_is_rejected() -> None:
    """Canary (dec-378, closes the FAIL-1 shape a prior `.*$` strip let through): prose
    parked *after* the mandated Spec pointer -- naturally arising, e.g., from an author
    extending the pointer with extra guidance -- must fail the contract, not vanish into
    an unbounded strip. `re.fullmatch` cannot match with a non-empty tail, so this is
    exactly the escape a whole-column parse closes that a to-end-of-string strip left
    open.
    """
    trailing_prose = "x" * 800
    text = (
        "### D\n\n"
        f"| X01 | A | rule | Run `python3 scripts/x.py --json`. verdict text. {_SPEC_TAIL} "
        f"{trailing_prose} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("prose parked after the Spec pointer must fail, not silently pass")


def test_reordered_parts_is_rejected() -> None:
    """Canary (dec-378, ordering): parts in any order other than Conditional? +
    Invocation + verdict map + Spec pointer must fail -- `SYSTEMS_PLAN.md § The
    Extraction Contract` fixes the order ("Four parts, in this order, and no fifth"),
    and the whole-column parse enforces it structurally rather than leaving it
    unasserted.
    """
    text = (
        "### D\n\n"
        f"| X01 | A | rule | {_SPEC_TAIL} Run `python3 scripts/x.py --json`. verdict text. |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError:
        return
    raise AssertionError("a row with parts out of the mandated order must fail")


# ---------------------------------------------------------------------------
# Extraction registry -- append-only. Each extraction of an `A`-typed sentinel check
# appends its own (check_id, script_name) pair here in the same commit that collapses
# its row into the four-part residual template.
# ---------------------------------------------------------------------------

EXTRACTED_CHECKS: list[tuple[str, str]] = [
    ("AC13", "check_architecture_projection"),
    ("DH05", "adr_health"),
    ("DL06", "check_adr_reciprocity"),
    ("T03", "check_agent_prompt_size"),
    ("F11", "check_doc_manifest_freshness"),
    ("P03", "check_agent_lifecycle_pairing"),
]


def test_every_extracted_row_satisfies_the_contract() -> None:
    """Every row registered in `EXTRACTED_CHECKS` still satisfies the residual contract."""
    sentinel_text = SENTINEL_PATH.read_text(encoding="utf-8")
    for check_id, script_name in EXTRACTED_CHECKS:
        assert_residual_row_contract(sentinel_text, check_id, script_name)
