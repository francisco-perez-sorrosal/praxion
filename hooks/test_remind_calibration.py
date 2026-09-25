"""Tests for remind_calibration.py -- commit-time AND Stop-time calibration reminders.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate advising on
calibration-log lag. It ships canaries -- known-lagging / known-qualifying fixtures --
and asserts the reminder fires, proving the gate is not merely a no-op that always
passes on the current good state.

Two independent trigger paths share one hook script:

1. **Commit-time path** (PreToolUse on `git commit`, pre-existing): reuses
   check_calibration_coverage.py::compute_coverage in-process and fires only when ALL
   of the following hold: the pending command is a git commit,
   .ai-state/calibration_log.md exists, the lag reaches K=2 uncalibrated
   task-completing commits, the session is not inside a linked worktree, and the
   pending commit message does not start with bump: or chore(finalize). The reminder
   is emitted via `hookSpecificOutput.additionalContext` on stdout (NOT stderr --
   stderr at exit 0 is shown only in verbose mode and never reaches the model; see
   skills/hook-crafting/references/output-patterns.md and SKILL.md Gotchas).
2. **Stop-time path** (new): fires at most once per session, only when ALL hold: the
   project is managed (.ai-state/ exists), the session is outside a linked worktree,
   `stop_hook_active` is false, this session's WAL carries >= 1 qualifying tool_use
   row (Edit/Write/MultiEdit/NotebookEdit) on a path outside .ai-state/, .ai-work/,
   .claude/, .ai-state/calibration_log.md is unchanged vs HEAD and untouched by this
   session, and no earlier Stop reminder fired this session (deduped via the existing
   record_gate_fire mechanism, hook name "remind_calibration_stop"). Emits
   `{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}` on
   stdout, exit 0. Any condition false, or any error, produces empty stdout and exit 0
   (fail-open, silent).

Hermetic-git-repo pattern (template: scripts/test_check_calibration_coverage.py):
every test builds its own temporary git repo via tmp_path, with git identity
configured and an injected .ai-state/calibration_log.md fixture. The real Praxion
calibration_log.md is never read.

Subprocess harness (template: hooks/test_inject_rules.py): the hook is invoked as
a real subprocess with a JSON payload on stdin, mirroring exactly how commit_gate.sh
(commit-time) or the harness itself (Stop-time) dispatches it.

Real Stop payload shape (template: hooks/test_capture_session.py, e.g. its
TestOrphanedStopIsDetected / TestStopSourceProvenance fixtures): `{"hook_event_name":
"Stop", "session_id": ..., "cwd": ..., "transcript_path": ..., "stop_hook_active":
...}` -- reused verbatim below rather than invented.

BDD/TDD RED handshake: hooks/remind_calibration.py has no Stop branch and still emits
via stderr on the commit-time path -- every test below that exercises either the new
Stop path or the additionalContext channel switch fails against the current hook
(empty/absent additionalContext) until the implementer lands both changes.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent
_HOOK_PATH = _HOOKS_DIR / "remind_calibration.py"

# Calibration log header matching the real .ai-state/calibration_log.md format.
_CALIBRATION_HEADER = """\
# Calibration Log

Append-only tier-selection log. Each Standard/Full pipeline appends one row.

| Timestamp | Task | Signals | Recommended Tier | Actual Tier | Source | Retrospective |
|-----------|------|---------|------------------|-------------|--------|----------------|
"""


# -- Git / repo helpers -------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> Path:
    """Initialise a bare-minimum git repo suitable for git-log queries."""
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "commit.gpgsign", "false")
    return path


def _write_calibration_log(repo: Path, newest_timestamp: str) -> None:
    """Write a synthetic calibration_log.md with one row at newest_timestamp."""
    state_dir = repo / ".ai-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    row = (
        f"| {newest_timestamp} | wave-test | signals | Standard | Standard"
        " | test | retrospective |\n"
    )
    (state_dir / "calibration_log.md").write_text(_CALIBRATION_HEADER + row, encoding="utf-8")


def _make_commit(repo: Path, message: str) -> None:
    """Create a file change and commit it with the given message."""
    sentinel_file = repo / "dummy.txt"
    current = sentinel_file.read_text() if sentinel_file.exists() else ""
    sentinel_file.write_text(current + f"{message}\n", encoding="utf-8")
    _git(repo, "add", "dummy.txt")
    _git(repo, "commit", "-m", message)


def _build_lagging_repo(tmp_path: Path) -> Path:
    """A hermetic repo with a far-past calibration log and 2 uncalibrated task commits.

    Matches the known-bad canary fixture in test_check_calibration_coverage.py:
    calibration_log.md dated 2025-01-01, plus two feat: commits landed since --
    reaching the K=2 under-coverage threshold.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_calibration_log(repo, "2025-01-01")
    _git(repo, "add", ".ai-state")
    _git(repo, "commit", "-m", "chore: add calibration baseline")
    _make_commit(repo, "feat: add authentication service")
    _make_commit(repo, "feat: add payment gateway integration")
    return repo


