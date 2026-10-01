"""Liveness probe for the observation-log hooks: does a spawn from a subdirectory still land?

In September 2026 a session working from a subdirectory of a checkout wrote its
rows beside that directory, not into the checkout's log, and the old hook checks,
which ran from the checkout root, stayed green. This probe builds a scratch
checkout outside the repository (a git repository with a state directory and a
`.ai-work/<slug>/` subdirectory), replays one foreground spawn to the registered
hooks with the session's working directory set to that subdirectory, and reads
the checkout's log back through the log owner's reader.

It passes only when the checkout's log holds exactly one `agent_start` row
carrying the spawn-prompt slug attribution and exactly one spawn row naming the
spawned agent and the task slug, both for the scratch project, and no state
directory exists below the subdirectory. Any other log, or no log, fails naming
what is missing or wrong. Nothing passes by default.

The scratch project and its home live in the system temp directory and are
removed afterwards; nothing is written to the repository or to its own log.
`judge` is pure. Because this module reads the log through the owner's reader it
is a declared consumer in the log registry. Imports are flat siblings, the layout
the mutation sensor reads; the reader is loaded from the checkout under test at
run time.

The spawn-count probe (`run_spawn_count`) shares the scratch project and the
replay. The hooks write the log from a known set of simulated spawns, all from the
subdirectory: two for the probe's task slug (one resumed once), one whose prompt
states no slug, one for another slug. It then runs the checkout's
`scripts/spawn_count.py` over that project and passes only when the reported
spawns, resumes and agent ids equal the known set exactly, and a slug no row names
is withheld (exit 2, `slug-unseen`) rather than answered with zero. A difference,
an undercount included, fails with both tallies. `judge_counted` and `judge_unseen`
are pure. The module `gate_probes.spawn_count` exposes this probe under the entry
point the CLI registers. Tests: `scripts/gate_probes/test_observation.py`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gate_probes import hook_replay
from gate_probes.verdict import GateId, Verdict

SLUG = "liveness-probe"
PROJECT_NAME = "liveness-project"
STATE_DIRNAME = ".ai-state"
SUBDIRECTORY = Path(".ai-work") / SLUG  # where the session works, below the checkout root

SLUG_ATTRIBUTION = "spawn-prompt"
SESSION_ID = "liveness-session"
AGENT_ID = "liveness-agent"
AGENT_TYPE = "praxion:implementer"
TOOL_USE_ID = "toolu_liveness_001"
GIT_TIMEOUT_S = 30

OTHER_SLUG = "liveness-other"
UNSEEN_SLUG = "liveness-unseen"  # named by no row, so the counter must withhold its answer
COUNTER = Path("scripts") / "spawn_count.py"
COUNTER_TIMEOUT_S = 30
COUNTER_WITHHELD_EXIT = 2
COUNTER_WITHHELD_CODE = "slug-unseen"
_OBSERVED_CHARS = 300

ReadRows = Callable[[Path], list[dict]]


@dataclass(frozen=True)
class Spawn:
    """One simulated foreground spawn: its prompt states `slug`, or none when None."""

    agent_id: str
    tool_use_id: str
    slug: str | None
    resumes: int = 0  # further SubagentStart events for the same agent

    @property
    def prompt(self) -> str:
        if self.slug is None:
            return "Liveness probe spawn that states no task slug."
        return f"Task slug: {self.slug}\n\nLiveness probe spawn."


@dataclass(frozen=True)
class Tally:
    spawns: int
    resumes: int
    agent_ids: tuple[str, ...]  # sorted


@dataclass(frozen=True)
class CounterAnswer:
    """What the counter did: `exit_code` is None when it never finished."""

    exit_code: int | None
    stdout: str
    stderr: str


# The situations that undercounted in production, all started from the subdirectory:
# a resumed spawn, a spawn naming no slug, a spawn for another slug.
HOOKS_SPAWN = Spawn(AGENT_ID, TOOL_USE_ID, SLUG)
SPAWNS = (
    Spawn("liveness-agent-a", "toolu_liveness_a", SLUG, resumes=1),
    Spawn("liveness-agent-b", "toolu_liveness_b", SLUG),
    Spawn("liveness-agent-c", "toolu_liveness_c", None),
    Spawn("liveness-agent-d", "toolu_liveness_d", OTHER_SLUG),
)


@dataclass(frozen=True)
class Session:
    """A scratch checkout and the session replaying hook events into it from its subdirectory."""

    repo_root: Path
    env: Mapping[str, str]
    project: Path
    directory: Path
    scratch: Path

    def replay(self, spawn: Spawn) -> None:
        """SubagentStart, the completed Agent call naming the slug, then each resume's start."""
        transcript = self.scratch / "session.jsonl"
        start = hook_replay.subagent_start_payload(
            session_id=SESSION_ID,
            cwd=self.directory,
            transcript_path=transcript,
            agent_id=spawn.agent_id,
            agent_type=AGENT_TYPE,
        )
        result = hook_replay.agent_result_payload(
            session_id=SESSION_ID,
            cwd=self.directory,
            transcript_path=transcript,
            tool_use_id=spawn.tool_use_id,
            prompt=spawn.prompt,
            agent_id=spawn.agent_id,
            agent_type=AGENT_TYPE,
        )
        for event, payload in (
            ("SubagentStart", start),
            ("PostToolUse", result),
            *(("SubagentStart", start),) * spawn.resumes,
        ):
            hook_replay.deliver(
                event,
                payload,
                repo=self.repo_root,
                project=self.project,
                cwd=self.directory,
                home=self.scratch / "home",
                base_env=self.env,
            )


