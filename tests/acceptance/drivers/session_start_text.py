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
  `.claude/settings.local.json` (its link path or its target) is skipped.
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
and `hooks="injection-off"` (every hook runs with `PRAXION_DISABLE_RULE_INJECTION=1`).

Bound here, from the specification and Claude Code's documentation: the delivery channels
above; `CLAUDE_PROJECT_DIR` is the directory the session started in; a headless session
carries `CLAUDE_CODE_ENTRYPOINT=sdk-cli` and an interactive one `cli`. A *statement* is a
sentence (`shipped_texts.sentences`) of at least 30 characters that is not a heading; process
text is compared as a multiset of statements, so a statement that arrives twice counts twice.

The frozen fixtures under `tests/acceptance/fixtures/project_gating/` were taken with `freeze`
from the tree at the pipeline base, so scenarios compare with today without reading history.

Unbound until its binding step: `declared_edits`, the record of the change's declared edits,
each with its before and after wording. It is read only when a reading differs from today.

Every process runs hermetically (`kernel_sandbox.isolated_env`): a scratch HOME, no inherited
`CLAUDE*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variable, so no session or API is reached.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tests.acceptance.drivers import model_routing_move as routing_move
from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError, isolated_env

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "project_gating"

# The five managed-only procedures (the spec's Terms). Four are texts frozen from the base; the
# decision context is what a project's own decision records put at session start, recognised
# by the titles of the fixture index planted in that project.
COORDINATION_PROTOCOL = "coordination protocol"
INTERMEDIATE_DOCUMENTS = "intermediate-documents rule"
ADR_RESIDENT = "ADR resident"
ROUTING_RESIDENT = "routing resident"
DECISION_CONTEXT = "decision context"
MANAGED_ONLY_TEXTS = {
    COORDINATION_PROTOCOL: "rules/swe/swe-agent-coordination-protocol.md",
    INTERMEDIATE_DOCUMENTS: "rules/swe/agent-intermediate-documents.md",
    ADR_RESIDENT: "rules/swe/adr-conventions-resident.md",
    ROUTING_RESIDENT: "rules/swe/agent-model-routing-resident.md",
}
MANAGED_ONLY = (*MANAGED_ONLY_TEXTS, DECISION_CONTEXT)

# The constitution's file-borne units, frozen from the base.
BEHAVIOURAL_CONTRACT = "behavioural contract"
USER_INSTRUCTIONS = "user's personal instructions"
GIT_CONVENTIONS = "git conventions"
CONSTITUTION_TEXTS = {
    BEHAVIOURAL_CONTRACT: "rules/swe/agent-behavioral-contract.md",
    USER_INSTRUCTIONS: "user CLAUDE.md",
    GIT_CONVENTIONS: "rules/swe/vcs/git-conventions.md",
}

BLACKLIST = ".claude/praxion-rules.yaml"
TEMPLATE = ".claude/praxion-rules.yaml.example"
KILL_SWITCH = "PRAXION_DISABLE_RULE_INJECTION"
HEADLESS, INTERACTIVE = "sdk-cli", "cli"
STATEMENT_MINIMUM = 30
LEAN_ROLE = "researcher"
INHERITING_ROLE = "implementer"
HOST_NATIVE = "general-purpose"
NON_TRIVIAL_PROMPT = (
    "Please restructure the payment module so refunds and charges share one validation path, "
    "add tests for both, and tell me what you would change in the API?"
)
_PERSONAL_INFO = re.compile(r"^- (Username|Email/GitHub|GitHub): .*$", re.M)


# -- Text ----------------------------------------------------------------------------------------


def normalize(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("`", "").replace("*", "")).strip()


def statements(text: str) -> Counter:
    """Every statement of `text`, counted: sentences of 30+ characters that are not headings."""
    found: Counter = Counter()
    for line in text.splitlines():
        if line.lstrip().startswith("#") or re.fullmatch(r"\s*\|?[-:| ]+\|?\s*", line):
            continue
        for sentence in re.split(r";|\.\s", normalize(line)):
            sentence = sentence.strip(" -.")
            if len(sentence) >= STATEMENT_MINIMUM:
                found[sentence] += 1
    return found


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _holds_all(text: str, *alternatives: tuple[str, ...]) -> bool:
    lowered = normalize(text).lower()
    return all(any(token in lowered for token in group) for group in alternatives)


