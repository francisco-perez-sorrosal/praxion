"""The nine seeded cases as live sessions: fixture repos, prompts, capture.

Each scenario is a :class:`ScenarioSpec` — a fixture-repo builder, a prompt
builder that reads seeded input from the frozen YAML, the session's
permissions, and a pure ``capture`` function that turns one session's
envelope (plus, for two scenarios, a filesystem delta) into a
:class:`~praxion_evals.live.results.Capture`. This module is the single
source of scenario knowledge — ``eval/scripts/record_live_envelopes.py``
imports these specs rather than redefining fixture repos, prompts or
Bash allowlists of its own.

Capture never trusts the model's self-report: ``spawn-selection`` reads
``result.structured_output``; ``ui-step-conformance`` reads the subagent's own
forwarded text (never the orchestrator's relay); ``adr-authoring`` and
``lightweight-fix`` read a filesystem delta; ``commit-staging`` reads the
Bash tool_use commands the session actually ran.
"""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxion_evals.live.results import Capture, Captured, NotElicited
from praxion_evals.live.session import PermissionMode, SessionEnvelope

_FIXTURE_REPOS_DIR = Path(__file__).resolve().parent / "fixture_repos"
FIXTURE_USER_NAME = "scenario"
FIXTURE_USER_EMAIL = "scenario@example.invalid"

IMPLEMENTER_SUBAGENT_TYPE = "implementer"
_DECISIONS_DIR = ".ai-state/decisions/"
_DRAFTS_DIR = ".ai-state/decisions/drafts/"
_TIER_SUFFIX = " tier"

# Granted beside every scenario's narrow command set: inspection utilities
# that cannot write or run arbitrary code, so a session can orient itself
# (list a directory, read a file, page long output) without reaching for a
# broader `Bash(git *)`/`Bash(python3 *)` grant.
HARMLESS_UTILITIES = (
    "Bash(cd *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(grep *)",
    "Bash(wc *)",
)

Seeded = Mapping[str, Any]

# ---------------------------------------------------------------------------
# Filesystem delta — the ground truth `adr-authoring` and `lightweight-fix`
# capture from, computed once outside any capture function so `capture`
# itself stays a pure function of its three inputs.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FsDelta:
    created: Mapping[str, str]  # relpath -> decoded content ("" when undecodable)
    modified: tuple[str, ...]  # relpath, sorted

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(sorted({*self.created, *self.modified}))


def snapshot(root: Path) -> dict[str, tuple[str, str]]:
    """``{relpath: (sha256, content)}`` for every file under ``root``, excluding ``.git/``."""
    result: dict[str, tuple[str, str]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        payload = path.read_bytes()
        content = payload.decode("utf-8", errors="ignore") if _is_text(payload) else ""
        result[path.relative_to(root).as_posix()] = (hashlib.sha256(payload).hexdigest(), content)
    return result


def _is_text(payload: bytes) -> bool:
    return b"\0" not in payload


def compute_fs_delta(
    before: Mapping[str, tuple[str, str]], after: Mapping[str, tuple[str, str]]
) -> FsDelta:
    """Pure diff of two :func:`snapshot` results — no filesystem access."""
    created = {path: content for path, (_, content) in after.items() if path not in before}
    modified = tuple(
        sorted(
            path for path, (sha, _) in after.items() if path in before and before[path][0] != sha
        )
    )
    return FsDelta(created=created, modified=modified)


# ---------------------------------------------------------------------------
# spawn-selection — capture from `result.structured_output`
# ---------------------------------------------------------------------------

SPAWN_SELECTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tier": {"type": "string"},
        "agents": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tier", "agents"],
}

_SPAWN_SELECTION_PROMPT = (
    "Consult your process-planning conventions for the task below, but do not "
    "perform it and do not use any tools. Reply in prose with two things only: "
    "the name of the process tier those conventions assign to this task, and "
    "the subagent types you would spawn over the course of the work.\n\nTask: {task}"
)


def prompt_spawn_selection(case: Seeded) -> str:
    return _SPAWN_SELECTION_PROMPT.format(task=case["task"])


def build_spawn_selection(root: Path, seeded: Seeded) -> None:
    del seeded  # the fixture is identical for every case: a minimal repo
    _init_repo(root)
    _commit_all(root, {"README.md": "# fixture\n"}, "baseline")


def _normalize_tier(raw: str) -> str:
    normalized = raw.strip().lower()
    return normalized[: -len(_TIER_SUFFIX)] if normalized.endswith(_TIER_SUFFIX) else normalized


