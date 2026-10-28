"""What an arm's copy delivers, observed by running it offline and never trusted from its declaration.

Two observations, both over the runner's copy of a checkout:

- ``session_start`` is what is resident when a session opens: the rule files the copy's own
  installer links into a sandbox home (those without ``paths:`` frontmatter load at once), plus
  what the copy's registered session-start rule injection emits over a synthetic payload.
- ``hook_output`` is what one registered hook emits for a synthetic event payload.

Each answers ``Observed`` (the non-blank lines delivered, possibly none) or ``Refused`` naming
what could not be observed: a registry or manifest that cannot be read, a manifest row of an
install kind the linker does not know, a hook that exits non-zero, times out or prints something
that is not a hook result. A refusal is never turned into an empty observation, because an empty
one reads as "nothing arrives".

Every subprocess runs in a throwaway sandbox home and project directory, under a timeout, with an
environment built from scratch so the operator's own settings and rules cannot reach it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SUBPROCESS_TIMEOUT_SECONDS = 30
HOOK_REGISTRY = "hooks/hooks.json"
RULES_MANIFEST = "rules/_manifest.yaml"
SESSION_START = "SessionStart"
ALL_MATCHERS = ("", "*")
RULE_INJECTION_HOOK = "inject_rules.py"
RULE_INJECTION_SKIPPED = "## Praxion rule injection skipped"
LINKED_INSTALL = "symlink"
INJECTED_INSTALL = "hook-deliver"
INSTALL_KINDS = (LINKED_INSTALL, INJECTED_INSTALL)

# Must stay the call `live.materialize.install_user_scope` makes: the copy's own linker.
_LINK_RULES = 'source "$1/lib/install_shared.sh" && link_rules "$1/rules" "$2"'
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
        """Built from scratch; ``python3`` resolves to this interpreter, which has the hooks' PyYAML."""
        path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
        return {
            "HOME": str(self.home),
            "PATH": path,
            "CLAUDE_PLUGIN_ROOT": str(copy),
            "PYTHONDONTWRITEBYTECODE": "1",
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
        except OSError as error:
            return Refused(f"the linked rule {rule.relative_to(target)} cannot be read: {error}")
        if not _is_path_scoped(text):
            lines.extend(_body_lines(text))
    return Observed(tuple(lines))


def _manifest_refusal(copy: Path) -> Refused | None:
    manifest = copy / RULES_MANIFEST
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
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
    registry = copy / HOOK_REGISTRY
    try:
        groups = json.loads(registry.read_text(encoding="utf-8"))["hooks"].get(event, [])
    except (OSError, ValueError, KeyError, AttributeError) as error:
        return Refused(f"the hook registry {HOOK_REGISTRY} cannot be read: {error!r}")
    subject = str(payload.get("tool_name") or payload.get("source") or "")
    commands: list[str] = []
    for group in groups:
        try:
            if not _matches(group.get("matcher", ""), subject):
                continue
            commands.extend(
                hook["command"] for hook in group["hooks"] if hook.get("type") == "command"
            )
        except (re.error, KeyError, TypeError, AttributeError) as error:
            return Refused(f"the {event} hook group {group!r} is malformed: {error!r}")
    return [command for command in commands if script is None or script in command]


def _matches(matcher: str, subject: str) -> bool:
    """An empty or ``*`` matcher takes every event; any other is a regex over the whole subject."""
    return matcher in ALL_MATCHERS or re.fullmatch(matcher, subject) is not None


def _emitted_lines(result: subprocess.CompletedProcess[str], command: str) -> Observed | Refused:
    if not result.stdout.strip():
        return Observed(())
    try:
        output = json.loads(result.stdout)
        context = output.get("hookSpecificOutput", {}).get("additionalContext", "")
    except (ValueError, AttributeError):
        return Refused(f"the hook {command!r} printed something that is not a hook result")
    return Observed(_nonblank(context) if isinstance(context, str) else ())


# -- Running and reading --------------------------------------------------------------------


def _run(
    args: list[str], *, sandbox: _Sandbox, copy: Path, stdin: str, label: str
) -> subprocess.CompletedProcess[str] | Refused:
    try:
        result = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            cwd=sandbox.project,
            env=sandbox.environment(copy),
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Refused(f"{label} did not finish within {SUBPROCESS_TIMEOUT_SECONDS} seconds")
    except OSError as error:
        return Refused(f"{label} could not be started: {error}")
    if result.returncode != 0:
        return Refused(f"{label} exited {result.returncode}: {result.stderr.strip()[-300:]}")
    return result


def _body_lines(rule_text: str) -> tuple[str, ...]:
    return _nonblank(_FRONTMATTER.sub("", rule_text, count=1))


def _nonblank(text: str) -> tuple[str, ...]:
    return tuple(line for line in text.splitlines() if line.strip())
