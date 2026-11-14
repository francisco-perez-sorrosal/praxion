"""Driver for the adherence eval's refactoring-mode tasks, reached from outside its package.

Bound here, through the adherence eval's own driver (`adherence_eval`): the console entry
`praxion-evals-adherence`, its `--dry-run` flag, the stand-in `claude` first on `PATH` that records
any launch instead of starting a paying session, and the dry run's printed lines (one planned
session each, its main-session prompt the argument after `-p`).

Bound to the designed seams of the paired run of the move: a task is graded by
`praxion_evals.adherence.checks_refactoring.grade_workspace(role, workspace, account)`, whose
result has a boolean `passed`; the dry run is the entry with `--axis refactoring-delivery`, one
`--arm preloaded` and one `--arm delivered`, each printed line gaining an `arm` key; an arm is
built by `praxion_evals.adherence.arms.build_refactoring_arm(checkout, arm, dest) -> Path`, from a
committed git checkout (the arm builder materializes it as the eval does). The eval package is
reached only through `adherence_eval.run_in_eval`; the account is handed over and no check reads it.

The committed task data a task is graded from
------------------------------------------------
Each role's tasks are the templates of its refactoring pool, the directories under
`eval/src/praxion_evals/adherence/fixtures/<role>/refactoring/`; a task is graded in every
template found there. Besides the files the other templates carry, each holds plain-file trees,
one per end state:

    start/                      the repository the session starts in: its tracked files
    end_states/clean/           the whole repository a session leaves when every checklist item holds
    end_states/<item>/          the same repository with exactly that one checklist item violated

`<item>` is the checklist item's text lower-cased, each run of other characters turned into one
`-` (`item_slug`): `the-tests-still-pass`, `behaviour-is-unchanged`, `every-call-site-is-re-wired`,
`no-dead-code-remains`, `no-transitional-shim-remains` (implementer) and
`characterization-tests-exist-before-any-structural-change`,
`characterization-tests-pin-behaviour-through-the-public-surface` (test-engineer). An end-state
tree is complete, not a patch, so a violation may delete or rename a file. A file name ending in
`.tmpl` loses that suffix wherever it is copied; code and anything a tool might mistake for live
configuration carry it, as in every template. A template whose repository is shared with a
`fixtures/repos` entry still keeps its own `start/`, so grading never depends on that entry.

The workspace the grader receives is a git repository: `start/` committed as its only commit,
then the working tree replaced by the chosen end state and left uncommitted. The grader therefore
sees the session's whole change as `git status` and `git diff` against `HEAD`, the way a real
session leaves its scratch repository, and reads nothing else.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers import refactoring_delivery as rd
from tests.acceptance.drivers.adherence_eval import PlannedSession, RunRequest
from tests.acceptance.drivers.kernel_sandbox import isolated_env

# The refactoring skill's verification checklist, per role, as the specification states it.
CHECKLIST = {
    "implementer": (
        "the tests still pass",
        "behaviour is unchanged",
        "every call site is re-wired",
        "no dead code remains",
        "no transitional shim remains",
    ),
    "test-engineer": (
        "characterization tests exist before any structural change",
        "characterization tests pin behaviour through the public surface",
    ),
}

FIXTURES_DIR = adherence_eval.EVAL_SRC / "praxion_evals" / "adherence" / "fixtures"
AXIS = "refactoring-delivery"
TEMPLATE_SUFFIX = ".tmpl"

ArmKind = Literal["preloaded", "delivered"]
ARM_KINDS: tuple[ArmKind, ArmKind] = ("preloaded", "delivered")


@dataclass(frozen=True)
class DryRun:
    sessions: tuple[PlannedSession, ...]
    launches: int  # sessions the stand-in `claude` saw start
    exit_code: int
    stderr: str


def dry_run(role: str, workspace: Path) -> DryRun:
    """Dry-run the adherence eval for `role` in its `full` arm, as an operator would."""
    fake = adherence_eval.install_fake_claude(workspace)
    request = RunRequest(
        roles=(role,),
        arms=("full",),
        checkout=adherence_eval.checkout_under_test(workspace),
        output=workspace / "results" / "adherence.json",
        dry_run=True,
    )
    result = adherence_eval.run_adherence_eval(request, fake.bin_dir)
    sessions = adherence_eval.planned_sessions(result.stdout) if result.exit_code == 0 else []
    return DryRun(tuple(sessions), len(fake.launches()), result.exit_code, result.stderr)


@dataclass(frozen=True)
class Grade:
    passed: bool


_GRADE_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import checks_refactoring

p = json.load(sys.stdin)
verdict = checks_refactoring.grade_workspace(p["role"], Path(p["workspace"]), p["account"])
print(json.dumps({"passed": bool(verdict.passed)}))
"""


def grade_refactoring_task(
    role: str, workspace: Path, *, broken: str | None, account: str
) -> Grade:
    """Grade the role's refactoring task from an end state, never from the session's own account.

    The end state is each pool template's clean one, or the one violating exactly the checklist
    item `broken` names; `account` stands in for the session's final message and is only handed
    over. The task passes only if every template of the pool passes, so a violation must fail in
    every template and the clean end state must pass in every template.
    """
    templates = refactoring_templates(role)
    grades = [_grade_template(role, template, workspace, broken, account) for template in templates]
    return Grade(passed=all(grades))


