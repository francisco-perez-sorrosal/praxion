"""The rendered prompt tells the agent the driver runs the derived scope and the agent its Check.

An implement or a revise prompt says, beyond the plan block it carries verbatim, that the
driver runs the step's derived test scope once the agent returns, and that the agent runs the
step's Check in the foreground, finished before it returns, starting no scope or suite itself.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.loop_repairs import next_request, outside_step_block, prompt_text
from tests.acceptance.drivers.step_loop import (
    Step,
    attempt,
    build_loop,
    leave_review_verdict,
    record,
)


def _implement_prompt(tmp_path) -> str:
    task = build_loop(tmp_path, Step("1"))
    return prompt_text(next_request(task))


def _revise_prompt(tmp_path) -> str:
    task = build_loop(tmp_path, Step("1", annotations=("**review**: force",)), Step("2"))
    attempt(task)
    review = next_request(task)
    record(
        task, review["id"], agent_id=leave_review_verdict(task, review, "revise"), marker="complete"
    )
    revision = next_request(task)
    assert revision["kind"] == "revise", revision
    return prompt_text(revision)


PROMPTS = {"implement": _implement_prompt, "revise": _revise_prompt}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:])\s+|\n", text) if s.strip()]


@pytest.mark.parametrize("kind", list(PROMPTS))
def test_the_prompt_says_the_driver_runs_the_derived_scope(tmp_path, kind):
    said = outside_step_block(PROMPTS[kind](tmp_path))

    naming = [
        s
        for s in _sentences(said)
        if re.search(r"\bderived\b", s, re.I) and re.search(r"\bdriver\b", s, re.I)
    ]

    assert naming, f"the {kind} prompt never says the driver runs the derived scope:\n{said}"


@pytest.mark.parametrize("kind", list(PROMPTS))
def test_the_prompt_says_the_agent_runs_its_check_in_the_foreground(tmp_path, kind):
    said = outside_step_block(PROMPTS[kind](tmp_path))

    naming = [s for s in _sentences(said) if "Check" in s and re.search(r"\bforeground\b", s, re.I)]

    assert naming, f"the {kind} prompt never says the Check runs in the foreground:\n{said}"
