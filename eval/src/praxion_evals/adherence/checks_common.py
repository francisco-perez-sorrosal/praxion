"""Checks every role is held to: C1 (durable output, no stray write), C2 (pointer return).

Each check is a :class:`~praxion_evals.adherence.model.MechanicalCheck`: a pure
function of the session's recorded evidence, never of the agent's account of
itself, plus the ``violation`` canary that builds evidence it must flag. A check
whose rule binds but which has no data yet for a role reports ``Withheld`` with
the reason; nothing is silently passed.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from praxion_evals.adherence.model import (
    Binding,
    Binds,
    CheckOutcome,
    Failed,
    MechanicalCheck,
    NotApplicable,
    Passed,
    RepoFacts,
    Role,
    RuleRef,
    SessionEvidence,
    TaskFacts,
    Withheld,
)
from praxion_evals.live.session import SessionEnvelope, ToolUse

# ---------------------------------------------------------------------------
# C1: the durable output is where the role's definition puts it, and nothing else is written
# ---------------------------------------------------------------------------

AI_WORK = ".ai-work"
# The tools whose input names the file they write, and the input key that names it;
# Bash writes show only in the repository.
WRITE_TOOLS: Mapping[str, str] = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


@dataclass(frozen=True)
class DurableOutput:
    """Where a role's own definition puts its output."""

    document: str  # a file name inside the task's slug directory
    other_locations: tuple[str, ...] = ()  # repo-relative files or directories it may also write


# Rows are read off each role's agent definition, one per role the eval covers so far.
DURABLE_OUTPUTS: Mapping[str, DurableOutput] = {
    "researcher": DurableOutput("RESEARCH_FINDINGS.md"),
    "verifier": DurableOutput("VERIFICATION_REPORT.md", (".ai-state/TECH_DEBT_LEDGER.md",)),
}


def durable_output(evidence: SessionEvidence) -> CheckOutcome:
    row = DURABLE_OUTPUTS.get(evidence.role)
    if row is None:
        return Withheld(f"no durable output location is recorded for {evidence.role} yet")
    expected = f"{slug_dir(evidence.slug)}/{row.document}"
    problems: list[str] = []
    if not evidence.repo.files.get(expected, "").strip():
        problems.append(f"{expected} was never written or is empty")
    allowed = (slug_dir(evidence.slug), *row.other_locations)
    stray = sorted(path for path in written_paths(evidence) if not _within_any(path, allowed))
    if stray:
        problems.append(f"wrote outside {slug_dir(evidence.slug)}: {', '.join(stray[:5])}")
    return Failed("; ".join(problems)) if problems else Passed()


def slug_dir(slug: str) -> str:
    return f"{AI_WORK}/{slug}"


def written_paths(evidence: SessionEvidence) -> frozenset[str]:
    """Every path the session changed: the repository's delta and the role's own Write/Edit calls."""
    cwd = evidence.envelope.init.cwd if evidence.envelope.init else None
    named = {
        _repo_relative(str(use.input[WRITE_TOOLS[use.name]]), cwd)
        for use in evidence.role_tool_uses
        if use.name in WRITE_TOOLS and WRITE_TOOLS[use.name] in use.input
    }
    return frozenset(evidence.repo.files) | evidence.repo.deleted | named


def _repo_relative(file_path: str, cwd: str | None) -> str:
    if cwd is None or not os.path.isabs(file_path):
        return os.path.normpath(file_path)
    root, target = os.path.realpath(cwd), os.path.realpath(file_path)
    return os.path.relpath(target, root) if target.startswith(root + os.sep) else target


def _within_any(path: str, locations: Sequence[str]) -> bool:
    return any(path == place or path.startswith(place + "/") for place in locations)


# ---------------------------------------------------------------------------
# C2: the role's own return is a short pointer ending in exactly one terminal marker
# ---------------------------------------------------------------------------

