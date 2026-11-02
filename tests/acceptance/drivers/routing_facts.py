"""Driver for the routing-facts correction: every routing surface states the facts the harness applies.

The scenarios reach the system only through its entry points:

- the session-start rule injection (`hooks/inject_rules.py`, run hermetically by
  `model_routing_move.session_start`), whose routing text is the *session-start text*;
- the texts a reader opens: the path-loaded routing rule, the routing policy reference, the
  L-tier definition's `model:` line, the deployment document's configuration row, and each
  routing check's shipped description (its module docstring and its `--help` text);
- the spawn-model check (`scripts/check_spawn_models.py`) over recorded transcripts;
- the parity gate, the gate-liveness check and the other named gates, in this checkout or in a
  sandbox copy a scenario may change (`kernel_sandbox`);
- the Codex pipeline adapter, the Codex agents exporter, the Codex rules bridge and the Cursor
  exporter; the always-loaded reading; the installer.

The frozen fixtures under `tests/acceptance/fixtures/routing_facts/` were taken with `freeze`
from the tree at this pipeline's base, so the scenarios compare like with like without reading
git history:

- `base_rule.md`: the routing rule; `base_cursor_rule.md`: its Cursor export file;
- `base_cursor.json`: each Cursor export file, by digest;
- `base_adapter.json`: the Codex pipeline adapter's two exports, parsed, repository root `<repo>`;
- `base_codex_agents.json`: each Codex agent's model settings and the digest of its
  instructions, root `<repo>`, plus the L-tier agent's instructions in full;
- `base_bridge.json`: the Codex rules bridge's rule-id sets, rule paths, session-start pointer
  and the routing rule's entry, root `<repo>`;
- `base_budget_files.json`: the files the always-loaded reading counts.

A sentence is what `shipped_texts.sentences` reads: a stretch bounded by a line end, a semicolon
or a full stop followed by a space, with code and emphasis marks dropped. A model alias counts
only as the bare lowercase word (`haiku`, never `claude-haiku-4-5` or `Haiku 4.5`).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import kernel_sandbox, shipped_texts
from tests.acceptance.drivers import model_routing_move as move
from tests.acceptance.drivers.kernel_sandbox import isolated_env

REPO_ROOT = move.REPO_ROOT
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "routing_facts"

RULE = move.RULE
RESIDENT = "rules/swe/agent-model-routing-resident.md"
POLICY_REFERENCE = move.POLICY_REFERENCE
L_TIER_DEFINITION = "agents/doc-engineer.md"
DEPLOYMENT = ".ai-state/SYSTEM_DEPLOYMENT.md"
SPAWN_CHECK = "scripts/check_spawn_models.py"
PARITY_GATE = "scripts/check_model_routing_parity.py"
LIVENESS = "scripts/check_gate_liveness.py"
CURSOR_RULE = move.CURSOR_RULE
CODEX_RULE_ID = move.CODEX_RULE_ID

ENV_VAR = "CLAUDE_CODE_SUBAGENT_MODEL"
FORCING = "CLAUDE_CODE_SUBAGENT_MODEL_FORCE"

S, P, R, D = "session-start text", "path-loaded rule", "policy reference", "L-tier floor line"


# -- Reading texts --------------------------------------------------------------------------------


def read(relpath: str, root: Path = REPO_ROOT) -> str:
    return (root / relpath).read_text(encoding="utf-8")


def sentences(text: str) -> list[str]:
    return shipped_texts.sentences(text)


def names_alias(sentence: str, alias: str) -> bool:
    """Whether `sentence` names the bare model alias (lowercase, not part of a longer id)."""
    return re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", sentence) is not None


def holds(text: str, token: str) -> bool:
    return move.holds(text, token)


def session_start_text(scratch: Path) -> str:
    """The routing text the session-start injection delivers to a fresh project."""
    return move.routing_section(move.session_start(scratch).context)


def floor_line() -> str:
    """The L-tier definition's `model:` frontmatter line as written, any comment included."""
    block, _ = move.split_frontmatter(read(L_TIER_DEFINITION))
    lines = [line for line in block.splitlines() if line.startswith("model:")]
    assert len(lines) == 1, f"{L_TIER_DEFINITION} has {len(lines)} model: lines"
    return lines[0]


