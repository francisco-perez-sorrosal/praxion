"""Driver for what a spawned role holds at its first turn, reached the way the harness reaches it.

A spawn passes through two harness boundaries, and this driver crosses both exactly as Claude
Code does, against a sandbox copy of the plugin, so any delivery the design registers there is
exercised without the driver knowing which one it is:

1. `PreToolUse` for the `Agent` tool: every command `hooks/hooks.json` registers for it (matcher
   tested against `tool_name`) runs as its own process with the event on stdin. A command may
   rewrite the call through `hookSpecificOutput.updatedInput`; what it adds around the
   delegation reaches the agent with it. Exit 2, `decision: block`, `continue: false` or
   `permissionDecision: deny` refuse the call.
2. `SubagentStart`: every command registered for it (matcher tested against `agent_type`) runs
   as its own process; each `hookSpecificOutput.additionalContext` string it prints reaches the
   spawn. Hooks run in parallel, as the harness runs them; their strings are read back in
   registration order.

Between the two, the driver leaves what the harness has filed by then: the main session's
transcript holding the `Agent` call, and the spawn's own transcript opened by its delegation,
under the sandbox's config directory (`CLAUDE_CONFIG_DIR`). A role's preloaded skills are the
`skills:` list of its definition's frontmatter; the harness puts each one's body in the spawn, so
a preload counts as one copy of that skill's text.

The skill's links are reachable when what a hook adds around the skill's text names, as an
absolute path, a directory inside the installation (the skill's own, or the installation's root)
against which every relative link of the body reaches an existing file and section: the same
directory a preload gives the agent, so the body needs no rewriting.

Bound here, because the specification or the base commit fixes them: the marker, the two roles,
the skill's text (its `SKILL.md` after the metadata header), the 10,000-character limit one
context string may carry, the two events and their payload fields as the base's own drivers
send them, and the isolation every process gets (`kernel_sandbox.isolated_env`).

Bound to the designed surfaces, each stated in its hook's docstring: a resume (`PreToolUse` for
`SendMessage`, then `SubagentStart` again with the same agent id), the canary (the delivery
module deleted from the installation), the move (the installation's own
`scripts/refactoring_move.py`), the failure records (the project's observation log, read through
the installation's own reader) and the arrival matcher (the delivery module's own
`shows_arrival`). Each of them fails loudly, never quietly, while the production piece it reaches
does not exist.
"""

from __future__ import annotations

import atexit
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from itertools import count
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import isolated_env

REPO_ROOT = Path(__file__).resolve().parents[3]

MARKER = "[Phase: Refactoring]"
ROLES = ("implementer", "test-engineer")
SKILL = "skills/refactoring/SKILL.md"
SKILL_NAME = "refactoring"
DELIVERY_MODULE = "hooks/_skill_delivery.py"
MOVE_TOOL = "scripts/refactoring_move.py"
CHANNEL_LIMIT = 10_000  # characters one context string may carry
DISTINCT_LINE = 40  # a body line this long counts copies; shorter ones recur in other texts

_MARKER_PATTERN = re.compile(r"\[\s*phase\s*:\s*refactoring\s*\]", re.IGNORECASE)


# -- The plugin installation ------------------------------------------------------------------

# Trees no spawn-time delivery reads: the suite itself, other packages, narrative docs.
_SKIPPED_TREES = (
    "tests",
    "dashboard_app",
    "eval",
    "evals",
    "task-chronograph-mcp",
    "fitness",
    ".obsidian",
    ".github",
    "docs",
    ".ai-work",
)
_KEPT_STATE = (".ai-state/kernel_adoption.yaml",)
_TEST_MODULE = re.compile(r"(?:^|/)(?:test_[^/]*\.py|conftest\.py)$")

_template: Path | None = None
_template_lock = threading.Lock()


def _in_installation(rel: str) -> bool:
    top = rel.split("/", 1)[0]
    return (
        bool(rel)
        and top not in _SKIPPED_TREES
        and (top != ".ai-state" or rel.startswith(_KEPT_STATE))
        and not (top in ("hooks", "scripts") and _TEST_MODULE.search(rel))
        and ((REPO_ROOT / rel).is_file() or (REPO_ROOT / rel).is_symlink())
    )


def _installation_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split("\0")
    return sorted(rel for rel in set(listed) if _in_installation(rel))


