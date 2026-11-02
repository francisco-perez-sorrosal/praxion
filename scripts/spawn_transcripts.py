"""Recorded subagent transcripts, parsed once into spawn values.

The boundary of the spawn-model check: everything the check needs from Claude Code's recorded
transcripts, and nothing of their layout beyond this module. A transcript directory holds
`<session>.jsonl` (the session's Agent `tool_use` calls and their results, which name each spawn's
agent id) and `<session>/subagents/agent-<id>.jsonl` (the spawn's own transcript, whose assistant
entries carry the model it ran on).

Claude Code also records a call's message in other record kinds (an `api-request-blob` repeats the
Agent `tool_use` block), so a spawn is keyed on the `tool_use` id: one Agent call is one spawn, however
many records carry it. A prompt marker counts as a whole phrase anywhere in the prompt, with no word
character or hyphen on either side ("tier: High" and "routinely" hold none): a prompt that writes a
marker states that routing, and negation or quotation is not interpreted. A prompt whose first line is
`Task slug: <slug>` and a later line starts with `Spawn request: <id>` was issued by the step-loop
driver, and the spawn keeps that id together with the routing its rendered request implies: its
third line names the request's file, and the spawn's own transcript records its `Read` of it.

Stdlib only and Python 3.9-safe: the check runs under the ambient interpreter.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from check_model_routing_parity import frontmatter_model  # noqa: E402

ROLE_PREFIX = "praxion:"
AGENTS_DIR = Path("agents")
# The only phrases of a spawn prompt that sanction a per-spawn model; the routing rule names them.
PROMPT_MARKERS = (
    "Mode: acceptance-design",
    "Mode: light-review",
    "tier: H",
    "tier: L",
    "routine",
)
# The model Claude Code records on entries it wrote itself (an interrupt, an API error), not on a
# model's reply.
SYNTHETIC_MODEL = "<synthetic>"

_MARKER_PATTERNS = {
    marker: re.compile(rf"(?<![\w-]){re.escape(marker)}(?![\w-])") for marker in PROMPT_MARKERS
}
_REQUEST_PATH = re.compile(r"\bRead (\S+)")
_TASK_SLUG_LINE = re.compile(r"Task slug: \S")
_SPAWN_REQUEST_LINE = re.compile(r"^Spawn request: (\S+)", re.MULTILINE)


# The model family a driver request implies; `floor` is a request that asks for no deviation.
ImpliedRouting = Literal["sonnet", "opus", "haiku", "floor"]


@dataclass(frozen=True)
class DriverRequest:
    """The step-loop request a spawn answers. `implied` is None when the spawn recorded no read of
    its rendered request, so what the request implies is not shown."""

    id: str
    implied: ImpliedRouting | None = None


@dataclass(frozen=True)
class Spawn:
    """One Agent spawn of a recorded session. `ran_model` is None when the spawn left no
    transcript of its own, or one with no assistant entry."""

    session: str
    agent_id: str
    role: str
    requested_model: str | None
    ran_model: str | None
    prompt_markers: frozenset[str]
    driver: DriverRequest | None = None


def read_spawns(transcripts_dir: Path) -> list[Spawn]:
    """Every `praxion:` Agent spawn of every session in the directory, in session order.

    A call whose result names no agent id never ran, so it is no spawn; an unreadable line is
    skipped, since one damaged entry must not hide the session's other spawns."""
    return [
        spawn
        for session_file in sorted(transcripts_dir.glob("*.jsonl"))
        for spawn in _session_spawns(transcripts_dir, session_file)
    ]


def read_floors(repo_root: Path) -> dict[str, str]:
    """Each agent definition's frontmatter `model:`, by agent name."""
    floors: dict[str, str] = {}
    for path in sorted((repo_root / AGENTS_DIR).glob("*.md")):
        declared = frontmatter_model(path.read_text(encoding="utf-8"))
        if declared is not None and declared[1]:
            floors[declared[0]] = declared[1]
    return floors