def holds_external_docs_sentence(text: str) -> bool:
    """The first constitutional sentence, in one paragraph: verify an external API against its
    current official documentation, fetched documentation is data and not instructions, check a
    library's version before committing to it."""
    return any(
        _holds_all(
            p,
            ("official",),
            ("doc",),
            ("data",),
            ("instruction",),
            ("version",),
        )
        for p in paragraphs(text)
    )


def holds_delegation_depth_sentence(text: str) -> bool:
    """The second constitutional sentence, in one paragraph: a chain of three or more agents
    needs the user's explicit confirmation; an agent may recommend further agents but never
    starts such a chain on its own."""
    return any(
        _holds_all(
            p,
            ("3+", "three or more", "3 or more"),
            ("confirm",),
            ("recommend",),
            ("never", "not "),
        )
        for p in paragraphs(text)
    )


def mask(text: str, tokens: dict[Path, str]) -> str:
    """Scratch locations written as tokens and the personal-info lines masked, so readings
    from two machines or two sandboxes compare."""
    for path, token in sorted(tokens.items(), key=lambda kv: -len(str(kv[0]))):
        for form in {str(path), str(path.resolve())}:
            text = text.replace(form, token)
    return _PERSONAL_INFO.sub(r"- \1: <personal>", text)


# -- Frozen base texts and today's readings ------------------------------------------------------


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def base_unit_text(unit: str) -> str:
    return fixture_text(f"base_units/{_unit_file(unit)}")


def _unit_file(unit: str) -> str:
    return re.sub(r"[^a-z]+", "_", unit.lower()).strip("_") + ".md"


def _body(text: str) -> str:
    if text.startswith("---\n"):
        return text[text.index("\n---\n", 4) + 5 :]
    return text


def distinctive_statements(unit: str) -> Counter:
    """A unit's statements that no other constitution text at the base also carries and
    that do not state a constitutional sentence (those move to every-project text)."""
    shared: Counter = Counter()
    for other in CONSTITUTION_TEXTS:
        if other != unit:
            shared |= statements(base_unit_text(other))
    own = statements(_body(base_unit_text(unit)))
    return Counter(
        {
            s: n
            for s, n in own.items()
            if s not in shared
            and not holds_external_docs_sentence(s)
            and not holds_delegation_depth_sentence(s)
        }
    )


def held_statements(unit: str, text: str) -> list[str]:
    """The unit's distinctive statements found in `text`."""
    present = statements(text)
    return sorted(s for s in distinctive_statements(unit) if s in present)


def missing_statements(unit: str, text: str) -> list[str]:
    """The unit's statements (at the base) that `text` does not carry and no declared edit
    accounts for."""
    present = statements(text)
    missing = [s for s in statements(_body(base_unit_text(unit))) if s not in present]
    return _unexcused(missing, "before")


def holds_decision_context(text: str, marker: str) -> bool:
    return marker.lower() in normalize(text).lower()


@dataclass(frozen=True)
class Changes:
    missing: list[str]  # today's statements gone, or arriving fewer times
    added: list[str]  # statements new, or arriving more times

    @property
    def none(self) -> bool:
        return not self.missing and not self.added


def unexplained_changes(today: str, now: str) -> Changes:
    """How `now` differs from `today` by statement, less what the declared edits account for."""
    before, after = statements(today), statements(now)
    missing = sorted((before - after).elements())
    added = sorted((after - before).elements())
    return Changes(_unexcused(missing, "before"), _unexcused(added, "after"))


def _unexcused(found: list[str], side: str) -> list[str]:
    if not found:
        return []
    wordings = [normalize(edit[side]).lower() for edit in declared_edits()]
    return [s for s in found if not any(s.lower() in w for w in wordings if w)]


