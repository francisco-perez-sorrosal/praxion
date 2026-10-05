"""Tests for the file and transcript adapters of the step-loop driver
(``scripts/_step_loop_files.py``).

Writers run on real files in ``tmp_path``; the handoff composer is replaced by a stub that
returns text shaped like the real one, since what is under test is the rewrite-only-when-
section-2-moves decision, not the composer. The transcript tests build the harness's directory
layout (``projects/<p>/<session>/subagents/agent-<id>.jsonl`` with a ``.meta.json``) under a
temporary config directory.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_files as files  # noqa: E402
from _agent_transcript import Missing, Read, Unreadable, read_transcript  # noqa: E402
from _loop_fields import Attempt, OutstandingAttempt, latest_result, parse_attempts  # noqa: E402
from _step_loop_render import AgentCall  # noqa: E402
from compose_handoff import SECTION_HEADINGS  # noqa: E402
from iteration_ledger import IterationRecord, read_ledger  # noqa: E402

LABEL = files.STEP_LABEL
REQUEST = "s17-a1-implement"
OUTSTANDING = OutstandingAttempt(2, REQUEST)
WIP = f"""\
# WIP

## Progress

- [x] {LABEL}1: Take the baseline
  - Attempts: {LABEL}1 count=1
- [ ] {LABEL}17: Add the adapters
- [ ] {LABEL}18: Land the command
"""
GATE_BODY = [
    "Command: pytest -q",
    "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop",
]


def attempts_of(text: str, step: str) -> object:
    return parse_attempts(text).counts.get(f"{LABEL}{step}")


# --- The atomic primitive ---------------------------------------------------------------


def test_a_write_creates_the_file_and_leaves_no_temporary_beside_it(tmp_path: Path) -> None:
    target = tmp_path / "out.md"

    wrote = files.write_atomic(target, "text\n")

    assert (wrote, target.read_text(), sorted(p.name for p in tmp_path.iterdir())) == (
        True,
        "text\n",
        ["out.md"],
    )


def test_writing_what_the_file_already_holds_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("text\n")
    before = target.stat().st_mtime_ns

    wrote = files.write_atomic(target, "text\n")

    assert (wrote, target.stat().st_mtime_ns) == (False, before)


def test_a_rewrite_keeps_the_files_mode(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("old\n")
    target.chmod(0o640)

    files.write_atomic(target, "new\n")

    assert (target.read_text(), stat.S_IMODE(target.stat().st_mode)) == ("new\n", 0o640)


def test_a_failed_rename_leaves_the_original_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.md"
    target.write_text("old\n")

    def refuse(*_: object) -> None:
        raise OSError("disk says no")

    monkeypatch.setattr(files.os, "replace", refuse)
    with pytest.raises(OSError, match="disk says no"):
        files.write_atomic(target, "new\n")

    assert (target.read_text(), sorted(p.name for p in tmp_path.iterdir())) == ("old\n", ["out.md"])


# --- The Attempts: line -----------------------------------------------------------------


def test_a_new_line_goes_under_the_steps_checklist_line_indented_as_a_child() -> None:
    text = files.with_attempts_line(WIP, "17", OUTSTANDING)

    assert text.splitlines()[6:8] == [
        f"- [ ] {LABEL}17: Add the adapters",
        f"  - Attempts: {LABEL}17 count=2 request={REQUEST}",
    ]


def test_the_written_line_reads_back_as_the_attempt_that_was_written() -> None:
    text = files.with_attempts_line(WIP, "17", OUTSTANDING)

    assert (attempts_of(text, "17"), attempts_of(text, "1")) == (OUTSTANDING, Attempt(1))


def test_an_existing_line_is_replaced_in_place_with_its_indent_kept() -> None:
    first = files.with_attempts_line(WIP, "17", OUTSTANDING)

    second = files.with_attempts_line(first, "17", Attempt(2, request=REQUEST))

    assert second.splitlines()[7] == f"  - Attempts: {LABEL}17 count=2 request={REQUEST}"
    assert len(second.splitlines()) == len(first.splitlines())


def test_a_stale_duplicate_line_for_the_step_is_dropped() -> None:
    doubled = WIP.replace(
        f"- [ ] {LABEL}17: Add the adapters\n",
        f"- [ ] {LABEL}17: Add the adapters\n"
        f"  - Attempts: {LABEL}17 count=1\n  - Attempts: {LABEL}17 count=2\n",
    )

    text = files.with_attempts_line(doubled, "17", Attempt(3))

    assert [line for line in text.splitlines() if f"{LABEL}17 count" in line] == [
        f"  - Attempts: {LABEL}17 count=3"
    ]


def test_writing_the_same_attempt_twice_changes_nothing_the_second_time() -> None:
    once = files.with_attempts_line(WIP, "17", OUTSTANDING)

    assert files.with_attempts_line(once, "17", OUTSTANDING) == once


@pytest.mark.parametrize(("other", "untouched"), [("1", "17"), ("17", "1")])
def test_a_step_id_never_matches_the_line_of_a_longer_or_shorter_id(
    other: str, untouched: str
) -> None:
    both = f"{WIP}\n  - Attempts: {LABEL}17 count=4\n"

    text = files.with_attempts_line(both, other, Attempt(9))

    assert attempts_of(text, untouched) == attempts_of(both, untouched)


def test_none_removes_the_steps_line_and_only_that() -> None:
    text = files.with_attempts_line(WIP, "1", None)

    assert text == WIP.replace(f"  - Attempts: {LABEL}1 count=1\n", "")


def test_a_step_without_a_checklist_line_gets_its_line_at_the_end_before_the_final_newline() -> (
    None
):
    text = files.with_attempts_line("# WIP\n\n- notes\n", "5", Attempt(1))

    assert text == f"# WIP\n\n- notes\n- Attempts: {LABEL}5 count=1\n"


def test_a_line_inside_a_code_fence_is_not_the_steps_line() -> None:
    fenced = f"```\n- Attempts: {LABEL}17 count=1\n```\n{WIP}"

    text = files.with_attempts_line(fenced, "17", Attempt(2))

    assert text.startswith(f"```\n- Attempts: {LABEL}17 count=1\n```\n")
    assert attempts_of(text, "17") == Attempt(2)


def test_the_file_form_reports_whether_it_wrote(tmp_path: Path) -> None:
    wip = tmp_path / "WIP.md"
    wip.write_text(WIP)

    first = files.set_attempts_line(wip, "17", OUTSTANDING)
    second = files.set_attempts_line(wip, "17", OUTSTANDING)
    withdrawn = files.set_attempts_line(wip, "17", None)

    assert (first, second, withdrawn, wip.read_text()) == (True, False, True, WIP)


# --- The gate block ----------------------------------------------------------------------


def results_with(*blocks: list[str]) -> str:
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


def test_a_gate_block_is_appended_under_its_heading_and_ends_on_the_deciding_line(
    tmp_path: Path,
) -> None:
    results = tmp_path / "TEST_RESULTS.md"
    results.write_text(results_with([f"## {LABEL}16 — Adapters", "Result: pass=1 fail=0 skip=0"]))

    files.write_gate_block(results, "17", REQUEST, GATE_BODY)

    heading = f"## {LABEL}17 — step-loop gate, {REQUEST}"
    assert files.gate_heading("17", REQUEST) == heading
    assert results.read_text().endswith(f"{heading}\n\n{GATE_BODY[0]}\n{GATE_BODY[1]}\n")


def test_the_appended_block_is_read_as_the_steps_latest_result() -> None:
    results = results_with([f"## {LABEL}17 — Earlier", "Result: pass=1 fail=1 skip=0"])
    block = [files.gate_heading("17", REQUEST), "", *GATE_BODY]

    text = files._with_block(results, block)

    assert latest_result(f"{LABEL}17", text)[1] == GATE_BODY[1]


def test_the_same_request_replaces_its_block_and_leaves_its_neighbours() -> None:
    other = [f"## {LABEL}18 — Next", "Result: none — not run"]
    block = [files.gate_heading("17", REQUEST), "", "Result: pass=1 fail=1 skip=0 pending=0"]
    first = files._with_block(results_with(block, other), block)
    replacement = [*block[:2], *GATE_BODY]

    second = files._with_block(first, replacement)

    assert second == results_with(replacement, other)


def test_writing_a_gate_block_twice_writes_nothing_the_second_time(tmp_path: Path) -> None:
    results = tmp_path / "TEST_RESULTS.md"

    first = files.write_gate_block(results, "17", REQUEST, GATE_BODY)
    second = files.write_gate_block(results, "17", REQUEST, GATE_BODY)

    assert (first, second) == (True, False)


@pytest.mark.parametrize(
    "body",
    [[], ["Command: x"], ["Result: pass=1 fail=0", "stray tail"], [f"## {LABEL}3", "Result: none"]],
)
def test_a_body_that_does_not_end_on_a_result_or_holds_a_heading_is_refused(
    tmp_path: Path, body: list[str]
) -> None:
    with pytest.raises(ValueError, match="gate block"):
        files.write_gate_block(tmp_path / "TEST_RESULTS.md", "17", REQUEST, body)


# --- The prompt and the snapshot ---------------------------------------------------------


def test_the_prompt_and_the_snapshot_sit_flat_beside_the_task_documents(tmp_path: Path) -> None:
    prompt = files.write_prompt(tmp_path, REQUEST, "prompt\n")
    snapshot = files.write_tree_snapshot(tmp_path, REQUEST, "# staged\n")

    assert (prompt, snapshot) == (
        tmp_path / f"PROMPT_{REQUEST}.md",
        tmp_path / f"TREE_SNAPSHOT_{REQUEST}.patch",
    )
    assert (prompt.read_text(), snapshot.read_text()) == ("prompt\n", "# staged\n")


def test_a_prompt_rewritten_with_the_same_text_keeps_its_write_time(tmp_path: Path) -> None:
    path = files.write_prompt(tmp_path, REQUEST, "prompt\n")
    os.utime(path, (1_000, 1_000))

    files.write_prompt(tmp_path, REQUEST, "prompt\n")

    assert path.stat().st_mtime == 1_000


@pytest.mark.parametrize("request_id", ["../escape", "Upper", "a b", "", "-lead"])
def test_a_request_id_that_is_not_path_safe_is_refused(tmp_path: Path, request_id: str) -> None:
    with pytest.raises(ValueError, match="request id"):
        files.write_prompt(tmp_path, request_id, "x")


def test_the_snapshots_beside_the_task_are_listed_by_the_request_they_belong_to(
    tmp_path: Path,
) -> None:
    files.write_tree_snapshot(tmp_path, "s2-a1-implement", "# b\n")
    files.write_tree_snapshot(tmp_path, REQUEST, "# a\n")
    files.write_prompt(tmp_path, REQUEST, "prompt\n")
    (tmp_path / "TREE_SNAPSHOT_Not A Request.patch").write_text("x", encoding="utf-8")
    (tmp_path / "TREE_SNAPSHOT_notes.txt").write_text("x", encoding="utf-8")

    assert files.snapshot_requests(tmp_path) == (REQUEST, "s2-a1-implement")


def test_a_deleted_snapshot_is_no_longer_listed_and_a_task_without_any_lists_none(
    tmp_path: Path,
) -> None:
    path = files.write_tree_snapshot(tmp_path, REQUEST, "# a\n")
    path.unlink()

    assert files.snapshot_requests(tmp_path) == ()


# --- The ledger --------------------------------------------------------------------------


def a_record(**overrides: object) -> IterationRecord:
    fields = {
        "step": f"{LABEL}17",
        "attempt": 1,
        "agent_id": "a1b2c3",
        "verdict": "verified-complete",
        "decided_by": "check",
        "test_result": "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop",
        "commit": "abc1234",
        "stop_reason": "completed",
        "request": REQUEST,
        "step_digest": "0123456789ab",
        "turns": 41,
        "max_turns": 100,
    }
    return IterationRecord(**{**fields, **overrides})


def test_a_record_appends_once_and_its_replay_appends_nothing(tmp_path: Path) -> None:
    first = files.append_ledger_record(tmp_path, a_record())
    replay = files.append_ledger_record(tmp_path, a_record(agent_id="other"))

    reading = read_ledger(tmp_path)
    assert (first, replay, len(reading.records), reading.findings) == (True, False, 1, ())


def test_a_second_request_appends_beside_the_first(tmp_path: Path) -> None:
    files.append_ledger_record(tmp_path, a_record())
    files.append_ledger_record(tmp_path, a_record(request="s17-a2-implement", attempt=2))

    assert read_ledger(tmp_path).requests == {REQUEST, "s17-a2-implement"}


def test_a_record_without_a_request_is_refused(tmp_path: Path) -> None:
    bare = IterationRecord(**{**a_record().__dict__, "request": None, "step_digest": None,
                              "turns": None, "max_turns": None})  # fmt: skip

    with pytest.raises(ValueError, match="names its request"):
        files.append_ledger_record(tmp_path, bare)


# --- The handoff -------------------------------------------------------------------------


def handoff_text(next_action: str, stamp: str = "2026-10-05T10:00:00Z") -> str:
    sections = [f"## {heading}\n\nbody\n" for heading in SECTION_HEADINGS]
    sections[2] = f"## {SECTION_HEADINGS[2]}\n\n{next_action}\n"
    return f"# Handoff\n\ncomposed: {stamp}\n\n" + "\n".join(sections)


@pytest.fixture
def composer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A stub composer: what it is called with, and the text it answers."""
    state: dict = {"calls": [], "next_action": "stop one", "stamp": "2026-10-05T10:00:00Z"}

    def stub(slug: str, repo_root: Path, **kwargs: object) -> dict:
        state["calls"].append((slug, repo_root, kwargs))
        text = handoff_text(kwargs["next_action"], state["stamp"])
        return {"text": text, "path": tmp_path / "HANDOFF.md"}

    monkeypatch.setattr(files, "write_handoff", stub)
    return state


