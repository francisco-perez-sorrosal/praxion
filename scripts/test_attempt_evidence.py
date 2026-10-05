"""Tests for attempt evidence: started in ``WIP.md``, ended in the iteration ledger.

An attempt whose request the ledger has not recorded is still running, so the
step reads ``in-flight`` and never ``attempts-exhausted``; once recorded without
verified completion the cap applies. ``reconcile(..., assume_recorded=...)`` gives
the post-record verdict before the record exists, and a ``WIP.md`` without a
request token reads exactly as it did before the token existed. The first group
is the pure policy, the second the reconciler over a temporary task directory.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_verdict as verdicts  # noqa: E402
import reconcile_pipeline_state as rps  # noqa: E402
from _loop_fields import (  # noqa: E402
    ATTEMPT_CAP,
    Attempt,
    Met,
    NoResult,
    OutstandingAttempt,
    Unmet,
    UnmetExpectation,
    UnreadableCheck,
)
from iteration_ledger import (  # noqa: E402
    LEDGER_FILE,
    NO_RESULT_RECORDED,
    IterationRecord,
    append_record,
)

STEP_LABEL = "Step "
STEP_ID = "1"
STEP = f"{STEP_LABEL}{STEP_ID}"
REQUEST = "s1-a2-implement"
OTHER_REQUEST = "s1-a1-implement"
SLUG = "attempt-evidence"
FILES = ["a.py", "b.py"]
NO_AGENT = {"agent_stop_seen": False, "last_write": None}

PLAN = f"""## Steps

