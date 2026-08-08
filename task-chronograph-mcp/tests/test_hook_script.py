"""Tests for the Claude Code hook script at hooks/send_event.py."""

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

HOOK_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "hooks" / "send_event.py"


@pytest.fixture
def hook_module():
    """Load the hook script module for access to all functions.

    send_event.py imports _hook_utils from its own directory; prepend that
    directory to sys.path so the bare import resolves at load time.
    """
    hooks_dir = str(HOOK_SCRIPT_PATH.parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    spec = importlib.util.spec_from_file_location("send_event", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def build_events(hook_module):
    """Load the _build_events function from the hook script."""
    return hook_module._build_events


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
            "agent_type": "praxion:researcher",
            "session_id": "sess-001",
            "agent_id": "agent-001",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "agent_start"
        assert event["agent_type"] == "praxion:researcher"
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
            "agent_type": "praxion:researcher",
            "session_id": "sess-001",
        }
        events, interactions = build_events(payload)
        assert interactions[0]["target"] == "praxion:researcher"


# ---------------------------------------------------------------------------
# _build_events: SubagentStop
# ---------------------------------------------------------------------------


class TestBuildEventsSubagentStop:
    def test_subagent_stop_produces_event_and_interaction(self, build_events):
        payload = {
            "hook_event_name": "SubagentStop",
            "agent_type": "praxion:researcher",
            "session_id": "sess-001",
            "agent_id": "agent-001",
            "agent_transcript_path": "/tmp/transcript.md",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "agent_stop"
        assert event["agent_type"] == "praxion:researcher"
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
            "agent_type": "praxion:architect",
            "session_id": "sess-002",
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        assert events[0]["event_type"] == "agent_stop"
        # Phase 4 adds hook_event to every event's metadata, but no transcript
        # means no agent_transcript_path key is present.
        assert "agent_transcript_path" not in events[0].get("metadata", {})
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


# ---------------------------------------------------------------------------
# Git context capture
# ---------------------------------------------------------------------------


class TestGitContextInEvents:
    def test_session_start_includes_git_metadata(self, build_events):
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "sess-001",
            "cwd": "/test/project",
        }
        events, _ = build_events(payload)
        assert "git" in events[0].get("metadata", {})

    def test_subagent_start_includes_git_metadata(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "session_id": "sess-001",
            "agent_type": "researcher",
            "agent_id": "a1",
            "cwd": "/test/project",
        }
        events, _ = build_events(payload)
        assert "git" in events[0].get("metadata", {})


# ---------------------------------------------------------------------------
# Skill invocation detection
# ---------------------------------------------------------------------------


class TestSkillDetection:
    def test_skill_tool_produces_skill_use_event(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_name": "Skill",
            "tool_input": {"skill": "software-planning", "args": ""},
        }
        events, _ = build_events(payload)
        skill_events = [e for e in events if e["event_type"] == "skill_use"]
        assert len(skill_events) == 1
        assert skill_events[0]["tool_name"] == "skill:software-planning"
        assert skill_events[0]["metadata"]["artifact_type"] == "skill"
        assert skill_events[0]["metadata"]["artifact_name"] == "software-planning"

    def test_skill_tool_also_produces_tool_use_event(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_name": "Skill",
            "tool_input": {"skill": "testing-strategy"},
        }
        events, _ = build_events(payload)
        tool_events = [e for e in events if e["event_type"] == "tool_use"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool_name"] == "Skill"

    def test_non_skill_tool_does_not_produce_skill_use(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_name": "Read",
            "tool_input": {"file_path": "/test.py"},
        }
        events, _ = build_events(payload)
        skill_events = [e for e in events if e["event_type"] == "skill_use"]
        assert len(skill_events) == 0


# ---------------------------------------------------------------------------
# MCP tool classification
# ---------------------------------------------------------------------------


class TestMcpToolClassification:
    def test_praxion_mcp_tool_enriched_with_metadata(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_name": "mcp__plugin_praxion_memory__remember",
            "tool_input": {"key": "test"},
        }
        events, _ = build_events(payload)
        tool_event = [e for e in events if e["event_type"] == "tool_use"][0]
        assert tool_event["metadata"]["artifact_type"] == "mcp_tool"
        assert tool_event["metadata"]["mcp_server"] == "memory"
        assert tool_event["metadata"]["mcp_tool"] == "remember"

    def test_non_praxion_mcp_tool_not_enriched(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_name": "mcp__other_server__tool",
            "tool_input": {},
        }
        events, _ = build_events(payload)
        tool_event = [e for e in events if e["event_type"] == "tool_use"][0]
        assert "artifact_type" not in tool_event["metadata"]

    def test_chronograph_mcp_tool_classified(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-001",
            "tool_name": "mcp__plugin_praxion_task-chronograph__get_pipeline_status",
            "tool_input": {},
        }
        events, _ = build_events(payload)
        tool_event = [e for e in events if e["event_type"] == "tool_use"][0]
        assert tool_event["metadata"]["mcp_server"] == "task-chronograph"
        assert tool_event["metadata"]["mcp_tool"] == "get_pipeline_status"


# ---------------------------------------------------------------------------
# Task slug extraction
# ---------------------------------------------------------------------------


class TestTaskSlugExtraction:
    def test_task_slug_extracted_from_prompt(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "session_id": "sess-001",
            "agent_type": "researcher",
            "agent_id": "a1",
            "prompt": "Research the auth flow.\n\nTask slug: auth-flow",
        }
        events, _ = build_events(payload)
        assert events[0]["metadata"].get("task_slug") == "auth-flow"

    def test_task_slug_extracted_from_description(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "session_id": "sess-001",
            "agent_type": "researcher",
            "agent_id": "a1",
            "description": "Task slug: payment-api research",
        }
        events, _ = build_events(payload)
        assert events[0]["metadata"].get("task_slug") == "payment-api"

    def test_no_task_slug_when_absent(self, build_events):
        payload = {
            "hook_event_name": "SubagentStart",
            "session_id": "sess-001",
            "agent_type": "researcher",
            "agent_id": "a1",
        }
        events, _ = build_events(payload)
        assert "task_slug" not in events[0].get("metadata", {})


# ---------------------------------------------------------------------------
# Worktree port resolution
# ---------------------------------------------------------------------------


class TestResolveProjectRoot:
    def test_returns_repo_root_for_regular_checkout(self, hook_module, tmp_path):
        """In a regular git repo, resolves to the repo root (same as cwd)."""
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        result = hook_module._resolve_project_root(str(tmp_path))
        assert result == str(tmp_path)

    def test_returns_main_repo_root_for_worktree(self, hook_module, tmp_path):
        """In a git worktree, resolves to the MAIN repo root, not the worktree."""
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        subprocess.run(["git", "init", str(main_repo)], capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=str(main_repo),
            capture_output=True,
        )
        wt_path = tmp_path / "wt"
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", "wt-branch"],
            cwd=str(main_repo),
            capture_output=True,
        )
        result = hook_module._resolve_project_root(str(wt_path))
        assert result == str(main_repo)

    def test_worktree_derives_same_port_as_main_repo(self, hook_module, tmp_path):
        """The whole point: worktree and main repo must hash to the same port."""
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        subprocess.run(["git", "init", str(main_repo)], capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=str(main_repo),
            capture_output=True,
        )
        wt_path = tmp_path / "wt"
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", "wt-branch"],
            cwd=str(main_repo),
            capture_output=True,
        )
        main_port = hook_module._derive_port(hook_module._resolve_project_root(str(main_repo)))
        wt_port = hook_module._derive_port(hook_module._resolve_project_root(str(wt_path)))
        assert main_port == wt_port

    def test_fallback_to_cwd_for_non_git_directory(self, hook_module, tmp_path):
        """Non-git directories fall back to using cwd as-is."""
        result = hook_module._resolve_project_root(str(tmp_path))
        assert result == str(tmp_path)

    def test_empty_string_returns_empty(self, hook_module):
        """Empty cwd returns empty without calling git."""
        assert hook_module._resolve_project_root("") == ""

    def test_none_returns_none(self, hook_module):
        """None cwd returns None without calling git."""
        assert hook_module._resolve_project_root(None) is None


