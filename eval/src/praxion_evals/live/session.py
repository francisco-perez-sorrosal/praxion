"""One headless ``claude -p`` session: invocation, envelope parsing, verdicts.

Everything here is pure except :func:`run_session`, the single place a
``claude`` process is started. The session's argv and environment are built
from explicit inputs only — the environment from a closed allowlist — so no
ambient ``~/.claude`` file, installed plugin, MCP server or inherited
``CLAUDE_PLUGIN_ROOT``/``CLAUDECODE`` value can reach the measured layer.

The stream-json envelope is parsed once, at this boundary, into typed values;
isolation is judged from the harness's own ``init`` telemetry, never from what
the model says about itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

from praxion_evals.live.results import ErrorKind

CLAUDE_BINARY = "claude"
EMPTY_MCP_CONFIG = '{"mcpServers":{}}'
DEFAULT_TIMEOUT_S = 900
SUCCESS_SUBTYPE = "success"
BUILTIN_PLUGIN_SUFFIX = "@builtin"

# ``bypassPermissions`` is deliberately not representable: a session with
# unrestricted Bash could write outside its sandbox through absolute paths.
PermissionMode = Literal["default", "acceptEdits", "plan"]

PASS_THROUGH_KEYS = (
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "USER",
    "LOGNAME",
    "SHELL",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
)

# Side-effect-only hooks off through their own kill switches (one would relink
# the real ~/.claude; another writes a WAL into the fixture and posts events),
# plus harness noise. Context-injecting hooks stay on: they are the layer under test.
FIXED_SWITCHES = {
    "PRAXION_DISABLE_AUTO_COMPLETE": "1",
    "PRAXION_DISABLE_OBSERVABILITY": "1",
    "PRAXION_DISABLE_HOOK_CHAIN_HEAL": "1",
    "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "DISABLE_AUTOUPDATER": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}

# Hooks resolve ``python3`` from PATH; the runner's own interpreter imports
# PyYAML (the graders need it), so putting it first lets hook-delivered rules
# reach the session the way they reach a correctly installed operator session.
_RUNNER_INTERPRETER = Path(sys.executable)


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionSpec:
    prompt: str
    model: str
    effort: str
    plugin_dir: Path
    cwd: Path
    permission_mode: PermissionMode
    max_budget_usd: float
    allowed_tools: tuple[str, ...] = ()
    json_schema: Mapping[str, Any] | None = None
    forward_subagent_text: bool = False
    timeout_s: int = DEFAULT_TIMEOUT_S


@dataclass(frozen=True)
class SandboxPaths:
    """The per-session sandbox layout; the only directories a session may write."""

    root: Path

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def config_dir(self) -> Path:
        return self.home / ".claude"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"


@dataclass(frozen=True)
class SessionRun:
    """Raw process outcome. ``exit_code is None`` means the session timed out."""

    stdout: str
    stderr: str
    exit_code: int | None

    @property
    def timed_out(self) -> bool:
        return self.exit_code is None


def build_argv(spec: SessionSpec) -> list[str]:
    argv = [
        CLAUDE_BINARY,
        "-p",
        spec.prompt,
        "--model",
        spec.model,
        "--effort",
        spec.effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--plugin-dir",
        str(spec.plugin_dir),
        "--strict-mcp-config",
        "--mcp-config",
        EMPTY_MCP_CONFIG,
        "--permission-prompts",
        "none",
        "--permission-mode",
        spec.permission_mode,
    ]
    if spec.allowed_tools:
        argv += ["--allowedTools", *spec.allowed_tools]
    if spec.json_schema is not None:
        argv += ["--json-schema", json.dumps(spec.json_schema, separators=(",", ":"))]
    if spec.forward_subagent_text:
        argv.append("--forward-subagent-text")
    return [*argv, "--max-budget-usd", str(spec.max_budget_usd)]


def build_env(
    sandbox: Path, ambient: Mapping[str, str], *, interpreter: Path = _RUNNER_INTERPRETER
) -> dict[str, str]:
    """Build a session environment from scratch; nothing outside the allowlist survives."""
    paths = SandboxPaths(sandbox)
    search_path = os.pathsep.join((str(interpreter.parent), ambient.get("PATH", os.defpath)))
    return {
        **{key: ambient[key] for key in PASS_THROUGH_KEYS if key in ambient},
        "PATH": search_path,
        "HOME": str(paths.home),
        "CLAUDE_CONFIG_DIR": str(paths.config_dir),
        "TMPDIR": str(paths.tmp),
        **FIXED_SWITCHES,
    }


def run_session(spec: SessionSpec, env: Mapping[str, str]) -> SessionRun:
    return run_argv(build_argv(spec), cwd=spec.cwd, env=env, timeout_s=spec.timeout_s)


def run_argv(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout_s: int
) -> SessionRun:
    """Start one ``claude`` process and wait for it; the module's only side effect."""
    try:
        done = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return SessionRun(
            stdout=_decoded(expired.stdout), stderr=_decoded(expired.stderr), exit_code=None
        )
    return SessionRun(stdout=done.stdout, stderr=done.stderr, exit_code=done.returncode)


