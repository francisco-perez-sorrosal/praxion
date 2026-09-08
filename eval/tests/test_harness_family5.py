"""Behavioral tests for Family 5 — token-budget surface stability collector.

Tests cover: PASS/WARN/FAIL verdict thresholds, the trailing-30-day byte-delta
comparison (missing baseline, too-young history, positive/negative delta),
the frozen listing-ceiling comparison (basis-matched, basis-mismatched,
absent), the never-mutates-the-baseline-file guarantee, and the run_eval()
wiring proof.

A fake ``measure_module`` (mirroring FakeJudgeClient elsewhere in this test
suite) stands in for the dynamically-imported ``scripts/measure_token_budget``
module, so these tests never touch this machine's real ``~/.claude/`` surface,
never make a network call, and never read/write the real committed baseline.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


class _FakeMeasureModule:
    """Scripted stand-in for scripts/measure_token_budget.py's public functions."""

    def __init__(self, governed: dict[str, Any], listing: dict[str, Any]) -> None:
        self._governed = governed
        self._listing = listing

    def measure(self, repo_root: Path, *, api_key: str | None = None) -> dict[str, Any]:
        del repo_root, api_key
        return self._governed

    def measure_listing(self, repo_root: Path, *, api_key: str | None = None) -> dict[str, Any]:
        del repo_root, api_key
        return self._listing


def _governed(
    tokens: int, bytes_: int, budget: int = 25_000, measured: bool = True
) -> dict[str, Any]:
    return {
        "files": ["CLAUDE.md"],
        "bytes": bytes_,
        "tokens": tokens,
        "budget": budget,
        "over_by": max(0, tokens - budget),
        "headroom": max(0, budget - tokens),
        "utilisation": round(tokens / budget, 4),
        "basis": "tokenizer" if measured else "estimate (bytes / 3.6)",
        "measured": measured,
    }


def _listing(
    tokens: int, bytes_: int = 1000, file_count: int = 5, measured: bool = True
) -> dict[str, Any]:
    return {
        "tokens": tokens,
        "bytes": bytes_,
        "basis": "tokenizer" if measured else "estimate (bytes / 3.6)",
        "measured": measured,
        "file_count": file_count,
    }


def _write_baseline(path: Path, baseline: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline), encoding="utf-8")


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------


def test_under_budget_and_no_baseline_is_pass(tmp_path: Path):
    """No baseline file at all: PASS, with a note that the trend is unavailable."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    fake = _FakeMeasureModule(_governed(10_000, 40_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path,
        baseline_path=tmp_path / "no-such-baseline.json",
        measure_module=fake,
    )

    results = family.run(corpus=object(), judge=object())

    assert len(results) == 1
    result = results[0]
    assert result.check_name == "token_budget_stability"
    assert result.check_kind == "mechanical"
    assert result.verdict == "PASS"
    assert any("no baseline file" in f for f in result.findings)


def test_over_ceiling_is_fail(tmp_path: Path):
    """Governed tokens over the budget ceiling always FAILs, baseline or not."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    fake = _FakeMeasureModule(_governed(25_500, 96_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=tmp_path / "absent.json", measure_module=fake
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "FAIL"
    assert any("exceed the 25,000 ceiling" in f for f in result.findings)


