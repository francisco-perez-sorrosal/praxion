"""Tests for what a served spawn receives, rendered by ``hooks/_skill_delivery.py``.

The block carries the skill's body as one unaltered substring under a label whose digest names it,
the failure notice says where the skill is without instructing anything, and the arrival matcher
tells a delivered block from everything that only resembles one. None of the delivery's own lines
may carry the marker, or a relayed block would mark a later delegation.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402

BASE_DIR = Path("/plugins/praxion/skills/refactoring")
SKILL_PATH = BASE_DIR / "SKILL.md"
LIVE_SKILL = PLUGIN_ROOT / "skills" / "refactoring" / "SKILL.md"
REASONS = ["skill-unreadable", "skill-read-timeout", "definition-unreadable", "internal-error"]

# Every markdown form a skill body can hold, with the edges a transform would touch: leading and
# trailing blank lines, trailing spaces, tabs, CRLF, a link, a table, fences of both kinds, and a
# line that looks like the delivery's own end line.
ALL_FORMS_BODY = (
    "\n\n# Title  \n\n"
    "Setext\n======\n\n"
    "- item one\n  - nested\t\n"
    "1. numbered\n\n"
    "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
    "[a link](references/patterns.md) and ![img](x.png) and <https://example.com>\n\n"
    "```python\nprint('fenced')\n```\n\n"
    "~~~\ntilde fence\n~~~\n\n"
    "> quoted\n\n"
    "crlf line\r\nnext\r\n\n"
    "[End of skill delivery: refactoring] inside the body\n\n"
    "unicode: café, 日本語\n\n\n"
)


def block_of(body: str) -> str:
    return delivery.render_block(body, BASE_DIR)


def label_line(block: str) -> str:
    return block.splitlines()[0]


def test_block_has_the_label_the_base_directory_the_body_and_the_end_line_in_order():
    body = "Body text.\n"

    block = block_of(body)

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]
    assert block.splitlines() == [
        f"[Skill delivery: refactoring {digest}] {delivery._LABEL_SENTENCE}",
        f"Base directory for this skill: {BASE_DIR}",
        "",
        "Body text.",
        "",
        "[End of skill delivery: refactoring]",
    ]


@pytest.mark.parametrize("body", ["", "no trailing newline", ALL_FORMS_BODY])
def test_the_body_is_one_unaltered_substring_of_the_block(body):
    assert body in block_of(body)


@pytest.mark.skipif(not LIVE_SKILL.is_file(), reason="a mutation sensor's copy holds no skills/")
def test_the_live_skill_body_is_one_unaltered_substring_of_the_block():
    body = LIVE_SKILL.read_text(encoding="utf-8")

    assert body in block_of(body)


@pytest.mark.parametrize("body", ["", "no trailing newline", "ends with newline\n"])
def test_the_end_line_sits_on_a_line_of_its_own_after_the_body(body):
    assert block_of(body).splitlines()[-1] == delivery.END_LINE


def test_the_digest_is_the_first_eight_hex_digits_of_the_bodys_sha256():
    digest = delivery.body_digest("abc")

    assert digest == hashlib.sha256(b"abc").hexdigest()[:8]
    assert len(digest) == 8


def test_the_digest_changes_when_the_body_changes():
    assert delivery.body_digest("body") != delivery.body_digest("body ")
    assert label_line(block_of("body")) != label_line(block_of("body "))


def test_the_label_carries_the_digest_of_the_body_it_delivers():
    label = label_line(block_of(ALL_FORMS_BODY))

    assert f"refactoring {delivery.body_digest(ALL_FORMS_BODY)}]" in label


@pytest.mark.parametrize("body", ["", "x", ALL_FORMS_BODY])
def test_no_delivery_line_carries_the_marker(body):
    block = block_of(body)
    own_lines = [label_line(block), *block.splitlines()[1:2], delivery.END_LINE]

    for line in own_lines:
        assert delivery.MARKER_PATTERN.search(line) is None


@pytest.mark.parametrize("reason", REASONS)
def test_the_notice_names_the_reason_and_the_path_and_carries_no_marker(reason):
    notice = delivery.render_notice(reason, SKILL_PATH)

    assert notice == (
        f"[Skill delivery failed: refactoring ({reason})] The refactoring skill's text was not "
        f"delivered with this delegation; it is at {SKILL_PATH}."
    )
    assert delivery.MARKER_PATTERN.search(notice) is None


# --- The arrival matcher -------------------------------------------------------------------------


def test_the_matcher_is_true_for_a_block_alone_and_inside_a_record():
    block = block_of(ALL_FORMS_BODY)
    record = f"hook context\n{block}\nThe delegation.\n"

    assert delivery.shows_arrival(block)
    assert delivery.shows_arrival(record)


def test_the_matcher_is_false_for_a_failure_notice():
    assert not delivery.shows_arrival(delivery.render_notice("skill-unreadable", SKILL_PATH))


def test_the_matcher_is_false_for_a_bare_body_and_for_an_empty_record():
    assert not delivery.shows_arrival(ALL_FORMS_BODY)
    assert not delivery.shows_arrival("")


@pytest.mark.parametrize(
    "quote",
    [
        "> {label}",
        "`{label}`",
        "see {label}",
        "- {label}",
    ],
    ids=["block-quote", "code-span", "prose", "list-item"],
)
def test_the_matcher_is_false_for_a_quoted_label(quote):
    block = block_of("body\n")
    label = label_line(block)
    quoted_block = block.replace(label, quote.format(label=label), 1)

    assert not delivery.shows_arrival(quoted_block)


def test_the_matcher_is_false_for_a_label_with_no_end_line_after_it():
    block = block_of("body\n")
    without_end = block.removesuffix(delivery.END_LINE)

    assert not delivery.shows_arrival(without_end)
    assert not delivery.shows_arrival(f"{delivery.END_LINE}\n{without_end}")


def test_the_matcher_is_false_for_a_label_with_a_malformed_digest():
    block = block_of("body\n")
    digest = delivery.body_digest("body\n")

    assert not delivery.shows_arrival(block.replace(digest, digest[:7], 1))
    assert not delivery.shows_arrival(block.replace(digest, digest.upper(), 1))


def test_the_matcher_given_the_installed_body_requires_its_digest():
    delivered = "the body that was delivered\n"
    block = block_of(delivered)

    assert delivery.shows_arrival(block, installed_body=delivered)
    assert not delivery.shows_arrival(block, installed_body="a different installed body\n")


def test_the_matcher_given_the_installed_body_finds_the_matching_block_among_labels():
    stale = block_of("stale body\n")
    current = block_of("current body\n")

    assert delivery.shows_arrival(f"{stale}\n{current}", installed_body="current body\n")
