"""Core data types for the Praxion eval harness.

All types are frozen dataclasses — the harness is purely read-only over its
corpus; no mutation is needed after construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# JudgeClient output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeVerdict:
    """Parsed verdict returned by a JudgeClient.judge() call.

    Fields:
        verdict: Categorical outcome — PASS, WARN, or FAIL.
        findings: Ordered prose observations from the judge.
        score: 0–100 confidence / quality score.
        raw: The raw structured-output dict from the underlying SDK call.
    """

    verdict: Literal["PASS", "WARN", "FAIL"]
    findings: tuple[str, ...]
    score: int
    raw: dict  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Family output
# ---------------------------------------------------------------------------


CheckKind = Literal["mechanical", "llm", "skip"]


@dataclass(frozen=True)
class CheckResult:
    """Single check outcome produced by a Family.

    Fields:
        check_name: Machine-readable slug for the check.
        check_kind: Whether the check was mechanical, llm-judged, or skipped.
        verdict: Categorical outcome.
        artifact_path: Path (relative to corpus root) of the artifact judged.
        findings: Ordered prose observations.
        score: 0–100 score; -1 when not applicable (mechanical checks).
    """

    check_name: str
    check_kind: CheckKind
    verdict: Literal["PASS", "WARN", "FAIL", "SKIP"]
    artifact_path: str
    findings: tuple[str, ...]
    score: int = -1


# ---------------------------------------------------------------------------
# In-flight task artifact verdict
# ---------------------------------------------------------------------------


ArtifactVerdict = Literal["present", "missing", "stale"]


@dataclass(frozen=True)
class TaskArtifactVerdict:
    """One artifact-manifest verdict for an in-flight pipeline.

    Populated by the corpus reader when a task_slug is supplied. Family 1
    translates each verdict into a CheckResult.

    Fields:
        path: Path (relative to corpus root) of the expected artifact.
        verdict: ``present`` if the file exists, ``missing`` if not,
            ``stale`` if recency was checked and the mtime predates the
            pipeline-start timestamp.
        required: When True, ``missing`` flips the overall check to FAIL.
        description: Human-readable explanation of the artifact's purpose.
        detail: Optional extra context (e.g., the mtime that caused stale).
    """

    path: str
    verdict: ArtifactVerdict
    required: bool
    description: str = ""
    detail: str = ""


# ---------------------------------------------------------------------------
# CorpusReader output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Corpus:
    """A resolved, immutable snapshot of the target's artifact set.

    Fields:
        target_kind: How the target was resolved — filesystem path, worktree
            expansion, or git ref.
        target_label: Human-readable description for report headers.
        decisions: Pairs of (relative_path, file_content) for ADR files.
        specs: Pairs of (relative_path, file_content) for archived SPEC files.
        verification_reports: Pairs of (relative_path, file_content) for
            VERIFICATION_REPORT.md files found in .ai-work/ directories.
        task_slug: When the run is scoped to an in-flight pipeline, the
            ``.ai-work/<task_slug>/`` directory whose artifact manifest was
            checked. ``None`` for post-merge runs.
        pipeline_tier: Pipeline tier that determined the expected manifest —
            ``lightweight`` / ``standard`` / ``full``. ``None`` when
            ``task_slug`` is also ``None``.
        task_artifacts: Per-artifact verdicts from the manifest scan. Empty
            tuple when ``task_slug`` is ``None``.
    """

    target_kind: Literal["path", "worktree", "ref"]
    target_label: str
    decisions: tuple[tuple[str, str], ...]
    specs: tuple[tuple[str, str], ...]
    verification_reports: tuple[tuple[str, str], ...]
    task_slug: str | None = None
    pipeline_tier: str | None = None
    task_artifacts: tuple[TaskArtifactVerdict, ...] = ()


# ---------------------------------------------------------------------------
# Harness orchestrator output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    """Aggregated results from a full eval run.

    Fields:
        corpus: The resolved corpus the families ran against.
        check_results: All CheckResult objects from all families, in order.
        cost_usd_estimate: Rough LLM call cost; 0.0 when no LLM calls were made.
        report_path: Absolute path to the written report file, or empty string
            if the report has not been written yet.
    """

    corpus: Corpus
    check_results: tuple[CheckResult, ...]
    cost_usd_estimate: float = 0.0
    report_path: str = ""

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.check_results if r.verdict == "PASS")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.check_results if r.verdict == "WARN")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.check_results if r.verdict == "FAIL")

    @property
    def skip_count(self) -> int:
        return sum(1 for r in self.check_results if r.verdict == "SKIP")


# ---------------------------------------------------------------------------
# Utility: empty Corpus sentinel for when nothing was resolved
# ---------------------------------------------------------------------------

EMPTY_CORPUS = Corpus(
    target_kind="path",
    target_label="(empty)",
    decisions=(),
    specs=(),
    verification_reports=(),
)


__all__ = [
    "ArtifactVerdict",
    "CheckKind",
    "CheckResult",
    "Corpus",
    "EMPTY_CORPUS",
    "JudgeVerdict",
    "Report",
    "TaskArtifactVerdict",
]
