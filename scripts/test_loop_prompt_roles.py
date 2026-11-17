"""The rendered implement and revise prompts say who runs what at the step's gate.

The driver runs the step's derived test scope once the agent returns; the agent runs the
step's own `Check` itself, in the foreground. Pure render: text in, text out, no process.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import (  # noqa: E402
    PROMPT_CEILING,
    PromptInputs,
    RequestKey,
    render_prompt,
    spawn_request,
)

WORK = "/repo/.ai-work/demo"
STEP = "Step "
PLAN = f"""\
### {STEP}3: Add the widget

**Assignee**: implementer
**Implementation**: Build the widget.
**Files**: `src/widget.py`
**Done when**: the widget exists.
"""
REVISE_FINDINGS = "- the widget ignores an empty id"


def rendered_finish(kind: str) -> str:
    step = parse_plan_steps(PLAN)[0]
    round_ = None if kind == "implement" else 1
    request = spawn_request("demo", step, RequestKey(step.id, 1, kind, 1, round_), 2, WORK)
    inputs = PromptInputs(request, step, WORK, findings_text=REVISE_FINDINGS)
    text, _ = render_prompt(inputs)
    assert len(text) <= PROMPT_CEILING
    return text.split("<finish>")[1]


@pytest.mark.parametrize("kind", ["implement", "revise"])
def test_the_closing_instructions_say_the_driver_runs_the_derived_test_scope(kind):
    finish = rendered_finish(kind)

    assert "The driver runs the derived test scope at its gate" in finish
    assert "start no scope yourself" in finish


@pytest.mark.parametrize("kind", ["implement", "revise"])
def test_the_closing_instructions_say_the_agent_runs_its_check_in_the_foreground(kind):
    finish = rendered_finish(kind)

    assert "Run the step's Check in the foreground and finish it before you return." in finish
