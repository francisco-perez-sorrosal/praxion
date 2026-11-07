"""The check catalog: every role's checks, the rule each names, and the canary each carries."""

from __future__ import annotations

import ast
from dataclasses import replace

import pytest

from praxion_evals.adherence import grade
from praxion_evals.adherence.catalog import (
    ARCHITECT_FEATURE_SECTIONS,
    ARCHITECT_PARTIAL,
    ARCHITECT_SPEC_SECTIONS,
    RESEARCHER_DOCS_FIRST,
    RESEARCHER_SECTIONS,
    RESEARCHER_SOURCES,
    ROLE_ROWS,
    TEST_ENGINEER_INPUTS,
    TEST_ENGINEER_RESULTS,
    TEST_ENGINEER_SECTIONS,
    VERIFIER_LEDGER,
    VERIFIER_PARTIAL,
    VERIFIER_TAGS,
    check_catalog,
    role_check,
)
from praxion_evals.adherence.catalog_rows import (
    CARTOGRAPHER_DECISION_LOG,
    CARTOGRAPHER_ISOLATION,
    CONSULT_BLOCKED,
    CONTEXT_STAGES,
    DESIGN_SELF_TEST,
    VALIDATOR_PRE_MERGE,
    VALIDATOR_SECTIONS,
)
from praxion_evals.adherence.checks_adr import FILE_NAME, ID_FROM_NAME, adr_row
from praxion_evals.adherence.checks_common import COMMON_CHECKS, synthetic_evidence
from praxion_evals.adherence.checks_roles import CHECKOUT_ROOT, section_body
from praxion_evals.adherence.model import (
    CONVENTION_MARKER,
    PILOT_ROLES,
    ROLES,
    Binds,
    CheckErrored,
    DoesNotBind,
    Failed,
    Measured,
    NotApplicable,
    Passed,
    TaskFacts,
    convention_check_name,
)
from praxion_evals.live.session import InitInfo, ResultInfo, ToolUse

ALL_CHECKS = [(role, check) for role in ROLES for check in check_catalog(role)]


def _ids(pairs):
    return [f"{role}:{check.name[:48]}" for role, check in pairs]


def _gradable(role: str, **kwargs):
    """Synthetic evidence whose stream reads as a finished session, so the grader scores it."""
    evidence = synthetic_evidence(role, **kwargs)
    plugin = {"name": "praxion", "path": str(evidence.plugin_copy), "source": "praxion@inline"}
    init = InitInfo(None, (plugin,), (), None, None, None)
    result = ResultInfo("done", None, False, "success", None, None)
    envelope = replace(evidence.envelope, init=init, final_result=result, result_count=1)
    return replace(evidence, envelope=envelope)


# ---------------------------------------------------------------------------
# What the catalog holds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_every_role_opens_with_the_common_checks_and_names_each_check_once(role):
    names = [check.name for check in check_catalog(role)]

    assert names[: len(COMMON_CHECKS)] == list(COMMON_CHECKS)
    assert len(set(names)) == len(names)


@pytest.mark.parametrize("role", ROLES)
def test_only_the_common_checks_are_marked_common(role):
    common = [check.name for check in check_catalog(role) if check.common]

    assert common == list(COMMON_CHECKS)


@pytest.mark.parametrize(("role", "clauses"), [("researcher", 4), ("verifier", 4)])
def test_the_researcher_and_the_verifier_each_carry_their_four_clauses(role, clauses):
    row = ROLE_ROWS[role]

    assert len(row) == clauses
    assert all(check.name.startswith(f"{role}: ") for check in row)


def test_every_role_carries_a_row_of_its_own():
    assert set(ROLE_ROWS) == set(ROLES)


def test_the_only_judged_role_checks_are_the_adr_categories():
    judged = {role for role, row in ROLE_ROWS.items() for c in row if c.kind == "judged"}

    assert judged == {
        "systems-architect",
        "implementation-planner",
        "interface-designer",
        "agentic-transactions-architect",
    }


