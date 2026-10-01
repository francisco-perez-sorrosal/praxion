"""Tests for `observation.py` -- the liveness probe for the observation-log hooks.

The failure this closes: in September 2026 a session working from a subdirectory
wrote its rows beside that directory, not into the checkout's log; the old hook
checks ran from the root and never saw it. The judge is fed a log with no rows,
a log written beside the subdirectory, and a row missing its slug; the replay is
run against stand-in hooks that log correctly, log nowhere, and log beside the
session directory. Expected values come from the probe's contract.
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import observation  # noqa: E402

from gate_probes.verdict import GateId, Verdict  # noqa: E402

PROJECT = "liveness-project"
START = {"event_type": "agent_start", "project": PROJECT, "slug_attribution": "spawn-prompt"}
SPAWN = {
    "event_type": "tool_use",
    "project": PROJECT,
    "spawned_agent_id": "agent-1",
    "task_slug": observation.SLUG,
}


def _judged(rows, strays=()) -> str | None:
    return observation.judge(rows, project=PROJECT, strays=strays)


# -- the pure judge ---------------------------------------------------------------


def test_one_start_row_and_one_spawn_row_for_the_project_pass_the_judge():
    assert _judged([START, SPAWN]) is None


def test_unrelated_rows_in_the_log_do_not_matter():
    other = {"event_type": "tool_use", "project": PROJECT, "tool_name": "Bash"}

    assert _judged([other, START, SPAWN]) is None


@pytest.mark.parametrize(
    ("label", "rows", "strays", "quoted"),
    [
        ("a log with no rows", [], (), "agent_start rows: 0"),
        ("no start row", [SPAWN], (), "agent_start rows: 0"),
        ("no spawn row", [START], (), "spawn rows: 0"),
        ("two start rows", [START, START, SPAWN], (), "agent_start rows: 2"),
        ("two spawn rows", [START, SPAWN, SPAWN], (), "spawn rows: 2"),
        (
            "a start row without its slug attribution",
            [{**START, "slug_attribution": None}, SPAWN],
            (),
            "slug_attribution None",
        ),
        (
            "a start row for another project",
            [{**START, "project": "praxion"}, SPAWN],
            (),
            "agent_start project 'praxion'",
        ),
        (
            "a spawn row missing its slug",
            [START, {**SPAWN, "task_slug": None}],
            (),
            "task_slug None",
        ),
        (
            "a spawn row missing the spawned agent",
            [START, {**SPAWN, "spawned_agent_id": ""}],
            (),
            "spawn rows: 0",
        ),
        (
            "a spawn row for another project",
            [START, {**SPAWN, "project": "elsewhere"}],
            (),
            "spawn project 'elsewhere'",
        ),
        (
            "a log written beside the session directory",
            [],
            (".ai-work/liveness-probe/.ai-state",),
            ".ai-work/liveness-probe/.ai-state",
        ),
    ],
)
def test_every_dead_log_fails_the_judge_naming_what_is_wrong(label, rows, strays, quoted):
    reason = _judged(rows, strays)

    assert reason is not None, f"{label} passed"
    assert quoted in reason, f"{label}: {reason}"


def test_a_log_beside_the_session_directory_also_fails_when_the_root_log_is_right():
    reason = _judged([START, SPAWN], (".ai-work/liveness-probe/.ai-state",))

    assert reason is not None
    assert "below the session directory" in reason


def test_every_failure_reason_is_a_legal_failed_verdict_reason():
    for rows, strays in (([], ()), ([START], ()), ([START, SPAWN], ("a/.ai-state",))):
        Verdict(
            gate=GateId.OBSERVATION_HOOKS,
            passed=False,
            reason=_judged(rows, strays),
            elapsed_s=0.0,
        )


def test_the_exact_words_of_a_failure():
    reason = _judged([START], (".ai-work/liveness-probe/.ai-state",))

    assert reason == (
        "expected the checkout's log to hold one agent_start row (slug_attribution "
        "'spawn-prompt') and one spawn row (spawned_agent_id, task_slug 'liveness-probe'), "
        f"both for project '{PROJECT}', and no .ai-state below the session directory; "
        "observed agent_start rows: 1, spawn rows: 0, "
        ".ai-state below the session directory: .ai-work/liveness-probe/.ai-state"
    )


# -- the replay, against stand-in hooks -------------------------------------------

HOOK_TEMPLATE = """\
    import json, os, sys
    from pathlib import Path
    MODE = {mode!r}
    payload = json.load(sys.stdin)
    with open({record!r}, "a") as handle:
        handle.write(json.dumps(payload) + "\\n")
    cwd = Path(payload["cwd"])
    if MODE == "silent":
        sys.exit(0)
    target = cwd
    if MODE == "right":
        for directory in (cwd, *cwd.parents):
            if (directory / ".ai-state").is_dir():
                target = directory
                break
            if (directory / ".git").exists():
                break
    (target / ".ai-state").mkdir(exist_ok=True)
    row = {{"project": target.name, "event_type": "agent_start", "slug_attribution": "spawn-prompt"}}
    if payload["hook_event_name"] == "PostToolUse":
        prompt = payload["tool_input"]["prompt"]
        row = {{
            "project": target.name,
            "event_type": "tool_use",
            "spawned_agent_id": payload["tool_response"]["agentId"],
            "task_slug": prompt.split("Task slug:")[1].split()[0],
        }}
    with open(target / ".ai-state" / "observations.jsonl", "a") as handle:
        handle.write(json.dumps(row) + "\\n")
