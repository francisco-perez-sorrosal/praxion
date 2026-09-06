"""Tests for hooks/cleanup_gate.sh — PreToolUse shell fast-path.

Verifies four behaviors of the gate:

  - Fast-path for non-matching commands (exit 0, no Python invoked).
  - Pass-through for matching commands (Python invoked, stdout propagated).
  - Conservative regex: ambiguous patterns fall through to Python,
    obvious non-cleanups short-circuit.
  - Latency budget: non-match execution stays within a threshold measured
    relative to this run's own bare-subprocess fork+exec floor, not an
    absolute wall-clock number (see LATENCY_BUDGET_MULTIPLIER).

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
import subprocess
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
GATE_SCRIPT = HOOKS_DIR / "cleanup_gate.sh"
PROMOTE_HOOK = HOOKS_DIR / "promote_learnings.py"

# A bare subprocess with the same process-spawn shape as the gate itself
# (POSIX shell, no-op body) -- this run's own fork+exec floor, measured
# fresh every time the test runs rather than assumed from a fixed constant.
BASELINE_COMMAND = ["sh", "-c", ":"]

# Relative-to-baseline budget: `gate_min < baseline_min * LATENCY_BUDGET_MULTIPLIER
# + LATENCY_BUDGET_MARGIN_MS`. The multiplier absorbs the gate's own
# additional forks over the bare baseline (cat | grep inside cleanup_gate.sh,
# on top of the sh interpreter both share) staying proportional under CPU
# load rather than fixed in wall-clock ms; the margin absorbs constant-ish
# overhead (argv/JSON payload size, measurement jitter) that does not scale
# with the baseline. Calibrated from repeated local measurement: idle-machine
# min-ratio ~2.2x, and ~1.4x-2.9x under four concurrent `yes > /dev/null`
# CPU-load processes -- both comfortably under a 5x multiplier plus margin.
LATENCY_BUDGET_MULTIPLIER = 5.0
LATENCY_BUDGET_MARGIN_MS = 15.0
LATENCY_WARMUP_RUNS = 3
LATENCY_MEASURED_RUNS = 10

# Historical absolute budget (informational only -- no longer asserted).
# It broke under concurrent CPU load because fork+exec cost is highly
# load- and machine-dependent; a bound tied to a fixed wall-clock number
# cannot track that, while a same-run relative baseline does.
#   LATENCY_BUDGET_MS = 40.0       (old mean bound)
#   LATENCY_BUDGET_MIN_MS = 25.0   (old min bound)

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
    assert os.access(GATE_SCRIPT, os.X_OK), f"{GATE_SCRIPT} is not executable (chmod +x required)"


# ---------------------------------------------------------------------------
# Fast-path for non-matching commands
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
    assert result.stdout == "", f"expected empty stdout on fast-path, got: {result.stdout!r}"


# ---------------------------------------------------------------------------
# Pass-through for matching commands
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
        f"expected {PROMOTE_MARKER!r} in stdout (Python was not invoked), got: {result.stdout!r}"
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
# Conservative regex (escape correctness)
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
# Latency budget for fast-path
# ---------------------------------------------------------------------------


def _measure_wall_clock_ms(argv: list[str], *, stdin_bytes: bytes | None, runs: int) -> list[float]:
    """Run `argv` `runs` times, feeding `stdin_bytes` on each invocation, and
    return the per-run wall-clock durations in milliseconds."""
    samples_ms: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run(
            argv,
            input=stdin_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        samples_ms.append((time.perf_counter() - start) * 1000.0)
    return samples_ms


def test_non_matching_command_under_latency_budget() -> None:
    """Non-match fast-path completes within a budget relative to this run's
    own bare-subprocess fork+exec floor -- never an absolute wall-clock
    number, which drifts with machine load and CI noise (the historical
    failure mode this replaces; see LATENCY_BUDGET_MULTIPLIER above).

    Measurement methodology:
      - 3 warmup runs each for baseline and gate, to amortize filesystem
        cache and interpreter startup.
      - 10 measured runs each; assert on min (scheduling-noise-resistant --
        the floor is the fastest a process can possibly be scheduled, so
        the minimum across many samples converges on the true floor even
        under load, whereas the mean is pulled upward by scheduler noise
        that the gate and the baseline both experience, not necessarily
        proportionally).
      - The gate adds no Python invocation on this path; its latency over
        the baseline comes from cleanup_gate.sh's own cat | grep forks.
    """
    gate_argv = [str(GATE_SCRIPT), str(PROMOTE_HOOK)]
    payload = json.dumps(_make_bash_payload("ls -la")).encode("utf-8")

    _measure_wall_clock_ms(BASELINE_COMMAND, stdin_bytes=None, runs=LATENCY_WARMUP_RUNS)
    _measure_wall_clock_ms(gate_argv, stdin_bytes=payload, runs=LATENCY_WARMUP_RUNS)

    baseline_samples_ms = _measure_wall_clock_ms(
        BASELINE_COMMAND, stdin_bytes=None, runs=LATENCY_MEASURED_RUNS
    )
    gate_samples_ms = _measure_wall_clock_ms(
        gate_argv, stdin_bytes=payload, runs=LATENCY_MEASURED_RUNS
    )

    baseline_min_ms = min(baseline_samples_ms)
    gate_min_ms = min(gate_samples_ms)
    budget_ms = baseline_min_ms * LATENCY_BUDGET_MULTIPLIER + LATENCY_BUDGET_MARGIN_MS

    assert gate_min_ms < budget_ms, (
        f"fast-path min latency {gate_min_ms:.2f} ms exceeded the relative budget "
        f"{budget_ms:.2f} ms (baseline_min={baseline_min_ms:.2f} ms x "
        f"{LATENCY_BUDGET_MULTIPLIER} + {LATENCY_BUDGET_MARGIN_MS} ms margin; "
        f"gate samples: {[f'{s:.2f}' for s in gate_samples_ms]}, "
        f"baseline samples: {[f'{s:.2f}' for s in baseline_samples_ms]})"
    )


# ---------------------------------------------------------------------------
# Canary: gate blocks (rejects fast-path) for .ai-work cleanup commands
# ---------------------------------------------------------------------------


def test_blocks_fast_path_for_ai_work_rm_command(tmp_path: Path) -> None:
    """Canary: a `rm -rf .ai-work/...` command is NOT swallowed by the fast-path.

    The gate's job is to intercept cleanup commands and forward them to the
    Python hook. A command matching the cleanup regex must reach Python — the
    fast-path (silent exit 0 with empty stdout) must NOT fire.

    We use a spy hook so the test does not depend on promote_learnings.py's
    own CLEANUP_PATTERNS matching the payload.
    """
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload("rm -rf .ai-work/my-task"), hook=spy_hook)
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout, (
        "cleanup_gate.sh must delegate an `rm -rf .ai-work/` command to Python "
        f"(fast-path must NOT silence it); stdout={result.stdout!r}"
    )
