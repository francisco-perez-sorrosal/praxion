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


STEP = "Step"  # step labels are built from this, never written out in test data


def test_a_result_line_under_a_non_step_level_two_heading_belongs_to_no_step() -> None:
    text = f"## {STEP} 1\nResult: pass=1 fail=1 skip=0\n\n## Notes\nResult: pass=9 fail=0 skip=0\n"

    blocks = schema.split_step_blocks(text)

    assert [(b.step, [r.failed for _, r in b.results], "Notes" in b.text) for b in blocks] == [
        (f"{STEP} 1", [1], False)
    ]


def test_a_mutation_line_under_a_non_step_level_two_heading_feeds_no_step() -> None:
    text = f"### {STEP} 4\nResult: pass=3 fail=0\n\n## Notes\n{GOLDEN_RAN_LINES[0]}\n"

    blocks = schema.split_step_blocks(text)

    assert schema.step_mutation_reading(f"{STEP} 4", blocks) is None


def test_a_step_heading_after_a_non_step_heading_opens_a_block_again() -> None:
    text = (
        f"## {STEP} 1\nResult: pass=1 fail=0 skip=0\n\n## Notes\nprose\n\n"
        f"## {STEP} 2\nResult: pass=2 fail=0 skip=0\n"
    )

    blocks = schema.split_step_blocks(text)

    assert [(b.step, b.first_line, "Notes" in b.text) for b in blocks] == [
        (f"{STEP} 1", 1, False),
        (f"{STEP} 2", 7, False),
    ]


@pytest.mark.parametrize("sub_heading", ["### Failures", "#### Detail"])
def test_a_deeper_non_step_heading_stays_inside_its_steps_block(sub_heading: str) -> None:
    text = f"## {STEP} 1\nResult: pass=1 fail=1 skip=0\n\n{sub_heading}\nResult: pass=2 fail=0\n"

    blocks = schema.split_step_blocks(text)

    assert [(b.step, len(b.results)) for b in blocks] == [(f"{STEP} 1", 2)]


def test_a_file_with_only_non_step_headings_is_one_stepless_block() -> None:
    text = "# Title\n\n## Notes\nResult: pass=3 fail=0 skip=0\n\n## More\nprose\n"

    blocks = schema.split_step_blocks(text)

    assert [(b.step, len(b.results), b.first_line) for b in blocks] == [(None, 1, 1)]


def test_a_level_two_heading_line_inside_a_code_fence_does_not_close_the_block() -> None:
    text = f"## {STEP} 1\n```\n## pasted\n```\nResult: pass=1 fail=0 skip=0\n"

    blocks = schema.split_step_blocks(text)

    assert [(b.step, len(b.results)) for b in blocks] == [(f"{STEP} 1", 1)]
    assert schema.non_step_headings(text) == ()


def test_non_step_headings_lists_level_two_headings_only_with_their_lines() -> None:
    text = f"# Top\n## Notes\n## {STEP} 1\n### Sub\n#### Deep\n## Appendix — check\n"

    assert schema.non_step_headings(text) == ((2, "Notes"), (6, "Appendix — check"))


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


# ---------------------------------------------------------------------------
# The `Mutation:` line grammar (Contract A) -- the one parser and the one
# renderer, plus the single policy deciding whether a reading blocks a step.
# ---------------------------------------------------------------------------

# Every line the sensor prints today, captured from its renderer before the
# render moved here: ran (plain, with `inconclusive`, clean, several targets,
# `+<j> more`) and a refusal per closed reason.
GOLDEN_RAN_LINES = (
    "Mutation: survivors=3 mutants=10 targets=[a.py] (f: 2, g: 1)",
    "Mutation: survivors=2 mutants=10 inconclusive=1 targets=[a.py] (f: 2)",
    "Mutation: survivors=0 mutants=5 targets=[a.py] ()",
    "Mutation: survivors=2 mutants=7 targets=[a.py, b.py] (f: 1, g: 1)",
    "Mutation: survivors=28 mutants=48 targets=[a.py] "
    "(fn0: 4, fn1: 4, fn2: 4, fn3: 4, fn4: 4, +2 more)",
)
GOLDEN_REFUSAL_REASONS = (
    "not-flat-layout",
    "path-missing",
    "pyproject-present",
    "mutants-dir-present",
    "toolchain-missing",
    "run-timeout",
    "run-failed",
)
GOLDEN_REFUSAL_LINES = tuple(
    f"Mutation: unavailable reason={reason} (line one line two (x))"
    for reason in GOLDEN_REFUSAL_REASONS
)


