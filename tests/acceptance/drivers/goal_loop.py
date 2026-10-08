"""Driver for the step-loop driver's goal mode, reached only through its command line.

A scenario names what varies: the goal's iteration budget, which widget functions the
checkout already implements, what each iteration's worker does to the tree (which
functions it implements, whether it appends a progress line, what else it edits, the
marker it ends on) and, for a headless worker, what its result object reports. This
driver builds everything else: a git checkout with a pytest project whose goal is to make
`tests/test_widget.py` pass, a goal plan scaffolded through `step_loop.py goal`, and the
two ways an iteration's worker is started:

- through the relay (`next`, the Agent tool's double, `record`), reusing the ordinary
  driver's subagent-transcript double from `tests/acceptance/drivers/step_loop.py`;
- through `step_loop.py run`, which starts `claude` from `PATH`. A substitute program
  named `claude` (installed by `install_worker`) stands in for the harness. Its contract:
  it records how it was started (argument vector, working directory, standard input),
  does the scripted iteration's edits in its working directory, writes a top-level
  session transcript at `<config>/projects/<project>/<session id>.jsonl` (`<config>` is
  `CLAUDE_CONFIG_DIR`, else `~/.claude`; `<project>` is its working directory with every
  character that is not a letter or a digit replaced by `-`), opened by a user record
  whose text is the prompt, with `requestId` on every assistant record, and prints one
  JSON result object on standard output (`session_id`, `subtype`, `is_error`,
  `num_turns`, `result`, `total_cost_usd`, `permission_denials`).

The checkout, the envelope reader, the ledger and reconciler readers and the git readers
come from the ordinary driver unchanged.
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

from tests.acceptance.drivers.shipped_texts import section
from tests.acceptance.drivers.step_loop import (
    CONFIG_DIR_VARIABLE,
    END_WAIT_VARIABLE,
    MARKER_TEXT,
    PYTHON,
    STEP_LOOP,
    Envelope,
    LoopTask,
    git,
    leave_agent_transcript,
    new_agent_id,
    next_action,
    record,
    status,
    step_id_of,
)

GOAL_SLUG = "goal-task"
GOAL_SENTENCE = "Make every widget test pass (goal sentence 17)."
WIDGET = "src/widget.py"
WIDGET_TESTS = "tests/test_widget.py"
FUNCTIONS = (("one", 1), ("two", 2), ("three", 3))
ALL_FUNCTIONS = tuple(name for name, _ in FUNCTIONS)
CHECK_COMMAND = f"{PYTHON} -m pytest {WIDGET_TESTS} -q -p no:cacheprovider"
EXPECTS = "pass=3 fail=0"
DEFAULT_BUDGET = 5

# A protected path by default (an outer-loop test) and one a scenario protects by name.
OUTER_LOOP_TEST = "tests/acceptance/test_widget_contract.py"
PROTECTED_DOC = "docs/contract.md"
DEFAULT_PROTECTED = (
    "tests/acceptance",
    "tests/e2e",
    "CLAUDE.md",
    "rules",
    "agents",
    "skills",
    ".claude",
)

# A module outside the goal whose own test passes at the base.
SHARED_MODULE = "src/shared.py"
SHARED_TEST = "tests/test_shared.py"
SHARED_FILES = {
    SHARED_MODULE: "def shared():\n    return 1\n",
    SHARED_TEST: "from src.shared import shared\n\n\ndef test_shared_is_one():\n"
    "    assert shared() == 1\n",
}
BROKEN_SHARED = "def shared():\n    return 2\n"

PROGRESS_HEADING = "## Progress record"
PROGRESS_LINE = "- Implemented one more widget function; the rest remain; nothing surprising."
SETTINGS = ".claude/settings.local.json"
STEP_LOOP_REQUEST_TRAILER = "Step-Loop-Request:"

_COMMAND_TIMEOUT = 900


# -- The checkout and the goal plan ----------------------------------------------------


def widget_source(implemented: tuple[str, ...], note: str = "") -> str:
    """`src/widget.py` with the named functions implemented and the rest still raising."""
    header = f"# {note}\n\n\n" if note else ""
    bodies = [
        f"def {name}():\n    "
        + (f"return {value}" if name in implemented else "raise NotImplementedError")
        + "\n"
        for name, value in FUNCTIONS
    ]
    return header + "\n\n".join(bodies)


def _widget_tests() -> str:
    imports = ", ".join(ALL_FUNCTIONS)
    tests = [
        f"def test_{name}_returns_{value}():\n    assert {name}() == {value}\n"
        for name, value in FUNCTIONS
    ]
    return f"from src.widget import {imports}\n\n\n" + "\n\n".join(tests)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.pop("PYTEST_ADDOPTS", None)
    env["PATH"] = f"{Path(PYTHON).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def build_checkout(
    workspace: Path,
    *,
    implemented: tuple[str, ...] = (),
    base_files: dict[str, str] | None = None,
) -> LoopTask:
    """A git checkout whose base commit holds the widget, its failing tests, an outer-loop
    test and a protected document; no task documents yet."""
    root = workspace / "project"
    root.mkdir(parents=True)
    git(root, "init", "-q")
    for key, value in (
        ("user.name", "Goal Acceptance"),
        ("user.email", "goal-acceptance@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(root, "config", key, value)
    files = {
        ".gitignore": ".ai-work/\n__pycache__/\n.pytest_cache/\n.claude/settings.local.json\n",
        "README.md": "# widget\n",
        "pyproject.toml": '[project]\nname = "widget"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n',
        WIDGET: widget_source(implemented),
        WIDGET_TESTS: _widget_tests(),
        OUTER_LOOP_TEST: "def test_the_widget_contract_holds():\n    assert True\n",
        PROTECTED_DOC: "# Widget contract\n\nOne, two, three.\n",
        **(base_files or {}),
    }
    for rel, text in files.items():
        _write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    task = LoopTask(
        root=root, slug=GOAL_SLUG, base=git(root, "rev-parse", "HEAD"), steps=(), env=_clean_env()
    )
    task.sandbox_home = workspace / "home"
    task.env[CONFIG_DIR_VARIABLE] = str(task.sandbox_home / ".claude")
    task.env[END_WAIT_VARIABLE] = "0"
    return task


def goal_arguments(
    *,
    slug: str = GOAL_SLUG,
    goal: str = GOAL_SENTENCE,
    check: str = CHECK_COMMAND,
    expects: str = EXPECTS,
    paths: tuple[str, ...] = (WIDGET,),
    protect: tuple[str, ...] = (PROTECTED_DOC,),
    iterations: str | int = DEFAULT_BUDGET,
) -> list[str]:
    """The `goal` verb's argument vector; an empty `paths` or `protect` omits the option."""
    args = ["goal", slug, "--goal", goal, "--check", check, "--expects", expects]
    if paths:
        args += ["--paths", *paths]
    if protect:
        args += ["--protect", *protect]
    return [*args, "--iterations", str(iterations)]


