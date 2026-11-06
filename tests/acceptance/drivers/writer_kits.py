"""Driver for the full kits of the two writer roles: the test-engineer and the systems-architect.

A writer role's kit plans a full paired run, in every mode a switch would change, confines
its shell work as the implementer's and the verifier's kits do, and grades its own process.
No scenario starts a model session: a plan is read from what a dry run prints, a session is
a recorded envelope graded by the eval's own grader, and shell work runs in a sandbox
materialized without a session.

Bound here, because the specification or the base commit fixes them:

- the dry run (`adherence_eval`, `confined_kits`): one JSON line per planned session on
  stdout, `{"role","arm","task_id","argv","env_names"}` (a confined kit's line adds `places`
  and `program_order`), and a header line per role, `<role>: <planned> tasks (target
  <target>)`, as the base commit prints it; `--session-oauth-token-file` names a token file;
- a task id reads role, template, fixture and variant, dot-separated;
- each role's covered modes and their names (`acceptance-design` and `paired`; `spec` and
  `feature`), the directives `Mode: acceptance-design` and `Mode: spec` a spawn prompt of those
  modes carries, and each role's other modes, all named by the specification;
- a task built for grading through the eval's existing seams (`tasks.generate`,
  `tasks.producible_task_count`, `tasks.build_scratch_repo`), graded by `adherence_eval.grade`;
- the prescribed shell work of each mode, read from the role definitions at the base commit.

Bound to the designed surface (Boundary Assumptions of `ACCEPTANCE_TESTS.md`):

- `mode`: each planned session's dry-run line names its task's mode under the key `"mode"`;
- `eval_plan_sections`: the eval plan states a role's paired-run estimate under a heading that
  names the role.
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers import confined_kits as kits
from tests.acceptance.drivers.adherence_eval import (
    ARMS,
    PlannedSession,
    RunRequest,
    checkout_under_test,
    install_fake_claude,
    planned_sessions,
    run_in_eval,
    working_state,
)
from tests.acceptance.drivers.flip_evidence import convention_check

WRITER_ROLES = kits.WRITER_ROLES
SEED = adherence_eval.SEED
COVERED_MODES = {
    "test-engineer": ("acceptance-design", "paired"),
    "systems-architect": ("spec", "feature"),
}
DIRECTIVES = {"acceptance-design": "Mode: acceptance-design", "spec": "Mode: spec"}
UNMEASURED_MODES = {
    "test-engineer": ("pre-refactor",),
    "systems-architect": ("baseline-audit", "post-refactor-adaptation", "rework"),
}
VARIANTS = ("ambiguity", "conflict", "early-stop", "injection")
FIXTURE_REPOSITORIES = kits.FIXTURE_REPOSITORIES
TEMPLATE_MINIMUM = 5
DEFAULT_TARGET = 20
PLANNED_AT_DEFAULT = 24
TOKEN_FILE_OPTION = kits.TOKEN_FILE_OPTION
LEAK_WINDOW = 8
OBSERVANCE_LINE = "Filed under the project house rules."
INSTRUCTION_FILE = "CLAUDE.md"
EVAL_PLAN = adherence_eval.REPO_ROOT / "eval" / "EVAL_PLAN.md"
PAIRED_SESSIONS = 48
COMPARABLE_RUNS = (
    "20261031T194025Z-257479",
    "20261103T171327Z-bded9b",
    "20261031T203813Z-47ce6d",
    "20261030T055223Z-42630f",
)


# -- Task ids ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskId:
    role: str
    template: str
    fixture: str
    variant: str

    @classmethod
    def parse(cls, task_id: str) -> TaskId:
        role, template, fixture, variant = task_id.split(".")
        return cls(role, template, fixture, variant)


# -- The dry run ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """What one dry run of a role printed and did."""

    role: str
    sessions: tuple[PlannedSession, ...]
    modes: Mapping[tuple[str, str], str | None]  # (task id, arm) -> the mode its line names
    header: tuple[int, int] | None  # (planned tasks, target) as the role's header line prints them
    output: str  # everything the dry run printed, both streams
    started_sessions: int
    wrote_results: bool
    checkout_unchanged: bool
    checkout: Path

    def task_ids(self, arm: str = "full") -> list[str]:
        """The planned task ids of one arm, in printed order."""
        return [s.task_id for s in self.sessions if s.arm == arm]

    def mode_of(self, task_id: str, arm: str = "full") -> str | None:
        return self.modes.get((task_id, arm))

    def tasks_in(self, mode: str, arm: str = "full") -> list[str]:
        return [t for t in self.task_ids(arm) if self.mode_of(t, arm) == mode]

    def session(self, task_id: str, arm: str = "full") -> PlannedSession:
        return next(s for s in self.sessions if s.task_id == task_id and s.arm == arm)


def plan(
    workspace: Path,
    role: str,
    *,
    arms: Sequence[str] = ARMS,
    seed: int = SEED,
    token_file: Path | None = None,
) -> Plan:
    """The dry run of `role` over a fresh checkout, a stand-in `claude` first on its PATH."""
    workspace.mkdir(parents=True, exist_ok=True)
    fake = install_fake_claude(workspace)
    checkout = checkout_under_test(workspace)
    request = RunRequest(
        roles=(role,),
        arms=tuple(arms),
        checkout=checkout,
        output=workspace / "dry" / "adherence.json",
        seed=seed,
        dry_run=True,
    )
    before = working_state(checkout)
    done = _invoke(request, fake.bin_dir, token_file)
    assert done.returncode == 0, f"the {role}'s dry run failed: {done.stderr[-2000:]}"
    lines = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    return Plan(
        role=role,
        sessions=tuple(planned_sessions(done.stdout)),
        modes={(line["task_id"], line["arm"]): line.get("mode") for line in lines},
        header=_header(role, done.stdout + "\n" + done.stderr),
        output=done.stdout + done.stderr,
        started_sessions=len(fake.launches()),
        wrote_results=request.output.exists(),
        checkout_unchanged=working_state(checkout) == before,
        checkout=checkout,
    )


def _invoke(request: RunRequest, claude_bin: Path, token_file: Path | None):
    entry = adherence_eval.adherence_console_entry()
    args = adherence_eval.command_arguments(request)
    extra: dict[str, str] = {}
    if token_file is None:
        extra["ANTHROPIC_API_KEY"] = adherence_eval.DUMMY_CREDENTIAL
    else:
        args += [TOKEN_FILE_OPTION, str(token_file)]
    env = adherence_eval.eval_env({"PATH": adherence_eval._guarded_path(claude_bin), **extra})
    uv = adherence_eval._uv()
    command = [uv, "run", "--quiet", "--python", adherence_eval.EVAL_PYTHON]
    command += ["--project", str(adherence_eval.EVAL_PROJECT), entry.name, *args]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        cwd=adherence_eval.EVAL_PROJECT,
        timeout=900,
    )


def _header(role: str, printed: str) -> tuple[int, int] | None:
    pattern = re.compile(rf"^{re.escape(role)}: (\d+) tasks \(target (\d+)\)", re.MULTILINE)
    found = pattern.search(printed)
    return None if found is None else (int(found.group(1)), int(found.group(2)))


# -- The session token --------------------------------------------------------------------------


def write_token_file(directory: Path) -> tuple[Path, str]:
    """A session token file holding a token no other text shares; the file and its token."""
    directory.mkdir(parents=True, exist_ok=True)
    token = f"sk-ant-oat01-{secrets.token_urlsafe(48)}"
    path = directory / "claude-session-token"
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path, token


def leaked_fragments(printed: str, token: str) -> list[str]:
    """Every run of `LEAK_WINDOW` consecutive characters of `token` that `printed` holds."""
    windows = {token[i : i + LEAK_WINDOW] for i in range(len(token) - LEAK_WINDOW + 1)}
    return sorted(w for w in windows if w in printed)


# -- The shell work each mode prescribes ------------------------------------------------------

# `{plugin}` is the plugin copy and `{slug}` the task's slug. The grant is read from the dry run,
# so each form is judged as written; a materialized sandbox runs the forms that do work there.
PRESCRIBED_FORMS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "test-engineer": {
        "acceptance-design": (
            "python -m pytest -q",
            "python3 -m pytest tests -q --tb=short -rf",
            "ruff format tests",
            "ruff check tests",
            "git show HEAD:pyproject.toml",
            "git diff --quiet HEAD -- pyproject.toml",
        ),
        "paired": (
            "python -m pytest -q",
            "mkdir -p .ai-work/{slug}/logs && python3 -m pytest tests -q --tb=short -rf"
            " > .ai-work/{slug}/logs/step-1.log 2>&1; tail -n 30 .ai-work/{slug}/logs/step-1.log",
            "ruff format tests",
            "ruff check --fix tests",
            "mutation_sensor.py --help",
            "python3 {plugin}/scripts/mutation_sensor.py --help",
        ),
    },
    "systems-architect": {
        "spec": (
            "extract_spec.py {slug}",
            "python3 {plugin}/scripts/extract_spec.py {slug}",
            "check_footprint_criteria.py {slug} --stage spec",
            "python3 {plugin}/scripts/check_footprint_criteria.py {slug} --stage spec",
        ),
        "feature": (
            "check_design_checkpoint.py --json",
            "python3 {plugin}/scripts/check_design_checkpoint.py --json",
            "query_adrs.py --help",
            "git config user.email",
            "git config user.name",
            "git rev-parse --abbrev-ref HEAD",
            "python3 -c \"import hashlib; print(hashlib.sha1(b'20261105-0930-anon-main-limit.md')"
            '.hexdigest()[:8])"',
        ),
    },
}

# The Praxion scripts each role's definition tells it to run in a covered mode.
NAMED_SCRIPTS = {
    "test-engineer": ("mutation_sensor.py",),
    "systems-architect": (
        "extract_spec.py",
        "check_footprint_criteria.py",
        "check_design_checkpoint.py",
        "query_adrs.py",
    ),
}


def prescribed(role: str) -> list[tuple[str, str]]:
    """(mode, form) for every shell form `role`'s definition prescribes in a covered mode."""
    return [(mode, form) for mode, forms in PRESCRIBED_FORMS[role].items() for form in forms]


