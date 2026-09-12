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

A verdict-map budget alone does not close the row: every other slot that can vary --
the Conditional's path (`_CONDITIONAL_PATH_MAX_CHARS`) and its optional parenthetical
(`_CONDITIONAL_PAREN_MAX_CHARS`), the dimension-name token (`_DIMENSION_MAX_CHARS`), the
Invocation's backtick span (`_INVOCATION_FLAGS_MAX_CHARS`), the Tp cell
(`_TP_MAX_CHARS`), and the Rule/claim cell (`_RULE_MAX_CHARS`) -- carries its own
explicit ceiling, asserted directly rather than left as unenforced prose. That list is a
cache, not the invariant it restates: this file's two prior FAILs were each exactly one
slot missing from a list shaped just like it. The invariant that cannot silently go
stale the same way is checked structurally instead --
`test_no_unbounded_quantifier_escapes_the_verdict_slot` below scans the built row
pattern's own regex source and asserts that no unbounded repetition (`*`, `+`, or an
absent-upper-bound `{m,}`) survives outside the two constructs deliberately left open:
the verdict-map capture itself (bounded after the match, by byte length, not by the
regex) and `\\s*` separators (whitespace-only, stripped before measurement, so they
cannot carry graded content). A new unbounded slot fails that scan on sight, without
first needing to be added to this paragraph.

`EXTRACTED_CHECKS` is append-only: entries are never removed or reordered, only added,
one per extraction step. It is also one corner of the **Triangle** -- the three-way set
equality (catalogue rows citing a script == that script's `EXTRACTED_CHECKS` entries ==
the ids the script itself declares) that `assert_check_registration_triangle` enforces,
in the sibling `tests/test_sentinel_check_triangle.py`. All three legs are parsed, none
is hand-maintained, so a row, a registry entry, or a declared check id that loses its
two partners fails rather than drifting.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md§Pragmatism.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENTINEL_PATH = PROJECT_ROOT / "agents" / "sentinel.md"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

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

_CONDITIONAL_PAREN_MAX_CHARS = 40  # the only live parenthetical is DL06's "(either
# lifecycle stage)" -- 23 chars of content. 40 leaves room for a second short qualifier
# without leaving room for the 900-char padding NEW-2 found ACCEPTED on the prior open
# `[^)]*` span.

_DIMENSION_MAX_CHARS = 4  # every live dimension token is 1-2 uppercase letters (F, P,
# AC, DH, DL, TT, GL, RD, SH, TD, CA, PR, EC -- see agents/sentinel.md's `### <dim>`
# headings). 4 leaves room for a slightly longer future dimension code without leaving
# room for the 900-char padding NEW-2 found ACCEPTED on the prior open `[A-Za-z]+` token.

_CONDITIONAL_SHAPE = (
    rf"Conditional on .{{1,{_CONDITIONAL_PATH_MAX_CHARS}}}? present"
    rf"(?: \([^)]{{0,{_CONDITIONAL_PAREN_MAX_CHARS}}}\))?; "
    rf"skip with an? [A-Za-z]{{1,{_DIMENSION_MAX_CHARS}}}-dimension INFO note\.\s*"
)


_INVOCATION_FLAGS_MAX_CHARS = 20  # every live invocation carries exactly " --json" (7
# chars); 20 leaves room for a second short flag (e.g. " --json --strict") without
# leaving room for padding riding the open `[^\`]*` span a prior version of this pattern
# used.

