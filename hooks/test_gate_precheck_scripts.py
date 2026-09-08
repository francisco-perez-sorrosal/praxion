"""Tests for the SessionStart pre-check gates added in P1.11:
hooks/gate_surface_feedback.sh and hooks/gate_sidecar_banner.sh.

Cites: rules/swe/gate-liveness.md — every CODE gate ships tests proving both
the pass (interpreter starts) and skip (interpreter never starts) paths. Each
gate mirrors one early-return condition already documented in the guarded
hook's own module docstring (see the gate script's own header comment for the
exact citation), so a "skip" here must correspond to a real no-op in the
Python hook, never a suppressed real advisory.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent

DELEGATION_MARKER = "GATE_DELEGATED_TO_INTERPRETER"


def _write_spy_interpreter(tmp_path: Path) -> Path:
    """A stand-in for `_py.sh <hook.py>` that just proves it was invoked."""
    spy = tmp_path / "spy_py.sh"
    spy.write_text(
        "#!/bin/sh\ncat >/dev/null\necho " + DELEGATION_MARKER + "\n",
        encoding="utf-8",
    )
    spy.chmod(0o755)
    return spy


def _run_gate(
    gate: Path, spy_interpreter: Path, payload: dict, env_overrides: dict
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for key in (
        "PRAXION_DISABLE_FEEDBACK_SURFACING",
        "PRAXION_DISABLE_SIDECAR_BANNER",
    ):
        env.pop(key, None)
    env.update(env_overrides)
    return subprocess.run(
        [str(gate), str(spy_interpreter), "hook.py"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# ---------------------------------------------------------------------------
# gate_surface_feedback.sh
# ---------------------------------------------------------------------------

GATE_FEEDBACK = HOOKS_DIR / "gate_surface_feedback.sh"


def test_feedback_gate_is_executable() -> None:
    assert GATE_FEEDBACK.exists()
    assert os.access(GATE_FEEDBACK, os.X_OK)


def test_feedback_gate_skips_when_pending_md_absent(tmp_path: Path) -> None:
    """No .ai-state/praxion_feedback/PENDING.md -- the hook's own documented
    'absent ledger' no-op -- so the interpreter must never start."""
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_FEEDBACK, spy, payload, {})
    assert result.returncode == 0
    assert DELEGATION_MARKER not in result.stdout


def test_feedback_gate_delegates_when_pending_md_present(tmp_path: Path) -> None:
    ledger_dir = tmp_path / ".ai-state" / "praxion_feedback"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "PENDING.md").write_text("# Pending Praxion Feedback\n", encoding="utf-8")
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_FEEDBACK, spy, payload, {})
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout


def test_feedback_gate_skips_when_disable_flag_set(tmp_path: Path) -> None:
    """Disable flag wins even when the ledger is present."""
    ledger_dir = tmp_path / ".ai-state" / "praxion_feedback"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "PENDING.md").write_text("# Pending Praxion Feedback\n", encoding="utf-8")
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_FEEDBACK, spy, payload, {"PRAXION_DISABLE_FEEDBACK_SURFACING": "1"})
    assert result.returncode == 0
    assert DELEGATION_MARKER not in result.stdout


# ---------------------------------------------------------------------------
# gate_sidecar_banner.sh
# ---------------------------------------------------------------------------

GATE_SIDECAR = HOOKS_DIR / "gate_sidecar_banner.sh"


def test_sidecar_gate_is_executable() -> None:
    assert GATE_SIDECAR.exists()
    assert os.access(GATE_SIDECAR, os.X_OK)


def test_sidecar_gate_skips_when_ai_state_is_a_plain_directory(tmp_path: Path) -> None:
    """.ai-state exists and is not a symlink -- resolve_placement's InRepo
    branch unconditionally, so the interpreter must never start."""
    (tmp_path / ".ai-state").mkdir()
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_SIDECAR, spy, payload, {})
    assert result.returncode == 0
    assert DELEGATION_MARKER not in result.stdout


def test_sidecar_gate_delegates_when_ai_state_is_a_symlink(tmp_path: Path) -> None:
    """A symlinked .ai-state could be SidecarOwned/Dangling/Foreign -- all
    require the Python resolver, so the interpreter must start."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    (tmp_path / ".ai-state").symlink_to(target)
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_SIDECAR, spy, payload, {})
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout


def test_sidecar_gate_delegates_when_ai_state_is_absent(tmp_path: Path) -> None:
    """Absence could be NotYetLinked (a fresh worktree awaiting its heal) --
    the one case this hook exists to handle -- so it must never be skipped."""
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_SIDECAR, spy, payload, {})
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout


def test_sidecar_gate_skips_when_disable_flag_set(tmp_path: Path) -> None:
    spy = _write_spy_interpreter(tmp_path)
    payload = {"cwd": str(tmp_path)}
    result = _run_gate(GATE_SIDECAR, spy, payload, {"PRAXION_DISABLE_SIDECAR_BANNER": "true"})
    assert result.returncode == 0
    assert DELEGATION_MARKER not in result.stdout
