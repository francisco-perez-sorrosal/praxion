"""Tests for hooks/capture_session.py — the observations-WAL lifecycle writer.

`.ai-state/observations.jsonl` is the recovery write-ahead log dec-248
designates, and its job is to *localize* a truncated pipeline step: which agent
stopped, and where it last wrote. A row that cannot name its agent cannot
localize anything.

Gate-liveness contract (rules/swe/gate-liveness.md): the emitter's agent
resolution is a CODE gate — it must turn an unnameable subagent termination
into an explicitly flagged row rather than a silently blank one. Every canary
below feeds a **known-bad** payload (the exact shape measured in the live WAL:
`agent_type` present-but-empty, no prior `agent_start`, no `tool_use` rows) and
asserts the gap is *detected and named*. Each canary is paired with an inverse
guard that feeds a resolvable payload and asserts the detector stays silent —
ruling out both "never flags" and "flags unconditionally".
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "capture_session.py"


def _load_module():
    """Load capture_session.py as a module inside a test body."""
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location("capture_session", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# WAL fragment helpers — rows are built at runtime in tmp_path, never committed
# ---------------------------------------------------------------------------


def _wal_row(**overrides: object) -> dict:
    """One observations.jsonl row with the envelope every reader expects."""
    row: dict = {
        "timestamp": "2026-08-06T18:00:00+00:00",
        "session_id": "sess-1",
        "agent_type": "i-am:implementer",
        "agent_id": "agent-1",
        "project": "praxion",
        "event_type": "tool_use",
        "tool_name": "Write",
        "summary": "Write src/thing.py",
        "file_paths": ["src/thing.py"],
        "outcome": "success",
        "classification": "implementation",
    }
    row.update(overrides)
    return row


def _write_wal(obs_path: Path, rows: list[dict]) -> Path:
    """Materialize a WAL fragment on disk and return its path."""
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    obs_path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )
    return obs_path


def _read_wal(obs_path: Path) -> list[dict]:
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]


def unnameable_lifecycle_rows(rows: list[dict]) -> list[dict]:
    """Detector: WAL lifecycle rows that cannot say which agent they describe.

    This is the check the sentinel's pipeline dimension performs against the
    live WAL. A row is unnameable when its `agent_type` is blank, or when it is
    an explicit `unknown` the emitter could not resolve. Rows the emitter
    resolved (payload / wal-backfill / session-default) are nameable.
    """
    findings = []
    for row in rows:
        if row.get("event_type") not in ("agent_start", "agent_stop"):
            continue
        agent_type = str(row.get("agent_type") or "").strip()
        if not agent_type or agent_type == "unknown":
            findings.append(row)
    return findings


def _stop_payload(cwd: Path, **overrides: object) -> dict:
    payload: dict = {
        "hook_event_name": "SubagentStop",
        "session_id": "sess-1",
        "agent_id": "agent-orphan",
        "agent_type": "",  # present-but-empty: the measured harness shape
        "cwd": str(cwd),
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A directory that looks like a Praxion-managed project."""
    (tmp_path / ".ai-state").mkdir()
    return tmp_path


