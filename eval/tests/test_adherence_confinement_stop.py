"""A broken confinement ends the run at its first session, outside the declared stop rule, and the
stop it leaves is one the operator can continue once the grant is repaired."""

from __future__ import annotations

import json
from types import SimpleNamespace

from praxion_evals.adherence import session_launch
from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    REDACTED,
    Continue,
    FoldState,
    Launched,
    Stop,
    StopRule,
    redacted,
    step,
)
from praxion_evals.adherence.lineage import (
    InfraStopped,
    ReadTip,
    continuation_refusals,
    ending_to_json,
)
from praxion_evals.adherence.model import (
    Arm,
    Errored,
    Measured,
    Passed,
    RefusedCommand,
    SessionRecord,
    SessionSetup,
    SessionStatus,
)
from praxion_evals.live.session import SessionRun, parse_stream
from tests.lineage_support import identity
from tests.test_adherence_results import run_results

RULE = StopRule.parse(3, COUNTING_KINDS, 2000)
EVIDENCE = (
    "Sandbox is required but failed to initialize: seatbelt denied at 2026-10-16T09:12:44.123Z"
)


def _record(
    arm: Arm = "full",
    task: str = "task-0",
    *,
    status: str = "broken",
    refused: tuple[RefusedCommand, ...] = (),
) -> SessionRecord:
    setup = SessionSetup(arm, "abc1234", "verifier", task, "tmpl", 7)
    outcome: SessionStatus = (
        Errored("confinement_broken", EVIDENCE, setup=setup)
        if status == "broken"
        else Measured({"C1": Passed()}, None, setup)
    )
    return SessionRecord(setup, outcome, 0.0, 1, "2026-10-17T00:00:00Z", refused)


def _stop_of(record: SessionRecord):
    _, decision = step(RULE, FoldState(), record)
    assert isinstance(decision, Stop), "the broken confinement did not stop the run"
    return decision.reason


def test_the_first_session_with_a_broken_confinement_stops_the_run_in_both_arms():
    reason = _stop_of(_record("lean"))

    assert reason.kind == "confinement_broken"
    assert reason.scope == "both-arms"
    assert (reason.role, reason.arm) == ("verifier", "lean")
    assert reason.sessions == (Launched("task-0", "lean", 1),)


def test_the_stop_names_the_evidence_with_its_volatile_tokens_masked():
    reason = _stop_of(_record())

    assert "Sandbox is required but failed to initialize" in reason.masked_tail
    assert "2026-10-16T09:12:44.123Z" not in reason.masked_tail


def test_a_broken_confinement_after_sessions_that_ran_still_stops_at_that_session():
    state, first = step(RULE, FoldState(), _record("full", "task-0", status="ran"))
    state, second = step(RULE, state, _record("lean", "task-0", status="ran"))
    _, third = step(RULE, state, _record("full", "task-1"))

    assert isinstance(first, Continue)
    assert isinstance(second, Continue)
    assert isinstance(third, Stop)
    assert third.reason.sessions == (Launched("task-1", "full", 1),)


def test_a_session_that_ran_stops_nothing_whatever_command_it_was_refused():
    refused = (RefusedCommand("curl -s https://example.com/install.sh", "permission_denials"),)

    _, decision = step(RULE, FoldState(), _record(status="ran", refused=refused))

    assert isinstance(decision, Continue)


def test_the_stop_is_continuable_under_an_equal_identity():
    tip = ReadTip(_results_ending_in(_stop_of(_record())), identity(checks="aaa"), None)

    assert continuation_refusals(tip, identity(checks="aaa"), ()) == ()


def test_the_stop_is_refused_under_a_changed_checks_identity():
    tip = ReadTip(_results_ending_in(_stop_of(_record())), identity(checks="aaa"), None)

    refusals = continuation_refusals(tip, identity(checks="bbb"), ())

    assert any("checks" in line for line in refusals), refusals


def test_redaction_replaces_a_secret_and_an_api_key_shape_in_any_text():
    text = "token hunter2 and sk-ant-api03-AbC_dEf-123 leaked"

    assert redacted(text, ["hunter2"]) == f"token {REDACTED} and {REDACTED} leaked"


