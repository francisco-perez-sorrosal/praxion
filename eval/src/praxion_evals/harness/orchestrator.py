"""Orchestrator — wires families → ReportWriter → Report.

The orchestrator is intentionally thin: no business logic beyond aggregation.
It instantiates families (or accepts pre-built instances), runs each against
the corpus, aggregates CheckResults, writes the report, and returns the Report.

Fail-soft contract: if a family's run() raises, the orchestrator captures the
error as a FAIL CheckResult and continues with the remaining families.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.report_writer import ReportWriter
from praxion_evals.harness.schemas import CheckResult, Corpus, Report

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Aggregate per-family CheckResults into a single written Report.

    Args:
        families: Ordered sequence of Family instances to run.
                  Results appear in the Report in this order.
        output_dir: Directory passed to ReportWriter for report + log files.
    """

    def __init__(self, families: list[Any], output_dir: Path | str) -> None:
        self._families = list(families)
        self._output_dir = Path(output_dir)

    def run(self, corpus: Corpus, judge: JudgeClient) -> Report:
        """Run all families, aggregate results, write the report, and return it.

        Each family's run() is called in registration order.  If a family raises
        any exception, the error is captured as a FAIL CheckResult and the next
        family continues.

        Args:
            corpus: Resolved corpus to run checks against.
            judge: JudgeClient for LLM-backed checks.

        Returns:
            Report with all check results and a non-empty report_path.
        """
        all_results: list[CheckResult] = []

        for family in self._families:
            try:
                family_results = family.run(corpus, judge)
                all_results.extend(family_results)
            except Exception as exc:
                family_id = getattr(family, "id", repr(family))
                all_results.append(
                    CheckResult(
                        check_name=f"family_error_{family_id}",
                        check_kind="mechanical",
                        verdict="FAIL",
                        artifact_path="(orchestrator)",
                        findings=(
                            f"Family {family_id!r} raised an error during run(): "
                            f"{type(exc).__name__}: {exc}",
                        ),
                        score=-1,
                    )
                )

        report = Report(
            corpus=corpus,
            check_results=tuple(all_results),
            cost_usd_estimate=0.0,
        )

        writer = ReportWriter(output_dir=self._output_dir)
        report_path = writer.write(report)
        writer.append_log(report, report_path)

        return Report(
            corpus=corpus,
            check_results=tuple(all_results),
            cost_usd_estimate=0.0,
            report_path=report_path,
        )
