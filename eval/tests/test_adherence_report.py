"""The report states counts and bounds, never improvement, and recomputes every verdict."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

from praxion_evals.adherence import report, results
from praxion_evals.adherence.model import (
    CheckErrored,
    CheckOutcome,
    DeclaredSettings,
    Errored,
    Failed,
    Measured,
    NotApplicable,
    NotMeasured,
    Passed,
    RuleRef,
    SessionRecord,
    SessionSetup,
    SessionStatus,
    Withheld,
)
from praxion_evals.adherence.results import CatalogEntry, EarlierRun, RunInfo, RunResults

COMMIT = "0123456789abcdef0123456789abcdef01234567"
RULE = RuleRef("rules/swe/agent-behavioral-contract.md", "Agent Behavioral Contract")
CHECKS = (
    CatalogEntry("C1", "mechanical", RULE, True, None),
    CatalogEntry("C2", "mechanical", RuleRef("rules/swe/coding-style.md", "Naming"), True, None),
    CatalogEntry("C3", "judged", RULE, True, "a return that states no assumption"),
)
PASS = Passed()
FAIL = Failed("the check failed")
ALL_PASS = {"C1": PASS, "C2": PASS, "C3": PASS}
ALL_FAIL = {"C1": FAIL, "C2": FAIL, "C3": FAIL}
GAIN_WORDS = re.compile(
    r"\b(improv\w*|better|outperform\w*|superior|gains?|boost\w*|benefit\w*|advantage\w*)\b",
    re.IGNORECASE,
)
MET_INTERVAL = re.compile(
    r"\binterval\w*\s+(?:was\s+|is\s+|were\s+)?(?:met|satisfied|achieved|cleared)\b", re.IGNORECASE
)


def measured(outcomes: Mapping[str, CheckOutcome], tokens: int | None = 1000) -> Measured:
    return Measured(dict(outcomes), tokens)


def declared(required_pairs: int = 1) -> DeclaredSettings:
    return DeclaredSettings(
        margin_pp=10.0,
        method="tango-score",
        confidence=0.95,
        sidedness="one-sided",
        required_pairs=required_pairs,
        pair_slack=0,
        retry_policy="one retry per session, for infrastructure errors only",
        allowance_source=None,
        allowances={},
    )


def sessions_of(
    role: str, pairs: Iterable[tuple[SessionStatus, SessionStatus]]
) -> list[SessionRecord]:
    records = []
    for index, statuses in enumerate(pairs):
        for arm, status in zip(("full", "lean"), statuses, strict=True):
            setup = SessionSetup(arm, COMMIT, role, f"task-{index:03d}", "template", 7)  # type: ignore[arg-type]
            records.append(SessionRecord(setup, status, 0.01, 1000, "2026-10-12T09:00:00Z"))
    return records


def results_of(
    sessions: list[SessionRecord],
    *,
    required_pairs: int = 1,
    earlier_runs: tuple[EarlierRun, ...] = (),
    observed_error: float | None = None,
) -> RunResults:
    return RunResults(
        run=RunInfo(
            id="run-a",
            model="claude-opus-5-5",
            claude_code_version="9.9.9",
            complete=True,
            refused_launches=(),
            earlier_runs={"researcher": earlier_runs},
            extra={},
        ),
        settings=declared(required_pairs),
        declared_at="2026-10-12T08:59:00Z",
        catalog={"researcher": CHECKS},
        arms={"researcher": {"full": {"built": True}, "lean": {"built": True}}},
        sessions=tuple(sessions),
        golden_bad_case_verdicts=None
        if observed_error is None
        else {"observed_error": observed_error},
    )


def render(pairs, **kwargs) -> str:
    return report.render(results_of(sessions_of("researcher", pairs), **kwargs))


def same_both_arms(count: int, outcomes: Mapping[str, CheckOutcome] = ALL_PASS):
    return [(measured(outcomes), measured(outcomes))] * count


# ---------------------------------------------------------------------------
# Wording: at most non-regression, never a gain, never a met interval
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lean_outcomes",
    [ALL_PASS, ALL_FAIL],
    ids=["lean passes as often", "lean fails everywhere"],
)
def test_no_gain_word_and_no_met_interval_appears_whatever_the_figures(
    lean_outcomes: Mapping[str, CheckOutcome],
):
    pairs = [(measured(ALL_FAIL), measured(lean_outcomes))] * 6 + same_both_arms(14)

    text = render(pairs, required_pairs=20, observed_error=0.1)

    assert GAIN_WORDS.findall(text) == []
    assert MET_INTERVAL.findall(text) == []


def test_the_report_states_that_judge_error_attenuates_and_that_the_interval_did_not_decide():
    text = render(same_both_arms(3))

    assert "attenuates differences" in text
    assert "interval did not decide" in text


# ---------------------------------------------------------------------------
# Counts per role, arm and check
# ---------------------------------------------------------------------------


def test_each_checks_pass_counts_are_given_per_arm_over_the_complete_pairs():
    pairs = [(measured(ALL_PASS), measured({**ALL_PASS, "C1": FAIL}))] * 3 + same_both_arms(2)

    text = render(pairs)

    assert "full: passed 5 of 5 scored" in text
    assert "lean: passed 2 of 5 scored" in text  # C1 only; C2 and C3 pass all five
    assert text.count("lean: passed 5 of 5 scored") == 2


def test_withheld_not_applicable_and_errored_outcomes_are_counted_with_their_reasons():
    odd = {
        "C1": Withheld("no page to fetch"),
        "C2": NotApplicable("the role holds no WebFetch tool"),
        "C3": CheckErrored("the judge timed out"),
    }

    text = render(same_both_arms(2, odd))

    for reason in ("withheld: no page to fetch", "not applicable: the role holds no WebFetch"):
        assert reason in text
    assert "errored: the judge timed out" in text
    assert "passed 0 of 0 scored; withheld 2, not applicable 0, errored 0" in text


def test_errored_and_not_measured_sessions_are_counted_with_their_kind_and_reason():
    crash = Errored("timeout", "429 from the API")
    unspawned = NotMeasured("the main session never spawned the role")
    pairs = same_both_arms(1) + [(measured(ALL_PASS), crash), (unspawned, measured(ALL_PASS))]

    text = render(pairs)

    assert "full arm: 2 measured, 0 errored, 1 not measured" in text
    assert "lean arm: 2 measured, 1 errored, 0 not measured" in text
    assert "errored, timeout: 429 from the API" in text
    assert "not measured: the main session never spawned the role" in text


def test_the_worst_case_recount_counts_pairs_whose_lean_side_alone_errored():
    pairs = same_both_arms(2) + [(measured(ALL_PASS), Errored("timeout", "no answer"))]

    text = render(pairs)

    assert "2 complete pairs of 3 paired tasks" in text
    assert "lean failures: 1." in text
    assert "no regression (b 1, c 0, n 3, lean failures 1; noise allowance 0)" not in text
    assert "regression (b 1, c 0, n 3, lean failures 1; noise allowance 0)" in text


def test_first_request_token_medians_are_integers_with_thousands_separators():
    pairs = [
        (measured(ALL_PASS, tokens=42203), measured(ALL_PASS, tokens=30117)),
        (measured(ALL_PASS, tokens=51877), measured(ALL_PASS, tokens=38460)),
        (measured(ALL_PASS, tokens=None), measured(ALL_PASS, tokens=None)),
    ]

    text = render(pairs)

    assert "median 47,040 over 2 sessions" in text  # (42203 + 51877) / 2
    assert "median 34,288 over 2 sessions" in text  # (30117 + 38460) / 2 = 34288.5, rounded


def test_an_arm_with_no_token_reading_says_so():
    text = render([(measured(ALL_PASS, tokens=None), measured(ALL_PASS, tokens=None))])

    assert "median not recorded" in text


# ---------------------------------------------------------------------------
# Verdicts: recomputed, with intervals, underpowered roles and not-covered checks
# ---------------------------------------------------------------------------


def test_an_underpowered_role_is_labelled_so_and_gets_no_flip_verdict():
    text = render(same_both_arms(2), required_pairs=20)

    assert "underpowered, counts only and no flip verdict" in text
    assert "flip verdict clear" not in text
    assert "flip verdict not clear" not in text
    assert "verdict: none (the role is underpowered)" in text


def test_a_clear_flip_names_the_rule_it_rests_on_and_a_judged_check_reports_its_interval():
    text = render(same_both_arms(25), required_pairs=25)

    assert "flip verdict clear" in text
    assert "no regression on any scored mechanical check" in text
    match = re.search(
        r"non-inferior \(pass rates: lean 25 of 25, full 25 of 25.*?"
        r"lower (?P<lower>[+-][\d.]+) pp, upper \+100\.0 pp, width (?P<width>[\d.]+) pp, reported only",
        text,
    )
    assert match, "the judged check's interval and its width are missing"
    assert float(match["width"]) == pytest.approx(100 - float(match["lower"]), abs=0.1)


def test_a_regression_and_an_inferior_check_are_stated_with_their_counts():
    pairs = [(measured(ALL_PASS), measured(ALL_FAIL))] * 5 + same_both_arms(15)

    text = render(pairs, required_pairs=20)

    assert "flip verdict not clear" in text
    assert "regression (b 5, c 0, n 20, lean failures 5; noise allowance 0)" in text
    assert "inferior (pass rates: lean 15 of 20, full 20 of 20" in text


def test_a_check_no_pair_scored_is_listed_as_not_covered_with_its_reason():
    withheld = {**ALL_PASS, "C2": Withheld("no page to fetch")}

    text = render(same_both_arms(3, withheld), required_pairs=3)

    assert "not covered by the flip verdict (no page to fetch)" in text
    assert "flip verdict clear" in text


def test_the_stored_verdict_is_ignored_and_the_report_follows_the_sessions(tmp_path: Path):
    path = tmp_path / "run.json"
    pairs = [(measured(ALL_PASS), measured(ALL_FAIL))] * 3
    results.write_atomic(path, results_of(sessions_of("researcher", pairs)))
    document = json.loads(path.read_text())
    document["verdicts"]["researcher"] = {"underpowered": False, "flip": "clear"}
    path.write_text(json.dumps(document))

    text = report.render(results.load(path))

    assert "flip verdict not clear" in text
    assert "flip verdict clear" not in text


# ---------------------------------------------------------------------------
# Provenance: rules, earlier runs, the judge's error, the declared settings
# ---------------------------------------------------------------------------


def test_every_check_shows_the_rule_file_and_section_it_enforces():
    text = render(same_both_arms(1))

    assert "C1 (mechanical) enforces rules/swe/agent-behavioral-contract.md, section" in text
    assert "'Agent Behavioral Contract'" in text
    assert "C2 (mechanical) enforces rules/swe/coding-style.md, section 'Naming'" in text


def test_every_earlier_run_of_the_role_is_listed_with_its_verdict():
    earlier = (EarlierRun("run-0", "not clear"), EarlierRun("run-00", "underpowered"))

    text = render(same_both_arms(1), earlier_runs=earlier)

    assert "run-0: flip not clear; run-00: flip underpowered" in text
    assert "Earlier runs of this role on this checkout: none." in render(same_both_arms(1))


def test_the_judges_observed_golden_case_error_is_given_when_recorded():
    assert "observed on the golden cases: 0.15 (15%)" in render(
        same_both_arms(1), observed_error=0.15
    )
    assert "golden cases: not recorded in this run" in render(same_both_arms(1))


def test_the_declared_settings_are_stated_with_the_run_that_made_them():
    text = render(same_both_arms(1), required_pairs=20)

    assert "Declared at 2026-10-12T08:59:00Z, before the first session" in text
    assert "margin 10 pp" in text
    assert "target 20 complete pairs per role" in text
    assert "Model claude-opus-5-5; Claude Code 9.9.9; the run is complete." in text
    assert "none, so every allowance is zero" in text
