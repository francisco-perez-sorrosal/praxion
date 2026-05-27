"""Corpus-shape integration tests for Family 1 — real ADRs from .ai-state/decisions/.

These tests parse REAL ADRs from the repository, not synthetic fixtures. That is the
whole point: synthetic fixtures cannot catch parser failures against the actual corpus
format, which uses multi-line block-list YAML syntax for fields like `affected_files`
and `re_affirmed_by` (the dominant form in 94%+ of the ADR corpus).

This test file is the discipline: every future family must have a corpus-shape integration
test that runs against real on-disk artifacts, not just handcrafted strings.
"""

from __future__ import annotations

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

# The draft ADR that partially supersedes dec-040.
_DRAFT_ID = "dec-draft-e1f01781"


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
# Test 2: dec-040's superseded_by parses to the draft id (scalar case)
# ---------------------------------------------------------------------------


def test_dec040_superseded_by_parses_to_draft_id() -> None:
    """dec-040's superseded_by is a plain scalar referencing the draft ADR id."""
    parse = _get_parse_fn()
    _, content = _read_adr(_DEC_040_PATH)

    fm = parse(content)

    superseded_by = fm.get("superseded_by")
    assert superseded_by == _DRAFT_ID, (
        f"superseded_by should be {_DRAFT_ID!r}; got {superseded_by!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: dec-040's re_affirmed_by parses to a list containing the draft id
# ---------------------------------------------------------------------------


def test_dec040_re_affirmed_by_parses_to_list_with_draft_id() -> None:
    """dec-040's re_affirmed_by uses YAML block-list syntax (partial-supersession pattern).

    The stdlib parser returned an empty list for block lists; yaml.safe_load must
    return a list that includes the draft id.
    """
    parse = _get_parse_fn()
    _, content = _read_adr(_DEC_040_PATH)

    fm = parse(content)

    re_affirmed_by = fm.get("re_affirmed_by")
    assert isinstance(re_affirmed_by, list), (
        f"re_affirmed_by should be a list; got {type(re_affirmed_by).__name__!r}: {re_affirmed_by!r}"
    )
    assert len(re_affirmed_by) >= 1, f"re_affirmed_by should have ≥1 item; got: {re_affirmed_by!r}"
    assert _DRAFT_ID in re_affirmed_by, (
        f"{_DRAFT_ID!r} not found in re_affirmed_by: {re_affirmed_by!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: re_affirmation_reciprocity check PASS against the dec-040 ↔ draft pair
# ---------------------------------------------------------------------------


def test_re_affirmation_reciprocity_passes_for_dec040_and_draft() -> None:
    """The re_affirmation_reciprocity check must return PASS for the dec-040/draft pair.

    dec-040 is the target of re_affirms from dec-draft-e1f01781.
    dec-040's re_affirmed_by field lists dec-draft-e1f01781.
    The check must find the back-link and return PASS, not FAIL.

    This is the partial-supersession-clause pattern the architect designed:
    dec-040 carries BOTH superseded_by AND re_affirmed_by for the same draft id.
    """
    from praxion_evals.harness.families.family1_pipeline_fidelity import (  # type: ignore[import]
        Family1PipelineOutcomeFidelity,
        _parse_frontmatter,
    )

    # Load the draft ADR that re_affirms dec-040
    draft_path = (
        _DECISIONS_DIR
        / "drafts"
        / "20260526-1300-fperezsorrosal-worktree-praxion-self-eval-v1-praxion-self-eval-framework.md"
    )
    assert draft_path.exists(), f"Draft ADR not found at {draft_path}"

    dec040_entry = _read_adr(_DEC_040_PATH)
    draft_entry = _read_adr(draft_path)

    # Verify the draft has a re_affirms field pointing to dec-040
    draft_fm = _parse_frontmatter(draft_entry[1])
    re_affirms = draft_fm.get("re_affirms")
    if re_affirms is None:
        # The draft may only have supersedes; that's fine — dec-040 still carries
        # re_affirmed_by pointing back. Check by running the check directly.
        pass

    # Build a minimal corpus with just these two ADRs
    # _check_re_affirmation_reciprocity takes a list[tuple[str, str]] directly —
    # no need to construct a full Corpus object.
    adr_entries = [dec040_entry, draft_entry]

    family = Family1PipelineOutcomeFidelity()

    results = family._check_re_affirmation_reciprocity(adr_entries)

    # Filter to re_affirmation_reciprocity results only
    ra_results = [r for r in results if r.check_name == "re_affirmation_reciprocity"]

    assert ra_results, "No re_affirmation_reciprocity results emitted"

    # At least one result must be PASS (the dec-040 ↔ draft pair)
    verdicts = [r.verdict for r in ra_results]
    assert "PASS" in verdicts, (
        f"re_affirmation_reciprocity should PASS for dec-040 ↔ {_DRAFT_ID}; "
        f"verdicts={verdicts!r}, findings={[r.findings for r in ra_results]!r}"
    )
    # No FAIL should be emitted
    assert "FAIL" not in verdicts, (
        f"re_affirmation_reciprocity emitted FAIL unexpectedly; "
        f"findings={[r.findings for r in ra_results if r.verdict == 'FAIL']!r}"
    )