def _template_checkout() -> Path:
    """This process's read-only copy of the checkout; every sandbox copies it."""
    global _template
    with _template_lock:
        if _template is None:
            parent = Path(tempfile.mkdtemp(prefix="refactoring-delivery-"))
            atexit.register(shutil.rmtree, parent, ignore_errors=True)
            dest = parent / "plugin"
            for rel in _installation_files():
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO_ROOT / rel, target, follow_symlinks=True)
            assert (dest / SKILL).is_file(), f"the installation copy lacks {SKILL}"
            _template = dest
        return _template


@dataclass(frozen=True)
class Installation:
    """A plugin installation a scenario may change freely."""

    root: Path

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str) -> str:
        return self.path(rel).read_text(encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def new_installation(dest: Path) -> Installation:
    shutil.copytree(_template_checkout(), dest, symlinks=True)
    return Installation(dest)


def skill_body(root: Path) -> str:
    """The refactoring skill's text: its `SKILL.md` after the metadata header."""
    text = (root / SKILL).read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{SKILL} has no metadata header"
    return text.split("\n---\n", 1)[1]


def _definition(role: str) -> str:
    return f"agents/{role}.md"


def _frontmatter(text: str) -> tuple[str, str]:
    assert text.startswith("---\n"), "an agent definition opens with its frontmatter"
    head, rest = text[4:].split("\n---\n", 1)
    return head, rest


def preloaded_skills(root: Path, role: str) -> tuple[str, ...]:
    head, _ = _frontmatter((root / _definition(role)).read_text(encoding="utf-8"))
    skills = (yaml.safe_load(head) or {}).get("skills") or []
    return tuple(str(s) for s in skills)


def _set_preloads(installation: Installation, role: str, skills: tuple[str, ...]) -> None:
    rel = _definition(role)
    head, rest = _frontmatter(installation.read(rel))
    lines = head.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("skills:")), None)
    end = start + 1 if start is not None else len(lines)
    while start is not None and end < len(lines) and lines[end].startswith((" ", "\t", "-")):
        end += 1
    replacement = [f"skills: [{', '.join(skills)}]"] if skills else []
    lines = lines[:start] + replacement + lines[end:] if start is not None else lines + replacement
    installation.write(rel, "---\n" + "\n".join(lines) + "\n---\n" + rest)
    assert preloaded_skills(installation.root, role) == skills, f"{rel} kept other preloads"


def without_preload(installation: Installation, role: str) -> None:
    """Make `role`'s definition preload no part of the refactoring skill, every other preload kept."""
    kept = tuple(s for s in preloaded_skills(installation.root, role) if s != SKILL_NAME)
    _set_preloads(installation, role, kept)


def with_preload(installation: Installation, role: str) -> None:
    """Make `role`'s definition preload the refactoring skill, as it does at the base."""
    skills = preloaded_skills(installation.root, role)
    if SKILL_NAME not in skills:
        _set_preloads(installation, role, (*skills, SKILL_NAME))


def project_checkout(path: Path, *, managed: bool = True) -> Path:
    """A git working tree; `managed` gives it `.ai-state/`."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q"],
        cwd=path,
        env=isolated_env(path.parent / f".{path.name}-git"),
        check=True,
        capture_output=True,
        timeout=30,
    )
    if managed:
        (path / ".ai-state").mkdir(exist_ok=True)
    return path


# -- One spawn -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class HookExit:
    event: str
    command: str
    exit_code: int | None  # None: the process outlived its registered timeout
    stdout: str


@dataclass(frozen=True)
class Spawn:
    agent_type: str
    delegation: str
    preloaded: tuple[str, ...]  # skills the definition preloads
    skill_text: str  # the installation's refactoring skill text when the spawn started
    context: tuple[str, ...]  # SubagentStart context strings, registration order
    prompt_additions: tuple[str, ...]  # text an Agent-tool hook put around the delegation
    prompts_kept_delegation: bool  # every rewritten prompt still holds the delegation verbatim
    exits: tuple[HookExit, ...]
    session_id: str
    agent_id: str

    @property
    def delivered(self) -> str:
        """Everything a hook added to the spawn, in registration order."""
        return "\n".join((*self.context, *self.prompt_additions))

    @property
    def own_record(self) -> str:
        """What the spawn's own transcript records of its start: hook context, then its prompt."""
        return "\n".join((*self.context, *self.prompt_additions, self.delegation))

    @property
    def refusals(self) -> list[str]:
        return [e.command for e in self.exits if _refuses(e)]


