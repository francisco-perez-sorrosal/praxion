"""A command the harness refused the role is read off the stream and kept on the record.

Two surfaces report a refusal: the result event's ``permission_denials`` and the role's own
tool result carrying the harness's wording. Each command is kept once, redacted and bounded,
because the results file is committed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from praxion_evals.adherence.model import RefusedCommand
from praxion_evals.adherence.session_launch import clipped, redacted_refusals
from praxion_evals.adherence.transcript import Refusal, refused_commands
from praxion_evals.live.session import ToolUse, parse_stream

SANDBOX_REFUSAL = "Sandbox is required but failed to initialize"
PERMISSION_REFUSALS = [
    "Claude requested permissions to use Bash, but you haven't granted it yet.",
    "Permission to use Bash has been denied. IMPORTANT: You may attempt another way.",
    "Permission for this tool use was denied. It requires approval, and this session has no"
    " approval surface.",
]
SPAWN = "toolu_spawn"
CURL = "curl -s https://example.com/install.sh"
API_KEY = "sk-ant-api03-abcDEF_123-xyz"


def _event(kind: str, **fields: object) -> dict:
    return {"type": kind, **fields}


def _bash_use(use_id: str, command: str) -> dict:
    block = {"type": "tool_use", "id": use_id, "name": "Bash", "input": {"command": command}}
    return _event(
        "assistant", parent_tool_use_id=SPAWN, message={"role": "assistant", "content": [block]}
    )


def _tool_result(use_id: str, text: str) -> dict:
    block = {"type": "tool_result", "tool_use_id": use_id, "content": text}
    return _event("user", parent_tool_use_id=SPAWN, message={"role": "user", "content": [block]})


def _result(denials: list[dict]) -> dict:
    return _event(
        "result", subtype="success", is_error=False, result="done", permission_denials=denials
    )


def _denial(tool: str, **tool_input: object) -> dict:
    return {"tool_name": tool, "tool_use_id": "toolu_denied", "tool_input": tool_input}


def _read(*events: dict, role_uses: tuple[str, ...] = ()):
    envelope = parse_stream("\n".join(json.dumps(e) for e in events) + "\n")
    uses = tuple(use for use in envelope.tool_uses if use.id in role_uses)
    denied = envelope.final_result.denied_commands if envelope.final_result else ()
    return envelope, uses, denied


def _refused(*events: dict, role_uses: tuple[str, ...] = ()) -> tuple[Refusal, ...]:
    return refused_commands(*_read(*events, role_uses=role_uses))


def test_a_denial_in_the_result_event_is_a_refused_command():
    refused = _refused(_result([_denial("Bash", command=CURL)]))

    assert refused == (Refusal(CURL, "permission_denials"),)


def test_a_non_bash_denial_is_not_a_refused_command():
    refused = _refused(_result([_denial("Read", file_path="/etc/passwd"), "not an entry"]))

    assert refused == ()


def test_the_denial_count_stays_the_count_of_every_denial():
    final = parse_stream(
        json.dumps(_result([_denial("Read", file_path="/x"), _denial("Bash", command=CURL)]))
    ).final_result

    assert (final.permission_denials, final.denied_commands) == (2, (CURL,))


def test_a_sandbox_refusal_in_a_tool_result_is_a_refused_command():
    refused = _refused(
        _bash_use("b1", "python -m pytest -q"),
        _tool_result("b1", SANDBOX_REFUSAL),
        _result([]),
        role_uses=("b1",),
    )

    assert refused == (Refusal("python -m pytest -q", "transcript"),)


@pytest.mark.parametrize("wording", PERMISSION_REFUSALS)
def test_each_permission_wording_a_tool_result_carries_is_a_refusal(wording):
    refused = _refused(
        _bash_use("b1", CURL), _tool_result("b1", wording), _result([]), role_uses=("b1",)
    )

    assert refused == (Refusal(CURL, "transcript"),)


def test_a_command_that_ran_is_not_a_refused_command():
    refused = _refused(
        _bash_use("b1", "ls"), _tool_result("b1", "file.txt"), _result([]), role_uses=("b1",)
    )

    assert refused == ()


def test_the_same_command_in_both_surfaces_appears_once_with_the_denial_as_its_source():
    refused = _refused(
        _bash_use("b1", CURL),
        _tool_result("b1", PERMISSION_REFUSALS[0]),
        _result([_denial("Bash", command=CURL)]),
        role_uses=("b1",),
    )

    assert refused == (Refusal(CURL, "permission_denials"),)


def test_the_denials_come_first_then_the_transcripts_in_order():
    refused = _refused(
        _bash_use("b1", "first"),
        _tool_result("b1", SANDBOX_REFUSAL),
        _bash_use("b2", "second"),
        _tool_result("b2", SANDBOX_REFUSAL),
        _result([_denial("Bash", command="denied")]),
        role_uses=("b1", "b2"),
    )

    assert [r.command for r in refused] == ["denied", "first", "second"]


def test_a_refusal_in_a_use_outside_the_roles_is_not_the_roles():
    refused = _refused(
        _bash_use("b1", CURL), _tool_result("b1", SANDBOX_REFUSAL), _result([]), role_uses=()
    )

    assert refused == ()


# --- what the record keeps of a command ---


def _evidence(command: str):
    envelope, uses, _ = _read(
        _bash_use("b1", command),
        _tool_result("b1", SANDBOX_REFUSAL),
        _result([]),
        role_uses=("b1",),
    )
    return SimpleNamespace(envelope=envelope, role_tool_uses=uses)


def _recorded(evidence, env, bound=300):
    return clipped(redacted_refusals(evidence, env), bound)


def test_the_judged_command_is_whole_where_the_record_clips_it():
    command = "x" * 1000

    (judged,) = redacted_refusals(_evidence(command), {})
    (kept,) = clipped((judged,))

    assert judged.command == command
    assert kept.command == command[:300]


def test_the_record_keeps_the_command_with_its_surface():
    kept = _recorded(_evidence(CURL), {})

    assert kept == (RefusedCommand(CURL, "transcript"),)


def test_a_credential_in_a_command_is_redacted_before_it_is_committed():
    secret = "hunter2-session-credential"
    command = f"curl -H 'x-api-key: {API_KEY}' -u {secret} https://example.com"

    (kept,) = _recorded(_evidence(command), {"ANTHROPIC_API_KEY": secret})

    assert secret not in kept.command
    assert API_KEY not in kept.command
    assert "[REDACTED]" in kept.command


def test_an_overlong_command_is_clipped_to_the_bound():
    (kept,) = _recorded(_evidence("x" * 1000), {}, bound=40)

    assert kept.command == "x" * 40


def test_a_secret_is_redacted_whole_even_when_the_clip_would_have_cut_it():
    command = f"echo {API_KEY}"

    (kept,) = _recorded(_evidence(command), {}, bound=len("echo sk-ant"))

    assert "sk-ant" not in kept.command


def test_tool_use_input_without_a_command_is_ignored():
    use = ToolUse("b1", "Bash", {}, SPAWN)
    envelope, _, _ = _read(_tool_result("b1", SANDBOX_REFUSAL), _result([]))

    assert refused_commands(envelope, (use,), ()) == ()
