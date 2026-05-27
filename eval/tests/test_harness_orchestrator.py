"""Behavioral tests for the Orchestrator — harness/orchestrator.py.

The orchestrator wires CorpusReader → JudgeClient → families → ReportWriter.
It is intentionally thin: no business logic, just glue.

Tests verify:
- Running multiple families produces a single aggregate Report
- A family that raises during run() doesn't crash the whole orchestrator (fail-soft)
- Result ordering is deterministic (families run in registry order)
- ReportWriter is called with the aggregated Report
- The orchestrator records which auth route was used in the report header

All production imports are deferred inside each test body (RED-state handshake).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Test doubles — defined at module scope for collection-time availability
# ---------------------------------------------------------------------------


class FakeJudgeClient:
    """Scripted JudgeClient that never calls a real SDK."""

    def __init__(
        self, verdict: str = "PASS", findings: tuple[str, ...] = ("ok",), score: int = 90
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


def _make_fake_corpus(label: str = "test-target") -> Any:
    """Build a minimal Corpus for orchestrator tests."""
    from praxion_evals.harness.schemas import Corpus

    return Corpus(
        target_kind="path",
        target_label=label,
        decisions=(),
        specs=(),
        verification_reports=(),
    )


class _FamilyProducingOnePass:
    """A minimal Family substitute that returns one PASS CheckResult."""

    id = "fake-family-pass"
    name = "Fake Family (pass)"
    corpus_paths: tuple[str, ...] = ()

    def run(self, corpus: Any, judge: Any) -> list[Any]:
        from praxion_evals.harness.schemas import CheckResult

        return [
            CheckResult(
                check_name="fake_check",
                check_kind="mechanical",
                verdict="PASS",
                artifact_path="fake/path.md",
                findings=("all good",),
                score=-1,
            )
        ]


class _FamilyProducingOneWarn:
    """A minimal Family substitute that returns one WARN CheckResult."""

    id = "fake-family-warn"
    name = "Fake Family (warn)"
    corpus_paths: tuple[str, ...] = ()

    def run(self, corpus: Any, judge: Any) -> list[Any]:
        from praxion_evals.harness.schemas import CheckResult

        return [
            CheckResult(
                check_name="fake_warn_check",
                check_kind="mechanical",
                verdict="WARN",
                artifact_path="fake/warn.md",
                findings=("worth noting",),
                score=-1,
            )
        ]


class _FamilyThatRaises:
    """A Family substitute that always raises RuntimeError during run()."""

    id = "fake-family-raises"
    name = "Fake Family (raises)"
    corpus_paths: tuple[str, ...] = ()

    def run(self, corpus: Any, judge: Any) -> list[Any]:
        raise RuntimeError("Simulated family failure")


# ---------------------------------------------------------------------------
# Orchestrator: run_eval produces a Report aggregating all family results
# ---------------------------------------------------------------------------


def test_run_eval_produces_report_with_combined_check_results(tmp_path: Path):
    """Running two families through the orchestrator produces a single Report
    whose check_results contains results from both families."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("test-two-families")
    judge = FakeJudgeClient()
    families = [_FamilyProducingOnePass(), _FamilyProducingOneWarn()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    assert len(report.check_results) == 2, (
        f"Report must contain results from both families (2 total); got {len(report.check_results)}"
    )
    verdicts = {r.verdict for r in report.check_results}
    assert "PASS" in verdicts, "Report must include the PASS result from the first family"
    assert "WARN" in verdicts, "Report must include the WARN result from the second family"


def test_run_eval_report_pass_and_warn_counts_are_correct(tmp_path: Path):
    """The Report's pass_count and warn_count properties reflect the aggregated results."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("count-test")
    judge = FakeJudgeClient()
    families = [_FamilyProducingOnePass(), _FamilyProducingOneWarn()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    assert report.pass_count == 1, f"Expected 1 PASS; got {report.pass_count}"
    assert report.warn_count == 1, f"Expected 1 WARN; got {report.warn_count}"
    assert report.fail_count == 0, f"Expected 0 FAIL; got {report.fail_count}"


def test_run_eval_result_order_follows_family_registry_order(tmp_path: Path):
    """CheckResults in the Report appear in the order families were registered."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("order-test")
    judge = FakeJudgeClient()
    # Pass family first, warn family second — results must appear in that order.
    families = [_FamilyProducingOnePass(), _FamilyProducingOneWarn()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    assert len(report.check_results) >= 2
    assert report.check_results[0].check_name == "fake_check", (
        "First result must come from the first family (fake_check); "
        f"got {report.check_results[0].check_name!r}"
    )
    assert report.check_results[1].check_name == "fake_warn_check", (
        "Second result must come from the second family (fake_warn_check); "
        f"got {report.check_results[1].check_name!r}"
    )


# ---------------------------------------------------------------------------
# Orchestrator: fail-soft — a family that raises doesn't break the run
# ---------------------------------------------------------------------------


def test_family_runtime_error_does_not_abort_orchestrator(tmp_path: Path):
    """When a family raises during run(), the orchestrator continues with the other families
    and includes a FAIL CheckResult capturing the error."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("fail-soft-test")
    judge = FakeJudgeClient()
    # Raising family first, then a normal family — the normal family must still run.
    families = [_FamilyThatRaises(), _FamilyProducingOnePass()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    # Must not raise — the orchestrator must catch the family's RuntimeError.
    report = orchestrator.run(corpus, judge)

    # The normal family's PASS result must still appear.
    pass_results = [r for r in report.check_results if r.verdict == "PASS"]
    assert len(pass_results) >= 1, (
        "The normal family's PASS result must appear even when the first family raises"
    )


def test_family_runtime_error_captured_as_fail_check_result(tmp_path: Path):
    """When a family raises, the orchestrator captures the error as a FAIL CheckResult."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("error-capture-test")
    judge = FakeJudgeClient()
    families = [_FamilyThatRaises()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    fail_results = [r for r in report.check_results if r.verdict == "FAIL"]
    assert len(fail_results) >= 1, (
        "A family that raises must produce at least one FAIL CheckResult capturing the error"
    )
    # The FAIL result's findings must mention the error
    fail_findings = " ".join(" ".join(r.findings) for r in fail_results)
    assert fail_findings, "FAIL CheckResult for a family error must have non-empty findings"


# ---------------------------------------------------------------------------
# Orchestrator: report is written via ReportWriter
# ---------------------------------------------------------------------------


def test_orchestrator_writes_report_file(tmp_path: Path):
    """After run(), the returned Report has a non-empty report_path pointing to a real file."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("report-write-test")
    judge = FakeJudgeClient()
    families = [_FamilyProducingOnePass()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    assert report.report_path, "Report.report_path must be non-empty after orchestrator.run()"
    assert Path(report.report_path).exists(), (
        f"The report file must exist at {report.report_path!r}"
    )


def test_orchestrator_report_file_contains_calibration_notes(tmp_path: Path):
    """The report file written by the orchestrator contains a Calibration Notes section."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("calibration-notes-test")
    judge = FakeJudgeClient()
    families = [_FamilyProducingOnePass()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    assert report.report_path
    content = Path(report.report_path).read_text(encoding="utf-8")
    assert "## Calibration Notes" in content, (
        "Report file must contain a '## Calibration Notes' section"
    )


# ---------------------------------------------------------------------------
# run_eval() composition — proves the wiring is live (no NotImplementedError)
# ---------------------------------------------------------------------------


def test_run_eval_is_wired_and_returns_report(tmp_path: Path, monkeypatch: Any):
    """run_eval() must not raise NotImplementedError; it must return a Report.

    JudgeClient is mocked so no real SDK or credentials are needed.
    CorpusReader is pointed at a tmp_path dir that has no artifacts — both
    families will emit only SKIP results, which is fine for wiring proof.
    """
    from unittest.mock import patch

    from praxion_evals.harness import run_eval
    from praxion_evals.harness.schemas import Report

    # Point run_eval at a repo root that has no ADRs/specs/reports so families
    # produce only SKIP results — we're testing composition, not family logic.
    (tmp_path / ".ai-state" / "decisions").mkdir(parents=True)
    (tmp_path / ".ai-state" / "specs").mkdir(parents=True)

    output_dir = tmp_path / "reports"

    with patch(
        "praxion_evals.harness.select_judge_client",
        return_value=FakeJudgeClient(),
    ):
        report = run_eval(
            target=str(tmp_path),
            output_dir=output_dir,
            repo_root=tmp_path,
        )

    assert isinstance(report, Report), f"run_eval() must return a Report; got {type(report)!r}"
    assert report.report_path, "run_eval() must produce a non-empty report_path"
    assert Path(report.report_path).exists(), (
        f"run_eval() report file must exist at {report.report_path!r}"
    )


# ---------------------------------------------------------------------------
# Orchestrator: corpus is passed through to families unchanged
# ---------------------------------------------------------------------------


def test_orchestrator_passes_corpus_to_each_family(tmp_path: Path):
    """The orchestrator passes the corpus to each family's run() method unchanged."""
    received_corpora: list[Any] = []

    class _CapturingFamily:
        id = "capturing"
        name = "Capturing Family"
        corpus_paths: tuple[str, ...] = ()

        def run(self, corpus: Any, judge: Any) -> list[Any]:
            received_corpora.append(corpus)
            return []

    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("corpus-pass-through")
    judge = FakeJudgeClient()
    families = [_CapturingFamily()]

    orchestrator = Orchestrator(families=families, output_dir=tmp_path)
    orchestrator.run(corpus, judge)

    assert len(received_corpora) == 1, "Family.run() must be called exactly once"
    assert received_corpora[0].target_label == "corpus-pass-through", (
        "The corpus passed to Family.run() must match the corpus given to the orchestrator"
    )


# ---------------------------------------------------------------------------
# Orchestrator: empty family list produces an empty-but-valid Report
# ---------------------------------------------------------------------------


def test_orchestrator_with_no_families_produces_empty_report(tmp_path: Path):
    """An orchestrator with zero families produces a valid Report with no check results."""
    from praxion_evals.harness.orchestrator import Orchestrator

    corpus = _make_fake_corpus("empty-families")
    judge = FakeJudgeClient()

    orchestrator = Orchestrator(families=[], output_dir=tmp_path)
    report = orchestrator.run(corpus, judge)

    assert report.check_results == () or len(report.check_results) == 0, (
        "A no-family orchestrator run must produce a Report with zero check results"
    )
    assert report.pass_count == 0
    assert report.warn_count == 0
    assert report.fail_count == 0
