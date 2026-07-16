"""Tests for hooks/capture_memory.py — the `skill_activation` observations event.

Targets `build_observation(payload: dict) -> dict`, the pure function
extracted from `main()`'s inlined observation-dict assembly. Calling it
directly (no stdin/subprocess harness) lets these tests exercise the new
`Skill`-tool branch, envelope preservation, the non-Skill negative case, and
merge-driver survival — all hermetically, with fixtures built at runtime.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOKS_DIR.parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "capture_memory.py"


def _load_module():
    """Load capture_memory.py as a module inside a test body."""
    spec = importlib.util.spec_from_file_location("capture_memory", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_reconcile_observations():
    """Load reconcile_observations from scripts/reconcile_ai_state.py.

    Mirrors scripts/merge_driver_observations.py's own sys.path-based import
    of its sibling script.
    """
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from reconcile_ai_state import reconcile_observations  # noqa: E402

    return reconcile_observations


def _tool_call_payload(tool_name: str, tool_input: dict | None = None, **overrides: object) -> dict:
    """Build a synthetic completed-PostToolUse payload for the given tool.

    Mirrors the fields `capture_memory.py` reads off a real Claude Code
    PostToolUse payload: tool_name, tool_input, tool_response, cwd,
    session_id, agent_type, agent_id.
    """
    payload: dict = {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "tool_response": {},
        "cwd": "/tmp/some-project",
        "session_id": "session-abc123",
        "agent_type": "main",
        "agent_id": "session-abc123",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# skill_activation shape — event type and skill_name field
# ---------------------------------------------------------------------------


class TestSkillActivationShape:
    def test_completed_skill_call_is_classified_as_skill_activation_with_its_skill_name(self):
        m = _load_module()
        payload = _tool_call_payload("Skill", {"skill": "python-development"})

        observation = m.build_observation(payload)

        assert observation["event_type"] == "skill_activation"
        assert observation["skill_name"] == "python-development"


# ---------------------------------------------------------------------------
# Envelope preservation — Skill rows keep the standard observation envelope
# ---------------------------------------------------------------------------


class TestSkillActivationEnvelope:
    def test_skill_activation_row_carries_every_existing_envelope_field(self):
        m = _load_module()
        payload = _tool_call_payload(
            "Skill",
            {"skill": "python-development"},
            session_id="session-envelope-check",
            agent_type="test-engineer",
            agent_id="session-envelope-check",
        )

        observation = m.build_observation(payload)

        assert observation["timestamp"]  # non-empty ISO8601 stamp
        assert observation["session_id"] == "session-envelope-check"
        assert observation["agent_type"] == "test-engineer"
        assert observation["agent_id"] == "session-envelope-check"
        assert observation["project"] == "some-project"  # Path(cwd).name
        assert observation["tool_name"] == "Skill"
        assert observation["summary"] == "Activate skill: python-development"
        assert observation["outcome"] == "success"
        assert observation["classification"] == "tool_use"  # classify_event unchanged
        assert observation["file_paths"] == []


# ---------------------------------------------------------------------------
# Negative case — non-Skill tools stay tool_use and never carry skill_name
# ---------------------------------------------------------------------------


class TestNonSkillToolsStayToolUse:
    def test_write_tool_call_is_not_classified_as_skill_activation(self):
        m = _load_module()
        payload = _tool_call_payload("Write", {"file_path": "src/foo.py"})

        observation = m.build_observation(payload)

        assert observation["event_type"] == "tool_use"
        assert "skill_name" not in observation

    def test_agent_spawn_is_not_classified_as_skill_activation(self):
        m = _load_module()
        payload = _tool_call_payload(
            "Agent", {"subagent_type": "researcher", "description": "explore the codebase"}
        )

        observation = m.build_observation(payload)

        assert observation["event_type"] == "tool_use"
        assert "skill_name" not in observation


# ---------------------------------------------------------------------------
# Merge-driver survival — skill_activation rows keep all dedup-key fields
# ---------------------------------------------------------------------------


class TestSkillActivationMergeSurvival:
    def test_reconcile_observations_preserves_skill_activation_rows_from_both_branches(self):
        m = _load_module()
        reconcile_observations = _load_reconcile_observations()

        ours_row = m.build_observation(
            _tool_call_payload(
                "Skill",
                {"skill": "python-development"},
                session_id="session-ours",
                agent_id="session-ours",
            )
        )
        ours_row["timestamp"] = "2026-07-16T09:00:00+00:00"

        theirs_row = m.build_observation(
            _tool_call_payload(
                "Skill",
                {"skill": "refactoring"},
                session_id="session-theirs",
                agent_id="session-theirs",
            )
        )
        theirs_row["timestamp"] = "2026-07-16T10:00:00+00:00"

        ours_text = json.dumps(ours_row) + "\n"
        theirs_text = json.dumps(theirs_row) + "\n"

        merged_text = reconcile_observations(ours_text, theirs_text)

        merged_rows = [json.loads(line) for line in merged_text.strip().splitlines()]
        merged_session_ids = [row["session_id"] for row in merged_rows]
        assert merged_session_ids == ["session-ours", "session-theirs"]  # sorted by timestamp
        assert all(row["event_type"] == "skill_activation" for row in merged_rows)
