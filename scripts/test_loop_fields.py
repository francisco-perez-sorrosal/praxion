"""Tests for the `Check:` grammar and its evaluation (``scripts/_loop_fields.py``).

The grammar is table-tested (every valid form, one case per invariant), the
evaluator is table-tested against recorded `Result:` lines (met, each unmet
key, no result), and a canary proves a command carrying result- or
mutation-shaped text cannot change what the step-document readers see.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _loop_fields as fields  # noqa: E402
from _step_schema import mutation_tagged_steps, split_step_blocks  # noqa: E402

COMMAND = "uv run pytest tests/test_widget.py -q"


def label(number: int) -> str:
    """A step's label as the step-document readers key it."""
    return f"Step {number}"


def check_line(*expectations: str, command: str = COMMAND, label: str = "**Check**:") -> str:
    return f"{label} `{command}` expects {' '.join(expectations)}"


def parsed_check(*expectations: str) -> fields.Check:
    reading = fields.parse_check_field(check_line(*expectations))
    assert isinstance(reading, fields.Check)
    return reading


def results_text(*blocks: tuple[str, tuple[str, ...]]) -> str:
    """A TEST_RESULTS.md body: one `## <step> -- title` block per (step label, lines) pair."""
    return "\n\n".join(
        f"## {step} — a block\n\nCommand: `pytest`\n" + "\n".join(lines) for step, lines in blocks
    )


# ---------------------------------------------------------------------------
# The grammar: valid forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        f"**Check**: `{COMMAND}` expects pass>=4 fail=0",
        f"Check: `{COMMAND}` expects pass>=4 fail=0",
        f"- **Check**: `{COMMAND}` expects pass>=4 fail=0",
        f"**Check:** `{COMMAND}` expects pass>=4 fail=0",
        f"  Check:   `{COMMAND}`   expects   pass>=4   fail=0  ",
        f"**Check**: `{COMMAND}` expects fail=0 pass>=4",
    ],
)
def test_every_label_form_reads_the_same_command_and_expectations(line: str) -> None:
    reading = fields.parse_check_field(line)

    assert isinstance(reading, fields.Check)
    assert reading.command == COMMAND
    assert {(e.key, e.op, e.count) for e in reading.expectations} == {
        ("pass", ">=", 4),
        ("fail", "=", 0),
    }


def test_all_four_keys_both_operators_and_declared_order_are_kept() -> None:
    reading = parsed_check("pass>=135", "fail=0", "skip=0", "pending>=17")

    assert [(e.key, e.op, e.count) for e in reading.expectations] == [
        ("pass", ">=", 135),
        ("fail", "=", 0),
        ("skip", "=", 0),
        ("pending", ">=", 17),
    ]


def test_a_command_may_carry_result_and_mutation_shaped_text() -> None:
    command = "pytest -k 'a or b' | tee out; echo Result: pass=0 mutation: on"

    reading = fields.parse_check_field(check_line("pass>=1", "fail=0", command=command))

    assert isinstance(reading, fields.Check)
    assert reading.command == command


def test_the_example_in_the_module_docstring_parses() -> None:
    examples = [
        line.strip()
        for line in (fields.__doc__ or "").splitlines()
        if "`" in line and "pass>=4" in line
    ]

    assert len(examples) == 1
    reading = fields.parse_check_field(examples[0])
    assert isinstance(reading, fields.Check)
    assert (reading.command, len(reading.expectations)) == (
        "uv run pytest tests/test_widget.py -q",
        3,
    )


def test_the_one_line_grammar_constant_is_the_line_the_docstring_states() -> None:
    assert fields.CHECK_GRAMMAR_LINE in (fields.__doc__ or "")


@pytest.mark.parametrize("expectations", [("pass>=1", "fail=0"), ("pass=7", "fail=0", "skip>=0")])
def test_a_rendered_check_parses_back_to_the_same_value(expectations: tuple[str, ...]) -> None:
    reading = parsed_check(*expectations)
    rendered = check_line(*(f"{e.key}{e.op}{e.count}" for e in reading.expectations))

    assert fields.parse_check_field(rendered) == reading


