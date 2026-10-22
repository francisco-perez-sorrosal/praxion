"""The gate decides on every pocket's counts, bounds each run, and keeps what it saw.

A pocket whose tests pass decides the step on its counts however long they take, within a
record call that a caller's ceiling may cut off and run again without repeating a pocket
run that already finished. Every pocket run still has a finite bound: a run that exceeds
it is cut off, the gate is red, and the block names the pocket that ran out, the bound,
every failure seen before the cut and the counts of every run that finished. The next
attempt's prompt carries that evidence from the driver's own record, cut to its size
bound with a pointer to the full record. A green block summarises each pocket run in
place of its command and stays within the shape checker's section ceiling.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.pocket_gate import gate_block, pocket_config, prompt_of
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    build_loop,
    commits_after,
    head,
    next_action,
    record,
    work_on,
)

SLOW_POCKET = "eval"
SLOW_TESTS = "eval/tests/test_slow_pocket.py"
BOUND_SECONDS = 7
HANGS = "def test_hangs_past_the_bound():\n    import time\n    time.sleep(600)\n"
TWO_FAILURES_THEN_A_HANG = (
    "def test_first_slow_failure():\n    assert 1 == 2\n\n\n"
    "def test_second_slow_failure():\n    assert 'a' == 'b'\n\n\n" + HANGS
)
THREE_FAILURES = (
    "test_first_slow_failure",
    "test_second_slow_failure",
    "test_value_is_the_step_id",
)


def _loop_with_slow_pocket(tmp_path, slow_tests_text):
    """A step whose derived scope spans the root pocket and the slow pocket's changed test."""
    step = Step("1", more_files=(SLOW_TESTS,))
    task = build_loop(
        tmp_path, step, base_files={f"{SLOW_POCKET}/pyproject.toml": pocket_config("evals")}
    )
    return task, Work(other_edits=((SLOW_TESTS, slow_tests_text),))


def _one_gate(task, work):
    asked = next_action(task)
    agent_id = work_on(task, asked.request, work)
    returned = record(task, asked.request["id"], agent_id=agent_id, marker=work.final_marker)
    return asked.request["id"], returned


# -- A cut-off run is red and keeps its evidence ----------------------------------------------


def test_a_pocket_run_past_its_bound_is_cut_off_and_the_gate_is_red(tmp_path):
    task, work = _loop_with_slow_pocket(tmp_path, HANGS)
    pocket_gate.bound_pocket_run(task, SLOW_POCKET, BOUND_SECONDS)
    head_before = head(task)

    request_id, returned = _one_gate(task, work)

    assert returned.recorded["gate"]["verdict"] != "verified-complete", returned.doc
    assert returned.recorded["commit"] is None
    assert head(task) == head_before
    block = gate_block(task, request_id)
    assert re.search(rf"\b{BOUND_SECONDS}(\.0+)?\s*(s|sec|seconds)\b", block), block


def test_a_cut_off_block_names_the_pocket_the_bound_and_every_failure_seen(tmp_path):
    task, work = _loop_with_slow_pocket(tmp_path, TWO_FAILURES_THEN_A_HANG)
    pocket_gate.bound_pocket_run(task, SLOW_POCKET, BOUND_SECONDS)

    request_id, _ = _one_gate(task, Work(passes=False, other_edits=work.other_edits))

    block = gate_block(task, request_id)
    assert SLOW_POCKET in block, block
    assert re.search(rf"\b{BOUND_SECONDS}(\.0+)?\s*(s|sec|seconds)\b", block), block
    missing = [failing for failing in THREE_FAILURES if failing not in block]
    assert missing == [], f"failures missing from the block:\n{block}"
    assert re.search(r"\bfail=1\b", block), f"the finished pocket's counts are missing:\n{block}"


def test_the_next_prompt_carries_the_cut_off_gates_failures_and_its_pocket(tmp_path):
    task, work = _loop_with_slow_pocket(tmp_path, TWO_FAILURES_THEN_A_HANG)
    pocket_gate.bound_pocket_run(task, SLOW_POCKET, BOUND_SECONDS)
    _one_gate(task, Work(passes=False, other_edits=work.other_edits))

    prompt = prompt_of(next_action(task))

    missing = [item for item in (*THREE_FAILURES, SLOW_POCKET) if item not in prompt]
    assert missing == [], f"evidence missing from the next prompt:\n{prompt}"


