"""Driver for the workflow that hosts the liveness checks, read and run the way GitHub would.

The liveness checks are the gate-liveness command (`scripts/check_gates_bite.py`) and the
`liveness`-marked scenarios under `tests/e2e` and `tests/acceptance`. Their workflow is found,
never named: it is the one workflow file other than the scheduled test-health workflow whose jobs
run either of them. A job is read through what its steps run: each step's `run:` text split into
command lines, the gate-liveness command's `--gate` choices, and each pytest invocation, whose
selection is read by running that invocation with `--collect-only` against this checkout.

A job can also be *run locally* (`run_job_locally`): its `run:` steps in order, in a scratch copy,
with GitHub's `if:` rules for a step after a failure or a cut, so a scenario reads the job's log
the way the runner would write it. Before a step runs its text is checked for anything that could
reach beyond the copy (`sudo`, the dependency install), and those steps are skipped.

Bound here, because the specification or the base commit fixes them: the two-space indentation
every workflow file of this repository uses, the scheduled workflow's path and name, the autofix
workflow's watch list, the gate ids, the marker name, the synced interpreter
`.venv/bin/python` and the step that builds it, `uv sync --frozen`.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from tests.acceptance.drivers.gate_liveness import RepoCopy, isolated_env

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_DIR = Path(".github") / "workflows"
SCHEDULED = ".github/workflows/test-scheduled.yml"
SCHEDULED_NAME = "Test (scheduled)"
AUTOFIX = ".github/workflows/ci-autofix.yml"
AUTOFIX_WATCHED = ["Test", "Architecture", "Test (scheduled)"]

GATE_COMMAND = "scripts/check_gates_bite.py"
SYNCED_PYTHON = ".venv/bin/python"
SYNC_STEP = "uv sync --frozen"
QUICK_PROBES = ("mutation-sensor", "observation-hooks", "spawn-count")
AUDIT_PROBE = "selection-audit"
ALL_PROBES = (*QUICK_PROBES, AUDIT_PROBE)
MARKER = "liveness"
SCENARIO_TREES = ("tests/e2e", "tests/acceptance")
RUNNER_JOB_MAXIMUM_MINUTES = 360  # GitHub's 6-hour ceiling for one job on a hosted runner
FAST_JOB_MAXIMUM_MINUTES = 20

# The scenarios that run the traced default suite, and the quick ones that run in seconds.
WHOLE_SUITE_SCENARIO_FILES = ("tests/e2e/test_gate_liveness_run.py",)
QUICK_SCENARIO_FILES = (
    "tests/acceptance/test_liveness_run_outcome.py",
    "tests/acceptance/test_mutation_sensor_liveness.py",
    "tests/acceptance/test_spawn_count_liveness.py",
)

_SHA_PIN = re.compile(r"@[0-9a-f]{40}\b")
_WEEKLY_CRON = re.compile(r"^\d{1,2} \d{1,2} \* \* [0-7A-Za-z]{1,3}$")
_SEPARATORS = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
_SESSION_COMMAND = re.compile(r"(?:^|[\s;&|(])claude(?:\s|$)")
REACHING_TOKENS = ("secrets.", "github.token", "GITHUB_TOKEN", "GH_TOKEN", "ANTHROPIC_")
SESSION_TOKENS = ("claude-code-action", "anthropics/")


# -- Reading a workflow ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Workflow:
    relpath: str
    text: str
    data: dict

    @property
    def name(self) -> str:
        return str(self.data.get("name", ""))

    @property
    def basename(self) -> str:
        return Path(self.relpath).name

    @property
    def triggers(self) -> dict:
        # YAML 1.1 reads a bare `on:` key as the boolean True.
        triggers = self.data.get("on", self.data.get(True))
        return triggers if isinstance(triggers, dict) else dict.fromkeys(triggers or ())

    @property
    def jobs(self) -> dict[str, dict]:
        return dict(self.data.get("jobs") or {})

    def permissions_of(self, job_id: str) -> object:
        """The grant a job runs with: its own block, else the workflow's."""
        return self.jobs[job_id].get("permissions", self.data.get("permissions"))

    def is_weekly_and_by_hand(self) -> bool:
        triggers = self.triggers
        weekly = any(
            _WEEKLY_CRON.match(str(entry.get("cron", "")).strip())
            for entry in (triggers.get("schedule") or [])
        )
        return weekly and "workflow_dispatch" in triggers


