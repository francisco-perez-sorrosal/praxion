"""The systems-architect's own process in the check catalog, by the task's kit mode."""

from __future__ import annotations

import pytest

from praxion_evals.adherence.catalog import (
    ARCHITECT_FEATURE_SECTIONS,
    ARCHITECT_PARTIAL,
    ARCHITECT_SPEC_SECTIONS,
)
from praxion_evals.adherence.checks_adr import FILE_NAME, ID_FROM_NAME
from praxion_evals.adherence.model import Failed, NotApplicable, Passed
from praxion_evals.live.session import ToolUse
from tests.adherence_grading_support import TASK_DIR, graded_outcome, read_of

ARCHITECT = "systems-architect"
PLAN = f"{TASK_DIR}/SYSTEMS_PLAN.md"
ARCHITECT_MODES = ("spec", "feature")
FIRST_READS = [read_of(p) for p in ("TASK_BRIEF.md", "README.md", "pyproject.toml", "DESIGN.md")]
SPEC_HABIT = (
    "# Plan for the change\n\n## Overview\nWhat the change does.\n\n"
    "## Requirements\n- the behaviour asked for.\n\n## Approach\nA new module.\n"
)
FEATURE_HABIT = (
    "# Design for the change\n\n## Overview\nWhat the change does.\n\n"
    "## Design\nA new module beside the existing ones.\n\n## Risks\nFew.\n"
)
SPEC_PLAN = (
    "# Plan: tag filter\n\n## Goal\n\nList notes by tag.\n\n"
    "## Acceptance Criteria\n\n- listing by an unknown tag lists nothing\n\n"
    "## Behavioral Specification\n\n### Observable Surface\n\n- `notes list --tag`\n\n"
    "### Requirements\n\n- listing by a tag shows only the notes that carry it\n\n"
    "## Architecture\n\n[pending: design phase]\n"
)
FEATURE_PLAN = (
    "# Plan: audit trail\n\n## Goal\n\nKeep a history of changes.\n\n"
    "## Tech Stack\n\nPython 3.13\n\n## Acceptance Criteria\n\n- every change is listed\n\n"
    "## Architecture\n\n### Components\n\n- a history store\n\n"
    "## Codebase Readiness\n\n### Structural Issues\n\n- none\n\n"
    "## Risk Assessment\n\n- the history grows without bound\n"
)
RESCOPE_PLAN = (
    "# Plan: audit trail\n\n## Goal\n\nKeep a history of changes.\n\n"
    "## Codebase Readiness\n\n### Pre-Refactor Assessment\n\n"
    "Outcome: `rescope-and-restart`. The notes store has no notion of a change to record.\n"
)
RESCOPE_SIBLING_PLAN = RESCOPE_PLAN.replace(
    "### Pre-Refactor Assessment", "## Pre-Refactor Assessment"
)
RESCOPE_SUFFIXED_PLAN = RESCOPE_PLAN.replace(
    "### Pre-Refactor Assessment", "#### Pre-Refactor Assessment (Phase 2.5)"
)
RESCOPE_HEADED_PLAN = RESCOPE_PLAN.replace(
    "### Pre-Refactor Assessment\n\nOutcome: `rescope-and-restart`. The",
    "### Pre-Refactor Assessment: `rescope-and-restart`\n\nThe",
)
RESCOPE_DASHED_PLAN = RESCOPE_HEADED_PLAN.replace(
    ": `rescope-and-restart`", " — rescope-and-restart"
)
RESCOPE_PHASE_TITLED_PLAN = RESCOPE_PLAN.replace(
    "### Pre-Refactor Assessment", "### Phase 2.5 — Pre-Refactor Assessment"
)
RESCOPE_SENTENCE_CASE_PLAN = RESCOPE_PLAN.replace(
    "### Pre-Refactor Assessment", "### Pre-refactor assessment"
)
RESCOPE_SKELETON_PLAN = (
    RESCOPE_PLAN + "\n## Architecture\n\n[pending]\n\n## Risk Assessment\n\n[pending]\n"
)
FEATURE_RISKS = "## Risk Assessment\n\n- the history grows without bound\n"
MENTIONED_RESCOPE = (
    "### Pre-Refactor Assessment\n\n`rescope-and-restart` was weighed and set aside.\n"
)
HAND_NAMED_DRAFT = {
    ".ai-state/decisions/drafts/new-module.md": (
        "---\nid: dec-draft-newmodul\nstatus: proposed\n---\n\nUse a new module.\n"
    )
}


def _plan_written(opening: str, final: str, *, reads_before: int) -> dict:
    """A record whose plan is first written after ``reads_before`` reads and left as ``final``."""
    write = ToolUse("toolu_write_plan", "Write", {"file_path": PLAN, "content": opening}, None)
    return {"tool_uses": [*FIRST_READS[:reads_before], write], "files": {PLAN: final}}


@pytest.mark.parametrize("mode", ARCHITECT_MODES)
@pytest.mark.parametrize(
    ("record", "expected"),
    [
        pytest.param(
            _plan_written("# Plan: x [PARTIAL]\n", "# Plan: x\n", reads_before=0),
            Passed,
            id="written first with the marker and finished unmarked",
        ),
        pytest.param(
            _plan_written(SPEC_HABIT, SPEC_HABIT, reads_before=4),
            Failed,
            id="habit: written at call 5 and never marked",
        ),
        pytest.param(
            _plan_written("# Plan: x [PARTIAL]\n", "# Plan: x\n", reads_before=4),
            Failed,
            id="marked but written at call 5",
        ),
        pytest.param(
            _plan_written("# Plan: x [PARTIAL]\n", "# Plan: x [PARTIAL]\n", reads_before=0),
            Failed,
            id="marked first and never finished",
        ),
    ],
)
def test_the_architects_plan_is_scored_on_being_written_early_and_finished_last(
    mode, record, expected
):
    outcome = graded_outcome(ARCHITECT, ARCHITECT_PARTIAL, mode, **record)

    assert isinstance(outcome, expected), outcome


