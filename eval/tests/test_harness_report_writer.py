"""Behavioral tests for ReportWriter's cost/usage rendering.

ReportWriter renders a "Tokens" line summed across every judged CheckResult
and an "Estimated cost" line/log cell that reads "unpriced" when the judge
model has no known rate (Report.cost_usd_estimate is None), rather than a
hardcoded dollar figure.

All production imports are deferred inside each test body (RED-state
handshake, matching the rest of this test suite).
"""

from __future__ import annotations

from pathlib import Path


def _make_corpus():
    from praxion_evals.harness.schemas import Corpus

    return Corpus(
        target_kind="path",
        target_label="report-writer-test",
        decisions=(),
        specs=(),
        verification_reports=(),
    )


def _make_llm_check_result():
    from praxion_evals.harness.schemas import CheckResult, JudgeUsage

    return CheckResult(
        check_name="fake_llm_check",
        check_kind="llm",
        verdict="PASS",
        artifact_path="fake/llm.md",
        findings=("ok",),
        score=90,
        usage=JudgeUsage(
            input_tokens=1_000,
            output_tokens=200,
            cache_read_input_tokens=50,
            cache_creation_input_tokens=10,
        ),
    )


# ---------------------------------------------------------------------------
# Report body: Tokens line + priced Estimated cost line
# ---------------------------------------------------------------------------


def test_report_body_renders_tokens_line_with_summed_totals(tmp_path: Path):
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import Report

    report = Report(
        corpus=_make_corpus(),
        check_results=(_make_llm_check_result(),),
        cost_usd_estimate=0.0021,
    )

    writer = ReportWriter(output_dir=tmp_path)
    content = Path(writer.write(report)).read_text(encoding="utf-8")

    assert "**Tokens**: 1,000 in / 200 out / 50 cache-read / 10 cache-write" in content


def test_report_body_renders_dollar_cost_when_model_is_priced(tmp_path: Path):
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import Report

    report = Report(
        corpus=_make_corpus(),
        check_results=(_make_llm_check_result(),),
        cost_usd_estimate=0.0021,
    )

    writer = ReportWriter(output_dir=tmp_path)
    content = Path(writer.write(report)).read_text(encoding="utf-8")

    assert "**Estimated cost**: $0.0021 USD" in content


def test_report_body_renders_unpriced_when_cost_is_none(tmp_path: Path):
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import Report

    report = Report(
        corpus=_make_corpus(),
        check_results=(_make_llm_check_result(),),
        cost_usd_estimate=None,
    )

    writer = ReportWriter(output_dir=tmp_path)
    content = Path(writer.write(report)).read_text(encoding="utf-8")

    assert "**Estimated cost**: unpriced" in content
    assert "$None" not in content


# ---------------------------------------------------------------------------
# Log row: frozen columns, real cost cell (never a hardcoded zero)
# ---------------------------------------------------------------------------


def test_log_row_renders_dollar_cell_when_cost_is_known(tmp_path: Path):
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import Report

    report = Report(corpus=_make_corpus(), check_results=(), cost_usd_estimate=1.5)

    writer = ReportWriter(output_dir=tmp_path)
    report_path = writer.write(report)
    writer.append_log(report, report_path)

    log_content = (tmp_path / "PRAXION_EVAL_LOG.md").read_text(encoding="utf-8")
    assert "$1.5000" in log_content


def test_log_row_renders_unpriced_cell_when_cost_is_none(tmp_path: Path):
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import Report

    report = Report(corpus=_make_corpus(), check_results=(), cost_usd_estimate=None)

    writer = ReportWriter(output_dir=tmp_path)
    report_path = writer.write(report)
    writer.append_log(report, report_path)

    log_content = (tmp_path / "PRAXION_EVAL_LOG.md").read_text(encoding="utf-8")
    rows = [line for line in log_content.splitlines() if "report-writer-test" in line]
    assert len(rows) == 1
    assert "unpriced" in rows[0]