def test_the_handoff_is_composed_mid_phase_with_the_gate_overridden_and_nothing_written_by_it(
    tmp_path: Path, composer: dict
) -> None:
    files.write_stop_handoff("slug", tmp_path, "stop one")

    assert composer["calls"] == [
        (
            "slug",
            tmp_path,
            {
                "boundary": None,
                "force": True,
                "base_ref": None,
                "next_action": "stop one",
                "dry_run": True,
            },
        )
    ]


def test_the_handoff_carries_the_base_ref_it_is_given(tmp_path: Path, composer: dict) -> None:
    files.write_stop_handoff("slug", tmp_path, "stop one", base_ref="cb14bddc")

    assert composer["calls"][0][2]["base_ref"] == "cb14bddc"


def test_a_first_handoff_is_written(tmp_path: Path, composer: dict) -> None:
    wrote = files.write_stop_handoff("slug", tmp_path, "stop one")

    assert (wrote, (tmp_path / "HANDOFF.md").read_text()) == (True, handoff_text("stop one"))


def test_a_repeated_stop_leaves_the_file_and_its_timestamp_alone(
    tmp_path: Path, composer: dict
) -> None:
    files.write_stop_handoff("slug", tmp_path, "stop one")
    composer["stamp"] = "2026-10-05T11:30:00Z"

    wrote = files.write_stop_handoff("slug", tmp_path, "stop one")

    assert (wrote, "10:00:00Z" in (tmp_path / "HANDOFF.md").read_text()) == (False, True)


