"""Driver for the confined kits of the adherence eval: the implementer's and the verifier's.

A confined kit's sessions may run the shell work their definitions prescribe (the
fixture's test runner, the formatter and the linter, git reads, and the Praxion scripts
the definitions name), inside a confinement the harness enforces. No scenario starts a
model session: the shell grant is read from what a dry run prints, and the shell work is
run in a sandbox materialized for a task without a session.

Bound here, because the specification or the base commit fixes them:

- the dry run and its printed sessions (`adherence_eval`): one JSON line per planned
  session, `{"role","arm","task_id","argv","env_names"}`, the tool grant being the values
  after `--allowedTools`;
- the option `--session-oauth-token-file`, which names the operator's session token file;
- the roles whose kits are confined (the implementer and the verifier), the Praxion
  scripts their definitions name, and the session credentials (`CLAUDE_CODE_OAUTH_TOKEN`,
  `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`), all named by the specification;
- the fixture repositories (`ledger-cli`, `notes-service`), each built for a task by the
  task generator (`tasks.generate`, `tasks.build_scratch_repo`, the seams `implementer_kit`
  reaches), and the test runner run there with no arguments under the runner's own
  interpreter;
- the grant every other role's sessions had at the base commit, frozen in
  `fixtures/eval_kit_grants_before.json` (`freeze_grants()` at that commit).

Unbound, raising until a driver-binding step binds them to the designed surface:

- `printed_confinement`: the confinement a printed session would be started with, read
  in the consumer's terms of `Confinement`;
- `planned_places`: where that session's sandbox, fixture repository, home and plugin copy
  sit;
- `materialize`: a task sandbox built without a session, with the environment and working
  directory a confined shell command of that session starts with.

A materialized sandbox's commands are run here as plain processes in that environment and
directory. The harness's confinement cannot be applied at no cost, so a scenario that needs
it reads it from `printed_confinement` instead; what `run_shell` proves is that a command
the grant lets through finds its program and does its work.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import (
    PlannedSession,
    RunRequest,
    checkout_under_test,
    install_fake_claude,
    planned_sessions,
    run_adherence_eval,
    run_in_eval,
)

CONFINED_ROLES = ("implementer", "verifier")
OTHER_ROLES = tuple(role for role in adherence_eval.ROLES if role not in CONFINED_ROLES)
ARMS = adherence_eval.ARMS
SESSION_CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
FIXTURE_REPOSITORIES = ("ledger-cli", "notes-service")
FROZEN_GRANTS = Path(__file__).resolve().parents[1] / "fixtures" / "eval_kit_grants_before.json"
TOKEN_FILE_OPTION = "--session-oauth-token-file"

# The Praxion scripts each definition names. `rework_manifest.py` has no command line: the
# verifier's definition names its row-id function, `compute_row_id(report_id, signature)`.
NAMED_SCRIPTS = {
    "implementer": ("check_id_citation_discipline.py", "resolve_test_scope.py"),
    "verifier": (
        "extract_spec.py",
        "check_test_results_shape.py",
        "check_state_ledgers.py",
        "rework_manifest.py",
    ),
}
MODULE_ONLY_SCRIPTS = frozenset({"rework_manifest.py"})
TOOLCHAIN = ("python", "python3", "pytest", "ruff")

# The shell work each confined role's definition prescribes, in the forms the specification lists: a
# bare name, an absolute path into the plugin copy, an inline interpreter call into a
# module, a chain, and output redirected into the task's directory. `{plugin}` is the plugin
# copy and `{slug}` the task's slug.
COMMON_FORMS = (
    "python -m pytest -q",
    "pytest -q",
    "python3 -m pytest -q",
    "ruff check .",
    "ruff format .",
    "git diff",
    "git log --oneline -5",
    "git status --short",
    "git show --stat HEAD",
    "ruff format . && ruff check . && python -m pytest -q",
    "mkdir -p .ai-work/{slug}/logs && python -m pytest -q > .ai-work/{slug}/logs/step-1.log 2>&1",
)
ROLE_FORMS = {
    "implementer": (
        "check_id_citation_discipline.py --files src",
        "python3 {plugin}/scripts/check_id_citation_discipline.py --files src",
        "resolve_test_scope.py --changed src --json",
        "python3 {plugin}/scripts/resolve_test_scope.py --changed src --json",
    ),
    "verifier": (
        "extract_spec.py {slug} --check",
        "python3 {plugin}/scripts/extract_spec.py {slug} --check",
        "check_test_results_shape.py .ai-work/{slug}/TEST_RESULTS.md",
        "python3 {plugin}/scripts/check_test_results_shape.py .ai-work/{slug}/TEST_RESULTS.md",
        "check_state_ledgers.py --check",
        "python3 -c \"import sys; sys.path.insert(0, '{plugin}/scripts');"
        " from rework_manifest import compute_row_id; print(compute_row_id('r', 's'))\"",
    ),
}


def prescribed_forms(role: str) -> tuple[str, ...]:
    return (*COMMON_FORMS, *ROLE_FORMS[role])


def fill(form: str, *, plugin: Path, slug: str) -> str:
    return form.format(plugin=shlex.quote(str(plugin)).strip("'"), slug=slug)


class UnboundDriverError(NotImplementedError):
    """Raised by a driver hook not yet bound to the designed surface."""


# -- The dry run -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DryRun:
    sessions: tuple[PlannedSession, ...]
    started_sessions: int  # sessions the stand-in `claude` was asked to start
    checkout: Path
    token_file: Path | None


def dry_run(
    workspace: Path,
    roles: Sequence[str],
    *,
    arms: Sequence[str] = ARMS,
    token_file: Path | None = None,
) -> DryRun:
    """The dry run of `roles` over a fresh checkout, a stand-in `claude` first on its PATH."""
    workspace.mkdir(parents=True, exist_ok=True)
    fake = install_fake_claude(workspace)
    checkout = checkout_under_test(workspace)
    request = RunRequest(
        roles=tuple(roles),
        arms=tuple(arms),
        checkout=checkout,
        output=workspace / "dry" / "adherence.json",
        dry_run=True,
    )
    if token_file is None:
        result = run_adherence_eval(request, fake.bin_dir)
    else:
        result = _dry_run_with_token_file(request, fake.bin_dir, token_file)
    assert result.exit_code == 0, f"the dry run failed: {result.stderr[-2000:]}"
    assert not request.output.exists(), "a dry run wrote a results file"
    return DryRun(
        tuple(planned_sessions(result.stdout)), len(fake.launches()), checkout, token_file
    )


def _dry_run_with_token_file(request: RunRequest, claude_bin: Path, token_file: Path):
    entry = adherence_eval.adherence_console_entry()
    args = [*adherence_eval.command_arguments(request), TOKEN_FILE_OPTION, str(token_file)]
    env = adherence_eval.eval_env({"PATH": adherence_eval._guarded_path(claude_bin)})
    uv = adherence_eval._uv()
    command = [uv, "run", "--quiet", "--python", adherence_eval.EVAL_PYTHON]
    command += ["--project", str(adherence_eval.EVAL_PROJECT), entry.name, *args]
    done = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        cwd=adherence_eval.EVAL_PROJECT,
        timeout=900,
    )
    return adherence_eval.CliResult(done.returncode, done.stdout, done.stderr)


def write_token_file(directory: Path) -> Path:
    """A session token file as `claude setup-token` leaves one: the token on one line."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "claude-session-token"
    path.write_text("sk-ant-oat01-acceptance-dummy-session-token-0000\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def granted_tools(session: PlannedSession) -> tuple[str, ...]:
    """The session's tool grant: every value after `--allowedTools`, up to the next option."""
    argv = list(session.argv)
    assert "--allowedTools" in argv, f"the session grants no tools: {argv}"
    start = argv.index("--allowedTools") + 1
    end = next((i for i in range(start, len(argv)) if argv[i].startswith("--")), len(argv))
    return tuple(argv[start:end])


def option_names(session: PlannedSession) -> tuple[str, ...]:
    """The option names on the session's command line, in order."""
    return tuple(arg for arg in session.argv if arg.startswith("-") and arg != "-")


def shell_grants(session: PlannedSession) -> tuple[str, ...]:
    return tuple(tool for tool in granted_tools(session) if tool.startswith("Bash"))


# -- The grant at the base commit ---------------------------------------------------------------


def frozen_grants() -> Mapping[str, Mapping[str, Mapping[str, list[str]]]]:
    """role -> arm -> {"tools", "options", "env_names"} as the base commit printed them."""
    raw = json.loads(FROZEN_GRANTS.read_text(encoding="utf-8"))
    return raw["roles"]


def frozen_with_token_file() -> Mapping[str, Mapping[str, list[str]]]:
    """role -> arm -> the session's environment names when the run is given a token file."""
    return json.loads(FROZEN_GRANTS.read_text(encoding="utf-8"))["with_token_file"]


def freeze_grants() -> dict:
    """What `fixtures/eval_kit_grants_before.json` holds; run once, at the base commit."""
    with tempfile.TemporaryDirectory(prefix="eval-kit-grants-") as scratch:
        printed = dry_run(Path(scratch), adherence_eval.ROLES).sessions
    roles: dict[str, dict[str, dict[str, list[str]]]] = {}
    for session in printed:
        seen = {
            "tools": list(granted_tools(session)),
            "options": list(option_names(session)),
            "env_names": sorted(session.env_names),
        }
        kept = roles.setdefault(session.role, {}).setdefault(session.arm, seen)
        assert kept == seen, f"{session.role}/{session.arm}: sessions of one kit differ"
    return {"_about": "Each role's printed grant at the base commit, per arm.", "roles": roles}


# -- The confinement a printed session would receive (unbound) ------------------------------------


@dataclass(frozen=True)
class Confinement:
    """A confined session's shell confinement, in the consumer's terms.

    `required`: a shell command runs only inside the confinement; `unconfined_fallback`: a
    command may run unconfined when the confinement cannot be established; `unconfined_retry`:
    a refused command may be retried unconfined; `approves_without_prompt`: a command inside
    the confinement runs without a permission prompt; `program_order`: the directories the
    session resolves a program name in, first match wins. The predicates answer, for a path or
    a host, whether a confined command is refused it; `shell_env_drops` names the variables a
    confined command's environment never carries; `approves` answers whether the grant lets a
    shell command run without a denial.
    """

    required: bool
    unconfined_fallback: bool
    unconfined_retry: bool
    approves_without_prompt: bool
    program_order: tuple[str, ...]
    write_refused: Callable[[str], bool]
    read_refused: Callable[[str], bool]
    network_refused: Callable[[str], bool]
    shell_env_drops: frozenset[str]
    approves: Callable[[str], bool]


def printed_confinement(session: PlannedSession) -> Confinement | None:
    """The confinement the printed session would be started with; None when it has none."""
    raise UnboundDriverError(
        "unbound: how a printed session states the shell confinement it would be started with"
        " is not bound yet"
    )


@dataclass(frozen=True)
class Places:
    """Where a planned session runs, as the dry run plans it."""

    run_root: Path
    plugin_copy: Path
    sandbox: Path  # the session's sandbox: its fixture repository, home and temp directory
    scratch: Path  # the fixture repository, the session's working directory
    home: Path  # the sandbox home
    tmp: Path
    slug: str


def planned_places(session: PlannedSession) -> Places:
    raise UnboundDriverError(
        "unbound: where a planned session's run root, sandbox, fixture repository, sandbox"
        " home and plugin copy sit is not bound yet"
    )


# -- A task sandbox materialized without a session (unbound) -------------------------------------


@dataclass(frozen=True)
class MaterializedSandbox:
    scratch: Path  # the fixture repository, committed, and the working directory
    home: Path  # the sandbox home
    tmp: Path
    plugin_copy: Path  # read-only
    run_root: Path
    shell_env: Mapping[str, str]  # what a confined shell command of the session starts with
    slug: str


def materialize(
    workspace: Path, role: str, *, operator_path_first: Path | None = None
) -> MaterializedSandbox:
    """A sandbox for the first task of `role`'s kit, both of its places and its shell environment.

    `operator_path_first` is a directory put first on the PATH of the operator's environment the
    runner is started from, as a copy of Praxion installed on the operator's machine would be.
    """
    raise UnboundDriverError(
        "unbound: a task sandbox built without a session, with the environment and working"
        " directory a confined shell command of that session starts with, is not bound yet"
    )


@dataclass(frozen=True)
class ShellRun:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def found_its_program(self) -> bool:
        lowered = self.stderr.lower()
        return self.exit_code not in (126, 127) and "command not found" not in lowered


def run_shell(sandbox: MaterializedSandbox, command: str, *, timeout: int = 300) -> ShellRun:
    done = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=sandbox.scratch,
        env=dict(sandbox.shell_env),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return ShellRun(command, done.returncode, done.stdout, done.stderr)


def resolved(sandbox: MaterializedSandbox, program: str) -> Path | None:
    """Where the sandbox's shell finds `program`, or None when it finds none."""
    found = run_shell(sandbox, f"command -v {shlex.quote(program)}")
    line = found.stdout.strip().splitlines()
    return Path(line[0]).resolve() if found.exit_code == 0 and line else None


def plant_decoys(directory: Path, names: Sequence[str]) -> Path:
    """An installed-elsewhere copy of each named script, which exits 3 and says so."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        decoy = directory / name
        decoy.write_text("#!/bin/sh\necho 'the operator install ran' >&2\nexit 3\n")
        decoy.chmod(0o755)
    return directory


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


# -- The runner's own environment ----------------------------------------------------------------

_RUNNER_CODE = """
import json, os, sys
print(json.dumps({"prefix": sys.prefix, "base_prefix": sys.base_prefix,
                  "interpreter": os.path.realpath(sys.executable)}))
"""


@dataclass(frozen=True)
class RunnerEnvironment:
    prefix: Path  # the runner's environment
    base_prefix: Path  # the interpreter installation it runs on
    interpreter: Path


@cache
def runner_environment() -> RunnerEnvironment:
    found = run_in_eval(_RUNNER_CODE, None)
    return RunnerEnvironment(
        Path(found["prefix"]), Path(found["base_prefix"]), Path(found["interpreter"])
    )


# -- The fixture repositories' own tests --------------------------------------------------------

_FIXTURE_TESTS_CODE = """
import json, os, subprocess, sys
from pathlib import Path
from praxion_evals.adherence import tasks

p = json.load(sys.stdin)
role, fixture, seed = p["role"], p["fixture"], p["seed"]
spec = next(s for s in tasks.generate(role, seed, tasks.producible_task_count(role, seed))
            if s.fixture_id == fixture)
dest = Path(p["into"])
tasks.build_scratch_repo(spec, dest, None)
home = Path(p["home"])
home.mkdir(parents=True, exist_ok=True)
env = {k: v for k, v in os.environ.items()
       if not k.startswith(("CLAUDE", "ANTHROPIC", "PRAXION", "PYTHONPATH", "VIRTUAL_ENV", "UV_"))}
env.update(HOME=str(home), PYTHONDONTWRITEBYTECODE="1")
done = subprocess.run([sys.executable, "-m", "pytest"], cwd=dest, env=env,
                      capture_output=True, text=True, timeout=300)
test_files = sorted(str(f.relative_to(dest)) for f in dest.rglob("test_*.py")
                    if ".git" not in f.parts)
print(json.dumps({"task_id": spec.task_id, "exit_code": done.returncode,
                  "stdout": done.stdout, "stderr": done.stderr, "test_files": test_files}))
"""


@dataclass(frozen=True)
class FixtureTestRun:
    task_id: str
    exit_code: int
    output: str
    test_files: tuple[str, ...]  # every test module the fixture holds

    def collected_files(self) -> set[str]:
        """The test modules the run's progress lines name (`path/test_x.py ....`)."""
        named = set()
        for line in self.output.splitlines():
            first = line.split(" ", 1)[0]
            if first.endswith(".py") and "/" in first:
                named.add(first)
        return named


def fixture_test_run(workspace: Path, role: str, fixture: str) -> FixtureTestRun:
    """`python -m pytest`, no arguments, at the root of `fixture` as built for a `role` task."""
    found = run_in_eval(
        _FIXTURE_TESTS_CODE,
        {
            "role": role,
            "fixture": fixture,
            "seed": adherence_eval.SEED,
            "into": str(workspace / "scratch"),
            "home": str(workspace / "home"),
        },
    )
    return FixtureTestRun(
        found["task_id"],
        found["exit_code"],
        found["stdout"] + found["stderr"],
        tuple(found["test_files"]),
    )


def real_home() -> Path:
    """The operator's own home directory, as the dry run's environment carries it."""
    return Path(os.environ["HOME"])
