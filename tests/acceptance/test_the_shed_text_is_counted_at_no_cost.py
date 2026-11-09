"""The text a split recipient sheds is counted, per rule and in total, by a command that makes
no model request; its split figure is the length of what rule delivery gives a split recipient.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers.audience_split import REPO_ROOT, SPLIT_UNITS


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return split.fresh_project(tmp_path / "project")


def _chars(delivery: split.Delivery, unit: split.Unit) -> int:
    return sum(len(s) for s in delivery.unit_strings(unit))


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_the_split_figure_is_what_a_split_recipient_receives(
    tmp_path: Path, project: Path, unit: split.Unit
) -> None:
    received = split.spawn(REPO_ROOT, project, "praxion:verifier")

    count = split.shed_count(REPO_ROOT, tmp_path / "count")

    assert count.units[unit.id].split_chars == _chars(received, unit)


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_the_whole_figure_is_what_a_whole_recipient_receives(
    tmp_path: Path, project: Path, unit: split.Unit
) -> None:
    received = split.spawn(REPO_ROOT, project, "general-purpose")

    count = split.shed_count(REPO_ROOT, tmp_path / "count")

    assert count.units[unit.id].whole_chars == _chars(received, unit)


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_each_rules_difference_is_its_whole_less_its_split(
    tmp_path: Path, unit: split.Unit
) -> None:
    figure = split.shed_count(REPO_ROOT, tmp_path / "count").units[unit.id]

    assert figure.difference == figure.whole_chars - figure.split_chars > 0


def test_the_total_is_the_sum_over_both_rules(tmp_path: Path) -> None:
    count = split.shed_count(REPO_ROOT, tmp_path / "count")

    assert (count.total.whole_chars, count.total.split_chars, count.total.difference) == (
        sum(count.units[u.id].whole_chars for u in SPLIT_UNITS),
        sum(count.units[u.id].split_chars for u in SPLIT_UNITS),
        sum(count.units[u.id].difference for u in SPLIT_UNITS),
    )


def test_the_token_figure_is_labelled_with_its_basis(tmp_path: Path) -> None:
    total = split.shed_count(REPO_ROOT, tmp_path / "count").total

    assert total.token_basis in {"tokenizer", "estimate"}
    assert total.tokens > 0


def test_counting_makes_no_model_request_and_needs_no_network(tmp_path: Path) -> None:
    trap = split.model_request_trap(tmp_path / "trap")

    count = split.shed_count(REPO_ROOT, tmp_path / "count", trap=trap)

    assert (count.exit_code, trap.recorded()) == (0, [])
