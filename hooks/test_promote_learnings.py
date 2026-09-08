"""Tests for promote_learnings.py -- Step 12 gate_fire coverage.

`promote_learnings.py` had no prior dedicated test file (only
`test_cleanup_gate.py`, which exercises the `cleanup_gate.sh` shell wrapper's
own delegation/fast-path contract via a spy hook, not this hook's own
pass/warn decision or its Step-12 `record_gate_fire` call site).

Contract under test (hooks/promote_learnings.py): the hook fires on Bash
commands matching CLEANUP_PATTERNS, warns (stdout hookSpecificOutput) when
`.ai-work/**/LEARNINGS.md` under `payload["cwd"]` has unpromoted entries, and
always exits 0 (fail-open). Step 12 adds one `record_gate_fire` call per
invocation, wrapped in its own `except Exception: pass` (belt-and-suspenders
on top of `_hook_utils.record_gate_fire`'s own fail-open contract).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_PATH = HOOKS_DIR / "promote_learnings.py"


def _cleanup_payload(cwd: str) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf .ai-work/some-slug"},
        "cwd": cwd,
    }


def _write_learnings(cwd: Path) -> None:
    learnings_dir = cwd / ".ai-work" / "test-slug"
    learnings_dir.mkdir(parents=True)
    (learnings_dir / "LEARNINGS.md").write_text(
        "# LEARNINGS\n- **[implementer] sample**: test entry\n", encoding="utf-8"
    )


def _read_gate_fire_rows(cwd: Path) -> list[dict]:
    obs_path = cwd / ".ai-state" / "observations.jsonl"
    if not obs_path.exists():
        return []
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]


def _load_module():
    """Load promote_learnings.py fresh, for in-process test control."""
    import importlib.util

    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location("promote_learnings", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raise(*_args, **_kwargs):
    raise RuntimeError("boom")


def test_gate_fire_row_on_pass(tmp_path: Path, monkeypatch) -> None:
    """No unpromoted LEARNINGS.md under cwd's .ai-work -> outcome=pass.

    `.ai-state/` lives under tmp_path (via chdir) -- never the live WAL.
    """
    module = _load_module()
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()

    rows = _read_gate_fire_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "gate_fire"
    assert rows[0]["tool_name"] == "promote_learnings"
    assert rows[0]["outcome"] == "pass"


def test_gate_fire_row_on_warn(tmp_path: Path, monkeypatch) -> None:
    """Unpromoted LEARNINGS.md entries under cwd's .ai-work -> outcome=warn."""
    module = _load_module()
    (tmp_path / ".ai-state").mkdir()
    _write_learnings(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()

    rows = _read_gate_fire_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "warn"


def test_helper_exception_does_not_change_exit_code_on_pass(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()  # must not raise


def test_helper_exception_does_not_change_exit_code_on_warn(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _write_learnings(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()  # must not raise; the hook stays fail-open (exits 0)


def test_non_cleanup_command_never_fires_gate(tmp_path: Path, monkeypatch) -> None:
    """A non-cleanup Bash command must not emit a gate_fire row at all."""
    module = _load_module()
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.chdir(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": str(tmp_path)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    module.main()

    assert _read_gate_fire_rows(tmp_path) == []
