"""Tests for judge stubs — Tier 2 marker test."""

from __future__ import annotations

import importlib

import pytest


def test_judges_package_importable():
    import praxion_evals.judges  # noqa: F401 — import is the assertion
    import praxion_evals.judges.anthropic  # noqa: F401
    import praxion_evals.judges.openai  # noqa: F401


def test_anthropic_judge_raises_not_implemented():
    anthropic = importlib.import_module("praxion_evals.judges.anthropic")
    with pytest.raises(NotImplementedError, match="Tier 2"):
        anthropic.main()


def test_cost_stub_raises_not_implemented():
    from praxion_evals.stubs.cost import run_cost

    with pytest.raises(NotImplementedError, match="Tier 2 stub"):
        run_cost()


def test_decision_quality_stub_raises_not_implemented():
    from praxion_evals.stubs.decision_quality import run_decision_quality

    with pytest.raises(NotImplementedError, match="Tier 2 stub"):
        run_decision_quality()
