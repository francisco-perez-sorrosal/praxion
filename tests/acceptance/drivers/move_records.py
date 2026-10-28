"""The one writer of main-session records, in the harness's own JSONL form.

A planted session record and the record the move stand-in leaves for a launched session are
written here and nowhere else, so the runner's reader meets one shape. The shape is the one
the harness and the role stand-in already use for a spawned role's transcript
(`stand_in_claude._write_role_transcript`, read by `adherence.transcript`), extended to a main
session. One JSON object per line, each stamped with an increasing UTC `timestamp`:

- an `attachment` record is what a hook delivered into the session:
  `{"type": "attachment", "timestamp", "attachment": {"type": "hook_additional_context",
  "hookEvent": "SessionStart" | "PreToolUse", "content": [text, ...]}}`;
- a `user` record is the prompt, `{"type": "user", "timestamp", "message": {"role": "user",
  "content": [{"type": "text", "text"}]}}`, or a tool result,
  `{"content": [{"type": "tool_result", "tool_use_id", "content": [{"type": "text", "text"}]}]}`
  (a gate's refusal is a tool result carrying the reason);
- an `assistant` record holds `tool_use` blocks, `{"type": "assistant", "timestamp",
  "message": {"role": "assistant", "content": [{"type": "tool_use", "id", "name", "input"}]}}`.

What arrives at session start is a `SessionStart` attachment, as `hooks/inject_rules.py` emits
it: the rule bodies with their frontmatter stripped. What arrives at the point of use is a
`PreToolUse` attachment ahead of the tool call it governs. This is the designer's reading of
that form until a real main-session record is frozen; it is not a claim about any harness
version. A planted session whose arm owes no text still carries a `SessionStart` attachment
(of unrelated text), so an unreadable record is never mistaken for an empty one.

The same module holds the other side of the stand-in `claude` of the move journeys (`serve`): the
process a run launches. It learns its arm from the words of the `--plugin-dir` path, its task from
a path component of its working directory that is a task id, acts in that fixture as scripted, and
leaves its record where Claude Code keeps a session's own: `<config dir>/projects/<cwd with every
non-alphanumeric character a dash>/<session id>.jsonl`, the session id being the one its stream
reports. It reads nothing from the evaluation package and never the session token.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, NamedTuple

from tests.acceptance.drivers import move_declarations
from tests.acceptance.drivers.move_declarations import Payload

Entry = dict[str, Any]
HookEvent = Literal["SessionStart", "PreToolUse"]
SessionStart = Literal[
    "the whole rule", "the resident kernel only", "one line of the rule", "no line of the rule"
]
FIRST_TIMESTAMP = datetime(2026, 10, 27, 9, 0, 0, tzinfo=UTC)
UNRELATED_CONTEXT = "Session context: no rule text is loaded here."
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


# -- Entries ----------------------------------------------------------------------------------


def attachment(event: HookEvent, text: str) -> Entry:
    """Text a hook delivered into the session at `event`."""
    return {
        "type": "attachment",
        "attachment": {
            "type": "hook_additional_context",
            "hookEvent": event,
            "content": [text],
        },
    }


def prompt(text: str) -> Entry:
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def tool_call(use_id: str, name: str, tool_input: Mapping[str, Any]) -> Entry:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": dict(tool_input)}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def tool_result(use_id: str, text: str) -> Entry:
    block = {
        "type": "tool_result",
        "tool_use_id": use_id,
        "content": [{"type": "text", "text": text}],
    }
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def write_record(path: Path, entries: Sequence[Entry]) -> Path:
    """Write `entries` in order, each stamped one second after the one before."""
    lines = []
    for position, entry in enumerate(entries):
        stamp = (FIRST_TIMESTAMP + timedelta(seconds=position)).isoformat().replace("+00:00", "Z")
        lines.append(json.dumps({**entry, "timestamp": stamp}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# -- What an arm owes the record --------------------------------------------------------------


def rule_body(payload: Payload) -> str:
    """The moved rule as the session-start injection delivers it: frontmatter stripped."""
    text = (move_declarations.REPO_ROOT / payload["moved_rule"]).read_text(encoding="utf-8")
    return _FRONTMATTER.sub("", text, count=1).strip("\n")


def session_start_text(payload: Payload, at_session_start: SessionStart) -> str:
    """The text a planted session's start carries of the moved rule, as the scenario names it."""
    body = rule_body(payload)
    if at_session_start == "the whole rule":
        return body
    if at_session_start == "the resident kernel only":
        return move_declarations.resident_kernel(payload)
    if at_session_start == "one line of the rule":
        return next(line for line in body.splitlines() if line.strip() and line[0] != "#")
    return UNRELATED_CONTEXT


