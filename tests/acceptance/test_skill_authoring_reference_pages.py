"""The skill-authoring reference pages hold the depth the entry page links to.

Three new pages state the description-tuning loop, both evaluation formats and the agent-facing
script contract; the user-invoked guide agrees with the entry page; the template, examples and
workflow patterns live in the content-guidance page and the two pages that held them are gone.
"""

from __future__ import annotations

import posixpath
import re

import pytest

from tests.acceptance.drivers.skill_pages import (
    REFERENCES,
    paragraphs,
    read,
    read_tracked,
    reference,
    sentences,
    tracked_files,
)


def page(name: str) -> str:
    return read(reference(name)).replace("`", "")


def assert_states(text: str, pattern: str, what: str, name: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.DOTALL), (
        f"references/{name} does not state {what} (looked for /{pattern}/)"
    )


# --- the description-tuning loop ---------------------------------------------------------------

DESCRIPTION_LOOP = {
    "about twenty realistic queries": r"\b(twenty|20)\b",
    "about half should-trigger and half near-miss queries": r"\bhalf\b",
    "near-miss queries that must not trigger": r"near[- ]miss",
    "each query run three times": r"(three|3) (times|runs)",
    "a trigger-rate threshold of 0.5": r"\b0\.5\b",
    "60 percent of queries used for tuning": r"\b60\s*(%|percent)",
    "40 percent held out": r"\b40\s*(%|percent)",
    "the winner chosen on the held-out part": r"held[- ]out",
    "at most five iterations": r"(five|5) iterations",
    "generalizing from failures rather than adding keywords": r"generali[sz]",
    "not adding the failing query's keywords": r"keyword",
    "the plugin eval runner": r"claude plugin eval",
    "a tool_used grader": r"tool_used",
    "the Skill tool as the grader's target": r"\bSkill\b",
    "a zero ceiling for a must-not-trigger case": r"ceiling",
    "the must-not-trigger case scored in both arms": r"both arms",
}


@pytest.mark.parametrize("what", sorted(DESCRIPTION_LOOP))
def test_the_description_optimization_page_states_the_measured_tuning_loop(what):
    name = "description-optimization.md"
    assert_states(page(name), DESCRIPTION_LOOP[what], what, name)


# --- both evaluation formats -------------------------------------------------------------------

EVALUATION_FORMATS = {
    "the open-standard evals file": r"evals/evals\.json",
    "the skill name it carries": r"skill[ _]name",
    "each eval's id": r"\bid\b",
    "each eval's prompt": r"\bprompt\b",
    "each eval's expected output": r"expected[ _]output",
    "each eval's input files": r"\bfiles\b",
    "each eval's assertions": r"assertions",
    "running each eval with and without the skill": r"without the skill|without[ _]skill",
    "grading each assertion with cited evidence": r"evidence",
    "reporting the with-minus-without delta": r"delta",
    "recording human feedback": r"feedback",
    "keeping evals few, each with a reason to exist": r"\bfew\b",
    "the plugin eval runner": r"claude plugin eval",
    "a prompt.md per case": r"prompt\.md",
    "graders per case": r"grader",
    "the grader types, tool_used among them": r"tool_used",
    "three runs per case": r"(three|3) runs",
    "the no-plugin baseline": r"no[- ]plugin",
    "the threshold": r"threshold",
    "the exit status": r"exit (status|code)",
    "that the two formats are not interchangeable": r"not interchangeable",
}


@pytest.mark.parametrize("what", sorted(EVALUATION_FORMATS))
def test_the_evaluating_skills_page_states_both_formats(what):
    name = "evaluating-skills.md"
    assert_states(page(name), EVALUATION_FORMATS[what], what, name)


# --- the agent-facing script contract ----------------------------------------------------------

SCRIPT_CONTRACT = {
    "no interactive prompts": r"interactive",
    "self-documentation through --help": r"--help",
    "an error saying what was wrong": r"wrong",
    "an error saying what was expected": r"expected",
    "results on standard output": r"stdout|standard output",
    "diagnostics on standard error": r"stderr|standard error",
    "structured results for another program": r"structured|json",
    "distinct, documented exit codes": r"exit codes?",
    "safe to re-run": r"re-?run|idempot",
    "--dry-run for anything destructive": r"--dry-run",
    "destructive operations": r"destructive",
    "bounded output": r"bound|truncat|cap\b|limit",
    "pinned dependencies through inline script metadata": r"PEP 723|inline script metadata",
    "or a pinned runner": r"\bpin",
}


