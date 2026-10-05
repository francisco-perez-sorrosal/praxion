"""Driver for the step-loop command, reached only through its command line.

A scenario names what varies: the plan's steps (dependencies, parallel groups,
routing and review annotations, whether a step declares a check), what a spawned
agent does to the tree and which terminal marker it returns, and which of the
loop's three verbs the orchestrator calls next. This driver builds everything
else -- a git checkout with a pytest project, the plan, the progress file and the
task brief in the shapes the planning templates document -- and runs
`scripts/step_loop.py`, the reconciler and the iteration ledger the way the
orchestrator and a human do: as commands, parsing what they print.

The test double for the Agent tool lives here too (`work_on`): it edits the tree
the way an implementer would and leaves behind what a finished agent leaves. Two
parts of that are not yet bound to a designed surface -- where the command looks
for a spawned agent's own transcript, and where a light reviewer leaves its
verdict -- and raise `UnboundDriverError` until a driver-binding step binds them.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STEP_LOOP = REPO_ROOT / "scripts" / "step_loop.py"
RECONCILER = REPO_ROOT / "scripts" / "reconcile_pipeline_state.py"
LEDGER = REPO_ROOT / "scripts" / "iteration_ledger.py"
IMPLEMENTER_DEFINITION = REPO_ROOT / "agents" / "implementer.md"

SLUG = "loop-task"
PYTHON = sys.executable

# Text placed in the task's documents so a scenario can tell where a prompt's parts came from.
HEALTH_GUARD = "Every widget module stays importable without side effects (brief guard 41)."
INTENT_TEXT = "The loop widget exists so the acceptance suite can drive a plan (brief intent 29)."
GOAL_TEXT = "Build the loop widget one step at a time (plan goal 53)."

EXIT_CODES = frozenset({0, 1, 2, 3, 4})
_EXIT_BY_OUTCOME = {"spawn": 0, "complete": 0, "needs-human": 2, "budget-exhausted": 3}
_COMMAND_TIMEOUT = 900


class UnboundDriverError(NotImplementedError):
    """Raised by a driver hook not yet bound to the designed surface."""


# -- The plan a scenario describes ---------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One plan step. Its own files are a source module and the unit test that proves it."""

    id: str
    title: str = "Write the widget"
    depends_on: tuple[str, ...] = ()
    parallel_group: str | None = None
    annotations: tuple[str, ...] = ()  # verbatim lines, e.g. "tier: H", "**review**: force"
    assignee: str = "implementer"
    declares_check: bool = True
    read_only: tuple[str, ...] = ()
    more_files: tuple[str, ...] = ()  # further declared files beyond the step's own pair
    implementation: str | None = None  # the step's Implementation text; a default names its file
    check_prefix: str = ""  # shell text run before the check's pytest command

    @property
    def module(self) -> str:
        return f"step_{self.id}"

    @property
    def source(self) -> str:
        return f"src/{self.module}.py"

    @property
    def unit_test(self) -> str:
        return f"tests/test_{self.module}.py"

    @property
    def files(self) -> tuple[str, ...]:
        return (self.source, self.unit_test, *self.more_files)

    @property
    def check_command(self) -> str:
        return f"{self.check_prefix}{PYTHON} -m pytest {self.unit_test} -q -p no:cacheprovider"


def _heading(step: Step) -> str:
    heading = f"### Step {step.id}: {step.title}"
    if step.parallel_group is not None:
        heading += f" [parallel-group: {step.parallel_group}]"
    if step.depends_on:
        heading += f" [depends-on: {', '.join(step.depends_on)}]"
    return heading


def step_block(step: Step) -> str:
    """The step's block exactly as the plan carries it."""
    implementation = step.implementation or (
        f"Write `{step.source}` so that `value()` returns the step id."
    )
    lines = [
        _heading(step),
        "",
        f"**Assignee**: {step.assignee}",
        f"**Implementation**: {implementation}",
        "**Files**: " + ", ".join(f"`{f}`" for f in step.files),
        *step.annotations,
    ]
    if step.read_only:
        lines.append("**Read-only**: " + ", ".join(f"`{node}`" for node in step.read_only))
    if step.declares_check:
        lines.append(f"**Check**: `{step.check_command}` expects pass=1 fail=0 skip=0")
    lines.append(f"**Done when**: `{step.unit_test}` passes.")
    return "\n".join(lines) + "\n"


def _plan(steps: tuple[Step, ...]) -> str:
    return f"# Plan: loop widget\n\n## Goal\n\n{GOAL_TEXT}\n\n## Steps\n\n" + "\n".join(
        step_block(s) for s in steps
    )


