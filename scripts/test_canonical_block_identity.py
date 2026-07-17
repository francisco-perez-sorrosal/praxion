"""Unit tests for scripts/canonical_block_identity.py.

Tests are designed from the shared identity module's behavioral contract
(the single normalization + hashing + extraction primitives shared by the
history-manifest generator and the consumer refresh script), not from
reading the production implementation, which does not exist yet at the time
these tests are written.

Three behavioral areas:

1. **normalize_block_body / hash_block_body**: a body hashes identically
   regardless of whitespace, trailing-newline, or leading-blank-line noise —
   the invariant that keeps a block appended in its real on-disk shape from
   being misclassified relative to its canonical source. A negative control
   (two genuinely different bodies) proves the hash is not a constant.
2. **REFRESHABLE_SLUGS**: the exact, closed set of eligible block slugs —
   never more (conditional/template blocks), never fewer.
3. **extract_live_body**: the heading-to-next-heading-or-EOF extraction
   boundary, including the determinism guarantee when a heading appears more
   than once in the target file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

# A synthetic block body used across the normalization/hashing tests. Shaped
# like a real canonical block (heading line + prose) without depending on any
# specific real canonical file's content.
SAMPLE_BLOCK_BODY = "## Agent Pipeline\n\nSome canonical prose.\n\nSecond paragraph.\n"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_module():
    """Import canonical_block_identity lazily (ensures a fresh module each call)."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import canonical_block_identity as mod

    return importlib.reload(mod)


# ---------------------------------------------------------------------------
# normalize_block_body / hash_block_body: round-trip stability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "variant_body"),
    [
        ("trailing_blank_line", SAMPLE_BLOCK_BODY + "\n"),
        ("trailing_whitespace_on_last_line", SAMPLE_BLOCK_BODY.rstrip("\n") + "   \n"),
        ("multiple_trailing_newlines", SAMPLE_BLOCK_BODY + "\n\n\n"),
        ("single_leading_blank_line", "\n" + SAMPLE_BLOCK_BODY),
        ("multiple_leading_blank_lines", "\n\n\n" + SAMPLE_BLOCK_BODY),
    ],
)
def test_hash_is_stable_across_whitespace_and_blank_line_variants(
    label: str, variant_body: str
) -> None:
    """A body carrying whitespace/blank-line noise — the shape a block actually
    takes once appended into a target file — hashes identically to its clean
    canonical form. A gap here would misclassify an unmodified stale block as
    locally customized."""
    mod = _load_module()

    canonical_hash = mod.hash_block_body(SAMPLE_BLOCK_BODY)
    variant_hash = mod.hash_block_body(variant_body)

    assert variant_hash == canonical_hash, (
        f"variant '{label}' hashed differently from the clean body — "
        "a normalization gap would misclassify an unmodified block"
    )


def test_hash_differs_for_semantically_different_bodies() -> None:
    """Two bodies with genuinely different prose hash to different values —
    hash_block_body actually discriminates content rather than collapsing
    everything to one value (the negative control for the stability tests
    above)."""
    mod = _load_module()

    hash_a = mod.hash_block_body(SAMPLE_BLOCK_BODY)
    hash_b = mod.hash_block_body("## Agent Pipeline\n\nCompletely unrelated prose.\n")

    assert hash_a != hash_b


def test_hash_block_body_returns_a_sha256_hex_digest() -> None:
    """hash_block_body returns a 64-character lowercase hex string — the exact
    shape the shipped history manifest stores for every historical body hash,
    so the generator and the consumer script agree on a wire format."""
    mod = _load_module()

    digest = mod.hash_block_body(SAMPLE_BLOCK_BODY)

    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(char in "0123456789abcdef" for char in digest)


def test_normalize_block_body_is_idempotent() -> None:
    """Normalizing an already-normalized body a second time is a no-op —
    normalize_block_body converges to a fixed point rather than continuing to
    mutate its own output."""
    mod = _load_module()

    once = mod.normalize_block_body(SAMPLE_BLOCK_BODY + "\n\n   \n")
    twice = mod.normalize_block_body(once)

    assert twice == once


def test_normalize_block_body_collapses_trailing_noise_to_one_newline() -> None:
    """A body with trailing spaces and multiple trailing blank lines normalizes
    to end with exactly one newline and no trailing whitespace."""
    mod = _load_module()

    normalized = mod.normalize_block_body("## Heading\n\nBody.   \n\n\n")

    assert normalized.endswith("Body.\n")
    assert not normalized.endswith("\n\n")


def test_normalize_block_body_strips_leading_blank_lines() -> None:
    """A body carrying leading blank lines — the separator a project inserts
    before an appended block — normalizes to start directly at the heading
    line, with no leading blank lines surviving."""
    mod = _load_module()

    normalized = mod.normalize_block_body("\n\n## Heading\n\nBody.\n")

    assert normalized.startswith("## Heading")


