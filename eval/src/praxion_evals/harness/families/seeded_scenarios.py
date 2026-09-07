"""Seeded scenario corpus (process-economy P0.7).

Five static, golden-fixture scenarios seeded under
``eval/tests/fixtures/scenarios/`` that exercise agent-behavior conventions
the process-economy roadmap depends on for measuring future simplification:
tier/spawn selection, UI-step conformance, ADR authoring, commit-staging
discipline, and Lightweight-tier artifact minimalism.

Each fixture carries a ``recorded_*`` field — a golden capture of what a
compliant agent produced for the seeded input. This family grades the
recorded fixture; it does not spawn a live agent. (The one scenario that
does spawn a live subagent, ``inheritance-probe``, is intentionally out of
this family's scope — see ``eval/scripts/inheritance_probe.py``.)

Mechanical checks (no API calls) validate the recorded field against a
structural rule specific to each scenario. LLM-judged checks (skipped under
``mechanical_only``) ask a judge to rate the same recorded field against a
rubric baked into the fixture — the paid tier this family exists to support.

This module never imports claude_agent_sdk or anthropic directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from praxion_evals.harness.families import FAMILY_REGISTRY, Family
from praxion_evals.harness.families.family1_pipeline_fidelity import (
    _REQUIRED_FRONTMATTER_FIELDS,
    _parse_frontmatter,
)
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import CheckResult, Corpus

# ---------------------------------------------------------------------------
# Fixture location and load order
# ---------------------------------------------------------------------------

# eval/src/praxion_evals/harness/families/ -> eval/
_EVAL_ROOT = Path(__file__).resolve().parents[4]
_SCENARIOS_DIR = _EVAL_ROOT / "tests" / "fixtures" / "scenarios"

_SCENARIO_FILES = (
    "01_spawn_selection.yaml",
    "02_ui_step_conformance.yaml",
    "03_adr_authoring.yaml",
    "04_commit_staging.yaml",
    "05_lightweight_fix.yaml",
)

_JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "WARN", "FAIL"],
            "description": "Overall verdict for this seeded scenario.",
        },
        "findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Prose observations about the recorded fixture.",
        },
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Confidence score 0-100.",
        },
    },
    "required": ["verdict", "findings", "score"],
}


def load_scenario_fixtures(scenarios_dir: Path = _SCENARIOS_DIR) -> list[dict[str, Any]]:
    """Load the seeded scenario fixtures in a fixed, deterministic order.

    Args:
        scenarios_dir: Directory containing the scenario YAML fixtures.
                        Overridable for tests against a scratch fixture set.

    Returns:
        One dict per fixture file, in ``_SCENARIO_FILES`` order.
    """
    fixtures: list[dict[str, Any]] = []
    for filename in _SCENARIO_FILES:
        path = scenarios_dir / filename
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        fixtures.append(data)
    return fixtures


# ---------------------------------------------------------------------------
# Per-scenario mechanical checks
# ---------------------------------------------------------------------------


def _check_spawn_selection(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Every seeded case's recorded tier+agents must match the expected pair."""
    mismatches: list[str] = []
    for case in data["cases"]:
        if case["recorded_tier"] != case["expected_tier"]:
            mismatches.append(
                f"task {case['task']!r}: recorded_tier={case['recorded_tier']!r} "
                f"!= expected_tier={case['expected_tier']!r}"
            )
        elif case["recorded_agents"] != case["expected_agents"]:
            mismatches.append(
                f"task {case['task']!r}: recorded_agents={case['recorded_agents']!r} "
                f"!= expected_agents={case['expected_agents']!r}"
            )
    return (not mismatches, mismatches)