"""


def _stand_in_repo(tmp_path: Path, mode: str) -> Path:
    repo = tmp_path / "plugin"
    (repo / "hooks").mkdir(parents=True)
    command = {
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stand_in.py",
        "timeout": 10,
    }
    registration = {
        "hooks": {
            "SubagentStart": [{"matcher": "", "hooks": [command]}],
            "PostToolUse": [{"matcher": "", "hooks": [command]}],
        }
    }
    (repo / "hooks" / "hooks.json").write_text(json.dumps(registration))
    (repo / "hooks" / "stand_in.py").write_text(
        textwrap.dedent(HOOK_TEMPLATE.format(mode=mode, record=str(tmp_path / "payloads.jsonl")))
    )
    return repo


def _read_rows(state_dir: Path) -> list[dict]:
    log = state_dir / "observations.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _replay(repo: Path, env: dict[str, str] | None = None) -> Verdict:
    base = {"PATH": "/usr/bin:/bin"} if env is None else env
    return observation.replay_and_judge(repo, base, read_rows=_read_rows)


def test_hooks_that_log_into_the_checkout_pass_from_a_subdirectory(tmp_path):
    verdict = _replay(_stand_in_repo(tmp_path, "right"))

    assert verdict.passed, verdict.reason
    assert verdict.gate is GateId.OBSERVATION_HOOKS


def test_hooks_that_write_nothing_fail_naming_the_missing_rows(tmp_path):
    verdict = _replay(_stand_in_repo(tmp_path, "silent"))

    assert not verdict.passed
    assert "agent_start rows: 0" in verdict.reason
    assert "spawn rows: 0" in verdict.reason


def test_hooks_that_log_beside_the_session_directory_fail_naming_the_stray_state(tmp_path):
    verdict = _replay(_stand_in_repo(tmp_path, "beside"))

    assert not verdict.passed
    assert "agent_start rows: 0" in verdict.reason
    assert f".ai-work/{observation.SLUG}/.ai-state" in verdict.reason


def test_a_missing_hook_registration_fails_the_probe_and_says_so(tmp_path):
    verdict = _replay(tmp_path / "no-plugin")

    assert not verdict.passed
    assert "hooks/hooks.json" in verdict.reason


def test_the_scratch_project_lives_outside_the_checkout_and_is_removed(tmp_path, monkeypatch):
    scratch_root = tmp_path / "system-temp"
    scratch_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch_root))
    repo = _stand_in_repo(tmp_path, "right")
    before = sorted(path.relative_to(repo) for path in repo.rglob("*"))

    verdict = _replay(repo)

    assert verdict.passed, verdict.reason
    assert sorted(path.relative_to(repo) for path in repo.rglob("*")) == before
    assert list(scratch_root.iterdir()) == []


def test_the_scratch_project_is_removed_when_the_hooks_fail(tmp_path, monkeypatch):
    scratch_root = tmp_path / "system-temp"
    scratch_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch_root))

    _replay(_stand_in_repo(tmp_path, "silent"))

    assert list(scratch_root.iterdir()) == []


# -- what the replay sends, and how the probe is built ----------------------------


def _payloads(tmp_path: Path) -> list[dict]:
    log = tmp_path / "payloads.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_the_spawn_is_replayed_start_first_from_the_subdirectory_with_the_slug_in_the_prompt(
    tmp_path,
):
    _replay(_stand_in_repo(tmp_path, "right"))

    start, result = _payloads(tmp_path)
    assert start["hook_event_name"] == "SubagentStart"
    assert result["hook_event_name"] == "PostToolUse"
    assert start["cwd"] == result["cwd"]
    assert start["cwd"].endswith(f"{PROJECT}/.ai-work/{observation.SLUG}")
    assert start["agent_id"] == observation.AGENT_ID
    assert start["agent_type"] == observation.AGENT_TYPE
    assert start["session_id"] == observation.SESSION_ID
    assert result["tool_response"]["agentId"] == observation.AGENT_ID
    assert result["tool_use_id"] == observation.TOOL_USE_ID
    assert result["tool_input"]["prompt"].startswith(f"Task slug: {observation.SLUG}")


def test_the_scratch_project_is_a_git_checkout_with_a_state_directory_and_a_subdirectory(
    tmp_path,
):
    project = tmp_path / PROJECT

    session_dir = observation._build_project(project, {"PATH": "/usr/bin:/bin"})

    assert session_dir == project / ".ai-work" / observation.SLUG
    assert session_dir.is_dir()
    assert (project / ".ai-state").is_dir()
    assert (project / ".git").exists()
    assert not (session_dir / ".ai-state").exists()


def test_stray_state_below_the_session_directory_is_found_relative_to_the_checkout(tmp_path):
    session_dir = observation._build_project(tmp_path / PROJECT, {"PATH": "/usr/bin:/bin"})
    (session_dir / "deeper" / ".ai-state").mkdir(parents=True)
    (session_dir / ".ai-state").mkdir()

    strays = observation._stray_state(tmp_path / PROJECT, session_dir)

    assert strays == [
        f".ai-work/{observation.SLUG}/.ai-state",
        f".ai-work/{observation.SLUG}/deeper/.ai-state",
    ]


def test_a_missing_registration_reason_is_exact_up_to_the_error_text(tmp_path):
    verdict = _replay(tmp_path / "no-plugin")

    assert verdict.reason.startswith(
        "expected the hook registration to be replayed; observed FileNotFoundError: "
    )


def test_a_passing_verdict_has_an_empty_reason_and_the_probe_elapsed_time(tmp_path):
    verdict = _replay(_stand_in_repo(tmp_path, "right"))

    assert verdict.reason == ""
    assert verdict.elapsed_s > 0
    assert verdict.unselected == ()


def _with_stand_in_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, present: bool
) -> Path:
    repo = _stand_in_repo(tmp_path, "right")
    if present:
        package = repo / "hooks" / "_observation_log"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "reader.py").write_text(
            textwrap.dedent(
                """\
                import json

                def read_rows(state_dir):
                    log = state_dir / "observations.jsonl"
                    return [json.loads(line) for line in log.read_text().splitlines()]
                """
            )
        )
    # No other checkout's hooks directory may answer for the one under test.
    others = [entry for entry in sys.path if not (Path(entry) / "_observation_log").is_dir()]
    monkeypatch.setattr(sys, "path", others)
    monkeypatch.delitem(sys.modules, "_observation_log", raising=False)
    monkeypatch.delitem(sys.modules, "_observation_log.reader", raising=False)
    return repo


def test_run_reads_the_log_through_the_reader_of_the_checkout_under_test(tmp_path, monkeypatch):
    repo = _with_stand_in_reader(tmp_path, monkeypatch, present=True)

    verdict = observation.run(repo, {"PATH": "/usr/bin:/bin"})

    assert verdict.passed, verdict.reason
    assert str(repo / "hooks") in sys.path


def test_run_fails_saying_so_when_the_checkout_has_no_reader(tmp_path, monkeypatch):
    repo = _with_stand_in_reader(tmp_path, monkeypatch, present=False)

    verdict = observation.run(repo, {"PATH": "/usr/bin:/bin"})

    assert not verdict.passed
    assert verdict.gate is GateId.OBSERVATION_HOOKS
    assert verdict.elapsed_s == 0.0
    assert verdict.reason.startswith(
        "expected the log owner's reader importable from hooks/; observed ImportError: "
    )