### {STEP}: Build the thing
**Files**: src/a.py, src/b.py
"""

PLAN_WITH_CHECK = PLAN + "**Check**: `pytest tests/test_a.py -q` expects pass>=1 fail=0\n"


# ---------------------------------------------------------------------------
# The pure policy
# ---------------------------------------------------------------------------


def evidence(**overrides: Any) -> verdicts.StepEvidence:
    """The step with nothing changed yet and no claim of completion."""
    fields: dict[str, Any] = {
        "step_id": STEP,
        "claim": "PENDING",
        "files": list(FILES),
        "changed": [],
        "unchanged": list(FILES),
        "test_status": "green",
        "tier2": dict(NO_AGENT),
    }
    return verdicts.StepEvidence(**{**fields, **overrides})


def test_an_outstanding_capped_attempt_reads_in_flight_naming_its_request() -> None:
    result = verdicts.classify_step(evidence(), None, OutstandingAttempt(ATTEMPT_CAP, REQUEST))

    assert (result["verdict"], result["attempt"]) == ("in-flight", ATTEMPT_CAP)
    assert result["evidence"] == (
        f"attempt {ATTEMPT_CAP} is outstanding under request {REQUEST} (started, no ledger "
        "record yet); underlying verdict pending: step not started (no file changes)"
    )


def test_the_same_capped_attempt_once_ended_reads_attempts_exhausted() -> None:
    result = verdicts.classify_step(evidence(), None, Attempt(ATTEMPT_CAP, request=REQUEST))

    assert result["verdict"] == "attempts-exhausted"


def test_an_outstanding_attempt_over_a_step_not_started_is_decided_by_nothing() -> None:
    result = verdicts.classify_step(evidence(), None, OutstandingAttempt(1, REQUEST))

    assert result["decided_by"] == "none"


@pytest.mark.parametrize(
    ("ev", "check", "underlying"),
    [
        pytest.param(evidence(), None, "pending", id="not-started"),
        pytest.param(evidence(claim="COMPLETE"), NoResult("none"), "mismatch", id="claimed"),
        pytest.param(evidence(), UnreadableCheck("broken", "Check: x"), "unknown", id="unreadable"),
        pytest.param(
            evidence(changed=list(FILES), unchanged=[], mutation_block="no reading"),
            None,
            "blocked",
            id="mutation-blocked",
        ),
        pytest.param(
            evidence(changed=["a.py"], unchanged=["b.py"], tier2={"agent_stop_seen": True}),
            None,
            "partial@?",
            id="partial",
        ),
    ],
)
def test_an_outstanding_attempt_is_in_flight_whatever_the_step_would_have_read(
    ev: verdicts.StepEvidence, check: Any, underlying: str
) -> None:
    result = verdicts.classify_step(ev, check, OutstandingAttempt(ATTEMPT_CAP, REQUEST))

    assert result["verdict"] == "in-flight"
    assert f"underlying verdict {underlying}:" in result["evidence"]


def test_an_outstanding_attempt_never_overrides_a_verified_completion() -> None:
    done = evidence(changed=list(FILES), unchanged=[])

    result = verdicts.classify_step(done, None, OutstandingAttempt(ATTEMPT_CAP, REQUEST))

    assert (result["verdict"], result["attempt"]) == ("verified-complete", ATTEMPT_CAP)


@pytest.mark.parametrize(
    ("outcome", "source"),
    [
        pytest.param(Met(by_step_loop=True), "run", id="met-by-driver"),
        pytest.param(
            Unmet((UnmetExpectation("fail", "=", 0, 1),), by_step_loop=True), "run", id="unmet"
        ),
        pytest.param(Met(), "recorded", id="met-by-agent"),
        pytest.param(NoResult("no Result: recorded"), "recorded", id="no-result"),
    ],
)
def test_outcome_source_is_run_exactly_when_the_driver_ran_the_deciding_line(
    outcome: Any, source: str
) -> None:
    claimed = evidence(changed=list(FILES), unchanged=[], claim="COMPLETE")

    assert verdicts.classify_step(claimed, outcome, None)["outcome_source"] == source


def test_only_an_override_may_carry_the_verdict_it_replaced() -> None:
    kept = verdicts.Decision("in-flight", "text", [], underlying="pending")

    assert kept.underlying == "pending"
    with pytest.raises(ValueError, match="attempts-exhausted"):
        verdicts.Decision("partial@a.py", "text", [], underlying="pending")


# ---------------------------------------------------------------------------
# The reconciler: the ledger decides what ended
# ---------------------------------------------------------------------------


def attempts_line(request: str | None = REQUEST) -> str:
    token = f" request={request}" if request is not None else ""
    return f"- [ ] {STEP}: build\n  - Attempts: {STEP} count={ATTEMPT_CAP}{token}\n"


def task(tmp_path: Path, wip: str, plan: str = PLAN, results: str = "") -> Path:
    task_dir = tmp_path / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task_dir / "TEST_RESULTS.md").write_text(results, encoding="utf-8")
    return task_dir


def record(task_dir: Path, request: str) -> None:
    """Append the ledger record of an attempt that ended unverified."""
    append_record(
        task_dir,
        IterationRecord(
            step=STEP,
            attempt=ATTEMPT_CAP,
            agent_id="agent-1",
            verdict="pending",
            decided_by="none",
            test_result=NO_RESULT_RECORDED,
            commit=None,
            stop_reason="no-marker",
            request=request,
        ),
    )


def break_the_ledger(task_dir: Path) -> None:
    """Append a line that breaks the record shape, as a truncated append leaves one."""
    with (task_dir / LEDGER_FILE).open("a", encoding="utf-8") as ledger:
        ledger.write('{"v": 1, "step": \n')


def reconcile(tmp_path: Path, **seams: Any) -> list[dict[str, Any]]:
    return rps.reconcile(
        SLUG, tmp_path, None, _changed_files_override=[], _wal_rows_override=[], **seams
    )


def test_a_capped_attempt_the_ledger_has_not_recorded_reads_in_flight(tmp_path: Path) -> None:
    task(tmp_path, attempts_line())

    (verdict,) = reconcile(tmp_path)

    assert (verdict["verdict"], verdict["attempt"]) == ("in-flight", ATTEMPT_CAP)
    assert REQUEST in verdict["evidence"]


def test_the_same_attempt_once_recorded_unverified_reads_attempts_exhausted(
    tmp_path: Path,
) -> None:
    record(task(tmp_path, attempts_line()), REQUEST)

    (verdict,) = reconcile(tmp_path)

    assert verdict["verdict"] == "attempts-exhausted"


def test_a_record_for_another_request_leaves_the_attempt_in_flight(tmp_path: Path) -> None:
    record(task(tmp_path, attempts_line()), OTHER_REQUEST)

    assert reconcile(tmp_path)[0]["verdict"] == "in-flight"


def test_assuming_a_request_recorded_gives_the_verdict_after_it_is(tmp_path: Path) -> None:
    task_dir = task(tmp_path, attempts_line())
    assumed = reconcile(tmp_path, assume_recorded=frozenset({REQUEST}))

    record(task_dir, REQUEST)

    assert assumed == reconcile(tmp_path)
    assert assumed[0]["verdict"] == "attempts-exhausted"


def test_a_wip_without_a_request_token_reads_as_it_always_did(tmp_path: Path) -> None:
    task_dir = task(tmp_path, attempts_line(request=None))
    before = reconcile(tmp_path)

    record(task_dir, REQUEST)

    assert before[0]["verdict"] == "attempts-exhausted"
    assert (
        reconcile(tmp_path)
        == before
        == reconcile(tmp_path, assume_recorded=frozenset({OTHER_REQUEST}))
    )


def test_the_driver_s_own_result_line_reads_as_a_run(tmp_path: Path) -> None:
    results = f"## {STEP}\n\nResult: pass=3 fail=0 skip=0 by=step-loop\n"
    task(tmp_path, f"- [x] {STEP}: build\n", PLAN_WITH_CHECK, results)

    (verdict,) = reconcile(tmp_path)

    assert (verdict["verdict"], verdict["outcome_source"]) == ("verified-complete", "run")


def test_an_outstanding_attempt_reads_unknown_while_the_ledger_has_an_unreadable_line(
    tmp_path: Path,
) -> None:
    break_the_ledger(task(tmp_path, attempts_line()))

    (verdict,) = reconcile(tmp_path)

    assert verdict["verdict"] == "unknown"
    assert verdict["evidence"].startswith(
        f"{STEP}: the iteration ledger record ending request {REQUEST} cannot be read (record 1: "
    )
    assert "underlying verdict pending:" in verdict["evidence"]


def test_a_recorded_attempt_is_unaffected_by_an_unreadable_line_elsewhere(tmp_path: Path) -> None:
    task_dir = task(tmp_path, attempts_line())
    record(task_dir, REQUEST)

    break_the_ledger(task_dir)

    assert reconcile(tmp_path)[0]["verdict"] == "attempts-exhausted"


def test_a_well_formed_ledger_reads_an_outstanding_attempt_as_no_ledger_does(
    tmp_path: Path,
) -> None:
    task_dir = task(tmp_path, attempts_line())
    without = reconcile(tmp_path)

    record(task_dir, OTHER_REQUEST)

    assert reconcile(tmp_path) == without
