"""Family ABC and the global family registry.

Each concrete Family subclass encapsulates a coherent set of related checks.
New families are added by subclassing Family and registering the class here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import CheckResult, Corpus


class Family(ABC):
    """A family of related checks against a corpus.

    Each family declares its id, human-readable name, and the corpus subset
    it consumes (which subdirectories of the resolved target it reads).
    Concrete subclasses implement ``run``.

    Class attributes:
        id: Machine-readable slug — e.g. ``"family1-pipeline-fidelity"``.
        name: Human-readable title shown in reports.
        corpus_paths: Subdirectory paths this family reads from the corpus,
                      relative to the corpus root — e.g.
                      ``(".ai-state/specs/", ".ai-state/decisions/")``.
    """

    id: str
    name: str
    corpus_paths: tuple[str, ...]

    @abstractmethod
    def run(self, corpus: Corpus, judge: JudgeClient) -> list[CheckResult]:
        """Execute all checks in this family. Read-only over the corpus.

        Mechanical checks call no method on *judge*.
        LLM-judged checks call ``judge.judge(rubric, artifact, schema)`` and
        translate the verdict into a CheckResult.

        Each CheckResult names the check, the artifact(s) it judged, the
        verdict (PASS | WARN | FAIL | SKIP), and prose findings.

        Args:
            corpus: Resolved, immutable snapshot of the target's artifacts.
            judge: JudgeClient to use for LLM-backed checks.

        Returns:
            Ordered list of CheckResult objects, one per check executed.
        """


# ---------------------------------------------------------------------------
# Global registry — populated by concrete family modules
# ---------------------------------------------------------------------------

FAMILY_REGISTRY: list[type[Family]] = []
