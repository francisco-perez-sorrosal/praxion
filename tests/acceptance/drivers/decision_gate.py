"""Driver for the decision-record gate, reached only through the hooks the plugin registers.

The harness runs every PreToolUse command registered in `hooks/hooks.json` whose matcher takes
the tool's name, as a shell command, with the tool call's JSON payload on stdin and
`CLAUDE_PLUGIN_ROOT` naming the plugin. A command refuses the call by exiting 2 (its stderr is
the reason the session sees), or by printing a JSON object whose `hookSpecificOutput` carries
`permissionDecision: "deny"` (its `permissionDecisionReason` is the reason), or `decision:
"block"` (`reason`), or `continue: false` (`stopReason`). This driver does exactly that and
never imports a hook; a call no command refuses *lands*.

A commit is the Bash tool call `git commit -m <message>` run from the project, its changes
already staged; the gate sees the payload and the project's index, as the harness would leave
them. A scenario on the hook-absent side does the same work with no hook at all.

Isolation: every command runs with a scratch HOME, `python3` on PATH this suite's interpreter,
no inherited `CLAUDE*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variable, and event posting
disabled (`kernel_sandbox.isolated_env`), so no hook reaches the user's files or a server.

Nothing here is unbound: the registry, the payload and the refusal protocol are the harness's.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import decision_records
from tests.acceptance.drivers.kernel_sandbox import isolated_env

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_REGISTRY = "hooks/hooks.json"
PRE_TOOL_USE = "PreToolUse"
BLOCKING_EXIT = 2
MOVED_RULE = "rules/swe/adr-conventions.md"
INDEX_FILE = decision_records.INDEX_FILE
# What a plugin copy carries: everything a registered hook could run or read at its root.
PLUGIN_TREES = ("hooks", "rules", "scripts", "lib", ".claude-plugin", "claude")


@dataclass(frozen=True)
class HookVerdict:
    refused: bool
    message: str  # every reason a refusing command gave, joined
    said: str  # everything any command put before the session or on stderr, refused or not
    ran: tuple[str, ...]


def registered_commands(event: str, tool_name: str, plugin_root: Path = REPO_ROOT) -> list[dict]:
    """The registered commands the harness would run for `event` on a call of `tool_name`."""
    registry = json.loads((plugin_root / HOOK_REGISTRY).read_text(encoding="utf-8"))
    commands = []
    for group in registry.get("hooks", {}).get(event, []):
        matcher = group.get("matcher") or ""
        if matcher not in ("", "*") and not re.fullmatch(matcher, tool_name):
            continue
        commands += [h for h in group.get("hooks", []) if h.get("type", "command") == "command"]
    return commands


def payload(project: Path, tool_name: str, tool_input: dict) -> dict:
    return {
        "session_id": "decision-gate-acceptance",
        "transcript_path": str(project.parent / "transcript.jsonl"),
        "cwd": str(project),
        "permission_mode": "default",
        "hook_event_name": PRE_TOOL_USE,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "toolu_decision_gate",
    }


def replay(
    project: Path,
    tool_name: str,
    tool_input: dict,
    *,
    plugin_root: Path = REPO_ROOT,
    scratch: Path | None = None,
) -> HookVerdict:
    """Run every registered PreToolUse command for this call, the way the harness does."""
    scratch = scratch or project.parent / f".{project.name}-hooks"
    env = isolated_env(
        scratch,
        CLAUDE_PLUGIN_ROOT=str(plugin_root),
        CLAUDE_PROJECT_DIR=str(project),
        PRAXION_DISABLE_OBSERVABILITY="1",
    )
    stdin = json.dumps(payload(project, tool_name, tool_input))
    refused, reasons, said, ran = False, [], [], []
    for hook in registered_commands(PRE_TOOL_USE, tool_name, plugin_root):
        command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))
        try:
            result = subprocess.run(
                ["sh", "-c", command],
                input=stdin,
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                timeout=hook.get("timeout", 60) + 30,
            )
        except subprocess.TimeoutExpired:
            said.append(f"{command}: timed out")
            continue
        ran.append(command)
        stop, reason, shown = _judged(result)
        if stop:
            refused = True
            reasons.append(reason)
        if shown:
            said.append(shown)
    return HookVerdict(refused, "\n".join(reasons), "\n".join(said), tuple(ran))


def _judged(result: subprocess.CompletedProcess[str]) -> tuple[bool, str, str]:
    """Whether a command refused, the reason it gave, and what it showed at all."""
    stderr = result.stderr.strip()
    if result.returncode == BLOCKING_EXIT:
        return True, stderr or result.stdout.strip(), stderr or result.stdout.strip()
    answer = _json_object(result.stdout)
    specific = answer.get("hookSpecificOutput") or {}
    shown = "\n".join(
        str(text)
        for text in (
            specific.get("permissionDecisionReason"),
            specific.get("additionalContext"),
            answer.get("reason"),
            answer.get("systemMessage"),
            answer.get("stopReason"),
            stderr if result.returncode != 0 else None,
        )
        if text
    )
    if specific.get("permissionDecision") == "deny":
        return True, str(specific.get("permissionDecisionReason") or ""), shown
    if answer.get("decision") == "block":
        return True, str(answer.get("reason") or ""), shown
    if answer.get("continue") is False:
        return True, str(answer.get("stopReason") or ""), shown
    return False, "", shown


def _json_object(stdout: str) -> dict:
    text = stdout.strip()
    if not text.startswith("{"):
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


# -- The calls a session makes ------------------------------------------------------------------


def write(project: Path, relpath: str, content: str, **kw) -> HookVerdict:
    return replay(project, "Write", {"file_path": str(project / relpath), "content": content}, **kw)


def edit(project: Path, relpath: str, old: str, new: str, **kw) -> HookVerdict:
    tool_input = {"file_path": str(project / relpath), "old_string": old, "new_string": new}
    return replay(project, "Edit", tool_input, **kw)


def read(project: Path, relpath: str, *, limit: int | None = None, **kw) -> HookVerdict:
    tool_input: dict = {"file_path": str(project / relpath)}
    if limit is not None:
        tool_input |= {"offset": 1, "limit": limit}
    return replay(project, "Read", tool_input, **kw)


def commit(project: Path, message: str = "Record the cache decision", **kw) -> HookVerdict:
    """The commit command a session runs, its changes already staged."""
    return replay(project, "Bash", {"command": f'git commit -m "{message}"'}, **kw)


def stage(project: Path, *relpaths: str) -> None:
    decision_records.git(project, "add", "--", *relpaths)


# -- A plugin copy a scenario may break ---------------------------------------------------------


def plugin_copy(dest: Path, *, without: tuple[str, ...] = ()) -> Path:
    """The plugin's tracked files under `PLUGIN_TREES`, copied to `dest`, minus `without`."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", *PLUGIN_TREES],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    ).stdout.split("\0")
    for rel in filter(None, listed):
        source = REPO_ROOT / rel
        if rel in without or not (source.is_file() or source.is_symlink()):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)
    return dest


def link_rule_into_home(scratch: Path, plugin_root: Path) -> None:
    """Link the moved rule where the installer puts it, under the scratch HOME the hooks see."""
    target = scratch / "home" / ".claude" / "rules" / "swe" / "adr-conventions.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.symlink_to(plugin_root / MOVED_RULE)
