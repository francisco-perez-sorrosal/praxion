"""Orchestrator — wires families → ReportWriter → Report.

The orchestrator is intentionally thin: no business logic beyond aggregation.
It instantiates families (or accepts pre-built instances), runs each against
the corpus, aggregates CheckResults, writes the report, and returns the Report.

Fail-soft contract: if a family's run() raises, the orchestrator captures the
error as a FAIL CheckResult and continues with the remaining families.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from praxion_evals.harness.judge_client import JudgeClient, estimate_cost_usd, judge_workers
from praxion_evals.harness.report_writer import ReportWriter
from praxion_evals.harness.schemas import CheckResult, Corpus, Report, sum_usage

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

    def run(
        self,
        corpus: Corpus,
        judge: JudgeClient,
        *,
        mechanical_only: bool = False,
    ) -> Report:
        """Run all families, aggregate results, write the report, and return it.

        Each family's run() is called in registration order.  If a family raises
        any exception, the error is captured as a FAIL CheckResult and the next
        family continues.

        Args:
            corpus: Resolved corpus to run checks against.
            judge: JudgeClient for LLM-backed checks.
            mechanical_only: When True, families skip every LLM-judged check.

        Returns:
            Report with all check results and a non-empty report_path.
        """
        all_results: list[CheckResult] = []
        total_items = len(corpus.decisions) + len(corpus.specs) + len(corpus.verification_reports)

        for family in self._families:
            family_id = getattr(family, "id", family.__class__.__name__)
            print(f"[{family_id}] start — corpus={total_items} items", flush=True)
            try:
                family_results = family.run(corpus, judge, mechanical_only=mechanical_only)
                all_results.extend(family_results)
                pass_count = sum(1 for r in family_results if r.verdict == "PASS")
                warn_count = sum(1 for r in family_results if r.verdict == "WARN")
                fail_count = sum(1 for r in family_results if r.verdict == "FAIL")
                summary = f"{pass_count} PASS, {warn_count} WARN, {fail_count} FAIL"
                print(f"[{family_id}] done — {len(family_results)} checks, {summary}", flush=True)
            except Exception as exc:
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

        # Model absent (e.g. a test double with no .model) prices as "unpriced",
        # same as any other unrecognized model — see estimate_cost_usd().
        usage_totals = sum_usage(all_results)
        cost_usd_estimate = estimate_cost_usd(getattr(judge, "model", ""), usage_totals)

        report = Report(
            corpus=corpus,
            check_results=tuple(all_results),
            cost_usd_estimate=cost_usd_estimate,
            judge_calls=getattr(judge, "call_count", 0),
            judge_cache_hits=getattr(judge, "cache_hit_count", 0),
            judge_workers=judge_workers(),
        )

        writer = ReportWriter(output_dir=self._output_dir)
        report_path = writer.write(report)
        writer.append_log(report, report_path)

        return dataclasses.replace(report, report_path=report_path)
