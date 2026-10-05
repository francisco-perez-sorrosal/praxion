"""The loop gates each attempt on ground truth, never on what the agent says.

The loop runs the step's declared check and its derived test scope itself; the relayed
marker, the WIP.md checkbox and any result the agent wrote are recorded but never
decide. A failed gate commits nothing and leaves every file outside the step's declared
files as it was. Afterwards the reconciler's verdict agrees with the gate, and the
reconciler itself still runs no declared command.
"""

from __future__ import annotations

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    commits_after,
    head,
    ledger_records,
    reconciler_verdict,
    snapshot,
)

SHARED_MODULE = "src/shared.py"
SHARED_TEST = "tests/test_shared.py"
WORKING_SHARED_FILES = {
    SHARED_MODULE: "def shared():\n    return 1\n",
    SHARED_TEST: "from src.shared import shared\n\n\ndef test_shared_is_one():\n    assert shared() == 1\n",
}
BROKEN_SHARED_MODULE = "def shared():\n    return 2\n"
CHECK_RAN = "check-ran.flag"


def test_a_complete_marker_whose_check_fails_is_a_failed_attempt_and_commits_nothing(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    head_before = head(task)

    returned = attempt(task, Work(passes=False, final_marker="complete", claims_green=True))

    assert returned.recorded["gate"]["verdict"] != "verified-complete"
    assert returned.recorded["commit"] is None
    assert head(task) == head_before
    assert ledger_records(task)[0][-1]["commit"] is None


def test_an_attempt_whose_check_passes_verifies_even_when_the_agent_recorded_no_result(
    tmp_path,
):
    task = build_loop(tmp_path, Step("1"))

    returned = attempt(task, Work(claims_green=False))

    assert returned.recorded["gate"]["verdict"] == "verified-complete"
    assert returned.recorded["gate"]["decided_by"] == "check"
    assert returned.recorded["commit"] is not None


def test_an_attempt_with_no_marker_whose_check_passes_verifies_and_is_committed(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    returned = attempt(task, Work(final_marker="none", ticks_checkbox=False))

    assert returned.recorded["gate"]["verdict"] == "verified-complete"
    assert returned.recorded["commit"] is not None


def test_a_passing_check_does_not_verify_a_step_whose_derived_tests_fail(tmp_path):
    step = Step("1", more_files=(SHARED_MODULE,))
    task = build_loop(tmp_path, step, base_files=WORKING_SHARED_FILES)
    head_before = head(task)

    returned = attempt(task, Work(other_edits=((SHARED_MODULE, BROKEN_SHARED_MODULE),)))

    assert returned.recorded["gate"]["verdict"] != "verified-complete"
    assert returned.recorded["commit"] is None
    assert head(task) == head_before


def test_a_step_with_no_declared_check_verifies_on_its_changed_files_and_green_tests(tmp_path):
    task = build_loop(tmp_path, Step("1", declares_check=False))

    returned = attempt(task, Work())

    assert returned.recorded["gate"]["verdict"] == "verified-complete"
    assert returned.recorded["gate"]["decided_by"] == "fallback"
    assert returned.recorded["commit"] is not None


def test_a_step_with_no_declared_check_and_no_changed_files_does_not_verify(tmp_path):
    task = build_loop(tmp_path, Step("1", declares_check=False))

    returned = attempt(task, Work(touches_files=False, final_marker="complete"))

    assert returned.recorded["gate"]["verdict"] != "verified-complete"
    assert returned.recorded["commit"] is None


def test_a_failed_gate_leaves_every_file_outside_the_declared_files_as_it_was(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    (task.root / "README.md").write_text("# loop widget, edited by the user\n", encoding="utf-8")
    (task.root / "notes.txt").write_text("the user's own notes\n", encoding="utf-8")
    declared = set(task.step("1").files)
    before = {
        path: data
        for path, data in snapshot(task).items()
        if path not in declared and not path.startswith(".ai-work/")
    }

    attempt(task, Work(passes=False))

    after = snapshot(task)
    assert {path: after.get(path) for path in before} == before


def test_after_a_verified_attempt_the_reconciler_agrees_the_step_is_verified(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))

    attempt(task, Work(ticks_checkbox=True))

    assert reconciler_verdict(task, "1")["verdict"] == "verified-complete"


def test_after_a_failed_attempt_the_reconciler_does_not_read_the_step_as_verified(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))

    attempt(task, Work(passes=False, ticks_checkbox=True, claims_green=True))

    assert reconciler_verdict(task, "1")["verdict"] != "verified-complete"


def test_the_loop_runs_the_declared_check_and_the_reconciler_never_does(tmp_path):
    task = build_loop(tmp_path, Step("1", check_prefix=f"touch {CHECK_RAN} && "))
    attempt(task, Work())
    ran_during_gate = (task.root / CHECK_RAN).exists()
    (task.root / CHECK_RAN).unlink(missing_ok=True)

    reconciler_verdict(task, "1")

    assert ran_during_gate, "the loop gated the step without running its declared check"
    assert not (task.root / CHECK_RAN).exists(), "the reconciler ran the declared check"


def test_a_verified_attempt_is_the_only_new_commit_after_a_failed_one(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    head_before = head(task)
    attempt(task, Work(passes=False))

    attempt(task, Work())

    assert len(commits_after(task, head_before)) == 1