def test_the_next_prompt_names_the_failing_test_of_a_red_gate(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _one_gate(task, Work(passes=False))

    prompt = prompt_of(next_action(task))

    assert "test_value_is_the_step_id" in prompt, prompt


MANY_FAILURES = 150


def _many_failures() -> str:
    return "\n\n".join(
        f"def test_failure_{n:03d}_whose_name_is_long_enough_to_fill_a_bounded_prompt():\n"
        "    assert False\n"
        for n in range(MANY_FAILURES)
    )


def test_more_failures_than_the_prompt_holds_are_cut_with_a_pointer_to_the_full_record(
    tmp_path,
):
    step = Step("1", more_files=("tests/test_many_failures.py",))
    task = build_loop(tmp_path, step)
    _one_gate(task, Work(other_edits=(("tests/test_many_failures.py", _many_failures()),)))

    prompt = prompt_of(next_action(task))

    carried = re.findall(r"test_failure_\d{3}_", prompt)
    assert 0 < len(set(carried)) < MANY_FAILURES, f"{len(set(carried))} failures carried"
    assert "TEST_RESULTS.md" in prompt.split("<previous-attempts>", 1)[-1], prompt


# -- A record call cut off by its caller resumes -----------------------------------------------


def test_a_record_call_cut_off_and_run_again_never_repeats_a_finished_pocket_run(tmp_path):
    log, release = tmp_path / "pocket-runs.log", tmp_path / "release"
    root_test = "tests/test_root_pocket_meets.py"
    step = Step("1", more_files=(SLOW_TESTS, root_test))
    task = build_loop(
        tmp_path, step, base_files={f"{SLOW_POCKET}/pyproject.toml": pocket_config("evals")}
    )
    work = Work(
        other_edits=(
            (SLOW_TESTS, pocket_gate.meeting_test("eval", "root", log, release)),
            (root_test, pocket_gate.meeting_test("root", "eval", log, release)),
        )
    )
    asked = next_action(task)
    agent_id = work_on(task, asked.request, work)
    call = pocket_gate.start_record(task, asked.request["id"], agent_id)
    finished_first = pocket_gate.wait_for_lines(log, 2, deadline_seconds=300)[0]
    pocket_gate.cut_off(call)
    release.touch()
    base_commits = len(commits_after(task, task.base))

    returned = record(task, asked.request["id"], agent_id=agent_id, marker="complete")

    runs = log.read_text(encoding="utf-8").splitlines()
    assert runs.count(finished_first) == 1, f"the finished {finished_first} run repeated: {runs}"
    assert returned.recorded["gate"]["verdict"] == "verified-complete", returned.doc
    assert len(commits_after(task, task.base)) == base_commits + 1


# -- A green block summarises its selection --------------------------------------------------


SHARED = "src/shared.py"
ROOT_IMPORTERS = 101
EVAL_TESTS = 3


def _wide_green_scope(tmp_path):
    base = {SHARED: "def shared():\n    return 1\n", "eval/pyproject.toml": pocket_config("evals")}
    for n in range(ROOT_IMPORTERS):
        base[f"tests/test_importer_{n:03d}.py"] = (
            "from src.shared import shared\n\n\n"
            "def test_shared_is_one():\n    assert shared() == 1\n\n\n"
            "def test_shared_is_truthy():\n    assert shared()\n"
        )
    eval_tests = tuple(f"eval/tests/test_eval_{n}.py" for n in range(EVAL_TESTS))
    step = Step("1", more_files=(SHARED, *eval_tests))
    task = build_loop(tmp_path, step, base_files=base)
    edits = ((SHARED, "def shared():\n    return 1  # settled\n"),) + tuple(
        (path, "def test_one():\n    assert True\n\n\ndef test_two():\n    assert True\n")
        for path in eval_tests
    )
    return task, Work(other_edits=edits)


def test_a_green_block_for_a_wide_scope_stays_within_the_section_ceiling(tmp_path):
    task, work = _wide_green_scope(tmp_path)

    request_id, returned = _one_gate(task, work)

    assert returned.recorded["gate"]["verdict"] == "verified-complete", returned.doc
    block = gate_block(task, request_id)
    checked = pocket_gate.shape_check(tmp_path, block)
    assert checked.returncode == 0, f"{len(block.encode())} bytes:\n{checked.stdout}{block}"


def test_a_green_block_names_each_pocket_run_with_its_file_and_test_counts(tmp_path):
    task, work = _wide_green_scope(tmp_path)

    request_id, _ = _one_gate(task, work)

    block = gate_block(task, request_id)
    root_files, root_tests = ROOT_IMPORTERS + 1, 2 * ROOT_IMPORTERS + 1
    figures = (root_files, root_tests, EVAL_TESTS, 2 * EVAL_TESTS)
    missing = [n for n in figures if not re.search(rf"\b{n}\b", block)]
    assert missing == [], f"counts {missing} are not in the block:\n{block}"
    assert SLOW_POCKET in block, block
    assert "narrow" in block.lower(), block


def test_a_green_block_says_when_a_pocket_run_was_widened(tmp_path):
    unmapped = "config/settings.ini"
    task = build_loop(tmp_path, Step("1", more_files=(unmapped,)))

    request_id, returned = _one_gate(task, Work(other_edits=((unmapped, "[app]\nmode = 1\n"),)))

    assert returned.recorded["gate"]["verdict"] == "verified-complete", returned.doc
    assert "widened" in gate_block(task, request_id).lower()