# ---------------------------------------------------------------------------
# The grammar: one case per invariant violation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "reason_part"),
    [
        (check_line("pass>=4"), "missing required key(s): fail"),
        (check_line("fail=0"), "missing required key(s): pass"),
        ("**Check**: `x` expects", "missing required key(s): pass, fail"),
        (check_line("pass>=4", "fail=0", "pass=4"), "key declared twice: pass"),
        (check_line("pass>=4", "fail=0", "flaky=0"), "unknown key: flaky"),
        (check_line("pass>=4", "fail=0", "extra"), "unreadable expectation: 'extra'"),
        (check_line("pass>4", "fail=0"), "unreadable expectation: 'pass>4'"),
        (check_line("pass==4", "fail=0"), "unreadable expectation: 'pass==4'"),
        (check_line("pass>=x", "fail=0"), "unreadable expectation: 'pass>=x'"),
        (check_line("pass>=-1", "fail=0"), "unreadable expectation: 'pass>=-1'"),
        (check_line("pass>=٣", "fail=0"), "unreadable expectation"),
        (check_line("Pass>=4", "fail=0"), "unreadable expectation"),
        ("**Check**: pytest expects pass>=4 fail=0", "wrapped in backticks"),
        ("**Check**: `pytest expects pass>=4 fail=0", "wrapped in backticks"),
        ("**Check**: `` expects pass>=4 fail=0", "the command is empty"),
        ("**Check**: `a `b` c` expects pass>=4 fail=0", "contains a backtick"),
        ("**Check**: `pytest` pass>=4 fail=0", "`expects` must follow"),
    ],
)
def test_a_line_that_breaks_the_grammar_is_unreadable_and_names_why(
    line: str, reason_part: str
) -> None:
    reading = fields.parse_check_field(line)

    assert isinstance(reading, fields.UnreadableCheck)
    assert reason_part in reading.reason
    assert reading.line == line.strip()


@pytest.mark.parametrize(
    "line",
    [
        "Checking the result by hand",
        "**Done when**: the `Check:` result is met",
        "Result: pass=3 fail=0",
        "check: `x` expects pass>=1 fail=0",
        "Check protocol: run it",
        "",
    ],
)
def test_a_line_that_is_not_a_check_line_is_none(line: str) -> None:
    assert fields.parse_check_field(line) is None


# ---------------------------------------------------------------------------
# Reading a plan: one entry per declaring step
# ---------------------------------------------------------------------------

PLAN = f"""# Plan: widget

## Steps

### {label(1)}: First

**Files**: a.py
**Tests**: full
**Done when**: it works.

### {label(2)}: Second

**Files**: b.py
{check_line("pass>=4", "fail=0")}
**Done when**: the `Check:` result is met.

### {label(3)}: Third

- {check_line("pass>=1", "fail=0", "pending=2")}
"""


def test_a_plan_with_no_check_line_yields_an_empty_map() -> None:
    legacy = PLAN.split(f"### {label(2)}")[0]

    assert fields.parse_step_checks(legacy) == {}


def test_each_check_belongs_to_its_own_step_and_a_step_without_one_has_no_entry() -> None:
    checks = fields.parse_step_checks(PLAN)

    assert sorted(checks) == [label(2), label(3)]
    assert checks[label(2)] == parsed_check("pass>=4", "fail=0")
    third = checks[label(3)]
    assert isinstance(third, fields.Check)
    assert [e.key for e in third.expectations] == ["pass", "fail", "pending"]


def test_an_unreadable_line_is_reported_under_its_step() -> None:
    plan = f"### {label(4)}: Fourth\n\n**Check**: `pytest` expects pass>=1\n"

    reading = fields.parse_step_checks(plan)[label(4)]

    assert isinstance(reading, fields.UnreadableCheck)
    assert reading.reason == "missing required key(s): fail"


