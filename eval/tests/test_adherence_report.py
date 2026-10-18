"""The report states counts and bounds, never improvement, and recomputes every verdict."""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from praxion_evals.adherence import model, report, results, session_launch
from praxion_evals.adherence.infra_stop import EvidenceTail, Launched, StopReason
from praxion_evals.adherence.lineage import LAUNCH_REFUSED, Finished, InfraStopped, ending_to_json
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
from praxion_evals.adherence.transcript import EndedOnItsOwn, RoleEnding, StoppedAtCap, Unknown
from praxion_evals.live.session import SessionRun
from praxion_evals.live.spend import SpendLedger

COMMIT = "0123456789abcdef0123456789abcdef01234567"
OWN = "own-discordance-exact"
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


def declared(required_pairs: int = 1, allowance_method: str | None = None) -> DeclaredSettings:
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
        allowance_method=allowance_method,  # type: ignore[arg-type]
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
    allowance_method: str | None = None,
    extra: Mapping[str, object] | None = None,
) -> RunResults:
    return RunResults(
        run=RunInfo(
            id="run-a",
            model="claude-opus-5-5",
            claude_code_version="9.9.9",
            complete=True,
            refused_launches=(),
            earlier_runs={"researcher": earlier_runs},
            extra=dict(extra or {}),
        ),
        settings=declared(required_pairs, allowance_method),
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


C1_DOWN = {**ALL_PASS, "C1": FAIL}


def own_discordance_run(discordant: int, net: int) -> list[tuple[Measured, Measured]]:
    """Twenty-four pairs of which ``discordant`` differ on C1, ``net`` more against the lean arm."""
    lean_failed = (discordant + net) // 2
    return (
        [(measured(ALL_PASS), measured(C1_DOWN))] * lean_failed
        + [(measured(C1_DOWN), measured(ALL_PASS))] * (discordant - lean_failed)
        + same_both_arms(24 - discordant)
    )


def c1_block(text: str) -> list[str]:
    """The header line of C1's block and every deeper line after it."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith("C1 ("))
    indent = len(lines[start]) - len(lines[start].lstrip())
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if len(line) - len(line.lstrip()) <= indent:
            break
        block.append(line)
    return block


def test_a_mechanical_check_states_its_discordance_and_allowance_beside_the_margin():
    text = render(own_discordance_run(2, 2), required_pairs=24, allowance_method=OWN)

    block = c1_block(text)
    assert "allowance: 2 pairs (8.3 pp) at 2 discordant pairs; declared margin 10 pp" in block[-2]
    assert block[-1].strip().startswith("verdict: no regression (b 2, c 0, n 24")


def test_a_check_whose_allowance_exceeds_the_margin_ends_its_block_with_the_not_covered_verdict():
    text = render(own_discordance_run(15, 7), required_pairs=24, allowance_method=OWN)

    block = c1_block(text)
    assert "allowance: 7 pairs (29.2 pp) at 15 discordant pairs; declared margin 10 pp" in block[-2]
    assert block[-1].strip() == (
        "verdict: not covered by the flip verdict"
        " (the allowance exceeds the margin times the usable pairs)"
    )


def test_a_regression_under_a_wide_allowance_is_reported_as_a_regression_beside_its_allowance():
    text = render(own_discordance_run(15, 9), required_pairs=24, allowance_method=OWN)

    block = c1_block(text)
    assert "allowance: 7 pairs (29.2 pp) at 15 discordant pairs" in block[-2]
    assert block[-1].strip().startswith("verdict: regression (b 12, c 3, n 24")
    assert "flip verdict not clear" in text


def test_a_results_file_without_the_allowance_method_renders_no_allowance_line():
    text = render(own_discordance_run(15, 7), required_pairs=24)

    assert "allowance:" not in text.replace("noise allowance", "")
    assert c1_block(text)[-1].strip().startswith("verdict: regression (b 11, c 4, n 24")


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


def listing(**by_kind) -> dict[str, object]:
    return {"earlier": {"researcher": {"draws": [], "apart": {}, "calibration": [], **by_kind}}}


def test_a_listed_draw_is_shown_with_its_verdict_and_an_empty_listing_says_none():
    draws = [
        {"run_ids": ["run-0"], "flip": "not clear", "interim": False},
        {"run_ids": ["run-1"], "flip": "clear", "interim": False},
    ]

    text = render(same_both_arms(1), extra=listing(draws=draws))

    assert (
        "Earlier runs of this role on the same definition and kernel:"
        " run-0: flip not clear; run-1: flip clear."
    ) in text
    assert "same definition and kernel: none." in render(same_both_arms(1), extra=listing())


def test_a_run_of_another_identity_is_shown_apart_with_how_it_differs():
    apart = {"run-2": "roles.researcher.definition: 1a2b -> 3c4d"}

    text = render(same_both_arms(1), extra=listing(apart=apart))

    assert "set apart, with how they differ:" in text
    assert "run-2: roles.researcher.definition: 1a2b -> 3c4d" in text


def test_a_calibration_run_is_shown_apart_and_never_among_the_draws():
    text = render(same_both_arms(1), extra=listing(calibration=["run-3", "run-4"]))

    assert "Calibration runs of this role, never a draw: run-3, run-4." in text
    assert "same definition and kernel: none." in text


def test_the_json_files_that_were_skipped_are_named_in_the_run_section():
    text = render(same_both_arms(1), extra={**listing(), "skipped_files": ["notes.json"]})

    assert "Skipped, not adherence results files, beside this run's: notes.json." in text
    assert "Skipped" not in render(same_both_arms(1), extra=listing())


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


# ---------------------------------------------------------------------------
# Kernel delivery evidence and the saving wording
# ---------------------------------------------------------------------------

DELIVERY_ROWS = (
    {"session_id": "sess-7", "kernel_version": "0a1b2c3d", "slot": 1},
    {"session_id": "sess-7", "kernel_version": "0a1b2c3d", "slot": 2},
)


def lean_delivered(rows: Iterable[Mapping[str, object]] = DELIVERY_ROWS) -> Measured:
    return Measured(dict(ALL_PASS), 1000, kernel_rows=tuple(rows))


def test_the_report_lists_the_delivery_markers_of_the_lean_sessions_its_verdict_relies_on():
    stray = lean_delivered([{"session_id": "sess-stray", "kernel_version": "ffffffff", "slot": 1}])
    unpaired = (Errored("launch_refused", "the full arm was refused"), stray)

    text = render([(measured(ALL_PASS), lean_delivered()), unpaired])

    assert "Kernel delivery evidence (" in text
    assert "task-000: session sess-7, kernel 0a1b2c3d, slot 1" in text
    assert "task-000: session sess-7, kernel 0a1b2c3d, slot 2" in text
    assert "sess-stray" not in text


def test_the_kernel_evidence_never_reads_as_a_gain():
    text = render([(measured(ALL_PASS), lean_delivered())])

    assert GAIN_WORDS.findall(text) == []
    assert MET_INTERVAL.findall(text) == []


def test_a_role_whose_lean_sessions_show_no_markers_lists_no_kernel_evidence():
    assert "Kernel delivery evidence (" not in render(same_both_arms(2))


def test_a_token_saving_is_stated_only_as_a_startup_probe_reading_within_the_margin():
    text = render([(measured(ALL_PASS), lean_delivered())])

    assert "startup-probe reading" in text
    assert "No verdict here claims a saving" in text
    assert "within the declared margin" in text


# ---------------------------------------------------------------------------
# An errored session keeps, redacts and shows the end of its output
# ---------------------------------------------------------------------------

TOKEN = "subscription-token-0123456789"
TAIL_BOUND = 40


def result_stream(text: str) -> str:
    event = {"type": "result", "subtype": "error_during_execution", "is_error": True}
    return json.dumps({**event, "result": text, "total_cost_usd": 0.1})


def attempt_ending(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ended: SessionRun,
    error: Errored,
    *,
    cap_usd: float = 10.0,
) -> Errored:
    """The Errored one launch yields when the session ended as `ended` and grading says `error`."""
    monkeypatch.setattr(session_launch, "_prepare", lambda *args: (None, "commit"))
    monkeypatch.setattr(session_launch, "run_session", lambda spec, env: ended)
    monkeypatch.setattr(session_launch, "_evidence", lambda *args: None)
    launch = session_launch.Launch(
        run_root=tmp_path,
        checkout_commit=COMMIT,
        page_url="",
        judge=None,
        seed=7,
        model="m",
        effort="low",
        session_budget_usd=1.0,
        keep_sandbox=False,
        env_for=lambda root: {"CLAUDE_CODE_OAUTH_TOKEN": TOKEN},
        tail_chars=TAIL_BOUND,
    )
    task = SimpleNamespace(role="researcher")
    _, done = session_launch.attempt(
        launch,
        SpendLedger(cap_usd=cap_usd),
        task,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        lambda root: None,
        None,
        lambda evidence: error,
    )
    assert isinstance(done.result, Errored)
    return done.result


@pytest.mark.parametrize("kind", ["timeout", "exit_nonzero", "result_error", "kernel_missing"])
def test_each_kind_of_errored_session_keeps_the_end_of_both_streams(
    kind, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    ended = SessionRun(result_stream("r" * 100 + "result end"), "e" * 100 + "stderr end", 1)

    errored = attempt_ending(monkeypatch, tmp_path, ended, Errored(kind, "why"))

    assert errored.tails == EvidenceTail(
        ("e" * 100 + "stderr end")[-TAIL_BOUND:], ("r" * 100 + "result end")[-TAIL_BOUND:]
    )


def test_a_stream_the_session_never_wrote_is_recorded_as_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    errored = attempt_ending(
        monkeypatch, tmp_path, SessionRun("", "", 1), Errored("no_result_event", "none")
    )

    assert errored.tails == EvidenceTail("", "")


def test_a_launch_that_started_no_session_still_carries_empty_tails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    errored = attempt_ending(
        monkeypatch, tmp_path, SessionRun("", "", 0), Errored("timeout", "unused"), cap_usd=0.5
    )

    assert (errored.kind, errored.tails) == ("launch_refused", EvidenceTail("", ""))


def test_the_session_credential_never_reaches_a_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    leak = f"auth failed for {TOKEN}"
    ended = SessionRun(result_stream(leak), leak, 1)

    errored = attempt_ending(monkeypatch, tmp_path, ended, Errored("result_error", "why"))

    assert errored.tails == EvidenceTail("auth failed for [REDACTED]", "auth failed for [REDACTED]")


def test_a_tail_written_to_the_results_file_loads_back_and_an_old_record_has_none():
    kept = Errored("timeout", "no answer", None, EvidenceTail("stderr end", ""))

    wire = model.status_to_json(kept)

    assert wire["tails"] == {"error": "stderr end", "result": ""}
    assert model.status_from_json(wire) == kept
    assert "tails" not in model.status_to_json(Errored("timeout", "no answer"))
    old = {"kind": "errored", "error_kind": "timeout", "detail": "d"}
    assert model.status_from_json(old) == Errored("timeout", "d")


def test_the_report_shows_each_errored_sessions_tails_and_none_for_an_old_record():
    kept = Errored("timeout", "no answer", None, EvidenceTail("boom\n  at line 3", ""))
    old = Errored("timeout", "no answer")

    text = render([(measured(ALL_PASS), kept), (measured(ALL_PASS), old)])

    assert "lean task-000 (timeout):" in text
    assert "error tail: boom at line 3" in text
    assert "result tail: (empty)" in text
    assert text.count("error tail:") == 1


# ---------------------------------------------------------------------------
# Forced-stop sessions: how they ended, and the coverage floor of the forced-stop check
# ---------------------------------------------------------------------------

CAP = 6
C5_ENTRY = CatalogEntry("C5", "mechanical", RULE, False, None)
RAN_OUT = {"C5": PASS}
ENDED_EARLY = {"C5": NotApplicable("the role ended before its cap")}
NOT_FORCED = {"C5": NotApplicable("the task did not stop the role early")}


def forced(outcomes: Mapping[str, CheckOutcome], ending: RoleEnding | None) -> Measured:
    return Measured(dict(outcomes), 1000, role_ending=ending)


STOPPED = forced(RAN_OUT, StoppedAtCap(CAP, CAP))
ENDED = forced(ENDED_EARLY, EndedOnItsOwn(CAP - 3))
UNTOLD = forced(ENDED_EARLY, Unknown("the transcript could not be read"))
CLEAN = forced(NOT_FORCED, None)


def lone(arm: str, index: int, status: Measured) -> SessionRecord:
    """A session whose task ran in no other arm: it completes no pair."""
    setup = SessionSetup(arm, COMMIT, "researcher", f"lone-{arm}-{index:03d}", "template", 7)  # type: ignore[arg-type]
    return SessionRecord(setup, status, 0.01, 1000, "2026-10-12T09:00:00Z")


def forced_stop_report(both_ran_out: int, lone_sessions: Iterable[SessionRecord] = ()) -> str:
    pairs = [(STOPPED, STOPPED)] * both_ran_out + [(CLEAN, CLEAN)] * (24 - both_ran_out)
    sessions = sessions_of("researcher", pairs) + list(lone_sessions)
    run = results_of(sessions, required_pairs=24, allowance_method=OWN)
    return report.render(dataclasses.replace(run, catalog={"researcher": (C5_ENTRY,)}))


def line_of(text: str, start: str) -> str:
    return next(ln.strip() for ln in text.splitlines() if ln.strip().startswith(start))


def test_the_report_counts_forced_stop_sessions_by_how_they_ended_per_arm():
    lone_sessions = [lone("full", 0, ENDED)] + [lone("lean", i, ENDED) for i in range(3)]

    text = forced_stop_report(5, [*lone_sessions, lone("lean", 9, UNTOLD)])

    assert line_of(text, "forced-stop sessions, full") == (
        "forced-stop sessions, full arm: 5 ran out of turns, 1 ended before their cap"
    )
    assert line_of(text, "forced-stop sessions, lean") == (
        "forced-stop sessions, lean arm: 5 ran out of turns, 3 ended before their cap"
    )


def test_the_differential_run_out_rate_is_lean_minus_full_in_points():
    lone_sessions = [lone("full", 0, ENDED)] + [lone("lean", i, ENDED) for i in range(3)]

    text = forced_stop_report(5, lone_sessions)  # lean 5 of 8 ran out, full 5 of 6

    assert line_of(text, "differential run-out rate") == (
        "differential run-out rate (lean minus full): -20.8 pp"
    )


def test_the_differential_run_out_rate_is_not_defined_when_an_arm_has_no_known_ending():
    text = forced_stop_report(0, [lone("full", 0, STOPPED)])

    assert "(lean minus full): not defined" in line_of(text, "differential run-out rate")


def test_a_run_recorded_before_endings_were_kept_states_no_run_out_lines():
    text = render(same_both_arms(3))

    assert "forced-stop sessions" not in text
    assert "run-out rate" not in text


def test_the_run_out_counts_never_move_the_flip_verdict():
    plain = forced_stop_report(5)
    skewed = forced_stop_report(5, [lone("lean", i, ENDED) for i in range(4)])

    assert line_of(plain, "Role researcher:") == line_of(skewed, "Role researcher:")


@pytest.mark.parametrize(("both_ran_out", "covered"), [(4, False), (5, True)])
def test_the_report_lists_the_forced_stop_check_as_not_covered_under_five_pairs(
    both_ran_out, covered
):
    text = forced_stop_report(both_ran_out)

    verdict_line = line_of(text, "verdict:")
    assert ("not covered by the flip verdict" not in verdict_line) is covered, verdict_line
    assert (f"{both_ran_out} pairs ran out of turns on both sides" in verdict_line) is not covered


# ---------------------------------------------------------------------------
# A continued run reads as one run, naming its parts
# ---------------------------------------------------------------------------

TWO_PAIRS = sessions_of("researcher", same_both_arms(2))  # task-000 then task-001, full then lean


def part_of(
    run_id: str,
    sessions: Iterable[SessionRecord],
    *,
    started_at: str,
    version: str,
    extra: Mapping[str, object],
) -> RunResults:
    whole = results_of(list(sessions), extra={"started_at": started_at, **extra})
    return dataclasses.replace(
        whole, run=dataclasses.replace(whole.run, id=run_id, claude_code_version=version)
    )


def stopped_part(sessions: Iterable[SessionRecord] = TWO_PAIRS[:2]) -> RunResults:
    streak = tuple(Launched(f"task-{i:03d}", "full", 1) for i in range(3))
    stop = StopReason("credit_exhausted", "no credit", "researcher", "full", streak, "both-arms")
    return part_of(
        "run-a",
        sessions,
        started_at="2026-10-12T09:00:00+00:00",
        version="9.9.8",
        extra={"ending": ending_to_json(InfraStopped(stop))},
    )


def continuing_part(
    sessions: Iterable[SessionRecord] = TWO_PAIRS[2:], **extra: object
) -> RunResults:
    return part_of(
        "run-b",
        sessions,
        started_at="2026-10-13T09:00:00+00:00",
        version="9.9.9",
        extra={"continues": "run-a", "ending": ending_to_json(Finished()), **extra},
    )


def test_a_continued_runs_report_says_so_and_names_every_part_with_what_it_cost():
    text = report.render(continuing_part(), [stopped_part()])

    assert "Continued run: part 2 of 2" in text
    assert line_of(text, "part 1:") == (
        "part 1: run-a (started 2026-10-12T09:00:00+00:00; Claude Code 9.9.8; 2 sessions launched;"
        " $0.02 spent; 3 full sessions in a row ended in credit_exhausted with the same evidence)"
    )
    assert line_of(text, "part 2:") == (
        "part 2: run-b (started 2026-10-13T09:00:00+00:00; Claude Code 9.9.9; 2 sessions launched;"
        " $0.02 spent; it finished its plan)"
    )


def test_a_continued_runs_role_section_counts_the_pairs_of_every_part():
    text = report.render(continuing_part(), [stopped_part()])

    assert "2 complete pairs of 2 paired tasks;" in text


def test_a_refused_launch_is_not_a_session_the_part_launched():
    refusal = Errored(LAUNCH_REFUSED, "the spend cap refused it")
    refused = dataclasses.replace(TWO_PAIRS[0], status=refusal)

    text = report.render(continuing_part(), [stopped_part([*TWO_PAIRS[:2], refused])])

    assert "2 sessions launched" in line_of(text, "part 1:")


def test_a_run_that_continues_nothing_names_no_parts():
    text = report.render(continuing_part())

    assert "Continued run" not in text
    assert "part 1:" not in text


def test_a_continued_runs_report_does_not_list_its_own_parts_as_earlier_runs():
    draws = [
        {"run_ids": ["run-a"], "flip": "underpowered", "interim": False},
        {"run_ids": ["run-0"], "flip": "clear", "interim": False},
    ]
    lineage = [{"run_id": "run-a", "stop": "x"}, {"run_id": "run-b", "stop": None}]

    text = report.render(continuing_part(lineage=lineage, **listing(draws=draws)), [stopped_part()])

    assert "same definition and kernel: run-0: flip clear." in text
