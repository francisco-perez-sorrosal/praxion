"""A run never spends past its cap and always leaves exactly one results file.

A launch whose worst-case budget would cross the run-level cap is refused, as is
every later one; the refusal is recorded and the run marked incomplete. A session
that reports no cost is counted at its full budget. The results file records,
before any session launches, the flip rule's settings (margin, method, interval
confidence, target pairs and slack, retry policy, noise-allowance source), and for the run its
identifier, model and Claude Code version. An existing results file is replaced
only with `--overwrite`; without it the run is refused at start, before any launch.
"""

from __future__ import annotations

import json

from tests.acceptance.drivers.adherence_eval import (
    DEFAULT_MARGIN_PP,
    DEFAULT_REQUIRED_PAIRS,
    FAKE_CLAUDE_VERSION,
)
from tests.e2e.drivers.adherence_journey import run_journey

BELOW_ONE_SESSION = 0.5  # with a 1.0 per-session budget
EARLIER_RUN = json.dumps({"earlier": "run", "sessions": [1, 2, 3]})


def test_a_cap_below_one_sessions_budget_launches_nothing_and_records_the_refusal(tmp_path):
    journey = run_journey(
        tmp_path, roles=("researcher",), arms=("lean",), run_cap_usd=BELOW_ONE_SESSION
    )

    results = journey.results

    assert journey.launches == [], "a session launched although its budget alone crosses the cap"
    assert results.refused_launches() >= 1
    assert results.complete() is False
    assert journey.files_in_results_dir() == [journey.request.output], (
        "a run left more than one results file"
    )


def test_a_session_reporting_no_cost_is_counted_at_its_full_budget(tmp_path):
    journey = run_journey(
        tmp_path,
        roles=("researcher", "verifier"),
        arms=("lean",),
        run_cap_usd=1.5,
        session_budget_usd=1.0,
        sessions_report_cost=False,
    )

    assert len(journey.launches) == 1, (
        f"{len(journey.launches)} sessions launched under a cap that holds one uncosted session"
    )
    assert journey.results.refused_launches() >= 1


def test_the_flip_rules_default_settings_are_recorded_before_any_session(tmp_path):
    journey = run_journey(
        tmp_path, roles=("verifier",), arms=("full",), run_cap_usd=BELOW_ONE_SESSION
    )

    settings = journey.results.settings()

    assert journey.launches == []
    assert settings.margin_pp == DEFAULT_MARGIN_PP
    assert settings.required_pairs == DEFAULT_REQUIRED_PAIRS
    assert settings.method.strip(), "the paired comparison's method is not recorded"
    assert 0 < settings.confidence < 1
    assert settings.pair_slack >= 0
    assert settings.retry_policy.strip(), "the retry policy for errored sessions is not recorded"
    assert settings.allowance_source is None, (
        "no calibration run was declared, so every allowance is zero"
    )


def test_declared_flip_settings_are_recorded_as_declared(tmp_path):
    journey = run_journey(
        tmp_path,
        roles=("verifier",),
        arms=("full",),
        run_cap_usd=BELOW_ONE_SESSION,
        margin_pp=5,
        required_pairs=30,
    )

    settings = journey.results.settings()

    assert (settings.margin_pp, settings.required_pairs) == (5, 30)


def test_a_run_records_its_identifier_model_and_claude_code_version(tmp_path):
    journey = run_journey(tmp_path, roles=("verifier",), arms=("lean",))
    models = {v for launch in journey.launches for v in launch.option_values("--model")}

    results = journey.results

    assert results.run_id().strip()
    assert results.schema_version().strip()
    assert journey.launches, f"the run launched no session; {journey.describe()}"
    assert results.model() in models, (
        f"recorded model {results.model()!r}; sessions were launched with {models}"
    )
    assert results.claude_code_version() == FAKE_CLAUDE_VERSION


def test_an_existing_results_file_is_refused_at_start_without_overwrite(tmp_path):
    journey = run_journey(
        tmp_path,
        roles=("researcher",),
        arms=("lean",),
        existing_results=EARLIER_RUN,
    )

    assert journey.launches == [], (
        "a session launched although the results file could not be written"
    )
    assert journey.cli.exit_code != 0, (
        "the run reported success although it could not write its results"
    )
    assert journey.request.output.read_text(encoding="utf-8") == EARLIER_RUN


def test_overwrite_replaces_an_existing_results_file_with_this_runs(tmp_path):
    journey = run_journey(
        tmp_path,
        roles=("researcher",),
        arms=("lean",),
        run_cap_usd=BELOW_ONE_SESSION,
        existing_results=EARLIER_RUN,
        overwrite=True,
    )

    assert journey.request.output.read_text(encoding="utf-8") != EARLIER_RUN
    assert journey.results.schema_version().strip()