def surfaces(scratch: Path) -> dict[str, str]:
    return {
        S: session_start_text(scratch),
        P: move.body(read(RULE)),
        R: read(POLICY_REFERENCE),
        D: floor_line(),
    }


def deployment_row() -> str:
    """The deployment document's configuration-table row for the subagent-model variable."""
    rows = [line for line in read(DEPLOYMENT).splitlines() if line.startswith(f"| `{ENV_VAR}` |")]
    assert len(rows) == 1, f"{DEPLOYMENT} has {len(rows)} configuration rows for {ENV_VAR}"
    return rows[0]


def check_description(script: str, scratch: Path) -> str:
    """A check's shipped description: its module docstring and, when it answers, its `--help`."""
    # The docstring is hard-wrapped; join each paragraph's lines so a sentence reads whole.
    doc = re.sub(r"(?<!\n)\n(?!\n)", " ", ast.get_docstring(ast.parse(read(script))) or "")
    helped = subprocess.run(
        [sys.executable, str(REPO_ROOT / script), "--help"],
        cwd=REPO_ROOT,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return doc + ("\n" + helped.stdout if helped.returncode == 0 else "")


def table_row(text: str, agent: str) -> list[str]:
    """The tier-table row for `agent`, as its stripped cells (code marks dropped)."""
    rows = [line for line in move.tier_rows(text) if line.startswith(f"| `{agent}` |")]
    assert len(rows) == 1, f"the tier table has {len(rows)} rows for {agent}"
    return [cell.strip().strip("`").strip() for cell in rows[0].strip().strip("|").split("|")]


def first_positions(text: str, layers: tuple[str, ...]) -> dict[str, int]:
    lowered = move.normalize(text).lower()
    return {layer: lowered.find(layer.lower()) for layer in layers}


# -- Sentence readings the placement table's evidence names ---------------------------------------

KILL_SWITCH = re.compile(r"kill[- ]switch", re.I)
NEGATION = re.compile(r"\b(?:never|not|no longer|retired|below|older|instead)\b|n't\b", re.I)
SINGLE_SANCTIONED_DOWNGRADE = re.compile(r"\b(?:only|one)\s+sanctioned\s+downgrade\b", re.I)
LIGHT_REVIEW = re.compile(r"light[- ]review", re.I)


def unconditioned_kill_switch(text: str) -> list[str]:
    """Sentences that use the phrase kill switch without naming the forcing setting."""
    return [s for s in sentences(text) if KILL_SWITCH.search(s) and FORCING not in s]


def places_env_var_above_the_floor(sentence: str) -> bool:
    """Whether a sentence ranks the subagent-model variable first, or above another layer,
    without the forcing condition."""
    if FORCING in sentence:
        return False
    if re.search(r"\blayers?[- ]?(?:1|one)\b|\blayers 2", sentence, re.I):
        return True
    names_it = ENV_VAR in sentence or KILL_SWITCH.search(sentence)
    ranks = re.search(r"\b(?:first|beats|overrides?|precedence over|wins over)\b|>", sentence, re.I)
    return bool(names_it and ranks)


def says_haiku_is_3_5(sentence: str) -> bool:
    return (
        "3.5" in sentence
        and bool(re.search("haiku", sentence, re.I))
        and not NEGATION.search(sentence)
    )


def says_a_full_id_is_never_passed_per_spawn(sentence: str) -> bool:
    return bool(
        re.search(r"full[- ]ids?\b", sentence, re.I)
        and re.search(r"\b(?:never|not|no)\b", sentence, re.I)
        and re.search(r"spawn", sentence, re.I)
    )


def says_a_full_id_is_pinned_at_spawn_time(sentence: str) -> bool:
    pinned = re.search(r"\bpin\w*\b.*\bspawn[- ]time\b", sentence, re.I) or re.search(
        r"full[- ]ids?\b.*\bspawn[- ]time\b", sentence, re.I
    )
    return bool(pinned) and not re.search(r"\b(?:never|not)\b", sentence, re.I)


def says_the_l_tier_is_not_passable(sentence: str) -> bool:
    if re.search(r"not a value to pass", sentence, re.I):
        return True
    return bool(
        re.search(r"\bL tier\b", sentence)
        and re.search(r"\b(?:not|never)\b[^.]{0,40}\bpass", sentence, re.I)
    )


def names_the_l_tier(sentence: str) -> bool:
    return bool(re.search(r"\bL\b", sentence))


INTERNAL_RECORD = re.compile(
    r"\bdec-(?:draft-)?[0-9a-f]{3,}\b|\btd-\d{3,}\b|\bSPEC_[\w-]+_\d{4}-\d{2}-\d{2}\.md\b"
)


# -- Gates and the sandbox ------------------------------------------------------------------------


def run_check(argv: list[str], scratch: Path, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return move.run_check(argv, scratch, cwd)


def new_sandbox(tmp_path: Path) -> kernel_sandbox.Sandbox:
    return kernel_sandbox.new_sandbox(kernel_sandbox.build_template(tmp_path), tmp_path / "plugin")


def set_floor(sandbox: kernel_sandbox.Sandbox, agent: str, value: str) -> None:
    """Rewrite an agent definition's `model:` frontmatter line to `model: <value>`."""
    rel = kernel_sandbox.agent_path(agent)
    text = sandbox.read(rel)
    rewritten, count = re.subn(r"(?m)^model:.*$", f"model: {value}", text, count=1)
    assert count == 1, f"{rel} has no model: line to rewrite"
    sandbox.write(rel, rewritten)


def gate_in_sandbox(
    argv: list[str], sandbox: kernel_sandbox.Sandbox
) -> subprocess.CompletedProcess:
    return run_check([*argv, "--repo-root", str(sandbox.root)], sandbox.scratch, sandbox.root)


def uninvoked_gate_findings(scratch: Path) -> list[dict]:
    """The gate-liveness check's uninvoked-gate findings over this checkout."""
    result = run_check([LIVENESS, "--check", "uninvoked-gate", "--json"], scratch)
    try:
        findings = json.loads(result.stdout)["findings"]
    except (ValueError, KeyError) as error:
        raise AssertionError(
            f"the uninvoked-gate check gave no readable findings: {result.stdout[-1000:]}"
            f"{result.stderr[-1000:]}"
        ) from error
    return [f for f in findings if f.get("check") == "GL04"]


def agent_roles() -> list[str]:
    """Every agent definition's name (a file under agents/ whose frontmatter names it)."""
    return kernel_sandbox.agent_names(REPO_ROOT)


def definitions_naming(token: str) -> list[str]:
    return [f"agents/{role}.md" for role in agent_roles() if token in read(f"agents/{role}.md")]


# -- The spawn-model check over recorded transcripts ----------------------------------------------

SLUG = "routing-facts-fixture"
STEADY_ROLE = (
    "context-engineer"  # a sonnet-floor role recorded on its floor beside the spawn under test
)


@dataclass(frozen=True)
class SpawnReading:
    exit_code: int
    verdicts: dict[str, str]  # agent id -> verdict
    rows: dict[str, str]  # agent id -> the text output's row for that spawn
    claude_launches: list[str]


def check_recorded(sessions: list[move.RecordedSession], scratch: Path) -> SpawnReading:
    """Record `sessions` and run the spawn-model check over them, once with `--json` and once
    for its text output."""
    transcripts = scratch / "projects" / "-sandbox"
    move.record_sessions(transcripts, sessions)
    return read_recorded(transcripts, scratch)


def read_recorded(transcripts: Path, scratch: Path) -> SpawnReading:
    parsed = move.run_spawn_model_check(transcripts, scratch / "json")
    env = isolated_env(scratch / "text")
    env["PATH"] = f"{move.stand_in_claude(scratch / 'text')}:{env['PATH']}"
    text = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / SPAWN_CHECK),
            str(transcripts),
            "--repo-root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert text.returncode == parsed.exit_code, (
        f"the text run exited {text.returncode}, the --json run {parsed.exit_code}: {text.stderr}"
    )
    rows = {}
    for agent_id in parsed.verdicts:
        matching = [line for line in text.stdout.splitlines() if line.strip().startswith(agent_id)]
        rows[agent_id] = matching[0] if len(matching) == 1 else ""
    launches = parsed.claude_launches + move.claude_launches(scratch / "text")
    return SpawnReading(parsed.exit_code, parsed.verdicts, rows, launches)


