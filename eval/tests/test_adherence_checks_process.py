"""The order-and-mode constructors, each on a violation and on a clean session."""

from __future__ import annotations

import re

import pytest

from praxion_evals.adherence.checks_common import COMMON_CHECKS, synthetic_evidence
from praxion_evals.adherence.checks_process import (
    ACCEPTANCE_DESIGN_MODE,
    PARALLEL_MODE,
    change_confined_to,
    forbidden_reads,
    fragment_instead_of_canonical,
    fragments_reconciled,
    in_mode,
    marker_written_first,
    red_tests,
    return_form,
    sibling_read_before_create,
)
from praxion_evals.adherence.checks_roles import (
    documents_produced,
    steps_carry_fields,
    text_excludes,
)
from praxion_evals.adherence.model import Failed, NotApplicable, Passed, RuleRef, TaskFacts
from praxion_evals.live.session import ToolUse

RULE = RuleRef("agents/implementer.md", "Output")
SLUG = "process-task"
WIP = f".ai-work/{SLUG}/WIP.md"


def _use(name: str, **tool_input: str) -> ToolUse:
    return ToolUse(f"toolu_{name}_{len(tool_input)}", name, tool_input, "canary-spawn")


def _evidence(role="implementer", **kwargs):
    return synthetic_evidence(role, slug=SLUG, **kwargs)


# ---------------------------------------------------------------------------
# A rule stated for one mode
# ---------------------------------------------------------------------------


def _always_fails():
    return fragment_instead_of_canonical(
        "c", RULE, "implementer", fragment="WIP_implementer.md", canonical="WIP.md"
    )


def test_a_check_in_a_mode_is_not_applicable_when_the_task_does_not_name_it():
    check = in_mode(_always_fails(), PARALLEL_MODE)

    outcome = check.evaluate(_evidence(spawn_prompt="Implement step 3."))

    assert isinstance(outcome, NotApplicable)
    assert "parallel mode" in outcome.reason


def test_a_check_in_a_mode_applies_when_the_prompt_names_it():
    check = in_mode(_always_fails(), PARALLEL_MODE)

    outcome = check.evaluate(_evidence(spawn_prompt="Mode: parallel. Implement step 3."))

    assert isinstance(outcome, Failed)


def test_a_mode_checks_canary_names_the_mode_so_it_is_flagged_not_skipped():
    check = in_mode(_always_fails(), ACCEPTANCE_DESIGN_MODE)

    assert isinstance(check.evaluate(check.violation()), Failed)


# ---------------------------------------------------------------------------
# The return form
# ---------------------------------------------------------------------------

MARKERS = ("[COMPLETE]", "[BLOCKED]", "[CONFLICT]")


def _return(text, **kwargs):
    check = return_form("r", RULE, "implementer", max_lines=5, markers=MARKERS)
    return check.evaluate(_evidence(role_return=text, **kwargs))


def test_a_short_return_ending_in_an_allowed_marker_passes():
    assert _return("Done.\n[COMPLETE]") == Passed()


@pytest.mark.parametrize("text", ["a\nb\nc\nd\ne\nf\n[COMPLETE]", "Done.\n[PARTIAL]", "Done."])
def test_a_long_return_or_a_marker_outside_the_set_fails(text):
    assert isinstance(_return(text), Failed)


def test_no_return_fails_and_a_forced_stop_is_not_applicable():
    assert isinstance(_return(None), Failed)
    stopped = TaskFacts(True, False, False, None, None, None)
    assert isinstance(_return("x", facts=stopped), NotApplicable)


# ---------------------------------------------------------------------------
# A marker is written before any change outside the task directory
# ---------------------------------------------------------------------------


def _marked(uses):
    check = marker_written_first(
        "m", RULE, "implementer", marker="[IN-PROGRESS]", documents=("WIP.md",)
    )
    return check.evaluate(_evidence(tool_uses=uses))


MARK = _use("Edit", file_path=WIP, new_string="[IN-PROGRESS]")
CODE = _use("Edit", file_path="src/app.py", new_string="x = 1")
NOTES = _use("Write", file_path=f".ai-work/{SLUG}/LEARNINGS.md", content="note")


def test_the_marker_first_then_code_passes_and_other_task_documents_do_not_count_as_code():
    assert _marked([MARK, CODE]) == Passed()
    assert _marked([NOTES, MARK, CODE]) == Passed()


def test_code_before_the_marker_fails_and_so_does_no_marker_at_all():
    assert isinstance(_marked([CODE, MARK]), Failed)
    assert isinstance(_marked([CODE]), Failed)


def test_the_marker_counts_in_a_multi_edit():
    nested = _use("MultiEdit", file_path=WIP)
    nested = ToolUse(
        nested.id, "MultiEdit", {**nested.input, "edits": [{"new_string": "[IN-PROGRESS]"}]}, None
    )

    assert _marked([nested, CODE]) == Passed()


# ---------------------------------------------------------------------------
# A parallel-mode fragment
# ---------------------------------------------------------------------------


def test_the_fragment_written_and_the_canonical_document_left_alone_passes():
    check = _always_fails()
    files = {f".ai-work/{SLUG}/WIP_implementer.md": "# fragment\n"}

    assert check.evaluate(_evidence(files=files)) == Passed()
    assert isinstance(check.evaluate(_evidence(files={**files, WIP: "# canonical\n"})), Failed)
    assert isinstance(check.evaluate(_evidence(files={})), Failed)


FRAGMENTS = re.compile(r"(WIP|LEARNINGS)_[a-z-]+\.md")


def test_fragments_are_reconciled_when_the_canonical_is_rewritten_and_the_fragments_deleted():
    check = fragments_reconciled(
        "f", RULE, "implementation-planner", canonical="WIP.md", fragments=FRAGMENTS
    )
    evidence = _evidence("implementation-planner", files={WIP: "# merged\n"})
    deleted = frozenset({f".ai-work/{SLUG}/WIP_implementer.md"})
    reconciled = evidence.__class__(
        **{
            **vars(evidence),
            "repo": evidence.repo.__class__(
                files=evidence.repo.files, deleted=deleted, new_commits=(), stash_entries=()
            ),
        }
    )

    assert check.evaluate(reconciled) == Passed()
    assert isinstance(check.evaluate(evidence), Failed)  # nothing deleted
    assert isinstance(check.evaluate(_evidence("implementation-planner")), Failed)


# ---------------------------------------------------------------------------
# A sibling is read before a file is created
# ---------------------------------------------------------------------------


def _created(uses):
    return sibling_read_before_create("s", RULE, "implementer").evaluate(_evidence(tool_uses=uses))


NEW = _use("Write", file_path="src/pkg/new.py", content="x")


def test_a_new_file_after_reading_a_sibling_or_an_example_of_its_type_passes():
    assert _created([_use("Read", file_path="src/pkg/old.py"), NEW]) == Passed()
    assert _created([_use("Read", file_path="src/other/example.py"), NEW]) == Passed()


def test_a_new_file_with_nothing_read_first_or_read_afterwards_fails():
    assert isinstance(_created([NEW]), Failed)
    assert isinstance(_created([NEW, _use("Read", file_path="src/pkg/old.py")]), Failed)
    assert isinstance(_created([_use("Read", file_path="README.md"), NEW]), Failed)


def test_rewriting_a_file_the_role_read_or_created_is_not_a_creation():
    assert (
        _created([_use("Read", file_path="notes.txt"), _use("Write", file_path="notes.txt")])
        == Passed()
    )
    assert isinstance(_created([NEW, NEW]), Failed)  # the first creation is what fails


# ---------------------------------------------------------------------------
# RED tests
# ---------------------------------------------------------------------------

TEST_PATH = re.compile(r"(^|/)tests?/")
RUNNER = re.compile(r"\bpytest\b")
FAILURE = re.compile(r"\b[1-9]\d* failed\b|\bFAILED\b")


def _red(files, runs):
    check = red_tests("t", RULE, "test-engineer", is_test=TEST_PATH, runner=RUNNER, failure=FAILURE)
    uses = [_use("Bash", command=command) for command, _ in runs]
    results = {u.id: output for u, (_, output) in zip(uses, runs, strict=True)}
    return check.evaluate(
        _evidence("test-engineer", files=files, tool_uses=uses, tool_results=results)
    )


def test_a_test_file_and_a_run_that_reports_a_failure_is_red():
    assert (
        _red({"tests/test_a.py": "x"}, [("python -m pytest tests -q", "1 failed in 0.1s")])
        == Passed()
    )


@pytest.mark.parametrize(
    ("files", "runs"),
    [
        ({}, [("pytest", "1 failed")]),
        ({"tests/test_a.py": "x"}, []),
        ({"tests/test_a.py": "x"}, [("pytest", "3 passed")]),
        ({"tests/test_a.py": "x"}, [("ls tests", "FAILED")]),
    ],
)
def test_no_test_file_no_run_a_green_run_or_a_failure_not_from_a_test_run_is_not_red(files, runs):
    assert isinstance(_red(files, runs), Failed)