def _refuses(exit_: HookExit) -> bool:
    if exit_.exit_code == 2:
        return True
    out = _parsed(exit_.stdout)
    specific = out.get("hookSpecificOutput") or {}
    return (
        out.get("decision") == "block"
        or out.get("continue") is False
        or (isinstance(specific, dict) and specific.get("permissionDecision") == "deny")
    )


def _parsed(stdout: str) -> dict:
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _registrations(root: Path, event: str, value: object) -> list[tuple[str, int]]:
    groups = json.loads((root / "hooks" / "hooks.json").read_text())["hooks"].get(event, [])
    chosen = []
    for group in groups:
        matcher = group.get("matcher", "")
        if matcher not in ("", "*") and not (
            isinstance(value, str) and re.fullmatch(matcher, value)
        ):
            continue
        chosen += [(h["command"], int(h.get("timeout", 60))) for h in group["hooks"]]
    return chosen


def _run_hook(event: str, command: str, timeout: int, stdin: str, cwd: Path, env: dict) -> HookExit:
    try:
        proc = subprocess.run(
            ["/bin/sh", "-c", command],
            input=stdin,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return HookExit(event, command, proc.returncode, proc.stdout)
    except subprocess.TimeoutExpired:
        return HookExit(event, command, None, "")


def _run_event(
    root: Path, event: str, match_value: object, stdin: str, cwd: Path, env: dict
) -> list[HookExit]:
    registered = _registrations(root, event, match_value)
    with ThreadPoolExecutor(max_workers=max(1, len(registered))) as pool:
        futures = [
            pool.submit(_run_hook, event, command, timeout, stdin, cwd, env)
            for command, timeout in registered
        ]
        return [f.result() for f in futures]


def _project_dir_name(cwd: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def _jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


_numbers = count(1)


def config_dir_of(installation: Installation) -> Path:
    return installation.root.parent / f".{installation.root.name}-config" / ".claude"


def _hook_env(installation: Installation, number: int) -> dict[str, str]:
    return isolated_env(
        installation.root.parent / f".{installation.root.name}-scratch-{number}",
        CLAUDE_PLUGIN_ROOT=str(installation.root),
        CLAUDE_CONFIG_DIR=str(config_dir_of(installation)),
    )


def _transcript_paths(
    installation: Installation, project: Path, session_id: str, agent_id: str
) -> tuple[Path, Path]:
    """The main session's transcript and the spawn's own, as the harness files them."""
    sessions = config_dir_of(installation) / "projects" / _project_dir_name(project)
    return (
        sessions / f"{session_id}.jsonl",
        sessions / session_id / "subagents" / f"agent-{agent_id}.jsonl",
    )


def _append_jsonl(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def _subagent_start(
    installation: Installation,
    project: Path,
    env: dict,
    *,
    session_id: str,
    agent_id: str,
    agent_type: str,
    raw_stdin: str | None = None,
) -> tuple[list[HookExit], tuple[str, ...]]:
    """Run every `SubagentStart` hook; the exits, and the context strings they print in order."""
    main_transcript, agent_transcript = _transcript_paths(
        installation, project, session_id, agent_id
    )
    payload = {
        "session_id": session_id,
        "transcript_path": str(main_transcript),
        "agent_transcript_path": str(agent_transcript),
        "cwd": str(project),
        "permission_mode": "default",
        "hook_event_name": "SubagentStart",
        "agent_id": agent_id,
        "agent_type": agent_type,
    }
    exits = _run_event(
        installation.root,
        "SubagentStart",
        agent_type,
        raw_stdin or json.dumps(payload),
        project,
        env,
    )
    context = tuple(
        out["additionalContext"]
        for e in exits
        for out in [_parsed(e.stdout).get("hookSpecificOutput") or {}]
        if isinstance(out, dict) and isinstance(out.get("additionalContext"), str)
    )
    return exits, context


def spawn(
    installation: Installation,
    project: Path,
    agent_type: str,
    delegation: str,
    *,
    raw_stdin: str | None = None,
) -> Spawn:
    """Spawn `agent_type` in `project` with `delegation` as its prompt; read what it holds.

    `raw_stdin`, when given, replaces both events' payloads, as a malformed input would.
    """
    number = next(_numbers)
    root = installation.root
    session_id = f"refactoring-delivery-session-{number}"
    agent_id = f"a{number:015d}"
    tool_use_id = f"toolu_refactoring_delivery_{number:04d}"
    main_transcript, agent_transcript = _transcript_paths(
        installation, project, session_id, agent_id
    )
    env = _hook_env(installation, number)
    skill_text = skill_body(root) if (root / SKILL).is_file() else ""
    role = agent_type.removeprefix("praxion:")
    preloaded = preloaded_skills(root, role) if (root / _definition(role)).is_file() else ()

    tool_input = {"prompt": delegation, "subagent_type": agent_type, "description": "step work"}
    pre_payload = {
        "session_id": session_id,
        "transcript_path": str(main_transcript),
        "cwd": str(project),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_use_id": tool_use_id,
        "tool_input": tool_input,
    }
    _jsonl(
        main_transcript,
        [
            {
                "type": "assistant",
                "sessionId": session_id,
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_use_id,
                            "name": "Agent",
                            "input": tool_input,
                        }
                    ],
                },
            }
        ],
    )
    pre_exits = _run_event(
        root, "PreToolUse", "Agent", raw_stdin or json.dumps(pre_payload), project, env
    )
    additions, kept = _prompt_additions(pre_exits, delegation)

    _jsonl(
        agent_transcript,
        [
            {
                "type": "user",
                "sessionId": session_id,
                "agentId": agent_id,
                "isSidechain": True,
                "message": {"role": "user", "content": "\n".join((*additions, delegation))},
            }
        ],
    )
    start_exits, context = _subagent_start(
        installation,
        project,
        env,
        session_id=session_id,
        agent_id=agent_id,
        agent_type=agent_type,
        raw_stdin=raw_stdin,
    )
    return Spawn(
        agent_type=agent_type,
        delegation=delegation,
        preloaded=preloaded,
        skill_text=skill_text,
        context=context,
        prompt_additions=additions,
        prompts_kept_delegation=kept,
        exits=(*pre_exits, *start_exits),
        session_id=session_id,
        agent_id=agent_id,
    )


