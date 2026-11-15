"""The delivery proof: what a proof spawn's own record shows of the refactoring skill, and the
decision that follows.

Everything runs on recorded transcripts written under a sandbox's config directory. No session is
started: the plugin copy is this checkout, whose own delivery module counts the blocks and renders
the one block the tests paste.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import arms, axis_runs, grade, refactoring_arms, transcript
from praxion_evals.adherence.arms import DeliveryObservation, decide_delivery_proof
from praxion_evals.adherence.model import (
    NotBuilt,
    RepoFacts,
    SessionEvidence,
    TaskFacts,
)
from praxion_evals.adherence.refactoring_arms import observe_delivery
from praxion_evals.live.session import SandboxPaths, parse_stream

REPO_ROOT = Path(__file__).resolve().parents[2]
SPAWN = "toolu_spawn"
SESSION = "sess-proof"
AGENT = "a2450d924b822afe6"
USAGE = {"input_tokens": 3, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 50}
DELEGATION = refactoring_arms.PROOF_PROMPT
REAL_HOME = Path("/nonexistent-home")

# What the copy's delivery module renders for the installed skill, as a spawn's hook would.
_RENDER = (
    "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1] + '/hooks'); "
    "import _skill_delivery as d; skill = d.skill_dir(Path(sys.argv[1])); "
    "print(d.render_block(d.read_body(skill), skill), end='')"
)


@pytest.fixture(scope="module")
def block() -> str:
    done = subprocess.run(
        [sys.executable, "-B", "-c", _RENDER, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def _stale(block: str) -> str:
    """The same block with another body's digest in its label."""
    label, rest = block.split("]", 1)
    return label[: -len("0")] + ("1" if label.endswith("0") else "0") + "]" + rest


def _preload(skill: str = "refactoring") -> dict:
    """The harness's preload of a skill, as recorded: wrapper lines, then the directory line."""
    wrapper = f"<command-message>{skill}</command-message>\n<command-name>{skill}</command-name>"
    directory = f"Base directory for this skill: /somewhere/skills/{skill}\n\n# {skill.title()}\n"
    return {
        "type": "user",
        "isMeta": True,
        "message": {
            "role": "user",
            "content": [
                {"type": "text", "text": wrapper + "\n<skill-format>true</skill-format>"},
                {"type": "text", "text": directory},
            ],
        },
    }


def _user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _tool_result(text: str) -> dict:
    block = {"type": "tool_result", "tool_use_id": "toolu_x", "content": text}
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def _stream(cwd: Path, plugin_copy: Path, *, spawned: bool = True) -> str:
    events = [
        {
            "type": "system",
            "subtype": "init",
            "cwd": str(cwd),
            "mcp_servers": [],
            "plugins": [{"name": "praxion", "path": str(plugin_copy), "source": "praxion@inline"}],
        }
    ]
    if spawned:
        spawn = {"type": "tool_use", "id": SPAWN, "name": "Agent", "input": {"prompt": "go"}}
        events.append({"type": "assistant", "message": {"content": [spawn], "usage": USAGE}})
        role_use = {"type": "text", "text": "ARM-PROOF-DONE"}
        events.append(
            {
                "type": "assistant",
                "parent_tool_use_id": SPAWN,
                "message": {"content": [role_use], "usage": USAGE},
            }
        )
        done = f"ARM-PROOF-DONE\nagentId: {AGENT} (use SendMessage to resume)"
        result = {"type": "tool_result", "tool_use_id": SPAWN, "content": done}
        events.append({"type": "user", "message": {"content": [result]}})
    events.append({"type": "result", "subtype": "success", "is_error": False, "result": "ok"})
    events[-1]["session_id"] = SESSION
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _evidence(
    tmp_path: Path, records: list[dict] | None, *, spawned: bool = True, copy: Path = REPO_ROOT
):
    """A proof session whose role transcript (when ``records`` is not None) holds ``records``."""
    cwd, sandbox = tmp_path / "scratch", tmp_path / "sandbox"
    envelope = parse_stream(_stream(cwd, copy, spawned=spawned))
    if records is not None:
        path = transcript.transcript_path(
            SandboxPaths(sandbox).config_dir, str(cwd), SESSION, AGENT
        )
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return SessionEvidence(
        role="implementer",
        slug="arm-proof",
        envelope=envelope,
        exit_code=0,
        timed_out=False,
        sandbox=sandbox,
        plugin_copy=copy,
        spawn_id=SPAWN if spawned else None,
        role_tool_uses=(),
        role_return="ARM-PROOF-DONE",
        repo=RepoFacts({}, frozenset(), (), ()),
        facts=TaskFacts(False, False, False, None, None, None),
    )


