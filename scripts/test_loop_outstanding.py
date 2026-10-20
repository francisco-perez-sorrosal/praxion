"""Tests for the outstanding-request probe (``scripts/_step_loop_outstanding.py``).

Every world is built under ``tmp_path``: a task directory with its ``WIP.md``, prompt file and
ledger, a ``CLAUDE_CONFIG_DIR`` holding one session's ``subagents`` directory, and a stand-in
agents directory for the turn cap. The parity tests ask the driver's own ``record`` reading
(``_step_loop_record.sight``) the same question, so the probe never holds what ``record`` would
refuse as running.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_files as files  # noqa: E402
import _step_loop_outstanding as probe  # noqa: E402
import _step_loop_record as record  # noqa: E402
from _loop_fields import OutstandingAttempt, render_attempts_line  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import Invocation, RequestKey, spawn_request  # noqa: E402
from iteration_ledger import IterationRecord, append_record  # noqa: E402

REQUEST, SLUG, STEP = "s2-a1-implement", "demo", "2"
SESSION, AGENT = "sess-1", "a1b2c3"
MAX_TURNS = 3
INVOCATION = Invocation("step-loop")
SPAWN_PROMPT = f"Task slug: {SLUG}\nSpawn request: {REQUEST}\nRead PROMPT_{REQUEST}.md first."


def user(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def assistant(request_id: str, *blocks: dict) -> dict:
    return {"type": "assistant", "requestId": request_id, "message": {"content": list(blocks)}}


def say(text: str) -> dict:
    return {"type": "text", "text": text}


def call(name: str) -> dict:
    return {"type": "tool_use", "name": name, "input": {}}


MARKED = [
    user(SPAWN_PROMPT),
    assistant("r1", call("Edit")),
    assistant("r2", say("done\n[COMPLETE]")),
]
UNMARKED = [user(SPAWN_PROMPT), assistant("r1", call("Edit")), assistant("r2", say("all done"))]
CAPPED = [user(SPAWN_PROMPT), *(assistant(f"r{n}", call("Edit")) for n in range(MAX_TURNS))]
RUNNING = [user(SPAWN_PROMPT), assistant("r1", say("working"), call("Bash"))]
HELD_FIXTURES = {"marker": MARKED, "final-text": UNMARKED, "turn-cap": CAPPED}


class World:
    """One session's files: the task directories, the transcripts and the observation log."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.work = root / ".ai-work"
        self.subagents = root / "config" / "projects" / "p" / SESSION / "subagents"
        self.subagents.mkdir(parents=True)
        self.stopped: set[str] = set()

    def issue(
        self, request: str = REQUEST, *, slug: str = SLUG, step: str = STEP, at: float = 100.0
    ):
        task = self.work / slug
        task.mkdir(parents=True, exist_ok=True)
        line = render_attempts_line(step, OutstandingAttempt(1, request))
        with (task / "WIP.md").open("a", encoding="utf-8") as stream:
            stream.write(f"- [ ] Step {step}: do it\n  {line}\n")
        prompt = task / f"PROMPT_{request}.md"
        prompt.write_text("prompt\n", encoding="utf-8")
        os.utime(prompt, (at, at))
        return task

    def record(self, task: Path, request: str = REQUEST) -> None:
        append_record(
            task,
            IterationRecord(
                step=f"Step {STEP}",
                attempt=1,
                agent_id=AGENT,
                verdict="verified-complete",
                decided_by="check",
                test_result="Result: pass=3 fail=0 skip=0 pending=0 by=step-loop",
                commit="abc1234",
                stop_reason="completed",
                request=request,
                step_digest="0123456789ab",
                turns=2,
                max_turns=MAX_TURNS,
            ),
        )

    def put(self, records: list[dict], agent: str = AGENT, *, under: str = "") -> Path:
        directory = self.subagents / under
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"agent-{agent}.jsonl"
        path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
        return path

    def held(self, invocation: Invocation = INVOCATION):
        return probe.ended_unrecorded(self.work, self.subagents, invocation)

    def verdicts(self):
        return [v for _, v in probe.judge_outstanding(self.work, self.subagents, INVOCATION)]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    agents = tmp_path / "agents"
    agents.mkdir()
    for name in ("implementer", "verifier"):
        (agents / f"{name}.md").write_text(f"---\nname: {name}\nmaxTurns: {MAX_TURNS}\n---\n")
    built = World(tmp_path)
    monkeypatch.setattr(record, "AGENTS_DIR", agents)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(
        files,
        "session_wal_rows",
        lambda root: [{"event_type": "agent_stop", "agent_id": a} for a in built.stopped],
    )
    return built


