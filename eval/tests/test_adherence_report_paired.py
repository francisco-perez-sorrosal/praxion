"""A paired run is reported in its own arms' names; the default axis's report keeps its text."""

from __future__ import annotations

import dataclasses
import re

from praxion_evals.adherence import report
from praxion_evals.adherence.axis import DEFAULT_AXIS, POSITIONS
from praxion_evals.adherence.model import Measured, SessionRecord, SessionSetup
from praxion_evals.adherence.results import CatalogEntry, RunResults
from praxion_evals.adherence.transcript import EndedOnItsOwn, StoppedAtCap
from tests.test_adherence_report import (
    CHECKS,
    COMMIT,
    ENDED_EARLY,
    FAIL,
    PASS,
    RAN_OUT,
    RULE,
    results_of,
)

PAIRED = "refactoring-delivery"
CAP = 6
FORCED_STOP = CatalogEntry("C5", "mechanical", RULE, False, None)
ROLES = ("researcher", "implementer")
NOT_SHOWN = "the delivered copy's skill was not seen arriving once, by its own way"


def _session(axis: str, arm: str, role: str, task: str, status: Measured) -> SessionRecord:
    setup = SessionSetup(arm, COMMIT, role, task, "template", 7, axis)  # type: ignore[arg-type]
    return SessionRecord(setup, status, 0.01, 1000, "2026-10-12T09:00:00Z")


def _measured(c1: object, ending: object) -> Measured:
    outcomes = {"C1": c1, "C2": PASS, "C3": PASS, **(RAN_OUT if ending else ENDED_EARLY)}
    return Measured(outcomes, 1000, role_ending=ending)  # type: ignore[arg-type]


def two_role_run(axis: str, unshown_reason: str = NOT_SHOWN) -> RunResults:
    """The researcher runs three tasks in both arms; the implementer's treatment arm was not
    built, so only its baseline arm has sessions."""
    baseline, treatment = POSITIONS[axis].baseline, POSITIONS[axis].treatment
    sessions = [
        _session(axis, arm, "researcher", f"task-{n}", _measured(c1, ending))
        for n in range(3)
        for arm, c1, ending in (
            (baseline, PASS, StoppedAtCap(CAP, CAP)),
            (treatment, FAIL if n else PASS, EndedOnItsOwn(CAP - 2)),
        )
    ]
    sessions += [
        _session(axis, baseline, "implementer", f"task-{n}", _measured(PASS, None))
        for n in range(2)
    ]
    run = results_of([], extra={} if axis == DEFAULT_AXIS else {"axis": axis})
    return dataclasses.replace(
        run,
        sessions=tuple(sessions),
        catalog=dict.fromkeys(ROLES, (*CHECKS, FORCED_STOP)),
        arms={
            "researcher": {baseline: {"built": True}, treatment: {"built": True}},
            "implementer": {
                baseline: {"built": True},
                treatment: {"built": False, "reason": unshown_reason},
            },
        },
    )


def line_of(text: str, start: str) -> str:
    return next(ln.strip() for ln in text.splitlines() if ln.strip().startswith(start))


def role_block(text: str, role: str) -> str:
    return text.split(f"Role {role}:")[1].split("\nRole ")[0]


def forced_run(axis: str, baseline: list[object], treatment: list[object]) -> RunResults:
    """One role, each arm's forced-stop sessions ended as listed (True: ran out of turns)."""
    positions = POSITIONS[axis]
    sessions = [
        _session(axis, arm, "researcher", f"{arm}-{n}", _measured(PASS, _ending(ran_out)))
        for arm, endings in ((positions.baseline, baseline), (positions.treatment, treatment))
        for n, ran_out in enumerate(endings)
    ]
    run = results_of([], extra={"axis": axis})
    return dataclasses.replace(
        run,
        sessions=tuple(sessions),
        catalog={"researcher": (FORCED_STOP,)},
        arms={
            "researcher": {
                arm: {"built": True} for arm in (positions.baseline, positions.treatment)
            }
        },
    )


