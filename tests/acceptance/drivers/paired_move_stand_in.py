"""A `claude` stand-in for a paired run of the refactoring move: every session answered, none paid.

A paired run launches one `claude -p` process per session, each handed one arm's plugin copy
(`--plugin-dir`). A scenario puts this stand-in first on the run's `PATH`, so every launch is
answered here. It plays the harness the way a real session presents itself:

- The main session spawns the role (`praxion:<role>`) with the delegation its prompt carries:
  the text between a `<<<` line and a `>>>` line, the ordinary eval's form at the base, else the
  whole prompt. The spawn's harness boundary is crossed for real against the session's copy:
  every `PreToolUse` hook the copy registers for `Agent`, then every `SubagentStart` hook it
  registers for the role, each a process of its own in the session's working directory, with
  `CLAUDE_PLUGIN_ROOT` the copy and `CLAUDE_CONFIG_DIR` the session's own.
- The role's own record is filed where the harness keeps it:
  `<CLAUDE_CONFIG_DIR>/projects/<cwd, each non-alphanumeric character a dash>/<session id>/`
  `subagents/agent-<agent id>.jsonl`. Its first line is the user message holding the delegation
  as the hooks rewrote it; one `hook_additional_context` attachment (`hookEvent: SubagentStart`)
  follows per context string. A preloaded skill is not filed there: it rides the definition.
- A session that starts in a repository holding a task template's starting state (every file of
  the template's `start/`, the `.tmpl` suffix dropped, with the same bytes) is a task session of
  that template. Any other session is an arm proof.
- A task session leaves the end state its script names, as a session would: each starting file
  the end state lacks is deleted and every end-state file written, all else left as it was. The
  role then returns the scripted account, a pointer and a terminal marker.
- Scripted harness failures: `unserved` files the role's record with the bare delegation and
  nothing the hooks added, as when the delivered text never reached the role; an `error` ends
  the session in an error result carrying the text (a spent credit balance).

The arm of a session is read from its copy: `preloaded` when the role's definition preloads the
refactoring skill, `delivered` otherwise. Every launch is logged with its arm, its template (empty
for a proof), its ordinal among the arm's task launches, its ending and the digest of every file
its repository held when it started (`.git` excluded).

The module runs under the suite's interpreter, never the evaluation package's, and reads the
plugin copy only as files and hook processes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_SUFFIX = ".tmpl"
SKILL_NAME = "refactoring"
TASK_TEXT = re.compile(r"<<<\n(?P<task>.*)\n>>>", re.DOTALL)
EXIT_FAILED = 1
CLEAN = "clean"


@dataclass(frozen=True)
class Ending:
    """How one task session ends: the end state it leaves, what the role says, what arrives."""

    work: str = CLEAN  # "clean", or the checklist item (spec wording) the end state violates
    account: str = "Done."  # the role's own account; never evidence
    served: bool = True  # False: the role's record holds nothing the hooks added
    error: str = ""  # non-empty: the session ends in an error result carrying this text


@dataclass(frozen=True)
class Launch:
    arm: str
    proof: bool
    template: str  # empty for an arm proof
    ordinal: int  # the session's place among its arm's task launches; -1 for a proof
    ending: Mapping[str, Any]
    start_files: Mapping[str, str]  # relative path -> sha256 of the repository at the start
    cwd: str
    plugin_dir: str


@dataclass(frozen=True)
class StandIn:
    root: Path

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def log_dir(self) -> Path:
        return self.root / "log"

    def launches(self) -> tuple[Launch, ...]:
        return tuple(Launch(**raw) for raw in _logged(self.log_dir))


@dataclass(frozen=True)
class Script:
    by_arm: Mapping[str, Sequence[Ending]] = field(default_factory=dict)  # by task-launch ordinal
    default: Ending = field(default_factory=Ending)


# -- Driver side ---------------------------------------------------------------------------------


def install(
    root: Path, *, version: str, role: str, templates: Mapping[str, Path], script: Script
) -> StandIn:
    """Write the stand-in `claude` under `root`; `templates` maps a template's name to its directory."""
    stand_in = StandIn(root)
    stand_in.bin_dir.mkdir(parents=True)
    config = root / "config.json"
    config.write_text(
        json.dumps(
            {
                "log_dir": str(stand_in.log_dir),
                "version": version,
                "role": role,
                "templates": {name: str(path) for name, path in templates.items()},
                "by_arm": {arm: [asdict(e) for e in ends] for arm, ends in script.by_arm.items()},
                "default": asdict(script.default),
            }
        ),
        encoding="utf-8",
    )
    launcher = stand_in.bin_dir / "claude"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from tests.acceptance.drivers import paired_move_stand_in as stand_in\n"
        f"sys.exit(stand_in.serve({str(config)!r}))\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return stand_in


