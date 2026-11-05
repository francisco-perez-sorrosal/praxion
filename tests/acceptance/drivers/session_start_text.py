"""Driver for what a Claude Code session, or a spawn it starts, receives at its start.

No `claude` runs. The driver plays the harness's two delivery channels against a scratch
install, the way Claude Code documents them, and composes what reaches the model:

- **Instruction files**, loaded natively: the user's `CLAUDE.md` and every rule under the
  user rules directory without a `paths:` frontmatter key (both under `<home>/.claude`, or
  under `CLAUDE_CONFIG_DIR` when a launch sets it), then `CLAUDE.md`, `.claude/CLAUDE.md`,
  `CLAUDE.local.md` and the `.claude/rules/` rules without `paths:` of the start directory and
  of every directory above it (inside the scenario's sandbox), root first. `@path` imports
  outside code marks are expanded, four hops at most. A file matched by a `claudeMdExcludes`
  glob of the user settings or of the start directory's `.claude/settings.json` or
  `.claude/settings.local.json` (its link path or its target) is skipped. A rule file reaches
  the model from its first body line: its YAML frontmatter is read by the harness, not shown.
- **Hooks**, run as the harness runs them: every command the plugin's `hooks/hooks.json`
  registers for the event (matcher tested as the harness tests it), each its own process,
  the event as one JSON object on stdin, in the start directory, with `CLAUDE_PLUGIN_ROOT`
  the plugin root and `CLAUDE_PROJECT_DIR` the start directory. What reaches the model is
  each synchronous command's `additionalContext`; an `async` command runs (it may write) but
  delivers nothing.

A main session receives the instruction files and its `SessionStart` (`startup`) hooks' context.
An inheriting spawn receives the same instruction files plus its `SubagentStart` hooks'
strings, and a host-native one the text the `PreToolUse` (Agent) hooks put ahead of its prompt.
A lean spawn (its definition sets `omitClaudeMd: true`) receives the hooks' strings only.
The project's own instruction files are the project's, not process text: `process_text` leaves
their literal text out and keeps what they import from outside the project.

Hooks absent comes in three forms: `hooks="on"` (today's install), `hooks="off"` (no hook runs)
and `hooks="injection-off"` (every hook runs with `PRAXION_DISABLE_RULE_INJECTION=1`). An
`impaired_machine` keeps every hook running but takes away what the injector reads: its YAML
reader (an importable `yaml` that refuses to load, first on the hooks' `PYTHONPATH`) or its rules
manifest (missing, unreadable, or not YAML).

Bound here, from the specification and Claude Code's documentation: the delivery channels
above; `CLAUDE_PROJECT_DIR` is the directory the session started in; a headless session
carries `CLAUDE_CODE_ENTRYPOINT=sdk-cli` and an interactive one `cli`.

Every process runs hermetically (`kernel_sandbox.isolated_env`): a scratch HOME, no inherited
`CLAUDE*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variable, so no session or API is reached.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import isolated_env
from tests.acceptance.drivers.process_text_oracles import REPO_ROOT
from tests.acceptance.drivers.scratch_projects import copy_home, impair_manifest, plugin_root

KILL_SWITCH = "PRAXION_DISABLE_RULE_INJECTION"
HEADLESS, INTERACTIVE = "sdk-cli", "cli"
LEAN_ROLE = "researcher"
# A role outside the eligibility pin, so no flip can make it lean: the implementer, named first,
# was switched to its kernel on main (08ca61da).
INHERITING_ROLE = "systems-architect"
HOST_NATIVE = "general-purpose"
NON_TRIVIAL_PROMPT = (
    "Please restructure the payment module so refunds and charges share one validation path, "
    "add tests for both, and tell me what you would change in the API?"
)


# -- Instruction files -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    source: str  # "user", "project", "imported" or "hook:<script>"
    path: str
    text: str


def _has_paths(text: str) -> bool:
    if not text.startswith("---\n"):
        return False
    try:
        block = text[4 : text.index("\n---\n", 4)]
    except ValueError:
        return False
    try:
        data = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return False
    return isinstance(data, dict) and "paths" in data


def _rule_body(text: str) -> str:
    """A rule file as the model sees it: from the first line after its YAML frontmatter."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 3)
    return text if end < 0 else text[end + len("\n---\n") :]


