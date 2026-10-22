"""Tests for what `record` does with a return that called its scope incomplete
(``scripts/_step_loop_record.py``).

A [CONFLICT] or [BLOCKED] return commits nothing and ticks nothing whatever the check shows,
and is still one ledger record with no commit; [PARTIAL] keeps the rule that the check decides.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

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
    """`record_return` over a verified gate, with the effects it would have recorded.

    The names `record_return` calls are replaced with explicit-signature stand-ins, `_pending`
    among them; the acceptance nodes in the step's Check pin the same behavior end to end.
    `read_return` stands for the resolved marker, so `relayed` can differ from it.
    """
    effects = SimpleNamespace(committed=[], ticked=[], ledger=[])
    key = RequestKey(step="1", attempt=1, kind="implement")
    gate = SimpleNamespace(deciding="Result: pass=1 fail=0 skip=0 pending=0 by=step-loop")
    inputs = LoopInputs(steps=(THE_STEP,), attempts={}, records=(), verdicts={})
    task = SimpleNamespace(slug="demo", dir=tmp_path, repo=tmp_path, inputs=inputs)
    asked = SimpleNamespace(key=key, agent_call=SimpleNamespace(subagent_type="implementer"))

    def take_back(resolved, relayed=None):
        def pending(inputs, request):
            return SimpleNamespace(step=THE_STEP, key=key)

        def the_request(slug, step, key, cap, task_dir):
            return asked

        def the_end(repo, request, agent_id, max_turns, exited=False):
            return SimpleNamespace(turns=5)

        def the_return(seen, relayed_marker, asked, max_turns):
            return resolved, rec.derive_stop_reason(resolved, seen.turns, max_turns), ()

        def commit(task, step, asked, deciding):
            effects.committed.append(step.id)
            return rec.Committing(COMMIT, None)

        monkeypatch.setattr(rec, "_pending", pending)
        monkeypatch.setattr(rec, "spawn_request", the_request)
        monkeypatch.setattr(rec, "declared_max_turns", lambda subagent_type: 100)
        monkeypatch.setattr(rec, "await_end", the_end)
        monkeypatch.setattr(rec, "read_return", the_return)
        monkeypatch.setattr(rec, "run_gate", lambda task, step, request: gate)
        monkeypatch.setattr(
            rec,
            "read_verdict",
            lambda task, step_id, request, gate: {"verdict": VERIFIED, "decided_by": "check"},
        )
        monkeypatch.setattr(rec, "commit_attempt", commit)
        monkeypatch.setattr(rec, "tick_step", lambda wip, step_id: effects.ticked.append(step_id))
        monkeypatch.setattr(
            rec, "append_ledger_record", lambda task_dir, record: effects.ledger.append(record)
        )
        monkeypatch.setattr(rec, "settle_replan", lambda wip, inputs, step, request: False)
        monkeypatch.setattr(rec, "edit_warnings", lambda task, step, request: ())
        taken = rec.record_return(cast(rec.TaskView, task), REQUEST, "agent-1", relayed or resolved)
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

    assert (effects.committed, effects.ticked) == (["1"], ["1"])
    assert taken.recorded["commit"] == COMMIT


def test_the_transcripts_marker_outranks_a_relayed_complete(returned):
    effects, taken = returned("conflict", relayed="complete")

    assert (effects.committed, effects.ticked) == ([], [])
    assert taken.recorded["commit"] is None