def _prompt_additions(
    exits: list[HookExit], delegation: str, field: str = "prompt"
) -> tuple[tuple[str, ...], bool]:
    """What the hooks rewrote of `field` around `delegation`, and whether `delegation` survived."""
    additions: list[str] = []
    kept = True
    for exit_ in exits:
        specific = _parsed(exit_.stdout).get("hookSpecificOutput") or {}
        updated = specific.get("updatedInput") if isinstance(specific, dict) else None
        prompt = updated.get(field) if isinstance(updated, dict) else None
        if not isinstance(prompt, str):
            continue
        if delegation not in prompt:
            kept = False
            additions.append(prompt)
            continue
        before, after = prompt.split(delegation, 1)
        additions += [part for part in (before, after) if part.strip()]
    return tuple(additions), kept


# -- Reading the skill's text back ----------------------------------------------------------------


def _distinct_lines(body: str) -> Counter:
    return Counter(ln.rstrip() for ln in body.splitlines() if len(ln.strip()) >= DISTINCT_LINE)


@dataclass(frozen=True)
class Copies:
    whole: int  # complete copies of the skill's text the spawn holds
    most: int  # the largest count of any one of its lines: above `whole` means a part repeats


def copies_held(s: Spawn) -> Copies:
    """Copies of the skill's text a spawn holds: one per preload, plus what the hooks added."""
    lines = _distinct_lines(s.skill_text)
    assert lines, "the installation's refactoring skill has no text to look for"
    added = Counter(ln.rstrip() for ln in s.delivered.splitlines())
    ratios = [added[ln] // n for ln, n in lines.items()]
    preload = 1 if SKILL_NAME in s.preloaded else 0
    return Copies(whole=preload + min(ratios), most=preload + max(ratios))


def delivered_as_one_passage(s: Spawn) -> bool:
    """The skill's text sits, unbroken and unaltered, inside one piece a hook added.

    A piece is one context string or one addition around the prompt; text the delivery adds
    around the passage is allowed, text inside it is not.
    """
    passage = s.skill_text.strip("\n")
    return bool(passage) and any(passage in piece for piece in (*s.context, *s.prompt_additions))


# -- What the skill's body links to ----------------------------------------------------------------

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_ABSOLUTE_PATH = re.compile(r"(?<![\w.~])(/[^\s`'\"()<>\[\]]+)")


@dataclass(frozen=True)
class Link:
    path: str
    anchor: str | None


def body_links(body: str) -> tuple[Link, ...]:
    """The body's relative links to files, with the section anchor each names."""
    links = []
    for match in _LINK.finditer(body):
        target = match.group(1)
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
            continue
        path, _, anchor = target.partition("#")
        links.append(Link(path, anchor or None))
    return tuple(links)


def _slug(heading: str) -> str:
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s", "-", text)


def _anchors(text: str) -> set[str]:
    headings = {_slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*?)\s*#*\s*$", text, re.M)}
    ids = set(re.findall(r"""id=["']([^"']+)["']""", text))
    return headings | ids


def link_failures(base: Path, body: str) -> list[str]:
    """The links of `body` that do not reach an existing file, or section, from `base`."""
    failures = []
    for link in body_links(body):
        target = base / link.path
        if not target.is_file():
            failures.append(f"{link.path}: no such file under {base}")
        elif link.anchor and link.anchor not in _anchors(target.read_text(encoding="utf-8")):
            failures.append(f"{link.path}#{link.anchor}: no such section")
    return failures


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def link_base_named(s: Spawn, installation: Installation) -> Path | None:
    """A directory inside the installation, named by what a hook added around the passage,
    against which every link of the skill's body resolves; None when the delivery names none.

    A named file stands for its own directory; a named installation root stands for the skill's
    directory under it.
    """
    around = s.delivered.replace(s.skill_text.strip("\n"), "")
    for match in _ABSOLUTE_PATH.finditer(around):
        named = Path(match.group(1).rstrip(".,;:"))
        directory = named.parent if named.is_file() else named
        for base in (directory, directory / Path(SKILL).parent):
            if _resolves_every_link(base, installation, s.skill_text):
                return base
    return None


def _resolves_every_link(base: Path, installation: Installation, body: str) -> bool:
    return base.is_dir() and _within(base, installation.root) and not link_failures(base, body)


def longest_context_string(s: Spawn) -> int:
    return max((len(c) for c in s.context), default=0)


def mentions_marker(text: str) -> bool:
    """The marker anywhere in `text`, whatever its letter case and inner spacing."""
    return bool(_MARKER_PATTERN.search(text))


def unreadable_skill(installation: Installation) -> None:
    """The installation's skill cannot be read: its file is gone."""
    installation.path(SKILL).unlink()


def blocking_skill(installation: Installation) -> None:
    """Reading the installation's skill never finishes: its file is a pipe nobody writes to."""
    import os

    path = installation.path(SKILL)
    path.unlink()
    os.mkfifo(path)


# -- The parts the design chooses ------------------------------------------------------------------


def resume(installation: Installation, project: Path, earlier: Spawn, follow_up: str) -> Spawn:
    """Send `follow_up` to the spawn `earlier` started; read what it holds afterwards.

    The harness announces a resume without a new `Agent` call: `PreToolUse` for `SendMessage`
    (`to` the agent id, the message as the follow-up), then `SubagentStart` again with the same
    agent id. The agent keeps its whole conversation, so it holds what it held before plus
    whatever the hooks add now: a second copy of the skill's text shows up as a second copy here.
    """
    number = next(_numbers)
    env = _hook_env(installation, number)
    main_transcript, agent_transcript = _transcript_paths(
        installation, project, earlier.session_id, earlier.agent_id
    )
    tool_use_id = f"toolu_refactoring_delivery_{number:04d}"
    tool_input = {"to": earlier.agent_id, "message": follow_up}
    pre_payload = {
        "session_id": earlier.session_id,
        "transcript_path": str(main_transcript),
        "cwd": str(project),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "SendMessage",
        "tool_use_id": tool_use_id,
        "tool_input": tool_input,
    }
    _append_jsonl(
        main_transcript,
        {
            "type": "assistant",
            "sessionId": earlier.session_id,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "SendMessage",
                        "input": tool_input,
                    }
                ],
            },
        },
    )
    pre_exits = _run_event(
        installation.root, "PreToolUse", "SendMessage", json.dumps(pre_payload), project, env
    )
    additions, kept = _prompt_additions(pre_exits, follow_up, field="message")
    _append_jsonl(
        agent_transcript,
        {
            "type": "user",
            "sessionId": earlier.session_id,
            "agentId": earlier.agent_id,
            "isSidechain": True,
            "message": {"role": "user", "content": "\n".join((*additions, follow_up))},
        },
    )
    start_exits, context = _subagent_start(
        installation,
        project,
        env,
        session_id=earlier.session_id,
        agent_id=earlier.agent_id,
        agent_type=earlier.agent_type,
    )
    return replace(
        earlier,
        context=(*earlier.context, *context),
        prompt_additions=(*earlier.prompt_additions, *additions),
        prompts_kept_delegation=earlier.prompts_kept_delegation and kept,
        exits=(*earlier.exits, *pre_exits, *start_exits),
    )


