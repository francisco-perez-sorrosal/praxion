"""Structural invariants for the gate-liveness workflow.

`.github/workflows/gate-liveness.yml` is the weekly proof that the gates still bite on known
input. It is worth nothing if it quietly stops being weekly, gains a write grant or a secret,
loses a job's time limit, runs the gate command from the wrong interpreter, drifts onto an
unmarked scenario, mixes the two test trees in one run, unpins an action, runs the slow selection
audit beside the fast probes, or has one job wait on another. Each property is one test, named
for it, so the failure says which one broke.

Every job's time limit also carries one `# sized:` line naming the reading it was sized from. The
three tests that check that arithmetic are red while the line is the placeholder
`pending the measurement step`, so a placeholder cannot survive to merge.

Scope: parsed YAML, command text and comment lines only. Whether the jobs run on GitHub is
proven only by a live dispatch.
"""

from __future__ import annotations

import math
import re
import shlex
import tomllib
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = PROJECT_ROOT / ".github/workflows/gate-liveness.yml"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"

GATE_COMMAND = "scripts/check_gates_bite.py"
SYNCED_INTERPRETER = ".venv/bin/python"
SYNC_STEP = "uv sync --frozen"
FAST_PROBES = frozenset({"mutation-sensor", "observation-hooks", "spawn-count"})
SELECTION_AUDIT = "selection-audit"
ALL_PROBES = FAST_PROBES | {SELECTION_AUDIT}
LIVENESS_MARKER = "liveness"
SCENARIO_TREES = frozenset({"tests/e2e", "tests/acceptance"})
READ_ONLY_GRANT = {"contents": "read"}
PYTEST_OPTIONS_WITH_A_VALUE = frozenset({"-m", "-n", "-p", "-k", "-c", "-o"})

SHA_PIN = re.compile(r"@[0-9a-f]{40}$")
# minute hour day-of-month month day-of-week, one day of the week by number (0-7) or
# three-letter name: once a week.
WEEKLY_CRON = re.compile(r"^\d{1,2} \d{1,2} \* \* (?:[0-7]|[A-Za-z]{3})$")
PYTEST_LINE = re.compile(r"\bpytest\b")
SHELL_OPERATOR = re.compile(r"&&|\|\||;|\|")
CLAUDE_COMMAND = re.compile(r"(?:^|[\s;&|(])claude(?:\s|$)")
# Matched against the YAML dump, which has no comments, so prose cannot trip it. `\bsecrets\b`
# and `github\W+token` also catch `secrets['X']`, `toJSON(secrets)`, `secrets: inherit` and
# `github['token']`, not only the dotted forms.
SECRET_OR_SESSION = re.compile(
    r"\bsecrets\b|github\W+token|GITHUB_TOKEN|GH_TOKEN|ANTHROPIC_|claude-code-action|anthropics/"
)

# The `# sized:` arithmetic. The runner's own setup varies by minutes, so no limit is under the
# floor; no limit passes the ceiling (a job whose limit would is split), which leaves room under
# the runner's 6-hour job maximum for the 80-percent re-size trigger.
PENDING = "pending the measurement step"
BOUND_KEY = "selection-audit-timeout-seconds"
SIZED_MARGIN = Fraction(3, 2)
JOB_LIMIT_FLOOR_MINUTES = 10
JOB_LIMIT_CEILING_MINUTES = 240
SCENARIO_STEP_HEADROOM_MINUTES = 2  # a cut scenario step leaves the report step this long
CLI_ALLOWANCE_SECONDS = 360  # what the gate command may take beyond the audit's declared bound
JOB_SIZED_FIELDS = (
    "measured",
    "commit",
    "where",
    "step",
    "scale",
    "setup",
    "fixed",
    "margin",
    "limit",
)
BOUND_SIZED_FIELDS = ("step", "scale", "margin", "bound")
SIZED_UNITS = {
    "step": "s",
    "scale": "",
    "setup": "s",
    "fixed": "s",
    "margin": "",
    "limit": "min",
    "bound": "s",
}


# -- Triggers, grants, secrets, time limits ----------------------------------------------------


