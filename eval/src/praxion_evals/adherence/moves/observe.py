"""What an arm's copy delivers, observed by running it offline and never trusted from its declaration.

Two observations, both over the runner's copy of a checkout:

- ``session_start`` is what is resident when a session opens: the rule files the copy's own
  installer links into a sandbox home (those without ``paths:`` frontmatter load at once), plus
  what the copy's registered session-start rule injection emits over a synthetic payload.
- ``hook_output`` is what one registered hook emits for a synthetic event payload.

Each answers ``Observed`` (the non-blank lines delivered, possibly none) or ``Refused`` naming
what could not be observed: a registry or manifest that cannot be read, a manifest row of an
install kind the linker does not know, a matcher the payload cannot be tested against, a hook that
is not a command, exits non-zero, times out, or prints something that is not a hook result carrying
context to observe. A refusal is never turned into an empty observation, because an empty
one reads as "nothing arrives".

Every subprocess runs in a throwaway sandbox home and project directory, under a timeout, with an
environment built from scratch so the operator's own settings and rules cannot reach it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# The linker call `install_user_scope` makes, shared so the observed residency is the installed one.
from praxion_evals.live.materialize import _LINK_RULES
from praxion_evals.live.session import FIXED_SWITCHES

SUBPROCESS_TIMEOUT_SECONDS = 30
HOOK_REGISTRY = "hooks/hooks.json"
RULES_MANIFEST = "rules/_manifest.yaml"
SESSION_START = "SessionStart"
ALL_MATCHERS = ("", "*")
RULE_INJECTION_HOOK = "inject_rules.py"
# Checklist: mirrors the header `_report_unavailable` prints in hooks/inject_rules.py; a canary
# test reads that file for it, so change both together.
RULE_INJECTION_SKIPPED = "## Praxion rule injection skipped"
COMMAND_HOOK = "command"
MATCHER_SUBJECT_FIELDS = ("tool_name", "source", "agent_type")
STDERR_TAIL_CHARS = 300
LINKED_INSTALL = "symlink"
INJECTED_INSTALL = "hook-deliver"
INSTALL_KINDS = (LINKED_INSTALL, INJECTED_INSTALL)

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_PATHS_KEY = re.compile(r"^paths\s*:", re.MULTILINE)


@dataclass(frozen=True)
class Observed:
    lines: tuple[str, ...]  # non-blank lines, in delivery order; empty is a real observation


@dataclass(frozen=True)
class Refused:
    reason: str  # names the file, row or hook that could not be observed


Observation = Observed | Refused


@dataclass(frozen=True)
class _Sandbox:
    home: Path
    project: Path

    def environment(self, copy: Path) -> dict[str, str]:
        """Built from scratch; ``python3`` resolves to this interpreter, which has the hooks' PyYAML.

        The runner's own kill switches keep the side-effect hooks (event posting, relinking,
        autocommit) from reaching the network or the operator's checkout.
        """
        path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
        return {
            **FIXED_SWITCHES,
            "HOME": str(self.home),
            "PATH": path,
            "CLAUDE_PLUGIN_ROOT": str(copy),
        }


@contextmanager
def _sandbox() -> Iterator[_Sandbox]:
    with tempfile.TemporaryDirectory(prefix="moves-observe-") as root:
        sandbox = _Sandbox(Path(root) / "home", Path(root) / "project")
        sandbox.home.mkdir()
        sandbox.project.mkdir()
        yield sandbox


# -- Public observations --------------------------------------------------------------------


def session_start(copy: Path) -> Observation:
    """The lines resident at session start in ``copy``: linked rules, then the rule injection."""
    copy = copy.resolve()
    with _sandbox() as sandbox:
        linked = _linked_rule_lines(copy, sandbox)
        if isinstance(linked, Refused):
            return linked
        payload = {"source": "startup", "cwd": str(sandbox.project)}
        injected = _registered_output(
            copy, SESSION_START, payload, sandbox, script=RULE_INJECTION_HOOK
        )
    if isinstance(injected, Refused):
        return injected
    if injected.lines[:1] and injected.lines[0].startswith(RULE_INJECTION_SKIPPED):
        return Refused("the rule injection reports it was skipped: " + " ".join(injected.lines[1:]))
    return Observed(linked.lines + injected.lines)


def hook_output(
    copy: Path, event: str, payload: Mapping[str, Any], *, script: str | None = None
) -> Observation:
    """The lines the hooks registered for ``event`` and matching ``payload`` emit.

    ``script`` narrows the run to hooks whose command names that file, so a copy's gates and
    loggers are not executed to observe one rule hook.
    """
    copy = copy.resolve()
    with _sandbox() as sandbox:
        return _registered_output(copy, event, payload, sandbox, script=script)


# -- Rules the installer links --------------------------------------------------------------


def _linked_rule_lines(copy: Path, sandbox: _Sandbox) -> Observed | Refused:
    refusal = _manifest_refusal(copy)
    if refusal is not None:
        return refusal
    target = sandbox.home / ".claude" / "rules"
    link = _run(
        ["bash", "-c", _LINK_RULES, "_", str(copy), str(target)],
        sandbox=sandbox,
        copy=copy,
        stdin="",
        label="the rule linker",
    )
    if isinstance(link, Refused):
        return link
    lines: list[str] = []
    for rule in sorted(target.rglob("*.md")):
        try:
            text = rule.read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            return Refused(f"the linked rule {rule.relative_to(target)} cannot be read: {error}")
        if not _is_path_scoped(text):
            lines.extend(_body_lines(text))
    return Observed(tuple(lines))


def _manifest_refusal(copy: Path) -> Refused | None:
    manifest = copy / RULES_MANIFEST
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as error:
        return Refused(f"the rule manifest {RULES_MANIFEST} cannot be read: {error}")
    rows = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return Refused(f"the rule manifest {RULES_MANIFEST} holds no list of rules")
    for row in rows:
        install = row.get("install") if isinstance(row, dict) else None
        if install not in INSTALL_KINDS:
            name = row.get("id", row) if isinstance(row, dict) else row
            return Refused(
                f"the manifest row {name!r} has the install kind {install!r}, "
                f"not one of {list(INSTALL_KINDS)}"
            )
    return None


def _is_path_scoped(rule_text: str) -> bool:
    frontmatter = _FRONTMATTER.match(rule_text)
    return frontmatter is not None and _PATHS_KEY.search(frontmatter.group(1)) is not None


# -- Hooks the copy registers ---------------------------------------------------------------


def _registered_output(
    copy: Path,
    event: str,
    payload: Mapping[str, Any],
    sandbox: _Sandbox,
    *,
    script: str | None,
) -> Observed | Refused:
    commands = _matching_commands(copy, event, payload, script)
    if isinstance(commands, Refused):
        return commands
    stdin = json.dumps({"cwd": str(sandbox.project), **payload, "hook_event_name": event})
    lines: list[str] = []
    for command in commands:
        result = _run(
            ["bash", "-c", command], sandbox=sandbox, copy=copy, stdin=stdin, label=command
        )
        if isinstance(result, Refused):
            return result
        emitted = _emitted_lines(result, command)
        if isinstance(emitted, Refused):
            return emitted
        lines.extend(emitted.lines)
    return Observed(tuple(lines))


def _matching_commands(
    copy: Path, event: str, payload: Mapping[str, Any], script: str | None
) -> list[str] | Refused:
    groups = _event_groups(copy, event)
    if isinstance(groups, Refused):
        return groups
    subject = next((str(payload[key]) for key in MATCHER_SUBJECT_FIELDS if payload.get(key)), None)
    commands: list[str] = []
    registered = script is None
    for group in groups:
        found = _group_commands(event, group, subject, script)
        if isinstance(found, Refused):
            return found
        registered = registered or found[0]
        commands.extend(found[1])
    if not registered:
        return Refused(f"no {event} hook in {HOOK_REGISTRY} runs the script {script!r}")
    return commands


def _event_groups(copy: Path, event: str) -> list[Any] | Refused:
    try:
        groups = json.loads((copy / HOOK_REGISTRY).read_text(encoding="utf-8"))["hooks"].get(
            event, []
        )
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as error:
        return Refused(f"the hook registry {HOOK_REGISTRY} cannot be read: {error!r}")
    if not isinstance(groups, list):
        return Refused(f"the hook registry {HOOK_REGISTRY} holds no list of groups for {event}")
    return groups


def _group_commands(
    event: str, group: Any, subject: str | None, script: str | None
) -> tuple[bool, list[str]] | Refused:
    """Whether the script is registered in this group, and its commands the payload reaches."""
    try:
        selected = [
            hook for hook in group["hooks"] if script is None or script in hook.get("command", "")
        ]
        matcher = group.get("matcher", "")
        if not selected:
            return False, []
        if matcher not in ALL_MATCHERS and subject is None:
            return Refused(
                f"the {event} matcher {matcher!r} keys on a field the payload does not "
                f"carry (one of {list(MATCHER_SUBJECT_FIELDS)})"
            )
        if not _matches(matcher, subject or ""):
            return True, []
        other = next((hook for hook in selected if hook.get("type") != COMMAND_HOOK), None)
        if other is not None:
            return Refused(f"the {event} hook {other!r} is not a command hook and cannot be run")
        return True, [hook["command"] for hook in selected]
    except (re.error, KeyError, TypeError, AttributeError) as error:
        return Refused(f"the {event} hook group {group!r} is malformed: {error!r}")


def _matches(matcher: str, subject: str) -> bool:
    """An empty or ``*`` matcher takes every event; any other is a regex over the whole subject."""
    return matcher in ALL_MATCHERS or re.fullmatch(matcher, subject) is not None


def _emitted_lines(result: subprocess.CompletedProcess[str], command: str) -> Observed | Refused:
    if not result.stdout.strip():
        return Observed(())
    try:
        output = json.loads(result.stdout)
    except ValueError:
        output = None
    if not isinstance(output, dict):
        return Refused(f"the hook {command!r} printed something that is not a hook result")
    if not output:
        return Observed(())
    specific = output.get("hookSpecificOutput")
    context = specific.get("additionalContext") if isinstance(specific, dict) else None
    if not isinstance(context, str):
        return Refused(
            f"the hook {command!r} printed a result with no additionalContext to observe"
        )
    return Observed(_nonblank(context))


# -- Running and reading --------------------------------------------------------------------


def _run(
    args: list[str], *, sandbox: _Sandbox, copy: Path, stdin: str, label: str
) -> subprocess.CompletedProcess[str] | Refused:
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=sandbox.project,
            env=sandbox.environment(copy),
            start_new_session=True,
        )
    except OSError as error:
        return Refused(f"{label} could not be started: {error}")
    try:
        stdout, stderr = process.communicate(stdin, timeout=SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        return Refused(f"{label} did not finish within {SUBPROCESS_TIMEOUT_SECONDS} seconds")
    if process.returncode != 0:
        tail = stderr.strip()[-STDERR_TAIL_CHARS:]
        return Refused(f"{label} exited {process.returncode}: {tail}")
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _kill_group(process: subprocess.Popen[str]) -> None:
    """A timeout takes the hook's whole process group, so no grandchild outlives the sandbox."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.communicate()


def _body_lines(rule_text: str) -> tuple[str, ...]:
    return _nonblank(_FRONTMATTER.sub("", rule_text, count=1))


def _nonblank(text: str) -> tuple[str, ...]:
    return tuple(line for line in text.splitlines() if line.strip())
