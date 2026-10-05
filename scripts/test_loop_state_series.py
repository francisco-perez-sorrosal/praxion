"""Tests for the step-loop driver's pure state (``scripts/_step_loop_state.py``): a step's series,
done-ness and the selection of the next step.

Every case passes plan text, WIP attempt readings, ledger records and reconciler verdict dicts
in and reads values out: no file is written, no process runs, nothing is mocked. The two plan and
WIP fixtures are real excerpts copied from an earlier pipeline; the rest are hand-built.
"""

from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import ATTEMPT_CAP, Attempt, OutstandingAttempt, parse_attempts  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
from _step_loop_state import (  # noqa: E402
    AllDone,
    Defect,
    Defects,
    DoneOutside,
    Exhausted,
    Failed,
    Fresh,
    HumanVerdict,
    LoopInputs,
    Marked,
    Next,
    NotDriven,
    Running,
    Verified,
    bare_id,
    is_done,
    request_kind,
    select_step,
    series_states,
    spent,
    step_series,
)
from _step_schema import parse_wip_claims  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

STEP = "Step "
FIXTURES = SCRIPT_DIR / "fixtures"
ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "dataclasses",
    "re",
    "typing",
    "_loop_fields",
    "_plan_steps",
    "_step_loop_review",
    "iteration_ledger",
}
IMPLEMENTER = "**Assignee**: implementer"
OTHER = "**Assignee**: test-engineer"
FILES = "**Files**: `scripts/a.py`"
NO_FILES = "**Files**: none"
PIPELINE_ONLY_FILES = "**Files**: `.ai-work/NOTES.md`"
CHECK = "**Check**: `uv run pytest scripts/test_a.py -q` expects pass>=2 fail=0"
COMMIT = "abc1234"
REQUEST = "s1-a1-implement"


def block(number, *lines, annotations=""):
    body = "".join(f"{line}\n" for line in lines)
    return f"### {STEP}{number}: Do it{annotations}\n\n{body}\n"


def steps_of(*blocks):
    return parse_plan_steps("## Steps\n\n" + "".join(blocks))


def one(*lines, number="1"):
    return steps_of(block(number, *lines))[0]


def rec(step, attempt=1, kind="implement", *, verdict="mismatch", stop="completed", **more):
    """A ledger record for `step`, its request id built the way the driver builds it."""
    round_ = None if kind == "implement" else more.pop("round_", 1)
    key = RequestKey(step.id, attempt, kind, more.pop("series", 1), round_)
    return IterationRecord(
        step=STEP + step.id,
        attempt=attempt,
        agent_id=f"agent-{attempt}",
        verdict=verdict,
        decided_by="check",
        test_result="Result: none",
        commit=more.pop("commit", None),
        stop_reason=stop,
        request=key.id,
        step_digest=more.pop("digest", step.digest),
    )


def verdict(step_id, word, claim="PENDING", evidence=""):
    return {"step": STEP + step_id, "verdict": word, "wip_claim": claim, "evidence": evidence}


def given(attempts=None, records=(), verdicts=()):
    return (attempts or {}, records, verdicts)


def read(steps, attempts=None, records=(), verdicts=()):
    return LoopInputs.read(steps, attempts or {}, records, verdicts)


DRIVEN = one(IMPLEMENTER, FILES, CHECK)
VERIFIED_RECORD = rec(DRIVEN, verdict="verified-complete", commit=COMMIT)


@pytest.mark.parametrize(
    ("build"),
    [
        pytest.param(lambda s: (given(), Fresh(1)), id="no-record-is-fresh"),
        pytest.param(
            lambda s: (given(verdicts=[verdict("1", "pending")]), Fresh(1)), id="pending-is-fresh"
        ),
        pytest.param(
            lambda s: (given(verdicts=[verdict("1", "mismatch", "COMPLETE")]), Fresh(1)),
            id="claimed-but-mismatched-is-fresh",
        ),
        pytest.param(
            lambda s: (given(verdicts=[verdict("1", "verified-complete")]), Fresh(1)),
            id="verified-but-unclaimed-is-fresh",
        ),
        pytest.param(
            lambda s: (given(attempts={STEP + "1": Attempt(1)}), Fresh(1)),
            id="a-hand-written-count-is-no-series",
        ),
    ],
)
def test_a_step_with_no_driver_record_is_fresh(build):
    expected_given, expected = build(DRIVEN)

    assert step_series(DRIVEN, read([DRIVEN], *expected_given)) == expected


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        pytest.param(
            {STEP + "1": OutstandingAttempt(1, REQUEST)}, Running(1, REQUEST), id="first-attempt"
        ),
        pytest.param(
            {STEP + "1": OutstandingAttempt(2, "s1-a2-implement")},
            Running(2, "s1-a2-implement"),
            id="second-attempt",
        ),
    ],
)
def test_an_unrecorded_request_in_wip_is_running_not_exhausted(attempts, expected):
    inputs = read([DRIVEN], attempts, verdicts=[verdict("1", "in-flight")])

    assert step_series(DRIVEN, inputs) == expected


