"""Tests for the pure render of the step-loop driver (``scripts/_step_loop_render.py``).

Every case passes plan steps, document text and attempt facts in and reads text out: no file
is written, no process runs, nothing is mocked. The rendered prompt is pinned byte for byte
by a golden fixture; the negative cases show what a prompt must never hold.
"""

from __future__ import annotations

import re
import sys
from dataclasses import asdict, fields
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import (  # noqa: E402
    _ACTIONS,
    AgentCall,
    PriorAttempt,
    PromptInputs,
    RequestKey,
    SpawnRequest,
    StopView,
    commit_message,
    parse_request_id,
    render_prompt,
    section_body,
    spawn_request,
    stop_next_action,
    stop_stderr,
)

STEP = "Step "
SLUG = "demo"
WORK = "/repo/.ai-work/demo"
INVOKE = "python3 scripts/step_loop.py"
GOLDEN = SCRIPT_DIR / "fixtures" / "step_loop_prompt_golden.md"
GOAL_TEXT = "the goal of the whole pipeline (goal text 83)"
NEIGHBOUR_TEXT = "Wire the neighbouring widget (neighbour text 61)."
READ_ONLY_ENTRY = "tests/acceptance/test_widget.py::test_widget_returns_its_id"
READ_ONLY_LINE = re.compile(r"^\W*Read-only\W*:", re.MULTILINE)
MODEL_NAMES = ("opus", "sonnet", "haiku")
KINDS = ("implement", "revise", "review")

PLAN = f"""\
# Plan: the widget pipeline

## Goal

{GOAL_TEXT}.

## Steps

### {STEP}7: [Phase: Refactoring] Add the widget [depends-on: 6]

**Assignee**: implementer
**Implementation**: Build the widget.
**Files**: `src/widget.py`, `tests/test_widget.py`
**Read-only**: `{READ_ONLY_ENTRY}`
**Check**: `uv run pytest tests/test_widget.py -q` expects pass>=2 fail=0
**Done when**: the widget exists.

### {STEP}8: Wire the neighbour

**Assignee**: implementer
**Implementation**: {NEIGHBOUR_TEXT}
"""
BRIEF = """\
# Task brief

## Key Signals

- the widget returns its id

## Health Guards

- [ ] derived test scope green after every step
- [ ] no commit while a subagent runs

## Uncertainty Flag

- low
"""
WIP_TEXT = """\
# WIP

## Corrections in force

- Run scratch work as scripts under the scratchpad.
- Give each unit-test file a unique basename.

## Notes

- sequential mode
"""
ATTEMPT_ONE = PriorAttempt(
    1, "a3f9c2e17b55d0e1", "turn-cap", 100, 100, "check unmet: fail=: expected =0, observed 3", None
)
ATTEMPT_TWO = PriorAttempt(
    2, "b81d0c44aa02f9c3", "completed", 23, 100, "check unmet: pending=: expected =17", "3f9c2e1aa"
)


def make_step(step_id="7", title="Add the widget", extra=()):
    lines = [
        f"### {STEP}{step_id}: {title}",
        "",
        "**Assignee**: implementer",
        "**Implementation**: Build the widget.",
        "**Files**: `src/widget.py`, `tests/test_widget.py`",
        *extra,
        "**Done when**: the widget exists.",
    ]
    return parse_plan_steps("\n".join(lines) + "\n")[0]


STEP_SEVEN = parse_plan_steps(PLAN)[0]
STEP_HIGH = make_step(extra=("tier: H",))


def request_for(step=STEP_SEVEN, kind="implement", attempt=1, cap=2, series=1):
    round_ = None if kind == "implement" else 1
    return spawn_request(SLUG, step, RequestKey(step.id, attempt, kind, series, round_), cap, WORK)


def prompt_for(kind="implement", step=STEP_SEVEN, attempt=1, series=1, **overrides):
    given = {"brief_text": BRIEF, "wip_text": WIP_TEXT}
    if kind == "review":
        given["review_range"] = ("aaa111", "bbb222")
    inputs = PromptInputs(
        request_for(step, kind, attempt, series=series), step, WORK, **{**given, **overrides}
    )
    return render_prompt(inputs)


