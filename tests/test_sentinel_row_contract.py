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
pattern's own regex source and asserts that no `*`/`+` repetition survives outside the
two constructs deliberately left open: the verdict-map capture itself (bounded after the
match, by byte length, not by the regex) and `\\s*` separators (whitespace-only, stripped
before measurement, so they cannot carry graded content). A new unbounded slot fails
that scan on sight, without first needing to be added to this paragraph.

`EXTRACTED_CHECKS` is append-only: entries are never removed or reordered, only added,
one per extraction step. It is also one corner of the **Triangle** -- the three-way set
equality (catalogue rows citing a script == that script's `EXTRACTED_CHECKS` entries ==
the ids the script itself declares) that `assert_check_registration_triangle` enforces.
All three legs are parsed, none is hand-maintained, so a row, a registry entry, or a
declared check id that loses its two partners fails rather than drifting.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md§Pragmatism.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Sequence
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


# ---------------------------------------------------------------------------
# The Triangle: catalogue row <-> extraction registry <-> script
# ---------------------------------------------------------------------------

_SCRIPT_NAME_MAX_CHARS = 40  # the longest live script name is
# `check_agent_lifecycle_pairing` (29 chars); 40 leaves room for a longer family script
# name without leaving room for the padding a bare `+` would admit. The slot is bounded
# for the same reason every other slot in this file is: an unbounded name would silently
# widen which rows Leg 1 believes cite a script.
_SCRIPT_CITATION = re.compile(
    rf"python3 scripts/(?P<script>[a-z0-9_]{{1,{_SCRIPT_NAME_MAX_CHARS}}})\.py"
)

# Rows that cite a script the registry already names, but in the pre-extraction legacy
# shape -- so they are not part of the extracted surface Leg 1 totalises over. Scoping
# Leg 1 to *registered scripts* is necessary but not sufficient: `adr_health.py` is cited
# by DH01 and DH06 (legacy prose) as well as by DH05 (extracted), so a script-name-only
# scope fails on day one exactly the way an unscoped leg would.
#
# The exemption cannot silently go stale: `test_legacy_citing_rows_allowlist_is_not_stale`
# asserts it stays disjoint from `EXTRACTED_CHECKS`, that every entry still cites a
# registered script, and that every entry still genuinely fails the four-part template
# parse -- so it can neither outlive its rows nor be used to park a conforming row
# outside the guard.
_LEGACY_CITING_ROWS = frozenset({"DH01", "DH06"})

_CHECK_ID_NAMES = ("CHECK_ID", "CHECK_IDS")


def _rows_by_cited_script(sentinel_text: str) -> dict[str, set[str]]:
    """Map each cited script name to the ids of the catalogue rows whose Pass column cites it.

    The citation is *parsed* with a bounded pattern rather than located by substring: a
    row naming two scripts registers under both, and a name longer than
    `_SCRIPT_NAME_MAX_CHARS` is a parse miss rather than a silent accept.
    """
    by_script: dict[str, set[str]] = {}
    for row in _TABLE_ROW.finditer(sentinel_text):
        for citation in _SCRIPT_CITATION.finditer(_pass_column(row.group(0))):
            by_script.setdefault(citation.group("script"), set()).add(row.group("id"))
    return by_script


def _check_id_declarations(source: str) -> list[tuple[str, ast.expr]]:
    """Return `(constant_name, value_node)` per module-level CHECK_ID/CHECK_IDS assignment.

    Module level only: a check id assigned inside a function or class is not the declared
    surface a reader of the script's header would see, so it does not count as one.
    """
    declarations: list[tuple[str, ast.expr]] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign):
            targets: list[ast.expr] = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        else:
            continue
        if node.value is None:  # a bare annotation declares no value
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in _CHECK_ID_NAMES:
                declarations.append((target.id, node.value))
    return declarations


