"""The check catalog: C1 to C6 for every role, and each role's row of the role check table.

Every check names the rule it enforces as a file and a heading in it
(:class:`~praxion_evals.adherence.model.RuleRef`); the catalog's tests fail when
either does not exist. A role's row is a list of constructor applications from
:mod:`~praxion_evals.adherence.checks_roles`, so a clause cannot be added without
the canary that proves it fires. This module holds the rows of the seven pipeline roles; those
of the ten roles that advise, audit and report are in
:mod:`~praxion_evals.adherence.catalog_rows`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlparse

from praxion_evals.adherence.catalog_rows import (
    MALFORMED_LEDGER,
    PARTIAL_MARKER,
    SUPPORT_ROLE_ROWS,
    TECH_DEBT_LEDGER,
    convention_check,
)
from praxion_evals.adherence.checks_adr import adr_row
from praxion_evals.adherence.checks_common import COMMON_CHECKS
from praxion_evals.adherence.checks_process import (
    PARALLEL_MODE,
    change_confined_to,
    forbidden_reads,
    fragment_instead_of_canonical,
    fragments_reconciled,
    in_mode,
    in_task_mode,
    marker_written_first,
    red_tests,
    return_form,
    sibling_read_before_create,
)
from praxion_evals.adherence.checks_roles import (
    Section,
    binds_unless_stopped_early,
    closed_tag_set,
    documents_produced,
    has_content,
    path_scope,
    required_sections,
    script_exits_zero,
    section_bodies,
    section_body,
    section_problems,
    steps_carry_fields,
    text_excludes,
    title_marker_first_unmarked_last,
    titled_sections,
    tool_order,
)
from praxion_evals.adherence.model import (
    ROLES,
    Binding,
    Binds,
    CheckDef,
    DoesNotBind,
    Role,
    RuleRef,
    SessionEvidence,
    TaskFacts,
)
from praxion_evals.live.session import ToolUse

# ---------------------------------------------------------------------------
# The researcher
# ---------------------------------------------------------------------------

RESEARCHER_SECTIONS = (
    "researcher: RESEARCH_FINDINGS.md carries its Research Goal and Research Questions sections"
    " with content"
)
RESEARCHER_SOURCES = "researcher: RESEARCH_FINDINGS.md cites the sources it relies on"
RESEARCHER_DOCS_FIRST = (
    "researcher: on a question about an external API, the session fetches the vendor's current"
    " documentation (an llms.txt or Markdown page) before it searches"
)

# A citation is a link, a bare URL or a backticked path.
CITATION = re.compile(r"https?://|\]\([^)\s]+\)|`[^`\n]+`")
API_DOCS_HOST = "docs.example.com"  # the vendor host of the researcher's canary


def _binds_on_api_question(role: Role, facts: TaskFacts) -> Binding:
    del role
    if facts.external_api_docs is None:
        return DoesNotBind("the task asks about no external API")
    return Binds()


def _fetches_vendor_docs(evidence: SessionEvidence, use: ToolUse) -> bool:
    """A WebFetch on the vendor's docs host or a subdomain of it; the page form is not judged."""
    host = evidence.facts.external_api_docs
    if use.name != "WebFetch" or host is None:
        return False
    fetched = urlparse(str(use.input.get("url", ""))).hostname or ""
    return fetched == host or fetched.endswith("." + host)


def _searches_the_web(evidence: SessionEvidence, use: ToolUse) -> bool:
    del evidence
    return use.name == "WebSearch"


_RESEARCHER_CANARY_FACTS = TaskFacts(
    forced_stop=False,
    judging=False,
    fetchable_page=False,
    planted_instruction=None,
    planted_effect=None,
    external_api_docs=API_DOCS_HOST,
)

