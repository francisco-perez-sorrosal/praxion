"""Tests for the Claude Code hook script at .claude-plugin/hooks/send_event.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the hook script via importlib (it is outside the package)
# ---------------------------------------------------------------------------

HOOK_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / ".claude-plugin" / "hooks" / "send_event.py"
)


@pytest.fixture
def build_events():
    """Load the _build_events function from the hook script."""
    spec = importlib.util.spec_from_file_location("send_event", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_events


@pytest.fixture(autouse=True)
def _mock_project_dir():
    """Provide a consistent CLAUDE_PROJECT_DIR for all tests."""
    with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "/test/project"}):
        yield


# ---------------------------------------------------------------------------
# _build_events: SessionStart
# ---------------------------------------------------------------------------


class TestBuildEventsSessionStart:
    def test_session_start_produces_event(self, build_events):
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "sess-100",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "session_start"
        assert event["session_id"] == "sess-100"
        assert event["project_dir"] == "/test/project"
        assert interactions == []

    def test_session_start_uses_project_dir_from_env(self, build_events):
        with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "/custom/path"}):
            payload = {
                "hook_event_name": "SessionStart",
                "session_id": "sess-101",
            }
            events, _ = build_events(payload)
            assert events[0]["project_dir"] == "/custom/path"


# ---------------------------------------------------------------------------
# _build_events: Stop
# ---------------------------------------------------------------------------


class TestBuildEventsStop:
    def test_stop_produces_session_stop_event(self, build_events):
        payload = {
            "hook_event_name": "Stop",
            "session_id": "sess-200",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "session_stop"
        assert event["session_id"] == "sess-200"
        assert event["project_dir"] == "/test/project"
        assert interactions == []


# ---------------------------------------------------------------------------
# _build_events: SubagentStart
# ---------------------------------------------------------------------------


class TestBuildEventsSubagentStart:
    def test_subagent_start_produces_event_and_interaction(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "agent_type": "i-am:researcher",
            "session_id": "sess-001",
            "agent_id": "agent-001",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "agent_start"
        assert event["agent_type"] == "i-am:researcher"
        assert event["session_id"] == "sess-001"
        assert event["agent_id"] == "agent-001"
        assert event["parent_session_id"] == "sess-001"
        assert "started" in event["message"]

        assert len(interactions) == 1
        ix = interactions[0]
        assert ix["source"] == "main_agent"
        assert ix["target"] == "agent-001"
        assert ix["interaction_type"] == "delegation"
        assert "researcher" in ix["summary"]

    def test_subagent_start_missing_agent_type_falls_back_to_unknown(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "session_id": "sess-001",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        assert events[0]["agent_type"] == "unknown-agent"
        assert "unknown-agent" in events[0]["message"]
        assert len(interactions) == 1
        assert "unknown-agent" in interactions[0]["summary"]

    def test_subagent_start_empty_type_falls_back_to_agent_id(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "agent_id": "abc1234",
            "session_id": "sess-001",
        }
        events, interactions = build_events(payload)
        assert events[0]["agent_type"] == "abc1234"
        assert "abc1234" in events[0]["message"]
        assert "abc1234" in interactions[0]["summary"]

    def test_subagent_start_interaction_uses_agent_type_when_no_id(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "agent_type": "i-am:researcher",
            "session_id": "sess-001",
        }
        events, interactions = build_events(payload)
        assert interactions[0]["target"] == "i-am:researcher"


# ---------------------------------------------------------------------------
# _build_events: SubagentStop
# ---------------------------------------------------------------------------


class TestBuildEventsSubagentStop:
    def test_subagent_stop_produces_event_and_interaction(self, build_events):
        payload = {
            "hook_event_name": "SubagentStop",
            "agent_type": "i-am:researcher",
            "session_id": "sess-001",
            "agent_id": "agent-001",
            "agent_transcript_path": "/tmp/transcript.md",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "agent_stop"
        assert event["agent_type"] == "i-am:researcher"
        assert event["parent_session_id"] == "sess-001"
        assert "stopped" in event["message"]
        assert event["metadata"]["agent_transcript_path"] == "/tmp/transcript.md"

        assert len(interactions) == 1
        ix = interactions[0]
        assert ix["source"] == "agent-001"
        assert ix["target"] == "main_agent"
        assert ix["interaction_type"] == "result"

    def test_subagent_stop_without_transcript(self, build_events):
        payload = {
            "hook_event_name": "SubagentStop",
            "agent_type": "i-am:architect",
            "session_id": "sess-002",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "agent_stop"
        assert "metadata" not in events[0]
        assert len(interactions) == 1


# ---------------------------------------------------------------------------
# _build_events: PostToolUse — PROGRESS.md parsing (tool_use + phase_transition)
# ---------------------------------------------------------------------------


class TestBuildEventsPostToolUse:
    def test_write_to_progress_md_with_parseable_content(self, build_events):
        content = (
            "[2025-01-15T10:30:00Z] [researcher] "
            "Phase 2/5: context-inventory -- Scanning skills directory"
        )
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "agent_id": "agent-001",
            "tool_input": {
                "file_path": "/project/.ai-work/PROGRESS.md",
                "content": content,
            },
        }
        events, interactions = build_events(payload)
        assert len(events) == 2
        # First event: tool_use
        assert events[0]["event_type"] == "tool_use"
        assert events[0]["session_id"] == "sess-001"
        # Second event: phase_transition
        event = events[1]
        assert event["event_type"] == "phase_transition"
        assert event["agent_type"] == "researcher"
        assert event["phase"] == 2
        assert event["total_phases"] == 5
        assert event["phase_name"] == "context-inventory"
        assert "Scanning skills directory" in event["message"]
        assert len(interactions) == 0

    def test_edit_to_progress_md_uses_new_string(self, build_events):
        new_string = (
            "[2025-01-15T10:35:00Z] [systems-architect] "
            "Phase 1/4: scope -- Reviewing architecture requirements"
        )
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {
                "file_path": "/project/.ai-work/PROGRESS.md",
                "new_string": new_string,
            },
        }
        events, interactions = build_events(payload)
        assert len(events) == 2
        assert events[0]["event_type"] == "tool_use"
        assert events[1]["agent_type"] == "systems-architect"
        assert events[1]["phase"] == 1
        assert events[1]["total_phases"] == 4

    def test_write_to_progress_md_unparseable_content(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {
                "file_path": "/project/.ai-work/PROGRESS.md",
                "content": "some random text",
            },
        }
        events, interactions = build_events(payload)
        # tool_use only — unparseable content does NOT produce a phase_transition
        assert len(events) == 1
        assert events[0]["event_type"] == "tool_use"

    def test_write_to_progress_md_no_content(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {"file_path": "/project/.ai-work/PROGRESS.md"},
        }
        events, interactions = build_events(payload)
        # tool_use only — no content means no phase_transition
        assert len(events) == 1
        assert events[0]["event_type"] == "tool_use"

    def test_progress_line_without_phase(self, build_events):
        content = "[2025-01-15T10:30:00Z] [researcher] Starting exploration"
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {
                "file_path": "/project/.ai-work/PROGRESS.md",
                "content": content,
            },
        }
        events, interactions = build_events(payload)
        assert len(events) == 2
        assert events[0]["event_type"] == "tool_use"
        phase_event = events[1]
        assert phase_event["event_type"] == "phase_transition"
        assert phase_event["agent_type"] == "researcher"
        assert phase_event["phase"] == 0
        assert phase_event["total_phases"] == 0
        assert phase_event["phase_name"] == ""

    def test_write_to_other_file_produces_tool_use(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {"file_path": "/project/src/module.py"},
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "tool_use"
        assert interactions == []

    def test_write_without_tool_input_produces_tool_use(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "tool_use"
        assert interactions == []

    def test_multiline_content_parses_last_line(self, build_events):
        content = (
            "[2025-01-15T10:30:00Z] [researcher] Phase 1/5: scope -- Understanding request\n"
            "[2025-01-15T10:35:00Z] [researcher] Phase 2/5: inventory -- Cataloging artifacts\n"
        )
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {
                "file_path": "/project/.ai-work/PROGRESS.md",
                "content": content,
            },
        }
        events, interactions = build_events(payload)
        assert len(events) == 2
        assert events[0]["event_type"] == "tool_use"
        assert events[1]["phase"] == 2
        assert events[1]["phase_name"] == "inventory"

    def test_progress_line_with_hashtag_labels(self, build_events):
        content = (
            "[2025-01-15T10:30:00Z] [researcher] "
            "Phase 2/5: scope -- Scanning codebase #observability #feature=auth"
        )
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {
                "file_path": "/project/.ai-work/PROGRESS.md",
                "content": content,
            },
        }
        events, interactions = build_events(payload)
        assert len(events) == 2
        assert events[1]["message"] == "Scanning codebase"

    def test_task_scoped_progress_path_detected(self, build_events):
        """PROGRESS.md inside a task-scoped subdirectory is detected."""
        content = "[2025-01-15T10:30:00Z] [researcher] Phase 1/3: scope -- Gathering context"
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_input": {
                "file_path": "/project/.ai-work/auth-flow/PROGRESS.md",
                "content": content,
            },
        }
        events, interactions = build_events(payload)
        assert len(events) == 2
        assert events[0]["event_type"] == "tool_use"
        assert events[1]["event_type"] == "phase_transition"
        assert events[1]["agent_type"] == "researcher"
        assert events[1]["phase"] == 1


# ---------------------------------------------------------------------------
# _build_events: PostToolUse — all tools emit tool_use
# ---------------------------------------------------------------------------


class TestBuildEventsPostToolUseAllTools:
    def test_read_tool_produces_tool_use(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-300",
            "agent_id": "agent-300",
            "tool_name": "Read",
            "tool_input": {"file_path": "/project/src/main.py"},
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "tool_use"
        assert event["tool_name"] == "Read"
        assert event["session_id"] == "sess-300"
        assert event["agent_id"] == "agent-300"
        assert interactions == []

    def test_bash_tool_includes_command_in_summary(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-301",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la /tmp"},
        }
        events, _ = build_events(payload)
        assert len(events) == 1
        assert events[0]["tool_name"] == "Bash"
        assert "command=ls -la /tmp" in events[0]["metadata"]["input_summary"]

    def test_tool_use_has_input_and_output_summary(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-302",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/out.txt", "content": "hello"},
            "tool_response": "File written successfully",
        }
        events, _ = build_events(payload)
        assert len(events) == 1
        meta = events[0]["metadata"]
        assert "file_path=/project/out.txt" in meta["input_summary"]
        assert "File written successfully" in meta["output_summary"]


# ---------------------------------------------------------------------------
# _build_events: PostToolUseFailure
# ---------------------------------------------------------------------------


class TestBuildEventsPostToolUseFailure:
    def test_failure_produces_error_event(self, build_events):
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "session_id": "sess-400",
            "agent_id": "agent-400",
            "tool_name": "Bash",
            "error": "Permission denied: /etc/shadow",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "error"
        assert event["tool_name"] == "Bash"
        assert event["message"] == "Permission denied: /etc/shadow"
        assert event["session_id"] == "sess-400"
        assert event["project_dir"] == "/test/project"
        assert interactions == []

    def test_failure_with_dict_error_stringified(self, build_events):
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "session_id": "sess-401",
            "tool_name": "Read",
            "error": {"code": "ENOENT", "message": "File not found"},
        }
        events, _ = build_events(payload)
        assert len(events) == 1
        msg = events[0]["message"]
        assert "ENOENT" in msg
        assert "File not found" in msg


# ---------------------------------------------------------------------------
# _build_events: Truncation of long tool input
# ---------------------------------------------------------------------------

MAX_TRUNCATION_BYTES = 4096


class TestBuildEventsTruncation:
    def test_long_tool_input_truncated(self, build_events):
        long_content = "x" * 10_000
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-500",
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/big.txt", "content": long_content},
        }
        events, _ = build_events(payload)
        assert len(events) == 1
        summary = events[0]["metadata"]["input_summary"]
        # input_summary uses key=value format for known keys, so file_path is short
        # The content field is NOT a known key so won't appear in parts —
        # but the full tool_input JSON would be truncated if no known keys match.
        # Here file_path IS a known key, so summary starts with "file_path=..."
        assert len(summary) <= MAX_TRUNCATION_BYTES + 3  # +3 for "..."

    def test_long_unknown_keys_tool_input_truncated(self, build_events):
        """When no known keys match, the full JSON dump is truncated."""
        long_value = "z" * 10_000
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-501",
            "tool_name": "Custom",
            "tool_input": {"data": long_value},
        }
        events, _ = build_events(payload)
        summary = events[0]["metadata"]["input_summary"]
        assert len(summary) <= MAX_TRUNCATION_BYTES + 3  # +3 for "..."
        assert summary.endswith("...")


# ---------------------------------------------------------------------------
# _build_events: project_dir present in all event types
# ---------------------------------------------------------------------------


class TestBuildEventsProjectDir:
    def test_session_start_includes_project_dir(self, build_events):
        events, _ = build_events({"hook_event_name": "SessionStart", "session_id": "s"})
        assert events[0]["project_dir"] == "/test/project"

    def test_stop_includes_project_dir(self, build_events):
        events, _ = build_events({"hook_event_name": "Stop", "session_id": "s"})
        assert events[0]["project_dir"] == "/test/project"

    def test_subagent_start_includes_project_dir(self, build_events):
        events, _ = build_events(
            {"hook_event_name": "SubagentStart", "session_id": "s", "agent_type": "r"}
        )
        assert events[0]["project_dir"] == "/test/project"

    def test_subagent_stop_includes_project_dir(self, build_events):
        events, _ = build_events(
            {"hook_event_name": "SubagentStop", "session_id": "s", "agent_type": "r"}
        )
        assert events[0]["project_dir"] == "/test/project"

    def test_post_tool_use_includes_project_dir(self, build_events):
        events, _ = build_events(
            {"hook_event_name": "PostToolUse", "session_id": "s", "tool_name": "Read"}
        )
        assert events[0]["project_dir"] == "/test/project"

    def test_post_tool_use_failure_includes_project_dir(self, build_events):
        events, _ = build_events(
            {
                "hook_event_name": "PostToolUseFailure",
                "session_id": "s",
                "tool_name": "Bash",
                "error": "fail",
            }
        )
        assert events[0]["project_dir"] == "/test/project"

    def test_cwd_from_payload_takes_priority_over_env(self, build_events):
        events, _ = build_events(
            {
                "hook_event_name": "SessionStart",
                "session_id": "s",
                "cwd": "/from/payload",
            }
        )
        assert events[0]["project_dir"] == "/from/payload"

    def test_env_var_used_when_no_cwd_in_payload(self, build_events):
        events, _ = build_events({"hook_event_name": "SessionStart", "session_id": "s"})
        assert events[0]["project_dir"] == "/test/project"  # from mocked env

    def test_missing_both_cwd_and_env_defaults_to_empty(self, build_events):
        with patch.dict("os.environ", {}, clear=True):
            events, _ = build_events({"hook_event_name": "SessionStart", "session_id": "s"})
            assert events[0]["project_dir"] == ""


# ---------------------------------------------------------------------------
# _build_events: Unknown hook
# ---------------------------------------------------------------------------


class TestBuildEventsUnknownHook:
    def test_unknown_hook_returns_empty_lists(self, build_events):
        payload = {"hook_event_name": "SomeUnknownHook", "session_id": "sess-001"}
        events, interactions = build_events(payload)
        assert events == []
        assert interactions == []

    def test_missing_hook_name_returns_empty_lists(self, build_events):
        payload = {"session_id": "sess-001"}
        events, interactions = build_events(payload)
        assert events == []
        assert interactions == []


# ---------------------------------------------------------------------------
# Hook script: exits 0 when server is unavailable
# ---------------------------------------------------------------------------


class TestHookScriptProcess:
    def test_exits_zero_when_server_unavailable(self):
        """Run the actual script via subprocess, piping valid JSON to stdin."""
        payload = json.dumps(
            {
                "hook_event_name": "SubagentStart",
                "agent_type": "researcher",
                "session_id": "sess-001",
            }
        )
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT_PATH)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=10,
            env={"CHRONOGRAPH_PORT": "19999", "PATH": ""},
        )
        assert result.returncode == 0

    def test_exits_zero_with_invalid_json(self):
        """Script should not crash even with bad input."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT_PATH)],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
