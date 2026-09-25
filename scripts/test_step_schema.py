"""Contract tests for the shared step-document grammar (``scripts/_step_schema.py``).

Written before the module exists (paired BDD/TDD ordering) directly from the
architecture's declared interface -- not from the implementer's code. Two
readers (the shape checker and the reconciler) both classify a step's test
outcome and split a document into step blocks through this one module, so
every behavioral requirement it must satisfy is pinned here once rather than
twice.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_schema as schema  # noqa: E402

# ---------------------------------------------------------------------------
# STEP_ID_RE -- the bare "<digits><optional lowercase letter>" grammar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("candidate", ["1", "1b", "12c"])
def test_step_id_re_accepts_digits_with_an_optional_lowercase_letter_suffix(
    candidate: str,
) -> None:
    assert schema.STEP_ID_RE.fullmatch(candidate) is not None


def test_step_id_re_rejects_a_leading_letter() -> None:
    assert schema.STEP_ID_RE.fullmatch("Nb1") is None


# ---------------------------------------------------------------------------
# step_id_from_heading -- recognizes a "#{2,4} Step <id>" heading line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("## Step 1", "Step 1"),  # id-citation-discipline:ignore
        ("### Step 1b: title", "Step 1b"),  # id-citation-discipline:ignore
        ("#### Step 12c (parenthetical)", "Step 12c"),  # id-citation-discipline:ignore
    ],
)
def test_step_id_from_heading_recognizes_headings_at_levels_two_through_four(
    heading: str, expected: str
) -> None:
    assert schema.step_id_from_heading(heading) == expected


@pytest.mark.parametrize(
    "heading",
    [
        "## Command",
        "# Step 1",  # id-citation-discipline:ignore -- level 1, outside the grammar
        "##### Step 1",  # id-citation-discipline:ignore -- level 5, outside the grammar
    ],
)
def test_step_id_from_heading_rejects_non_step_headings(heading: str) -> None:
    assert schema.step_id_from_heading(heading) is None


# ---------------------------------------------------------------------------
# step_sort_key -- letter-suffixed ids sort between their numeric neighbors
# ---------------------------------------------------------------------------


def test_step_sort_key_orders_a_letter_suffixed_id_between_its_numeric_neighbors() -> None:
    steps = ["Step 10", "Step 2", "Step 1b", "Step 1"]  # id-citation-discipline:ignore

    ordered = sorted(steps, key=schema.step_sort_key)

    assert ordered == ["Step 1", "Step 1b", "Step 2", "Step 10"]  # id-citation-discipline:ignore


# ---------------------------------------------------------------------------
# parse_result_line -- the Counts | NoRun | Malformed | None sum type
# ---------------------------------------------------------------------------


def test_all_zero_counts_is_red_even_though_nothing_failed() -> None:
    """td-214: a Result line that proves nothing (pass=0, fail=0) is red, not
    green -- a zero total is never mistaken for a clean run."""
    result = schema.parse_result_line("Result: pass=0 fail=0 skip=0")

    assert isinstance(result, schema.Counts)
    assert result.status == schema.RED


def test_zero_new_failures_with_passing_tests_is_green() -> None:
    result = schema.parse_result_line("Result: pass=10 fail=0 preexisting=2")

    assert isinstance(result, schema.Counts)
    assert result.status == schema.GREEN


def test_new_failures_on_top_of_preexisting_ones_is_red() -> None:
    result = schema.parse_result_line("Result: pass=10 fail=2 preexisting=2")

    assert isinstance(result, schema.Counts)
    assert result.status == schema.RED


@pytest.mark.parametrize("preexisting", [0, 1, 2, 7, 50, 9999])
def test_a_green_lines_status_never_depends_on_the_preexisting_value(
    preexisting: int,
) -> None:
    result = schema.parse_result_line(f"Result: pass=10 fail=0 preexisting={preexisting}")

    assert isinstance(result, schema.Counts)
    assert result.status == schema.GREEN


@pytest.mark.parametrize("preexisting", [0, 1, 2, 7, 50, 9999])
def test_a_red_lines_status_never_depends_on_the_preexisting_value(preexisting: int) -> None:
    result = schema.parse_result_line(f"Result: pass=10 fail=2 preexisting={preexisting}")

    assert isinstance(result, schema.Counts)
    assert result.status == schema.RED


@pytest.mark.parametrize(
    "line",
    [
        "Result: fail=0 skip=0",  # missing pass=
        "Result: pass=10 skip=0",  # missing fail=
    ],
)
def test_a_result_line_missing_a_required_key_is_malformed(line: str) -> None:
    result = schema.parse_result_line(line)

    assert isinstance(result, schema.Malformed)
    assert result.reason


def test_a_repeated_known_key_is_malformed() -> None:
    result = schema.parse_result_line("Result: pass=10 pass=5 fail=0")

    assert isinstance(result, schema.Malformed)
    assert result.reason


def test_a_value_that_is_neither_counts_nor_none_is_malformed() -> None:
    result = schema.parse_result_line("Result: banana")

    assert isinstance(result, schema.Malformed)
    assert result.reason


def test_bare_none_declares_a_no_run_block_with_no_rationale() -> None:
    result = schema.parse_result_line("Result: none")

    assert isinstance(result, schema.NoRun)
    assert result.rationale == ""


def test_none_with_trailing_prose_carries_it_as_the_rationale() -> None:
    result = schema.parse_result_line("Result: none -- documentation-only step, no tests ran")

    assert isinstance(result, schema.NoRun)
    assert "documentation-only step" in result.rationale


def test_none_is_recognised_case_insensitively() -> None:
    result = schema.parse_result_line("Result: NONE")

    assert isinstance(result, schema.NoRun)


def test_a_line_that_is_not_a_result_line_returns_none() -> None:
    assert schema.parse_result_line("Command: `uv run pytest`") is None


def test_green_and_red_constants_match_the_derived_status_literals() -> None:
    assert schema.GREEN == "green"
    assert schema.RED == "red"


# ---------------------------------------------------------------------------
# split_step_blocks -- only a step heading opens a block
# ---------------------------------------------------------------------------


def test_a_sub_heading_inside_a_steps_body_does_not_open_its_own_block() -> None:
    """A ``### Failures`` sub-heading stays inside the enclosing step's block --
    this is the fixture behind the live shape-checker corpus dropping from 29
    findings to 6: sub-heading titles must never be misread as their own,
    unrelated sections."""
    text = (
        "## Step 1 -- a step\n"  # id-citation-discipline:ignore
        "\n"
        "Result: pass=1 fail=1 skip=0\n"
        "\n"
        "### Failures\n"
        "\n"
        "- some failing test\n"
    )

    blocks = schema.split_step_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].step == "Step 1"  # id-citation-discipline:ignore
    assert "### Failures" in blocks[0].text


def test_a_heading_only_anchor_produces_an_empty_block_with_no_results() -> None:
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "\n"
        "## Step 1: RED -- agreement test\n"  # id-citation-discipline:ignore
        "\n"
        "Result: pass=1 fail=0 skip=0\n"
    )

    blocks = schema.split_step_blocks(text)

    assert len(blocks) == 2
    assert blocks[0].step == "Step 1"  # id-citation-discipline:ignore
    assert blocks[0].results == ()
    assert blocks[0].text.strip() == "## Step 1"  # id-citation-discipline:ignore


def test_a_file_with_no_step_heading_is_checked_as_a_single_stepless_block() -> None:
    text = "Some preamble.\n\nResult: pass=3 fail=0 skip=0\n"

    blocks = schema.split_step_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].step is None


def test_a_heading_outside_the_two_to_four_hash_range_does_not_open_a_block() -> None:
    text = "# Step 1\n\nResult: pass=1 fail=0 skip=0\n"  # id-citation-discipline:ignore

    blocks = schema.split_step_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].step is None


def test_several_blocks_may_carry_the_same_step_id_for_addenda() -> None:
    text = (
        "## Step 6\n\nResult: pass=5 fail=0 skip=0\n\n"  # id-citation-discipline:ignore
        "## Step 6 (post-review addendum)\n\nResult: pass=6 fail=0 skip=0\n"  # id-citation-discipline:ignore
    )

    blocks = schema.split_step_blocks(text)

    assert len(blocks) == 2
    assert blocks[0].step == "Step 6"  # id-citation-discipline:ignore
    assert blocks[1].step == "Step 6"  # id-citation-discipline:ignore
    assert blocks[0].title != blocks[1].title


def test_every_result_line_in_a_block_is_collected_in_document_order() -> None:
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: x\n"
        "Result: pass=1 fail=0 skip=0\n"
        "more text\n"
        "Result: pass=2 fail=0 skip=0\n"
    )

    blocks = schema.split_step_blocks(text)

    assert len(blocks) == 1
    line_numbers = [line_no for line_no, _ in blocks[0].results]
    assert line_numbers == sorted(line_numbers)
    assert len(blocks[0].results) == 2


# ---------------------------------------------------------------------------
# parse_wip_claims -- one claim map from every declared WIP claim source
# (checklist, status table, heading marker), merged with the existing
# conflicting-claim rule.
# ---------------------------------------------------------------------------


def test_checklist_claim_binds_to_the_immediately_following_step_not_a_later_mention() -> None:
    text = "- [x] Step 11: finish after Step 10\n"  # id-citation-discipline:ignore

    claims = schema.parse_wip_claims(text)

    assert claims == {"Step 11": "COMPLETE"}  # id-citation-discipline:ignore


def test_checklist_line_mentioning_a_step_later_on_yields_no_claim_for_it() -> None:
    text = "- [x] Failure mode 1: … (Step 6)\n"  # id-citation-discipline:ignore

    assert schema.parse_wip_claims(text) == {}


# Verbatim excerpt: sidecar-placement/sidecar-placement's WIP status table.
_STATUS_TABLE_EXCERPT = (
    "| Step | Assignee | Status | Files |\n"
    "|---|---|---|---|\n"
    "| 1 | implementer | complete (GREEN -- 21 passed; self-review clean) "
    "| `scripts/_state_repo.py` |\n"
    "| 1b | test-engineer | complete (RED -- awaiting Step 1) "  # id-citation-discipline:ignore
    "| `scripts/test_state_repo.py` |\n"
)


def test_status_table_row_yields_a_claim_from_the_leading_status_word() -> None:
    claims = schema.parse_wip_claims(_STATUS_TABLE_EXCERPT)

    assert claims == {"Step 1": "COMPLETE", "Step 1b": "COMPLETE"}  # id-citation-discipline:ignore


def test_a_hash_headed_table_mints_no_claims() -> None:
    text = "| # | Finding | Status |\n|---|---|---|\n| 1 | some review row | pending |\n"

    assert schema.parse_wip_claims(text) == {}


# Verbatim excerpt: process-economy-p2-6/WIP.md's backticked heading marker.
_HEADING_CLAIM_EXCERPT = "## Step 1 — script + canaries  `[x]`\n"  # id-citation-discipline:ignore


def test_an_upper_case_step_suffix_in_a_table_cell_names_the_lower_case_plan_step() -> None:
    text = "| Step | Assignee | Status | Files |\n|---|---|---|---|\n| 1B | test-engineer | complete | t.py |\n"

    claims = schema.parse_wip_claims(text)

    assert claims == {"Step 1b": "COMPLETE"}  # id-citation-discipline:ignore


def test_heading_with_a_backticked_checkbox_marker_yields_a_claim() -> None:
    claims = schema.parse_wip_claims(_HEADING_CLAIM_EXCERPT)

    assert claims == {"Step 1": "COMPLETE"}  # id-citation-discipline:ignore


@pytest.mark.parametrize(
    ("status_word", "expected_claim"),
    [
        ("in-progress", "IN-PROGRESS"),
        ("not started", "PENDING"),
        ("—", "PENDING"),
        ("red", "AMBIGUOUS"),
        ("completed", "COMPLETE"),
        ("[COMPLETE]", "COMPLETE"),
        ("complete — merged", "COMPLETE"),
        ("[COMPLETE] — merged at the batch gate", "COMPLETE"),
        ("complete + follow-up filed", "COMPLETE"),
        ("**done**, verified", "COMPLETE"),
        ("completely rewritten", "AMBIGUOUS"),
    ],
)
def test_status_table_word_vocabulary_maps_to_the_documented_claim(
    status_word: str, expected_claim: str
) -> None:
    text = (
        "| Step | Assignee | Status | Files |\n"
        "|---|---|---|---|\n"
        f"| 1 | implementer | {status_word} | a.py |\n"
    )

    claims = schema.parse_wip_claims(text)

    assert claims == {"Step 1": expected_claim}  # id-citation-discipline:ignore


# Verbatim excerpt: process-economy-p2-10/WIP.md's "Batch 3" table -- every
# Step cell carries a parenthetical label alongside the bare id.
_STEP_CELL_WITH_LABEL_EXCERPT = (
    "| Step | Depends-on | Status |\n"
    "|---|---|---|\n"
    "| 12 (integration checkpoint) | 1,2,3,4,5,6,7,8,9,10,11 | complete (orchestrator) |\n"
    "| 14 (taxonomy refresh) | 12 | complete |\n"
    "| 16 (run_check_families --table) | 12 | complete (orchestrator: BC05 in digest, "
    "14 families / 56 checks) |\n"
    "| 15 (token budget + ratchet) | 12, 14 | complete (orchestrator: 16,639 in-worktree, "
    "16,569 projected post-merge; ratchet exit 0) |\n"
    "| 17 (full suite, detached) | 1-16 | complete (4781 passed, 5 skipped, exit 0) |\n"
    "| 18 (verifier) | 17 | pending |\n"
)


def test_status_table_step_cell_with_a_parenthetical_label_still_yields_a_claim() -> None:
    claims = schema.parse_wip_claims(_STEP_CELL_WITH_LABEL_EXCERPT)

    assert claims == {  # id-citation-discipline:ignore
        "Step 12": "COMPLETE",  # id-citation-discipline:ignore
        "Step 14": "COMPLETE",  # id-citation-discipline:ignore
        "Step 16": "COMPLETE",  # id-citation-discipline:ignore
        "Step 15": "COMPLETE",  # id-citation-discipline:ignore
        "Step 17": "COMPLETE",  # id-citation-discipline:ignore
        "Step 18": "PENDING",  # id-citation-discipline:ignore
    }


def test_conflicting_claims_from_different_sources_become_ambiguous() -> None:
    text = (
        "- [x] Step 1: build the thing\n"  # id-citation-discipline:ignore
        "| Step | Assignee | Status | Files |\n"
        "|---|---|---|---|\n"
        "| 1 | implementer | pending | a.py |\n"
    )

    claims = schema.parse_wip_claims(text)

    assert claims == {"Step 1": "AMBIGUOUS"}  # id-citation-discipline:ignore


# ---------------------------------------------------------------------------
# Module import on the oldest bare interpreter the readers are invoked with
# ---------------------------------------------------------------------------

_LEGACY_INTERPRETER = "/usr/bin/python3"


@pytest.mark.skipif(
    not Path(_LEGACY_INTERPRETER).exists(),
    reason=f"{_LEGACY_INTERPRETER} not present on this machine",
)
def test_the_three_step_document_readers_import_under_a_legacy_bare_interpreter() -> None:
    """All three step-document readers are invoked by a slash command or a
    git hook with a bare `python3` -- an interpreter this project does not
    control the version of. A module-level union-type alias evaluated at
    import time (rather than deferred as a string or annotation-only form)
    breaks that contract on any interpreter that predates runtime `|` union
    support, even though the project's own declared floor is newer."""
    result = subprocess.run(
        [
            _LEGACY_INTERPRETER,
            "-c",
            f"import sys; sys.path.insert(0, {str(SCRIPT_DIR)!r}); "
            "import _step_schema, reconcile_pipeline_state, check_test_results_shape",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
