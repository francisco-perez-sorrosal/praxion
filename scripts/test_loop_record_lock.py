"""Tests for the record lock where the driver and the Stop guard's probe read it.

A `record` call holds `gate/<request>/record.lock` for its whole run (`step_loop.run_record`), a
second `record` of the request meanwhile is refused as `record-running` and writes nothing, and
the probe (`_step_loop_outstanding.judge_outstanding`) reads a held lock as a record in flight,
never as an agent that ended unrecorded. Another holder is a descriptor of its own in this
process: `flock` locks belong to an open file description, so it contends as a process would.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_outstanding as probe  # noqa: E402
import _step_loop_record as rec  # noqa: E402
import _step_loop_recording as recording  # noqa: E402
import step_loop  # noqa: E402
from _step_loop_render import Invocation  # noqa: E402

SLUG = "demo"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
STEP = "Step "  # split from its number, as the plan grammar spells it
PLAN = f"# Plan\n\n## Steps\n\n### {STEP}1: Do it\n\n**Assignee**: implementer\n{CHECK}\n"
WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n"
HOLDER_PID = 4242
AGENT = "a1b2c3"
MAX_TURNS = 30


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_DIR / "step_loop.py")])


@pytest.fixture
def root(tmp_path: Path) -> Path:
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(PLAN, encoding="utf-8")
    (task / "WIP.md").write_text(WIP, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty"]
        + ["-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def call(root: Path, verb: str, *more: str):
    return step_loop.execute([verb, SLUG, *more, "--repo-root", str(root), "--base-ref", "HEAD"])


def issued(root: Path) -> str:
    return call(root, "next").doc["request"]["id"]


def task_dir(root: Path) -> Path:
    return root / ".ai-work" / SLUG


def run_dir(root: Path, request: str) -> Path:
    return task_dir(root) / "gate" / request


def task_files(root: Path) -> dict[str, bytes]:
    """Every file of the task bar the lock itself, by content."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(task_dir(root).rglob("*"))
        if path.is_file() and path.name != recording.LOCK_FILE
    }


@contextmanager
def held_elsewhere(directory: Path) -> Iterator[None]:
    """The lock held as another `record` of the request holds it, naming its pid."""
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory / recording.LOCK_FILE, os.O_RDWR | os.O_CREAT)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(
        descriptor, json.dumps({"pid": HOLDER_PID, "started": "2026-11-16T10:00:00Z"}).encode()
    )
    try:
        yield
    finally:
        os.close(descriptor)


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(recording, "WAIT_SECONDS", 0.0)


# --- The driver --------------------------------------------------------------------------------


def test_a_second_record_while_the_first_holds_the_lock_exits_four_and_writes_nothing(
    root, no_wait
):
    request = issued(root)
    before = task_files(root)

    with held_elsewhere(run_dir(root, request)):
        refused = call(
            root, "record", "--request", request, "--agent-id", AGENT, "--marker", "complete"
        )

    assert (refused.exit, refused.doc["error"]["code"]) == (4, "record-running")
    assert request in refused.doc["error"]["message"]
    assert f"process {HOLDER_PID}" in refused.doc["error"]["message"]
    assert task_files(root) == before


def test_a_withdrawal_while_a_record_holds_the_lock_is_refused_too(root, no_wait):
    request = issued(root)

    with held_elsewhere(run_dir(root, request)):
        refused = call(root, "record", "--request", request, "--not-started", "never ran")

    assert (refused.exit, refused.doc["error"]["code"]) == (4, "record-running")


def test_a_record_holds_the_lock_while_it_reads_the_task_and_takes_the_return_back(
    root, monkeypatch
):
    request = issued(root)
    seen: list[tuple[str, bool]] = []
    reading, taking = step_loop.read_task, rec.take_back

    def read_task(args):
        seen.append(("read", recording.record_in_flight(run_dir(root, request))))
        return reading(args)

    def take_back(*args, **kwargs):
        seen.append(("take", recording.record_in_flight(run_dir(root, request))))
        return taking(*args, **kwargs)

    monkeypatch.setattr(step_loop, "read_task", read_task)
    monkeypatch.setattr(rec, "take_back", take_back)

    withdrawn = call(root, "record", "--request", request, "--not-started", "never ran")

    assert withdrawn.doc["outcome"] == "withdrawn", withdrawn.doc
    assert seen == [("read", False), ("read", True), ("take", True)]
    assert recording.record_in_flight(run_dir(root, request)) is False


def test_a_record_of_an_unknown_request_is_refused_before_any_lock_is_taken(root):
    issued(root)

    refused = call(root, "record", "--request", "s9-a1-implement", "--not-started", "never ran")

    assert refused.doc["error"]["code"] == "request-not-pending"
    assert not (task_dir(root) / "gate").exists()


def test_the_error_vocabulary_names_record_running_beside_gate_running():
    assert step_loop.__doc__ is not None
    assert "gate-running, record-running" in " ".join(step_loop.__doc__.split())


# --- The Stop guard's probe ----------------------------------------------------------------------


@pytest.fixture
def ended_agent(root, monkeypatch) -> tuple[Path, str]:
    """An issued request whose agent of this session ended with a marker; the subagents dir."""
    agents = root / "agents"
    agents.mkdir()
    for name in ("implementer", "verifier"):
        (agents / f"{name}.md").write_text(f"---\nname: {name}\nmaxTurns: {MAX_TURNS}\n---\n")
    monkeypatch.setattr(rec, "AGENTS_DIR", agents)
    request = issued(root)
    subagents = root / "session" / "subagents"
    subagents.mkdir(parents=True)
    prompt = f"Task slug: {SLUG}\nSpawn request: {request}\nRead PROMPT_{request}.md first."
    lines = [
        {"type": "user", "message": {"content": prompt}},
        {
            "type": "assistant",
            "requestId": "r1",
            "message": {"content": [{"type": "text", "text": "done\n[COMPLETE]"}]},
        },
    ]
    transcript = subagents / f"agent-{AGENT}.jsonl"
    transcript.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return subagents, request


def verdicts(root: Path, subagents: Path) -> list:
    judged = probe.judge_outstanding(root / ".ai-work", subagents, Invocation("step_loop.py"))
    return [verdict for _, verdict in judged]


def test_an_ended_agent_whose_record_holds_the_lock_is_in_flight_not_held(root, ended_agent):
    subagents, request = ended_agent

    with held_elsewhere(run_dir(root, request)):
        judged = verdicts(root, subagents)

    assert judged == [probe.NotHeld("record-running")]


def test_an_ended_agent_whose_record_lock_is_free_is_held_as_before(root, ended_agent):
    subagents, request = ended_agent
    with held_elsewhere(run_dir(root, request)):  # a record that ended leaves its lock file behind
        pass

    (judged,) = verdicts(root, subagents)

    assert isinstance(judged, probe.Held), judged
    assert request in judged.command


def test_the_probe_creates_no_lock_file_for_a_request_never_recorded(root, ended_agent):
    subagents, request = ended_agent

    verdicts(root, subagents)

    assert not run_dir(root, request).exists()
