"""The skill-authoring entry page teaches the canon in the order an author needs it.

A reader meets who invokes a skill first, then the eval-first loop, degrees of freedom and
gotchas, scripts for agents, runtime lifecycle facts and portability, and the page closes with a
checklist. The page stays small and every reference page is one link away.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.skill_pages import (
    ENTRY_PAGE,
    ENTRY_TOPICS,
    LAYOUT_TOPIC,
    REFERENCES,
    first_heading,
    headings,
    last_h2_section,
    links_to_reference,
    list_items,
    opens_with_contents,
    read,
    section,
)


def entry() -> str:
    return read(ENTRY_PAGE)


def topic_section(topic: str) -> str:
    return section(entry(), ENTRY_TOPICS[topic], topic)


def assert_states(text: str, pattern: str, what: str) -> None:
    assert re.search(pattern, text.replace("`", ""), re.IGNORECASE | re.DOTALL), (
        f"the section does not state {what} (looked for /{pattern}/)"
    )


# --- order of topics ---------------------------------------------------------------------------


def first_positions(text: str, patterns: dict[str, str], *, headings_only: bool) -> list:
    """`(position, name)` of each pattern's first match, None for a pattern never matched."""
    found = []
    for name, pattern in patterns.items():
        if headings_only:
            heading = first_heading(text, pattern)
            found.append((heading[2], name) if heading else (None, name))
        else:
            match = re.search(pattern, text, re.IGNORECASE)
            found.append((match.start(), name) if match else (None, name))
    return found


def test_the_entry_page_meets_the_reader_with_its_topics_in_the_canonical_order():
    positions = first_positions(entry(), ENTRY_TOPICS, headings_only=True)
    missing = [name for at, name in positions if at is None]

    assert not missing, f"no heading names: {missing}"
    assert positions == sorted(positions), f"topics appear out of order: {sorted(positions)}"


def test_invocation_modes_come_before_any_layout_or_packaging_guidance():
    text = entry()
    invocation = first_heading(text, ENTRY_TOPICS["invocation modes"])
    layout = [h for h in headings(text) if re.search(LAYOUT_TOPIC, h[1], re.IGNORECASE)]

    assert invocation is not None, "no heading names the invocation modes"
    assert all(invocation[2] < h[2] for h in layout), (
        f"layout or packaging guidance precedes the invocation modes: {[h[1] for h in layout]}"
    )


# --- who invokes a skill and who reads its description -----------------------------------------

INVOCATION_STATEMENTS = {
    "the user-only mode and its key": r"disable-model-invocation",
    "the hidden-from-the-menu mode and its key": r"user-invocable",
    "the forked mode and its key": r"\bcontext\b.{0,40}\bfork|\bfork.{0,80}\bcontext\b",
    "the forked mode's agent key": r"\bagent\b",
    "the forked mode's background key": r"\bbackground\b",
    "which modes keep a description in the always-loaded listing": r"listing",
    "a model-invocable description in the third person": r"third[- ]person",
    "a description focused on user intent": r"intent",
    "that a description never summarizes the procedure": r"summar",
    "a user-only description as one plain line": r"one (plain )?line|single line|one-line",
    "guarding a side-effecting skill as user-only": r"side[- ]effect",
}


@pytest.mark.parametrize("what", sorted(INVOCATION_STATEMENTS))
def test_the_invocation_section_states_who_invokes_and_who_reads_the_description(what):
    assert_states(topic_section("invocation modes"), INVOCATION_STATEMENTS[what], what)


# --- the eval-first creation loop --------------------------------------------------------------


CREATION_STEPS = {
    "record failures without the skill": r"without (the|a|any) skill|no[- ]skill",
    "write at least three scenarios": r"(three|3)\b[^.\n]{0,40}(scenario|eval)|at least (three|3)",
    "write the smallest body": r"smallest|minimal",
    "re-run against the baseline": r"re-?run",
}


