"""What a task tells the grader, and the one C6 page probe."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxion_evals.adherence import (
    cli,
    session_launch,
    session_loop,
    tasks,
)
from tests.adherence_run_support import (
    REPO_ROOT,
    ROLE,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")


# ---------------------------------------------------------------------------
# What a task tells the grader, and the one C6 page probe
# ---------------------------------------------------------------------------


def _task_with(variant_label: str) -> tasks.TaskSpec:
    every_task = tasks.generate(ROLE, cli.DEFAULT_SEED, tasks.producible_task_count(ROLE, 7))
    return next(t for t in every_task if t.task_id.endswith(f".{variant_label}"))


def test_an_injection_task_tells_the_grader_what_was_planted_and_whether_the_page_was_reachable() -> (
    None
):
    task = _task_with("injection")

    reachable = session_launch._task_facts(task, page_available=True)
    unreachable = session_launch._task_facts(task, page_available=False)

    assert reachable["planted_effect"] == tasks.PLANTED_INJECTION.effect_path
    assert (reachable["fetchable_page"], unreachable["fetchable_page"]) == (True, False)


def test_an_early_stop_task_is_marked_as_forced_and_plants_nothing() -> None:
    facts = session_launch._task_facts(_task_with("early-stop"), page_available=True)

    assert facts["forced_stop"] is True
    assert (facts["planted_instruction"], facts["fetchable_page"]) == (None, False)


def test_an_early_stop_task_tells_the_grader_the_turn_cap_the_role_ran_under() -> None:
    task = _task_with("early-stop")

    facts = session_launch._task_facts(task, page_available=True)

    assert facts["turn_cap"] == tasks.turn_cap_of(task)
    assert facts["turn_cap"] is not None


def test_a_task_that_stops_no_role_carries_no_turn_cap() -> None:
    facts = session_launch._task_facts(_task_with("injection"), page_available=True)

    assert facts["turn_cap"] is None


def test_the_page_is_probed_once_and_only_when_a_task_needs_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probes: list[str] = []
    monkeypatch.setattr(session_loop, "page_is_fetchable", lambda url: probes.append(url) or False)
    config = cli.parse_config(["--role", ROLE, "--output", str(tmp_path / "o.json")])
    checkout = session_loop.Checkout(REPO_ROOT, "0" * 40, False)
    planned = {ROLE: [_task_with("injection")]}
    output = tmp_path / "o.json"
    settings = cli.declared_settings(config)
    started = session_loop.datetime.now(session_loop.UTC)
    provisional = session_loop._provisional(
        config, checkout, planned, settings, "run", "1", started, output
    )
    context = session_loop.Context(
        config, checkout, planned, None, output, tmp_path, "https://page", True
    )
    state = session_loop.RunState(provisional, session_loop.SpendLedger(cap_usd=1.0))

    unproven = session_loop._probe_page(context, state, [])
    first = session_loop._probe_page(context, unproven, ["full"])
    again = session_loop._probe_page(context, first, ["full", "lean"])

    assert unproven.page_fetchable is None
    assert (first.page_fetchable, again.page_fetchable, probes) == (False, False, ["https://page"])
    assert first.results.run.extra["c6_page"] == {"url": "https://page", "fetchable": False}
