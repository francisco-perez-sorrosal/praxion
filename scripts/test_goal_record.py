"""Tests for the goal recorder (``scripts/_goal_record.py``), through the real `record` verb.

Each test builds a scratch git checkout holding a hand-written goal plan (one implementer step
with `Files:`, `Read-only:`, `Check:` and `Iterations:`), a `WIP.md` with a progress record and a
baseline block in `TEST_RESULTS.md`. It asks the driver for a request with `next`, leaves what an
agent leaves behind (edits and a transcript, optionally a worker file) and runs `record`. What is
asserted is what the checkout, the ledger and the task directory hold afterwards.

The judgement alone is in ``scripts/test_goal_judgement.py``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# The checkout's root is found by climbing, not by one `..`: under the mutation sensor this file
# runs from a copy one directory deeper, and the transcript reader lives beside the hooks.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(p for p in SCRIPT_DIR.parents if (p / "hooks").is_dir())
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import step_loop  # noqa: E402
from _step_loop_files import write_gate_block, write_worker_end  # noqa: E402
from _step_loop_record import declared_max_turns  # noqa: E402

PYTHON = sys.executable
SLUG = "goal-task"
STEP_NUMBER = "1"
STEP_LABEL = "Step " + STEP_NUMBER
WIDGET = "src/widget.py"
WIDGET_TESTS = "tests/test_widget.py"
SHARED = "src/shared.py"
SHARED_TESTS = "tests/test_shared.py"
OUTER_LOOP_TEST = "tests/acceptance/test_contract.py"
PROTECTED_DOC = "docs/contract.md"
FUNCTIONS = (("one", 1), ("two", 2), ("three", 3))
CHECK_COMMAND = f"{PYTHON} -m pytest {WIDGET_TESTS} -q -p no:cacheprovider"
EXPECTS = "pass=3 fail=0"
PROGRESS_HEADING = "## Progress record"
PROGRESS_LINE = "- Implemented one more function; the rest remain; nothing surprising."
TRAILER = "Step-Loop-Request: "
CONFIG_ENV, END_WAIT_ENV = "CLAUDE_CONFIG_DIR", "PRAXION_STEP_LOOP_END_WAIT_SECONDS"
SANDBOX_PROJECT, SANDBOX_SESSION = "-sandbox", "session-goal-record"
AGENT = "a1b2c3d4e5f60718"
STRAY = ("README.md", "# widget, edited on the way\n")
EXIT_REFUSED, EXIT_STOP = 4, 2


# --- A scratch checkout holding a goal plan ----------------------------------------------------


@dataclass(frozen=True)
class Goal:
    root: Path
    base: str
    config: Path

    @property
    def task_dir(self) -> Path:
        return self.root / ".ai-work" / SLUG


def widget_source(implemented: tuple[str, ...]) -> str:
    bodies = [
        f"def {name}():\n    "
        + (f"return {value}" if name in implemented else "raise NotImplementedError")
        + "\n"
        for name, value in FUNCTIONS
    ]
    return "\n\n".join(bodies)


def widget_tests() -> str:
    names = ", ".join(name for name, _ in FUNCTIONS)
    tests = [f"def test_{n}():\n    assert {n}() == {v}\n" for n, v in FUNCTIONS]
    return f"from src.widget import {names}\n\n\n" + "\n\n".join(tests)


def plan_text() -> str:
    return (
        "# Plan: goal task\n\n## Goal\n\nMake every widget test pass.\n\n## Steps\n\n"
        f"### {STEP_LABEL}: Make every widget test pass\n\n"
        "**Assignee**: implementer\n"
        f"**Files**: `{WIDGET}`, `{SHARED}`\n"
        f"**Read-only**: `tests/acceptance`, `{PROTECTED_DOC}`\n"
        f"**Check**: `{CHECK_COMMAND}` expects {EXPECTS}\n"
        "**Iterations**: 5\n"
        "**Done when**: the check is met and no protected path changed.\n"
    )


def wip_text() -> str:
    return (
        "# WIP: goal task\n\n## Progress\n\n"
        f"- [ ] {STEP_LABEL}: Make every widget test pass\n\n{PROGRESS_HEADING}\n"
    )


def brief_text() -> str:
    return (
        "# Task Brief: goal task\n\n## Task Intent\n\nMake the widget tests pass.\n\n"
        "## Key Signals\n\n- [ ] The widget tests pass.\n\n"
        "## Health Guards\n\n- [ ] No protected path changes.\n\n## Uncertainty Flag\n\n8/10\n"
    )


def baseline_result(passing: int) -> str:
    """The scaffold's reading of a checkout with `passing` of the widget's tests passing."""
    return f"Result: pass={passing} fail=0 skip=0 pending={len(FUNCTIONS) - passing} by=step-loop"


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path):
    """The environment the verbs and the checks they run see: no inherited git variables or
    pytest options, the interpreter's own `bin/` first on `PATH`, no wait for an end."""
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.setenv("PATH", f"{Path(PYTHON).parent}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "home" / ".claude"))
    monkeypatch.setenv(END_WAIT_ENV, "0")


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=60
    )
    return done.stdout.strip()


