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
driver, and the spawn keeps that id together with the routing its request implies. The driver
routes a spawn by the step's own `tier:` field (`_plan_steps.py` is the grammar that reads it) and
a light review by the pointer prompt, so that is all the reading takes from it: a `Mode:
light-review` in the pointer (its third line names the request's file and may open with it, which
the renderer writes there and nowhere in the file) implies `sonnet`; otherwise the spawn's own
transcript records its `Read`s of the file, and the step's `tier:` field in what it read implies
the routing, `floor` when it read the whole file and the step has none. A marker in step prose, in
a code fence or in a section after the step block sets nothing. A request is shown only when a read
held the field or the whole file; a first part of a longer file that stops short of it shows
nothing, and neither does a read with no line counts that asked for an `offset` or a `limit`.

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

from _plan_steps import Routing, parse_plan_steps  # noqa: E402
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
LIGHT_REVIEW = "Mode: light-review"
# The model Claude Code records on entries it wrote itself (an interrupt, an API error), not on a
# model's reply.
SYNTHETIC_MODEL = "<synthetic>"

_MARKER_PATTERNS = {
    marker: re.compile(rf"(?<![\w-]){re.escape(marker)}(?![\w-])") for marker in PROMPT_MARKERS
}
_REQUEST_PATH = re.compile(r"\bRead (\S+)")
_LINE_NUMBER_PREFIX = re.compile(r"^\s*\d+[\t\u2192]", re.MULTILINE)
_STEP_BLOCK_END = "\n</step>"
_STEP_OPENING = "### Step 0\n"  # id-citation-discipline:ignore
_TASK_SLUG_LINE = re.compile(r"Task slug: \S")
_SPAWN_REQUEST_LINE = re.compile(r"^Spawn request: (\S+)", re.MULTILINE)


# The model family a driver request implies; `floor` is a request that asks for no deviation.
ImpliedRouting = Literal["sonnet", "opus", "haiku", "floor"]


@dataclass(frozen=True)
class DriverRequest:
    """The step-loop request a spawn answers. `implied` is the routing the spawn's request states:
    `sonnet` for a light review its pointer prompt names, else the one its rendered request's step
    names by its own `tier:` field (`floor` when it read the whole request and there is none).
    None when neither is shown."""

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
    if LIGHT_REVIEW in _prompt_markers(text):
        return DriverRequest(request.group(1), "sonnet")
    return DriverRequest(request.group(1), _read_step_routing(own_records, _request_path(text)))


def _request_path(prompt: str) -> str | None:
    """The file the pointer prompt's third line tells the spawn to read."""
    lines = prompt.splitlines()
    named = _REQUEST_PATH.search(lines[2]) if len(lines) > 2 else None
    return named.group(1) if named else None


def _read_step_routing(own_records: list[dict], path: str | None) -> ImpliedRouting | None:
    """The routing of the step in what the spawn's own transcript records it read from `path`,
    across all its reads. None when it read nothing, or only parts of the file that held no tier
    field: the transcripts then do not show the request."""
    reads = _request_reads(own_records, path)
    if not reads:
        return None
    routing = _step_routing("\n".join(text for text, _ in reads))
    if routing != "sonnet":
        return routing
    return "floor" if any(whole for _, whole in reads) else None


def _step_routing(text: str) -> Routing:
    """The routing the driver derives from the first step in `text`, which ends at the rendered
    step block's closing tag; text that opens no step heading (a later part of the file) is read as
    the body of one."""
    block = text.partition(_STEP_BLOCK_END)[0]
    steps = parse_plan_steps(block) or parse_plan_steps(_STEP_OPENING + block)
    return steps[0].routing if steps else "sonnet"


def _request_reads(own_records: list[dict], path: str | None) -> list[tuple[str, bool]]:
    """(text, whole file) of each successful `Read` of `path` in the spawn's own transcript."""
    asked = {
        block.get("id"): block["input"]
        for block in _blocks(own_records, "tool_use")
        if block.get("name") == "Read"
        and isinstance(block.get("input"), dict)
        and block["input"].get("file_path") == path
    }
    reads = []
    for record in own_records:
        for block in _blocks([record], "tool_result"):
            if block.get("tool_use_id") not in asked or block.get("is_error"):
                continue
            text = _read_result_text(record, block)
            if text:
                reads.append((text, _is_whole_file(record, asked[block["tool_use_id"]])))
    return reads


def _read_result_text(record: dict, result_block: dict) -> str | None:
    """The file as Claude Code stores it in `toolUseResult`, else the numbered lines of the result
    without their numbers."""
    file_result = _file_result(record)
    content = file_result.get("content") if file_result else None
    if isinstance(content, str):
        return content
    content = result_block.get("content")
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return _LINE_NUMBER_PREFIX.sub("", content) if isinstance(content, str) else None


def _is_whole_file(record: dict, read_input: dict) -> bool:
    """Whether a read result holds the whole file. The line counts decide when the result records
    them; without, the read is whole unless it asked for an `offset` or a `limit`."""
    file_result = _file_result(record) or {}
    lines, total = file_result.get("numLines"), file_result.get("totalLines")
    if isinstance(lines, int) and isinstance(total, int):
        return lines >= total
    return not (read_input.get("offset") or read_input.get("limit"))


def _file_result(record: dict) -> dict | None:
    result = record.get("toolUseResult")
    file_result = result.get("file") if isinstance(result, dict) else None
    return file_result if isinstance(file_result, dict) else None


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