# --- A request whose agent has ended is held -----------------------------------------------


def test_a_final_text_with_a_marker_holds_the_request_with_that_marker(world: World) -> None:
    world.issue()
    world.put(MARKED)

    (held,) = world.held()

    assert (held.outstanding.request, held.agent_id, held.marker) == (REQUEST, AGENT, "complete")


def test_a_final_text_without_a_marker_holds_the_request_as_none(world: World) -> None:
    world.issue()
    world.put(UNMARKED)

    (held,) = world.held()

    assert held.marker == "none"


def test_an_agent_at_its_turn_cap_holds_the_request(world: World) -> None:
    world.issue()
    world.put(CAPPED)

    assert [h.agent_id for h in world.held()] == [AGENT]


def test_an_agent_stop_row_holds_a_request_whose_agent_was_last_calling_a_tool(
    world: World,
) -> None:
    world.issue()
    world.put(RUNNING)
    before = world.held()
    world.stopped.add(AGENT)

    assert (before, [h.agent_id for h in world.held()]) == ((), [AGENT])


def test_a_transcript_under_a_workflow_run_holds_the_request_too(world: World) -> None:
    world.issue()
    world.put(MARKED, under="workflows/run-1")

    assert [h.agent_id for h in world.held()] == [AGENT]


# --- What is never held --------------------------------------------------------------------


def test_a_running_agent_does_not_hold_the_request(world: World) -> None:
    world.issue()
    world.put(RUNNING)

    assert (world.held(), world.verdicts()) == ((), [probe.NotHeld("running")])


def test_a_request_no_transcript_of_the_session_names_is_not_held(world: World) -> None:
    world.issue()
    other = [user("Spawn request: s9-a1-implement"), assistant("r1", say("[COMPLETE]"))]
    world.put(other)

    assert (world.held(), world.verdicts()) == ((), [probe.NotHeld("no-transcript-in-session")])


def test_an_agent_that_wrote_no_transcript_does_not_hold_the_request(world: World) -> None:
    world.issue()

    assert (world.held(), world.verdicts()) == ((), [probe.NotHeld("no-transcript-in-session")])


def test_a_file_whose_name_is_not_an_agent_id_does_not_hold_the_request(world: World) -> None:
    world.issue()
    world.put(MARKED, agent="a.b")

    assert world.held() == ()


def test_a_transcript_with_one_unparseable_line_is_not_held_even_where_record_accepts_it(
    world: World,
) -> None:
    world.issue()
    path = world.put(MARKED)
    first, *rest = path.read_text().splitlines()
    path.write_text("\n".join([first, "{not json", *rest]) + "\n")

    seen = record.sight(world.root, AGENT, MAX_TURNS)

    assert (seen.ended, world.held(), world.verdicts()) == (
        True,
        (),
        [probe.NotHeld("unreadable")],
    )


def test_an_assistant_record_without_a_request_id_is_not_held(world: World) -> None:
    world.issue()
    headless = {"type": "assistant", "message": {"content": [say("[COMPLETE]")]}}
    world.put([user(SPAWN_PROMPT), headless])

    assert world.verdicts() == [probe.NotHeld("unreadable")]


