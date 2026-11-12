"""What the catalog tests share to grade a role's synthetic session against its checks."""

from __future__ import annotations

from dataclasses import replace

from praxion_evals.adherence import grade
from praxion_evals.adherence.checks_common import synthetic_evidence
from praxion_evals.adherence.model import Measured, TaskFacts
from praxion_evals.live.session import InitInfo, ResultInfo, ToolUse

TASK_DIR = ".ai-work/grade-task"


def gradable(role: str, **kwargs):
    """Synthetic evidence whose stream reads as a finished session, so the grader scores it."""
    evidence = synthetic_evidence(role, **kwargs)
    plugin = {"name": "praxion", "path": str(evidence.plugin_copy), "source": "praxion@inline"}
    init = InitInfo(None, (plugin,), (), None, None, None)
    result = ResultInfo("done", None, False, "success", None, None)
    envelope = replace(evidence.envelope, init=init, final_result=result, result_count=1)
    return replace(evidence, envelope=envelope)


def read_of(path: str) -> ToolUse:
    return ToolUse(f"toolu_read_{path}", "Read", {"file_path": path}, "canary-spawn")


def graded_outcome(role: str, name: str, mode: str | None, *, forced_stop: bool = False, **kwargs):
    facts = TaskFacts(forced_stop, False, False, None, None, None, mode=mode)
    evidence = gradable(role, slug="grade-task", facts=facts, **kwargs)

    status = grade.grade(evidence, [name], judge=None, setup=None)

    assert isinstance(status, Measured)
    return status.outcomes[name]
