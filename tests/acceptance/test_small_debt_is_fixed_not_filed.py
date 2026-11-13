"""Small debt found while solving a task is fixed after the feature, not filed as a ledger row.

Presence checks: each text a reader meets carries its part of the rule once. The definition of
small and the filing rule live in the ledger reference, one sentence in the always-loaded
summary, the closing step at the pipeline's exit, and the finders' lines in their definitions;
the roles that find debt with no task at hand keep filing rows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers import kernel_adoption, kernel_sandbox, kernel_spawn
from tests.acceptance.drivers.follow_ups import RECORD
from tests.acceptance.drivers.kernel_sandbox import (
    REPO_ROOT,
    Sandbox,
    agent_path,
    markdown_sections,
    normalize_plugin_location,
)

INTERMEDIATE_DOCUMENTS = "rules/swe/agent-intermediate-documents.md"
LEDGER_REFERENCE = "skills/software-planning/references/tech-debt-ledger.md"
COORDINATION_REFERENCE = "skills/software-planning/references/coordination-details.md"
SUMMARY_HEADING = "living tech-debt ledger pair"
TERMINAL_STATES = ("fixed <sha>", "ledgered td-NNN", "dropped <reason>")

# The seven conditions of small, each recognised by the words that state it.
SMALL_CONDITIONS = {
    "one commit, at most two production files": r"\b(two|2) production files\b",
    "no design decision": r"\bdesign decision",
    "no decision record": r"\b(decision record|ADR)\b",
    "no new dependency": r"\bnew dependenc",
    "no change to acceptance, end-to-end or frozen tests": r"\bfrozen\b",
    "nothing on the ask-first list": r"\bask-first\b",
    "no change to a shipped contract": r"\bshipped contract",
    "fits in the current session": r"\bcurrent session\b",
}


def read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def tech_debt_summary() -> str:
    found = [
        s.body
        for s in markdown_sections(read(INTERMEDIATE_DOCUMENTS))
        if SUMMARY_HEADING in s.heading
    ]
    assert len(found) == 1, f"no single tech-debt summary in {INTERMEDIATE_DOCUMENTS}"
    return found[0]


def missing(patterns: dict[str, str], text: str) -> list[str]:
    return [name for name, p in patterns.items() if not re.search(p, text, re.IGNORECASE)]


# -- One definition, one filing rule -------------------------------------------------------------


def test_the_always_loaded_summary_says_small_debt_is_fixed_rather_than_filed() -> None:
    summary = tech_debt_summary()

    assert re.search(r"\bsmall\b", summary, re.I), summary
    assert re.search(r"\bfix", summary, re.I), summary


def test_the_ledger_reference_states_all_seven_conditions_of_small() -> None:
    assert missing(SMALL_CONDITIONS, read(LEDGER_REFERENCE)) == []


def test_the_ledger_reference_files_a_row_only_for_debt_that_is_not_small() -> None:
    assert re.search(r"\bnot small\b", read(LEDGER_REFERENCE), re.I)


# -- The finders and the pipeline's exit --------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    ["agents/verifier.md", "agents/implementer.md", LEDGER_REFERENCE, COORDINATION_REFERENCE],
)
def test_a_text_that_routes_small_debt_names_the_follow_up_record(rel: str) -> None:
    assert RECORD in read(rel), f"{rel} does not name {RECORD}"


def test_the_pipeline_exit_names_every_final_state_a_follow_up_closes_in() -> None:
    text = read(COORDINATION_REFERENCE)

    assert [s for s in TERMINAL_STATES if s not in text] == []


@pytest.mark.parametrize("rel", [LEDGER_REFERENCE, COORDINATION_REFERENCE])
def test_a_reference_keeps_follow_ups_in_the_task_list_at_the_tiers_without_a_task_directory(
    rel: str,
) -> None:
    text = read(rel)

    assert re.search(r"\btask list\b", text, re.I), f"{rel} names no task list"
    assert re.search(r"\bfollow-ups?\b", text, re.I), f"{rel} names no follow-up"


@pytest.mark.parametrize("role", ["sentinel", "architect-validator"])
def test_a_finder_with_no_task_at_hand_is_never_told_to_record_a_follow_up(role: str) -> None:
    assert RECORD not in read(agent_path(role))


# -- What the finders' kernels carry ------------------------------------------------------------


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def injected(sandbox: Sandbox, tmp_path: Path, role: str) -> str:
    """The kernel text `role` is given at spawn, at trial, without its own definition."""
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial(role))
    project = kernel_spawn.project_checkout(tmp_path / "project")
    joined = kernel_spawn.spawn(sandbox.root, project, f"praxion:{role}").joined
    return normalize_plugin_location(joined, sandbox.root)


def test_the_verifiers_kernel_routes_small_debt_to_the_follow_up_record(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    assert RECORD in injected(sandbox, tmp_path, "verifier")


@pytest.mark.parametrize("role", ["sentinel", "architect-validator"])
def test_a_ledger_writer_with_no_task_at_hand_gets_no_follow_up_routing_in_its_kernel(
    sandbox: Sandbox, tmp_path: Path, role: str
) -> None:
    assert RECORD not in injected(sandbox, tmp_path, role)
