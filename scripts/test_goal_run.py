"""Tests for the terminal form of the goal loop (``scripts/_goal_run.py`` and the `run` verb).

The pure parts (the iteration line, the options a printed command ends with) are called
directly. The rest runs the verb in a scratch git checkout holding a hand-written goal plan,
with a stand-in `claude` first on `PATH` that logs how it was started and either does one
scripted iteration or crashes. A real `claude` is never started.

The outer-loop scenarios for the same verb are ``tests/acceptance/test_goal_loop_runner.py``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _goal_run  # noqa: E402
import _goal_worker  # noqa: E402
import _step_loop_cli as cli  # noqa: E402
import step_loop  # noqa: E402
from _goal_record import protected_set  # noqa: E402
from _step_loop_files import WorkerEnd, write_gate_block  # noqa: E402

PYTHON = sys.executable
STEP_LOOP = SCRIPT_DIR / "step_loop.py"
SLUG = "goal-task"
STEP = "1"
STEP_LABEL = "Step " + STEP
WIDGET, WIDGET_TESTS = "src/widget.py", "tests/test_widget.py"
OUTER_LOOP_DIR, PROTECTED_DOC = "tests/acceptance", "docs/contract.md"
FUNCTIONS = (("one", 1), ("two", 2), ("three", 3))
CHECK_COMMAND = f"{PYTHON} -m pytest {WIDGET_TESTS} -q -p no:cacheprovider"
SETTINGS = ".claude/settings.local.json"
PROGRESS_LINE = "- Implemented two; one more function remains; nothing surprising."
REQUEST = "s1-a1-implement"
SESSION = "11111111-2222-3333-4444-555555555555"
SHA = "0123456789abcdef0123456789abcdef01234567"
COST, TURNS, DENIALS, SUBTYPE = 0.0731, 3, 2, "error_max_turns"
ITERATION_LINE = (
    rf"^step_loop: {REQUEST} committed [0-9a-f]{{7}} · {TURNS} turns · cost \${COST}"
    rf" · {DENIALS} permission denials · stopped at {SUBTYPE}$"
)


# --- The line each iteration prints -------------------------------------------------------


def recorded(commit: str | None = SHA, ledger: str | None = None, turns: int | None = 9) -> dict:
    return {"commit": commit, "turns": turns, "ledger": ledger, "gate": {"verdict": "unverified"}}


def ended(cost: float | None = 0.0731, denials: int = 0, subtype: str = "success") -> WorkerEnd:
    return WorkerEnd(SESSION, subtype, "text", cost, denials, 9, 40)


def test_a_committed_iteration_names_its_request_commit_turns_and_cost() -> None:
    line = _goal_run.iteration_line(REQUEST, recorded(), ended())

    assert line == f"step_loop: {REQUEST} committed {SHA[:7]} · 9 turns · cost $0.0731"


@pytest.mark.parametrize(
    ("ledger", "reason"),
    [
        pytest.param(
            "appended 1 attempt 1: unverified (check); not kept: the gate is red; the worker"
            " ended success",
            "the gate is red",
            id="the-judgements-words",
        ),
        pytest.param("appended 1 attempt 1: unverified (check)", "unverified", id="the-verdict"),
        pytest.param(None, "unverified", id="a-replay"),
    ],
)
def test_an_iteration_that_committed_nothing_says_why(ledger, reason) -> None:
    line = _goal_run.iteration_line(REQUEST, recorded(None, ledger), ended())

    assert f"no commit ({reason})" in line


@pytest.mark.parametrize(
    ("end", "tail"),
    [
        pytest.param(ended(denials=2), " · 2 permission denials", id="denials"),
        pytest.param(ended(subtype="error_max_turns"), " · stopped at error_max_turns", id="stop"),
        pytest.param(
            ended(denials=1, subtype="error_max_budget_usd"),
            " · 1 permission denials · stopped at error_max_budget_usd",
            id="both",
        ),
        pytest.param(ended(), "", id="neither"),
    ],
)
def test_denials_and_a_non_success_subtype_are_added_when_the_worker_reported_them(end, tail):
    line = _goal_run.iteration_line(REQUEST, recorded(), end)

    assert line.endswith(f"cost $0.0731{tail}")


@pytest.mark.parametrize(
    ("cost", "tail"),
    [(0.00001, "cost $0.00001"), (2.0, "cost $2.0"), (0.1142, "cost $0.1142"), (None, "cost n/a")],
)
def test_the_cost_is_the_reported_decimal_never_an_exponent(cost, tail) -> None:
    line = _goal_run.iteration_line(REQUEST, recorded(), ended(cost=cost))

    assert line.endswith(tail)


def test_turns_the_transcript_could_not_count_read_as_unknown() -> None:
    line = _goal_run.iteration_line(REQUEST, recorded(turns=None), ended())

    assert " · unknown turns · " in line


# --- The options every printed command ends with ----------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        pytest.param(
            Namespace(repo_root="/r", worktree_root=None),
            ("--repo-root", "/r", "--base-ref", "main"),
            id="repo-only",
        ),
        pytest.param(
            Namespace(repo_root="/r", worktree_root="/w"),
            ("--repo-root", "/r", "--base-ref", "main", "--worktree-root", "/w"),
            id="both-roots",
        ),
        pytest.param(
            Namespace(repo_root=None, worktree_root=None),
            ("--repo-root", "/found", "--base-ref", "main"),
            id="root-found",
        ),
    ],
)
def test_the_location_keeps_the_roots_as_given_and_the_base_it_read_against(given, expected):
    assert _goal_run.location(Path("/found"), "main", given) == expected


@pytest.mark.parametrize(
    ("doc", "code"),
    [
        ({"outcome": "complete"}, 0),
        ({"outcome": "needs-human"}, 2),
        ({"outcome": "budget-exhausted"}, 3),
        ({"outcome": "error", "error": {"code": "worker-not-started"}}, 4),
        ({"outcome": "error", "error": {"code": cli.INTERNAL}}, 1),
    ],
)
def test_every_way_a_run_ends_has_its_exit_code(doc, code) -> None:
    assert cli.exit_code(doc) == code


# --- The help text and the defaults it states ------------------------------------------


def help_text(*verb: str) -> str:
    done = subprocess.run(
        [PYTHON, str(STEP_LOOP), *verb, "--help"], capture_output=True, text=True, check=True
    )
    return " ".join(done.stdout.split())


def test_the_help_states_the_defaults_the_worker_module_uses() -> None:
    shown = help_text("run")

    assert f"default {_goal_worker.DEFAULT_MAX_TURNS})" in shown, shown
    assert f"default {_goal_worker.DEFAULT_MAX_BUDGET_USD:.2f})" in shown, shown
    assert cli.RUN_DEFAULT_MAX_TURNS == _goal_worker.DEFAULT_MAX_TURNS
    assert cli.RUN_DEFAULT_MAX_BUDGET_USD == _goal_worker.DEFAULT_MAX_BUDGET_USD


def test_the_command_help_names_five_verbs_and_how_they_end() -> None:
    shown = help_text()

    assert "exactly these five verbs" in shown, shown
    assert "step_loop.py run" in shown, shown
    assert "worker-not-started" in shown, shown


# --- A scratch checkout holding a goal plan and a stand-in `claude` ---------------------


@dataclass(frozen=True)
class Scratch:
    root: Path
    base: str
    bin_dir: Path

    @property
    def task_dir(self) -> Path:
        return self.root / ".ai-work" / SLUG

    def calls(self) -> list[dict[str, Any]]:
        log = self.bin_dir / "calls.jsonl"
        return (
            [json.loads(line) for line in log.read_text("utf-8").splitlines()]
            if log.exists()
            else []
        )

    def run(self, *extra: str, base_ref: bool = True) -> step_loop.Reply:
        location = ["--repo-root", str(self.root)]
        location += ["--base-ref", self.base] if base_ref else []
        return step_loop.execute(["run", SLUG, *location, *extra])


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=60
    )
    return done.stdout.strip()


def widget_source() -> str:
    """`one` is done; the others raise."""
    bodies = [
        f"def {name}():\n    "
        + (f"return {value}" if name == "one" else "raise NotImplementedError")
        for name, value in FUNCTIONS
    ]
    return "\n\n\n".join(bodies) + "\n"


def widget_tests() -> str:
    names = ", ".join(name for name, _ in FUNCTIONS)
    tests = [f"def test_{n}():\n    assert {n}() == {v}\n" for n, v in FUNCTIONS]
    return f"from src.widget import {names}\n\n\n" + "\n\n".join(tests)


def plan_text(iterations: int, check: str) -> str:
    return (
        "# Plan: goal task\n\n## Goal\n\nMake every widget test pass.\n\n## Steps\n\n"
        f"### {STEP_LABEL}: Make every widget test pass\n\n"
        "**Assignee**: implementer\n"
        f"**Files**: `{WIDGET}`\n"
        f"**Read-only**: `{OUTER_LOOP_DIR}`, `{PROTECTED_DOC}`\n"
        f"**Check**: `{check}` expects pass=3 fail=0\n"
        f"**Iterations**: {iterations}\n"
        "**Done when**: the check is met and no protected path changed.\n"
    )


def deny_rules(root: Path) -> list[str]:
    return [
        _goal_run.deny_rule(entry, root) for entry in protected_set((OUTER_LOOP_DIR, PROTECTED_DOC))
    ]


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path):
    """No inherited git variables or pytest options, the interpreter's `bin/` on `PATH`, a
    private config directory, and no wait for a transcript to flush."""
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.setenv("PATH", f"{Path(PYTHON).parent}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home" / ".claude"))
    monkeypatch.setenv("PRAXION_STEP_LOOP_END_WAIT_SECONDS", "0")


@pytest.fixture
def scratch(tmp_path) -> Scratch:
    return build_scratch(tmp_path, iterations=1)


def build_scratch(tmp_path: Path, iterations: int, check: str = CHECK_COMMAND) -> Scratch:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    for key, value in (
        ("user.name", "Goal Run"),
        ("user.email", "goal-run@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(root, "config", key, value)
    files = {
        ".gitignore": ".ai-work/\n__pycache__/\n.pytest_cache/\n.claude/\n",
        "pyproject.toml": '[project]\nname = "widget"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n',
        WIDGET: widget_source(),
        WIDGET_TESTS: widget_tests(),
        f"{OUTER_LOOP_DIR}/test_contract.py": "def test_contract():\n    assert True\n",
        PROTECTED_DOC: "# Widget contract\n",
    }
    for rel, text in files.items():
        put(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    task_dir = root / ".ai-work" / SLUG
    put(task_dir, "IMPLEMENTATION_PLAN.md", plan_text(iterations, check))
    put(
        task_dir, "WIP.md", f"# WIP\n\n## Progress\n\n- [ ] {STEP_LABEL}: x\n\n## Progress record\n"
    )
    baseline = [f"Command: `{check}`", "Result: pass=1 fail=0 skip=0 pending=2 by=step-loop"]
    write_gate_block(task_dir / "TEST_RESULTS.md", STEP, "baseline", baseline)
    put(root, SETTINGS, json.dumps({"permissions": {"deny": deny_rules(root)}}))
    return Scratch(root, git(root, "rev-parse", "HEAD"), tmp_path / "worker-bin")


STAND_IN = """#!{python}
import json, os, re, sys, uuid
from pathlib import Path

