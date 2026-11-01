"""Driver for the model-routing move: the tier table leaves session start, its guidance stays.

The scenarios reach the system only through its entry points: the session-start rule injection
(`hooks/inject_rules.py`), the installer, the always-loaded reading, the gates, the Codex and
Cursor exporters, and (unbound until its binding step) the spawn-model check over recorded
transcripts. The frozen fixtures under `tests/acceptance/fixtures/model_routing_move/` were
taken with `freeze` from the tree as it stood at the pipeline base, so the scenarios compare
like with like without reading git history:

- `base_rule.md`: the routing rule at the base;
- `base_cursor.json`: each Cursor export file, by digest; `base_cursor_rule.md`: the routing
  rule's own Cursor file;
- `base_adapter.json`: the Codex pipeline adapter's two exports, parsed, repository root `<repo>`;
- `base_bridge.json`: the Codex rules bridge's rule-id sets, rule paths, session-start pointer
  and the routing rule's entry, repository root `<repo>`;
- `base_budget_files.json`: the files the always-loaded reading counts;
- `base_kernels.json`: each generated role kernel and the kernel index, by digest;
- `base_links.json`: the rule files a fresh install linked into the user rules directory.

The session-start routing text's file is the design's to name: a scenario finds it as the file
the always-loaded reading counts that carries the routing title and is not the full rule.

Observations run hermetically (`kernel_sandbox.isolated_env`): a scratch HOME, no inherited
`CLAUDE*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variable, and a `claude` stand-in first on
PATH where a command could reach one, so no model session can start.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError, isolated_env

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "model_routing_move"
RULE = "rules/swe/agent-model-routing.md"
RULE_ID = "swe/agent-model-routing"
POLICY_REFERENCE = "skills/agent-crafting/references/model-routing-policy.md"
AGENTS_SCOPE = "agents/**"
TITLE = "Agent Model Routing"
TIER_TABLE_HEADING = "### Tier Table"
DIRECTIVE_OPENING = "**Orchestrator directive.**"
CURSOR_RULE = "swe/agent-model-routing.md"
CODEX_RULE_ID = "rules::swe::agent-model-routing"
HACKATHON_PRESET = "claude/aac-templates/praxion-rules.hackathon-preset.yaml"
GLOBAL_INSTRUCTIONS = "claude/config/CLAUDE.md.tmpl"
LIVE_MATERIALIZER = "eval/src/praxion_evals/live/materialize.py"
INHERITANCE_PROBE = "eval/scripts/inheritance_probe.py"
BUDGET_CEILING = 25_000


# -- Text helpers ---------------------------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter block with its fences, body); no block reads as ("", text)."""
    if not text.startswith("---\n"):
        return "", text
    end = text.index("\n---\n", 4) + len("\n---\n")
    return text[:end], text[end:]


def frontmatter(text: str) -> dict:
    block, _ = split_frontmatter(text)
    return (yaml.safe_load(block.strip("-\n")) or {}) if block else {}


def body(text: str) -> str:
    return split_frontmatter(text)[1]