def test_a_recorded_request_is_not_outstanding(world: World) -> None:
    task = world.issue()
    world.record(task)
    world.put(MARKED)

    assert (probe.outstanding_requests(world.work), world.held()) == ((), ())


def test_a_task_whose_ledger_has_a_broken_line_yields_no_request(world: World) -> None:
    task = world.issue()
    (task / "ITERATION_LEDGER.jsonl").write_text("not a record\n")
    world.put(MARKED)

    assert (probe.outstanding_requests(world.work), world.held()) == ((), ())


def test_a_task_whose_wip_cannot_be_read_yields_no_request(world: World) -> None:
    task = world.issue()
    (task / "WIP.md").write_bytes(b"\xff\xfe- Attempts: unreadable")

    assert probe.outstanding_requests(world.work) == ()


def test_an_absent_work_root_yields_nothing(tmp_path: Path) -> None:
    assert probe.ended_unrecorded(tmp_path / "none", tmp_path / "also-none", INVOCATION) == ()


# --- Order ---------------------------------------------------------------------------------


def test_two_qualifying_requests_come_back_oldest_issued_first(world: World) -> None:
    world.issue(slug="zeta", at=100.0)
    world.issue(slug="alpha", at=200.0)
    world.put(MARKED)

    assert [h.outstanding.slug for h in world.held()] == ["zeta", "alpha"]


def test_requests_issued_together_break_the_tie_by_task_slug(world: World) -> None:
    world.issue(slug="beta", at=100.0)
    world.issue(slug="alpha", at=100.0)
    world.put(MARKED)

    assert [h.outstanding.slug for h in world.held()] == ["alpha", "beta"]


# --- The command ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invocation",
    [
        Invocation("step-loop"),
        Invocation("python3 /x/scripts/step_loop.py", ("--repo-root", "/a b", "--base-ref", "m")),
    ],
)
def test_the_held_command_is_the_drivers_own_record_command(
    world: World, invocation: Invocation
) -> None:
    world.issue()
    world.put(MARKED)

    (held,) = world.held(invocation)

    assert held.command == invocation.command(
        "record", SLUG, "--request", REQUEST, "--agent-id", AGENT, "--marker", "complete"
    )


# --- Parity with `record` ------------------------------------------------------------------


@pytest.mark.parametrize("fixture", sorted(HELD_FIXTURES))
def test_every_held_agent_is_one_record_reads_as_ended(world: World, fixture: str) -> None:
    world.issue()
    world.put(HELD_FIXTURES[fixture])

    (held,) = world.held()

    assert record.sight(world.root, held.agent_id, MAX_TURNS).ended is True


def test_a_held_agent_stopped_by_the_log_is_one_record_reads_as_ended(world: World) -> None:
    world.issue()
    world.put(RUNNING)
    world.stopped.add(AGENT)

    (held,) = world.held()

    assert record.sight(world.root, held.agent_id, MAX_TURNS).ended is True


def test_a_running_agent_is_one_record_would_refuse_as_running(world: World) -> None:
    world.issue()
    world.put(RUNNING)

    assert (world.held(), record.sight(world.root, AGENT, MAX_TURNS).ended) == ((), False)


def test_the_agent_type_of_a_request_is_the_one_the_driver_spawns() -> None:
    plan = "# Plan\n\n### Step 1: Do it\n\n**Assignee**: implementer\n**Files**: `a.py`\n"  # id-citation-discipline:ignore (plan heading format)
    (step,) = parse_plan_steps(plan)
    keys = [RequestKey("1", 1, "implement"), RequestKey("1", 1, "review", round=1)]

    asked = {k.kind: spawn_request(SLUG, step, k, 3, "/w").agent_call.subagent_type for k in keys}

    assert {kind: probe._agent_type(k.id) for kind, k in zip(asked, keys, strict=True)} == asked