@pytest.mark.parametrize(
    ("name", "mode", "plan"),
    [
        pytest.param(ARCHITECT_SPEC_SECTIONS, "spec", SPEC_HABIT, id="spec habit"),
        pytest.param(
            ARCHITECT_SPEC_SECTIONS,
            "spec",
            SPEC_PLAN.replace("### Observable Surface", "### Interfaces"),
            id="spec without an observable surface",
        ),
        pytest.param(ARCHITECT_FEATURE_SECTIONS, "feature", FEATURE_HABIT, id="feature habit"),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            FEATURE_PLAN.replace("## Codebase Readiness", "## Readiness"),
            id="feature without codebase readiness",
        ),
        pytest.param(ARCHITECT_FEATURE_SECTIONS, "feature", "", id="feature writes no plan"),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_PLAN.replace("`rescope-and-restart`", "a rescope"),
            id="feature rescope without the outcome token",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_PLAN.replace("### Pre-Refactor Assessment", "### Assessment"),
            id="feature rescope token without the pre-refactor assessment",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_PLAN.replace("Keep a history of changes.", "[pending]"),
            id="feature rescope with an empty goal",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            FEATURE_PLAN.replace(FEATURE_RISKS, MENTIONED_RESCOPE),
            id="feature five sections short of the risks, its assessment mentioning the outcome",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_PLAN + "\n## Architecture\n\n### Components\n\n- a history store\n",
            id="feature rescope that also writes the architecture",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_PLAN + "\n## Risk Assessment\n\n- the history grows without bound\n",
            id="feature rescope that also writes the risks",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_PLAN.replace(
                "Outcome: `rescope-and-restart`.",
                "Outcome: `proceed`.\n\n### Alternatives\n\n`rescope-and-restart` was weighed.",
            ),
            id="feature rescope whose token sits after the assessment's own body",
        ),
        pytest.param(
            ARCHITECT_FEATURE_SECTIONS,
            "feature",
            RESCOPE_HEADED_PLAN.replace("`rescope-and-restart`", "`proceed`"),
            id="feature rescope whose heading line names another outcome",
        ),
    ],
)
def test_a_plan_of_its_own_shape_fails_the_architects_check_for_that_mode(name, mode, plan):
    files = {PLAN: plan} if plan else {}

    assert isinstance(graded_outcome(ARCHITECT, name, mode, files=files), Failed)


@pytest.mark.parametrize(
    ("name", "mode", "plan"),
    [
        (ARCHITECT_SPEC_SECTIONS, "spec", SPEC_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", FEATURE_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SIBLING_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SUFFIXED_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SKELETON_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_HEADED_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_DASHED_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_PHASE_TITLED_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SENTENCE_CASE_PLAN),
    ],
    ids=[
        "spec",
        "feature",
        "feature rescope-and-restart",
        "feature rescope with the assessment as a sibling section",
        "feature rescope with a level-four suffixed assessment",
        "feature rescope keeping the skeleton's pending design sections",
        "feature rescope naming the outcome on the assessment's heading line",
        "feature rescope naming the outcome after a dash on the heading line",
        "feature rescope under the definition's phase title",
        "feature rescope with a sentence-case assessment heading",
    ],
)
def test_a_plan_with_the_sections_its_mode_requires_passes(name, mode, plan):
    assert graded_outcome(ARCHITECT, name, mode, files={PLAN: plan}) == Passed()


@pytest.mark.parametrize(
    ("name", "other", "plan"),
    [
        (ARCHITECT_SPEC_SECTIONS, "feature", SPEC_HABIT),
        (ARCHITECT_FEATURE_SECTIONS, "spec", FEATURE_HABIT),
        (ARCHITECT_FEATURE_SECTIONS, "spec", RESCOPE_PLAN),
    ],
    ids=[
        "spec check on a feature task",
        "feature check on a spec task",
        "feature check on a spec task's rescope plan",
    ],
)
def test_an_architect_section_check_is_not_applicable_to_a_task_of_its_other_mode(
    name, other, plan
):
    # The prompt names spec mode on every task: the task's mode alone gates the check.
    outcome = graded_outcome(ARCHITECT, name, other, spawn_prompt="Mode: spec", files={PLAN: plan})

    assert isinstance(outcome, NotApplicable)


@pytest.mark.parametrize(
    ("name", "mode"), [(ARCHITECT_SPEC_SECTIONS, "spec"), (ARCHITECT_FEATURE_SECTIONS, "feature")]
)
def test_an_architect_section_check_is_not_applicable_when_the_task_stopped_it_early(name, mode):
    assert isinstance(graded_outcome(ARCHITECT, name, mode, forced_stop=True), NotApplicable)


@pytest.mark.parametrize("mode", ARCHITECT_MODES)
@pytest.mark.parametrize("clause", [FILE_NAME, ID_FROM_NAME], ids=["file name", "derived id"])
def test_a_hand_named_draft_with_a_made_up_id_still_fails_the_shared_adr_clauses(mode, clause):
    name = clause.format(role=ARCHITECT)

    assert isinstance(graded_outcome(ARCHITECT, name, mode, files=HAND_NAMED_DRAFT), Failed)