@pytest.mark.parametrize("what", sorted(SCRIPT_CONTRACT))
def test_the_scripts_for_agents_page_states_the_script_contract(what):
    name = "scripts-for-agents.md"
    assert_states(page(name), SCRIPT_CONTRACT[what], what, name)


# --- the user-invoked guide agrees with the entry page -----------------------------------------

USER_INVOKED_GUIDE = "user-invoked-skills.md"


def test_the_user_invoked_guide_covers_forked_execution_with_agent_and_background():
    covering = [
        p
        for p in paragraphs(read(reference(USER_INVOKED_GUIDE)))
        if all(
            re.search(x, p) for x in (r"\bcontext\b", r"\bfork", r"\bagent\b", r"\bbackground\b")
        )
    ]

    assert covering, "no paragraph of the guide covers forked execution with agent and background"


def caveat_sentences(text: str) -> list[str]:
    """Sentences telling the reader to expect the validator to flag a supported field as unknown."""
    return [
        s
        for s in sentences(text)
        if re.search(r"validat", s, re.I)
        and re.search(r"unknown", s, re.I)
        and re.search(r"\b(expect|still|although|until|lags?|aligned)\b", s, re.I)
    ]


@pytest.mark.parametrize("name", [USER_INVOKED_GUIDE, "schema.md"])
def test_no_guidance_tells_authors_to_expect_unknown_field_findings_for_supported_fields(name):
    found = caveat_sentences(read(reference(name)))

    assert not found, f"references/{name} still carries the validator-gap caveat: {found}"


# --- the template, examples and workflow patterns have one home --------------------------------

FOLDED_PATTERNS = {
    "the strict template pattern": (r"strict", r"template"),
    "the flexible template pattern": (r"flexible", r"template"),
    "the examples pattern": (r"examples", r"pattern|input|output"),
    "the sequential workflow pattern": (r"sequential", r"workflow|step"),
    "the conditional workflow pattern": (r"conditional", r"workflow|branch"),
}


@pytest.mark.parametrize("pattern", sorted(FOLDED_PATTERNS))
def test_the_content_guidance_page_offers_each_folded_pattern(pattern):
    blocks = paragraphs(read(reference("content-and-development.md")))
    covering = [b for b in blocks if all(re.search(x, b, re.I) for x in FOLDED_PATTERNS[pattern])]

    assert covering, f"content-and-development.md does not offer {pattern}"


RETIRED_PAGES = ("output-patterns.md", "workflows.md")
RETIRED_PATHS = {f"skills/skill-crafting/references/{name}" for name in RETIRED_PAGES}


@pytest.mark.parametrize("name", RETIRED_PAGES)
def test_a_folded_reference_page_no_longer_exists(name):
    assert not (REFERENCES / name).exists()


# Frozen history: records of the past, never rewritten. Also exempt: this outer loop, which
# names the retired pages in order to assert their absence, and the raw observation logs, which
# record tool calls (the deletion itself among them) as they happened.
FROZEN_HISTORY = re.compile(
    r"^(\.ai-state/(decisions|specs|sentinel_reports|metrics_reports|skill_genesis_reports)/"
    r"|\.ai-state/(TECH_DEBT_LEDGER|TECH_DEBT_RESOLVED)\.md$|CHANGELOG\.md$"
    r"|\.ai-state/observations[^/]*$|tests/acceptance/)"
)
_PATH_MENTION = re.compile(r"[\w./-]*(?:output-patterns|workflows)\.md")


def mentions_of_retired_pages(relative: str, text: str) -> list[str]:
    """Each line naming a path that resolves, from the file or from the root, to a retired page."""
    here = posixpath.dirname(relative)
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        resolved = {
            path
            for mention in _PATH_MENTION.findall(line)
            for path in (
                posixpath.normpath(posixpath.join(here, mention)),
                posixpath.normpath(mention),
            )
        }
        if resolved & RETIRED_PATHS:
            hits.append(f"{relative}:{number}: {line.strip()[:160]}")
    return hits


def test_nothing_outside_frozen_history_points_at_a_folded_page():
    hits = [
        hit
        for relative in tracked_files()
        if not FROZEN_HISTORY.search(relative)
        for hit in mentions_of_retired_pages(relative, read_tracked(relative) or "")
    ]

    assert not hits, f"{len(hits)} live references to a folded page:\n" + "\n".join(hits[:40])
