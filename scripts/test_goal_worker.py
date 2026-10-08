"""Tests for the headless worker (``scripts/_goal_worker.py``).

A stand-in `claude` written into ``tmp_path`` and put first on ``PATH`` records how it was
started and prints what the test scripted. A real `claude` is never started.
"""

from __future__ import annotations

import _thread
import contextlib
import errno
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _goal_worker as worker_module  # noqa: E402
import step_loop  # noqa: E402
from _goal_run import writable_rules  # noqa: E402
from _goal_worker import (  # noqa: E402
    HeadlessWorker,
    resolver_invocation,
    shell_rule,
    terminal_marker,
)
from _step_loop_files import WorkerEnd, read_worker_end  # noqa: E402
from _step_loop_io import KILL_GRACE_SECONDS, kill_group  # noqa: E402

REQUEST_ID = "s1-a1-implement"
PROMPT = f"Task slug: demo\nSpawn request: {REQUEST_ID}\nRead the files, then stop."
MODEL = "sonnet"
SESSION = "11111111-2222-3333-4444-555555555555"
PYTHON = sys.executable
CHECK = f"{PYTHON} -m pytest tests/test_widget.py -q -p no:cacheprovider"
RESOLVER = "python3 scripts/resolve_test_scope.py"
CONFIG_VARIABLE, CONFIG_VALUE = "CLAUDE_CONFIG_DIR", "/somewhere/config"
FORBIDDEN_OPTIONS = (
    "--resume",
    "-r",
    "--continue",
    "-c",
    "bypassPermissions",
    "--dangerously-skip-permissions",
    "--bare",
    "--agent",
)
READ_TOOLS = ["Read", "Glob", "Grep"]
SLUG = "demo"
WIDGET = "src/widget.py"

_STAND_IN = """#!{python}
import json, os, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
behaviour = json.load(open(os.path.join(here, "behaviour.json")))
call = {{
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "stdin": sys.stdin.read(),
    "config": os.environ.get("CLAUDE_CONFIG_DIR"),
}}
with open(os.path.join(here, "calls.jsonl"), "a") as log:
    log.write(json.dumps(call) + "\\n")
time.sleep(behaviour["sleep"])
sys.stdout.write(behaviour["stdout"])
sys.exit(behaviour["exit"])
"""


def result_object(**changes) -> dict:
    """A result object as the harness prints it, with `changes` applied."""
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 7,
        "session_id": SESSION,
        "total_cost_usd": 0.42,
        "permission_denials": [],
        "result": "Done.\n[COMPLETE]",
    }
    return {**base, **changes}