def steady_spawn() -> move.Spawn:
    return move.Spawn(
        STEADY_ROLE, ran_on="claude-sonnet-5-5", prompt="Review the context.\nTask slug: x"
    )


@dataclass
class DriverSpawn:
    """A spawn the step-loop driver issued: a three-line pointer prompt opening with the task slug
    and naming its request, the model the driver passed, and (unless `rendered` is None) the
    rendered prompt the spawn's own transcript records it reading."""

    role: str
    ran_on: str | None
    request_id: str
    model: str | None
    pointer_mode: str = ""  # a marker opening the pointer's third line, e.g. "Mode: light-review. "
    rendered: str | None = None

    @property
    def prompt_path(self) -> str:
        return f"/sandbox/.ai-work/{SLUG}/PROMPT_{self.request_id}.md"

    def as_spawn(self) -> move.Spawn:
        pointer = (
            f"Task slug: {SLUG}\nSpawn request: {self.request_id}\n"
            f"{self.pointer_mode}Read {self.prompt_path} first and follow it."
        )
        return move.Spawn(self.role, ran_on=self.ran_on, model=self.model, prompt=pointer)


def step_block(step: str, hint: str | None) -> str:
    """A plan step block as the plan carries it, with its routing hint as its own line."""
    lines = [
        f"### Step {step}: Write the widget",
        "",
        "**Assignee**: implementer",
        "**Implementation**: Write `widget.py` so that `value()` returns the step id.",
        "**Files**: `widget.py`",
    ]
    if hint:
        lines.append(hint)
    lines.append("**Done when**: `tests/test_widget.py` passes.")
    return "\n".join(lines)