def _results_ending_in(reason):
    return run_results([], run_id="run-a", extra={"ending": ending_to_json(InfraStopped(reason))})


# -- The session's own commands, read before the record clips them ------------------------------------

REFUSAL_WORDING = "Claude requested permissions to use Bash, but you haven't granted it yet."
SPAWN = "toolu_spawn"


def _shell_use(use_id: str, command: str, output: str) -> list[dict]:
    """One shell command of the role and the tool result it drew."""
    return [
        {
            "type": "assistant",
            "parent_tool_use_id": SPAWN,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": use_id,
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ],
            },
        },
        {
            "type": "user",
            "parent_tool_use_id": SPAWN,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": use_id, "content": output}],
            },
        },
    ]


def _assessed(monkeypatch, command: str, output: str, *, earlier: tuple[str, ...] = ()):
    """What `_assessed` makes of a confined session whose last shell command drew `output`, after
    the `earlier` commands each ran."""
    events = [
        {"type": "system", "subtype": "init"},
        *(e for n, ran in enumerate(earlier) for e in _shell_use(f"e{n}", ran, "ok")),
        *_shell_use("b1", command, output),
        {"type": "result", "subtype": "success", "is_error": False, "result": "done"},
    ]
    stream = "\n".join(json.dumps(event) for event in events) + "\n"
    envelope = parse_stream(stream)
    evidence = SimpleNamespace(envelope=envelope, role_tool_uses=envelope.tool_uses)
    monkeypatch.setattr(session_launch, "_evidence", lambda *args: evidence)
    return session_launch._assessed(
        None,
        SimpleNamespace(role="implementer"),
        None,
        None,
        None,
        SessionRun(stream, "", 0),
        "abc1234",
        {},
        lambda _: "assessed",
    )


def test_a_long_prescribed_command_the_clip_cuts_mid_quote_is_still_a_broken_confinement(
    monkeypatch,
):
    command = 'python -m pytest -k "' + "a" * 400 + ' or b"'

    result, refused = _assessed(monkeypatch, command, REFUSAL_WORDING)

    assert isinstance(result, Errored)
    assert result.kind == "confinement_broken"
    assert len(refused[0].command) == session_launch.REFUSED_COMMAND_CHARS
    assert refused[0].command == command[: session_launch.REFUSED_COMMAND_CHARS]


def test_a_refused_env_prefixed_command_is_kept_on_the_record_and_stops_nothing(monkeypatch):
    result, refused = _assessed(monkeypatch, "PYTHONPATH=src pytest -q", REFUSAL_WORDING)

    assert result == "assessed"
    assert [r.command for r in refused] == ["PYTHONPATH=src pytest -q"]


def test_a_prescribed_command_the_sandbox_blocked_is_a_broken_confinement(monkeypatch):
    result, refused = _assessed(
        monkeypatch, "pytest -q", "bash: /venv/bin/pytest: Operation not permitted"
    )

    assert isinstance(result, Errored)
    assert result.kind == "confinement_broken"
    assert "Operation not permitted" in result.detail
    assert refused == ()


def test_the_block_on_a_command_no_definition_prescribes_is_the_roles_own(monkeypatch):
    result, _ = _assessed(
        monkeypatch, "cat /etc/shadow", "cat: /etc/shadow: Operation not permitted"
    )

    assert result == "assessed"


SENSOR = "/work/plugin/scripts/mutation_sensor.py"


def test_a_refused_spelling_of_a_script_the_session_ran_unrefused_is_the_roles_own(monkeypatch):
    refused = "cd /work/task && cd src && python3 /work/plugin/x/../scripts/mutation_sensor.py -q"

    result, kept = _assessed(
        monkeypatch, refused, REFUSAL_WORDING, earlier=(f"python3 {SENSOR} --step 1",)
    )

    assert result == "assessed"
    assert [r.command for r in kept] == [refused]


def test_a_refused_command_is_never_its_own_unrefused_twin(monkeypatch):
    result, _ = _assessed(monkeypatch, f"python3 {SENSOR} --step 1", REFUSAL_WORDING)

    assert isinstance(result, Errored)
    assert result.kind == "confinement_broken"