def load(relpath: str, root: Path = REPO_ROOT) -> Workflow:
    text = (root / relpath).read_text(encoding="utf-8")
    return Workflow(relpath, text, yaml.safe_load(text) or {})


def all_workflows(root: Path = REPO_ROOT) -> list[Workflow]:
    directory = root / WORKFLOW_DIR
    paths = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    return [load(p.relative_to(root).as_posix(), root) for p in paths]


def run_texts(job: Mapping) -> list[str]:
    return [str(step.get("run", "")) for step in job.get("steps", []) if step.get("run")]


def command_lines(run_text: str) -> list[str]:
    """Each command of a `run:` text: continuations joined, split at newlines and shell operators."""
    joined = re.sub(r"\\\n\s*", " ", run_text)
    commands = []
    for line in joined.splitlines():
        line = line.split(" #", 1)[0].strip()
        if line and not line.startswith("#"):
            commands += [part for part in _SEPARATORS.split(line) if part.strip()]
    return commands


def _argv(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def gate_invocations(job: Mapping) -> list[list[str]]:
    return [
        _argv(command)
        for text in run_texts(job)
        for command in command_lines(text)
        if GATE_COMMAND in command
    ]


def pytest_invocations(job: Mapping) -> list[list[str]]:
    return [
        _argv(command)
        for text in run_texts(job)
        for command in command_lines(text)
        if re.search(r"(?:^|[\s/])(?:pytest|py\.test)(?:\s|$)", command)
    ]


def probes_selected(argv: list[str]) -> tuple[str, ...]:
    """The probes a gate-liveness invocation runs: its `--gate` values, all four when none."""
    chosen = [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--gate"]
    chosen += [arg.split("=", 1)[1] for arg in argv if arg.startswith("--gate=")]
    return tuple(chosen) if chosen else ALL_PROBES


def marker_expression(argv: list[str]) -> str | None:
    """The last `-m` expression of a pytest invocation (the last one wins over the config's)."""
    found = None
    for i, arg in enumerate(argv):
        if arg == "-m" and i + 1 < len(argv):
            found = argv[i + 1]
        elif arg.startswith("-m") and len(arg) > 2 and not arg.startswith("-m="):
            found = arg[2:]
    return found


def selects_the_marker(argv: list[str]) -> bool:
    expression = marker_expression(argv)
    if expression is None:
        return False
    return bool(re.search(rf"\b{MARKER}\b", expression)) and not re.search(
        rf"\bnot\s+{MARKER}\b", expression
    )


def path_arguments(argv: list[str]) -> list[str]:
    """Positional arguments of a pytest invocation that name a path of the checkout."""
    try:
        start = argv.index("pytest") + 1
    except ValueError:
        start = 1
    paths = []
    skip_next = False
    for arg in argv[start:]:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-m", "-k", "-n", "-p", "--dist", "-c", "--rootdir", "--durations", "-o"}:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        paths.append(arg)
    return paths


def gate_runs_outside_the_synced_environment(wf: Workflow) -> dict[str, object]:
    """Each step that runs the gate command other than from the synced environment, once built."""
    misrun: dict[str, object] = {}
    for job_id, job in wf.jobs.items():
        steps = [str(step.get("run", "")) for step in job.get("steps", [])]
        synced_at = next((i for i, text in enumerate(steps) if SYNC_STEP in text), None)
        for i, text in enumerate(steps):
            if GATE_COMMAND not in text:
                continue
            invocations = gate_invocations({"steps": [{"run": text}]})
            wrong = [argv for argv in invocations if argv[:2] != [SYNCED_PYTHON, GATE_COMMAND]]
            if wrong or synced_at is None or synced_at >= i:
                misrun[f"{job_id} step {i}"] = wrong or "not after the environment is built"
    return misrun


def runs_the_gate_command(job: Mapping) -> bool:
    return bool(gate_invocations(job))


def runs_the_liveness_scenarios(job: Mapping) -> bool:
    return any(selects_the_marker(argv) for argv in pytest_invocations(job))


def runs_a_liveness_check(job: Mapping) -> bool:
    return runs_the_gate_command(job) or runs_the_liveness_scenarios(job)


def hosts_of_the_liveness_checks(root: Path = REPO_ROOT) -> list[Workflow]:
    return [wf for wf in all_workflows(root) if any(map(runs_a_liveness_check, wf.jobs.values()))]


def liveness_workflow(root: Path = REPO_ROOT) -> Workflow:
    """The one workflow, other than the scheduled test-health one, that runs the liveness checks."""
    hosts = [wf for wf in hosts_of_the_liveness_checks(root) if wf.relpath != SCHEDULED]
    assert hosts, (
        f"no workflow other than {SCHEDULED} runs {GATE_COMMAND} or the {MARKER}-marked scenarios"
    )
    assert len(hosts) == 1, (
        f"the liveness checks are spread over several workflows: {[wf.relpath for wf in hosts]}"
    )
    return hosts[0]


def fast_probe_job(wf: Workflow) -> str:
    """The job whose gate-liveness command runs exactly the three fast probes."""
    found = [
        job_id
        for job_id, job in wf.jobs.items()
        if any(set(probes_selected(argv)) == set(QUICK_PROBES) for argv in gate_invocations(job))
    ]
    assert len(found) == 1, (
        f"{wf.relpath}: expected one job running exactly {QUICK_PROBES}, found {found}"
    )
    return found[0]


def audit_job(wf: Workflow) -> str:
    """The job whose gate-liveness command runs the selection audit."""
    found = [
        job_id
        for job_id, job in wf.jobs.items()
        if any(AUDIT_PROBE in probes_selected(argv) for argv in gate_invocations(job))
    ]
    assert len(found) == 1, f"{wf.relpath}: expected one job running {AUDIT_PROBE}, found {found}"
    return found[0]


def needs_closure(wf: Workflow, job_id: str) -> set[str]:
    """Every job `job_id` waits for, directly or through another job."""
    seen: set[str] = set()
    pending = [job_id]
    while pending:
        needs = wf.jobs.get(pending.pop(), {}).get("needs") or []
        for needed in [needs] if isinstance(needs, str) else needs:
            if needed not in seen:
                seen.add(needed)
                pending.append(needed)
    return seen


def job_level_limit(wf: Workflow, job_id: str) -> int | None:
    limit = wf.jobs[job_id].get("timeout-minutes")
    return None if limit is None else int(limit)


def limit_annotation(wf: Workflow, job_id: str) -> str:
    """The comments beside a job's own time limit: above the job, above the limit, on its line."""
    lines = wf.text.splitlines()
    job_line = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(rf"^  {re.escape(job_id)}:\s*(#.*)?$", line)
        ),
        None,
    )
    if job_line is None:
        return ""
    end = next(
        (i for i in range(job_line + 1, len(lines)) if re.match(r"^  \S", lines[i])), len(lines)
    )
    limit_line = next(
        (i for i in range(job_line + 1, end) if re.match(r"^    timeout-minutes:", lines[i])), None
    )
    parts = _comments_above(lines, job_line)
    if limit_line is not None:
        parts += _comments_above(lines, limit_line)
        inline = lines[limit_line].split("#", 1)
        parts += [inline[1].strip()] if len(inline) == 2 else []
    return "\n".join(parts)


