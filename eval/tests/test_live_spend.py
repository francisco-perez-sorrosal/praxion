"""Behavioral tests for the live runner's run-level spend cap.

`SpendLedger` is the single cap mechanism shared by the runner and the
envelope recorder: every launch first reserves its worst case (the session's
own `--max-budget-usd`) and is refused with a typed `not_run_budget_exhausted`
outcome when that reservation would cross the cap; a finished session settles
at its reported `total_cost_usd`, or at its full budget when the envelope
reported no cost (a timeout or crash may still have spent it).
"""

from __future__ import annotations

import pytest


def test_a_launch_within_the_cap_is_reserved_at_its_budget():
    from praxion_evals.live.spend import SpendLedger

    ledger = SpendLedger(cap_usd=10.0).reserve(3.0)

    assert isinstance(ledger, SpendLedger)
    assert ledger.reserved_usd == 3.0
    assert ledger.spent_usd == 0.0


def test_a_launch_that_would_cross_the_cap_is_refused_with_a_typed_outcome():
    from praxion_evals.live.results import Errored
    from praxion_evals.live.spend import SpendLedger

    ledger = SpendLedger(cap_usd=10.0, spent_usd=8.5)

    refusal = ledger.reserve(2.0)

    assert isinstance(refusal, Errored)
    assert refusal.kind == "not_run_budget_exhausted"
    assert "10.00" in refusal.detail


def test_a_launch_that_lands_exactly_on_the_cap_is_allowed():
    from praxion_evals.live.spend import SpendLedger

    assert isinstance(SpendLedger(cap_usd=10.0, spent_usd=7.0).reserve(3.0), SpendLedger)


def test_in_flight_reservations_count_against_the_cap():
    """Two concurrent launches cannot both claim the last dollars."""
    from praxion_evals.live.results import Errored
    from praxion_evals.live.spend import SpendLedger

    first = SpendLedger(cap_usd=5.0).reserve(3.0)
    assert isinstance(first, SpendLedger)

    assert isinstance(first.reserve(3.0), Errored)


def test_settling_charges_the_reported_cost_and_releases_the_reservation():
    from praxion_evals.live.spend import SpendLedger

    reserved = SpendLedger(cap_usd=10.0).reserve(3.0)
    assert isinstance(reserved, SpendLedger)

    settled = reserved.settle(3.0, cost_usd=0.243873)

    assert settled.reserved_usd == 0.0
    assert settled.spent_usd == pytest.approx(0.243873)


def test_settling_an_unreported_cost_charges_the_full_budget():
    """A timed-out or crashed session reports no cost but may have spent its budget."""
    from praxion_evals.live.spend import SpendLedger

    reserved = SpendLedger(cap_usd=10.0).reserve(3.0)
    assert isinstance(reserved, SpendLedger)

    assert reserved.settle(3.0, cost_usd=None).spent_usd == 3.0


def test_the_ledger_rejects_a_non_positive_cap():
    from praxion_evals.live.spend import SpendLedger

    with pytest.raises(ValueError, match="cap"):
        SpendLedger(cap_usd=0.0)


def test_the_runner_and_recorder_caps_are_fifty_and_ten_dollars():
    from praxion_evals.live.spend import RECORDER_SPEND_CAP_USD, RUNNER_SPEND_CAP_USD

    assert RUNNER_SPEND_CAP_USD == 50.0
    assert RECORDER_SPEND_CAP_USD == 10.0
