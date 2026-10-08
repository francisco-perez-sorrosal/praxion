"""`goal` scaffolds a one-step goal plan every existing reader parses, or writes nothing.

From one command line the verb writes the task's plan (one implementer step whose files,
read-only paths, check, iteration budget and done-when come from the options), a progress
file with an empty progress record, a task brief whose one key signal is the goal, and
deny rules on the protected paths in the repository's local harness settings, keeping
whatever those settings already held. It refuses, writing nothing, what it cannot scaffold
safely: an existing plan, an ungrammatical check, a budget that is not a whole number of at
least one, no paths in scope, or a path in scope under a protected path.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.drivers.goal_loop import (
    CHECK_COMMAND,
    DEFAULT_PROTECTED,
    EXPECTS,
    GOAL_SENTENCE,
    GOAL_SLUG,
    OUTER_LOOP_TEST,
    PROTECTED_DOC,
    SETTINGS,
    WIDGET,
    brief_section_lines,
    build_checkout,
    check_field,
    checklist_lines,
    deny_rules,
    edit_rule_paths,
    goal_step_id,
    json_object,
    plan_field,
    progress_lines,
    scaffold,
    task_files,
)
from tests.acceptance.drivers.step_loop import assert_well_formed, reconciler_verdict, status

WRITTEN_FILES = ("IMPLEMENTATION_PLAN.md", "WIP.md", "TASK_BRIEF.md", "settings.local.json")
E2E_PATH = "tests/e2e/test_widget_journey.py"
EARLIER_SETTINGS = {
    "model": "sonnet",
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(./.env)"]},
}


def test_the_goal_verb_prints_one_object_naming_the_slug_and_every_file_it_wrote(tmp_path):
    task = build_checkout(tmp_path)

    result = scaffold(task, iterations=4)

    named = json.dumps(json_object(result))
    assert result.returncode == 0, result.stderr
    assert GOAL_SLUG in named
    assert {name: name in named for name in WRITTEN_FILES} == dict.fromkeys(WRITTEN_FILES, True)


def test_status_and_the_reconciler_read_the_scaffold_as_one_step_not_yet_complete(tmp_path):
    task = build_checkout(tmp_path)
    scaffold(task, iterations=4)

    report = status(task, as_json=True)
    step_id = goal_step_id(task)

    assert report.exit_code == 0, report.stdout + report.stderr
    assert report.json()["steps"][0]["verdict"] != "verified-complete"
    assert reconciler_verdict(task, step_id)["verdict"] != "verified-complete"


def test_the_goal_step_is_the_implementers_and_states_the_goal(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4)

    assert "implementer" in plan_field(task, "Assignee")
    assert GOAL_SENTENCE in task.plan_path.read_text(encoding="utf-8")


def test_the_goal_steps_files_are_the_paths_given(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4, paths=(WIDGET, "src/widget_helpers.py"))

    files = plan_field(task, "Files")
    assert WIDGET in files
    assert "src/widget_helpers.py" in files


def test_the_check_is_the_given_command_and_expectation_in_the_check_grammar(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4)

    assert check_field(task) == f"`{CHECK_COMMAND}` expects {EXPECTS}"


def test_the_iteration_field_is_the_given_budget(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4)

    assert plan_field(task, "Iterations") == "4"


def test_read_only_names_the_protected_paths_with_outer_loop_tests_first(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4, protect=(PROTECTED_DOC, E2E_PATH))

    read_only = plan_field(task, "Read-only")
    assert PROTECTED_DOC in read_only, read_only
    assert E2E_PATH in read_only, read_only
    assert read_only.index(E2E_PATH) < read_only.index(PROTECTED_DOC), read_only


def test_done_when_is_the_check_met_with_no_protected_path_changed(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4)

    done_when = plan_field(task, "Done when").lower()
    assert "protect" in done_when, done_when
    assert "check" in done_when or "pass=3" in done_when, done_when


def test_wip_holds_the_step_unticked_and_an_empty_progress_record(tmp_path):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4)

    lines = checklist_lines(task)
    assert len(lines) == 1, lines
    assert "- [ ]" in lines[0], lines
    assert progress_lines(task) == []


def test_the_brief_has_the_goal_as_its_one_key_signal_and_guards_the_protected_paths(tmp_path):
    task = build_checkout(tmp_path)
    scaffold(task, iterations=4)

    signals = brief_section_lines(task, r"key signals")
    guards = "\n".join(brief_section_lines(task, r"health guards"))
    assert len(signals) == 1, signals
    assert GOAL_SENTENCE in signals[0], signals
    assert PROTECTED_DOC in guards, guards
    assert "tests/acceptance" in guards, guards


@pytest.mark.parametrize("protected", [*DEFAULT_PROTECTED, PROTECTED_DOC])
def test_the_scaffold_denies_edits_under_each_protected_path_at_the_harness(tmp_path, protected):
    task = build_checkout(tmp_path)

    scaffold(task, iterations=4)

    assert protected in edit_rule_paths(deny_rules(task.root)), deny_rules(task.root)


def test_the_scaffold_keeps_every_setting_the_local_settings_already_held(tmp_path):
    task = build_checkout(tmp_path)
    (task.root / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    (task.root / SETTINGS).write_text(json.dumps(EARLIER_SETTINGS), encoding="utf-8")

    result = scaffold(task, iterations=4)

    settings = json.loads((task.root / SETTINGS).read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/acceptance" in edit_rule_paths(settings["permissions"]["deny"])
    assert settings["model"] == "sonnet"
    assert settings["permissions"]["allow"] == ["Bash(ls:*)"]
    assert "Read(./.env)" in settings["permissions"]["deny"]


def test_a_second_goal_in_the_same_repository_adds_no_deny_rule_twice(tmp_path):
    task = build_checkout(tmp_path)
    scaffold(task, iterations=4)

    second = scaffold(task, slug="second-goal", iterations=4)

    rules = deny_rules(task.root)
    assert second.returncode == 0, second.stdout + second.stderr
    assert len(rules) == len(set(rules)), rules


def test_a_task_that_already_has_a_plan_is_refused_and_nothing_is_written(tmp_path):
    task = build_checkout(tmp_path)
    scaffold(task, iterations=4)
    files_before = task_files(task)

    refused = assert_well_formed("goal", scaffold(task, iterations=7))

    assert refused.exit_code == 4
    assert "IMPLEMENTATION_PLAN.md" in refused.error["message"]
    assert task_files(task) == files_before


@pytest.mark.parametrize(
    ("options", "named"),
    [
        pytest.param({"expects": "passes three"}, "expect", id="ungrammatical-expectation"),
        pytest.param({"check": "pytest `tests`"}, "check", id="ungrammatical-command"),
        pytest.param({"iterations": "0"}, "iteration", id="zero-iterations"),
        pytest.param({"iterations": "two"}, "iteration", id="iterations-not-a-number"),
        pytest.param({"iterations": "1.5"}, "iteration", id="iterations-not-whole"),
        pytest.param({"paths": (), "iterations": "4"}, "path", id="no-paths"),
        pytest.param({"paths": (OUTER_LOOP_TEST,)}, "protect", id="path-under-a-default"),
        pytest.param({"paths": (PROTECTED_DOC,)}, "protect", id="path-given-to-protect"),
    ],
)
def test_an_unsafe_goal_is_refused_naming_what_and_nothing_is_written(tmp_path, options, named):
    task = build_checkout(tmp_path)
    files_before = task_files(task)

    refused = assert_well_formed("goal", scaffold(task, **{"iterations": 4, **options}))

    assert refused.exit_code == 4
    assert refused.outcome == "error"
    assert named in refused.error["message"].lower(), refused.error
    assert task_files(task) == files_before