# ---------------------------------------------------------------------------
# _build_events: PreToolUse (Phase 2 duration correlation -- ADR 052)
# ---------------------------------------------------------------------------


class TestBuildEventsPreToolUse:
    """PreToolUse hook must emit a tool_start event when tool_use_id is present."""

    def test_pre_tool_use_with_correlation_id_emits_tool_start(self, build_events):
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "sess-200",
            "agent_id": "agent-200",
            "tool_name": "Bash",
            "tool_use_id": "toolu_abc123",
            "tool_input": {"command": "ls"},
        }
        events, interactions = build_events(payload)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "tool_start"
        assert event["tool_use_id"] == "toolu_abc123"
        assert event["tool_name"] == "Bash"
        assert interactions == []

    def test_pre_tool_use_without_tool_use_id_emits_nothing(self, build_events):
        """No correlation id means PostToolUse falls back to instant span."""
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "sess-200",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        events, interactions = build_events(payload)
        assert events == []
        assert interactions == []

    def test_pre_tool_use_without_tool_name_emits_nothing(self, build_events):
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "sess-200",
            "tool_use_id": "toolu_xyz",
        }
        events, _ = build_events(payload)
        assert events == []

    def test_pre_tool_use_populates_input_summary_in_metadata(self, build_events):
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "sess-200",
            "tool_name": "Bash",
            "tool_use_id": "toolu_abc",
            "tool_input": {"command": "echo hello"},
        }
        events, _ = build_events(payload)
        assert "command=echo hello" in events[0]["metadata"]["input_summary"]

    def test_pre_tool_use_redacts_secrets_in_input(self, build_events):
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "sess-200",
            "tool_name": "Bash",
            "tool_use_id": "toolu_abc",
            "tool_input": {
                "command": "curl -H 'Authorization: Bearer sk-secretxxxxxxxxxxxxxxxxxx'"
            },
        }
        events, _ = build_events(payload)
        assert "sk-secret" not in events[0]["metadata"]["input_summary"]
        assert "[REDACTED]" in events[0]["metadata"]["input_summary"]

    def test_pre_tool_use_classifies_praxion_mcp_tool(self, build_events):
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "sess-200",
            "tool_name": "mcp__plugin_praxion_memory__remember",
            "tool_use_id": "toolu_mcp",
            "tool_input": {"category": "learnings"},
        }
        events, _ = build_events(payload)
        meta = events[0]["metadata"]
        assert meta["artifact_type"] == "mcp_tool"
        assert meta["mcp_server"] == "memory"
        assert meta["mcp_tool"] == "remember"


