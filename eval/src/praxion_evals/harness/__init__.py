"""Praxion eval harness — LLM-as-judge quality measurement.

Public surface:
    Family       — ABC for pluggable check families
    JudgeClient  — ABC for auth-mode adapters; use select_judge_client() to get one
    CorpusReader — resolves an invocation target to an immutable Corpus
    Family1PipelineOutcomeFidelity — Family 1 checks (pipeline-outcome fidelity)
    Family2BehavioralContractAdherence — Family 2 checks (BC adherence)
    Orchestrator — wires families → ReportWriter → Report
    ReportWriter — writes per-run report + appends to frozen-column log
    run_eval     — thin composition function: resolves corpus, selects judge,
                   runs both families, writes report, returns Report

SDK imports are lazy — importing this package never fails even when
``claude_agent_sdk`` or ``anthropic`` are absent.  They are only imported
inside the concrete JudgeClient subclass constructors / methods.
"""

from __future__ import annotations

from pathlib import Path

from praxion_evals.harness.corpus_reader import CorpusReader
from praxion_evals.harness.families import Family
from praxion_evals.harness.families.family1_pipeline_fidelity import (
    Family1PipelineOutcomeFidelity,
)
from praxion_evals.harness.families.family2_bc_adherence import (
    Family2BehavioralContractAdherence,
)
from praxion_evals.harness.judge_client import JudgeClient, select_judge_client
from praxion_evals.harness.orchestrator import Orchestrator
from praxion_evals.harness.report_writer import ReportWriter
from praxion_evals.harness.schemas import (
    CheckResult,
    Corpus,
    JudgeVerdict,
    Report,
)

__all__ = [
    "Family",
    "Family1PipelineOutcomeFidelity",
    "Family2BehavioralContractAdherence",
    "JudgeClient",
    "CorpusReader",
    "Orchestrator",
    "ReportWriter",
    "select_judge_client",
    "CheckResult",
    "Corpus",
    "JudgeVerdict",
    "Report",
    "run_eval",
]

# Default report output directory (relative to repo root / cwd).
_DEFAULT_OUTPUT_DIR = Path(".ai-state") / "praxion_eval_reports"


def run_eval(
    target: str = "main",
    output_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> Report:
    """Run both eval families against a target and return the written Report.

    Composition:
        CorpusReader(repo_root).resolve(target)
        → select_judge_client()
        → Orchestrator([Family1, Family2], output_dir).run(corpus, judge)
        → Report

    Args:
        target: Invocation target — path, worktree name, git ref, or 'main'.
        output_dir: Directory for the eval report and log.  Defaults to
                    ``.ai-state/praxion_eval_reports/`` relative to *repo_root*.
        repo_root: Repository root for corpus resolution and worktree expansion.
                   Defaults to ``Path.cwd()``.

    Returns:
        A populated Report with a non-empty ``report_path``.
    """
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    out_dir = Path(output_dir) if output_dir is not None else root / _DEFAULT_OUTPUT_DIR

    corpus = CorpusReader(root).resolve(target)
    judge = select_judge_client()

    families: list[Family] = [
        Family1PipelineOutcomeFidelity(),
        Family2BehavioralContractAdherence(),
    ]
    orchestrator = Orchestrator(families=families, output_dir=out_dir)
    return orchestrator.run(corpus, judge)