# -- Hook invocation helpers ---------------------------------------------------


def _run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke remind_calibration.py as a subprocess, mirroring commit_gate.sh's dispatch.

    Payload shape matches remind_adr.py's stdin contract exactly: a JSON object with
    tool_input.command. The subprocess cwd stands in for the shell cwd commit_gate.sh
    runs from during a real `git commit`.
    """
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


def _additional_context(result: subprocess.CompletedProcess[str]) -> str:
    """Extract the additionalContext string from the hook's stdout JSON.

    Accepts both output-patterns.md shapes: the flat `{"additionalContext": "..."}`
    and the structured `{"hookSpecificOutput": {"additionalContext": "..."}}` --
    matches hooks/test_inject_rules.py's own helper. Returns "" when stdout is empty
    (no reminder fired). Raises if stdout is non-empty but not valid JSON.
    """
    stdout = result.stdout.strip()
    if not stdout:
        return ""
    parsed = json.loads(stdout)
    if "additionalContext" in parsed:
        return parsed["additionalContext"]
    return parsed.get("hookSpecificOutput", {}).get("additionalContext", "")


def _run_hook_raw_stdin(raw_input: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke remind_calibration.py with an arbitrary raw stdin body (non-JSON cases)."""
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


# -- Tests ----------------------------------------------------------------------


def test_flags_lagging_calibration_log(tmp_path: Path) -> None:
    """Gate-liveness canary: a known-lagging fixture must fire the additionalContext reminder.

    Scenario: calibration_log.md dated 2025-01-01, two feat: commits landed since
    (the K=2 threshold reached), and the pending commit (on stdin) is itself another
    feat: commit with no suppression predicate active. A gate that never fires on
    known-bad input is indistinguishable from no gate (rules/swe/gate-liveness.md).

    Self-test: if the hook's lag check were gutted, stdout would stay empty and this
    test would fail. The contrast against the test_suppresses_reminder_* tests below
    (same lagging fixture, only the suppression predicate varies) rules out a hook
    that fires unconditionally regardless of coverage state.

    Channel: the reminder must reach the model via `additionalContext`, not stderr --
    stderr at exit 0 is shown only in verbose mode and never reaches Claude (this is
    the defect the Stop-time reminder work narrows; see module docstring).
    """
    repo = _build_lagging_repo(tmp_path)

    result = _run_hook('git commit -m "feat: add rate limiting"', repo)

    assert result.returncode == 0, "the hook must always exit 0 (fail-open, advisory-only)"
    context = _additional_context(result)
    assert context != "", (
        "a lagging calibration log with an unsuppressed pending commit must "
        "produce an additionalContext reminder"
    )
    assert "calibration_log.md" in context, (
        "the reminder must point at .ai-state/calibration_log.md"
    )
    assert "retrospective" in context.lower(), (
        "the reminder must name the Retrospective cell as the micro-capture slot"
    )


def test_suppresses_reminder_inside_linked_worktree(tmp_path: Path) -> None:
    """A linked worktree suppresses the reminder even when the calibration log lags.

    Direct-tier work happens only in the canonical checkout (isolation table);
    linked (pipeline/scratch) worktrees append their calibration row at pipeline
    completion, not per-commit, so per-commit nudging inside one would be noise.
    """
    main_repo = _build_lagging_repo(tmp_path)
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(main_repo), "worktree", "add", "-q", str(linked), "-b", "feature"],
        check=True,
        capture_output=True,
        text=True,
    )

    result = _run_hook('git commit -m "feat: work done inside the worktree"', linked)

    assert result.returncode == 0
    assert _additional_context(result) == "", (
        "a linked worktree must suppress the reminder even with a lagging "
        f"calibration log; got stdout={result.stdout!r}"
    )


