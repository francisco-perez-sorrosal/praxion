"""Whether a stopped run may be continued: it is refused with every reason, never only the first,
and how well the run did never decides."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence.lineage import (
    CONTINUATION_OPTIONS,
    Finished,
    Interrupted,
    Legacy,
    ReadTip,
    RunEnding,
    SpendRefused,
    UnreadableTip,
    continuation_refusals,
    ending_to_json,
)
from praxion_evals.adherence.model import Errored
from praxion_evals.adherence.run_identity import MeasuredIdentity
from tests.lineage_support import (
    closed_ending,
    identity,
    infra_stop,
    read_tip,
)
from tests.test_adherence_results import declared, pair_of_sessions, run_results, session

# ---------------------------------------------------------------------------
# Whether a stopped run may be continued
# ---------------------------------------------------------------------------


def _refusals(
    tip: ReadTip, now: MeasuredIdentity | None = None, options: Any = ()
) -> tuple[str, ...]:
    return continuation_refusals(tip, now or identity(), options)


@pytest.mark.parametrize(
    "ending",
    [infra_stop("both-arms"), SpendRefused(("task-1",))],
    ids=["both-arms stop", "spend refusal"],
)
def test_a_run_that_stopped_continuably_and_still_measures_the_same_is_not_refused(
    ending: RunEnding,
) -> None:
    assert _refusals(read_tip(ending)) == ()


def test_a_results_file_that_cannot_be_read_is_refused_naming_it() -> None:
    unreadable = UnreadableTip(Path("out/20261020T000000Z-0badf1.json"), "it is not JSON")

    refused = continuation_refusals(unreadable, identity(), ())

    assert refused == (
        "20261020T000000Z-0badf1.json cannot be read as a results file: it is not JSON",
    )


@pytest.mark.parametrize(
    ("ending", "said"),
    [
        (Finished(), "finished its plan"),
        (infra_stop("one-arm"), "lean arm alone"),
        (Interrupted(), "interrupted"),
        (closed_ending(), "was closed on 2026-10-17T09:00:00Z: no credit left"),
        (Legacy(), "before runs recorded how they ended"),
    ],
    ids=["complete run", "one-arm stop", "interrupt or crash", "closed run", "recorded before"],
)
def test_a_run_that_did_not_stop_continuably_is_refused_with_the_reason_and_its_name(
    ending: RunEnding, said: str
) -> None:
    (refused,) = _refusals(read_tip(None if isinstance(ending, Legacy) else ending))

    assert refused.startswith("run run-a ")
    assert said in refused


def test_a_run_that_already_has_a_continuation_is_refused_naming_it() -> None:
    (refused,) = _refusals(read_tip(infra_stop(), continued_by="run-b"))

    assert "already has a continuation, run-b" in refused


@pytest.mark.parametrize("option", sorted(CONTINUATION_OPTIONS))
def test_an_option_that_only_bounds_spend_or_output_may_accompany_a_continuation(
    option: str,
) -> None:
    assert _refusals(read_tip(infra_stop()), options=[option]) == ()


@pytest.mark.parametrize("option", ["--margin-pp", "--seed", "--role"])
def test_an_option_that_could_change_what_is_measured_is_refused_naming_it(option: str) -> None:
    (refused,) = _refusals(read_tip(infra_stop()), options=["--output", option])

    assert refused.startswith(f"{option} would change what the run measures")


@pytest.mark.parametrize(
    ("now", "named"),
    [
        (identity(tree="tree-b"), "tree"),
        (identity(model="claude-opus-5-6"), "model"),
        (identity(seed=8), "seed"),
        (identity(tasks={"researcher": ("task-1",)}), "tasks.researcher"),
        (identity(declared=replace(declared(), margin_pp=12.0)), "declared.margin_pp"),
    ],
    ids=["tree", "model", "seed", "tasks", "a declared setting"],
)
def test_a_difference_in_what_is_measured_is_refused_naming_it(
    now: MeasuredIdentity, named: str
) -> None:
    (refused,) = _refusals(read_tip(infra_stop()), now)

    assert refused.startswith(f"changed since the stop: {named}")


def test_every_reason_is_named_not_only_the_first() -> None:
    refused = _refusals(read_tip(Interrupted(), continued_by="run-b"), identity(seed=9), ["--seed"])

    assert [line.split(" ")[0] for line in refused] == ["run", "run", "--seed", "changed"]


def test_how_well_the_run_did_never_decides_whether_it_is_continued() -> None:
    errored = Errored("result_error", "boom")
    outcomes = {
        "none": [],
        "all passed": [*pair_of_sessions("task-0")],
        "lean errored": [session("task-0", "full"), session("task-0", "lean", errored)],
    }
    ending = {"ending": ending_to_json(infra_stop())}

    refusals = {
        name: continuation_refusals(
            ReadTip(run_results(sessions, extra=ending), identity()), identity(), ()
        )
        for name, sessions in outcomes.items()
    }

    assert refusals == dict.fromkeys(outcomes, ())