def _excludes(user_dir: Path, start: Path) -> list[str]:
    patterns: list[str] = []
    for settings in (
        user_dir / "settings.json",
        start / ".claude" / "settings.json",
        start / ".claude" / "settings.local.json",
    ):
        if settings.is_file():
            try:
                patterns += json.loads(settings.read_text(encoding="utf-8")).get(
                    "claudeMdExcludes", []
                )
            except ValueError:
                pass
    return patterns


def _excluded(path: Path, patterns: list[str]) -> bool:
    forms = {str(path), str(path.resolve())}
    return any(fnmatch.fnmatchcase(form, p) for form in forms for p in patterns)


_IMPORT = re.compile(r"(?<![\w`])@((?:~|\.{0,2})?/?[\w./-]+)")


def _imports(file: Path, text: str, home: Path, depth: int, seen: set[Path]) -> list[Part]:
    if depth >= 4:
        return []
    found = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _IMPORT.finditer(re.sub(r"`[^`]*`", "", line)):
            raw = match.group(1)
            target = Path(raw.replace("~", str(home), 1)) if raw.startswith("~") else Path(raw)
            target = target if target.is_absolute() else file.parent / target
            if target.is_file() and target.resolve() not in seen:
                seen.add(target.resolve())
                body = target.read_text(encoding="utf-8")
                found.append(Part("imported", str(target), body))
                found += _imports(target, body, home, depth + 1, seen)
    return found


def instruction_files(
    start: Path, home: Path, sandbox: Path, config_dir: Path | None = None
) -> list[Part]:
    """The instruction files a session started in `start` loads, in load order."""
    user_dir = config_dir or home / ".claude"
    patterns = _excludes(user_dir, start)
    parts: list[Part] = []
    seen: set[Path] = set()

    def take(path: Path, source: str, rule: bool = False) -> None:
        if not path.is_file() or _excluded(path, patterns) or path.resolve() in seen:
            return
        text = path.read_text(encoding="utf-8")
        text = _rule_body(text) if rule else text
        seen.add(path.resolve())
        parts.append(Part(source, str(path), text))
        parts.extend(_imports(path, text, home, 0, seen))

    take(user_dir / "CLAUDE.md", "user")
    rules = user_dir / "rules"
    if rules.is_dir():
        for rule in sorted(rules.rglob("*.md")):
            if not _has_paths(rule.read_text(encoding="utf-8")):
                take(rule, "user", rule=True)
    chain = [start, *start.parents]
    top = sandbox.resolve()
    walk = [d for d in chain if d.resolve() == top or top in d.resolve().parents]
    for directory in reversed(walk):
        for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
            take(directory / name, "project")
        project_rules = directory / ".claude" / "rules"
        if project_rules.is_dir():
            for rule in sorted(project_rules.rglob("*.md")):
                if not _has_paths(rule.read_text(encoding="utf-8")):
                    take(rule, "project", rule=True)
    return parts


# -- Hooks -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HookRun:
    script: str
    exit_code: int | None
    context: str
    stderr: str


def _registered(plugin: Path, event: str, value: str) -> list[dict]:
    groups = json.loads((plugin / "hooks" / "hooks.json").read_text())["hooks"].get(event, [])
    chosen = []
    for group in groups:
        matcher = group.get("matcher", "")
        if matcher in ("", "*") or re.fullmatch(matcher, value):
            chosen += group["hooks"]
    return chosen


def _context_of(stdout: str) -> str:
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    inner = parsed.get("hookSpecificOutput") or {}
    for holder in (inner, parsed):
        if isinstance(holder, dict) and isinstance(holder.get("additionalContext"), str):
            return holder["additionalContext"]
    return ""


def _env(
    plugin: Path,
    start: Path,
    home: Path,
    scratch: Path,
    hooks: str,
    machine_env: tuple[tuple[str, str], ...] = (),
    **extra: str,
) -> dict:
    env = isolated_env(
        scratch, CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PROJECT_DIR=str(start), **extra
    )
    env["HOME"] = str(home)
    if hooks == "injection-off":
        env[KILL_SWITCH] = "1"
    env.update(machine_env)
    return env


