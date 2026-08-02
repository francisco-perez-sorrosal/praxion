"""Behavioral tests for ``enrich_readiness`` — the out-of-collect LLM step.

No test makes a real network call: ``judge.detect_auth`` and
``urllib.request.urlopen`` are mocked throughout. The tests pin the gated
behaviors:

* no auth → ``llm_skipped``, LLM criteria excluded from denominators, exit 0,
* ``--require-readiness-ai`` + no auth → ``SystemExit`` raised before any write,
* ``--mechanical-only`` → ``llm_skipped`` regardless of auth,
* auth present (mocked transport) → verdicts merged, ``llm.status == "scored"``,
  ``grounded_on`` populated from the prior report,
* transport error mid-flight → ``llm_error`` (graceful), or re-raise under the
  require flag.

The readiness block is constructed via the real collector so the ``data``
shape under test matches production exactly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.project_metrics.cli import enrich_readiness
from scripts.project_metrics.collectors.base import CollectionContext
from scripts.project_metrics.collectors.readiness import judge
from scripts.project_metrics.collectors.readiness_collector import ReadinessCollector
from scripts.project_metrics.schema import AggregateBlock, Report

# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _args(*, mechanical_only: bool = False, require_readiness_ai: bool = False) -> Any:
    """Build a minimal argparse-namespace-like object for the two flags."""

    return argparse.Namespace(
        mechanical_only=mechanical_only,
        require_readiness_ai=require_readiness_ai,
    )


def _aggregate() -> AggregateBlock:
    return AggregateBlock(
        schema_version="1.1.0",
        timestamp="2026-04-23T12:00:00Z",
        commit_sha="0" * 40,
        window_days=90,
        sloc_total=0,
        file_count=0,
        language_count=0,
        ccn_p95=None,
        cognitive_p95=None,
        cyclic_deps=None,
        churn_total_90d=0,
        change_entropy_90d=0.0,
        truck_factor=0,
        hotspot_top_score=0.0,
        hotspot_gini=0.0,
        coverage_line_pct=None,
    )


def _report_with_readiness(repo_root: Path) -> Report:
    """Build a Report whose ``readiness`` collector block is freshly collected."""

    collector = ReadinessCollector(repo_root=repo_root)
    ctx = CollectionContext(repo_root=str(repo_root), window_days=90, git_sha="0" * 40)
    result = collector.collect(ctx)
    return Report(
        schema_version="1.1.0",
        aggregate=_aggregate(),
        tool_availability={},
        collectors={"readiness": result},
    )


def _verdict_response(passed: bool, rationale: str, recommendation: str | None = None) -> bytes:
    """A Messages-API-shaped response body carrying a verdict tool call.

    When ``recommendation`` is supplied it is included in the tool input,
    mirroring the judge returning a project-specific next step on a failure.
    """

    verdict_input: dict[str, Any] = {"passed": passed, "rationale": rationale}
    if recommendation is not None:
        verdict_input["recommendation"] = recommendation
    document = {
        "id": "msg_test",
        "content": [
            {
                "type": "tool_use",
                "name": "verdict",
                "input": verdict_input,
            }
        ],
    }
    return json.dumps(document).encode("utf-8")


class _FakeResponse:
    """Context-manager stand-in for the urlopen response object."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def populated_repo(tmp_path: Path) -> Path:
    """A repo with a README and a couple of signals so scoring is non-trivial."""

    (tmp_path / "README.md").write_text(
        "# Project\n\nSetup, usage, and architecture.\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return tmp_path


def _llm_criteria(data: dict) -> list[dict]:
    return [c for c in data["criteria"] if c["llm"]]


# ---------------------------------------------------------------------------
# No auth → llm_skipped, exit 0, criteria excluded from denominators.
# ---------------------------------------------------------------------------


class TestNoAuthDegrades:
    """Offline CI: no credential present → mechanical-only, run still succeeds."""

    def test_no_auth_marks_llm_skipped(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value=None):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["llm"]["status"] == "llm_skipped"

    def test_no_auth_sets_mechanical_only_note(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value=None):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["note"] == "mechanical-only"

    def test_no_auth_leaves_llm_criteria_unscored(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value=None):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        for crit in _llm_criteria(data):
            assert crit["passed"] is None

    def test_no_auth_excludes_llm_criteria_from_denominators(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value=None):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        # An unscored (passed=None) criterion never counts toward any pillar
        # denominator — the documentation pillar has two LLM criteria, so its
        # denominator reflects mechanical criteria only.
        docs = next(p for p in data["pillars"] if p["id"] == "documentation")
        scored_docs = [
            c
            for c in data["criteria"]
            if c["pillar"] == "documentation"
            and not c["llm"]
            and c["applicable"]
            and c["passed"] is not None
        ]
        assert docs["denominator"] == len(scored_docs)


# ---------------------------------------------------------------------------
# --require-readiness-ai + no auth → SystemExit before any write.
# ---------------------------------------------------------------------------


class TestRequireFlagHardFails:
    """The require flag turns a missing credential into a hard, pre-write fail."""

    def test_require_flag_no_auth_raises_system_exit(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value=None):
            with pytest.raises(SystemExit):
                enrich_readiness(report, populated_repo, _args(require_readiness_ai=True))

    def test_require_flag_no_auth_does_not_mutate_llm_block(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value=None):
            with pytest.raises(SystemExit):
                enrich_readiness(report, populated_repo, _args(require_readiness_ai=True))

        # The block was never marked skipped — it still carries the collector's
        # pending placeholder, proving the raise happened before any mutation.
        data = report.collectors["readiness"].data
        assert data["llm"]["status"] == "pending"


# ---------------------------------------------------------------------------
# --mechanical-only → llm_skipped regardless of auth.
# ---------------------------------------------------------------------------


class TestMechanicalOnlyFlag:
    """The flag skips the LLM tier even when a credential is present."""

    def test_mechanical_only_marks_skipped_even_with_auth(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with patch.object(judge, "detect_auth", return_value="api_key"):
            enrich_readiness(report, populated_repo, _args(mechanical_only=True))

        data = report.collectors["readiness"].data
        assert data["llm"]["status"] == "llm_skipped"

    def test_mechanical_only_never_calls_the_judge(self, populated_repo: Path) -> None:
        report = _report_with_readiness(populated_repo)
        with (
            patch.object(judge, "detect_auth", return_value="api_key"),
            patch.object(judge, "judge_criterion") as judge_mock,
        ):
            enrich_readiness(report, populated_repo, _args(mechanical_only=True))

        judge_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Auth present + mocked transport → verdicts merged, scored, grounded.
# ---------------------------------------------------------------------------


@pytest.fixture
def with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a real ANTHROPIC_API_KEY so the judge's auth header build succeeds.

    The judge reads ``os.environ`` directly when building request headers, so
    grounding the credential in the environment (not just patching
    ``detect_auth``) keeps the auth-detection and header-build paths consistent
    — the transport itself is still mocked, so no network call occurs.
    """

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


class TestAuthPresentScores:
    """With a credential and a mocked judge, the LLM criteria get scored."""

    def test_auth_merges_verdicts_and_sets_scored(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(_verdict_response(True, "looks good"))

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["llm"]["status"] == "scored"
        for crit in _llm_criteria(data):
            if crit["applicable"]:
                assert crit["passed"] is True
                assert crit["rationale"] == "looks good"

    def test_auth_sets_model_and_clears_note(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(_verdict_response(False, "needs work"))

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["llm"]["model"] == judge.DEFAULT_MODEL
        assert data["note"] is None

    def test_grounded_on_names_prior_report_file(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        # Plant a prior report carrying a readiness block so grounding has a
        # source to name.
        reports_dir = populated_repo / ".ai-state" / "metrics_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        prior_name = "METRICS_REPORT_2026-04-22_10-00-00.json"
        prior_payload = {
            "schema_version": "1.1.0",
            "readiness": {
                "status": "ok",
                "data": {
                    "criteria": [
                        {
                            "id": "c.docs.readme_quality",
                            "passed": True,
                            "rationale": "prior pass",
                        }
                    ]
                },
            },
        }
        (reports_dir / prior_name).write_text(json.dumps(prior_payload), encoding="utf-8")

        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(_verdict_response(True, "still good"))

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["llm"]["grounded_on"] == prior_name

    def test_grounded_on_is_null_on_first_run(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        # No prior report → grounded_on must be null.
        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(_verdict_response(True, "ok"))

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["llm"]["grounded_on"] is None


# ---------------------------------------------------------------------------
# Transport error → llm_error (graceful) or re-raise under the require flag.
# ---------------------------------------------------------------------------


class TestJudgeErrorDegrades:
    """A mid-flight judge failure degrades unless the require flag is set."""

    def test_urlopen_error_degrades_to_llm_error(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _boom(request: Any, timeout: int = 0) -> _FakeResponse:
            raise OSError("connection reset")

        with patch("urllib.request.urlopen", _boom):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        assert data["llm"]["status"] == "llm_skipped"
        assert data["llm"]["reason"] == "llm_error"

    def test_urlopen_error_reraises_under_require_flag(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _boom(request: Any, timeout: int = 0) -> _FakeResponse:
            raise OSError("connection reset")

        with patch("urllib.request.urlopen", _boom):
            with pytest.raises(judge.JudgeUnavailableError):
                enrich_readiness(report, populated_repo, _args(require_readiness_ai=True))


# ---------------------------------------------------------------------------
# Recommendation layering — LLM recommendation overrides static remediation
# for failing criteria; static fallback survives when none is returned.
# ---------------------------------------------------------------------------


class TestRecommendationLayering:
    """Failing LLM criteria get the project-specific recommendation; the static
    deterministic remediation remains the fallback otherwise."""

    def test_failing_llm_criterion_uses_llm_recommendation(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(
                _verdict_response(False, "thin", recommendation="Add an arch section")
            )

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        failing_llm = [c for c in _llm_criteria(data) if c["applicable"] and c["passed"] is False]
        assert failing_llm, "expected at least one failing LLM criterion"
        for crit in failing_llm:
            assert crit["remediation"] == "Add an arch section"
            assert crit["remediation_source"] == "llm"

    def test_passing_llm_criterion_keeps_static_remediation_source(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(_verdict_response(True, "great", recommendation=""))

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        for crit in _llm_criteria(data):
            if crit["passed"] is True:
                assert crit["remediation_source"] == "static"

    def test_mechanical_criteria_retain_static_remediation(
        self, populated_repo: Path, with_api_key: None
    ) -> None:
        report = _report_with_readiness(populated_repo)

        def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(_verdict_response(False, "thin", recommendation="LLM advice"))

        with patch("urllib.request.urlopen", _fake_urlopen):
            enrich_readiness(report, populated_repo, _args())

        data = report.collectors["readiness"].data
        # The LLM recommendation must never leak onto a mechanical criterion.
        for crit in data["criteria"]:
            if not crit["llm"]:
                assert crit["remediation_source"] == "static"
                assert crit["remediation"] != "LLM advice"
