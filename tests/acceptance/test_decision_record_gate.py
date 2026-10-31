"""A decision record in a refused shape cannot land, through the hooks the plugin registers.

Every call is replayed through the registered PreToolUse commands the way the harness delivers
it (`decision_gate`), in a planted managed project on a branch other than `main`. A Write that
would create a misplaced, self-numbered, misnamed or uncategorised record, an Edit that would
remove or invalidate a record's `category`, a commit carrying such a record or a numbered record
the default branch does not hold, and a whole read of the decisions index are refused, each
naming the defect and the correct form and carrying the rule's own governing lines (still
refused when the rule cannot be read). Conforming work is allowed with no message, and a host
without the plugin's hooks writes and commits as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import adr_rule_move, decision_gate, decision_records
from tests.acceptance.drivers.decision_kit import CATEGORY_VALUES
from tests.acceptance.drivers.decision_records import (
    DECISIONS_DIR,
    DRAFTS_DIR,
    INDEX_FILE,
    conforming,
    fragment_name,
    leave,
    older_habit,
    with_changes,
)

NUMBERED = with_changes(older_habit(), category="behavioral")
REFUSED_WRITES = {
    "a numbered record": (NUMBERED, "placement"),
    "a fragment outside the drafts": (
        with_changes(conforming(), relpath=f"{DECISIONS_DIR}/{fragment_name()}"),
        "placement",
    ),
    "a record in another subdirectory": (
        with_changes(conforming(), relpath=f"{DECISIONS_DIR}/archive/{fragment_name()}"),
        "placement",
    ),
    "a draft with a malformed name": (
        with_changes(conforming(), relpath=f"{DRAFTS_DIR}/adopt-sqlite-for-the-cache.md"),
        "placement",
    ),
    "a draft whose name has no real date": (
        with_changes(conforming(), relpath=f"{DRAFTS_DIR}/{fragment_name(stamp='20261399-2599')}"),
        "placement",
    ),
    "a draft with a malformed id": (with_changes(conforming(), id="dec-draft-XYZ"), "placement"),
    "a draft with a self-picked number": (with_changes(conforming(), id="dec-043"), "placement"),
    "a record with no category": (
        with_changes(conforming("behavioral"), category=None),
        "category",
    ),
    "a record with an invalid category": (
        with_changes(conforming("behavioral"), category="strategic"),
        "category",
    ),
}
GOVERNING_PHRASES = {
    "placement": ("fragment", "drafts"),
    "category": ("what exists or what connects", "however consequential"),
}


@pytest.fixture
def project(tmp_path) -> Path:
    return decision_records.planted_project(tmp_path).project


def _rule_lines_carrying(phrase: str) -> set[str]:
    _, body = adr_rule_move.split_frontmatter(adr_rule_move.fixture_text("base_rule.md"))
    return {line.strip() for line in body.splitlines() if phrase in line}


def _carries_a_rule_line(message: str, phrase: str) -> bool:
    held = {line.strip() for line in message.splitlines()}
    return bool(_rule_lines_carrying(phrase) & held)


# -- Writes that do not land ----------------------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(REFUSED_WRITES))
def test_a_write_creating_a_refused_record_is_refused_naming_the_correct_form(project, shape):
    record, defect = REFUSED_WRITES[shape]

    verdict = decision_gate.write(project, record.relpath, record.text())

    assert verdict.refused, f"{shape} would land"
    assert (DRAFTS_DIR in verdict.message, "dec-draft-" in verdict.message) == (True, True)


@pytest.mark.parametrize(
    "shape", sorted(s for s, (_, d) in REFUSED_WRITES.items() if d == "category")
)
def test_a_category_refusal_names_the_four_values(project, shape):
    record, _ = REFUSED_WRITES[shape]

    verdict = decision_gate.write(project, record.relpath, record.text())

    assert [v for v in CATEGORY_VALUES if v not in verdict.message] == [], verdict.message


@pytest.mark.parametrize("new", ["", "category: strategic\n"])
def test_an_edit_removing_or_invalidating_a_records_category_is_refused(project, new):
    record = conforming("behavioral")
    leave(project, record)

    verdict = decision_gate.edit(project, record.relpath, "category: behavioral\n", new)

    assert verdict.refused, "the edit would leave the record without a valid category"
    assert [v for v in CATEGORY_VALUES if v not in verdict.message] == [], verdict.message


# -- A refusal carries the rule's own lines -------------------------------------------------------


@pytest.mark.parametrize(
    ("shape", "phrase"),
    [
        ("a numbered record", "fragment"),
        ("a numbered record", "drafts"),
        ("a record with no category", "what exists or what connects"),
        ("a record with no category", "however consequential"),
    ],
)
def test_a_refusal_carries_the_rules_own_line_holding_the_governed_phrase(project, shape, phrase):
    record, _ = REFUSED_WRITES[shape]

    verdict = decision_gate.write(project, record.relpath, record.text())

    assert _carries_a_rule_line(verdict.message, phrase), verdict.message


def test_the_same_write_is_refused_when_the_rule_cannot_be_read(project, tmp_path):
    plugin = decision_gate.plugin_copy(tmp_path / "plugin", without=(adr_rule_move.MOVED_RULE,))

    verdict = decision_gate.write(project, NUMBERED.relpath, NUMBERED.text(), plugin_root=plugin)

    assert verdict.refused, "the gate let the record through once the rule was unreadable"
    assert "dec-draft-" in verdict.message, verdict.message


# -- Conforming work lands with no message --------------------------------------------------------


@pytest.mark.parametrize(
    ("relpath", "content"),
    [
        (conforming("architectural").relpath, conforming("architectural").text()),
        (conforming("behavioral").relpath, conforming("behavioral").text()),
        (INDEX_FILE, "# Decisions\n\n| id | title |\n|---|---|\n"),
        (f"{DECISIONS_DIR}/CLAUDE.md", "# Decision records\n\nDrafts live under drafts/.\n"),
        (f"{DRAFTS_DIR}/CLAUDE.md", "# Drafts\n\nOne fragment per decision.\n"),
        ("src/cache.py", "CACHE_FILE = 'cache.sqlite'\n"),
    ],
    ids=[
        "architectural draft",
        "behavioral draft",
        "index",
        "directory guide",
        "drafts guide",
        "code",
    ],
)
def test_a_conforming_write_lands_with_no_message(project, relpath, content):
    verdict = decision_gate.write(project, relpath, content)

    assert (verdict.refused, verdict.said) == (False, "")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("status: accepted", "status: superseded"),
        ("We chose the simpler path.", "We chose SQLite."),
    ],
)
def test_an_edit_of_an_older_record_lacking_a_category_lands_with_no_message(project, old, new):
    relpath = f"{DECISIONS_DIR}/041-keep-orders-in-postgres.md"

    verdict = decision_gate.edit(project, relpath, old, new)

    assert (verdict.refused, verdict.said) == (False, "")


def test_an_edit_of_a_numbered_record_that_keeps_its_category_lands_with_no_message(project):
    leave(project, NUMBERED)

    verdict = decision_gate.edit(project, NUMBERED.relpath, "status: proposed", "status: accepted")

    assert (verdict.refused, verdict.said) == (False, "")


# -- Commits --------------------------------------------------------------------------------------


def test_a_commit_on_a_feature_branch_adding_a_numbered_record_is_refused_naming_it(project):
    leave(project, NUMBERED)
    decision_gate.stage(project, NUMBERED.relpath)

    verdict = decision_gate.commit(project)

    assert verdict.refused, "the numbered record would be committed on a feature branch"
    assert NUMBERED.relpath in verdict.message, verdict.message


def test_a_commit_carrying_records_a_shell_wrote_names_each_offending_path(project):
    uncategorised = with_changes(conforming("behavioral"), category=None)
    leave(project, NUMBERED, uncategorised)
    decision_gate.stage(project, NUMBERED.relpath, uncategorised.relpath)

    verdict = decision_gate.commit(project)

    assert verdict.refused
    assert [p for p in (NUMBERED.relpath, uncategorised.relpath) if p not in verdict.message] == []


def test_a_commit_of_a_conforming_draft_on_a_feature_branch_is_allowed(project):
    leave(project, conforming())
    decision_gate.stage(project, conforming().relpath)

    assert decision_gate.commit(project).refused is False


def test_a_commit_on_main_adding_a_promoted_numbered_record_is_allowed(project):
    decision_records.git(project, "checkout", "-q", decision_records.DEFAULT_BRANCH)
    leave(project, NUMBERED)
    decision_gate.stage(project, NUMBERED.relpath)

    assert decision_gate.commit(project).refused is False


def test_a_merge_bringing_in_a_numbered_record_main_holds_is_allowed(project):
    decision_records.git(project, "checkout", "-q", decision_records.DEFAULT_BRANCH)
    leave(project, NUMBERED)
    decision_records.git(project, "add", "-A")
    decision_records.git(project, "commit", "-q", "-m", "Finalize the cache decision")
    decision_records.git(project, "checkout", "-q", decision_records.BRANCH)
    decision_records.git(
        project, "merge", "-q", "--no-ff", "--no-commit", decision_records.DEFAULT_BRANCH
    )

    assert decision_gate.commit(project, "Merge main").refused is False


# -- Without the plugin's hooks -------------------------------------------------------------------


def test_without_the_plugins_hooks_a_numbered_record_is_written_and_committed_as_before(project):
    leave(project, NUMBERED)
    decision_records.git(project, "add", "--", NUMBERED.relpath)

    decision_records.git(project, "commit", "-q", "-m", "Record the cache decision")

    assert (
        decision_records.git(project, "ls-files", "--", NUMBERED.relpath).strip()
        == NUMBERED.relpath
    )


# -- Reading the decisions index ------------------------------------------------------------------


def test_a_whole_read_of_the_decisions_index_is_refused_naming_the_bounded_alternatives(project):
    verdict = decision_gate.read(project, INDEX_FILE)

    assert verdict.refused, "the whole index would be read"
    assert ("query_adrs.py" in verdict.message, "grep" in verdict.message) == (True, True)


@pytest.mark.parametrize(
    ("relpath", "limit"),
    [
        (INDEX_FILE, 40),
        (f"{DECISIONS_DIR}/041-keep-orders-in-postgres.md", None),
        ("CLAUDE.md", None),
    ],
    ids=["bounded index read", "a record", "another file"],
)
def test_a_bounded_read_of_the_index_or_a_read_of_any_other_file_lands_with_no_message(
    project, relpath, limit
):
    verdict = decision_gate.read(project, relpath, limit=limit)

    assert (verdict.refused, verdict.said) == (False, "")