def test_the_workflow_runs_weekly_on_a_cron_schedule() -> None:
    # PyYAML reads the bare `on:` key as boolean True.
    schedule = _workflow()[True].get("schedule") or []
    crons = [str(entry.get("cron", "")).strip() for entry in schedule]
    # Two weekly crons are a twice-weekly schedule, which is not weekly either.
    assert len(crons) == 1, f"the workflow needs exactly one weekly cron schedule: {crons}"
    assert WEEKLY_CRON.match(crons[0]), f"not a weekly cron schedule: {crons[0]}"


def test_the_workflow_can_be_dispatched_by_hand() -> None:
    assert "workflow_dispatch" in _workflow()[True], "workflow_dispatch trigger is missing"


def test_every_permission_grant_is_contents_read_and_nothing_more() -> None:
    workflow = _workflow()
    grants = {"workflow": workflow.get("permissions")}
    grants |= {job_id: job.get("permissions") for job_id, job in workflow["jobs"].items()}
    wrong = {holder: grant for holder, grant in grants.items() if grant != READ_ONLY_GRANT}
    assert not wrong, f"every permission grant must be {READ_ONLY_GRANT} (no write): {wrong}"


def test_no_job_reaches_a_secret_or_token_or_starts_an_assistant_session() -> None:
    workflow = _workflow()
    reached = sorted(set(SECRET_OR_SESSION.findall(yaml.safe_dump(workflow, width=math.inf))))
    sessions = [
        line
        for job in workflow["jobs"].values()
        for line in _run_lines(job)
        if CLAUDE_COMMAND.search(line)
    ]
    assert not reached, f"the workflow reaches a secret or token: {reached}"
    assert not sessions, f"the workflow starts an assistant session: {sessions}"


def test_every_job_has_a_timeout_of_its_own() -> None:
    unbounded = [
        job_id
        for job_id, job in _workflow()["jobs"].items()
        if not isinstance(job.get("timeout-minutes"), int) or job["timeout-minutes"] <= 0
    ]
    assert not unbounded, f"jobs without a job-level timeout-minutes: {unbounded}"


def test_no_job_declares_needs_on_another() -> None:
    waiting = [job_id for job_id, job in _workflow()["jobs"].items() if "needs" in job]
    assert not waiting, (
        f"no job may declare needs: on another, so none hides its conclusion: {waiting}"
    )


# -- What the jobs run -------------------------------------------------------------------------


def test_the_gate_command_runs_only_through_the_synced_interpreter_after_the_sync() -> None:
    misrun = {
        job_id: lines
        for job_id, job in _workflow()["jobs"].items()
        if (lines := _gate_misruns(job))
    }
    assert not misrun, (
        f"the gate command must run as '{SYNCED_INTERPRETER} {GATE_COMMAND}' after "
        f"'{SYNC_STEP}' (the synced interpreter): {misrun}"
    )


def test_the_selection_audit_never_runs_beside_the_fast_probes() -> None:
    together = [
        job_id for job_id, job in _workflow()["jobs"].items() if _audit_beside_fast_probes(job)
    ]
    assert not together, (
        f"the selection audit needs a time limit of its own, never the fast probes' job: {together}"
    )


def test_every_pytest_line_selects_the_liveness_marker_in_the_scenario_trees_only() -> None:
    strays = [
        line for line in _all_pytest_lines() if not _selects_the_marker_in_scenario_trees(line)
    ]
    assert not strays, (
        f"every pytest line must select the '{LIVENESS_MARKER}' marker and name only "
        f"{sorted(SCENARIO_TREES)}: {strays}"
    )


def test_no_pytest_line_names_the_fitness_tree() -> None:
    # tests/ and fitness/tests/ in one invocation collide on the `tests` package name (td-302).
    mixed = [line for line in _all_pytest_lines() if "fitness" in line]
    assert not mixed, f"a pytest line names the fitness tree, which never shares a run: {mixed}"


def test_every_action_is_pinned_to_a_full_sha() -> None:
    unpinned = [
        step["uses"]
        for job in _workflow()["jobs"].values()
        for step in job["steps"]
        if "uses" in step and not SHA_PIN.search(step["uses"])
    ]
    assert not unpinned, f"actions not pinned to a full 40-hex SHA: {unpinned}"


