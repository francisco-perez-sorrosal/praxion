"""Driver for reports a session leaves behind, graded on the write-early check and C5.

The verifier and the sentinel open their reports early, marked `[PARTIAL]`, and take the
marker off last. A scenario builds one such session's recorded evidence from four facts:
how the report opened (which tool call first wrote it, with which tool, under which
title), the text it ends with, and how the session ended.

Bound here, because the specification or the base commit fixes them:

- a session's evidence and its grading (`adherence_eval.grade`, `session_envelope`,
  `scratch_repo`): the report's opening is the role's first recorded write of it, and the
  text it ends with is the file the scratch repository holds;
- how a session ended, as its stream holds it (`adherence_scoring`): a role the harness
  stopped at its turn cap carries the harness's note ahead of its partial return; a role
  that ended on its own wrote a return ending in a terminal marker; a stream with neither
  a note nor a return cannot tell; a task with no lowered turn cap is not a forced stop;
- each role's write-early check, found in its catalog as the one role clause whose name
  states the `[PARTIAL]` opening; and C5;
- where each report lives: `.ai-work/<slug>/VERIFICATION_REPORT.md`, and
  `.ai-state/sentinel_reports/SENTINEL_REPORT_<timestamp>.md`.

Unbound, raising until a driver-binding step binds it: `canaries`, the violation evidence
the catalog pairs with a check, described in the consumer's terms of `Canary`.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import (
    SLUG,
    GradedSession,
    Outcome,
    SessionEvidence,
    edit,
    grade,
    read,
    scratch_repo,
    session_envelope,
    session_places,
    write,
)
from tests.acceptance.drivers.adherence_scoring import TURN_LIMIT_NOTE

Ending = Literal["stopped at cap", "ended on its own", "unknown", "no lowered cap"]
OpeningTool = Literal["Write", "Edit"]

REPORT_PATHS = {
    "verifier": f".ai-work/{SLUG}/VERIFICATION_REPORT.md",
    "sentinel": ".ai-state/sentinel_reports/SENTINEL_REPORT_2026-10-31_09-00-00.md",
    "researcher": f".ai-work/{SLUG}/RESEARCH_FINDINGS.md",
}
TITLES = {
    "verifier": "# Verification Report",
    "sentinel": "# Sentinel Report",
    "researcher": "# Research Findings: idempotency keys",
}
PARTIAL = " [PARTIAL]"
WRITE_WINDOW = 3  # the verifier's definition: the report is written within its first three calls
VERDICTS = ("PASS", "PASS WITH FINDINGS", "FAIL")

_RETURNS: dict[Ending, str | None] = {
    "stopped at cap": "This is my last turn. I am writing the final report now.",
    "ended on its own": "The report is written.\n[COMPLETE]",
    "unknown": None,
    "no lowered cap": "The report is written.\n[COMPLETE]",
}


def body(
    *,
    completed: str = "all",
    sections: dict[str, str] | None = None,
    verdict: str | None = "PASS",
) -> str:
    """A report's body under its title: the progress line, its sections, then its verdict.

    `verdict=None` leaves the `## Verdict` section out altogether.
    """
    filled = sections or {
        "Summary": "Every criterion was checked against the code.",
        "Acceptance Criteria": "- the export writes one row per entry: PASS",
        "Findings": "None.",
    }
    text = f"\n**Completed phases**: {completed}\n"
    for heading, content in filled.items():
        text += f"\n## {heading}\n{content}\n"
    if verdict is not None:
        text += f"\n## Verdict\n{verdict}\n"
    return text


SKELETON = body(
    completed="none",
    sections={"Summary": "[pending]", "Acceptance Criteria": "[pending]", "Findings": "[pending]"},
    verdict="[pending]",
)
FINISHED = body()


def title(role: str, *, marked: bool) -> str:
    return TITLES[role] + (PARTIAL if marked else "")


@dataclass(frozen=True)
class Report:
    """How a role's report was opened and what it ends as."""

    role: str
    opened_marked: bool = True
    opened_at_call: int = 1  # the tool call, counted from one, that first touched the report
    opened_with: OpeningTool = "Write"
    final_text: str | None = None  # None: the session never changed the opening's text

    @property
    def path(self) -> str:
        return REPORT_PATHS[self.role]

    @property
    def opening_text(self) -> str:
        return title(self.role, marked=self.opened_marked) + SKELETON


def report_session(workspace: Path, report: Report, ending: Ending) -> SessionEvidence:
    """The recorded evidence of a session that opened `report` and ended as `ending` says."""
    final = report.opening_text if report.final_text is None else report.final_text
    files = {report.path: report.opening_text} if report.opened_with == "Edit" else {}
    repo = scratch_repo(workspace, files)
    places = session_places(workspace)
    path = repo.put(report.path, final)
    actions = [read(repo.path("README.md"))] * (report.opened_at_call - 1)
    if report.opened_with == "Write":
        actions.append(write(path, report.opening_text))
    else:
        opening_title = title(report.role, marked=report.opened_marked)
        actions.append(edit(path, opening_title, opening_title))
    if final != report.opening_text:
        actions.append(write(path, final))
    envelope = session_envelope(
        role=report.role,
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=actions,
        return_text=_RETURNS[ending],
        spawn_result_note=TURN_LIMIT_NOTE if ending == "stopped at cap" else "",
    )
    forced_stop = ending != "no lowered cap"
    return SessionEvidence(report.role, repo, envelope, places, forced_stop=forced_stop)


@cache
def write_early_check(role: str) -> str:
    """The role clause holding the role to its `[PARTIAL]` opening and its unmarked ending."""
    named = [
        c.name
        for c in adherence_eval.check_catalog(role)
        if not c.common and c.name.startswith(f"{role}:") and "[PARTIAL]" in c.name
    ]
    assert len(named) == 1, f"the {role}'s catalog has {len(named)} write-early clauses: {named}"
    return named[0]


def graded(report: Report, ending: Ending, check: str) -> Outcome:
    with tempfile.TemporaryDirectory(prefix="capped-report-") as scratch:
        session: GradedSession = grade(report_session(Path(scratch), report, ending), [check])
    return session.outcome(check)


def write_early(report: Report, ending: Ending) -> Outcome:
    return graded(report, ending, write_early_check(report.role))


def c5(report: Report, ending: Ending = "stopped at cap") -> Outcome:
    return graded(report, ending, "C5")


# -- A check's canaries (unbound) ----------------------------------------------------------------


@dataclass(frozen=True)
class Canary:
    """One violation the catalog pairs with a check, and the outcome its check gives it.

    `ending` is how the canary's session ended; `opening` how its report opened: "in time"
    (a write within the window, marked `[PARTIAL]`), "late", "unmarked" or "edit";
    `final_title_marked` whether the title the report ends with still carries `[PARTIAL]`;
    `pending_sections` the headings still reading `[pending]`; `verdict` what `## Verdict`
    names (None: no verdict section).
    """

    ending: Ending
    opening: Literal["in time", "late", "unmarked", "edit"] | None
    final_title_marked: bool | None
    pending_sections: tuple[str, ...]
    verdict: str | None
    outcome: str  # "passed", "failed", "withheld", "not applicable" or "errored"


def canaries(role: str, check: str) -> list[Canary]:
    raise UnboundDriverError(
        "unbound: the violation evidence the catalog pairs with a check, each graded by that"
        " check and described by how its session ended and how its report opened and ends,"
        " is not bound yet"
    )


class UnboundDriverError(NotImplementedError):
    """Raised by a driver hook not yet bound to the designed surface."""