def _comments_above(lines: list[str], index: int) -> list[str]:
    found = []
    i = index - 1
    while i >= 0 and lines[i].strip().startswith("#"):
        found.insert(0, lines[i].strip().lstrip("#").strip())
        i -= 1
    return found


def header_comment(relpath: str, root: Path = REPO_ROOT) -> str:
    """The comment block a workflow file opens with."""
    lines = (root / relpath).read_text(encoding="utf-8").splitlines()
    header = []
    for line in lines:
        if not line.strip().startswith("#") and line.strip():
            break
        header.append(line)
    return "\n".join(header)


# -- What a job's pytest invocations select -------------------------------------------------------


def _interpreter(root: Path) -> str:
    synced = root / SYNCED_PYTHON
    return str(synced) if synced.exists() else sys.executable


def _local_argv(argv: list[str], root: Path) -> list[str]:
    """A workflow's pytest invocation, run on this machine's interpreter."""
    if "pytest" in argv:
        rest = argv[argv.index("pytest") + 1 :]
    else:
        rest = argv[1:]
    return [_interpreter(root), "-m", "pytest", *rest]


@cache
def _collected(argv: tuple[str, ...], root: Path) -> frozenset[str]:
    command = [*_local_argv(list(argv), root), "--collect-only", "-q", "-n", "0"]
    command += ["-p", "no:cacheprovider", "--no-cov"]
    done = subprocess.run(
        command, cwd=root, capture_output=True, text=True, timeout=600, env=isolated_env()
    )
    if done.returncode not in (0, 5):
        raise AssertionError(
            f"collecting {' '.join(argv)} failed (exit {done.returncode}):\n{done.stdout[-3000:]}"
        )
    return frozenset(line.strip() for line in done.stdout.splitlines() if "::" in line)