def build_goal(tmp_path: Path, implemented: tuple[str, ...] = ()) -> Goal:
    """A checkout whose widget has `implemented` functions, with the goal plan beside it."""
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    for key, value in (
        ("user.name", "Goal Record"),
        ("user.email", "goal-record@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(root, "config", key, value)
    files = {
        ".gitignore": ".ai-work/\n__pycache__/\n.pytest_cache/\n",
        "README.md": "# widget\n",
        "pyproject.toml": '[project]\nname = "widget"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n',
        WIDGET: widget_source(implemented),
        WIDGET_TESTS: widget_tests(),
        SHARED: "def shared():\n    return 1\n",
        SHARED_TESTS: "from src.shared import shared\n\n\ndef test_shared():\n"
        "    assert shared() == 1\n",
        OUTER_LOOP_TEST: "def test_contract():\n    assert True\n",
        PROTECTED_DOC: "# Widget contract\n",
    }
    for rel, text in files.items():
        put(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    goal = Goal(root, git(root, "rev-parse", "HEAD"), tmp_path / "home" / ".claude")
    goal.task_dir.mkdir(parents=True)
    put(goal.task_dir, "IMPLEMENTATION_PLAN.md", plan_text())
    put(goal.task_dir, "WIP.md", wip_text())
    put(goal.task_dir, "TASK_BRIEF.md", brief_text())
    write_gate_block(
        goal.task_dir / "TEST_RESULTS.md",
        STEP_NUMBER,
        "baseline",
        [f"Command: `{CHECK_COMMAND}`", baseline_result(len(implemented))],
    )
    return goal


# --- Driving the verbs --------------------------------------------------------------------------


@dataclass(frozen=True)
class Reply:
    code: int
    doc: dict[str, Any]

    @property
    def recorded(self) -> dict[str, Any]:
        return self.doc["recorded"]

    @property
    def stop(self) -> dict[str, Any]:
        return self.doc["stop"]


def verb(goal: Goal, *args: str) -> Reply:
    """One call of the driver's entry point, in this process, against the scratch checkout."""
    location = ["--repo-root", str(goal.root), "--base-ref", goal.base]
    replied = step_loop.execute([*args, *location])
    return Reply(replied.exit, replied.doc)


def ask(goal: Goal) -> dict[str, Any]:
    """The request `next` issues (and writes ahead to `WIP.md`)."""
    reply = verb(goal, "next", SLUG)
    assert reply.doc["outcome"] == "spawn", reply.doc
    return reply.doc["request"]


@dataclass(frozen=True)
class Work:
    """What one iteration's agent does: the widget it leaves, whether it logs progress, the other
    files it touches and what its transcript shows."""

    implemented: tuple[str, ...] | None = ("one",)  # None leaves the widget as it is
    progress: bool = True
    edits: tuple[tuple[str, str], ...] = ()
    requests: int = 3
    ended_on_text: bool = True
    marker: str = "[PARTIAL]"


DEFAULT_WORK = Work()


def do_work(goal: Goal, work: Work) -> None:
    if work.implemented is not None:
        put(goal.root, WIDGET, widget_source(work.implemented))
    for rel, text in work.edits:
        put(goal.root, rel, text)
    if work.progress:
        wip = goal.task_dir / "WIP.md"
        wip.write_text(wip.read_text(encoding="utf-8") + PROGRESS_LINE + "\n", encoding="utf-8")


def transcript_lines(request: dict[str, Any], agent_id: str, work: Work) -> str:
    """An agent's own transcript: the prompt, tool requests, then (when it ended) a final text."""

    def entry(kind: str, request_id: str | None, block: Any) -> str:
        record: dict[str, Any] = {"type": kind, "agentId": agent_id, "isSidechain": True}
        record["message"] = {"role": kind, "content": block}
        record.update({} if request_id is None else {"requestId": request_id})
        return json.dumps(record)

    tool_requests = work.requests - 1 if work.ended_on_text else work.requests
    lines = [entry("user", None, request["agent_call"]["prompt"])]
    for n in range(tool_requests):
        blocks = [{"type": "text", "text": "Working."}, {"type": "tool_use", "name": "Bash"}]
        lines.append(entry("assistant", f"req_{n}", blocks))
        lines.append(entry("user", None, [{"type": "tool_result"}]))
    if work.ended_on_text:
        final = [{"type": "text", "text": f"Done for now. {work.marker}"}]
        lines.append(entry("assistant", f"req_{tool_requests}", final))
    return "\n".join(lines) + "\n"


def leave_transcript(goal: Goal, request: dict[str, Any], agent_id: str, work: Work) -> Path:
    path = goal.config / "projects" / SANDBOX_PROJECT / SANDBOX_SESSION / "subagents"
    path = path / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transcript_lines(request, agent_id, work), encoding="utf-8")
    return path


def record(goal: Goal, request: dict[str, Any], agent_id: str = AGENT, marker: str = "partial"):
    return verb(
        goal, "record", SLUG, "--request", request["id"], "--agent-id", agent_id, "--marker", marker
    )


def iterate(goal: Goal, work: Work = DEFAULT_WORK, agent_id: str = AGENT) -> tuple[dict, Reply]:
    """One full iteration by the relay: request, the agent's work, its transcript, `record`."""
    request = ask(goal)
    do_work(goal, work)
    leave_transcript(goal, request, agent_id, work)
    return request, record(goal, request, agent_id)


def head(goal: Goal) -> str:
    return git(goal.root, "rev-parse", "HEAD")


def files_in(goal: Goal, sha: str) -> set[str]:
    return set(git(goal.root, "show", "--name-only", "--format=", sha).split())


def ledger(goal: Goal) -> list[dict[str, Any]]:
    path = goal.task_dir / "ITERATION_LEDGER.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def patch_of(goal: Goal, request: dict[str, Any]) -> Path:
    return goal.task_dir / f"ITERATION_{request['id']}.patch"


def snapshot_of(goal: Goal, request: dict[str, Any]) -> Path:
    return goal.task_dir / f"TREE_SNAPSHOT_{request['id']}.patch"


def tree_text(goal: Goal, rel: str) -> str:
    return (goal.root / rel).read_text(encoding="utf-8")


# --- What is kept ---------------------------------------------------------------------------------


def test_a_progressing_iteration_is_committed_with_the_requests_trailer(tmp_path):
    goal = build_goal(tmp_path)

    request, reply = iterate(goal)

    sha = reply.recorded["commit"]
    assert sha == head(goal)
    assert f"{TRAILER}{request['id']}" in git(goal.root, "log", "-1", "--format=%B").splitlines()


def test_a_progressing_iterations_commit_holds_only_the_declared_files(tmp_path):
    goal = build_goal(tmp_path)

    _, reply = iterate(goal, Work(edits=(STRAY,)))

    assert files_in(goal, reply.recorded["commit"]) == {WIDGET}
    assert tree_text(goal, STRAY[0]) == STRAY[1]


def test_a_kept_iterations_ledger_record_carries_its_progress_count_and_no_cost(tmp_path):
    goal = build_goal(tmp_path)

    iterate(goal)

    kept = ledger(goal)[0]
    assert (kept["progress_lines"], "cost_usd" in kept, kept["turns"]) == (1, False, 3)


def test_an_iteration_that_meets_the_check_ticks_the_step_and_completes_the_goal(tmp_path):
    goal = build_goal(tmp_path, implemented=("one", "two"))

    _, reply = iterate(goal, Work(implemented=("one", "two", "three")))
    finished = verb(goal, "next", SLUG)

    assert reply.recorded["gate"]["verdict"] == "verified-complete"
    assert "- [x]" in (goal.task_dir / "WIP.md").read_text(encoding="utf-8")
    assert finished.doc["outcome"] == "complete"


def test_an_iteration_that_regresses_the_last_committed_reading_commits_nothing(tmp_path):
    goal = build_goal(tmp_path)
    iterate(goal, Work(implemented=("one", "two")))
    after_progress = head(goal)

    _, reply = iterate(goal, Work(implemented=("three",)))

    assert (reply.recorded["commit"], head(goal)) == (None, after_progress)


def test_an_iteration_after_a_kept_one_that_adds_no_progress_line_commits_nothing(tmp_path):
    goal = build_goal(tmp_path)
    iterate(goal, Work(implemented=("one",)))
    after_progress = head(goal)

    request, reply = iterate(goal, Work(implemented=("one", "two"), progress=False))

    assert (reply.recorded["commit"], head(goal)) == (None, after_progress)
    assert patch_of(goal, request).stat().st_size > 0
    assert "gained no line" in reply.recorded["gate"]["evidence"]


DISTURBING_HOOK = "#!/bin/sh\necho disturbed >> README.md\n"


def disturb_commits(goal: Goal) -> None:
    """Make every commit rewrite a file outside its paths, as a repository hook might."""
    hooks = goal.root.parent / "hooks"
    put(hooks, "pre-commit", DISTURBING_HOOK)
    (hooks / "pre-commit").chmod(0o755)
    git(goal.root, "config", "core.hooksPath", str(hooks))


def let_commits_be(goal: Goal) -> None:
    git(goal.root, "config", "core.hooksPath", "/dev/null")
    for snapshot in goal.task_dir.glob("TREE_SNAPSHOT_*.patch"):
        snapshot.unlink()


def test_a_kept_commit_whose_line_is_a_refusal_does_not_switch_the_regression_guard_off(
    tmp_path,
):
    goal = build_goal(tmp_path, implemented=("one", "two"))
    disturb_commits(goal)
    iterate(
        goal, Work(implemented=None, edits=((SHARED, "def shared():\n    return 1  # tidy\n"),))
    )
    let_commits_be(goal)
    after_disturbance = head(goal)

    request, reply = iterate(goal, Work(implemented=("one",)))

    assert (reply.recorded["commit"], head(goal)) == (None, after_disturbance)
    assert patch_of(goal, request).stat().st_size > 0
    assert "regressed" in reply.recorded["gate"]["evidence"]


# --- What is left as a patch ------------------------------------------------------------------

BROKEN_SHARED = "def shared():\n    return 2\n"
UNKEPT = [
    pytest.param(("one", "two"), Work(implemented=("one",)), "regressed", id="a-regression"),
    pytest.param(("one",), Work(implemented=None, edits=(STRAY,)), "no path", id="no-file"),
    pytest.param((), Work(progress=False), "gained no line", id="no-progress-line"),
    pytest.param((), Work(edits=((SHARED, BROKEN_SHARED),)), "fail=1", id="a-red-gate"),
]


@pytest.mark.parametrize(("at_base", "work", "said"), UNKEPT)
def test_an_iteration_not_kept_commits_nothing_keeps_a_patch_and_restores_its_scope(
    tmp_path, at_base, work, said
):
    goal = build_goal(tmp_path, implemented=at_base)
    before = head(goal)

    request, reply = iterate(goal, work)

    assert (reply.recorded["commit"], head(goal)) == (None, before)
    assert patch_of(goal, request).stat().st_size > 0
    assert (tree_text(goal, WIDGET), tree_text(goal, SHARED)) == (
        widget_source(at_base),
        "def shared():\n    return 1\n",
    )
    assert said in reply.recorded["gate"]["evidence"]


def test_the_patch_holds_the_whole_trees_diff_but_only_the_scope_is_restored(tmp_path):
    goal = build_goal(tmp_path)

    request, _ = iterate(goal, Work(progress=False, edits=(STRAY,)))

    patch = patch_of(goal, request).read_text(encoding="utf-8")
    assert ("return 1" in patch, STRAY[1].strip() in patch, tree_text(goal, STRAY[0])) == (
        True,
        True,
        STRAY[1],
    )


# --- What stops for a person ----------------------------------------------------------------------

PROTECTED = [
    pytest.param(OUTER_LOOP_TEST, "def test_contract():\n    pass\n", id="an-outer-loop-test"),
    pytest.param(PROTECTED_DOC, "# Rewritten\n", id="a-path-given-read-only"),
    pytest.param("rules/widget.md", "# A new rule\n", id="a-new-file-under-a-default"),
]


@pytest.mark.parametrize(("path", "text"), PROTECTED)
def test_a_change_under_a_protected_path_commits_nothing_and_restores_nothing(tmp_path, path, text):
    goal = build_goal(tmp_path)
    before = head(goal)

    request, reply = iterate(goal, Work(edits=((path, text),)))

    assert (reply.recorded["commit"], head(goal)) == (None, before)
    assert snapshot_of(goal, request).stat().st_size > 0
    assert (tree_text(goal, WIDGET), tree_text(goal, path)) == (widget_source(("one",)), text)


@pytest.mark.parametrize(("path", "text"), PROTECTED)
def test_a_change_under_a_protected_path_stops_the_loop_naming_the_path(tmp_path, path, text):
    goal = build_goal(tmp_path)
    iterate(goal, Work(edits=((path, text),)))

    stopped = verb(goal, "next", SLUG)

    assert (stopped.code, stopped.stop["cause"]) == (EXIT_STOP, "commit-disturbed-tree")
    assert path in json.dumps(stopped.stop["evidence"])


# --- A call run again ----------------------------------------------------------------------------

SETTLED = [
    pytest.param(DEFAULT_WORK, id="a-kept-iteration"),
    pytest.param(Work(progress=False), id="an-unkept-iteration"),
    pytest.param(Work(edits=((PROTECTED_DOC, "# Rewritten\n"),)), id="a-protected-change"),
]


def effects(goal: Goal, request: dict[str, Any]) -> tuple[str, ...]:
    """What the iteration left in the checkout and beside the plan, as text."""
    files = (patch_of(goal, request), snapshot_of(goal, request))
    kept = tuple(f.read_text(encoding="utf-8") if f.exists() else "" for f in files)
    return (head(goal), tree_text(goal, WIDGET), *kept)


def cut_off(goal: Goal, request: dict[str, Any]) -> None:
    """Return the task to the instant a `record` was cut off before its ledger line: the ledger
    is empty and the request is the one `WIP.md` still says is pending."""
    (goal.task_dir / "ITERATION_LEDGER.jsonl").write_text("", encoding="utf-8")
    wip = goal.task_dir / "WIP.md"
    pending = f"count={request['attempt']} request={request['id']}"
    wip.write_text(
        re.sub(r"count=\d+ request=\S+", pending, wip.read_text(encoding="utf-8")),
        encoding="utf-8",
    )


@pytest.mark.parametrize("work", SETTLED)
def test_a_replayed_record_appends_nothing_twice(tmp_path, work):
    goal = build_goal(tmp_path)
    request, first = iterate(goal, work)
    settled = effects(goal, request)

    again = record(goal, request)

    assert again.recorded["replayed"] is True
    assert (len(ledger(goal)), again.recorded["commit"], effects(goal, request)) == (
        1,
        first.recorded["commit"],
        settled,
    )


@pytest.mark.parametrize("work", SETTLED)
def test_a_record_cut_off_before_its_ledger_line_completes_without_repeating_its_effects(
    tmp_path, work
):
    goal = build_goal(tmp_path)
    request, first = iterate(goal, work)
    settled = effects(goal, request)
    cut_off(goal, request)

    again = record(goal, request)

    assert again.recorded["replayed"] is False
    assert (len(ledger(goal)), again.recorded["commit"], effects(goal, request)) == (
        1,
        first.recorded["commit"],
        settled,
    )


def test_a_record_cut_off_after_a_patch_restores_the_scope_again_and_keeps_the_first_patch(
    tmp_path,
):
    goal = build_goal(tmp_path)
    request, _ = iterate(goal, Work(progress=False))
    first_patch = patch_of(goal, request).read_text(encoding="utf-8")
    cut_off(goal, request)
    put(goal.root, WIDGET, "stray = 1\n")

    record(goal, request)

    assert (tree_text(goal, WIDGET), patch_of(goal, request).read_text(encoding="utf-8")) == (
        widget_source(()),
        first_patch,
    )


# --- The stall ------------------------------------------------------------------------------------


def test_two_iterations_in_a_row_that_commit_nothing_publish_a_stall_and_stop_the_loop(tmp_path):
    goal = build_goal(tmp_path)
    iterate(goal, Work(progress=False))
    iterate(goal, Work(progress=False))

    stopped = verb(goal, "next", SLUG)

    assert "[BLOCKED] replan:" in (goal.task_dir / "WIP.md").read_text(encoding="utf-8")
    assert (stopped.code, stopped.stop["cause"]) == (EXIT_STOP, "stalled")


# --- Worker files and session transcripts -------------------------------------------------------


def leave_worker(
    goal: Goal,
    request: dict[str, Any],
    *,
    subtype: str = "success",
    session: str = AGENT,
    max_turns: int = 40,
    cost: float = 0.31,
) -> None:
    """The file `run` leaves once the headless worker has exited."""
    result = {
        "session_id": session,
        "subtype": subtype,
        "is_error": subtype != "success",
        "num_turns": 3,
        "total_cost_usd": cost,
        "permission_denials": [],
    }
    write_worker_end(
        goal.task_dir,
        request["id"],
        argv=["claude"],
        exit_code=0,
        max_turns=max_turns,
        max_budget_usd=2.0,
        stdout_tail="",
        result=result,
    )


def leave_session_transcript(goal: Goal, request: dict[str, Any], session: str, work: Work) -> None:
    """A top-level session's transcript, where the harness writes one for a headless run."""
    folder = re.sub(r"[^A-Za-z0-9]", "-", str(goal.root.resolve()))
    path = goal.config / "projects" / folder / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transcript_lines(request, session, work), encoding="utf-8")


def worked(goal: Goal, work: Work = DEFAULT_WORK) -> dict[str, Any]:
    """A request issued, its work done and its transcript left; `record` not yet run."""
    request = ask(goal)
    do_work(goal, work)
    leave_transcript(goal, request, AGENT, work)
    return request


STILL_WORKING = Work(requests=2, ended_on_text=False)


def test_a_worker_file_with_the_turn_cap_error_records_turn_cap_and_is_never_awaited(tmp_path):
    goal = build_goal(tmp_path)
    request = worked(goal, STILL_WORKING)
    leave_worker(goal, request, subtype="error_max_turns", max_turns=40, cost=0.31)

    reply = record(goal, request)

    kept = ledger(goal)[0]
    assert reply.code == 0
    assert (kept["stop_reason"], kept["max_turns"], kept["cost_usd"]) == ("turn-cap", 40, 0.31)


def test_the_same_transcript_without_a_worker_file_is_still_running(tmp_path):
    goal = build_goal(tmp_path)
    request = worked(goal, STILL_WORKING)

    reply = record(goal, request)

    assert (reply.code, reply.doc["error"]["code"]) == (EXIT_REFUSED, "agent-running")


@pytest.mark.parametrize(
    ("subtype", "stop_reason"),
    [
        ("error_max_turns", "turn-cap"),
        ("error_max_budget_usd", "no-marker"),
        ("error_during_execution", "no-marker"),
    ],
)
def test_a_worker_that_ended_on_an_error_without_a_marker_stopped_for_that_error(
    tmp_path, subtype, stop_reason
):
    goal = build_goal(tmp_path)
    request = worked(goal, STILL_WORKING)
    leave_worker(goal, request, subtype=subtype)

    reply = record(goal, request, marker="none")

    assert reply.recorded["stop_reason"] == stop_reason


def test_a_worker_that_ended_on_a_marker_keeps_the_markers_stop_reason(tmp_path):
    goal = build_goal(tmp_path)
    request = worked(goal, Work(marker="[BLOCKED]"))
    leave_worker(goal, request, subtype="error_during_execution")

    reply = record(goal, request, marker="blocked")

    assert reply.recorded["stop_reason"] == "blocked"


def test_a_worker_file_for_another_session_is_refused_and_writes_nothing(tmp_path):
    goal = build_goal(tmp_path)
    request = worked(goal)
    leave_worker(goal, request, session="someone-elses-session")

    before = head(goal)

    reply = record(goal, request)

    assert (reply.code, reply.doc["error"]["code"]) == (EXIT_REFUSED, "agent-not-for-request")
    assert not (goal.task_dir / "ITERATION_LEDGER.jsonl").exists()
    assert (head(goal), tree_text(goal, WIDGET)) == (before, widget_source(("one",)))
    assert not patch_of(goal, request).exists()
    assert not snapshot_of(goal, request).exists()
    assert request["id"] not in (goal.task_dir / "TEST_RESULTS.md").read_text(encoding="utf-8")


def test_a_worker_file_that_shows_no_result_leaves_the_relays_evidence_to_decide(tmp_path):
    goal = build_goal(tmp_path)
    request = worked(goal)
    write_worker_end(
        goal.task_dir,
        request["id"],
        argv=["claude"],
        exit_code=1,
        max_turns=40,
        max_budget_usd=2.0,
        stdout_tail="boom",
        result=None,
    )

    reply = record(goal, request)

    assert ("cost_usd" in ledger(goal)[0], reply.recorded["stop_reason"]) == (False, "partial")


def test_a_worker_file_that_shows_no_result_still_means_the_process_has_exited(tmp_path):
    goal = build_goal(tmp_path)
    request = worked(goal, STILL_WORKING)
    write_worker_end(
        goal.task_dir,
        request["id"],
        argv=["claude"],
        exit_code=1,
        max_turns=40,
        max_budget_usd=2.0,
        stdout_tail="killed",
        result=None,
    )

    reply = record(goal, request)

    kept = ledger(goal)[0]
    declared = declared_max_turns(request["agent_call"]["subagent_type"])
    assert (reply.code, "cost_usd" in kept, kept["max_turns"]) == (0, False, declared)


def test_a_top_level_sessions_transcript_is_found_by_the_repository_root(tmp_path):
    goal = build_goal(tmp_path)
    request = ask(goal)
    do_work(goal, DEFAULT_WORK)
    leave_session_transcript(goal, request, AGENT, DEFAULT_WORK)
    leave_worker(goal, request)

    reply = record(goal, request)

    assert (reply.code, reply.recorded["turns"]) == (0, DEFAULT_WORK.requests)