@pytest.mark.parametrize(
    ("role", "clauses"),
    [("implementer", 8), ("test-engineer", 6), ("doc-engineer", 3), ("systems-architect", 10)],
)
def test_each_role_carries_one_check_per_clause_of_its_row(role, clauses):
    assert len(ROLE_ROWS[role]) == clauses
    assert all(check.name.startswith(f"{role}: ") for check in ROLE_ROWS[role])


@pytest.mark.parametrize(
    ("role", "clauses"),
    [
        ("sentinel", 4),
        ("architect-validator", 3),
        ("context-engineer", 3),
        ("cicd-engineer", 1),
        ("discipline-consultant", 4),
        ("promethean", 3),
        ("roadmap-cartographer", 4),
        ("skill-genesis", 4),
    ],
)
def test_each_remaining_role_carries_one_check_per_clause_of_its_row(role, clauses):
    assert len(ROLE_ROWS[role]) == clauses
    assert all(check.name.startswith(f"{role}: ") for check in ROLE_ROWS[role])


def _architect_adr_clauses() -> list[str]:
    """The ADR clauses the architect's row shares with the design roles and the planner."""
    return [c.name.removeprefix("systems-architect: ") for c in adr_row("systems-architect")]


@pytest.mark.parametrize("role", ["interface-designer", "agentic-transactions-architect"])
def test_the_design_roles_share_the_adr_clauses_and_add_their_challenges_and_self_test(role):
    names = [c.name.removeprefix(f"{role}: ") for c in ROLE_ROWS[role]]
    architect = _architect_adr_clauses()

    assert names[: len(architect)] == architect
    assert len(names) == len(architect) + 2


def test_the_planner_shares_the_architects_adr_clauses_and_adds_its_own():
    names = [
        c.name.removeprefix("implementation-planner: ") for c in ROLE_ROWS["implementation-planner"]
    ]
    architect = _architect_adr_clauses()

    assert names[: len(architect)] == architect
    assert len(names) == len(architect) + 3


def test_an_unknown_role_is_refused():
    with pytest.raises(ValueError, match="unknown role"):
        check_catalog("janitor")


# ---------------------------------------------------------------------------
# Every check names a rule that exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("role", "check"), ALL_CHECKS, ids=_ids(ALL_CHECKS))
def test_a_check_cites_a_heading_that_is_in_the_file(role, check):
    source = CHECKOUT_ROOT / check.rule.file

    assert source.is_file(), f"{role}/{check.name}: no file {check.rule.file}"
    text = source.read_text(encoding="utf-8")
    assert section_body(text, check.rule.section) is not None, (
        f"{role}/{check.name}: no heading {check.rule.section!r} in {check.rule.file}"
    )


# ---------------------------------------------------------------------------
# Every check proves itself
# ---------------------------------------------------------------------------


MECHANICAL = [(role, c) for role, c in ALL_CHECKS if c.kind == "mechanical"]
JUDGED = [(role, c) for role, c in ALL_CHECKS if c.kind == "judged"]


@pytest.mark.parametrize(("role", "check"), MECHANICAL, ids=_ids(MECHANICAL))
def test_a_mechanical_checks_planted_violation_is_flagged_failed(role, check):
    for index, build in enumerate(check.violations):
        outcome = check.evaluate(build())

        assert isinstance(outcome, Failed), f"{role}/{check.name}: canary {index} read as {outcome}"


@pytest.mark.parametrize(("role", "check"), JUDGED, ids=_ids(JUDGED))
def test_a_judged_check_documents_a_bad_and_a_good_case_that_differ(role, check):
    assert check.golden_bad_case.strip()
    assert check.golden_good_case.strip()
    assert check.golden_bad_case != check.golden_good_case


def test_the_verifiers_ledger_canary_reads_the_real_script_output():
    check = role_check("verifier", VERIFIER_LEDGER)

    outcome = check.evaluate(check.violation())

    assert isinstance(outcome, Failed)
    assert "field-count" in outcome.detail  # a finding of the script, not an exception fallback


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------


def _facts(api_docs: str | None) -> TaskFacts:
    return TaskFacts(False, False, False, None, None, api_docs)