_TP_MAX_CHARS = 10  # every live Tp value is a single letter ("A" or "L" --
# `SYSTEMS_PLAN.md § The Extraction Contract`'s type column). 10 leaves room for a short
# future type code without leaving room for the 900-char padding NEW-2 found ACCEPTED on
# the unchecked Tp cell.


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
    binds. The Tp cell is checked separately against `_TP_MAX_CHARS` and the Rule/claim
    cell separately against `_RULE_MAX_CHARS`, so this cell is the only place the
    mandated template parts and the verdict map they wrap can live.
    """
    return _row_cells(row)[-1]


def _tp_column(row: str) -> str:
    """Return the second (Tp/type) cell of `row`."""
    return _row_cells(row)[1]


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

    Six checks, each binding a live consumer named in `SYSTEMS_PLAN.md § The Extraction
    Contract`: (a) the row sits under a `### <dimension>` heading and carries the literal
    `python3 scripts/<script_name>.py` invocation phrase -- the same phrase
    `_delegated_gates`, GL04 (`check_uninvoked_gate`) and GL05 (`check_ambient_import`) all
    key on; (b) the row names its canary sibling, `scripts/test_<script_name>.py`; (c) the
    Tp cell is at most `_TP_MAX_CHARS`; (d) the Rule/claim cell is at most
    `_RULE_MAX_CHARS`; (e) the verdict map -- the Pass column parsed down to its
    non-template residue -- is at most `_VERDICT_MAP_MAX_BYTES`.
    """
    row = _find_row(sentinel_text, check_id)

    dimension = _dimension_heading_before(sentinel_text, row)
    assert dimension is not None, f"{check_id}: row is not under any `### <dimension>` heading"

    invocation = f"python3 scripts/{script_name}.py"
    assert invocation in row, f"{check_id}: row is missing the literal `{invocation}` phrase"

    canary_ref = f"scripts/test_{script_name}.py"
    assert canary_ref in row, f"{check_id}: row is missing its canary pointer `{canary_ref}`"

    tp = _tp_column(row)
    assert len(tp) <= _TP_MAX_CHARS, (
        f"{check_id}: Tp column is {len(tp)} chars, exceeds the {_TP_MAX_CHARS}-char budget"
    )

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