def _observed(tmp_path: Path, records: list[dict]):
    return observe_delivery(_evidence(tmp_path, records), REAL_HOME)


def _counts(seen: DeliveryObservation) -> tuple[int, int, int]:
    return seen.delivered_blocks, seen.stray_labels, seen.preload_messages


# --- the reader of the role's user messages --------------------------------------------------


def test_user_messages_are_the_text_of_each_user_record_and_a_tool_result_is_none(tmp_path):
    path = transcript.transcript_path(tmp_path, "/w", SESSION, AGENT)
    path.parent.mkdir(parents=True)
    records = [_user("first"), _tool_result("not a message"), _preload(), {"type": "assistant"}]
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + '{"type": "user", "mess')

    read = transcript.read_role_user_messages(tmp_path, "/w", SESSION, AGENT)

    assert isinstance(read, transcript.UserMessagesRead)
    assert read.path == path
    assert read.messages[0] == "first"
    assert len(read.messages) == 2
    assert "</skill-format>\nBase directory for this skill:" in read.messages[1]


@pytest.mark.parametrize(
    ("session_id", "agent_id", "reason"),
    [(SESSION, AGENT, "was not found"), (None, AGENT, "session id"), (SESSION, None, "agent id")],
)
def test_the_user_messages_reader_says_why_a_transcript_cannot_be_read(
    tmp_path, session_id, agent_id, reason
):
    read = transcript.read_role_user_messages(tmp_path, "/w", session_id, agent_id)

    assert isinstance(read, transcript.TranscriptUnread)
    assert reason in read.reason


def test_the_user_messages_share_a_transcript_with_the_attachments_that_stay_as_read(tmp_path):
    attachment = {"type": "attachment", "attachment": {"type": "hook_success"}}
    path = transcript.transcript_path(tmp_path, "/w", SESSION, AGENT)
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in [_user("hello"), attachment]))

    read = transcript.read_role_transcript(tmp_path, "/w", SESSION, AGENT)

    assert isinstance(read, transcript.TranscriptRead)
    assert read.attachments == ({"type": "hook_success"},)


def test_the_graders_reader_finds_the_transcript_by_the_sandbox_the_session_and_the_agent(tmp_path):
    evidence = _evidence(tmp_path, [_user("hello")])

    read = grade.role_user_messages(evidence)

    assert isinstance(read, transcript.UserMessagesRead)
    assert read.messages == ("hello",)


def test_the_graders_reader_says_so_when_no_role_was_spawned(tmp_path):
    read = grade.role_user_messages(_evidence(tmp_path, None, spawned=False))

    assert isinstance(read, transcript.TranscriptUnread)
    assert "never spawned" in read.reason


# --- the observer, on recorded transcripts ---------------------------------------------------


def test_one_delivered_block_is_one_matching_block_and_the_tokens_are_recorded(tmp_path, block):
    seen = _observed(tmp_path, [_user(f"{DELEGATION}\n{block}")])

    assert isinstance(seen, DeliveryObservation)
    assert _counts(seen) == (1, 0, 0)
    assert seen.first_request_tokens == 453


def test_a_block_with_another_bodys_digest_is_a_stray_label_and_no_match(tmp_path, block):
    seen = _observed(tmp_path, [_user(f"{DELEGATION}\n{_stale(block)}")])

    assert _counts(seen) == (0, 1, 0)


def test_a_block_quoted_inside_a_code_span_is_neither_a_match_nor_a_stray(tmp_path, block):
    label = block.splitlines()[0]
    seen = _observed(
        tmp_path, [_user(f"{DELEGATION} It said `{label}` and `{block.splitlines()[-1]}`")]
    )

    assert _counts(seen) == (0, 0, 0)


