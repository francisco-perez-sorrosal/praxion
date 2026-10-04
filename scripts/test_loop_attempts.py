"""Tests for the `Attempts:` grammar and its reading (``scripts/_loop_fields.py``).

The grammar is table-tested, the merge across lines is a property (the
highest count, whatever the line order), and a non-interference proof shows
the step-claim reader returns the same claims with and without the lines.
"""

from __future__ import annotations

import itertools
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _loop_fields as fields  # noqa: E402
import _step_schema as schema  # noqa: E402


def label(number: int | str) -> str:
    """A step's label as the step-document readers key it."""
    return f"Step {number}"


def attempts_line(step: int | str, count: int | str, replan: str | None = None) -> str:
    tail = f" [BLOCKED] replan: {replan}" if replan is not None else ""
    return f"  - Attempts: {label(step)} count={count}{tail}"


# ---------------------------------------------------------------------------
# The grammar: valid forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "- Attempts: {step} count=1",
        "  - Attempts: {step} count=1",
        "* Attempts: {step} count=1",
        "  - **Attempts**: {step} count=1",
        "  - **Attempts:** {step} count=1",
        "  -   Attempts:   {step}   count=1   ",
    ],
)
def test_every_accepted_form_reads_the_same_step_and_count(line: str) -> None:
    reading = fields.parse_attempts(line.format(step=label(3)))

    assert reading.counts == {label(3): fields.Attempt(1)}
    assert reading.unreadable == {}


def test_a_step_id_with_a_letter_suffix_is_read() -> None:
    reading = fields.parse_attempts(attempts_line("1b", 2))

    assert reading.counts == {label("1b"): fields.Attempt(2)}


def test_the_replan_text_follows_the_blocked_marker_on_the_same_line() -> None:
    text = attempts_line(6, 2, "the first attempt ran out of turns; the second broke the parser")

    reading = fields.parse_attempts(text)

    assert reading.counts[label(6)] == fields.Attempt(
        2, "the first attempt ran out of turns; the second broke the parser"
    )


def test_a_step_with_no_line_has_no_count_and_is_not_unreadable() -> None:
    reading = fields.parse_attempts(attempts_line(3, 1))

    assert label(4) not in reading.counts
    assert label(4) not in reading.unreadable
    assert fields.parse_attempts("") == fields.AttemptsReading({}, {})


# ---------------------------------------------------------------------------
# The grammar: lines that break it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "  - Attempts: {step} count=0",
        "  - Attempts: {step} count=",
        "  - Attempts: {step} count=x",
        "  - Attempts: {step} count=-1",
        "  - Attempts: {step} count=2 extra",
        "  - Attempts: {step} count=2 [BLOCKED] replan:",
        "  - Attempts: {step} count=2 [BLOCKED] no colon",
        "  - Attempts: {step} attempts=2",
        "  - Attempts: {step}",
    ],
)
def test_a_line_that_breaks_the_grammar_is_unreadable_under_its_step(line: str) -> None:
    reading = fields.parse_attempts(line.format(step=label(3)))

    assert reading.counts == {}
    assert list(reading.unreadable) == [label(3)]
    assert reading.unreadable[label(3)]


@pytest.mark.parametrize(
    ("line", "unnamed"),
    [
        ("  - Attempts: count=2", "count=2"),
        ("  - Attempts: three attempts so far", "three attempts so far"),
        ("  - Attempts: step 3 count=2", "step 3 count=2"),
        ("  - Attempts: 3 count=2", "3 count=2"),
        ("  - Attempts:", ""),
    ],
)
def test_a_broken_line_naming_no_step_is_listed_as_unnamed_and_gives_no_count(
    line: str, unnamed: str
) -> None:
    assert fields.parse_attempts(line) == fields.AttemptsReading({}, {}, (unnamed,))


def test_an_unnamed_line_does_not_disturb_a_readable_one_or_an_unreadable_one() -> None:
    text = "\n".join(
        [
            f"  - Attempts: {label(1)} count=2",
            "  - Attempts: step 2 count=1",
            f"  - Attempts: {label(3)} count=zero",
        ]
    )

    reading = fields.parse_attempts(text)

    assert reading.counts == {label(1): fields.Attempt(2)}
    assert list(reading.unreadable) == [label(3)]
    assert reading.unnamed == ("step 2 count=1",)


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] Attempts: {step} count=1",
        "Attempts: {step} count=1",
        "  - attempts: {step} count=1",
        "  - Attempts so far: {step} count=1",
        "  - Retry attempts: {step} count=1",
    ],
)
def test_a_line_that_is_not_an_attempts_sub_bullet_is_not_read(line: str) -> None:
    assert fields.parse_attempts(line.format(step=label(3))) == fields.AttemptsReading({}, {})


def test_a_count_below_one_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        fields.Attempt(0)


# ---------------------------------------------------------------------------
# Merging two lines for one step: the highest count, whatever the order
# ---------------------------------------------------------------------------

