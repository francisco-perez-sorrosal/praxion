"""Tests for remind_adr.py -- commit-time ADR reminder hook.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate advising on
missing ADRs when architectural files are committed. It ships a canary -- a test that
stages a known-architectural file (rules/x.md) with no companion ADR staged and asserts
the reminder fires on stderr -- proving the gate is not merely a no-op that always
passes on the current good state.

Contract under test (hooks/remind_adr.py): the hook reads a stdin JSON payload shaped
like tool_input.command, checks staged files (git diff --cached --name-only) against
ARCHITECTURAL_PATTERNS, and emits a stderr [adr-reminder] warning only when
architectural files are staged AND no .ai-state/decisions/*.md file is staged (or was
committed at HEAD). It always exits 0 (fail-open -- never blocks a commit).

Hermetic-git-repo pattern (template: hooks/test_remind_calibration.py): every test
builds its own temporary git repo via tmp_path, with git identity configured. The real
Praxion .ai-state/decisions/ directory is never read.

Subprocess harness (template: hooks/test_remind_calibration.py): the hook is invoked as
a real subprocess with a JSON payload on stdin, mirroring exactly how commit_gate.sh
dispatches it during a real `git commit`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parent / "remind_adr.py"


# -- Git / repo helpers -------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> Path:
    """Initialise a bare-minimum git repo suitable for staged-file queries."""
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "commit.gpgsign", "false")
    return path


def _stage_file(repo: Path, rel_path: str, content: str = "content\n") -> None:
    """Write a file at rel_path under repo and stage it."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", rel_path)


# -- Hook invocation helpers ---------------------------------------------------

# Explicit env override: the hackathon flag silences the reminder entirely (see
# remind_adr.py), so tests must not inherit an ambient PRAXION_HACKATHON_MODE value
# from the calling shell -- hermeticity per rules/swe/testing-conventions.md.
_HERMETIC_ENV = {**os.environ, "PRAXION_HACKATHON_MODE": "0"}


def _run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke remind_adr.py as a subprocess, mirroring commit_gate.sh's dispatch."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=_HERMETIC_ENV,
        timeout=10,
    )


def _run_hook_raw_stdin(raw_input: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke remind_adr.py with an arbitrary raw stdin body (non-JSON cases)."""
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=_HERMETIC_ENV,
        timeout=10,
    )


# -- Tests ----------------------------------------------------------------------


def test_flags_architectural_change_without_adr(tmp_path: Path) -> None:
    """Gate-liveness canary: an architectural file staged with no ADR fires the reminder.

    Scenario: rules/x.md (matches the rules/**/*.md architectural pattern) is staged
    with no .ai-state/decisions/*.md staged, and there is no prior commit to carry a
    recent ADR either. A gate that never fires on known-bad input is indistinguishable
    from no gate (rules/swe/gate-liveness.md). The contrast test below (same staged
    file, plus a staged ADR) rules out a hook that fires unconditionally on any commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage_file(repo, "rules/x.md", "## New Rule\n")

    result = _run_hook('git commit -m "docs: add rule"', repo)

    assert result.returncode == 0, "the hook must always exit 0 (fail-open, advisory-only)"
    assert result.stderr.strip() != "", (
        "an architectural file staged without an ADR must produce a stderr reminder"
    )
    assert "[adr-reminder]" in result.stderr
    assert "rules/x.md" in result.stderr, (
        f"the reminder must name the changed architectural file; got stderr={result.stderr!r}"
    )


def test_silent_when_adr_staged_alongside_architectural_change(tmp_path: Path) -> None:
    """A staged ADR file alongside the architectural change suppresses the reminder.

    Same architectural file as the canary above -- only the presence of a staged
    .ai-state/decisions/*.md file differs. Proves the hook checks for a companion ADR
    rather than firing on every architectural commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage_file(repo, "rules/x.md", "## New Rule\n")
    _stage_file(repo, ".ai-state/decisions/001-new-rule.md", "# ADR\n")

    result = _run_hook('git commit -m "docs: add rule with ADR"', repo)

    assert result.returncode == 0
    assert result.stderr.strip() == "", (
        "an architectural change with a companion staged ADR must not trigger the "
        f"reminder; got stderr={result.stderr!r}"
    )


def test_malformed_stdin_json_never_raises(tmp_path: Path) -> None:
    """Malformed stdin JSON never raises and always exits 0 (fail-open).

    main() is wrapped in except Exception: pass so a hook bug can never wedge or
    block a commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    result = _run_hook_raw_stdin("not-json{{{", repo)

    assert result.returncode == 0, "malformed stdin must never cause a non-zero exit"
    assert "Traceback" not in result.stderr, (
        f"malformed stdin must not leak a Python traceback; got stderr={result.stderr!r}"
    )
