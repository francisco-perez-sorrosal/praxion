"""Canaries for the decision-record refusal text (`_decision_record_refusal.py`).

The pure composers are fed the live rule text, so a rule edit that moves a governing line out of
its heading fails here instead of silently quoting the wrong sentence; the synthetic rules prove
each degradation path (reworded heading, short section, over-long line, no rule at all).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _decision_record_refusal as refusal  # noqa: E402 -- after sys.path insertion
from _decision_record_refusal import (  # noqa: E402
    CORRECT_FORM,
    MAX_LISTED_PATHS,
    RULE_CHAR_CAP,
    commit_refusal_text,
    find_rule_text,
    refusal_text,
    rule_candidates,
)
from _decision_records import CATEGORIES, Allowed, Defect, Refused  # noqa: E402

LIVE_RULE = (_SCRIPT_DIR.parent / refusal.RULE_RELPATH).read_text(encoding="utf-8")
RULE_LINES = {line.strip() for line in LIVE_RULE.splitlines() if line.strip()}
RECORD_DEFECTS = [d for d in Defect if d is not Defect.UNBOUNDED_INDEX_READ]
DRAFT = ".ai-state/decisions/drafts/20261029-1430-fixture-person-adopt-sqlite.md"
NUMBERED = ".ai-state/decisions/043-adopt-sqlite.md"
FRAMING_MARKER = "From the ADR conventions rule:"


def refused(*defects: Defect, path: str = NUMBERED) -> Refused:
    return Refused(path, tuple(defects))


def quoted_lines(message: str) -> list[str]:
    return [line for line in message.splitlines() if line.strip() in RULE_LINES]


def synthetic_rule(**overrides: str) -> str:
    """A rule with every heading the refusal selects from; each section holds five lines."""
    headings = {
        "file": "### File Format",
        "schema": "#### Fragment Filename Schema",
        "finalized": "#### Finalized ADRs (post-merge)",
        "architectural": "#### What makes a decision `architectural`",
        "discovery": "### Discovery Protocol",
    }
    headings.update(overrides)
    return "\n".join(
        f"{heading}\n\nline-0 of {key}\n\nline-1 of {key}\n- line-2 of {key}\n"
        f"line-3 of {key}\nline-4 of {key}\n"
        for key, heading in headings.items()
    )


# -- Each family quotes the rule line carrying its governed phrase ----------------------------


@pytest.mark.parametrize(
    ("defect", "phrase"),
    [
        (Defect.SELF_NUMBERED, "fragment"),
        (Defect.SELF_NUMBERED, "drafts"),
        (Defect.MISPLACED, "drafts"),
        (Defect.NESTED, "fragment"),
        (Defect.MALFORMED_NAME, "fragment"),
        (Defect.MALFORMED_ID, "drafts"),
        (Defect.SELF_PICKED_ID, "drafts"),
        (Defect.NO_CATEGORY, "what exists or what connects"),
        (Defect.INVALID_CATEGORY, "however consequential"),
        (Defect.CATEGORY_LOST, "Falsifier"),
        (Defect.UNBOUNDED_INDEX_READ, "Retrieval-first"),
        (Defect.UNBOUNDED_INDEX_READ, "Pre-scan"),
    ],
)
def test_a_family_quotes_the_whole_rule_line_carrying_its_governed_phrase(defect, phrase):
    message = refusal_text(refused(defect), LIVE_RULE)

    carrying = {line for line in RULE_LINES if phrase in line}
    assert carrying & {line.strip() for line in message.splitlines()}, message


@pytest.mark.parametrize("defect", list(Defect))
def test_every_defect_has_a_description_and_rule_lines(defect):
    message = refusal_text(refused(defect), LIVE_RULE)

    assert FRAMING_MARKER in message
    assert quoted_lines(message), message


@pytest.mark.parametrize("defect", list(Defect))
def test_the_quoted_rule_lines_stay_within_the_budget(defect):
    message = refusal_text(refused(defect), LIVE_RULE)

    assert sum(len(line.strip()) for line in quoted_lines(message)) <= RULE_CHAR_CAP


def test_one_defect_family_is_quoted_per_refusal():
    category = refusal_text(refused(Defect.NO_CATEGORY), LIVE_RULE)
    placement = refusal_text(refused(Defect.MISPLACED), LIVE_RULE)

    assert not any("Falsifier" in line for line in quoted_lines(placement))
    assert not any("drafts/<YYYYMMDD" in line for line in quoted_lines(category))


def test_a_refusal_names_every_defect_but_quotes_the_first_ones_family():
    message = refusal_text(
        refused(Defect.MALFORMED_NAME, Defect.NO_CATEGORY, path=DRAFT), LIVE_RULE
    )

    head = message.splitlines()[0]
    assert DRAFT in head
    assert "fragment name" in head
    assert "no category" in head
    assert not any("Falsifier" in line for line in quoted_lines(message))


# -- The correct form is stated by every refusal ----------------------------------------------


@pytest.mark.parametrize("rule_text", [LIVE_RULE, None], ids=["rule read", "rule unreadable"])
@pytest.mark.parametrize("defect", RECORD_DEFECTS)
def test_a_record_refusal_states_the_correct_form(defect, rule_text):
    message = refusal_text(refused(defect), rule_text)

    wanted = [".ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md", "dec-draft-"]
    wanted += ["finalize at merge to main", *CATEGORIES]
    assert [w for w in wanted if w not in message] == [], message


def test_a_refused_read_states_the_exact_bounded_retry():
    message = refusal_text(refused(Defect.UNBOUNDED_INDEX_READ), LIVE_RULE)

    wanted = [
        "query_adrs.py --paths",
        "--grep",
        "grep -in",
        "offset",
        "limit",
        "loaded no path rule",
    ]
    assert [w for w in wanted if w not in message] == [], message


# -- Degradation: the message shrinks, the correct form stays ---------------------------------


@pytest.mark.parametrize(
    "rule_text",
    [
        None,
        "",
        LIVE_RULE.replace("#### Fragment Filename Schema", "#### Fragment Naming"),
        synthetic_rule(schema="#### Reworded"),
    ],
    ids=["unreadable", "empty", "reworded heading", "heading missing from a synthetic rule"],
)
def test_a_rule_that_cannot_supply_the_lines_falls_back_to_one_line(rule_text):
    message = refusal_text(refused(Defect.SELF_NUMBERED), rule_text)

    assert message.count("\n") == 0, message
    assert CORRECT_FORM in message
    assert FRAMING_MARKER not in message


def test_a_reworded_category_heading_falls_back_for_category_only():
    rule = LIVE_RULE.replace(
        "#### What makes a decision `architectural`", "#### Architectural test"
    )

    category = refusal_text(refused(Defect.NO_CATEGORY), rule)
    placement = refusal_text(refused(Defect.MISPLACED), rule)

    assert FRAMING_MARKER not in category
    assert FRAMING_MARKER in placement


def test_a_section_shorter_than_the_selected_ordinal_falls_back():
    rule = synthetic_rule()
    short = rule.replace("line-4 of architectural\n", "").replace("line-3 of architectural\n", "")

    assert FRAMING_MARKER in refusal_text(refused(Defect.NO_CATEGORY), rule)
    assert FRAMING_MARKER not in refusal_text(refused(Defect.NO_CATEGORY), short)


def test_a_first_line_over_the_budget_falls_back_instead_of_quoting_nothing():
    rule = synthetic_rule().replace("line-0 of schema", "x" * (RULE_CHAR_CAP + 1))

    assert FRAMING_MARKER not in refusal_text(refused(Defect.MALFORMED_ID), rule)


def test_lines_are_taken_in_priority_order_while_they_fit_the_budget():
    message = refusal_text(refused(Defect.MISPLACED), synthetic_rule())

    taken = [line for line in message.splitlines() if line.startswith("line-")]
    assert taken == ["line-0 of schema", "line-0 of file", "line-0 of finalized"]


def test_a_line_that_would_pass_the_budget_is_skipped_not_cut():
    long_line = "y" * (RULE_CHAR_CAP - 5)
    rule = synthetic_rule().replace("line-0 of file", long_line)

    message = refusal_text(refused(Defect.MISPLACED), rule)

    assert long_line not in message
    assert "line-0 of schema" in message
    assert "line-0 of finalized" in message


# -- The allow path emits nothing -------------------------------------------------------------


def test_an_allowed_verdict_emits_nothing():
    assert refusal_text(Allowed(), LIVE_RULE) == ""


def test_a_commit_with_no_refusals_emits_nothing():
    assert commit_refusal_text([], LIVE_RULE) == ""


# -- A commit refusal quotes the shared lines once and lists rows -----------------------------


def commit_refusals(count: int) -> list[Refused]:
    return [
        refused(Defect.SELF_NUMBERED, path=f".ai-state/decisions/{n:03d}-record.md")
        for n in range(count)
    ]


def test_a_commit_refusal_quotes_the_rule_lines_once_for_all_paths():
    message = commit_refusal_text(commit_refusals(3), LIVE_RULE)

    assert len(quoted_lines(message)) == len(set(quoted_lines(message))) >= 1
    assert message.count(FRAMING_MARKER) == 1


def test_a_commit_refusal_lists_each_path_with_its_defect():
    message = commit_refusal_text(commit_refusals(2), LIVE_RULE)

    assert ".ai-state/decisions/000-record.md - a numbered record" in message
    assert ".ai-state/decisions/001-record.md - a numbered record" in message


def test_a_commit_refusal_caps_the_list_at_eight_then_counts_the_rest():
    message = commit_refusal_text(commit_refusals(MAX_LISTED_PATHS + 4), LIVE_RULE)

    rows = [line for line in message.splitlines() if "-record.md - " in line]
    assert len(rows) == MAX_LISTED_PATHS
    assert "and 4 more" in message


def test_a_commit_refusal_at_the_cap_has_no_more_row():
    message = commit_refusal_text(commit_refusals(MAX_LISTED_PATHS), LIVE_RULE)

    assert " more" not in message


def test_a_commit_refusal_keeps_its_rows_and_form_when_the_rule_is_unreadable():
    message = commit_refusal_text(commit_refusals(2), None)

    assert FRAMING_MARKER not in message
    assert CORRECT_FORM in message
    assert message.count("-record.md - ") == 2


# -- The one effect: finding the rule ---------------------------------------------------------


def plant_rule(root: Path, text: str) -> None:
    target = root / refusal.RULE_RELPATH
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No plugin variable, a module two levels below an empty tree, an empty home."""
    monkeypatch.delenv(refusal.PLUGIN_ROOT_ENV, raising=False)
    monkeypatch.setattr(refusal, "__file__", str(tmp_path / "plugin" / "scripts" / "mod.py"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


def test_candidates_come_in_the_documented_order(tmp_path):
    found = rule_candidates("/plug", str(tmp_path / "scripts" / "mod.py"), Path("/home/u"))

    assert found == [
        Path("/plug") / refusal.RULE_RELPATH,
        tmp_path.resolve() / refusal.RULE_RELPATH,
        Path("/home/u/.claude") / refusal.RULE_RELPATH,
    ]


def test_candidates_skip_an_unset_plugin_root(tmp_path):
    found = rule_candidates(None, str(tmp_path / "scripts" / "mod.py"), Path("/home/u"))

    assert len(found) == 2


def test_the_plugin_root_is_read_first(isolated, monkeypatch):
    plant_rule(isolated / "given-root", "from the plugin root")
    plant_rule(isolated / "plugin", "from the module")
    monkeypatch.setenv(refusal.PLUGIN_ROOT_ENV, str(isolated / "given-root"))

    assert find_rule_text() == "from the plugin root"


def test_the_module_relative_rule_is_next(isolated):
    plant_rule(isolated / "plugin", "from the module")
    plant_rule(isolated / "home" / ".claude", "from home")

    assert find_rule_text() == "from the module"


def test_the_home_rule_is_the_last_resort(isolated):
    plant_rule(isolated / "home" / ".claude", "from home")

    assert find_rule_text() == "from home"


def test_no_readable_rule_gives_none(isolated):
    assert find_rule_text() is None


def test_an_unreadable_candidate_is_skipped(isolated, monkeypatch):
    broken = isolated / "given-root"
    (broken / refusal.RULE_RELPATH).mkdir(parents=True)
    plant_rule(isolated / "home" / ".claude", "from home")
    monkeypatch.setenv(refusal.PLUGIN_ROOT_ENV, str(broken))

    assert find_rule_text() == "from home"


def test_a_candidate_that_is_not_utf8_is_skipped(isolated, monkeypatch):
    bad = isolated / "given-root" / refusal.RULE_RELPATH
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff\xfe\x00bad")
    plant_rule(isolated / "home" / ".claude", "from home")
    monkeypatch.setenv(refusal.PLUGIN_ROOT_ENV, str(isolated / "given-root"))

    assert find_rule_text() == "from home"


def test_the_project_tree_is_never_searched(isolated, monkeypatch):
    project = isolated / "project"
    plant_rule(project, "the project's own copy")
    monkeypatch.chdir(project)

    assert find_rule_text() is None


def test_the_repo_ships_a_rule_where_the_module_looks():
    assert rule_candidates(None, refusal.__file__, Path("/nowhere"))[0].is_file()


# -- Purity: only find_rule_text touches the disk ---------------------------------------------

FILE_READERS = frozenset(
    {"read_text", "read_bytes", "open", "iterdir", "glob", "exists", "is_file"}
)


def test_no_function_reads_a_file_except_find_rule_text():
    tree = ast.parse(Path(refusal.__file__).read_text(encoding="utf-8"))
    offenders = []
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for call in (n for n in ast.walk(func) if isinstance(n, ast.Call)):
            name = getattr(call.func, "attr", getattr(call.func, "id", None))
            if name in FILE_READERS and func.name != "find_rule_text":
                offenders.append(f"{func.name} calls {name}")
    assert offenders == []
