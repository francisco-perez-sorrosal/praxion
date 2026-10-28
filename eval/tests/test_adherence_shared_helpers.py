"""The helpers the role runner and the move shell share, each now reachable by its own name:
the trailing streak of a failure, the chain of a lineage, and the pieces of one paid launch."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from praxion_evals.adherence.infra_stop import Failure, trailing_streak
from praxion_evals.adherence.lineage import PartRef, chain_of
from praxion_evals.adherence.session_launch import (
    new_sandbox_root,
    resolved_model,
    settle,
    tails_of,
)
from praxion_evals.live.session import SessionRun
from praxion_evals.live.spend import SpendLedger

TIMEOUT = Failure("timeout", "no output")
EXIT = Failure("exit_nonzero", "boom")


def _stream(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events)


INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5-5", "plugins": []}


def _result(**fields) -> dict:
    return {"type": "result", "subtype": "success", "is_error": False, "result": "", **fields}


# --- trailing_streak ---


@pytest.mark.parametrize(
    ("failures", "expected"),
    [
        ([], 0),
        ([TIMEOUT, None], 0),
        ([None, TIMEOUT, TIMEOUT], 2),
        ([TIMEOUT, EXIT, TIMEOUT], 1),
        ([TIMEOUT, TIMEOUT, None, TIMEOUT, TIMEOUT, TIMEOUT], 3),
    ],
)
def test_the_streak_counts_only_the_unbroken_tail_of_the_same_failure(failures, expected):
    assert trailing_streak(failures, TIMEOUT) == expected


# --- chain_of ---


def _parts(*links: tuple[str, str | None]) -> dict[str, PartRef]:
    return {run: PartRef(run, Path("/runs") / f"{run}.json", cont) for run, cont in links}


def test_any_part_resolves_to_the_whole_chain_root_first():
    parts = _parts(("a", None), ("b", "a"), ("c", "b"))
    expected = tuple(parts.values())
    assert [chain_of(parts, run) for run in parts] == [expected] * 3


def test_a_run_that_continues_nothing_and_is_continued_by_nothing_is_its_own_chain():
    parts = _parts(("a", None))
    assert chain_of(parts, "a") == (parts["a"],)


def test_a_missing_predecessor_is_a_gap_naming_the_results_directory():
    with pytest.raises(ValueError, match=r"gap: run b continues lost.*in /runs holds"):
        chain_of(_parts(("b", "lost")), "b")


def test_a_chain_that_continues_itself_loops():
    with pytest.raises(ValueError, match=r"loops: run a continues itself"):
        chain_of(_parts(("a", "b"), ("b", "a")), "a")


def test_two_parts_continuing_one_run_fork_even_off_the_named_branch():
    parts = _parts(("a", None), ("b", "a"), ("c", "a"), ("d", "b"))
    with pytest.raises(ValueError, match=r"forks: b, c all continue a"):
        chain_of(parts, "d")


# --- the launch helpers ---


def test_a_sandbox_root_is_fresh_and_sits_under_the_run_root_by_role(tmp_path: Path):
    launch, task = SimpleNamespace(run_root=tmp_path), SimpleNamespace(role="verifier")
    first, second = new_sandbox_root(launch, task), new_sandbox_root(launch, task)
    assert first != second
    assert first.parent == second.parent == tmp_path / "verifier" / "sessions"
    assert first.is_dir()


def test_a_session_settles_at_its_reported_cost_and_at_the_budget_when_it_reported_none():
    reserved = SpendLedger(cap_usd=10.0).reserve(2.0)
    run_with_cost = SessionRun(_stream(INIT, _result(total_cost_usd=0.5)), "", 0)
    ledger, charged = settle(reserved, 2.0, run_with_cost)
    assert (charged, ledger.spent_usd, ledger.reserved_usd) == (0.5, 0.5, 0.0)
    ledger, charged = settle(reserved, 2.0, SessionRun("", "", 0))
    assert (charged, ledger.spent_usd, ledger.reserved_usd) == (2.0, 2.0, 0.0)


def test_the_resolved_model_is_the_one_the_init_event_reported_else_none():
    assert resolved_model(SessionRun(_stream(INIT, _result()), "", 0)) == "claude-opus-5-5"
    assert resolved_model(SessionRun("", "", 0)) is None


def test_the_tails_keep_the_end_of_each_stream_and_redact_the_session_credentials():
    secret = "sk-ant-oat01-" + "x" * 20
    stdout = _stream(INIT, _result(result=f"done using {secret}"))
    tails = tails_of(
        SessionRun(stdout, f"trace {secret}", 1), {"CLAUDE_CODE_OAUTH_TOKEN": secret}, 40
    )
    assert secret not in tails.error_tail + tails.result_tail
    assert tails.error_tail.startswith("trace")
    assert tails.result_tail.startswith("done")