def test_conditional_parenthetical_over_budget_is_rejected() -> None:
    """Canary (NEW-2, parenthetical probe): the optional `(...)` qualifier past
    `_CONDITIONAL_PAREN_MAX_CHARS` must fail the parse. The prior open `[^)]*` span was
    ACCEPTED at 900 chars; the explicit char ceiling turns that into a parse failure
    instead.
    """
    padding = "x" * 900
    text = (
        "### D\n\n"
        f"| X01 | A | rule | Conditional on `some/path` present ({padding}); skip with a "
        f"D-dimension INFO note. Run `python3 scripts/x.py --json`. verdict text here. "
        f"{_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError as exc:
        if "does not decompose" not in str(exc):
            raise AssertionError(f"expected the parse-failure message, got: {exc}") from exc
        return
    raise AssertionError("a Conditional parenthetical past the char budget must fail")


def test_dimension_token_over_budget_is_rejected() -> None:
    """Canary (NEW-2, dimension-token probe): the `<D>-dimension` token past
    `_DIMENSION_MAX_CHARS` must fail the parse. The prior open `[A-Za-z]+` token was
    ACCEPTED at 900 chars; the explicit char ceiling turns that into a parse failure
    instead.
    """
    padding = "x" * 900
    text = (
        "### D\n\n"
        f"| X01 | A | rule | Conditional on `some/path` present; skip with a "
        f"{padding}-dimension INFO note. Run `python3 scripts/x.py --json`. verdict text "
        f"here. {_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError as exc:
        if "does not decompose" not in str(exc):
            raise AssertionError(f"expected the parse-failure message, got: {exc}") from exc
        return
    raise AssertionError("a dimension-name token past the char budget must fail")


def test_conditional_with_parenthetical_is_accepted() -> None:
    """Inverse guard: DL06's real shape -- a Conditional carrying the optional
    parenthetical qualifier at ordinary length -- parses cleanly.
    """
    text = (
        "### D\n\n"
        "| X01 | A | rule | Conditional on `.ai-state/decisions/` present (either "
        f"lifecycle stage); skip with a D-dimension INFO note. Run "
        f"`python3 scripts/x.py --json`. verdict text here. {_SPEC_TAIL} |\n"
    )
    assert_residual_row_contract(text, "X01", "x")  # must not raise


def test_tp_column_over_budget_is_rejected() -> None:
    """Canary (NEW-2, Tp probe): a Tp/type cell past `_TP_MAX_CHARS` must fail.
    Previously unenforced -- the module docstring asserted "ID/Tp are trivially
    short" while nothing checked it, and 900 chars parked here was ACCEPTED.
    """
    padding = "x" * 900
    text = (
        f"### D\n\n| X01 | {padding} | rule | Run `python3 scripts/x.py --json`. verdict "
        f"text. {_SPEC_TAIL} |\n"
    )
    try:
        assert_residual_row_contract(text, "X01", "x")
    except AssertionError as exc:
        if "Tp column" not in str(exc):
            raise AssertionError(f"expected the Tp-column message, got: {exc}") from exc
        return
    raise AssertionError("a Tp column past the char budget must fail")


_BARE_QUANTIFIER = re.compile(r"(?<!\})(?<!\\)[*+]|\{\d*,\}")  # two families, closed
# because Python's `re` quantifier grammar itself has only two: (1) bare `*`/`+`,
# excluding a `}`-preceded char (a possessive suffix on a bounded `{m,n}+`, still
# bounded) and a `\`-escaped literal (e.g. `spec_pointer`'s `\+` for the literal "+" in
# "Spec + golden bad-cases") -- neither is a repetition operator; and (2) brace
# repetition with an absent upper bound, `{m,}` or `{,}`, matched by `\{\d*,\}` (a
# literal `,` immediately followed by `}`, with zero or more digits for `m` beforehand).
# `{m,n}` with an explicit `n` is excluded on purpose: the upper bound already caps the
# repetition regardless of how large `n` is, so it is not this scan's concern.
#
# Both families already catch every suffixed variant without extra alternation: a lazy
# `*?`/`+?` or a Python 3.11+ possessive `*+`/`++`/`{m,}+` still contains the bare `*`,
# `+`, or `{m,}` substring this pattern matches -- the trailing `?`/`+` modifies how the
# quantifier backtracks, not whether it is unbounded, so it never needs its own branch.

_VERDICT_SLOT = "(?P<verdict>.*?)"

# Every `re.Pattern` this module builds is classified into exactly one of the two
# registries below, and `test_every_module_pattern_is_classified` asserts the pair covers
# the module's compiled globals exactly. That is what keeps the quantifier scan
# totalising while widening its domain past `_row_pattern`: a new pattern cannot appear
# without its author deciding which bucket it belongs in, and an unclassified one fails
# on sight instead of quietly escaping the scan the way a hand-listed set of scanned
# patterns would let it.
#
# `_row_pattern`'s outputs are budget-bearing too, but they are built per script name
# rather than held as globals, so the scan builds and scans them separately. This
# module holds no budget-bearing globals of its own since the Triangle split moved
# `_SCRIPT_CITATION` to `test_sentinel_check_triangle` -- that module carries its own
# pair of the same two registries, and the totalising tests below scan both modules'
# globals rather than just this one.
_BUDGET_BEARING_PATTERNS: tuple[re.Pattern[str], ...] = ()

# Patterns exempt from the scan, each with the reason its quantifiers cannot carry
# graded content. An exemption is a claim about the pattern, not a convenience.
_NON_BUDGET_PATTERNS: dict[re.Pattern[str], str] = {
    _DIMENSION_HEADING: (
        "locator: captures a heading line, which no budget is ever measured against"
    ),
    _TABLE_ROW: (
        "locator: captures a whole row, whose cells are then re-parsed -- the Pass "
        "column by the anchored `_row_pattern`, the rest against their own ceilings"
    ),
    _BARE_QUANTIFIER: (
        "meta: scans regex source; the `*`/`+`/`{m,}` shapes in its own alternation are "
        "the operators being searched for, not operators it applies"
    ),
}


def _triangle_module():
    """Import the sibling Triangle test module, deferred to test-execution time.

    A module-level import would be circular: `test_sentinel_check_triangle` imports
    this module (`contract`) for its shared row-parsing helpers, so this module cannot
    also import it back at load time. Deferring to call time -- only the two totalising
    tests below need it -- breaks the cycle without either module owning the other.
    """
    # Bare-name import, not `tests.…`: `tests/` has no `__init__.py`, so the dotted form
    # only resolves while the repo root is the sole `tests` on sys.path -- and any
    # invocation that also collects `fitness/` (a package whose `tests/` subdir IS a
    # package) binds `tests` to the wrong tree and errors here. pytest prepends this
    # file's own directory, so the sibling is importable by name in every invocation.
    import test_sentinel_check_triangle as triangle

    return triangle


def _module_patterns(module_name: str, module_globals: dict) -> dict[re.Pattern[str], str]:
    """Map each compiled `re.Pattern` in `module_globals` to a `module_name.NAME` label."""
    return {
        value: f"{module_name}.{name}"
        for name, value in module_globals.items()
        if isinstance(value, re.Pattern)
    }


def _assert_no_unbounded_quantifier(pattern_text: str, origin: str) -> None:
    """Assert no repetition operator in `pattern_text` survives outside the two open constructs.

    The verdict-map capture is bounded after the match by `_VERDICT_MAP_MAX_BYTES` rather
    than by the regex, and `\\s*` separators are whitespace-only (stripped before
    measurement), so padding there carries no measurable content. Everything else must
    carry an explicit `{m,n}` bound.
    """
    residue = pattern_text.replace(_VERDICT_SLOT, "", 1)
    for match in _BARE_QUANTIFIER.finditer(residue):
        preceding = residue[: match.start()]
        assert preceding.endswith("\\s"), (
            f"{origin}: unbounded quantifier {match.group(0)!r} found outside the verdict "
            f"slot and outside a \\s separator, near: "
            f"...{residue[max(0, match.start() - 24) : match.start() + 4]!r}"
        )


def test_unbounded_brace_quantifier_is_rejected() -> None:
    """Canary (F1): brace-form unbounded repetition -- `{0,}` and `{1,}` -- must be
    caught by the scan exactly as `*`/`+` are; a bound with a genuine upper limit
    (`{0,5}`, `{2,7}`) must not trip it. `{0,}` and `[^x]*` are semantically identical,
    so a scan blind to the brace form would let an author reintroduce, in brace syntax,
    the exact unbounded-padding defect this file's canaries already close for `*`/`+`.
    """
    try:
        _assert_no_unbounded_quantifier(r"[^`]{0,}", "canary")
    except AssertionError:
        pass
    else:
        raise AssertionError("'[^`]{0,}': unbounded brace quantifier must be rejected")

    try:
        _assert_no_unbounded_quantifier(r"x{1,}", "canary")
    except AssertionError:
        pass
    else:
        raise AssertionError("'x{1,}': unbounded brace quantifier must be rejected")

    _assert_no_unbounded_quantifier(r"[^`]{0,5}", "canary")  # must not raise
    _assert_no_unbounded_quantifier(r"x{2,7}", "canary")  # must not raise


def test_every_module_pattern_is_classified() -> None:
    """Totalising guard: every compiled pattern this module AND its sibling
    `test_sentinel_check_triangle` module hold is classified as budget-bearing (scanned
    below) or non-budget (exempt, with a stated reason).

    Iterates each module's own globals rather than a hand list, so a pattern added or
    moved in either file is picked up automatically -- neither module can silently grow
    an unscanned pattern. The Triangle module is discovered by (deferred) import; see
    `_triangle_module`'s docstring for why the import cannot happen at load time.
    """
    triangle = _triangle_module()
    for label, module_globals, budget, non_budget in (
        (__name__, globals(), _BUDGET_BEARING_PATTERNS, _NON_BUDGET_PATTERNS),
        (
            triangle.__name__,
            vars(triangle),
            triangle._BUDGET_BEARING_PATTERNS,
            triangle._NON_BUDGET_PATTERNS,
        ),
    ):
        names = _module_patterns(label, module_globals)
        compiled = set(names)
        classified = set(budget) | set(non_budget)

        unclassified = compiled - classified
        assert not unclassified, (
            f"{label}: patterns {sorted(names[p] for p in unclassified)} are in neither "
            "_BUDGET_BEARING_PATTERNS nor _NON_BUDGET_PATTERNS -- classify them (an "
            "exemption must state why its quantifiers cannot carry graded content)"
        )

        dangling = classified - compiled
        assert not dangling, (
            f"{label}: {len(dangling)} classified pattern(s) are no longer module "
            "globals -- drop them from the registries rather than leaving a "
            "classification behind"
        )


def test_no_unbounded_quantifier_escapes_the_verdict_slot() -> None:
    """Totalizing guard (NEW-2, extended for the Triangle split): rather than re-listing
    which slots are individually bounded -- a list two prior FAILs each fell out of sync
    with by exactly one slot -- this scans the regex source of *every budget-bearing
    pattern either this module or `test_sentinel_check_triangle` builds* -- each
    `_row_pattern` built for a registered script plus each module's own
    `_BUDGET_BEARING_PATTERNS` -- for any repetition operator that isn't an explicit
    `{m,n}` bound. The domain is kept honest by `test_every_module_pattern_is_classified`,
    not by this list. Only two constructs are allowed to stay unbounded: the
    deliberately-open verdict-map capture (`(?P<verdict>.*?)`, bounded after the match by
    `_VERDICT_MAP_MAX_BYTES` rather than by the regex) and `\\s*` separators
    (whitespace-only, stripped by `_verdict_map` before measurement, so padding there
    carries no measurable content). A new unbounded slot -- the parenthetical, the
    dimension token, and the Tp cell were each exactly this shape -- fails this scan on
    sight, without needing to be named here first.
    """
    triangle = _triangle_module()
    names = {
        **_module_patterns(__name__, globals()),
        **_module_patterns(triangle.__name__, vars(triangle)),
    }
    for pattern in (*_BUDGET_BEARING_PATTERNS, *triangle._BUDGET_BEARING_PATTERNS):
        _assert_no_unbounded_quantifier(pattern.pattern, names.get(pattern, repr(pattern)))

    for script_name in sorted({script for _, script in EXTRACTED_CHECKS} | {"x"}):
        built = _row_pattern(script_name).pattern
        assert _VERDICT_SLOT in built, (
            f"_row_pattern({script_name!r}): verdict capture group not found in the built pattern"
        )
        _assert_no_unbounded_quantifier(built, f"_row_pattern({script_name!r})")


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
    ("P07", "check_specialist_dispositions"),
    ("F07", "check_staleness_markers"),
    ("F08", "check_staleness_markers"),
    ("F09", "check_staleness_markers"),
    ("F10", "check_hook_installation"),
    ("DL01", "check_state_corpus"),
    ("DL02", "check_state_corpus"),
    ("SH01", "check_state_corpus"),
    ("SH02", "check_state_corpus"),
    ("CA01", "check_state_corpus"),
    ("TT01", "check_topology_conformance"),
    ("TT02", "check_topology_conformance"),
    ("TT05", "check_topology_conformance"),
    ("TT06", "check_topology_conformance"),
    ("HK01", "check_hackathon_graduation"),
    ("V01", "check_sentinel_self_audit"),
    ("V02", "check_sentinel_self_audit"),
    ("V03", "check_sentinel_self_audit"),
    ("V04", "check_sentinel_self_audit"),
    ("DH02", "adr_health"),
    ("DH04", "adr_health"),
    ("DL03", "regenerate_adr_index"),
    ("X01", "check_registry_projection"),
    ("X02", "check_registry_projection"),
    ("X05", "check_registry_projection"),
    ("X06", "check_registry_projection"),
    ("EC01", "check_registry_projection"),
    ("EC02", "check_registry_projection"),
    ("F01", "check_path_resolution"),
    ("F02", "check_path_resolution"),
    ("F05", "check_path_resolution"),
    ("X03", "check_path_resolution"),
    ("X09", "check_path_resolution"),
    ("BC01", "check_behavioral_contract"),
    ("BC03", "check_behavioral_contract"),
    ("BC04", "check_behavioral_contract"),
]


def test_every_extracted_row_satisfies_the_contract() -> None:
    """Every row registered in `EXTRACTED_CHECKS` still satisfies the residual contract."""
    sentinel_text = SENTINEL_PATH.read_text(encoding="utf-8")
    for check_id, script_name in EXTRACTED_CHECKS:
        assert_residual_row_contract(sentinel_text, check_id, script_name)
