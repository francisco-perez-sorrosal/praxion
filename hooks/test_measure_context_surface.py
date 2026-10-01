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

# Mirrors hooks/test_capture_observations.py's own sys.path-based import of a
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

    @pytest.mark.parametrize(
        "off_env",
        [{"PRAXION_OBSERVATION_LOG": "off"}, {"PRAXION_DISABLE_OBSERVABILITY": "1"}],
        ids=["new-key", "legacy-switch"],
    )
    def test_off_mode_never_measures_either_spelling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, off_env: dict
    ):
        """`off` returns before `measure()` (and so before `count_tokens`); the
        unset control must hit the spy, so an empty call list proves the
        early return rather than a spy off the path."""
        m = _load_module()
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        # Unset: a mis-bound spy falls through to the offline estimate, never the network.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        calls: list[Path] = []

        class SpyHitError(Exception):
            pass

        def spy(root: Path, **_kwargs: object) -> dict:
            calls.append(root)
            raise SpyHitError(str(root))

        monkeypatch.setattr(mtb, "measure", spy)
        payload = {"hook_event_name": "SessionStart", "cwd": str(tmp_path), "session_id": "x"}

        for key in ("PRAXION_OBSERVATION_LOG", "PRAXION_DISABLE_OBSERVABILITY"):
            monkeypatch.delenv(key, raising=False)
        for key, value in off_env.items():
            monkeypatch.setenv(key, value)
        self._stub_stdin(payload, monkeypatch)
        m.main()

        assert calls == []
        assert not (ai_state / "observations.jsonl").exists()

        for key in off_env:
            monkeypatch.delenv(key)
        self._stub_stdin(payload, monkeypatch)
        with pytest.raises(SpyHitError):
            m.main()

    def test_malformed_stdin_does_not_crash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        m = _load_module()
        monkeypatch.setattr(sys, "stdin", _StringIO("not-json{"))
        m.main()  # No raise = pass.

    def test_a_broken_measure_token_budget_import_fails_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        """The import lives inside main()'s own try/except specifically so a
        broken sys.path or plugin-cache layout (missing scripts/ sibling, a
        bad import inside measure_token_budget.py itself) degrades to a
        silent no-op instead of a crash -- proving the fail-open contract
        ("Exit 0 unconditionally.") actually covers the import, not just the
        code that runs after it.
        """
        m = _load_module()
        monkeypatch.setitem(sys.modules, "measure_token_budget", None)

        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)

        m.main()  # No raise = pass.

        assert not (ai_state / "observations.jsonl").exists()
        assert "import failed" in capsys.readouterr().err


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
        monkeypatch.setattr(
            m.writer, "record", lambda _dir, _event_class, row, **_kw: captured.append(row)
        )

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


class TestStartedBelowTheProjectRoot:
    def test_measures_the_project_root_and_names_it_when_started_in_a_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".ai-state").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
        below = tmp_path / "src" / "pkg"
        below.mkdir(parents=True)
        payload = {"hook_event_name": "SessionStart", "cwd": str(below), "session_id": "sub"}
        monkeypatch.setattr(sys, "stdin", _StringIO(json.dumps(payload)))

        m.main()

        obs_path = tmp_path / ".ai-state" / "observations.jsonl"
        (row,) = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]
        assert row["project"] == tmp_path.name
        assert any(p.endswith("CLAUDE.md") for p in row["file_paths"])
        assert not (below / ".ai-state").exists()

    @pytest.mark.parametrize("cwd", [None, "", 7, "absent"])
    def test_records_nothing_without_a_usable_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cwd
    ):
        m = _load_module()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / ".ai-state").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)  # the old process-directory fallback would have recorded
        payload = {"hook_event_name": "SessionStart", "session_id": "no-cwd"}
        if cwd != "absent":
            payload["cwd"] = cwd
        monkeypatch.setattr(sys, "stdin", _StringIO(json.dumps(payload)))

        m.main()

        assert not (tmp_path / ".ai-state" / "observations.jsonl").exists()


class TestWritesThroughTheOwnerWriter:
    """The measurement row goes through the observation log's owner writer,
    not a private appender: it rotates like every other writer and appends
    after existing rows under the shared lock. Before the owner package, this
    hook carried its own non-rotating appender, so the log could grow past
    the rotation threshold unchecked.
    """

    def _run_session_start(self, project: Path, monkeypatch: pytest.MonkeyPatch):
        m = _load_module()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (project / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(project),
            "session_id": "owner-writer",
            "agent_type": "main",
        }
        monkeypatch.setattr(sys, "stdin", _StringIO(json.dumps(payload)))
        return m

    def test_rotates_an_oversized_log_like_every_other_writer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        obs_path = ai_state / "observations.jsonl"
        obs_path.write_text('{"event_type":"tool_use"}\n', encoding="utf-8")
        m = self._run_session_start(tmp_path, monkeypatch)
        monkeypatch.setattr(m.writer, "OBSERVATIONS_MAX_BYTES", 1)

        m.main()

        assert (ai_state / "observations.jsonl.1").exists(), "the oversized log must rotate"
        rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]
        assert [r["event_type"] for r in rows] == ["context_surface_measurement"]

    def test_appends_after_existing_rows_under_the_shared_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        obs_path = ai_state / "observations.jsonl"
        obs_path.write_text('{"event_type":"tool_use"}\n', encoding="utf-8")
        m = self._run_session_start(tmp_path, monkeypatch)

        m.main()

        rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]
        assert [r["event_type"] for r in rows] == ["tool_use", "context_surface_measurement"]
        assert (ai_state / "observations.lock").exists(), "the append must take the shared lock"


class _StringIO:
    """Minimal stdin stub — sys.stdin.read() returns the captured string."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self, *_args: object) -> str:
        return self._text
