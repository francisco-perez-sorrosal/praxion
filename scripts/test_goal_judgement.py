"""Tests for the judgement of a goal iteration (``scripts/_goal_record.py``).

Covers what counts as a progressing iteration and the order in which a protected change, a red
gate, a regression, an empty diff and a missing progress line decide; the readers of a
``Result:`` line and of the progress record; and the protected-path helper.
"""

from __future__ import annotations

import re
import sys
from collections import ChainMap
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _goal_record as goal  # noqa: E402
from _goal_record import Evidence, Progressing, Protected, Reading, Unkept  # noqa: E402

REFERENCE = Reading(passes=5, failures=2)
OWN_FILE = "scripts/_goal_record.py"
PROTECTED_PATH = "tests/acceptance/test_goal.py"

KEPT = Evidence(
    red=False,
    reading=REFERENCE,
    reference=REFERENCE,
    changed_files=(OWN_FILE,),
    progress_before=1,
    progress_now=2,
)

PROTECTED_BREAK = {"protected_changes": (PROTECTED_PATH,)}
RED_BREAK = {"red": True}
REGRESSION_BREAK = {"reading": Reading(passes=5, failures=3)}
EMPTY_DIFF_BREAK = {"changed_files": ()}
NO_LINE_BREAK = {"progress_now": 1}

# Each rung first, then every rung below it, in the order the judgement reads them.
LADDER = [
    (
        (PROTECTED_BREAK, RED_BREAK, REGRESSION_BREAK, EMPTY_DIFF_BREAK, NO_LINE_BREAK),
        Protected,
        "Protected(paths=('tests/acceptance/test_goal.py',))",
    ),
    (
        (RED_BREAK, REGRESSION_BREAK, EMPTY_DIFF_BREAK, NO_LINE_BREAK),
        Unkept,
        goal.RED_GATE,
    ),
    ((REGRESSION_BREAK, EMPTY_DIFF_BREAK, NO_LINE_BREAK), Unkept, "the check regressed"),
    ((EMPTY_DIFF_BREAK, NO_LINE_BREAK), Unkept, goal.NO_FILE_CHANGED),
    ((NO_LINE_BREAK,), Unkept, goal.NO_PROGRESS_LINE),
]


def evidence(*breaks: dict) -> Evidence:
    """The kept iteration with each of `breaks` applied, the first taking precedence."""
    return replace(KEPT, **dict(ChainMap(*breaks)))


# --- The precedence of the judgement ---


def test_an_iteration_that_breaks_nothing_is_progressing() -> None:
    assert goal.judge(KEPT) == Progressing()


@pytest.mark.parametrize(("breaks", "kind", "fragment"), LADDER)
def test_a_rung_alone_decides_the_judgement(
    breaks: tuple[dict, ...], kind: type, fragment: str
) -> None:
    judgement = goal.judge(evidence(breaks[0]))

    assert isinstance(judgement, kind)
    assert fragment in repr(judgement)


@pytest.mark.parametrize(("breaks", "kind", "fragment"), LADDER)
def test_a_rung_beats_every_rung_below_it(
    breaks: tuple[dict, ...], kind: type, fragment: str
) -> None:
    judgement = goal.judge(evidence(*breaks))

    assert isinstance(judgement, kind)
    assert fragment in repr(judgement)


@pytest.mark.parametrize(
    ("upper", "lower"),
    [
        (PROTECTED_BREAK, RED_BREAK),
        (RED_BREAK, REGRESSION_BREAK),
        (REGRESSION_BREAK, EMPTY_DIFF_BREAK),
        (EMPTY_DIFF_BREAK, NO_LINE_BREAK),
    ],
)
def test_a_rung_loses_to_the_one_above_it(upper: dict, lower: dict) -> None:
    assert goal.judge(evidence(upper, lower)) == goal.judge(evidence(upper))


def test_a_protected_change_names_every_path_it_touched() -> None:
    paths = (PROTECTED_PATH, "rules/swe/x.md")

    assert goal.judge(evidence({"protected_changes": paths})) == Protected(paths)


# --- Regression ---


@pytest.mark.parametrize(
    ("passes", "failures", "regressed"),
    [
        (5, 3, True),  # one failure more
        (4, 2, True),  # one pass fewer
        (4, 3, True),  # both worse
        (5, 2, False),  # equal counts
        (6, 2, False),  # one pass more
        (5, 1, False),  # one failure fewer
        (7, 0, False),  # both better
    ],
)
def test_a_reading_is_a_regression_only_when_a_count_is_worse(
    passes: int, failures: int, regressed: bool
) -> None:
    assert Reading(passes, failures).regressed_from(REFERENCE) is regressed


