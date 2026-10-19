"""The infrastructure stop over a whole paid run: a scripted `claude` ends each task session as
a test says, and the run stops itself after exactly the declared count of identical failures of
one arm, launching nothing more, while outcomes that never count leave it going."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import lineage, model, results, session_loop
from praxion_evals.adherence.arms import PROOF_LABEL
from praxion_evals.adherence.infra_stop import StopReason
from praxion_evals.adherence.model import Errored, Failed, Measured
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.adherence_run_support import (
    ROLE,
    Script,
    run_small,
)

# Every task launches full first, as these runs count sessions.
pytestmark = pytest.mark.usefixtures("full_first", "unswitched_checkout")

Ending = Callable[[Script, SessionSpec, dict[str, str]], SessionRun]
STOP_RUN = ["--required-pairs", "5"]  # five tasks per arm: room for a streak and what follows
CREDIT = "API Error: request req_{0}x at 2026-10-16T09:12:0{0}Z: credit balance is too low"
REFUSED = "API Error: Connection error: connect ECONNREFUSED 127.0.0.1:443"
CRASH = "fatal: the session channel closed unexpectedly"


class Endings(Script):
    """Ends each task session of an arm as that arm's list says, in launch order; a session past
    the list, and every proof, answers as usual. ``arms`` logs the task sessions' arms."""

    def __init__(self, **by_arm: list[Ending]):
        super().__init__()
        self.by_arm = by_arm
        self.arms: list[str] = []

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        if PROOF_LABEL in spec.prompt:
            return super().__call__(spec, env)
        arm = "lean" if "lean" in spec.plugin_dir.name else "full"
        self.arms.append(arm)
        planned = self.by_arm.get(arm, [])
        position = self.arms.count(arm) - 1
        if position >= len(planned):
            return super().__call__(spec, env)
        return planned[position](self, spec, env)


def _error_result(text: str) -> Ending:
    """An error ``result`` event carrying ``text``, which the error output repeats; never retried."""
    event = {"type": "result", "subtype": "success", "is_error": True, "result": text}
    stream = json.dumps({**event, "total_cost_usd": 0.01})
    return lambda script, spec, env: SessionRun(stream, text, 1)


def _credit(variant: int = 0) -> Ending:
    """A spent credit balance; variants differ only in a request id and a timestamp."""
    return _error_result(CREDIT.format(variant))


def _crash(text: str) -> Ending:
    """A non-zero exit with ``text`` on the error output and no result; retried once."""
    return lambda script, spec, env: SessionRun("", text, 3)


def _ran(script: Script, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
    return Script.__call__(script, spec, env)


def _breach(script: Script, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
    """A session that ran, with an MCP server leaked into its sandbox."""
    leaked = '"mcp_servers": [{"name": "leaked"}]'
    return SessionRun(script._stream(spec, env).replace('"mcp_servers": []', leaked), "", 0)


def _graded_failure(script: Script, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
    """A session that ran and whose role returned no terminal marker."""
    return SessionRun(script._stream(spec, env).replace("[COMPLETE]", ""), "", 0)


def _how_it_ended(record: model.SessionRecord) -> str:
    status = record.status
    if isinstance(status, Errored):
        return status.kind
    failed = isinstance(status, Measured) and any(
        isinstance(outcome, Failed) for outcome in status.outcomes.values()
    )
    return "graded failure" if failed else type(status).__name__


def _stop_run(
    paid: Callable[[Script], None], tmp_path: Path, script: Endings, *options: str
) -> results.RunResults:
    paid(script)
    return run_small(tmp_path, *STOP_RUN, *options)[1]


def _stop_of(loaded: results.RunResults) -> StopReason:
    ending = lineage.ending_of(loaded)
    assert isinstance(ending, lineage.InfraStopped), f"the run ended {ending}, not in a stop"
    return ending.reason


def _finished(loaded: results.RunResults) -> bool:
    return isinstance(lineage.ending_of(loaded), lineage.Finished)


def test_n_identical_errors_of_one_arm_stop_the_run_after_exactly_n_sessions_of_that_arm(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_credit()] * 5)
    paid(script)

    code, loaded = run_small(tmp_path, *STOP_RUN)

    stop = _stop_of(loaded)
    assert code == session_loop.EXIT_INCOMPLETE
    assert not loaded.run.complete
    assert script.arms == ["full", "lean"] * 3, "a session launched after the third lean error"
    assert (stop.kind, stop.arm, stop.scope) == ("result_error", "lean", "one-arm")
    assert "credit balance is too low" in stop.masked_tail
    assert [s.task_id for s in stop.sessions] == [
        r.setup.task_id for r in loaded.sessions if r.setup.arm == "lean"
    ]
    assert len(loaded.sessions) == 6, "a recorded session was dropped"


def test_a_retry_is_the_arms_next_session_and_a_stop_on_it_launches_no_retry(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_crash(CRASH)] * 5)

    loaded = _stop_run(paid, tmp_path, script, "--arm", "lean")

    assert [s.attempt for s in _stop_of(loaded).sessions] == [1, 2, 1]
    assert script.arms == ["lean"] * 3, "the stopping session was retried"
    assert len(loaded.run.extra["retries"]) == 1


def test_tails_differing_only_in_masked_tokens_stop_the_run(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_credit(variant) for variant in range(5)])

    loaded = _stop_run(paid, tmp_path, script)

    assert "<request-id>" in _stop_of(loaded).masked_tail
    assert script.arms.count("lean") == 3