def _decoded(output: bytes | str | None) -> str:
    # TimeoutExpired carries bytes even under text=True.
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InitInfo:
    model: str | None
    plugins: tuple[Mapping[str, Any], ...]
    mcp_servers: tuple[Mapping[str, Any], ...]
    api_key_source: str | None
    claude_code_version: str | None
    cwd: str | None


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: Mapping[str, Any]
    parent_tool_use_id: str | None


class SubagentText(NamedTuple):
    parent_tool_use_id: str
    subagent_type: str
    text: str


class TaskNotification(NamedTuple):
    tool_use_id: str
    status: str
    summary: str


class HookOutput(NamedTuple):
    hook_name: str
    output: str


@dataclass(frozen=True)
class ResultInfo:
    result_text: str | None
    structured_output: Any
    is_error: bool
    subtype: str
    total_cost_usd: float | None
    session_id: str | None
    num_turns: int | None = None
    duration_ms: int | None = None
    usage: Mapping[str, Any] | None = None
    permission_denials: int | None = None
    subagents_spawned: int | None = None

    @property
    def failed(self) -> bool:
        # A budget or max-turns stop reports an error subtype; an API error
        # can report ``success`` with ``is_error`` set.
        return self.is_error or self.subtype != SUCCESS_SUBTYPE


@dataclass(frozen=True)
class SessionEnvelope:
    init: InitInfo | None
    tool_uses: tuple[ToolUse, ...]
    subagent_texts: tuple[SubagentText, ...]
    task_notifications: tuple[TaskNotification, ...]
    hook_outputs: tuple[HookOutput, ...]
    final_result: ResultInfo | None
    result_count: int
    unparseable: bool


UNPARSEABLE_ENVELOPE = SessionEnvelope(
    init=None,
    tool_uses=(),
    subagent_texts=(),
    task_notifications=(),
    hook_outputs=(),
    final_result=None,
    result_count=0,
    unparseable=True,
)


class _MalformedEnvelopeError(ValueError):
    pass


def parse_stream(text: str) -> SessionEnvelope:
    """Parse a stream-json envelope; any malformed line invalidates the whole stream."""
    try:
        events = [_parse_event(line) for line in text.splitlines() if line.strip()]
        return _assemble(events)
    except _MalformedEnvelopeError:
        return UNPARSEABLE_ENVELOPE


def _assemble(events: Sequence[Mapping[str, Any]]) -> SessionEnvelope:
    init: InitInfo | None = None
    tool_uses: list[ToolUse] = []
    subagent_texts: list[SubagentText] = []
    notifications: list[TaskNotification] = []
    hook_outputs: list[HookOutput] = []
    results: list[ResultInfo] = []
    for event in events:
        match event.get("type"), event.get("subtype"):
            case "system", "init":
                init = _merge_init(init, _init_info(event))
            case "system", "task_notification":
                notifications.append(_task_notification(event))
            case "system", "hook_response":
                hook_outputs.extend(_hook_output(event))
            case "assistant", _:
                tool_uses.extend(_tool_uses(event))
                subagent_texts.extend(_subagent_text(event))
            case "result", _:
                results.append(_result_info(event))
            case _:
                pass  # unknown event types carry nothing the runner consumes
    return SessionEnvelope(
        init=init,
        tool_uses=tuple(tool_uses),
        subagent_texts=tuple(subagent_texts),
        task_notifications=tuple(notifications),
        hook_outputs=tuple(hook_outputs),
        # Background subagents make the stream emit several results; the last
        # one carries the session's final answer.
        final_result=results[-1] if results else None,
        result_count=len(results),
        unparseable=False,
    )


def _merge_init(previous: InitInfo | None, current: InitInfo) -> InitInfo:
    """A resumed stream re-emits ``init``; keep every plugin and server any of them saw."""
    if previous is None:
        return current
    return InitInfo(
        model=previous.model,
        plugins=_union(previous.plugins, current.plugins),
        mcp_servers=_union(previous.mcp_servers, current.mcp_servers),
        api_key_source=previous.api_key_source,
        claude_code_version=previous.claude_code_version,
        cwd=previous.cwd,
    )


def _union(
    first: tuple[Mapping[str, Any], ...], second: tuple[Mapping[str, Any], ...]
) -> tuple[Mapping[str, Any], ...]:
    return first + tuple(item for item in second if item not in first)


def _init_info(event: Mapping[str, Any]) -> InitInfo:
    return InitInfo(
        model=_optional(event, "model", str),
        plugins=_mappings(event.get("plugins", [])),
        mcp_servers=_mappings(event.get("mcp_servers", [])),
        api_key_source=_optional(event, "apiKeySource", str),
        claude_code_version=_optional(event, "claude_code_version", str),
        cwd=_optional(event, "cwd", str),
    )


