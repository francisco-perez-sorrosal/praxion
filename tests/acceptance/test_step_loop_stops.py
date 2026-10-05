"""The loop stops only on its named conditions, each with its own exit, and every pause hands off.

Every call prints one envelope and exits with one of five codes: 0 for a pending request
or a complete plan, 2 when a human must decide, 3 when the plan-derived iteration
budget is used up, 4 for a caller error and 1 for a driver failure. Completion takes
precedence over a human stop and a human stop over the budget stop, which is reachable.
Every exit 2 or 3 leaves a HANDOFF.md whose next-action section carries the stop.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers.step_loop import (
    HANDOFF_SECTIONS,
    SLUG,
    Step,
    Work,
    assert_well_formed,
    attempt,
    build_loop,
    handoff_section,
    next_action,
    revise_step,
    run_raw,
    step_id_of,
)

FAILS_ITS_CHECK = Work(passes=False, final_marker="complete")


def _exhaust(task):
    """Spend every attempt the cap allows on the next step; return the attempts' records."""
    cap = next_action(task).request["attempt_cap"]
    return [attempt(task, FAILS_ITS_CHECK).recorded for _ in range(cap)]


@pytest.mark.parametrize(
    ("marker", "cause"),
    [("blocked", "blocked-marker"), ("conflict", "conflict-marker")],
)
def test_a_blocked_or_conflicted_return_stops_for_a_human_naming_the_step(tmp_path, marker, cause):
    task = build_loop(tmp_path, Step("1"), Step("2"))

    stopped = attempt(task, Work(touches_files=False, final_marker=marker))

    assert stopped.exit_code == 2
    assert stopped.outcome == "needs-human"
    assert stopped.stop["cause"] == cause
    assert step_id_of(stopped.stop["step"]) == "1"


def test_a_blocked_return_whose_work_verified_is_committed_before_the_stop(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))

    stopped = attempt(task, Work(final_marker="blocked"))

    assert stopped.exit_code == 2
    assert stopped.recorded["commit"] is not None


def test_completion_takes_precedence_over_a_human_stop(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    attempt(task, Work(final_marker="blocked"))

    finished = next_action(task)

    assert finished.exit_code == 0
    assert finished.outcome == "complete"


def test_an_attempts_line_naming_no_step_stops_for_a_human(tmp_path):
    task = build_loop(tmp_path, Step("1"), extra_progress={"1": "  - Attempts: count=1"})

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.stop["cause"] == "unnamed-attempts"
    assert stopped.stop["step"] is None


def test_the_iteration_budget_is_the_plans_steps_times_the_attempt_cap(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"), Step("3"))

    asked = next_action(task)

    assert asked.iterations["budget"] == 3 * asked.request["attempt_cap"]


def test_a_human_stop_takes_precedence_over_a_used_up_budget(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)

    stopped = next_action(task)

    assert stopped.iterations["used"] == stopped.iterations["budget"]
    assert stopped.exit_code == 2
    assert stopped.stop["cause"] == "attempts-exhausted"


def test_the_budget_stop_is_reachable_and_exits_three(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)
    revise_step(task, "1", "Write `src/step_1.py` returning the step id, smaller this time.")

    stopped = next_action(task)

    assert stopped.exit_code == 3
    assert stopped.outcome == "budget-exhausted"
    assert stopped.stop["cause"] == "iteration-budget"
    assert stopped.stop["step"] is None
    assert stopped.iterations["used"] == stopped.iterations["budget"]


def test_every_envelope_but_a_usage_error_reports_iterations_within_the_budget(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    asked = next_action(task)
    recorded = attempt(task, Work())

    envelopes = [asked, recorded, next_action(task)]

    assert all(e.iterations["used"] <= e.iterations["budget"] for e in envelopes), [
        e.iterations for e in envelopes
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(["record", SLUG, "--agent-id", "a1", "--marker", "complete"], id="no-request"),
        pytest.param(
            [
                "record",
                SLUG,
                "--request",
                "s1-a1-implement",
                "--agent-id",
                "a1",
                "--marker",
                "complete",
                "--not-started",
                "failed",
            ],
            id="both-record-variants",
        ),
        pytest.param(
            [
                "record",
                SLUG,
                "--request",
                "s1-a1-implement",
                "--agent-id",
                "a1",
                "--marker",
                "[COMPLETE]",
            ],
            id="bracketed-marker",
        ),
        pytest.param(["next", SLUG, "--json"], id="next-takes-no-json-flag"),
    ],
)
def test_a_usage_error_exits_four_with_one_usage_envelope(tmp_path, arguments):
    task = build_loop(tmp_path, Step("1"))

    refused = assert_well_formed(
        arguments[0], run_raw(task, *arguments, "--repo-root", str(task.root))
    )

    assert refused.exit_code == 4
    assert refused.error["code"] == "usage"


@pytest.mark.parametrize("verb", ["gate", "commit", "run"])
def test_there_is_no_verb_beyond_next_record_and_status(tmp_path, verb):
    task = build_loop(tmp_path, Step("1"))

    result = run_raw(task, verb, SLUG, "--repo-root", str(task.root))

    assert result.returncode == 4


def test_a_task_without_a_plan_is_a_caller_error_naming_the_missing_document(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    task.plan_path.unlink()

    refused = next_action(task)

    assert refused.exit_code == 4
    assert refused.error["code"] == "missing-artifact"
    assert "IMPLEMENTATION_PLAN.md" in refused.error["message"]


def test_an_exhausted_step_leaves_a_handoff_whose_next_action_carries_the_stop(tmp_path):
    task = build_loop(tmp_path, Step("7"))
    attempts = _exhaust(task)

    stopped = next_action(task)

    handoff = Path(stopped.stop["handoff"])
    assert handoff.resolve() == (task.task_dir / "HANDOFF.md").resolve()
    text = handoff.read_text(encoding="utf-8")
    headings = re.findall(r"^## (§\d .+)$", text, re.MULTILINE)
    assert headings == list(HANDOFF_SECTIONS)
    next_section = handoff_section(text, "§2 Next action")
    assert re.search(r"\b7\b", next_section), next_section
    assert "attempts-exhausted" in next_section
    assert all(a["agent_id"] in next_section for a in attempts), next_section
    assert f"step_loop.py next {SLUG}" in next_section


def test_the_stop_names_the_command_that_resumes_the_loop(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)

    stopped = next_action(task)

    assert stopped.stop["resume"] == f"python3 scripts/step_loop.py next {SLUG}"


def test_a_budget_stop_also_leaves_a_handoff_with_the_resume_command(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)
    revise_step(task, "1", "Write `src/step_1.py` returning the step id, smaller this time.")

    stopped = next_action(task)

    text = Path(stopped.stop["handoff"]).read_text(encoding="utf-8")
    assert f"step_loop.py next {SLUG}" in handoff_section(text, "§2 Next action")