RESEARCHER_ROW: tuple[CheckDef, ...] = (
    required_sections(
        RESEARCHER_SECTIONS,
        RuleRef("agents/researcher.md", "RESEARCH_FINDINGS.md Structure"),
        "researcher",
        document="RESEARCH_FINDINGS.md",
        sections=(Section("Research Goal"), Section("Research Questions")),
    ),
    required_sections(
        RESEARCHER_SOURCES,
        RuleRef("agents/researcher.md", "Constraints"),
        "researcher",
        document="RESEARCH_FINDINGS.md",
        sections=(Section("Sources", CITATION),),
    ),
    tool_order(
        RESEARCHER_DOCS_FIRST,
        RuleRef("agents/researcher.md", "Phase 3 — External Research"),
        "researcher",
        earlier=_fetches_vendor_docs,
        earlier_label="fetched the vendor's documentation",
        later=_searches_the_web,
        later_label="a web search",
        earlier_sample=ToolUse(
            "canary-fetch", "WebFetch", {"url": f"https://{API_DOCS_HOST}/llms.txt"}, None
        ),
        later_sample=ToolUse("canary-search", "WebSearch", {"query": "example api"}, None),
        facts=_RESEARCHER_CANARY_FACTS,
        binds=_binds_on_api_question,
    ),
    convention_check("researcher"),
)

# ---------------------------------------------------------------------------
# The verifier
# ---------------------------------------------------------------------------

VERIFIER_PARTIAL = (
    "verifier: VERIFICATION_REPORT.md is written early with [PARTIAL] in its title and ends"
    " unmarked"
)
VERIFIER_TAGS = "verifier: its behavioral-contract findings use exactly the six canonical tags"
VERIFIER_LEDGER = "verifier: the ledger rows it writes pass check_state_ledgers.py --check"

EARLY_TOOL_CALLS = 3  # "Within your first three tool calls, write ... as a skeleton"
CANONICAL_TAGS = frozenset(
    {
        "UNSURFACED-ASSUMPTION",
        "MISSING-OBJECTION",
        "NON-SURGICAL",
        "SCOPE-CREEP",
        "BLOAT",
        "DEAD-CODE-UNREMOVED",
    }
)
VERIFIER_ROW: tuple[CheckDef, ...] = (
    title_marker_first_unmarked_last(
        VERIFIER_PARTIAL,
        RuleRef("agents/verifier.md", "Phase 12 -- Report Generation"),
        "verifier",
        document="VERIFICATION_REPORT.md",
        marker=PARTIAL_MARKER,
        within_first=EARLY_TOOL_CALLS,
    ),
    closed_tag_set(
        VERIFIER_TAGS,
        RuleRef("agents/verifier.md", "Phase 5.5 -- Behavioral Contract Compliance"),
        "verifier",
        document="VERIFICATION_REPORT.md",
        section="Behavioral Contract Findings",
        allowed=CANONICAL_TAGS,
    ),
    script_exits_zero(
        VERIFIER_LEDGER,
        RuleRef("agents/verifier.md", "Tech-Debt Ledger Writes"),
        "verifier",
        script="check_state_ledgers.py",
        arguments=("--check", "--repo-root", "{repo}"),
        planted={TECH_DEBT_LEDGER: MALFORMED_LEDGER},
        watched=(TECH_DEBT_LEDGER,),
    ),
    convention_check("verifier"),
)

# ---------------------------------------------------------------------------
# The implementer
# ---------------------------------------------------------------------------

IMPLEMENTER_PROGRESS = "implementer: [IN-PROGRESS] is written to WIP.md before any code change"
IMPLEMENTER_RETURN = (
    "implementer: the return is at most 5 lines and ends in [COMPLETE], [BLOCKED] or [CONFLICT]"
)
IMPLEMENTER_OUTER_LOOP = (
    "implementer: nothing changes under the acceptance or end-to-end test directories"
)
IMPLEMENTER_ID_CITATIONS = "implementer: check_id_citation_discipline.py exits 0 on its change"
IMPLEMENTER_FRAGMENT = "implementer: in parallel mode it writes WIP_implementer.md, not WIP.md"
IMPLEMENTER_TEST_RESULTS = "implementer: TEST_RESULTS.md has the shape its definition states"
IMPLEMENTER_SIBLING = (
    "implementer: an existing sibling file is read before a new file is created in a directory"
)