@pytest.mark.parametrize(
    "message",
    [
        'git commit -m "bump: version 0.11.3 -> 0.12.0"',
        'git commit -m "chore(finalize): promote draft ADR to dec-999"',
    ],
    ids=["bump", "chore-finalize"],
)
def test_suppresses_reminder_for_release_and_finalize_commits(tmp_path: Path, message: str) -> None:
    """bump: and chore(finalize) commits suppress the reminder even when lagging.

    Release-automation and ADR-finalize bookkeeping commits are not task-completing
    work (mirrors the _EXCLUDED_PREFIXES exclusion in check_calibration_coverage.py);
    nudging on them would be pure noise on every version bump or ADR promotion.
    """
    repo = _build_lagging_repo(tmp_path)

    result = _run_hook(message, repo)

    assert result.returncode == 0
    assert _additional_context(result) == "", (
        "bump:/chore(finalize) pending commits must suppress the reminder even "
        f"with a lagging calibration log; got stdout={result.stdout!r}"
    )


def test_silent_when_calibration_log_absent(tmp_path: Path) -> None:
    """Absent .ai-state/calibration_log.md produces no output and exit 0.

    Existence-gating (inherited from compute_coverage's covered=True-when-absent
    behavior): a project that has never onboarded the calibration log has no
    baseline to nudge against and must not be penalised at bootstrap.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _make_commit(repo, "feat: initial commit -- no calibration log exists yet")

    result = _run_hook('git commit -m "feat: second commit, still no log"', repo)

    assert result.returncode == 0
    assert _additional_context(result) == "", (
        f"absent calibration_log.md must produce no reminder; got stdout={result.stdout!r}"
    )


def test_malformed_stdin_json_never_raises(tmp_path: Path) -> None:
    """Malformed stdin JSON never raises and always exits 0 (fail-open).

    Mirrors remind_adr.py's contract: main() is wrapped in except Exception: pass so
    a hook bug can never wedge or block a commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    result = _run_hook_raw_stdin("not-json{{{", repo)

    assert result.returncode == 0, "malformed stdin must never cause a non-zero exit"
    assert "Traceback" not in result.stderr, (
        f"malformed stdin must not leak a Python traceback; got stderr={result.stderr!r}"
    )


def test_resolves_consumer_repo_root_via_git(tmp_path: Path) -> None:
    """Structural: the consumer repo root must be resolved via git, not __file__.

    Mirrors the structural-assertion style in
    test_check_calibration_coverage.py::test_runs_to_verdict_without_sentinel.
    remind_calibration.py is reached through a symlinked plugin-cache install in
    every managed project's commit_gate.sh chain -- Path(__file__).resolve() would
    follow the symlink back to the PLUGIN's own checkout, not the consumer repo (the
    plugin-cache lesson), silently pointing the reminder at the wrong calibration
    log. __file__ is legitimate ONLY to locate the sibling scripts/ module for the
    in-process compute_coverage import -- never to resolve the consumer repo root,
    which must come from `git rev-parse --show-toplevel`
    (e.g. via scripts/_repo_root.py::git_toplevel_from_cwd).
    """
    source = _HOOK_PATH.read_text(encoding="utf-8")

    assert "show-toplevel" in source or "git_toplevel_from_cwd" in source, (
        "remind_calibration.py must resolve the consumer repo root via git "
        "(git rev-parse --show-toplevel / git_toplevel_from_cwd), not __file__"
    )


# -- gate_fire observations -------------------------------------------------


def _read_gate_fire_rows(repo: Path) -> list[dict]:
    obs_path = repo / ".ai-state" / "observations.jsonl"
    if not obs_path.exists():
        return []
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]


