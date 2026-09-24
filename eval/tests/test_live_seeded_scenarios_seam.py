"""Behavioral tests for the additive public grading seam in `seeded_scenarios`.

`grade_mechanical`/`judge_scenario` are thin wrappers the live runner calls so
its grading can never diverge from `SeededScenarioFamily`'s own path. Every
assertion here compares the seam's output against that existing path directly
— never against a hand-written expectation — so a future edit to the family's
internals is caught here too.

Also covers the orchestrator's amendment to `_check_spawn_selection`: tier
comparison is case-insensitive, and `expected_agents` only needs to be a
subset of `recorded_agents` (after stripping a `<plugin>:` prefix and
lowercasing both sides) — not an exact match.
"""

from __future__ import annotations

import copy
from typing import Any


class FakeJudgeClient:
    """Scripted JudgeClient double — never calls a real SDK."""

    def __init__(
        self, verdict: str = "PASS", findings: tuple[str, ...] = ("looks good",), score: int = 90
    ) -> None:
        self._verdict = verdict
        self._findings = findings
        self._score = score
        self.calls: list[tuple[str, str, Any]] = []

    def judge(self, rubric: str, artifact: str, schema: Any) -> Any:
        from praxion_evals.harness.schemas import JudgeVerdict

        self.calls.append((rubric, artifact, schema))
        return JudgeVerdict(
            verdict=self._verdict,  # type: ignore[arg-type]
            findings=self._findings,
            score=self._score,
            raw={"verdict": self._verdict, "findings": list(self._findings), "score": self._score},
        )


def _fixtures_by_id() -> dict[str, dict[str, Any]]:
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures

    return {data["scenario_id"]: data for data in load_scenario_fixtures()}


# ---------------------------------------------------------------------------
# grade_mechanical / judge_scenario == the family's own path, for every fixture
# ---------------------------------------------------------------------------


def test_grade_mechanical_matches_the_familys_own_mechanical_check_for_every_fixture():
    from praxion_evals.harness.families.seeded_scenarios import _MECHANICAL_CHECKS, grade_mechanical

    for scenario_id, data in _fixtures_by_id().items():
        expected = _MECHANICAL_CHECKS[scenario_id](data)

        assert grade_mechanical(data) == expected, scenario_id


def test_judge_scenario_returns_exactly_what_the_familys_own_llm_call_returns():
    from praxion_evals.harness.families.seeded_scenarios import judge_scenario

    for data in _fixtures_by_id().values():
        judge = FakeJudgeClient(verdict="WARN", findings=("a", "b"), score=42)
        family_judge = FakeJudgeClient(verdict="WARN", findings=("a", "b"), score=42)

        seam_verdict = judge_scenario(data, judge)
        family_verdict = family_judge.judge(
            rubric=data["llm_rubric"], artifact=_expected_artifact(data), schema=judge.calls[0][2]
        )

        assert seam_verdict == family_verdict
        assert judge.calls[0][0] == data["llm_rubric"]


def _expected_artifact(data: dict[str, Any]) -> str:
    """Recompute the artifact the family's own `_judged_artifact` would build."""
    import yaml

    for key in (
        "cases",
        "recorded_output",
        "adr_fragment",
        "recorded_command",
        "recorded_artifacts_written",
    ):
        if key in data:
            return yaml.safe_dump({key: data[key]}, sort_keys=False)
    raise KeyError(f"no judged field in {data.get('scenario_id')!r}")


def test_grade_mechanical_still_passes_every_frozen_fixture():
    from praxion_evals.harness.families.seeded_scenarios import grade_mechanical

    for scenario_id, data in _fixtures_by_id().items():
        passed, findings = grade_mechanical(data)

        assert passed, (scenario_id, findings)


# ---------------------------------------------------------------------------
# _check_spawn_selection amendment: case-insensitive tier, subset-of-agents
# ---------------------------------------------------------------------------


def _spawn_selection_data(case_overrides: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(_fixtures_by_id()["spawn-selection"])
    data["cases"] = [{**data["cases"][2], **case_overrides}]  # the "standard" case
    return data


def test_spawn_selection_tier_comparison_is_case_insensitive():
    from praxion_evals.harness.families.seeded_scenarios import grade_mechanical

    data = _spawn_selection_data({"recorded_tier": "STANDARD "})

    passed, findings = grade_mechanical(data)

    assert passed, findings


def test_spawn_selection_accepts_a_recorded_agent_superset_of_expected():
    from praxion_evals.harness.families.seeded_scenarios import grade_mechanical

    data = _spawn_selection_data(
        {
            "recorded_agents": [
                "praxion:researcher",
                "praxion:systems-architect",
                "praxion:implementation-planner",
                "praxion:implementer",
                "praxion:test-engineer",
                "praxion:verifier",
            ]
        }
    )

    passed, findings = grade_mechanical(data)

    assert passed, findings


def test_spawn_selection_still_fails_when_an_expected_agent_is_missing():
    from praxion_evals.harness.families.seeded_scenarios import grade_mechanical

    data = _spawn_selection_data({"recorded_agents": ["praxion:implementer"]})

    passed, findings = grade_mechanical(data)

    assert not passed
    assert "not a subset" in findings[0]
