"""The eval plan's move section claims what the move instrument now does, and nothing more.

The section of `eval/EVAL_PLAN.md` that documents `praxion-evals-adherence --move` names the
adr-conventions move's two governed checks with the rule section each grades, says its lean arm
links the moved rule scoped to the decision directory beside its resident kernel, names the two
build-time refusals (a path-matched rule the manifest would not link, a declared phrase its
section does not hold), gives the move's dry-run total, and no longer says the move has no task
kit or that the lean arm's rule never loads. It still says no paid run has happened and that
the path-matched trigger reading over a real record awaits a probe.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_PLAN = REPO_ROOT / "eval" / "EVAL_PLAN.md"
MOVE_ENTRY = "praxion-evals-adherence --move"
STATED = (
    "decision draft placement",
    "decision category",
    "file format",
    "what makes a decision",
    ".ai-state/decisions",
    "kernel",
    "--move adr-conventions --dry-run",
    "56",
    "no paid run",
    "probe",
    "expected failure",
)
RETRACTED = (
    "has no task kit",
    "the path-scoped rule never loads",
)


def _move_section() -> str:
    """The `###` section of the eval plan that documents the move entry."""
    text = EVAL_PLAN.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^(?=#{2,3} )", text)
    (section,) = [s for s in sections if s.startswith("### ") and MOVE_ENTRY in s]
    return section.lower()


@pytest.fixture(scope="module")
def section() -> str:
    return _move_section()


def _sentences(section: str) -> list[str]:
    return re.split(r"(?<=[.;:])\s+", section)


@pytest.mark.parametrize("claim", STATED)
def test_the_move_section_states_what_the_instrument_does(section, claim):
    assert claim in section, f"the move section does not state {claim!r}"


@pytest.mark.parametrize("claim", RETRACTED)
def test_the_move_section_no_longer_states_a_retracted_claim(section, claim):
    assert claim not in section, f"the move section still says {claim!r}"


@pytest.mark.parametrize("subject", ["manifest", "phrase"])
def test_the_move_section_names_each_build_time_refusal(section, subject):
    refusals = [s for s in _sentences(section) if "refus" in s and subject in s]

    assert refusals, f"no sentence of the move section names a refusal about the {subject}"
