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


def _index_of(lines: int, total_bytes: int) -> str:
    """An index of `lines` short pointer lines whose UTF-8 size is exactly `total_bytes`."""
    pad = total_bytes - lines * len("- [t](t.md) — \n".encode())
    per_line, extra = divmod(pad, lines)
    assert 0 <= per_line < 130, "keep every line under the 150-character line limit"
    body = ["- [t](t.md) — " + "x" * (per_line + (1 if i < extra else 0)) for i in range(lines)]
    text = "\n".join(body) + "\n"
    assert len(text.encode("utf-8")) == total_bytes
    return text


def _write_growing(tmp_path: Path, before: str, after: str) -> dict | None:
    index = _index(tmp_path, PROJECT, before)
    return _decision(_run(tmp_path, "Write", {"file_path": str(index), "content": after}))


def test_canary_a_write_past_the_byte_ceiling_lands_and_warns(tmp_path: Path) -> None:
    decision = _write_growing(tmp_path, _index_of(39, 4_990), _index_of(39, 5_010))
    assert decision is not None
    assert "permissionDecision" not in decision
    assert decision["hookEventName"] == "PreToolUse"
    warning = decision["additionalContext"]
    assert "5,010 bytes" in warning
    assert "39 lines" in warning
    assert "5,000 bytes" in warning
    assert "topic file" in warning


def test_canary_an_edit_adding_the_forty_first_line_warns(tmp_path: Path) -> None:
    before = _index_of(40, 2_300)
    last = before.splitlines()[-1]
    index = _index(tmp_path, PROJECT, before)
    edit = {"file_path": str(index), "old_string": last, "new_string": f"{last}\n{POINTER}"}
    decision = _decision(_run(tmp_path, "Edit", edit))
    assert decision is not None
    assert "41 lines" in decision["additionalContext"]


def test_a_write_ending_exactly_at_the_ceiling_draws_no_warning(tmp_path: Path) -> None:
    assert _write_growing(tmp_path, _index_of(39, 4_990), _index_of(39, 5_000)) is None


def test_a_write_that_shrinks_an_index_still_above_the_ceiling_draws_no_warning(
    tmp_path: Path,
) -> None:
    assert _write_growing(tmp_path, _index_of(45, 6_000), _index_of(45, 5_900)) is None


def test_a_growing_write_well_under_the_ceiling_draws_no_warning(tmp_path: Path) -> None:
    assert _write_growing(tmp_path, _index_of(10, 1_000), _index_of(11, 1_100)) is None


def test_a_refusal_wins_over_the_warning(tmp_path: Path) -> None:
    before = _index_of(39, 4_990)
    decision = _write_growing(tmp_path, before, before + LONG_LINE + "\n")
    assert decision is not None
    assert decision["permissionDecision"] == "deny"
    assert "additionalContext" not in decision


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
