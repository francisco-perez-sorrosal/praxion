"""Driver for how the adherence eval scores a pilot role's lean sessions.

The eval's existing seams are reached through `adherence_eval`; this module binds
what the lean-spawn pilot adds to them, as the Seam Contract of the implementation
plan fixes it:

- a lean session whose kernel never arrived is passed to `grade.evidence_from_recording`
  with `kernel_expected=True` and no `kernel_rows`; the eval reads delivery from the
  one-line marker that heads each injected string in the transcript (a sandboxed
  session writes no observation row the runner can read), handed over as marker
  records through the `kernel_rows` keyword, each carrying `kernel_version`;
- an isolation breach is the lean session reading a path under the operator's home;
  the operator's home is a scratch directory handed to the grader as `real_home`;
- a pilot task's fixture is read from `tasks.generate(role, seed, 1)`: the scratch
  repository `tasks.build_scratch_repo` builds, with the convention the task's
  `project_convention` states and the role check that reads it.

Scenarios describe sessions by what happened in them. The full arm of every pair is
a clean measured session, so only the lean side is synthesised: it decides every
count a scenario reads. Every call into the evaluation package runs in a subprocess
under the evaluation project's own `uv` environment (`adherence_eval.run_in_eval`).

Two stand-ins, because the check that reads a convention is not designed yet:

- a session that followed the project's convention shows it in what it wrote and in
  its return (both carry the convention's wording); one that did not, shows neither;
- `LeanSession.followed_project_convention=False` is a lean regression the grader can
  see without the pilot fixture: the lean session returns without a terminal marker,
  so the pointer-return check fails.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import run_in_eval

KERNEL_VERSION = "acceptance-kernel"
GRADED_CHECKS = ("C2",)  # the pointer return: what a lean regression stand-in breaks
CLEAN_RETURN = "Done; the findings are in the task directory.\n[COMPLETE]"
UNMARKED_RETURN = "Done; the findings are in the task directory."
CONVENTION_FILE = "CONVENTION_NOTES.md"


@dataclass(frozen=True)
class LeanSession:
    task_id: str
    kernel_row: bool = True  # the spawn left a kernel_injected row
    read_user_instruction_file: bool = False  # the role read ~/.claude/CLAUDE.md
    followed_project_convention: bool = True


@dataclass(frozen=True)
class LeanScoring:
    scored: frozenset[str]  # task ids whose pair was scored
    infrastructure_errors: frozenset[str]  # task ids whose pair errored as infrastructure
    lean_failures: frozenset[str]  # task ids whose lean session counts as a failure
    retried: frozenset[str]  # task ids the run launched again


_SCORE_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import grade, model, session_loop

p = json.load(sys.stdin)
statuses = []
for s in p["sessions"]:
    evidence = grade.evidence_from_recording(
        role=p["role"],
        envelope=s["envelope"],
        repo_root=Path(s["repo_root"]),
        fixture_commit=s["fixture_commit"],
        sandbox=Path(s["sandbox"]),
        plugin_copy=Path(s["plugin_copy"]),
        slug=p["slug"],
        exit_code=0,
        timed_out=False,
        kernel_rows=s["kernel_rows"],
        kernel_expected=True,
    )
    setup = model.SessionSetup(**s["setup"])
    status = grade.grade(evidence, p["checks"], None, setup, real_home=Path(p["real_home"]))
    statuses.append(model.status_to_json(status))
print(json.dumps({"statuses": statuses, "retryable": sorted(session_loop.RETRYABLE_ERRORS)}))
"""


def _marker_records(role: str, present: bool) -> list[dict[str, str]]:
    """The delivery evidence: one marker record per injected string's heading line."""
    return [{"kernel_version": KERNEL_VERSION, "role": role}] if present else []


def _setup(role: str, arm: str, task_id: str, commit: str) -> dict[str, object]:
    return {
        "arm": arm,
        "checkout_commit": commit,
        "role": role,
        "task_id": task_id,
        "template_id": adherence_eval.TEMPLATE_ID,
        "seed": adherence_eval.SEED,
    }


def _lean_session(role: str, session: LeanSession, workspace: Path, home: Path) -> dict:
    repo = adherence_eval.scratch_repo(workspace)
    places = adherence_eval.session_places(workspace)
    reads = home / ".claude" / "CLAUDE.md" if session.read_user_instruction_file else None
    actions = [adherence_eval.read(reads or repo.path("README.md"))]
    envelope = adherence_eval.session_envelope(
        role=role,
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=actions,
        return_text=CLEAN_RETURN if session.followed_project_convention else UNMARKED_RETURN,
    )
    return {
        "envelope": envelope,
        "repo_root": str(repo.root),
        "fixture_commit": repo.fixture_commit,
        "sandbox": str(places.sandbox),
        "plugin_copy": str(places.plugin_copy),
        "kernel_rows": _marker_records(role, session.kernel_row),
        "setup": _setup(role, "lean", session.task_id, repo.fixture_commit),
    }