def paragraphs(text: str) -> list[str]:
    """Blank-line separated blocks, each stripped of surrounding whitespace."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def normalize(text: str) -> str:
    """Markdown emphasis and code marks dropped, runs of blanks collapsed, for token search."""
    return re.sub(r"[ \t]+", " ", text.replace("`", "").replace("*", ""))


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"\n|;|\.\s", normalize(text)) if s.strip()]


def holds(text: str, token: str) -> bool:
    """Whether `token` appears in `text`, case-insensitively, code marks ignored."""
    return normalize(token).lower() in normalize(text).lower()


def scope_takes(globs: list[str], relpath: str) -> bool:
    return any(fnmatch.fnmatchcase(relpath, glob) for glob in globs)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def tier_table(text: str) -> str:
    """The tier-table section: its heading through the line before the next blank-led paragraph
    that is not part of the table."""
    lines = body(text).splitlines()
    start = lines.index(TIER_TABLE_HEADING)
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("|")):
        end += 1
    return "\n".join(lines[start:end]).strip()


def tier_rows(text: str) -> list[str]:
    return [line for line in tier_table(text).splitlines() if line.startswith("| `")]


def replaced_paragraphs(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """The run of `before` that `after` replaced, and what replaced it, by common prefix and
    suffix. Equal lists give ([], [])."""
    head = 0
    while head < min(len(before), len(after)) and before[head] == after[head]:
        head += 1
    tail = 0
    while (
        tail < min(len(before), len(after)) - head
        and before[len(before) - 1 - tail] == after[len(after) - 1 - tail]
    ):
        tail += 1
    return before[head : len(before) - tail], after[head : len(after) - tail]


def routing_section(context: str) -> str:
    """The routing text inside a session-start payload: from the heading that carries the routing
    title to the next heading of the same or a higher level; empty when no heading carries it."""
    lines = context.splitlines()
    for index, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s", line)
        if heading and TITLE in line:
            level = len(heading.group(1))
            end = index + 1
            while end < len(lines):
                other = re.match(r"^(#{1,6})\s", lines[end])
                if (
                    other
                    and len(other.group(1)) <= level
                    and not lines[end].startswith("#" * (level + 1))
                ):
                    break
                end += 1
            return "\n".join(lines[index:end])
    return ""


# -- The placement table (the spec's oracle for where each statement of today's rule lands) ------

S, P, R = "session-start text", "path-loaded rule", "policy reference"


@dataclass(frozen=True)
class Statement:
    """One statement of today's rule: the surfaces that must carry it and its evidence tokens.

    `tokens[surface]` lists what a check finds on that surface (every token, case-insensitive);
    `absent_at_start` lists tokens the session-start text must not carry."""

    sid: str
    meaning: str
    tokens: dict[str, tuple[str, ...]]
    absent_at_start: tuple[str, ...] = ()


PLACEMENT = (
    Statement("title", "the title names the routing rule", {S: (TITLE,), P: (TITLE,)}),
    Statement(
        "kill-switch",
        "the kill switch is the first resolution layer",
        dict.fromkeys((S, P, R), ("CLAUDE_CODE_SUBAGENT_MODEL", "kill switch")),
    ),
    Statement(
        "per-spawn",
        "the per-spawn model is the orchestrator's lever",
        dict.fromkeys((S, P, R), ("per-spawn", "lever")),
    ),
    Statement(
        "floor",
        "frontmatter model: is the capability floor",
        dict.fromkeys((S, P, R), ("capability floor",)),
    ),
    Statement(
        "fallback",
        "the main session model is the fallback",
        dict.fromkeys((S, P), ("main session model", "fallback")),
    ),
    Statement(
        "aliases",
        "opus and sonnet aliases track the newest generation",
        dict.fromkeys((S, P, R), ("newest generation",)),
    ),
    Statement(
        "haiku-pin",
        "the L tier pins claude-haiku-4-5 because bare haiku is Haiku 3.5",
        dict.fromkeys((S, P, R), ("claude-haiku-4-5", "Haiku 3.5")),
    ),
    Statement(
        "version-lock",
        "full ids are pinned at spawn time only when version-locking",
        dict.fromkeys((S, P, R), ("version-locking",)),
    ),
    Statement(
        "sanctioned",
        "deviations are the sanctioned cases: researcher modes, implementer step hint",
        dict.fromkeys((S, P, R), ("researcher", "modes", "tier: H", "tier: L")),
    ),
    Statement(
        "tier-table",
        "the tier table stays out of session start",
        {P: (TIER_TABLE_HEADING,)},
        absent_at_start=(TIER_TABLE_HEADING, "| Agent | Tier | Alias | Rationale |"),
    ),
    Statement(
        "consultant",
        "the discipline-consultant spawns at opus unless the consult is routine",
        dict.fromkeys((S, P, R), ("discipline-consultant", "opus", "routine")),
    ),
    Statement(
        "acceptance-design",
        "test-engineer acceptance design spawns at opus",
        dict.fromkeys((S, P, R), ("Mode: acceptance-design", "opus")),
    ),
    Statement(
        "researcher-modes",
        "researcher modes route up or down",
        dict.fromkeys((S, P, R), ("researcher", "modes")),
    ),
    Statement(
        "implementer-hint",
        "the implementer step hint routes tier: H or tier: L",
        dict.fromkeys((S, P, R), ("tier: H", "tier: L")),
    ),
    Statement(
        "doc-engineer-row",
        "the doc-engineer row's pinned id stays in the table",
        {P: ("| `doc-engineer` | L | `claude-haiku-4-5` |",)},
        absent_at_start=("| `doc-engineer` |",),
    ),
    Statement(
        "pointer",
        "the policy reference is named for the full detail",
        dict.fromkeys((S, P), (POLICY_REFERENCE,)),
    ),
    Statement(
        "scope",
        "the rule governs subagent routing inside Claude Code",
        {P: ("Governs subagent routing",)},
        absent_at_start=("Governs subagent routing",),
    ),
    Statement(
        "light-review",
        "verifier light review spawns at sonnet",
        dict.fromkeys((S, P, R), ("Mode: light-review", "sonnet")),
    ),
)

# Each sanctioned per-spawn deviation, as the session-start text must name it in one sentence:
# its role, its marker and its model (any one of the alternatives counts).
DEVIATIONS = {
    "the consultant at opus unless routine": ("discipline-consultant", "routine", ("opus",)),
    "acceptance design at opus": ("test-engineer", "acceptance-design", ("opus",)),
    "light review at sonnet": ("verifier", "light-review", ("sonnet",)),
    "researcher modes up or down": ("researcher", "mode", ("opus", "haiku")),
    "the implementer step hint": ("implementer", "tier: H", ("opus", "haiku")),
}

# What today's directive says and the restated contract must not: an id the Agent tool cannot
# take passed on every spawn, and a fall-through a definition's floor makes untrue.
EVERY_SPAWN_DIRECTIVE = re.compile(r"\bpass\w*\b.*\bon every spawn\b", re.I)
ROW_ALIAS_DIRECTIVE = re.compile(
    r"\bpass\w* (?:that row's|the row's|its) (?:model: ?<alias>|alias)\b", re.I
)
FALL_THROUGH = re.compile(r"\bfall\w* through to the (?:main )?session model\b", re.I)
NO_MODEL_RUNS_AT_FLOOR = re.compile(
    r"\b(?:no|without(?: a)?|omit\w*)\s+(?:per-spawn\s+)?model\b.*\bfloor\b"
    r"|\bfloor\b.*\b(?:no|without(?: a)?|omit\w*)\s+(?:per-spawn\s+)?model\b",
    re.I,
)
ONLY_FOR_A_DEVIATION = re.compile(r"\bonly\b.*\b(?:deviation|sanctioned)", re.I)


# -- Processes ------------------------------------------------------------------------------------


def stand_in_claude(scratch: Path) -> Path:
    """A `claude` that records its arguments and exits 1, so no session can start."""
    bin_dir = scratch / "claude-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    stand_in = bin_dir / "claude"
    stand_in.write_text(f'#!/bin/sh\necho "$@" >> "{scratch}/claude-calls.log"\nexit 1\n')
    stand_in.chmod(0o755)
    return bin_dir


def claude_launches(scratch: Path) -> list[str]:
    log = scratch / "claude-calls.log"
    return log.read_text().splitlines() if log.exists() else []


def run_check(argv: list[str], scratch: Path, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    """`python3 <argv>` with this checkout's script, run in `cwd`, hermetically."""
    script, *args = argv
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *args],
        cwd=cwd,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=600,
    )


