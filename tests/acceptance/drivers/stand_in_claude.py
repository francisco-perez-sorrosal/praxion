"""A `claude` stand-in for whole adherence runs: every session answered, none paid for.

The adherence eval launches one `claude -p` process per session: an arm proof per built
arm, then each planned task in each arm. A scenario puts this stand-in first on the run's
`PATH` so each of those launches is answered here instead. The stand-in plays the harness
the way a real session would present itself to the runner:

- an arm proof: the main session spawns the role, which echoes the nonce planted in the
  session's installed instruction file when the plugin copy's definition does not omit
  it, and answers `NO-MARKER` when it does; the lean role's first request is the smaller;
- a task session: the main session spawns the role; the role writes its durable output
  and returns a pointer ending in a terminal marker; for the lean arm of a role whose
  copy delivers a kernel, the role's own transcript carries the delivery marker the
  runner reads;
- a scripted ending instead of that, when the scenario asks for one: a graded failure
  (the role returns no terminal marker), an isolation breach (a plugin from outside the
  sandbox in the init event), a crash (non-zero exit, text on the error output), an
  error result (an error `result` event carrying text), or a stream with no result.

Every launch is logged with its arm, task and attempt, which is how a scenario sees what
the run started. Nothing here reads the evaluation package: the stand-in reaches the run
only through the process interface a real `claude` has, so a run cannot tell the two
apart, and the module imports nothing outside the standard library (plus `yaml` for the
plugin copy's adoption ledger) because it runs under the suite's own interpreter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

# -- Driver side: install the stand-in and read back what it was asked to do ------------------

NO_MARKER_REPLY = "NO-MARKER"  # the proof contract of the arm proof
PROOF_LABEL = "PRXARM"
KERNEL_ACTIVE_STATUSES = frozenset({"trial", "switched"})  # the statuses that deliver a kernel
KERNEL_MARKER = "[praxion 0.0.0-stand-in #1] the kernel the role was owed"


def fingerprint(scratch: Path) -> str:
    """A digest of the files a session starts from, which tells one planned task from another."""
    digest = hashlib.sha256()
    files = (p for p in scratch.rglob("*") if p.is_file() and ".git" not in p.parts)
    for path in sorted(files):
        digest.update(path.relative_to(scratch).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class ScriptedEnding(Protocol):
    """What a scenario scripts for one session (`adherence_runs.Ending`)."""

    kind: str
    error_output: str
    result_text: str


@dataclass(frozen=True)
class TaskPlace:
    """A planned task: its id and its position in the run's planned order."""

    task_id: str
    position: int


@dataclass(frozen=True)
class LaunchRecord:
    """One session the run started."""

    arm: str
    task_id: str  # empty for an arm proof
    attempt: int  # 1 for a task's first session in that arm, 2 for its retry
    proof: bool


@dataclass(frozen=True)
class StandIn:
    root: Path

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def log_dir(self) -> Path:
        return self.root / "log"

    def launches(self) -> list[LaunchRecord]:
        return [_launch_of(raw) for raw in _logged_launches(self.log_dir)]