here = Path(__file__).resolve().parent
with (here / "calls.jsonl").open("a") as log:
    log.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd()}}) + "\\n")
if (here / "crash").exists():
    print("the worker crashed before it could report")
    sys.exit(1)
prompt = sys.argv[sys.argv.index("-p") + 1]
slug = re.search(r"^Task slug:\\s*(\\S+)", prompt, re.MULTILINE).group(1)
widget = Path("src/widget.py")
widget.write_text(widget.read_text().replace(
    "def two():\\n    raise NotImplementedError", "def two():\\n    return 2"))
wip = Path(".ai-work") / slug / "WIP.md"
wip.write_text(wip.read_text().rstrip("\\n") + "\\n{progress}\\n")
session, cwd = str(uuid.uuid4()), os.getcwd()
def entry(kind, **extra):
    return {{"type": kind, "sessionId": session, "cwd": cwd, "isSidechain": False, **extra}}
lines = [entry("user", message={{"role": "user", "content": prompt}})]
for n in range({turns}):
    for block in ({{"type": "text", "text": "Working."}}, {{"type": "tool_use", "name": "Bash"}}):
        message = {{"role": "assistant", "content": [block]}}
        lines.append(entry("assistant", requestId=f"req_{{n}}", message=message))
    if n < {turns} - 1:
        answer = {{"role": "user", "content": [{{"type": "tool_result"}}]}}
        lines.append(entry("user", message=answer))
