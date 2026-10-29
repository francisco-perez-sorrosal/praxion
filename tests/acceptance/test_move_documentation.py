"""The eval plan and the adherence how-to describe the main-session half of the instrument.

Together, `eval/EVAL_PLAN.md` and `docs/lean-spawn-how-to.md` (or a how-to it links) describe
moves and their full, lean and floor arms, the floor run with its continuation and citation,
the trigger record, the allowance and coverage statements, the sensitivity line, the dry run,
the git-conventions kit and the moves the instrument can express.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_PLAN = REPO_ROOT / "eval" / "EVAL_PLAN.md"
HOW_TO = REPO_ROOT / "docs" / "lean-spawn-how-to.md"
TOPICS = (
    "governed check",
    "floor run",
    "trigger record",
    "sensitivity line",
    "git-conventions",
    "adr-conventions",
)


def _documents() -> str:
    """The eval plan, the how-to, and every docs page the how-to links."""
    how_to = HOW_TO.read_text(encoding="utf-8")
    linked = {
        (HOW_TO.parent / target).resolve() for target in re.findall(r"\]\(([^)#\s]+\.md)", how_to)
    }
    pages = [EVAL_PLAN.read_text(encoding="utf-8"), how_to]
    pages += [page.read_text(encoding="utf-8") for page in sorted(linked) if page.is_file()]
    return "\n".join(pages).lower()


@pytest.fixture(scope="module")
def documents() -> str:
    return _documents()


@pytest.mark.parametrize("topic", TOPICS)
def test_the_eval_plan_and_how_to_describe_each_part_of_the_main_session_half(documents, topic):
    assert topic in documents, f"neither the eval plan nor the how-to describes {topic!r}"