def test_the_creation_procedure_records_failures_before_writing_and_reruns_against_a_baseline():
    text = topic_section("eval-first creation loop").replace("`", "")
    positions = first_positions(text, CREATION_STEPS, headings_only=False)
    missing = [step for at, step in positions if at is None]

    assert not missing, f"the creation procedure never says to: {missing}"
    assert positions == sorted(positions), f"steps out of order: {sorted(positions)}"


@pytest.mark.parametrize(
    ("what", "pattern"),
    [
        (
            "near-miss cases that must not trigger the skill",
            r"near[- ]miss|not trigger|should[- ]not",
        ),
        ("comparison against a no-skill baseline", r"baseline"),
        ("the plugin eval runner for a plugin-shipped skill", r"claude plugin eval"),
    ],
)
def test_the_creation_procedure_names_its_evaluation_needs(what, pattern):
    assert_states(topic_section("eval-first creation loop"), pattern, what)


# --- degrees of freedom and gotchas first ------------------------------------------------------

FREEDOM_STATEMENTS = {
    "specificity matched to the task's fragility": r"fragil",
    "prose for open choices": r"prose",
    "parameterized patterns where a default exists": r"parameteri[sz]",
    "exact commands where one safe path exists": r"exact command",
    "one default with an escape hatch over a menu": r"escape hatch",
    "gotchas leading the body": r"gotcha",
    "the gotcha list grown from observed failures": r"observ",
    "load-bearing instructions near the top": r"near the top|top of the body|at the top",
}


@pytest.mark.parametrize("what", sorted(FREEDOM_STATEMENTS))
def test_the_specificity_section_teaches_degrees_of_freedom_and_gotchas_first(what):
    assert_states(topic_section("degrees of freedom and gotchas"), FREEDOM_STATEMENTS[what], what)


# --- runtime lifecycle facts -------------------------------------------------------------------

LIFECYCLE_FACTS = {
    "the always-loaded listing under a budget": r"listing.{0,200}budget|budget.{0,200}listing",
    "least-used entries dropping first": r"least[- ](recently[- ])?used",
    "description plus when_to_use truncated at 1,536 characters": r"when_to_use.{0,200}1,?536|1,?536.{0,200}when_to_use",
    "an invoked body is not re-read": r"(not|never) re-?read",
    "the first 5,000 tokens re-attached after compaction": r"5,?000",
    "25,000 tokens for all re-attached skills": r"25,?000",
    "compaction": r"compact",
    "plugin skills discovered at session start": r"session start|start of (a|the) session|when a session starts",
    "a mid-session skill invisible until a fresh session": r"fresh session|new session",
    "a worktree-built skill as the example": r"worktree",
    "an unknown frontmatter key ignored silently": r"(unknown|unrecogni[sz]ed|misspel).{0,80}(key|field)",
    "per-skill overrides not applying to plugin skills": r"override.{0,200}plugin|plugin.{0,200}override",
}


@pytest.mark.parametrize("what", sorted(LIFECYCLE_FACTS))
def test_the_lifecycle_section_states_each_runtime_fact(what):
    assert_states(topic_section("runtime lifecycle facts"), LIFECYCLE_FACTS[what], what)


@pytest.mark.parametrize(("fact", "pattern"), [("1,536", r"1,?536"), ("5,000", r"5,?000")])
def test_each_numeric_lifecycle_fact_is_stated_once_on_the_entry_page(fact, pattern):
    count = len(re.findall(rf"(?<![\d,]){pattern}(?![\d,])", entry()))

    assert count == 1, f"{fact} is stated {count} times on the entry page"


# --- scripts designed for agents ---------------------------------------------------------------

SCRIPT_STATEMENTS = {
    "bundling for deterministic work": r"determinis",
    "bundling a helper an agent keeps rewriting": r"rewrit",
    "running without interactive prompts": r"interactive",
    "solving error cases rather than deferring them": r"error",
    "justifying constants": r"constant",
}


@pytest.mark.parametrize("what", sorted(SCRIPT_STATEMENTS))
def test_the_scripts_section_states_when_and_how_to_bundle_a_script(what):
    assert_states(topic_section("scripts designed for agents"), SCRIPT_STATEMENTS[what], what)