def run(repo_root: Path, env: Mapping[str, str]) -> Verdict:
    """The probe against the checkout at `repo_root`, reading the log through its own reader."""
    try:
        read_rows = _reader_rows(repo_root)
    except ImportError as exc:
        reason = _failure("the log owner's reader importable from hooks/", f"ImportError: {exc}")
        return Verdict(gate=GateId.OBSERVATION_HOOKS, passed=False, reason=reason, elapsed_s=0.0)
    return replay_and_judge(repo_root, env, read_rows=read_rows)


def replay_and_judge(repo_root: Path, env: Mapping[str, str], *, read_rows: ReadRows) -> Verdict:
    return _timed_verdict(
        GateId.OBSERVATION_HOOKS, lambda: _hooks_reason(repo_root, env, read_rows)
    )


def run_spawn_count(repo_root: Path, env: Mapping[str, str]) -> Verdict:
    """The spawn-count probe: the hooks write the log, the checkout's counter tallies it."""
    return _timed_verdict(GateId.SPAWN_COUNT, lambda: _spawn_count_reason(repo_root, env))


def judge(
    rows: Sequence[Mapping[str, object]], *, project: str, strays: Sequence[str]
) -> str | None:
    """Why the log shows dead hooks; None when it shows live ones.

    `rows` are the checkout's log; `strays` are state directories found below the
    session's subdirectory (paths relative to the checkout).
    """
    starts = [row for row in rows if row.get("event_type") == "agent_start"]
    spawns = [
        row for row in rows if row.get("event_type") == "tool_use" and row.get("spawned_agent_id")
    ]
    expectations = (
        (
            "agent_start",
            starts,
            (("slug_attribution", SLUG_ATTRIBUTION, "slug_attribution"),
             ("project", project, "agent_start project")),
        ),
        (
            "spawn",
            spawns,
            (("task_slug", SLUG, "task_slug"), ("project", project, "spawn project")),
        ),
    )  # fmt: skip
    observed: list[str] = []
    dead = bool(strays)
    for label, matching, wanted in expectations:
        observed.append(f"{label} rows: {len(matching)}")
        wrong = _wrong_fields(matching[0], wanted) if len(matching) == 1 else []
        observed += wrong
        dead = dead or len(matching) != 1 or bool(wrong)
    if strays:
        observed.append(f".ai-state below the session directory: {', '.join(strays)}")
    return _failure(_expected(project), ", ".join(observed)) if dead else None


def _wrong_fields(row: Mapping[str, object], wanted: Sequence[tuple[str, str, str]]) -> list[str]:
    return [
        f"{name} {row.get(field)!r}" for field, value, name in wanted if row.get(field) != value
    ]


def _expected(project: str) -> str:
    return (
        "the checkout's log to hold one agent_start row "
        f"(slug_attribution {SLUG_ATTRIBUTION!r}) and one spawn row "
        f"(spawned_agent_id, task_slug {SLUG!r}), both for project {project!r}, "
        "and no .ai-state below the session directory"
    )


def _failure(expected: str, observed: str) -> str:
    return f"expected {expected}; observed {observed}"


def _timed_verdict(gate: GateId, reason_of: Callable[[], str | None]) -> Verdict:
    started = time.monotonic()
    try:
        reason = reason_of()
    except (OSError, ValueError) as exc:  # no readable registration, no git, no scratch space
        reason = _failure("the hook registration to be replayed", f"{type(exc).__name__}: {exc}")
    elapsed = time.monotonic() - started
    return Verdict(gate=gate, passed=reason is None, reason=reason or "", elapsed_s=elapsed)