def _declared_check_ids(source: str, script_name: str) -> set[str]:
    """Return the check ids `source` declares, read via `ast.literal_eval` without importing it.

    Importing a check script to read one constant would drag its whole import surface --
    and any module-level side effect -- into this test for no gain, so the declaration is
    read off the parse tree instead. A declaration that is not a literal (computed,
    aliased, built at runtime) fails here by design.

    Flat (`CHECK_ID = "DL06"`) and keyed (`CHECK_IDS = ("DH02", "DH05")`) are the two
    legal shapes and are mutually exclusive -- exactly one declaration, so "which one
    wins" is never a question the reader has to answer.
    """
    declarations = _check_id_declarations(source)
    assert len(declarations) == 1, (
        f"{script_name}: expected exactly one module-level "
        f"{' or '.join(_CHECK_ID_NAMES)} declaration, found {len(declarations)} -- a "
        "check script declares its surface once, in one literal"
    )

    name, value = declarations[0]
    try:
        declared = ast.literal_eval(value)
    except (ValueError, TypeError) as exc:
        raise AssertionError(
            f"{script_name}: {name} is not a literal -- the contract test reads it with "
            "`ast.literal_eval` rather than importing the script, so a computed "
            f"declaration has no readable value ({exc})"
        ) from exc

    if name == "CHECK_ID":
        assert isinstance(declared, str), (
            f"{script_name}: CHECK_ID must be a string literal, got {type(declared).__name__}"
        )
        return {declared}

    assert isinstance(declared, tuple), (
        f"{script_name}: CHECK_IDS must be a literal tuple of strings, got "
        f"{type(declared).__name__}"
    )
    assert all(isinstance(item, str) for item in declared), (
        f"{script_name}: CHECK_IDS must be a literal tuple of strings; {declared!r} "
        "holds a non-string member"
    )
    return set(declared)


def assert_check_registration_triangle(
    sentinel_text: str,
    registry: Sequence[tuple[str, str]],
    read_script_source: Callable[[str], str],
) -> None:
    """Assert row == registry == declared-id, per script `registry` names.

    Three one-directional containments closing a cycle -- rows subset-of registry
    subset-of script subset-of rows -- which is set equality, and which lets each leg
    fail with its own message and carry its own canary:

    * **Leg 1, document to registry**: a row cites a live family script but the registry
      never learned about it -- the drift the family shape (one script, many rows) newly
      creates. Scoped to registered scripts minus `_LEGACY_CITING_ROWS`.
    * **Leg 2, registry to script**: a registry entry names a check its script does not
      emit.
    * **Leg 3, script to document**: a script declares a check id no row cites -- dead
      check surface.
    """
    registered: dict[str, set[str]] = {}
    for check_id, script_name in registry:
        registered.setdefault(script_name, set()).add(check_id)

    cited = _rows_by_cited_script(sentinel_text)

    for script_name in sorted(registered):
        expected = registered[script_name]
        from_rows = cited.get(script_name, set()) - _LEGACY_CITING_ROWS
        from_script = _declared_check_ids(read_script_source(script_name), script_name)

        unregistered = from_rows - expected
        assert not unregistered, (
            f"{script_name}: rows {sorted(unregistered)} cite the script but have no "
            "EXTRACTED_CHECKS entry (Leg 1, document -> registry)"
        )

        undeclared = expected - from_script
        assert not undeclared, (
            f"{script_name}: EXTRACTED_CHECKS registers {sorted(undeclared)}, which the "
            f"script's {'/'.join(_CHECK_ID_NAMES)} does not declare (Leg 2, registry -> "
            "script)"
        )

        uncited = from_script - from_rows
        assert not uncited, (
            f"{script_name}: declares {sorted(uncited)}, which no catalogue row cites "
            "(Leg 3, script -> document) -- dead check surface"
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


_BARE_QUANTIFIER = re.compile(r"(?<!\})(?<!\\)[*+]")  # `}` excludes `{m,n}` bounds; `\`
# excludes an escaped literal `+`/`*` (e.g. `spec_pointer`'s `\+` for the literal "+" in
# "Spec + golden bad-cases") -- neither is a repetition operator.

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
# rather than held as globals, so the scan builds and scans them separately.
_BUDGET_BEARING_PATTERNS: tuple[re.Pattern[str], ...] = (_SCRIPT_CITATION,)

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
        "meta: scans regex source; the `*`/`+` in its character class are the operators "
        "being searched for, not operators it applies"
    ),
}