def rendered_implement_prompt(step: str, hint: str | None) -> str:
    return (
        f"# Step {step}, attempt 1\n\n{step_block(step, hint)}\n\n"
        "Run the step's check before you report, and stop when it passes.\n"
    )


def rendered_review_prompt(step: str, hint: str | None) -> str:
    return (
        f"# Light review of step {step}\n\nMode: light-review\n\n{step_block(step, hint)}\n\n"
        "Review the change the step made and write your verdict.\n"
    )


def _numbered(text: str) -> str:
    return "".join(f"{index:>6}\t{line}\n" for index, line in enumerate(text.splitlines(), 1))


def check_driver_session(driver: DriverSpawn, scratch: Path) -> tuple[SpawnReading, move.Spawn]:
    """Record one session holding a steady spawn on its floor and the driver-issued spawn, and
    run the check; returns the reading and the driver spawn as recorded (its agent id set)."""
    transcripts = scratch / "projects" / "-sandbox"
    session_id = "5e55a1b2-0000-4000-8000-0000000000d1"
    spawn = driver.as_spawn()
    move.record_sessions(transcripts, [move.RecordedSession(session_id, [steady_spawn(), spawn])])
    if driver.rendered is not None and driver.ran_on is not None:
        _record_rendered_read(transcripts, session_id, spawn, driver)
    return read_recorded(transcripts, scratch), spawn