final = {final_text}
if final:
    answer = {{"role": "user", "content": [{{"type": "tool_result"}}]}}
    closing = {{"role": "assistant", "content": [{{"type": "text", "text": final}}]}}
    lines.append(entry("user", message=answer))
    lines.append(entry("assistant", requestId="req_end", message=closing))
config = Path(os.environ["CLAUDE_CONFIG_DIR"])
transcript = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd) / (session + ".jsonl")
transcript.parent.mkdir(parents=True, exist_ok=True)
transcript.write_text("\\n".join(json.dumps(line) for line in lines) + "\\n")
denial = {{"tool_name": "Bash", "tool_use_id": "t", "tool_input": {{"command": "ls"}}}}
print(json.dumps({{
    "type": "result", "subtype": "{subtype}", "is_error": True, "num_turns": {turns},
    "session_id": session, "total_cost_usd": {cost}, "permission_denials": [denial] * {denials},
    **{result_field},
}}))
"""


def install_stand_in(
    scratch: Scratch, *, crashes: bool = False, subtype: str = SUBTYPE, result: str | None = None
) -> None:
    """Put a `claude` first on `PATH` that does one scripted iteration, or crashes. Its result
    object carries `result` as the worker's final text when one is given."""
    scratch.bin_dir.mkdir()
    program = scratch.bin_dir / "claude"
    program.write_text(
        STAND_IN.format(
            python=PYTHON,
            progress=PROGRESS_LINE,
            turns=TURNS,
            subtype=subtype,
            cost=COST,
            denials=DENIALS,
            result_field=repr({} if result is None else {"result": result}),
            final_text=repr(result or ""),
        ),
        encoding="utf-8",
    )
    program.chmod(0o755)
    if crashes:
        (scratch.bin_dir / "crash").touch()
    os.environ["PATH"] = f"{scratch.bin_dir}{os.pathsep}{os.environ['PATH']}"


