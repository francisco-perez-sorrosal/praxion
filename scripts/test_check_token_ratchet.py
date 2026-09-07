"""Tests for check_token_ratchet.py -- the commit-gate wrapper over `ratchet()`.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input. Here that means a breached ratchet must exit
non-zero, and an unhandled exception must exit 3 (script error), never 1
(findings) or 2 -- `hooks/commit_gate.sh --blocking` translates only rc==1
to 2, but a literal 2 from this script would reach PreToolUse as 2
unchanged, blocking every future commit exactly like a real breach would.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import check_token_ratchet as gate
import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
GATE_SCRIPT = HOOKS_DIR / "commit_gate.sh"


def _stub_ratchet(monkeypatch: pytest.MonkeyPatch, result: dict) -> None:
    monkeypatch.setattr(gate, "resolve_repo_root", lambda *a, **kw: Path("/unused"))
    monkeypatch.setattr(gate.mtb, "ratchet", lambda repo_root, **kw: result)


def test_exits_zero_on_a_fail_open_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """No baseline anywhere in the fleet must never block a commit."""
    _stub_ratchet(
        monkeypatch,
        {"skipped": True, "reason": "no baseline file", "ratchet_ok": True},
    )

    assert gate.main() == 0


def test_exits_zero_when_the_ratchet_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ratchet(
        monkeypatch,
        {
            "skipped": False,
            "ratchet_ok": True,
            "governed_delta": -5,
            "listing_over_ceiling": False,
            "listing_tokens": 100,
            "listing_ceiling": 200,
        },
    )

    assert gate.main() == 0


def test_canary_a_breached_ratchet_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate contract: growth over the window must block, not just report."""
    _stub_ratchet(
        monkeypatch,
        {
            "skipped": False,
            "ratchet_ok": False,
            "governed_delta": 42,
            "listing_over_ceiling": False,
            "listing_tokens": 100,
            "listing_ceiling": 200,
        },
    )

    assert gate.main() == 1
    assert "42" in capsys.readouterr().out


def test_a_listing_ceiling_breach_also_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    """The second, independent tripwire must block too."""
    _stub_ratchet(
        monkeypatch,
        {
            "skipped": False,
            "ratchet_ok": False,
            "governed_delta": None,
            "listing_over_ceiling": True,
            "listing_tokens": 250,
            "listing_ceiling": 200,
        },
    )

    assert gate.main() == 1


def test_an_unexpected_exception_exits_script_error_not_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bug here must degrade to non-blocking (3), never to blocking (1) or
    the harness's own block code (2)."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(gate, "resolve_repo_root", lambda *a, **kw: Path("/unused"))
    monkeypatch.setattr(gate.mtb, "ratchet", _boom)

    assert gate.main() == 3


def test_canary_a_raised_exception_reaches_pretooluse_as_non_blocking(
    tmp_path: Path,
) -> None:
    """The end-to-end proof the unit test above cannot give: a script that
    raises must not become a PreToolUse block once `hooks/commit_gate.sh
    --blocking` has translated its exit code -- the exact way `_SCRIPT_ERROR
    = 2` silently blocked every future commit fleet-wide before this fix.
    """
    broken_hook = tmp_path / "broken_ratchet.py"
    broken_hook.write_text(
        f"import sys\nsys.stdin.read()\nsys.exit({gate._SCRIPT_ERROR})\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(GATE_SCRIPT), "--blocking", str(broken_hook)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == gate._SCRIPT_ERROR
    assert result.returncode != 2, "a script error must never reach PreToolUse as a block"


# -- End-to-end: a real repo fixture through the real ratchet() -----------------


def _seed(tmp_path: Path, *, listing_ceiling: int, samples: list[dict]) -> None:
    baseline = tmp_path / ".ai-state" / "token_budget_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        json.dumps({"schema": 1, "listing_ceiling": listing_ceiling, "samples": samples})
    )


def test_end_to_end_a_deliberately_breached_baseline_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(gate, "resolve_repo_root", lambda *a, **kw: tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# project\n" + "word " * 30_000, encoding="utf-8")
    old_date = (date.today() - timedelta(days=31)).isoformat()
    # basis="estimate" matches the no-API-key reading this test takes today --
    # a same-basis prior is required for the delta check to actually compare
    # rather than fail open (see measure_token_budget.ratchet's basis-aware fix).
    _seed(
        tmp_path,
        listing_ceiling=999_999,
        samples=[{"date": old_date, "governed_tokens": 10, "basis": "estimate"}],
    )

    assert gate.main() == 1


def test_end_to_end_a_clean_baseline_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(gate, "resolve_repo_root", lambda *a, **kw: tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
    old_date = (date.today() - timedelta(days=31)).isoformat()
    _seed(
        tmp_path,
        listing_ceiling=999_999,
        samples=[{"date": old_date, "governed_tokens": 999_999, "basis": "estimate"}],
    )

    assert gate.main() == 0
