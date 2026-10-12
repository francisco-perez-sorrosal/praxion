"""The check catalog: C1 to C6 for every role, and each role's row of the role check table.

Every check names the rule it enforces as a file and a heading in it
(:class:`~praxion_evals.adherence.model.RuleRef`); the catalog's tests fail when
either does not exist. A role's row is a list of constructor applications from
:mod:`~praxion_evals.adherence.checks_roles`, so a clause cannot be added without
the canary that proves it fires. This module holds the researcher's and the
verifier's rows; a role with no row yet carries C1 to C6 alone.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlparse

from praxion_evals.adherence.checks_common import COMMON_CHECKS
from praxion_evals.adherence.checks_roles import (
    Section,
    closed_tag_set,
    required_sections,
    script_exits_zero,
    title_marker_first_unmarked_last,
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

PARTIAL_MARKER = "[PARTIAL]"
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
TECH_DEBT_LEDGER = ".ai-state/TECH_DEBT_LEDGER.md"
_LEDGER_COLUMNS = (
    "id | severity | class | direction | location | goal-ref-type | goal-ref-value | source"
    " | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key"
)
# The ledger's real header over a row with two cells where fifteen belong.
MALFORMED_LEDGER = (
    "# Technical Debt Ledger\n\n**Schema**: 14 row fields + 1 structural `dedup_key`.\n\n"
    f"| {_LEDGER_COLUMNS} |\n|{'---|' * 15}\n| td-001 | suggested |\n"
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
)

# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

ROLE_ROWS: Mapping[str, tuple[CheckDef, ...]] = {
    "researcher": RESEARCHER_ROW,
    "verifier": VERIFIER_ROW,
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