def test_the_scripts_section_links_the_full_script_contract_in_one_hop():
    assert links_to_reference(topic_section("scripts designed for agents"), "scripts-for-agents.md")


# --- what travels between hosts ----------------------------------------------------------------

PORTABILITY_STATEMENTS = {
    "name and description read by every host": r"(every|all|each) host",
    "the fields Cursor reads": r"cursor",
    "the fields Codex reads": r"codex",
    "the claude.ai upload rejecting other fields": r"claude\.ai.{0,300}(reject|refus|fail)",
    "Claude Code ignoring keys it does not recognize": r"ignor",
}
CLAUDE_AI_FIELDS = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")


@pytest.mark.parametrize("what", sorted(PORTABILITY_STATEMENTS))
def test_the_portability_section_states_what_travels(what):
    assert_states(topic_section("portability between hosts"), PORTABILITY_STATEMENTS[what], what)


@pytest.mark.parametrize("field", CLAUDE_AI_FIELDS)
def test_the_portability_section_names_each_field_a_claude_ai_upload_accepts(field):
    text = topic_section("portability between hosts").replace("`", "")
    upload = [s for s in re.split(r"(?<=[.!?])\s+", text) if "claude.ai" in s]

    assert any(re.search(rf"(?<![\w-]){re.escape(field)}(?![\w-])", s) for s in upload), (
        f"no claude.ai sentence names {field}"
    )


# --- the closing checklist ---------------------------------------------------------------------

CHECKLIST_COVERAGE = {
    "name and directory agree": (r"\bname\b", r"director"),
    "description written for its reader": (
        r"description",
        r"reader|invo|third[- ]person|user[- ]only",
    ),
    "entry page under 500 lines with references one hop away": (r"500", r"hop|direct|link"),
    "gotchas present": (r"gotcha",),
    "three scenarios with should-not-trigger cases against a baseline": (
        r"three|\b3\b",
        r"not[- ]trigger|near[- ]miss|should[- ]not",
        r"baseline",
    ),
    "bundled scripts meet the agent-facing contract": (r"script",),
    "drift-prone sections cataloged and marked": (r"stal|drift", r"mark"),
    "the validator run with no error": (r"validat", r"error"),
}


def test_the_entry_page_closes_with_its_checklist():
    title, _ = last_h2_section(entry())

    assert re.search(ENTRY_TOPICS["closing checklist"], title, re.IGNORECASE), (
        f"the last section is {title!r}"
    )


@pytest.mark.parametrize("item", sorted(CHECKLIST_COVERAGE))
def test_the_closing_checklist_has_one_item_for_each_canon_requirement(item):
    _, text = last_h2_section(entry())
    items = [i.replace("`", "") for i in list_items(text)]

    assert any(
        all(re.search(p, i, re.IGNORECASE) for p in CHECKLIST_COVERAGE[item]) for i in items
    ), f"no checklist item covers: {item}"


# --- small entry page, every reference one hop away --------------------------------------------

REFERENCE_PAGES = sorted(p.name for p in REFERENCES.glob("*.md"))


def test_the_entry_page_is_under_five_hundred_lines():
    count = len(entry().splitlines())

    assert count < 500, f"the entry page has {count} lines"


@pytest.mark.parametrize(
    "page",
    sorted(
        set(REFERENCE_PAGES)
        | {"description-optimization.md", "evaluating-skills.md", "scripts-for-agents.md"}
    ),
)
def test_every_reference_page_is_linked_directly_from_the_entry_page(page):
    assert (REFERENCES / page).is_file(), f"references/{page} does not exist"
    assert links_to_reference(entry(), page), f"the entry page does not link references/{page}"


LONG_REFERENCE_PAGES = sorted(
    p.name for p in REFERENCES.glob("*.md") if len(p.read_text(encoding="utf-8").splitlines()) > 100
)


@pytest.mark.parametrize("page", LONG_REFERENCE_PAGES)
def test_a_reference_page_over_a_hundred_lines_opens_with_a_list_of_its_contents(page):
    assert opens_with_contents(read(REFERENCES / page)), (
        f"references/{page} is over 100 lines and has no contents list near its top"
    )
