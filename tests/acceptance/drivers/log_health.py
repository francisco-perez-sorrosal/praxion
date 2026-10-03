"""Driver for the log-health check family, run over one checkout.

Assumed boundary, unbound until a binding step names it: the family is one
command that takes `--repo-root <checkout>` and `--json` and prints the
envelope every multi-check sentinel family prints today (`checks`, `skipped`,
`examined`, `findings`, `bound`, keyed by check id; each finding carrying
`check`, `severity`, `entity` and `message`), with information reported as
findings of severity `info` and warnings as severity `warn`. Unbound too:
which check id is which of the six checks, and how each check's information
(the figures the specification says it reports) is read from its envelope.

The envelope parsing that only relies on today's family shape is bound here.
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


# -- The assumed boundary ----------------------------------------------------------


def family_command() -> list[str]:
    """The family's command, relative to this repository, without `--repo-root`/`--json`."""
    raise NotImplementedError(
        "unbound: the log-health family's command (taking --repo-root and --json and "
        "printing the multi-check family envelope) has not been bound to this driver yet"
    )


def check_ids() -> dict[Check, str]:
    """The check id the family reports each of the six log-health checks under."""
    raise NotImplementedError(
        "unbound: which check id the log-health family reports each of its six checks "
        "under has not been bound to this driver yet"
    )


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


def _unbound(what: str) -> NotImplementedError:
    return NotImplementedError(
        f"unbound: reading {what} from the log-health family's envelope has not been "
        "bound to this driver yet"
    )


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


# -- Information readings (assumed boundary) ------------------------------------------


def archive_coverage(report: LogHealthReport) -> ArchiveCoverage:
    raise _unbound("the retained span and archive count")


def rotation_state(report: LogHealthReport) -> RotationState:
    raise _unbound("the active log's size against its cap")


def helper_share(report: LogHealthReport) -> HelperShare:
    raise _unbound("the helper-stop and agent-stop counts and the helpers' share")


def mode_sources(report: LogHealthReport) -> dict[str | None, int]:
    """Sessions per recorded mode source; None counts sessions recorded before modes."""
    raise _unbound("the count of sessions per recorded mode source")


def in_flight_worktrees(report: LogHealthReport) -> list[str]:
    """Names of worktrees reported as in flight."""
    raise _unbound("the worktrees reported as in flight")


def judged_against(report: LogHealthReport) -> JudgedAgainst:
    raise _unbound("the retention policy and worktree age limit the family judged against")


def malformed_detail(finding: Finding) -> tuple[int, tuple[int, ...]]:
    """(count, line numbers) a malformed-lines warning reports."""
    raise _unbound("the malformed-line count and line numbers of a warning")


def unmerged_detail(finding: Finding) -> Unmerged:
    raise _unbound("the worktree, unmerged-row count and newest-row time of a warning")