def _pattern_names() -> dict[re.Pattern[str], str]:
    """Map each compiled pattern this module holds to its global name, for failure messages."""
    return {value: name for name, value in globals().items() if isinstance(value, re.Pattern)}


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


def test_every_module_pattern_is_classified() -> None:
    """Totalising guard: every compiled pattern this module holds is classified as
    budget-bearing (scanned below) or non-budget (exempt, with a stated reason).

    Without this, widening the quantifier scan past `_row_pattern` would just trade one
    hand-maintained list for another -- a new pattern would be unscanned and unnoticed,
    which is the exact staleness shape two prior FAILs in this file already took.
    """
    names = _pattern_names()
    compiled = set(names)
    classified = set(_BUDGET_BEARING_PATTERNS) | set(_NON_BUDGET_PATTERNS)

    unclassified = compiled - classified
    assert not unclassified, (
        f"patterns {sorted(names[p] for p in unclassified)} are in neither "
        "_BUDGET_BEARING_PATTERNS nor _NON_BUDGET_PATTERNS -- classify them (an "
        "exemption must state why its quantifiers cannot carry graded content)"
    )

    dangling = classified - compiled
    assert not dangling, (
        f"{len(dangling)} classified pattern(s) are no longer module globals -- drop "
        "them from the registries rather than leaving a classification behind"
    )


def test_no_unbounded_quantifier_escapes_the_verdict_slot() -> None:
    """Totalizing guard (NEW-2): rather than re-listing which slots are individually
    bounded -- a list two prior FAILs each fell out of sync with by exactly one slot --
    this scans the regex source of *every budget-bearing pattern the module builds* --
    each `_row_pattern` built for a registered script plus the standalone patterns in
    `_BUDGET_BEARING_PATTERNS` -- for any repetition operator that isn't an explicit
    `{m,n}` bound. The domain is kept honest by
    `test_every_module_pattern_is_classified`, not by this list. Only two constructs are
    allowed to stay
    unbounded: the deliberately-open verdict-map capture (`(?P<verdict>.*?)`, bounded
    after the match by `_VERDICT_MAP_MAX_BYTES` rather than by the regex) and `\\s*`
    separators (whitespace-only, stripped by `_verdict_map` before measurement, so
    padding there carries no measurable content). A new unbounded slot -- the
    parenthetical, the dimension token, and the Tp cell were each exactly this shape --
    fails this scan on sight, without needing to be named here first.
    """
    for pattern in _BUDGET_BEARING_PATTERNS:
        _assert_no_unbounded_quantifier(
            pattern.pattern, _pattern_names().get(pattern, repr(pattern))
        )

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
# Triangle canaries: one per leg, plus the shapes each leg's parse must not admit
# ---------------------------------------------------------------------------


def _triangle_row(check_id: str) -> str:
    """A four-part template row for `check_id` citing the fixture script `x`."""
    return (
        f"| {check_id} | A | rule | Run `python3 scripts/x.py --json`. verdict text. {_SPEC_TAIL} |"
    )


def _triangle_doc(*rows: str) -> str:
    """A minimal catalogue fragment holding `rows` under one dimension heading."""
    return "### D\n\n" + "\n".join(rows) + "\n"


def _fixed_source(source: str) -> Callable[[str], str]:
    """A `read_script_source` that returns `source` for whatever script is asked for."""
    return lambda _script_name: source