def collected_by_job(wf: Workflow, job_id: str, root: Path = REPO_ROOT) -> frozenset[str]:
    nodes: set[str] = set()
    for argv in pytest_invocations(wf.jobs[job_id]):
        nodes |= _collected(tuple(argv), root)
    return frozenset(nodes)


def liveness_marked_scenarios(root: Path = REPO_ROOT) -> frozenset[str]:
    return _collected(("python", "-m", "pytest", "-m", MARKER, *SCENARIO_TREES), root)


def jobs_collecting(wf: Workflow, files: Iterable[str], root: Path = REPO_ROOT) -> set[str]:
    prefixes = tuple(f"{f}::" for f in files)
    return {
        job_id
        for job_id in wf.jobs
        if any(node.startswith(prefixes) for node in collected_by_job(wf, job_id, root))
    }


def scenario_jobs(wf: Workflow) -> list[str]:
    return [job_id for job_id, job in wf.jobs.items() if runs_the_liveness_scenarios(job)]


# -- Breaking one property of the liveness workflow, in a copy -----------------------------------


def _sub_in_lines(pattern: str, replacement: str, text: str, where: str) -> str:
    return "\n".join(
        re.sub(pattern, replacement, line) if re.search(where, line) else line
        for line in text.split("\n")
    )


def _first(pattern: str, replacement: str) -> Callable[[str], str]:
    return lambda text: re.sub(pattern, replacement, text, count=1)