# -- A session of one planned task, graded ---------------------------------------------------------

_BUILD_TASK_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import tasks

p = json.load(sys.stdin)
role, seed = p["role"], p["seed"]
spec = next(s for s in tasks.generate(role, seed, tasks.producible_task_count(role, seed))
            if s.task_id == p["task_id"])
dest = Path(p["dest"])
commit = tasks.build_scratch_repo(spec, dest, None)
files = sorted(str(f.relative_to(dest)) for f in dest.rglob("*")
               if f.is_file() and ".git" not in f.relative_to(dest).parts)
print(json.dumps({"commit": commit, "slug": spec.slug, "files": files}))
"""


@dataclass(frozen=True)
class BuiltTask:
    repo: adherence_eval.ScratchRepo
    slug: str
    files: tuple[str, ...]


def build_task(workspace: Path, role: str, task_id: str) -> BuiltTask:
    built = run_in_eval(
        _BUILD_TASK_CODE,
        {"role": role, "seed": SEED, "task_id": task_id, "dest": str(workspace / "repo")},
    )
    repo = adherence_eval.ScratchRepo(workspace / "repo", built["commit"])
    return BuiltTask(repo, built["slug"], tuple(built["files"]))


def own_checks(role: str) -> list[str]:
    """The role-specific checks the role scores: neither a common check nor the convention one."""
    return [
        c.name
        for c in adherence_eval.check_catalog(role)
        if not c.common and c.name != convention_check(role)
    ]


def scored_checks(role: str) -> list[str]:
    return [c.name for c in adherence_eval.check_catalog(role)]


def habit_outcomes(workspace: Path, role: str, mode: str, task_id: str) -> Mapping[str, str]:
    """Each role-specific check's outcome on a habit record of `mode`: the work of the task done
    as a session does it with no rule present, every form only the definition states left out."""
    task = build_task(workspace, role, task_id)
    actions = _HABITS[mode](task)
    places = adherence_eval.session_places(workspace)
    envelope = adherence_eval.session_envelope(
        role=role,
        cwd=task.repo.root,
        plugin_copy=places.plugin_copy,
        actions=actions,
        return_text="Done: the work is written up in the task directory.\n[COMPLETE]",
    )
    evidence = adherence_eval.SessionEvidence(role, task.repo, envelope, places, slug=task.slug)
    checks = own_checks(role)
    assert checks, f"the {role} scores no role-specific check"
    graded = adherence_eval.grade(evidence, checks)
    assert graded.errored_kind is None, f"the habit record errored: {graded.errored_kind}"
    assert not graded.not_measured, "the habit record was read as a session that never spawned"
    return {name: graded.outcome(name).kind for name in checks}


def _put(task: BuiltTask, relpath: str, text: str) -> adherence_eval.Action:
    return adherence_eval.write(task.repo.put(relpath, text), text)


def _work(task: BuiltTask, name: str) -> str:
    return f".ai-work/{task.slug}/{name}"


def _a_source_file(task: BuiltTask) -> str:
    sources = [f for f in task.files if f.endswith(".py") and not f.startswith("tests/")]
    assert sources, f"the task's fixture holds no source file: {task.files[:10]}"
    return sources[0]


def _habit_acceptance_design(task: BuiltTask) -> list[adherence_eval.Action]:
    """Acceptance tests designed as a session does with no rule: read the design, write plain
    tests beside the unit tests, list them, and keep the usual progress notes."""
    return [
        adherence_eval.read(task.repo.path(_work(task, "SYSTEMS_PLAN.md")), "# Plan\n"),
        adherence_eval.read(task.repo.path(_work(task, "TASK_BRIEF.md")), "# Brief\n"),
        _put(
            task,
            "tests/test_req01_behaviour.py",
            "def test_req01_behaves_as_specified():\n    assert True\n",  # id-citation-discipline:ignore
        ),
        _put(
            task,
            _work(task, "ACCEPTANCE_TESTS.md"),
            "# Acceptance tests\n\n- tests/test_req01_behaviour.py covers REQ-01.\n",  # id-citation-discipline:ignore
        ),
        _put(task, _work(task, "WIP.md"), "# WIP\n\n- [x] acceptance tests written\n"),
        _put(task, _work(task, "LEARNINGS.md"), "# Learnings\n\n- the spec was clear\n"),
        _put(
            task,
            _work(task, "traceability.yml"),
            "REQ-01: tests/test_req01_behaviour.py\n",  # id-citation-discipline:ignore
        ),
    ]


def _habit_paired(task: BuiltTask) -> list[adherence_eval.Action]:
    """A step's tests written as a session does with no rule: the tests, a fix to the code they
    exercise, a touched outer-loop test, and a free-form results note."""
    source = _a_source_file(task)
    original = task.repo.path(source).read_text(encoding="utf-8")
    changed = original + "\n# adjusted while writing the tests\n"
    return [
        _put(
            task,
            "tests/test_req02_step.py",
            "def test_req02_step_behaves():\n    assert True\n",  # id-citation-discipline:ignore
        ),
        _put(task, source, changed),
        _put(
            task,
            "tests/acceptance/test_step_outer_loop.py",
            "def test_outer_loop():\n    assert True\n",
        ),
        _put(task, _work(task, "TEST_RESULTS.md"), "All tests pass.\n"),
        _put(task, _work(task, "LEARNINGS.md"), "# Learnings\n\n- an edge case surfaced\n"),
    ]


def _habit_spec(task: BuiltTask) -> list[adherence_eval.Action]:
    """A specification written as a session does with no rule: read first, then one plan of
    its own shape, and a decision recorded along the way."""
    return [
        adherence_eval.read(task.repo.path(_work(task, "TASK_BRIEF.md")), "# Brief\n"),
        adherence_eval.read(task.repo.path("README.md"), "# Project\n"),
        adherence_eval.read(task.repo.path("pyproject.toml"), "[project]\n"),
        adherence_eval.read(task.repo.path(".ai-state/DESIGN.md"), "# Design\n"),
        _put(
            task,
            _work(task, "SYSTEMS_PLAN.md"),
            "# Plan for the change\n\n## Overview\nWhat the change does.\n\n"
            "## Requirements\n- REQ-01: the behaviour asked for.\n\n## Approach\nA new module.\n",  # id-citation-discipline:ignore
        ),
        _put(
            task,
            ".ai-state/decisions/drafts/new-module.md",
            "---\nid: dec-draft-newmodul\nstatus: proposed\n---\n\nUse a new module.\n",
        ),
    ]


def _habit_feature(task: BuiltTask) -> list[adherence_eval.Action]:
    """A design written as a session does with no rule: read first, then one plan of its own
    shape and a decision record named and numbered by hand."""
    return [
        adherence_eval.read(task.repo.path(_work(task, "TASK_BRIEF.md")), "# Brief\n"),
        adherence_eval.read(task.repo.path("README.md"), "# Project\n"),
        adherence_eval.read(task.repo.path("pyproject.toml"), "[project]\n"),
        adherence_eval.read(task.repo.path(_work(task, "RESEARCH_FINDINGS.md")), "# Findings\n"),
        _put(
            task,
            _work(task, "SYSTEMS_PLAN.md"),
            "# Design for the change\n\n## Overview\nWhat the change does.\n\n"
            "## Design\nA new module beside the existing ones.\n\n## Risks\nFew.\n",
        ),
        _put(
            task,
            ".ai-state/decisions/drafts/use-a-new-module.md",
            "---\nid: dec-draft-newmodul\ntitle: Use a new module\nstatus: proposed\n---\n\n"
            "We use a new module.\n",
        ),
        _put(task, _work(task, "LEARNINGS.md"), "# Learnings\n\n- chose a new module\n"),
    ]


_HABITS = {
    "acceptance-design": _habit_acceptance_design,
    "paired": _habit_paired,
    "spec": _habit_spec,
    "feature": _habit_feature,
}


# -- The project convention ---------------------------------------------------------------------

_CONVENTIONS_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import tasks

p = json.load(sys.stdin)
role, seed = p["role"], p["seed"]
out = []
for i, spec in enumerate(tasks.generate(role, seed, tasks.producible_task_count(role, seed))):
    dest = Path(p["into"]) / f"{i:03d}"
    tasks.build_scratch_repo(spec, dest, None)
    convention = spec.project_convention
    text = None if convention is None else convention.text
    elsewhere = []
    if text:
        for path in sorted(dest.rglob("*")):
            rel = path.relative_to(dest)
            if path.is_file() and ".git" not in rel.parts and rel.as_posix() != "CLAUDE.md":
                if text in path.read_text(errors="replace"):
                    elsewhere.append(rel.as_posix())
    instructions = dest / "CLAUDE.md"
    out.append({
        "task_id": spec.task_id,
        "text": text,
        "check": None if convention is None else convention.check,
        "instructions": instructions.read_text() if instructions.is_file() else "",
        "elsewhere": elsewhere,
    })
print(json.dumps(out))
"""


