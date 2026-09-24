"""Corpus-shape integration tests for Family 1 — real ADRs from .ai-state/decisions/.

These tests parse REAL ADR text, not handcrafted YAML strings. That is the whole point:
synthetic fixtures cannot catch parser failures against the actual corpus format, which
uses multi-line block-list YAML syntax for fields like `affected_files` and
`re_affirmed_by` (the dominant form in 94%+ of the ADR corpus).

Two sourcing strategies are used, chosen per test by what the test is actually verifying:

- The corpus-discipline test below (block-list `affected_files`) reads the LIVE corpus —
  its purpose is to catch a parser regression against whatever real-world shapes exist
  today, so it must track the corpus as it evolves.
- The parser-contract and reciprocity-check tests read PINNED fixtures under
  `tests/fixtures/pinned_adr_*.md` — verbatim frontmatter excerpts of real ADRs captured
  at a fixed commit (cited in each fixture's header comment). Their purpose is to verify
  the parser's and the reciprocity check's CONTRACT (scalar round-trips to a string,
  block-list round-trips to a list, a genuine back-link yields PASS) — not whether two
  specific live ADRs currently relate a particular way. Pinning decouples these tests
  from legitimate future corpus edits (a new supersession, a new re-affirmation, an id
  renumbering) while still exercising the real multi-line block-list YAML shape, because
  the excerpts are themselves real corpus text, just frozen in time.

This test file is the discipline: every future family must have a corpus-shape integration
test that runs against real on-disk artifacts, not just handcrafted strings.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve the real decisions directory (relative to this file's repo location)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
_DECISIONS_DIR = _REPO_ROOT / ".ai-state" / "decisions"
_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# dec-020 is a known live-corpus ADR used as a test anchor for the
# corpus-shape test below (block-list affected_files).
_DEC_020_PATH = _DECISIONS_DIR / "020-architecture-md-living-artifact.md"

# Pinned fixtures — verbatim frontmatter excerpts of real ADRs captured at a
# fixed commit (see each fixture's header comment). Used instead of reading
# the live corpus so that a later, legitimate ADR edit (supersession,
# re-affirmation, id renumbering) cannot flip these parser/check-logic tests
# red. What they exercise is the parser's and the reciprocity check's
# CONTRACT — not any one ADR's current fields.
_PINNED_DEC020_PATH = _FIXTURES_DIR / "pinned_adr_dec020.md"
_PINNED_DEC022_PATH = _FIXTURES_DIR / "pinned_adr_dec022.md"
_PINNED_DEC049_PATH = _FIXTURES_DIR / "pinned_adr_dec049.md"


def _read_adr(path: Path) -> tuple[str, str]:
    """Return (str_path, content) for a real ADR file."""
    return str(path), path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper: import _parse_frontmatter lazily (module must exist for tests to pass)
# ---------------------------------------------------------------------------


def _get_parse_fn() -> Any:
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        _parse_frontmatter,  # type: ignore[import]
    )

    return _parse_frontmatter


# ---------------------------------------------------------------------------
# Test 1: dec-020's affected_files is a list with ≥1 item (block-list case)
# ---------------------------------------------------------------------------


def test_dec020_affected_files_parses_to_nonempty_list() -> None:
    """dec-020 uses YAML block-list syntax for affected_files.

    The stdlib parser silently returned an empty string; yaml.safe_load must
    return a proper list.
    """
    parse = _get_parse_fn()
    _, content = _read_adr(_DEC_020_PATH)

    fm = parse(content)

    affected = fm.get("affected_files")
    assert isinstance(affected, list), (
        f"affected_files should be a list; got {type(affected).__name__!r}: {affected!r}"
    )
    assert len(affected) >= 1, f"affected_files should have ≥1 item; got: {affected!r}"
    # Spot-check a known entry
    assert any(".ai-state/ARCHITECTURE.md" in str(item) for item in affected), (
        f".ai-state/ARCHITECTURE.md not found in affected_files: {affected!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: a scalar cross-reference field round-trips to a plain id string
# ---------------------------------------------------------------------------


def test_pinned_scalar_crossref_field_parses_to_plain_id_string() -> None:
    """A plain-scalar cross-reference field (e.g. superseded_by) parses to a bare string.

    Uses a pinned, verbatim frontmatter excerpt (see the fixture's header comment
    for source path and commit) rather than reading the live corpus, so a later
    legitimate ADR edit (e.g. a fresh supersession) cannot turn this test red —
    the fixture's shape is what is under test, not any one ADR's current fields.
    """
    parse = _get_parse_fn()
    _, content = _read_adr(_PINNED_DEC020_PATH)

    fm = parse(content)

    superseded_by = fm.get("superseded_by")
    assert superseded_by == "dec-021", f"superseded_by should be 'dec-021'; got {superseded_by!r}"


# ---------------------------------------------------------------------------
# Test 3: a block-list cross-reference field round-trips to a list of ids
# ---------------------------------------------------------------------------


def test_pinned_list_crossref_field_parses_to_id_list() -> None:
    """A YAML block-list cross-reference field (e.g. re_affirmed_by) parses to a list.

    The stdlib parser silently returns an empty list for block-list syntax;
    yaml.safe_load must return the real list of ids. Uses a pinned, verbatim
    frontmatter excerpt (see the fixture's header comment) rather than the live
    corpus, so a later legitimate re-affirmation added to the real ADR's list
    cannot turn this test red.
    """
    parse = _get_parse_fn()
    _, content = _read_adr(_PINNED_DEC022_PATH)

    fm = parse(content)

    re_affirmed_by = fm.get("re_affirmed_by")
    assert isinstance(re_affirmed_by, list), (
        f"re_affirmed_by should be a list; got {type(re_affirmed_by).__name__!r}: {re_affirmed_by!r}"
    )
    assert len(re_affirmed_by) >= 1, f"re_affirmed_by should have ≥1 item; got: {re_affirmed_by!r}"
    assert "dec-049" in re_affirmed_by, f"'dec-049' not found in re_affirmed_by: {re_affirmed_by!r}"


# ---------------------------------------------------------------------------
# Test 3b: parser correctly handles dec-draft-<hash> format (synthetic fixture)
#
# This synthetic test covers the parser's ability to round-trip the ephemeral
# draft-id format — a format that appears in ADRs during pipeline execution
# (before finalize runs) and in the re_affirmed_by lists of finalized ADRs that
# were partially superseded by a still-in-flight draft. The format constraint
# is: "dec-draft-" prefix followed by an 8-char lowercase hex hash.
# ---------------------------------------------------------------------------

_SYNTHETIC_DRAFT_ID_ADR = textwrap.dedent("""\
    ---
    id: dec-099
    title: Synthetic ADR for draft-id parser coverage
    status: accepted
    category: architectural
    date: "2026-01-01"
    summary: Verifies the parser handles dec-draft-<hash> scalars and lists
    tags: [test]
    made_by: agent
    superseded_by: dec-draft-abcd1234  # id-citation-discipline:ignore
    re_affirmed_by:
      - dec-draft-abcd1234  # id-citation-discipline:ignore
    ---

    ## Context

    Synthetic fixture for parser contract tests.

    ## Decision

    Test only.

    ## Considered Options

    ### Option A

    - (+) Pro

    ## Consequences

    None.
""")


def test_parser_handles_draft_id_scalar_in_superseded_by() -> None:
    """Parser correctly round-trips a dec-draft-<hash> scalar in superseded_by.

    This format appears during pipeline execution before the finalize script
    rewrites draft ids to dec-NNN. The parser must not mangle or lose the value.
    """
    parse = _get_parse_fn()

    fm = parse(_SYNTHETIC_DRAFT_ID_ADR)

    superseded_by = fm.get("superseded_by")
    assert superseded_by == "dec-draft-abcd1234", (  # id-citation-discipline:ignore
        f"superseded_by should be 'dec-draft-abcd1234'; got {superseded_by!r}"  # id-citation-discipline:ignore
    )


def test_parser_handles_draft_id_in_re_affirmed_by_list() -> None:
    """Parser correctly round-trips a dec-draft-<hash> entry in re_affirmed_by block list.

    This covers the partial-supersession-clause pattern where an ADR carries BOTH
    superseded_by and re_affirmed_by pointing to the same draft hash — the standard
    form when a draft narrowly supersedes one clause while re-affirming others.
    """
    parse = _get_parse_fn()

    fm = parse(_SYNTHETIC_DRAFT_ID_ADR)

    re_affirmed_by = fm.get("re_affirmed_by")
    assert isinstance(re_affirmed_by, list), (
        f"re_affirmed_by should be a list; got {type(re_affirmed_by).__name__!r}: {re_affirmed_by!r}"
    )
    assert "dec-draft-abcd1234" in re_affirmed_by, (  # id-citation-discipline:ignore
        f"'dec-draft-abcd1234' not found in re_affirmed_by: {re_affirmed_by!r}"  # id-citation-discipline:ignore
    )


# ---------------------------------------------------------------------------
# Test 4: re_affirmation_reciprocity check PASS against a reciprocal pinned pair
# ---------------------------------------------------------------------------


def test_re_affirmation_reciprocity_passes_for_reciprocal_pinned_pair() -> None:
    """The re_affirmation_reciprocity check finds a real back-link and returns PASS.

    This exercises the check's own logic (does it correctly match a `re_affirms`
    scalar against the target's `re_affirmed_by` list and emit PASS, not whether
    any two specific live ADRs currently reciprocate) — so it is deliberately built
    from a pinned, verbatim two-ADR pair (see each fixture's header comment for
    source path and commit) rather than reading the live corpus. A live-corpus
    version of this test would pin the assertion to whichever two ADRs happen to
    reciprocate today; a later legitimate re-affirmation, supersession, or id
    renumbering elsewhere in the corpus could silently make it vacuous (PASS via
    the check's own "no reciprocation links found, trivially consistent" branch)
    or flip it red — neither of which says anything about the check's logic.

    The pinned pair genuinely reciprocates: dec-049 carries a scalar
    `re_affirms: dec-022`; dec-022 carries a block-list `re_affirmed_by: [dec-049]`.
    That non-trivial linkage is what makes the PASS meaningful — if either id
    were dropped from either field, this test would fail.
    """
    from praxion_evals.harness.families.family1_pipeline_fidelity import (  # type: ignore[import]
        Family1PipelineOutcomeFidelity,
        _parse_frontmatter,
    )

    dec022_entry = _read_adr(_PINNED_DEC022_PATH)
    dec049_entry = _read_adr(_PINNED_DEC049_PATH)

    # Sanity-check the fixture pair actually encodes reciprocity before asking
    # the check to find it — a broken fixture must fail loudly here, not be
    # papered over by the check's own vacuous-PASS branch below.
    dec049_fm = _parse_frontmatter(dec049_entry[1])
    assert dec049_fm.get("re_affirms") == "dec-022", (
        f"fixture dec-049 should have re_affirms: dec-022; got {dec049_fm.get('re_affirms')!r}"
    )

    # _check_re_affirmation_reciprocity takes a list[tuple[str, str]] directly —
    # no need to construct a full Corpus object.
    adr_entries = [dec022_entry, dec049_entry]

    family = Family1PipelineOutcomeFidelity()

    results = family._check_re_affirmation_reciprocity(adr_entries)

    # Filter to re_affirmation_reciprocity results only
    ra_results = [r for r in results if r.check_name == "re_affirmation_reciprocity"]

    assert ra_results, "No re_affirmation_reciprocity results emitted"

    # At least one result must be PASS (the dec-022 ↔ dec-049 pair)
    verdicts = [r.verdict for r in ra_results]
    assert "PASS" in verdicts, (
        f"re_affirmation_reciprocity should PASS for dec-022 ↔ dec-049; "
        f"verdicts={verdicts!r}, findings={[r.findings for r in ra_results]!r}"
    )
    # No FAIL should be emitted
    assert "FAIL" not in verdicts, (
        f"re_affirmation_reciprocity emitted FAIL unexpectedly; "
        f"findings={[r.findings for r in ra_results if r.verdict == 'FAIL']!r}"
    )
