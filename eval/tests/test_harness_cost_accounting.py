"""Behavioral tests for usage summation and cost estimation.

schemas.sum_usage() aggregates JudgeUsage across a run's CheckResults;
judge_client.estimate_cost_usd() prices that aggregate against a judge
model's rate. Both are pure functions — no network, no fixtures.

All production imports are deferred inside each test body (RED-state
handshake, matching the rest of this test suite).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# sum_usage(): aggregation across CheckResults
# ---------------------------------------------------------------------------


def test_sum_usage_adds_across_multiple_check_results():
    """Two judged CheckResults with usage sum field-by-field."""
    from praxion_evals.harness.schemas import CheckResult, JudgeUsage, sum_usage

    results = [
        CheckResult(
            check_name="a",
            check_kind="llm",
            verdict="PASS",
            artifact_path="a.md",
            findings=(),
            usage=JudgeUsage(
                input_tokens=100,
                output_tokens=10,
                cache_read_input_tokens=5,
                cache_creation_input_tokens=2,
            ),
        ),
        CheckResult(
            check_name="b",
            check_kind="llm",
            verdict="PASS",
            artifact_path="b.md",
            findings=(),
            usage=JudgeUsage(input_tokens=50, output_tokens=5),
        ),
    ]

    totals = sum_usage(results)

    assert totals == JudgeUsage(
        input_tokens=150,
        output_tokens=15,
        cache_read_input_tokens=5,
        cache_creation_input_tokens=2,
    )


def test_sum_usage_skips_check_results_with_no_usage():
    """A mechanical CheckResult (usage=None) contributes zero, not an error."""
    from praxion_evals.harness.schemas import CheckResult, JudgeUsage, sum_usage

    results = [
        CheckResult(
            check_name="mechanical",
            check_kind="mechanical",
            verdict="PASS",
            artifact_path="x.md",
            findings=(),
        ),
        CheckResult(
            check_name="llm",
            check_kind="llm",
            verdict="PASS",
            artifact_path="y.md",
            findings=(),
            usage=JudgeUsage(input_tokens=10, output_tokens=1),
        ),
    ]

    totals = sum_usage(results)

    assert totals == JudgeUsage(input_tokens=10, output_tokens=1)


def test_sum_usage_of_empty_sequence_is_all_zero():
    from praxion_evals.harness.schemas import JudgeUsage, sum_usage

    assert sum_usage([]) == JudgeUsage()


# ---------------------------------------------------------------------------
# estimate_cost_usd(): price table application
# ---------------------------------------------------------------------------


def test_estimate_cost_usd_prices_input_and_output_at_haiku_rates():
    """1M input + 1M output tokens at $1/$5 per MTok = $6.00."""
    from praxion_evals.harness.judge_client import estimate_cost_usd
    from praxion_evals.harness.schemas import JudgeUsage

    usage = JudgeUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    cost = estimate_cost_usd("claude-haiku-4-5", usage)

    assert cost == 6.00


def test_estimate_cost_usd_discounts_cache_reads_and_premiums_cache_writes():
    """Cache reads bill at 10% of input rate; cache writes at 125%."""
    from praxion_evals.harness.judge_client import estimate_cost_usd
    from praxion_evals.harness.schemas import JudgeUsage

    usage = JudgeUsage(cache_read_input_tokens=1_000_000, cache_creation_input_tokens=1_000_000)

    cost = estimate_cost_usd("claude-haiku-4-5", usage)

    # input rate $1.00/MTok: 10% read + 125% write = $0.10 + $1.25
    assert cost == 1.35


def test_estimate_cost_usd_unknown_model_returns_none():
    """A model absent from the price table is 'unpriced', not zero-cost —
    even when the usage itself is all zeros."""
    from praxion_evals.harness.judge_client import estimate_cost_usd
    from praxion_evals.harness.schemas import JudgeUsage

    assert estimate_cost_usd("some-future-model", JudgeUsage()) is None


def test_estimate_cost_usd_zero_usage_on_known_model_is_zero_not_none():
    from praxion_evals.harness.judge_client import estimate_cost_usd
    from praxion_evals.harness.schemas import JudgeUsage

    assert estimate_cost_usd("claude-haiku-4-5", JudgeUsage()) == 0.0