def refactoring_templates(role: str) -> tuple[Path, ...]:
    """The templates of the role's refactoring pool, by name."""
    pool = FIXTURES_DIR / role / "refactoring"
    assert pool.is_dir(), f"the committed task data is missing: {pool}"
    templates = tuple(sorted(entry for entry in pool.iterdir() if entry.is_dir()))
    assert templates, f"the committed task data is missing: no template in {pool}"
    return templates


def _grade_template(
    role: str, template: Path, workspace: Path, broken: str | None, account: str
) -> bool:
    repository = _repository_with_end_state(role, template, workspace / template.name, broken)
    payload = {"role": role, "workspace": str(repository), "account": account}
    graded = adherence_eval.run_in_eval(_GRADE_CODE, payload)
    return graded["passed"] is True


def item_slug(item: str) -> str:
    """The name of the end-state tree that violates the checklist item `item`."""
    return re.sub(r"[^a-z0-9]+", "-", item.lower()).strip("-")


def _repository_with_end_state(
    role: str, template: Path, workspace: Path, broken: str | None
) -> Path:
    assert broken is None or broken in CHECKLIST[role], f"not a {role} checklist item: {broken!r}"
    start = template / "start"
    end_state = template / "end_states" / ("clean" if broken is None else item_slug(broken))
    for tree in (start, end_state):
        assert tree.is_dir(), f"the committed task data is missing: {tree}"
    repository = workspace / "repository"
    _copy_tree(start, repository)
    _commit_all(repository, "the repository a session starts in")
    for entry in repository.iterdir():
        if entry.name != ".git":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    _copy_tree(end_state, repository)
    return repository


def _copy_tree(source: Path, dest: Path) -> None:
    """Copy every file of `source` under `dest`, a trailing `.tmpl` dropped from each name."""
    for file in sorted(source.rglob("*")):
        if file.is_file():
            relative = file.relative_to(source).as_posix().removesuffix(TEMPLATE_SUFFIX)
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)


def _commit_all(repository: Path, message: str) -> None:
    env = isolated_env(
        repository.parent / ".git-scratch",
        GIT_AUTHOR_NAME="fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
    )
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", message)):
        subprocess.run(
            ["git", *args], cwd=repository, env=env, check=True, capture_output=True, timeout=60
        )


@dataclass(frozen=True)
class PairedSession:
    arm: ArmKind
    task_id: str
    prompt: str


@dataclass(frozen=True)
class PairedDryRun:
    sessions: tuple[PairedSession, ...]
    launches: int


def dry_run_paired_move(role: str, workspace: Path) -> PairedDryRun:
    """Dry-run the paired run of the move for `role` through the adherence eval's entry.

    The run must succeed: a failing entry is a defect to read, not an empty plan to compare.
    """
    fake = adherence_eval.install_fake_claude(workspace)
    arguments = [
        str(adherence_eval.checkout_under_test(workspace)),
        *("--role", role, "--axis", AXIS),
        *(flag for arm in ARM_KINDS for flag in ("--arm", arm)),
        *("--output", str(workspace / "results" / "adherence.json"), "--dry-run"),
    ]
    result = _run_entry(arguments, fake.bin_dir)
    assert result.exit_code == 0, f"the paired dry run failed: {result.stderr[-2000:]}"
    planned = adherence_eval.planned_sessions(result.stdout)
    sessions = tuple(PairedSession(cast(ArmKind, s.arm), s.task_id, s.prompt) for s in planned)
    return PairedDryRun(sessions, len(fake.launches()))


def _run_entry(arguments: list[str], claude_bin: Path) -> adherence_eval.CliResult:
    """The console entry with `claude_bin/claude` first on `PATH`, as `run_adherence_eval` runs it.

    `RunRequest` cannot name an axis, and the adherence driver is not this module's to change, so
    the same command is assembled here from its parts; the stand-in check is the driver's own.
    """
    entry = adherence_eval.adherence_console_entry()
    env = adherence_eval.eval_env(
        {
            "PATH": adherence_eval._guarded_path(claude_bin),
            "ANTHROPIC_API_KEY": adherence_eval.DUMMY_CREDENTIAL,
        }
    )
    result = subprocess.run(
        [adherence_eval._uv(), "run", "--quiet", "--python", adherence_eval.EVAL_PYTHON]
        + ["--project", str(adherence_eval.EVAL_PROJECT), entry.name, *arguments],
        capture_output=True,
        text=True,
        env=env,
        cwd=adherence_eval.EVAL_PROJECT,
        timeout=900,
    )
    return adherence_eval.CliResult(result.returncode, result.stdout, result.stderr)


_BUILD_ARMS_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import arms

p = json.load(sys.stdin)
built = {
    arm: str(arms.build_refactoring_arm(Path(p["checkout"]), arm, Path(p["arms_dir"]) / arm))
    for arm in p["arms"]
}
print(json.dumps(built))
"""


def build_paired_move_arms(role: str, workspace: Path) -> dict[ArmKind, Path]:
    """One plugin installation per arm, built by the eval's own arm builder.

    The move changes both roles' definitions together, so the arms do not depend on `role`; the
    checkout they are built from is a committed copy of the plugin, which the builder materializes
    as it does a real checkout, and which stays untouched.
    """
    checkout = rd.new_installation(workspace / "checkout").root
    _commit_all(checkout, "a checkout of the plugin")
    payload = {"checkout": str(checkout), "arms_dir": str(workspace / "arms"), "arms": ARM_KINDS}
    built = adherence_eval.run_in_eval(_BUILD_ARMS_CODE, payload)
    return {arm: Path(built[arm]) for arm in ARM_KINDS}
