"""Core data types for the Praxion eval harness.

All types are frozen dataclasses — the harness is purely read-only over its
corpus; no mutation is needed after construction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# JudgeClient output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeUsage:
    """Token usage for one live judge() call.

    ``None`` on JudgeVerdict/CheckResult when no usage is available: a
    cached verdict (no call was made, so nothing was spent) or a judge
    route that exposes no usage data (see AgentSdkJudgeClient).

    Fields:
        input_tokens: Non-cached input tokens billed for this call.
        output_tokens: Output tokens generated.
        cache_read_input_tokens: Input tokens served from a prompt cache
            (billed at a discount — see judge_client.estimate_cost_usd()).
        cache_creation_input_tokens: Input tokens written to a prompt cache
            (billed at a premium — see judge_client.estimate_cost_usd()).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class JudgeVerdict:
    """Parsed verdict returned by a JudgeClient.judge() call.

    Fields:
        verdict: Categorical outcome — PASS, WARN, or FAIL.
        findings: Ordered prose observations from the judge.
        score: 0–100 confidence / quality score.
        raw: The raw structured-output dict from the underlying SDK call.
        cached: True when this verdict was served from CachingJudgeClient's
            verdict cache instead of a live judge call. A cached verdict
            never carries usage (no call was made, so nothing was spent).
        usage: Token usage for this call, or None (see JudgeUsage).
    """

    verdict: Literal["PASS", "WARN", "FAIL"]
    findings: tuple[str, ...]
    score: int
    raw: dict  # type: ignore[type-arg]
    cached: bool = False
    usage: JudgeUsage | None = None


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
        usage: Token usage copied from the originating JudgeVerdict for an
            ``llm``-kind check; None for mechanical/skip checks and for any
            llm check whose verdict itself carried no usage.
    """

    check_name: str
    check_kind: CheckKind
    verdict: Literal["PASS", "WARN", "FAIL", "SKIP"]
    artifact_path: str
    findings: tuple[str, ...]
    score: int = -1
    usage: JudgeUsage | None = None


def sum_usage(check_results: Iterable[CheckResult]) -> JudgeUsage:
    """Sum token usage across every judged CheckResult.

    A CheckResult with no usage (mechanical check, cache hit, or a route
    that exposed none) contributes zero — it is skipped, not an error.
    """
    input_tokens = output_tokens = cache_read = cache_creation = 0
    for result in check_results:
        if result.usage is None:
            continue
        input_tokens += result.usage.input_tokens
        output_tokens += result.usage.output_tokens
        cache_read += result.usage.cache_read_input_tokens
        cache_creation += result.usage.cache_creation_input_tokens
    return JudgeUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )


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
        cost_usd_estimate: Rough LLM call cost estimated from summed usage
            (see judge_client.estimate_cost_usd()); 0.0 when no LLM calls
            were made; None when the judge model has no known price
            ("unpriced" — see judge_client's price table).
        report_path: Absolute path to the written report file, or empty string
            if the report has not been written yet.
        judge_calls: Total .judge() invocations across all families,
            including cache hits.
        judge_cache_hits: Subset of judge_calls served from
            CachingJudgeClient's verdict cache (no network call made).
        judge_workers: Configured worker-pool size for a judged loop
            (see judge_client.judge_workers()).
    """

    corpus: Corpus
    check_results: tuple[CheckResult, ...]
    cost_usd_estimate: float | None = 0.0
    report_path: str = ""
    judge_calls: int = 0
    judge_cache_hits: int = 0
    judge_workers: int = 0

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
    "JudgeUsage",
    "JudgeVerdict",
    "Report",
    "TaskArtifactVerdict",
    "sum_usage",
]
