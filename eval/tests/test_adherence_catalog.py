"""The check catalog: every role's checks, the rule each names, and the canary each carries."""

from __future__ import annotations

from dataclasses import replace

import pytest

from praxion_evals.adherence import grade
from praxion_evals.adherence.catalog import (
    RESEARCHER_DOCS_FIRST,
    RESEARCHER_SECTIONS,
    RESEARCHER_SOURCES,
    ROLE_ROWS,
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
from praxion_evals.adherence.checks_common import COMMON_CHECKS, synthetic_evidence
from praxion_evals.adherence.checks_roles import CHECKOUT_ROOT, section_body
from praxion_evals.adherence.model import (
    ROLES,
    Binds,
    CheckErrored,
    DoesNotBind,
    Failed,
    Measured,
    NotApplicable,
    Passed,
    TaskFacts,
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


@pytest.mark.parametrize(("role", "clauses"), [("researcher", 3), ("verifier", 3)])
def test_the_researcher_and_the_verifier_each_carry_their_three_clauses(role, clauses):
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
    [("implementer", 7), ("test-engineer", 4), ("doc-engineer", 3), ("systems-architect", 6)],
)
def test_each_role_carries_one_check_per_clause_of_its_row(role, clauses):
    assert len(ROLE_ROWS[role]) == clauses
    assert all(check.name.startswith(f"{role}: ") for check in ROLE_ROWS[role])


@pytest.mark.parametrize(
    ("role", "clauses"),
    [
        ("sentinel", 4),
        ("architect-validator", 3),
        ("context-engineer", 2),
        ("cicd-engineer", 1),
        ("discipline-consultant", 3),
        ("promethean", 3),
        ("roadmap-cartographer", 4),
        ("skill-genesis", 3),
    ],
)
def test_each_remaining_role_carries_one_check_per_clause_of_its_row(role, clauses):
    assert len(ROLE_ROWS[role]) == clauses
    assert all(check.name.startswith(f"{role}: ") for check in ROLE_ROWS[role])


@pytest.mark.parametrize("role", ["interface-designer", "agentic-transactions-architect"])
def test_the_design_roles_share_the_adr_clauses_and_add_their_challenges_and_self_test(role):
    names = [c.name.removeprefix(f"{role}: ") for c in ROLE_ROWS[role]]
    architect = [c.name.removeprefix("systems-architect: ") for c in ROLE_ROWS["systems-architect"]]

    assert names[: len(architect)] == architect
    assert len(names) == len(architect) + 2


def test_the_planner_shares_the_architects_adr_clauses_and_adds_its_own():
    names = [
        c.name.removeprefix("implementation-planner: ") for c in ROLE_ROWS["implementation-planner"]
    ]
    architect = [c.name.removeprefix("systems-architect: ") for c in ROLE_ROWS["systems-architect"]]

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
    outcome = check.evaluate(check.violation())

    assert isinstance(outcome, Failed), f"{role}/{check.name}: the canary read as {outcome}"


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
