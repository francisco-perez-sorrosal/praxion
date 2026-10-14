"""Grade one finished session: read its evidence once, then score each named check.

:func:`evidence_from_recording` is the one impure step: it parses the recorded
stream, reads the spawned role's transcript and asks ``git`` what the session changed
in the scratch repository.
:func:`grade` is then a function of that evidence alone and returns exactly one
status: ``Errored`` when infrastructure failed (a lean session whose kernel never
arrived included), ``NotMeasured`` when the main session never spawned the role,
otherwise ``Measured`` with one outcome per check.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, assert_never

import yaml

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
    KernelEvidence,
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
from praxion_evals.adherence.transcript import (
    RoleTranscript,
    TranscriptRead,
    TranscriptUnread,
    read_role_transcript,
    spawned_agent_id,
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

# The delivering hook heads every injected string with `[praxion <version> #<slot>]`. A
# sandbox keeps no observation log, so that marker, read from the role's transcript, is the
# eval's only delivery evidence. The shape is the hook's contract: change both together.
_KERNEL_MARKER = re.compile(r"\[praxion (?P<version>[^\s\]]+) #(?P<slot>\d+)\]")
# The transcript's attachment records of a spawn's hooks: one aggregate of every delivered
# string (what the harness renders into the role's context), and one log per hook command.
SPAWN_HOOK_EVENT = "SubagentStart"
AGGREGATE_ATTACHMENT = "hook_additional_context"
PER_HOOK_ATTACHMENT = "hook_success"
KERNEL_ACTIVE_STATUSES = frozenset({"trial", "switched"})  # the adoption statuses that deliver
KERNEL_LEDGER = Path(".ai-state") / "kernel_adoption.yaml"  # under the running plugin's root

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
    kernel_expected: bool = False,
    kernel_rows: Sequence[Mapping[str, Any]] | None = None,
    config_dir: Path | None = None,
) -> SessionEvidence:
    """Everything a grader may look at, from the stream, the role's transcript and the repository.

    ``kernel_expected`` says the session was owed an injected kernel. Its delivery evidence is
    ``kernel_rows`` when given, otherwise the markers in the role's transcript, kept under
    ``config_dir`` (the session's ``CLAUDE_CONFIG_DIR``), and in the stream's hook output.
    """
    parsed = parse_stream(envelope)
    spawn_id = _spawn_id(parsed, role)
    if kernel_rows is not None:
        rows, unread = tuple(kernel_rows), None
    else:
        found = _role_transcript(parsed, spawn_id, config_dir, repo_root)
        attachments = found.attachments if isinstance(found, TranscriptRead) else ()
        rows = kernel_marker_records(parsed, attachments)
        unread = found.reason if isinstance(found, TranscriptUnread) else None
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
        kernel=KernelEvidence(kernel_expected, rows, unread) if kernel_expected or rows else None,
    )


def _role_transcript(
    envelope: SessionEnvelope, spawn_id: str | None, config_dir: Path | None, repo_root: Path
) -> RoleTranscript | None:
    """The spawned role's transcript; None when no role was spawned or no config dir was given."""
    if spawn_id is None or config_dir is None:
        return None
    init_cwd = None if envelope.init is None else envelope.init.cwd
    result = envelope.final_result
    return read_role_transcript(
        config_dir,
        init_cwd or str(repo_root.resolve()),
        None if result is None else result.session_id,
        spawned_agent_id(envelope.tool_results.get(spawn_id)),
    )


def kernel_marker_records(
    envelope: SessionEnvelope, attachments: Sequence[Mapping[str, Any]] = ()
) -> tuple[Mapping[str, Any], ...]:
    """One record per kernel delivery marker, from the role's transcript, then the stream.

    ``attachments`` are the transcript's attachment records. A marker seen again (same version
    and slot) is not counted twice, so a stream that one day carries the spawn's hook output
    too adds nothing the transcript already showed. The id is the stream's own, so a flip
    record can name the session a marker was seen in; a stream that never reported a result
    has none to give.
    """
    result = envelope.final_result
    session = (
        {} if result is None or result.session_id is None else {"session_id": result.session_id}
    )
    found = [
        *((marker, "transcript") for marker in _transcript_markers(attachments)),
        *(
            (marker, "stream")
            for hook in envelope.hook_outputs
            for marker in _KERNEL_MARKER.finditer(hook.output)
        ),
    ]
    records: dict[tuple[str, int], Mapping[str, Any]] = {}
    for marker, source in found:
        version, slot = marker["version"], int(marker["slot"])
        records.setdefault(
            (version, slot), {**session, "kernel_version": version, "slot": slot, "source": source}
        )
    return tuple(records.values())


def _transcript_markers(attachments: Sequence[Mapping[str, Any]]) -> list[re.Match[str]]:
    """The marker heading each string the spawn's hooks delivered.

    The aggregate record lists every delivered string; the per-hook logs repeat them, so they
    are read only when no aggregate was recorded.
    """
    spawn_hooks = [record for record in attachments if record.get("hookEvent") == SPAWN_HOOK_EVENT]
    aggregate = [record for record in spawn_hooks if record.get("type") == AGGREGATE_ATTACHMENT]
    texts = (
        [text for record in aggregate for text in _strings(record.get("content"))]
        if aggregate
        else [
            _additional_context(record.get("stdout"))
            for record in spawn_hooks
            if record.get("type") == PER_HOOK_ATTACHMENT
        ]
    )
    return [marker for text in texts if (marker := _KERNEL_MARKER.match(text))]


def _strings(content: object) -> list[str]:
    return [item for item in content if isinstance(item, str)] if isinstance(content, list) else []


def _additional_context(stdout: object) -> str:
    """The string a hook's JSON output asked the harness to add; empty when it asked for none."""
    try:
        output = json.loads(stdout) if isinstance(stdout, str) else None
    except json.JSONDecodeError:
        return ""
    specific = output.get("hookSpecificOutput") if isinstance(output, dict) else None
    context = specific.get("additionalContext") if isinstance(specific, dict) else None
    return context if isinstance(context, str) else ""


def kernel_adopted(plugin_copy: Path, role: str) -> bool:
    """Whether the plugin copy's adoption ledger has ``role`` receiving a kernel at spawn.

    Mirrors the delivering hook: a ledger that is absent or does not read, or a role at no
    status, delivers nothing, so the lean arm of such a role is not owed a kernel.
    """
    try:
        ledger = yaml.safe_load((plugin_copy / KERNEL_LEDGER).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    roles = ledger.get("roles") if isinstance(ledger, dict) else None
    entry = roles.get(role) if isinstance(roles, dict) else None
    return isinstance(entry, dict) and entry.get("status") in KERNEL_ACTIVE_STATUSES


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
    if evidence.kernel is not None and evidence.kernel.missing:
        reason = evidence.kernel.unread or "its transcript holds no delivery marker"
        return Errored(
            kind="kernel_missing",
            detail=f"the {evidence.role} was owed an injected kernel and {reason}",
            setup=setup,
        )
    checks = [role_check(evidence.role, name) for name in check_names]
    outcomes = {check.name: _outcome(check, evidence, judge) for check in checks}
    return Measured.for_checks(
        check_names,
        outcomes,
        first_request_tokens(evidence),
        setup,
        role_return=_recorded_return(evidence),
        kernel_rows=() if evidence.kernel is None else evidence.kernel.rows,
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
