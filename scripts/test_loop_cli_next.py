"""Tests for the step-loop command's `next` and `status` verbs and its envelope layer
(``scripts/step_loop.py``, ``scripts/_step_loop_cli.py``).

Every case runs the real command over a small checkout built in ``tmp_path``: the plan and
progress file are text, the ledger is the real one, and the reconciler, the prompt writer and the
handoff composer are the real ones. The one case that starts the script through ``PATH`` runs a
subprocess, because what it pins is how the interpreter reports its own start.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_cli as cli  # noqa: E402
import step_loop  # noqa: E402
from iteration_ledger import IterationRecord, append_record  # noqa: E402

STEP = "Step "
SLUG = "demo"
SCRIPT = SCRIPT_DIR / "step_loop.py"
SELF_HOST = "python3 scripts/step_loop.py"
FIXTURES = SCRIPT_DIR / "fixtures"
RELAY = ("--agent-id", "a1", "--marker", "complete")
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"


def plan_block(number, *lines, heading="", assignee="implementer"):
    body = "".join(f"{line}\n" for line in lines)
    return f"### {STEP}{number}: Do it{heading}\n\n**Assignee**: {assignee}\n{body}\n"


PLAN = "# Plan\n\n## Steps\n\n" + plan_block(1, "**Files**: `src/one.py`", CHECK)
TWO_STEP_PLAN = PLAN + plan_block(2, "**Files**: `src/two.py`", CHECK, heading=" [depends-on: 1]")
STUCK_PLAN = "# Plan\n\n## Steps\n\n" + plan_block(
    1, "**Files**: `src/one.py`", CHECK, heading=" [depends-on: 9]"
)
WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Do it\n"


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    """The command is run by explicit path, so its directory is not a `PATH` entry."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])


def build(tmp_path, plan=PLAN, wip=WIP, ledger=()):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task / "WIP.md").write_text(wip, encoding="utf-8")
    for record in ledger:
        append_record(task, record)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty"]
        + ["-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def where(root):
    return ["--repo-root", str(root), "--base-ref", "HEAD"]


def call(root, verb, *more):
    return step_loop.execute([verb, SLUG, *more, *where(root)])


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def attempts_line(root):
    lines = (root / ".ai-work" / SLUG / "WIP.md").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if "Attempts:" in line]


# --- The invocation the caller used -----------------------------------------------------------


@pytest.mark.parametrize(
    ("script_dir", "path_entries", "expected"),
    [
        ("bin", ["bin", "other"], "step_loop.py"),
        ("bin", ["other", "bin/"], "step_loop.py"),
        ("bin", ["other"], SELF_HOST),
        ("bin", [""], SELF_HOST),
    ],
    ids=["a-path-entry", "a-path-entry-with-a-trailing-slash", "no-path-entry", "empty-entry"],
)
def test_the_invocation_follows_whether_the_scripts_directory_is_a_path_entry(
    tmp_path, script_dir, path_entries, expected
):
    path = os.pathsep.join(str(tmp_path / entry) if entry else "" for entry in path_entries)

    assert cli.invocation(str(tmp_path / script_dir / "step_loop.py"), path) == expected


def test_a_script_started_through_path_reports_the_short_form(tmp_path):
    root = build(tmp_path / "checkout")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "step_loop.py").symlink_to(SCRIPT)
    tools = {str(Path(shutil.which(name)).parent) for name in ("python3", "git")}
    path = os.pathsep.join([str(bin_dir), *sorted(tools)])

    ran = subprocess.run(
        ["step_loop.py", "next", SLUG, *where(root)],
        cwd=root,
        env={**os.environ, "PATH": path},
        capture_output=True,
        text=True,
    )

    assert json.loads(ran.stdout)["then"].startswith(f"step_loop.py record {SLUG} --request ")


def test_a_script_started_by_explicit_path_reports_the_checkout_form(tmp_path):
    root = build(tmp_path)

    doc = call(root, "next").doc

    assert doc["then"].startswith(f"{SELF_HOST} record {SLUG} --request s1-a1-implement ")


# --- The envelope, one constructor per outcome ------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "code", "expected"),
    [
        ("spawn", None, 0),
        ("complete", None, 0),
        ("needs-human", None, 2),
        ("budget-exhausted", None, 3),
        ("error", "usage", 4),
        ("error", "agent-running", 4),
        ("error", "internal", 1),
    ],
)
def test_the_exit_code_is_a_total_function_of_the_outcome_and_error_code(outcome, code, expected):
    doc = {"outcome": outcome, "error": {"code": code}}

    assert cli.exit_code(doc) == expected


def test_a_spawn_carries_a_request_and_a_then_and_nothing_of_the_other_outcomes(tmp_path):
    doc = call(build(tmp_path), "next").doc

    assert sorted(doc) == ["iterations", "outcome", "request", "schema", "slug", "then", "warnings"]
    assert doc["iterations"] == {"used": 0, "budget": 2}