def test_a_harness_preload_message_is_one_preload_and_no_block(tmp_path):
    seen = _observed(tmp_path, [_user(DELEGATION), _preload()])

    assert _counts(seen) == (0, 0, 1)


def test_the_preload_of_another_skill_is_not_a_preload_of_this_one(tmp_path):
    seen = _observed(tmp_path, [_user(DELEGATION), _preload("code-review")])

    assert _counts(seen) == (0, 0, 0)


def test_a_block_and_a_preload_together_are_both_counted(tmp_path, block):
    seen = _observed(tmp_path, [_preload(), _user(f"{DELEGATION}\n{block}")])

    assert _counts(seen) == (1, 0, 1)


def test_a_doubled_block_is_counted_twice_whether_in_one_message_or_two(tmp_path, block):
    in_one = _observed(tmp_path / "one", [_user(f"{DELEGATION}\n{block}\n{block}")])
    in_two = _observed(tmp_path / "two", [_user(f"{DELEGATION}\n{block}"), _user(block)])

    assert _counts(in_one) == (2, 0, 0)
    assert _counts(in_two) == (2, 0, 0)


def test_a_block_a_tool_result_quotes_is_not_a_delivery(tmp_path, block):
    seen = _observed(tmp_path, [_user(DELEGATION), _tool_result(block)])

    assert _counts(seen) == (0, 0, 0)


def test_a_record_with_neither_holds_no_block_and_no_preload(tmp_path):
    seen = _observed(tmp_path, [_user(DELEGATION)])

    assert _counts(seen) == (0, 0, 0)


def test_a_transcript_with_no_user_message_holds_nothing(tmp_path):
    seen = _observed(tmp_path, [{"type": "assistant", "message": {"content": []}}])

    assert _counts(seen) == (0, 0, 0)


def test_a_transcript_that_cannot_be_read_is_not_built_with_its_reason(tmp_path):
    unobserved = observe_delivery(_evidence(tmp_path, None), REAL_HOME)

    assert isinstance(unobserved, NotBuilt)
    assert "cannot be read" in unobserved.reason
    assert "was not found" in unobserved.reason


def test_a_role_never_spawned_is_not_built(tmp_path):
    unobserved = observe_delivery(_evidence(tmp_path, None, spawned=False), REAL_HOME)

    assert isinstance(unobserved, NotBuilt)
    assert "never spawned" in unobserved.reason


def test_a_copy_whose_delivery_module_cannot_run_is_not_built(tmp_path, block):
    seen = observe_delivery(
        _evidence(tmp_path, [_user(block)], copy=tmp_path / "no-copy"), REAL_HOME
    )

    assert isinstance(seen, NotBuilt)
    assert "delivery module could not read the record" in seen.reason


def test_the_proof_prompt_is_a_marked_delegation_to_the_copys_own_hook():
    program = (
        "import sys; sys.path.insert(0, sys.argv[1] + '/hooks'); import _skill_delivery as d; "
        "print(type(d.classify('praxion:implementer', sys.stdin.read(), d.read_request)).__name__)"
    )
    verdict = refactoring_arms._run(
        "the copy's delivery module",
        "-c",
        program,
        str(REPO_ROOT),
        input=refactoring_arms.PROOF_PROMPT,
    )

    assert verdict.strip() == "Marked"


# --- the decision ----------------------------------------------------------------------------

ONE_BLOCK = DeliveryObservation(1, 0, 0, 453)
ONE_PRELOAD = DeliveryObservation(0, 0, 1, 450)


def test_the_delivered_arm_is_proven_by_one_matching_block_alone():
    verdict = decide_delivery_proof({"delivered": ONE_BLOCK})["delivered"]

    assert verdict == arms.ArmProven("delivered", 453, cross_checked=False)


@pytest.mark.parametrize(
    ("seen", "why"),
    [
        (DeliveryObservation(0, 0, 0, 1), "absent"),
        (DeliveryObservation(0, 1, 0, 1), "stale"),
        (DeliveryObservation(2, 0, 0, 1), "doubled"),
        (DeliveryObservation(1, 1, 0, 1), "a stray label beside it"),
        (DeliveryObservation(1, 0, 1, 1), "accompanied by a preload"),
        (DeliveryObservation(0, 0, 1, 1), "a preload instead"),
    ],
)
def test_the_delivered_arm_is_refused_unless_exactly_one_block_arrived_alone(seen, why):
    verdict = decide_delivery_proof({"delivered": seen})["delivered"]

    assert isinstance(verdict, NotBuilt), why
    assert "delivered arm" in verdict.reason