def golden_prompt():
    return prompt_for(
        attempt=2,
        previous=(ATTEMPT_ONE,),
        dirty_files=("src/widget.py", "tests/test_widget.py"),
    )[0]


def order_of(text, markers):
    positions = [text.find(marker) for marker in markers]
    return positions == sorted(positions) and -1 not in positions


def element(text, tag):
    found = re.search(rf"<{tag}[^>]*>\n(.*?)\n</{tag}>", text, re.DOTALL)
    return found.group(1) if found else None


def long_text(lines=300):
    return "\n".join(f"- line {n:03d} " + "x" * 50 for n in range(lines))


def sized_section(size):
    body = "\n".join(f"- [ ] guard {n:02d} " + "g" * 84 for n in range(19))
    return body + "g" * (size - len(body))


def stop_view(cause="attempts-exhausted", step="7", attempts=(ATTEMPT_ONE, ATTEMPT_TWO)):
    return StopView(cause, step, "the evidence line", attempts, SLUG, INVOKE)


# --- Request ids ---


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (RequestKey("7", 1, "implement"), "s7-a1-implement"),
        (RequestKey("12b", 2, "implement"), "s12b-a2-implement"),
        (RequestKey("1", 1, "review", round=1), "s1-a1-review-r1"),
        (RequestKey("1", 1, "revise", round=1), "s1-a1-revise-r1"),
        (RequestKey("1", 1, "implement", series=2), "s1-p2-a1-implement"),
    ],
)
def test_a_request_id_follows_the_grammar(key, expected):
    assert key.id == expected


def test_a_request_id_uses_only_lowercase_letters_digits_and_hyphens():
    keys = [RequestKey("12b", 2, "review", series=3, round=2), RequestKey("7", 1, "implement")]
    assert all(re.fullmatch(r"[a-z0-9-]+", key.id) for key in keys)


@pytest.mark.parametrize(
    ("bad", "complaint"),
    [
        ({"step": "7", "attempt": 1, "kind": "implement", "round": 1}, "not a request kind"),
        ({"step": "7", "attempt": 1, "kind": "review"}, "not a request kind"),
        ({"step": "7", "attempt": 1, "kind": "review", "round": 0}, "not a request"),
        ({"step": "7", "attempt": 0, "kind": "implement"}, "not a request"),
        ({"step": "7", "attempt": 1, "kind": "implement", "series": 0}, "not a request"),
        ({"step": "x1", "attempt": 1, "kind": "implement"}, "not a request"),
        ({"step": "7", "attempt": 1, "kind": "bogus"}, "not a request kind"),
    ],
)
def test_a_key_that_breaks_the_grammar_is_refused(bad, complaint):
    with pytest.raises(ValueError, match=complaint):
        RequestKey(**bad)


ROUND_TRIP_KEYS = [
    RequestKey("7", 1, "implement"),
    RequestKey("12b", 2, "implement"),
    RequestKey("7", 3, "implement", series=2),
    RequestKey("1", 1, "review", round=1),
    RequestKey("1", 2, "review", series=3, round=2),
    RequestKey("1", 1, "revise", round=1),
    RequestKey("12b", 2, "revise", series=2, round=1),
]


@pytest.mark.parametrize("key", ROUND_TRIP_KEYS, ids=[key.id for key in ROUND_TRIP_KEYS])
def test_parsing_a_request_id_gives_back_the_key_that_wrote_it(key):
    assert parse_request_id(key.id) == key


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not-a-request",
        "s1-a1-implement-r1",
        "s1-a1-review",
        "s1-a0-implement",
        "s1-p1-a1-implement",
        "s1-a01-implement",
        "s1-a1-review-r0",
        "S1-a1-implement",
        "s1-a1-implement ",
        "s1-a1-bogus",
    ],
)
def test_text_that_is_the_id_of_no_key_parses_to_none(text):
    assert parse_request_id(text) is None


# --- The Agent call and the request ---


def test_the_agent_call_has_exactly_four_fields_and_none_that_picks_a_mode():
    names = [field.name for field in fields(AgentCall)]
    assert names == ["subagent_type", "model", "description", "prompt"]
    assert list(asdict(request_for().agent_call)) == names