IN_PROGRESS = "[IN-PROGRESS]"
IMPLEMENTER_RETURN_LINES = 5
IMPLEMENTER_MARKERS = ("[COMPLETE]", "[BLOCKED]", "[CONFLICT]")
OUTER_LOOP_DIRECTORIES = ("tests/acceptance", "tests/e2e")
WIP_DOCUMENTS = ("WIP.md", "WIP_implementer.md")
TEST_RESULTS_DOCUMENTS = ("TEST_RESULTS.md", "TEST_RESULTS_implementer.md")
# A step section whose result line the shape checker cannot read: a count with no keys.
MALFORMED_TEST_RESULTS = "## Step 1 -- a change\nCommand: `pytest -q`\nResult: 3 passed\n"  # id-citation-discipline:ignore
CODE_WITH_A_CITATION = "# implements REQ-01\n"  # id-citation-discipline:ignore

IMPLEMENTER_ROW: tuple[CheckDef, ...] = (
    marker_written_first(
        IMPLEMENTER_PROGRESS,
        RuleRef("agents/implementer.md", "WIP.md Update Protocol"),
        "implementer",
        marker=IN_PROGRESS,
        documents=WIP_DOCUMENTS,
    ),
    return_form(
        IMPLEMENTER_RETURN,
        RuleRef("agents/implementer.md", "Output"),
        "implementer",
        max_lines=IMPLEMENTER_RETURN_LINES,
        markers=IMPLEMENTER_MARKERS,
    ),
    path_scope(
        IMPLEMENTER_OUTER_LOOP,
        RuleRef("agents/implementer.md", "Boundary Discipline"),
        "implementer",
        forbidden=OUTER_LOOP_DIRECTORIES,
    ),
    script_exits_zero(
        IMPLEMENTER_ID_CITATIONS,
        RuleRef("rules/swe/id-citation-discipline.md", "Enforcement"),
        "implementer",
        script="check_id_citation_discipline.py",
        arguments=("--repo-root", "{repo}", "--files", "{changed}"),
        planted={"src/app.py": CODE_WITH_A_CITATION},
    ),
    in_mode(
        fragment_instead_of_canonical(
            IMPLEMENTER_FRAGMENT,
            RuleRef("agents/implementer.md", "WIP.md Update Protocol"),
            "implementer",
            fragment="WIP_implementer.md",
            canonical="WIP.md",
        ),
        PARALLEL_MODE,
    ),
    script_exits_zero(
        IMPLEMENTER_TEST_RESULTS,
        RuleRef(
            "skills/software-planning/references/agent-pipeline-details.md",
            "TEST_RESULTS.md Reconciliation",
        ),
        "implementer",
        script="check_test_results_shape.py",
        arguments=("{document}",),
        planted={".ai-work/canary-task/TEST_RESULTS.md": MALFORMED_TEST_RESULTS},
        documents=TEST_RESULTS_DOCUMENTS,
    ),
    sibling_read_before_create(
        IMPLEMENTER_SIBLING, RuleRef("agents/implementer.md", "Constraints"), "implementer"
    ),
    convention_check("implementer"),
)

# ---------------------------------------------------------------------------
# The test-engineer
# ---------------------------------------------------------------------------

TEST_ENGINEER_RED = "test-engineer: its RED tests are present and fail"
TEST_ENGINEER_PRODUCTION = "test-engineer: its change touches no production file"
TEST_ENGINEER_INPUTS = (
    "test-engineer: in acceptance-design mode the session reads no input outside the allowed"
    " classes A1 to A4"
)
TEST_ENGINEER_SECTIONS = (
    "test-engineer: in acceptance-design mode ACCEPTANCE_TESTS.md has its five sections"
)
TEST_ENGINEER_RESULTS = (
    "test-engineer: in paired mode TEST_RESULTS.md carries a step section with its Command and"
    " Result lines"
)