def declared_edits() -> list[dict[str, str]]:
    """The change's declared edits, each `{"before": ..., "after": ...}` in its recorded wording
    (an insertion's `before`, or a removal's `after`, is empty)."""
    raise UnboundDriverError(
        "the record of the declared edits (the two constitutional sentences relocated into "
        "every-project text, and every-project sentences reworded where a managed-only "
        "procedure is absent), each with its before and after wording, is not bound yet"
    )


# -- Places ---------------------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Gating Acceptance",
            "-c",
            "user.email=gating@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        env=isolated_env(cwd.parent / f".{cwd.name}-git"),
        check=True,
        capture_output=True,
        timeout=60,
    )


def decisions_index(marker: str) -> str:
    """A decision index whose two decisions carry `marker` in their titles."""
    return fixture_text("decisions_index.md").replace("<marker>", marker)


def plant_state(directory: Path, marker: str | None = None) -> Path:
    """Give `directory` a `.ai-state/` and, with `marker`, a decision index."""
    state = directory / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    if marker is not None:
        (state / "decisions").mkdir(exist_ok=True)
        (state / "decisions" / "DECISIONS_INDEX.md").write_text(
            decisions_index(marker), encoding="utf-8"
        )
    return directory


def repository(path: Path, *, state_marker: str | None = None, managed: bool = False) -> Path:
    """A git working tree with one commit; `managed` (or a marker) gives it committed state."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("# scratch\n", encoding="utf-8")
    if managed or state_marker is not None:
        plant_state(path, state_marker)
        (path / ".ai-state" / "README.md").write_text("state\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "start")
    return path


def linked_worktree(main: Path, path: Path) -> Path:
    _git(main, "worktree", "add", "-q", "-b", "gating-wt", str(path))
    return path


def shipped_instructions() -> str:
    """A project CLAUDE.md written from this checkout's shipped instruction blocks (every
    `claude/canonical-blocks/*.md` but the hackathon block, in name order)."""
    blocks = sorted((REPO_ROOT / "claude" / "canonical-blocks").glob("*.md"))
    return "\n\n".join(
        b.read_text(encoding="utf-8") for b in blocks if b.name != "hackathon-mode.md"
    )


def project_with_current_instructions(path: Path) -> Path:
    """A managed project whose own CLAUDE.md this checkout's shipped blocks wrote."""
    repository(path, managed=True)
    (path / "CLAUDE.md").write_text(shipped_instructions(), encoding="utf-8")
    return path


def project_with_old_instructions(path: Path) -> Path:
    """A managed project whose own CLAUDE.md the base's shipped blocks wrote."""
    repository(path, managed=True)
    (path / "CLAUDE.md").write_text(fixture_text("base_project_CLAUDE.md"), encoding="utf-8")
    return path


def write_blacklist(directory: Path, disable: list[str]) -> None:
    listed = "".join(f"  - '{pattern}'\n" for pattern in disable)
    target = directory / BLACKLIST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"version: 1\ndisable:\n{listed}", encoding="utf-8")


# -- The install and the plugin --------------------------------------------------------------------


def installed_home(scratch: Path) -> Path:
    """A HOME after `bash install.sh code --relink` from this checkout (the scratch's `home`)."""
    result = routing_move.install(scratch)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return scratch / "home"


def copy_home(template: Path, dest: Path) -> Path:
    shutil.copytree(template, dest, symlinks=True)
    return dest


def plugin_root(dest: Path) -> Path:
    """This checkout as the running plugin, with a frozen kernel adoption ledger in place of the
    live one, so what a spawn receives never follows the checkout's own `.ai-state/`."""
    dest.mkdir(parents=True, exist_ok=True)
    for entry in REPO_ROOT.iterdir():
        if entry.name not in (".ai-state", ".ai-work", ".git", ".claude"):
            (dest / entry.name).symlink_to(entry)
    (dest / ".ai-state").mkdir()
    shutil.copy(FIXTURES / "kernel_adoption.yaml", dest / ".ai-state" / "kernel_adoption.yaml")
    return dest


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

    def take(path: Path, source: str) -> None:
        if not path.is_file() or _excluded(path, patterns) or path.resolve() in seen:
            return
        text = path.read_text(encoding="utf-8")
        seen.add(path.resolve())
        parts.append(Part(source, str(path), text))
        parts.extend(_imports(path, text, home, 0, seen))

    take(user_dir / "CLAUDE.md", "user")
    rules = user_dir / "rules"
    if rules.is_dir():
        for rule in sorted(rules.rglob("*.md")):
            if not _has_paths(rule.read_text(encoding="utf-8")):
                take(rule, "user")
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
                    take(rule, "project")
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