def test_the_agent_call_refuses_haiku():
    with pytest.raises(ValueError, match="haiku"):
        AgentCall("praxion:implementer", "haiku", f"{STEP}7 attempt 1/2", "p")


def test_a_description_of_forty_characters_is_accepted():
    call = AgentCall("praxion:implementer", "sonnet", "d" * 40, "p")
    assert len(call.description) == 40


def test_a_description_of_forty_one_characters_is_refused():
    with pytest.raises(ValueError, match="40"):
        AgentCall("praxion:implementer", "sonnet", "d" * 41, "p")


@pytest.mark.parametrize(("attempt", "cap"), [(3, 2), (1, 0)])
def test_a_request_outside_its_attempt_cap_is_refused(attempt, cap):
    call = request_for().agent_call
    with pytest.raises(ValueError, match="is outside 1"):
        SpawnRequest(RequestKey("7", attempt, "implement"), cap, call, "/p")


def test_a_request_within_its_cap_is_built():
    assert request_for(attempt=2, cap=2).attempt_cap == 2


def test_the_agent_prompt_is_the_three_lines_that_point_at_the_prompt_file():
    request = request_for()
    expected = [
        f"Task slug: {SLUG}",
        "Spawn request: s7-a1-implement",
        f"Read {request.prompt_path} first and follow it; it holds your step and its constraints.",
    ]
    assert request.agent_call.prompt.splitlines() == expected


def test_a_review_prompt_opens_its_third_line_in_light_review_mode():
    request = request_for(kind="review")
    third = request.agent_call.prompt.splitlines()[2]
    assert third == (
        f"Mode: light-review. Read {request.prompt_path} first and follow it; "
        "it holds the step and the change to review."
    )


def test_the_prompt_path_is_flat_under_the_task_directory():
    assert request_for().prompt_path == f"{WORK}/PROMPT_s7-a1-implement.md"


@pytest.mark.parametrize(
    ("step", "kind", "model"),
    [
        (STEP_SEVEN, "implement", "sonnet"),
        (STEP_HIGH, "implement", "opus"),
        (STEP_HIGH, "revise", "opus"),
        (STEP_HIGH, "review", "sonnet"),
    ],
)
def test_the_model_follows_the_routing_and_never_the_reviewer(step, kind, model):
    assert request_for(step, kind).agent_call.model == model


@pytest.mark.parametrize(
    ("kind", "agent"),
    [
        ("implement", "praxion:implementer"),
        ("revise", "praxion:implementer"),
        ("review", "praxion:verifier"),
    ],
)
def test_the_agent_type_follows_the_kind(kind, agent):
    assert request_for(kind=kind).agent_call.subagent_type == agent


@pytest.mark.parametrize(
    ("kind", "series", "expected"),
    [
        ("implement", 1, f"{STEP}7 attempt 1/2"),
        ("implement", 2, f"{STEP}7 attempt 1/2 · rev 2"),
        ("revise", 1, f"{STEP}7 revision 1"),
        ("review", 1, f"{STEP}7 light review 1"),
    ],
)
def test_the_description_names_the_step_and_the_try(kind, series, expected):
    assert request_for(kind=kind, series=series).agent_call.description == expected


def test_a_key_that_names_another_step_is_refused():
    with pytest.raises(ValueError, match="names step"):
        spawn_request(SLUG, STEP_SEVEN, RequestKey("8", 1, "implement"), 2, WORK)


# --- The prompt file ---


def test_the_rendered_prompt_is_pinned_byte_for_byte_by_the_golden_fixture():
    assert golden_prompt() == GOLDEN.read_text(encoding="utf-8")


def test_the_prompt_opens_with_the_two_header_lines_of_the_agent_prompt():
    text, _ = prompt_for()
    assert text.splitlines()[:2] == request_for().agent_call.prompt.splitlines()[:2]


