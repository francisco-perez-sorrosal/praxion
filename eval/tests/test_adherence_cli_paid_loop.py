"""The paid loop of the adherence console entry, over a scripted `claude`: arms proven before a
task runs, retried and exhausted sessions, an unreported cost charged in full, and the golden cases
judged once before any session.

The loop runs over a real copy of this repository with a scripted stand-in for the one function that
starts ``claude`` (``session_launch.run_session``); no process is ever started.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import (
    cli,
    results,
    session_loop,
)
from praxion_evals.adherence.checks_common import C3, GoldenVerdicts
from praxion_evals.adherence.model import (
    CheckErrored,
    Errored,
    Failed,
    Measured,
    Passed,
)
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import JudgeVerdict
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.adherence_run_support import (
    AGENT_ID,
    ROLE,
    Script,
    run_small,
    scripted_checkout,
    sessions_of,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")


# ---------------------------------------------------------------------------
# The golden-case record
# ---------------------------------------------------------------------------


def test_the_golden_record_counts_the_cases_the_judge_got_wrong() -> None:
    right = GoldenVerdicts(bad=Failed("missed"), good=Passed())
    wrong = GoldenVerdicts(bad=Passed(), good=Passed())

    record = session_loop.golden_record({"C3": right, "C9": wrong})

    assert record["observed_error"] == 0.25
    assert record["cases"]["C3"]["separates"] is True
    assert record["cases"]["C9"]["bad"] == {"outcome": "passed"}


def test_an_errored_golden_case_is_recorded_but_neither_right_nor_wrong() -> None:
    errored = GoldenVerdicts(bad=CheckErrored("judge down"), good=Passed())

    assert session_loop.golden_record({"C3": errored})["observed_error"] == 0.0
    assert (
        session_loop.golden_record({"C3": GoldenVerdicts(CheckErrored("x"), CheckErrored("y"))})[
            "observed_error"
        ]
        is None
    )


class _ScriptedJudge(JudgeClient):
    """Fails the golden bad case and passes everything else, as a faithful judge would."""

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        verdict = "FAIL" if artifact == C3.golden_bad_case else "PASS"  # type: ignore[union-attr]
        return JudgeVerdict(verdict=verdict, findings=(), score=0, raw={})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The paid loop, over a scripted `claude`
# ---------------------------------------------------------------------------


class Explodes(Script):
    """Launches the third session like the others, then raises as a decode failure would."""

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        run = super().__call__(spec, env)
        if len(self.specs) == 3:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return run


@pytest.mark.usefixtures("full_first")
def test_an_exception_after_the_session_was_launched_is_charged_the_full_session_budget(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Explodes())

    loaded = run_small(tmp_path, "--max-total-usd", "4")[1]

    assert sessions_of(loaded) == [("full", "Errored"), ("lean", "Measured")]
    exploded = loaded.sessions[0]
    assert getattr(exploded.status, "kind", None) == "evaluation_exception"
    assert exploded.cost_usd == 1.0  # the session budget: the process may have run and spent
    assert loaded.run.extra["spend"]["spent_usd"] == pytest.approx(1.0 + 3 * 0.01)


@pytest.mark.usefixtures("full_first")
def test_each_arm_is_proven_then_the_task_runs_in_both_arms_in_turn(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    code, loaded = run_small(tmp_path)

    assert code == 0
    assert loaded.run.complete
    assert [("lean" in s.plugin_dir.name) for s in script.specs] == [False, True, False, True]
    assert sessions_of(loaded) == [("full", "Measured"), ("lean", "Measured")]
    assert {arm: loaded.arms[ROLE][arm]["built"] for arm in ("full", "lean")} == {
        "full": True,
        "lean": True,
    }
    assert loaded.arms[ROLE]["lean"]["proof"]["cross_checked"] is True
    assert loaded.run.claude_code_version == "9.9.9-test"
    assert loaded.run.extra["retries"] == []


@pytest.mark.usefixtures("full_first")
def test_a_lean_session_whose_transcript_is_absent_names_the_path_it_looked_at(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    script.delivers_kernel = False
    paid(script)

    lean = run_small(tmp_path)[1].sessions[1].status

    assert getattr(lean, "kind", None) == "kernel_missing"
    assert f"/subagents/agent-{AGENT_ID}.jsonl was not found" in lean.detail


@pytest.mark.usefixtures("full_first")
def test_a_transient_infrastructure_error_is_retried_once_and_the_retry_replaces_it(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number == 4)  # the lean task session
    paid(script)

    code, loaded = run_small(tmp_path)

    assert code == 0
    assert sessions_of(loaded) == [("full", "Measured"), ("lean", "Errored"), ("lean", "Measured")]
    assert loaded.run.extra["retries"] == [
        {
            "role": ROLE,
            "arm": "lean",
            "task_id": loaded.sessions[0].setup.task_id,
            "after": "exit_nonzero",
        }
    ]
    assert isinstance(results.pairs_of(loaded, ROLE)[0].lean, Measured)


def test_an_error_that_keeps_failing_is_retried_once_only_and_leaves_the_run_incomplete(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number >= 2)  # every launch after the proof
    paid(script)

    code, loaded = run_small(tmp_path, "--arm", "lean")

    assert code == 1
    assert len(script.specs) == 3  # the proof, the lean session and its one retry
    assert sessions_of(loaded) == [("lean", "Errored"), ("lean", "Errored")]
    assert not loaded.run.complete


@pytest.mark.usefixtures("full_first")
def test_a_session_that_reports_no_cost_is_charged_its_budget_and_the_cap_refuses_the_rest(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(cost=None)
    paid(script)

    code, loaded = run_small(tmp_path, "--max-total-usd", "2")

    assert code == 1
    assert len(script.specs) == 2  # the two proofs fill the cap
    assert [
        (r.setup.arm, r.status.kind) for r in loaded.sessions if isinstance(r.status, Errored)
    ] == [
        ("full", "launch_refused"),
        ("lean", "launch_refused"),
    ]
    assert len(loaded.run.refused_launches) == 2
    assert loaded.run.extra["spend"] == {"cap_usd": 2.0, "spent_usd": 2.0}


def test_an_arm_whose_proof_fails_runs_no_task(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number == 1)  # the full arm's proof
    paid(script)

    code, loaded = run_small(tmp_path)

    assert code == 1
    assert loaded.arms[ROLE]["full"]["built"] is False
    assert loaded.arms[ROLE]["lean"]["built"] is True
    assert sessions_of(loaded) == [("lean", "Measured")]


def test_golden_cases_are_judged_once_and_recorded_before_any_session(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paid(Script())
    monkeypatch.setattr(session_loop, "select_judge_client", _ScriptedJudge)
    output = tmp_path / "golden.json"

    code = cli.main(
        [
            str(scripted_checkout()),
            "--role",
            ROLE,
            "--output",
            str(output),
            "--judge-golden",
            "--max-total-usd",
            "0.5",
            "--session-budget-usd",
            "1",
        ]
    )

    recorded = results.load(output).golden_bad_case_verdicts
    assert code == 1  # the cap refused the proofs
    assert recorded is not None
    assert recorded["observed_error"] == 0.0
    assert recorded["cases"]["C3"]["separates"] is True


def test_judging_that_is_unavailable_is_a_usage_error_before_anything_is_written(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paid(Script())

    def unavailable() -> JudgeClient:
        raise RuntimeError("no judge credentials")

    monkeypatch.setattr(session_loop, "select_judge_client", unavailable)

    code = cli.main(
        [str(scripted_checkout()), "--role", ROLE, "--output", str(tmp_path / "o.json")]
    )

    assert code == 2
    assert not (tmp_path / "o.json").exists()