TERMINAL_MARKERS = ("[COMPLETE]", "[BLOCKED]", "[CONFLICT]", "[PARTIAL]")
_MARKER = re.compile(r"\[(?:COMPLETE|BLOCKED|CONFLICT|PARTIAL)\]")
DEFAULT_RETURN_LINES = 15
# A role whose own definition sets a tighter cap than the shared Return contract.
RETURN_LINE_CAPS: Mapping[str, int] = {"implementer": 5}


def pointer_return(evidence: SessionEvidence) -> CheckOutcome:
    if evidence.facts.forced_stop:
        return NotApplicable("a hard stop leaves no return the agent authored")
    if evidence.role_return is None:
        return Failed("no return was recorded for the spawn: the return was not elicited")
    lines = evidence.role_return.strip().splitlines()
    cap = RETURN_LINE_CAPS.get(evidence.role, DEFAULT_RETURN_LINES)
    problems = []
    if len(lines) > cap:
        problems.append(f"{len(lines)} lines against a cap of {cap}")
    final = lines[-1].strip() if lines else ""
    markers = _MARKER.findall(final)
    if len(markers) != 1 or not final.endswith(markers[0]):
        problems.append(f"the last line must end in exactly one terminal marker: {final[:80]!r}")
    return Failed("; ".join(problems)) if problems else Passed()


# ---------------------------------------------------------------------------
# The table and the canaries
# ---------------------------------------------------------------------------


def _always_binds(role: Role, task: object) -> Binding:
    del role, task
    return Binds()


def synthetic_evidence(
    role: Role,
    *,
    files: Mapping[str, str] | None = None,
    tool_uses: Sequence[ToolUse] = (),
    role_return: str | None = None,
    forced_stop: bool = False,
    slug: str = "canary-task",
) -> SessionEvidence:
    """Evidence built in memory: no process, no repository; the canaries' only source."""
    envelope = SessionEnvelope(
        init=None,
        tool_uses=tuple(tool_uses),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )
    return SessionEvidence(
        role=role,
        slug=slug,
        envelope=envelope,
        exit_code=0,
        timed_out=False,
        sandbox=Path("/canary/sandbox"),
        plugin_copy=Path("/canary/plugin-copy"),
        spawn_id="canary-spawn",
        role_tool_uses=tuple(tool_uses),
        role_return=role_return,
        repo=RepoFacts(files=files or {}, deleted=frozenset(), new_commits=(), stash_entries=()),
        facts=TaskFacts(
            forced_stop=forced_stop,
            judging=False,
            fetchable_page=False,
            planted_instruction=None,
            planted_effect=None,
            external_api_docs=None,
        ),
    )


def _stray_write_canary() -> SessionEvidence:
    row = DURABLE_OUTPUTS["researcher"]
    stray = ToolUse("canary-write", "Write", {"file_path": "notes/scratch.md"}, "canary-spawn")
    return synthetic_evidence(
        "researcher",
        files={
            f"{slug_dir('canary-task')}/{row.document}": "# Findings\n",
            "notes/scratch.md": "x",
        },
        tool_uses=[stray],
        role_return="Findings written.\n[COMPLETE]",
    )


def _unmarked_return_canary() -> SessionEvidence:
    return synthetic_evidence("researcher", role_return="Findings are in the report file.")


C1 = MechanicalCheck(
    name="C1",
    rule=RuleRef("rules/swe/agent-intermediate-documents.md", "Task Slug Convention"),
    common=True,
    binds=_always_binds,
    evaluate=durable_output,
    violation=_stray_write_canary,
)
C2 = MechanicalCheck(
    name="C2",
    rule=RuleRef("rules/swe/swe-agent-coordination-protocol.md", "Coordination Pipeline"),
    common=True,
    binds=_always_binds,
    evaluate=pointer_return,
    violation=_unmarked_return_canary,
)

COMMON_CHECKS: Mapping[str, MechanicalCheck] = {check.name: check for check in (C1, C2)}