def test_two_check_lines_in_one_step_are_unreadable_as_declared_twice() -> None:
    plan = f"### {label(5)}: Fifth\n\n{check_line('pass>=1', 'fail=0')}\n{check_line('pass>=2', 'fail=0')}\n"

    reading = fields.parse_step_checks(plan)[label(5)]

    assert isinstance(reading, fields.UnreadableCheck)
    assert reading.reason == "declared twice"


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_a_check_line_inside_a_code_fence_declares_nothing(fence: str) -> None:
    plan = f"### {label(6)}: Sixth\n\n{fence}\n{check_line('pass>=1', 'fail=0')}\n{fence}\n"

    assert fields.parse_step_checks(plan) == {}


def test_a_check_line_after_a_closed_fence_is_read() -> None:
    plan = f"### {label(6)}: Sixth\n\n```\nexample\n```\n{check_line('pass>=1', 'fail=0')}\n"

    assert label(6) in fields.parse_step_checks(plan)


def test_a_check_line_before_any_step_heading_belongs_to_no_step() -> None:
    plan = f"# Plan\n\n{check_line('pass>=1', 'fail=0')}\n\n### {label(1)}: One\n"

    assert fields.parse_step_checks(plan) == {}


def test_a_command_with_result_or_mutation_text_changes_neither_reader() -> None:
    command = "echo Result: pass=0 fail=9 and mutation: on"
    plan = f"### {label(7)}: Seventh\n\n{check_line('pass>=1', 'fail=0', command=command)}\n"

    (block,) = split_step_blocks(plan)
    assert block.results == ()
    assert block.mutation is None
    assert mutation_tagged_steps(plan) == frozenset()
    reading = fields.parse_step_checks(plan)[label(7)]
    assert isinstance(reading, fields.Check)
    assert reading.command == command


# ---------------------------------------------------------------------------
# Judging a check against a recorded result
# ---------------------------------------------------------------------------


def judge(check: fields.Check, *lines: str, step: str = label(3)) -> fields.CheckOutcome:
    return fields.evaluate_check(check, step, results_text((step, lines)))


def test_a_result_that_meets_every_declared_expectation_is_met() -> None:
    outcome = judge(parsed_check("pass>=4", "fail=0", "skip=0"), "Result: pass=130 fail=0 skip=0")

    assert outcome == fields.Met()


def test_the_at_least_operator_holds_at_the_boundary() -> None:
    assert judge(parsed_check("pass>=130", "fail=0"), "Result: pass=130 fail=0") == fields.Met()


@pytest.mark.parametrize(
    ("expectations", "result_line", "rendered"),
    [
        (("pass>=135", "fail=0"), "Result: pass=130 fail=0", "pass=: expected >=135, observed 130"),
        (("pass=130", "fail=0"), "Result: pass=131 fail=0", "pass=: expected =130, observed 131"),
        (("pass>=1", "fail=0"), "Result: pass=5 fail=2", "fail=: expected =0, observed 2"),
        (
            ("pass>=1", "fail=0", "skip=0"),
            "Result: pass=5 fail=0 skip=3",
            "skip=: expected =0, observed 3",
        ),
        (
            ("pass>=1", "fail=0", "pending=0"),
            "Result: pass=5 fail=0 pending=2",
            "pending=: expected =0, observed 2",
        ),
        (
            ("pass>=1", "fail=0", "pending=17"),
            "Result: pass=5 fail=0",
            "pending=: expected =17, observed 0",
        ),
    ],
)
def test_each_unmet_key_is_named_with_expected_and_observed(
    expectations: tuple[str, ...], result_line: str, rendered: str
) -> None:
    outcome = judge(parsed_check(*expectations), result_line)

    assert isinstance(outcome, fields.Unmet)
    assert [item.render() for item in outcome.unmet] == [rendered]


def test_every_unmet_expectation_is_listed_in_declared_order() -> None:
    outcome = judge(parsed_check("fail=0", "pass>=10"), "Result: pass=3 fail=1")

    assert isinstance(outcome, fields.Unmet)
    assert [item.key for item in outcome.unmet] == ["fail", "pass"]


