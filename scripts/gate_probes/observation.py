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
run time. Tests: `scripts/gate_probes/test_observation.py`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
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

ReadRows = Callable[[Path], list[dict]]


def run(repo_root: Path, env: Mapping[str, str]) -> Verdict:
    """The probe against the checkout at `repo_root`, reading the log through its own reader."""
    try:
        read_rows = _reader_rows(repo_root)
    except ImportError as exc:
        reason = _failure("the log owner's reader importable from hooks/", f"ImportError: {exc}")
        return Verdict(gate=GateId.OBSERVATION_HOOKS, passed=False, reason=reason, elapsed_s=0.0)
    return replay_and_judge(repo_root, env, read_rows=read_rows)


def replay_and_judge(repo_root: Path, env: Mapping[str, str], *, read_rows: ReadRows) -> Verdict:
    started = time.monotonic()
    reason = _probe(repo_root, env, read_rows)
    elapsed = time.monotonic() - started
    return Verdict(
        gate=GateId.OBSERVATION_HOOKS, passed=reason is None, reason=reason or "", elapsed_s=elapsed
    )


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


def _probe(repo_root: Path, env: Mapping[str, str], read_rows: ReadRows) -> str | None:
    scratch = Path(tempfile.mkdtemp(prefix="gate-liveness-hooks-"))
    try:
        project = scratch / PROJECT_NAME
        session_dir = _build_project(project, env)
        _replay_spawn(repo_root, env, project, session_dir, scratch)
        rows = read_rows(project / STATE_DIRNAME)
        return judge(rows, project=project.name, strays=_stray_state(project, session_dir))
    except (OSError, ValueError) as exc:  # no readable registration, no git, no scratch space
        return _failure("the hook registration to be replayed", f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


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


def _replay_spawn(
    repo_root: Path, env: Mapping[str, str], project: Path, session_dir: Path, scratch: Path
) -> None:
    """SubagentStart, then the completed Agent call whose prompt names the task slug."""
    transcript = scratch / "session.jsonl"
    prompt = f"Task slug: {SLUG}\n\nLiveness probe spawn."
    deliveries = (
        (
            "SubagentStart",
            hook_replay.subagent_start_payload(
                session_id=SESSION_ID,
                cwd=session_dir,
                transcript_path=transcript,
                agent_id=AGENT_ID,
                agent_type=AGENT_TYPE,
            ),
        ),
        (
            "PostToolUse",
            hook_replay.agent_result_payload(
                session_id=SESSION_ID,
                cwd=session_dir,
                transcript_path=transcript,
                tool_use_id=TOOL_USE_ID,
                prompt=prompt,
                agent_id=AGENT_ID,
                agent_type=AGENT_TYPE,
            ),
        ),
    )
    for event, payload in deliveries:
        hook_replay.deliver(
            event,
            payload,
            repo=repo_root,
            project=project,
            cwd=session_dir,
            home=scratch / "home",
            base_env=env,
        )


def _stray_state(project: Path, session_dir: Path) -> list[str]:
    return sorted(path.relative_to(project).as_posix() for path in session_dir.rglob(STATE_DIRNAME))


def _reader_rows(repo_root: Path) -> ReadRows:
    """The log owner's `read_rows`, loaded from the checkout under test."""
    hooks_dir = str(repo_root / "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    from _observation_log import reader

    return reader.read_rows