def run_command(task: LoopTask, *args: str) -> subprocess.CompletedProcess[str]:
    """`step_loop.py <args>` from the checkout's root, standard input closed."""
    return subprocess.run(
        [sys.executable, str(STEP_LOOP), *args],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=_COMMAND_TIMEOUT,
        env=task.env,
        stdin=subprocess.DEVNULL,
    )


def scaffold(task: LoopTask, **options: Any) -> subprocess.CompletedProcess[str]:
    """`step_loop.py goal ...` as a user types it, from the checkout's root."""
    return run_command(task, *goal_arguments(**options))


def build_goal(
    workspace: Path,
    *,
    iterations: int = DEFAULT_BUDGET,
    implemented: tuple[str, ...] = (),
    base_files: dict[str, str] | None = None,
    paths: tuple[str, ...] = (WIDGET,),
) -> LoopTask:
    """A checkout with a goal plan scaffolded by the `goal` verb."""
    task = build_checkout(workspace, implemented=implemented, base_files=base_files)
    result = scaffold(task, iterations=iterations, paths=paths)
    if result.returncode != 0:
        raise AssertionError(
            f"`step_loop.py goal` exited {result.returncode}; the goal plan was not scaffolded."
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return task


def json_object(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """The one JSON object a command printed on standard output."""
    try:
        doc = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"exit {result.returncode} without one JSON object on stdout:\n"
            f"{result.stdout}\nstderr:\n{result.stderr}"
        ) from exc
    if not isinstance(doc, dict):
        raise AssertionError(f"stdout holds JSON that is not an object: {doc!r}")
    return doc


def task_files(task: LoopTask) -> dict[str, bytes]:
    """Every file under the checkout outside `.git/` (the task documents included)."""
    return {
        str(p.relative_to(task.root)): p.read_bytes()
        for p in sorted(task.root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(task.root).parts
    }


def deny_rules(root: Path) -> list[str]:
    """`permissions.deny` of the repository's local harness settings."""
    path = root / SETTINGS
    if not path.is_file():
        raise AssertionError(f"{SETTINGS} does not exist at the repository root")
    settings = json.loads(path.read_text(encoding="utf-8"))
    return list(settings.get("permissions", {}).get("deny", []))


def edit_rule_paths(rules: list[str]) -> set[str]:
    """The path each `Edit(...)` rule names, anchors and trailing globs dropped."""
    paths = set()
    for rule in rules:
        match = re.fullmatch(r"Edit\((.*)\)", rule.strip())
        if match:
            inner = re.sub(r"^(\./|/|\*\*/)+", "", match.group(1))
            paths.add(re.sub(r"(/\*\*|/\*)+$", "", inner))
    return paths


def progress_lines(task: LoopTask) -> list[str]:
    """The non-blank lines of WIP.md's `## Progress record` section."""
    text = _read(task.wip_path)
    if PROGRESS_HEADING not in text:
        raise AssertionError(f"WIP.md has no {PROGRESS_HEADING!r} section:\n{text}")
    section = text.split(PROGRESS_HEADING, 1)[1]
    section = re.split(r"^#{1,2} ", section, maxsplit=1, flags=re.MULTILINE)[0]
    return [line for line in section.splitlines() if line.strip()]


def goal_step_id(task: LoopTask) -> str:
    """The goal step's id, as `status` names it."""
    report = status(task, as_json=True).json()
    if "steps" not in report:
        raise AssertionError(f"`status --json` reports no steps: {report}")
    steps = report["steps"]
    if len(steps) != 1:
        raise AssertionError(f"a goal plan holds one step; status reads {steps}")
    return step_id_of(steps[0]["step"])


def patch_files(task: LoopTask, request_id: str) -> list[Path]:
    """Files the driver left in the task directory named by `request_id`, prompts aside."""
    return [
        p
        for p in sorted(task.task_dir.iterdir())
        if request_id in p.name and not p.name.startswith("PROMPT_")
    ]


def commit_holds_trailer(message: str, request_id: str) -> bool:
    pattern = rf"^{re.escape(STEP_LOOP_REQUEST_TRAILER)}\s*{re.escape(request_id)}\s*$"
    return re.search(pattern, message, re.MULTILINE) is not None


# -- An iteration's work ------------------------------------------------------------------


@dataclass(frozen=True)
class Iteration:
    """What one iteration's worker does before it ends, and what its result reports."""

    implemented: tuple[str, ...] = ()  # the widget functions implemented once it is done
    note: str = ""  # a comment line, so an edit can differ without changing behaviour
    touches_widget: bool = True
    progress: str | None = PROGRESS_LINE  # the line appended to `## Progress record`
    other_edits: tuple[tuple[str, str], ...] = ()  # (path, text) beyond the widget
    marker: str = "complete"  # the marker the worker's final message ends with
    requests: int = 7  # distinct API requests in its transcript
    # The headless worker's result object only:
    result_text: str | None = None  # None: a closing sentence, then the marker's line
    omits_result_text: bool = False
    stopped_at_turn_bound: bool = False
    cost_usd: float = 0.0731
    permission_denials: int = 0
    exit_status: int = 0
    prints_result: bool = True

    @property
    def final_text(self) -> str:
        if self.result_text is not None:
            return self.result_text
        return f"Iteration finished.\n{MARKER_TEXT[self.marker]}".rstrip()


def append_progress(wip: Path, line: str) -> None:
    """Append `line` to WIP.md's `## Progress record` section, as the worker is told to."""
    text = wip.read_text(encoding="utf-8")
    if PROGRESS_HEADING not in text:
        raise AssertionError(f"WIP.md has no {PROGRESS_HEADING!r} section to append to")
    before, after = text.split(PROGRESS_HEADING, 1)
    parts = re.split(r"(^#{1,2} .*$)", after, maxsplit=1, flags=re.MULTILINE)
    section = parts[0].rstrip("\n") + f"\n{line}\n"
    rest = "".join(parts[1:])
    wip.write_text(before + PROGRESS_HEADING + section + ("\n" + rest if rest else ""), "utf-8")


def apply_iteration(root: Path, slug: str, iteration: Iteration) -> None:
    """The worker's edits: the widget, any other edits, and its progress line."""
    if iteration.touches_widget:
        _write(root, WIDGET, widget_source(iteration.implemented, iteration.note))
    for rel, text in iteration.other_edits:
        _write(root, rel, text)
    if iteration.progress is not None:
        append_progress(root / ".ai-work" / slug / "WIP.md", iteration.progress)


@dataclass(frozen=True)
class Relayed:
    asked: Envelope  # the `next` that issued the spawn request
    returned: Envelope  # the `record` that took the iteration back
    agent_id: str

    @property
    def request(self) -> dict[str, Any]:
        assert self.asked.request is not None
        return self.asked.request


DEFAULT_ITERATION = Iteration()


def iterate_by_relay(task: LoopTask, iteration: Iteration = DEFAULT_ITERATION) -> Relayed:
    """One iteration through the relay: `next`, the Agent tool's double, `record`."""
    asked = next_action(task)
    if asked.outcome != "spawn" or asked.request is None:
        raise AssertionError(f"expected a spawn request for the goal step, got: {asked.doc}")
    apply_iteration(task.root, task.slug, iteration)
    agent_id = new_agent_id()
    leave_agent_transcript(
        task,
        asked.request,
        agent_id,
        requests=iteration.requests,
        final_text=iteration.final_text,
        ended=True,
    )
    returned = record(task, asked.request["id"], agent_id=agent_id, marker=iteration.marker)
    return Relayed(asked=asked, returned=returned, agent_id=agent_id)


# -- Reading the task's documents -----------------------------------------------------------


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"{path.name} was not written in {path.parent}")
    return path.read_text(encoding="utf-8")


def _plain(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("`", "").replace("*", ""))


def plan_field(task: LoopTask, name: str) -> str:
    """The value of plan-step field `name` (e.g. `Files`), emphasis and code marks dropped."""
    text = _plain(_read(task.plan_path))
    found = re.findall(rf"^\W*{re.escape(name)}\W*:\s*(.*)$", text, re.MULTILINE)
    if len(found) != 1:
        raise AssertionError(f"the plan carries {len(found)} {name!r} fields, not one:\n{text}")
    return found[0].strip()


def check_field(task: LoopTask) -> str:
    """The `Check:` field as the plan writes it, code marks kept."""
    text = _read(task.plan_path).replace("*", "")
    found = re.findall(r"^\W*Check\W*:\s*(.*)$", text, re.MULTILINE)
    if len(found) != 1:
        raise AssertionError(f"the plan carries {len(found)} Check fields, not one:\n{text}")
    return found[0].strip()


def checklist_lines(task: LoopTask) -> list[str]:
    """WIP.md's checkbox lines, ticked or not."""
    text = _read(task.wip_path)
    return re.findall(r"^\s*- \[[ xX]\] .*$", text, re.MULTILINE)


def brief_section_lines(task: LoopTask, heading_pattern: str) -> list[str]:
    """The non-blank lines under the task brief's heading matching `heading_pattern`."""
    brief = _read(task.task_dir / "TASK_BRIEF.md")
    return [line for line in section(brief, heading_pattern).splitlines() if line.strip()]


def names_count(text: str, key: str, count: int) -> bool:
    """`text` states `count` for `key`: `pass=1`, `passed: 1`, `1 passed` or `2 permission
    denials`."""
    pattern = rf"\b{key}\w*\s*[=:]\s*{count}\b|\b{count}\s+(\w+\s+)?{key}"
    return re.search(pattern, text, re.IGNORECASE) is not None


def prompt_text(request: dict[str, Any]) -> str:
    """The rendered prompt a spawn request points to."""
    return _read(Path(request["prompt_path"]))


def ticked(task: LoopTask) -> bool:
    """WIP.md's one checkbox line is ticked."""
    lines = checklist_lines(task)
    if len(lines) != 1:
        raise AssertionError(f"WIP.md holds {len(lines)} checkbox lines, not one: {lines}")
    return "- [x]" in lines[0].lower()