@dataclass(frozen=True)
class Injection:
    context: str
    stderr: str
    excludes: list[str]

    @property
    def summary(self) -> str:
        """The injection's one-line summary of what it loaded and suppressed."""
        lines = [line for line in self.stderr.splitlines() if "suppressed:" in line]
        return lines[-1] if lines else ""


def session_start(
    scratch: Path,
    *,
    disable: list[str] | None = None,
    preset: Path | None = None,
    plugin_root: Path = REPO_ROOT,
) -> Injection:
    """The registered session-start rule injection over a fresh project, as the harness runs it.

    `disable` writes a blacklist naming those patterns; `preset` copies a blacklist file in."""
    project = scratch / "project"
    (project / ".claude").mkdir(parents=True, exist_ok=True)
    blacklist = project / ".claude" / "praxion-rules.yaml"
    if preset is not None:
        blacklist.write_bytes(preset.read_bytes())
    elif disable is not None:
        listed = "".join(f"  - '{pattern}'\n" for pattern in disable)
        blacklist.write_text(f"version: 1\ndisable:\n{listed}", encoding="utf-8")
    env = isolated_env(
        scratch / "env", CLAUDE_PLUGIN_ROOT=str(plugin_root), CLAUDE_PROJECT_DIR=str(project)
    )
    event = {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(project)}
    result = subprocess.run(
        [sys.executable, str(plugin_root / "hooks" / "inject_rules.py")],
        input=json.dumps(event | {"session_id": "model-routing-move"}),
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(result.stdout or "{}").get("hookSpecificOutput", {})
    settings = project / ".claude" / "settings.json"
    excludes = (
        json.loads(settings.read_text()).get("claudeMdExcludes", []) if settings.exists() else []
    )
    return Injection(str(payload.get("additionalContext", "")), result.stderr, excludes)


def install(scratch: Path) -> subprocess.CompletedProcess[str]:
    """`bash install.sh code --relink` from this checkout into `scratch`'s HOME, never a session."""
    env = isolated_env(scratch)
    env["PATH"] = f"{stand_in_claude(scratch)}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh"), "code", "--relink"],
        input="Y\nY\nY\n",
        cwd=scratch,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )


def install_check(scratch: Path) -> subprocess.CompletedProcess[str]:
    """`bash install.sh code --check` against the install already in `scratch`'s HOME."""
    env = isolated_env(scratch)
    env["PATH"] = f"{stand_in_claude(scratch)}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh"), "code", "--check"],
        cwd=scratch,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def rules_dir(scratch: Path) -> Path:
    return scratch / "home" / ".claude" / "rules"


def linked_rules(rules: Path) -> dict[str, Path]:
    """Every link in a user rules directory: its path under the directory -> what it resolves to."""
    return {
        str(p.relative_to(rules)): p.resolve() for p in sorted(rules.rglob("*")) if p.is_symlink()
    }


def plant_old_install(scratch: Path) -> None:
    """The user rules directory an install made at the base left behind: the base's links."""
    rules = rules_dir(scratch)
    for rel in fixture_json("base_links.json"):
        link = rules / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(REPO_ROOT / "rules" / rel)


def marketplace_complete(scratch: Path) -> Path:
    """The marketplace first-session completion, run over this checkout as the installed plugin
    into `scratch`'s HOME; returns the user rules directory it linked."""
    raise UnboundDriverError(
        "the marketplace first-session completion is not yet driven over a checkout as the "
        "installed plugin: the binding step names how a scratch HOME's plugin cache is laid out "
        "so the completion links this checkout's rules"
    )


def budget(scratch: Path, root: Path = REPO_ROOT) -> tuple[int, dict]:
    """The always-loaded reading over `root`, under a HOME holding only the global file."""
    home = scratch / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "CLAUDE.md").write_bytes((REPO_ROOT / GLOBAL_INSTRUCTIONS).read_bytes())
    result = run_check(["scripts/measure_token_budget.py", "--json"], scratch, root)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    return result.returncode, json.loads(result.stdout)


def budget_files(scratch: Path, root: Path = REPO_ROOT) -> list[str]:
    """The files the always-loaded reading counts, HOME written `<home>` and `root` `<repo>`."""
    _, reading = budget(scratch, root)
    home = scratch / "home"
    tokens = [
        (home.resolve(), "<home>"),
        (home, "<home>"),
        (root.resolve(), "<repo>"),
        (root, "<repo>"),
    ]

    def tokenized(path: str) -> str:
        for prefix, token in tokens:
            path = path.replace(str(prefix), token)
        return path

    return sorted(tokenized(f) for f in reading["files"])


def session_start_routing_file(scratch: Path, root: Path = REPO_ROOT) -> str | None:
    """The file the always-loaded reading counts that carries the routing title and is not the
    full rule, relative to `root`; None when there is none."""
    found = [
        f[len("<repo>/") :]
        for f in budget_files(scratch, root)
        if f.startswith("<repo>/")
        and f != f"<repo>/{RULE}"
        and routing_section((root / f[len("<repo>/") :]).read_text(encoding="utf-8"))
    ]
    assert len(found) <= 1, f"more than one always-loaded file carries the routing title: {found}"
    return found[0] if found else None


def kernel_digests(root: Path = REPO_ROOT) -> dict[str, str]:
    kernels = root / "claude" / "kernels"
    files = [*sorted(kernels.glob("*.md")), kernels / "index.json"]
    return {f.name: digest(f.read_bytes()) for f in files}