def _run_main(module, payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive main() in-process with the payload on stdin."""
    monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    module.main()


# ---------------------------------------------------------------------------
# Canaries — a WAL fragment carrying an orphaned agent_stop must be DETECTED
# ---------------------------------------------------------------------------


class TestOrphanedStopIsDetected:
    def test_orphaned_stop_with_blank_agent_type_is_flagged_not_written_blank(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CANARY: the measured defect shape, end to end.

        The WAL fragment holds an orphaned `agent_stop` (blank `agent_type`, no
        matching `agent_start`, no `tool_use` rows) — the row shape found 6
        times in the live WAL. A `SubagentStop` for a second such agent then
        arrives. The emitted row must NAME the gap: `agent_type` resolves to the
        explicit `unknown` sentinel with `agent_type_source == "unresolved"`.

        Reverting the fix (writing `payload.get("agent_type", "main")` straight
        through) emits `agent_type == ""` with no source field, and every
        assertion below fails.
        """
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        _write_wal(
            obs_path,
            [
                _wal_row(
                    event_type="agent_stop",
                    agent_type="",
                    agent_id="already-orphaned",
                    tool_name=None,
                    file_paths=[],
                )
            ],
        )

        _run_main(module, _stop_payload(project), monkeypatch)

        emitted = _read_wal(obs_path)[-1]
        assert emitted["event_type"] == "agent_stop"
        assert emitted["agent_type"] == module.UNKNOWN_AGENT_TYPE
        assert emitted["agent_type_source"] == module.SOURCE_UNRESOLVED
        assert emitted["agent_type"] != "", "a blank agent_type is the defect, not the fallback"

    def test_detector_flags_the_orphaned_row_in_the_resulting_wal(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CANARY: the WAL-level detector fires on the known-bad fragment.

        Paired with `test_detector_stays_silent_on_a_resolvable_wal` below: same
        detector, same fixture shape, the only variable is whether the agent is
        nameable. That pairing is what proves the detector discriminates rather
        than flagging (or ignoring) everything.
        """
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        _write_wal(obs_path, [])

        _run_main(module, _stop_payload(project), monkeypatch)

        findings = unnameable_lifecycle_rows(_read_wal(obs_path))
        assert len(findings) == 1, "the orphaned agent_stop must be detected"
        assert findings[0]["agent_id"] == "agent-orphan"

    def test_detector_stays_silent_on_a_resolvable_wal(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """INVERSE GUARD: a nameable termination produces no finding."""
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        _write_wal(obs_path, [])

        _run_main(module, _stop_payload(project, agent_type="i-am:verifier"), monkeypatch)

        assert unnameable_lifecycle_rows(_read_wal(obs_path)) == []

    @pytest.mark.parametrize(
        "hook_event",
        ["SessionStart", "Stop", "SubagentStart", "SubagentStop"],
    )
    @pytest.mark.parametrize("agent_type_field", [{}, {"agent_type": ""}, {"agent_type": "   "}])
    def test_no_row_is_ever_written_with_a_blank_agent_type(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        hook_event: str,
        agent_type_field: dict,
    ) -> None:
        """CANARY: blank `agent_type` is unreachable across every hook event.

        Absent, empty, and whitespace-only all resolve to something a reader can
        act on — the invariant the WAL's localization job depends on.
        """
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        payload = {
            "hook_event_name": hook_event,
            "session_id": "sess-1",
            "agent_id": "agent-9",
            "cwd": str(project),
            **agent_type_field,
        }

        _run_main(module, payload, monkeypatch)

        emitted = _read_wal(obs_path)[-1]
        assert emitted["agent_type"].strip(), f"{hook_event} wrote a blank agent_type"
        assert emitted["agent_type_source"]


# ---------------------------------------------------------------------------
# Backfill — a dropped SubagentStart is recoverable from an earlier row
# ---------------------------------------------------------------------------


class TestWalBackfill:
    def test_blank_stop_recovers_agent_type_from_an_earlier_start_row(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        _write_wal(
            obs_path,
            [
                _wal_row(
                    event_type="agent_start",
                    agent_type="i-am:test-engineer",
                    agent_id="agent-orphan",
                )
            ],
        )

        _run_main(module, _stop_payload(project), monkeypatch)

        emitted = _read_wal(obs_path)[-1]
        assert emitted["agent_type"] == "i-am:test-engineer"
        assert emitted["agent_type_source"] == module.SOURCE_WAL_BACKFILL

    def test_blank_stop_recovers_agent_type_from_a_tool_use_row(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dropped `SubagentStart` capture is still recoverable.

        This hook is async and can be killed; the PostToolUse writer is a
        separate process. Every real subagent in the measured WAL emitted 2-76
        `tool_use` rows carrying the correct agent_type, so one is enough.
        """
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        _write_wal(
            obs_path,
            [_wal_row(agent_type="i-am:doc-engineer", agent_id="agent-orphan")],
        )

        _run_main(module, _stop_payload(project), monkeypatch)

        assert _read_wal(obs_path)[-1]["agent_type"] == "i-am:doc-engineer"

    def test_backfill_uses_the_most_recent_matching_row(self, project: Path) -> None:
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [
                _wal_row(agent_type="i-am:researcher", agent_id="agent-1"),
                _wal_row(agent_type="i-am:implementer", agent_id="agent-1"),
            ],
        )
        assert module.lookup_agent_type(obs_path, "agent-1") == "i-am:implementer"

    def test_backfill_ignores_rows_for_other_agents(self, project: Path) -> None:
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [_wal_row(agent_type="i-am:researcher", agent_id="somebody-else")],
        )
        assert module.lookup_agent_type(obs_path, "agent-1") == ""

    def test_backfill_ignores_prior_unknown_sentinels(self, project: Path) -> None:
        """An earlier `unknown` is not evidence — it must not propagate."""
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [_wal_row(agent_type="unknown", agent_id="agent-1")],
        )
        assert module.lookup_agent_type(obs_path, "agent-1") == ""

    def test_backfill_survives_a_torn_line_from_a_concurrent_append(self, project: Path) -> None:
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [_wal_row(agent_type="i-am:verifier", agent_id="agent-1")],
        )
        with open(obs_path, "a", encoding="utf-8") as handle:
            handle.write('{"agent_id": "agent-1", "agent_ty')  # torn mid-write
        assert module.lookup_agent_type(obs_path, "agent-1") == "i-am:verifier"

    def test_backfill_skips_non_object_rows(self, project: Path) -> None:
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        obs_path.parent.mkdir(parents=True, exist_ok=True)
        obs_path.write_text(
            '["not", "a", "row"]\n\n'
            + json.dumps(_wal_row(agent_type="i-am:sentinel", agent_id="agent-1"))
            + "\n",
            encoding="utf-8",
        )
        assert module.lookup_agent_type(obs_path, "agent-1") == "i-am:sentinel"

    def test_backfill_returns_empty_for_a_missing_wal(self, tmp_path: Path) -> None:
        module = _load_module()
        assert module.lookup_agent_type(tmp_path / "nope.jsonl", "agent-1") == ""

    def test_backfill_returns_empty_without_an_agent_id(self, project: Path) -> None:
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [_wal_row(agent_id="agent-1")],
        )
        assert module.lookup_agent_type(obs_path, "") == ""

    def test_backfill_returns_empty_without_a_wal_path(self) -> None:
        module = _load_module()
        assert module.lookup_agent_type(None, "agent-1") == ""

    def test_tail_window_drops_the_record_it_cut_in_half(self, project: Path) -> None:
        """A window starting mid-file must not parse the fragment it split.

        Discarding the first line is what keeps a half-record from being read as
        data; the row that survives is the one wholly inside the window.
        """
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [
                _wal_row(agent_type="i-am:researcher", agent_id="agent-1"),
                _wal_row(agent_type="i-am:implementer", agent_id="agent-1"),
            ],
        )
        whole = obs_path.read_text(encoding="utf-8")
        window = len(whole.splitlines()[-1]) + 10  # slices into the first record

        lines = module._tail_lines(obs_path, max_bytes=window)

        assert len(lines) == 1
        assert json.loads(lines[0])["agent_type"] == "i-am:implementer"

    def test_tail_window_larger_than_the_file_keeps_every_line(self, project: Path) -> None:
        module = _load_module()
        obs_path = _write_wal(
            project / ".ai-state" / "observations.jsonl",
            [_wal_row(agent_id="a"), _wal_row(agent_id="b")],
        )
        assert len(module._tail_lines(obs_path, max_bytes=1_000_000)) == 2