def _ending(ran_out: object) -> StoppedAtCap | EndedOnItsOwn:
    return StoppedAtCap(CAP, CAP) if ran_out else EndedOnItsOwn(CAP - 2)


# ---------------------------------------------------------------------------
# The default axis's text is what it was before the report named its run's arms
# ---------------------------------------------------------------------------


def test_a_two_role_default_run_renders_the_text_it_rendered_before_arms_were_named():
    assert report.render(two_role_run(DEFAULT_AXIS)) == DEFAULT_TEXT


def test_the_default_axis_keeps_its_not_built_line_and_prints_no_reason_for_it():
    text = report.render(two_role_run(DEFAULT_AXIS))

    assert "lean arm (not built):" in text
    assert "not shown" not in text
    assert NOT_SHOWN not in text


# ---------------------------------------------------------------------------
# A paired run is reported in its own arms' names
# ---------------------------------------------------------------------------


def test_a_paired_runs_session_lines_name_its_two_arms_baseline_first():
    block = role_block(report.render(two_role_run(PAIRED)), "researcher")

    lines = [ln.strip() for ln in block.splitlines() if " arm: " in ln and "measured" in ln]
    assert [ln.split(":")[0] for ln in lines] == ["preloaded arm", "delivered arm"]
    assert all("3 measured, 0 errored, 0 not measured" in ln for ln in lines)


def test_a_paired_runs_forced_stop_lines_name_its_arms():
    text = report.render(two_role_run(PAIRED))

    assert line_of(text, "forced-stop sessions, preloaded") == (
        "forced-stop sessions, preloaded arm: 3 ran out of turns, 0 ended before their cap"
    )
    assert line_of(text, "forced-stop sessions, delivered") == (
        "forced-stop sessions, delivered arm: 0 ran out of turns, 3 ended before their cap"
    )


def test_the_paired_differential_is_the_treatment_share_minus_the_baseline_share():
    run = forced_run(PAIRED, baseline=[True, False], treatment=[True, True])  # 50% and 100%

    text = report.render(run)

    assert line_of(text, "differential run-out rate") == (
        "differential run-out rate (delivered minus preloaded): 50.0 pp"
    )


def test_the_paired_differential_is_not_defined_when_an_arm_has_no_known_ending():
    text = report.render(forced_run(PAIRED, baseline=[True], treatment=[]))

    assert line_of(text, "differential run-out rate").startswith(
        "differential run-out rate (delivered minus preloaded): not defined"
    )


def test_each_check_of_a_paired_run_gives_its_pass_counts_under_the_arms_names():
    text = report.render(two_role_run(PAIRED))

    c1 = text.split("C1 (mechanical)")[1].split("C2 (mechanical)")[0]
    assert "preloaded: passed 3 of 3 scored" in c1
    assert "delivered: passed 1 of 3 scored" in c1


def test_a_paired_report_names_no_default_arm_in_its_per_arm_lines():
    text = report.render(two_role_run(PAIRED))

    per_arm = ("full arm", "lean arm", "full:", "lean:", "forced-stop sessions, full")
    named = [ln for ln in text.splitlines() if ln.strip().startswith(per_arm)]
    assert named == []
    assert "(lean minus full)" not in text


# ---------------------------------------------------------------------------
# An arm that was not shown says why
# ---------------------------------------------------------------------------


def test_an_arm_a_paired_run_could_not_show_is_named_with_the_reason_it_recorded():
    text = report.render(two_role_run(PAIRED))

    assert f"delivered arm not shown: {NOT_SHOWN}" in role_block(text, "implementer")


def test_an_arm_that_was_shown_and_has_no_session_yet_is_not_called_unshown():
    run = forced_run(PAIRED, baseline=[True], treatment=[])

    assert "not shown" not in report.render(run)


def test_a_recorded_reason_is_flattened_onto_one_line():
    run = two_role_run(PAIRED, unshown_reason="the proof\nspawn  never\nheld the skill")

    assert "delivered arm not shown: the proof spawn never held the skill" in report.render(run)


