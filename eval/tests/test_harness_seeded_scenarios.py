"""Behavioral tests for the seeded scenario corpus family (P0.7).

Tests cover: fixture loading (all 5 scenarios present, in order), mechanical
checks against the shipped golden fixtures (all PASS — they are seeded to be
compliant), a mechanical-only run emitting zero LLM checks, a FakeJudgeClient
run producing one LLM CheckResult per scenario, and a deliberately-broken
fixture producing a FAIL from each mechanical check function.

All production imports are deferred inside each test body so pytest collection
succeeds before the family module exists (RED-state handshake).
"""

from __future__ import annotations

import copy
from typing import Any

# ---------------------------------------------------------------------------
# FakeJudgeClient — never calls a real SDK
# ---------------------------------------------------------------------------


class FakeJudgeClient:
    """Scripted JudgeClient double, mirroring the Family 2 test convention."""

    def __init__(
        self, verdict: str = "PASS", findings: tuple[str, ...] = ("looks good",), score: int = 90
    ) -> None:
        self._verdict = verdict
        self._findings = findings
        self._score = score

    def judge(self, rubric: str, artifact: str, schema: Any) -> Any:
        from praxion_evals.harness.schemas import JudgeVerdict

        return JudgeVerdict(
            verdict=self._verdict,  # type: ignore[arg-type]
            findings=self._findings,
            score=self._score,
            raw={"verdict": self._verdict, "findings": list(self._findings), "score": self._score},
        )


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def test_load_scenario_fixtures_returns_five_scenarios_in_order():
    """The shipped fixture set has exactly 5 scenarios in the documented order."""
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures

    fixtures = load_scenario_fixtures()
    scenario_ids = [f["scenario_id"] for f in fixtures]

    assert scenario_ids == [
        "spawn-selection",
        "ui-step-conformance",
        "adr-authoring",
        "commit-staging",
        "lightweight-fix",
    ]


def test_every_fixture_carries_an_llm_rubric():
    """Every scenario fixture must supply an llm_rubric for the judged tier."""
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures

    for fixture in load_scenario_fixtures():
        assert fixture.get("llm_rubric"), (
            f"scenario {fixture['scenario_id']!r} is missing an llm_rubric"
        )


# ---------------------------------------------------------------------------
# Mechanical checks — golden fixtures are seeded to PASS
# ---------------------------------------------------------------------------


def test_mechanical_only_run_produces_five_pass_and_zero_llm_checks():
    """A mechanical-only run grades all 5 golden fixtures PASS with no LLM
    calls, plus one always-SKIP result for the inheritance-probe scenario."""
    from praxion_evals.harness.families.seeded_scenarios import SeededScenarioFamily
    from praxion_evals.harness.judge_client import NullJudgeClient
    from praxion_evals.harness.schemas import EMPTY_CORPUS

    family = SeededScenarioFamily()
    results = family.run(EMPTY_CORPUS, NullJudgeClient(), mechanical_only=True)

    mechanical_results = [r for r in results if r.check_kind == "mechanical"]
    skip_results = [r for r in results if r.check_kind == "skip"]

    assert len(results) == 6, f"expected 5 mechanical + 1 skip, got {len(results)}"
    assert len(mechanical_results) == 5
    assert all(r.verdict == "PASS" for r in mechanical_results), [
        (r.check_name, r.findings) for r in mechanical_results if r.verdict != "PASS"
    ]
    assert len(skip_results) == 1
    assert skip_results[0].verdict == "SKIP"
    assert skip_results[0].check_name == "scenario_inheritance_probe_skip"


def test_full_run_adds_one_llm_result_per_scenario():
    """With mechanical_only=False, each fixture-graded scenario also gets one
    llm CheckResult; inheritance-probe still resolves to a single SKIP."""
    from praxion_evals.harness.families.seeded_scenarios import SeededScenarioFamily
    from praxion_evals.harness.schemas import EMPTY_CORPUS

    family = SeededScenarioFamily()
    results = family.run(EMPTY_CORPUS, FakeJudgeClient(), mechanical_only=False)

    assert len(results) == 11, (
        f"expected 11 results (5 mechanical + 5 llm + 1 skip), got {len(results)}"
    )
    llm_results = [r for r in results if r.check_kind == "llm"]
    skip_results = [r for r in results if r.check_kind == "skip"]
    assert len(llm_results) == 5
    assert all(r.verdict == "PASS" for r in llm_results)
    assert len(skip_results) == 1
    assert skip_results[0].verdict == "SKIP"