def test_an_implement_prompt_holds_its_sections_in_order():
    text, _ = prompt_for(attempt=2, previous=(ATTEMPT_ONE,))
    markers = [
        f"You are implementing {STEP}7 of IMPLEMENTATION_PLAN.md, attempt 2 of 2.",
        '<step id="7">',
        "<previous-attempts>",
        '<health-guards source="TASK_BRIEF.md § Health Guards">',  # id-citation-discipline:ignore
        '<corrections source="WIP.md § Corrections in force">',  # id-citation-discipline:ignore
        "<finish>",
    ]
    assert order_of(text, markers)


def test_the_step_block_is_carried_verbatim():
    text, _ = prompt_for()
    assert element(text, "step") == STEP_SEVEN.block


def test_the_slots_carry_their_sections_verbatim():
    text, _ = prompt_for()
    assert element(text, "health-guards") == section_body(BRIEF, "Health Guards")
    assert element(text, "corrections") == section_body(WIP_TEXT, "Corrections in force")


def test_a_first_attempt_has_no_previous_attempts_section():
    text, _ = prompt_for(previous=(), dirty_files=("src/widget.py",))
    assert "<previous-attempts>" not in text


def test_the_previous_attempts_slot_names_each_attempt_and_the_dirty_files():
    text, _ = prompt_for(
        attempt=2, previous=(ATTEMPT_ONE,), dirty_files=("src/widget.py", "tests/test_widget.py")
    )
    assert element(text, "previous-attempts").splitlines() == [
        "attempt 1 · agent a3f9c2e17b55d0e1 · turn-cap 100/100 · "
        "check unmet: fail=: expected =0, observed 3 · no commit",
        "Uncommitted edits to src/widget.py, tests/test_widget.py remain; read them first.",
    ]


def test_a_revise_prompt_carries_the_findings_in_place_of_the_attempts():
    text, _ = prompt_for("revise", findings_text="verdict: revise\nfindings:\n  - id: F1\n")
    markers = [
        f"You are revising {STEP}7 of IMPLEMENTATION_PLAN.md after its light review (round 1).",
        '<step id="7">',
        '<review-findings source="LIGHT_REVIEW_step-7.md">',
        "<health-guards",
        "<corrections",
        "<finish>",
    ]
    assert order_of(text, markers)
    assert "<previous-attempts>" not in text
    assert element(text, "review-findings") == "verdict: revise\nfindings:\n  - id: F1"


def test_a_review_prompt_holds_the_step_the_signals_the_diff_command_and_the_finish():
    text, _ = prompt_for("review")
    markers = [
        f"You are the light reviewer for {STEP}7 of IMPLEMENTATION_PLAN.md, round 1.",
        '<step id="7">',
        '<key-signals source="TASK_BRIEF.md § Key Signals">',  # id-citation-discipline:ignore
        "<diff>",
        "<finish>",
    ]
    assert order_of(text, markers)
    assert element(text, "diff") == "git diff aaa111..bbb222 -- src/widget.py tests/test_widget.py"
    assert "<health-guards" not in text


def test_a_review_prompt_without_a_commit_range_is_refused():
    request = request_for(kind="review")
    with pytest.raises(ValueError, match="commit range"):
        render_prompt(PromptInputs(request, STEP_SEVEN, WORK, BRIEF, WIP_TEXT))


def test_the_finish_binds_the_absolute_paths_the_step_and_the_no_commit_rule():
    finish = prompt_for()[0].split("<finish>")[1]
    assert f"`## {STEP}7`" in finish
    assert f"{WORK}/TEST_RESULTS.md" in finish
    assert f"{WORK}/WIP.md" in finish
    assert "committable" in finish
    assert "never commit" in finish
    assert "[COMPLETE]" in finish


def test_the_review_finish_binds_the_review_file_and_the_verdict_order():
    finish = prompt_for("review")[0].split("<finish>")[1]
    assert f"{WORK}/LIGHT_REVIEW_step-7.md" in finish
    assert order_of(finish, ["`verdict: [PARTIAL]` first", "the verdict line last"])


def test_a_missing_health_guards_section_gives_an_empty_slot_not_a_failed_render():
    text, warnings = prompt_for(brief_text="# Brief\n\n## Key Signals\n\n- x\n")
    assert "<health-guards" not in text
    assert warnings == ()