# -- The sized time limits ---------------------------------------------------------------------


def test_each_scenario_step_limit_is_two_minutes_under_its_job_limit() -> None:
    problems = [
        problem
        for job_id, job in _workflow()["jobs"].items()
        for problem in _scenario_step_problems(job_id, job)
    ]
    assert not problems, "\n".join(problems)


def test_each_job_limit_follows_its_sized_line() -> None:
    comments = _sized_comments_by_job(WORKFLOW_FILE.read_text(encoding="utf-8"))
    problems = [
        problem
        for job_id, job in _workflow()["jobs"].items()
        for problem in _limit_problems(
            job_id, job.get("timeout-minutes"), _read_job_sizing(comments.get(job_id, ""))
        )
    ]
    assert not problems, "\n".join(problems)


def test_the_audit_job_limit_outlasts_the_declared_bound_and_the_cli_allowance() -> None:
    audit_jobs = [
        job_id
        for job_id, job in _workflow()["jobs"].items()
        if SELECTION_AUDIT in _gates_selected_by(job)
    ]
    assert len(audit_jobs) == 1, f"expected one job running {SELECTION_AUDIT}, found {audit_jobs}"
    job_id = audit_jobs[0]
    sizing = _read_job_sizing(
        _sized_comments_by_job(WORKFLOW_FILE.read_text(encoding="utf-8")).get(job_id, "")
    )
    limit = _workflow()["jobs"][job_id].get("timeout-minutes")
    problems = _audit_limit_problems(job_id, limit, sizing, _declared_bound())
    assert not problems, "\n".join(problems)


def test_the_declared_bound_follows_its_sized_line() -> None:
    sizing = _read_bound_sizing(_declared_bound_sized_comment())
    problems = _declared_bound_problems(sizing, _declared_bound())
    assert not problems, "\n".join(problems)


# -- Reading the workflow ----------------------------------------------------------------------


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))


def _command_lines(run_text: str) -> list[str]:
    """Each command of a `run:` text: comments dropped, continuations joined, split at operators."""
    joined = re.sub(r"\\\n\s*", " ", run_text)
    lines = (line.strip() for line in joined.splitlines())
    return [
        command
        for line in lines
        if line and not line.startswith("#")
        for command in map(str.strip, SHELL_OPERATOR.split(line))
        if command
    ]


def _run_lines(job: dict) -> list[str]:
    return [line for step in job["steps"] for line in _command_lines(step.get("run", ""))]


def _all_pytest_lines() -> list[str]:
    return [
        line
        for job in _workflow()["jobs"].values()
        for line in _run_lines(job)
        if PYTEST_LINE.search(line)
    ]


def _gates_selected_by(job: dict) -> frozenset[str]:
    """The probes a job's gate command runs: its `--gate` choices, all four when none."""
    selected: set[str] = set()
    for line in _run_lines(job):
        if GATE_COMMAND in line:
            selected |= set(re.findall(r"--gate[ =](\S+)", line)) or ALL_PROBES
    return frozenset(selected)


def _audit_beside_fast_probes(job: dict) -> bool:
    gates = _gates_selected_by(job)
    return SELECTION_AUDIT in gates and bool(gates & FAST_PROBES)


def _gate_misruns(job: dict) -> list[str]:
    """Each line that runs the gate command from anywhere but the synced environment, once built."""
    misrun = []
    synced = False
    for step in job["steps"]:
        text = step.get("run", "")
        proper = f"{SYNCED_INTERPRETER} {GATE_COMMAND}"
        misrun += [
            line
            for line in _command_lines(text)
            if GATE_COMMAND in line and not (synced and line.startswith(proper))
        ]
        synced = synced or SYNC_STEP in text
    return misrun