def _normalize_agent(agent: str) -> str:
    return agent.strip().lower().rsplit(":", 1)[-1]


def _order_agents(recorded: set[str], expected: Sequence[str]) -> list[str]:
    """Equality-preserving order: expected members first, unknown ones sorted after."""
    expected_lower = [_normalize_agent(a) for a in expected]
    known = [a for a in expected_lower if a in recorded]
    unknown = sorted(recorded - set(expected_lower))
    return [*known, *unknown]


def capture_spawn_selection(
    envelope: SessionEnvelope, fs_delta: FsDelta | None, case: Seeded
) -> Capture:
    del fs_delta
    result = envelope.final_result
    output = result.structured_output if result else None
    if not isinstance(output, Mapping) or "tier" not in output or "agents" not in output:
        return NotElicited(reason="no structured output on the result event", diagnostics={})
    recorded_agents = {_normalize_agent(a) for a in output["agents"]}
    value = {
        "recorded_tier": _normalize_tier(str(output["tier"])),
        "recorded_agents": _order_agents(recorded_agents, case.get("expected_agents", ())),
    }
    diagnostics = {
        "tier_match": value["recorded_tier"] == str(case.get("expected_tier", "")).lower(),
        "subagents_spawned": result.subagents_spawned if result else None,
    }
    return Captured(value=value, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# ui-step-conformance — capture from the subagent's own forwarded text
# ---------------------------------------------------------------------------

_SPAWN_IMPLEMENTER_PROMPT = (
    "Spawn exactly one `praxion:implementer` subagent with the prompt "
    "`Task slug: ui-step. Implement the current step in WIP.md.` "
    "When it finishes, stop."
)
_UI_STEP_ALLOWED_TOOLS = (
    *HARMLESS_UTILITIES,
    "Bash(git status)",
    "Bash(git status *)",
    "Bash(git diff)",
)


def prompt_ui_step_conformance(seeded: Seeded) -> str:
    del seeded  # the prompt names no scenario detail; the step lives in WIP.md
    return _SPAWN_IMPLEMENTER_PROMPT


def build_ui_step_conformance(root: Path, seeded: Seeded) -> None:
    _init_repo(root)
    _copy_tree(_FIXTURE_REPOS_DIR / "ui-step-conformance", root)
    _commit_all(root, {"README.md": "# fixture\n"}, "baseline")
    step = f"## Current step\n\n{seeded['seeded_step']}"
    # Left untracked (the copied .gitignore excludes .ai-work/): the WIP/plan
    # pair a real implementer step lives in, dynamic per session.
    _write_tree(
        root,
        {
            ".ai-work/ui-step/IMPLEMENTATION_PLAN.md": f"# Plan: ADR list loading state\n\n{step}",
            ".ai-work/ui-step/WIP.md": f"# WIP\n\n{step}\nStatus: TODO\n",
        },
    )


def capture_ui_step_conformance(
    envelope: SessionEnvelope, fs_delta: FsDelta | None, fixture_yaml: Seeded
) -> Capture:
    del fs_delta, fixture_yaml
    agent_call = next(
        (
            tool_use
            for tool_use in envelope.tool_uses
            if tool_use.name == "Agent"
            and _normalize_agent(str(tool_use.input.get("subagent_type", "")))
            == IMPLEMENTER_SUBAGENT_TYPE
        ),
        None,
    )
    if agent_call is None:
        return NotElicited(reason="no Agent tool_use spawning the implementer", diagnostics={})
    forwarded = [t for t in envelope.subagent_texts if t.parent_tool_use_id == agent_call.id]
    if forwarded:
        return Captured(
            value=forwarded[-1].text,
            diagnostics={"agent_tool_use_id": agent_call.id, "source": "subagent_text"},
        )
    notification = next(
        (n for n in envelope.task_notifications if n.tool_use_id == agent_call.id), None
    )
    if notification is None or not notification.summary:
        return NotElicited(
            reason="no forwarded subagent text or task notification for the Agent call",
            diagnostics={"agent_tool_use_id": agent_call.id},
        )
    return Captured(
        value=notification.summary,
        diagnostics={"agent_tool_use_id": agent_call.id, "source": "task_notification"},
    )


# ---------------------------------------------------------------------------
# adr-authoring — capture from the created `.ai-state/decisions/` file
# ---------------------------------------------------------------------------

_RECORD_ADR_PROMPT = (
    "Record the following decision as an ADR according to the conventions in your "
    "context. Do not spawn agents.\n\n"
)
_ADR_ALLOWED_TOOLS = (
    *HARMLESS_UTILITIES,
    "Bash(git config --get *)",
    "Bash(git config user.name)",
    "Bash(git config user.email)",
    "Bash(git rev-parse *)",
    "Bash(git branch --show-current)",
    "Bash(date *)",
    "Bash(shasum *)",
)


def prompt_adr_authoring(seeded: Seeded) -> str:
    return _RECORD_ADR_PROMPT + seeded["seeded_decision"]


def build_adr_authoring(root: Path, seeded: Seeded) -> None:
    del seeded
    _init_repo(root)
    _copy_tree(_FIXTURE_REPOS_DIR / "adr-authoring", root)
    _commit_all(root, {"README.md": "# fixture\n"}, "baseline")


def capture_adr_authoring(
    envelope: SessionEnvelope, fs_delta: FsDelta | None, fixture_yaml: Seeded
) -> Capture:
    del envelope, fixture_yaml
    if fs_delta is None:
        return NotElicited(
            reason="no filesystem delta was computed for this session", diagnostics={}
        )
    candidates = sorted(
        (
            path
            for path in fs_delta.created
            if path.startswith(_DECISIONS_DIR) and path.endswith(".md")
        ),
        key=lambda path: (0 if path.startswith(_DRAFTS_DIR) else 1, path),
    )
    if not candidates:
        return NotElicited(reason="no .md file created under .ai-state/decisions/", diagnostics={})
    chosen = candidates[0]
    return Captured(
        value=fs_delta.created[chosen],
        diagnostics={"path": chosen, "other_candidates": candidates[1:]},
    )


# ---------------------------------------------------------------------------
# commit-staging — capture from the Bash commands the session actually ran
# ---------------------------------------------------------------------------

_COMMIT_STAGING_ALLOWED_TOOLS = (
    *HARMLESS_UTILITIES,
    "Bash(git status)",
    "Bash(git status *)",
    "Bash(git diff)",
    "Bash(git diff --cached)",
    "Bash(git add *)",
    "Bash(git commit *)",
)
_SEGMENT_OPERATORS = ("&&", "||", ";", "|")
_STAGING_FLAGS = frozenset({"-a", "--all", "-am"})


def prompt_commit_staging(seeded: Seeded) -> str:
    return f"{seeded['seeded_change'].strip()} Commit it."


def build_commit_staging(root: Path, seeded: Seeded) -> None:
    del seeded
    _init_repo(root)
    _copy_tree(_FIXTURE_REPOS_DIR / "commit-staging" / "baseline", root)
    _commit_all(root, {"README.md": "# fixture\n"}, "baseline")
    _copy_tree(_FIXTURE_REPOS_DIR / "commit-staging" / "worktree", root)


def _shell_segments(command: str) -> list[str]:
    """Split on top-level (unquoted) &&, ||, ;, |, and newline; quotes are never split."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index, length = 0, len(command)
    while index < length:
        char = command[index]
        if quote:
            current.append(char)
            if char == quote and command[index - 1] != "\\":
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "\n":
            segments.append("".join(current))
            current = []
            index += 1
            continue
        operator = next((op for op in _SEGMENT_OPERATORS if command.startswith(op, index)), None)
        if operator is not None:
            segments.append("".join(current))
            current = []
            index += len(operator)
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def _drop_git_global_options(tokens: Sequence[str]) -> list[str]:
    """Skip `-C <path>` / `-c k=v` between `git` and its subcommand."""
    index = 1
    while index + 1 < len(tokens) and tokens[index] in ("-C", "-c"):
        index += 2
    return [tokens[0], *tokens[index:]]


def _is_staging_segment(segment: str) -> bool:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return False
    if not tokens or tokens[0] != "git":
        return False
    tokens = _drop_git_global_options(tokens)
    if len(tokens) < 2:
        return False
    subcommand = tokens[1]
    if subcommand in ("add", "stage"):
        return True
    return subcommand == "commit" and any(flag in _STAGING_FLAGS for flag in tokens[2:])


def capture_commit_staging(
    envelope: SessionEnvelope, fs_delta: FsDelta | None, fixture_yaml: Seeded
) -> Capture:
    del fs_delta, fixture_yaml
    commands = [str(t.input.get("command", "")) for t in envelope.tool_uses if t.name == "Bash"]
    segments = [segment for command in commands for segment in _shell_segments(command)]
    staging = [segment for segment in segments if _is_staging_segment(segment)]
    if not staging:
        return NotElicited(
            reason="no staging command among the session's Bash calls", diagnostics={}
        )
    return Captured(value=" ; ".join(staging), diagnostics={"bash_command_count": len(commands)})


# ---------------------------------------------------------------------------
# lightweight-fix — capture from the filesystem delta
# ---------------------------------------------------------------------------

_RUN_TESTS = ("Bash(python3 -m pytest)", "Bash(python3 -m pytest *)")
_LIGHTWEIGHT_ALLOWED_TOOLS = (
    *HARMLESS_UTILITIES,
    *_RUN_TESTS,
    "Bash(git status)",
    "Bash(git status *)",
    "Bash(git diff)",
    "Bash(git add *)",
    "Bash(git commit *)",
)


def prompt_lightweight_fix(seeded: Seeded) -> str:
    return str(seeded["seeded_fix"])


def build_lightweight_fix(root: Path, seeded: Seeded) -> None:
    del seeded
    _init_repo(root)
    _copy_tree(_FIXTURE_REPOS_DIR / "lightweight-fix", root)
    _commit_all(root, {"README.md": "# fixture\n"}, "baseline")


def capture_lightweight_fix(
    envelope: SessionEnvelope, fs_delta: FsDelta | None, fixture_yaml: Seeded
) -> Capture:
    del envelope, fixture_yaml
    if fs_delta is None:
        return NotElicited(
            reason="no filesystem delta was computed for this session", diagnostics={}
        )
    paths = fs_delta.changed_paths
    if not paths:
        return NotElicited(reason="no file created or modified", diagnostics={})
    return Captured(value=list(paths), diagnostics={})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    build_fixture: Callable[[Path, Seeded], None]
    prompt: Callable[[Seeded], str]
    capture: Callable[[SessionEnvelope, FsDelta | None, Seeded], Capture]
    permission_mode: PermissionMode
    max_budget_usd: float
    allowed_tools: tuple[str, ...] = ()
    json_schema: Mapping[str, Any] | None = None
    forward_subagent_text: bool = False
    requires_structured_output: bool = False


SCENARIOS: dict[str, ScenarioSpec] = {
    spec.scenario_id: spec
    for spec in (
        ScenarioSpec(
            scenario_id="spawn-selection",
            build_fixture=build_spawn_selection,
            prompt=prompt_spawn_selection,
            capture=capture_spawn_selection,
            permission_mode="default",
            max_budget_usd=1.0,
            allowed_tools=HARMLESS_UTILITIES,
            json_schema=SPAWN_SELECTION_JSON_SCHEMA,
            requires_structured_output=True,
        ),
        ScenarioSpec(
            scenario_id="ui-step-conformance",
            build_fixture=build_ui_step_conformance,
            prompt=prompt_ui_step_conformance,
            capture=capture_ui_step_conformance,
            permission_mode="acceptEdits",
            max_budget_usd=3.0,
            allowed_tools=_UI_STEP_ALLOWED_TOOLS,
            forward_subagent_text=True,
        ),
        ScenarioSpec(
            scenario_id="adr-authoring",
            build_fixture=build_adr_authoring,
            prompt=prompt_adr_authoring,
            capture=capture_adr_authoring,
            permission_mode="acceptEdits",
            max_budget_usd=3.0,
            allowed_tools=_ADR_ALLOWED_TOOLS,
        ),
        ScenarioSpec(
            scenario_id="commit-staging",
            build_fixture=build_commit_staging,
            prompt=prompt_commit_staging,
            capture=capture_commit_staging,
            permission_mode="default",
            max_budget_usd=2.0,
            allowed_tools=_COMMIT_STAGING_ALLOWED_TOOLS,
        ),
        ScenarioSpec(
            scenario_id="lightweight-fix",
            build_fixture=build_lightweight_fix,
            prompt=prompt_lightweight_fix,
            capture=capture_lightweight_fix,
            permission_mode="acceptEdits",
            max_budget_usd=3.0,
            allowed_tools=_LIGHTWEIGHT_ALLOWED_TOOLS,
        ),
    )
}


# ---------------------------------------------------------------------------
# Fixture-repo git plumbing (self-contained: no dependency on the recorder)
# ---------------------------------------------------------------------------


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", FIXTURE_USER_NAME)
    _git(root, "config", "user.email", FIXTURE_USER_EMAIL)


def _write_tree(root: Path, files: Mapping[str, str]) -> None:
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _copy_tree(source: Path, dest: Path) -> None:
    for path in source.rglob("*"):
        if path.is_file():
            target = dest / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())


def _commit_all(root: Path, extra_files: Mapping[str, str], message: str) -> None:
    _write_tree(root, extra_files)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout
