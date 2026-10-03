#!/usr/bin/env python3
"""P09-P14: the observation log's health -- archives, rotation, integrity, provenance.

Six checks over the log of the checkout the script runs in, and over the logs
of the repository's linked worktrees. Every read goes through the log's owner
(`hooks/_observation_log/`): the segment listing, the raw read, the row
identity and the row time all come from there, so a later change to retention
reaches this check by changing one place. Information and warnings are kept
apart: an `info` finding states a figure, a `warn` finding names a defect.

* **P09 archive coverage.** The retained span (oldest and newest row time) and
  the archive count as information. Warns for a missing position between two
  present archives (a rotation was left pending; the next one closes the gap,
  so it is not by itself a lost archive), for each archive past the policy's
  count, and once when the archive count has reached the policy's count while
  the retained span is shorter than the policy's history target.
  Golden bad-case: archives at positions 1 and 3 with nothing at 2.
* **P10 rotation state.** The active log's size against the cap as information.
  Warns when the log, less its last row, is still at or past the cap: the
  writer rotates before every append, so one append past the cap is normal and
  more than one means rotation stopped firing. Golden bad-case: an active log
  a megabyte past the cap.
* **P11 segment integrity.** Warns per segment with lines that are not a
  single JSON object (count and line numbers) and per segment that cannot be
  read; well-formed rows are still judged by every other check.
  Golden bad-case: a JSON array on line 5 of the active log.
* **P12 helper share.** Information only: harness helper stops (older stop
  rows that self-report as helper calls included), real agent stops, and the
  share helpers form of all stops (`null` with no stops). Never a warning.
  Golden bad-case: none by design; the canary proves it is never a warning.
* **P13 recorded mode source.** Information: sessions per recorded
  `log_mode_source` and the count recorded before modes existed. Warns per
  session recorded with `invalid-setting` (a mistyped setting that fell back
  to full recording) and per session recorded with `legacy-disable` (a
  setting under which nothing is recorded, so the row contradicts the mode
  rules). Golden bad-case: a session start with `invalid-setting`.
* **P14 unmerged worktree logs.** Warns per linked worktree whose newest row
  is older than `WORKTREE_AGE_LIMIT` and which holds rows with no equal row in
  the main checkout's log; a worktree inside the limit is reported as in
  flight, as information. Golden bad-case: a worktree log last written three
  weeks ago whose rows the main log lacks.

P09 to P13 skip together, with exactly one of three named states, never as a
clean pass: `substrate-absent` (no segment exists), `reader-unreachable` (every
segment that exists failed to read) or `substrate-carries-no-history` (zero
rows and zero malformed lines). P14 does not depend on the main log -- an
absent main log is an empty set of identities -- and skips as
`reader-unreachable` only when the checkouts cannot be listed. When only some
segments are unreadable, P11 warns for each and the rest are judged.

Consumers of the output: the sentinel report's Pipeline Discipline section
reads each check's verdict; P12's share is the figure a published attribution
claim over stops must be checked against; P14's warning is the cue to run
`scripts/merge_worktree_log.py --worktree <path>` before the worktree is
removed; P09's span warning is the cue to revisit the retention policy.

Declared limits: P14 compares rows by their identity as stored, so a worktree
removed before this ran took its log with it and cannot be reported; a segment
of the main log this could not read is named in P14's `unreadable` figure, and
rows only that segment held read as unmerged.

Invocation:

    check_observation_log_health.py                  # human-readable summary
    check_observation_log_health.py --json           # machine-readable envelope
    check_observation_log_health.py --check          # exit 1 when any warning
    check_observation_log_health.py --repo-root DIR  # operate on another checkout

Exit code: 0 by default (advisory). With `--check`, 1 when at least one `warn`
finding exists; a skip is not a warning. 2 when the resolved root is a
plugin-cache path.

Invoked by the sentinel's P dimension (`--json`); also runnable standalone.
Golden bad-cases and canaries: `scripts/test_check_observation_log_health.py`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from _observation_log import checkouts, reader, retention  # noqa: E402 (after sys.path injection)
from _repo_root import is_plugin_cache_path, resolve_repo_root  # noqa: E402
from _script_cli import configure_logging  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent

CHECK_IDS: tuple[str, ...] = ("P09", "P10", "P11", "P12", "P13", "P14")
SEVERITY = "warn"

AI_STATE_REL = ".ai-state"

# A worktree whose newest row is older than this is no longer a pipeline in flight.
WORKTREE_AGE_LIMIT = timedelta(days=14)

# Line numbers a malformed-lines finding carries; its count is always the true one.
MAX_LINE_NUMBERS_LISTED = 100

_HELPER_STOP_EVENT = "helper_stop"
_AGENT_STOP_EVENT = "agent_stop"
_SESSION_START_EVENT = "session_start"
_LEGACY_DISABLE_SOURCE = "legacy-disable"
_INVALID_SETTING_SOURCE = "invalid-setting"

SKIP_ABSENT = "substrate-absent"
SKIP_UNREACHABLE = "reader-unreachable"
SKIP_NO_HISTORY = "substrate-carries-no-history"

_BOUNDS = {
    "P09": (
        "P09 clean means the archive positions are contiguous and within the policy's count, "
        "not that every archived row is intact (P11) or that the history target is met."
    ),
    "P10": (
        "P10 clean means the active log is within one append of the size cap, "
        "not that rotation has run recently."
    ),
    "P11": ("P11 clean means every readable line is one JSON object, not that every row is true."),
    "P12": "P12 is information only: it reports the helper share and never judges it.",
    "P13": (
        "P13 clean means no session was recorded under an invalid setting or the legacy "
        "kill switch, not that every session left a row."
    ),
    "P14": (
        "P14 clean means no worktree log past the age limit holds rows missing from the main "
        "log, not that a worktree already removed was merged first."
    ),
}

logger = logging.getLogger("check_observation_log_health")


# -- Value types -----------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """What the log is judged against: the owner's retention policy and this check's age limit."""

    archive_count: int
    history_target: timedelta
    size_cap_bytes: int
    worktree_age_limit: timedelta

    def judged_against(self) -> dict:
        return {
            "archive_count": self.archive_count,
            "history_target_days": _days(self.history_target),
            "size_cap_bytes": self.size_cap_bytes,
            "worktree_age_limit_days": _days(self.worktree_age_limit),
        }


@dataclass(frozen=True)
class Stamped:
    """A row time with the timestamp string the row stored it as."""

    time: datetime
    stamp: str


@dataclass(frozen=True)
class SegmentFacts:
    """Everything the checks need from one segment; the rows themselves are not kept."""

    path: Path
    error: str | None
    malformed_lines: tuple[int, ...]
    rows: int
    oldest: Stamped | None
    newest: Stamped | None
    last_row_bytes: int
    helper_stops: int
    agent_stops: int
    session_starts: tuple[tuple[str | None, str], ...]  # (log_mode_source, session_id)


@dataclass(frozen=True)
class LogView:
    """One checkout's log as gathered: where it is, what it holds, how big the active file is."""

    active: Path
    listing: reader.SegmentListing
    facts: tuple[SegmentFacts, ...]
    active_bytes: int

    @property
    def archives(self) -> tuple[Path, ...]:
        return tuple(path for path in self.listing.segments if path != self.active)

    @property
    def oldest(self) -> Stamped | None:
        return min((f.oldest for f in self.facts if f.oldest), key=_time, default=None)

    @property
    def newest(self) -> Stamped | None:
        return max((f.newest for f in self.facts if f.newest), key=_time, default=None)


@dataclass(frozen=True)
class Outcome:
    """One check's result: what it examined and found, or why it did not run."""

    examined: dict | None = None
    findings: tuple[dict, ...] = ()
    skipped: dict | None = None


def _time(stamped: Stamped) -> datetime:
    return stamped.time


def _days(span: timedelta) -> int | float:
    days = span / timedelta(days=1)
    return int(days) if days == int(days) else days


def _finding(check: str, severity: str, entity: object, message: str, **detail: object) -> dict:
    finding = {"check": check, "severity": severity, "entity": str(entity), "message": message}
    if detail:
        finding["detail"] = detail
    return finding


# -- Gathering (the effects) -----------------------------------------------------


def current_policy() -> Policy:
    """The owner's policy as it stands now, read at call time."""
    return Policy(
        retention.ARCHIVE_COUNT,
        retention.HISTORY_TARGET,
        retention.SIZE_CAP_BYTES,
        WORKTREE_AGE_LIMIT,
    )


def read_log(state_dir: Path) -> LogView:
    """Every segment of the log in `state_dir`, reduced to facts, plus the active file's size."""
    listing = reader.segment_listing(state_dir, archives=True)
    active = reader.log_path(state_dir)
    facts = tuple(summarize(reader.read_raw_segment(path)) for path in listing.segments)
    return LogView(active, listing, facts, _file_size(active))


def _file_size(path: Path) -> int:
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def summarize(read: reader.RawSegmentRead) -> SegmentFacts:
    """Reduce one raw segment read to the facts the checks judge."""
    oldest = newest = None
    helpers = agents = 0
    starts: list[tuple[str | None, str]] = []
    for _text, raw in read.entries:
        moment = reader.row_time(raw)
        if moment != reader.UNTIMED:
            stamped = Stamped(moment, raw["timestamp"])
            oldest = stamped if oldest is None or moment < oldest.time else oldest
            newest = stamped if newest is None or moment > newest.time else newest
        event = reader.upcast(raw).get("event_type")
        if event == _HELPER_STOP_EVENT:
            helpers += 1
        elif event == _AGENT_STOP_EVENT:
            agents += 1
        elif event == _SESSION_START_EVENT:
            source = raw.get("log_mode_source")
            starts.append(
                (None if source is None else str(source), str(raw.get("session_id") or ""))
            )
    last_text = read.entries[-1][0] if read.entries else ""
    return SegmentFacts(
        path=read.path,
        error=read.error,
        malformed_lines=tuple(read.malformed_lines),
        rows=len(read.entries),
        oldest=oldest,
        newest=newest,
        last_row_bytes=len(last_text.encode("utf-8")) + 1 if last_text else 0,
        helper_stops=helpers,
        agent_stops=agents,
        session_starts=tuple(starts),
    )


# -- Skips: the three named substrate states -----------------------------------------


def log_skip(view: LogView) -> dict | None:
    """Why the log-reading checks cannot run, or `None` when they can."""
    if not view.listing.segments:
        return {"reason": SKIP_ABSENT, "path": str(view.active)}
    if all(f.error is not None for f in view.facts):
        return {"reason": SKIP_UNREACHABLE, "path": str(view.active), "detail": view.facts[0].error}
    if not any(f.rows or f.malformed_lines for f in view.facts):
        return {"reason": SKIP_NO_HISTORY, "path": str(view.active)}
    return None


# -- P09: archive coverage ----------------------------------------------------------


def check_archive_coverage(view: LogView, policy: Policy) -> Outcome:
    oldest, newest = view.oldest, view.newest
    surplus = tuple(p for p in view.archives if _position(p) > policy.archive_count)
    findings = [
        _finding("P09", "warn", path, _missing_message(path)) for path in view.listing.missing
    ]
    findings += [
        _finding(
            "P09",
            "warn",
            path,
            f"{path.name} is position {_position(path)}, past the policy's "
            f"{policy.archive_count} archives: retention is not being enforced",
        )
        for path in surplus
    ]
    if _span_outgrown(view, policy):
        findings.append(
            _finding(
                "P09",
                "warn",
                view.active,
                f"{len(view.archives)} archives reached the policy's count of "
                f"{policy.archive_count} but cover {_days(newest.time - oldest.time)} days, "
                f"short of the {_days(policy.history_target)}-day history target: "
                "the volume has outgrown the policy",
            )
        )
    findings.append(_finding("P09", "info", view.active, _coverage_summary(view, oldest, newest)))
    examined = {
        "archive_count": len(view.archives),
        "oldest": oldest.stamp if oldest else None,
        "newest": newest.stamp if newest else None,
        "missing": [str(p) for p in view.listing.missing],
        "surplus": [str(p) for p in surplus],
    }
    return Outcome(examined, tuple(findings))


def _position(archive: Path) -> int:
    position = retention.archive_position(archive, reader.LOG_FILENAME)
    assert position is not None, f"{archive} is not an archive of the log"
    return position


def _missing_message(path: Path) -> str:
    return (
        f"archive {path.name} is missing between two present archives: a rotation was left "
        "pending, and the next rotation closes the gap by shifting (nothing is lost by the "
        "gap alone)"
    )


def _span_outgrown(view: LogView, policy: Policy) -> bool:
    if len(view.archives) < policy.archive_count or not (view.oldest and view.newest):
        return False
    return view.newest.time - view.oldest.time < policy.history_target


def _coverage_summary(view: LogView, oldest: Stamped | None, newest: Stamped | None) -> str:
    span = f"rows from {oldest.stamp} to {newest.stamp}" if oldest and newest else "no timed row"
    return f"{len(view.archives)} archive(s) beside the active log, {span}"


# -- P10: rotation state ------------------------------------------------------------


def check_rotation_state(view: LogView, policy: Policy) -> Outcome:
    active_facts = next((f for f in view.facts if f.path == view.active), None)
    last_row_bytes = active_facts.last_row_bytes if active_facts else 0
    size, cap = view.active_bytes, policy.size_cap_bytes
    findings = []
    if size - last_row_bytes >= cap:
        findings.append(
            _finding(
                "P10",
                "warn",
                view.active,
                f"the active log is {size} bytes against a {cap}-byte cap, past it by more than "
                "one append: rotation has stopped firing",
            )
        )
    findings.append(
        _finding("P10", "info", view.active, f"the active log is {size} of {cap} bytes")
    )
    return Outcome({"active_bytes": size, "cap_bytes": cap}, tuple(findings))


# -- P11: segment integrity ---------------------------------------------------------


def check_segment_integrity(view: LogView) -> Outcome:
    findings: list[dict] = []
    for facts in view.facts:
        if facts.error is not None:
            findings.append(
                _finding(
                    "P11",
                    "warn",
                    facts.path,
                    f"{facts.path.name} could not be read ({facts.error}); its rows are not judged",
                    segment=str(facts.path),
                    error=facts.error,
                )
            )
        if facts.malformed_lines:
            findings.append(_malformed_finding(facts))
    malformed = sum(len(f.malformed_lines) for f in view.facts)
    unreadable = [str(f.path) for f in view.facts if f.error is not None]
    findings.append(
        _finding(
            "P11",
            "info",
            view.active,
            f"{len(view.facts)} segment(s) read, {malformed} malformed line(s), "
            f"{len(unreadable)} unreadable",
        )
    )
    examined = {"segments": len(view.facts), "malformed_lines": malformed, "unreadable": unreadable}
    return Outcome(examined, tuple(findings))


def _malformed_finding(facts: SegmentFacts) -> dict:
    lines = facts.malformed_lines[:MAX_LINE_NUMBERS_LISTED]
    shown = "" if len(lines) == len(facts.malformed_lines) else f" (first {len(lines)} listed)"
    return _finding(
        "P11",
        "warn",
        facts.path,
        f"{facts.path.name} holds {len(facts.malformed_lines)} line(s) that are not one JSON "
        f"object, at line(s) {', '.join(map(str, lines))}{shown}",
        segment=str(facts.path),
        count=len(facts.malformed_lines),
        lines=list(lines),
    )


# -- P12: helper share --------------------------------------------------------------


def check_helper_share(view: LogView) -> Outcome:
    helpers = sum(f.helper_stops for f in view.facts)
    agents = sum(f.agent_stops for f in view.facts)
    share = round(helpers / (helpers + agents), 3) if helpers + agents else None
    shown = "no stops recorded" if share is None else f"{share:.1%} of all stops"
    message = f"{helpers} helper stop(s), {agents} agent stop(s): {shown}"
    examined = {"helper_stops": helpers, "agent_stops": agents, "share": share}
    return Outcome(examined, (_finding("P12", "info", view.active, message),))


# -- P13: recorded mode source ------------------------------------------------------


def check_mode_source(view: LogView) -> Outcome:
    sessions = {start for f in view.facts for start in f.session_starts}
    by_source: dict[str, int] = {}
    before_modes = 0
    for source, _session in sessions:
        if source is None:
            before_modes += 1
        else:
            by_source[source] = by_source.get(source, 0) + 1
    findings = [
        _finding("P13", "warn", session or "(no session id)", _mode_warning(source, session))
        for source, session in sorted(sessions, key=_session_order)
        if source in (_INVALID_SETTING_SOURCE, _LEGACY_DISABLE_SOURCE)
    ]
    summary = ", ".join(f"{n} {source}" for source, n in sorted(by_source.items()))
    findings.append(
        _finding(
            "P13",
            "info",
            view.active,
            f"{len(sessions)} session(s): {summary or 'none with a recorded source'}; "
            f"{before_modes} recorded before modes existed",
        )
    )
    examined = {"sessions": len(sessions), "by_source": by_source, "before_modes": before_modes}
    return Outcome(examined, tuple(findings))


def _session_order(start: tuple[str | None, str]) -> tuple[str, str]:
    return (start[0] or "", start[1])


def _mode_warning(source: str | None, session: str) -> str:
    named = session or "a session with no id"
    if source == _INVALID_SETTING_SOURCE:
        return (
            f"{named} was recorded under an invalid mode setting and fell back to full "
            "recording: check the setting for a typo"
        )
    return (
        f"{named} was recorded under the legacy kill switch, a setting under which "
        "nothing is recorded: the row contradicts the mode rules"
    )


# -- P14: unmerged worktree logs ----------------------------------------------------


def check_unmerged_worktrees(repo_root: Path, policy: Policy, now: datetime) -> Outcome:
    listing = checkouts.repository_checkouts(repo_root)
    if listing.error is not None:
        skipped = {"reason": SKIP_UNREACHABLE, "path": str(repo_root), "detail": listing.error}
        return Outcome(skipped=skipped)
    worktrees = [c for c in listing.checkouts if not c.is_main]
    logged = [
        (c, segments)
        for c in worktrees
        if (segments := reader.segment_listing(c.state_dir, archives=True).segments)
    ]
    main = next(c for c in listing.checkouts if c.is_main)
    held, unreadable = main_identities(main.state_dir) if logged else (frozenset(), [])
    findings: list[dict] = []
    unmerged: list[dict] = []
    in_flight: list[str] = []
    for checkout, segments in logged:
        rows, newest, bad = worktree_rows_missing_from(segments, held)
        unreadable += bad
        if not rows:
            continue
        newest_stamp = newest.stamp if newest else None
        if newest is not None and now - newest.time <= policy.worktree_age_limit:
            in_flight.append(checkout.name)
            findings.append(_in_flight_finding(checkout, rows, newest_stamp))
            continue
        unmerged.append({"worktree": checkout.name, "rows": rows, "newest": newest_stamp})
        findings.append(_unmerged_finding(checkout, rows, newest_stamp))
    findings.append(_worktree_summary(repo_root, len(worktrees), unmerged, in_flight))
    examined = {
        "worktrees": len(worktrees),
        "in_flight": in_flight,
        "unmerged": unmerged,
        "unreadable": unreadable,
    }
    return Outcome(examined, tuple(findings))


def main_identities(state_dir: Path) -> tuple[frozenset[str], list[str]]:
    """Identities of every row in the main checkout's log, and the segments it could not read."""
    held: set[str] = set()
    unreadable: list[str] = []
    for path in reader.segment_listing(state_dir, archives=True).segments:
        read = reader.read_raw_segment(path)
        if read.error is not None:
            unreadable.append(str(path))
        held.update(reader.row_identity(row) for _text, row in read.entries)
    return frozenset(held), unreadable


def worktree_rows_missing_from(
    segments: tuple[Path, ...], held: frozenset[str]
) -> tuple[int, Stamped | None, list[str]]:
    """`(distinct rows not in held, newest row of the log, unreadable segments)` for one worktree."""
    missing: set[str] = set()
    newest: Stamped | None = None
    unreadable: list[str] = []
    for path in segments:
        read = reader.read_raw_segment(path)
        if read.error is not None:
            unreadable.append(str(path))
        for _text, row in read.entries:
            identity = reader.row_identity(row)
            if identity not in held:
                missing.add(identity)
            moment = reader.row_time(row)
            if moment != reader.UNTIMED and (newest is None or moment > newest.time):
                newest = Stamped(moment, row["timestamp"])
    return len(missing), newest, unreadable


def _unmerged_finding(checkout: checkouts.Checkout, rows: int, newest: str | None) -> dict:
    return _finding(
        "P14",
        "warn",
        checkout.root,
        f"worktree {checkout.name} holds {rows} row(s) the main log lacks; its newest row is "
        f"{newest or 'untimed'}, past the age limit: merge it in before removing the worktree "
        f"(scripts/merge_worktree_log.py --worktree {checkout.root})",
        worktree=checkout.name,
        rows=rows,
        newest=newest,
    )


def _in_flight_finding(checkout: checkouts.Checkout, rows: int, newest: str | None) -> dict:
    return _finding(
        "P14",
        "info",
        checkout.root,
        f"worktree {checkout.name} is in flight: {rows} row(s) not yet in the main log, "
        f"newest {newest}",
        worktree=checkout.name,
        rows=rows,
        newest=newest,
    )


def _worktree_summary(root: Path, worktrees: int, unmerged: list, in_flight: list) -> dict:
    return _finding(
        "P14",
        "info",
        root,
        f"{worktrees} linked worktree(s): {len(unmerged)} with unmerged rows past the age "
        f"limit, {len(in_flight)} in flight",
    )


# -- Core classification -----------------------------------------------------------

_LOG_CHECKS = (
    ("P09", check_archive_coverage),
    ("P10", check_rotation_state),
    ("P11", lambda view, _policy: check_segment_integrity(view)),
    ("P12", lambda view, _policy: check_helper_share(view)),
    ("P13", lambda view, _policy: check_mode_source(view)),
)


def classify(repo_root: Path, now: datetime) -> dict:
    """Build the envelope for the checkout at `repo_root`, judging worktree age at `now`."""
    policy = current_policy()
    view = read_log(repo_root / AI_STATE_REL)
    skip = log_skip(view)
    outcomes = {
        check_id: Outcome(skipped=skip) if skip else check(view, policy)
        for check_id, check in _LOG_CHECKS
    }
    outcomes["P14"] = check_unmerged_worktrees(repo_root, policy, now)
    return {
        "script": "check_observation_log_health",
        "checks": list(CHECK_IDS),
        "skipped": {check_id: outcomes[check_id].skipped for check_id in CHECK_IDS},
        "examined": {check_id: outcomes[check_id].examined for check_id in CHECK_IDS},
        "findings": [f for check_id in CHECK_IDS for f in outcomes[check_id].findings],
        "bound": dict(_BOUNDS),
        "judged_against": policy.judged_against(),
    }


# -- CLI --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_observation_log_health",
        description=(
            "Advisory: judge the observation log's archives, rotation, integrity, helper "
            "share, recorded mode source and unmerged worktree logs. Called by sentinel P09-P14."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any warning is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _warnings(report: dict) -> list[dict]:
    return [f for f in report["findings"] if f["severity"] == SEVERITY]


def _format_human(report: dict) -> str:
    lines = []
    for check_id in CHECK_IDS:
        skipped = report["skipped"][check_id]
        if skipped is not None:
            lines.append(f"{check_id}: skipped ({skipped['reason']})")
    warnings = _warnings(report)
    lines.append(f"check_observation_log_health: {len(warnings)} warning(s).")
    lines.extend(f"  - {f['check']} {f['message']}" for f in warnings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root, datetime.now(timezone.utc))
    warnings = _warnings(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_format_human(report), file=sys.stderr if warnings else sys.stdout)

    return 1 if (args.check and warnings) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_observation_log_health: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