def test_mechanical_only_never_calls_the_judge():
    """NullJudgeClient.judge() raises if called — proving mechanical_only skips LLM calls."""
    from praxion_evals.harness.families.seeded_scenarios import SeededScenarioFamily
    from praxion_evals.harness.judge_client import NullJudgeClient
    from praxion_evals.harness.schemas import EMPTY_CORPUS

    family = SeededScenarioFamily()
    # Would raise RuntimeError if any mechanical_only=True path called judge.judge().
    family.run(EMPTY_CORPUS, NullJudgeClient(), mechanical_only=True)


# ---------------------------------------------------------------------------
# Per-scenario mechanical logic — deliberately broken fixtures fail
# ---------------------------------------------------------------------------


def _fixtures_by_id() -> dict[str, dict[str, Any]]:
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures

    return {f["scenario_id"]: f for f in load_scenario_fixtures()}


def test_spawn_selection_mismatch_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_spawn_selection

    data = copy.deepcopy(_fixtures_by_id()["spawn-selection"])
    data["cases"][0]["recorded_tier"] = "full"

    passed, problems = _check_spawn_selection(data)

    assert not passed
    assert problems


def test_ui_step_conformance_missing_citation_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_ui_step_conformance

    data = copy.deepcopy(_fixtures_by_id()["ui-step-conformance"])
    data["recorded_output"] = "Added a spinner because it seemed fine."

    passed, problems = _check_ui_step_conformance(data)

    assert not passed
    assert problems


def test_adr_authoring_missing_disconfirmation_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_adr_authoring

    data = copy.deepcopy(_fixtures_by_id()["adr-authoring"])
    data["adr_fragment"] = data["adr_fragment"].split("## Disconfirmation")[0]

    passed, problems = _check_adr_authoring(data)

    assert not passed
    assert any("Disconfirmation" in p for p in problems)


def test_adr_authoring_missing_frontmatter_field_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_adr_authoring

    data = copy.deepcopy(_fixtures_by_id()["adr-authoring"])
    data["adr_fragment"] = data["adr_fragment"].replace("made_by: agent\n", "")

    passed, problems = _check_adr_authoring(data)

    assert not passed
    assert any("made_by" in p for p in problems)


def test_commit_staging_dash_a_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_commit_staging

    data = copy.deepcopy(_fixtures_by_id()["commit-staging"])
    data["recorded_command"] = "git add -A"

    passed, problems = _check_commit_staging(data)

    assert not passed
    assert problems


def test_commit_staging_wal_path_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_commit_staging

    data = copy.deepcopy(_fixtures_by_id()["commit-staging"])
    data["recorded_command"] = "git add .ai-state/observations.jsonl"

    passed, problems = _check_commit_staging(data)

    assert not passed
    assert problems


def test_lightweight_fix_full_pipeline_artifact_fails():
    from praxion_evals.harness.families.seeded_scenarios import _check_lightweight_fix

    data = copy.deepcopy(_fixtures_by_id()["lightweight-fix"])
    data["recorded_artifacts_written"] = [
        ".ai-state/calibration_log.md",
        ".ai-work/some-slug/IMPLEMENTATION_PLAN.md",
    ]

    passed, problems = _check_lightweight_fix(data)

    assert not passed
    assert problems


# ---------------------------------------------------------------------------
# Registration + no-direct-SDK-import lint guard
# ---------------------------------------------------------------------------


def test_seeded_scenario_family_is_registered_in_family_registry():
    from praxion_evals.harness.families import FAMILY_REGISTRY
    from praxion_evals.harness.families.seeded_scenarios import SeededScenarioFamily

    assert SeededScenarioFamily in FAMILY_REGISTRY


def test_seeded_scenarios_module_source_contains_no_direct_sdk_imports():
    import inspect

    from praxion_evals.harness.families import seeded_scenarios

    source = inspect.getsource(seeded_scenarios)
    assert "import claude_agent_sdk" not in source
    assert "import anthropic" not in source


def test_seeded_scenario_family_wired_into_run_eval():
    """run_eval()'s composition must include SeededScenarioFamily."""
    import inspect

    from praxion_evals import harness

    source = inspect.getsource(harness.run_eval)
    assert "SeededScenarioFamily" in source