def test_gate_fire_row_on_pass(tmp_path: Path) -> None:
    """No calibration log yet (covered=True by definition) records outcome=pass.

    `.ai-state/` lives under the hermetic tmp_path repo -- never the live WAL.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".ai-state").mkdir()
    _make_commit(repo, "feat: initial commit -- no calibration log exists yet")

    result = _run_hook('git commit -m "feat: second commit, still no log"', repo)

    assert result.returncode == 0
    rows = _read_gate_fire_rows(repo)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "gate_fire"
    assert rows[0]["tool_name"] == "remind_calibration"
    assert rows[0]["outcome"] == "pass"


def test_gate_fire_row_on_warn(tmp_path: Path) -> None:
    """A lagging calibration log (the gate-liveness canary fixture) records outcome=warn."""
    repo = _build_lagging_repo(tmp_path)

    result = _run_hook('git commit -m "feat: add rate limiting"', repo)

    assert result.returncode == 0
    rows = _read_gate_fire_rows(repo)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "warn"


def _load_module():
    """Load remind_calibration.py fresh, for in-process exception-injection tests."""
    import importlib.util

    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location("remind_calibration", _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raise(*_args, **_kwargs):
    raise RuntimeError("boom")


def test_helper_exception_does_not_change_exit_code_on_pass(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _make_commit(repo, "feat: initial commit -- no calibration log exists yet")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    payload = {"tool_name": "Bash", "tool_input": {"command": 'git commit -m "feat: two"'}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    module.main()  # must not raise; always exits 0 (fail-open)


def test_helper_exception_does_not_change_exit_code_on_warn(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    repo = _build_lagging_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": 'git commit -m "feat: add rate limiting"'},
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    module.main()  # must not raise; always exits 0 (fail-open, advisory-only)


# -- Stop-time calibration reminder (new) --------------------------------------


def _write_wal_row(repo: Path, row: dict) -> None:
    """Append one raw observation row to the hermetic repo's WAL (no locking needed --
    single-threaded test fixture, never the real Praxion WAL)."""
    obs_path = repo / ".ai-state" / "observations.jsonl"
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(obs_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _qualifying_edit_row(session_id: str, path: str = "src/app.py") -> dict:
    """A tool_use WAL row shaped like capture_session.py's real Edit rows -- the kind
    of row the Stop reminder's "this session made a qualifying edit" gate condition reads."""
    return {
        "timestamp": "2026-09-25T10:00:00.000000+00:00",
        "session_id": session_id,
        "agent_type": "main",
        "agent_id": session_id,
        "project": "repo",
        "event_type": "tool_use",
        "tool_name": "Edit",
        "summary": f"Edit {path}",
        "file_paths": [path],
        "outcome": "success",
        "classification": "tool_use",
    }