def _selects_the_marker_in_scenario_trees(line: str) -> bool:
    arguments = shlex.split(line)
    runner = next(
        (at for at, argument in enumerate(arguments) if Path(argument).name == "pytest"), None
    )
    if runner is None:  # `uv pip install pytest-cov` mentions pytest without running it
        return False
    options = iter(arguments[runner + 1 :])
    marker: str | None = None  # the last -m wins over the runner config's own
    paths: set[str] = set()
    for argument in options:
        if argument in PYTEST_OPTIONS_WITH_A_VALUE:
            value = next(options, "")
            marker = value if argument == "-m" else marker
        elif not argument.startswith("-"):
            paths.add(argument)
    return marker == LIVENESS_MARKER and bool(paths) and paths <= SCENARIO_TREES


def _scenario_step_problems(job_id: str, job: dict) -> list[str]:
    limit = job.get("timeout-minutes")
    if not isinstance(limit, int):
        return [f"{job_id}: no job-level timeout-minutes to measure a scenario step against"]
    wanted = limit - SCENARIO_STEP_HEADROOM_MINUTES
    return [
        f"{job_id}: step {step.get('name')!r} has timeout-minutes {step.get('timeout-minutes')}, "
        f"not {wanted} (job limit {limit} less {SCENARIO_STEP_HEADROOM_MINUTES})"
        for step in job["steps"]
        if PYTEST_LINE.search(step.get("run", "")) and step.get("timeout-minutes") != wanted
    ]


# -- The `# sized:` line ----------------------------------------------------------------------
#
#   # sized: measured=<date> commit=<12 hex> where=<local|runner> step=<s>s scale=<factor>
#   #        setup=<s>s fixed=<s>s margin=1.5 limit=<n>min [bound=<s>s]
#
# One comment block directly above a job's `timeout-minutes:` and above the bound key in
# pyproject.toml; the block may wrap over several comment lines.


@dataclass(frozen=True)
class JobSizing:
    step: Fraction
    scale: Fraction
    setup: Fraction
    fixed: Fraction
    margin: Fraction
    limit: Fraction
    bound: Fraction | None  # the audit job's alone


@dataclass(frozen=True)
class BoundSizing:
    step: Fraction
    scale: Fraction
    margin: Fraction
    bound: Fraction


@dataclass(frozen=True)
class Unsized:
    reason: str


def _read_job_sizing(comment: str) -> JobSizing | Unsized:
    numbers = _sized_numbers(comment, JOB_SIZED_FIELDS)
    if isinstance(numbers, Unsized):
        return numbers
    return JobSizing(
        step=numbers["step"],
        scale=numbers["scale"],
        setup=numbers["setup"],
        fixed=numbers["fixed"],
        margin=numbers["margin"],
        limit=numbers["limit"],
        bound=numbers.get("bound"),
    )


def _read_bound_sizing(comment: str) -> BoundSizing | Unsized:
    numbers = _sized_numbers(comment, BOUND_SIZED_FIELDS)
    if isinstance(numbers, Unsized):
        return numbers
    return BoundSizing(
        step=numbers["step"],
        scale=numbers["scale"],
        margin=numbers["margin"],
        bound=numbers["bound"],
    )


def _sized_numbers(comment: str, required: tuple[str, ...]) -> dict[str, Fraction] | Unsized:
    if not comment:
        return Unsized("no '# sized:' line directly above the limit")
    if PENDING in comment:
        return Unsized(f"the sized line is a placeholder: {PENDING}")
    fields = dict(re.findall(r"(\w+)=(\S+)", comment))
    missing = [name for name in required if name not in fields]
    if missing:
        return Unsized(f"the sized line lacks {missing}")
    try:
        return {
            name: Fraction(value.removesuffix(SIZED_UNITS[name]))
            for name, value in fields.items()
            if name in SIZED_UNITS
        }
    except ValueError as error:
        return Unsized(f"the sized line has a value that is not a number: {error}")


def _expected_limit_minutes(sizing: JobSizing) -> int:
    seconds = sizing.margin * (sizing.step * sizing.scale + sizing.setup) + sizing.fixed
    return max(JOB_LIMIT_FLOOR_MINUTES, math.ceil(seconds / 60))


