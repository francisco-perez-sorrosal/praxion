"""Tests for the review file's current round: the text above its superseded-record heading.

A round-2 reviewer keeps the first round's record below its own review, under a heading naming
it superseded. `file_verdict` reads the last `verdict:` line above that boundary, and the whole
file when there is none. Every case passes text in and reads a value out: nothing is mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import PromptInputs, RequestKey, render_prompt, spawn_request  # noqa: E402
from _step_loop_review import SUPERSEDED_HEADING, file_verdict  # noqa: E402

ROUND_ONE_RECORD = "verdict: revise\nfindings:\n  - id: F1\n"
WORK = "/repo/.ai-work/demo"
STEP = "Step "


def second_round_file(own: str, boundary: str, separator: str = "---\n\n") -> str:
    """A round-2 file: its own review, an optional separator, the boundary, round 1's record."""
    return f"{own}\n{separator}{boundary}\n\n{ROUND_ONE_RECORD}"


@pytest.mark.parametrize(
    "boundary",
    [
        pytest.param("## Superseded round-1 record", id="level-two"),
        pytest.param("# Superseded round-1 record", id="level-one"),
        pytest.param("###### Superseded round-1 record", id="level-six"),
        pytest.param("## SUPERSEDED round-1 record", id="upper-case"),
        pytest.param("## superseded", id="lower-case-alone"),
        pytest.param("## The superseded record of round 1", id="word-inside-the-heading"),
        pytest.param("##\tSuperseded round-1 record", id="tab-after-the-hashes"),
    ],
)
@pytest.mark.parametrize("separator", ["---\n\n", ""], ids=["after-a-separator", "no-separator"])
def test_a_verdict_above_a_superseded_heading_is_the_files_verdict(boundary, separator):
    text = second_round_file(
        "verdict: accept\nnotes: the revision derives it.\n", boundary, separator
    )

    assert file_verdict(text) == "accept"


@pytest.mark.parametrize(
    "boundary",
    [
        pytest.param("####### Superseded round-1 record", id="seven-hashes"),
        pytest.param("##Superseded round-1 record", id="no-space-after-the-hashes"),
        pytest.param("Superseded round-1 record", id="no-hashes"),
        pytest.param("## Earlier round-1 record", id="heading-without-the-word"),
        pytest.param("## Unsuperseded round-1 record", id="word-inside-a-longer-word"),
        pytest.param("   ## Superseded round-1 record", id="indented"),
    ],
)
def test_a_line_that_is_not_a_superseded_heading_is_no_boundary(boundary):
    text = second_round_file("verdict: accept\n", boundary)

    assert file_verdict(text) == "revise"


def test_a_separator_alone_is_no_boundary():
    assert file_verdict("verdict: accept\n---\nverdict: revise\n") == "revise"


def test_the_last_verdict_above_the_boundary_decides():
    text = second_round_file(
        "verdict: [PARTIAL]\nfindings: []\nverdict: accept\n", SUPERSEDED_HEADING
    )

    assert file_verdict(text) == "accept"


def test_text_above_the_first_of_two_boundaries_is_the_current_round():
    text = (
        "verdict: accept\n\n## Superseded round-2 record\n\nverdict: revise\n\n"
        "## Superseded round-1 record\n\nverdict: partial\n"
    )

    assert file_verdict(text) == "accept"


def test_a_round_whose_own_verdict_is_revise_still_reads_revise():
    text = second_round_file("verdict: revise\nfindings:\n  - id: F2\n", SUPERSEDED_HEADING)

    assert file_verdict(text) == "revise"


def test_a_verdict_only_below_the_boundary_is_no_verdict():
    assert file_verdict(f"findings: none\n\n{SUPERSEDED_HEADING}\n\nverdict: revise\n") is None


def test_a_single_round_file_reads_by_its_last_verdict_as_before():
    assert file_verdict("verdict: [PARTIAL]\nfindings:\nverdict: accept\n") == "accept"


def test_the_heading_a_prompt_names_is_one_a_reader_takes_for_the_boundary():
    own = "verdict: accept\n"

    assert file_verdict(f"{own}\n{SUPERSEDED_HEADING}\n\n{ROUND_ONE_RECORD}") == "accept"


def review_prompt(round_: int) -> str:
    step = parse_plan_steps(
        f"### {STEP}7: Add the widget\n\n**Assignee**: implementer\n"
        "**Implementation**: Build it.\n**Files**: `src/widget.py`\n**Done when**: it exists.\n"
    )[0]
    request = spawn_request("demo", step, RequestKey("7", 1, "review", round=round_), 2, WORK)
    inputs = PromptInputs(request, step, WORK, review_range=("aaa111", "bbb222"))
    return render_prompt(inputs)[0]


def test_a_round_two_review_prompt_names_the_boundary_heading():
    finish = review_prompt(2).split("<finish>")[1]

    assert SUPERSEDED_HEADING in finish


def test_a_round_one_review_prompt_names_no_boundary():
    assert SUPERSEDED_HEADING not in review_prompt(1)