def test_an_outstanding_attempt_whose_driver_died_stays_running_and_reissues_its_request():
    attempts = {STEP + "1": OutstandingAttempt(1, REQUEST)}
    inputs = read([DRIVEN], attempts, verdicts=[verdict("1", "in-flight")])

    first, second = select_step(inputs), select_step(inputs)

    assert first == second == Next(DRIVEN, Running(1, REQUEST))


@pytest.mark.parametrize(
    ("build"),
    [
        pytest.param(
            lambda s: ([rec(s, 1)], Failed(1, (rec(s, 1),))), id="one-failed-attempt-under-cap"
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1), rec(s, 2)],
                Exhausted((rec(s, 1), rec(s, 2))),
            ),
            id="cap-reached-unverified",
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1, stop="turn-cap"), rec(s, 2, stop="no-marker")],
                Exhausted((rec(s, 1, stop="turn-cap"), rec(s, 2, stop="no-marker"))),
            ),
            id="cap-reached-by-stops-without-a-completion",
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1, stop="blocked")],
                Marked("BLOCKED", (rec(s, 1, stop="blocked"),)),
            ),
            id="blocked-marker",
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1, stop="conflict")],
                Marked("CONFLICT", (rec(s, 1, stop="conflict"),)),
            ),
            id="conflict-marker",
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1), rec(s, 2, stop="blocked")],
                Marked("BLOCKED", (rec(s, 1), rec(s, 2, stop="blocked"))),
            ),
            id="marker-on-the-capped-attempt-is-marked-not-exhausted",
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1, verdict="verified-complete", stop="blocked", commit=COMMIT)],
                Marked(
                    "BLOCKED",
                    (rec(s, 1, verdict="verified-complete", stop="blocked", commit=COMMIT),),
                ),
            ),
            id="verified-work-with-a-blocked-marker-is-marked",
        ),
        pytest.param(
            lambda s: ([VERIFIED_RECORD], Verified(1, 1, COMMIT)), id="verified-with-a-commit"
        ),
        pytest.param(
            lambda s: (
                [rec(s, 1), rec(s, 2, verdict="verified-complete")],
                Verified(2, 1, None),
            ),
            id="verified-on-the-second-attempt-without-a-commit",
        ),
        pytest.param(
            lambda s: (
                [VERIFIED_RECORD, rec(s, 1, "review", stop="blocked")],
                Verified(1, 1, COMMIT),
            ),
            id="a-review-return-is-no-attempt-and-no-marker",
        ),
        pytest.param(
            lambda s: (
                [VERIFIED_RECORD, rec(s, 1, "revise", stop="blocked")],
                Marked("BLOCKED", (VERIFIED_RECORD,)),
            ),
            id="a-revision-return-carrying-a-marker-marks-the-series",
        ),
        pytest.param(
            lambda s: ([rec(s, 1, "review")], Fresh(1)),
            id="a-review-record-alone-opens-no-attempt",
        ),
    ],
)
def test_the_current_series_reads_off_the_driver_records(build):
    records, expected = build(DRIVEN)

    assert step_series(DRIVEN, read([DRIVEN], records=records)) == expected


def test_a_series_ignores_records_written_without_the_driver():
    legacy = IterationRecord(
        STEP + "1", 1, "agent-0", "verified-complete", "check", "Result: none", COMMIT, "completed"
    )

    assert step_series(DRIVEN, read([DRIVEN], records=[legacy])) == Fresh(1)


def test_records_of_other_steps_do_not_leak_into_a_series():
    other = one(IMPLEMENTER, FILES, number="2")

    inputs = read([DRIVEN, other], records=[rec(other, 1, verdict="verified-complete")])

    assert step_series(DRIVEN, inputs) == Fresh(1)