def _limit_problems(job_id: str, timeout: object, sizing: JobSizing | Unsized) -> list[str]:
    if isinstance(sizing, Unsized):
        return [f"{job_id}: {sizing.reason}"]
    broken = {
        f"timeout-minutes {timeout} is not its sized limit {sizing.limit}": timeout != sizing.limit,
        f"the sized limit {sizing.limit} is not {_expected_limit_minutes(sizing)}, "
        f"max({JOB_LIMIT_FLOOR_MINUTES}, ceil((margin * (step * scale + setup) + fixed) / 60))": (
            sizing.limit != _expected_limit_minutes(sizing)
        ),
        f"margin {sizing.margin} is not {SIZED_MARGIN}": sizing.margin != SIZED_MARGIN,
        f"limit {sizing.limit} passes {JOB_LIMIT_CEILING_MINUTES} minutes, so the job is to be split": (
            sizing.limit > JOB_LIMIT_CEILING_MINUTES
        ),
    }
    return [f"{job_id}: {why}" for why, is_broken in broken.items() if is_broken]


def _audit_limit_problems(
    job_id: str, limit: object, sizing: JobSizing | Unsized, declared: int
) -> list[str]:
    if isinstance(sizing, Unsized):
        return [f"{job_id}: {sizing.reason}"]
    needed_seconds = declared + CLI_ALLOWANCE_SECONDS + sizing.setup
    outlasts = isinstance(limit, int) and limit * 60 >= needed_seconds
    broken = {
        f"its sized bound {sizing.bound} is not the declared {BOUND_KEY} {declared}": (
            sizing.bound != declared
        ),
        f"limit {limit} min is under the declared bound {declared} s plus the CLI allowance "
        f"{CLI_ALLOWANCE_SECONDS} s plus setup {sizing.setup} s ({needed_seconds} s)": not outlasts,
    }
    return [f"{job_id}: {why}" for why, is_broken in broken.items() if is_broken]


def _declared_bound_problems(sizing: BoundSizing | Unsized, declared: int) -> list[str]:
    if isinstance(sizing, Unsized):
        return [f"{BOUND_KEY}: {sizing.reason}"]
    expected = math.ceil(sizing.margin * sizing.step * sizing.scale / 60) * 60
    broken = {
        f"the sized bound {sizing.bound} is not ceil(margin * step * scale / 60) * 60 = {expected}": (
            sizing.bound != expected
        ),
        f"the declared {BOUND_KEY} {declared} is not its sized bound {sizing.bound}": (
            sizing.bound != declared
        ),
        f"margin {sizing.margin} is not {SIZED_MARGIN}": sizing.margin != SIZED_MARGIN,
    }
    return [f"{BOUND_KEY}: {why}" for why, is_broken in broken.items() if is_broken]


def _sized_comments_by_job(workflow_text: str) -> dict[str, str]:
    """The sized comment directly above each job's own `timeout-minutes:` line."""
    lines = workflow_text.splitlines()
    assert "jobs:" in lines, f"{WORKFLOW_FILE.name} has no top-level 'jobs:' line"
    comments: dict[str, str] = {}
    job_id = ""
    for index in range(lines.index("jobs:") + 1, len(lines)):
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", lines[index])
        if header:
            job_id = header.group(1)
        elif lines[index].startswith("    timeout-minutes:"):
            comments[job_id] = _sized_comment_above(lines, index)
    return comments


def _declared_bound_sized_comment() -> str:
    lines = PYPROJECT_FILE.read_text(encoding="utf-8").splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith(f"{BOUND_KEY} ")), None)
    assert index is not None, f"{PYPROJECT_FILE.name} has no '{BOUND_KEY}' key"
    return _sized_comment_above(lines, index)


def _declared_bound() -> int:
    table = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))["tool"]["praxion"][
        "gate-liveness"
    ]
    return table[BOUND_KEY]


def _sized_comment_above(lines: list[str], index: int) -> str:
    """The comment block ending at `lines[index - 1]`, from its `sized:` line down; empty if none."""
    block: list[str] = []
    for line in reversed(lines[:index]):
        if not line.lstrip().startswith("#"):
            break
        block.insert(0, line.lstrip().removeprefix("#").strip())
    start = next((i for i, text in enumerate(block) if text.startswith("sized:")), None)
    return "" if start is None else " ".join(block[start:])
