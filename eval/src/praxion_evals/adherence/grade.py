"""Grade one finished session: read its evidence once, then score each named check.

:func:`evidence_from_recording` is the one impure step: it parses the recorded
stream and asks ``git`` what the session changed in the scratch repository.
:func:`grade` is then a function of that evidence alone and returns exactly one
status: ``Errored`` when infrastructure failed, ``NotMeasured`` when the main
session never spawned the role, otherwise ``Measured`` with one outcome per check.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

from praxion_evals.adherence.catalog import role_check
from praxion_evals.adherence.checks_common import judge_check
from praxion_evals.adherence.model import (
    Binds,
    CheckDef,
    CheckErrored,
    CheckOutcome,
    DoesNotBind,
    Errored,
    JudgedCheck,
    Measured,
    MechanicalCheck,
    NotApplicable,
    NotMeasured,
    RepoFacts,
    Role,
    SessionEvidence,
    SessionSetup,
    SessionStatus,
    TaskFacts,
)
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.live.scenarios import _is_authored  # drops hook and toolchain byproducts
from praxion_evals.live.session import (
    SessionEnvelope,
    SessionRun,
    ToolUse,
    parse_stream,
    session_error,
)

SPAWN_TOOLS = frozenset({"Agent", "Task"})  # the tool's name before Claude Code 2.1.63
GIT_TIMEOUT_S = 60
# A synchronous spawn's result ends with a harness trailer after the role's own text.
_AGENT_TRAILER = re.compile(r"^agentId:", re.MULTILINE)
LAUNCH_STUB_PREFIX = "Async agent launched"

# ---------------------------------------------------------------------------
# Reading the evidence
# ---------------------------------------------------------------------------


def evidence_from_recording(
    *,
    role: Role,
    envelope: str,
    repo_root: Path,
    fixture_commit: str,
    sandbox: Path,
    plugin_copy: Path,
    slug: str,
    exit_code: int | None,
    timed_out: bool,
    forced_stop: bool = False,
    judging: bool = False,
    fetchable_page: bool = False,
    planted_instruction: str | None = None,
    planted_effect: str | None = None,
    external_api_docs: str | None = None,
) -> SessionEvidence:
    """Everything a grader may look at, from the stream text and the scratch repository."""
    parsed = parse_stream(envelope)
    spawn_id = _spawn_id(parsed, role)
    return SessionEvidence(
        role=role,
        slug=slug,
        envelope=parsed,
        exit_code=exit_code,
        timed_out=timed_out,
        sandbox=sandbox,
        plugin_copy=plugin_copy,
        spawn_id=spawn_id,
        role_tool_uses=_role_tool_uses(parsed, spawn_id),
        role_return=_role_return(parsed, spawn_id),
        repo=read_repo(repo_root, fixture_commit, slug),
        facts=TaskFacts(
            forced_stop=forced_stop,
            judging=judging,
            fetchable_page=fetchable_page,
            planted_instruction=planted_instruction,
            planted_effect=planted_effect,
            external_api_docs=external_api_docs,
        ),
    )


def _spawn_id(envelope: SessionEnvelope, role: str) -> str | None:
    for use in envelope.tool_uses:
        spawned = use.input.get("subagent_type")
        if (
            use.name in SPAWN_TOOLS
            and use.parent_tool_use_id is None
            and isinstance(spawned, str)
            and spawned.split(":")[-1] == role
        ):
            return use.id
    return None


def _role_tool_uses(envelope: SessionEnvelope, spawn_id: str | None) -> tuple[ToolUse, ...]:
    return tuple(
        use for use in envelope.tool_uses if spawn_id and use.parent_tool_use_id == spawn_id
    )


def _role_return(envelope: SessionEnvelope, spawn_id: str | None) -> str | None:
    """The role's own return: its Agent tool result, never the main session's relay.

    A background spawn answers the tool call with a launch stub; the role's return
    then arrives as the task notification that names the same tool-use id.
    """
    if spawn_id is None:
        return None
    result = envelope.tool_results.get(spawn_id)
    if result is not None and not result.startswith(LAUNCH_STUB_PREFIX):
        return _AGENT_TRAILER.split(result, maxsplit=1)[0].rstrip()
    for notification in envelope.task_notifications:
        if notification.tool_use_id == spawn_id and notification.status == "completed":
            return notification.summary
    return None


# --- the scratch repository -------------------------------------------------


class GitReadError(RuntimeError):
    """``git`` could not answer a question about the scratch repository."""


def read_repo(repo_root: Path, fixture_commit: str, slug: str) -> RepoFacts:
    """What the session changed since the fixture commit, read from the repository itself."""
    changed, deleted = _tracked_changes(repo_root, fixture_commit)
    untracked = _git_lines(repo_root, "ls-files", "--others", "--exclude-standard", "-z")
    # The slug directory may be ignored by the fixture; the durable output lives there.
    untracked += _git_lines(repo_root, "ls-files", "--others", "-z", "--", f".ai-work/{slug}")
    paths = sorted({path for path in (*changed, *untracked) if _is_authored(path)})
    return RepoFacts(
        files={path: _text_of(repo_root / path) for path in paths},
        deleted=frozenset(path for path in deleted if _is_authored(path)),
        new_commits=tuple(
            _git(repo_root, "log", "--format=%s", f"{fixture_commit}..HEAD").splitlines()
        ),
        stash_entries=tuple(_git(repo_root, "stash", "list").splitlines()),
    )


def _tracked_changes(repo_root: Path, fixture_commit: str) -> tuple[list[str], list[str]]:
    """Paths whose working-tree content differs from the fixture commit: changed, deleted."""
    fields = _git_lines(repo_root, "diff", "--name-status", "-z", "--no-renames", fixture_commit)
    changed, deleted = [], []
    for status, path in zip(fields[0::2], fields[1::2], strict=True):
        (deleted if status == "D" else changed).append(path)
    return changed, deleted


def _text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _git(repo_root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo_root), "-c", "core.quotepath=off", *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=False,
    )
    if done.returncode != 0:
        raise GitReadError(f"git {' '.join(args)} failed in {repo_root}: {done.stderr.strip()}")
    return done.stdout


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    """Fields of a NUL-separated ``git`` listing."""
    return [field for field in _git(repo_root, *args).split("\0") if field]


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def grade(
    evidence: SessionEvidence,
    check_names: Sequence[str],
    judge: JudgeClient | None,
    setup: SessionSetup | None,
    *,
    real_home: Path | None = None,
) -> SessionStatus:
    """The session's one status. ``real_home``, when given, arms the real-home leak scan.

    ``judge`` rates the judged checks; given none, they are withheld as not requested.
    """
    failure = _infrastructure_error(evidence, setup, real_home)
    if failure is not None:
        return failure
    if evidence.spawn_id is None:
        return NotMeasured(f"the main session never spawned the {evidence.role}", setup)
    checks = [role_check(evidence.role, name) for name in check_names]
    outcomes = {check.name: _outcome(check, evidence, judge) for check in checks}
    return Measured.for_checks(
        check_names,
        outcomes,
        first_request_tokens(evidence),
        setup,
        role_return=_recorded_return(evidence),
    )


RECORDED_RETURN_CHARS = (
    4_000  # a conformant return is a few hundred; this keeps a runaway one legible
)
CLIPPED_NOTE = "\n[clipped by the recorder]"


def _recorded_return(evidence: SessionEvidence) -> str | None:
    """The role's return as graded, so a failed return check can be read from the record."""
    text = evidence.role_return
    if text is None or len(text) <= RECORDED_RETURN_CHARS:
        return text
    return text[:RECORDED_RETURN_CHARS] + CLIPPED_NOTE


