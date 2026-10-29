"""One headless main session of a move: reserve its budget, sandbox it, start it, settle it, read it.

``session_launch`` launches a role's session; this is the half a move shares with it and the
half a move owns. The shared pieces (the spend settlement, the envelope's model, the redacted
output tails, the ``Attempt`` result) are that module's own. The move's differences:

- the working directory is the task's fixture repository, built where the stand-in finds its task
  (a path component named by the task id); the arm travels as the plugin directory's path, the
  one plugin directory the session loads, and the prompt is the task's wording alone;
- the sandbox home is populated from the arm's copy by ``install_user_scope`` and from nothing
  else, then checked before anything starts: no plugin install, no rule that does not link into
  the arm's copy, no memory index, and the rendered user instructions the pinned digest names;
- the session environment is ``build_env``'s allowlist, and when the run names a session token
  file ``with_session_token`` swaps the API keys for that token, so a session bills the
  token's subscription and never the key. Nothing here builds an environment of its own.

The sandbox outlives the assessment (the session's record and the fixture are read from it) and
is removed after, unless the run keeps it.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from praxion_evals.adherence.infra_stop import EvidenceTail
from praxion_evals.adherence.model import Errored
from praxion_evals.adherence.moves import pinning
from praxion_evals.adherence.moves.model import MoveArm, Pinned
from praxion_evals.adherence.moves.tasks import MoveTask
from praxion_evals.adherence.session_launch import (
    DEFAULT_TAIL_CHARS,
    MS_PER_S,
    NO_OUTPUT,
    REAL_HOME,
    Attempt,
    resolved_model,
    settle,
    tails_of,
)
from praxion_evals.adherence.tasks import PERMISSION_MODE
from praxion_evals.adherence.transcript import transcript_dir_name
from praxion_evals.live.materialize import install_user_scope
from praxion_evals.live.results import Errored as LiveErrored
from praxion_evals.live.session import (
    SandboxPaths,
    SessionEnvelope,
    SessionRun,
    SessionSpec,
    build_env,
    parse_stream,
    run_session,
    session_error,
    with_session_token,
)
from praxion_evals.live.spend import SpendLedger

SESSIONS_DIRNAME = "sessions"
FIXTURES_DIRNAME = "fixture"
PLUGIN_INSTALLS_DIRNAME = "plugins"
RULES_DIRNAME = "rules"
RENDERED_INSTRUCTIONS = "CLAUDE.md"
RECORD_SUFFIX = ".jsonl"

# A main session works the repository with git and with files. Each git command gets its own
# narrow pattern, never a broad one (see ``live.session.PermissionMode``); staging and committing
# are granted whole, since how the session stages and commits is what a move measures.
GIT_COMMANDS = ("status", "diff", "log", "show", "add", "stage", "commit", "reset", "restore", "rm")
FILE_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep")
ALLOWED_TOOLS: tuple[str, ...] = (
    *FILE_TOOLS,
    *(
        pattern
        for command in GIT_COMMANDS
        for pattern in (f"Bash(git {command})", f"Bash(git {command} *)")
    ),
)


@dataclass(frozen=True)
class MoveLaunch:
    """What a session launch reads of the run; fixed for the whole run.

    ``ambient`` is the runner's environment, read once at the edge; ``session_token_file``, when
    the run names one, holds the token every session authenticates with.
    """

    run_root: Path
    pinned: Pinned
    session_budget_usd: float
    ambient: Mapping[str, str] = field(repr=False)
    session_token_file: Path | None = None
    keep_sandbox: bool = False
    tail_chars: int = DEFAULT_TAIL_CHARS


@dataclass(frozen=True)
class Finished:
    """A session that ran and can be graded, with everything the runner reads from it.

    ``record`` is the session's own record under the sandbox's config dir, ``None`` when the
    harness left none; the sandbox is removed once the assessment returns.
    """

    envelope: SessionEnvelope
    run: SessionRun
    record: Path | None
    repo: Path
    sandbox: Path


class SandboxError(ValueError):
    """A sandbox that is not what the arm's session may start in; names what leaks."""


def launch_session[R](
    launch: MoveLaunch,
    ledger: SpendLedger,
    task: MoveTask,
    arm: MoveArm,
    copy: Path,
    build_fixture: Callable[[Path], object],
    assess: Callable[[Finished], R],
) -> tuple[SpendLedger, Attempt[R]]:
    """Run ``task`` once under ``arm``'s ``copy`` in a fresh sandbox, assess it, and clean up.

    ``build_fixture`` builds the task's repository at the directory it is given. The budget is
    reserved first and a refusal starts nothing; a session that never started settles at nothing,
    one whose outcome is lost settles at the full budget.
    """
    budget = launch.session_budget_usd
    started_at, began = datetime.now(UTC).isoformat(), time.monotonic()

    def finish(
        result: R | Errored,
        charged: float,
        tails: EvidenceTail = NO_OUTPUT,
        model: str | None = None,
    ) -> Attempt[R]:
        if isinstance(result, Errored):
            result = replace(result, tails=tails)
        duration_ms = int((time.monotonic() - began) * MS_PER_S)
        return Attempt(result, charged, duration_ms, started_at, model)

    reserved = ledger.reserve(budget)
    if isinstance(reserved, LiveErrored):
        return ledger, finish(Errored("launch_refused", reserved.detail), 0.0)
    root = _new_sandbox_root(launch)
    try:
        try:
            spec, env, repo = _prepare(launch, task, arm, copy, build_fixture, root)
        except Exception as error:  # nothing was started, so nothing was spent
            return reserved.settle(budget, 0.0), finish(_refusal(error), 0.0)
        try:
            run = run_session(spec, env)
        except Exception as error:  # the process may have run and spent: charge the budget
            return reserved.settle(budget, None), finish(_crash(error), budget)
        settled, charged = settle(reserved, budget, run)
        tails, model = tails_of(run, env, launch.tail_chars), resolved_model(run)
        try:
            result = _assessed(run, root, repo, copy, assess)
            return settled, finish(result, charged, tails, model)
        except Exception as error:  # one unreadable session must not discard the paid run
            return settled, finish(_crash(error), charged, tails, model)
    finally:
        if not launch.keep_sandbox:
            shutil.rmtree(root, ignore_errors=True)


