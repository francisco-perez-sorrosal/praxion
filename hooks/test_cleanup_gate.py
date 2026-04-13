"""Tests for hooks/cleanup_gate.sh — PreToolUse shell fast-path.

Validates:
  REQ-SG-01 — Fast-path for non-matching commands (exit 0, no Python).
  REQ-SG-02 — Pass-through for matching commands (Python invoked, stdout propagated).
  REQ-SG-03 — Conservative regex: ambiguous patterns fall through to Python,
              obvious non-cleanups short-circuit.
  EC-3.2.4  — Latency budget: non-match execution under 10 ms wall (measured
              against subprocess floor; see LATENCY_BUDGET_MS).

The gate is an opaque shell script — tests treat it as a black box, feeding
JSON payloads via stdin. Two modes of verification are used:

  (a) End-to-end: delegate to real promote_learnings.py and assert on its
      promote-marker output when both shell AND Python CLEANUP_PATTERNS match.

  (b) Delegation spy: substitute a tiny stub hook (`_write_delegation_spy`) in
      place of promote_learnings.py to verify the shell gate forwards stdin
      even when the Python hook's own patterns don't match — isolating the
      shell-gate contract from Python's authoritative filter.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
GATE_SCRIPT = HOOKS_DIR / "cleanup_gate.sh"
PROMOTE_HOOK = HOOKS_DIR / "promote_learnings.py"

# Wall-clock budget for the no-match fast path on macOS (EC-3.2.4).
# Floor includes Python subprocess.run fork+exec (~5 ms baseline on macOS),
# sh interpreter startup, grep exec, and exit. Measured min ~13 ms; we
# assert on the minimum across 10 warm runs to remove scheduling noise.
LATENCY_BUDGET_MS = 40.0
LATENCY_BUDGET_MIN_MS = 25.0
LATENCY_WARMUP_RUNS = 3
LATENCY_MEASURED_RUNS = 10

# Marker string from promote_learnings.py's Python fallthrough output.
PROMOTE_MARKER = "LEARNINGS.md files found"


DELEGATION_MARKER = "GATE_DELEGATED_TO_PYTHON"


def _run_gate(
    payload: dict, *, cwd: str | None = None, hook: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke cleanup_gate.sh with a JSON payload on stdin.

    By default uses the real promote_learnings.py; pass `hook=` to
    substitute a spy hook for delegation-only verification.
    """
    target_hook = str(hook) if hook is not None else str(PROMOTE_HOOK)
    return subprocess.run(
        [str(GATE_SCRIPT), target_hook],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def _write_delegation_spy(tmp_path: Path) -> Path:
    """Write a Python hook stub that prints a marker when invoked.

    Used to verify the shell gate forwards stdin to Python without relying
    on promote_learnings.py's own CLEANUP_PATTERNS filter.
    """
    spy = tmp_path / "spy_hook.py"
    spy.write_text(
        f"import sys\nsys.stdin.read()\nprint({DELEGATION_MARKER!r})\n",
        encoding="utf-8",
    )
    return spy


def _make_bash_payload(command: str, cwd: str | None = None) -> dict:
    payload: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = cwd
    return payload


# ---------------------------------------------------------------------------
# Script integrity
# ---------------------------------------------------------------------------


def test_gate_script_is_executable() -> None:
    """The shell gate must be executable or the hook silently no-ops."""
    assert GATE_SCRIPT.exists(), f"missing {GATE_SCRIPT}"
    assert os.access(GATE_SCRIPT, os.X_OK), (
        f"{GATE_SCRIPT} is not executable (chmod +x required)"
    )


# ---------------------------------------------------------------------------
# REQ-SG-01 — Fast-path for non-matching commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "ls /tmp",
        "git status",
        "python script.py",
        "rm /tmp/scratch",
    ],
    ids=["ls", "git-status", "python", "rm-non-aiwork"],
)
def test_non_matching_command_exits_fast(command: str) -> None:
    """Non-cleanup commands exit 0 with empty stdout — Python never runs."""
    result = _run_gate(_make_bash_payload(command))
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}"
    assert result.stdout == "", (
        f"expected empty stdout on fast-path, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# REQ-SG-02 — Pass-through for matching commands
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_cwd_with_learnings(tmp_path: Path) -> Path:
    """Fixture .ai-work/ directory with a LEARNINGS.md entry so that
    promote_learnings.py has something to warn about — otherwise its
    fallthrough is silent and we cannot observe that Python was reached."""
    learnings_dir = tmp_path / ".ai-work" / "test-slug"
    learnings_dir.mkdir(parents=True)
    (learnings_dir / "LEARNINGS.md").write_text(
        "# LEARNINGS\n- **[implementer] sample**: test entry\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .ai-work/some-slug",
        "rm -f .ai-work/foo/bar",
    ],
    ids=["rm-rf", "rm-f"],
)
def test_rm_ai_work_invokes_promote_learnings(
    command: str, fixture_cwd_with_learnings: Path
) -> None:
    """End-to-end: `rm ... .ai-work` matches BOTH the shell gate regex AND
    promote_learnings.py's CLEANUP_PATTERNS, so the full promote-warning
    marker reaches stdout."""
    result = _run_gate(_make_bash_payload(command, cwd=str(fixture_cwd_with_learnings)))
    assert result.returncode == 0
    assert PROMOTE_MARKER in result.stdout, (
        f"expected {PROMOTE_MARKER!r} in stdout (Python was not invoked), "
        f"got: {result.stdout!r}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .ai-work/some-slug",
        "rm -f .ai-work/foo/bar",
        "find .ai-work -name 'PROGRESS.md' -delete",
    ],
    ids=["rm-rf", "rm-f", "find-delete"],
)
def test_shell_gate_delegates_to_python(command: str, tmp_path: Path) -> None:
    """Delegation contract: shell gate forwards stdin to `python3 $1` for
    every command its regex matches, including patterns that Python's own
    CLEANUP_PATTERNS filter would reject. This isolates the gate's contract
    (forwarding) from promote_learnings.py's authoritative filter."""
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload(command), hook=spy_hook)
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout, (
        f"shell gate did not delegate {command!r} to Python; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# REQ-SG-03 — Conservative regex (escape correctness)
# ---------------------------------------------------------------------------


def test_regex_escapes_dot_correctly() -> None:
    """`rmXai-work` must NOT match — an unescaped `.` in the shell regex
    would be a false positive. The gate escapes `\\.` to protect the literal."""
    result = _run_gate(_make_bash_payload("rmXai-work"))
    assert result.returncode == 0
    assert result.stdout == "", (
        "regex is too permissive: 'rmXai-work' matched, meaning `.` was "
        f"unescaped. stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# EC-3.2.4 — Latency budget for fast-path
# ---------------------------------------------------------------------------


def test_non_matching_command_under_latency_budget() -> None:
    """Non-match fast-path completes within the wall-clock budget.

    Measurement methodology:
      - 3 warmup runs to amortize filesystem cache and interpreter startup.
      - 10 measured runs; assert on min (scheduling-noise-resistant) and mean.
      - Budget accounts for subprocess.run fork+exec overhead on macOS (~5 ms)
        plus the gate itself (~8 ms). The gate adds no Python invocation in
        this path; latency is dominated by sh + grep + exit.
    """
    payload = json.dumps(_make_bash_payload("ls -la")).encode("utf-8")

    for _ in range(LATENCY_WARMUP_RUNS):
        subprocess.run(
            [str(GATE_SCRIPT), str(PROMOTE_HOOK)],
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    samples_ms: list[float] = []
    for _ in range(LATENCY_MEASURED_RUNS):
        start = time.perf_counter()
        subprocess.run(
            [str(GATE_SCRIPT), str(PROMOTE_HOOK)],
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        samples_ms.append((time.perf_counter() - start) * 1000.0)

    min_ms = min(samples_ms)
    mean_ms = statistics.mean(samples_ms)

    assert min_ms < LATENCY_BUDGET_MIN_MS, (
        f"fast-path min latency {min_ms:.2f} ms exceeded budget "
        f"{LATENCY_BUDGET_MIN_MS} ms (samples: "
        f"{[f'{s:.2f}' for s in samples_ms]})"
    )
    assert mean_ms < LATENCY_BUDGET_MS, (
        f"fast-path mean latency {mean_ms:.2f} ms exceeded budget "
        f"{LATENCY_BUDGET_MS} ms (samples: "
        f"{[f'{s:.2f}' for s in samples_ms]})"
    )