def _wip(steps: tuple[Step, ...], done: frozenset[str], extra_progress: dict[str, str]) -> str:
    entries = []
    for s in steps:
        entry = f"- [{'x' if s.id in done else ' '}] Step {s.id}: {s.title}"
        if s.id in extra_progress:
            entry += "\n" + extra_progress[s.id]
        entries.append(entry)
    first = steps[0]
    return (
        "# WIP: loop widget\n\n## Current Step\n\n"
        f"Step {first.id} of {len(steps)}: {first.title}\n\n"
        "## Status\n\n[IN-PROGRESS] - Step underway\n\n"
        "## Progress\n\n" + "\n".join(entries) + "\n\n## Blockers\n\nNone\n"
    )


def _brief() -> str:
    return (
        "# Task Brief: loop widget\n\n"
        f"## Task Intent\n\n{INTENT_TEXT}\n\n"
        "## Key Signals\n\n- [ ] S1 — each widget module returns its step id.\n\n"
        f"## Health Guards\n\n- [ ] {HEALTH_GUARD}\n\n"
        "## Uncertainty Flag\n\n8/10 — none.\n"
    )


def _green_result_section(step: Step) -> str:
    return (
        f"## Step {step.id} — {step.title}\n"
        f"Command: `{step.check_command}`\n"
        "Result: pass=1 fail=0 skip=0\n"
        "Duration: 0.4s\n"
    )


def _source_text(step: Step, *, passes: bool) -> str:
    returned = repr(step.id) if passes else "None"
    return f"def value():\n    return {returned}\n"


def _unit_test_text(step: Step) -> str:
    return (
        f"from src.{step.module} import value\n\n\n"
        "def test_value_is_the_step_id():\n"
        f"    assert value() == {step.id!r}\n"
    )


# -- The checkout ---------------------------------------------------------------------