def _env(plugin: Path, start: Path, home: Path, scratch: Path, hooks: str, **extra: str) -> dict:
    env = isolated_env(
        scratch, CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PROJECT_DIR=str(start), **extra
    )
    env["HOME"] = str(home)
    if hooks == "injection-off":
        env[KILL_SWITCH] = "1"
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
    env = _env(machine.plugin, start, machine.home, machine.sandbox / f".spawn-{number}", hooks)
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
    env = _env(machine.plugin, start, machine.home, machine.sandbox / f".prompt-{number}", "on")
    payload = {
        "session_id": f"gating-prompt-{number}",
        "transcript_path": str(machine.sandbox / f".transcripts/prompt-{number}.jsonl"),
        "cwd": str(start),
        "hook_event_name": "UserPromptSubmit",
        "prompt": NON_TRIVIAL_PROMPT,
    }
    runs = run_hooks(machine.plugin, "UserPromptSubmit", "", payload, start, env)
    return "\n\n".join(r.context for r in runs if r.context)


# -- Readings over the whole checkout ---------------------------------------------------------------


def budget_reading(machine: Machine, directory: Path) -> tuple[int, dict]:
    """`measure_token_budget.py --json --repo-root <directory>` under the scratch install."""
    env = isolated_env(machine.sandbox / ".budget")
    env["HOME"] = str(machine.home)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "measure_token_budget.py"),
            "--json",
            "--repo-root",
            str(directory),
        ],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode in (0, 1), result.stdout[-2000:] + result.stderr[-2000:]
    return result.returncode, json.loads(result.stdout)


def counted_text(reading: dict) -> str:
    """The text of every file the always-loaded reading counts."""
    return "\n\n".join(Path(f).read_text(encoding="utf-8") for f in reading["files"])


EXPORTERS = (
    ("codex-agents", "codex/config/export-codex-agents.py"),
    ("codex-adapter", "codex/config/export-codex-pipeline-adapter.py"),
    ("codex-bridge", "codex/config/export-codex-rules-bridge.py"),
    ("codex-skills", "codex/config/export-codex-skills.py"),
)


