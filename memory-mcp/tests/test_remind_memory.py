"""Tests for remind_memory.py — the commit-time memory enforcement gate.

Validates that the hook blocks commits (exit 2) when significant work was
done without calling remember(), and allows them (exit 0) otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Load the hook module from its file path (it's not a regular package)
_HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "hooks"
_REMIND_MEMORY = _HOOK_DIR / "remind_memory.py"


def _make_transcript(entries: list[dict], path: Path) -> Path:
    """Write a fake JSONL transcript file."""
    transcript = path / "transcript.jsonl"
    lines = []
    for entry in entries:
        lines.append(json.dumps(entry))
    transcript.write_text("\n".join(lines) + "\n")
    return transcript


def _tool_use_turn(name: str, input_data: dict | None = None) -> dict:
    """Create a transcript entry for a tool_use block."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": name,
                    "input": input_data or {},
                }
            ]
        },
    }


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    """Run remind_memory.py with the given payload and return the result."""
    return subprocess.run(
        [sys.executable, str(_REMIND_MEMORY)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.fixture
def tmp(tmp_path: Path) -> Path:
    return tmp_path


class TestRemindMemoryBlocking:
    """Test that remind_memory.py blocks commits via exit 2."""

    def test_blocks_commit_when_significant_work_no_remember(self, tmp: Path):
        """Significant work + no remember() + git commit = exit 2."""
        entries = [_tool_use_turn("Edit", {"file_path": f"/tmp/f{i}.py"}) for i in range(5)]
        transcript = _make_transcript(entries, tmp)

        payload = {
            "tool_input": {"command": "git commit -m 'test'"},
            "transcript_path": str(transcript),
        }

        result = _run_hook(payload)
        assert result.returncode == 2
        assert "memory-gate:commit" in result.stderr
        assert "remember" in result.stderr.lower()

    def test_passes_when_remember_called(self, tmp: Path):
        """Significant work + remember() called = exit 0."""
        entries = [_tool_use_turn("Edit", {"file_path": f"/tmp/f{i}.py"}) for i in range(5)]
        entries.append(_tool_use_turn("mcp__plugin_i-am_memory__remember"))
        transcript = _make_transcript(entries, tmp)

        payload = {
            "tool_input": {"command": "git commit -m 'test'"},
            "transcript_path": str(transcript),
        }

        result = _run_hook(payload)
        assert result.returncode == 0
        assert result.stderr == ""

    def test_passes_when_insignificant_work(self, tmp: Path):
        """Minimal work (below thresholds) = exit 0 regardless of remember()."""
        entries = [_tool_use_turn("Edit", {"file_path": "/tmp/f.py"})]
        transcript = _make_transcript(entries, tmp)

        payload = {
            "tool_input": {"command": "git commit -m 'test'"},
            "transcript_path": str(transcript),
        }

        result = _run_hook(payload)
        assert result.returncode == 0

    def test_passes_for_non_commit_commands(self, tmp: Path):
        """Non-commit bash commands exit 0 without scanning."""
        entries = [_tool_use_turn("Edit", {"file_path": f"/tmp/f{i}.py"}) for i in range(5)]
        transcript = _make_transcript(entries, tmp)

        payload = {
            "tool_input": {"command": "ls -la"},
            "transcript_path": str(transcript),
        }

        result = _run_hook(payload)
        assert result.returncode == 0
        assert result.stderr == ""

    def test_passes_when_no_transcript(self):
        """Missing transcript_path = exit 0 (graceful degradation)."""
        payload = {
            "tool_input": {"command": "git commit -m 'test'"},
        }

        result = _run_hook(payload)
        assert result.returncode == 0

    def test_passes_on_invalid_json_input(self):
        """Invalid JSON input = exit 0 (fail-open)."""
        result = subprocess.run(
            [sys.executable, str(_REMIND_MEMORY)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_blocks_on_agent_delegation(self, tmp: Path):
        """Agent delegation counts as significant work."""
        entries = [_tool_use_turn("Agent")]
        transcript = _make_transcript(entries, tmp)

        payload = {
            "tool_input": {"command": "git commit -m 'test'"},
            "transcript_path": str(transcript),
        }

        result = _run_hook(payload)
        assert result.returncode == 2

    def test_blocks_on_many_reads(self, tmp: Path):
        """5+ reads counts as significant work (analysis session)."""
        entries = [_tool_use_turn("Read", {"file_path": f"/tmp/f{i}.py"}) for i in range(6)]
        transcript = _make_transcript(entries, tmp)

        payload = {
            "tool_input": {"command": "git commit -m 'test'"},
            "transcript_path": str(transcript),
        }

        result = _run_hook(payload)
        assert result.returncode == 2