@dataclass
class LoopTask:
    root: Path
    slug: str
    base: str
    steps: tuple[Step, ...]
    env: dict[str, str] = field(default_factory=dict)
    sandbox_home: Path | None = None  # for the transcript binding, should it need one

    @property
    def task_dir(self) -> Path:
        return self.root / ".ai-work" / self.slug

    @property
    def plan_path(self) -> Path:
        return self.task_dir / "IMPLEMENTATION_PLAN.md"

    @property
    def wip_path(self) -> Path:
        return self.task_dir / "WIP.md"

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.pop("PYTEST_ADDOPTS", None)
    # `python` on PATH must be an interpreter that has pytest, as it is under `uv run`.
    env["PATH"] = f"{Path(PYTHON).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def git(task_or_root: LoopTask | Path, *args: str, check: bool = True) -> str:
    root = task_or_root.root if isinstance(task_or_root, LoopTask) else task_or_root
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=check,
        timeout=60,
        env=_clean_env(),
    )
    return result.stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_loop(
    workspace: Path,
    *steps: Step,
    done: tuple[str, ...] = (),
    base_files: dict[str, str] | None = None,
    extra_progress: dict[str, str] | None = None,
) -> LoopTask:
    """A checkout whose plan holds `steps`; the steps in `done` already verified-complete.

    A done step's work is committed after the base commit, ticked in WIP.md and recorded
    green in TEST_RESULTS.md. `base_files` are committed in the base commit itself.
    `extra_progress` adds verbatim lines under a step's WIP.md checklist entry.
    """
    root = workspace / "project"
    root.mkdir(parents=True)
    git(root, "init", "-q")
    for key, value in (
        ("user.name", "Loop Acceptance"),
        ("user.email", "loop-acceptance@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(root, "config", key, value)
    _write(root, ".gitignore", ".ai-work/\n__pycache__/\n.pytest_cache/\n")
    _write(root, "README.md", "# loop widget\n")
    _write(
        root,
        "pyproject.toml",
        '[project]\nname = "loop-widget"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n',
    )
    for rel, text in (base_files or {}).items():
        _write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")

    by_id = {s.id: s for s in steps}
    if done:
        for step_id in done:
            step = by_id[step_id]
            _write(root, step.source, _source_text(step, passes=True))
            _write(root, step.unit_test, _unit_test_text(step))
        git(root, "add", "-A")
        git(root, "commit", "-qm", "earlier steps")

    task = LoopTask(root=root, slug=SLUG, base=base, steps=tuple(steps), env=_clean_env())
    task.sandbox_home = workspace / "home"
    task.task_dir.mkdir(parents=True)
    task.plan_path.write_text(_plan(task.steps), encoding="utf-8")
    task.wip_path.write_text(
        _wip(task.steps, frozenset(done), extra_progress or {}), encoding="utf-8"
    )
    (task.task_dir / "TASK_BRIEF.md").write_text(_brief(), encoding="utf-8")
    if done:
        (task.task_dir / "TEST_RESULTS.md").write_text(
            "\n".join(_green_result_section(by_id[i]) for i in done), encoding="utf-8"
        )
    return task


def revise_step(task: LoopTask, step_id: str, implementation: str) -> None:
    """A human revises the step's Implementation text in IMPLEMENTATION_PLAN.md."""
    old = task.step(step_id)
    new = replace(old, implementation=implementation)
    plan = task.plan_path.read_text(encoding="utf-8")
    task.plan_path.write_text(plan.replace(step_block(old), step_block(new)), encoding="utf-8")
    task.steps = tuple(new if s.id == step_id else s for s in task.steps)


# -- Running the command ----------------------------------------------------------------


@dataclass(frozen=True)
class Envelope:
    """What one `next` or `record` call printed, with its exit code."""

    exit_code: int
    doc: dict[str, Any]
    stderr: str

    @property
    def outcome(self) -> str:
        return str(self.doc["outcome"])

    @property
    def request(self) -> dict[str, Any] | None:
        return self.doc.get("request")

    @property
    def stop(self) -> dict[str, Any] | None:
        return self.doc.get("stop")

    @property
    def recorded(self) -> dict[str, Any] | None:
        return self.doc.get("recorded")

    @property
    def error(self) -> dict[str, Any] | None:
        return self.doc.get("error")

    @property
    def iterations(self) -> dict[str, Any] | None:
        return self.doc.get("iterations")

    @property
    def warning_codes(self) -> list[str]:
        return [w["code"] for w in self.doc.get("warnings", [])]

    def text(self) -> str:
        """Everything the call said, envelope and stderr, for 'is X named anywhere' checks."""
        return json.dumps(self.doc) + "\n" + self.stderr


def _run(task: LoopTask, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(STEP_LOOP), *args],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=_COMMAND_TIMEOUT,
        env=task.env,
    )


def _location(task: LoopTask) -> list[str]:
    return ["--repo-root", str(task.root), "--base-ref", task.base]


def assert_well_formed(verb: str, result: subprocess.CompletedProcess[str]) -> Envelope:
    """One JSON envelope on stdout, an exit code from the closed set, matching its outcome."""
    try:
        doc = json.loads(result.stdout)
    except json.JSONDecodeError:
        doc = None
    if not isinstance(doc, dict):
        raise AssertionError(
            f"`step_loop.py {verb}` exited {result.returncode} without exactly one JSON "
            f"envelope on stdout.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if result.returncode not in EXIT_CODES:
        raise AssertionError(
            f"`step_loop.py {verb}` exited {result.returncode}, outside the closed set "
            f"{sorted(EXIT_CODES)}: {doc}"
        )
    outcome = doc.get("outcome")
    if outcome == "error":
        expected = 1 if (doc.get("error") or {}).get("code") == "internal" else 4
    else:
        expected = _EXIT_BY_OUTCOME.get(outcome)
    if expected != result.returncode:
        raise AssertionError(
            f"`step_loop.py {verb}` exited {result.returncode} with outcome {outcome!r}, "
            f"which exits {expected}: {doc}\nstderr:\n{result.stderr}"
        )
    return Envelope(exit_code=result.returncode, doc=doc, stderr=result.stderr)


def next_action(task: LoopTask) -> Envelope:
    """`step_loop.py next <slug>`: the loop's next action."""
    return assert_well_formed("next", _run(task, "next", task.slug, *_location(task)))


def record(task: LoopTask, request_id: str, *, agent_id: str, marker: str) -> Envelope:
    """`step_loop.py record` with the three values the orchestrator relays."""
    return assert_well_formed(
        "record",
        _run(
            task,
            "record",
            task.slug,
            "--request",
            request_id,
            "--agent-id",
            agent_id,
            "--marker",
            marker,
            *_location(task),
        ),
    )


def record_not_started(task: LoopTask, request_id: str, reason: str) -> Envelope:
    """`step_loop.py record --not-started`: the Agent tool call failed before launch."""
    return assert_well_formed(
        "record",
        _run(
            task,
            "record",
            task.slug,
            "--request",
            request_id,
            "--not-started",
            reason,
            *_location(task),
        ),
    )


def run_raw(task: LoopTask, *args: str) -> subprocess.CompletedProcess[str]:
    """Any argument vector, as typed; for usage-error scenarios."""
    return _run(task, *args)


@dataclass(frozen=True)
class StatusReport:
    exit_code: int
    stdout: str
    stderr: str

    def json(self) -> dict[str, Any]:
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"`step_loop.py status --json` printed no JSON object (exit "
                f"{self.exit_code}):\n{self.stdout}{self.stderr}"
            ) from exc


def status(task: LoopTask, *, as_json: bool) -> StatusReport:
    """`step_loop.py status <slug> [--json]`."""
    flags = ["--json"] if as_json else []
    result = _run(task, "status", task.slug, *flags, *_location(task))
    if result.returncode not in EXIT_CODES:
        raise AssertionError(
            f"`step_loop.py status` exited {result.returncode}, outside the closed set:\n"
            f"{result.stdout}{result.stderr}"
        )
    return StatusReport(result.returncode, result.stdout, result.stderr)


# -- The Agent tool's test double ---------------------------------------------------------


MARKER_TEXT = {
    "complete": "[COMPLETE]",
    "blocked": "[BLOCKED]",
    "conflict": "[CONFLICT]",
    "partial": "[PARTIAL]",
    "none": "",
}


@dataclass(frozen=True)
class Work:
    """What a spawned implementer does before it returns."""

    passes: bool = True  # the step's own unit test passes against the edited source
    touches_files: bool = True  # whether it writes the step's declared files at all
    requests: int = 12  # distinct API requests in its own transcript
    final_marker: str = "complete"  # the marker its final message carries
    ticks_checkbox: bool = True
    claims_green: bool = False  # writes a TEST_RESULTS.md section claiming a green run
    other_edits: tuple[tuple[str, str], ...] = ()  # (path, text) outside the declared files


DEFAULT_WORK = Work()


def new_agent_id() -> str:
    return "a" + uuid.uuid4().hex[:15]


def work_on(task: LoopTask, request: dict[str, Any], work: Work = DEFAULT_WORK) -> str:
    """Do `work` for the spawn `request` as the implementer would; return its agent id."""
    step = task.step(str(request["step"]))
    if work.touches_files:
        _write(task.root, step.source, _source_text(step, passes=work.passes))
        _write(task.root, step.unit_test, _unit_test_text(step))
    for rel, text in work.other_edits:
        _write(task.root, rel, text)
    if work.ticks_checkbox:
        wip = task.wip_path.read_text(encoding="utf-8")
        task.wip_path.write_text(
            wip.replace(f"- [ ] Step {step.id}: ", f"- [x] Step {step.id}: "), encoding="utf-8"
        )
    if work.claims_green:
        results = task.task_dir / "TEST_RESULTS.md"
        earlier = results.read_text(encoding="utf-8") + "\n" if results.exists() else ""
        results.write_text(earlier + _green_result_section(step), encoding="utf-8")
    agent_id = new_agent_id()
    leave_agent_transcript(
        task,
        request,
        agent_id,
        requests=work.requests,
        final_text=f"Step {step.id} done. {MARKER_TEXT[work.final_marker]}".strip(),
        ended=True,
    )
    return agent_id


def leave_agent_transcript(
    task: LoopTask,
    request: dict[str, Any],
    agent_id: str,
    *,
    requests: int,
    final_text: str,
    ended: bool,
    readable: bool = True,
) -> None:
    """Leave what a spawned agent leaves behind: its own transcript, opened by the request's
    prompt, holding `requests` distinct API requests and ending with `final_text`; and, when
    `ended`, whatever shows the agent has ended. `readable=False` leaves a transcript that
    cannot be parsed.
    """
    raise UnboundDriverError(
        "not yet bound: where the step-loop command finds a spawned agent's own transcript "
        "from its agent id, how that transcript is tied to the spawn request it answers, "
        "and how the command tells an agent that has ended from one still running"
    )


def leave_review_verdict(task: LoopTask, request: dict[str, Any], verdict: str) -> str:
    """A light reviewer answers `request` with `verdict` (accept, revise or unfinished) and
    ends; return its agent id."""
    raise UnboundDriverError(
        "not yet bound: where a light reviewer spawned by the step loop leaves its accept or "
        "revise verdict for a step, and how a review still marked unfinished looks"
    )


def attempt(task: LoopTask, work: Work = DEFAULT_WORK, *, marker: str | None = None) -> Envelope:
    """One whole attempt: `next`, the double's work, then `record` with the double's marker."""
    asked = next_action(task)
    if asked.outcome != "spawn" or asked.request is None:
        raise AssertionError(f"expected a spawn request, got: {asked.doc}")
    agent_id = work_on(task, asked.request, work)
    return record(
        task,
        asked.request["id"],
        agent_id=agent_id,
        marker=marker if marker is not None else work.final_marker,
    )


# -- Reading ground truth back ------------------------------------------------------------


def step_id_of(value: Any) -> str:
    """A step as the command names it, with any `Step ` label dropped: labelled or bare, one id."""
    return str(value).removeprefix("Step ").strip()


def head(task: LoopTask) -> str:
    return git(task, "rev-parse", "HEAD")


def commits_after(task: LoopTask, ref: str) -> list[str]:
    out = git(task, "rev-list", f"{ref}..HEAD")
    return out.split() if out else []


def files_in_commit(task: LoopTask, sha: str) -> set[str]:
    out = git(task, "show", "--name-only", "--format=", sha)
    return {line for line in out.splitlines() if line}


def commit_message(task: LoopTask, sha: str) -> str:
    return git(task, "log", "-1", "--format=%B", sha)


def staged_paths(task: LoopTask) -> set[str]:
    out = git(task, "diff", "--cached", "--name-only")
    return {line for line in out.splitlines() if line}


def snapshot(task: LoopTask) -> dict[str, bytes]:
    """Every file under the checkout outside `.git/`, with its bytes."""
    return {
        str(p.relative_to(task.root)): p.read_bytes()
        for p in sorted(task.root.rglob("*"))
        if p.is_file()
        and ".git" not in p.relative_to(task.root).parts
        and "__pycache__" not in p.parts
    }


def ledger_records(task: LoopTask) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The task's iteration-ledger records and findings, through the ledger's own reader."""
    result = subprocess.run(
        [sys.executable, str(LEDGER), "read", task.slug, "--repo-root", str(task.root), "--json"],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=60,
        env=task.env,
    )
    try:
        doc = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"the ledger reader printed no JSON (exit {result.returncode}):\n"
            f"{result.stdout}{result.stderr}"
        ) from exc
    return list(doc.get("records", [])), list(doc.get("findings", []))


def reconciler_verdict(task: LoopTask, step_id: str) -> dict[str, Any]:
    """The reconciler's verdict for one step, as `/resume-pipeline` asks for it."""
    result = subprocess.run(
        [
            sys.executable,
            str(RECONCILER),
            task.slug,
            "--repo-root",
            str(task.root),
            "--base-ref",
            task.base,
            "--json",
            "--quiet",
        ],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=120,
        env=task.env,
    )
    try:
        verdicts = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"the reconciler printed no verdict JSON (exit {result.returncode}):\n"
            f"{result.stdout}{result.stderr}"
        ) from exc
    for verdict in verdicts:
        if str(verdict.get("step")) == f"Step {step_id}":
            return verdict
    raise AssertionError(f"the reconciler judged no 'Step {step_id}': {verdicts}")


