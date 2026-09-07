"""Tests for check_token_ratchet.py -- the commit-gate wrapper over `ratchet()`.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input. Here that means a breached ratchet must exit
non-zero, and an unhandled exception must exit 2 (script error), never 1
(findings) -- `--blocking` maps only 1 onto a block, so a bug here must not
silently block every future commit.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import check_token_ratchet as gate
import pytest


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
    """A bug here must degrade to non-blocking (2), never to blocking (1)."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(gate, "resolve_repo_root", lambda *a, **kw: Path("/unused"))
    monkeypatch.setattr(gate.mtb, "ratchet", _boom)

    assert gate.main() == 2


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
    _seed(tmp_path, listing_ceiling=999_999, samples=[{"date": old_date, "governed_tokens": 10}])

    assert gate.main() == 1


def test_end_to_end_a_clean_baseline_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(gate, "resolve_repo_root", lambda *a, **kw: tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
    old_date = (date.today() - timedelta(days=31)).isoformat()
    _seed(
        tmp_path, listing_ceiling=999_999, samples=[{"date": old_date, "governed_tokens": 999_999}]
    )

    assert gate.main() == 0