def point_of_use_text(payload: Payload) -> str:
    """What the lean arm delivers at the point of use: the rule's lines the kernel does not keep."""
    resident = set(move_declarations.resident_kernel(payload).splitlines())
    return "\n".join(line for line in rule_body(payload).splitlines() if line not in resident)


GOVERNED_COMMAND = "git add -- notes.md && git commit -m 'Add the notes'"
PLANTED_REQUEST = "Commit the notes file."


class Call(NamedTuple):
    """One governed tool call and what it printed."""

    command: str
    output: str


def session_entries(
    payload: Payload,
    arm: str,
    at_session_start: SessionStart,
    point_of_use_arrived: bool,
    request: str,
    calls: Sequence[Call],
) -> list[Entry]:
    """A main session's record lines: what arrived at its start, its request, what ran.

    Point-of-use text belongs to the lean arm's delivery: a full or a floor record never carries
    it, whatever `point_of_use_arrived` says, so a floor record holds no line of the rule.
    """
    entries = [
        attachment("SessionStart", session_start_text(payload, at_session_start)),
        prompt(request),
    ]
    if arm == "lean" and point_of_use_arrived:
        entries.append(attachment("PreToolUse", point_of_use_text(payload)))
    for number, call in enumerate(calls):
        use_id = f"toolu_session_{number:03d}"
        entries += [
            tool_call(use_id, "Bash", {"command": call.command}),
            tool_result(use_id, call.output),
        ]
    return entries


def plant_session(
    path: Path,
    payload: Payload,
    arm: str,
    at_session_start: SessionStart,
    point_of_use_arrived: bool,
) -> Path:
    """A main-session record by what arrived: at session start, and (lean only) at the point of use."""
    calls = [Call(GOVERNED_COMMAND, "[main 1a2b3c4] Add the notes")]
    entries = session_entries(
        payload, arm, at_session_start, point_of_use_arrived, PLANTED_REQUEST, calls
    )
    return write_record(path, entries)


# -- The session a stand-in plays -------------------------------------------------------------

ARM_WORDS = ("full", "lean", "floor")
OWED_AT_START: dict[str, SessionStart] = {
    "full": "the whole rule",
    "lean": "the resident kernel only",
    "floor": "no line of the rule",
}
CONFORMING_MESSAGE = "Add the requested files"
VIOLATING_MESSAGE = "Update a great many files in the project all at once."
INFRASTRUCTURE_ERROR = "stand-in: the session service is unavailable (infrastructure error)"
EXIT_FAILED = 1
SESSION_COST_USD = 0.01


