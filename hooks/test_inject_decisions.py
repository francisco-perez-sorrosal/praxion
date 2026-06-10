"""Tests for inject_decisions.py -- SessionStart ADR-context injection."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "inject_decisions.py"

_INDEX_HEADER = (
    "| ID | Title | Status | Category | Date | Tags | Summary |\n"
    "|----|-------|--------|----------|------|------|---------|\n"
)


def _load_module():
    """Load inject_decisions.py by path (hooks/ is not a package)."""
    sys.path.insert(0, str(MODULE_PATH.parent))  # so `import _hook_utils` resolves
    spec = importlib.util.spec_from_file_location("inject_decisions_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


decisions = _load_module()


def _write_index(cwd: Path, body_rows: str) -> None:
    """Create .ai-state/decisions/DECISIONS_INDEX.md with the given table rows."""
    index = cwd / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(_INDEX_HEADER + body_rows, encoding="utf-8")


def _run_hook(
    payload: dict, cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess with a JSON payload on stdin."""
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


def _injected_context(result: subprocess.CompletedProcess) -> str:
    parsed = json.loads(result.stdout)
    return parsed["hookSpecificOutput"]["additionalContext"]


class TestDecisionsInjected:
    """A populated index must surface accepted/proposed decisions (the gate bites)."""

    def test_emits_decision_context_for_accepted_adr(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-009 | Dual-layer memory | accepted | architectural | 2026-01-01 | memory | A memory design |\n",
        )
        result = _run_hook({"cwd": str(tmp_path)}, tmp_path)
        assert result.returncode == 0
        context = _injected_context(result)
        assert "## Decision Context (auto-injected)" in context
        assert "dec-009" in context
        assert "Dual-layer memory" in context

    def test_includes_proposed_status(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-200 | A proposal | proposed | architectural | 2026-02-02 | x | Some summary |\n",
        )
        context = _injected_context(_run_hook({"cwd": str(tmp_path)}, tmp_path))
        assert "dec-200" in context

    def test_falls_back_to_cwd_when_payload_lacks_cwd(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-001 | First | accepted | architectural | 2026-01-01 | a | Sum |\n",
        )
        result = _run_hook({}, tmp_path)
        assert result.returncode == 0
        assert "dec-001" in _injected_context(result)


class TestDecisionsSuppressed:
    """Cases where no context must be emitted."""

    def test_silent_when_index_missing(self, tmp_path: Path) -> None:
        result = _run_hook({"cwd": str(tmp_path)}, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_silent_when_no_injectable_rows(self, tmp_path: Path) -> None:
        # Only superseded/rejected rows -- none are injectable.
        _write_index(
            tmp_path,
            "| dec-009 | Old | superseded | architectural | 2026-01-01 | x | Gone |\n"
            "| dec-010 | Bad | rejected | architectural | 2026-01-02 | y | Nope |\n",
        )
        result = _run_hook({"cwd": str(tmp_path)}, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_disable_flag_suppresses_injection(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-001 | First | accepted | architectural | 2026-01-01 | a | Sum |\n",
        )
        result = _run_hook(
            {"cwd": str(tmp_path)},
            tmp_path,
            extra_env={decisions.DISABLE_FLAG: "1"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestFailsOpen:
    """Internal errors must never wedge session creation."""

    def test_malformed_payload_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="not-json",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0

    def test_empty_payload_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="{}",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0


class TestOutputBuilder:
    """Unit-level checks on the ADR output builder."""

    def test_recent_decisions_sorted_first(self) -> None:
        rows = [
            {
                "id": "dec-001",
                "title": "Old",
                "status": "accepted",
                "category": "x",
                "date": "2026-01-01",
                "tags": "a",
                "summary": "s1",
            },
            {
                "id": "dec-050",
                "title": "New",
                "status": "accepted",
                "category": "x",
                "date": "2026-06-01",
                "tags": "b",
                "summary": "s2",
            },
        ]
        out = decisions._build_adr_output(rows, budget=decisions.ADR_SOFT_CAP)
        assert out.index("dec-050") < out.index("dec-001")

    def test_empty_rows_yield_empty_string(self) -> None:
        assert decisions._build_adr_output([], budget=decisions.ADR_SOFT_CAP) == ""

    def test_soft_cap_truncates_and_footers(self) -> None:
        rows = [
            {
                "id": f"dec-{i:03d}",
                "title": "T" * 40,
                "status": "accepted",
                "category": "architectural",
                "date": f"2026-01-{i:02d}",
                "tags": "tag",
                "summary": "S" * 60,
            }
            for i in range(1, 40)
        ]
        out = decisions._build_adr_output(rows, budget=decisions.ADR_SOFT_CAP)
        assert len(out) <= decisions.ADR_SOFT_CAP
        assert "more decisions" in out