_LINES = (
    attempts_line(3, 1),
    attempts_line(3, 2),
    attempts_line(3, 2, "stopped on the cap"),
    attempts_line(3, 1, "an old replan"),
    attempts_line(3, 2, "a different replan"),
)


def test_the_merge_is_the_same_maximum_for_every_order_of_the_lines() -> None:
    results = {
        fields.parse_attempts("\n".join(order)).counts[label(3)]
        for order in itertools.permutations(_LINES)
    }

    assert len(results) == 1
    (merged,) = results
    assert merged.count == 2
    assert merged.replan == "stopped on the cap"


def test_a_stale_lower_line_never_lowers_the_count_or_replaces_the_replan() -> None:
    text = "\n".join((attempts_line(3, 2, "the replan"), attempts_line(3, 1, "stale")))

    assert fields.parse_attempts(text).counts[label(3)] == fields.Attempt(2, "the replan")


def test_steps_are_kept_apart_and_a_good_and_a_broken_line_for_one_step_both_show() -> None:
    text = "\n".join((attempts_line(3, 1), attempts_line(4, 2), attempts_line(3, "zero")))

    reading = fields.parse_attempts(text)

    assert reading.counts == {label(3): fields.Attempt(1), label(4): fields.Attempt(2)}
    assert list(reading.unreadable) == [label(3)]


# ---------------------------------------------------------------------------
# Where the line is read: outside code fences, one line only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_a_line_inside_a_code_fence_is_not_read(fence: str) -> None:
    text = f"{fence}\n{attempts_line(3, 2)}\n{fence}\n{attempts_line(4, 1)}\n"

    assert fields.parse_attempts(text).counts == {label(4): fields.Attempt(1)}


def test_a_replan_text_that_continues_onto_a_second_line_is_read_only_to_the_line_end() -> None:
    first = attempts_line(3, 2, "the first attempt stopped on the cap,")
    text = first + "\n    and the second broke\n"

    assert fields.parse_attempts(text).counts[label(3)] == fields.Attempt(
        2, "the first attempt stopped on the cap,"
    )


def test_the_cap_is_two_fresh_attempts() -> None:
    assert fields.ATTEMPT_CAP == 2


# ---------------------------------------------------------------------------
# Non-interference: the step-claim reader does not see the lines
# ---------------------------------------------------------------------------

_BARE_SEQUENTIAL = (
    "## Progress\n\n"
    f"- [x] {label(1)}: first\n"
    f"- [ ] {label(2)}: second\n"
    f"- [x] {label(3)}: third **[AUTO-RECOVERED 2026-10-04T10:00Z]**\n"
    f"- [ ] {label(4)}: fourth\n"
)

_BARE_PARALLEL = (
    "## Current Batch\n\n"
    "| Step | Assignee | Status | Files |\n"
    "|---|---|---|---|\n"
    "| 5 | implementer | complete | `a.py` |\n"
    "| 6 | implementer | in-progress | `b.py` |\n\n"
    f"## {label(5)} \u2014 the fifth  `[x]`\n\n"
    f"## {label(6)} \u2014 the sixth  `[ ]`\n"
)


_STEP_HEADING_RE = re.compile(r"^#+ Step (?P<id>\w+)")


def under_each_step_entry(text: str) -> str:
    """The same document with an `Attempts:` sub-bullet under every step entry."""
    out: list[str] = []
    for line in text.splitlines():
        out.append(line)
        step = schema.checklist_step_id(line)
        heading = _STEP_HEADING_RE.match(line)
        step = step or (label(heading["id"]) if heading else None)
        if step is not None:
            out.append(attempts_line(step.removeprefix("Step "), 2, "stopped on the cap"))
    return "\n".join(out) + "\n"


def as_trailing_lines(text: str) -> str:
    """The same document with one `Attempts:` line per step appended at the end."""
    return text + "\n" + "\n".join(attempts_line(n, 1) for n in range(1, 7)) + "\n"


@pytest.mark.parametrize("bare", [_BARE_SEQUENTIAL, _BARE_PARALLEL], ids=["sequential", "parallel"])
@pytest.mark.parametrize("decorate", [under_each_step_entry, as_trailing_lines])
def test_step_claims_are_identical_with_and_without_attempts_lines(
    bare: str, decorate: Callable[[str], str]
) -> None:
    decorated = decorate(bare)

    assert decorated != bare
    assert schema.parse_wip_claims(bare)
    assert schema.parse_wip_claims(decorated) == schema.parse_wip_claims(bare)


def test_the_auto_recovered_suffix_checklist_line_keeps_its_claim_beside_an_attempts_line() -> None:
    text = _BARE_SEQUENTIAL + attempts_line(3, 1) + "\n"

    assert schema.parse_wip_claims(text)[label(3)] == "COMPLETE"
    assert fields.parse_attempts(text).counts == {label(3): fields.Attempt(1)}
