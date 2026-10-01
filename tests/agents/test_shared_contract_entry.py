"""The `contract:` entry of a step's `**Read-only**:` field is one convention at five sites.

The decomposition guide defines it (with its golden bad-case), the plan template
carries its grammar, the planner places the contract step before the split, and
the implementer and its delegation checklist use the contract without editing it.
A site that drifts from the grammar or drops the rule leaves two lanes free to
encode two readings of one regex again, so each site is pinned here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

GRAMMAR = "contract: <path>::<symbol>, pinned by <test node>"

# Sites that state the full grammar, and sites that only consume the entry.
GRAMMAR_SITES = (
    "skills/software-planning/references/decomposition-guide.md",
    "skills/software-planning/references/document-templates.md",
    "agents/implementation-planner.md",
)
CONSUMER_SITES = (
    "agents/implementer.md",
    "skills/software-planning/references/coordination-details.md",
)


def _states_grammar(text: str) -> bool:
    return GRAMMAR in text


def _forbids_editing_contract(text: str) -> bool:
    entry = text.find("`contract:`")
    if entry == -1:
        return False
    window = text[entry : entry + 300]
    return "never edit" in window or "rather than edit" in window


@pytest.mark.parametrize("site", GRAMMAR_SITES)
def test_grammar_sites_state_the_contract_entry_grammar(site: str) -> None:
    assert _states_grammar((REPO_ROOT / site).read_text(encoding="utf-8"))


@pytest.mark.parametrize("site", CONSUMER_SITES)
def test_consumer_sites_forbid_editing_a_contract(site: str) -> None:
    assert _forbids_editing_contract((REPO_ROOT / site).read_text(encoding="utf-8"))


def test_the_guide_carries_the_golden_bad_case() -> None:
    guide = (REPO_ROOT / GRAMMAR_SITES[0]).read_text(encoding="utf-8")
    section = guide[guide.index("### Shared Contracts Before Parallel Lanes") :]
    assert "**Golden bad-case**" in section.split("\n## ", 1)[0]


def test_canary_a_drifted_grammar_or_an_editable_contract_is_rejected() -> None:
    assert not _states_grammar("**Read-only**: contract: <file>, pinned by <test>")
    assert not _forbids_editing_contract("A `contract:` entry there may be adjusted as needed.")