def test_every_golden_mutation_line_round_trips() -> None:
    for line in (*GOLDEN_RAN_LINES, *GOLDEN_REFUSAL_LINES):
        reading = schema.parse_mutation_line(line)
        assert reading is not None, line
        assert not isinstance(reading, schema.MutationMalformed), line
        assert schema.render_mutation_line(reading) == line


def test_a_parsed_ran_line_exposes_its_counts_targets_and_attribution() -> None:
    reading = schema.parse_mutation_line(GOLDEN_RAN_LINES[-1])
    assert reading == schema.MutationRan(
        survivors=28,
        mutants=48,
        inconclusive=0,
        targets=("a.py",),
        per_function=(("fn0", 4), ("fn1", 4), ("fn2", 4), ("fn3", 4), ("fn4", 4)),
        more=2,
    )


def test_a_line_that_is_not_a_mutation_line_parses_to_none() -> None:
    assert schema.parse_mutation_line("Result: pass=1 fail=0") is None
    assert schema.parse_mutation_line("  Mutation: survivors=0 mutants=5 targets=[a.py] ()") is None


def test_unseen_refusal_reason_parses_as_refused_and_blocks() -> None:
    reading = schema.parse_mutation_line("Mutation: unavailable reason=disk-on-fire (boom)")
    assert reading == schema.MutationRefused(reason="disk-on-fire", detail="boom")
    assert schema.mutation_block_reason(reading) == "refused, reason=disk-on-fire"


@pytest.mark.parametrize(
    "line",
    [
        "Mutation: survivors=x mutants=5 targets=[a.py] ()",
        "Mutation: survivors=1 targets=[a.py] ()",
        "Mutation: survivors=1 mutants=5 targets=[a.py]",
        "Mutation: survivors=1 mutants=5 targets=[a.py] (f: two)",
        "Mutation: survivors=1 mutants=5 targets=[a.py] (+1 more, f: 1)",
        "Mutation: unavailable reason=Bad_Code (x)",
        "Mutation: unavailable",
        "Mutation: survivors=0 mutants=0 targets=[a.py] ()",
        "Mutation: survivors=6 mutants=5 targets=[a.py] ()",
        "Mutation: survivors=3 mutants=5 inconclusive=3 targets=[a.py] ()",
        "Mutation:",
    ],
)
def test_garbled_mutation_line_parses_as_malformed_and_blocks(line: str) -> None:
    reading = schema.parse_mutation_line(line)
    assert reading == schema.MutationMalformed(line)
    assert schema.mutation_block_reason(reading) == "unreadable Mutation: line"


def test_absent_mutation_line_blocks_with_the_missing_line_reason() -> None:
    assert schema.mutation_block_reason(None) == "no Mutation: line"
    blocks = schema.split_step_blocks(
        "### Step 4\nResult: pass=3 fail=0\n"  # id-citation-discipline:ignore
    )
    assert schema.step_mutation_reading("Step 4", blocks) is None  # id-citation-discipline:ignore


def test_declared_layout_refusal_does_not_block() -> None:
    assert schema.DECLARED_LIMIT_REASONS == frozenset({"not-flat-layout"})
    layout = schema.parse_mutation_line(GOLDEN_REFUSAL_LINES[0])
    assert schema.mutation_block_reason(layout) is None
    ran = schema.parse_mutation_line(GOLDEN_RAN_LINES[0])
    assert schema.mutation_block_reason(ran) is None
    other = schema.parse_mutation_line(GOLDEN_REFUSAL_LINES[-1])
    assert schema.mutation_block_reason(other) == "refused, reason=run-failed"


