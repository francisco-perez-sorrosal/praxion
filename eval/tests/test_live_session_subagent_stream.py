"""The stream parser reads a spawned subagent's own words and its first request.

Two additions to ``SessionEnvelope`` serve the adherence eval: the result text of
each tool use keyed by tool-use id (the spawn's included), and the first request a
subagent made keyed by the spawn that started it. Both are read from the recorded
envelopes and from the foreground shape the harness emits for a synchronous spawn.
"""

from __future__ import annotations

import json
from pathlib import Path

from praxion_evals.live.session import (
    UNPARSEABLE_ENVELOPE,
    RequestUsage,
    SessionEnvelope,
    parse_stream,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "live_scenarios"
BACKGROUND_SPAWN = "toolu_019Na3M1JsL25rwD8kcakVxH"
UI_STEP_SPAWN = "toolu_019SBTCSNzNL7RJVAfbCnfED"
LAUNCH_STUB = "Async agent launched successfully."


def _recorded(name: str) -> SessionEnvelope:
    return parse_stream((FIXTURES_DIR / f"{name}.stream.jsonl").read_text(encoding="utf-8"))


def _stream(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _assistant(parent: str | None, usage: dict, content: list | None = None) -> dict:
    return {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {"role": "assistant", "content": content or [], "usage": usage},
    }


def _tool_result(tool_use_id: str, content: object, parent: str | None = None) -> dict:
    return {
        "type": "user",
        "parent_tool_use_id": parent,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}],
        },
    }


# ---------------------------------------------------------------------------
# First request of the spawned subagent
# ---------------------------------------------------------------------------


def test_the_first_subagent_request_is_read_off_the_recorded_background_spawn():
    envelope = _recorded("subagent_implementer_background_sonnet")

    assert envelope.subagent_first_usage == {
        BACKGROUND_SPAWN: RequestUsage(
            input_tokens=2, cache_creation_tokens=55622, cache_read_tokens=0
        )
    }
    assert envelope.subagent_first_usage[BACKGROUND_SPAWN].total == 55624


def test_only_the_first_request_of_a_subagent_counts_not_its_later_ones():
    envelope = _recorded("ui_step_conformance")

    # The role made dozens of requests; the first (cold cache) is its startup payload,
    # the later ones read a warmed cache (cache_creation 6025, cache_read 53831, ...).
    assert envelope.subagent_first_usage[UI_STEP_SPAWN].total == 53833


def test_the_main_sessions_own_requests_are_not_a_subagents_first_request():
    envelope = _recorded("lightweight_fix")

    assert envelope.subagent_first_usage == {}


def test_a_usage_without_cache_fields_counts_the_missing_ones_as_zero():
    envelope = parse_stream(_stream(_assistant("spawn-1", {"input_tokens": 7})))

    assert envelope.subagent_first_usage == {"spawn-1": RequestUsage(7, 0, 0)}


# ---------------------------------------------------------------------------
# Tool result text
# ---------------------------------------------------------------------------


def test_a_background_spawn_result_is_the_launch_stub_not_the_role_return():
    envelope = _recorded("subagent_implementer_background_sonnet")

    assert envelope.tool_results[BACKGROUND_SPAWN].startswith(LAUNCH_STUB)


def test_a_tool_result_given_as_a_plain_string_is_kept_verbatim():
    envelope = _recorded("ui_step_conformance")

    texts = [text for text in envelope.tool_results.values() if text.startswith("1\t# WIP")]
    assert len(texts) == 1
    assert "Status: TODO" in texts[0]


def test_a_foreground_spawn_result_joins_its_text_blocks_in_order():
    stream = _stream(
        _tool_result(
            "spawn-1",
            [
                {"type": "text", "text": "Findings written.\n[COMPLETE]"},
                {"type": "text", "text": "agentId: abc123"},
                {"type": "image", "source": "ignored"},
            ],
        )
    )

    assert parse_stream(stream).tool_results == {
        "spawn-1": "Findings written.\n[COMPLETE]\nagentId: abc123"
    }


def test_an_empty_result_is_recorded_as_empty_text_not_dropped():
    envelope = parse_stream(_stream(_tool_result("spawn-1", [])))

    assert envelope.tool_results == {"spawn-1": ""}


def test_a_tool_result_without_its_tool_use_id_invalidates_the_stream():
    broken = _tool_result("x", "text")
    del broken["message"]["content"][0]["tool_use_id"]

    assert parse_stream(_stream(broken)).unparseable


# ---------------------------------------------------------------------------
# Additive: nothing existing changes
# ---------------------------------------------------------------------------


def test_the_new_fields_default_empty_so_older_constructions_are_unchanged():
    assert UNPARSEABLE_ENVELOPE.tool_results == {}
    assert UNPARSEABLE_ENVELOPE.subagent_first_usage == {}


def test_every_recorded_envelope_still_parses():
    names = sorted(path.name for path in FIXTURES_DIR.glob("*.stream.jsonl"))

    parsed = {
        name: parse_stream((FIXTURES_DIR / name).read_text(encoding="utf-8")) for name in names
    }

    assert names
    assert [name for name, envelope in parsed.items() if envelope.unparseable] == []