# Recorded from the module before the report named its run's arms: a two-role default run, one
# role with its treatment arm not built.
DEFAULT_TEXT = """Adherence report for run run-a
Model claude-opus-5-5; Claude Code 9.9.9; the run is complete.
Declared at 2026-10-12T08:59:00Z, before the first session:
  non-inferiority margin 10 pp for judged checks; method tango-score, one-sided, confidence 95%;
  target 1 complete pairs per role, slack 0; retry policy: one retry per session, for infrastructure errors only;
  mechanical noise allowances: none, so every allowance is zero.
Judge error on the golden cases: not recorded in this run.

How to read this report
- Each verdict claims at most non-regression on a mechanical check, and non-inferiority within the declared margin on a judged check, over the pairs shown. It says nothing about either arm doing more than the other.
- Judge error attenuates differences between the arms toward zero, so a judged check can look equal when the arms differ.
- A judged check's interval is reported beside its verdict. The interval did not decide the verdict, which the margin on the pass rates alone decides.
- b counts pairs where only the full arm passed; c counts pairs where only the lean arm passed; n is the usable pairs after the worst-case recount.
- Withheld and not-applicable checks enter no rate and no verdict, and are not covered by a flip verdict; each is listed with its reason.
- A token saving appears only as a startup-probe reading: the median of first-request tokens beside each arm. No verdict here claims a saving; a verdict bounds non-regression within the declared margin and nothing more.
- Kernel delivery evidence lists, per role, the marker records of the lean sessions the verdict relies on. An adherence sandbox writes no observation row, so the marker in the spawned role's transcript is the record a flip can cite.

Role researcher: flip verdict not clear, over 3 complete pairs (a scored check shows a regression or is inferior, or no check was scored).
  3 complete pairs of 3 paired tasks; worst-case recount, pairs with a lean-side error and a measured full side counted as lean failures: 0.
  full arm: 3 measured, 0 errored, 0 not measured; first-request tokens, median 1,000 over 3 sessions.
  lean arm: 3 measured, 0 errored, 0 not measured; first-request tokens, median 1,000 over 3 sessions.
  forced-stop sessions, full arm: 3 ran out of turns, 0 ended before their cap
  forced-stop sessions, lean arm: 0 ran out of turns, 3 ended before their cap
  differential run-out rate (lean minus full): -100.0 pp
  Checks:
    C1 (mechanical) enforces rules/swe/agent-behavioral-contract.md, section 'Agent Behavioral Contract'
      full: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      lean: passed 1 of 3 scored; withheld 0, not applicable 0, errored 0
      verdict: regression (b 2, c 0, n 3, lean failures 2; noise allowance 0)
    C2 (mechanical) enforces rules/swe/coding-style.md, section 'Naming'
      full: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      lean: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      verdict: no regression (b 0, c 0, n 3, lean failures 0; noise allowance 0)
    C3 (judged) enforces rules/swe/agent-behavioral-contract.md, section 'Agent Behavioral Contract'
      full: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      lean: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      verdict: non-inferior (pass rates: lean 3 of 3, full 3 of 3; b 0, c 0, n 3, lean failures 0); one-sided interval on lean minus full: lower -47.4 pp, upper +100.0 pp, width 147.4 pp, reported only
    C5 (mechanical) enforces rules/swe/agent-behavioral-contract.md, section 'Agent Behavioral Contract'
      full: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      lean: passed 3 of 3 scored; withheld 0, not applicable 0, errored 0
      verdict: no regression (b 0, c 0, n 3, lean failures 0; noise allowance 0)
  Earlier runs of this role on this checkout: none.

Role implementer: underpowered, counts only and no flip verdict (0 complete pairs, fewer than the 1 declared).
  0 complete pairs of 0 paired tasks; worst-case recount, pairs with a lean-side error and a measured full side counted as lean failures: 0.
  full arm: 2 measured, 0 errored, 0 not measured; first-request tokens, median 1,000 over 2 sessions.
  lean arm (not built): 0 measured, 0 errored, 0 not measured; first-request tokens, median not recorded.
  Checks:
    C1 (mechanical) enforces rules/swe/agent-behavioral-contract.md, section 'Agent Behavioral Contract'
      full: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      lean: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      verdict: none (the role is underpowered)
    C2 (mechanical) enforces rules/swe/coding-style.md, section 'Naming'
      full: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      lean: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      verdict: none (the role is underpowered)
    C3 (judged) enforces rules/swe/agent-behavioral-contract.md, section 'Agent Behavioral Contract'
      full: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      lean: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      verdict: none (the role is underpowered)
    C5 (mechanical) enforces rules/swe/agent-behavioral-contract.md, section 'Agent Behavioral Contract'
      full: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      lean: passed 0 of 0 scored; withheld 0, not applicable 0, errored 0
      verdict: none (the role is underpowered)
  Earlier runs of this role on this checkout: none.
"""