class Harness:
    """A scratch repository and task directory, and the stand-in `claude` on `PATH`."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.bin_dir = root / "bin"
        self.repo = root / "repo"
        self.task_dir = root / "task"
        for directory in (self.bin_dir, self.repo, self.task_dir):
            directory.mkdir()
        self.monkeypatch = monkeypatch
        monkeypatch.setenv("PATH", f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv(CONFIG_VARIABLE, CONFIG_VALUE)

    def script(self, stdout: str = "", *, code: int = 0, sleep: float = 0) -> None:
        behaviour = {"stdout": stdout, "exit": code, "sleep": sleep}
        (self.bin_dir / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
        program = self.bin_dir / "claude"
        program.write_text(_STAND_IN.format(python=PYTHON), encoding="utf-8")
        program.chmod(program.stat().st_mode | stat.S_IXUSR)

    def print_result(self, **changes) -> None:
        self.script(json.dumps(result_object(**changes)))

    def without_claude(self) -> None:
        self.monkeypatch.setenv("PATH", str(self.repo))

    def worker(self, **options) -> HeadlessWorker:
        return HeadlessWorker(self.repo, self.task_dir, CHECK, RESOLVER, **options)

    def spawn(self, *, reissued: bool = False, **options):
        return self.worker(**options).spawn(request(reissued=reissued))

    def calls(self) -> list[dict]:
        log = self.bin_dir / "calls.jsonl"
        return (
            [json.loads(line) for line in log.read_text("utf-8").splitlines()]
            if log.exists()
            else []
        )

    def only_call(self) -> dict:
        (call,) = self.calls()
        return call

    def worker_file(self) -> dict:
        path = self.task_dir / f"WORKER_{REQUEST_ID}.json"
        return json.loads(path.read_text(encoding="utf-8"))


def request(*, reissued: bool = False) -> dict:
    return {
        "id": REQUEST_ID,
        "reissued": reissued,
        "agent_call": {"model": MODEL, "prompt": PROMPT},
    }


def option_values(argv: list[str], name: str) -> list[str]:
    """The tokens after `name` up to the next option."""
    tail = argv[argv.index(name) + 1 :]
    stop = next((i for i, token in enumerate(tail) if token.startswith("-")), len(tail))
    return tail[:stop]


@pytest.fixture
def harness(tmp_path, monkeypatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


# --- How the process is started ---------------------------------------------------------


def test_one_process_starts_in_the_repository_root_with_input_closed_and_the_environment(harness):
    harness.print_result()

    harness.spawn()

    call = harness.only_call()
    assert Path(call["cwd"]).resolve() == harness.repo.resolve()
    assert call["stdin"] == ""
    assert call["config"] == CONFIG_VALUE


def test_the_prompt_is_passed_verbatim_after_the_print_flag(harness):
    harness.print_result()

    harness.spawn()

    argv = harness.only_call()["argv"]
    assert argv[:2] == ["-p", PROMPT]


@pytest.mark.parametrize(
    ("name", "values"),
    [
        ("--model", [MODEL]),
        ("--max-turns", ["40"]),
        ("--max-budget-usd", ["2.00"]),
        ("--permission-mode", ["dontAsk"]),
        ("--permission-prompts", ["none"]),
        ("--output-format", ["json"]),
    ],
)
def test_each_fixed_option_is_passed_with_its_value(harness, name, values):
    harness.print_result()

    harness.spawn()

    assert option_values(harness.only_call()["argv"], name) == values


def test_the_bounds_are_the_ones_the_worker_was_built_with(harness):
    harness.print_result()

    harness.spawn(max_turns=12, max_budget_usd=0.5)

    argv = harness.only_call()["argv"]
    assert option_values(argv, "--max-turns") == ["12"]
    assert option_values(argv, "--max-budget-usd") == ["0.50"]


@pytest.mark.parametrize("forbidden", FORBIDDEN_OPTIONS)
def test_no_forbidden_option_is_ever_passed(harness, forbidden):
    harness.print_result()

    harness.spawn()

    assert forbidden not in harness.only_call()["argv"]


def the_allow_list_for(harness, *files: str) -> list[str]:
    """Spawn a worker whose edits are those the goal grants for `files`; its allow-list."""
    task_dir = harness.repo / ".ai-work" / SLUG
    harness.print_result()
    harness.spawn(writable=writable_rules(files, harness.repo, task_dir))
    return option_values(harness.only_call()["argv"], "--allowedTools")


def test_the_allow_list_names_the_read_tools_the_files_the_check_and_the_resolver_only(harness):
    allowed = the_allow_list_for(harness, WIDGET)

    assert allowed == [
        *READ_TOOLS,
        f"Edit(/{WIDGET})",
        f"Edit(/.ai-work/{SLUG}/WIP.md)",
        f"Bash({CHECK}:*)",
        f"Bash({RESOLVER}:*)",
    ]


def test_a_directory_among_the_files_is_allowed_whole(harness):
    allowed = the_allow_list_for(harness, "pkg/")

    assert allowed[len(READ_TOOLS)] == "Edit(/pkg/**)"


def test_a_task_directory_outside_the_repository_is_allowed_by_its_absolute_path(harness):
    rules = writable_rules((WIDGET,), harness.repo, harness.task_dir)

    assert rules == (f"Edit(/{WIDGET})", f"Edit(/{harness.task_dir.resolve()}/WIP.md)")


def test_a_worker_with_nothing_writable_is_read_only(harness):
    harness.print_result()

    harness.spawn()

    allowed = option_values(harness.only_call()["argv"], "--allowedTools")
    assert allowed == [*READ_TOOLS, f"Bash({CHECK}:*)", f"Bash({RESOLVER}:*)"]


def test_no_server_of_the_persons_own_reaches_the_worker(harness):
    harness.print_result()

    harness.spawn()

    assert "--strict-mcp-config" in harness.only_call()["argv"]


def test_a_parenthesised_check_is_allowed_up_to_its_pytest_token():
    check = f"{PYTHON} -m pytest tests -k '(slow or fast)' -q"

    assert shell_rule(check) == f"Bash({PYTHON} -m pytest:*)"


def test_a_parenthesised_check_without_a_pytest_token_cannot_be_allowed():
    with pytest.raises(ValueError, match="parenthesis"):
        shell_rule("make (all)")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/usr/bin:/home/me/.local/bin", "python3 scripts/resolve_test_scope.py"),
        ("/checkout/scripts:/usr/bin", "resolve_test_scope.py"),
    ],
)
def test_the_resolver_is_named_as_the_caller_can_run_it(path, expected):
    assert resolver_invocation("/checkout/scripts/step_loop.py", path) == expected


# --- Reading the result -------------------------------------------------------------------


@pytest.mark.parametrize("marker", ["complete", "blocked", "conflict", "partial"])
def test_each_terminal_marker_on_the_last_line_is_read(harness, marker):
    harness.print_result(result=f"Work done.\n[{marker.upper()}]\n")

    returned = harness.spawn()

    assert returned == step_loop.AgentRan(SESSION, marker)


@pytest.mark.parametrize(
    "final_text",
    ["[COMPLETE]\nbut then more words", "no marker at all", "[DONE]", "", None, ["a list"]],
)
def test_a_final_text_without_a_marker_on_its_last_line_reads_as_none(final_text):
    assert terminal_marker(final_text) == "none"


def test_a_result_object_without_result_text_is_recorded_with_marker_none(harness):
    document = result_object()
    del document["result"]
    harness.script(json.dumps(document))

    assert harness.spawn() == step_loop.AgentRan(SESSION, "none")


def test_a_worker_stopped_at_its_turn_bound_carries_its_subtype_in_the_file(harness):
    document = result_object(subtype="error_max_turns", is_error=True)
    del document["result"]
    harness.script(json.dumps(document), code=1)

    returned = harness.spawn()

    assert returned == step_loop.AgentRan(SESSION, "none")
    ended = read_worker_end(harness.task_dir, REQUEST_ID)
    assert isinstance(ended, WorkerEnd)
    assert (ended.subtype, ended.max_turns, ended.num_turns) == ("error_max_turns", 40, 7)


def test_the_worker_file_is_written_when_the_process_has_exited(harness):
    harness.print_result()

    harness.spawn(max_turns=9)

    document = harness.worker_file()
    assert document["exit"] == 0
    assert document["max_turns"] == 9
    assert document["max_budget_usd"] == 2.0
    assert document["argv"] == ["claude", *harness.only_call()["argv"]]
    assert document["result"]["session_id"] == SESSION
    assert document["stdout_tail"].endswith("}")


def test_the_returns_are_the_driver_modules_own_classes(harness):
    harness.print_result()

    returned = harness.spawn()

    assert isinstance(returned, step_loop.AgentRan)
    assert worker_module._return_types() == (step_loop.AgentRan, step_loop.NotStarted)


# --- A worker that cannot report --------------------------------------------------------


def test_no_claude_on_path_is_not_started_and_names_the_cause(harness):
    harness.without_claude()

    returned = harness.spawn()

    assert isinstance(returned, step_loop.NotStarted)
    assert "PATH" in returned.reason
    assert not list(harness.task_dir.iterdir())


def test_an_exit_with_no_result_object_is_not_started_and_leaves_a_null_result(harness):
    harness.script("the worker crashed before it could report", code=3)

    returned = harness.spawn()

    assert isinstance(returned, step_loop.NotStarted)
    assert "exited 3" in returned.reason
    document = harness.worker_file()
    assert document["result"] is None
    assert document["exit"] == 3


def test_a_result_object_without_a_session_id_counts_as_no_result_object(harness):
    harness.script(json.dumps({"type": "result", "subtype": "success"}))

    assert isinstance(harness.spawn(), step_loop.NotStarted)
    assert harness.worker_file()["result"] is None


def test_a_worker_past_its_wall_clock_bound_is_killed_and_has_no_result(harness):
    harness.script(json.dumps(result_object()), sleep=30)
    began = time.monotonic()

    returned = harness.spawn(timeout=0.5)

    assert time.monotonic() - began < 15
    assert isinstance(returned, step_loop.NotStarted)
    assert "stopped after 0.5 s" in returned.reason
    assert harness.worker_file()["result"] is None


# --- A request that comes again -----------------------------------------------------------


def test_a_reissued_request_with_a_worker_file_is_read_from_it_without_a_new_process(harness):
    harness.print_result(result="Done.\n[BLOCKED]")
    harness.spawn()

    again = harness.spawn(reissued=True)

    assert again == step_loop.AgentRan(SESSION, "blocked")
    assert len(harness.calls()) == 1


def test_a_reissued_request_whose_worker_left_no_result_is_not_started_again(harness):
    harness.script("garbage", code=1)
    harness.spawn()

    again = harness.spawn(reissued=True)

    assert isinstance(again, step_loop.NotStarted)
    assert len(harness.calls()) == 1


def test_a_reissued_request_without_a_worker_file_is_refused_not_started_blind(harness):
    harness.print_result()

    returned = harness.spawn(reissued=True)

    assert isinstance(returned, step_loop.NotStarted)
    assert "may have run" in returned.reason
    assert harness.calls() == []


# --- A worker's process: interrupt, bound, and a descendant holding the output ---------------

LINGERING_FILE = "lingering.json"
WORKER_PID_FILE = "worker.pid"
GRANDCHILD_PID_FILE = "grandchild.pid"
GRANDCHILD_SLEEP_SECONDS = 60
START_LIMIT_SECONDS = 20
POLL_SECONDS = 0.02
RESULT_BOUND_SECONDS = 3
PROMPT_RETURN_SECONDS = 10

_LINGERING_STAND_IN = """#!{python}
import json, os, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
behaviour = json.load(open(os.path.join(here, "lingering.json")))