def session_env(launch: MoveLaunch, root: Path) -> dict[str, str]:
    """A session's environment: ``build_env``'s allowlist rooted at the sandbox, and the token
    file's token in place of the API keys when the run names one."""
    env = build_env(root, launch.ambient)
    if launch.session_token_file is None:
        return env
    return with_session_token(env, launch.session_token_file.read_text(encoding="utf-8"))


def sandbox_leak(root: Path, arm: MoveArm, copy: Path, pinned: Pinned) -> str | None:
    """What makes the sandbox other than ``arm``'s own, or ``None`` when it is exactly that."""
    paths = SandboxPaths(root)
    installs = paths.config_dir / PLUGIN_INSTALLS_DIRNAME
    if installs.exists():
        return f"the {arm} arm's sandbox holds an installed plugin ({installs})"
    copy_root = copy.resolve()
    for rule in sorted((paths.config_dir / RULES_DIRNAME).rglob("*")):
        # A rule is a link into the arm's copy; the plain directories that hold them are not rules.
        if (rule.is_symlink() or rule.is_file()) and not rule.resolve().is_relative_to(copy_root):
            return f"the {arm} arm's sandbox holds a rule outside its copy ({rule})"
    try:
        pinning.require_no_memory(paths.home, arm)
    except pinning.PinningError as error:
        return str(error)
    instructions = (paths.config_dir / RENDERED_INSTRUCTIONS).read_text(encoding="utf-8")
    if hashlib.sha256(instructions.encode()).hexdigest() != pinned.user_instructions:
        return f"the {arm} arm's sandbox renders user instructions other than the pinned ones"
    return None


def record_of(envelope: SessionEnvelope, repo: Path, config_dir: Path) -> Path | None:
    """The session's own record, where Claude Code keeps it; ``None`` when there is none to read."""
    final = envelope.final_result
    if final is None or final.session_id is None:
        return None
    cwd = envelope.init.cwd if envelope.init and envelope.init.cwd else str(repo.resolve())
    path = config_dir / "projects" / transcript_dir_name(cwd) / f"{final.session_id}{RECORD_SUFFIX}"
    return path if path.is_file() else None


# --- the steps of one launch ---


def _new_sandbox_root(launch: MoveLaunch) -> Path:
    parent = launch.run_root / SESSIONS_DIRNAME
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="s-", dir=parent))


def _prepare(
    launch: MoveLaunch,
    task: MoveTask,
    arm: MoveArm,
    copy: Path,
    build_fixture: Callable[[Path], object],
    root: Path,
) -> tuple[SessionSpec, dict[str, str], Path]:
    """Populate and check the sandbox, build the fixture, and name the session; nothing starts."""
    install_user_scope(copy, root)
    leak = sandbox_leak(root, arm, copy, launch.pinned)
    if leak is not None:
        raise SandboxError(leak)
    repo = root / FIXTURES_DIRNAME / task.task_id
    build_fixture(repo)
    spec = SessionSpec(
        prompt=task.wording,
        model=launch.pinned.model,
        effort=launch.pinned.effort,
        plugin_dir=copy.resolve(),
        cwd=repo,
        permission_mode=PERMISSION_MODE,
        max_budget_usd=launch.session_budget_usd,
        allowed_tools=ALLOWED_TOOLS,
    )
    return spec, session_env(launch, root), repo


def _assessed[R](
    run: SessionRun, root: Path, repo: Path, copy: Path, assess: Callable[[Finished], R]
) -> R | Errored:
    """The session's assessment, or the infrastructure error that keeps it from having one."""
    envelope = parse_stream(run.stdout)
    error = session_error(envelope, run, copy.resolve(), real_home=REAL_HOME)
    if error is not None:
        return Errored(error.kind, error.detail)
    record = record_of(envelope, repo, SandboxPaths(root).config_dir)
    return assess(Finished(envelope, run, record, repo, root))


def _refusal(error: Exception) -> Errored:
    """A launch that was refused before it started: a leaking sandbox is a breach, any other a crash."""
    if isinstance(error, SandboxError):
        return Errored("isolation_breach", str(error))
    return _crash(error)


def _crash(error: Exception) -> Errored:
    return Errored("evaluation_exception", f"{type(error).__name__}: {error}")