@pytest.mark.parametrize(("passes", "failures"), [(5, 3), (4, 2)])
def test_a_regression_by_one_is_not_kept(passes: int, failures: int) -> None:
    judgement = goal.judge(evidence({"reading": Reading(passes, failures)}))

    assert isinstance(judgement, Unkept)
    assert f"{passes} passing and {failures} failing" in judgement.reason


def test_equal_counts_with_a_change_and_a_line_are_kept() -> None:
    assert goal.judge(evidence({"reading": REFERENCE})) == Progressing()


# --- The diff and the progress record ---


@pytest.mark.parametrize(
    ("before", "now", "kept"),
    [
        (0, 1, True),  # the first line of a record
        (3, 4, True),
        (3, 3, False),  # no line added
        (3, 2, False),  # a line removed is no progress
        (3, 0, False),
    ],
)
def test_the_progress_record_must_gain_a_line(before: int, now: int, kept: bool) -> None:
    judgement = goal.judge(evidence({"progress_before": before, "progress_now": now}))

    assert (judgement == Progressing()) is kept


def test_an_iteration_that_changed_no_file_is_not_kept() -> None:
    assert goal.judge(evidence(EMPTY_DIFF_BREAK)) == Unkept(goal.NO_FILE_CHANGED)


# --- The reference reading ---

BASELINE_LINE = "Result: pass=0 fail=0 skip=0 pending=3 by=step-loop"
COMMITTED_LINE = "Result: pass=12 fail=0 skip=0 pending=1 by=step-loop"
ERRORED_LINE = "Result: pass=4 fail=1 skip=2 error=2 pending=3 by=step-loop"
LEGACY_LINE = "Result: pass=12 fail=1 skip=0"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (BASELINE_LINE, Reading(0, 3)),  # a baseline: the goal's own failures are pending
        (COMMITTED_LINE, Reading(12, 1)),
        (ERRORED_LINE, Reading(4, 6)),  # failed + pending + errors
        (LEGACY_LINE, Reading(12, 1)),  # a line with no pending key
        ("Result: none — no summary", None),
        ("Result: pass=x", None),
        ("pass=12 fail=0", None),
        ("", None),
    ],
)
def test_a_result_line_reads_as_the_counts_the_judgement_compares(
    line: str, expected: Reading | None
) -> None:
    assert goal.reading_from_result(line) == expected


def test_a_first_iteration_is_judged_against_the_baseline_reading() -> None:
    reference = goal.reading_from_result(BASELINE_LINE)
    reading = goal.reading_from_result("Result: pass=2 fail=0 skip=0 pending=1 by=step-loop")

    judgement = goal.judge(evidence({"reading": reading, "reference": reference}))

    assert judgement == Progressing()


def test_a_later_iteration_is_judged_against_the_last_committed_reading() -> None:
    reference = goal.reading_from_result(COMMITTED_LINE)
    worse = goal.reading_from_result("Result: pass=11 fail=0 skip=0 pending=1 by=step-loop")

    judgement = goal.judge(evidence({"reading": worse, "reference": reference}))

    assert isinstance(judgement, Unkept)


@pytest.mark.parametrize(("passes", "failures"), [(-1, 0), (0, -1)])
def test_a_reading_cannot_count_fewer_than_none(passes: int, failures: int) -> None:
    with pytest.raises(ValueError, match="at least|fewer"):
        Reading(passes, failures)


# --- The progress record ---


def wip(*section: str) -> str:
    return "\n".join(["# WIP", "", "## Progress", "", "- [ ] one", "", *section])


@pytest.mark.parametrize(
    ("text", "count"),
    [
        (wip(), 0),  # no section at all
        (wip("## Progress record", ""), 0),  # an empty section
        (wip("## Progress record", "", "- did one", "- did two", "- did three"), 3),
        (wip("## Progress record", "", "- did one", "", "", "- did two", ""), 2),
        (wip("## Progress record", "- did one", "## Notes", "- not a record line"), 1),
        (wip("## Progress record", "- did one", "### Detail", "- still the record"), 3),
        (wip("## Progress record  ", "- did one"), 1),
        (wip("## Progress records", "- not this section"), 0),
    ],
)
def test_the_progress_record_counts_its_own_non_blank_lines(text: str, count: int) -> None:
    assert goal.progress_line_count(text) == count


