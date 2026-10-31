"""Tests for _resident_of.py -- the single reader of a resident file's `resident_of:` key."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _resident_of import resident_parent  # noqa: E402

PARENT = "rules/swe/adr-conventions.md"


def test_the_declared_parent_path_is_returned() -> None:
    text = f"---\ncore: true\nresident_of: {PARENT}\nload: always_on\n---\n## Rule\n"

    assert resident_parent(text) == PARENT


@pytest.mark.parametrize("value", [f"'{PARENT}'", f'"{PARENT}"', f"  {PARENT}  "])
def test_quotes_and_padding_around_the_value_are_not_part_of_the_path(value: str) -> None:
    assert resident_parent(f"---\nresident_of: {value}\n---\nBody\n") == PARENT


@pytest.mark.parametrize(
    "text",
    [
        "## Rule\n\nNo frontmatter at all.\n",
        "---\ncore: true\n---\n## Rule\n",
        "---\nresident_of:\n---\n## Rule\n",
        "---\nresident_of: ''\n---\n## Rule\n",
        "---\nnote:\n  resident_of: nested\n---\n## Rule\n",
        "---\nmy_resident_of: x\n---\n## Rule\n",
    ],
)
def test_a_file_that_declares_no_parent_has_none(text: str) -> None:
    assert resident_parent(text) is None


@pytest.mark.parametrize(
    "text",
    [
        f"---\ncore: true\n## Rule\nresident_of: {PARENT}\n",
        f"---\ndescription: x\n---\nresident_of: {PARENT}\n",
        f"## Rule\n\nresident_of: {PARENT}\n",
    ],
)
def test_the_key_outside_closed_frontmatter_declares_nothing(text: str) -> None:
    assert resident_parent(text) is None
