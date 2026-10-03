"""Driver for the log-health check family, run over one checkout.

The family is one command that takes `--repo-root <checkout>` and `--json` and
prints the envelope every multi-check sentinel family prints (`checks`,
`skipped`, `examined`, `findings`, `bound`, keyed by check id; each finding
carrying `check`, `severity`, `entity` and `message`), with information
reported as findings of severity `info` and warnings as severity `warn`, and
with a `judged_against` object naming the policy it judged. This driver maps
that envelope onto its value types: which check id is which of the six checks,
and how each check's figures are read from `examined`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class Check(Enum):
    ARCHIVE_COVERAGE = "archive coverage"
    ROTATION_STATE = "rotation state"
    MALFORMED_LINES = "malformed lines"
    HELPER_SHARE = "helper share"
    MODE_SOURCE = "recorded mode source"
    UNMERGED_WORKTREES = "unmerged worktree logs"


LOG_READING_CHECKS = tuple(c for c in Check if c is not Check.UNMERGED_WORKTREES)


# -- The family's command and check ids -------------------------------------------


def family_command() -> list[str]:
    """The family's command, relative to this repository, without `--repo-root`/`--json`."""
    return ["scripts/check_observation_log_health.py"]


def check_ids() -> dict[Check, str]:
    """The check id the family reports each of the six log-health checks under."""
    return {
        Check.ARCHIVE_COVERAGE: "P09",
        Check.ROTATION_STATE: "P10",
        Check.MALFORMED_LINES: "P11",
        Check.HELPER_SHARE: "P12",
        Check.MODE_SOURCE: "P13",
        Check.UNMERGED_WORKTREES: "P14",
    }


@dataclass(frozen=True)
class ArchiveCoverage:
    archive_count: int
    oldest: datetime
    newest: datetime


@dataclass(frozen=True)
class RotationState:
    active_bytes: int
    cap_bytes: int


@dataclass(frozen=True)
class HelperShare:
    helper_stops: int
    agent_stops: int
    share: float


@dataclass(frozen=True)
class JudgedAgainst:
    archive_count: int
    history_target: timedelta
    worktree_age_limit: timedelta


@dataclass(frozen=True)
class Unmerged:
    worktree: str
    rows: int
    newest: datetime


# -- Running the family and reading its envelope -----------------------------------


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    entity: str
    message: str
    raw: dict

    def text(self) -> str:
        return f"{self.entity} {self.message}"


@dataclass(frozen=True)
class LogHealthReport:
    envelope: dict
    ids: dict[Check, str]
    stderr: str

    def _findings(self, check: Check | None, severity: str) -> list[Finding]:
        wanted = None if check is None else self.ids[check]
        return [
            Finding(
                f["check"], f["severity"], str(f.get("entity", "")), str(f.get("message", "")), f
            )
            for f in self.envelope.get("findings", [])
            if f.get("severity") == severity and (wanted is None or f.get("check") == wanted)
        ]

    def warnings(self, check: Check | None = None) -> list[Finding]:
        """Warnings of one check, or of the whole family when `check` is None."""
        return self._findings(check, "warn")

    def information(self, check: Check) -> list[Finding]:
        return self._findings(check, "info")

    def skip_reason(self, check: Check) -> str | None:
        """The named skip state, words separated by spaces; None when the check ran."""
        skipped = self.envelope.get("skipped", {}).get(self.ids[check])
        if skipped is None:
            return None
        reason = skipped.get("reason") if isinstance(skipped, dict) else skipped
        return str(reason).replace("-", " ").replace("_", " ").strip()

    def examined(self, check: Check) -> object:
        return self.envelope.get("examined", {}).get(self.ids[check])

    def describe(self) -> str:
        return json.dumps(self.envelope, indent=1, default=str)[:4000] + self.stderr[-1000:]


def run_log_health(checkout: Path) -> LogHealthReport:
    ids = check_ids()
    command = family_command()
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_"))
    }
    result = subprocess.run(
        [sys.executable, *command, "--repo-root", str(checkout), "--json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"the log-health family printed no JSON (exit {result.returncode}): "
            f"{result.stdout[:500]!r} {result.stderr[-1500:]!r}"
        ) from exc
    return LogHealthReport(envelope, ids, result.stderr)


# -- Information readings ------------------------------------------------------------


def _figures(report: LogHealthReport, check: Check) -> dict:
    """What a check examined; a check that did not run fails the reading, naming why."""
    figures = report.examined(check)
    assert isinstance(figures, dict), (
        f"{report.ids[check]} ({check.value}) reported no figures "
        f"(skipped: {report.skip_reason(check)!r}):\n{report.describe()}"
    )
    return figures


def _stamp(figures: dict, key: str, check_id: str) -> datetime:
    stored = figures.get(key)
    assert stored is not None, f"{check_id} reported no {key!r} time: {figures}"
    return datetime.fromisoformat(stored)


def archive_coverage(report: LogHealthReport) -> ArchiveCoverage:
    figures = _figures(report, Check.ARCHIVE_COVERAGE)
    return ArchiveCoverage(
        figures["archive_count"],
        _stamp(figures, "oldest", "P09"),
        _stamp(figures, "newest", "P09"),
    )


def rotation_state(report: LogHealthReport) -> RotationState:
    figures = _figures(report, Check.ROTATION_STATE)
    return RotationState(figures["active_bytes"], figures["cap_bytes"])


def helper_share(report: LogHealthReport) -> HelperShare:
    figures = _figures(report, Check.HELPER_SHARE)
    assert figures["share"] is not None, f"P12 reported no share: {figures}"
    return HelperShare(figures["helper_stops"], figures["agent_stops"], figures["share"])


def mode_sources(report: LogHealthReport) -> dict[str | None, int]:
    """Sessions per recorded mode source; None counts sessions recorded before modes."""
    figures = _figures(report, Check.MODE_SOURCE)
    sources: dict[str | None, int] = dict(figures["by_source"])
    if figures["before_modes"]:
        sources[None] = figures["before_modes"]
    return sources


def in_flight_worktrees(report: LogHealthReport) -> list[str]:
    """Names of worktrees reported as in flight."""
    return sorted(_figures(report, Check.UNMERGED_WORKTREES)["in_flight"])


def judged_against(report: LogHealthReport) -> JudgedAgainst:
    judged = report.envelope.get("judged_against")
    assert isinstance(judged, dict), f"the family stated no judged_against:\n{report.describe()}"
    return JudgedAgainst(
        judged["archive_count"],
        timedelta(days=judged["history_target_days"]),
        timedelta(days=judged["worktree_age_limit_days"]),
    )


def malformed_detail(finding: Finding) -> tuple[int, tuple[int, ...]]:
    """(count, line numbers) a malformed-lines warning reports."""
    detail = finding.raw["detail"]
    return detail["count"], tuple(detail["lines"])


def unmerged_detail(finding: Finding) -> Unmerged:
    detail = finding.raw["detail"]
    return Unmerged(detail["worktree"], detail["rows"], datetime.fromisoformat(detail["newest"]))