def test_a_plan_revision_opens_a_fresh_series_and_the_next_revision_a_third():
    first = one(IMPLEMENTER, FILES, "First wording.")
    second = one(IMPLEMENTER, FILES, "Second wording.")
    third = one(IMPLEMENTER, FILES, "Third wording.")
    records = [rec(first, 1), rec(first, 2), rec(second, 1, series=2)]

    states = [step_series(step, read([step], records=records)) for step in (first, second, third)]

    assert states == [Exhausted((rec(first, 1), rec(first, 2))), Failed(2, (records[2],)), Fresh(3)]


def test_reverting_a_steps_text_restores_its_old_series():
    original = one(IMPLEMENTER, FILES, "Original wording.")
    revised = one(IMPLEMENTER, FILES, "Revised wording.")
    reverted = one(IMPLEMENTER, FILES, "Original wording.")
    records = [rec(original, 1), rec(original, 2)]

    before, during, after = (
        step_series(step, read([step], records=records)) for step in (original, revised, reverted)
    )

    assert (before, during, after) == (Exhausted(tuple(records)), Fresh(2), before)


def test_the_reconcilers_exhausted_verdict_does_not_hold_back_a_fresh_series():
    original = one(IMPLEMENTER, FILES, "Original wording.")
    revised = one(IMPLEMENTER, FILES, "Revised wording.")
    records = [rec(original, 1), rec(original, 2)]
    attempts = {STEP + "1": Attempt(ATTEMPT_CAP)}  # the write-ahead count survives the revision

    inputs = read([revised], attempts, records, [verdict("1", "attempts-exhausted")])

    assert step_series(revised, inputs) == Fresh(2)


@pytest.mark.parametrize(
    ("word", "claim", "expected"),
    [
        pytest.param("verified-complete", "COMPLETE", DoneOutside(), id="claimed-and-verified"),
        pytest.param(
            "attempts-exhausted",
            "PENDING",
            HumanVerdict("attempts-exhausted", "why"),
            id="exhausted-in-a-wip-written-without-the-loop",
        ),
    ],
)
def test_a_driven_step_without_a_driver_record_reads_the_reconciler(word, claim, expected):
    inputs = read([DRIVEN], verdicts=[verdict("1", word, claim, "why")])

    assert step_series(DRIVEN, inputs) == expected


@pytest.mark.parametrize("word", ["unknown", "blocked"])
@pytest.mark.parametrize(
    "records",
    [[], [rec(DRIVEN, 1)], [VERIFIED_RECORD]],
    ids=["no-record", "failed-series", "verified-series"],
)
def test_an_unknown_or_blocked_verdict_is_a_human_verdict_over_any_series(word, records):
    inputs = read([DRIVEN], records=records, verdicts=[verdict("1", word, evidence="see")])

    assert step_series(DRIVEN, inputs) == HumanVerdict(word, "see")


def test_an_unreadable_ledger_stops_even_a_running_step():
    attempts = {STEP + "1": OutstandingAttempt(1, REQUEST)}
    inputs = read([DRIVEN], attempts, verdicts=[verdict("1", "unknown", evidence="line 3")])

    assert step_series(DRIVEN, inputs) == HumanVerdict("unknown", "line 3")


