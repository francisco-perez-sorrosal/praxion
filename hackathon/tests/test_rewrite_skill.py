"""Tests for is_safe_rewrite() — 4-condition sanity check.

All tests are pure function calls: no LLM, no Cognee, no filesystem.
The 7 mandatory cases cover the full boundary space of the 4 conditions.
"""

from __future__ import annotations

from hackathon.rewrite_skill import is_safe_rewrite

# ---------------------------------------------------------------------------
# Minimal well-formed SKILL.md skeleton used as the "old" baseline.
# Has frontmatter, one section (## Gotchas), and no fenced python blocks.
# ---------------------------------------------------------------------------
_BASE_SKILL = """\
---
name: code-review
description: Structured code review methodology.
---

# Code Review

## Gotchas

- **Existing bullet**: Watch for this pattern.

## Relationship to coding-style Rule

Content here.
"""


def _make_new(
    extra_bullet: str = "", frontmatter_extra: str = "", extra_section: str = ""
) -> str:
    """Build a new SKILL.md from the base with optional modifications."""
    fm = f"---\nname: code-review\ndescription: Structured code review methodology.{frontmatter_extra}\n---"
    gotchas = "## Gotchas\n\n- **Existing bullet**: Watch for this pattern.\n"
    if extra_bullet:
        gotchas += extra_bullet + "\n"
    rest = "\n## Relationship to coding-style Rule\n\nContent here.\n"
    if extra_section:
        rest += extra_section
    return f"{fm}\n\n# Code Review\n\n{gotchas}{rest}"


# ---------------------------------------------------------------------------
# Helper to build a fenced python block with N code lines.
# N lines → N \n chars inside the block.
# ---------------------------------------------------------------------------
def _python_block(n_lines: int) -> str:
    lines = "\n".join(f"    x = {i}" for i in range(n_lines))
    return f"\n```python\n{lines}\n```\n"


# ---------------------------------------------------------------------------
# Case 1 — happy path: Gotcha-only append, well within all 4 limits.
# delta ~150 chars, frontmatter unchanged, no new sections, no python blocks.
# ---------------------------------------------------------------------------
def test_gotcha_only_append_passes() -> None:
    new = _make_new(
        extra_bullet="- **New gotcha**: Mutable defaults share state across calls."
    )
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is True
    assert reason is None


# ---------------------------------------------------------------------------
# Case 2 — boundary: delta exactly 399 chars → still passes (< 400).
# ---------------------------------------------------------------------------
def test_size_delta_399_passes() -> None:
    # _make_new appends extra_bullet + "\n" to the gotchas block.
    # The bullet prefix "- **Padded**: " is 14 chars; the trailing "\n" is 1 char.
    # Total extra chars = len(prefix) + len(padding) + 1.
    # Solve for len(padding): padding_len = 399 - len(prefix) - 1
    prefix = "- **Padded**: "
    padding = "x" * (399 - len(prefix) - 1)
    new = _make_new(extra_bullet=f"{prefix}{padding}")
    delta = len(new) - len(_BASE_SKILL)
    assert delta == 399, f"test setup: expected delta=399, got {delta}"
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is True
    assert reason is None


# ---------------------------------------------------------------------------
# Case 3 — boundary: delta exactly 400 chars → fails (not < 400, strict).
# ---------------------------------------------------------------------------
def test_size_delta_400_fails() -> None:
    prefix = "- **Padded**: "
    padding = "x" * (400 - len(prefix) - 1)
    new = _make_new(extra_bullet=f"{prefix}{padding}")
    delta = len(new) - len(_BASE_SKILL)
    assert delta == 400, f"test setup: expected delta=400, got {delta}"
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is False
    assert reason is not None
    assert "size delta" in reason


# ---------------------------------------------------------------------------
# Case 4 — frontmatter mutated (one field added) → fails.
# ---------------------------------------------------------------------------
def test_frontmatter_mutation_fails() -> None:
    new = _make_new(frontmatter_extra="\nallowed-tools: [Read]")
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is False
    assert reason is not None
    assert "frontmatter" in reason


# ---------------------------------------------------------------------------
# Case 5 — new ## section added → fails.
# ---------------------------------------------------------------------------
def test_new_section_added_fails() -> None:
    new = _make_new(extra_section="\n## New Section\n\nExtra content.\n")
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is False
    assert reason is not None
    assert "section" in reason


# ---------------------------------------------------------------------------
# Case 6 — fenced python block of exactly 8 lines → passes (≤ 8 boundary).
# The block itself is small enough not to trip the size-delta limit.
# ---------------------------------------------------------------------------
def test_python_block_8_lines_passes() -> None:
    block = _python_block(8)
    new = _make_new(extra_bullet=block)
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is True, f"expected True but got False: {reason}"
    assert reason is None


# ---------------------------------------------------------------------------
# Case 7 — fenced python block of 9 lines → fails (> 8).
# ---------------------------------------------------------------------------
def test_python_block_9_lines_fails() -> None:
    block = _python_block(9)
    new = _make_new(extra_bullet=block)
    passed, reason = is_safe_rewrite(_BASE_SKILL, new)
    assert passed is False
    assert reason is not None
    assert "fenced python block" in reason