def run_hooks(
    plugin: Path, event: str, value: str, payload: dict, start: Path, env: dict
) -> list[HookRun]:
    runs = []
    for hook in _registered(plugin, event, value):
        command = hook["command"]
        script = re.sub(r".*/hooks/", "", command.split(" 2>")[0]).split()[0]
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", command],
                input=json.dumps(payload),
                cwd=start,
                env=env,
                capture_output=True,
                text=True,
                timeout=int(hook.get("timeout", 60)) + 30,
            )
        except subprocess.TimeoutExpired:
            runs.append(HookRun(script, None, "", ""))
            continue
        context = "" if hook.get("async") else _context_of(proc.stdout)
        runs.append(HookRun(script, proc.returncode, context, proc.stderr))
    return runs


# -- What a start receives ---------------------------------------------------------------------------


def snapshot(directory: Path) -> dict[str, str]:
    """Every entry under `directory` except git's own, by relative path: a file's digest, a
    directory as `dir`, a link as its target."""
    found = {}
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory)
        if rel.parts[0] == ".git":
            continue
        if path.is_symlink():
            found[str(rel)] = f"link:{os.readlink(path)}"
        elif path.is_dir():
            found[str(rel)] = "dir"
        else:
            found[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def changed(before: dict[str, str], after: dict[str, str]) -> dict[str, tuple]:
    return {
        k: (before.get(k), after.get(k))
        for k in sorted(set(before) | set(after))
        if before.get(k) != after.get(k)
    }


@dataclass
class Start:
    parts: list[Part]
    hook_runs: list[HookRun] = field(default_factory=list)
    writes: dict[str, tuple] = field(default_factory=dict)  # in the start directory

    @property
    def text(self) -> str:
        """Everything that reaches the model."""
        return "\n\n".join(p.text for p in self.parts)

    @property
    def process_text(self) -> str:
        """What reaches the model, less the literal text of the project's own instruction files."""
        return "\n\n".join(p.text for p in self.parts if p.source != "project")

    @property
    def hook_text(self) -> str:
        return "\n\n".join(p.text for p in self.parts if p.source.startswith("hook:"))

    @property
    def warnings(self) -> str:
        return "\n".join(run.stderr for run in self.hook_runs)


@dataclass(frozen=True)
class Machine:
    """One scratch install: its HOME, the plugin and the sandbox every place lives in."""

    home: Path
    plugin: Path
    sandbox: Path
    env: tuple[tuple[str, str], ...] = ()  # set for every hook this machine runs

    def tokens(self) -> dict[Path, str]:
        return {
            self.home: "<home>",
            self.plugin: "<plugin>",
            self.sandbox: "<sandbox>",
            REPO_ROOT: "<repo>",
        }


def new_machine(template: Path, sandbox: Path) -> Machine:
    """A machine in `sandbox`: a copy of the installed HOME `template` and the plugin."""
    sandbox.mkdir(parents=True, exist_ok=True)
    return Machine(
        copy_home(template, sandbox / "home"), plugin_root(sandbox / "plugin"), sandbox.resolve()
    )


IMPAIRMENTS = (
    "yaml-reader-unavailable",
    "manifest-missing",
    "manifest-unreadable",
    "manifest-not-yaml",
)


def impaired_machine(template: Path, sandbox: Path, how: str) -> Machine:
    """A machine whose hooks all run, the rule injector's inputs impaired as `how` names."""
    machine = new_machine(template, sandbox)
    if how == "yaml-reader-unavailable":
        blocker = sandbox / "no-yaml" / "yaml"
        blocker.mkdir(parents=True)
        (blocker / "__init__.py").write_text(
            'raise ImportError("the YAML reader is unavailable in this scenario")\n'
        )
        return Machine(
            machine.home, machine.plugin, machine.sandbox, (("PYTHONPATH", str(blocker.parent)),)
        )
    impair_manifest(machine.plugin, how)
    return machine


_counter = iter(range(1, 1_000_000))


def session_start(
    machine: Machine, start: Path, *, hooks: str = "on", entrypoint: str = INTERACTIVE
) -> Start:
    """A main session started in `start`: what it receives and what its start writes there."""
    number = next(_counter)
    before = snapshot(start)
    parts = instruction_files(start, machine.home, machine.sandbox)
    runs: list[HookRun] = []
    if hooks != "off":
        env = _env(
            machine.plugin,
            start,
            machine.home,
            machine.sandbox / f".hooks-{number}",
            hooks,
            machine.env,
            CLAUDE_CODE_ENTRYPOINT=entrypoint,
        )
        payload = {
            "session_id": f"gating-{number}",
            "transcript_path": str(machine.sandbox / f".transcripts/gating-{number}.jsonl"),
            "cwd": str(start),
            "hook_event_name": "SessionStart",
            "source": "startup",
        }
        runs = run_hooks(machine.plugin, "SessionStart", "startup", payload, start, env)
        parts += [Part(f"hook:{r.script}", "", r.context) for r in runs if r.context]
    return Start(parts, runs, changed(before, snapshot(start)))


def _definition(machine: Machine, role: str) -> dict:
    text = (machine.plugin / "agents" / f"{role}.md").read_text(encoding="utf-8")
    return yaml.safe_load(text[4 : text.index("\n---\n", 4)]) or {}


def spawn_start(machine: Machine, start: Path, agent_type: str, *, hooks: str = "on") -> Start:
    """A spawn of `agent_type` (`praxion:<role>` or a host-native type) from a session in
    `start`: the instruction files unless it starts without them, plus its hooks' strings."""
    number = next(_counter)
    role = agent_type.split(":", 1)[1] if agent_type.startswith("praxion:") else None
    lean = role is not None and _definition(machine, role).get("omitClaudeMd") is True
    without_files = lean or agent_type in ("Explore", "Plan")
    parts = [] if without_files else instruction_files(start, machine.home, machine.sandbox)
    if hooks == "off":
        return Start(parts)
    env = _env(
        machine.plugin,
        start,
        machine.home,
        machine.sandbox / f".spawn-{number}",
        hooks,
        machine.env,
    )
    runs: list[HookRun] = []
    if role is None:
        original = "ORIGINAL-PROMPT: map the repository layout."
        payload = {
            "session_id": f"gating-spawn-{number}",
            "transcript_path": str(machine.sandbox / f".transcripts/spawn-{number}.jsonl"),
            "cwd": str(start),
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": f"toolu_gating_{number:04d}",
            "tool_input": {"prompt": original, "subagent_type": agent_type, "description": "x"},
        }
        for hook in _registered(machine.plugin, "PreToolUse", "Agent"):
            proc = subprocess.run(
                ["/bin/sh", "-c", hook["command"]],
                input=json.dumps(payload),
                cwd=start,
                env=env,
                capture_output=True,
                text=True,
                timeout=int(hook.get("timeout", 60)) + 30,
            )
            try:
                out = json.loads(proc.stdout).get("hookSpecificOutput") or {}
            except (ValueError, AttributeError):
                out = {}
            prompt = (out.get("updatedInput") or {}).get("prompt")
            if isinstance(prompt, str) and prompt.endswith(original):
                parts.append(Part("hook:preamble", "", prompt[: -len(original)]))
    payload = {
        "session_id": f"gating-spawn-{number}",
        "transcript_path": str(machine.sandbox / f".transcripts/spawn-{number}.jsonl"),
        "cwd": str(start),
        "hook_event_name": "SubagentStart",
        "agent_id": f"agent-{number:04d}",
        "agent_type": agent_type,
    }
    runs = run_hooks(machine.plugin, "SubagentStart", agent_type, payload, start, env)
    parts += [Part(f"hook:{r.script}", "", r.context) for r in runs if r.context]
    return Start(parts, runs)


def prompt_reminder(machine: Machine, start: Path) -> str:
    """What the prompt-submit hooks add to a non-trivial prompt in a session started in `start`."""
    number = next(_counter)
    env = _env(
        machine.plugin,
        start,
        machine.home,
        machine.sandbox / f".prompt-{number}",
        "on",
        machine.env,
    )
    payload = {
        "session_id": f"gating-prompt-{number}",
        "transcript_path": str(machine.sandbox / f".transcripts/prompt-{number}.jsonl"),
        "cwd": str(start),
        "hook_event_name": "UserPromptSubmit",
        "prompt": NON_TRIVIAL_PROMPT,
    }
    runs = run_hooks(machine.plugin, "UserPromptSubmit", "", payload, start, env)
    return "\n\n".join(r.context for r in runs if r.context)