# ---------------------------------------------------------------------------
# Resolution — provenance is recorded for every path
# ---------------------------------------------------------------------------


class TestAgentTypeResolution:
    def test_supplied_agent_type_is_used_verbatim_and_marked_as_payload(self) -> None:
        module = _load_module()
        agent_type, source = module.resolve_agent_type(
            {"agent_type": "i-am:verifier"}, "agent_stop"
        )
        assert (agent_type, source) == ("i-am:verifier", module.SOURCE_PAYLOAD)

    def test_supplied_agent_type_is_stripped_of_surrounding_whitespace(self) -> None:
        module = _load_module()
        agent_type, _ = module.resolve_agent_type({"agent_type": "  i-am:verifier "}, "agent_stop")
        assert agent_type == "i-am:verifier"

    @pytest.mark.parametrize("event_type", ["session_start", "session_stop"])
    def test_session_rows_resolve_to_main_with_a_named_source(self, event_type: str) -> None:
        """A session row's agent is known, not guessed — record which it is."""
        module = _load_module()
        agent_type, source = module.resolve_agent_type({}, event_type)
        assert (agent_type, source) == (module.MAIN_AGENT_TYPE, module.SOURCE_SESSION_DEFAULT)

    def test_subagent_row_never_falls_back_to_main(self) -> None:
        """`main` on a subagent row is an actively wrong answer, not a default."""
        module = _load_module()
        agent_type, _ = module.resolve_agent_type({"agent_id": "a-1"}, "agent_stop")
        assert agent_type != module.MAIN_AGENT_TYPE
        assert agent_type == module.UNKNOWN_AGENT_TYPE