TEST_FILE = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$"
)
TEST_RUNNER = re.compile(
    r"\b(pytest|unittest|vitest|jest|mocha|rspec|phpunit|go test|cargo test"
    r"|(npm|pnpm|yarn)( run)? test)\b"
)
TEST_FAILURE = re.compile(r"\b[1-9]\d* (failed|errors?)\b|\bFAILED\b|\bFAIL\b|\bERROR\b")
# The inputs the acceptance-design stage names as forbidden, so the audit is mechanical.
# The rest of its rule (the working-tree files that differ from the base commit, the
# parts of INTERFACE_DESIGN.md outside its public contract) is not readable from a stream.
_PIPELINE_DOCS = (
    "TASK_BRIEF|SYSTEMS_PLAN|SPEC_DELTA|RESEARCH_FINDINGS|IMPLEMENTATION_PLAN|WIP|LEARNINGS"
    "|CONTEXT_REVIEW|TRANSACTIONS_DESIGN|PRE_REFACTOR_PLAN"
)
FORBIDDEN_DESIGN_INPUTS = (
    re.compile(rf"\.ai-work/[^/\s]+/({_PIPELINE_DOCS}|CONSULT_[^/\s]*)\.md"),
    re.compile(r"\.ai-work/[^/\s]+/traceability\.yml"),
    re.compile(r"\.ai-state/decisions/drafts/"),
)
ACCEPTANCE_TESTS_SECTIONS = (
    "Sources Read",
    "Scenarios",
    "Boundary Assumptions",
    "Spec Questions",
    "Not Black-Box Testable",
)
# The step-section lines a free-form results note lacks. The shape script is no habit proof:
# it accepts such a note, and it errors where the plugin copy holds no scripts.
RESULTS_STEP_FIELDS = ("Command", "Result")
_TEST_ENGINEER = "agents/test-engineer.md"

TEST_ENGINEER_ROW: tuple[CheckDef, ...] = (
    red_tests(
        TEST_ENGINEER_RED,
        RuleRef(_TEST_ENGINEER, "Phase 3 — Test Implementation"),
        "test-engineer",
        is_test=TEST_FILE,
        runner=TEST_RUNNER,
        failure=TEST_FAILURE,
    ),
    change_confined_to(
        TEST_ENGINEER_PRODUCTION,
        RuleRef(_TEST_ENGINEER, "Constraints"),
        "test-engineer",
        allowed=TEST_FILE,
        outside_sample="src/app.py",
    ),
    in_task_mode(
        forbidden_reads(
            TEST_ENGINEER_INPUTS,
            RuleRef(_TEST_ENGINEER, "Inputs (closed set)"),
            "test-engineer",
            forbidden=FORBIDDEN_DESIGN_INPUTS,
            sample=".ai-work/canary-task/SYSTEMS_PLAN.md",
        ),
        "acceptance-design",
    ),
    in_task_mode(
        required_sections(
            TEST_ENGINEER_SECTIONS,
            RuleRef(_TEST_ENGINEER, "Mode: acceptance-design"),
            "test-engineer",
            document="ACCEPTANCE_TESTS.md",
            sections=tuple(Section(heading) for heading in ACCEPTANCE_TESTS_SECTIONS),
            binds=binds_unless_stopped_early,
        ),
        "acceptance-design",
    ),
    in_task_mode(
        steps_carry_fields(
            TEST_ENGINEER_RESULTS,
            RuleRef(
                "skills/software-planning/references/agent-pipeline-details.md",
                "TEST_RESULTS.md Reconciliation",
            ),
            "test-engineer",
            document="TEST_RESULTS.md",
            fields=RESULTS_STEP_FIELDS,
            binds=binds_unless_stopped_early,
        ),
        "paired",
    ),
    convention_check("test-engineer"),
)

# ---------------------------------------------------------------------------
# The doc-engineer
# ---------------------------------------------------------------------------

DOC_ENGINEER_FRAGMENT = "doc-engineer: in parallel mode it writes WIP_doc-engineer.md, not WIP.md"
DOC_ENGINEER_DOCS_ONLY = "doc-engineer: its change touches documentation only"
DOC_ENGINEER_ADR_LINKS = "doc-engineer: links to ADRs point at finalized records, never at drafts"

DOCUMENTATION = re.compile(r"\.(md|mdx|rst|txt|adoc)$|(^|/)docs/")
DRAFT_LINK = re.compile(r"\]\([^)\s]*decisions/drafts/[^)\s]*\)")
_DOC_ENGINEER = "agents/doc-engineer.md"