# Each mutation breaks exactly one property and leaves the file otherwise byte-identical.
MUTATIONS: dict[str, Callable[[str], str]] = {
    "a write grant": lambda t: re.sub(r"\bcontents:\s*read\b", "contents: write", t),
    "a secret reached": lambda t: t.replace(
        SYNC_STEP, SYNC_STEP + ' --index-url "${{ secrets.LIVENESS_INDEX_TOKEN }}"'
    ),
    "a job without its own time limit": lambda t: re.sub(r"(?m)^    timeout-minutes:.*\n", "", t),
    "the command through another interpreter": lambda t: t.replace(
        f"{SYNCED_PYTHON} {GATE_COMMAND}", f"python3 {GATE_COMMAND}"
    ),
    "the scenarios without the marker": lambda t: _sub_in_lines(
        r"\s-m\s+(?:'[^']*liveness[^']*'|\"[^\"]*liveness[^\"]*\"|\S*liveness\S*)",
        "",
        t,
        r"pytest",
    ),
    "the two trees in one run": lambda t: _sub_in_lines(
        r"tests/acceptance\b", "tests/acceptance fitness/tests", t, r"pytest"
    ),
    "an action unpinned": _first(r"@[0-9a-f]{40}\b", "@v7"),
    "the selection audit beside the fast probes": lambda t: _sub_in_lines(
        r"--gate spawn-count\b", f"--gate spawn-count --gate {AUDIT_PROBE}", t, r"--gate"
    ),
    "the by-hand trigger dropped": lambda t: re.sub(r"(?m)^  workflow_dispatch:.*\n", "", t),
    "the weekly schedule made daily": _first(
        r"cron:\s*([\"']?)(\d{1,2} \d{1,2}) \* \* [0-7A-Za-z]{1,3}\1", r"cron: \1\2 * * *\1"
    ),
}

# Words a failure that names the broken property carries (in a test's name, its assertion or
# its message).
PROPERTY_WORDS: dict[str, tuple[str, ...]] = {
    "a write grant": ("permission", "grant", "write", "read-only"),
    "a secret reached": ("secret", "token"),
    "a job without its own time limit": ("timeout", "time limit", "time_limit"),
    "the command through another interpreter": (SYNCED_PYTHON, "interpreter", "synced"),
    "the scenarios without the marker": ("marker",),
    "the two trees in one run": ("fitness",),
    "an action unpinned": ("pin", "sha"),
    "the selection audit beside the fast probes": (AUDIT_PROBE, "selection audit", "audit"),
    "the by-hand trigger dropped": ("workflow_dispatch", "dispatch", "by hand", "manual"),
    "the weekly schedule made daily": ("weekly", "cron", "schedule"),
}


def invariant_tests_of(wf: Workflow, root: Path = REPO_ROOT) -> list[str]:
    """Test files outside the outer loop that read the liveness workflow by its file name."""
    outer = ("tests/acceptance/", "tests/e2e/")
    found = []
    for tree in ("tests", "scripts"):
        for path in sorted((root / tree).rglob("test_*.py")):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(outer):
                continue
            if wf.basename in path.read_text(encoding="utf-8", errors="replace"):
                found.append(rel)
    return found


@dataclass(frozen=True)
class TestRun:
    exit_code: int
    output: str


def run_tests(copy: RepoCopy, files: list[str]) -> TestRun:
    command = [_interpreter(copy.root), "-m", "pytest", *files, "-q", "--tb=short", "-n", "0"]
    command += ["--no-cov", "-p", "no:cacheprovider"]
    env = isolated_env()
    env.pop("PYTEST_ADDOPTS", None)
    done = subprocess.run(
        command, cwd=copy.root, capture_output=True, text=True, timeout=600, env=env
    )
    return TestRun(done.returncode, done.stdout + done.stderr)