# ---------------------------------------------------------------------------
# The legend and the verdict sentences name the run's arms
# ---------------------------------------------------------------------------

DEFAULT_ARM_WORDS = re.compile(r"\b(?:lean|full)\b")


def with_kernel_rows(run: RunResults) -> RunResults:
    """The run with its treatment-arm sessions holding delivery markers, as a default run's lean
    sessions do."""
    row = {"session_id": "sess-7", "kernel_version": "0a1b2c3d", "slot": 1}
    treatment = POSITIONS[run.run.extra.get("axis", DEFAULT_AXIS)].treatment
    sessions = tuple(
        dataclasses.replace(r, status=dataclasses.replace(r.status, kernel_rows=(row,)))
        if r.setup.arm == treatment
        else r
        for r in run.sessions
    )
    return dataclasses.replace(run, sessions=sessions)


def test_a_paired_runs_legend_says_which_arm_each_discordant_count_belongs_to():
    text = report.render(two_role_run(PAIRED))

    assert (
        "- b counts pairs where only the preloaded arm passed; c counts pairs where only the"
        " delivered arm passed; n is the usable pairs after the worst-case recount."
    ) in text


def test_a_paired_runs_recount_sentence_names_its_arms():
    block = role_block(report.render(two_role_run(PAIRED)), "researcher")

    assert (
        "worst-case recount, pairs with a delivered-side error and a measured preloaded side"
        " counted as delivered failures: 0."
    ) in block


def test_a_paired_runs_mechanical_verdict_tallies_the_treatment_arms_failures():
    block = role_block(report.render(two_role_run(PAIRED)), "researcher")

    assert "regression (b 2, c 0, n 3, delivered failures 2; noise allowance 0)" in block


def test_a_paired_runs_judged_verdict_names_its_arms_in_pass_rates_and_interval():
    text = report.render(two_role_run(PAIRED))

    c3 = text.split("C3 (judged)")[1].split("C5 (mechanical)")[0]
    assert (
        "pass rates: delivered 3 of 3, preloaded 3 of 3; b 0, c 0, n 3, delivered failures 0" in c3
    )
    assert "one-sided interval on delivered minus preloaded: lower" in c3


def test_a_paired_report_uses_the_default_arms_names_nowhere():
    text = report.render(two_role_run(PAIRED))

    assert DEFAULT_ARM_WORDS.findall(text) == []


def test_a_paired_report_prints_no_kernel_delivery_section_or_note():
    text = report.render(with_kernel_rows(two_role_run(PAIRED)))

    assert "Kernel delivery evidence" not in text
    assert "kernel delivery" not in text.lower()


def test_a_default_run_with_delivery_markers_still_prints_its_kernel_delivery_section():
    text = report.render(with_kernel_rows(two_role_run(DEFAULT_AXIS)))

    assert "Kernel delivery evidence (lean sessions the verdict relies on):" in text


def test_the_default_reading_notes_are_the_notes_the_report_printed_before_arms_were_named():
    assert "\n".join(report.READING_NOTES) in DEFAULT_TEXT
    assert report.READING_NOTES == report.reading_notes(POSITIONS[DEFAULT_AXIS])