class TestAgentIdResolution:
    def test_supplied_agent_id_is_used(self) -> None:
        module = _load_module()
        assert module.resolve_agent_id({"agent_id": "a-1", "session_id": "s-1"}) == "a-1"

    def test_missing_agent_id_falls_back_to_session_id(self) -> None:
        module = _load_module()
        assert module.resolve_agent_id({"session_id": "s-1"}) == "s-1"

    def test_no_identifier_at_all_yields_the_explicit_sentinel(self) -> None:
        module = _load_module()
        assert module.resolve_agent_id({}) == module.UNKNOWN_AGENT_ID

    def test_emitted_row_always_carries_a_non_empty_agent_id(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"
        payload = {"hook_event_name": "SubagentStop", "cwd": str(project)}

        _run_main(module, payload, monkeypatch)

        assert _read_wal(obs_path)[-1]["agent_id"] == module.UNKNOWN_AGENT_ID


# ---------------------------------------------------------------------------
# Summary text
# ---------------------------------------------------------------------------


class TestSummary:
    @pytest.mark.parametrize(
        ("event_type", "expected"),
        [("session_start", "Session started"), ("session_stop", "Session ended")],
    )
    def test_session_summaries_are_fixed_strings(self, event_type: str, expected: str) -> None:
        module = _load_module()
        assert module.build_summary(event_type, {}, "main") == expected

    def test_agent_summary_prefers_the_description(self) -> None:
        module = _load_module()
        summary = module.build_summary("agent_start", {"description": "Audit the hooks"}, "unknown")
        assert summary == "Agent started: Audit the hooks"

    def test_agent_summary_falls_back_to_the_resolved_agent_type(self) -> None:
        module = _load_module()
        assert module.build_summary("agent_stop", {}, "i-am:sentinel") == (
            "Agent completed: i-am:sentinel"
        )

    def test_agent_summary_truncates_a_long_description(self) -> None:
        module = _load_module()
        summary = module.build_summary("agent_stop", {"description": "x" * 400}, "unknown")
        assert summary == "Agent completed: " + "x" * 150

    def test_unmapped_event_type_returns_itself(self) -> None:
        module = _load_module()
        assert module.build_summary("recovery", {}, "main") == "recovery"


# ---------------------------------------------------------------------------
# Row envelope — downstream readers depend on the field set
# ---------------------------------------------------------------------------


class TestObservationEnvelope:
    def test_row_carries_every_field_downstream_readers_expect(self, project: Path) -> None:
        module = _load_module()
        row = module.build_observation(
            {
                "session_id": "sess-1",
                "agent_id": "agent-1",
                "agent_type": "i-am:implementer",
                "cwd": str(project),
            },
            "agent_start",
        )
        assert set(row) == {
            "timestamp",
            "session_id",
            "agent_type",
            "agent_id",
            "project",
            "event_type",
            "tool_name",
            "summary",
            "file_paths",
            "outcome",
            "classification",
            "agent_type_source",
        }
        assert row["project"] == project.name
        assert row["tool_name"] is None
        assert row["file_paths"] == []

    def test_row_timestamp_is_utc_iso8601(self, project: Path) -> None:
        module = _load_module()
        row = module.build_observation({"cwd": str(project)}, "session_start")
        assert row["timestamp"].endswith("+00:00")

    def test_building_a_row_without_a_wal_path_does_no_io(self) -> None:
        """`obs_path=None` is the pure path — resolution degrades, never raises."""
        module = _load_module()
        row = module.build_observation({"agent_id": "a-1"}, "agent_stop", None)
        assert row["agent_type_source"] == module.SOURCE_UNRESOLVED


# ---------------------------------------------------------------------------
# main() — hook contract: exit 0, never block, degrade gracefully
# ---------------------------------------------------------------------------


class TestMainContract:
    def test_appends_one_row_per_invocation(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"

        _run_main(module, _stop_payload(project, agent_type="i-am:verifier"), monkeypatch)
        _run_main(module, _stop_payload(project, agent_type="i-am:verifier"), monkeypatch)

        assert len(_read_wal(obs_path)) == 2

    def test_observability_opt_out_writes_nothing(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()
        monkeypatch.setenv("PRAXION_DISABLE_OBSERVABILITY", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_stop_payload(project))))

        module.main()

        assert not (project / ".ai-state" / "observations.jsonl").exists()

    def test_malformed_stdin_writes_nothing_and_does_not_raise(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json {{{"))

        module.main()

        assert not (project / ".ai-state" / "observations.jsonl").exists()

    def test_non_object_payload_writes_nothing(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        monkeypatch.setattr(sys, "stdin", io.StringIO('["a", "list"]'))

        module.main()

        assert not (project / ".ai-state" / "observations.jsonl").exists()

    def test_unmapped_hook_event_writes_nothing(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()

        _run_main(module, {"hook_event_name": "PreToolUse", "cwd": str(project)}, monkeypatch)

        assert not (project / ".ai-state" / "observations.jsonl").exists()

    def test_project_without_ai_state_degrades_silently(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_module()

        _run_main(module, _stop_payload(tmp_path), monkeypatch)

        assert not (tmp_path / ".ai-state").exists()

    @pytest.mark.parametrize(
        ("hook_event", "event_type"),
        [
            ("SessionStart", "session_start"),
            ("Stop", "session_stop"),
            ("SubagentStart", "agent_start"),
            ("SubagentStop", "agent_stop"),
        ],
    )
    def test_each_hook_event_maps_to_its_wal_event_type(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        hook_event: str,
        event_type: str,
    ) -> None:
        module = _load_module()
        obs_path = project / ".ai-state" / "observations.jsonl"

        _run_main(module, {"hook_event_name": hook_event, "cwd": str(project)}, monkeypatch)

        assert _read_wal(obs_path)[-1]["event_type"] == event_type
