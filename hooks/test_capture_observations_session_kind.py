"""Tests for the session origin a spawn-result row records.

``build_observation`` and ``spawn_result_fields`` stay pure: the spawning
session's ``session_kind`` and ``checkout`` arrive as an ``origin`` argument
read once at the hook's edge, and only a spawn result that started an agent
records them.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "capture_observations.py"
ORIGIN = {"session_kind": "headless", "checkout": "/work/some-pipeline"}


def _load_module():
    spec = importlib.util.spec_from_file_location("capture_observations", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(tool_name: str = "Agent", tool_response: object = None) -> dict:
    return {
        "tool_name": tool_name,
        "tool_input": {"prompt": "Task slug: s1", "subagent_type": "researcher"},
        "tool_response": {"agentId": "child-1"} if tool_response is None else tool_response,
        "cwd": "/tmp/some-project",
        "session_id": "session-abc123",
    }


def test_a_spawn_result_records_the_origin_it_is_handed():
    row = _load_module().build_observation(_payload(), project="p", origin=ORIGIN)

    assert row["session_kind"] == "headless"
    assert row["checkout"] == "/work/some-pipeline"


@pytest.mark.parametrize("origin", [None, {}])
def test_a_spawn_result_without_an_origin_equals_the_row_written_before(origin):
    module = _load_module()
    without = module.build_observation(_payload(), project="p")

    with_origin = module.build_observation(_payload(), project="p", origin=origin)

    assert set(with_origin) == set(without)
    assert "session_kind" not in with_origin
    assert "checkout" not in with_origin


def test_a_partial_origin_records_only_the_evidence_it_holds():
    row = _load_module().build_observation(
        _payload(), project="p", origin={"session_kind": "interactive"}
    )

    assert row["session_kind"] == "interactive"
    assert "checkout" not in row


@pytest.mark.parametrize(
    "payload",
    [
        _payload("Bash", {}),
        _payload("Agent", {"error": "boom"}),
        _payload("Agent", "not an object"),
    ],
)
def test_a_row_that_started_no_agent_never_records_the_origin(payload):
    row = _load_module().build_observation(payload, project="p", origin=ORIGIN)

    assert "session_kind" not in row
    assert "checkout" not in row


# -- the hook's edge: the environment is read once, only for a spawn ----------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.setenv("PRAXION_OBSERVATION_LOG", "full")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return tmp_path


def _record(
    project: Path, monkeypatch: pytest.MonkeyPatch, payload: dict, cwd: Path | None = None
) -> dict:
    payload["cwd"] = str(cwd or project)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    _load_module().main()
    lines = (project / ".ai-state" / "observations.jsonl").read_text().splitlines()
    return json.loads(lines[-1])


def test_the_hook_records_the_session_kind_its_entrypoint_shows_and_the_checkout_it_logs_in(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-cli")

    row = _record(project, monkeypatch, _payload())

    assert row["session_kind"] == "headless"
    assert row["checkout"] == str(project.resolve())


def test_a_session_started_below_the_checkout_root_records_the_checkout_not_its_start_directory(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    (project / ".git").mkdir()
    started_in = project / "packages" / "app"
    started_in.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(started_in))

    row = _record(project, monkeypatch, _payload(), cwd=started_in)

    assert row["session_kind"] == "interactive"
    assert row["checkout"] == str(project.resolve())


def test_the_checkout_is_recorded_resolved_when_the_logging_directory_is_reached_by_a_link(
    project: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
):
    link = tmp_path_factory.mktemp("links") / "checkout-link"
    link.symlink_to(project, target_is_directory=True)
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")

    row = _record(project, monkeypatch, _payload(), cwd=link)

    assert row["checkout"] == str(project.resolve())


def test_the_hook_writes_the_row_it_wrote_before_when_the_entrypoint_is_not_set(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    row = _record(project, monkeypatch, _payload())

    assert "session_kind" not in row
    assert "checkout" not in row


def test_an_unclassified_entrypoint_costs_the_row_both_keys_and_never_the_row(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "no-such-entrypoint")

    row = _record(project, monkeypatch, _payload())

    assert row["spawned_agent_id"] == "child-1"
    assert "session_kind" not in row
    assert "checkout" not in row


def test_an_ordinary_tool_row_carries_neither_key_whatever_the_environment_shows(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-cli")

    row = _record(project, monkeypatch, _payload("Bash", {}))

    assert "session_kind" not in row
    assert "checkout" not in row