def remove_delivery(installation: Installation) -> None:
    """The canary: delete the delivery module from the installation, leave all else registered.

    The emitter then yields no trailing segment, while its leading segments and every
    `SubagentStart` delivery keep working. A removal that removes nothing fails loudly, since a
    canary that changes nothing proves nothing.
    """
    module = installation.path(DELIVERY_MODULE)
    assert module.is_file(), f"nothing to remove: the installation has no {DELIVERY_MODULE}"
    module.unlink()


def apply_the_move(installation: Installation) -> None:
    """Run the installation's own move tool to take the skill out of both definitions' preloads.

    The tool is idempotent, so a scenario may apply it to an installation already in the end state.
    """
    _run_move_tool(installation, "delivered")


def before_the_move(installation: Installation) -> None:
    """Run the installation's own move tool to put the skill back into both definitions' preloads.

    A paired run precedes the move, so a scenario about one builds its checkout in this state
    whichever state the working tree it was copied from holds. The tool is idempotent: an
    installation already in this state is left as it is.
    """
    _run_move_tool(installation, "preloaded")


def _run_move_tool(installation: Installation, state: str) -> None:
    root = installation.root
    tool = root / MOVE_TOOL
    assert tool.is_file(), f"the installation has no {MOVE_TOOL}"
    done = subprocess.run(
        [sys.executable, str(tool), "--to", state, "--root", str(root)],
        capture_output=True,
        text=True,
        env=isolated_env(root.parent / f".{root.name}-move"),
        timeout=60,
    )
    assert done.returncode == 0, f"{MOVE_TOOL} --to {state} exited {done.returncode}: {done.stderr}"


