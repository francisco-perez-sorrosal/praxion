"""Every reader of an agent's transcript gives the same count of its distinct requests.

The turn-budget reminder, the loop's `record` and the context instrument's cap-out count
read the same transcript the same way: one count of distinct API requests, whether the
transcript is clean, repeats lines or whole requests, or holds a cut-off or malformed line.
Where the transcript is readable, that count is its number of distinct requests.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.request_count import (
    DAMAGED_VARIANTS,
    READABLE_VARIANTS,
    VARIANTS,
    as_cap_judgement,
    corpus_agent,
    implementer_cap,
    instrument_reading,
    loop_reading,
    reminder_reading,
    workspace,
)
from tests.acceptance.drivers.step_loop import Step, build_loop

# Past the reminder's first threshold and below the cap, so a reader that counted lines
# or entries instead of distinct requests would cross the cap and disagree.
REQUESTS = int(implementer_cap() * 0.7)


@pytest.mark.parametrize("variant", list(READABLE_VARIANTS))
def test_the_reminder_and_the_loop_count_the_distinct_requests(tmp_path, variant):
    task = build_loop(workspace(tmp_path), Step("1"))
    request, agent_id = corpus_agent(task, variant, REQUESTS)

    readings = (reminder_reading(task, agent_id), loop_reading(task, request, agent_id))

    assert readings == (REQUESTS, REQUESTS)


@pytest.mark.parametrize("variant", list(DAMAGED_VARIANTS))
def test_the_reminder_and_the_loop_agree_on_a_damaged_transcript(tmp_path, variant):
    task = build_loop(workspace(tmp_path), Step("1"))
    request, agent_id = corpus_agent(task, variant, REQUESTS)

    from_the_reminder = reminder_reading(task, agent_id)
    from_the_loop = loop_reading(task, request, agent_id)

    assert from_the_reminder == from_the_loop


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_the_instruments_cap_out_count_agrees_with_the_loop(tmp_path, variant):
    task = build_loop(workspace(tmp_path), Step("1"))
    request, agent_id = corpus_agent(task, variant, REQUESTS)
    from_the_loop = loop_reading(task, request, agent_id)

    judged = instrument_reading(task, agent_id)

    assert judged == as_cap_judgement(from_the_loop, implementer_cap())