def test_the_docs_first_clause_binds_only_on_a_question_about_an_external_api():
    check = role_check("researcher", RESEARCHER_DOCS_FIRST)

    assert isinstance(check.binds("researcher", _facts("docs.example.com")), Binds)
    assert isinstance(check.binds("researcher", _facts(None)), DoesNotBind)


@pytest.mark.parametrize(
    ("fetched", "expected"),
    [
        ("https://docs.example.com/llms.txt", Passed),
        ("https://platform.docs.example.com/page.md", Passed),
        ("https://docs.example.com.evil.test/llms.txt", Failed),
        ("https://other.test/llms.txt", Failed),
    ],
)
def test_only_a_fetch_on_the_vendors_docs_host_counts_as_fetching_its_docs(fetched, expected):
    fetch = ToolUse("f", "WebFetch", {"url": fetched}, None)
    evidence = synthetic_evidence("researcher", tool_uses=[fetch], facts=_facts("docs.example.com"))

    assert isinstance(role_check("researcher", RESEARCHER_DOCS_FIRST).evaluate(evidence), expected)


# ---------------------------------------------------------------------------
# Resolving a name
# ---------------------------------------------------------------------------


def test_a_common_check_and_a_clause_resolve_by_name():
    assert role_check("researcher", "C1") is COMMON_CHECKS["C1"]
    assert role_check("verifier", VERIFIER_TAGS).name == VERIFIER_TAGS


def test_a_name_from_another_role_is_refused_and_the_known_names_are_listed():
    with pytest.raises(ValueError, match="no check named") as refused:
        role_check("researcher", VERIFIER_PARTIAL)

    assert RESEARCHER_SECTIONS in str(refused.value)


def test_the_grader_resolves_a_role_clause_through_the_catalog():
    evidence = _gradable("researcher", slug="grade-task")

    status = grade.grade(evidence, [RESEARCHER_SOURCES, "C2"], judge=None, setup=None)

    assert isinstance(status, Measured)
    assert isinstance(status.outcomes[RESEARCHER_SOURCES], Failed)  # no document was written
    assert set(status.outcomes) == {RESEARCHER_SOURCES, "C2"}


def test_a_measured_session_records_the_roles_return_as_it_was_graded():
    returned = "Findings: .ai-work/grade-task/RESEARCH_FINDINGS.md\n[COMPLETE]"
    evidence = _gradable("researcher", slug="grade-task", role_return=returned)

    status = grade.grade(evidence, ["C2"], judge=None, setup=None)

    assert isinstance(status, Measured)
    assert status.role_return == returned


def test_a_runaway_return_is_recorded_clipped_and_says_so():
    runaway = "x" * (grade.RECORDED_RETURN_CHARS + 50) + "\n[COMPLETE]"
    evidence = _gradable("researcher", slug="grade-task", role_return=runaway)

    status = grade.grade(evidence, ["C2"], judge=None, setup=None)

    assert isinstance(status, Measured)
    assert status.role_return is not None
    assert status.role_return.endswith(grade.CLIPPED_NOTE)
    assert len(status.role_return) == grade.RECORDED_RETURN_CHARS + len(grade.CLIPPED_NOTE)


def test_the_grader_refuses_a_clause_that_is_not_the_roles():
    evidence = _gradable("researcher")

    with pytest.raises(ValueError, match="no check named"):
        grade.grade(evidence, [VERIFIER_PARTIAL], judge=None, setup=None)


def test_a_clause_that_cannot_run_is_an_errored_outcome_never_a_failed_one():
    evidence = _gradable(
        "verifier", slug="grade-task", files={".ai-state/TECH_DEBT_LEDGER.md": "x"}
    )

    status = grade.grade(evidence, [VERIFIER_LEDGER], judge=None, setup=None)

    assert isinstance(status, Measured)
    assert isinstance(status.outcomes[VERIFIER_LEDGER], CheckErrored)  # no session directory


def test_a_clause_that_does_not_bind_is_not_applicable():
    evidence = _gradable("researcher")

    status = grade.grade(evidence, [RESEARCHER_DOCS_FIRST], judge=None, setup=None)

    assert isinstance(status, Measured)
    assert isinstance(status.outcomes[RESEARCHER_DOCS_FIRST], NotApplicable)


# ---------------------------------------------------------------------------
# The rows of the roles that advise, audit and report
# ---------------------------------------------------------------------------


def test_the_cartographers_lens_canary_reads_the_real_script_output():
    check = role_check("roadmap-cartographer", CARTOGRAPHER_ISOLATION)

    outcome = check.evaluate(check.violation())

    assert isinstance(outcome, Failed)
    assert "exited 1" in outcome.detail  # the script found the quoted sibling fragment


def test_the_lens_canary_lays_out_the_session_home_under_the_directory_the_harness_names(tmp_path):
    from praxion_evals.adherence import catalog_rows
    from praxion_evals.adherence.transcript import transcript_dir_name

    repo = tmp_path / "my_repo+1"
    repo.mkdir()

    homes = {path.split("/")[2] for path in catalog_rows._lens_run_files(repo)}

    assert homes == {transcript_dir_name(str(repo.resolve()))}


@pytest.mark.parametrize("role", ["interface-designer", "agentic-transactions-architect"])
def test_the_self_test_clause_is_reported_not_applicable_with_its_reason(role):
    evidence = _gradable(role, slug="grade-task")
    name = DESIGN_SELF_TEST.format(role=role)

    status = grade.grade(evidence, [name], judge=None, setup=None)

    assert isinstance(status, Measured)
    outcome = status.outcomes[name]
    assert isinstance(outcome, NotApplicable)
    assert f"no rule requires the self-test in the {role}'s output" in outcome.reason


@pytest.mark.parametrize(
    ("role", "name", "prompt"),
    [
        ("architect-validator", VALIDATOR_PRE_MERGE, "Run the validator with --mode=on-demand."),
        ("architect-validator", VALIDATOR_SECTIONS, "Run the validator with --mode=pre-merge."),
        ("discipline-consultant", CONSULT_BLOCKED, "Discipline: statistics"),
        ("context-engineer", CONTEXT_STAGES, "Audit the artifacts."),
        ("roadmap-cartographer", CARTOGRAPHER_DECISION_LOG, "Mode: fresh"),
    ],
)
def test_a_clause_stated_for_one_mode_does_not_apply_to_a_task_in_another(role, name, prompt):
    evidence = _gradable(role, slug="grade-task", spawn_prompt=prompt)

    status = grade.grade(evidence, [name], judge=None, setup=None)

    assert isinstance(status, Measured)
    assert isinstance(status.outcomes[name], NotApplicable)


# ---------------------------------------------------------------------------
# The test-engineer's own process, gated by the task's kit mode
# ---------------------------------------------------------------------------

TASK_DIR = ".ai-work/grade-task"
FIVE_SECTIONS = (
    "## Sources Read\n\n- the spec delta\n\n## Scenarios\n\n- a limit over the cap is refused\n\n"
    "## Boundary Assumptions\n\n- the CLI is the boundary\n\n## Spec Questions\n\n- none\n\n"
    "## Not Black-Box Testable\n\n- none\n"
)
RESULTS_SECTION = (
    "## Step 1 — the limit tests\n"  # id-citation-discipline:ignore (the shape's own heading)
    "Command: `uv run pytest tests -q`\nResult: pass=0 fail=3 skip=0\n"
)


def _read_of(path: str) -> ToolUse:
    return ToolUse(f"toolu_read_{path}", "Read", {"file_path": path}, "canary-spawn")


def _graded_outcome(role: str, name: str, mode: str | None, *, forced_stop: bool = False, **kwargs):
    facts = TaskFacts(forced_stop, False, False, None, None, None, mode=mode)
    evidence = _gradable(role, slug="grade-task", facts=facts, **kwargs)

    status = grade.grade(evidence, [name], judge=None, setup=None)

    assert isinstance(status, Measured)
    return status.outcomes[name]


HABIT_RECORDS = [
    pytest.param(
        TEST_ENGINEER_INPUTS,
        "acceptance-design",
        {
            "tool_uses": [
                _read_of(f"{TASK_DIR}/SYSTEMS_PLAN.md"),
                _read_of(f"{TASK_DIR}/TASK_BRIEF.md"),
            ]
        },
        id="acceptance-design reads the design",
    ),
    pytest.param(
        TEST_ENGINEER_SECTIONS,
        "acceptance-design",
        {
            "files": {
                f"{TASK_DIR}/ACCEPTANCE_TESTS.md": "# Acceptance tests\n\n- tests/test_limit.py\n"
            }
        },
        id="acceptance-design writes a plain list",
    ),
    pytest.param(
        TEST_ENGINEER_RESULTS,
        "paired",
        {"files": {f"{TASK_DIR}/TEST_RESULTS.md": "All tests pass.\n"}},
        id="paired writes a free-form note",
    ),
    pytest.param(TEST_ENGINEER_RESULTS, "paired", {"files": {}}, id="paired writes no results"),
]

GOOD_RECORDS = [
    pytest.param(
        TEST_ENGINEER_INPUTS,
        "acceptance-design",
        {"tool_uses": [_read_of("README.md"), _read_of("tests/acceptance/conftest.py")]},
        id="acceptance-design reads only the allowed",
    ),
    pytest.param(
        TEST_ENGINEER_SECTIONS,
        "acceptance-design",
        {"files": {f"{TASK_DIR}/ACCEPTANCE_TESTS.md": FIVE_SECTIONS}},
        id="acceptance-design writes the five sections",
    ),
    pytest.param(
        TEST_ENGINEER_RESULTS,
        "paired",
        {"files": {f"{TASK_DIR}/TEST_RESULTS.md": RESULTS_SECTION}},
        id="paired writes a step section",
    ),
]


@pytest.mark.parametrize(("name", "mode", "record"), HABIT_RECORDS)
def test_a_habit_record_of_the_test_engineers_mode_fails_its_check_for_that_mode(
    name, mode, record
):
    assert isinstance(_graded_outcome("test-engineer", name, mode, **record), Failed)


@pytest.mark.parametrize(("name", "mode", "record"), GOOD_RECORDS)
def test_a_record_in_the_form_its_rule_states_passes_the_check_for_that_mode(name, mode, record):
    assert _graded_outcome("test-engineer", name, mode, **record) == Passed()


@pytest.mark.parametrize(
    ("name", "other", "record"),
    [
        (TEST_ENGINEER_INPUTS, "paired", HABIT_RECORDS[0].values[2]),
        (TEST_ENGINEER_SECTIONS, "paired", HABIT_RECORDS[1].values[2]),
        (TEST_ENGINEER_RESULTS, "acceptance-design", HABIT_RECORDS[2].values[2]),
    ],
)
def test_a_test_engineer_check_is_not_applicable_to_a_task_of_its_other_mode(name, other, record):
    # The prompt names acceptance design on every task: the task's mode alone gates the check.
    outcome = _graded_outcome(
        "test-engineer", name, other, spawn_prompt="Mode: acceptance-design", **record
    )

    assert isinstance(outcome, NotApplicable)


@pytest.mark.parametrize(
    ("name", "mode"),
    [(TEST_ENGINEER_SECTIONS, "acceptance-design"), (TEST_ENGINEER_RESULTS, "paired")],
)
def test_a_test_engineer_document_check_is_not_applicable_when_the_task_stopped_it_early(
    name, mode
):
    assert isinstance(_graded_outcome("test-engineer", name, mode, forced_stop=True), NotApplicable)


# ---------------------------------------------------------------------------
# The systems-architect's own process, by the task's kit mode
# ---------------------------------------------------------------------------

ARCHITECT = "systems-architect"
PLAN = f"{TASK_DIR}/SYSTEMS_PLAN.md"
ARCHITECT_MODES = ("spec", "feature")
FIRST_READS = [_read_of(p) for p in ("TASK_BRIEF.md", "README.md", "pyproject.toml", "DESIGN.md")]
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
    outcome = _graded_outcome(ARCHITECT, ARCHITECT_PARTIAL, mode, **record)

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
    ],
)
def test_a_plan_of_its_own_shape_fails_the_architects_check_for_that_mode(name, mode, plan):
    files = {PLAN: plan} if plan else {}

    assert isinstance(_graded_outcome(ARCHITECT, name, mode, files=files), Failed)