def cursor_export(scratch: Path) -> dict[str, bytes]:
    out = scratch / "cursor-rules"
    result = run_check(["cursor/config/export-cursor-rules.py", str(REPO_ROOT), str(out)], scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    return {str(p.relative_to(out)): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


def _with_root_as_token(value, root: Path):
    if isinstance(value, str):
        return value.replace(str(root), "<repo>")
    if isinstance(value, list):
        return [_with_root_as_token(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _with_root_as_token(v, root) for k, v in value.items()}
    return value


def adapter_exports(scratch: Path) -> dict:
    out = scratch / "codex-adapter"
    argv = [
        "codex/config/export-codex-pipeline-adapter.py",
        "--repo-root",
        str(REPO_ROOT),
        "--out-dir",
        str(out),
    ]
    result = run_check(argv, scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        name: _with_root_as_token(
            json.loads((out / "praxion" / name).read_text(encoding="utf-8")), REPO_ROOT
        )
        for name in ("model_routing.json", "pipeline_semantics.json")
    }


def bridge_reach(scratch: Path) -> dict:
    out = scratch / "codex-bridge"
    argv = [
        "codex/config/export-codex-rules-bridge.py",
        "--repo-root",
        str(REPO_ROOT),
        "--out-dir",
        str(out),
    ]
    result = run_check(argv, scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = _with_root_as_token(
        json.loads((out / "praxion" / "rules_manifest.json").read_text(encoding="utf-8")), REPO_ROOT
    )
    project = scratch / "codex-project"
    project.mkdir(exist_ok=True)
    started = subprocess.run(
        [sys.executable, str(out / "hooks" / "praxion-session-start.py")],
        input=json.dumps(
            {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(project)}
        ),
        cwd=project,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=60,
    )
    pointer = json.loads(started.stdout)["hookSpecificOutput"]["additionalContext"]
    rules = {rule["id"]: rule for rule in manifest["rules"]}
    return {
        "always_on": sorted(manifest["always_on_rule_ids"]),
        "portable_always_on": sorted(manifest["codex_portable_always_on_rule_ids"]),
        "path_scoped": sorted(manifest["path_scoped_rule_ids"]),
        "rule_paths": sorted(rule["relpath"] for rule in manifest["rules"]),
        "pointer": pointer.replace(str(REPO_ROOT), "<repo>"),
        "routing_entry": rules.get(CODEX_RULE_ID),
    }


# -- The eval probes' declared targets ------------------------------------------------------------


def materializer_hook_delivered_rule() -> str:
    """The live eval materializer's declared example of a hook-delivered rule (a module constant)."""
    tree = ast.parse((REPO_ROOT / LIVE_MATERIALIZER).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "HOOK_DELIVERED_RULE" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{LIVE_MATERIALIZER} declares no hook-delivered example rule")


def inheritance_probe_heading() -> str:
    """The heading the inheritance probe's docstring says it discriminates on."""
    doc = (
        ast.get_docstring(ast.parse((REPO_ROOT / INHERITANCE_PROBE).read_text(encoding="utf-8")))
        or ""
    )
    found = re.search(r"section headed\s+`(#{1,6} [^`]+)`", doc)
    assert found, f"{INHERITANCE_PROBE} no longer names the heading it discriminates on"
    return found.group(1)


def manifest_rows(root: Path = REPO_ROOT) -> dict[str, dict]:
    rows = yaml.safe_load((root / "rules" / "_manifest.yaml").read_text(encoding="utf-8"))["rules"]
    return {row["id"]: row for row in rows}


# -- The spawn-model check over recorded transcripts ----------------------------------------------

MODEL_IDS = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
}
VERDICTS = ("floor", "override", "unexplained", "unknown")


def definition_floor(role: str) -> str:
    return frontmatter((REPO_ROOT / "agents" / f"{role}.md").read_text(encoding="utf-8"))["model"]


@dataclass
class Spawn:
    """One recorded spawn: the role requested, any per-spawn model, the prompt, and the model its
    own transcript shows it ran on (None: the spawn left no transcript)."""

    role: str
    ran_on: str | None
    model: str | None = None
    prompt: str = "Task slug: model-routing-fixture\nDo the step."
    agent_id: str = ""


@dataclass
class RecordedSession:
    session_id: str
    spawns: list[Spawn] = field(default_factory=list)


def record_sessions(transcripts: Path, sessions: list[RecordedSession]) -> None:
    """Write each session as Claude Code records it: `<dir>/<session>.jsonl` holding each Agent
    tool call and its result (which names the agent id), and each spawn's own transcript at
    `<dir>/<session>/subagents/agent-<id>.jsonl` whose assistant entries carry the model."""
    transcripts.mkdir(parents=True, exist_ok=True)
    for session in sessions:
        lines: list[dict] = []
        for index, spawn in enumerate(session.spawns):
            spawn.agent_id = spawn.agent_id or f"a{session.session_id[:6]}{index:02d}"
            use_id = f"toolu_{session.session_id[:6]}{index:02d}"
            spawn_input = {
                "description": f"Run the {spawn.role}",
                "subagent_type": f"praxion:{spawn.role}",
                "prompt": spawn.prompt,
            }
            if spawn.model is not None:
                spawn_input["model"] = spawn.model
            lines.append(
                {
                    "type": "assistant",
                    "sessionId": session.session_id,
                    "uuid": f"{use_id}-call",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-5-5",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": use_id,
                                "name": "Agent",
                                "input": spawn_input,
                            }
                        ],
                    },
                }
            )
            lines.append(
                {
                    "type": "user",
                    "sessionId": session.session_id,
                    "uuid": f"{use_id}-result",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": use_id,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"Done. [COMPLETE]\nagentId: {spawn.agent_id}",
                                    }
                                ],
                            }
                        ],
                    },
                    "toolUseResult": {"status": "completed", "agentId": spawn.agent_id},
                }
            )
            if spawn.ran_on is None:
                continue
            own = transcripts / session.session_id / "subagents" / f"agent-{spawn.agent_id}.jsonl"
            own.parent.mkdir(parents=True, exist_ok=True)
            own.write_text(
                "\n".join(
                    json.dumps(entry)
                    for entry in (
                        {
                            "type": "user",
                            "isSidechain": True,
                            "agentId": spawn.agent_id,
                            "sessionId": session.session_id,
                            "message": {"role": "user", "content": spawn.prompt},
                        },
                        {
                            "type": "assistant",
                            "isSidechain": True,
                            "agentId": spawn.agent_id,
                            "sessionId": session.session_id,
                            "message": {
                                "role": "assistant",
                                "model": spawn.ran_on,
                                "content": [{"type": "text", "text": "Done. [COMPLETE]"}],
                            },
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )
        (transcripts / f"{session.session_id}.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
        )


@dataclass(frozen=True)
class SpawnCheck:
    exit_code: int
    verdicts: dict[str, str]  # agent id -> one of VERDICTS
    claude_launches: list[str]


def run_spawn_model_check(transcripts: Path, scratch: Path) -> SpawnCheck:
    """The re-runnable spawn-model check over a directory of recorded transcripts, with a
    `claude` stand-in on PATH; each spawn's verdict keyed by its agent id."""
    raise UnboundDriverError(
        "the spawn-model check is not yet bound: the binding step names its command, how it is "
        "pointed at a directory of recorded transcripts, and how its report names each spawn "
        "and classifies it as matching its definition's floor, a sanctioned override, "
        "unexplained or unknown"
    )


# -- Freezing -------------------------------------------------------------------------------------


def freeze(scratch: Path) -> None:
    """Write every fixture from this tree, which must be the pipeline base."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "base_rule.md").write_bytes((REPO_ROOT / RULE).read_bytes())
    exported = cursor_export(scratch / "cursor")
    (FIXTURES / "base_cursor_rule.md").write_bytes(exported[CURSOR_RULE])
    installed = scratch / "install"
    result = install(installed)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    dumps = {
        "base_cursor.json": {rel: digest(data) for rel, data in exported.items()},
        "base_adapter.json": adapter_exports(scratch / "adapter"),
        "base_bridge.json": bridge_reach(scratch / "bridge"),
        "base_budget_files.json": budget_files(scratch / "budget"),
        "base_kernels.json": kernel_digests(),
        "base_links.json": sorted(
            rel for rel, target in linked_rules(rules_dir(installed)).items() if rel.endswith(".md")
        ),
    }
    for name, value in dumps.items():
        (FIXTURES / name).write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")


# -- Readings over observations -------------------------------------------------------------------


def install_check_rule_findings(output: str) -> list[str]:
    """The install check's `Rules:` section lines that are not a pass mark. The check's other
    sections judge the scratch HOME's environment (plugins, optional tools), not the rules."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "Rules:")
    section = []
    for line in lines[start + 1 :]:
        if not line.strip() or (
            line.strip().endswith(":") and not line.lstrip().startswith(("✓", "⚠", "✗"))
        ):
            break
        section.append(line.strip())
    return [line for line in section if not line.startswith("✓")]


def routing_entry_difference(base: dict, shipped: dict | None) -> dict[str, tuple]:
    """The routing rule's bridge entry keys whose values differ, as (base, shipped)."""
    shipped = shipped or {}
    return {
        k: (base.get(k), shipped.get(k))
        for k in sorted(set(base) | set(shipped))
        if base.get(k) != shipped.get(k)
    }
