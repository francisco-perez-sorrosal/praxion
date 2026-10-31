"""Tests for decisions_gate.sh -- the shell fast path in front of guard_decision_records.py.

The gate finds the Python hook next to itself, so a test copies the script into tmp_path beside
a spy hook that records that Python was started and what it read from stdin. That proves the
fast path (no Python for a payload that cannot concern the decisions tree) without timing it.
One end-to-end test runs the real hook through the real script.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
GATE = HOOKS_DIR / "decisions_gate.sh"
GUARD = HOOKS_DIR / "guard_decision_records.py"
COMMIT_GATE = HOOKS_DIR / "commit_gate.sh"

SPY_LOG = "spy_stdin.txt"
SPY_SOURCE = (
    "import sys\n"
    "from pathlib import Path\n"
    f"Path(__file__).with_name({SPY_LOG!r}).write_text(sys.stdin.read(), encoding='utf-8')\n"
)
DRAFT_HASH = "1a2b3c4d"
DECISIONS_PATH = "/repo/.ai-state/decisions/drafts/x.md"
INDEX_PATH = "/repo/.ai-state/decisions/DECISIONS_INDEX.md"


@pytest.fixture
def spied(tmp_path: Path) -> Path:
    """A directory holding the gate and a spy where the gate looks for the Python hook."""
    shutil.copy(GATE, tmp_path / GATE.name)
    (tmp_path / GUARD.name).write_text(SPY_SOURCE, encoding="utf-8")
    return tmp_path


def _gate(directory: Path, mode: str, payload: dict | str) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [str(directory / GATE.name), mode],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _payload(tool_name: str, file_path: str, **extra: object) -> dict:
    return {"tool_name": tool_name, "tool_input": {"file_path": file_path, **extra}}


def _started(directory: Path) -> bool:
    return (directory / SPY_LOG).exists()


def test_the_scripts_are_executable() -> None:
    for script in (GATE, GUARD):
        assert os.access(script, os.X_OK), f"{script} is not executable (chmod +x required)"


@pytest.mark.parametrize(
    "payload",
    [
        _payload("Write", DECISIONS_PATH, content="x"),
        _payload("Edit", DECISIONS_PATH, old_string="a", new_string="b"),
        _payload("Write", "/repo/.AI-State/Decisions/x.md", content="x"),
        _payload("Write", "/repo/.ai-state/./decisions/x.md", content="x"),
        _payload("Write", "/repo/.ai-state//decisions/x.md", content="x"),
        _payload("Write", "C:\\repo\\.ai-state\\decisions\\x.md", content="x"),
        _payload("Write", "/repo/docs/x.md", content="see .ai-state/decisions"),
    ],
    ids=[
        "write",
        "edit",
        "case-folded",
        "dot-segment",
        "double-slash",
        "backslash",
        "content-only",
    ],
)
def test_write_mode_starts_python_for_a_payload_that_holds_the_decisions_tree(
    spied: Path, payload: dict
) -> None:
    result = _gate(spied, "write", payload)
    assert result.returncode == 0
    assert _started(spied)


@pytest.mark.parametrize(
    "payload",
    [
        _payload("Write", "/repo/src/app.py", content="print(1)"),
        _payload("Write", "/repo/.ai-state/DESIGN.md", content="x"),
        _payload("Edit", "/repo/.ai-state/tech_debt/ledger.md", old_string="a", new_string="b"),
        _payload("Write", "/repo/docs/DECISIONS_INDEX.md", content="x"),
        _payload("Write", "/repo/.ai-state/decision-notes.md", content="x"),
    ],
    ids=["source", "other-state-file", "ledger", "index-elsewhere", "near-miss"],
)
def test_write_mode_never_starts_python_outside_the_decisions_tree(
    spied: Path, payload: dict
) -> None:
    result = _gate(spied, "write", payload)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not _started(spied)


@pytest.mark.parametrize(
    "path",
    [INDEX_PATH, "/repo/.ai-state/decisions/decisions_index.md", "/other/DECISIONS_INDEX.md"],
)
def test_read_mode_starts_python_for_the_index(spied: Path, path: str) -> None:
    result = _gate(spied, "read", _payload("Read", path))
    assert result.returncode == 0
    assert _started(spied)


@pytest.mark.parametrize(
    "path",
    [
        "/repo/.ai-state/decisions/001-some-record.md",
        "/repo/.ai-state/decisions/drafts/x.md",
        "/repo/README.md",
        "/repo/.ai-state/DESIGN.md",
    ],
)
def test_read_mode_never_starts_python_for_any_file_but_the_index(spied: Path, path: str) -> None:
    result = _gate(spied, "read", _payload("Read", path))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not _started(spied)


@pytest.mark.parametrize("mode", ["", "bash", "commit", "WRITE"])
def test_an_unknown_mode_exits_silently_without_python(spied: Path, mode: str) -> None:
    result = _gate(spied, mode, _payload("Write", DECISIONS_PATH, content="x"))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not _started(spied)


def test_the_payload_reaches_python_intact_when_it_carries_backslashes(spied: Path) -> None:
    payload = _payload("Write", DECISIONS_PATH, content="line one\nline two\t\\n \\s")
    _gate(spied, "write", payload)
    assert json.loads((spied / SPY_LOG).read_text(encoding="utf-8")) == payload


def test_a_bash_call_that_is_not_a_commit_never_starts_python(tmp_path: Path) -> None:
    """The commit-side fast path the same hook family relies on: no `git commit`, no Python."""
    spy = tmp_path / "spy.py"
    spy.write_text(SPY_SOURCE, encoding="utf-8")
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls .ai-state/decisions"}}
    result = subprocess.run(
        [str(COMMIT_GATE), str(spy)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not _started(tmp_path)


def test_the_real_hook_denies_a_malformed_write_through_the_real_gate(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    record = tmp_path / ".ai-state" / "decisions" / "loose-note.md"
    payload = {"cwd": str(tmp_path), **_payload("Write", str(record), content="---\n---\n")}
    result = _gate(HOOKS_DIR, "write", payload)
    assert result.returncode == 0
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Refused .ai-state/decisions/loose-note.md" in decision["permissionDecisionReason"]
    assert result.stderr == ""


def test_the_real_hook_stays_silent_for_a_conforming_write(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    record = tmp_path / ".ai-state/decisions/drafts/20261031-0900-fperez-branch-slug.md"
    content = "---\nid: dec-draft-" + DRAFT_HASH + "\ncategory: behavioral\n---\n"
    payload = {"cwd": str(tmp_path), **_payload("Write", str(record), content=content)}
    result = _gate(HOOKS_DIR, "write", payload)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
