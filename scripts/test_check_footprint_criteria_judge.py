"""Tests for the pure judge of `check_footprint_criteria.py`: the glob engine and every finding reason.

Every reason has a canary (a scenario that must draw it) and a golden-good twin (the nearest
scenario that must not). The judge takes its inputs as parameters, so freshness is tested with an
injected `Diffs`; the same behaviours meet real history in `test_check_footprint_criteria.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_footprint_criteria as cfc  # noqa: E402
from _footprint_grammar import (  # noqa: E402
    Footprint,
    NoRegistry,
    Registry,
    parse_measurements,
    parse_registry,
    parse_spec_tables,
)
from _footprint_testkit import (  # noqa: E402
    BUDGET_COMMAND,
    CRITERIA_HEADER,
    DECLARATION_HEADER,
    LOG_HEADER,
    PROMPT_COMMAND,
    REGISTRY_HEADER,
    criterion_row,
    log_row,
    plan,
    registry_row,
    table,
)

# --- the judge: scenario builder ------------------------------------------------------------

BASE_HEAD, FINAL_HEAD = "b0b0b0b0", "f1f1f1f1"
AGENT_FILE = "agents/a.md"
CLEAN = frozenset()
PROMPT_REGISTRY = registry_row("prompt-size", "agents/*.md, !agents/README.md", PROMPT_COMMAND)
CRITERION = criterion_row()  # FC-01, prompt-size, baseline-relative
BASELINE = log_row(phase="baseline", value="398 lines", head=BASE_HEAD, command=PROMPT_COMMAND)
FINAL = log_row(phase="final", value="399 lines", head=FINAL_HEAD, command=PROMPT_COMMAND)


def judged(
    stage="verify",
    *,
    criteria=(CRITERION,),
    declared=(),
    registry=(PROMPT_REGISTRY,),
    log=(BASELINE, FINAL),
    moved=(),
    since=None,
    between=None,
    tracked=(AGENT_FILE,),
):
    """The findings of one scenario; each keyword is the one thing a test changes."""
    spec = parse_spec_tables(
        plan(
            table(CRITERIA_HEADER, *criteria) if criteria else None,
            table(DECLARATION_HEADER, *declared) if declared else None,
        )
    )
    registry_parse = parse_registry(table(REGISTRY_HEADER, *registry) if registry else None)
    log_parse = parse_measurements(table(LOG_HEADER, *log) if log else "")
    diffs = cfc.Diffs(
        since_head={BASE_HEAD: CLEAN, FINAL_HEAD: CLEAN, **(since or {})},
        base_to_head={BASE_HEAD: CLEAN, FINAL_HEAD: CLEAN, **(between or {})},
    )
    return cfc.judge(stage, spec, registry_parse, log_parse, tuple(moved), diffs, tuple(tracked))


def reasons(findings):
    return sorted((f.code, f.reason) for f in findings)


def test_the_golden_good_scenario_draws_no_finding():
    assert judged() == ()


# --- the glob engine ------------------------------------------------------------------------

PROMPT_SIZE = Footprint("prompt-size", ("agents/*.md",), ("agents/README.md",), None, "")


def test_glob_star_crosses_directory_separators():
    assert cfc.glob_match("agents/*.md", "agents/deep/nested.md")
    assert not cfc.glob_match("agents/*.md", "skills/agents/x.md")


def test_exclusion_removes_a_path_from_the_footprint():
    paths = ("agents/a.md", "agents/README.md", "docs/x.md")

    assert cfc.footprint_paths(PROMPT_SIZE, paths) == ("agents/a.md",)


def test_moved_footprints_name_each_footprint_with_its_matching_paths():
    registry = Registry((PROMPT_SIZE, Footprint("docs", ("docs/*",), (), None, "")))

    moved = cfc.moved_footprints(registry, ("agents/a.md", "agents/b.md", "src/x.py"))

    assert moved == (cfc.Moved("prompt-size", ("agents/a.md", "agents/b.md")),)


def test_no_registry_moves_nothing():
    assert cfc.moved_footprints(NoRegistry(), ("agents/a.md",)) == ()


def test_dead_globs_name_an_include_glob_that_matches_no_tracked_file():
    registry = Registry((Footprint("hooks", ("hooks/*.py", "hooks.json"), (), None, ""),))

    assert cfc.dead_globs(registry, ("hooks/a.py",)) == (("hooks", "hooks.json"),)


# --- the inactive no-op ---------------------------------------------------------------------


def test_canary_inactive_when_there_is_no_registry_and_no_table():
    spec = parse_spec_tables(plan())

    assert not cfc.is_active(NoRegistry(), spec)
    assert judged(criteria=(), registry=(), log=(), moved=(AGENT_FILE,)) == ()


def test_active_once_either_a_registry_or_a_table_exists():
    with_table = parse_spec_tables(plan(table(CRITERIA_HEADER, CRITERION)))
    without = parse_spec_tables(plan())

    assert cfc.is_active(NoRegistry(), with_table)
    assert cfc.is_active(Registry(()), without)


def test_a_spec_table_that_is_only_malformed_still_activates_the_check():
    spec = parse_spec_tables(plan(table(CRITERIA_HEADER, criterion_row(id="bad"))))

    assert cfc.is_active(NoRegistry(), spec)


# --- FP01 unbounded -------------------------------------------------------------------------

OTHER_CRITERION = criterion_row(id="FC-02", footprint="listing-tokens", command=BUDGET_COMMAND)


def test_canary_flags_a_moved_registered_footprint_with_no_row():
    found = judged("plan", criteria=(OTHER_CRITERION,), registry=(PROMPT_REGISTRY,), log=(),
                   moved=(AGENT_FILE,))  # fmt: skip

    unbounded = [f for f in found if f.code == "FP01"]
    assert [(f.reason, f.footprint) for f in unbounded] == [("unbounded", "prompt-size")]
    assert AGENT_FILE in unbounded[0].message


def test_good_twin_a_bounded_moved_footprint_draws_no_unbounded():
    assert ("FP01", "unbounded") not in reasons(judged("plan", moved=(AGENT_FILE,), log=()))


def test_good_twin_a_declared_moved_footprint_draws_no_unbounded():
    declared = ("| prompt-size | the only instrument counts a finished pipeline |",)

    found = judged(
        "plan", criteria=(OTHER_CRITERION,), declared=declared, log=(), moved=(AGENT_FILE,)
    )

    assert ("FP01", "unbounded") not in reasons(found)


def test_good_twin_unmatched_and_excluded_paths_leave_a_footprint_unmoved():
    found = judged(
        "plan", criteria=(OTHER_CRITERION,), log=(), moved=("docs/x.md", "agents/README.md")
    )

    assert ("FP01", "unbounded") not in reasons(found)


def test_good_twin_the_spec_stage_ignores_moved_paths():
    found = judged("spec", criteria=(OTHER_CRITERION,), log=(), moved=(AGENT_FILE,))

    assert ("FP01", "unbounded") not in reasons(found)


# --- FP02 malformed, as the judge produces and passes it on ---------------------------------


def test_canary_flags_a_declaration_with_no_real_reason():
    found = judged("spec", declared=("| spawn-count | tbd |",), log=())

    assert ("FP02", "reasonless") in reasons(found)


def test_good_twin_a_declaration_with_a_reason_is_accepted():
    found = judged("spec", declared=("| spawn-count | counts a finished run only |",), log=())

    assert ("FP02", "reasonless") not in reasons(found)


def test_canary_flags_a_log_row_that_names_no_spec_criterion():
    stray = log_row(criterion="FC-07", phase="final", head=FINAL_HEAD, command=PROMPT_COMMAND)

    found = judged(log=(BASELINE, FINAL, stray))

    unknown = [f for f in found if f.reason == "unknown-criterion"]
    assert [(f.code, f.criterion) for f in unknown] == [("FP02", "FC-07")]


def test_good_twin_every_log_row_names_a_spec_criterion():
    assert ("FP02", "unknown-criterion") not in reasons(judged())


def test_canary_passes_on_a_log_row_that_breaks_the_log_grammar_at_verify_only():
    broken = log_row(head="not-hex", command=PROMPT_COMMAND)

    assert ("FP02", "bad-head") in reasons(judged(log=(BASELINE, FINAL, broken)))
    assert ("FP02", "bad-head") not in reasons(judged("plan", log=(BASELINE, FINAL, broken)))


# --- FP03 unmeasured: presence --------------------------------------------------------------


def test_canary_flags_a_criterion_with_no_final_row():
    assert ("FP03", "missing-final") in reasons(judged(log=(BASELINE,)))


def test_good_twin_a_criterion_with_a_final_row_is_measured():
    assert ("FP03", "missing-final") not in reasons(judged())


def test_canary_flags_a_baseline_criterion_with_no_baseline_row():
    assert ("FP03", "missing-baseline") in reasons(judged(log=(FINAL,)))


def test_good_twin_a_reference_criterion_needs_no_baseline_row():
    reference = criterion_row(against="reference: the 400-line ceiling")

    assert ("FP03", "missing-baseline") not in reasons(judged(criteria=(reference,), log=(FINAL,)))


def test_canary_flags_a_final_row_whose_reading_was_withheld():
    withheld = log_row(
        phase="final", value="n/a", reading="none: the instrument crashed", head=FINAL_HEAD,
        command=PROMPT_COMMAND,
    )  # fmt: skip

    found = judged(log=(BASELINE, withheld))

    assert [(f.code, f.reason) for f in found] == [("FP03", "no-reading")]


def test_canary_flags_a_baseline_row_whose_reading_was_withheld():
    withheld = log_row(
        phase="baseline", value="n/a", reading="none: not measurable then", head=BASE_HEAD,
        command=PROMPT_COMMAND,
    )  # fmt: skip

    assert ("FP03", "no-reading") in reasons(judged(log=(withheld, FINAL)))


def test_canary_flags_a_log_command_that_omits_the_criterions_command():
    wrong = log_row(phase="final", head=FINAL_HEAD, command=BUDGET_COMMAND)

    assert ("FP03", "wrong-command") in reasons(judged(log=(BASELINE, wrong)))


def test_good_twin_a_log_command_that_extends_the_criterions_command_is_the_same_instrument():
    extended = log_row(
        phase="final", head=FINAL_HEAD, command="`python3 scripts/check_agent_prompt_size.py --json --compare-ref abc1234`"
    )  # fmt: skip

    assert ("FP03", "wrong-command") not in reasons(judged(log=(BASELINE, extended)))


SUITE = "`.venv/bin/python -m pytest -q`"


def _suite_findings(command):
    suite_criterion = criterion_row(command=SUITE)
    baseline = log_row(phase="baseline", head=BASE_HEAD, command=SUITE)
    final = log_row(phase="final", head=FINAL_HEAD, command=command)
    return judged(criteria=(suite_criterion,), log=(baseline, final))


@pytest.mark.parametrize(
    "narrowed",
    [
        "`.venv/bin/python -m pytest -q tests/only_one_file.py`",
        "`.venv/bin/python -m pytest -q -x tests/only_one_file.py`",
        "`.venv/bin/python -m pytest -q -k widget tests/only_one_file.py`",
        "`.venv/bin/python -m pytest -q --junitxml out.xml tests/only_one_file.py`",
        "`.venv/bin/python -m pytest tests/only_one_file.py -q`",
        "`.venv/bin/python -m pytest -q 'unbalanced`",
    ],
)
def test_canary_flags_a_narrowed_run_as_a_different_instrument(narrowed):
    assert ("FP03", "wrong-command") in reasons(_suite_findings(narrowed))


@pytest.mark.parametrize(
    "same",
    [
        "`.venv/bin/python -m pytest -q`",
        "`.venv/bin/python -m pytest -q --no-cov`",
        "`.venv/bin/python -m pytest -q --junitxml out.xml -x`",
        "`.venv/bin/python -m pytest -q --junitxml=out.xml`",
    ],
)
def test_good_twin_added_options_and_their_values_are_the_same_instrument(same):
    assert ("FP03", "wrong-command") not in reasons(_suite_findings(same))


def test_good_twin_a_value_after_the_criterions_own_trailing_option_is_the_same_instrument():
    measure = "`python3 scripts/measure.py --compare-ref`"
    baseline = log_row(phase="baseline", head=BASE_HEAD, command=measure)
    final = log_row(
        phase="final", head=FINAL_HEAD, command="`python3 scripts/measure.py --compare-ref abc1234`"
    )

    found = judged(criteria=(criterion_row(command=measure),), log=(baseline, final))

    assert ("FP03", "wrong-command") not in reasons(found)


def _template_findings(criterion_command, logged_command):
    baseline = log_row(phase="baseline", head=BASE_HEAD, command=logged_command)
    final = log_row(phase="final", head=FINAL_HEAD, command=logged_command)
    return judged(criteria=(criterion_row(command=criterion_command),), log=(baseline, final))


@pytest.mark.parametrize(
    ("criterion_command", "logged_command"),
    [
        ("`/usr/bin/time -p <command...>`", "`/usr/bin/time -p python3 scripts/liveness.py --all`"),
        (
            "`.venv/bin/python -m pytest -q -m <marker>`",
            "`.venv/bin/python -m pytest -q -m liveness`",
        ),
        (
            "`python3 scripts/measure.py --compare-ref <ref>`",
            "`python3 scripts/measure.py --compare-ref abc1234`",
        ),
    ],
)
def test_good_twin_a_placeholder_matches_what_the_author_declared_variable(
    criterion_command, logged_command
):
    assert ("FP03", "wrong-command") not in reasons(
        _template_findings(criterion_command, logged_command)
    )


@pytest.mark.parametrize(
    ("criterion_command", "logged_command"),
    [
        ("`pytest -m <marker>`", "`pytest -m liveness tests/x.py`"),
        ("`/usr/bin/time -p <command...>`", "`/usr/bin/time -p`"),
        ("`/usr/bin/time -p <command...>`", "`/usr/bin/env -p python3 x.py`"),
        ("`pytest -m <marker>`", "`pytest -m <marker>`"),
        ("`/usr/bin/time -p <command...>`", "`/usr/bin/time -p <command...>`"),
    ],
)
def test_canary_a_placeholder_never_widens_past_its_declaration(criterion_command, logged_command):
    assert ("FP03", "wrong-command") in reasons(
        _template_findings(criterion_command, logged_command)
    )


def test_canary_flags_baseline_and_final_of_different_reading_kinds():
    estimate = log_row(
        phase="final", reading="estimate", head=FINAL_HEAD, command=PROMPT_COMMAND
    )  # fmt: skip

    assert ("FP03", "incomparable") in reasons(judged(log=(BASELINE, estimate)))


def test_good_twin_two_estimates_are_comparable():
    both = (
        log_row(phase="baseline", reading="estimate", head=BASE_HEAD, command=PROMPT_COMMAND),
        log_row(phase="final", reading="estimate", head=FINAL_HEAD, command=PROMPT_COMMAND),
    )

    assert ("FP03", "incomparable") not in reasons(judged(log=both))


def test_the_latest_row_per_phase_is_the_authoritative_one():
    superseded = log_row(phase="final", value="500 lines", head=FINAL_HEAD, command=BUDGET_COMMAND)

    assert judged(log=(BASELINE, superseded, FINAL)) == ()


@pytest.mark.parametrize("stage", ["spec", "plan"])
def test_good_twin_measurement_findings_belong_to_the_verify_stage_only(stage):
    found = judged(stage, log=())

    assert not [f for f in found if f.code == "FP03"]


# --- FP03 unmeasured: freshness -------------------------------------------------------------


def test_canary_flags_a_final_row_followed_by_a_change_to_the_footprints_paths():
    found = judged(since={FINAL_HEAD: frozenset({AGENT_FILE})})

    stale = [f for f in found if f.reason == "stale-final"]
    assert [f.criterion for f in stale] == ["FC-01"]
    assert AGENT_FILE in stale[0].message


def test_good_twin_a_later_change_outside_the_footprints_paths_leaves_the_final_fresh():
    outside = frozenset({"docs/x.md", "agents/README.md"})

    assert ("FP03", "stale-final") not in reasons(judged(since={FINAL_HEAD: outside}))


def test_canary_flags_a_final_row_whose_head_git_does_not_know():
    found = judged(log=(BASELINE, FINAL.replace(FINAL_HEAD, "deadbeef")))

    assert ("FP03", "stale-final") in reasons(found)


def test_canary_flags_a_baseline_row_later_than_a_change_to_the_paths():
    found = judged(between={BASE_HEAD: frozenset({AGENT_FILE})})

    assert ("FP03", "late-baseline") in reasons(found)


def test_good_twin_a_baseline_taken_before_any_change_to_the_paths_is_on_time():
    outside = frozenset({"docs/x.md"})

    assert ("FP03", "late-baseline") not in reasons(judged(between={BASE_HEAD: outside}))


def test_good_twin_a_reference_criterion_has_no_baseline_to_be_late():
    reference = criterion_row(against="reference: the ceiling")
    late = log_row(phase="baseline", head=BASE_HEAD, command=PROMPT_COMMAND)

    found = judged(
        criteria=(reference,), log=(late, FINAL), between={BASE_HEAD: frozenset({AGENT_FILE})}
    )

    assert ("FP03", "late-baseline") not in reasons(found)


UNREGISTERED = criterion_row(footprint="free-form")
UNREGISTERED_LOG = (
    log_row(phase="baseline", head=BASE_HEAD, command=PROMPT_COMMAND),
    log_row(phase="final", head=FINAL_HEAD, command=PROMPT_COMMAND),
)


def test_canary_an_unregistered_footprint_goes_stale_on_any_tracked_change():
    found = judged(criteria=(UNREGISTERED,), registry=(), log=UNREGISTERED_LOG,
                   since={FINAL_HEAD: frozenset({"src/anything.py"})})  # fmt: skip

    assert ("FP03", "stale-final") in reasons(found)


def test_good_twin_a_change_under_ai_state_does_not_stale_an_unregistered_footprint():
    found = judged(criteria=(UNREGISTERED,), registry=(), log=UNREGISTERED_LOG,
                   since={FINAL_HEAD: frozenset({".ai-state/FOOTPRINTS.md"})})  # fmt: skip

    assert ("FP03", "stale-final") not in reasons(found)


def test_an_unregistered_footprint_skips_the_late_baseline_check():
    found = judged(criteria=(UNREGISTERED,), registry=(), log=UNREGISTERED_LOG,
                   between={BASE_HEAD: frozenset({"src/anything.py"})})  # fmt: skip

    assert ("FP03", "late-baseline") not in reasons(found)


# --- FP04 unregistered, FP05 registry -------------------------------------------------------


def test_canary_reports_a_spec_footprint_missing_from_the_registry():
    found = judged("spec", criteria=(UNREGISTERED,), log=())

    assert [(f.code, f.severity, f.footprint) for f in found] == [("FP04", "info", "free-form")]


def test_canary_reports_every_spec_footprint_when_there_is_no_registry():
    found = judged(
        "spec", registry=(), log=(), declared=("| spawn-count | counts a finished run only |",)
    )

    assert sorted(f.footprint for f in found if f.code == "FP04") == ["prompt-size", "spawn-count"]


def test_good_twin_registry_names_match_spec_names_ignoring_case_and_padding():
    shouting = criterion_row(footprint="  Prompt-Size ")

    assert judged("spec", criteria=(shouting,), log=()) == ()


def test_canary_flags_an_include_glob_that_matches_no_tracked_file():
    found = judged("spec", log=(), tracked=("docs/x.md",))

    assert [(f.code, f.reason, f.footprint) for f in found] == [
        ("FP05", "dead-glob", "prompt-size")
    ]


def test_good_twin_an_include_glob_with_a_tracked_match_is_alive():
    assert judged("spec", log=()) == ()


def test_canary_flags_a_malformed_and_a_duplicate_registry_row():
    registry = (PROMPT_REGISTRY, PROMPT_REGISTRY, registry_row("Bad Name"))

    found = judged("spec", registry=registry, log=())

    assert reasons(found) == [("FP05", "duplicate"), ("FP05", "malformed")]


def test_good_twin_two_distinct_well_formed_registry_rows_draw_nothing():
    other = registry_row("listing-tokens", "skills/*", BUDGET_COMMAND)

    assert (
        judged("spec", registry=(PROMPT_REGISTRY, other), log=(), tracked=(AGENT_FILE, "skills/x"))
        == ()
    )


# --- what a message tells the reader --------------------------------------------------------


def message_of(found, reason):
    return next(f.message for f in found if f.reason == reason)


def test_a_long_path_list_is_shortened_with_a_count_of_the_rest():
    many = tuple(f"agents/p{n}.md" for n in range(7))

    found = judged("plan", criteria=(OTHER_CRITERION,), log=(), moved=many)

    shown = message_of(found, "unbounded")
    assert "agents/p0.md, agents/p1.md, agents/p2.md, agents/p3.md, agents/p4.md" in shown
    assert "agents/p5.md" not in shown
    assert "(+2 more)" in shown


def test_a_stale_final_names_the_head_and_the_changed_path():
    found = judged(since={FINAL_HEAD: frozenset({AGENT_FILE})})

    message = message_of(found, "stale-final")
    assert FINAL_HEAD in message
    assert AGENT_FILE in message
    assert message.startswith("FC-01 ")


def test_a_late_baseline_names_the_head_and_the_changed_path():
    found = judged(between={BASE_HEAD: frozenset({AGENT_FILE})})

    message = message_of(found, "late-baseline")
    assert BASE_HEAD in message
    assert AGENT_FILE in message


def test_an_unresolvable_head_is_named_in_both_freshness_findings():
    log = (BASELINE.replace(BASE_HEAD, "cafebabe"), FINAL.replace(FINAL_HEAD, "deadbeef"))

    found = judged(log=log)

    assert "deadbeef" in message_of(found, "stale-final")
    assert "cafebabe" in message_of(found, "late-baseline")


def test_the_withheld_reason_and_the_two_commands_are_named():
    withheld = log_row(
        phase="final", reading="none: crashed", head=FINAL_HEAD, command=BUDGET_COMMAND
    )

    found = judged(log=(BASELINE, withheld))

    assert "crashed" in message_of(found, "no-reading")
    wrong = message_of(found, "wrong-command")
    assert "check_agent_prompt_size.py" in wrong
    assert "measure_token_budget.py" in wrong


def test_the_two_reading_kinds_that_differ_are_named():
    estimate = log_row(phase="final", reading="estimate", head=FINAL_HEAD, command=PROMPT_COMMAND)

    found = judged(log=(BASELINE, estimate))

    assert "measured against estimate" in message_of(found, "incomparable")


def test_a_missing_row_and_a_dead_glob_are_named():
    found = judged(log=(), tracked=("docs/x.md",))

    assert "no final" in message_of(found, "missing-final")
    assert "no baseline" in message_of(found, "missing-baseline")
    assert "agents/*.md" in message_of(found, "dead-glob")


def test_an_unregistered_footprint_says_why_it_is():
    absent = judged("spec", criteria=(UNREGISTERED,), log=())
    no_registry = judged("spec", registry=(), log=())

    assert "not in the registry" in message_of(absent, "unregistered")
    assert "no registry" in message_of(no_registry, "unregistered")


def test_a_declaration_without_a_registry_row_says_nothing_about_staleness():
    declared = ("| spawn-count | counts a finished run only |",)

    found = judged("spec", registry=(), log=(), criteria=(), declared=declared)

    message = message_of(found, "unregistered")
    assert "spawn-count" in message
    assert "declared not measured" in message
    assert "stale" not in message