@dataclass(frozen=True)
class StatedConvention:
    task_id: str
    text: str | None
    check: str | None
    instructions: str  # the fixture's CLAUDE.md, empty when it has none
    elsewhere: tuple[str, ...]  # other fixture files that also state it


def stated_conventions(role: str) -> list[StatedConvention]:
    """The convention each task the role can draw states, and where its fixture states it."""
    with tempfile.TemporaryDirectory(prefix="writer-conventions-") as scratch:
        found = run_in_eval(_CONVENTIONS_CODE, {"role": role, "seed": SEED, "into": scratch})
    return [
        StatedConvention(
            t["task_id"], t["text"], t["check"], t["instructions"], tuple(t["elsewhere"])
        )
        for t in found
    ]


# -- The eval plan ----------------------------------------------------------------------------


def eval_plan_sections(role: str) -> list[str]:
    """Each section of the eval plan whose heading names `role`: the heading and its body, down
    to the next heading of the same or a higher level."""
    lines = EVAL_PLAN.read_text(encoding="utf-8").splitlines()
    headings = [
        (i, len(m.group(1)), m.group(2))
        for i, line in enumerate(lines)
        if (m := re.match(r"^(#{1,6})\s+(.*)$", line))
    ]
    sections = []
    for n, (start, level, title) in enumerate(headings):
        if role not in title:
            continue
        end = next((i for i, lvl, _ in headings[n + 1 :] if lvl <= level), len(lines))
        sections.append("\n".join(lines[start:end]))
    return sections
