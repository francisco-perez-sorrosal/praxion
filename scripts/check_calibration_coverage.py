#!/usr/bin/env python3
"""Detect calibration-coverage lapses: task-completing commits since the newest row.

Called by sentinel CA03 (which rewires that check to invoke this script mechanically),
but runs standalone too — no sentinel infrastructure required.

A calibration row in `.ai-state/calibration_log.md` anchors what the latest calibrated
task was. If task-completing commits of any tier (Direct through Full — see
`_PIPELINE_PREFIXES`, excluding release/bookkeeping commits in `_EXCLUDED_PREFIXES`)
have landed in git since that anchor, the project has uncalibrated task work. This
script counts those commits and flags under-coverage when the count reaches
`K_COMMITS` (default: 2).

Conditional-activation on absent substrate: when `.ai-state/calibration_log.md` is
absent, no verdict is produced (skip-with-INFO, exit 0). A project that has never
logged a calibration row has no baseline to compare against and must not be penalised
at bootstrap.

Also validates the Retrospective-cell enum convention: rows dated on or after
`ENUM_CUTOFF_DATE` must start their Retrospective cell with one of ENUM_VALUES
(`correct` / `over-calibrated` / `under-calibrated`), optionally followed by an
em-dash and prose. Rows predating the cutover are exempt (mirrors the ADR corpus's
clean-cutover precedent at dec-230). This stays advisory -- sentinel CA02 is the
mechanical consumer, matching the existing non-blocking `remind_calibration.py`
pattern; nothing wires `--check`'s exit code into the commit gate today.

Invocation:

    check_calibration_coverage.py                 # summary to stdout
    check_calibration_coverage.py --json          # machine-readable JSON
    check_calibration_coverage.py --check         # exit 1 when under-covered or enum-noncompliant
    check_calibration_coverage.py --repo-root DIR # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when under-covered or when a
post-cutover row is missing the required Retrospective enum prefix.
Always 0 when calibration_log.md is absent (no substrate).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from _git_runner import git_output
from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

CALIBRATION_LOG_REL = ".ai-state/calibration_log.md"

# Prefixes that signal a task-completing commit, of any tier (Direct through Full).
_PIPELINE_PREFIXES = (
    "feat:",
    "fix:",
    "docs:",
    "refactor:",
    "test:",
    "perf:",
    "style:",
    "build:",
    "ci:",
    "revert:",
    "chore:",
)

# Prefixes excluded from the count even though they match _PIPELINE_PREFIXES —
# release automation (bump:) and ADR-finalize bookkeeping (chore(finalize)) are not
# task-completing work.
_EXCLUDED_PREFIXES = ("bump:", "chore(finalize)")

# Threshold: uncalibrated pipeline-commit count that triggers under-coverage.
K_COMMITS = 2

# Required first token of the Retrospective cell on rows dated on/after the cutover.
ENUM_VALUES = ("correct", "over-calibrated", "under-calibrated")

# Rows dated on/after this date must carry an ENUM_VALUES prefix; older rows are
# exempt (the convention did not exist when they were written).
ENUM_CUTOFF_DATE = "2026-09-08"

# Timestamp column header in the calibration log Markdown table.
_TIMESTAMP_COL = "Timestamp"

# Regex to extract the content of the Timestamp cell from a table row.
# Matches `| <content> |` at the start of a Markdown table row.
_ROW_PATTERN = re.compile(r"^\|\s*([^|]+?)\s*\|")

logger = logging.getLogger("check_calibration_coverage")


# -- Git helpers --------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str | None:
    """Run `git <args>` in repo_root; return stripped stdout, None on failure."""
    return git_output(repo_root, *args, logger=logger)


def _pipeline_commits_since(repo_root: Path, since: str) -> int:
    """Count task-completing commits reachable from HEAD that post-date `since`.

    Uses `git log --oneline --since=<date>` then filters by commit message prefix.
    Commits whose first line starts with a prefix in `_PIPELINE_PREFIXES`
    (case-sensitive) count as task-completing work of any tier — except commits
    starting with a prefix in `_EXCLUDED_PREFIXES` (`bump:`, `chore(finalize)`),
    which are release automation or ADR-finalize bookkeeping, never task work.
    """
    output = _git(repo_root, "log", "--oneline", f"--since={since}")
    if not output:
        return 0
    count = 0
    for line in output.splitlines():
        # Each line: "<short-sha> <message>"
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        message = parts[1].strip()
        if any(message.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
            continue
        if any(message.startswith(prefix) for prefix in _PIPELINE_PREFIXES):
            count += 1
    return count


# -- Calibration log parsing --------------------------------------------------


def _newest_calibration_timestamp(log_path: Path) -> str | None:
    """Return the newest Timestamp cell value from calibration_log.md, or None.

    The log is a Markdown table with a header row (`| Timestamp | Task | ... |`)
    followed by a separator row and data rows. Each data row's first cell is the
    timestamp. We scan all rows and return the last data-row timestamp (newest
    entry, since the log is append-only chronological).
    """
    text = log_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    header_index: int | None = None
    for i, line in enumerate(lines):
        if _TIMESTAMP_COL in line and line.strip().startswith("|"):
            header_index = i
            break

    if header_index is None:
        return None

    # Data rows start after the header + separator rows.
    timestamps: list[str] = []
    for line in lines[header_index + 2 :]:
        line = line.strip()
        if not line.startswith("|"):
            continue
        match = _ROW_PATTERN.match(line)
        if match:
            candidate = match.group(1).strip()
            # Skip the header itself and separator dashes.
            if candidate and candidate != _TIMESTAMP_COL and not candidate.startswith("-"):
                timestamps.append(candidate)

    return timestamps[-1] if timestamps else None


def _row_timestamp_and_retrospective(line: str) -> tuple[str, str] | None:
    """Extract (timestamp, retrospective) from a calibration-log data row.

    Takes the first and last cells rather than a fixed-position split: a middle
    column (Task/Signals/Source prose) occasionally carries an unescaped literal
    pipe, which shifts a positional split but never touches the row's outer
    boundary cells. Returns None for non-data lines (header, separator, blank).
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = stripped.split("|")
    if len(cells) < 4:
        return None
    timestamp = cells[1].strip()
    if not timestamp or timestamp == _TIMESTAMP_COL or timestamp.startswith("-"):
        return None
    retrospective = cells[-2].strip()
    return timestamp, retrospective