class TestBuildEventsPostToolUseCorrelation:
    """PostToolUse must now thread tool_use_id so the relay can close paired spans."""

    def test_post_tool_use_includes_tool_use_id(self, build_events):
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-200",
            "agent_id": "agent-200",
            "tool_name": "Bash",
            "tool_use_id": "toolu_def456",
            "tool_input": {"command": "ls"},
            "tool_response": "file1\nfile2",
        }
        events, _ = build_events(payload)
        assert any(e["tool_use_id"] == "toolu_def456" for e in events)

    def test_post_tool_use_without_tool_use_id_passes_empty_string(self, build_events):
        """Empty tool_use_id is valid -- relay falls back to instant span."""
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "sess-200",
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/x"},
        }
        events, _ = build_events(payload)
        tool_events = [e for e in events if e["event_type"] == "tool_use"]
        assert tool_events[0]["tool_use_id"] == ""

    def test_post_tool_use_failure_includes_tool_use_id(self, build_events):
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "session_id": "sess-200",
            "tool_name": "Bash",
            "tool_use_id": "toolu_fail",
            "error": "command not found",
        }
        events, _ = build_events(payload)
        assert events[0]["tool_use_id"] == "toolu_fail"
        assert events[0]["event_type"] == "error"


class TestBuildEventsPhase4Metadata:
    """Every event carries hook_event; tool events carry pre-truncation byte counts."""

    def test_hook_event_populated_on_session_start(self, build_events):
        events, _ = build_events({"hook_event_name": "SessionStart", "session_id": "s1"})
        assert events[0]["metadata"]["hook_event"] == "SessionStart"

    def test_hook_event_populated_on_subagent_start(self, build_events):
        events, _ = build_events(
            {"hook_event_name": "SubagentStart", "session_id": "s1", "agent_type": "researcher"}
        )
        assert events[0]["metadata"]["hook_event"] == "SubagentStart"

    def test_hook_event_populated_on_post_tool_use(self, build_events):
        events, _ = build_events(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
            }
        )
        tool_events = [e for e in events if e["event_type"] == "tool_use"]
        assert tool_events[0]["metadata"]["hook_event"] == "PostToolUse"

    def test_pre_tool_use_captures_input_size_bytes(self, build_events):
        events, _ = build_events(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "s1",
                "tool_name": "Bash",
                "tool_use_id": "toolu_xyz",
                "tool_input": {"command": "echo hello world"},
            }
        )
        # "command=echo hello world" is 24 bytes in utf-8
        assert events[0]["metadata"]["input_size_bytes"] == 24

    def test_post_tool_use_captures_input_and_output_size_bytes(self, build_events):
        events, _ = build_events(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Read",
                "tool_input": {"file_path": "/etc/hosts"},
                "tool_response": "localhost",
            }
        )
        tool_event = next(e for e in events if e["event_type"] == "tool_use")
        # file_path=/etc/hosts is 20 bytes
        assert tool_event["metadata"]["input_size_bytes"] == 20
        assert tool_event["metadata"]["output_size_bytes"] == len("localhost")

    def test_size_bytes_survive_large_untruncated_input(self, build_events):
        """Sizes are captured BEFORE the 4096-byte summary truncation."""
        huge_command = "echo " + ("x" * 10_000)
        events, _ = build_events(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Bash",
                "tool_input": {"command": huge_command},
            }
        )
        tool_event = next(e for e in events if e["event_type"] == "tool_use")
        # input_size_bytes reflects the raw size, not the truncated summary length
        assert tool_event["metadata"]["input_size_bytes"] > 10_000
        # But the summary itself is truncated
        assert len(tool_event["metadata"]["input_summary"]) <= 4096 + len("...")