def _record_rendered_read(
    transcripts: Path, session_id: str, spawn: move.Spawn, driver: DriverSpawn
) -> None:
    """Insert, after the spawn's opening prompt, the Read call of its rendered prompt and the
    result Claude Code records for it (numbered lines in the message, the raw file in
    `toolUseResult`)."""
    own = transcripts / session_id / "subagents" / f"agent-{spawn.agent_id}.jsonl"
    lines = own.read_text(encoding="utf-8").splitlines()
    use_id = f"toolu_read_{spawn.agent_id}"
    total = len(driver.rendered.splitlines())
    call = {
        "type": "assistant",
        "isSidechain": True,
        "agentId": spawn.agent_id,
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": driver.ran_on,
            "content": [
                {
                    "type": "tool_use",
                    "id": use_id,
                    "name": "Read",
                    "input": {"file_path": driver.prompt_path},
                }
            ],
        },
    }
    result = {
        "type": "user",
        "isSidechain": True,
        "agentId": spawn.agent_id,
        "sessionId": session_id,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": _numbered(driver.rendered),
                }
            ],
        },
        "toolUseResult": {
            "type": "text",
            "file": {
                "filePath": driver.prompt_path,
                "content": driver.rendered,
                "numLines": total,
                "startLine": 1,
                "totalLines": total,
            },
        },
    }
    own.write_text(
        "\n".join([lines[0], json.dumps(call), json.dumps(result), *lines[1:]]) + "\n",
        encoding="utf-8",
    )


# -- Exports --------------------------------------------------------------------------------------


def _rooted(value, root: Path = REPO_ROOT):
    if isinstance(value, str):
        return value.replace(str(root), "<repo>")
    if isinstance(value, list):
        return [_rooted(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _rooted(v, root) for k, v in value.items()}
    return value


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def codex_agents(scratch: Path) -> dict[str, dict]:
    """Each Codex agent export: its model settings and its instructions, root `<repo>`."""
    out = scratch / "codex-agents"
    argv = [
        "codex/config/export-codex-agents.py",
        "--repo-root",
        str(REPO_ROOT),
        "--out-dir",
        str(out),
    ]
    result = run_check(argv, scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    agents = {}
    for path in sorted(out.rglob("*.toml")):
        data = _rooted(tomllib.loads(path.read_text(encoding="utf-8")))
        agents[data["name"]] = {
            "model": data.get("model"),
            "model_reasoning_effort": data.get("model_reasoning_effort"),
            "instructions": data.get("developer_instructions", ""),
        }
    return agents


def adapter_exports(scratch: Path) -> dict:
    return move.adapter_exports(scratch)


def bridge_reach(scratch: Path) -> dict:
    return move.bridge_reach(scratch)


def cursor_export(scratch: Path) -> dict[str, bytes]:
    return move.cursor_export(scratch)


def budget_files(scratch: Path) -> list[str]:
    return move.budget_files(scratch)


def routes(model_routing: dict) -> dict[str, dict]:
    return {route["agent"]: route for route in model_routing["agent_routes"]}


def changed_paragraphs(before: str, after: str) -> tuple[set[str], set[str]]:
    """(paragraphs only `before` has, paragraphs only `after` has)."""
    old, new = set(move.paragraphs(before)), set(move.paragraphs(after))
    return old - new, new - old


# -- Fixtures -------------------------------------------------------------------------------------


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def freeze(scratch: Path) -> None:
    """Write every fixture from this tree, which must be the pipeline base."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "base_rule.md").write_bytes((REPO_ROOT / RULE).read_bytes())
    exported = cursor_export(scratch / "cursor")
    (FIXTURES / "base_cursor_rule.md").write_bytes(exported[CURSOR_RULE])
    agents = codex_agents(scratch / "agents")
    dumps = {
        "base_cursor.json": {
            rel: hashlib.sha256(data).hexdigest() for rel, data in exported.items()
        },
        "base_adapter.json": adapter_exports(scratch / "adapter"),
        "base_bridge.json": bridge_reach(scratch / "bridge"),
        "base_budget_files.json": budget_files(scratch / "budget"),
        "base_codex_agents.json": {
            "agents": {
                name: {
                    "model": agent["model"],
                    "model_reasoning_effort": agent["model_reasoning_effort"],
                    "instructions_digest": digest(agent["instructions"]),
                }
                for name, agent in agents.items()
            },
            "l_tier_instructions": agents["doc-engineer"]["instructions"],
        },
    }
    for name, value in dumps.items():
        (FIXTURES / name).write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")