def test_the_preloaded_arm_is_proven_by_one_preload_message_alone():
    verdict = decide_delivery_proof({"preloaded": ONE_PRELOAD})["preloaded"]

    assert verdict == arms.ArmProven("preloaded", 450, cross_checked=False)


@pytest.mark.parametrize(
    "seen",
    [
        DeliveryObservation(0, 0, 0, 1),
        DeliveryObservation(0, 0, 2, 1),
        DeliveryObservation(1, 0, 1, 1),
        DeliveryObservation(0, 1, 1, 1),
    ],
)
def test_the_preloaded_arm_is_refused_unless_exactly_one_preload_arrived_alone(seen):
    verdict = decide_delivery_proof({"preloaded": seen})["preloaded"]

    assert isinstance(verdict, NotBuilt)
    assert "preloaded arm" in verdict.reason


def test_a_role_never_spawned_is_not_built_and_each_arm_is_decided_on_its_own():
    verdicts = decide_delivery_proof({"preloaded": ONE_PRELOAD, "delivered": None})

    assert isinstance(verdicts["preloaded"], arms.ArmProven)
    assert isinstance(verdicts["delivered"], NotBuilt)
    assert "never spawned" in verdicts["delivered"].reason


def test_the_tokens_are_recorded_and_never_decisive():
    unmeasured = decide_delivery_proof({"delivered": replace(ONE_BLOCK, first_request_tokens=None)})
    both = decide_delivery_proof({"preloaded": ONE_PRELOAD, "delivered": ONE_BLOCK})

    assert unmeasured["delivered"] == arms.ArmProven("delivered", None, cross_checked=False)
    assert all(v.cross_checked is False for v in both.values())
    assert both["delivered"].first_request_tokens > both["preloaded"].first_request_tokens


def test_an_arm_of_the_other_axis_is_not_decided_here():
    with pytest.raises(ValueError, match="unknown arms"):
        decide_delivery_proof({"lean": ONE_BLOCK})


# --- the default axis keeps its decision -----------------------------------------------------


def test_the_default_axis_still_decides_on_the_nonce_and_names_its_unknown_arms():
    nonce = "abcd1234"
    seen = arms.ProofObservation(f"PRXARM-{nonce}", 100)

    assert arms.decide_proof(nonce, {"full": seen})["full"] == arms.ArmProven("full", 100, False)
    with pytest.raises(ValueError, match="unknown arms"):
        arms.decide_proof(nonce, {"delivered": seen})  # type: ignore[dict-item]


def test_a_proven_arm_is_one_of_the_axes_arms_and_nothing_else():
    for name in ("full", "lean", "preloaded", "delivered"):
        assert arms.ArmProven(name, None, cross_checked=False).arm == name
    with pytest.raises(ValueError, match="a proven arm must be one of"):
        arms.ArmProven("middle", None, cross_checked=False)  # type: ignore[arg-type]


# --- the new axis's proof --------------------------------------------------------------------


def test_the_new_axis_proof_is_the_delivery_proof_and_the_default_keeps_the_nonce_proof():
    proof = axis_runs.axis_run("refactoring-delivery").proof

    assert proof.prompt == refactoring_arms.PROOF_PROMPT
    assert proof.observe is refactoring_arms.observe_delivery
    assert proof.decide("", {"delivered": ONE_BLOCK}) == decide_delivery_proof(
        {"delivered": ONE_BLOCK}
    )
    assert axis_runs.DEFAULT_RUN.proof.observe is arms.observe_proof


def test_the_new_axis_prepares_a_task_home_and_plants_no_nonce(tmp_path, monkeypatch):
    installed: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        axis_runs, "install_user_scope", lambda root, home: installed.append((root, home))
    )
    original = type("Original", (), {"root": tmp_path / "original"})()

    nonce = axis_runs.axis_run("refactoring-delivery").proof.prepare(original, tmp_path / "home")

    assert nonce == ""
    assert installed == [(tmp_path / "original", tmp_path / "home")]