def test_two_different_errors_of_one_kind_never_merge_into_a_streak(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_credit(), _error_result(REFUSED)] * 3)

    loaded = _stop_run(paid, tmp_path, script)

    assert _finished(loaded)
    assert script.arms.count("lean") == 5


@pytest.mark.parametrize(
    "lean",
    [
        pytest.param([_crash(CRASH), _crash(CRASH), _ran], id="a task and its retry"),
        pytest.param([_credit(), _credit(), _ran, _credit(), _credit()], id="n-1"),
    ],
)
def test_a_session_that_ran_after_fewer_than_n_identical_errors_breaks_the_streak(
    paid: Callable[[Script], None], tmp_path: Path, lean: list[Ending]
) -> None:
    script = Endings(lean=lean)

    loaded = _stop_run(paid, tmp_path, script, "--arm", "lean")

    assert _finished(loaded)
    assert script.arms.count("lean") >= 5


@pytest.mark.parametrize(
    ("ending", "label"),
    [
        pytest.param(_breach, "isolation_breach", id="isolation breaches"),
        pytest.param(_graded_failure, "graded failure", id="graded failures"),
    ],
)
def test_n_sessions_ending_in_an_outcome_that_never_counts_leave_the_run_going(
    paid: Callable[[Script], None], tmp_path: Path, ending: Ending, label: str
) -> None:
    script = Endings(full=[ending] * 5)

    loaded = _stop_run(paid, tmp_path, script)

    assert _finished(loaded)
    assert [_how_it_ended(r) for r in loaded.sessions if r.setup.arm == "full"] == [label] * 5


@pytest.mark.parametrize(
    ("by_arm", "scope", "said"),
    [
        pytest.param({"lean": [_credit()] * 5}, "one-arm", "; not continuable.", id="one arm"),
        pytest.param(
            {"full": [_credit()] * 5, "lean": [_credit()] * 5},
            "both-arms",
            "; continuable.",
            id="both arms",
        ),
    ],
)
def test_the_report_states_the_stop_and_whether_it_can_be_continued(
    paid: Callable[[Script], None],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    by_arm: dict[str, list[Ending]],
    scope: str,
    said: str,
) -> None:
    loaded = _stop_run(paid, tmp_path, Endings(**by_arm))

    printed = capsys.readouterr().out

    assert _stop_of(loaded).scope == scope
    assert "The run stopped itself: 3 " in printed
    assert said in printed


def test_the_declared_tail_bound_clips_an_errored_sessions_tails(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_crash(CRASH)])

    loaded = _stop_run(paid, tmp_path, script, "--arm", "lean", "--tail-chars", "7")

    status = loaded.sessions[0].status
    assert isinstance(status, Errored)
    assert status.tails is not None
    assert status.tails.error_tail == CRASH[-7:]


def test_a_declared_stop_count_stops_the_run_after_exactly_that_many_sessions_of_one_arm(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_credit()] * 5)

    loaded = _stop_run(paid, tmp_path, script, "--stop-count", "4")

    assert len(_stop_of(loaded).sessions) == 4
    assert script.arms == ["full", "lean"] * 4, "the run did not stop at the declared count"


def _proven_roles(script: Script) -> set[str]:
    proofs = (spec.prompt for spec in script.specs if PROOF_LABEL in spec.prompt)
    return {re.search(r"praxion:([a-z-]+)", prompt).group(1) for prompt in proofs}  # type: ignore[union-attr]


def test_a_stop_in_one_role_proves_and_launches_nothing_for_the_roles_after_it(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_credit()] * 5)

    loaded = _stop_run(paid, tmp_path, script, "--role", "verifier")

    assert _stop_of(loaded).role == ROLE
    assert _proven_roles(script) == {ROLE}, "a later role's arms were proven"
    assert {r.setup.role for r in loaded.sessions} == {ROLE}


def _budget_stopped(script: Script, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
    """A session its own spend budget stopped: an error ``result`` of the budget subtype, with
    nothing on either stream for its tails to keep."""
    event = {"type": "result", "subtype": "error_max_budget_usd", "is_error": True}
    return SessionRun(json.dumps({**event, "total_cost_usd": 0.01}), "", 1)


def test_sessions_their_own_spend_budget_stopped_never_count_toward_the_stop(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Endings(lean=[_budget_stopped] * 5)

    loaded = _stop_run(paid, tmp_path, script)

    assert _finished(loaded)
    assert [_how_it_ended(r) for r in loaded.sessions if r.setup.arm == "lean"] == [
        "result_error"
    ] * 5, "a budget stop stays the lean side's error, which the worst-case recount fails"
