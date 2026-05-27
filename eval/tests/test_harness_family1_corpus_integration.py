"""Corpus-shape integration tests for Family 1 — real ADRs from .ai-state/decisions/.

These tests parse REAL ADRs from the repository, not synthetic fixtures. That is the
whole point: synthetic fixtures cannot catch parser failures against the actual corpus
format, which uses multi-line block-list YAML syntax for fields like `affected_files`
and `re_affirmed_by` (the dominant form in 94%+ of the ADR corpus).

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

# dec-020 and dec-040 are known ADRs used as test anchors.
_DEC_020_PATH = _DECISIONS_DIR / "020-architecture-md-living-artifact.md"
_DEC_040_PATH = _DECISIONS_DIR / "040-eval-framework-out-of-band.md"
_DEC_204_PATH = _DECISIONS_DIR / "204-praxion-self-eval-framework.md"

# The finalized ADR id that superseded dec-040 and was also re-affirmed in its
# re_affirmed_by list. dec-040 carries BOTH superseded_by: dec-204 AND
# re_affirmed_by: [dec-204] to encode the partial-supersession-clause pattern.
_FINALIZED_ID = "dec-204"


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
# Test 2: dec-040's superseded_by parses to the finalized id (scalar case)
# ---------------------------------------------------------------------------


def test_dec040_superseded_by_parses_to_finalized_id() -> None:
    """dec-040's superseded_by is a plain scalar referencing the finalized ADR id.

    The draft that originally superseded dec-040 finalized to dec-204 at merge.
    After finalization, dec-040's superseded_by field carries the permanent id
    (dec-204), not the ephemeral draft hash. The parser must round-trip the
    scalar form correctly.
    """
    parse = _get_parse_fn()
    _, content = _read_adr(_DEC_040_PATH)

    fm = parse(content)

    superseded_by = fm.get("superseded_by")
    assert superseded_by == _FINALIZED_ID, (
        f"superseded_by should be {_FINALIZED_ID!r}; got {superseded_by!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: dec-040's re_affirmed_by parses to a list containing the finalized id
# ---------------------------------------------------------------------------


def test_dec040_re_affirmed_by_parses_to_list_with_finalized_id() -> None:
    """dec-040's re_affirmed_by uses YAML block-list syntax (partial-supersession pattern).

    The stdlib parser returned an empty list for block lists; yaml.safe_load must
    return a list that includes the finalized id. After the draft promoting to dec-204
    at merge, dec-040 carries re_affirmed_by: [dec-204].
    """
    parse = _get_parse_fn()
    _, content = _read_adr(_DEC_040_PATH)

    fm = parse(content)

    re_affirmed_by = fm.get("re_affirmed_by")
    assert isinstance(re_affirmed_by, list), (
        f"re_affirmed_by should be a list; got {type(re_affirmed_by).__name__!r}: {re_affirmed_by!r}"
    )
    assert len(re_affirmed_by) >= 1, f"re_affirmed_by should have ≥1 item; got: {re_affirmed_by!r}"
    assert _FINALIZED_ID in re_affirmed_by, (
        f"{_FINALIZED_ID!r} not found in re_affirmed_by: {re_affirmed_by!r}"
    )


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
    superseded_by: dec-draft-abcd1234
    re_affirmed_by:
      - dec-draft-abcd1234
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
    assert superseded_by == "dec-draft-abcd1234", (
        f"superseded_by should be 'dec-draft-abcd1234'; got {superseded_by!r}"
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
    assert "dec-draft-abcd1234" in re_affirmed_by, (
        f"'dec-draft-abcd1234' not found in re_affirmed_by: {re_affirmed_by!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: re_affirmation_reciprocity check PASS against the dec-040 ↔ dec-204 pair
# ---------------------------------------------------------------------------


def test_re_affirmation_reciprocity_passes_for_dec040_and_dec204() -> None:
    """The re_affirmation_reciprocity check must return PASS for the dec-040/dec-204 pair.

    dec-040 is the target of re_affirms from dec-204.
    dec-040's re_affirmed_by field lists dec-204.
    The check must find the back-link and return PASS, not FAIL.

    This is the partial-supersession-clause pattern the architect designed:
    dec-040 carries BOTH superseded_by AND re_affirmed_by for the same id (dec-204),
    encoding that dec-204 narrowly superseded one clause while re-affirming others.
    """
    from praxion_evals.harness.families.family1_pipeline_fidelity import (  # type: ignore[import]
        Family1PipelineOutcomeFidelity,
        _parse_frontmatter,
    )

    assert _DEC_204_PATH.exists(), f"Finalized ADR dec-204 not found at {_DEC_204_PATH}"

    dec040_entry = _read_adr(_DEC_040_PATH)
    dec204_entry = _read_adr(_DEC_204_PATH)

    # Verify dec-204 has a re_affirms field or supersedes field pointing to dec-040
    dec204_fm = _parse_frontmatter(dec204_entry[1])
    supersedes = dec204_fm.get("supersedes")
    assert supersedes == "dec-040", f"dec-204 should have supersedes: dec-040; got {supersedes!r}"

    # Build a minimal corpus with just these two ADRs
    # _check_re_affirmation_reciprocity takes a list[tuple[str, str]] directly —
    # no need to construct a full Corpus object.
    adr_entries = [dec040_entry, dec204_entry]

    family = Family1PipelineOutcomeFidelity()

    results = family._check_re_affirmation_reciprocity(adr_entries)

    # Filter to re_affirmation_reciprocity results only
    ra_results = [r for r in results if r.check_name == "re_affirmation_reciprocity"]

    assert ra_results, "No re_affirmation_reciprocity results emitted"

    # At least one result must be PASS (the dec-040 ↔ dec-204 pair)
    verdicts = [r.verdict for r in ra_results]
    assert "PASS" in verdicts, (
        f"re_affirmation_reciprocity should PASS for dec-040 ↔ {_FINALIZED_ID}; "
        f"verdicts={verdicts!r}, findings={[r.findings for r in ra_results]!r}"
    )
    # No FAIL should be emitted
    assert "FAIL" not in verdicts, (
        f"re_affirmation_reciprocity emitted FAIL unexpectedly; "
        f"findings={[r.findings for r in ra_results if r.verdict == 'FAIL']!r}"
    )