def test_utilisation_at_warn_threshold_is_warn(tmp_path: Path):
    """90% utilisation (and no other failure) WARNs rather than PASSes."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    fake = _FakeMeasureModule(_governed(22_500, 85_000), _listing(3_000))  # exactly 90.0%
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=tmp_path / "absent.json", measure_module=fake
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "WARN"
    assert any("warn threshold" in f for f in result.findings)


def test_utilisation_below_warn_threshold_is_pass(tmp_path: Path):
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    fake = _FakeMeasureModule(_governed(20_000, 76_000), _listing(3_000))  # 80%
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=tmp_path / "absent.json", measure_module=fake
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# Trailing-30-day byte delta
# ---------------------------------------------------------------------------


def test_positive_trailing_delta_is_fail(tmp_path: Path):
    """Governed bytes grew over the trailing 30 days: FAIL, even under the token ceiling."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    _write_baseline(
        baseline_path,
        {
            "schema": 1,
            "listing_ceiling": None,
            "samples": [
                {"date": "2026-08-01", "governed_bytes": 90_000, "governed_tokens": 23_600}
            ],
        },
    )
    fake = _FakeMeasureModule(_governed(20_000, 95_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path,
        baseline_path=baseline_path,
        measure_module=fake,
        today=date(2026, 9, 7),  # 37 days after the sample — past the 30-day window
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "FAIL"
    assert any("grew by 5,000 bytes" in f for f in result.findings)


def test_negative_trailing_delta_is_not_a_failure_reason(tmp_path: Path):
    """A shrinking surface never fails the ratchet, however far it shrinks."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    _write_baseline(
        baseline_path,
        {
            "schema": 1,
            "listing_ceiling": None,
            "samples": [
                {"date": "2026-08-01", "governed_bytes": 95_000, "governed_tokens": 24_600}
            ],
        },
    )
    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake, today=date(2026, 9, 7)
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "PASS"
    assert any("byte delta: -5,000" in f for f in result.findings)


def test_delta_within_window_skips_the_comparison(tmp_path: Path):
    """A prior sample less than 30 days old is too young for a trend verdict."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    _write_baseline(
        baseline_path,
        {
            "schema": 1,
            "listing_ceiling": None,
            "samples": [
                {"date": "2026-09-01", "governed_bytes": 90_000, "governed_tokens": 23_600}
            ],
        },
    )
    fake = _FakeMeasureModule(_governed(20_000, 99_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake, today=date(2026, 9, 7)
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "PASS"
    assert any("day(s) of baseline history" in f for f in result.findings)


def test_no_byte_tracked_prior_sample_skips_the_comparison(tmp_path: Path):
    """A legacy sample lacking governed_bytes degrades to 'no comparison', not KeyError."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    _write_baseline(
        baseline_path,
        {
            "schema": 1,
            "listing_ceiling": None,
            "samples": [{"date": "2026-08-01", "governed_tokens": 23_600}],
        },
    )
    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake, today=date(2026, 9, 7)
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "PASS"
    assert any("no byte-tracked prior sample" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Frozen listing ceiling
# ---------------------------------------------------------------------------


def test_listing_over_frozen_ceiling_is_fail(tmp_path: Path):
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    _write_baseline(
        baseline_path,
        {
            "schema": 1,
            "listing_ceiling": 11_336,
            "listing_ceiling_basis": "tokenizer",
            "samples": [],
        },
    )
    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(12_000, measured=True))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "FAIL"
    assert any("exceed the frozen ceiling 11,336" in f for f in result.findings)


def test_listing_basis_mismatch_skips_the_ceiling_check(tmp_path: Path):
    """A ceiling frozen on tokenizer basis is never compared against an estimate reading."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    _write_baseline(
        baseline_path,
        {
            "schema": 1,
            "listing_ceiling": 11_336,
            "listing_ceiling_basis": "tokenizer",
            "samples": [],
        },
    )
    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(20_000, measured=False))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "PASS"
    assert any("skipping the listing-ceiling check" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------


def test_run_never_writes_the_baseline_file(tmp_path: Path):
    """Unlike ratchet(), this collector must never mutate the baseline on disk."""
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    original = {
        "schema": 1,
        "listing_ceiling": 11_336,
        "listing_ceiling_basis": "tokenizer",
        "samples": [{"date": "2026-08-01", "governed_bytes": 90_000, "governed_tokens": 23_600}],
    }
    _write_baseline(baseline_path, original)
    before_mtime = baseline_path.stat().st_mtime_ns
    before_content = baseline_path.read_text(encoding="utf-8")

    fake = _FakeMeasureModule(_governed(20_000, 95_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake, today=date(2026, 9, 7)
    )
    family.run(corpus=object(), judge=object())

    assert baseline_path.stat().st_mtime_ns == before_mtime
    assert baseline_path.read_text(encoding="utf-8") == before_content


def test_corrupt_baseline_degrades_like_a_missing_one(tmp_path: Path):
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text("{not valid json", encoding="utf-8")
    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=baseline_path, measure_module=fake
    )

    result = family.run(corpus=object(), judge=object())[0]

    assert result.verdict == "PASS"
    assert any("no baseline file" in f for f in result.findings)


# ---------------------------------------------------------------------------
# mechanical_only invariance + no LLM call
# ---------------------------------------------------------------------------


def test_result_identical_regardless_of_mechanical_only(tmp_path: Path):
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=tmp_path, baseline_path=tmp_path / "absent.json", measure_module=fake
    )

    with_llm = family.run(corpus=object(), judge=object(), mechanical_only=False)
    mechanical_only = family.run(corpus=object(), judge=object(), mechanical_only=True)

    assert with_llm == mechanical_only


def test_judge_is_never_called():
    from praxion_evals.harness.families.family5_token_budget_stability import (
        Family5TokenBudgetStability,
    )

    class _ExplodingJudge:
        def judge(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Family 5 must never call judge.judge()")

    fake = _FakeMeasureModule(_governed(20_000, 90_000), _listing(3_000))
    family = Family5TokenBudgetStability(
        repo_root=Path("."), baseline_path=Path("/no/such/file.json"), measure_module=fake
    )

    family.run(corpus=object(), judge=_ExplodingJudge())


# ---------------------------------------------------------------------------
# run_eval() wiring proof
# ---------------------------------------------------------------------------


def test_family5_wired_into_run_eval():
    """run_eval()'s composition must include Family5TokenBudgetStability."""
    import inspect

    from praxion_evals import harness

    source = inspect.getsource(harness.run_eval)
    assert "Family5TokenBudgetStability" in source


def test_family5_module_source_contains_no_direct_sdk_imports():
    import inspect

    from praxion_evals.harness.families import family5_token_budget_stability

    source = inspect.getsource(family5_token_budget_stability)
    assert "import claude_agent_sdk" not in source
    assert "import anthropic" not in source