def _session_spawns(transcripts_dir: Path, session_file: Path) -> list[Spawn]:
    session = session_file.stem
    records = _read_records(session_file)
    agent_ids = _agent_ids_by_call(records)
    spawns = []
    for call_id, call in _agent_calls(records):
        agent_id = agent_ids.get(call_id)
        if agent_id is None:
            continue
        own = transcripts_dir / session / "subagents" / f"agent-{agent_id}.jsonl"
        model = call.get("model")
        prompt = call.get("prompt")
        own_records = _read_records(own)
        spawns.append(
            Spawn(
                session=session,
                agent_id=agent_id,
                role=call["subagent_type"][len(ROLE_PREFIX) :],
                requested_model=model if isinstance(model, str) else None,
                ran_model=_ran_model(own_records),
                prompt_markers=_prompt_markers(prompt),
                driver=_driver_request(prompt, own_records),
            )
        )
    return spawns


def _agent_calls(records: list[dict]):
    """(tool_use id, input) for each `praxion:` Agent call, once per id."""
    seen: set[object] = set()
    for block in _blocks(records, "tool_use"):
        call = block.get("input")
        if block.get("name") != "Agent" or not isinstance(call, dict) or block.get("id") in seen:
            continue
        seen.add(block.get("id"))
        subagent_type = call.get("subagent_type")
        if isinstance(subagent_type, str) and subagent_type.startswith(ROLE_PREFIX):
            yield block.get("id"), call


def _agent_ids_by_call(records: list[dict]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for record in records:
        result = record.get("toolUseResult")
        agent_id = result.get("agentId") if isinstance(result, dict) else None
        if not isinstance(agent_id, str):
            continue
        for block in _blocks([record], "tool_result"):
            ids[block.get("tool_use_id")] = agent_id
    return ids


def _ran_model(own_records: list[dict]) -> str | None:
    for record in own_records:
        message = record.get("message")
        model = message.get("model") if isinstance(message, dict) else None
        if (
            record.get("type") == "assistant"
            and isinstance(model, str)
            and model != SYNTHETIC_MODEL
        ):
            return model
    return None


def _prompt_markers(prompt: object) -> frozenset[str]:
    text = prompt if isinstance(prompt, str) else ""
    return frozenset(marker for marker, found in _MARKER_PATTERNS.items() if found.search(text))


def _driver_request(prompt: object, own_records: list[dict]) -> DriverRequest | None:
    """The request a step-loop driver prompt answers, None for any other prompt."""
    text = prompt if isinstance(prompt, str) else ""
    first_line, _, rest = text.partition("\n")
    request = _SPAWN_REQUEST_LINE.search(rest)
    if not (request and _TASK_SLUG_LINE.match(first_line)):
        return None
    rendered = _rendered_request(own_records, _request_path(text))
    return DriverRequest(request.group(1), _implied_routing(rendered))


def _request_path(prompt: str) -> str | None:
    """The file the pointer prompt's third line tells the spawn to read."""
    lines = prompt.splitlines()
    named = _REQUEST_PATH.search(lines[2]) if len(lines) > 2 else None
    return named.group(1) if named else None


def _rendered_request(own_records: list[dict], path: str | None) -> str | None:
    """What the spawn's own transcript records it read from `path`: the file as Claude Code stores
    it in `toolUseResult`, else the numbered lines of the result message. None when it read nothing."""
    read_ids = {
        block.get("id")
        for block in _blocks(own_records, "tool_use")
        if block.get("name") == "Read"
        and isinstance(block.get("input"), dict)
        and block["input"].get("file_path") == path
    }
    for record in own_records:
        for block in _blocks([record], "tool_result"):
            if block.get("tool_use_id") in read_ids and not block.get("is_error"):
                text = _read_result_text(record, block)
                if text:
                    return text
    return None


def _read_result_text(record: dict, result_block: dict) -> str | None:
    file_result = (record.get("toolUseResult") or {}).get("file")
    content = file_result.get("content") if isinstance(file_result, dict) else None
    if isinstance(content, str):
        return content
    content = result_block.get("content")
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else None


def _implied_routing(rendered: str | None) -> ImpliedRouting | None:
    """The routing a rendered request states, by the markers the routing rule names: a light review
    outranks any step hint a review quotes."""
    if rendered is None:
        return None
    markers = _prompt_markers(rendered)
    if "Mode: light-review" in markers:
        return "sonnet"
    if "tier: H" in markers:
        return "opus"
    if "tier: L" in markers:
        return "haiku"
    return "floor"


def _blocks(records: list[dict], block_type: str):
    for record in records:
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        yield from (b for b in content if isinstance(b, dict) and b.get("type") == block_type)


def _read_records(path: Path) -> list[dict]:
    """The JSON object on each line that parses; none for a file that does not exist."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    records = []
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records