def test_pending_is_read_from_the_raw_result_line_and_absent_means_zero() -> None:
    with_pending = judge(
        parsed_check("pass>=1", "fail=0", "pending=17"), "Result: pass=9 fail=0 pending=17"
    )
    without = judge(parsed_check("pass>=1", "fail=0", "pending=0"), "Result: pass=9 fail=0")

    assert with_pending == fields.Met()
    assert without == fields.Met()


def test_a_key_the_check_does_not_declare_is_not_judged() -> None:
    assert (
        judge(parsed_check("pass>=1", "fail=0"), "Result: pass=5 fail=0 skip=9 pending=4")
        == fields.Met()
    )


@pytest.mark.parametrize("pending", ["pending=abc", "pending=", "pending=1 pending=2"])
def test_an_unreadable_pending_is_no_result_when_the_check_declares_it(pending: str) -> None:
    outcome = judge(
        parsed_check("pass>=1", "fail=0", "pending=0"), f"Result: pass=5 fail=0 {pending}"
    )

    assert isinstance(outcome, fields.NoResult)
    assert "pending=" in outcome.reason


def test_an_unreadable_pending_is_ignored_when_the_check_does_not_declare_it() -> None:
    assert (
        judge(parsed_check("pass>=1", "fail=0"), "Result: pass=5 fail=0 pending=abc")
        == fields.Met()
    )


# ---------------------------------------------------------------------------
# Judging: no result speaks for the step
# ---------------------------------------------------------------------------

CHECK = parsed_check("pass>=1", "fail=0")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# Test Results\n\nnothing recorded\n",
        results_text((label(4), ("Result: pass=9 fail=0",))),
        results_text((label(30), ("Result: pass=9 fail=0",))),
        results_text((label(3), ("Result: none -- measurement",))),
        results_text((label(3), ("Result: pass=9",))),
        results_text((label(3), ("Outcome: all green",))),
        "Result: pass=9 fail=0\n",
    ],
)
def test_no_countable_result_for_the_step_is_never_met(text: str) -> None:
    outcome = fields.evaluate_check(CHECK, label(3), text)

    assert outcome == fields.NoResult(f"no Result: recorded for {label(3)}")


def test_the_latest_counts_line_decides_so_a_later_green_rerun_supersedes_a_red_one() -> None:
    lines = ("Result: pass=5 fail=3", "Result: pass=8 fail=0")

    assert judge(CHECK, *lines) == fields.Met()
    assert isinstance(judge(CHECK, *reversed(lines)), fields.Unmet)


def test_a_later_line_that_is_not_a_count_does_not_hide_the_latest_count() -> None:
    outcome = judge(CHECK, "Result: pass=5 fail=0", "Result: none -- note", "Result: pass=oops")

    assert outcome == fields.Met()


def test_a_step_label_without_the_word_step_names_the_same_block() -> None:
    text = results_text((label(3), ("Result: pass=2 fail=0",)))

    assert fields.evaluate_check(CHECK, "3", text) == fields.Met()


def test_the_latest_line_across_a_steps_blocks_decides() -> None:
    text = results_text(
        (label(3), ("Result: pass=5 fail=0",)),
        (label(4), ("Result: pass=9 fail=0",)),
        (label(3), ("Result: pass=5 fail=2",)),
    )

    assert isinstance(fields.evaluate_check(CHECK, label(3), text), fields.Unmet)


# ---------------------------------------------------------------------------
# Module discipline
# ---------------------------------------------------------------------------


def test_the_module_never_imports_the_reconciler() -> None:
    tree = ast.parse((SCRIPT_DIR / "_loop_fields.py").read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not any("reconcile" in name for name in imported)


def test_the_module_uses_no_match_statement_so_it_loads_under_the_ambient_python() -> None:
    tree = ast.parse((SCRIPT_DIR / "_loop_fields.py").read_text())

    assert not any(isinstance(node, ast.Match) for node in ast.walk(tree))