# -- Enum-compliance computation -----------------------------------------------


def compute_enum_compliance(repo_root: Path) -> dict[str, object]:
    """Return enum-compliance stats for rows dated on/after ENUM_CUTOFF_DATE.

    Rows predating the cutover are exempt -- the enum-first Retrospective
    convention only binds new rows (dec-draft-3adfda75), mirroring the ADR
    corpus's clean-cutover precedent at dec-230.
    """
    log_path = repo_root / CALIBRATION_LOG_REL

    if not log_path.exists():
        return {
            "compliant": True,
            "new_rows": 0,
            "violations": [],
            "details": "No calibration_log.md found — skip-with-INFO (no substrate)",
        }

    text = log_path.read_text(encoding="utf-8")
    violations: list[dict[str, str]] = []
    new_rows = 0

    for line in text.splitlines():
        cells = _row_timestamp_and_retrospective(line)
        if cells is None:
            continue
        timestamp, retrospective = cells
        if timestamp[:10] < ENUM_CUTOFF_DATE:
            continue
        new_rows += 1
        if not retrospective.startswith(ENUM_VALUES):
            violations.append({"timestamp": timestamp, "retrospective": retrospective})

    compliant = not violations
    if new_rows == 0:
        details = "No rows on/after the enum cutover — nothing to validate."
    elif compliant:
        details = f"{new_rows} row(s) on/after the enum cutover, all enum-compliant."
    else:
        details = (
            f"{len(violations)} of {new_rows} row(s) on/after the enum cutover are "
            f"missing the required Retrospective enum prefix ({'/'.join(ENUM_VALUES)})."
        )

    return {
        "compliant": compliant,
        "new_rows": new_rows,
        "violations": violations,
        "details": details,
    }


# -- Coverage computation -----------------------------------------------------


def compute_coverage(repo_root: Path) -> dict[str, object]:
    """Return a coverage dict: covered, newest_calibration, uncalibrated_commits, details."""
    log_path = repo_root / CALIBRATION_LOG_REL

    if not log_path.exists():
        return {
            "covered": True,
            "newest_calibration": None,
            "uncalibrated_commits": 0,
            "details": "No calibration_log.md found — skip-with-INFO (no substrate)",
        }

    newest_ts = _newest_calibration_timestamp(log_path)
    if newest_ts is None:
        return {
            "covered": True,
            "newest_calibration": None,
            "uncalibrated_commits": 0,
            "details": "calibration_log.md present but contains no data rows — skip-with-INFO",
        }

    count = _pipeline_commits_since(repo_root, newest_ts)
    covered = count < K_COMMITS

    if covered:
        details = (
            f"Calibration current — {count} uncalibrated pipeline commit(s) since "
            f"{newest_ts} (threshold: {K_COMMITS})."
        )
    else:
        details = (
            f"Under-coverage — {count} uncalibrated pipeline commit(s) since "
            f"{newest_ts} (threshold: {K_COMMITS}). "
            "Append a calibration row to .ai-state/calibration_log.md."
        )

    return {
        "covered": covered,
        "newest_calibration": newest_ts,
        "uncalibrated_commits": count,
        "details": details,
    }


# -- Reporting ----------------------------------------------------------------


def _format_human(result: dict[str, object]) -> str:
    covered = result["covered"]
    details = result["details"]
    if covered:
        return f"check_calibration_coverage: {details}"
    return (
        "\n"
        + "=" * 72
        + "\n"
        + "CALIBRATION UNDER-COVERAGE\n"
        + "=" * 72
        + f"\n{details}\n"
        + "=" * 72
        + "\n"
    )


def _format_enum_human(enum_result: dict[str, object]) -> str:
    if enum_result["compliant"]:
        return f"check_calibration_coverage (enum): {enum_result['details']}"
    lines = [
        "",
        "=" * 72,
        "CALIBRATION RETROSPECTIVE ENUM NON-COMPLIANCE",
        "=" * 72,
        str(enum_result["details"]),
    ]
    for violation in enum_result["violations"]:
        lines.append(f"  - {violation['timestamp']}: {violation['retrospective']!r}")
    lines.append("=" * 72)
    return "\n".join(lines) + "\n"


# -- Orchestration ------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_calibration_coverage",
        description=(
            "Advisory: flag when task-completing commits (any tier) have landed since "
            "the newest calibration_log.md row (the unenforced-producer gap). "
            "Runs standalone — no /sentinel invocation required. Called by sentinel CA03."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when under-covered or when a post-cutover row is enum-noncompliant (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2
    result = compute_coverage(repo_root)
    enum_result = compute_enum_compliance(repo_root)

    if args.json:
        payload = dict(result)
        payload["enum_compliance"] = enum_result
        print(json.dumps(payload, indent=2))
    else:
        covered = result["covered"]
        print(_format_human(result), file=sys.stdout if covered else sys.stderr)
        enum_compliant = enum_result["compliant"]
        print(_format_enum_human(enum_result), file=sys.stdout if enum_compliant else sys.stderr)

    return 1 if (args.check and (not result["covered"] or not enum_result["compliant"])) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_calibration_coverage: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