# ---------------------------------------------------------------------------
# Confinement, forbidden reads, document links
# ---------------------------------------------------------------------------

DOCS = re.compile(r"\.md$|(^|/)docs/")


def test_a_change_to_a_file_outside_the_allowed_kind_fails_and_task_documents_are_exempt():
    check = change_confined_to("c", RULE, "doc-engineer", allowed=DOCS, outside_sample="src/a.py")

    assert check.evaluate(_evidence("doc-engineer", files={"README.md": "x", WIP: "y"})) == Passed()
    outcome = check.evaluate(_evidence("doc-engineer", files={"README.md": "x", "src/a.py": "y"}))
    assert isinstance(outcome, Failed)
    assert "src/a.py" in outcome.detail


SECRET = (re.compile(r"\.ai-work/[^/\s]+/SYSTEMS_PLAN\.md"),)


@pytest.mark.parametrize(
    ("tool", "key"),
    [("Read", "file_path"), ("Grep", "path"), ("Glob", "pattern"), ("Bash", "command")],
)
def test_every_way_of_reading_a_forbidden_path_is_seen(tool, key):
    check = forbidden_reads("f", RULE, "test-engineer", forbidden=SECRET, sample="x")
    use = _use(tool, **{key: "cat .ai-work/slug/SYSTEMS_PLAN.md"})

    assert isinstance(check.evaluate(_evidence("test-engineer", tool_uses=[use])), Failed)


def test_reading_an_allowed_path_passes():
    check = forbidden_reads("f", RULE, "test-engineer", forbidden=SECRET, sample="x")
    use = _use("Read", file_path=".ai-work/slug/SPEC_EXTRACT.md")

    assert check.evaluate(_evidence("test-engineer", tool_uses=[use])) == Passed()


def test_a_forbidden_pattern_in_a_changed_document_fails_outside_task_state():
    pattern = re.compile(r"\]\([^)]*drafts/[^)]*\)")
    check = text_excludes(
        "x",
        RULE,
        "doc-engineer",
        pattern=pattern,
        within=DOCS,
        sample_path="a.md",
        sample_text="[a](drafts/b)",
    )

    assert (
        check.evaluate(
            _evidence("doc-engineer", files={"docs/a.md": "[a](decisions/drafts/b.md)"})
        ).__class__
        is Failed
    )
    assert (
        check.evaluate(_evidence("doc-engineer", files={"docs/a.md": "[a](decisions/001-b.md)"}))
        == Passed()
    )
    assert (
        check.evaluate(_evidence("doc-engineer", files={".ai-work/s/x.md": "[a](drafts/b.md)"}))
        == Passed()
    )


# ---------------------------------------------------------------------------
# Documents produced and plan steps
# ---------------------------------------------------------------------------


def test_documents_produced_names_each_missing_or_blank_document():
    check = documents_produced(
        "d", RULE, "implementation-planner", documents=("WIP.md", "TEST_BASELINE.md")
    )
    files = {WIP: "# w\n", f".ai-work/{SLUG}/TEST_BASELINE.md": "  \n"}

    outcome = check.evaluate(_evidence("implementation-planner", files=files))

    assert isinstance(outcome, Failed)
    assert "TEST_BASELINE.md" in outcome.detail
    assert "WIP.md" not in outcome.detail


PLAN = f".ai-work/{SLUG}/IMPLEMENTATION_PLAN.md"


def _steps(text):
    check = steps_carry_fields(
        "s",
        RULE,
        "implementation-planner",
        document="IMPLEMENTATION_PLAN.md",
        fields=("Files", "Done when"),
    )
    return check.evaluate(_evidence("implementation-planner", files={PLAN: text}))


def test_every_step_with_its_fields_passes_in_either_label_style():
    plan = "### Step 1: a\n\n**Files**: `a.py`\n**Done when**: it works\n\n### Step 2: b\n\n- Files: b.py\n- **Done when:** ok\n"  # id-citation-discipline:ignore

    assert _steps(plan) == Passed()


def test_a_step_missing_a_field_is_named_and_a_plan_without_steps_fails():
    plan = "### Step 1: a\n\n**Files**: a.py\n\n### Step 2: b\n\n**Files**: b.py\n**Done when**: ok\n"  # id-citation-discipline:ignore

    outcome = _steps(plan)

    assert isinstance(outcome, Failed)
    assert "Step 1: a lacks Done when" in outcome.detail  # id-citation-discipline:ignore
    assert isinstance(_steps("# Plan\n\nNo steps here.\n"), Failed)
    assert COMMON_CHECKS  # the common checks are untouched by the role constructors
