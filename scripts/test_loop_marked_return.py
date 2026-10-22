"""Tests for what `record` does with a return that called its scope incomplete
(``scripts/_step_loop_record.py``).

A [CONFLICT] or [BLOCKED] return commits nothing and ticks nothing whatever the check shows,
and is still one ledger record with no commit; [PARTIAL] keeps the rule that the check decides.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record as rec  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
from _step_loop_state import VERIFIED, LoopInputs  # noqa: E402

REQUEST = "s1-a1-implement"
COMMIT = "c" * 40
STEP_ID = 1
PLAN = (
    f"# Plan\n\n## Steps\n\n### Step {STEP_ID}: Do it\n\n**Assignee**: implementer\n"
    "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0\n"
)
THE_STEP = parse_plan_steps(PLAN)[0]
UNVERIFIED = "mismatch"


@pytest.mark.parametrize(
    ("verdict_word", "stop_reason", "commits"),
    [
        (VERIFIED, "completed", True),
        (VERIFIED, "partial", True),
        (VERIFIED, "turn-cap", True),
        (VERIFIED, "no-marker", True),
        (VERIFIED, "blocked", False),
        (VERIFIED, "conflict", False),
        (UNVERIFIED, "completed", False),
        (UNVERIFIED, "blocked", False),
    ],
)
def test_only_a_verified_attempt_that_did_not_call_its_scope_incomplete_commits(
    verdict_word, stop_reason, commits
):
    assert rec.commits_work(verdict_word, stop_reason) is commits


@pytest.fixture
def returned(monkeypatch, tmp_path):
    """`record_return` over a verified gate, with the effects it would have recorded."""
    effects = SimpleNamespace(committed=[], ticked=[], ledger=[])
    key = RequestKey("1", 1, "implement", 1, None)
    spawn = SimpleNamespace(step=THE_STEP, key=key)
    gate = SimpleNamespace(deciding="Result: pass=1 fail=0 skip=0 pending=0 by=step-loop")
    inputs = LoopInputs((THE_STEP,), {}, (), {})
    task = SimpleNamespace(slug="demo", dir=tmp_path, repo=tmp_path, inputs=inputs)

    def take_back(marker):
        monkeypatch.setattr(rec, "_pending", lambda *_: spawn)
        asked = SimpleNamespace(key=key, agent_call=SimpleNamespace(subagent_type="implementer"))
        monkeypatch.setattr(rec, "spawn_request", lambda *_: asked)
        monkeypatch.setattr(rec, "declared_max_turns", lambda *_: 100)
        monkeypatch.setattr(rec, "await_end", lambda *_, **__: SimpleNamespace(turns=5))
        monkeypatch.setattr(
            rec, "read_return", lambda *_: (marker, rec.derive_stop_reason(marker, 5, 100), ())
        )
        monkeypatch.setattr(rec, "run_gate", lambda *_: gate)
        monkeypatch.setattr(
            rec, "read_verdict", lambda *_: {"verdict": VERIFIED, "decided_by": "check"}
        )
        monkeypatch.setattr(
            rec,
            "commit_attempt",
            lambda *_: effects.committed.append(1) or rec.Committing(COMMIT, None),
        )
        monkeypatch.setattr(rec, "tick_step", lambda _wip, step: effects.ticked.append(step))
        monkeypatch.setattr(rec, "append_ledger_record", lambda _dir, r: effects.ledger.append(r))
        monkeypatch.setattr(rec, "settle_replan", lambda *_: False)
        monkeypatch.setattr(rec, "edit_warnings", lambda *_: ())
        taken = rec.record_return(task, REQUEST, "agent-1", marker)
        return effects, taken

    return take_back


@pytest.mark.parametrize("marker", ["conflict", "blocked"])
def test_a_marked_return_whose_check_passes_commits_nothing_and_ticks_nothing(returned, marker):
    effects, taken = returned(marker)

    assert (effects.committed, effects.ticked) == ([], [])
    assert taken.recorded["commit"] is None


@pytest.mark.parametrize("marker", ["conflict", "blocked"])
def test_a_marked_return_is_one_ledger_record_with_no_commit(returned, marker):
    effects, _ = returned(marker)

    (written,) = effects.ledger
    assert (written.commit, written.stop_reason) == (None, marker)


@pytest.mark.parametrize("marker", ["complete", "partial"])
def test_an_unmarked_return_whose_check_passes_commits_and_ticks_the_step(returned, marker):
    effects, taken = returned(marker)

    assert (effects.committed, effects.ticked) == ([1], ["1"])
    assert taken.recorded["commit"] == COMMIT