DOC_ENGINEER_ROW: tuple[CheckDef, ...] = (
    in_mode(
        fragment_instead_of_canonical(
            DOC_ENGINEER_FRAGMENT,
            RuleRef(_DOC_ENGINEER, "Fragment Files"),
            "doc-engineer",
            fragment="WIP_doc-engineer.md",
            canonical="WIP.md",
        ),
        PARALLEL_MODE,
    ),
    change_confined_to(
        DOC_ENGINEER_DOCS_ONLY,
        RuleRef(_DOC_ENGINEER, "File Disjointness"),
        "doc-engineer",
        allowed=DOCUMENTATION,
        outside_sample="src/app.py",
    ),
    text_excludes(
        DOC_ENGINEER_ADR_LINKS,
        RuleRef("rules/swe/adr-conventions.md", "Linking to ADRs"),
        "doc-engineer",
        pattern=DRAFT_LINK,
        within=DOCUMENTATION,
        sample_path="docs/architecture.md",
        sample_text="See [the decision](../.ai-state/decisions/drafts/20261011-0930-a-b-c.md).\n",
    ),
)

# ---------------------------------------------------------------------------
# The systems-architect and the implementation-planner
# ---------------------------------------------------------------------------

ARCHITECT_PARTIAL = (
    "systems-architect: SYSTEMS_PLAN.md is written early with [PARTIAL] in its title and ends"
    " unmarked"
)
ARCHITECT_SPEC_SECTIONS = (
    "systems-architect: in spec mode SYSTEMS_PLAN.md carries its Goal, Acceptance Criteria and"
    " a Behavioral Specification with an Observable Surface"
)
ARCHITECT_FEATURE_SECTIONS = (
    "systems-architect: in feature mode SYSTEMS_PLAN.md carries its six required sections"
)

OBSERVABLE_SURFACE = re.compile(r"^### Observable Surface\s*$", re.MULTILINE)
SPEC_SECTIONS = (
    Section("Goal"),
    Section("Acceptance Criteria"),
    Section("Behavioral Specification", OBSERVABLE_SURFACE),
)
FEATURE_SECTIONS = tuple(
    Section(heading)
    for heading in (
        "Goal",
        "Tech Stack",
        "Acceptance Criteria",
        "Architecture",
        "Codebase Readiness",
        "Risk Assessment",
    )
)
# The rescope-and-restart outcome writes the Goal, the Codebase Readiness and an assessment
# that names the outcome on its heading line or in its own body, and no Architecture or Risk
# Assessment: a plan that fills either is held to the six. A skeleton heading left [pending]
# writes nothing, and any other section (such as the Tech Stack or Acceptance Criteria Phase 1 fills first) is allowed.
RESCOPE_OUTCOME = "rescope-and-restart"
RESCOPE_SECTIONS = (Section("Goal"),)
RESCOPE_PRESENT = "Codebase Readiness"
RESCOPE_ASSESSMENT = re.compile(r"Pre-Refactor Assessment\b.*")
RESCOPE_ASSESSMENT_LEVELS = (2, 3, 4)
RESCOPE_ABSENT = ("Architecture", "Risk Assessment")
TOP_SECTION_LEVEL = (2,)


def rescope_problems(text: str) -> list[str]:
    """What keeps a plan from the one the rescope-and-restart outcome writes."""
    problems = section_problems(text, RESCOPE_SECTIONS)
    if section_body(text, RESCOPE_PRESENT) is None:
        problems.append(f"no section {RESCOPE_PRESENT!r}")
    assessments = titled_sections(text, RESCOPE_ASSESSMENT, RESCOPE_ASSESSMENT_LEVELS)
    if not any(RESCOPE_OUTCOME in "\n".join([title, *body]) for title, body in assessments):
        problems.append(f"no Pre-Refactor Assessment that names {RESCOPE_OUTCOME!r}")
    problems.extend(
        f"a section {heading!r} the outcome does not write"
        for heading in RESCOPE_ABSENT
        if any(
            has_content(body)
            for body in section_bodies(text, re.compile(re.escape(heading)), TOP_SECTION_LEVEL)
        )
    )
    return problems


_ARCHITECT = "agents/systems-architect.md"