def serve(config_path: str) -> int:
    """Answer one launch of `claude` as the move run asked; see the module header."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    argv = sys.argv[1:]
    if "--version" in argv or argv == ["-v"]:
        print(f"{config['version']} (Claude Code)")
        return 0
    plugin_dir, request = _option(argv, "--plugin-dir") or "", _option(argv, "-p") or ""
    arm, cwd = _arm_of(plugin_dir), os.getcwd()
    task_id = _task_of(cwd, config["tasks"])
    ending = _scripted_ending(config, arm)
    _log_launch(config, arm, task_id, cwd, request, ending)
    session_id = f"stand-in-{time.time_ns()}"
    if ending == "infrastructure error":
        _emit([_init(cwd, session_id, plugin_dir)])
        sys.stderr.write(INFRASTRUCTURE_ERROR + "\n")
        return EXIT_FAILED
    if task_id is None:
        sys.stderr.write(f"stand-in: no task id is a component of the working directory {cwd}\n")
        return EXIT_FAILED
    payload = move_declarations.declared_payload(config["move"], _declaration(config))
    calls = _act(cwd, ending, config["tasks"][task_id])
    owed = "no line of the rule" if ending == "kernel never arrived" else OWED_AT_START[arm]
    entries = session_entries(payload, arm, owed, True, request, calls)
    record = _record_path(config, cwd, session_id)
    write_record(record, entries)
    _emit(_stream(cwd, session_id, plugin_dir, calls))
    return 0


def _option(argv: Sequence[str], flag: str) -> str | None:
    return next((argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == flag), None)


def _arm_of(plugin_dir: str) -> str:
    """The arm named by the nearest component of the plugin directory that names one."""
    for part in reversed(Path(plugin_dir).parts):
        found = {word for word in re.split(r"[^a-z]+", part.lower()) if word in ARM_WORDS}
        if len(found) == 1:
            return found.pop()
    raise SystemExit(f"stand-in: no arm is named by the plugin directory {plugin_dir!r}")


def _task_of(cwd: str, tasks: Mapping[str, Any]) -> str | None:
    return next((part for part in reversed(Path(cwd).parts) if part in tasks), None)


def _declaration(config: Mapping[str, Any]) -> Path | None:
    return None if config["declaration"] is None else Path(config["declaration"])


def _launches(log_dir: str) -> list[dict[str, Any]]:
    paths = sorted(Path(log_dir).glob("launch-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _scripted_ending(config: Mapping[str, Any], arm: str) -> str:
    """The ending for this arm's nth launch since the last script, else the arm's, else the default."""
    script = config["script"]
    since = _launches(config["log_dir"])[config["epoch"] :]
    nth = 1 + sum(1 for raw in since if raw["arm"] == arm)
    return script["by_launch"].get(f"{arm}|{nth}") or script["by_arm"].get(arm) or script["default"]


def _log_launch(
    config: Mapping[str, Any], arm: str, task_id: str | None, cwd: str, request: str, ending: str
):
    log_dir = Path(config["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    ordinal = len(_launches(config["log_dir"]))
    record = {"arm": arm, "task_id": task_id or "", "cwd": cwd, "prompt": request, "ending": ending}
    (log_dir / f"launch-{ordinal}.json").write_text(json.dumps(record), encoding="utf-8")


def _act(cwd: str, ending: str, named_files: Sequence[str]) -> list[Call]:
    """Commit in the fixture as the ending scripts, and say what ran."""
    stage = ["add", "-A"] if ending == "violating" else ["add", "--", *named_files]
    message = (
        CONFORMING_MESSAGE
        if ending in ("conforming", "kernel never arrived")
        else VIOLATING_MESSAGE
    )
    outputs = [_git(cwd, *stage), _git(cwd, "commit", "-q", "-m", message)]
    return [
        Call("git " + " ".join(stage), outputs[0]),
        Call(f"git commit -q -m {message!r}", outputs[1]),
    ]


def _git(cwd: str, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return done.stdout


def _record_path(config: Mapping[str, Any], cwd: str, session_id: str) -> Path:
    """Where a session's own record lives: the sandbox's config dir, else the stand-in's own."""
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or config["records_dir"])
    return config_dir / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd) / f"{session_id}.jsonl"


def _emit(events: Sequence[Mapping[str, Any]]) -> None:
    for event in events:
        print(json.dumps(event), flush=True)


def _init(cwd: str, session_id: str, plugin_dir: str) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "init",
        "cwd": cwd,
        "session_id": session_id,
        "tools": ["Bash", "Read", "Write", "Edit"],
        "mcp_servers": [],
        "model": "claude-opus-5-5",
        "permissionMode": "acceptEdits",
        "apiKeySource": "ANTHROPIC_API_KEY",
        "claude_code_version": "9.9.9-stand-in",
        "plugins": [{"name": "praxion", "path": plugin_dir, "source": "praxion@inline"}],
    }


def _stream(
    cwd: str, session_id: str, plugin_dir: str, calls: Sequence[Call]
) -> list[dict[str, Any]]:
    usage = {"input_tokens": 2, "output_tokens": 7}

    def assistant(content: list[dict[str, Any]]) -> dict[str, Any]:
        message = {
            "role": "assistant",
            "type": "message",
            "model": "claude-opus-5-5",
            "content": content,
        }
        return {
            "type": "assistant",
            "message": {**message, "usage": usage},
            "session_id": session_id,
        }

    events = [_init(cwd, session_id, plugin_dir)]
    for number, call in enumerate(calls):
        use_id = f"toolu_stand_in_{number:03d}"
        block = {
            "type": "tool_use",
            "id": use_id,
            "name": "Bash",
            "input": {"command": call.command},
        }
        result = {
            "tool_use_id": use_id,
            "type": "tool_result",
            "content": [{"type": "text", "text": call.output}],
        }
        events += [
            assistant([block]),
            {
                "type": "user",
                "message": {"role": "user", "content": [result]},
                "session_id": session_id,
            },
        ]
    events.append(assistant([{"type": "text", "text": "Committed the requested files."}]))
    events.append(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Committed the requested files.",
            "session_id": session_id,
            "num_turns": len(calls) + 1,
            "duration_ms": 5,
            "total_cost_usd": SESSION_COST_USD,
            "usage": usage,
            "permission_denials": [],
        }
    )
    return events