def _infrastructure_error(
    evidence: SessionEvidence, setup: SessionSetup | None, real_home: Path | None
) -> Errored | None:
    run = SessionRun("", "", None if evidence.timed_out else evidence.exit_code)
    error = session_error(evidence.envelope, run, evidence.plugin_copy, real_home=real_home)
    if error is None:
        return None
    return Errored(kind=error.kind, detail=error.detail, setup=setup)


def _outcome(check: CheckDef, evidence: SessionEvidence, judge: JudgeClient | None) -> CheckOutcome:
    """Bind first; a check or a judge that raises is an errored check, never a pass or a withhold."""
    try:
        match check.binds(evidence.role, evidence.facts):
            case DoesNotBind(reason=reason):
                return NotApplicable(reason)
            case Binds():
                return _evaluate(check, evidence, judge)
            case binding:
                assert_never(binding)
    except Exception as error:
        return CheckErrored(f"{check.name} raised {type(error).__name__}: {error}")


def _evaluate(
    check: CheckDef, evidence: SessionEvidence, judge: JudgeClient | None
) -> CheckOutcome:
    match check:
        case MechanicalCheck():
            return check.evaluate(evidence)
        case JudgedCheck():
            return judge_check(check, evidence, judge)
        case _:
            assert_never(check)


def first_request_tokens(evidence: SessionEvidence) -> int | None:
    """The spawned role's own startup payload: input plus cache creation plus cache read."""
    usage = evidence.envelope.subagent_first_usage.get(evidence.spawn_id or "")
    return None if usage is None else usage.total