# The adr_row clauses are shared with three other roles and bind only on a written draft, so
# they cannot prove the role's habit; the three checks after them can. The early-write check
# is not gated by mode: the kit draws only spec and feature tasks, and both write the plan
# (only the baseline-audit mode, never drawn, writes none).
ARCHITECT_ROW: tuple[CheckDef, ...] = (
    *adr_row("systems-architect"),
    title_marker_first_unmarked_last(
        ARCHITECT_PARTIAL,
        RuleRef(_ARCHITECT, "Phase 10 — Document Creation"),
        "systems-architect",
        document="SYSTEMS_PLAN.md",
        marker=PARTIAL_MARKER,
        within_first=EARLY_TOOL_CALLS,
    ),
    in_task_mode(
        required_sections(
            ARCHITECT_SPEC_SECTIONS,
            RuleRef(_ARCHITECT, "Phase 1 — Input Assessment"),
            "systems-architect",
            document="SYSTEMS_PLAN.md",
            sections=SPEC_SECTIONS,
            binds=binds_unless_stopped_early,
        ),
        "spec",
    ),
    in_task_mode(
        required_sections(
            ARCHITECT_FEATURE_SECTIONS,
            RuleRef(_ARCHITECT, "Phase 10 — Document Creation"),
            "systems-architect",
            document="SYSTEMS_PLAN.md",
            sections=FEATURE_SECTIONS,
            or_form=rescope_problems,
            binds=binds_unless_stopped_early,
        ),
        "feature",
    ),
    convention_check("systems-architect"),
)

PLANNER_STEPS = (
    "implementation-planner: every plan step carries its files and its done-when condition"
)
PLANNER_DOCUMENTS = "implementation-planner: WIP.md and TEST_BASELINE.md are produced"
PLANNER_RECONCILED = (
    "implementation-planner: in a parallel batch, fragments are reconciled into the canonical"
    " documents"
)
STEP_FIELDS = ("Files", "Done when")
BATCH_FRAGMENTS = re.compile(r"(WIP|LEARNINGS)_[a-z-]+\.md")
_PLANNER = "agents/implementation-planner.md"

PLANNER_ROW: tuple[CheckDef, ...] = (
    *adr_row("implementation-planner"),
    steps_carry_fields(
        PLANNER_STEPS,
        RuleRef(_PLANNER, "Phase 3 — Step Decomposition"),
        "implementation-planner",
        document="IMPLEMENTATION_PLAN.md",
        fields=STEP_FIELDS,
    ),
    documents_produced(
        PLANNER_DOCUMENTS,
        RuleRef(_PLANNER, "Phase 6 — Document Completion"),
        "implementation-planner",
        documents=("WIP.md", "TEST_BASELINE.md"),
    ),
    in_mode(
        fragments_reconciled(
            PLANNER_RECONCILED,
            RuleRef(_PLANNER, "Phase 7 — Execution Supervision"),
            "implementation-planner",
            canonical="WIP.md",
            fragments=BATCH_FRAGMENTS,
        ),
        PARALLEL_MODE,
    ),
)
# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

ROLE_ROWS: Mapping[str, tuple[CheckDef, ...]] = {
    "researcher": RESEARCHER_ROW,
    "verifier": VERIFIER_ROW,
    "implementer": IMPLEMENTER_ROW,
    "test-engineer": TEST_ENGINEER_ROW,
    "doc-engineer": DOC_ENGINEER_ROW,
    "systems-architect": ARCHITECT_ROW,
    "implementation-planner": PLANNER_ROW,
    **SUPPORT_ROLE_ROWS,
}


def check_catalog(role: str) -> tuple[CheckDef, ...]:
    """C1 to C6, then the role's own row of the role check table."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; known: {list(ROLES)}")
    return (*COMMON_CHECKS.values(), *ROLE_ROWS.get(role, ()))


def role_check(role: str, name: str) -> CheckDef:
    """The role's check called ``name``: a common check by its ``C<n>``, or a clause by its text."""
    checks = check_catalog(role)
    for check in checks:
        if check.name == name:
            return check
    raise ValueError(f"no check named {name!r} for {role}; known: {[c.name for c in checks]}")
