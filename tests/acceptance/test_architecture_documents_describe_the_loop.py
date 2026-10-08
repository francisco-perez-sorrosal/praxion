"""The architecture documents describe the step-loop driver and the turn-budget reminder.

The developer guide describes both as built components and every path it names for them
exists; the scripts guide has entries for the driver's command and the modules behind it;
the design target marks both rows of their section Built.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.shipped_texts import (
    REPO_ROOT,
    lines_containing,
    path_of,
    read,
    section,
)

DEVELOPER_GUIDE = "docs/architecture.md"
SCRIPTS_GUIDE = "scripts/CLAUDE.md"
DESIGN_TARGET = ".ai-state/DESIGN.md"

DRIVER = r"step_loop\.py"
REMINDER = r"remind_turn_budget\.py"
LOOP_TOPIC = r"step[_ -]loop|turn[_ -]budget|_agent_transcript"
NAMED_PATH = re.compile(r"`([\w./-]+/[\w.-]+\.(?:py|md|json|sh|jsonl))`")


def _paths_named_for_the_loop_that_do_not_exist(relative: str) -> list[str]:
    named = {
        path
        for line in lines_containing(read(relative), LOOP_TOPIC)
        for path in NAMED_PATH.findall(line)
    }
    return sorted(path for path in named if not path_of(path).exists())


@pytest.mark.parametrize("component", [DRIVER, REMINDER], ids=["driver", "reminder"])
@pytest.mark.parametrize("guide", [DEVELOPER_GUIDE, SCRIPTS_GUIDE])
def test_the_guide_describes_the_component(guide, component):
    assert lines_containing(read(guide), component), f"{guide} never names {component}"


def test_every_path_the_developer_guide_names_for_the_loop_exists():
    assert _paths_named_for_the_loop_that_do_not_exist(DEVELOPER_GUIDE) == []


def _modules_behind_the_driver() -> list[str]:
    return sorted(p.name for p in (REPO_ROOT / "scripts").glob("_step_loop*.py"))


def _modules_the_scripts_guide_does_not_name() -> list[str]:
    guide = read(SCRIPTS_GUIDE)
    return [name for name in _modules_behind_the_driver() if name not in guide]


def test_the_scripts_guide_has_an_entry_for_every_module_behind_the_driver():
    assert _modules_behind_the_driver(), "no module sits behind the driver's command"
    assert _modules_the_scripts_guide_does_not_name() == []


def _design_rows() -> list[str]:
    body = section(read(DESIGN_TARGET), r"step[- ]loop")
    return lines_containing(body, r"^\|.*(driver|reminder)")


def _rows_not_marked_built(rows: list[str]) -> list[str]:
    return [row for row in rows if not re.search(r"\|\s*\**Built\**\s*\|", row)]


def test_the_design_target_marks_both_rows_of_the_loops_section_built():
    rows = _design_rows()

    assert len(rows) >= 2, f"the step-loop section has no driver and reminder rows: {rows}"
    assert _rows_not_marked_built(rows) == []