def score_lean_pairs(role: str, sessions: tuple[LeanSession, ...]) -> LeanScoring:
    """Score a pilot role's pairs from synthetic lean sessions through the adherence eval."""
    with tempfile.TemporaryDirectory(prefix="lean-scoring-") as scratch:
        root = Path(scratch)
        home = root / "operator-home"
        built = [
            _lean_session(role, session, root / f"session-{i}", home)
            for i, session in enumerate(sessions)
        ]
        payload = {
            "role": role,
            "slug": adherence_eval.SLUG,
            "checks": list(GRADED_CHECKS),
            "real_home": str(home),
            "sessions": built,
        }
        result = run_in_eval(_SCORE_CODE, payload)
    scored, infrastructure, failures, retried = set(), set(), set(), set()
    for session, status in zip(sessions, result["statuses"], strict=True):
        task = session.task_id
        if status["kind"] == "measured":
            scored.add(task)
            if any(o["outcome"] == "failed" for o in status["outcomes"].values()):
                failures.add(task)
        elif status["kind"] == "errored":
            kind = status["error_kind"]
            (failures if kind == "isolation_breach" else infrastructure).add(task)
            if kind in result["retryable"]:
                retried.add(task)
    return LeanScoring(
        frozenset(scored), frozenset(infrastructure), frozenset(failures), frozenset(retried)
    )


@dataclass(frozen=True)
class PilotFixture:
    instructions: str  # the fixture's own CLAUDE.md
    other_files: Mapping[str, str]  # every other file of the fixture, by path
    convention: str  # the convention's wording as the fixture's CLAUDE.md states it
    convention_check: str  # the role check that reads whether the role followed it


_FIXTURE_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import tasks

p = json.load(sys.stdin)
task = tasks.generate(p["role"], p["seed"], 1)[0]
convention = task.project_convention
assert convention is not None, f"the {p['role']} pilot task states no project convention"
dest = Path(p["dest"])
commit = tasks.build_scratch_repo(task, dest)
files = {}
for path in sorted(dest.rglob("*")):
    relative = path.relative_to(dest).as_posix()
    if path.is_file() and relative.split("/")[0] != ".git":
        try:
            files[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
print(json.dumps({
    "commit": commit, "slug": task.slug, "files": files,
    "convention": convention.text, "check": convention.check,
}))
"""

_CONVENTION_GRADE_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import grade, model

p = json.load(sys.stdin)
evidence = grade.evidence_from_recording(
    role=p["role"],
    envelope=p["envelope"],
    repo_root=Path(p["repo_root"]),
    fixture_commit=p["fixture_commit"],
    sandbox=Path(p["sandbox"]),
    plugin_copy=Path(p["plugin_copy"]),
    slug=p["slug"],
    exit_code=0,
    timed_out=False,
    kernel_rows=p["kernel_rows"],
    kernel_expected=p["kernel_expected"],
)
setup = model.SessionSetup(**p["setup"])
print(json.dumps(model.status_to_json(grade.grade(evidence, [p["check"]], None, setup))))
"""


def _read_fixture(role: str, seed: int, dest: Path) -> dict:
    return run_in_eval(_FIXTURE_CODE, {"role": role, "seed": seed, "dest": str(dest)})


def pilot_task_fixture(role: str, seed: int) -> PilotFixture:
    """A pilot task's fixture and the project convention it writes in its own CLAUDE.md."""
    with tempfile.TemporaryDirectory(prefix="pilot-fixture-") as scratch:
        built = _read_fixture(role, seed, Path(scratch) / "fixture")
    files = dict(built["files"])
    instructions = files.pop("CLAUDE.md", "")
    return PilotFixture(instructions, files, built["convention"], built["check"])


def convention_outcome(role: str, arm: str, *, received_project_file: bool) -> str:
    """The convention check's outcome for a session that did or did not receive the file.

    A session that received the fixture's CLAUDE.md follows its convention; one that did
    not, cannot. Returns the check's outcome ("passed", "failed", ...), or the status
    kind ("errored: <kind>", "not measured") when the session was not graded.
    """
    with tempfile.TemporaryDirectory(prefix="convention-outcome-") as scratch:
        root = Path(scratch)
        built = _read_fixture(role, adherence_eval.SEED, root / "scratch")
        repo = adherence_eval.ScratchRepo(root / "scratch", built["commit"])
        places = adherence_eval.session_places(root)
        slug = built["slug"]
        notes = f".ai-work/{slug}/{CONVENTION_FILE}"
        wording = built["convention"] if received_project_file else "Nothing special."
        repo.put(notes, wording + "\n")
        envelope = adherence_eval.session_envelope(
            role=role,
            cwd=repo.root,
            plugin_copy=places.plugin_copy,
            actions=[adherence_eval.write(repo.path(notes), wording)],
            return_text=f"{wording}\n[COMPLETE]",
        )
        status = run_in_eval(
            _CONVENTION_GRADE_CODE,
            {
                "role": role,
                "envelope": envelope,
                "repo_root": str(repo.root),
                "fixture_commit": repo.fixture_commit,
                "sandbox": str(places.sandbox),
                "plugin_copy": str(places.plugin_copy),
                "slug": slug,
                "check": built["check"],
                "kernel_rows": _marker_records(role, arm == "lean"),
                "kernel_expected": arm == "lean",
                "setup": _setup(role, arm, f"{role}-convention", repo.fixture_commit),
            },
        )
    if status["kind"] == "measured":
        return status["outcomes"][built["check"]]["outcome"]
    return f"errored: {status['error_kind']}" if status["kind"] == "errored" else status["kind"]