def attempts_line(task: LoopTask, step_id: str) -> str | None:
    """The `Attempts:` line WIP.md carries for the step, if any."""
    for line in task.wip_path.read_text(encoding="utf-8").splitlines():
        if re.search(rf"Attempts:\s*Step {re.escape(step_id)}\b", line):
            return line.strip()
    return None


def implementer_max_turns() -> int:
    """The implementer's declared `maxTurns`, from its agent definition's frontmatter."""
    text = IMPLEMENTER_DEFINITION.read_text(encoding="utf-8")
    front = text.split("---", 2)[1]
    match = re.search(r"^maxTurns:\s*(\d+)\s*$", front, re.MULTILINE)
    if match is None:
        raise AssertionError("the implementer's definition declares no maxTurns")
    return int(match.group(1))


HANDOFF_SECTIONS = (
    "§0 Preflight",
    "§1 State",
    "§2 Next action",
    "§3 Decisions & assumptions in force",
    "§4 Operating constraints from the user",
    "§5 Corrections in force",
    "§6 Do not re-inherit",
    "§7 Start here",
)


def handoff_section(text: str, heading: str) -> str:
    """The body of one `## §N ...` section of HANDOFF.md."""
    marker = f"## {heading}"
    if marker not in text:
        raise AssertionError(f"HANDOFF.md has no {marker!r} section:\n{text}")
    rest = text.split(marker, 1)[1]
    return re.split(r"^## §\d", rest, maxsplit=1, flags=re.MULTILINE)[0]