def test_a_stop_that_changes_section_two_rewrites_the_file(tmp_path: Path, composer: dict) -> None:
    files.write_stop_handoff("slug", tmp_path, "stop one")

    wrote = files.write_stop_handoff("slug", tmp_path, "stop two")

    assert (wrote, "stop two" in (tmp_path / "HANDOFF.md").read_text()) == (True, True)


def test_a_change_outside_section_two_does_not_rewrite_the_file(
    tmp_path: Path, composer: dict
) -> None:
    files.write_stop_handoff("slug", tmp_path, "stop one")
    path = tmp_path / "HANDOFF.md"
    path.write_text(path.read_text().replace("body", "edited by hand", 1))

    wrote = files.write_stop_handoff("slug", tmp_path, "stop one")

    assert (wrote, "edited by hand" in path.read_text()) == (False, True)


# --- The agent's transcript --------------------------------------------------------------

SESSION, AGENT = "sess-1", "a1b2c3"
SPAWN_PROMPT = f"Task slug: s\nSpawn request: {REQUEST}\nRead PROMPT_{REQUEST}.md first."


def user(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def assistant(request_id: str, *blocks: dict) -> dict:
    return {"type": "assistant", "requestId": request_id, "message": {"content": list(blocks)}}


def say(text: str) -> dict:
    return {"type": "text", "text": text}


def call(name: str) -> dict:
    return {"type": "tool_use", "name": name, "input": {}}


def put_transcript(
    config: Path, agent: str, records: list[dict], *, project: str = "p", meta: object = None
) -> Path:
    subagents = config / "projects" / project / SESSION / "subagents"
    subagents.mkdir(parents=True, exist_ok=True)
    path = subagents / f"agent-{agent}.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    if meta is not None:
        path.with_suffix(".meta.json").write_text(json.dumps(meta))
    return path


FINISHED = [
    user(SPAWN_PROMPT),
    assistant("r1", call("Edit")),
    assistant("r2", say("done\n[COMPLETE]")),
]
RUNNING = [user(SPAWN_PROMPT), assistant("r1", say("working"), call("Bash"))]


def test_a_transcript_is_found_by_agent_id_under_the_config_directory(tmp_path: Path) -> None:
    written = put_transcript(tmp_path, AGENT, FINISHED)

    path, reading = files.read_agent(AGENT, config=tmp_path)

    assert (path, isinstance(reading, Read), reading.requests) == (written, True, 2)


def test_an_unknown_agent_reads_as_a_missing_transcript(tmp_path: Path) -> None:
    put_transcript(tmp_path, AGENT, FINISHED)

    assert files.read_agent("nobody", config=tmp_path) == (None, Missing())


@pytest.mark.parametrize(
    ("records", "max_turns", "stopped", "expected"),
    [
        (FINISHED, 100, False, files.EndEvidence("done\n[COMPLETE]", 2, 100, False)),
        (RUNNING, 100, False, files.EndEvidence(None, 1, 100, False)),
        (RUNNING, 100, True, files.EndEvidence(None, 1, 100, True)),
        (RUNNING, None, False, files.EndEvidence(None, 1, None, False)),
    ],
)
def test_end_evidence_carries_the_last_text_the_request_count_and_the_stop(
    tmp_path: Path, records: list[dict], max_turns: int | None, stopped: bool, expected: object
) -> None:
    put_transcript(tmp_path, AGENT, records)
    _, reading = files.read_agent(AGENT, config=tmp_path)

    assert files.end_evidence(reading, max_turns, stopped) == expected


@pytest.mark.parametrize("reading", [Missing(), Unreadable(lines_ok=3, last_ok=False)])
def test_end_evidence_of_an_unreadable_or_missing_transcript_holds_nothing_of_it(
    reading: object,
) -> None:
    assert files.end_evidence(reading, 100, True) == files.EndEvidence(None, None, 100, True)


def test_a_handback_call_reads_as_the_final_text(tmp_path: Path) -> None:
    handback = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": "[BLOCKED]"}}
    put_transcript(tmp_path, AGENT, [user(SPAWN_PROMPT), assistant("r1", handback)])
    _, reading = files.read_agent(AGENT, config=tmp_path)

    assert files.end_evidence(reading, 100, False).final_text == "[BLOCKED]"


@pytest.mark.parametrize(
    ("asked", "prompt", "expected"),
    [
        (REQUEST, SPAWN_PROMPT, True),
        (REQUEST, f"hook preamble\n\n{SPAWN_PROMPT}", True),
        ("s17-a1-review-r1", "Spawn request: s17-a1-review-r10\n", False),
        ("s17-a1-review-r10", "Spawn request: s17-a1-review-r10\n", True),
        ("s17-a1", "Spawn request: s17-a1-implement\n", False),
        (REQUEST, "no request named here", False),
    ],
)
def test_a_transcript_names_exactly_the_request_it_was_spawned_for(
    tmp_path: Path, asked: str, prompt: str, expected: bool
) -> None:
    path = put_transcript(tmp_path, AGENT, [user(prompt), assistant("r1", say("x"))])

    assert files.names_request(read_transcript(path), asked) is expected


def test_an_unreadable_transcript_names_no_request() -> None:
    assert files.names_request(Unreadable(0, False), REQUEST) is False


CALL = AgentCall("praxion:implementer", "sonnet", f"{LABEL}17 attempt 1/2", "p")
GOOD_META = {"agentType": "praxion:implementer", "model": "sonnet", "toolUseId": "t"}


def test_a_meta_file_that_matches_the_request_warns_of_nothing(tmp_path: Path) -> None:
    path = put_transcript(tmp_path, AGENT, FINISHED, meta=GOOD_META)

    assert files.meta_warnings(path, CALL) == ()


@pytest.mark.parametrize(
    ("meta", "key", "asked"),
    [
        ({**GOOD_META, "agentType": "praxion:verifier"}, "agentType", "praxion:implementer"),
        ({**GOOD_META, "model": "opus"}, "model", "sonnet"),
    ],
)
def test_a_meta_file_that_differs_from_the_request_warns_naming_the_field(
    tmp_path: Path, meta: dict, key: str, asked: str
) -> None:
    path = put_transcript(tmp_path, AGENT, FINISHED, meta=meta)

    (warning,) = files.meta_warnings(path, CALL)

    assert warning.startswith(files.REQUEST_FIDELITY)
    assert (key in warning, asked in warning) == (True, True)


def test_a_meta_file_missing_a_key_warns_for_that_key(tmp_path: Path) -> None:
    path = put_transcript(tmp_path, AGENT, FINISHED, meta={"model": "sonnet"})

    (warning,) = files.meta_warnings(path, CALL)

    assert ("agentType" in warning, "None" in warning) == (True, True)


@pytest.mark.parametrize("meta_text", ["not json", "[1, 2]"])
def test_a_malformed_meta_file_warns_it_cannot_be_read(tmp_path: Path, meta_text: str) -> None:
    path = put_transcript(tmp_path, AGENT, FINISHED)
    path.with_suffix(".meta.json").write_text(meta_text)

    assert files.meta_warnings(path, CALL) == (files.META_UNREADABLE,)


def test_an_absent_meta_file_warns_it_cannot_be_read(tmp_path: Path) -> None:
    path = put_transcript(tmp_path, AGENT, FINISHED)

    assert files.meta_warnings(path, CALL) == (files.META_UNREADABLE,)


def test_no_transcript_means_no_fidelity_warning() -> None:
    assert files.meta_warnings(None, CALL) == ()


def test_the_agent_stop_row_is_found_by_agent_id_in_the_session_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {"event_type": "agent_start", "agent_id": AGENT},
        {"event_type": "agent_stop", "agent_id": "someone-else"},
    ]
    monkeypatch.setattr(files, "session_wal_rows", lambda root: rows)
    before = files.agent_stopped(tmp_path, AGENT)
    rows.append({"event_type": "agent_stop", "agent_id": AGENT})

    assert (before, files.agent_stopped(tmp_path, AGENT)) == (False, True)