def _tool_uses(event: Mapping[str, Any]) -> list[ToolUse]:
    parent = _optional(event, "parent_tool_use_id", str)
    return [
        ToolUse(
            id=_required(block, "id", str),
            name=_required(block, "name", str),
            input=_required(block, "input", dict),
            parent_tool_use_id=parent,
        )
        for block in _content_blocks(event)
        if block.get("type") == "tool_use"
    ]


def _subagent_text(event: Mapping[str, Any]) -> list[SubagentText]:
    """Forwarded subagent text — the subagent's own words, not the orchestrator's relay."""
    parent = _optional(event, "parent_tool_use_id", str)
    if parent is None:
        return []
    text = "".join(
        _required(block, "text", str)
        for block in _content_blocks(event)
        if block.get("type") == "text"
    )
    if not text:
        return []
    return [SubagentText(parent, _optional(event, "subagent_type", str) or "", text)]


def _task_notification(event: Mapping[str, Any]) -> TaskNotification:
    return TaskNotification(
        tool_use_id=_required(event, "tool_use_id", str),
        status=_required(event, "status", str),
        summary=_optional(event, "summary", str) or "",
    )


def _hook_output(event: Mapping[str, Any]) -> list[HookOutput]:
    output = _optional(event, "output", str)
    if not output:
        return []
    return [HookOutput(_optional(event, "hook_name", str) or "", output)]


def _result_info(event: Mapping[str, Any]) -> ResultInfo:
    denials = _optional(event, "permission_denials", list)
    stats = _optional(event, "subagent_stats", dict)
    return ResultInfo(
        result_text=_optional(event, "result", str),
        structured_output=event.get("structured_output"),
        is_error=_required(event, "is_error", bool),
        subtype=_required(event, "subtype", str),
        total_cost_usd=_optional(event, "total_cost_usd", float),
        session_id=_optional(event, "session_id", str),
        num_turns=_optional(event, "num_turns", int),
        duration_ms=_optional(event, "duration_ms", int),
        usage=_optional(event, "usage", dict),
        permission_denials=None if denials is None else len(denials),
        subagents_spawned=None if stats is None else _optional(stats, "spawned", int),
    )


def _parse_event(line: str) -> Mapping[str, Any]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError as error:
        raise _MalformedEnvelopeError(f"non-JSON line: {line[:80]!r}") from error
    if not isinstance(event, dict):
        raise _MalformedEnvelopeError(f"event is not an object: {line[:80]!r}")
    return event


def _content_blocks(event: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    message = _required(event, "message", dict)
    content = message.get("content", [])
    if isinstance(content, str):
        return []
    return list(_mappings(content))


def _mappings(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise _MalformedEnvelopeError(f"expected a list of objects, got {value!r:.80}")
    return tuple(value)


def _required[T](event: Mapping[str, Any], key: str, kind: type[T]) -> T:
    value = _optional(event, key, kind)
    if value is None:
        raise _MalformedEnvelopeError(f"missing {key!r}")
    return value


def _optional[T](event: Mapping[str, Any], key: str, kind: type[T]) -> T | None:
    value = event.get(key)
    if value is None:
        return None
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)  # type: ignore[return-value]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise _MalformedEnvelopeError(f"{key!r} is not {kind.__name__}: {value!r:.80}")
    return value


# ---------------------------------------------------------------------------
# Verdicts over an envelope
# ---------------------------------------------------------------------------


def classify(envelope: SessionEnvelope, exit_code: int | None, timed_out: bool) -> ErrorKind | None:
    """The infrastructure error a session suffered, or ``None`` if it can be graded.

    An error ``result`` outranks a non-zero exit: a budget or max-turns stop
    exits non-zero too, and its result names the cause.
    """
    if timed_out:
        return "timeout"
    if envelope.final_result is not None and envelope.final_result.failed:
        return "result_error"
    if exit_code != 0:
        return "exit_nonzero"
    if envelope.unparseable:
        return "envelope_unparseable"
    if envelope.final_result is None:
        return "no_result_event"
    return None


def check_isolation(envelope: SessionEnvelope, copy_root: Path) -> bool:
    """True iff the session loaded the target copy, builtins, and nothing else.

    ``copy_root`` must be the copy's resolved path — ``init`` reports real paths.
    """
    init = envelope.init
    if init is None or init.mcp_servers:
        return False
    copy_path = os.path.normpath(copy_root)
    non_builtin = [p for p in init.plugins if not _is_builtin(p)]
    return bool(non_builtin) and all(
        os.path.normpath(str(p.get("path"))) == copy_path for p in non_builtin
    )


def _is_builtin(plugin: Mapping[str, Any]) -> bool:
    return str(plugin.get("source", "")).endswith(BUILTIN_PLUGIN_SUFFIX)
