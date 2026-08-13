"""Tests for hooks/capture_memory.py — the `skill_activation` observations event.

Targets `build_observation(payload: dict) -> dict`, the pure function
extracted from `main()`'s inlined observation-dict assembly. Calling it
directly (no stdin/subprocess harness) lets these tests exercise the new
`Skill`-tool branch, envelope preservation, the non-Skill negative case, and
merge-driver survival — all hermetically, with fixtures built at runtime.
"""

from __future__ import annotations

import importlib.util
import io
import json
import runpy
import sys
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# WAL isolation — every `main()` test below routes writes into tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_project(tmp_path: Path) -> Path:
    """A throwaway project root carrying a real `.ai-state/` directory.

    `capture_memory` derives the WAL path from the *payload's* `cwd`, so a
    payload pointing here can never reach the repository's own
    `.ai-state/observations.jsonl`. The `.ai-state/` directory must exist or
    `main()` takes its graceful-degradation exit instead of the write path.
    """
    (tmp_path / ".ai-state").mkdir()
    return tmp_path


def _wal_rows(project: Path) -> list[dict]:
    """Read back every observation `main()` appended under `project`."""
    obs_path = project / ".ai-state" / "observations.jsonl"
    if not obs_path.exists():
        return []
    text = obs_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _drive_main(module, payload_text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `main()` in-process with `payload_text` standing in for stdin."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))
    module.main()


# ---------------------------------------------------------------------------
# classify_event — the branch-dense heart of the module
# ---------------------------------------------------------------------------


class TestFileEditClassification:
    """A Write/Edit is classified by the first path it touches."""

    @pytest.mark.parametrize(
        ("file_path", "expected"),
        [
            (".ai-state/decisions/042-choose-postgres.md", "decision"),
            ("tests/test_refund.py", "test"),
            ("app/refund_test.py", "test"),
            ("src/refund.py", "implementation"),
            ("docs/architecture.md", "documentation"),
            ("pyproject.toml", "configuration"),
            ("package.json", "configuration"),
            ("ci/pipeline.yaml", "configuration"),
            ("ci/pipeline.yml", "configuration"),
            ("Makefile", "implementation"),
        ],
    )
    def test_edited_path_determines_the_classification(self, file_path: str, expected: str):
        m = _load_module()

        assert m.classify_event("Edit", [file_path]) == expected

    def test_write_touching_nothing_falls_back_to_implementation(self):
        m = _load_module()

        assert m.classify_event("Write", []) == "implementation"


class TestClassificationPrecedence:
    """Overlapping path rules resolve in a fixed, load-bearing order.

    Each case below satisfies *two* rules at once. Getting the order wrong
    silently mislabels a whole category in the WAL, which the sentinel's
    pipeline dimension and the metrics rollup both read back.
    """

    def test_adr_markdown_is_a_decision_rather_than_documentation(self):
        m = _load_module()

        # An ADR is always a .md file, so `documentation` would also match.
        assert m.classify_event("Write", [".ai-state/decisions/007-adopt-uv.md"]) == "decision"

    def test_test_file_under_src_is_a_test_rather_than_implementation(self):
        m = _load_module()

        assert m.classify_event("Write", ["src/pkg/test_billing.py"]) == "test"

    def test_commit_of_a_test_related_change_is_a_commit_rather_than_a_test(self):
        m = _load_module()

        # The message mentions pytest; the *action* is still a commit.
        assert m.classify_event("Bash", [], "git commit -m 'wire up pytest config'") == "commit"


class TestCommandClassification:
    """A Bash call is classified by what its command line does."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("git commit -m 'wip'", "commit"),
            ("uv run pytest -q", "test"),
            ("python -m pytest tests/", "test"),
            ("ruff check --fix .", "lint"),
            ("mypy hooks/", "lint"),
            ("git push origin main", "git"),
            ("git rebase -i HEAD~3", "git"),
            ("uv pip install httpx", "dependency"),
            ("npm install", "dependency"),
            ("ls -la", "command"),
            ("", "command"),
        ],
    )
    def test_command_line_determines_the_classification(self, command: str, expected: str):
        m = _load_module()

        assert m.classify_event("Bash", [], command) == expected


class TestNonFileToolClassification:
    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("Agent", "delegation"),
            ("Skill", "tool_use"),
            ("WebFetch", "tool_use"),
        ],
    )
    def test_tool_without_a_file_or_command_surface(self, tool_name: str, expected: str):
        m = _load_module()

        assert m.classify_event(tool_name, []) == expected


# ---------------------------------------------------------------------------
# extract_file_paths — which input keys become `file_paths`
# ---------------------------------------------------------------------------


class TestFilePathExtraction:
    def test_reads_both_file_path_and_path_keys(self):
        m = _load_module()

        paths = m.extract_file_paths({"file_path": "a.py", "path": "b.py"}, "Write")

        assert paths == ["a.py", "b.py"]

    def test_does_not_repeat_a_path_named_by_both_keys(self):
        m = _load_module()

        paths = m.extract_file_paths({"file_path": "a.py", "path": "a.py"}, "Write")

        assert paths == ["a.py"]

    def test_grep_pattern_is_not_mistaken_for_a_file_path(self):
        m = _load_module()

        # A regex is not a path -- recording it as one would poison
        # `file_paths`, which downstream readers treat as real edited files.
        assert m.extract_file_paths({"pattern": r"def \w+\("}, "Grep") == []


# ---------------------------------------------------------------------------
# Summaries — bounded, and drawn from the most informative available field
# ---------------------------------------------------------------------------


class TestSummaryTruncation:
    def test_text_at_the_limit_is_left_intact(self):
        m = _load_module()
        exact = "x" * m.MAX_SUMMARY_LEN

        assert m._truncate(exact) == exact

    def test_text_past_the_limit_is_cut_and_marked_as_elided(self):
        m = _load_module()

        result = m._truncate("y" * (m.MAX_SUMMARY_LEN + 50))

        assert result.endswith("...")
        assert len(result) == m.MAX_SUMMARY_LEN + len("...")

    def test_empty_text_stays_empty(self):
        m = _load_module()

        assert m._truncate("") == ""


class TestSummaryContent:
    def test_bash_summary_prefers_the_human_description_over_the_raw_command(self):
        m = _load_module()

        summary = m.build_summary(
            "Bash",
            {"command": "rg -n 'TODO' --glob '!*.lock'", "description": "Find outstanding TODOs"},
            "command",
        )

        assert summary == "Find outstanding TODOs"

    def test_bash_summary_falls_back_to_the_command_when_undescribed(self):
        m = _load_module()

        assert m.build_summary("Bash", {"command": "ls -la"}, "command") == "ls -la"

    def test_agent_summary_names_the_subagent_and_its_description(self):
        m = _load_module()

        summary = m.build_summary(
            "Agent",
            {"subagent_type": "researcher", "description": "survey the auth layer"},
            "delegation",
        )

        assert summary == "Spawn researcher — survey the auth layer"

    def test_agent_summary_falls_back_to_a_prompt_preview_when_undescribed(self):
        m = _load_module()

        summary = m.build_summary(
            "Agent",
            {"subagent_type": "verifier", "prompt": "Check the refund invariants hold"},
            "delegation",
        )

        assert summary == "Spawn verifier — Check the refund invariants hold"

    def test_agent_summary_degrades_when_neither_type_nor_text_is_present(self):
        m = _load_module()

        assert m.build_summary("Agent", {}, "delegation") == "Spawn agent"

    def test_generic_tool_summary_lists_its_recognised_input_keys(self):
        m = _load_module()

        summary = m.build_summary("WebSearch", {"query": "fcntl flock semantics"}, "tool_use")

        assert summary == "query=fcntl flock semantics"

    def test_generic_tool_with_no_recognised_keys_falls_back_to_its_name(self):
        m = _load_module()

        assert m.build_summary("MysteryTool", {"unrecognised": "x"}, "tool_use") == "MysteryTool"


# ---------------------------------------------------------------------------
# build_observation — envelope fields the WAL readers depend on
# ---------------------------------------------------------------------------


class TestObservationEnvelope:
    def test_string_tool_input_is_tolerated_rather_than_indexed(self):
        m = _load_module()

        # A malformed payload must not make the observation unbuildable --
        # `main()` has no recovery path once `build_observation` raises.
        observation = m.build_observation(_tool_call_payload("Write", tool_input="not-a-dict"))

        assert observation["file_paths"] == []
        assert observation["tool_name"] == "Write"

    def test_tool_error_is_recorded_as_a_failed_outcome(self):
        m = _load_module()

        observation = m.build_observation(
            _tool_call_payload("Bash", {"command": "false"}, tool_response={"error": "exit 1"})
        )

        assert observation["outcome"] == "failure"

    def test_missing_agent_id_falls_back_to_the_session_id(self):
        m = _load_module()

        observation = m.build_observation(
            _tool_call_payload("Write", {"file_path": "a.py"}, session_id="sess-9", agent_id="")
        )

        assert observation["agent_id"] == "sess-9"

    def test_trace_context_surfaced_by_a_tool_is_carried_onto_the_row(self):
        m = _load_module()

        observation = m.build_observation(
            _tool_call_payload(
                "Bash",
                {"command": "true"},
                tool_response={
                    "additionalContext": {
                        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                        "span_id": "00f067aa0ba902b7",
                        "parent_span_id": "0020000000000001",
                    }
                },
            )
        )

        assert observation["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert observation["span_id"] == "00f067aa0ba902b7"
        assert observation["parent_span_id"] == "0020000000000001"

    def test_malformed_trace_context_degrades_to_empty_ids(self):
        m = _load_module()

        observation = m.build_observation(
            _tool_call_payload("Bash", {"command": "true"}, tool_response={"additionalContext": []})
        )

        assert observation["trace_id"] == ""
        assert observation["span_id"] == ""
        assert observation["parent_span_id"] == ""


# ---------------------------------------------------------------------------
# main() — what actually reaches the write-ahead log
# ---------------------------------------------------------------------------


class TestObservationsAreAppended:
    def test_a_captured_tool_call_lands_as_one_wal_row(
        self, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        payload = _tool_call_payload(
            "Write", {"file_path": "src/refund.py"}, cwd=str(isolated_project)
        )

        _drive_main(m, json.dumps(payload), monkeypatch)

        rows = _wal_rows(isolated_project)
        assert len(rows) == 1
        assert rows[0]["tool_name"] == "Write"
        assert rows[0]["classification"] == "implementation"
        assert rows[0]["file_paths"] == ["src/refund.py"]

    def test_successive_calls_append_rather_than_overwrite(
        self, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        first = _tool_call_payload("Write", {"file_path": "a.py"}, cwd=str(isolated_project))
        second = _tool_call_payload("Write", {"file_path": "b.py"}, cwd=str(isolated_project))

        _drive_main(m, json.dumps(first), monkeypatch)
        _drive_main(m, json.dumps(second), monkeypatch)

        assert [row["file_paths"] for row in _wal_rows(isolated_project)] == [["a.py"], ["b.py"]]


class TestObservationsAreSuppressed:
    @pytest.mark.parametrize("tool_name", ["Read", "Grep", "TodoWrite", "ToolSearch"])
    def test_high_noise_tools_are_never_recorded(
        self, tool_name: str, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        payload = _tool_call_payload(tool_name, {"file_path": "a.py"}, cwd=str(isolated_project))

        _drive_main(m, json.dumps(payload), monkeypatch)

        assert _wal_rows(isolated_project) == []

    def test_kill_switch_stops_all_recording(
        self, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        monkeypatch.setenv(m.DISABLE_OBSERVABILITY, "1")
        payload = _tool_call_payload("Write", {"file_path": "a.py"}, cwd=str(isolated_project))

        _drive_main(m, json.dumps(payload), monkeypatch)

        assert _wal_rows(isolated_project) == []

    def test_project_without_ai_state_is_left_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        # No `.ai-state/` here: the hook must degrade, not create the directory.
        payload = _tool_call_payload("Write", {"file_path": "a.py"}, cwd=str(tmp_path))

        _drive_main(m, json.dumps(payload), monkeypatch)

        assert not (tmp_path / ".ai-state").exists()

    def test_unparseable_stdin_records_nothing(
        self, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()

        _drive_main(m, "not-json-at-all", monkeypatch)

        assert _wal_rows(isolated_project) == []

    @pytest.mark.parametrize("payload_text", ["[]", "null", '"a bare string"', "123"])
    def test_well_formed_non_object_payload_records_nothing(
        self, payload_text: str, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()

        _drive_main(m, payload_text, monkeypatch)

        assert _wal_rows(isolated_project) == []


class TestHookNeverRaisesIntoTheHarness:
    """The script boundary must swallow everything -- it runs on every tool call.

    Driven through `runpy` so the `__main__` guard is exercised as a second,
    outer line of defense on top of `main()`'s own totality against
    well-formed non-object payloads (`[]`, `null`, a bare string, a bare
    number) -- see `TestObservationsAreSuppressed` for the in-process proof
    that `main()` itself no longer propagates on these inputs.
    """

    @pytest.mark.parametrize(
        "payload_text",
        ["not-json-at-all", "[]", "null", '"a bare string"', "123", ""],
    )
    def test_hostile_stdin_is_swallowed_at_the_script_boundary(
        self, payload_text: str, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))

        runpy.run_path(str(HOOK_SCRIPT_PATH), run_name="__main__")