def test_the_progress_checklist_is_not_the_progress_record() -> None:
    assert goal.progress_line_count("## Progress\n\n- [x] one\n- [x] two\n") == 0


# --- The protected set ---

DEFAULT_SET = goal.protected_set(())
READ_ONLY_FILE = "scripts/_step_loop_gate.py"
READ_ONLY_DIRECTORY = "scripts/fixtures/"
READ_ONLY_GLOB = "scripts/test_goal_*.py"
READ_ONLY_NODE = "scripts/test_pinned.py::test_one"
EXTENDED_SET = goal.protected_set(
    (READ_ONLY_FILE, READ_ONLY_DIRECTORY, READ_ONLY_GLOB, READ_ONLY_NODE)
)


@pytest.mark.parametrize(
    ("path", "protected"),
    [
        ("CLAUDE.md", True),  # a file
        ("scripts/CLAUDE.md", False),  # the root file only
        ("skills/step-loop/SKILL.md", True),  # a directory prefix
        ("rules/swe/coding-style.md", True),
        ("agents/sentinel.md", True),
        (".claude/settings.local.json", True),
        ("skillset/readme.md", False),  # a prefix is a directory, not a string prefix
        ("tests/acceptance/test_goal.py", True),  # an outer-loop prefix
        ("tests/e2e/drivers/driver.py", True),
        ("tests/test_unit.py", False),
        (OWN_FILE, False),
        ("scripts/test_goal_judgement.py", False),
    ],
)
def test_the_default_set_covers_files_directories_and_the_outer_loop(
    path: str, protected: bool
) -> None:
    assert goal.is_protected(path, DEFAULT_SET) is protected


@pytest.mark.parametrize(
    ("path", "protected"),
    [
        (READ_ONLY_FILE, True),  # a Read-only entry that is a file
        ("scripts/_step_loop_gate_extra.py", False),
        ("scripts/fixtures/data.json", True),  # one that is a directory
        ("scripts/fixtures", True),
        ("scripts/fixturesque.py", False),
        ("scripts/test_goal_scaffold.py", True),  # one that is a glob
        ("scripts/test_loop_gate.py", False),
        ("scripts/test_pinned.py", True),  # one that is a test node: its whole file
        ("scripts/test_pinned_other.py", False),
        (OWN_FILE, False),
    ],
)
def test_a_read_only_entry_extends_the_set(path: str, protected: bool) -> None:
    assert goal.is_protected(path, EXTENDED_SET) is protected


def test_a_read_only_entry_protects_nothing_outside_its_own_step() -> None:
    assert goal.is_protected(READ_ONLY_FILE, DEFAULT_SET) is False


def test_the_set_is_the_default_then_the_entries_each_once() -> None:
    entries = goal.protected_set((READ_ONLY_FILE, "skills/**", READ_ONLY_FILE))

    assert entries == (*goal.DEFAULT_PROTECTED, READ_ONLY_FILE)


def test_the_changed_paths_under_the_set_keep_their_order() -> None:
    changed = ("skills/a.md", OWN_FILE, "CLAUDE.md", PROTECTED_PATH, "docs/x.md")

    assert goal.changed_protected(changed, DEFAULT_SET) == (
        "skills/a.md",
        "CLAUDE.md",
        PROTECTED_PATH,
    )


def test_no_changed_path_under_the_set_is_an_empty_tuple() -> None:
    assert goal.changed_protected((OWN_FILE, "docs/x.md"), DEFAULT_SET) == ()


def test_a_protected_judgement_must_name_a_path() -> None:
    with pytest.raises(ValueError, match="at least|fewer"):
        Protected(())


# --- Purity ---

IMPURE_MODULES = {
    "os",
    "io",
    "subprocess",
    "pathlib",
    "shutil",
    "tempfile",
    "socket",
    "time",
    "datetime",
    "glob",
}


def test_the_module_imports_nothing_that_touches_a_file_a_repository_or_a_process() -> None:
    source = (SCRIPT_DIR / "_goal_record.py").read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import)\s+(\w+)", source, flags=re.MULTILINE))

    assert imported.isdisjoint(IMPURE_MODULES)


def test_the_same_evidence_always_gives_the_same_answer() -> None:
    assert goal.judge(evidence(RED_BREAK)) == goal.judge(evidence(RED_BREAK))