def without_claude() -> None:
    entries = os.environ["PATH"].split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(e for e in entries if not (Path(e) / "claude").exists())


# --- What is refused before any worker starts --------------------------------------------


def set_settings(scratch: Scratch, content: str | None) -> None:
    """Replace the repository's local harness settings, or remove them."""
    path = scratch.root / SETTINGS
    path.unlink(missing_ok=True) if content is None else path.write_text(content, "utf-8")


@pytest.mark.parametrize(
    "content",
    [None, "{}", "not json", '{"permissions": {"deny": []}}', '{"permissions": []}'],
    ids=["absent", "empty", "unreadable", "no-rules", "wrong-shape"],
)
def test_a_protected_path_without_its_deny_rule_is_refused_before_any_worker(scratch, content):
    install_stand_in(scratch)
    set_settings(scratch, content)

    reply = scratch.run()

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "usage")
    assert "deny rule" in reply.doc["error"]["message"], reply.doc
    assert scratch.calls() == []


def test_one_missing_deny_rule_is_named_and_refused(scratch):
    install_stand_in(scratch)
    kept = [rule for rule in deny_rules(scratch.root) if PROTECTED_DOC not in rule]
    set_settings(scratch, json.dumps({"permissions": {"deny": kept}}))

    reply = scratch.run()

    assert reply.exit == 4
    assert PROTECTED_DOC in reply.doc["error"]["message"], reply.doc
    assert scratch.calls() == []