def test_latest_block_reading_supersedes_an_earlier_one() -> None:
    text = (
        "### Step 4\nResult: pass=3 fail=0\n"  # id-citation-discipline:ignore
        f"{GOLDEN_REFUSAL_LINES[-1]}\n"
        "### Step 5\nResult: pass=1 fail=0\n"  # id-citation-discipline:ignore
        f"{GOLDEN_RAN_LINES[2]}\n"
        "### Step 4\nResult: pass=3 fail=0\n"  # id-citation-discipline:ignore
        f"{GOLDEN_RAN_LINES[0]}\n"
    )
    blocks = schema.split_step_blocks(text)
    latest = schema.step_mutation_reading("Step 4", blocks)  # id-citation-discipline:ignore
    assert isinstance(latest, schema.MutationRan)
    assert latest.survivors == 3
    assert schema.mutation_block_reason(latest) is None
    # the reverse order: a refusal recorded later clears nothing, it blocks
    reversed_blocks = schema.split_step_blocks(
        f"### Step 4\n{GOLDEN_RAN_LINES[0]}\n### Step 4\n{GOLDEN_REFUSAL_LINES[-1]}\n"  # id-citation-discipline:ignore
    )
    later = schema.step_mutation_reading("4", reversed_blocks)
    assert schema.mutation_block_reason(later) == "refused, reason=run-failed"
    assert schema.step_mutation_reading("Step 9", blocks) is None  # id-citation-discipline:ignore


# ---------------------------------------------------------------------------
# The `mutation: on|off` plan tag -- fails closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "mutation: on",
        "Mutation: On",
        "MUTATION: ON",
        "**mutation: on**",
        "**mutation:** on",
        "**mutation**: on",
        "`mutation: on`",
        "- mutation: on",
        "* mutation: on",
        "+ mutation: on",
        "1. mutation: on",
        "> mutation: on",
        "   mutation: on   ",
        "mutation: on # risky world-read step",
        "mutation: yes",
        "mutation: onn",
        "mutation: on please",
        "mutation:",
    ],
)
def test_parse_mutation_tag_reads_every_spelling_that_is_not_an_explicit_off_as_tagged(
    line: str,
) -> None:
    assert schema.parse_mutation_tag(line) is True


@pytest.mark.parametrize(
    "line",
    ["mutation: off", "Mutation: OFF", "**mutation: off**", "- mutation: off # no sensor here"],
)
def test_parse_mutation_tag_reads_an_explicit_off_as_untagged(line: str) -> None:
    assert schema.parse_mutation_tag(line) is False


@pytest.mark.parametrize(
    "line",
    [
        "",
        "**Implementation**: set mutation: on for the risky steps later",
        "The mutation: on tag is the planner's",
        "mutation testing is optional",
        "Mutation: survivors=1 mutants=14 targets=[a.py] (f: 1)",
        "Mutation: unavailable reason=run-failed (boom)",
    ],
)
def test_parse_mutation_tag_ignores_prose_and_a_mutation_reading(line: str) -> None:
    assert schema.parse_mutation_tag(line) is None