def test_an_empty_corrections_section_gives_an_empty_slot():
    text, _ = prompt_for(wip_text="## Corrections in force\n\n## Notes\n\n- n\n")
    assert "<corrections" not in text


def test_rendering_the_same_inputs_twice_gives_identical_bytes():
    assert prompt_for(attempt=2, previous=(ATTEMPT_ONE,)) == prompt_for(
        attempt=2, previous=(ATTEMPT_ONE,)
    )


# --- What a prompt never holds ---


@pytest.mark.parametrize("name", MODEL_NAMES)
@pytest.mark.parametrize("kind", KINDS)
def test_a_prompt_never_names_a_model(name, kind):
    text, _ = prompt_for(kind, step=STEP_HIGH, findings_text="findings")
    assert name not in text.lower()


def test_the_read_only_line_appears_exactly_once():
    assert len(READ_ONLY_LINE.findall(prompt_for()[0])) == 1


def test_a_step_without_a_read_only_line_gets_none_from_the_prompt():
    assert READ_ONLY_LINE.findall(prompt_for(step=STEP_HIGH)[0]) == []


@pytest.mark.parametrize("kind", KINDS)
def test_no_plan_text_from_outside_the_step_block_reaches_the_prompt(kind):
    text, _ = prompt_for(kind, findings_text="findings")
    assert GOAL_TEXT not in text
    assert NEIGHBOUR_TEXT not in text
    assert "Wire the neighbour" not in text


# --- Sections ---


@pytest.mark.parametrize("marker", ["##", "###"])
def test_a_section_is_read_at_either_heading_level(marker):
    assert section_body(f"{marker} Health Guards\n\n- one\n- two\n", "Health Guards") == (
        "- one\n- two"
    )


@pytest.mark.parametrize(
    "text",
    ["", "## Other\n\n- x\n", "## Health Guards\n\n\n## Next\n\n- x\n", "# Health Guards\n- x\n"],
)
def test_an_absent_or_empty_section_reads_as_empty(text):
    assert section_body(text, "Health Guards") == ""


def test_a_section_ends_at_the_next_heading_of_its_level_or_higher():
    text = "## A\n\n- a1\n\n### Sub\n\n- s1\n\n## B\n\n- b1\n"
    assert section_body(text, "A") == "- a1\n\n### Sub\n\n- s1"


def test_a_heading_shaped_line_in_a_code_fence_does_not_end_a_section():
    text = "## A\n\n```sh\n# a comment\n## not a heading\n```\n\n- after\n\n## B\n"
    assert section_body(text, "A") == "```sh\n# a comment\n## not a heading\n```\n\n- after"


# --- Bounds ---


def long_section(title):
    return f"## {title}\n\n{long_text()}\n"


def long_attempts(count=39):
    return tuple(
        ATTEMPT_ONE._replace(attempt=n, gate="check unmet: " + "y" * 60) for n in range(1, count)
    )


CUT_CASES = [
    ("implement", {"brief_text": long_section("Health Guards")}, "health-guards", 3000),
    ("implement", {"wip_text": long_section("Corrections in force")}, "corrections", 1500),
    ("review", {"brief_text": long_section("Key Signals")}, "key-signals", 2000),
    ("revise", {"findings_text": long_text()}, "review-findings", 3000),
    ("implement", {"previous": long_attempts()}, "previous-attempts", 1000),
]
SOURCE_FILES = {
    "health-guards": "TASK_BRIEF.md",
    "corrections": "WIP.md",
    "key-signals": "TASK_BRIEF.md",
    "review-findings": "LIGHT_REVIEW_step-7.md",
    "previous-attempts": "ITERATION_LEDGER.jsonl",
}


@pytest.mark.parametrize(("kind", "given", "tag", "bound"), CUT_CASES)
def test_a_slot_over_its_bound_is_cut_at_a_line_and_points_at_its_source(kind, given, tag, bound):
    text, warnings = prompt_for(kind, **given)
    inner = element(text, tag).splitlines()
    pointer = f"[truncated: full text in {WORK}/{SOURCE_FILES[tag]}]"
    assert len("\n".join(inner)) <= bound
    assert inner[-1] == pointer
    assert [code for code, _ in warnings] == ["slot-truncated"]
    assert all(line.startswith(("- line", "attempt")) for line in inner[:-1])