def test_a_plan_with_no_goal_step_is_refused_before_any_worker(scratch):
    install_stand_in(scratch)
    plan = scratch.task_dir / "IMPLEMENTATION_PLAN.md"
    plan.write_text(re.sub(r"\*\*Iterations\*\*: \d+\n", "", plan.read_text("utf-8")), "utf-8")

    reply = scratch.run()

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "usage")
    assert "no goal step" in reply.doc["error"]["message"], reply.doc
    assert scratch.calls() == []


def test_a_check_that_cannot_be_allow_listed_is_refused_before_any_worker(tmp_path):
    unlisted = build_scratch(tmp_path, iterations=1, check="(true)")
    install_stand_in(unlisted)

    reply = unlisted.run()

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "usage")
    assert "parenthesis" in reply.doc["error"]["message"], reply.doc
    assert unlisted.calls() == []


@pytest.mark.parametrize(
    "bound", [("--max-turns", "0"), ("--max-turns", "-3"), ("--max-budget-usd", "0")]
)
def test_a_bound_that_leaves_the_worker_nothing_is_refused_before_any_worker(scratch, bound):
    install_stand_in(scratch)

    reply = scratch.run(*bound)

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "usage")
    assert scratch.calls() == []


def test_a_task_that_does_not_exist_is_a_missing_artifact(scratch):
    reply = step_loop.execute(["run", "no-such-task", "--repo-root", str(scratch.root)])

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "missing-artifact")


# --- A worker that cannot start ends the run ---------------------------------------------


def test_with_no_claude_the_run_ends_with_exit_four_naming_the_cause(scratch, capsys):
    without_claude()

    reply = scratch.run()

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "worker-not-started")
    assert "no `claude` on PATH" in reply.doc["error"]["message"], reply.doc
    assert " turns" not in capsys.readouterr().err


def test_a_worker_that_crashes_is_not_an_iteration(scratch, capsys):
    install_stand_in(scratch, crashes=True)

    reply = scratch.run()

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "worker-not-started")
    assert "exited 1" in reply.doc["error"]["message"], reply.doc
    assert not (scratch.task_dir / "ITERATION_LEDGER.jsonl").exists()
    assert " turns" not in capsys.readouterr().err


# --- A worker that runs ------------------------------------------------------------------


def test_one_iteration_prints_its_line_with_the_denials_and_the_subtype(scratch, capsys):
    install_stand_in(scratch)

    reply = scratch.run("--max-turns", "12", "--max-budget-usd", "0.50")

    lines = [
        line for line in capsys.readouterr().err.splitlines() if line.startswith("step_loop: s")
    ]
    assert (reply.exit, reply.doc["outcome"]) == (3, "budget-exhausted")
    assert len(lines) == 1, lines
    assert re.fullmatch(ITERATION_LINE, lines[0]), lines[0]


def test_the_bounds_and_the_repository_root_reach_the_worker(scratch):
    install_stand_in(scratch)

    scratch.run("--max-turns", "12", "--max-budget-usd", "0.50")

    argv = scratch.calls()[0]["argv"]
    assert argv[argv.index("--max-turns") + 1] == "12"
    assert float(argv[argv.index("--max-budget-usd") + 1]) == 0.5
    assert scratch.calls()[0]["cwd"] == str(scratch.root.resolve())


def test_a_task_already_out_of_budget_starts_no_worker(scratch):
    install_stand_in(scratch)
    scratch.run()
    started = len(scratch.calls())

    again = scratch.run()

    assert (again.exit, again.doc["outcome"]) == (3, "budget-exhausted")
    assert len(scratch.calls()) == started == 1