@pytest.mark.parametrize(
    ("name", "mode", "plan"),
    [
        (ARCHITECT_SPEC_SECTIONS, "spec", SPEC_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", FEATURE_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SIBLING_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SUFFIXED_PLAN),
        (ARCHITECT_FEATURE_SECTIONS, "feature", RESCOPE_SKELETON_PLAN),
    ],
    ids=[
        "spec",
        "feature",
        "feature rescope-and-restart",
        "feature rescope with the assessment as a sibling section",
        "feature rescope with a level-four suffixed assessment",
        "feature rescope keeping the skeleton's pending design sections",
    ],
)
def test_a_plan_with_the_sections_its_mode_requires_passes(name, mode, plan):
    assert _graded_outcome(ARCHITECT, name, mode, files={PLAN: plan}) == Passed()


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
    outcome = _graded_outcome(ARCHITECT, name, other, spawn_prompt="Mode: spec", files={PLAN: plan})

    assert isinstance(outcome, NotApplicable)


@pytest.mark.parametrize(
    ("name", "mode"), [(ARCHITECT_SPEC_SECTIONS, "spec"), (ARCHITECT_FEATURE_SECTIONS, "feature")]
)
def test_an_architect_section_check_is_not_applicable_when_the_task_stopped_it_early(name, mode):
    assert isinstance(_graded_outcome(ARCHITECT, name, mode, forced_stop=True), NotApplicable)


@pytest.mark.parametrize("mode", ARCHITECT_MODES)
@pytest.mark.parametrize("clause", [FILE_NAME, ID_FROM_NAME], ids=["file name", "derived id"])
def test_a_hand_named_draft_with_a_made_up_id_still_fails_the_shared_adr_clauses(mode, clause):
    name = clause.format(role=ARCHITECT)

    assert isinstance(_graded_outcome(ARCHITECT, name, mode, files=HAND_NAMED_DRAFT), Failed)


# ---------------------------------------------------------------------------
# The convention a pilot role's project states only in its own instruction file
# ---------------------------------------------------------------------------

KERNEL_ELIGIBILITY_PIN = CHECKOUT_ROOT / "scripts" / "kernel_eligibility.py"


def _eligible_roles() -> set[str]:
    """The roles the commit gate's pin makes eligible, read by syntax: this project is its own."""
    for statement in ast.parse(KERNEL_ELIGIBILITY_PIN.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ELIGIBLE_ROLES"
            for target in statement.targets
        ):
            return set(ast.literal_eval(statement.value))
    raise AssertionError(f"{KERNEL_ELIGIBILITY_PIN} binds no ELIGIBLE_ROLES")


def test_every_pilot_role_is_a_role_the_commit_gate_makes_eligible():
    assert set(PILOT_ROLES) <= _eligible_roles()


@pytest.mark.parametrize("role", ROLES)
def test_a_role_carries_the_convention_check_exactly_when_it_is_a_pilot_role(role):
    names = [check.name for check in check_catalog(role)]

    assert (convention_check_name(role) in names) == (role in PILOT_ROLES)


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_the_convention_check_fails_a_session_that_never_wrote_the_conventions_wording(role):
    check = role_check(role, convention_check_name(role))

    outcome = check.evaluate(synthetic_evidence(role, files={"notes.md": "Nothing special."}))

    assert isinstance(outcome, Failed)


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_the_convention_check_passes_a_session_that_wrote_the_conventions_wording(role):
    check = role_check(role, convention_check_name(role))

    outcome = check.evaluate(synthetic_evidence(role, files={"notes.md": CONVENTION_MARKER}))

    assert outcome == Passed()


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_the_convention_check_is_not_applicable_to_a_task_that_stopped_the_role_early(role):
    stopped = TaskFacts(True, False, False, None, None, None)
    check = role_check(role, convention_check_name(role))

    assert isinstance(check.binds(role, stopped), DoesNotBind)