def _build_qualifying_stop_repo(tmp_path: Path, session_id: str) -> Path:
    """A hermetic repo satisfying every Stop-reminder gate condition at once: managed
    project (committed .ai-state/calibration_log.md), a qualifying edit this session
    (WAL tool_use row on a file OTHER than calibration_log.md), and calibration_log.md
    untouched since HEAD.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_calibration_log(repo, "2026-09-20")
    _git(repo, "add", ".ai-state")
    _git(repo, "commit", "-m", "chore: add calibration baseline")
    _write_wal_row(repo, _qualifying_edit_row(session_id))
    return repo


def _stop_payload(session_id: str, cwd: Path, *, stop_hook_active: bool = False) -> dict:
    """A real Stop payload shape (template: hooks/test_capture_session.py)."""
    transcript = cwd / "transcript.jsonl"
    if not transcript.exists():
        transcript.write_text("", encoding="utf-8")
    return {
        "hook_event_name": "Stop",
        "session_id": session_id,
        "cwd": str(cwd),
        "transcript_path": str(transcript),
        "stop_hook_active": stop_hook_active,
    }


def _run_stop_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


class TestStopTimeCalibrationReminder:
    """New behavior: a once-per-session Stop reminder when a session left work
    uncalibrated, silent on any gate-condition failure or error. Each gate-condition
    test flips exactly one condition off the qualifying baseline
    (_build_qualifying_stop_repo) to prove the hook is a real conjunction, not a hook
    that fires unconditionally.
    """

    def test_fires_when_every_gate_condition_holds(self, tmp_path: Path) -> None:
        """Gate-liveness canary: a fully-qualifying session must produce a reminder."""
        session_id = "stop-sess-fires"
        repo = _build_qualifying_stop_repo(tmp_path, session_id)

        result = _run_stop_hook(_stop_payload(session_id, repo), repo)

        assert result.returncode == 0
        context = _additional_context(result)
        assert context != "", "a fully-qualifying session must produce a Stop-time reminder"
        assert "calibration_log.md" in context

    def test_emits_via_the_structured_hook_specific_output_key(self, tmp_path: Path) -> None:
        """Pins the exact Stop output shape -- verified against
        skills/hook-crafting/references/output-patterns.md's structured form (and
        SKILL.md's Gotchas confirmation that additionalContext works on Stop, where it
        also forces one continuation turn) rather than assumed from another event's shape.
        """
        session_id = "stop-sess-shape"
        repo = _build_qualifying_stop_repo(tmp_path, session_id)

        result = _run_stop_hook(_stop_payload(session_id, repo), repo)

        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert "hookSpecificOutput" in parsed, (
            f"the Stop reminder must use the structured key; got stdout={result.stdout!r}"
        )
        assert parsed["hookSpecificOutput"]["hookEventName"] == "Stop"
        assert parsed["hookSpecificOutput"]["additionalContext"] != ""

    def test_silent_when_stop_hook_active_is_true(self, tmp_path: Path) -> None:
        """The infinite-loop guard: stop_hook_active=true means Claude Code is already
        continuing because of a stop hook -- this invocation must exit 0 with nothing.
        """
        session_id = "stop-sess-active"
        repo = _build_qualifying_stop_repo(tmp_path, session_id)

        result = _run_stop_hook(_stop_payload(session_id, repo, stop_hook_active=True), repo)

        assert result.returncode == 0
        assert _additional_context(result) == ""

    def test_silent_inside_a_linked_worktree(self, tmp_path: Path) -> None:
        """Pipeline/scratch worktrees append their calibration row at pipeline
        completion, not per-session -- a Stop-time nudge inside one would be noise.
        """
        session_id = "stop-sess-worktree"
        main_repo = _build_qualifying_stop_repo(tmp_path, session_id)
        linked = tmp_path / "linked"
        subprocess.run(
            ["git", "-C", str(main_repo), "worktree", "add", "-q", str(linked), "-b", "feature"],
            check=True,
            capture_output=True,
            text=True,
        )
        _write_wal_row(linked, _qualifying_edit_row(session_id))

        result = _run_stop_hook(_stop_payload(session_id, linked), linked)

        assert result.returncode == 0
        assert _additional_context(result) == ""

    def test_silent_when_project_is_not_managed(self, tmp_path: Path) -> None:
        """No .ai-state/ at all -- an unmanaged project has nothing to calibrate."""
        session_id = "stop-sess-unmanaged"
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _make_commit(repo, "feat: initial commit")

        result = _run_stop_hook(_stop_payload(session_id, repo), repo)

        assert result.returncode == 0
        assert _additional_context(result) == ""

    def test_silent_when_session_made_no_qualifying_edits(self, tmp_path: Path) -> None:
        """A read-only session (no Edit/Write/MultiEdit/NotebookEdit WAL row) has
        nothing to nudge -- there is no completed work to record a calibration row for.
        """
        session_id = "stop-sess-no-edits"
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _write_calibration_log(repo, "2026-09-20")
        _git(repo, "add", ".ai-state")
        _git(repo, "commit", "-m", "chore: add calibration baseline")
        # Deliberately no WAL row at all for this session.

        result = _run_stop_hook(_stop_payload(session_id, repo), repo)

        assert result.returncode == 0
        assert _additional_context(result) == ""

    def test_silent_when_calibration_log_already_changed_this_session(self, tmp_path: Path) -> None:
        """A session that already touched calibration_log.md (uncommitted working-tree
        edit, i.e. changed vs HEAD) must not be nudged to append a row again."""
        session_id = "stop-sess-already-calibrated"
        repo = _build_qualifying_stop_repo(tmp_path, session_id)
        log_path = repo / ".ai-state" / "calibration_log.md"
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + "| extra | already-calibrated | row |\n",
            encoding="utf-8",
        )

        result = _run_stop_hook(_stop_payload(session_id, repo), repo)

        assert result.returncode == 0
        assert _additional_context(result) == ""

    def test_fires_at_most_once_per_session(self, tmp_path: Path) -> None:
        """A second Stop in the SAME session must not re-fire, even though every other
        gate condition still holds -- proves the dedup, not any other condition,
        suppresses the second call.
        """
        session_id = "stop-sess-once"
        repo = _build_qualifying_stop_repo(tmp_path, session_id)

        first = _run_stop_hook(_stop_payload(session_id, repo), repo)
        second = _run_stop_hook(_stop_payload(session_id, repo), repo)

        assert _additional_context(first) != "", "the first Stop in a qualifying session must fire"
        assert _additional_context(second) == "", (
            "a second Stop in the same session must not re-fire the reminder"
        )
