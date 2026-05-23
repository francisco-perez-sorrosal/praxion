"""Canary tests for hooks/memory_gate.py — Stop hook blocking unmemorized work.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. These tests drive memory_gate.py's reject condition:
significant work in the transcript with no remember() call and an active memory
system. The gate must block (exit 2) when that condition is met.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HOOKS_DIR = Path(__file__).resolve().parent
MEMORY_GATE = HOOKS_DIR / "memory_gate.py"

# Minimum edits to trigger "significant work" threshold (MIN_EDITS = 3 in _hook_utils.py)
_ENOUGH_EDITS = 3


def _make_transcript(tmp_path: Path, *, edits: int = 0, remember: bool = False) -> Path:
    """Build a minimal JSONL transcript with the requested tool pattern.

    Each edit is a Write tool_use block. The remember call uses the
    mcp__plugin_i-am_memory__remember tool name so _hook_utils recognises it.
    """
    lines: list[dict] = []

    def _tool(name: str, input_: dict | None = None) -> dict:
        return {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": name, "input": input_ or {}}]
            },
        }

    for i in range(edits):
        lines.append(_tool("Write", {"file_path": f"scripts/file_{i}.py"}))

    if remember:
        lines.append(_tool("mcp__plugin_i-am_memory__remember", {"key": "test"}))

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )
    return transcript


def _make_memory_file(project_dir: Path) -> None:
    """Create a .ai-state/memory.json that makes is_memory_system_active() return True."""
    memory_dir = project_dir / ".ai-state"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "memory.json").write_text(
        json.dumps({"schema_version": "2.0"}), encoding="utf-8"
    )


def _run_gate(
    transcript: Path,
    cwd: Path,
    *,
    stop_hook_active: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke memory_gate.py via subprocess, feeding the hook JSON payload on stdin."""
    payload = json.dumps(
        {
            "transcript_path": str(transcript),
            "cwd": str(cwd),
            "stop_hook_active": stop_hook_active,
        }
    )
    # Start from a clean baseline (Praxion's own env sets PRAXION_DISABLE_MEMORY_MCP=1,
    # which would short-circuit the gate to exit 0 in every test), then apply the test's
    # env LAST so a test that explicitly sets a disable var still takes effect.
    merged_env = dict(os.environ)
    merged_env.pop("PRAXION_DISABLE_MEMORY_GATE", None)
    merged_env.pop("PRAXION_DISABLE_MEMORY_MCP", None)
    merged_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(MEMORY_GATE)],
        input=payload,
        capture_output=True,
        text=True,
        env=merged_env,
        check=False,
    )


# ---------------------------------------------------------------------------
# Canary: gate blocks when significant work has no remember() call
# ---------------------------------------------------------------------------


def test_blocks_session_with_significant_unmemorized_work(tmp_path: Path) -> None:
    """Canary: gate exits 2 when transcript has enough edits and no remember().

    This is the primary reject condition: significant work done (>= MIN_EDITS
    file edits) in a session where memory is active but remember() was never
    called. The gate must block to prompt the user to memorise their work.
    """
    transcript = _make_transcript(tmp_path, edits=_ENOUGH_EDITS, remember=False)
    _make_memory_file(tmp_path)

    result = _run_gate(transcript, tmp_path)

    assert result.returncode == 2, (
        f"memory_gate must exit 2 (block) when significant work is unmemorized; "
        f"got rc={result.returncode}, stderr={result.stderr!r}"
    )
    assert "block" in result.stderr.lower() or "memory-gate" in result.stderr.lower(), (
        f"gate stderr must contain block decision or 'memory-gate' tag; "
        f"got: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Happy paths: gate does NOT block in safe conditions
# ---------------------------------------------------------------------------


def test_passes_when_remember_was_called(tmp_path: Path) -> None:
    """After a remember() call, the gate allows the session to end."""
    transcript = _make_transcript(tmp_path, edits=_ENOUGH_EDITS, remember=True)
    _make_memory_file(tmp_path)

    result = _run_gate(transcript, tmp_path)

    assert result.returncode == 0, (
        f"gate must not block after remember() was called; "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )


def test_passes_when_work_below_threshold(tmp_path: Path) -> None:
    """Fewer than MIN_EDITS edits does not trigger the gate."""
    transcript = _make_transcript(tmp_path, edits=1, remember=False)
    _make_memory_file(tmp_path)

    result = _run_gate(transcript, tmp_path)

    assert result.returncode == 0, (
        f"gate must not block when work is below threshold; "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )


def test_passes_when_no_memory_system_active(tmp_path: Path) -> None:
    """Gate does not block if the memory system is not active (no memory.json)."""
    transcript = _make_transcript(tmp_path, edits=_ENOUGH_EDITS, remember=False)
    # Deliberately do NOT create .ai-state/memory.json

    result = _run_gate(transcript, tmp_path)

    assert result.returncode == 0, (
        f"gate must not block when memory system is not active; "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )


def test_passes_when_memory_gate_disabled(tmp_path: Path) -> None:
    """Gate does not block when PRAXION_DISABLE_MEMORY_GATE=1."""
    transcript = _make_transcript(tmp_path, edits=_ENOUGH_EDITS, remember=False)
    _make_memory_file(tmp_path)

    result = _run_gate(
        transcript,
        tmp_path,
        env={"PRAXION_DISABLE_MEMORY_GATE": "1"},
    )

    assert result.returncode == 0, (
        f"gate must not block when PRAXION_DISABLE_MEMORY_GATE=1; "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )


def test_passes_on_second_attempt_to_prevent_infinite_loop(tmp_path: Path) -> None:
    """Gate allows through on the second stop attempt (stop_hook_active=True)."""
    transcript = _make_transcript(tmp_path, edits=_ENOUGH_EDITS, remember=False)
    _make_memory_file(tmp_path)

    result = _run_gate(transcript, tmp_path, stop_hook_active=True)

    assert result.returncode == 0, (
        f"gate must not block on second attempt (stop_hook_active=True); "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )
