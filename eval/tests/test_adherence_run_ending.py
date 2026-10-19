"""How a run ended: the ending's wire form round-trips, only a both-arms stop or a spend refusal
is continuable, a file without an ending is legacy, the runner records the ending it had, and the
report says it. What a run was measured on is tested in `test_adherence_run_identity.py`."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence import report, results
from praxion_evals.adherence.lineage import (
    Closed,
    Finished,
    Interrupted,
    Legacy,
    RunEnding,
    SpendRefused,
    continuable,
    ending_from_json,
    ending_of,
    ending_to_json,
)
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.adherence_run_support import Script, run_small
from tests.lineage_support import (
    CREDIT_TAIL,
    closed_ending,
    infra_stop,
)
from tests.test_adherence_report import results_of

pytestmark = pytest.mark.usefixtures("full_first", "unswitched_checkout")


ROUND_TRIPPING: dict[str, RunEnding] = {
    "finished": Finished(),
    "infrastructure stop": infra_stop(),
    "one-arm infrastructure stop": infra_stop("one-arm"),
    "spend refusal": SpendRefused(("task-001", "task-002")),
    "interrupt": Interrupted(),
    "closed run": closed_ending(),
}


@pytest.mark.parametrize("ending", ROUND_TRIPPING.values(), ids=ROUND_TRIPPING.keys())
def test_every_ending_survives_its_wire_form(ending: RunEnding) -> None:
    assert ending_from_json(ending_to_json(ending)) == ending


def test_an_infrastructure_stop_is_written_with_the_pinned_field_names() -> None:
    assert ending_to_json(infra_stop()) == {
        "kind": "infra_stopped",
        "error_kind": "result_error",
        "masked_tail": CREDIT_TAIL,
        "role": "researcher",
        "arm": "lean",
        "sessions": [{"task_id": f"task-{n}", "arm": "lean", "attempt": 1} for n in range(3)],
        "scope": "both-arms",
    }


def test_a_closed_ending_keeps_the_stop_it_closed() -> None:
    wire = ending_to_json(closed_ending(SpendRefused(("task-001",))))

    assert wire["stopped"] == {"kind": "spend_refused", "tasks": ["task-001"]}


def test_a_spend_refusal_written_without_tasks_reads_as_naming_none() -> None:
    assert ending_from_json({"kind": "spend_refused"}) == SpendRefused()


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        (infra_stop("both-arms"), True),
        (SpendRefused(), True),
        (infra_stop("one-arm"), False),
        (Finished(), False),
        (Interrupted(), False),
        (closed_ending(), False),
        (Legacy(), False),
    ],
    ids=[
        "both-arms stop",
        "spend refusal",
        "one-arm stop",
        "finished",
        "interrupt",
        "closed",
        "legacy",
    ],
)
def test_only_a_both_arms_stop_or_a_spend_refusal_can_be_continued(
    ending: RunEnding, expected: bool
) -> None:
    assert continuable(ending) is expected


def test_a_file_with_no_ending_is_legacy_and_legacy_has_no_wire_form() -> None:
    legacy = results_of([])

    assert ending_of(legacy) == Legacy()
    with pytest.raises(ValueError, match="never written"):
        ending_to_json(Legacy())


def test_the_ending_is_read_from_the_run_record() -> None:
    loaded = results_of([])
    recorded = replace(loaded.run, extra={"ending": ending_to_json(infra_stop())})

    assert ending_of(replace(loaded, run=recorded)) == infra_stop()


@pytest.mark.parametrize(
    ("wire", "complaint"),
    [
        ({"kind": "exploded"}, "unknown run ending"),
        ({}, "lacks 'kind'"),
        ({**ending_to_json(infra_stop()), "arm": "middle"}, "unknown arm"),
        ({**ending_to_json(infra_stop()), "scope": "some-arms"}, "unknown scope"),
        ({"kind": "infra_stopped"}, "lacks 'error_kind'"),
        (
            {**ending_to_json(closed_ending()), "stopped": {"kind": "finished"}},
            "closes a stopped run",
        ),
    ],
    ids=[
        "unknown kind",
        "no kind",
        "unknown arm",
        "unknown scope",
        "missing field",
        "closed finish",
    ],
)
def test_a_malformed_ending_is_refused_with_what_was_wrong(
    wire: dict[str, Any], complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint):
        ending_from_json(wire)


def test_a_run_cannot_be_closed_without_a_reason() -> None:
    with pytest.raises(ValueError, match="needs a reason"):
        Closed("  ", "2026-10-17T09:00:00Z", {}, Interrupted())


# ---------------------------------------------------------------------------
# What the runner records
# ---------------------------------------------------------------------------


class Interrupts(Script):
    """Answers like the stand-in until its Nth launch, where the operator presses Ctrl-C."""

    def __init__(self, at_launch: int) -> None:
        super().__init__()
        self.at_launch = at_launch

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        run = super().__call__(spec, env)
        if len(self.specs) == self.at_launch:
            raise KeyboardInterrupt
        return run


def test_a_run_that_reaches_the_end_of_its_plan_records_that_it_finished(
    paid: Any, tmp_path: Path
) -> None:
    paid(Script())

    code, loaded = run_small(tmp_path)

    assert (code, ending_of(loaded)) == (0, Finished())


def test_a_launch_refused_by_the_spend_cap_is_recorded_as_a_continuable_spend_refusal(
    paid: Any, tmp_path: Path
) -> None:
    paid(Script(cost=None))

    code, loaded = run_small(tmp_path, "--max-total-usd", "2")

    ending = ending_of(loaded)
    assert (code, loaded.run.complete) == (1, False)
    assert ending == SpendRefused((loaded.sessions[0].setup.task_id,))
    assert continuable(ending)


def test_an_interrupt_still_writes_the_file_with_every_session_that_had_ended(
    paid: Any, tmp_path: Path
) -> None:
    paid(Interrupts(at_launch=4))  # the proofs, then the full arm's session, then Ctrl-C

    code, loaded = run_small(tmp_path)

    assert (code, loaded.run.complete) == (1, False)
    assert ending_of(loaded) == Interrupted()
    assert [(r.setup.arm, type(r.status).__name__) for r in loaded.sessions] == [
        ("full", "Measured")
    ]
    assert not continuable(ending_of(loaded))


def test_an_interrupt_keeps_the_spend_the_run_had_settled(paid: Any, tmp_path: Path) -> None:
    paid(Interrupts(at_launch=4))

    loaded = run_small(tmp_path)[1]

    assert loaded.run.extra["spend"]["spent_usd"] == pytest.approx(3 * 0.01)


# ---------------------------------------------------------------------------
# What the report says
# ---------------------------------------------------------------------------


def _rendered(ending: RunEnding | None) -> str:
    loaded = results_of([])
    extra = {} if ending is None else {"ending": ending_to_json(ending)}
    return report.render(replace(loaded, run=replace(loaded.run, extra=extra)))


@pytest.mark.parametrize("ending", [Finished(), None], ids=["finished", "recorded before endings"])
def test_a_run_that_finished_or_predates_endings_renders_without_an_ending_line(
    ending: RunEnding | None,
) -> None:
    assert _rendered(ending) == _rendered(None)
    assert "stopped" not in _rendered(ending).split("Declared at")[0]


def test_an_infrastructure_stop_is_reported_with_its_count_kind_evidence_and_continuability() -> (
    None
):
    assert (
        "The run stopped itself: 3 lean sessions in a row ended in result_error with the same"
        " evidence Credit balance is too low; continuable."
    ) in _rendered(infra_stop())


def test_a_one_arm_stop_is_reported_as_not_continuable() -> None:
    assert "; not continuable." in _rendered(infra_stop("one-arm"))


def test_an_interrupt_and_a_closed_run_are_reported_on_their_own_line() -> None:
    assert "The operator interrupted the run; not continuable." in _rendered(Interrupted())
    assert (
        "The run was closed on 2026-10-17T09:00:00Z without being continued: no credit left."
        in (_rendered(closed_ending()))
    )


def test_a_spend_refusal_is_reported_with_the_tasks_it_refused() -> None:
    assert "The spend cap refused launches (tasks task-001); continuable." in _rendered(
        SpendRefused(("task-001",))
    )


def test_the_results_loader_keeps_the_ending_it_was_given(tmp_path: Path) -> None:
    loaded = results_of([])
    recorded = replace(loaded.run, extra={"ending": ending_to_json(Interrupted())})
    path = tmp_path / "out.json"
    results.write_atomic(path, replace(loaded, run=recorded))

    assert ending_of(results.load(path)) == Interrupted()