def test_a_stop_carries_a_stop_object_naming_the_resume_command_and_the_handoff(tmp_path):
    root = build(tmp_path, STUCK_PLAN)

    reply = call(root, "next")

    stop = reply.doc["stop"]
    assert (reply.exit, reply.doc["outcome"], stop["cause"]) == (
        2,
        "needs-human",
        "dependency-defect",
    )
    assert sorted(reply.doc) == ["iterations", "outcome", "schema", "slug", "stop", "warnings"]
    assert stop["resume"] == f"{SELF_HOST} next {SLUG}"
    assert Path(stop["handoff"]).resolve() == (root / ".ai-work" / SLUG / "HANDOFF.md").resolve()
    assert reply.lines[0].startswith("step_loop: stopped")


def test_a_complete_plan_carries_neither_a_request_nor_a_stop(tmp_path):
    done = WIP.replace("- [ ]", "- [x]")
    root = build(
        tmp_path,
        "# Plan\n\n## Steps\n\n" + plan_block(1, "**Files**: none", assignee="orchestrator"),
        done,
    )

    reply = call(root, "next")

    assert (reply.exit, sorted(reply.doc)) == (
        0,
        ["iterations", "outcome", "schema", "slug", "warnings"],
    )
    assert reply.lines == ("step_loop: complete — 0 of 0 driven steps verified · iterations 0/0",)


@pytest.mark.parametrize(
    "argv",
    [
        ["gate", SLUG],
        ["next", SLUG, "--json"],
        ["record", SLUG, "--request", "s1-a1-implement"],
        ["record", SLUG, "--request", "r", "--agent-id", "a", "--marker", "none", "--not-started", "x"],
        ["record", SLUG, "--request", "r", "--agent-id", "a", "--marker", "[COMPLETE]"],
        ["record", SLUG, "--request", "r", "--agent-id", "a"],
        ["record", SLUG, "--request", "r", "--not-started", " "],
        [],
    ],
    ids=["unknown-verb", "json-on-next", "no-variant", "both-variants", "bracketed-marker",
         "agent-without-marker", "blank-reason", "no-verb"],
)  # fmt: skip
def test_a_usage_error_is_one_envelope_with_exit_four_and_no_iterations(argv):
    reply = step_loop.execute(argv)

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "usage")
    assert "iterations" not in reply.doc
    assert reply.lines[0].startswith("step_loop: error: ")


def test_a_missing_plan_names_the_document_and_reports_no_iterations(tmp_path):
    root = build(tmp_path)
    (root / ".ai-work" / SLUG / "IMPLEMENTATION_PLAN.md").unlink()

    reply = call(root, "next")

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "missing-artifact")
    assert "IMPLEMENTATION_PLAN.md" in reply.doc["error"]["message"]
    assert "iterations" not in reply.doc


# --- next -----------------------------------------------------------------------------------


def test_a_new_request_is_counted_in_the_progress_file_and_its_prompt_written_first(tmp_path):
    root = build(tmp_path)

    doc = call(root, "next").doc

    request = doc["request"]
    assert request["id"] == "s1-a1-implement"
    assert request["reissued"] is False
    assert (
        Path(request["prompt_path"])
        .read_text(encoding="utf-8")
        .startswith(f"Task slug: {SLUG}\nSpawn request: s1-a1-implement\n")
    )
    assert attempts_line(root) == [f"- Attempts: {STEP}1 count=1 request=s1-a1-implement"]


def test_asking_twice_reissues_the_request_and_changes_no_byte(tmp_path):
    root = build(tmp_path)
    first = call(root, "next")
    written = snapshot(root)

    second = call(root, "next")

    assert second.doc["request"] == {**first.doc["request"], "reissued": True}
    assert snapshot(root) == written
    assert second.lines == (
        f"step_loop: {STEP}1 attempt 1/2 is still pending (s1-a1-implement); "
        "reissued, nothing written",
    )


def test_a_reissue_restores_a_prompt_file_that_has_gone(tmp_path):
    root = build(tmp_path)
    path = Path(call(root, "next").doc["request"]["prompt_path"])
    original = path.read_bytes()
    path.unlink()

    call(root, "next")

    assert path.read_bytes() == original


def test_a_stop_repeats_byte_for_byte_and_rewrites_the_handoff_only_when_it_changes(tmp_path):
    root = build(tmp_path, STUCK_PLAN)
    first = call(root, "next")
    handoff = root / ".ai-work" / SLUG / "HANDOFF.md"
    written = snapshot(root)

    second = call(root, "next")

    assert second.doc == first.doc
    assert snapshot(root) == written
    assert f"step_loop.py next {SLUG}" in handoff.read_text(encoding="utf-8")