@contextmanager
def _scratch_session(repo_root: Path, env: Mapping[str, str]) -> Iterator[Session]:
    scratch = Path(tempfile.mkdtemp(prefix="gate-liveness-"))
    try:
        project = scratch / PROJECT_NAME
        yield Session(repo_root, env, project, _build_project(project, env), scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _hooks_reason(repo_root: Path, env: Mapping[str, str], read_rows: ReadRows) -> str | None:
    with _scratch_session(repo_root, env) as session:
        session.replay(HOOKS_SPAWN)
        rows = read_rows(session.project / STATE_DIRNAME)
        strays = _stray_state(session.project, session.directory)
        return judge(rows, project=session.project.name, strays=strays)


def _build_project(project: Path, env: Mapping[str, str]) -> Path:
    """A git checkout with a state directory and the session's subdirectory; returns the latter."""
    session_dir = project / SUBDIRECTORY
    session_dir.mkdir(parents=True)
    (project / STATE_DIRNAME).mkdir()
    subprocess.run(
        ["git", "init", "-q"],
        cwd=project,
        env=dict(env),
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_S,
    )
    return session_dir


def _spawn_count_reason(repo_root: Path, env: Mapping[str, str]) -> str | None:
    with _scratch_session(repo_root, env) as session:
        for spawn in SPAWNS:
            session.replay(spawn)
        counted = judge_counted(_ask_counter(session, SLUG), expected_tally(SPAWNS))
        return counted or judge_unseen(_ask_counter(session, UNSEEN_SLUG))


def expected_tally(spawns: Sequence[Spawn]) -> Tally:
    """What the counter must report for `SLUG` over `spawns`."""
    owned = [spawn for spawn in spawns if spawn.slug == SLUG]
    return Tally(
        spawns=len(owned),
        resumes=sum(spawn.resumes for spawn in owned),
        agent_ids=tuple(sorted(spawn.agent_id for spawn in owned)),
    )


def judge_counted(answer: CounterAnswer, expected: Tally) -> str | None:
    """Why the counter's tally for the slug differs from `expected`; None when it matches."""
    reported = _reported_tally(answer)
    if reported == expected:
        return None
    observed = _tally_text(reported) if reported else f"no tally ({_describe(answer)})"
    return _failure(_tally_text(expected), observed)


def judge_unseen(answer: CounterAnswer) -> str | None:
    """Why the counter answered a slug no row names instead of withholding it; None when it withheld."""
    if answer.exit_code == COUNTER_WITHHELD_EXIT and COUNTER_WITHHELD_CODE in answer.stderr:
        return None
    expected = (
        f"exit {COUNTER_WITHHELD_EXIT} with {COUNTER_WITHHELD_CODE} for a slug no row names "
        "(withheld, never a zero tally)"
    )
    return _failure(expected, _describe(answer))


def _reported_tally(answer: CounterAnswer) -> Tally | None:
    if answer.exit_code != 0:
        return None
    try:
        report = json.loads(answer.stdout)
        return Tally(
            spawns=int(report["spawns"]),
            resumes=sum(int(count) for count in report["resumes"].values()),
            agent_ids=tuple(sorted(agent["agent_id"] for agent in report["agents"])),
        )
    except (ValueError, KeyError, TypeError, AttributeError):  # not the counter's JSON report
        return None


def _tally_text(tally: Tally) -> str:
    return f"spawns {tally.spawns}, resumes {tally.resumes}, agent ids {list(tally.agent_ids)}"


def _describe(answer: CounterAnswer) -> str:
    if answer.exit_code is None:
        return f"no answer from the counter within {COUNTER_TIMEOUT_S} s"
    said = _last_line(answer.stderr) if answer.stderr.strip() else " ".join(answer.stdout.split())
    said = said[:_OBSERVED_CHARS]
    return f"exit {answer.exit_code}: {said or 'no output'}"


def _last_line(text: str) -> str:
    """A traceback's exception line is its last."""
    return [line.strip() for line in text.splitlines() if line.strip()][-1]


def _ask_counter(session: Session, slug: str) -> CounterAnswer:
    """The checkout's counter over the scratch project: nothing from the real log or transcripts."""
    empty_projects = session.scratch / "projects"
    empty_projects.mkdir(exist_ok=True)
    command = [
        sys.executable,
        str(session.repo_root / COUNTER),
        "--slug", slug,
        "--json",
        "--no-context",
        "--projects-dir", str(empty_projects),
        "--repo-root", str(session.project),
    ]  # fmt: skip
    env = {
        **session.env,
        "PYTHONDONTWRITEBYTECODE": "1",
    }  # the probe leaves no file in the checkout
    try:
        done = subprocess.run(
            command,
            cwd=session.scratch,
            env=env,
            capture_output=True,
            text=True,
            timeout=COUNTER_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return CounterAnswer(None, "", "")
    return CounterAnswer(done.returncode, done.stdout, done.stderr)


def _stray_state(project: Path, session_dir: Path) -> list[str]:
    return sorted(path.relative_to(project).as_posix() for path in session_dir.rglob(STATE_DIRNAME))


def _reader_rows(repo_root: Path) -> ReadRows:
    """The log owner's `read_rows`, loaded from the checkout under test."""
    hooks_dir = str(repo_root / "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    from _observation_log import reader

    return reader.read_rows
