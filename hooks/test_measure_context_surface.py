"""Tests for hooks/measure_context_surface.py — SessionStart observability hook.

The hook now delegates its measurement to `scripts.measure_token_budget.measure()`
-- the same function the commit-gate check calls -- so file-set correctness and
divisor/tokenizer behavior are already covered by `scripts/test_measure_token_budget.py`.
These tests cover only what is specific to the hook: SessionStart gating,
graceful degradation, the observability opt-out, and the parity guarantee that
motivated the delegation (the hook can never disagree with the gate on the
same tree).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOKS_DIR.parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "measure_context_surface.py"

# Mirrors hooks/test_capture_memory.py's own sys.path-based import of a
# sibling scripts/ module.
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import measure_token_budget as mtb  # noqa: E402


def _load_module():
    """Load measure_context_surface.py as a module inside a test body."""
    spec = importlib.util.spec_from_file_location("measure_context_surface", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMainEntry:
    def _stub_stdin(self, payload: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "stdin", _StringIO(json.dumps(payload)))

    def test_writes_observation_on_session_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Set up a project tree with .ai-state/ so the hook does not bail.
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")

        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "test-session-id",
            "agent_type": "main",
        }
        self._stub_stdin(payload, monkeypatch)

        m.main()

        obs_path = ai_state / "observations.jsonl"
        assert obs_path.exists()
        line = obs_path.read_text(encoding="utf-8").strip()
        observation = json.loads(line)
        assert observation["event_type"] == "context_surface_measurement"
        assert observation["session_id"] == "test-session-id"
        assert "Always-loaded surface" in observation["summary"]
        assert any("CLAUDE.md" in p for p in observation["file_paths"])

    def test_skips_when_ai_state_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        m = _load_module()
        # No .ai-state/ created.
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)
        m.main()  # Should not raise.
        # Nothing written.
        assert not (tmp_path / ".ai-state" / "observations.jsonl").exists()

    def test_skips_non_session_start_events(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        m = _load_module()
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        payload = {
            "hook_event_name": "Stop",  # Not SessionStart
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)
        m.main()
        assert not (ai_state / "observations.jsonl").exists()

    def test_disabled_by_observability_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        m = _load_module()
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        monkeypatch.setenv("PRAXION_DISABLE_OBSERVABILITY", "1")
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)
        m.main()
        assert not (ai_state / "observations.jsonl").exists()

    def test_malformed_stdin_does_not_crash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        m = _load_module()
        monkeypatch.setattr(sys, "stdin", _StringIO("not-json{"))
        m.main()  # No raise = pass.


# ---------------------------------------------------------------------------
# Parity with the commit-gate script — the whole reason for this step.
# ---------------------------------------------------------------------------


class TestMeasurementParity:
    def test_hook_tokens_and_bytes_match_the_gate(self, monkeypatch: pytest.MonkeyPatch):
        """The hook must report the identical figure as the gate on the same
        tree, in the deterministic (no API key) estimate path — the parity
        this whole step exists to guarantee, by construction rather than by
        keeping two divisors in sync.
        """
        m = _load_module()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        captured: list[dict] = []
        monkeypatch.setattr(m, "_append_observation", lambda _path, obs: captured.append(obs))

        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(PROJECT_ROOT),
            "session_id": "parity-check",
            "agent_type": "main",
        }
        monkeypatch.setattr(sys, "stdin", _StringIO(json.dumps(payload)))

        m.main()

        assert len(captured) == 1
        gate_report = mtb.measure(PROJECT_ROOT, api_key=None)

        observation = captured[0]
        assert f"{gate_report['tokens']:,} tokens" in observation["summary"]
        assert f"({gate_report['bytes']:,} bytes)" in observation["summary"]
        assert len(observation["file_paths"]) == len(gate_report["files"])
        assert sorted(observation["file_paths"]) == sorted(gate_report["files"])


class _StringIO:
    """Minimal stdin stub — sys.stdin.read() returns the captured string."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self, *_args: object) -> str:
        return self._text