def test_the_search_finds_the_transcript_that_names_the_request(tmp_path: Path) -> None:
    put_transcript(
        tmp_path, "other", [user("Spawn request: s9-a1-implement"), assistant("r1", say("x"))]
    )
    wanted = put_transcript(tmp_path, AGENT, FINISHED, project="q")

    assert files.find_request_transcript(REQUEST, 0.0, tmp_path) == wanted


def test_the_search_ignores_transcripts_older_than_the_write_ahead(tmp_path: Path) -> None:
    old = put_transcript(tmp_path, AGENT, FINISHED)
    os.utime(old, (1_000, 1_000))

    assert files.find_request_transcript(REQUEST, 2_000.0, tmp_path) is None


def test_the_search_reads_workflow_run_transcripts_too(tmp_path: Path) -> None:
    nested = tmp_path / "projects" / "p" / SESSION / "subagents" / "workflows" / "run1"
    nested.mkdir(parents=True)
    wanted = nested / f"agent-{AGENT}.jsonl"
    wanted.write_text(json.dumps(user(SPAWN_PROMPT)) + "\n")

    assert files.find_request_transcript(REQUEST, 0.0, tmp_path) == wanted


def test_the_search_finds_nothing_when_no_agent_started_on_the_request(tmp_path: Path) -> None:
    put_transcript(tmp_path, AGENT, [user("Spawn request: s9-a1-implement")])

    assert files.find_request_transcript(REQUEST, 0.0, tmp_path) is None


def test_the_search_under_a_config_directory_without_projects_finds_nothing(tmp_path: Path) -> None:
    assert files.find_request_transcript(REQUEST, 0.0, tmp_path / "empty") is None