# ---------------------------------------------------------------------------
# REFRESHABLE_SLUGS: closed membership set
# ---------------------------------------------------------------------------


def test_refreshable_slugs_is_exactly_the_four_eligible_blocks() -> None:
    """REFRESHABLE_SLUGS names exactly the four unconditional, byte-identical
    blocks — never more (template-filled or conditionally-installed blocks),
    never fewer — and is immutable (a frozenset), so no runtime code can grow
    or shrink the eligible set."""
    mod = _load_module()

    assert mod.REFRESHABLE_SLUGS == frozenset(
        {
            "agent-pipeline",
            "compaction-guidance",
            "behavioral-contract",
            "praxion-process",
        }
    )
    assert isinstance(mod.REFRESHABLE_SLUGS, frozenset)


# ---------------------------------------------------------------------------
# extract_live_body: heading-to-next-heading-or-EOF boundary
# ---------------------------------------------------------------------------


def test_extract_live_body_returns_none_when_heading_absent() -> None:
    """A target file that never had the block installed returns None — there
    is no live body to extract or classify."""
    mod = _load_module()

    claude_md = "## Working in this project\n\nSome template prose.\n"

    result = mod.extract_live_body(claude_md, "## Agent Pipeline")

    assert result is None


def test_extract_live_body_reads_through_eof_when_block_is_last_in_file() -> None:
    """When the target heading's section is the final content in the file,
    extraction returns everything from the heading through EOF — there is no
    trailing heading to bound it."""
    mod = _load_module()

    claude_md = (
        "## Working in this project\n\nTemplate prose.\n\n"
        "## Agent Pipeline\n\nLive body content.\nSecond line.\n"
    )

    result = mod.extract_live_body(claude_md, "## Agent Pipeline")

    assert result == "## Agent Pipeline\n\nLive body content.\nSecond line.\n"


def test_extract_live_body_does_not_truncate_at_non_h2_content() -> None:
    """Content that looks heading-like but is not a top-level '## ' heading —
    a '### ' subheading, or a new paragraph — stays inside the extracted
    body. Only a literal '## ' line bounds the section, so a block's own
    internal structure is never mistaken for the next block."""
    mod = _load_module()

    claude_md = (
        "## Agent Pipeline\n\nLive body.\n\n### Not a section boundary\n\nMore prose.\n\n"
        "## Compaction Guidance\n\nNext block.\n"
    )

    result = mod.extract_live_body(claude_md, "## Agent Pipeline")

    assert result == (
        "## Agent Pipeline\n\nLive body.\n\n### Not a section boundary\n\nMore prose.\n\n"
    )


def test_extract_live_body_uses_first_occurrence_when_heading_appears_twice() -> None:
    """A target file with the injectable heading duplicated extracts the FIRST
    occurrence deterministically — never the second occurrence, and never a
    fused merge of both bodies."""
    mod = _load_module()

    claude_md = (
        "## Agent Pipeline\n\nFirst occurrence body.\n\n"
        "## Compaction Guidance\n\nUnrelated block.\n\n"
        "## Agent Pipeline\n\nSecond occurrence body (must be ignored).\n"
    )

    result = mod.extract_live_body(claude_md, "## Agent Pipeline")

    assert result == "## Agent Pipeline\n\nFirst occurrence body.\n\n"


# ---------------------------------------------------------------------------
# End-to-end identity round trip
# ---------------------------------------------------------------------------


def test_extracted_live_body_hashes_identically_to_its_canonical_source() -> None:
    """A block appended into a target file in its real shape (a blank-line
    separator before the heading) round-trips through extraction and hashing
    to the same hash as its clean canonical source — the invariant that keeps
    the generator's and the consumer's hashes from ever diverging."""
    mod = _load_module()
    canonical_body = "## Agent Pipeline\n\nCanonical prose.\n"

    claude_md = "## Working in this project\n\nTemplate.\n\n" + canonical_body

    extracted = mod.extract_live_body(claude_md, "## Agent Pipeline")

    assert mod.hash_block_body(extracted) == mod.hash_block_body(canonical_body)


def test_hash_of_real_canonical_body_survives_realistic_append_shape() -> None:
    """The real, shipped agent-pipeline canonical file — embedded into a
    target file with the blank-line separator a project actually inserts
    before an appended block — hashes identically to the canonical file's own
    content. Proves the round trip holds for real content, not just a
    synthetic fixture."""
    mod = _load_module()
    canonical_path = REPO_ROOT / "claude" / "canonical-blocks" / "agent-pipeline.md"
    canonical_body = canonical_path.read_text(encoding="utf-8")

    claude_md = "## Working in this project\n\nTemplate prose.\n\n" + canonical_body

    extracted = mod.extract_live_body(claude_md, "## Agent Pipeline")

    assert mod.hash_block_body(extracted) == mod.hash_block_body(canonical_body)