def test_a_stop_resumes_with_the_base_it_resolved_when_none_was_given(scratch):
    install_stand_in(scratch)

    reply = scratch.run(base_ref=False)

    resume = reply.doc["stop"]["resume"]
    assert f"--repo-root {scratch.root}" in resume, resume
    assert re.search(r"--base-ref [0-9a-f]{40}\b", resume), resume


def test_a_stop_resumes_with_the_base_and_roots_it_was_given(scratch):
    install_stand_in(scratch)

    reply = scratch.run("--worktree-root", str(scratch.root))

    resume = reply.doc["stop"]["resume"]
    assert f"--base-ref {scratch.base}" in resume, resume
    assert f"--worktree-root {scratch.root}" in resume, resume


# --- The marker a worker's result text carries ---------------------------------------------


def ledger_stop_reasons(scratch: Scratch) -> list[str]:
    lines = (scratch.task_dir / "ITERATION_LEDGER.jsonl").read_text("utf-8").splitlines()
    return [json.loads(line)["stop_reason"] for line in lines]


@pytest.mark.parametrize(
    ("result", "stop_reason"),
    [(None, "no-marker"), ("Done.\n[COMPLETE]", "completed"), ("Stuck.\n[BLOCKED]", "blocked")],
    ids=["no-result-text", "complete", "blocked"],
)
def test_the_stop_reason_comes_from_the_workers_result_text(scratch, result, stop_reason):
    install_stand_in(scratch, subtype="success", result=result)

    scratch.run()

    assert ledger_stop_reasons(scratch) == [stop_reason]


# --- A request that comes again ------------------------------------------------------------

AGENT_CALL = {"model": "sonnet", "prompt": f"Task slug: {SLUG}\nImplement."}


def marked_worker(scratch: Scratch) -> _goal_run.MarkedWorker:
    inner = _goal_worker.HeadlessWorker(
        scratch.root, scratch.task_dir, CHECK_COMMAND, _goal_worker.RESOLVER_SCRIPT
    )
    return _goal_run.MarkedWorker(inner)


def spawn_request(*, reissued: bool) -> dict[str, Any]:
    return {"id": REQUEST, "reissued": reissued, "agent_call": AGENT_CALL}


def started_marker(scratch: Scratch) -> Path:
    return scratch.task_dir / f"WORKER_{REQUEST}{_goal_run.STARTED_SUFFIX}"


def test_a_request_only_previewed_has_no_marker_and_starts_fresh(scratch):
    install_stand_in(scratch)

    outcome = marked_worker(scratch).spawn(spawn_request(reissued=True))

    assert isinstance(outcome, step_loop.AgentRan)
    assert len(scratch.calls()) == 1


def test_a_request_with_a_marker_and_no_worker_file_may_have_run_and_is_refused(scratch):
    install_stand_in(scratch)
    started_marker(scratch).write_text("started\n", "utf-8")

    outcome = marked_worker(scratch).spawn(spawn_request(reissued=True))

    assert isinstance(outcome, step_loop.NotStarted)
    assert "may have run" in outcome.reason
    assert scratch.calls() == []


def test_a_request_with_a_worker_file_is_read_from_it_with_no_new_process(scratch):
    install_stand_in(scratch)
    worker = marked_worker(scratch)
    first = worker.spawn(spawn_request(reissued=False))

    again = worker.spawn(spawn_request(reissued=True))

    assert again == first
    assert len(scratch.calls()) == 1


def test_the_marker_is_written_before_the_process_is_launched(scratch):
    install_stand_in(scratch, crashes=True)

    marked_worker(scratch).spawn(spawn_request(reissued=False))

    assert started_marker(scratch).exists()


def test_a_worker_that_never_started_leaves_no_marker(scratch):
    without_claude()

    outcome = marked_worker(scratch).spawn(spawn_request(reissued=False))

    assert isinstance(outcome, step_loop.NotStarted)
    assert not started_marker(scratch).exists()
