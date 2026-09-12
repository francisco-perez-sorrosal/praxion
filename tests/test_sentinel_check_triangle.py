"""The Triangle: catalogue row <-> extraction registry <-> script.

Binds the three corners of a registered check's identity into one three-way set
equality -- catalogue rows citing a script, that script's `EXTRACTED_CHECKS` entry in
`tests/test_sentinel_row_contract.py`, and the check ids the script itself declares --
so none of the three can drift without one of the other two going red. All three legs
are parsed from their own substrate, never hand-listed:

* **Leg 1, document to registry** (`_rows_by_cited_script`): which catalogue rows cite
  a script, wherever the citation appears -- Rule cell or Pass cell, `./`-prefixed or
  not, `python3`-prefixed or not. Broad on purpose: a citation this leg cannot see is a
  row Leg 1 never asks the registry about, which is a drift this Triangle exists to
  catch, not a shape to special-case around.
* **Leg 2, registry to script** and **Leg 3, script to document** (`_declared_check_ids`,
  via `_check_id_declarations`): the check ids a script's own `CHECK_ID`/`CHECK_IDS`
  literal declares, read with `ast.literal_eval` rather than by importing the script.

`_LEGACY_CITING_ROWS` narrows Leg 1 to the extracted surface: `adr_health.py` is cited
by DH01/DH06 in pre-extraction legacy prose as well as by the extracted DH05, so a
script-name-only scope would false-fail on day one. The exemption is itself guarded
(`test_legacy_citing_rows_allowlist_is_not_stale`) so it cannot outlive its rows or
shelter a row that has since become conforming.

Split out of `tests/test_sentinel_row_contract.py` (Step A0 rework) once the file
crossed the 800-line hard ceiling in `rules/swe/coding-style.md` -- the residual-row
contract and the Triangle are cohesive but separable concerns, and this is their seam.
Shared row-parsing helpers (`_TABLE_ROW`, `_pass_column`, `_row_pattern`, `SENTINEL_PATH`,
`SCRIPTS_DIR`, `EXTRACTED_CHECKS`) are imported from that module qualified
(`contract.NAME`), never re-exported by name, so the quantifier meta-guard's
totalising pattern scan (which lives in that module and reaches into this one) never
mistakes a re-exported reference for a pattern this module defines.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md§Pragmatism.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Sequence

import tests.test_sentinel_row_contract as contract

_SCRIPT_NAME_MAX_CHARS = 40  # the longest live script name is
# `check_agent_lifecycle_pairing` (29 chars); 40 leaves room for a longer family script
# name without leaving room for the padding a bare `+` would admit. The slot is bounded
# for the same reason every other slot in this file is: an unbounded name would silently
# widen which rows Leg 1 believes cite a script.
#
# Anchored on `scripts/<name>.py` itself, not on any one cell or invocation phrasing --
# closes two review findings at once: a `./scripts/x.py`-prefixed citation (the negative
# lookbehind excludes a preceding word/slash/dot/hyphen character, so `./` no longer
# defeats it) and a citation living in the Rule cell rather than the Pass cell (Leg 1
# scans the whole row, see `_rows_by_cited_script`, not just the Pass column). The
# trailing `\b` additionally keeps `scripts/x.pyc` from being read as citing `x`.
_SCRIPT_CITATION = re.compile(
    rf"(?<![\w/.-])(?:\./)?scripts/(?P<script>[a-z0-9_]{{1,{_SCRIPT_NAME_MAX_CHARS}}})\.py\b"
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

# This module's own pair of the two pattern-classification registries
# `test_sentinel_row_contract.test_every_module_pattern_is_classified` and
# `test_no_unbounded_quantifier_escapes_the_verdict_slot` scan -- see that module's
# module docstring note on why the totalising scan reaches into this one rather than
# each module carrying its own copy of the meta-guard tests.
_BUDGET_BEARING_PATTERNS: tuple[re.Pattern[str], ...] = (_SCRIPT_CITATION,)
_NON_BUDGET_PATTERNS: dict[re.Pattern[str], str] = {}


def _rows_by_cited_script(sentinel_text: str) -> dict[str, set[str]]:
    """Map each cited script name to the ids of the catalogue rows citing it, anywhere in the row.

    Scans the whole row (`contract._TABLE_ROW`'s full match), not only the Pass column:
    a citation in the Rule cell is exactly as much a citation as one in the Pass cell,
    and confining the scan to one cell was a Leg 1 blind spot the row's own template
    doesn't ask for. A row naming two scripts registers under both; a name longer than
    `_SCRIPT_NAME_MAX_CHARS` is a parse miss rather than a silent accept.

    Scoped to Tp-A (automated) rows: only a Tp=A row actually invokes a script, so only
    it can carry a genuine citation in Leg 1's sense. A Tp=L (LLM-judged) row may still
    *mention* a script's name in explanatory prose without invoking it -- the live
    catalogue's AC09 does exactly this, cross-referencing AC13's script while running no
    script of its own -- and counting that mention as a citation would wrongly demand a
    registry entry for a row that has no script to register. Narrowing on Tp rather than
    exempting AC09 by id keeps the scope a property of the row's own declared type, not
    a second hand-maintained allow-list next to `_LEGACY_CITING_ROWS`.
    """
    by_script: dict[str, set[str]] = {}
    for row in contract._TABLE_ROW.finditer(sentinel_text):
        text = row.group(0)
        if contract._tp_column(text) != "A":
            continue
        for citation in _SCRIPT_CITATION.finditer(text):
            by_script.setdefault(citation.group("script"), set()).add(row.group("id"))
    return by_script


def _check_id_declarations(source: str) -> list[tuple[str, ast.expr]]:
    """Return `(constant_name, value_node)` per module-level CHECK_ID/CHECK_IDS assignment.

    Module level only: a check id assigned inside a function or class is not the declared
    surface a reader of the script's header would see, so it does not count as one.

    Counts `ast.Assign`, `ast.AnnAssign` *and* `ast.AugAssign` targets alike: an
    augmented assignment (`CHECK_IDS += (...)`) after a literal assignment is a SECOND
    declaration, not a silent extension of the first. Without counting it, the
    "exactly one declaration" assertion below would pass while reading back the
    pre-augment value, leaving the appended ids invisible to every leg.
    """
    declarations: list[tuple[str, ast.expr]] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign):
            targets: list[ast.expr] = [node.target]
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
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
# Triangle canaries: one per leg, plus the shapes each leg's parse must not admit
# ---------------------------------------------------------------------------


def _triangle_row(check_id: str) -> str:
    """A four-part template row for `check_id` citing the fixture script `x`."""
    return (
        f"| {check_id} | A | rule | Run `python3 scripts/x.py --json`. verdict text. "
        f"{contract._SPEC_TAIL} |"
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


def test_row_citing_script_with_dotslash_prefix_is_detected_as_a_citation() -> None:
    """Leg 1 canary (F2/P-G): `./scripts/x.py` (dot-slash prefix) must still be detected
    as citing the script -- a second such row with no registry entry fails Leg 1, proving
    the citation was seen rather than silently skipped because of the `./` prefix.
    """
    dotslash = _triangle_row("X02").replace("python3 scripts/x.py", "./scripts/x.py")
    doc = _triangle_doc(_triangle_row("X01"), dotslash)
    try:
        assert_check_registration_triangle(
            doc, [("X01", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
        )
    except AssertionError as exc:
        if "Leg 1" not in str(exc):
            raise AssertionError(f"expected the Leg 1 message, got: {exc}") from exc
        return
    raise AssertionError("a row citing ./scripts/x.py with no registry entry must fail")


def test_row_citing_script_in_rule_cell_is_detected_as_a_citation() -> None:
    """Leg 1 canary (F2/P-H): a row citing the script in its Rule cell, not its Pass
    cell, must still be detected -- a row with no registry entry fails Leg 1 rather than
    being invisible because `_rows_by_cited_script` only looked at the Pass column.
    """
    rule_cell_citation = "| X02 | A | mirrors scripts/x.py | verdict text, no citation here |"
    doc = _triangle_doc(_triangle_row("X01"), rule_cell_citation)
    try:
        assert_check_registration_triangle(
            doc, [("X01", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
        )
    except AssertionError as exc:
        if "Leg 1" not in str(exc):
            raise AssertionError(f"expected the Leg 1 message, got: {exc}") from exc
        return
    raise AssertionError("a row citing the script in its Rule cell must fail Leg 1")


def test_tp_l_row_mentioning_a_script_is_not_a_citation() -> None:
    """Inverse guard (live-catalogue re-probe): a Tp=L row that mentions a registered
    script's name in explanatory prose -- the shape the live catalogue's AC09 takes,
    cross-referencing AC13's script -- must not be read as citing it. Without the Tp=A
    scope, this row would fail Leg 1 for having no registry entry, even though it
    invokes no script at all.
    """
    prose_mention = (
        "| Z09 | L | cross-consistency check | prose that discusses "
        "`scripts/x.py` (AC13's script) without invoking it |"
    )
    doc = _triangle_doc(_triangle_row("X01"), prose_mention)
    assert_check_registration_triangle(
        doc, [("X01", "x")], _fixed_source('CHECK_IDS = ("X01",)\n')
    )  # must not raise


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
        f"`python3 scripts/x.py --json` after fixing. {contract._SPEC_TAIL} |"
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


def test_augmented_assignment_counts_as_a_second_declaration() -> None:
    """Leg 3 parse canary (F2/P-B): `CHECK_IDS = (...)` followed by `CHECK_IDS += (...)`
    at module level must be counted as two declarations, so the "exactly one" assertion
    fires instead of silently reading back the pre-augment value and leaving the
    appended ids invisible.
    """
    source = 'CHECK_IDS = ("X01",)\nCHECK_IDS += ("X99",)\n'
    try:
        assert_check_registration_triangle(
            _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
        )
    except AssertionError as exc:
        if "exactly one" not in str(exc):
            raise AssertionError(f"expected the single-declaration message, got: {exc}") from exc
        return
    raise AssertionError("an AugAssign to CHECK_IDS must count as a second declaration")


def test_annotated_assignment_is_counted_as_the_declaration() -> None:
    """Inverse guard (locks in the `ast.AnnAssign` branch): a single annotated
    assignment (`CHECK_IDS: tuple[str, ...] = (...)`) is counted as the one declaration,
    proving the branch is exercised rather than merely present and untested.
    """
    source = 'CHECK_IDS: tuple[str, ...] = ("X01",)\n'
    assert_check_registration_triangle(
        _triangle_doc(_triangle_row("X01")), [("X01", "x")], _fixed_source(source)
    )  # must not raise


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
# Live-catalogue proof: row, registry and script agree for every registered script
# ---------------------------------------------------------------------------


def _script_source(script_name: str) -> str:
    """Read `scripts/<script_name>.py`, the third leg's substrate."""
    return (contract.SCRIPTS_DIR / f"{script_name}.py").read_text(encoding="utf-8")


def test_every_extracted_check_is_bound_by_the_triangle() -> None:
    """Row, registry and script agree on the check ids of every registered script."""
    assert_check_registration_triangle(
        contract.SENTINEL_PATH.read_text(encoding="utf-8"),
        contract.EXTRACTED_CHECKS,
        _script_source,
    )


def test_legacy_citing_rows_allowlist_is_not_stale() -> None:
    """`_LEGACY_CITING_ROWS` narrows Leg 1's scope, so it is itself guarded three ways:
    it stays disjoint from the registry, every entry still cites a registered script, and
    every entry still genuinely fails the four-part template parse.

    Without these, the exemption is the one place in this contract where a conforming row
    could be parked outside the guard -- or where an extracted row could keep an
    exemption it no longer needs.
    """
    sentinel_text = contract.SENTINEL_PATH.read_text(encoding="utf-8")
    cited = _rows_by_cited_script(sentinel_text)
    registered_ids = {check_id for check_id, _ in contract.EXTRACTED_CHECKS}
    registered_scripts = {script for _, script in contract.EXTRACTED_CHECKS}

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
        pass_column = contract._pass_column(contract._find_row(sentinel_text, row_id))
        for citation in _SCRIPT_CITATION.finditer(pass_column):
            script_name = citation.group("script")
            assert contract._row_pattern(script_name).fullmatch(pass_column) is None, (
                f"{row_id} parses as a four-part template row citing {script_name} -- it "
                "belongs in EXTRACTED_CHECKS, not in the legacy scope exemption"
            )
