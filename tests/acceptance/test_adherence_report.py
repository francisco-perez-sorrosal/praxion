"""The report states counts and bounds, never improvement.

Per role and per arm it gives the check counts, the errored and not-measured
counts, the number of complete pairs and the worst-case recount, the paired
verdicts with each judged check's reported interval, every earlier run of the
role on the same checkout with its verdict, the judge's observed error on the
golden cases, and the spawned role's first-request tokens; it names the rule each
check enforces; an underpowered role is shown as such; and its wording claims at
most non-regression within the declared margin, states that judge error
attenuates differences, and never claims improvement or that an interval was met
-- even when the lean arm did better.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers.adherence_eval import (
    CheckSpec,
    FlipSettings,
    RoleMeasurement,
    check_catalog,
    lean_errored_pairs,
    render_report,
    repeated,
)

CHECKS = (CheckSpec("C1", "mechanical"), CheckSpec("C2", "mechanical"), CheckSpec("C3", "judged"))
ALL_PASS = {"C1": "passed", "C2": "passed", "C3": "passed"}
FULL_SLIPS = {"C1": "failed", "C2": "failed", "C3": "failed"}
CLAIMS_OF_GAIN = re.compile(r"\b(improv\w*|better|outperform\w*|superior|gains?)\b", re.IGNORECASE)
CLAIMS_OF_A_MET_INTERVAL = re.compile(
    r"\binterval\w*\s+(?:was\s+|is\s+|were\s+)?(?:met|satisfied|achieved|cleared)\b", re.IGNORECASE
)
EARLIER_RUN_ID = "adherence-2026-10-01-researcher-a"


def _measurements() -> dict[str, RoleMeasurement]:
    return {
        "researcher": RoleMeasurement(
            checks=CHECKS,
            pairs=repeated(14, ALL_PASS, ALL_PASS)
            + repeated(6, FULL_SLIPS, ALL_PASS)
            + lean_errored_pairs(1, ALL_PASS),
            first_request_tokens={"full": 42203, "lean": 30117},
            errored_sessions=3,
            not_measured_sessions=2,
            earlier_runs=[(EARLIER_RUN_ID, "not clear")],
        ),
        "verifier": RoleMeasurement(
            checks=CHECKS,
            pairs=repeated(2, ALL_PASS, ALL_PASS),
            first_request_tokens={"full": 51877, "lean": 38461},
        ),
    }


def _digits(text: str) -> str:
    return re.sub(r"(?<=\d)[,_  ](?=\d{3})", "", text)


def test_the_report_never_claims_improvement_even_when_the_lean_arm_passes_more():
    report = render_report(_measurements(), FlipSettings(required_pairs=20))

    claims = CLAIMS_OF_GAIN.findall(report) + CLAIMS_OF_A_MET_INTERVAL.findall(report)

    assert claims == [], f"the report claims a gain or a met interval: {claims}"


def test_the_report_gives_each_roles_arms_their_first_request_tokens_and_marks_the_underpowered_role():
    report = _digits(render_report(_measurements(), FlipSettings(required_pairs=20)))

    for role, figures in (("researcher", ("42203", "30117")), ("verifier", ("51877", "38461"))):
        assert role in report
        assert all(figure in report for figure in figures), (
            f"the {role}'s token figures are missing"
        )
    assert {"full", "lean"} <= set(re.findall(r"\b(full|lean)\b", report))
    assert re.search(r"underpowered", report, re.IGNORECASE), (
        "the two-pair role is not shown underpowered"
    )


def test_the_report_shows_the_recount_intervals_earlier_runs_and_judge_error_with_its_caveat():
    report = render_report(
        _measurements(), FlipSettings(required_pairs=20), judge_golden_error=0.15
    )

    assert re.search(r"worst[- ]case", report, re.IGNORECASE), "the worst-case recount is missing"
    assert re.search(r"\binterval", report, re.IGNORECASE), (
        "the judged checks' intervals are missing"
    )
    assert EARLIER_RUN_ID in report, (
        "the earlier run of the same role on the same checkout is missing"
    )
    assert re.search(r"\b(0\.15|15(\.0)?\s?%)", report), (
        "the judge's observed golden-case error is missing"
    )
    assert re.search(r"attenuat", report, re.IGNORECASE), (
        "the report does not say judge error attenuates differences"
    )


def test_the_report_names_the_rule_each_check_enforces():
    report = render_report(_measurements(), FlipSettings(required_pairs=20))
    rules = {
        c.name: c.rule_file for c in check_catalog("researcher") if c.name in {"C1", "C2", "C3"}
    }

    missing = {name: rule for name, rule in rules.items() if rule not in report}

    assert missing == {}, f"the report does not name these checks' rules: {missing}"
