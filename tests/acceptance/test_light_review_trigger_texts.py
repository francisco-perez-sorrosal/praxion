"""Every text that says when a light review fires states one plan-local rule.

A step carrying `review: force` or `tier: H` is reviewed unless it carries `review: off`.
An uncertainty flag below 7 and a one-way door reach the trigger only through the planner
marking the steps they bear on `review: force`, so no site names either as a signal read
when a step completes.

Clause-level reading (see the `shipped_texts` driver; a table row is one sentence, and
parentheses bound a clause): a clause that names an uncertainty flag or a one-way door
also names `review: force` and the marking (mark, tag, annotate, set, write or add).
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.shipped_texts import (
    CLAUSE_BREAK,
    COORDINATION_PROTOCOL,
    INTRA_STEP_REVIEW,
    PLANNER_PROMPT,
    SOFTWARE_PLANNING_SKILL,
    lines_containing,
    read,
    sentences_matching,
)

ANNOTATIONS = (r"review: ?force", r"tier: ?H\b", r"review: ?off")
INDIRECT_SIGNAL = r"uncertainty[- ]flag|one[- ]way[- ]door"
MARKING = r"\b(mark|tag|annotat|set|writ|add)\w*"


def _intra_step_review_row() -> str:
    rows = lines_containing(read(COORDINATION_PROTOCOL), r"^\|.*(light-review|pair-review)")
    assert rows, "the coordination protocol has no pipeline-rules row for intra-step review"
    return "\n".join(rows)


SITES = {
    "intra-step-review-reference": lambda: read(INTRA_STEP_REVIEW),
    "implementation-planner-prompt": lambda: read(PLANNER_PROMPT),
    "software-planning-skill": lambda: read(SOFTWARE_PLANNING_SKILL),
    "coordination-protocol-row": _intra_step_review_row,
}


def _missing_annotations(text: str) -> list[str]:
    return [a for a in ANNOTATIONS if not sentences_matching(text, a)]


def _indirect_signals_named_as_triggers(text: str) -> list[str]:
    """Clauses naming an uncertainty flag or a one-way door other than as the planner's
    reason to mark a step `review: force`."""
    named = sentences_matching(text, INDIRECT_SIGNAL, breaks=CLAUSE_BREAK)
    routed = set(
        sentences_matching(text, INDIRECT_SIGNAL, r"review: ?force", MARKING, breaks=CLAUSE_BREAK)
    )
    return [s for s in named if s not in routed]


@pytest.mark.parametrize("site", list(SITES))
def test_the_site_states_the_three_annotations_of_the_rule(site):
    assert _missing_annotations(SITES[site]()) == []


@pytest.mark.parametrize("site", list(SITES))
def test_the_site_never_names_an_indirect_signal_as_a_trigger(site):
    assert _indirect_signals_named_as_triggers(SITES[site]()) == []
