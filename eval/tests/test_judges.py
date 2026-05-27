"""Tests for eval stub modules — Tier 2 markers."""

from __future__ import annotations

import pytest


def test_cost_stub_raises_not_implemented():
    from praxion_evals.stubs.cost import run_cost

    with pytest.raises(NotImplementedError, match="Tier 2 stub"):
        run_cost()


def test_decision_quality_stub_raises_not_implemented():
    from praxion_evals.stubs.decision_quality import run_decision_quality

    with pytest.raises(NotImplementedError, match="Tier 2 stub"):
        run_decision_quality()