def install(
    root: Path,
    *,
    version: str,
    role: str,
    tasks: Mapping[str, TaskPlace],  # by fingerprint
    by_arm: Mapping[str, Sequence[ScriptedEnding]],
    by_task: Mapping[tuple[int, str], ScriptedEnding],
    default: ScriptedEnding,
) -> StandIn:
    """Write the stand-in `claude` and its script under `root`.

    `tasks` maps the fingerprint of a task's scratch repository (`fingerprint`) to its place:
    two tasks can share a prompt, but never the files they start from. An arm proof is the
    session whose prompt asks for the planted marker. A session's ending is, in order: the one scripted for its (planned position,
    arm), the one scripted for the arm's n-th task launch, else `default`.
    """
    stand_in = StandIn(root)
    stand_in.bin_dir.mkdir(parents=True)
    config = root / "config.json"
    config.write_text(
        json.dumps(
            {
                "log_dir": str(stand_in.log_dir),
                "version": version,
                "role": role,
                "tasks": {
                    seen: {"task_id": place.task_id, "position": place.position}
                    for seen, place in tasks.items()
                },
                "by_arm": {arm: [_ending_json(e) for e in ends] for arm, ends in by_arm.items()},
                "by_task": {f"{pos}|{arm}": _ending_json(e) for (pos, arm), e in by_task.items()},
                "default": _ending_json(default),
            }
        ),
        encoding="utf-8",
    )
    launcher = stand_in.bin_dir / "claude"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('stand_in_claude', {__file__!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['stand_in_claude'] = module\n"
        "spec.loader.exec_module(module)\n"
        f"sys.exit(module.serve({str(config)!r}))\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return stand_in


def _ending_json(ending: ScriptedEnding) -> dict[str, str]:
    return {
        "kind": ending.kind,
        "error_output": ending.error_output,
        "result_text": ending.result_text,
    }


def _logged_launches(log_dir: Path) -> list[Mapping[str, Any]]:
    if not log_dir.is_dir():
        return []
    paths = sorted(log_dir.glob("launch-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _launch_of(raw: Mapping[str, Any]) -> LaunchRecord:
    return LaunchRecord(raw["arm"], raw["task_id"], raw["attempt"], raw["proof"])


# -- Stand-in side: what runs when the run starts `claude` ---------------------------------------

FULL_FIRST_REQUEST = {
    "input_tokens": 3,
    "cache_creation_input_tokens": 41000,
    "cache_read_input_tokens": 1200,
}
LEAN_FIRST_REQUEST = {**FULL_FIRST_REQUEST, "cache_creation_input_tokens": 23000}
LATER_REQUEST = {
    "input_tokens": 2,
    "cache_creation_input_tokens": 512,
    "cache_read_input_tokens": 42203,
}
MAIN_REQUEST = {
    "input_tokens": 2,
    "cache_creation_input_tokens": 39013,
    "cache_read_input_tokens": 10359,
}
SESSION_COST_USD = 0.01
EXIT_FAILED = 1
SLUG_IN_PROMPT = re.compile(r"Task slug: (?P<slug>[\w-]+)\.")
TASK_TEXT = re.compile(r"<<<\n(?P<task>.*)\n>>>", re.DOTALL)
CAP_IN_COPY_NAME = re.compile(r"-cap\d+$")
FOREIGN_PLUGIN = {
    "name": "stray",
    "path": "/opt/outside-the-sandbox/stray",
    "source": "stray@inline",
}


@dataclass(frozen=True)
class Session:
    """What the run asked this process to be."""

    prompt: str
    plugin_dir: str
    model: str
    role: str
    arm: str
    cwd: str
    config_dir: str
    place: TaskPlace | None  # None: an arm proof

    @property
    def slug(self) -> str:
        found = SLUG_IN_PROMPT.search(self.prompt)
        return found["slug"] if found else "stand-in-task"

    @property
    def spawn_prompt(self) -> str:
        found = TASK_TEXT.search(self.prompt)
        return found["task"] if found else self.prompt

    @property
    def stopped_early(self) -> bool:
        return bool(CAP_IN_COPY_NAME.search(Path(self.plugin_dir).name))


def serve(config_path: str) -> int:
    """Answer one launch of `claude` as the run asked."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    argv = sys.argv[1:]
    if "--version" in argv or argv == ["-v"]:
        print(f"{config['version']} (Claude Code)")
        return 0
    session = _session_of(config, argv)
    log_dir = Path(config["log_dir"])
    previous = _logged_launches(log_dir)
    attempt = 1 + sum(
        1
        for raw in previous
        if not raw["proof"] and (raw["arm"], raw["task_id"]) == (session.arm, _task_id(session))
    )
    ending = _ending_of(config, session, previous)
    _log_launch(log_dir, session, attempt, ending["kind"], len(previous))
    return _play(session, ending)


def _session_of(config: Mapping[str, Any], argv: Sequence[str]) -> Session:
    prompt = _option(argv, "-p") or ""
    plugin_dir = _option(argv, "--plugin-dir") or ""
    role = config["role"]
    cwd = os.getcwd()
    found = None if f"{PROOF_LABEL}-" in prompt else config["tasks"].get(fingerprint(Path(cwd)))
    return Session(
        prompt=prompt,
        plugin_dir=plugin_dir,
        model=_option(argv, "--model") or "claude-opus-5-5",
        role=role,
        arm="lean" if _omits_claude_md(Path(plugin_dir) / "agents" / f"{role}.md") else "full",
        cwd=cwd,
        config_dir=os.environ.get("CLAUDE_CONFIG_DIR", ""),
        place=None if found is None else TaskPlace(found["task_id"], found["position"]),
    )


def _option(argv: Sequence[str], flag: str) -> str | None:
    for i, arg in enumerate(argv):
        if arg == flag and i + 1 < len(argv):
            return argv[i + 1]
    return None


def _omits_claude_md(definition: Path) -> bool:
    lines = definition.read_text(encoding="utf-8").splitlines() if definition.is_file() else []
    closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), 0)
    return any(line.strip() == "omitClaudeMd: true" for line in lines[1:closing])


def _task_id(session: Session) -> str:
    return "" if session.place is None else session.place.task_id


def _ending_of(
    config: Mapping[str, Any], session: Session, previous: Sequence[Mapping[str, Any]]
) -> Mapping[str, str]:
    if session.place is None:
        return {"kind": "ran", "error_output": "", "result_text": ""}
    scripted = config["by_task"].get(f"{session.place.position}|{session.arm}")
    if scripted is not None:
        return scripted
    arm_launches = sum(1 for raw in previous if not raw["proof"] and raw["arm"] == session.arm)
    by_arm = config["by_arm"].get(session.arm, [])
    return by_arm[arm_launches] if arm_launches < len(by_arm) else config["default"]


def _log_launch(log_dir: Path, session: Session, attempt: int, ending: str, ordinal: int) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "arm": session.arm,
        "task_id": _task_id(session),
        "attempt": attempt,
        "proof": session.place is None,
        "ending": ending,
        "cwd": session.cwd,
        "plugin_dir": session.plugin_dir,
    }
    (log_dir / f"launch-{ordinal}.json").write_text(json.dumps(record), encoding="utf-8")


def _play(session: Session, ending: Mapping[str, str]) -> int:
    kind = ending["kind"]
    sid = f"stand-in-{time.time_ns()}"
    if kind == "crashed":
        _emit([_init(session, sid)])
        sys.stderr.write(ending["error_output"])
        return EXIT_FAILED
    if kind == "unparseable":
        _emit([_init(session, sid)])
        return 0
    if kind == "error result":
        _emit([_init(session, sid), _result(sid, ending["result_text"], failed=True)])
        sys.stderr.write(ending["error_output"])
        return EXIT_FAILED
    _emit(_role_session(session, sid, kind))
    return 0


def _role_session(session: Session, sid: str, kind: str) -> list[dict[str, Any]]:
    """The main session that spawns the role, for every ending in which the role runs."""
    if session.place is None:
        answer = _proof_answer(session)
        actions: list[tuple[str, dict[str, Any], str]] = []
    else:
        answer, actions = _role_work(session, kind)
    agent_id = f"a{time.time_ns():x}"
    if session.place is not None and session.arm == "lean" and _delivers_kernel(session):
        _write_role_transcript(session, sid, agent_id)
    first = LEAN_FIRST_REQUEST if session.arm == "lean" else FULL_FIRST_REQUEST
    spawn = "toolu_stand_in_spawn"
    prompt = session.spawn_prompt
    events = [
        _init(session, sid, foreign=kind == "isolation breach"),
        _assistant(sid, [_tool_use(spawn, "Agent", _spawn_input(session, prompt))], MAIN_REQUEST),
    ]
    events += [_started(sid, spawn, session, prompt)]
    for i, (tool, tool_input, output) in enumerate(actions):
        use_id = f"toolu_stand_in_role_{i:03d}"
        usage = first if i == 0 else LATER_REQUEST
        events += [
            _assistant(
                sid, [_tool_use(use_id, tool, tool_input)], usage, parent=spawn, role=session.role
            ),
            _tool_result(sid, use_id, output, parent=spawn),
        ]
    usage = first if not actions else LATER_REQUEST
    events.append(
        _assistant(sid, [{"type": "text", "text": answer}], usage, parent=spawn, role=session.role)
    )
    events.append(_tool_result(sid, spawn, f"{answer}\nagentId: {agent_id}\n", parent=None))
    events.append(_assistant(sid, [{"type": "text", "text": answer}], MAIN_REQUEST))
    events.append(_result(sid, answer, failed=False))
    return events


def _proof_answer(session: Session) -> str:
    """The line the role finds in its inherited instructions, or the no-marker reply."""
    if session.arm == "lean":
        return NO_MARKER_REPLY
    instructions = Path(session.config_dir) / "CLAUDE.md"
    text = instructions.read_text(encoding="utf-8") if instructions.is_file() else ""
    marked = (line for line in text.splitlines() if line.startswith(f"{PROOF_LABEL}-"))
    return next(marked, NO_MARKER_REPLY)


def _role_work(session: Session, kind: str) -> tuple[str, list[tuple[str, dict[str, Any], str]]]:
    """What the role does and returns: its durable output and a pointer, or a failed return."""
    if kind == "graded failure":
        return "I looked into it and have nothing more to add.", []
    path = Path(session.cwd) / ".ai-work" / session.slug / "RESEARCH_FINDINGS.md"
    document = _findings(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    marker = "[PARTIAL]" if session.stopped_early else "[COMPLETE]"
    answer = f"The findings are in .ai-work/{session.slug}/RESEARCH_FINDINGS.md.\n{marker}"
    return answer, [("Write", {"file_path": str(path), "content": document}, "ok")]


def _findings(session: Session) -> str:
    if session.stopped_early:
        return "# Research Findings [PARTIAL]\n\n**Completed phases**: none\n"
    return (
        "# Research Findings\n\n## Research Goal\n\nAnswer the brief.\n\n"
        "## Research Questions\n\n1. What does the brief ask?\n\n"
        "## Sources\n\n- https://example.com/docs\n"
    )


def _delivers_kernel(session: Session) -> bool:
    """Whether the plugin copy's ledger has the role receiving a kernel at spawn."""
    ledger = Path(session.plugin_dir) / ".ai-state" / "kernel_adoption.yaml"
    try:
        roles = yaml.safe_load(ledger.read_text(encoding="utf-8")).get("roles") or {}
    except (OSError, yaml.YAMLError, AttributeError):
        return False
    return (roles.get(session.role) or {}).get("status") in KERNEL_ACTIVE_STATUSES


def _write_role_transcript(session: Session, sid: str, agent_id: str) -> None:
    """Where the harness keeps a subagent's transcript, holding the kernel's delivery marker."""
    project = re.sub(r"[^A-Za-z0-9]", "-", session.cwd)
    path = Path(session.config_dir) / "projects" / project / sid / "subagents"
    path.mkdir(parents=True, exist_ok=True)
    record = {
        "type": "attachment",
        "attachment": {
            "type": "hook_additional_context",
            "hookEvent": "SubagentStart",
            "content": [KERNEL_MARKER],
        },
    }
    (path / f"agent-{agent_id}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")


# -- The stream-json events of a session --------------------------------------------------------


def _emit(events: Sequence[Mapping[str, Any]]) -> None:
    for event in events:
        print(json.dumps(event), flush=True)


def _init(session: Session, sid: str, *, foreign: bool = False) -> dict[str, Any]:
    plugins = [
        {"name": "praxion", "path": session.plugin_dir, "source": "praxion@inline"},
        {"name": "agents-md", "path": "builtin", "source": "agents-md@builtin"},
    ]
    return {
        "type": "system",
        "subtype": "init",
        "cwd": session.cwd,
        "session_id": sid,
        "tools": ["Agent", "Bash", "Read", "Write", "Edit", "WebFetch", "WebSearch"],
        "mcp_servers": [],
        "model": session.model,
        "permissionMode": "acceptEdits",
        "apiKeySource": "ANTHROPIC_API_KEY",
        "claude_code_version": "9.9.9-stand-in",
        "agents": ["general-purpose", f"praxion:{session.role}"],
        "plugins": [*plugins, FOREIGN_PLUGIN] if foreign else plugins,
        "uuid": "00000000-0000-4000-8000-000000000001",
    }


def _tool_use(use_id: str, name: str, tool_input: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": use_id, "name": name, "input": dict(tool_input)}


def _spawn_input(session: Session, prompt: str) -> dict[str, Any]:
    return {
        "description": f"Run the {session.role}",
        "subagent_type": f"praxion:{session.role}",
        "prompt": prompt,
        "run_in_background": False,
    }


def _assistant(
    sid: str,
    content: Sequence[Mapping[str, Any]],
    usage: Mapping[str, int],
    *,
    parent: str | None = None,
    role: str = "",
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-5-5",
            "id": f"msg_{time.time_ns()}",
            "type": "message",
            "role": "assistant",
            "content": list(content),
            "usage": {**usage, "output_tokens": 7},
        },
        "parent_tool_use_id": parent,
        "session_id": sid,
    }
    if parent:
        event["subagent_type"] = f"praxion:{role}"
    return event


def _started(sid: str, spawn: str, session: Session, prompt: str) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "task_started",
        "task_id": "stand-in-task",
        "tool_use_id": spawn,
        "description": f"Run the {session.role}",
        "subagent_type": f"praxion:{session.role}",
        "is_backgrounded": False,
        "spawn_depth": 1,
        "task_type": "local_agent",
        "prompt": prompt,
        "session_id": sid,
    }


def _tool_result(sid: str, use_id: str, text: str, *, parent: str | None) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "tool_use_id": use_id,
                    "type": "tool_result",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        },
        "parent_tool_use_id": parent,
        "session_id": sid,
    }


def _result(sid: str, text: str, *, failed: bool) -> dict[str, Any]:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": failed,
        "result": text,
        "session_id": sid,
        "num_turns": 3,
        "duration_ms": 5,
        "total_cost_usd": 0.0 if failed else SESSION_COST_USD,
        "usage": {"input_tokens": 4, "output_tokens": 40},
        "permission_denials": [],
    }