def _logged(log_dir: Path) -> list[dict[str, Any]]:
    if not log_dir.is_dir():
        return []
    paths = sorted(log_dir.glob("launch-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


# -- Stand-in side -------------------------------------------------------------------------------


def serve(config_path: str) -> int:
    """Answer one launch of `claude` as the scenario scripted it."""
    from tests.acceptance.drivers import stand_in_claude as base

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    argv = sys.argv[1:]
    if "--version" in argv or argv == ["-v"]:
        print(f"{config['version']} (Claude Code)")
        return 0
    if argv[:1] == ["doctor"]:
        return base._doctor()
    plugin_dir = Path(base._option(argv, "--plugin-dir") or "")
    cwd = Path.cwd()
    role = config["role"]
    start_files = _digests(cwd)
    template = _template_of(config["templates"], start_files)
    arm = _arm_of(plugin_dir, role)
    previous = _logged(Path(config["log_dir"]))
    ordinal = -1 if template is None else _task_launches(previous, arm)
    ending = Ending() if template is None else _scripted(config, arm, ordinal)
    _log(
        config,
        previous,
        Launch(
            arm,
            template is None,
            template or "",
            ordinal,
            asdict(ending),
            start_files,
            str(cwd),
            str(plugin_dir),
        ),
    )
    prompt = base._option(argv, "-p") or ""
    found = TASK_TEXT.search(prompt)
    delegation = found["task"] if found else prompt
    scratch = Path(config["log_dir"]).parent / "hook-env"
    return _play(
        base, role, plugin_dir, cwd, delegation, config["templates"].get(template), ending, scratch
    )


def _digests(root: Path) -> dict[str, str]:
    files = (p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts)
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }


def tree_digests(tree: Path) -> dict[str, str]:
    """A template tree's files as a session's repository holds them: `.tmpl` dropped from each name."""
    return {rel.removesuffix(TEMPLATE_SUFFIX): sha for rel, sha in _digests(tree).items()}


def _template_of(templates: Mapping[str, str], held: Mapping[str, str]) -> str | None:
    matches = []
    for name, directory in templates.items():
        start = tree_digests(Path(directory) / "start")
        if start and all(held.get(rel) == sha for rel, sha in start.items()):
            matches.append((len(start), name))
    return max(matches)[1] if matches else None


def _arm_of(plugin_dir: Path, role: str) -> str:
    from tests.acceptance.drivers import refactoring_delivery as rd

    definition = plugin_dir / "agents" / f"{role}.md"
    preloads = rd.preloaded_skills(plugin_dir, role) if definition.is_file() else ()
    return "preloaded" if SKILL_NAME in preloads else "delivered"


def _task_launches(previous: Sequence[Mapping[str, Any]], arm: str) -> int:
    return sum(1 for raw in previous if not raw["proof"] and raw["arm"] == arm)


def _scripted(config: Mapping[str, Any], arm: str, ordinal: int) -> Ending:
    by_arm = config["by_arm"].get(arm, [])
    raw = by_arm[ordinal] if ordinal < len(by_arm) else config["default"]
    return Ending(**raw)


def _log(config: Mapping[str, Any], previous: Sequence[Any], launch: Launch) -> None:
    log_dir = Path(config["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"launch-{len(previous)}.json"
    path.write_text(json.dumps(asdict(launch)), encoding="utf-8")


def _play(
    base: Any,
    role: str,
    plugin_dir: Path,
    cwd: Path,
    delegation: str,
    template: str | None,
    ending: Ending,
    scratch: Path,
) -> int:
    from tests.acceptance.drivers import stand_in_claude

    sid = f"paired-stand-in-{time.time_ns()}"
    session = stand_in_claude.Session(
        prompt=delegation,
        plugin_dir=str(plugin_dir),
        model="claude-opus-5-5",
        role=role,
        arm="",
        cwd=str(cwd),
        config_dir=_config_dir(cwd),
        place=None,
    )
    if ending.error:
        base._emit([base._init(session, sid), base._result(sid, ending.error, failed=True)])
        sys.stderr.write(ending.error)
        return EXIT_FAILED
    agent_id = f"a{time.time_ns():x}"
    _file_role_record(
        role, plugin_dir, cwd, delegation, sid, agent_id, scratch, served=ending.served
    )
    if template is not None:
        _leave_end_state(Path(template), cwd, ending.work)
    answer = f"{ending.account}\nThe change is in the repository.\n[COMPLETE]"
    spawn = "toolu_paired_stand_in_spawn"
    base._emit(
        [
            base._init(session, sid),
            base._assistant(
                sid,
                [base._tool_use(spawn, "Agent", base._spawn_input(session, delegation))],
                base.MAIN_REQUEST,
            ),
            base._started(sid, spawn, session, delegation),
            base._assistant(
                sid,
                [{"type": "text", "text": answer}],
                base.FULL_FIRST_REQUEST,
                parent=spawn,
                role=role,
            ),
            base._tool_result(sid, spawn, f"{answer}\nagentId: {agent_id}\n", parent=None),
            base._assistant(sid, [{"type": "text", "text": answer}], base.MAIN_REQUEST),
            base._result(sid, answer, failed=False),
        ]
    )
    return 0


def _config_dir(cwd: Path) -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or str(cwd.parent / f".{cwd.name}-stand-in-config")


def _file_role_record(
    role: str,
    plugin_dir: Path,
    cwd: Path,
    delegation: str,
    sid: str,
    agent_id: str,
    scratch: Path,
    *,
    served: bool,
) -> None:
    """Cross the spawn's hook boundary against the copy and file the role's own record."""
    from tests.acceptance.drivers import refactoring_delivery as rd
    from tests.acceptance.drivers.kernel_sandbox import isolated_env

    config_dir = Path(_config_dir(cwd))
    sessions = config_dir / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    main_record = sessions / f"{sid}.jsonl"
    own_record = sessions / sid / "subagents" / f"agent-{agent_id}.jsonl"
    agent_type = f"praxion:{role}"
    tool_input = {
        "prompt": delegation,
        "subagent_type": agent_type,
        "description": f"Run the {role}",
    }
    use_id = "toolu_paired_stand_in_spawn"
    rd._jsonl(
        main_record,
        [
            {
                "type": "assistant",
                "sessionId": sid,
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": use_id, "name": "Agent", "input": tool_input}
                    ],
                },
            }
        ],
    )
    env = isolated_env(
        scratch,
        CLAUDE_PLUGIN_ROOT=str(plugin_dir),
        CLAUDE_CONFIG_DIR=str(config_dir),
        CLAUDE_PROJECT_DIR=str(cwd),
    )
    additions: tuple[str, ...] = ()
    context: tuple[str, ...] = ()
    if served:
        pre = {
            "session_id": sid,
            "transcript_path": str(main_record),
            "cwd": str(cwd),
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": use_id,
            "tool_input": tool_input,
        }
        exits = rd._run_event(plugin_dir, "PreToolUse", "Agent", json.dumps(pre), cwd, env)
        additions, _ = rd._prompt_additions(exits, delegation)
    first = {
        "type": "user",
        "sessionId": sid,
        "agentId": agent_id,
        "isSidechain": True,
        "message": {"role": "user", "content": "\n".join((*additions, delegation))},
    }
    rd._jsonl(own_record, [first])
    if served:
        start = {
            "session_id": sid,
            "transcript_path": str(main_record),
            "agent_transcript_path": str(own_record),
            "cwd": str(cwd),
            "permission_mode": "default",
            "hook_event_name": "SubagentStart",
            "agent_id": agent_id,
            "agent_type": agent_type,
        }
        exits = rd._run_event(plugin_dir, "SubagentStart", agent_type, json.dumps(start), cwd, env)
        context = tuple(
            out["additionalContext"]
            for e in exits
            for out in [rd._parsed(e.stdout).get("hookSpecificOutput") or {}]
            if isinstance(out, dict) and isinstance(out.get("additionalContext"), str)
        )
    for text in context:
        rd._append_jsonl(
            own_record,
            {
                "type": "attachment",
                "attachment": {
                    "type": "hook_additional_context",
                    "hookEvent": "SubagentStart",
                    "content": [text],
                },
            },
        )


def item_slug(item: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", item.lower()).strip("-")


def _leave_end_state(template: Path, repository: Path, work: str) -> None:
    end_state = template / "end_states" / (CLEAN if work == CLEAN else item_slug(work))
    start = tree_digests(template / "start")
    ending = {
        p.relative_to(end_state).as_posix().removesuffix(TEMPLATE_SUFFIX): p
        for p in end_state.rglob("*")
        if p.is_file()
    }
    for rel in start:
        if rel not in ending and (repository / rel).is_file():
            (repository / rel).unlink()
    for rel, source in ending.items():
        target = repository / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