@pytest.mark.parametrize(
    ("lines", "word", "claim", "expected"),
    [
        pytest.param([OTHER, FILES], None, None, NotDriven("test-engineer"), id="no-verdict"),
        pytest.param(
            [OTHER, FILES],
            "verified-complete",
            "PENDING",
            NotDriven("test-engineer"),
            id="files-verified-but-unclaimed",
        ),
        pytest.param(
            [OTHER, FILES],
            "mismatch",
            "COMPLETE",
            NotDriven("test-engineer"),
            id="files-claimed-only",
        ),
        pytest.param(
            [OTHER, FILES],
            "pending",
            "COMPLETE",
            NotDriven("test-engineer"),
            id="files-claimed-but-untouched-by-the-step",
        ),
        pytest.param(
            [OTHER, FILES],
            "verified-complete",
            "COMPLETE",
            DoneOutside(),
            id="files-claim-and-ground",
        ),
        pytest.param(
            [OTHER, NO_FILES, CHECK],
            "pending",
            "COMPLETE",
            NotDriven("test-engineer"),
            id="check-claimed-only",
        ),
        pytest.param(
            [OTHER, NO_FILES, CHECK],
            "verified-complete",
            "COMPLETE",
            DoneOutside(),
            id="check-claim-and-ground",
        ),
        pytest.param(
            [OTHER, NO_FILES], "pending", "COMPLETE", DoneOutside(), id="nothing-to-judge"
        ),
        pytest.param([OTHER], "pending", "COMPLETE", DoneOutside(), id="no-files-field-at-all"),
        pytest.param(
            [OTHER, PIPELINE_ONLY_FILES],
            "pending",
            "COMPLETE",
            DoneOutside(),
            id="only-pipeline-paths-are-no-admitted-file",
        ),
        pytest.param(
            [OTHER, NO_FILES],
            "unknown",
            "COMPLETE",
            DoneOutside(),
            id="nothing-to-judge-before-the-human-verdict",
        ),
        pytest.param(
            [OTHER, NO_FILES], "pending", "PENDING", NotDriven("test-engineer"), id="unclaimed"
        ),
        pytest.param(
            [OTHER, NO_FILES],
            "unknown",
            "PENDING",
            HumanVerdict("unknown", ""),
            id="unclaimed-and-unknown-is-a-human-verdict",
        ),
        pytest.param(
            [IMPLEMENTER, NO_FILES],
            "unknown",
            "COMPLETE",
            HumanVerdict("unknown", ""),
            id="a-driven-step-never-takes-the-claim-alone",
        ),
    ],
)
def test_a_step_outside_the_loop_is_done_only_with_what_its_declarations_allow(
    lines, word, claim, expected
):
    step = one(*lines)
    verdicts = [verdict("1", word, claim)] if word else []

    assert step_series(step, read([step], verdicts=verdicts)) == expected


def test_a_series_has_no_claim_of_its_own_a_driven_step_with_a_record_ignores_the_claim():
    inputs = read(
        [DRIVEN], records=[rec(DRIVEN, 1)], verdicts=[verdict("1", "mismatch", "COMPLETE")]
    )

    assert step_series(DRIVEN, inputs) == Failed(1, (rec(DRIVEN, 1),))


@pytest.mark.parametrize(
    ("state", "done"),
    [
        (Verified(1, 1, COMMIT), True),
        (DoneOutside(), True),
        (Fresh(1), False),
        (Running(1, REQUEST), False),
        (Failed(1, (rec(DRIVEN, 1),)), False),
        (Exhausted((rec(DRIVEN, 1), rec(DRIVEN, 2))), False),
        (Marked("BLOCKED", (rec(DRIVEN, 1),)), False),
        (NotDriven("test-engineer"), False),
        (HumanVerdict("unknown", ""), False),
    ],
    ids=lambda value: type(value).__name__ if not isinstance(value, bool) else str(value),
)
def test_only_a_verified_or_outside_done_step_is_done(state, done):
    assert is_done(state) is done


UNDER_CAP = (rec(DRIVEN, 1),)
AT_CAP = (rec(DRIVEN, 1), rec(DRIVEN, ATTEMPT_CAP))


@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(lambda: Fresh(0), "at least 1", id="series-index-below-one"),
        pytest.param(lambda: Failed(1, AT_CAP), "under the attempt cap", id="failed-at-the-cap"),
        pytest.param(
            lambda: Exhausted(UNDER_CAP), "reached the attempt cap", id="exhausted-under-the-cap"
        ),
        pytest.param(lambda: spent(()), "at least one record", id="no-attempts-to-count"),
    ],
)
def test_a_series_state_cannot_be_built_in_a_shape_the_cap_forbids(build, message):
    with pytest.raises(ValueError, match=message):
        build()


def test_the_step_keys_of_wip_ledger_and_reconciler_are_read_as_bare_ids():
    inputs = read(
        [DRIVEN], {STEP + "1": OutstandingAttempt(1, REQUEST)}, [rec(DRIVEN)], [verdict("1", "x")]
    )

    assert (bare_id(STEP + "12b"), bare_id("12b")) == ("12b", "12b")
    assert set(inputs.attempts) == set(inputs.verdicts) == {"1"}
    assert [r.step for r in inputs.driver_records("1")] == [STEP + "1"]


@pytest.mark.parametrize(
    ("request_id", "kind"),
    [
        ("s7-a1-implement", "implement"),
        ("s7-p2-a1-implement", "implement"),
        ("s7-a1-revise-r1", "revise"),
        ("s12b-a2-review-r2", "review"),
        (None, None),
    ],
)
def test_a_records_kind_is_read_off_its_request_id(request_id, kind):
    record = IterationRecord(
        STEP + "7",
        1,
        "a",
        "mismatch",
        "check",
        "Result: none",
        None,
        "completed",
        request=request_id,
    )

    assert request_kind(record) == kind