_FAILURES_CODE = """
import json, sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from _observation_log import reader

rows = reader.read_rows(Path(sys.argv[2]))
print(json.dumps([
    row.get("reason")
    for row in rows
    if row.get("event_type") == "skill_delivery" and row.get("outcome") == "failed"
]))
"""


def delivery_failures(installation: Installation, project: Path) -> tuple[str, ...]:
    """The reason of each failed delivery the project's observation log holds.

    The log is read through the installation's own reader, as every code reader does. A delivery
    that served, or rightly skipped, leaves no failed row, so the answer is empty. Asking about an
    installation with no delivery module is refused: with nothing to fail, an empty answer would
    only be a vacuous pass.
    """
    assert installation.path(DELIVERY_MODULE).is_file(), (
        f"the installation has no {DELIVERY_MODULE}, so no delivery can have been recorded"
    )
    done = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _FAILURES_CODE,
            str(installation.path("hooks")),
            str(project / ".ai-state"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, f"reading the observation log failed: {done.stderr[-1000:]}"
    return tuple(str(reason) for reason in json.loads(done.stdout))


_ARRIVAL_CODE = """
import json, sys

sys.path.insert(0, sys.argv[1])
from _skill_delivery import shows_arrival

print(json.dumps(bool(shows_arrival(sys.stdin.read()))))
"""


def shows_arrival(record: str) -> bool:
    """The delivery module's own matcher, applied to a spawn's own record.

    It runs in an isolated process against this process's copy of the checkout, the same code
    every installation copies, so a scenario never imports production code into the test process.
    """
    hooks = _template_checkout() / "hooks"
    assert (hooks / "_skill_delivery.py").is_file(), f"the checkout has no {DELIVERY_MODULE}"
    done = subprocess.run(
        [sys.executable, "-I", "-c", _ARRIVAL_CODE, str(hooks)],
        input=record,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, f"the arrival matcher failed: {done.stderr[-1000:]}"
    return json.loads(done.stdout) is True
