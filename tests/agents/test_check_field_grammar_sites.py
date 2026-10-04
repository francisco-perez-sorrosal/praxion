"""The `Check:` field is one grammar at every site that states it.

`_loop_fields.py` owns the grammar and exposes its one-line form
(`CHECK_GRAMMAR_LINE`); the module docstring, the canonical template paragraph
and the planner prompt quote it. `SKILL.md` is loaded by four agents on every
spawn, so it carries only the step-template line and a pointer, never the
grammar. A site that reorders the keys or drops `expects` would teach planners a
line the reconciler reads as unreadable, so each site is pinned here, the
template examples are parsed by the real parsers, and a canary proves the pin
bites.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import _loop_fields  # noqa: E402
from _loop_fields import CHECK_GRAMMAR_LINE, Check, parse_attempts, parse_check_field  # noqa: E402

TEMPLATES = REPO_ROOT / "skills" / "software-planning" / "references" / "document-templates.md"
SKILL = REPO_ROOT / "skills" / "software-planning" / "SKILL.md"
PLANNER = REPO_ROOT / "agents" / "implementation-planner.md"
IMPLEMENTER = REPO_ROOT / "agents" / "implementer.md"

GRAMMAR_SITES = {
    "_loop_fields docstring": lambda: _loop_fields.__doc__ or "",
    "document-templates paragraph": lambda: TEMPLATES.read_text(encoding="utf-8"),
    "implementation-planner prompt": lambda: PLANNER.read_text(encoding="utf-8"),
}

TEMPLATE_STEP_LINE = "**Check**: `<command>` expects pass>=<n> fail=0 [pending=<n>]"

# Anything shaped like the grammar line: from the label to the closing bracket of
# the expectation list, so a drifted copy is found as well as a faithful one.
_GRAMMAR_SHAPED_RE = re.compile(r"Check: `<command>`[^\n`]*?\]")
_EXAMPLE_CHECK_RE = re.compile(r"^\*\*Check\*\*: `uv run .*$", re.MULTILINE)
_ATTEMPTS_LINE_RE = re.compile(r"^ +- Attempts: .*$", re.MULTILINE)
_CHECK_MENTION_RE = re.compile(r"\*\*Check\*\*|`Check:`")


def quoted_grammar_lines(text: str) -> list[str]:
    return _GRAMMAR_SHAPED_RE.findall(text)


def states_the_grammar_exactly(text: str) -> bool:
    quoted = quoted_grammar_lines(text)
    return bool(quoted) and all(line == CHECK_GRAMMAR_LINE for line in quoted)


def parses_as_a_check(line: str) -> bool:
    return isinstance(parse_check_field(line), Check)


@pytest.mark.parametrize("site", GRAMMAR_SITES)
def test_each_grammar_site_quotes_the_constant_exactly(site: str) -> None:
    assert states_the_grammar_exactly(GRAMMAR_SITES[site]())


def test_a_concrete_line_in_the_constants_shape_parses() -> None:
    assert CHECK_GRAMMAR_LINE.startswith("Check: `<command>` expects ")
    assert parses_as_a_check("Check: `pytest -q` expects pass>=1 fail=0")


def test_the_template_check_example_parses() -> None:
    examples = _EXAMPLE_CHECK_RE.findall(TEMPLATES.read_text(encoding="utf-8"))
    assert examples, "document-templates.md carries no concrete `Check:` example"
    assert all(parses_as_a_check(line) for line in examples), examples


@pytest.mark.parametrize("path", [TEMPLATES, SKILL], ids=["template", "skill"])
def test_the_step_template_line_names_the_check_field(path: Path) -> None:
    assert TEMPLATE_STEP_LINE in path.read_text(encoding="utf-8")


def test_the_template_attempts_examples_parse() -> None:
    examples = _ATTEMPTS_LINE_RE.findall(TEMPLATES.read_text(encoding="utf-8"))
    assert len(examples) == 2, "both WIP templates show the `Attempts:` sub-bullet"
    for line in examples:
        assert parse_attempts(line).counts, line


def test_skill_carries_only_the_template_line_and_the_pointer() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert quoted_grammar_lines(text) == []
    assert "expects <key><op><count>" not in text
    assert len(_CHECK_MENTION_RE.findall(text)) == 2
    assert "`Check:` field** (implementer steps only)" in text


def test_planner_clause_states_scope_and_the_pending_rule() -> None:
    text = PLANNER.read_text(encoding="utf-8")
    assert "implementer steps only" in text
    assert "`pending=<n>`" in text


def test_canary_a_reordered_or_expects_less_site_is_rejected() -> None:
    reordered = "Check: `<command>` <key><op><count> expects [<key><op><count> ...]"
    expects_less = "Check: `<command>` <key><op><count> [<key><op><count> ...]"
    swapped_parts = "Check: `<command>` expects <op><key><count> [<key><op><count> ...]"
    for drifted in (reordered, expects_less, swapped_parts):
        assert not states_the_grammar_exactly(drifted)
    assert states_the_grammar_exactly(CHECK_GRAMMAR_LINE)
    assert not parses_as_a_check("Check: `pytest -q` pass>=1 fail=0")
    assert not parses_as_a_check("Check: `pytest -q` expects pass>=1")


def implementer_check_behavior_clause(text: str) -> bool:
    return (
        "record its `Result:` line last" in text
        and "never edit a `Check:` or an `Attempts:` line" in text
        and "return `[BLOCKED]` when the check cannot pass without contradicting the spec" in text
    )


def test_implementer_runs_the_check_and_never_edits_check_or_attempts_lines() -> None:
    text = IMPLEMENTER.read_text(encoding="utf-8")
    assert implementer_check_behavior_clause(text)
    assert "Files, `Check`, and `Read-only` when present" in text


def test_canary_an_implementer_clause_that_allows_editing_the_check_is_rejected() -> None:
    editable = (
        "record its `Result:` line last; edit the `Check:` line when it is wrong, "
        "and return `[BLOCKED]` when the check cannot pass without contradicting the spec"
    )
    assert not implementer_check_behavior_clause(editable)
