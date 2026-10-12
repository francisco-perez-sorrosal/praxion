"""Tests for guard_memory_index.py -- the PreToolUse gate on memory-index writes.

The hook runs as a subprocess, as Claude Code runs it, with CLAUDE_CONFIG_DIR
pointed at a tmp_path config directory, so no real memory is read or written.
Canaries prove it refuses a write that adds a violation; the controls prove it
stays silent for conforming writes, for debt the write does not touch, and for
files that are not memory indexes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "guard_memory_index.py"
POINTER = "- [Short title](topic.md) — when it applies and the one rule"
LONG_LINE = "- [Long](topic.md) — " + "x" * 160


def _run(config: Path, tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        check=False,
    )


def _index(config: Path, rel: str, text: str) -> Path:
    path = config / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _decision(result: subprocess.CompletedProcess[str]) -> dict | None:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None


PROJECT = "projects/-Users-me-repo/memory/MEMORY.md"
AGENT = "agent-memory/praxion-verifier/MEMORY.md"


@pytest.mark.parametrize("rel", [PROJECT, AGENT])
def test_canary_refuses_a_write_that_adds_an_over_long_line(tmp_path: Path, rel: str) -> None:
    index = _index(tmp_path, rel, f"{POINTER}\n")
    result = _run(
        tmp_path, "Write", {"file_path": str(index), "content": f"{POINTER}\n{LONG_LINE}\n"}
    )
    decision = _decision(result)
    assert decision is not None
    assert decision["permissionDecision"] == "deny"
    assert "150 characters" in decision["permissionDecisionReason"]


def test_canary_refuses_an_edit_that_adds_content(tmp_path: Path) -> None:
    index = _index(tmp_path, PROJECT, f"{POINTER}\n")
    edit = {
        "file_path": str(index),
        "old_string": POINTER,
        "new_string": f"{POINTER}\nMerged Tuesday.",
    }
    decision = _decision(_run(tmp_path, "Edit", edit))
    assert decision is not None
    assert decision["permissionDecision"] == "deny"
    assert "content in the index" in decision["permissionDecisionReason"]


def test_allows_a_conforming_entry_into_an_index_with_old_debt(tmp_path: Path) -> None:
    index = _index(tmp_path, PROJECT, f"{LONG_LINE}\n")
    edit = {
        "file_path": str(index),
        "old_string": LONG_LINE,
        "new_string": f"{LONG_LINE}\n{POINTER}",
    }
    assert _decision(_run(tmp_path, "Edit", edit)) is None


def test_allows_a_new_index_of_short_pointers(tmp_path: Path) -> None:
    path = tmp_path / PROJECT
    path.parent.mkdir(parents=True)
    result = _run(
        tmp_path, "Write", {"file_path": str(path), "content": f"# Memory\n\n{POINTER}\n"}
    )
    assert _decision(result) is None


@pytest.mark.parametrize(
    "rel",
    [
        "repo/docs/MEMORY.md",
        "projects/-Users-me-repo/memory/notes.md",
        "elsewhere/memory/MEMORY.md",
    ],
)
def test_ignores_files_that_are_not_memory_indexes(tmp_path: Path, rel: str) -> None:
    path = _index(tmp_path, rel, "")
    result = _run(tmp_path, "Write", {"file_path": str(path), "content": f"{LONG_LINE}\n"})
    assert _decision(result) is None


def test_fails_open_on_a_malformed_payload(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path)},
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