def note(name, pid):
    path = os.path.join(here, name)
    with open(path + ".tmp", "w") as handle:
        handle.write(str(pid))
    os.replace(path + ".tmp", path)


note("worker.pid", os.getpid())
if behaviour["grandchild"]:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({sleep})"])
    note("grandchild.pid", child.pid)
sys.stdout.write(behaviour["stdout"])
sys.stdout.flush()
time.sleep(behaviour["linger"])
"""

needs_default_interrupt = pytest.mark.skipif(
    signal.getsignal(signal.SIGINT) is not signal.default_int_handler,
    reason="an ignored interrupt cannot be raised into the test",
)


def lingering_stand_in(
    harness: Harness, *, stdout: str = "", grandchild: bool = False, linger: float = 0
) -> None:
    """A `claude` that records its pid, optionally starts a long-lived background process that
    inherits its output, prints `stdout` and stays alive `linger` seconds."""
    behaviour = {"stdout": stdout, "grandchild": grandchild, "linger": linger}
    (harness.bin_dir / LINGERING_FILE).write_text(json.dumps(behaviour), encoding="utf-8")
    program = harness.bin_dir / "claude"
    source = _LINGERING_STAND_IN.format(python=PYTHON, sleep=GRANDCHILD_SLEEP_SECONDS)
    program.write_text(source, encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)


def recorded_pids(harness: Harness) -> list[int]:
    names = (WORKER_PID_FILE, GRANDCHILD_PID_FILE)
    files = [harness.bin_dir / name for name in names]
    return [int(file.read_text(encoding="utf-8")) for file in files if file.exists()]


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def all_gone_within_the_kill_grace(pids: list[int]) -> bool:
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while any(is_alive(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    return not any(is_alive(pid) for pid in pids)


def interrupt_once_started(harness: Harness) -> None:
    """Raise `KeyboardInterrupt` in the main thread once the stand-in has started its
    background process."""
    started = harness.bin_dir / GRANDCHILD_PID_FILE

    def wait_then_interrupt() -> None:
        deadline = time.monotonic() + START_LIMIT_SECONDS
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
        _thread.interrupt_main()

    threading.Thread(target=wait_then_interrupt, daemon=True).start()


@pytest.fixture
def stand_in_pids(harness):
    """Every process a stand-in started is killed when the test ends, whatever the outcome."""
    yield
    for pid in recorded_pids(harness):
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


@needs_default_interrupt
def test_an_interrupt_leaves_neither_the_worker_nor_its_background_process_alive(
    harness, stand_in_pids
):
    lingering_stand_in(harness, grandchild=True, linger=GRANDCHILD_SLEEP_SECONDS)
    interrupt_once_started(harness)

    with pytest.raises(KeyboardInterrupt):
        harness.spawn()

    pids = recorded_pids(harness)
    assert len(pids) == 2
    assert all_gone_within_the_kill_grace(pids)


@needs_default_interrupt
def test_an_interrupted_worker_leaves_no_worker_file(harness, stand_in_pids):
    lingering_stand_in(harness, grandchild=True, linger=GRANDCHILD_SLEEP_SECONDS)
    interrupt_once_started(harness)

    with pytest.raises(KeyboardInterrupt):
        harness.spawn()

    assert not list(harness.task_dir.iterdir())


def test_a_worker_that_exited_with_its_result_is_recorded_while_a_descendant_holds_the_output(
    harness, stand_in_pids
):
    lingering_stand_in(harness, stdout=json.dumps(result_object()), grandchild=True)
    began = time.monotonic()

    returned = harness.spawn(timeout=GRANDCHILD_SLEEP_SECONDS / 2)

    assert returned == step_loop.AgentRan(SESSION, "complete")
    assert time.monotonic() - began < PROMPT_RETURN_SECONDS


def test_a_worker_killed_at_its_bound_after_printing_a_result_is_recorded_with_it(
    harness, stand_in_pids
):
    lingering_stand_in(harness, stdout=json.dumps(result_object()), linger=30)

    returned = harness.spawn(timeout=RESULT_BOUND_SECONDS)

    assert returned == step_loop.AgentRan(SESSION, "complete")
    document = harness.worker_file()
    assert document["exit"] == -signal.SIGKILL
    assert document["result"]["session_id"] == SESSION


def test_a_worker_killed_at_its_bound_before_printing_any_result_is_not_started(
    harness, stand_in_pids
):
    lingering_stand_in(harness, linger=30)

    returned = harness.spawn(timeout=0.5)

    assert isinstance(returned, step_loop.NotStarted)
    assert "stopped after 0.5 s" in returned.reason
    assert harness.worker_file()["result"] is None


def test_killing_a_process_group_that_is_already_gone_raises_nothing():
    process = subprocess.Popen([PYTHON, "-c", "pass"], start_new_session=True)
    process.wait()

    kill_group(process)

    assert process.poll() == 0


def test_a_claude_that_cannot_be_executed_is_not_started_and_names_the_error(harness):
    program = harness.bin_dir / "claude"
    program.write_text("#!/bin/sh\n", encoding="utf-8")
    program.chmod(stat.S_IRUSR | stat.S_IWUSR)
    harness.monkeypatch.setenv("PATH", str(harness.bin_dir))

    returned = harness.spawn()

    assert isinstance(returned, step_loop.NotStarted)
    assert os.strerror(errno.EACCES) in returned.reason
    assert "To fix:" in returned.reason
    assert not list(harness.task_dir.iterdir())


def test_a_worker_that_printed_no_result_object_is_not_started_with_a_fix_sentence(harness):
    harness.script("the worker crashed before it could report", code=3)

    returned = harness.spawn()

    assert "To fix:" in returned.reason


def test_a_reissued_request_without_a_worker_file_is_refused_with_a_fix_sentence(harness):
    harness.print_result()

    returned = harness.spawn(reissued=True)

    assert "To fix:" in returned.reason