def without_liveness_jobs(text: str) -> str:
    """The scheduled workflow's text with every job that runs a liveness check cut out."""
    data = yaml.safe_load(text)
    doomed = [job_id for job_id, job in data.get("jobs", {}).items() if runs_a_liveness_check(job)]
    lines = text.split("\n")
    kept = []
    skipping = False
    for line in lines:
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*(#.*)?$", line)
        if header:
            skipping = header.group(1) in doomed
        elif re.match(r"^\S", line):
            skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


# -- Running a job's steps locally ---------------------------------------------------------------

_UNSAFE_STEP = re.compile(r"\bsudo\b|\buv sync\b|\bapt(-get)?\b|\bbrew\b")


@dataclass(frozen=True)
class JobLog:
    text: str
    scenario_step_exit: int | None  # None: the scenarios step was cut
    skipped_steps: tuple[str, ...] = field(default=())
    failed: bool = False  # a step failed or was cut: the job concludes failure


def ensure_synced_environment(copy: RepoCopy) -> None:
    """Give the copy `.venv/bin/python` (this interpreter's environment) when it has none."""
    venv = copy.path(".venv")
    if venv.exists() or sys.prefix == sys.base_prefix:
        return
    venv.symlink_to(Path(sys.prefix))
    with copy.path(".git/info/exclude").open("a", encoding="utf-8") as exclude:
        exclude.write("\n.venv\n")


def _step_env(wf: Workflow, job: Mapping, step: Mapping) -> dict[str, str]:
    merged: dict[str, str] = {}
    for scope in (wf.data.get("env") or {}, job.get("env") or {}, step.get("env") or {}):
        merged.update({k: str(v) for k, v in scope.items() if "${{" not in str(v)})
    return merged


def _runs_after(step: Mapping, failed: bool, cut: bool) -> bool:
    condition = str(step.get("if", ""))
    if cut:
        return "always()" in condition
    if failed:
        return any(word in condition for word in ("always()", "failure()", "!cancelled()"))
    return "failure()" not in condition or "always()" in condition


def run_job_locally(
    copy: RepoCopy,
    wf: Workflow,
    job_id: str,
    *,
    extra_env: Mapping[str, str],
    cut_when: Path | None = None,
    timeout: float = 900,
) -> JobLog:
    """Run a job's `run:` steps in order in `copy`, as the runner would, and return its log.

    With `cut_when`, the step that runs the scenarios is cut the way a time limit cuts it (an
    interrupt, then a terminate, then a kill) once that file exists.
    """
    ensure_synced_environment(copy)
    job = wf.jobs[job_id]
    log: list[str] = []
    skipped: list[str] = []
    failed = cut = False
    scenario_exit: int | None = None
    for step in job.get("steps", []):
        text = step.get("run")
        label = str(step.get("name") or text or step.get("uses"))
        if not text:
            continue
        if not _runs_after(step, failed, cut):
            continue
        if _UNSAFE_STEP.search(str(text)):
            skipped.append(label)
            continue
        env = {**isolated_env(), **_step_env(wf, job, step), **extra_env}
        is_scenarios = any(
            selects_the_marker(argv) for argv in pytest_invocations({"steps": [step]})
        )
        output, code = _run_step(
            copy.root, str(text), env, cut_when if is_scenarios else None, timeout
        )
        log.append(f"##[step] {label}\n{output}")
        if is_scenarios:
            scenario_exit = code
        if code is None:
            cut = True
        elif code != 0:
            failed = True
    return JobLog("\n".join(log), scenario_exit, tuple(skipped), failed or cut)


def _run_step(
    root: Path, text: str, env: dict[str, str], cut_when: Path | None, timeout: float
) -> tuple[str, int | None]:
    proc = subprocess.Popen(
        ["bash", "-e", "-c", text],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    if cut_when is None:
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _cut(proc)
            output, _ = proc.communicate()
            return output, None
        return output, proc.returncode
    deadline = time.monotonic() + timeout
    while not cut_when.exists() and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    time.sleep(1)
    _cut(proc)
    output, _ = proc.communicate()
    return output, None


def _cut(proc: subprocess.Popen) -> None:
    """End a step as a runner's time limit does: interrupt, then terminate, then kill."""
    for sig, grace in ((signal.SIGINT, 7.5), (signal.SIGTERM, 2.5), (signal.SIGKILL, 5)):
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue


_SIZE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:[KMGTP]i?B?|bytes)\b|\b\d{5,}\b")
_FREE = re.compile(r"\b(?:free|avail(?:able)?)\b", re.IGNORECASE)


def disk_reading_positions(log: str) -> list[int]:
    """Character offsets of the lines that report a free-space figure."""
    lines = log.split("\n")
    offsets = []
    position = 0
    for i, line in enumerate(lines):
        window = lines[max(0, i - 2) : i + 1]
        if _SIZE.search(line) and any(_FREE.search(w) for w in window):
            offsets.append(position)
        position += len(line) + 1
    return offsets
