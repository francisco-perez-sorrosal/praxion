"""The cap on fresh attempts per step is stated once, in the completion handshake.

`_loop_fields.ATTEMPT_CAP` is the number the reconciler enforces; the handshake's
`Attempt cap` paragraph in `agent-pipeline-details.md` is the one prose site that
states it. Every other mention (the Mechanism paragraph, the spawn-budget note)
points there without a number, so changing the cap means editing the constant and
one paragraph, and a second spelled-out copy cannot drift. This pin checks that
the paragraph equals the constant, that no other prose file spells the number next
to "fresh attempts", and that the paragraph carries the behavior the orchestrator
follows. A canary proves the single-site scan bites.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from _loop_fields import ATTEMPT_CAP  # noqa: E402

REFERENCES = REPO_ROOT / "skills" / "software-planning" / "references"
PIPELINE_DETAILS = REFERENCES / "agent-pipeline-details.md"
COORDINATION_DETAILS = REFERENCES / "coordination-details.md"

# The prose an agent loads. `docs/architecture.md` describes the constant for
# developers and states the number beside it; it is not read by the orchestrator.
PROSE_ROOTS = ("skills", "agents", "rules", "commands", "claude")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_NUMBER_BEFORE_ATTEMPTS = r"\b(" + "|".join(NUMBER_WORDS) + r"|\d+)\s+fresh\s+attempts?\b"
_STATED_NUMBER_RE = re.compile(_NUMBER_BEFORE_ATTEMPTS, re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"^\*\*Attempt cap\.\*\*.*$", re.MULTILINE)


def attempt_cap_paragraph() -> str:
    match = _PARAGRAPH_RE.search(PIPELINE_DETAILS.read_text(encoding="utf-8"))
    assert match, "the handshake has no `Attempt cap` paragraph"
    return match.group(0)


def stated_numbers(text: str) -> list[int]:
    return [NUMBER_WORDS.get(word.lower()) or int(word) for word in _STATED_NUMBER_RE.findall(text)]


def prose_files_stating_a_number() -> list[Path]:
    return [
        path
        for root in PROSE_ROOTS
        for path in sorted((REPO_ROOT / root).rglob("*.md"))
        if stated_numbers(path.read_text(encoding="utf-8"))
    ]


def test_the_paragraph_states_the_number_the_reconciler_enforces() -> None:
    assert stated_numbers(attempt_cap_paragraph()) == [ATTEMPT_CAP]


def test_exactly_one_prose_site_states_the_number() -> None:
    assert prose_files_stating_a_number() == [PIPELINE_DETAILS]


def test_the_paragraph_is_the_only_statement_inside_its_own_file() -> None:
    text = PIPELINE_DETAILS.read_text(encoding="utf-8")
    assert len(stated_numbers(text)) == 1


def test_the_mechanism_and_spawn_budget_pointers_state_no_number() -> None:
    mechanism = next(
        line
        for line in PIPELINE_DETAILS.read_text(encoding="utf-8").splitlines()
        if line.startswith("**Mechanism.**")
    )
    assert "**Attempt cap**" in mechanism
    assert stated_numbers(mechanism) == []
    budget = COORDINATION_DETAILS.read_text(encoding="utf-8")
    assert "agent-pipeline-details.md § Completion handshake" in budget
    assert stated_numbers(budget) == []


def test_the_paragraph_carries_the_behavior_the_orchestrator_follows() -> None:
    paragraph = attempt_cap_paragraph()
    for clause in (
        "a resumed agent continues its current attempt",
        "`[BLOCKED]` with a replan request",
        "no third fresh attempt starts",
        "two attempts that do not converge",
        "writes `count=<n+1>`",
        "scripts/iteration_ledger.py append",
    ):
        assert clause in paragraph, clause


def test_fragment_merges_never_touch_an_attempts_line() -> None:
    text = PIPELINE_DETAILS.read_text(encoding="utf-8")
    assert "A fragment merge never touches an `Attempts:` line" in text


def test_canary_a_second_spelled_out_copy_is_found_and_a_pointer_is_not() -> None:
    assert stated_numbers("A step gets at most three fresh attempts.") == [3]
    assert stated_numbers("It gets 2 fresh attempts, then stops.") == [2]
    assert stated_numbers("The step used its fresh attempts; see the handshake.") == []
    assert stated_numbers("the fresh-attempt count") == []