def test_row_citing_a_registered_script_without_a_registry_entry_is_rejected() -> None:
    """Leg 1 canary: a second row pointed at a live family script, with no
    `EXTRACTED_CHECKS` entry, must fail -- the drift one-script-many-rows newly creates.
    """
    doc = _triangle_doc(_triangle_row("X01"), _triangle_row("X02"))
    try:
        assert_check_registration_triangle(
            doc, [("X01", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
        )
    except AssertionError as exc:
        if "Leg 1" not in str(exc):
            raise AssertionError(f"expected the Leg 1 message, got: {exc}") from exc
        return
    raise AssertionError("a row citing a registered script with no registry entry must fail")


def test_registry_entry_the_script_does_not_declare_is_rejected() -> None:
    """Leg 2 canary: a registry entry naming a check its script never declares must fail."""
    doc = _triangle_doc(_triangle_row("X01"), _triangle_row("X02"))
    try:
        assert_check_registration_triangle(
            doc, [("X01", "x"), ("X02", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
        )
    except AssertionError as exc:
        if "Leg 2" not in str(exc):
            raise AssertionError(f"expected the Leg 2 message, got: {exc}") from exc
        return
    raise AssertionError("a registry entry the script does not declare must fail")


def test_declared_check_id_no_row_cites_is_rejected() -> None:
    """Leg 3 canary: a check id the script declares but no row cites -- dead check
    surface -- must fail.
    """
    doc = _triangle_doc(_triangle_row("X01"))
    try:
        assert_check_registration_triangle(
            doc, [("X01", "x")], _fixed_source('CHECK_IDS = ("X01", "X02")\n')
        )
    except AssertionError as exc:
        if "Leg 3" not in str(exc):
            raise AssertionError(f"expected the Leg 3 message, got: {exc}") from exc
        return
    raise AssertionError("a declared check id no row cites must fail")


def test_legacy_shaped_row_citing_an_unregistered_script_is_accepted() -> None:
    """Inverse guard: the ~20 pre-extraction rows citing scripts in legacy shape (prose,
    no four-part template, no registry entry) must not fail -- Leg 1 totalises over the
    extracted surface, not over the whole catalogue.
    """
    legacy = (
        "| Y01 | A | rule | Run `python3 scripts/legacy_thing.py --json`. Each finding "
        "is a **WARN**; read the prose for the disposition. |"
    )
    doc = _triangle_doc(_triangle_row("X01"), legacy)
    assert_check_registration_triangle(
        doc, [("X01", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
    )  # must not raise


def test_row_citing_the_same_script_twice_counts_once() -> None:
    """Inverse guard: a row naming its script's invocation twice contributes one id, not
    a duplicate -- the legs compare sets, so a repeated citation is not drift.
    """
    doubled = (
        "| X01 | A | rule | Run `python3 scripts/x.py --json`, then re-run "
        f"`python3 scripts/x.py --json` after fixing. {_SPEC_TAIL} |"
    )
    assert_check_registration_triangle(
        _triangle_doc(doubled), [("X01", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
    )  # must not raise


def test_two_check_id_declarations_are_rejected() -> None:
    """Leg 3 parse canary: two module-level declarations leave "which one wins"
    unanswered, so the parse refuses rather than silently picking one.
    """
    source = 'CHECK_IDS = ("X01",)\nCHECK_IDS = ("X02",)\n'
    try:
        assert_check_registration_triangle(
            _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
        )
    except AssertionError as exc:
        if "exactly one" not in str(exc):
            raise AssertionError(f"expected the single-declaration message, got: {exc}") from exc
        return
    raise AssertionError("two CHECK_IDS declarations must fail")


def test_flat_and_keyed_declarations_together_are_rejected() -> None:
    """Leg 3 parse canary: flat (`CHECK_ID`) and keyed (`CHECK_IDS`) are mutually
    exclusive shapes -- a script declaring both has no single declared surface.
    """
    source = 'CHECK_ID = "X01"\nCHECK_IDS = ("X01",)\n'
    try:
        assert_check_registration_triangle(
            _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
        )
    except AssertionError as exc:
        if "exactly one" not in str(exc):
            raise AssertionError(f"expected the single-declaration message, got: {exc}") from exc
        return
    raise AssertionError("declaring both CHECK_ID and CHECK_IDS must fail")


def test_non_literal_check_ids_is_rejected() -> None:
    """Leg 3 parse canary: a computed declaration has no value `ast.literal_eval` can
    read, and the guard reads rather than imports -- so it must fail, not skip.
    """
    source = "_IDS = [1]\nCHECK_IDS = tuple(str(i) for i in _IDS)\n"
    try:
        assert_check_registration_triangle(
            _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
        )
    except AssertionError as exc:
        if "not a literal" not in str(exc):
            raise AssertionError(f"expected the non-literal message, got: {exc}") from exc
        return
    raise AssertionError("a computed CHECK_IDS must fail")


def test_check_ids_as_a_list_is_rejected() -> None:
    """Leg 3 parse canary: a list is literal-evaluable but mutable, so it is not the
    declared surface the family envelope specifies -- the shape is asserted, not inferred.
    """
    source = 'CHECK_IDS = ["X01"]\n'
    try:
        assert_check_registration_triangle(
            _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
        )
    except AssertionError as exc:
        if "literal tuple" not in str(exc):
            raise AssertionError(f"expected the tuple-shape message, got: {exc}") from exc
        return
    raise AssertionError("a list-valued CHECK_IDS must fail")


def test_script_declaring_no_check_id_is_rejected() -> None:
    """Leg 3 parse canary: a registered script that declares neither constant has no
    third leg at all, which must fail rather than vacuously pass.
    """
    source = 'SEVERITY = "warn"\n'
    try:
        assert_check_registration_triangle(
            _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
        )
    except AssertionError as exc:
        if "exactly one" not in str(exc):
            raise AssertionError(f"expected the single-declaration message, got: {exc}") from exc
        return
    raise AssertionError("a script declaring no check id must fail")


def test_well_formed_triangle_is_accepted() -> None:
    """Inverse guard: rows, registry and declaration agreeing on two ids across two
    scripts passes without raising -- flat and keyed declarations both.
    """
    doc = _triangle_doc(
        _triangle_row("X01"),
        "| Y01 | A | rule | Run `python3 scripts/y.py --json`. verdict text. Spec + "
        "golden bad-cases: `scripts/y.py` docstring; canary `scripts/test_y.py`. |",
    )
    sources = {"x": 'CHECK_IDS = ("X01",)\n', "y": 'CHECK_ID = "Y01"\n'}
    assert_check_registration_triangle(
        doc, [("X01", "x"), ("Y01", "y")], sources.__getitem__
    )  # must not raise


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


def _script_source(script_name: str) -> str:
    """Read `scripts/<script_name>.py`, the third leg's substrate."""
    return (SCRIPTS_DIR / f"{script_name}.py").read_text(encoding="utf-8")


def test_every_extracted_check_is_bound_by_the_triangle() -> None:
    """Row, registry and script agree on the check ids of every registered script."""
    assert_check_registration_triangle(
        SENTINEL_PATH.read_text(encoding="utf-8"), EXTRACTED_CHECKS, _script_source
    )


def test_legacy_citing_rows_allowlist_is_not_stale() -> None:
    """`_LEGACY_CITING_ROWS` narrows Leg 1's scope, so it is itself guarded three ways:
    it stays disjoint from the registry, every entry still cites a registered script, and
    every entry still genuinely fails the four-part template parse.

    Without these, the exemption is the one place in this contract where a conforming row
    could be parked outside the guard -- or where an extracted row could keep an
    exemption it no longer needs.
    """
    sentinel_text = SENTINEL_PATH.read_text(encoding="utf-8")
    cited = _rows_by_cited_script(sentinel_text)
    registered_ids = {check_id for check_id, _ in EXTRACTED_CHECKS}
    registered_scripts = {script for _, script in EXTRACTED_CHECKS}

    both = _LEGACY_CITING_ROWS & registered_ids
    assert not both, (
        f"{sorted(both)} are allow-listed as legacy *and* registered in EXTRACTED_CHECKS "
        "-- an extracted row leaves the allow-list in the same commit that registers it"
    )

    citing_registered = {
        row_id for script in registered_scripts for row_id in cited.get(script, set())
    }
    orphans = _LEGACY_CITING_ROWS - citing_registered
    assert not orphans, (
        f"{sorted(orphans)} no longer cite any registered script -- drop them rather "
        "than leaving a scope exemption with nothing behind it"
    )

    for row_id in sorted(_LEGACY_CITING_ROWS):
        pass_column = _pass_column(_find_row(sentinel_text, row_id))
        for citation in _SCRIPT_CITATION.finditer(pass_column):
            script_name = citation.group("script")
            assert _row_pattern(script_name).fullmatch(pass_column) is None, (
                f"{row_id} parses as a four-part template row citing {script_name} -- it "
                "belongs in EXTRACTED_CHECKS, not in the legacy scope exemption"
            )