def _check_ui_step_conformance(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """The recorded output must cite every required interface-skill convention."""
    output_lower = data["recorded_output"].lower()
    missing = [c for c in data["required_citations"] if c.lower() not in output_lower]
    if missing:
        return False, [f"recorded_output is missing citation(s): {missing}"]
    return True, []


def _check_adr_authoring(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Architectural fragments must carry complete frontmatter + Disconfirmation."""
    content = data["adr_fragment"]
    frontmatter = _parse_frontmatter(content)
    problems: list[str] = []

    missing_fields = [f for f in _REQUIRED_FRONTMATTER_FIELDS if f not in frontmatter]
    if missing_fields:
        problems.append(f"frontmatter missing required field(s): {missing_fields}")

    if frontmatter.get("category") == "architectural" and "## Disconfirmation" not in content:
        problems.append(
            "category is 'architectural' but the body has no '## Disconfirmation' section"
        )

    return (not problems, problems)


def _check_commit_staging(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """The recorded staging command must be pathspec-scoped."""
    command = data["recorded_command"]
    tokens = command.split()
    problems: list[str] = []

    hit_tokens = [t for t in data["forbidden_tokens"] if t in tokens]
    if hit_tokens:
        problems.append(f"recorded_command uses forbidden flag(s): {hit_tokens}")

    hit_paths = [p for p in data["forbidden_paths"] if p in command]
    if hit_paths:
        problems.append(f"recorded_command stages forbidden path(s): {hit_paths}")

    return (not problems, problems)


def _check_lightweight_fix(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """A Lightweight fix must not write any full-pipeline planning artifact."""
    written = data["recorded_artifacts_written"]
    problems: list[str] = []
    for artifact_path in written:
        for pattern in data["forbidden_artifact_patterns"]:
            if pattern in artifact_path:
                problems.append(f"{artifact_path!r} matches forbidden pattern {pattern!r}")
    return (not problems, problems)


_MECHANICAL_CHECKS: dict[str, Any] = {
    "spawn-selection": _check_spawn_selection,
    "ui-step-conformance": _check_ui_step_conformance,
    "adr-authoring": _check_adr_authoring,
    "commit-staging": _check_commit_staging,
    "lightweight-fix": _check_lightweight_fix,
}


def _slug(scenario_id: str) -> str:
    return scenario_id.replace("-", "_")


def _judged_artifact(data: dict[str, Any]) -> str:
    """Return the fixture field the LLM judge grades for a given scenario."""
    for key in (
        "cases",
        "recorded_output",
        "adr_fragment",
        "recorded_command",
        "recorded_artifacts_written",
    ):
        if key in data:
            return yaml.safe_dump({key: data[key]}, sort_keys=False)
    raise KeyError(f"no judged field found in scenario fixture {data.get('scenario_id')!r}")


# ---------------------------------------------------------------------------
# SeededScenarioFamily implementation
# ---------------------------------------------------------------------------


class SeededScenarioFamily(Family):
    """Seeded scenario corpus: mechanical fixture grading + LLM-judged tier."""

    id = "seeded-scenario-corpus"
    name = "Seeded scenario corpus"
    corpus_paths = ()

    def run(
        self,
        corpus: Corpus,
        judge: JudgeClient,
        *,
        mechanical_only: bool = False,
    ) -> list[CheckResult]:
        """Grade each seeded scenario fixture, mechanically and (optionally) via judge.

        Args:
            corpus: Unused — this family reads its own bundled fixtures
                    rather than the resolved target corpus (the scenarios are
                    static seeded data, not artifacts that vary per target).
            judge: JudgeClient for the LLM-judged tier.
            mechanical_only: When True, skip the LLM-judged check per scenario.

        Returns:
            Ordered list of CheckResult objects, two per scenario at most
            (mechanical always; llm unless mechanical_only).
        """
        del corpus  # unused: static fixture corpus, not the resolved target
        results: list[CheckResult] = []
        for data in load_scenario_fixtures():
            scenario_id = data["scenario_id"]
            results.append(self._check_mechanical(scenario_id, data))
            if not mechanical_only:
                results.append(self._check_llm(scenario_id, data, judge))
        return results

    def _check_mechanical(self, scenario_id: str, data: dict[str, Any]) -> CheckResult:
        check_fn = _MECHANICAL_CHECKS[scenario_id]
        passed, problems = check_fn(data)
        return CheckResult(
            check_name=f"scenario_{_slug(scenario_id)}_mechanical",
            check_kind="mechanical",
            verdict="PASS" if passed else "FAIL",
            artifact_path=f"scenarios/{scenario_id}.yaml",
            findings=tuple(problems)
            if problems
            else (f"{scenario_id}: recorded fixture conforms.",),
            score=-1,
        )

    def _check_llm(self, scenario_id: str, data: dict[str, Any], judge: JudgeClient) -> CheckResult:
        print(f"[{self.id}] llm-check scenario_{_slug(scenario_id)} — {scenario_id}", flush=True)
        verdict_obj = judge.judge(
            rubric=data["llm_rubric"],
            artifact=_judged_artifact(data),
            schema=_JUDGE_SCHEMA,
        )
        return CheckResult(
            check_name=f"scenario_{_slug(scenario_id)}_llm",
            check_kind="llm",
            verdict=verdict_obj.verdict,
            artifact_path=f"scenarios/{scenario_id}.yaml",
            findings=verdict_obj.findings,
            score=verdict_obj.score,
        )


# ---------------------------------------------------------------------------
# Register in the global family registry
# ---------------------------------------------------------------------------

FAMILY_REGISTRY.append(SeededScenarioFamily)