def test_a_fresh_series_after_a_plan_revision_restarts_its_count_at_one(tmp_path):
    spent = [
        IterationRecord(
            step=f"{STEP}1",
            attempt=n,
            agent_id=f"agent-{n}",
            verdict="mismatch",
            decided_by="check",
            test_result="Result: none",
            commit=None,
            stop_reason="completed",
            request=f"s1-a{n}-implement",
            step_digest="0" * 12,
        )
        for n in (1, 2)
    ]
    wip = WIP.replace(
        f"- [ ] {STEP}1: Do it\n", f"- [ ] {STEP}1: Do it\n  - Attempts: {STEP}1 count=2\n"
    )
    root = build(tmp_path, TWO_STEP_PLAN, wip, spent)

    doc = call(root, "next").doc

    assert doc["request"]["id"] == "s1-p2-a1-implement"
    assert attempts_line(root) == [f"- Attempts: {STEP}1 count=1 request=s1-p2-a1-implement"]


# --- status -----------------------------------------------------------------------------------


def test_status_writes_nothing_and_reports_the_pending_request(tmp_path):
    root = build(tmp_path, TWO_STEP_PLAN)
    pending = call(root, "next").doc["request"]["id"]
    written = snapshot(root)

    reply = call(root, "status", "--json")

    status = reply.doc
    assert (reply.exit, status["pending_request"], status["outcome"]) == (0, pending, "spawn")
    assert [(row["step"], row["verdict"], row["attempts"]) for row in status["steps"]] == [
        ("1", "in-flight", 1),
        ("2", "pending", 0),
    ]
    assert status["iterations"] == {"used": 0, "budget": 4}
    assert snapshot(root) == written


def test_status_without_json_prints_a_table_and_ends_on_the_next_action(tmp_path):
    root = build(tmp_path, TWO_STEP_PLAN)

    reply = call(root, "status")

    head, columns, *rows, last = reply.stdout.splitlines()
    assert head == f"{SLUG} · iterations 0/4"
    assert columns.split() == ["STEP", "ASSIGNEE", "VERDICT", "ATTEMPTS", "REVIEW", "COMMIT"]
    assert [row.split()[:2] for row in rows] == [["1", "implementer"], ["2", "implementer"]]
    assert last == f"next: run `{SELF_HOST} next {SLUG}` to start s1-a1-implement"


def test_status_exits_with_the_class_of_the_stop_it_reports_and_writes_nothing(tmp_path):
    root = build(tmp_path, STUCK_PLAN)
    written = snapshot(root)

    reply = call(root, "status", "--json")

    assert (reply.exit, reply.doc["stop"]["cause"]) == (2, "dependency-defect")
    assert snapshot(root) == written


# --- record, as far as this verb goes here ------------------------------------------------------


REFUSED = ("request-not-pending", 4)


def test_a_record_when_nothing_is_pending_is_refused_saying_none_is_pending(tmp_path):
    root = build(tmp_path)
    written = snapshot(root)

    reply = call(root, "record", "--request", "s1-a1-implement", *RELAY)

    assert (reply.doc["error"]["code"], reply.exit) == REFUSED
    assert "none is pending" in reply.doc["error"]["message"]
    assert snapshot(root) == written


def test_a_record_for_another_request_is_refused_naming_the_pending_one(tmp_path):
    root = build(tmp_path)
    call(root, "next")
    written = snapshot(root)

    reply = call(root, "record", "--request", "s9-a1-implement", *RELAY)

    assert (reply.doc["error"]["code"], reply.exit) == REFUSED
    assert "s1-a1-implement" in reply.doc["error"]["message"]
    assert snapshot(root) == written


# --- drive -----------------------------------------------------------------------------------


class ScriptedSpawner:
    def __init__(self, returned):
        self.returned, self.requests = returned, []

    def spawn(self, request):
        self.requests.append(request)
        return self.returned


def test_drive_hands_each_request_to_the_spawner_and_stops_on_a_non_spawn_outcome(tmp_path):
    root = build(tmp_path)
    spawner = ScriptedSpawner(step_loop.NotStarted("the call failed"))

    final = step_loop.drive(spawner, SLUG, where(root))

    assert [request["id"] for request in spawner.requests] == ["s1-a1-implement"]
    assert final["outcome"] != "spawn"


def test_drive_returns_a_stop_without_calling_the_spawner(tmp_path):
    spawner = ScriptedSpawner(step_loop.AgentRan("a1", "complete"))

    final = step_loop.drive(spawner, SLUG, where(build(tmp_path, STUCK_PLAN)))

    assert (final["outcome"], spawner.requests) == ("needs-human", [])


def test_the_fixtures_of_an_earlier_pipeline_read_as_a_stop_for_a_human(tmp_path):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    shutil.copy(FIXTURES / "step_schema_plan.md", task / "IMPLEMENTATION_PLAN.md")
    shutil.copy(FIXTURES / "step_schema_wip.md", task / "WIP.md")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    reply = step_loop.execute(["next", SLUG, "--repo-root", str(tmp_path)])

    assert (reply.exit, reply.doc["outcome"]) == (2, "needs-human")