def test_mutation_tagged_steps_binds_a_tag_to_the_step_it_sits_under() -> None:
    plan = (
        "### Step 1: a\n**Files**: a.py\n"  # id-citation-discipline:ignore
        "### Step 2: b\n**Files**: b.py\n**mutation: on**\n"  # id-citation-discipline:ignore
        "### Step 3: c\nmutation: off\n"  # id-citation-discipline:ignore
    )
    assert schema.mutation_tagged_steps(plan) == frozenset(
        {"Step 2"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_the_last_tag_under_a_step_wins() -> None:
    assert (
        schema.mutation_tagged_steps(
            "### Step 1: a\nmutation: on\nmutation: off\n"  # id-citation-discipline:ignore
        )
        == frozenset()
    )
    assert schema.mutation_tagged_steps(
        "### Step 1: a\nmutation: off\nmutation: on\n"  # id-citation-discipline:ignore
    ) == frozenset({"Step 1"})  # id-citation-discipline:ignore


def test_mutation_tagged_steps_reads_a_wip_checklist() -> None:
    wip = "- [ ] Step 7: x\nmutation: on\n- [x] Step 8: y\n"  # id-citation-discipline:ignore
    assert schema.mutation_tagged_steps(wip) == frozenset(
        {"Step 7"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_a_later_section_cannot_disarm_the_last_step() -> None:
    """A tag-shaped bullet under a closing section belongs to no step: read as the last
    step's, it would silently untag it and let it complete without a reading."""
    plan = (
        "### Step 3: c\nmutation: on\n"  # id-citation-discipline:ignore
        "## Notes\n- `mutation: off` (or omitting the field) means no sensor run.\n"
    )
    assert schema.mutation_tagged_steps(plan) == frozenset(
        {"Step 3"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_a_same_level_heading_ends_the_step_block() -> None:
    plan = "### Step 1: a\n### Risks\nmutation: on\n"  # id-citation-discipline:ignore
    assert schema.mutation_tagged_steps(plan) == frozenset()


def test_mutation_tagged_steps_a_subsection_inside_a_step_keeps_its_tag() -> None:
    plan = "### Step 1: a\n#### Detail\nmutation: on\n"  # id-citation-discipline:ignore
    assert schema.mutation_tagged_steps(plan) == frozenset(
        {"Step 1"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_a_comment_inside_a_code_fence_is_not_a_heading() -> None:
    plan = (
        "### Step 3: c\n```bash\n# run the sensor\n```\nmutation: on\n"  # id-citation-discipline:ignore
        "### Step 4: d\n~~~\n## not a section\n~~~\nmutation: on\n"  # id-citation-discipline:ignore
    )
    assert schema.mutation_tagged_steps(plan) == frozenset(
        {"Step 3", "Step 4"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_a_spaceless_step_heading_keeps_its_subsection() -> None:
    plan = "###Step 3: c\n#### Detail\nmutation: on\n"  # id-citation-discipline:ignore
    assert schema.mutation_tagged_steps(plan) == frozenset(
        {"Step 3"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_a_heading_ends_a_checklist_step() -> None:
    wip = (
        "- [ ] Step 7: x\nmutation: on\n## Notes\nmutation: off\n"  # id-citation-discipline:ignore
    )
    assert schema.mutation_tagged_steps(wip) == frozenset(
        {"Step 7"}  # id-citation-discipline:ignore
    )


def test_mutation_tagged_steps_ignores_a_tag_before_any_step() -> None:
    assert (
        schema.mutation_tagged_steps(
            "mutation: on\n### Step 1: a\n"  # id-citation-discipline:ignore
        )
        == frozenset()
    )


def test_mutation_block_reasons_names_only_tagged_steps_without_a_usable_reading() -> None:
    plan = "### Step 1: a\nmutation: on\n### Step 2: b\nmutation: on\n### Step 3: c\n"  # id-citation-discipline:ignore
    results = "## Step 1\nMutation: survivors=0 mutants=3 targets=[a.py] ()\n## Step 2\nResult: none\n"  # id-citation-discipline:ignore
    reasons = schema.mutation_block_reasons(plan, results)
    assert set(reasons) == {"Step 2"}  # id-citation-discipline:ignore
    assert reasons["Step 2"] == "no Mutation: line"  # id-citation-discipline:ignore


def test_off_followed_by_a_reason_disarms_the_tag() -> None:
    assert schema.parse_mutation_tag("mutation: off (no world reads)") is False
    assert schema.parse_mutation_tag("mutation: offline") is True


def test_canary_a_line_of_repeated_list_markers_parses_in_linear_time() -> None:
    # A nested quantifier around the list-marker prefix once backtracked exponentially
    # (about 3x per added marker); run it in a child so a regression fails on the timeout
    # instead of hanging the suite.
    probe = (
        "import sys; sys.path.insert(0, sys.argv[1]); import _step_schema as s; "
        "s.parse_mutation_tag('-   ' * 60 + 'x'); s.parse_mutation_tag('*   ' * 60 + 'x')"
    )
    scripts_dir = str(Path(__file__).resolve().parent)
    subprocess.run([sys.executable, "-c", probe, scripts_dir], check=True, timeout=10)