def test_a_cut_keeps_whole_leading_lines_of_the_source():
    text, _ = prompt_for(brief_text=f"## Health Guards\n\n{long_text()}\n")
    kept = element(text, "health-guards").splitlines()[:-1]
    assert kept == long_text().splitlines()[: len(kept)]


def test_a_health_guards_section_of_the_briefs_real_size_renders_untruncated():
    section = sized_section(1996)
    text, warnings = prompt_for(brief_text=f"## Health Guards\n\n{section}\n\n## Next\n")
    assert len(section) == 1996
    assert element(text, "health-guards") == section
    assert warnings == ()


def test_every_slot_cut_at_once_still_fits_the_ceiling():
    text, warnings = prompt_for(
        brief_text=f"## Health Guards\n\n{long_text()}\n",
        wip_text=f"## Corrections in force\n\n{long_text()}\n",
        previous=tuple(ATTEMPT_ONE._replace(attempt=n, gate="g" * 80) for n in range(1, 30)),
    )
    assert len(text) <= 16_000
    assert [code for code, _ in warnings] == ["slot-truncated"] * 3


def test_a_step_block_over_the_ceiling_is_carried_whole_with_a_warning():
    huge = make_step(extra=(f"**Notes**: {' '.join(f'clause-{n}' for n in range(3000))}",))
    text, warnings = prompt_for(step=huge)
    assert huge.block in text
    assert len(text) > 16_000
    assert [code for code, _ in warnings] == ["step-block-oversize"]
    assert f"{STEP}7" in warnings[0][1]


def test_an_ordinary_prompt_raises_no_warning():
    assert prompt_for()[1] == ()


# --- The stop text ---

CAUSES = {
    "attempts-exhausted", "stalled", "blocked-marker", "conflict-marker", "human-verdict",
    "unnamed-attempts", "review-revised-twice", "review-unfinished", "revision-failed",
    "not-driven", "dependency-defect", "commit-disturbed-tree", "loop-state-defect",
    "iteration-budget",
}  # fmt: skip


def test_every_stop_cause_has_an_action_and_no_other_does():
    assert set(_ACTIONS) == CAUSES


def test_the_stderr_block_says_what_happened_why_what_next_and_where():
    assert stop_stderr(stop_view()).splitlines() == [
        f"step_loop: stopped — {STEP}7 needs a human decision (attempts-exhausted).",
        "  attempt 1  a3f9c2e17b55d0e1  turn-cap 100/100  "
        "check unmet: fail=: expected =0, observed 3  no commit",
        "  attempt 2  b81d0c44aa02f9c3  completed 23/100  "
        "check unmet: pending=: expected =17  3f9c2e1",
        "  Why: the evidence line",
        "  Next: revise the step block (split it, or fix its Check: line), "
        f"then run: {INVOKE} next {SLUG}",
        f"  Handoff: .ai-work/{SLUG}/HANDOFF.md (§2 carries this stop)",
    ]


def test_the_budget_stop_names_no_step_and_no_attempts():
    stop = stop_view("iteration-budget", step=None, attempts=())
    assert stop_stderr(stop).splitlines()[0] == (
        "step_loop: stopped — the iteration budget is used up (iteration-budget)."
    )
    assert len(stop_stderr(stop).splitlines()) == 4


def test_a_step_handed_back_reads_differently_from_a_human_decision():
    first = stop_stderr(stop_view("not-driven", attempts=())).splitlines()[0]
    assert first == f"step_loop: stopped — {STEP}7 is handed back to you (not-driven)."


def test_a_stop_with_no_step_still_asks_for_a_human_decision():
    first = stop_stderr(stop_view("unnamed-attempts", step=None, attempts=())).splitlines()[0]
    assert first == "step_loop: stopped — the loop needs a human decision (unnamed-attempts)."


def test_an_action_that_names_the_review_file_names_the_stops_step():
    stop = stop_view("review-unfinished", attempts=())
    assert "LIGHT_REVIEW_step-7.md" in stop_stderr(stop)