def export_digests(scratch: Path) -> dict[str, str]:
    """Every file the Codex and Cursor exporters write from this checkout, by digest, with the
    checkout's location and the output location normalised out."""
    found: dict[str, str] = {}
    runs = [
        (name, [script, "--repo-root", str(REPO_ROOT), "--out-dir", "{out}"])
        for name, script in EXPORTERS
    ]
    runs.append(("cursor", ["cursor/config/export-cursor-rules.py", str(REPO_ROOT), "{out}"]))
    for name, argv in runs:
        out = scratch / name
        env = isolated_env(scratch / f".{name}-env")
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / argv[0]),
                *(a.replace("{out}", str(out)) for a in argv[1:]),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"{name} export failed: {result.stdout[-1000:]}{result.stderr[-1000:]}"
        )
        for path in sorted(out.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                for root, token in ((REPO_ROOT, b"<repo>"), (out, b"<out>")):
                    for form in {str(root), str(root.resolve())}:
                        data = data.replace(form.encode(), token)
                found[f"{name}/{path.relative_to(out)}"] = hashlib.sha256(data).hexdigest()
    return found


def kernel_digests() -> dict[str, str]:
    kernels = REPO_ROOT / "claude" / "kernels"
    files = [*sorted(kernels.glob("*.md")), kernels / "index.json"]
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


# -- Freezing --------------------------------------------------------------------------------------


def base_readings(scratch: Path) -> dict[str, str]:
    """Today's readings the scenarios compare with, masked: name -> text."""
    template = installed_home(scratch / "install")
    readings: dict[str, str] = {}

    def machine(name: str) -> Machine:
        sandbox = scratch / name
        sandbox.mkdir()
        return Machine(
            copy_home(template, sandbox / "home"), plugin_root(sandbox / "plugin"), sandbox
        )

    m = machine("managed")
    project = repository(m.sandbox / "project", state_marker="root gating fixture")
    for entry in (INTERACTIVE, HEADLESS):
        readings[f"managed-main-{entry}"] = mask(
            session_start(m, project, entrypoint=entry).process_text, m.tokens()
        )
    for kind in ("off", "injection-off"):
        readings[f"managed-main-hooks-{kind}"] = mask(
            session_start(m, project, hooks=kind).process_text, m.tokens()
        )
    for agent in (f"praxion:{INHERITING_ROLE}", HOST_NATIVE, f"praxion:{LEAN_ROLE}"):
        readings[f"managed-spawn-{agent}"] = mask(
            spawn_start(m, project, agent).process_text, m.tokens()
        )
    m = machine("onboarded")
    onboarded = project_with_current_instructions(m.sandbox / "onboarded")
    readings["project-CLAUDE.md"] = shipped_instructions()
    readings["managed-main-onboarded"] = mask(session_start(m, onboarded).process_text, m.tokens())
    m = machine("blacklisted")
    plain = m.sandbox / "plain"
    plain.mkdir()
    write_blacklist(plain, BLACKLIST_PATTERNS)
    started = session_start(m, plain)
    readings["unmanaged-blacklist-writes"] = json.dumps(
        {k: [mask(str(v), m.tokens()) for v in pair] for k, pair in started.writes.items()}
    )
    settings = plain / ".claude" / "settings.json"
    readings["unmanaged-blacklist-settings"] = mask(
        settings.read_text(encoding="utf-8") if settings.exists() else "", m.tokens()
    )
    readings["unmanaged-blacklist-warnings"] = "\n".join(
        line for line in mask(started.warnings, m.tokens()).splitlines() if CORE_RULE in line
    )
    m = machine("budget")
    budget_project = repository(m.sandbox / "budget-project", managed=True)
    _, reading = budget_reading(m, budget_project)
    readings["managed-budget-text"] = mask(counted_text(reading), m.tokens())
    return readings


BLACKLIST_PATTERNS = [
    "swe/vcs/git-conventions",
    "swe/coding-style",
    "swe/agent-behavioral-contract",
]
CORE_RULE = "swe/agent-behavioral-contract"


def freeze(scratch: Path) -> None:
    """Write every fixture from this tree, which must be the pipeline base."""
    units = FIXTURES / "base_units"
    units.mkdir(parents=True, exist_ok=True)
    for unit, rel in {**MANAGED_ONLY_TEXTS, **CONSTITUTION_TEXTS}.items():
        if rel == "user CLAUDE.md":
            continue
        (units / _unit_file(unit)).write_bytes((REPO_ROOT / rel).read_bytes())
    readings = base_readings(scratch)
    home_claude = scratch / "install" / "home" / ".claude" / "CLAUDE.md"
    (units / _unit_file(USER_INSTRUCTIONS)).write_text(
        mask(home_claude.read_text(encoding="utf-8"), {}), encoding="utf-8"
    )
    (FIXTURES / "base_project_CLAUDE.md").write_text(
        readings.pop("project-CLAUDE.md"), encoding="utf-8"
    )
    (FIXTURES / "base_readings.json").write_text(
        json.dumps(readings, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    (FIXTURES / "base_exports.json").write_text(
        json.dumps(export_digests(scratch / "exports"), indent=1, sort_keys=True) + "\n"
    )
    (FIXTURES / "base_kernels.json").write_text(
        json.dumps(kernel_digests(), indent=1, sort_keys=True) + "\n"
    )


def base_reading(name: str) -> str:
    return fixture_json("base_readings.json")[name]