# --- selection ---------------------------------------------------------------------------------


def DONE(*ids):  # noqa: N802 -- reads as a table constant in the cases below
    return [verdict(i, "verified-complete", "COMPLETE") for i in ids]


def selected(plan, verdicts=(), **more):
    result = select_step(read(plan, verdicts=verdicts, **more))
    return result.step.id if isinstance(result, Next) else result


@pytest.mark.parametrize(
    ("blocks", "done", "expected"),
    [
        pytest.param([block(n, IMPLEMENTER) for n in "123"], (), "1", id="plan-order"),
        pytest.param([block(n, IMPLEMENTER) for n in "123"], "1", "2", id="skips-done-steps"),
        pytest.param(
            [block(n, IMPLEMENTER) for n in "123"], "13", "2", id="skips-done-later-steps"
        ),
        pytest.param(
            [block("1", IMPLEMENTER, annotations=" [depends-on: 2]"), block("2", IMPLEMENTER)],
            (),
            "2",
            id="waits-for-its-dependency",
        ),
        pytest.param(
            [block("1", IMPLEMENTER), block("2", IMPLEMENTER, annotations=" [depends-on: 1]")],
            "1",
            "2",
            id="starts-once-its-dependencies-are-done",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER),
                block("2", IMPLEMENTER),
                block("3", IMPLEMENTER, annotations=" [depends-on: 1, 2]"),
            ],
            "1",
            "2",
            id="needs-every-dependency",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER, annotations=" [depends-on: 9]"),
                block("2", IMPLEMENTER, annotations=" [parallel-group: G]"),
                block("3", IMPLEMENTER, annotations=" [parallel-group: G]"),
            ],
            (),
            "2",
            id="a-stuck-step-holds-back-no-sibling",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER, annotations=" [parallel-group: G]"),
                block("2", IMPLEMENTER, annotations=" [parallel-group: G]"),
            ],
            "1",
            "2",
            id="a-group-member-waits-for-no-sibling",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER, annotations=" [parallel-group: G]"),
                block("2", IMPLEMENTER, annotations=" [parallel-group: G] [depends-on: 1]"),
            ],
            (),
            "1",
            id="an-explicit-dependency-inside-a-group-still-holds",
        ),
    ],
)
def test_selection_takes_the_first_step_not_done_whose_dependencies_are_done(
    blocks, done, expected
):
    assert selected(steps_of(*blocks), DONE(*done)) == expected


def test_selection_carries_the_series_of_the_step_it_names():
    plan = steps_of(block("1", IMPLEMENTER, FILES))

    assert select_step(read(plan)) == Next(plan[0], Fresh(1))


def test_a_step_handed_back_is_selected_so_the_stop_can_name_it():
    plan = steps_of(block("1", OTHER, FILES), block("2", IMPLEMENTER))

    assert select_step(read(plan)) == Next(plan[0], NotDriven("test-engineer"))


@pytest.mark.parametrize("blocks", [[], [block("1", IMPLEMENTER)]])
def test_selection_is_all_done_when_every_step_is_done_or_there_are_none(blocks):
    plan = steps_of(*blocks)

    assert select_step(read(plan, verdicts=DONE(*(s.id for s in plan)))) == AllDone()


@pytest.mark.parametrize(
    ("blocks", "done", "found"),
    [
        pytest.param(
            [block("1", IMPLEMENTER, annotations=" [depends-on: 9]")],
            (),
            (Defect("1", "9", "missing"),),
            id="missing-dependency",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER, annotations=" [depends-on: 2]"),
                block("2", IMPLEMENTER, annotations=" [depends-on: 1]"),
            ],
            (),
            (Defect("1", "2", "cycle"), Defect("2", "1", "cycle")),
            id="cycle",
        ),
        pytest.param(
            [block("1", IMPLEMENTER, annotations=" [depends-on: 1]")],
            (),
            (Defect("1", "1", "cycle"),),
            id="self-cycle",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER, annotations=" [depends-on: 9]"),
                block("2", IMPLEMENTER, annotations=" [depends-on: 1]"),
            ],
            (),
            (Defect("1", "9", "missing"), Defect("2", "1", "held")),
            id="a-step-held-by-a-stuck-one",
        ),
        pytest.param(
            [
                block("1", IMPLEMENTER),
                block("2", IMPLEMENTER, annotations=" [depends-on: 1, 9]"),
            ],
            "1",
            (Defect("2", "9", "missing"),),
            id="done-dependencies-are-not-named",
        ),
    ],
)
def test_when_no_step_can_start_each_stuck_step_is_named_with_its_dependency(blocks, done, found):
    assert selected(steps_of(*blocks), DONE(*done)) == Defects(found)