def test_the_unreadable_turn_count_prints_a_question_mark():
    unreadable = ATTEMPT_ONE._replace(turns=None, max_turns=None)
    line = stop_stderr(stop_view(attempts=(unreadable,))).splitlines()[1]
    assert "turn-cap ?" in line


def test_the_handoff_paragraph_carries_the_stop_each_attempt_and_the_resume_line():
    assert stop_next_action(stop_view()).splitlines() == [
        f"The step-loop driver stopped at `{STEP}7`: attempts-exhausted (exit 2).",
        "the evidence line",
        "- attempt 1 · agent a3f9c2e17b55d0e1 · turn-cap 100/100 · "
        "check unmet: fail=: expected =0, observed 3 · no commit",
        "- attempt 2 · agent b81d0c44aa02f9c3 · completed 23/100 · "
        "check unmet: pending=: expected =17 · 3f9c2e1",
        "Human decision owed: revise the step block (split it, or fix its Check: line).",
        f"Then resume the loop: `/praxion:step-loop {SLUG}` (it runs `{INVOKE} next {SLUG}`).",
    ]


def test_the_budget_handoff_opens_with_the_budget_line_and_exit_three():
    stop = stop_view("iteration-budget", step=None, attempts=())
    first = stop_next_action(stop).splitlines()[0]
    assert first == "The step-loop driver stopped: iteration budget used up (exit 3)."


def test_a_step_handed_back_owes_an_orchestrator_action():
    owed = stop_next_action(stop_view("not-driven", attempts=())).splitlines()[2]
    assert owed.startswith("Orchestrator action owed: ")


def test_the_handoff_resume_line_keeps_the_command_a_scenario_greps_for():
    last = stop_next_action(stop_view()).splitlines()[-1]
    assert f"step_loop.py next {SLUG}" in last


def test_a_stop_renders_the_same_bytes_every_time():
    assert stop_stderr(stop_view()) == stop_stderr(stop_view())
    assert stop_next_action(stop_view()) == stop_next_action(stop_view())


# --- The commit message ---


@pytest.mark.parametrize(
    ("title", "subject"),
    [
        ("Add the widget", "Add the widget"),
        ("[Phase: Refactoring] Add the widget", "Add the widget"),
        ("Add the widget [Architecture]", "Add the widget"),
        ("Add the render module: ids and prompts", "Add the render module: ids and prompts"),
    ],
)
def test_the_subject_is_the_step_title_without_bracketed_tags_or_a_type_prefix(title, subject):
    step = make_step(title=title)
    message = commit_message(step, SLUG, request_for(step), "Result: pass=5 fail=0")
    assert message.splitlines()[0] == subject


def test_the_body_names_the_step_the_task_the_attempt_the_driver_and_the_deciding_line():
    result = "Result: pass=5 fail=0 skip=0 by=step-loop"
    message = commit_message(STEP_SEVEN, SLUG, request_for(attempt=2), result)
    assert message.splitlines() == [
        "Add the widget",
        "",
        f"{STEP}7 of {SLUG}, attempt 2: verified by the step-loop driver.",
        result,
        "",
        "Step-Loop-Request: s7-a2-implement",
    ]


def test_a_revision_commit_names_the_review_revision():
    message = commit_message(STEP_SEVEN, SLUG, request_for(kind="revise"), "Result: pass=5 fail=0")
    assert f"{STEP}7 of {SLUG}, review revision 1: verified" in message
    assert message.splitlines()[-1] == "Step-Loop-Request: s7-a1-revise-r1"


def test_a_commit_message_carries_no_authorship_line():
    message = commit_message(STEP_SEVEN, SLUG, request_for(), "Result: pass=5 fail=0")
    assert not re.search(r"co-authored|generated by|signed-off", message, re.IGNORECASE)


def test_a_review_has_no_commit():
    with pytest.raises(ValueError, match="follows an implement"):
        commit_message(STEP_SEVEN, SLUG, request_for(kind="review"), "Result: pass=5")


def test_the_deciding_line_is_one_line():
    with pytest.raises(ValueError, match="one Result: line"):
        commit_message(STEP_SEVEN, SLUG, request_for(), "Result: pass=5\nResult: pass=6")
