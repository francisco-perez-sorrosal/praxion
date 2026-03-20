"""Tests for decision_tracker.__main__ — CLI write and extract subcommands."""

from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from decision_tracker.__main__ import (
    DECISIONS_FILENAME,
    PENDING_FILENAME,
    _handle_extract,
    _handle_write,
    main,
)
from decision_tracker.schema import Decision, ExtractedDecision, PendingDecisions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_args(
    cwd: str,
    *,
    decision: str = "Use Redis for caching",
    category: str = "implementation",
    agent_type: str = "implementer",
    rationale: str | None = None,
    alternatives: list[str] | None = None,
    affected_reqs: list[str] | None = None,
    affected_files: list[str] | None = None,
    tier: str | None = None,
    session_id: str | None = None,
    branch: str | None = None,
    commit_sha: str | None = None,
) -> SimpleNamespace:
    """Build a namespace mimicking argparse output for the write subcommand."""
    return SimpleNamespace(
        command="write",
        decision=decision,
        category=category,
        agent_type=agent_type,
        rationale=rationale,
        alternatives=alternatives,
        affected_reqs=affected_reqs,
        affected_files=affected_files,
        tier=tier,
        session_id=session_id,
        branch=branch,
        commit_sha=commit_sha,
        cwd=cwd,
    )


def _make_hook_payload(
    command: str = "git commit -m 'test'",
    cwd: str = ".",
    session_id: str = "sess-abc",
    transcript_path: str = "",
) -> str:
    """Build a JSON hook payload string."""
    return json.dumps(
        {
            "tool_input": {"command": command},
            "cwd": cwd,
            "session_id": session_id,
            "transcript_path": transcript_path,
        }
    )


def _read_log_entries(log_path: Path) -> list[dict]:
    """Read all entries from a decisions.jsonl file."""
    if not log_path.is_file():
        return []
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            entries.append(json.loads(stripped))
    return entries


def _make_extracted_decision(**overrides: object) -> ExtractedDecision:
    """Build an ExtractedDecision with defaults."""
    fields = {
        "decision": "Use Redis for caching",
        "category": "architectural",
        "made_by": "agent",
        "confidence": 0.9,
        **overrides,
    }
    return ExtractedDecision(**fields)


# ---------------------------------------------------------------------------
# Write subcommand tests
# ---------------------------------------------------------------------------


class TestWriteCreatesEntry:
    def test_creates_log_file_with_entry(self, tmp_path: Path) -> None:
        args = _write_args(str(tmp_path))
        _handle_write(args)

        log_path = tmp_path / DECISIONS_FILENAME
        assert log_path.is_file()
        entries = _read_log_entries(log_path)
        assert len(entries) == 1
        assert entries[0]["decision"] == "Use Redis for caching"
        assert entries[0]["source"] == "agent"
        assert entries[0]["status"] == "documented"
        assert entries[0]["category"] == "implementation"

    def test_prints_confirmation_to_stderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        args = _write_args(str(tmp_path))
        _handle_write(args)

        captured = capsys.readouterr()
        assert "decision-tracker: recorded decision dec-" in captured.err


class TestWriteRequiredFieldsOnly:
    def test_minimal_args_produce_valid_entry(self, tmp_path: Path) -> None:
        args = _write_args(str(tmp_path))
        _handle_write(args)

        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"].startswith("dec-")
        assert "timestamp" in entry
        assert entry["made_by"] == "agent"
        assert entry["agent_type"] == "implementer"
        # Optional fields should not appear when None
        assert "rationale" not in entry
        assert "alternatives" not in entry


class TestWriteAllFields:
    def test_all_optional_args_included(self, tmp_path: Path) -> None:
        args = _write_args(
            str(tmp_path),
            rationale="Low latency",
            alternatives=["Memcached", "In-process"],
            affected_reqs=["REQ-03", "REQ-05"],
            affected_files=["src/cache.py"],
            tier="standard",
            session_id="sess-123",
            branch="feat/caching",
            commit_sha="abc1234",
        )
        _handle_write(args)

        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        entry = entries[0]
        assert entry["rationale"] == "Low latency"
        assert entry["alternatives"] == ["Memcached", "In-process"]
        assert entry["affected_reqs"] == ["REQ-03", "REQ-05"]
        assert entry["affected_files"] == ["src/cache.py"]
        assert entry["pipeline_tier"] == "standard"
        assert entry["session_id"] == "sess-123"
        assert entry["branch"] == "feat/caching"
        assert entry["commit_sha"] == "abc1234"


# ---------------------------------------------------------------------------
# Extract subcommand tests
# ---------------------------------------------------------------------------


