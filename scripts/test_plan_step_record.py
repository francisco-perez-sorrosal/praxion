"""Tests for the plan-step record (``scripts/_plan_steps.py``): ``parse_plan_steps``.

Two fixtures are real plan and WIP excerpts copied verbatim from an earlier
pipeline (``scripts/fixtures/``); the rest are hand-built plans, so every
annotation is pinned both against the shapes planners wrote and against the
edges they did not. The reader is pure: every case passes document text.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import Check, Expectation, UnreadableCheck  # noqa: E402
from _plan_steps import Implementer, OtherAssignee, PlanStep, parse_plan_steps  # noqa: E402
from _step_schema import STEP_ID_RE, checklist_step_id  # noqa: E402

STEP = "Step "
FIXTURES = SCRIPT_DIR / "fixtures"
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "hashlib",
    "re",
    "typing",
    "_loop_fields",
    "_step_schema",
}
FILES_LINE = "**Files**: `scripts/a.py`"
IMPLEMENTER_LINE = "**Assignee**: implementer"
CHECK_LINE = "**Check**: `uv run pytest scripts/test_a.py -q` expects pass>=2 fail=0"


def step(number, *lines, title="Do it", annotations="", level="###"):
    """One plan step: its heading, then each field line, then the blank line before the next."""
    body = "".join(f"{line}\n" for line in lines)
    return f"{level} {STEP}{number}: {title}{annotations}\n\n{body}\n"


def plan(*steps):
    return "## Steps\n\n" + "".join(steps)


def only(*lines, **kwargs):
    """The single step a one-step plan with these field lines declares."""
    return parse_plan_steps(plan(step("1", *lines, **kwargs)))[0]


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


PLAN_FIXTURE = fixture("step_schema_plan.md")
WIP_FIXTURE = fixture("step_schema_wip.md")
FIXTURE_STEPS = parse_plan_steps(PLAN_FIXTURE)
CHAIN_PLAN = plan(
    step("1", IMPLEMENTER_LINE, FILES_LINE),
    step("2", IMPLEMENTER_LINE, annotations=" [depends-on: 1]"),
    step("3", IMPLEMENTER_LINE, annotations=" [depends-on: 1, 2] [parallel-group: A]"),
    step("4", IMPLEMENTER_LINE, annotations=" [parallel-group: A] [depends-on: 2]"),
    step("5", IMPLEMENTER_LINE, annotations=" [depends-on: 99]"),
    step("6", IMPLEMENTER_LINE, annotations=" [depends-on: 7]"),
    step("7", IMPLEMENTER_LINE, annotations=" [depends-on: 6]"),
)


# -- The two real excerpts ----------------------------------------------------


def test_the_plan_excerpt_reads_its_six_steps_in_order():
    assert [s.id for s in FIXTURE_STEPS] == ["1", "2", "3", "4", "5", "6"]


def test_every_fixture_step_keeps_the_annotations_its_plan_declared():
    test_engineer = OtherAssignee("test-engineer")
    assert {s.id: (s.depends_on, s.assignee, s.routing, s.review) for s in FIXTURE_STEPS} == {
        "1": ((), test_engineer, "sonnet", "absent"),
        "2": ((), test_engineer, "sonnet", "absent"),
        "3": ((), Implementer(), "sonnet", "force"),
        "4": ((), Implementer(), "sonnet", "absent"),
        "5": ((), Implementer(), "sonnet", "absent"),
        "6": (("3", "4", "5"), Implementer(), "sonnet", "force"),
    }


def test_fixture_titles_drop_the_step_prefix_and_the_dependency_annotation():
    assert [s.title for s in FIXTURE_STEPS][2:] == [
        "[Phase: Refactoring] Extract the verdict state machine into its own module",
        "Parse and evaluate a step's `Check:` line (new `_loop_fields.py`)",
        "Parse a step's attempt count (`Attempts:` line and `ATTEMPT_CAP`)",
        "Check-first verdict with the attempt cap (`_step_verdict.py`)",
    ]


def test_fixture_files_and_read_only_entries_are_read_per_step():
    assert {s.id: (s.files, s.read_only) for s in FIXTURE_STEPS} == {
        "1": (("tests/acceptance/drivers/step_checks.py",), ()),
        "2": (("tests/acceptance/drivers/iteration_ledger.py",), ()),
        "3": (
            ("scripts/_step_verdict.py", "scripts/reconcile_pipeline_state.py"),
            (
                "tests/acceptance/test_legacy_pipelines_reconcile_as_before.py"
                "::test_legacy_pipeline_reconciles_to_the_same_verdicts_and_exit_status",
            ),
        ),
        "4": (("scripts/_loop_fields.py", "scripts/test_loop_fields.py"), ()),
        "5": (("scripts/_loop_fields.py", "scripts/test_loop_attempts.py"), ()),
        "6": (("scripts/_step_verdict.py", "scripts/test_step_verdict.py"), ()),
    }


def test_a_fixture_step_check_is_read_and_a_step_without_one_has_none():
    assert [type(s.check) for s in FIXTURE_STEPS] == [type(None)] * 2 + [Check] * 4
    assert FIXTURE_STEPS[2].check == Check(
        "uv run pytest scripts/test_reconcile_pipeline_state.py "
        "tests/acceptance/test_legacy_pipelines_reconcile_as_before.py -q --no-cov",
        (Expectation("pass", ">=", 130), Expectation("fail", "=", 0), Expectation("skip", "=", 0)),
    )


def test_the_fixture_blocks_hold_every_line_of_the_excerpt():
    blocks = "\n\n".join(s.block for s in FIXTURE_STEPS)
    assert PLAN_FIXTURE == "## Steps\n\n" + blocks + "\n"


def test_the_wip_excerpt_checks_off_the_same_steps_and_holds_no_plan_step():
    wip_ids = {checklist_step_id(line) for line in WIP_FIXTURE.splitlines()} - {None}
    assert wip_ids == {f"{STEP}{s.id}" for s in FIXTURE_STEPS}
    assert parse_plan_steps(WIP_FIXTURE) == ()


# -- Heading annotations ------------------------------------------------------


def test_a_dependency_chain_and_a_parallel_group_are_recorded_as_written():
    steps = parse_plan_steps(CHAIN_PLAN)
    assert {s.id: (s.depends_on, s.parallel_group) for s in steps} == {
        "1": ((), None),
        "2": (("1",), None),
        "3": (("1", "2"), "A"),
        "4": (("2",), "A"),
        "5": (("99",), None),
        "6": (("7",), None),
        "7": (("6",), None),
    }


@pytest.mark.parametrize(
    "annotations",
    [
        " [depends-on: 1] [parallel-group: B]",
        " [parallel-group: B] [depends-on: 1]",
        "  [DEPENDS-ON: 1]   [Parallel-Group: B]",
    ],
)
def test_annotations_in_any_order_or_case_leave_the_title_alone(annotations):
    parsed = only(annotations=annotations, title="Do it")
    assert (parsed.title, parsed.depends_on, parsed.parallel_group) == ("Do it", ("1",), "B")


def test_an_empty_parallel_group_annotation_names_no_group():
    assert only(annotations=" [parallel-group: ]").parallel_group is None


def test_another_bracketed_tag_stays_in_the_title():
    parsed = only(annotations=" [depends-on: 1] [Architecture]")
    assert parsed.title == "Do it [Architecture]"


@pytest.mark.parametrize(
    ("annotations", "expected"),
    [
        (" [depends-on: 1, soon]", ("1", "soon")),
        (" [depends-on: ]", ()),
        (" [depends-on: 1b,2]", ("1b", "2")),
        (" [depends-on: 1] [depends-on: 2]", ("1", "2")),
        ("", ()),
    ],
)
def test_depends_on_entries_are_kept_verbatim_even_when_they_name_no_step(annotations, expected):
    assert only(annotations=annotations).depends_on == expected


# -- Blocks and the digest ----------------------------------------------------


def test_a_block_ends_before_prose_under_a_heading_of_the_same_level():
    text = plan(
        step("1", FILES_LINE),
        "### Band B: notes\n\nprose that is not a step\n\n",
        step("2", FILES_LINE),
        "## Envelope\n\nclosing prose\n",
    )
    assert [s.block for s in parse_plan_steps(text)] == [
        f"### {STEP}1: Do it\n\n{FILES_LINE}",
        f"### {STEP}2: Do it\n\n{FILES_LINE}",
    ]


def test_a_deeper_heading_stays_inside_the_block():
    parsed = only("#### Notes", "more text")
    assert parsed.block.endswith("#### Notes\nmore text")


def test_a_heading_shaped_line_in_a_code_fence_does_not_close_the_block():
    parsed = only("```", "## not a heading", "```", FILES_LINE)
    assert parsed.block.endswith(f"```\n## not a heading\n```\n{FILES_LINE}")


@pytest.mark.parametrize("level", ["##", "###", "####"])
def test_a_step_heading_of_level_two_to_four_opens_a_step(level):
    assert [s.id for s in parse_plan_steps(step("3b", level=level))] == ["3b"]


def test_steps_sharing_an_id_are_all_kept_in_document_order():
    text = plan(step("1", FILES_LINE), step("1", "**Files**: `scripts/b.py`"))
    assert [s.files for s in parse_plan_steps(text)] == [("scripts/a.py",), ("scripts/b.py",)]


def test_text_with_no_step_heading_has_no_steps():
    assert parse_plan_steps("# Plan\n\n## Steps\n\nnothing here\n") == ()


def test_the_digest_is_a_twelve_character_prefix_of_the_blocks_sha256():
    parsed = only(FILES_LINE)
    assert parsed.digest == hashlib.sha256(parsed.block.encode("utf-8")).hexdigest()[:12]


@pytest.mark.parametrize(
    "edited",
    [
        step("1", FILES_LINE, "extra line"),
        step("1", FILES_LINE, title="Do that"),
        step("1", "**Files**: `scripts/b.py`"),
        step("1", FILES_LINE, annotations=" [depends-on: 2]"),
        step("1", FILES_LINE.replace("scripts", "script")),
    ],
)
def test_the_digest_changes_when_the_blocks_text_changes(edited):
    base = parse_plan_steps(plan(step("1", FILES_LINE)))[0]
    assert parse_plan_steps(plan(edited))[0].digest != base.digest


@pytest.mark.parametrize(
    "surroundings",
    [
        lambda own: plan(own),
        lambda own: plan(own) + "\n\n\n",
        lambda own: plan(own, "### Band B: notes\n\nprose\n\n"),
        lambda own: plan(own, step("2", "other text")),
        lambda own: plan(step("0", "earlier text"), own),
        lambda own: plan(own, "## Envelope\n\nclosing prose\n"),
    ],
)
def test_the_digest_ignores_everything_outside_the_block(surroundings):
    own = step("1", FILES_LINE)
    digests = {s.id: s.digest for s in parse_plan_steps(surroundings(own))}
    assert digests["1"] == parse_plan_steps(plan(own))[0].digest


def test_the_digest_is_a_function_of_the_text_so_parsing_twice_agrees():
    assert parse_plan_steps(CHAIN_PLAN) == parse_plan_steps(CHAIN_PLAN)


# -- Fields -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["**Assignee**: implementer"], Implementer()),
        (["**Assignee:** Implementer"], Implementer()),
        (["- Assignee: implementer (resumed)"], Implementer()),
        (["assignee: `implementer`"], Implementer()),
        (["**Assignee**: test-engineer"], OtherAssignee("test-engineer")),
        (["**Assignee**: orchestrator, with the user"], OtherAssignee("orchestrator")),
        (["**Assignee**: implementer-2"], OtherAssignee("implementer-2")),
        (["**Assignee**:"], OtherAssignee("unassigned")),
        ([], OtherAssignee("unassigned")),
    ],
)
def test_only_the_implementer_is_the_implementer(lines, expected):
    assert only(*lines).assignee == expected


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["tier: H"], "opus"),
        (["**tier**: h"], "opus"),
        (["tier: H   # cross-cutting"], "opus"),
        (["tier: L"], "sonnet"),
        (["tier: High"], "sonnet"),
        (["tier:"], "sonnet"),
        ([], "sonnet"),
        (["```", "tier: H", "```"], "sonnet"),
        (["The tier: H label routes to opus"], "sonnet"),
    ],
)
def test_tier_h_routes_to_opus_and_nothing_else_does(lines, expected):
    assert only(*lines).routing == expected


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["**review**: force"], "force"),
        (["review: off"], "off"),
        (["**review**: force   # spawn a reviewer regardless"], "force"),
        (["**Review:** OFF"], "off"),
        (["review: maybe"], "absent"),
        (["review:"], "absent"),
        ([], "absent"),
        (["```", "review: force", "```"], "absent"),
    ],
)
def test_review_reads_force_or_off_and_otherwise_is_absent(lines, expected):
    assert only(*lines).review == expected


def test_no_step_of_any_plan_here_routes_to_haiku():
    routings = {s.routing for s in FIXTURE_STEPS + parse_plan_steps(CHAIN_PLAN)}
    assert routings <= {"opus", "sonnet"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("`tests/acceptance/test_a.py`", ["tests/acceptance/test_a.py"]),
        (
            "`tests/acceptance/test_a.py::test_x`, `tests/acceptance/test_b.py`",
            ["tests/acceptance/test_a.py::test_x", "tests/acceptance/test_b.py"],
        ),
        (
            "`tests/acceptance/test_a.py::test_x[case one]`",
            ["tests/acceptance/test_a.py::test_x[case one]"],
        ),
        (
            "tests/acceptance/test_a.py, tests/acceptance/test_b.py::test_y",
            ["tests/acceptance/test_a.py", "tests/acceptance/test_b.py::test_y"],
        ),
        (
            "tests/acceptance/test_a.py (the rest belong to a later step)",
            ["tests/acceptance/test_a.py"],
        ),
        (
            "`tests/a.py`, contract: `tests/drivers/d.py::bind`, "
            "pinned by `tests/drivers/t.py::test_bind`",
            ["tests/a.py"],
        ),
        ("contract: tests/drivers/d.py::bind, pinned by tests/drivers/t.py::test_bind", []),
        ("none", []),
        ("", []),
    ],
)
def test_read_only_entries_are_paths_and_node_ids_but_never_a_contract(value, expected):
    assert list(only(f"**Read-only**: {value}").read_only) == expected


def test_two_read_only_lines_accumulate_and_a_fenced_one_is_ignored():
    parsed = only(
        "**Read-only**: `tests/a.py`",
        "```",
        "**Read-only**: `tests/never.py`",
        "```",
        "**Read-only**: `tests/b.py`",
    )
    assert parsed.read_only == ("tests/a.py", "tests/b.py")


def test_files_come_from_the_moved_reader_including_a_wrapped_value_and_none():
    wrapped = only("**Files**: `scripts/a.py`,", "`scripts/b.py`")
    assert wrapped.files == ("scripts/a.py", "scripts/b.py")
    assert only("**Files**: none").files == ()
    assert only().files == ()


def test_a_field_inside_a_code_fence_is_not_read_for_any_field():
    parsed = only("```", FILES_LINE, IMPLEMENTER_LINE, CHECK_LINE, "```")
    assert (parsed.files, parsed.assignee, parsed.check) == (
        (),
        OtherAssignee("unassigned"),
        None,
    )


def test_a_check_is_read_by_the_check_parser_and_a_second_one_is_unreadable():
    readable = only(CHECK_LINE)
    assert readable.check == Check(
        "uv run pytest scripts/test_a.py -q",
        (Expectation("pass", ">=", 2), Expectation("fail", "=", 0)),
    )
    assert only(CHECK_LINE, CHECK_LINE).check == UnreadableCheck("declared twice", CHECK_LINE)
    assert only().check is None


# -- The record ----------------------------------------------------------------


def test_a_plan_step_cannot_be_changed_after_it_is_read():
    parsed = only(FILES_LINE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        parsed.title = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("change", "complaint"),
    [({"id": "x1"}, "not a step id"), ({"digest": "0" * 12}, "digest")],
)
def test_a_plan_step_with_an_unparseable_id_or_a_foreign_digest_is_refused(change, complaint):
    fields = {**dataclasses.asdict(only(FILES_LINE)), **change}
    with pytest.raises(ValueError, match=complaint):
        PlanStep(**fields)


def test_every_step_id_the_reader_produces_fits_the_step_id_grammar():
    steps = FIXTURE_STEPS + parse_plan_steps(CHAIN_PLAN) + parse_plan_steps(step("12b"))
    assert {bool(STEP_ID_RE.match(s.id)) for s in steps} == {True}


def test_the_module_imports_nothing_that_does_io():
    tree = ast.parse((SCRIPT_DIR / "_plan_steps.py").read_text(encoding="utf-8"))
    imported = {
        name.split(".")[0]
        for node in ast.walk(tree)
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    }
    assert imported <= ALLOWED_IMPORTS
