"""Tests for the pure gate of the step-loop driver (``scripts/_step_loop_gate.py``).

Every case passes pytest output text, plan fields or transcript facts in and reads
values out: no process runs, no file opens, nothing is mocked. The ownership rule is
pinned at its boundaries, and the whole gate is pinned against the reconciler's own
reader (``evaluate_check``) so the line the gate writes is the line the reconciler judges.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import Check, Expectation, Met, NoResult, Unmet, evaluate_check  # noqa: E402
from _step_loop_gate import (  # noqa: E402
    EndEvidence,
    GateRun,
    Ownership,
    classify_run,
    derive_stop_reason,
    end_source,
    entry_owns,
    gate_result_lines,
    parse_marker,
    parse_pytest_summary,
    render_result_line,
    resolve_marker,
)
from _step_schema import Counts, NoRun, parse_result_line  # noqa: E402

STEP = "Step "
COMMAND = "uv run pytest scripts/test_x.py -q"
NO_SUMMARY = "the output holds no pytest summary line"
SHORT_SUMMARY_RULE = "=========================== short test summary info ==="

DEFAULT_OUTPUT = f"""\
============================= test session starts ==============================
collected 30 items

scripts/test_x.py ....F.......E.....................                       [100%]

=================================== FAILURES ===================================
{SHORT_SUMMARY_RULE}
FAILED tests/acceptance/test_later.py::test_one - assert 1 == 2
FAILED tests/acceptance/test_later.py::test_two[a - b] - AssertionError
FAILED scripts/test_x.py::test_mine
ERROR tests/acceptance/test_later.py::test_three - fixture 'z' not found
=== 3 failed, 25 passed, 1 skipped, 1 error in 0.34s ===
"""

QUIET_OUTPUT = """\
FAILED a.py::t - boom
2 failed, 5 passed in 0.50s
"""


def green(command=COMMAND, passed=3):
    return GateRun(command, Counts(passed=passed, failed=0))


def red(command=COMMAND):
    return GateRun(command, Counts(passed=3, failed=1), failed_ids=("a.py::t",))


def no_run(command=COMMAND):
    return GateRun(command, NoRun("the output holds no pytest summary line"))


def ownership(own="10", *, later=(), done=()):
    owners = {"11": tuple(later), "10": ("scripts/test_x.py",)}
    return Ownership(own, owners, frozenset(done))


def results_text(step, lines):
    return f"## {STEP}{step} — gate\n\n" + "\n".join(lines) + "\n"


CHECK = Check(COMMAND, (Expectation("pass", ">=", 2), Expectation("fail", "=", 0)))


# --- (a) reading pytest output -------------------------------------------------


def test_default_short_summary_yields_counts_and_each_named_node():
    summary = parse_pytest_summary(DEFAULT_OUTPUT)

    assert summary.counts == Counts(passed=25, failed=3, skipped=1, errors=1)
    assert summary.failed_ids == (
        "tests/acceptance/test_later.py::test_one",
        "tests/acceptance/test_later.py::test_two[a - b]",
        "scripts/test_x.py::test_mine",
    )
    assert summary.error_ids == ("tests/acceptance/test_later.py::test_three",)


def test_quiet_summary_without_rules_reads_the_same():
    summary = parse_pytest_summary(QUIET_OUTPUT)

    assert (summary.counts, summary.failed_ids) == (Counts(passed=5, failed=2), ("a.py::t",))


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("=== 4 passed in 0.10s ===", Counts(passed=4, failed=0)),
        ("1 error in 0.20s", Counts(passed=0, failed=0, errors=1)),
        ("2 errors in 0.20s", Counts(passed=0, failed=0, errors=2)),
        ("=== no tests ran in 0.01s ===", Counts(passed=0, failed=0)),
        ("1 failed, 4 passed, 2 warnings, 3 deselected in 5.01s (0:00:05)", Counts(4, 1)),
        ("1 passed, 1 xfailed, 1 xpassed in 0.30s", Counts(passed=1, failed=0)),
    ],
)
def test_count_line_variants(line, expected):
    assert parse_pytest_summary(f"noise\n{line}\n").counts == expected


@pytest.mark.parametrize(
    "output",
    [
        "",
        "Traceback (most recent call last):\n  File x\nValueError: boom\n",
        "Killed\n",
        "INTERNALERROR> something broke\n",
        "FAILED a.py::t - boom\n",
        "took 3 seconds\ntotal time in 4s\n",
    ],
)
def test_output_with_no_count_line_is_no_run_never_a_guessed_pass(output):
    assert parse_pytest_summary(output) is None
    assert classify_run(COMMAND, output, ownership()).counts == NoRun(NO_SUMMARY)


def test_the_last_count_line_is_the_run_even_when_a_test_printed_one():
    output = "captured: 9 passed in 1s\nFAILED a.py::t - x\n1 failed in 0.20s\n"

    assert parse_pytest_summary(output).counts == Counts(passed=0, failed=1)


def test_a_line_after_the_count_line_does_not_hide_the_run():
    output = "FAILED a.py::t - x\n1 failed, 2 passed in 0.20s\nsentry: report sent\n"

    assert parse_pytest_summary(output).counts == Counts(passed=2, failed=1)


def test_a_node_line_whose_reason_looks_like_a_count_line_is_not_the_count_line():
    output = "FAILED a.py::t - the log said 3 passed in 2s\nERROR a.py::u - 1 error in 1s\n"

    assert parse_pytest_summary(output) is None
    assert classify_run(COMMAND, output, ownership()).counts == NoRun(NO_SUMMARY)


def test_a_node_listed_twice_is_named_once():
    output = "FAILED a.py::t - x\nFAILED a.py::t - x\n1 failed in 0.20s\n"

    assert parse_pytest_summary(output).failed_ids == ("a.py::t",)


@pytest.mark.parametrize(
    ("line", "node"),
    [
        ("FAILED a.py::t", "a.py::t"),
        ("FAILED a.py::t - reason - more", "a.py::t"),
        ("FAILED a.py::t[x - y] - reason", "a.py::t[x - y]"),
        ("FAILED a.py::t[a[0] - b] - reason", "a.py::t[a[0] - b]"),
    ],
)
def test_the_node_id_ends_at_the_first_separator_outside_brackets(line, node):
    assert parse_pytest_summary(f"{line}\n1 failed in 0.1s\n").failed_ids == (node,)


# --- (b) who owns a failed node ------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "node", "owned"),
    [
        ("a.py::f", "a.py::f[x]", True),
        ("a.py::f", "a.py::fg", False),
        ("a.py::f", "a.py::f", True),
        ("a.py::f", "a.py::f/x", False),
        ("a.py::f[x]", "a.py::f[x]", True),
        ("a.py::f[x]", "a.py::f[xy]", False),
        ("a.py::C", "a.py::C::m", True),
        ("a.py", "a.py::f", True),
        ("a.py", "a.pyc::f", False),
        ("a.py", "b.py::f", False),
        ("tests/acc", "tests/acc/x.py::f", True),
        ("tests/acc", "tests/acceptance/x.py::f", False),
        ("tests/acc/", "tests/acc/x.py::f", True),
    ],
)
def test_an_entry_owns_a_node_only_at_a_path_node_or_param_boundary(entry, node, owned):
    assert entry_owns(entry, node) is owned


@pytest.mark.parametrize(
    ("node", "later", "done", "pending"),
    [
        ("t/a.py::f", ["t/a.py::f"], [], True),
        ("t/a.py::f[x]", ["t/a.py::f"], [], True),
        ("t/a.py::fg", ["t/a.py::f"], [], False),
        ("t/a.py::f", ["t/a.py::f"], ["11"], False),
        ("scripts/test_x.py::own", [], [], False),
        ("elsewhere/z.py::f", ["t/a.py"], [], False),
        ("scripts/test_x.py::own", ["scripts/test_x.py::own"], [], True),
        ("scripts/test_x.py::own", ["scripts"], [], False),
        ("scripts/test_x.py::own[1]", ["scripts/test_x.py::own"], [], True),
        ("scripts/test_y.py::f", ["scripts/test_y.py"], [], True),
    ],
)
def test_a_node_is_pending_only_when_another_unfinished_step_owns_it(node, later, done, pending):
    assert ownership(later=later, done=done).is_pending(node) is pending


def test_a_tie_between_two_unfinished_later_steps_is_still_pending():
    owners = {"10": (), "11": ("t/a.py::f",), "12": ("t/a.py::f",)}

    assert Ownership("10", owners, frozenset()).is_pending("t/a.py::f") is True


def test_a_tie_that_includes_a_done_step_is_a_failure():
    owners = {"10": (), "11": ("t/a.py::f",), "12": ("t/a.py::f",)}

    assert Ownership("10", owners, frozenset({"12"})).is_pending("t/a.py::f") is False


def test_the_longest_entry_decides_who_owns_a_node():
    owners = {"10": ("t/a.py::f",), "11": ("t/a.py",)}

    assert Ownership("10", owners, frozenset()).is_pending("t/a.py::f") is False
    assert Ownership("11", owners, frozenset()).is_pending("t/a.py::f") is True


def test_failures_owned_by_a_later_step_count_as_pending_not_fail():
    run = classify_run(COMMAND, DEFAULT_OUTPUT, ownership(later=["tests/acceptance/test_later.py"]))

    assert run.counts == Counts(passed=25, failed=1, skipped=1, errors=0)
    assert run.pending == 3
    assert run.failed_ids == ("scripts/test_x.py::test_mine",)
    assert run.pending_ids == (
        "tests/acceptance/test_later.py::test_one",
        "tests/acceptance/test_later.py::test_two[a - b]",
        "tests/acceptance/test_later.py::test_three",
    )


def test_a_failure_the_summary_does_not_name_is_never_reclassified_as_pending():
    output = "FAILED t/a.py::f - x\n3 failed, 4 passed in 0.5s\n"

    run = classify_run(COMMAND, output, ownership(later=["t/a.py"]))

    assert (run.counts.failed, run.pending) == (2, 1)


@pytest.mark.parametrize("output", ["", QUIET_OUTPUT])
def test_a_classified_run_keeps_the_command_that_produced_it(output):
    assert classify_run(COMMAND, output, ownership()).command == COMMAND


def test_an_error_no_later_step_owns_is_a_named_failure_beside_the_failed_nodes():
    output = "FAILED t/a.py::f - x\nERROR t/b.py::g - y\n1 failed, 1 error, 4 passed in 0.5s\n"

    run = classify_run(COMMAND, output, ownership(later=["t/c.py"]))

    assert (run.counts, run.failed_ids) == (Counts(4, 1, errors=1), ("t/a.py::f", "t/b.py::g"))


def test_a_pending_node_the_count_line_does_not_cover_cannot_hide_an_own_failure():
    output = (
        "FAILED scripts/test_x.py::own - x\nFAILED t/a.py::f - captured stdout\n"
        "1 failed, 4 passed in 0.5s\n"
    )

    run = classify_run(COMMAND, output, ownership(later=["t/a.py"]))

    assert (run.counts, run.failed_ids, run.pending, run.red) == (
        Counts(passed=4, failed=1),
        ("scripts/test_x.py::own",),
        1,
        True,
    )


def test_an_error_line_the_count_line_does_not_cover_cannot_hide_an_own_error():
    output = "ERROR scripts/test_x.py::own - x\nERROR t/a.py::f - y\n1 error, 4 passed in 0.5s\n"

    run = classify_run(COMMAND, output, ownership(later=["t/a.py"]))

    assert (run.counts, run.red) == (Counts(passed=4, failed=0, errors=1), True)


def test_a_run_whose_every_failure_is_pending_is_green_with_the_pending_count():
    output = "FAILED t/a.py::f - x\nFAILED t/a.py::g - x\n2 failed, 4 passed in 0.5s\n"

    run = classify_run(COMMAND, output, ownership(later=["t/a.py"]))

    assert (run.counts, run.pending, run.red) == (Counts(passed=4, failed=0), 2, False)


def test_a_node_that_failed_and_errored_in_teardown_is_one_pending_node():
    output = "FAILED t/a.py::f - x\nERROR t/a.py::f - y\n1 failed, 1 error, 4 passed in 0.5s\n"

    run = classify_run(COMMAND, output, ownership(later=["t/a.py"]))

    assert (run.counts, run.pending_ids) == (Counts(passed=4, failed=0), ("t/a.py::f",))


def test_more_named_nodes_than_the_count_line_reports_never_make_a_negative_count():
    output = "FAILED t/a.py::f - x\nFAILED t/a.py::g - x\n1 failed, 4 passed in 0.5s\n"

    run = classify_run(COMMAND, output, ownership(later=["t/a.py"]))

    assert run.counts == Counts(passed=4, failed=0)


@pytest.mark.parametrize(
    ("failed_ids", "pending_ids"),
    [(("a.py::t",), ()), ((), ("a.py::t",)), (("a.py::t",), ("b.py::u",))],
)
def test_a_run_with_no_summary_cannot_name_failed_nodes(failed_ids, pending_ids):
    with pytest.raises(ValueError, match="^a run that showed no summary cannot name failed nodes$"):
        GateRun(COMMAND, NoRun("none"), failed_ids=failed_ids, pending_ids=pending_ids)


# --- (c) Result: lines and their order ----------------------------------------


@pytest.mark.parametrize(
    ("run", "line"),
    [
        (green(passed=7), "Result: pass=7 fail=0 skip=0 pending=0 by=step-loop"),
        (
            GateRun(COMMAND, Counts(25, 1, 2, 3), ("a.py::t",), ("b.py::u", "b.py::v")),
            "Result: pass=25 fail=1 skip=2 error=3 pending=2 by=step-loop",
        ),
        (no_run(), "Result: none — the output holds no pytest summary line"),
        (
            GateRun(COMMAND, NoRun("it  broke\nbadly ")),
            "Result: none — it broke badly",
        ),
    ],
)
def test_result_line_rendering(run, line):
    assert render_result_line(run) == line


@pytest.mark.parametrize(
    "run", [green(), red(), GateRun(COMMAND, Counts(5, 0, 1, 2), (), ("b::u",))]
)
def test_a_rendered_line_reads_back_as_the_counts_it_was_made_from(run):
    parsed = parse_result_line(render_result_line(run))

    assert parsed == Counts(
        run.counts.passed, run.counts.failed, run.counts.skipped, run.counts.errors
    )


SCOPE_GREEN = GateRun("scope", Counts(passed=9, failed=0))
SCOPE_RED = GateRun("scope", Counts(passed=8, failed=2), failed_ids=("a.py::s",))
SCOPE_NONE = GateRun("scope", NoRun("the scope run broke"))
CHECK_GREEN = GateRun("check", Counts(passed=4, failed=0))
CHECK_RED = GateRun("check", Counts(passed=3, failed=1), failed_ids=("a.py::c",))
CHECK_NONE = GateRun("check", NoRun("the check run broke"))


@pytest.mark.parametrize(
    ("scope", "check", "deciding"),
    [
        (SCOPE_GREEN, CHECK_GREEN, CHECK_GREEN),
        (SCOPE_RED, CHECK_GREEN, SCOPE_RED),
        (SCOPE_GREEN, CHECK_RED, CHECK_RED),
        (SCOPE_RED, CHECK_RED, CHECK_RED),
        (SCOPE_NONE, CHECK_GREEN, SCOPE_NONE),
        (SCOPE_GREEN, CHECK_NONE, CHECK_NONE),
        (SCOPE_NONE, CHECK_NONE, CHECK_NONE),
        (SCOPE_RED, CHECK_NONE, CHECK_NONE),
        (SCOPE_NONE, CHECK_RED, CHECK_RED),
    ],
)
def test_the_deciding_result_line_is_last(scope, check, deciding):
    other = scope if deciding is check else check

    lines = gate_result_lines(scope, check)

    assert lines == (render_result_line(other), render_result_line(deciding))


def test_both_runs_are_written_and_a_missing_scope_leaves_the_checks_line_alone():
    assert gate_result_lines(None, red()) == (render_result_line(red()),)
    assert gate_result_lines(green(passed=9), green(passed=4)) == (
        render_result_line(green(passed=9)),
        render_result_line(green(passed=4)),
    )


def test_a_green_check_after_a_red_scope_cannot_clear_the_red():
    lines = gate_result_lines(red(), green())

    outcome = evaluate_check(CHECK, "10", results_text("10", lines))

    assert isinstance(outcome, Unmet)


def test_the_reconciler_reads_the_driver_line_as_the_drivers_and_judges_pending():
    run = classify_run(COMMAND, DEFAULT_OUTPUT, ownership(later=["tests/acceptance"]))
    check = Check(COMMAND, (Expectation("pass", ">=", 25), Expectation("pending", "=", 3)))
    text = results_text("10", (render_result_line(run),))

    assert evaluate_check(check, "10", text) == Met(by_step_loop=True)


def test_a_run_red_only_by_errors_still_meets_a_check_that_names_no_error_key():
    """The check grammar has no `error` key: the caller must AND `GateRun.red` with it."""
    run = GateRun(COMMAND, Counts(passed=4, failed=0, errors=1))

    outcome = evaluate_check(CHECK, "10", results_text("10", (render_result_line(run),)))

    assert (run.red, outcome) == (True, Met(by_step_loop=True))


def test_an_ownership_whose_step_is_not_a_key_of_the_map_is_refused():
    with pytest.raises(ValueError, match="^step '10' is not a key of the Read-only map$"):
        Ownership("10", {f"{STEP}10": ("t/a.py",)}, frozenset())


def test_a_no_run_line_is_never_a_met_check():
    outcome = evaluate_check(CHECK, "10", results_text("10", gate_result_lines(None, no_run())))

    assert isinstance(outcome, NoResult)


def test_a_green_pair_is_met_by_the_driver():
    outcome = evaluate_check(CHECK, "10", results_text("10", gate_result_lines(green(), green())))

    assert outcome == Met(by_step_loop=True)


# --- (d) how an attempt ended --------------------------------------------------


@pytest.mark.parametrize(
    ("text", "marker"),
    [
        ("Done.\n[COMPLETE]", "complete"),
        ("[BLOCKED] cannot reach the file", "blocked"),
        ("Work finished. [CONFLICT]", "conflict"),
        ("work\n\n[PARTIAL]\n\n  \n", "partial"),
        ("**[COMPLETE]**", "complete"),
        ("`[PARTIAL]`", "partial"),
        ("[COMPLETE] changed 2 files [COMPLETE]", "complete"),
        ("[COMPLETE]\nand then some words", "none"),
        ("first\nsecond\n[COMPLETE]", "complete"),
        ("it said [COMPLETE] in the middle of a line", "none"),
        ("[BLOCKED] but also [COMPLETE]", "none"),
        ("[complete]", "none"),
        ("all tests green, now let me update the notes", "none"),
        ("", "none"),
        (None, "none"),
    ],
)
def test_marker_parse_of_a_final_text(text, marker):
    assert parse_marker(text) == marker


@pytest.mark.parametrize(
    ("evidence", "source"),
    [
        (EndEvidence("work\n[COMPLETE]", 5, 100), "marker"),
        (EndEvidence("work\n[COMPLETE]", 100, 100), "marker"),
        (EndEvidence("no marker here", 99, 100), "final-text"),
        (EndEvidence("no marker here", 100, 100), "turn-cap"),
        (EndEvidence(None, 101, 100), "turn-cap"),
        (EndEvidence(None, 5, 100, agent_stopped=True), "agent-stop"),
        (EndEvidence(None, 5, 100), None),
        (EndEvidence(None, None, 100), None),
        (EndEvidence(None, 100, None), None),
        (EndEvidence(None, None, None, agent_stopped=True), "agent-stop"),
        (EndEvidence(None, 5, 0), None),
        (EndEvidence(None, 1, 1), "turn-cap"),
        (EndEvidence("almost [COMPLETE", 5, 100), "final-text"),
    ],
)
def test_end_evidence_says_the_agent_ended_only_on_one_of_the_four_signs(evidence, source):
    assert end_source(evidence) == source


@pytest.mark.parametrize(
    ("marker", "requests", "max_turns", "reason"),
    [
        ("blocked", 5, 100, "blocked"),
        ("conflict", 5, 100, "conflict"),
        ("partial", 5, 100, "partial"),
        ("complete", 5, 100, "completed"),
        ("complete", 100, 100, "completed"),
        ("blocked", 100, 100, "blocked"),
        ("none", 100, 100, "turn-cap"),
        ("none", 120, 100, "turn-cap"),
        ("none", 99, 100, "no-marker"),
        ("none", None, 100, "no-marker"),
        ("none", 100, None, "no-marker"),
    ],
)
def test_stop_reason_follows_the_marker_then_the_cap_then_no_marker(
    marker, requests, max_turns, reason
):
    assert derive_stop_reason(marker, requests, max_turns) == reason


@pytest.mark.parametrize(
    ("transcript", "relayed", "marker", "disagrees"),
    [
        ("complete", "complete", "complete", False),
        ("none", "complete", "none", True),
        ("blocked", "complete", "blocked", True),
        ("complete", "none", "complete", True),
        (None, "partial", "partial", False),
        (None, "none", "none", False),
    ],
)
def test_the_transcripts_marker_wins_over_the_relayed_one(transcript, relayed, marker, disagrees):
    reading = resolve_marker(transcript, relayed)

    assert (reading.marker, reading.disagrees) == (marker, disagrees)


def test_a_complete_marker_with_a_red_check_is_completed_but_not_a_pass():
    """The golden bad case: the agent says done, the driver's own run says otherwise."""
    marker = parse_marker("All green, I checked.\n[COMPLETE]")
    check_run = classify_run(
        COMMAND, "FAILED scripts/test_x.py::t\n1 failed, 4 passed in 1s\n", ownership()
    )

    lines = gate_result_lines(green(), check_run)
    outcome = evaluate_check(CHECK, "10", results_text("10", lines))

    assert derive_stop_reason(marker, 5, 100) == "completed"
    assert check_run.red
    assert isinstance(outcome, Unmet)
    assert [item.key for item in outcome.unmet] == ["fail"]