# --- determinism and the fixtures --------------------------------------------------------------


def test_unchanged_inputs_give_the_same_answer_and_are_left_untouched():
    plan = steps_of(
        block("1", IMPLEMENTER, FILES), block("2", OTHER, annotations=" [depends-on: 1]")
    )
    attempts = {STEP + "1": Attempt(1)}
    records = [rec(plan[0], 1)]
    verdicts = [verdict("1", "mismatch", "COMPLETE"), verdict("2", "pending")]
    snapshot = copy.deepcopy((attempts, records, verdicts))

    answers = [select_step(read(plan, attempts, records, verdicts)) for _ in range(3)]

    assert answers[0] == answers[1] == answers[2] == Next(plan[0], Failed(1, tuple(records)))
    assert (attempts, records, verdicts) == snapshot


def test_the_order_of_the_wip_and_reconciler_inputs_changes_nothing():
    plan = steps_of(*[block(n, IMPLEMENTER) for n in "123"])
    verdicts = DONE("1") + [verdict("2", "pending"), verdict("3", "pending")]
    attempts = {STEP + "2": Attempt(1), STEP + "3": Attempt(1)}

    forward = select_step(read(plan, attempts, verdicts=verdicts))
    backward = select_step(read(plan, dict(reversed(attempts.items())), verdicts=verdicts[::-1]))

    assert forward == backward == Next(plan[1], Fresh(1))


def fixture_inputs(words, extra_attempts=None):
    """The step-schema plan and WIP excerpts: their claims, a verdict word per step."""
    plan = parse_plan_steps((FIXTURES / "step_schema_plan.md").read_text(encoding="utf-8"))
    wip = (FIXTURES / "step_schema_wip.md").read_text(encoding="utf-8")
    claims = parse_wip_claims(wip)
    verdicts = [
        verdict(s.id, words.get(s.id, "verified-complete"), claims.get(STEP + s.id, "PENDING"))
        for s in plan
    ]
    attempts = {**parse_attempts(wip).counts, **(extra_attempts or {})}
    return read(plan, attempts, verdicts=verdicts)


def test_the_fixture_pipeline_is_all_done_when_every_step_is_claimed_and_verified():
    inputs = fixture_inputs({})

    assert (
        [type(state).__name__ for state in series_states(inputs).values()],
        select_step(inputs),
    ) == (["DoneOutside"] * 6, AllDone())


def test_the_fixture_pipeline_names_the_first_step_whose_ground_truth_fails():
    inputs = fixture_inputs({"4": "mismatch"})

    chosen = select_step(inputs)

    assert (chosen.step.id, chosen.state) == ("4", Fresh(1))


def test_the_fixture_step_that_waits_on_three_steps_is_chosen_only_after_all_of_them():
    inputs = fixture_inputs({"6": "pending"})

    assert select_step(inputs).step.id == "6"
    assert select_step(fixture_inputs({"6": "pending", "5": "pending"})).step.id == "5"


def test_the_fixture_test_engineer_steps_are_handed_back_without_a_verified_claim():
    inputs = fixture_inputs({"1": "pending"})

    assert select_step(inputs) == Next(inputs.steps[0], NotDriven("test-engineer"))


def test_a_fixture_step_whose_wip_names_an_unrecorded_request_is_running():
    outstanding = {STEP + "4": OutstandingAttempt(1, "s4-a1-implement")}
    inputs = fixture_inputs({"4": "in-flight"}, outstanding)

    chosen = select_step(inputs)

    assert (chosen.step.id, chosen.state) == ("4", Running(1, "s4-a1-implement"))


def test_the_module_imports_nothing_that_reads_a_file_or_runs_a_process():
    source = (SCRIPT_DIR / "_step_loop_state.py").read_text(encoding="utf-8")
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }

    assert imported <= ALLOWED_IMPORTS