class TestExtractNonCommitExitsZero:
    def test_non_commit_command_exits_immediately(self, tmp_path: Path) -> None:
        payload = _make_hook_payload(command="git push origin main", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        # No log file should be created
        log_path = tmp_path / DECISIONS_FILENAME
        assert not log_path.is_file()


class TestExtractMissingApiKeyExitsZero:
    def test_skipped_status_when_no_key(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        payload = _make_hook_payload(command="git commit -m 'test'", cwd=str(tmp_path))

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch("sys.stdin", StringIO(payload)), patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["status"] == "skipped"
        assert "ANTHROPIC_API_KEY" in output["message"]


class TestExtractGatingTierBlocks:
    @patch("decision_tracker.__main__._detect_branch", return_value="feat/test")
    @patch("decision_tracker.__main__._detect_commit_sha", return_value="abc123")
    @patch("decision_tracker.__main__.subprocess.run")
    def test_exit_2_and_pending_file_created(
        self,
        mock_subprocess: MagicMock,
        mock_sha: MagicMock,
        mock_branch: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        # Mock git diff --staged (mock_sha and mock_branch are consumed by @patch decorators)
        mock_subprocess.return_value = MagicMock(stdout="diff --staged content", returncode=0)

        extracted = [_make_extracted_decision()]
        payload = _make_hook_payload(command="git commit -m 'feat: add cache'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("decision_tracker.extractor.extract_decisions", return_value=extracted),
            patch("decision_tracker.tier.detect_tier", return_value="standard"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 2

        # Pending file should exist with decisions in "pending" status
        pending_path = tmp_path / PENDING_FILENAME
        assert pending_path.is_file()
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        assert pending["tier"] == "standard"
        assert len(pending["decisions"]) == 1
        assert pending["decisions"][0]["status"] == "pending"

        # stderr should have review_required
        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["status"] == "review_required"
        assert output["count"] == 1


class TestExtractNonGatingTierAutoApproves:
    @patch("decision_tracker.__main__._detect_branch", return_value="main")
    @patch("decision_tracker.__main__._detect_commit_sha", return_value="def456")
    @patch("decision_tracker.__main__.subprocess.run")
    def test_exit_0_and_entries_in_log(
        self,
        mock_subprocess: MagicMock,
        mock_sha: MagicMock,
        mock_branch: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        mock_subprocess.return_value = MagicMock(stdout="diff content", returncode=0)
        extracted = [_make_extracted_decision()]
        payload = _make_hook_payload(command="git commit -m 'quick fix'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("decision_tracker.extractor.extract_decisions", return_value=extracted),
            patch("decision_tracker.tier.detect_tier", return_value="direct"),
            patch("decision_tracker.tier.is_gating_tier", return_value=False),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        # Decision should be in log with auto-approved status
        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        assert len(entries) == 1
        assert entries[0]["status"] == "auto-approved"
        assert entries[0]["source"] == "hook"

        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["status"] == "auto_logged"


class TestExtractNoNovelDecisions:
    @patch("decision_tracker.__main__._detect_branch", return_value="main")
    @patch("decision_tracker.__main__._detect_commit_sha", return_value="def456")
    @patch("decision_tracker.__main__.subprocess.run")
    def test_exit_0_no_decisions(
        self,
        mock_subprocess: MagicMock,
        mock_sha: MagicMock,
        mock_branch: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        mock_subprocess.return_value = MagicMock(stdout="diff content", returncode=0)

        # Pre-populate the log with the same decision
        log_path = tmp_path / DECISIONS_FILENAME
        existing = Decision(
            status="documented",
            category="architectural",
            decision="Use Redis for caching",
            made_by="agent",
            source="hook",
        )
        from decision_tracker.log import append_decision

        append_decision(log_path, existing)

        extracted = [_make_extracted_decision(decision="Use Redis for caching")]
        payload = _make_hook_payload(command="git commit -m 'test'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("decision_tracker.extractor.extract_decisions", return_value=extracted),
            patch("decision_tracker.tier.detect_tier", return_value="direct"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["status"] == "no_decisions"


class TestExtractFailOpenOnError:
    def test_exit_0_with_error_status(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        payload = _make_hook_payload(command="git commit -m 'test'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "decision_tracker.__main__._run_extraction",
                side_effect=RuntimeError("LLM call failed"),
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["status"] == "error"
        assert "LLM call failed" in output["message"]


class TestExtractPendingResolution:
    def test_approved_pending_appended_and_file_deleted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Full review cycle: pending -> approved -> logged."""
        pending_path = tmp_path / PENDING_FILENAME
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        approved_decision = Decision(
            status="approved",
            category="architectural",
            decision="Use Redis for caching",
            made_by="agent",
            source="hook",
        )
        pending = PendingDecisions(
            tier="standard",
            session_id="sess-abc",
            decisions=[approved_decision],
        )
        pending_path.write_text(pending.model_dump_json(indent=2), encoding="utf-8")

        payload = _make_hook_payload(command="git commit -m 'approved'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        assert not pending_path.is_file()
        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        assert len(entries) == 1
        assert entries[0]["decision"] == "Use Redis for caching"
        assert entries[0]["status"] == "approved"

    def test_rejected_pending_logged_for_audit_trail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Rejected decisions are still logged for audit trail."""
        pending_path = tmp_path / PENDING_FILENAME
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        rejected_decision = Decision(
            status="rejected",
            category="implementation",
            decision="Use global mutable state",
            made_by="agent",
            source="hook",
            rejection_reason="Violates immutability principle",
        )
        pending = PendingDecisions(
            tier="standard",
            session_id="sess-abc",
            decisions=[rejected_decision],
        )
        pending_path.write_text(pending.model_dump_json(indent=2), encoding="utf-8")

        payload = _make_hook_payload(command="git commit -m 'reviewed'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        assert not pending_path.is_file()
        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        assert len(entries) == 1
        assert entries[0]["status"] == "rejected"
        assert entries[0]["rejection_reason"] == "Violates immutability principle"

    def test_mixed_approved_and_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Mix of approved and rejected in one review — both logged."""
        pending_path = tmp_path / PENDING_FILENAME
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        decisions = [
            Decision(
                status="approved",
                category="architectural",
                decision="Use Redis",
                made_by="agent",
                source="hook",
            ),
            Decision(
                status="rejected",
                category="implementation",
                decision="Use global state",
                made_by="agent",
                source="hook",
                rejection_reason="Bad practice",
            ),
        ]
        pending = PendingDecisions(tier="standard", decisions=decisions)
        pending_path.write_text(pending.model_dump_json(indent=2), encoding="utf-8")

        payload = _make_hook_payload(command="git commit -m 'mixed'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 0

        assert not pending_path.is_file()
        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        assert len(entries) == 2
        assert entries[0]["status"] == "approved"
        assert entries[1]["status"] == "rejected"

        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert "1 approved" in output["message"]
        assert "1 rejected" in output["message"]

    def test_unresolved_pending_blocks_again(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Pending decisions that haven't been reviewed still block."""
        pending_path = tmp_path / PENDING_FILENAME
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        unresolved = Decision(
            status="pending",
            category="architectural",
            decision="Use Redis",
            made_by="agent",
            source="hook",
        )
        pending = PendingDecisions(tier="standard", decisions=[unresolved])
        pending_path.write_text(pending.model_dump_json(indent=2), encoding="utf-8")

        payload = _make_hook_payload(command="git commit -m 'retry'", cwd=str(tmp_path))

        with (
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_extract(SimpleNamespace(command="extract"))
            assert exc_info.value.code == 2

        # Pending file should still exist
        assert pending_path.is_file()

        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["status"] == "review_required"
        assert output["count"] == 1


# ---------------------------------------------------------------------------
# Main / argparse integration tests
# ---------------------------------------------------------------------------


class TestMainWriteArgparse:
    def test_main_dispatches_write(self, tmp_path: Path) -> None:
        test_args = [
            "decision-tracker",
            "write",
            "--decision",
            "Test decision",
            "--category",
            "implementation",
            "--agent-type",
            "test",
            "--cwd",
            str(tmp_path),
        ]
        with patch("sys.argv", test_args):
            main()

        entries = _read_log_entries(tmp_path / DECISIONS_FILENAME)
        assert len(entries) == 1
        assert entries[0]["decision"] == "Test decision"


class TestMainExtractArgparse:
    def test_main_dispatches_extract(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        payload = _make_hook_payload(command="git push", cwd=str(tmp_path))
        test_args = ["decision-tracker", "extract"]

        with (
            patch("sys.argv", test_args),
            patch("sys.stdin", StringIO(payload)),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGitCommitPatternMatching:
    """Verify the regex correctly identifies git commit commands."""

    def test_simple_commit_matches(self) -> None:
        from decision_tracker.__main__ import GIT_COMMIT_PATTERN

        assert GIT_COMMIT_PATTERN.search("git commit -m 'test'")

    def test_commit_with_flags_matches(self) -> None:
        from decision_tracker.__main__ import GIT_COMMIT_PATTERN

        assert GIT_COMMIT_PATTERN.search("git -c user.name='test' commit -m 'test'")

    def test_non_commit_does_not_match(self) -> None:
        from decision_tracker.__main__ import GIT_COMMIT_PATTERN

        assert not GIT_COMMIT_PATTERN.search("git push origin main")
        assert not GIT_COMMIT_PATTERN.search("git status")
        assert not GIT_COMMIT_PATTERN.search("git log --oneline")
