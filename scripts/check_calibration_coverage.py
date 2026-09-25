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
(`correct` / `over-calibrated` / `under-calibrated`) or the `ENUM_PENDING` marker
(`[pending]`, sanctioned by the calibration-procedure skill but not yet a verdict),
optionally followed by an em-dash and prose. Rows predating the cutover are exempt
(mirrors the ADR corpus's clean-cutover precedent at dec-230). This stays advisory --
sentinel CA02 is the mechanical consumer, matching the existing non-blocking
`remind_calibration.py` pattern; nothing wires `--check`'s exit code into the commit
gate today.

CA02/CA03 family envelope (`classify`, `--json`): the instrument is the enum,
computed here, not judged by an LLM. CA02 classifies the first token of the
Retrospective cell on the last `window` post-cutover rows into a verdict
(`correct`/`over-calibrated`/`under-calibrated`), the `[pending]` marker
(unclassified, not a violation), or non-canonical (anything else). Its WARN shares
(`over`/`under` > 25%, or the zero-variance alarm when every classified row reads
`correct`) are computed over the CLASSIFIED denominator only -- pending and
non-canonical rows are excluded from the denominator, since neither is a graded
verdict; a non-canonical token also earns its own per-row WARN. CA02 skips (no
findings) below 5 classified rows -- too few to be a distribution. CA03 wraps
`compute_coverage` as a family row. Both skip with `substrate-absent` when
calibration_log.md itself is absent.

Golden bad-cases (see `scripts/test_check_calibration_coverage.py`): a window with
>25% under-calibrated rows fails CA02; 20/20 `correct` rows fails CA02 (zero-variance);
a non-canonical Retrospective token fails CA02 for that row; a `[pending]` row is
silent (no finding, excluded from the denominator); a within-band mixed distribution
(e.g. 12/4/4 correct/under/over) is the no-false-positive control.

Invocation:

    check_calibration_coverage.py                 # summary to stdout
    check_calibration_coverage.py --json          # machine-readable family envelope
    check_calibration_coverage.py --check         # exit 1 when under-covered or enum-noncompliant
    check_calibration_coverage.py --repo-root DIR # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when under-covered or when a
post-cutover row is missing the required Retrospective enum prefix. A CA02
distribution WARN never flips the exit code -- it is advisory, unlike coverage/enum
compliance which --check gates on.
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

SCRIPT_NAME = "check_calibration_coverage"

# The family-envelope check ids this script computes (dec-382 family-row form).
# Read with `ast.literal_eval` by the sentinel Triangle contract -- see
# tests/test_sentinel_check_triangle.py -- never by importing this module.
CHECK_IDS: tuple[str, ...] = ("CA02", "CA03")

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

# Sanctioned but not a verdict (skills/spec-driven-development/references/
# calibration-procedure.md, Retrospective bullet): a row logged before its
# retrospective is known. Compliant for --check; unclassified (neither verdict nor
# violation) for CA02's distribution -- excluded from the classified denominator.
ENUM_PENDING = "[pending]"

# Rows dated on/after this date must carry an ENUM_VALUES prefix; older rows are
# exempt (the convention did not exist when they were written).
ENUM_CUTOFF_DATE = "2026-09-07"  # the date the enum shipped; its own pipeline's row is not exempt

# CA02: minimum classified rows before a distribution verdict is meaningful.
CA02_MIN_CLASSIFIED = 5

# CA02: over-/under-calibrated share of classified rows that triggers a WARN.
CA02_SHARE_THRESHOLD = 0.25

# CA02: default window of post-cutover rows the distribution is computed over.
CA02_WINDOW = 20

# Trailing punctuation stripped off a Retrospective cell's leading token before
# enum-membership comparison (e.g. "correct—" written with no space before the dash).
_TRAILING_TOKEN_PUNCT = "—:."

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
    convention only binds new rows (dec-376), mirroring the ADR
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
        if not retrospective.startswith(ENUM_VALUES) and not retrospective.startswith(ENUM_PENDING):
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


# -- Enum-distribution computation (CA02) --------------------------------------


def _classify_token(retrospective: str) -> str:
    """First token of a Retrospective cell, trailing enum punctuation stripped.

    "Up to the first whitespace" rather than a full split: an em-dash written with
    no leading space ("correct—retrospective") still yields "correct" once the
    trailing punctuation strip runs, matching a spaced em-dash ("correct — ...").
    """
    token = retrospective.strip().split(None, 1)[0] if retrospective.strip() else ""
    return token.rstrip(_TRAILING_TOKEN_PUNCT)


def compute_enum_distribution(repo_root: Path, window: int = CA02_WINDOW) -> dict[str, object]:
    """Classify the Retrospective enum token of the last `window` post-cutover rows.

    Denominator limit: `shares` are computed over the CLASSIFIED rows only --
    rows whose token is a verdict in ENUM_VALUES. `[pending]` rows and
    non-canonical tokens are excluded from the denominator: neither is a graded
    verdict, so folding them in would understate the share of an actual verdict.
    """
    log_path = repo_root / CALIBRATION_LOG_REL
    counts = dict.fromkeys(ENUM_VALUES, 0)

    if not log_path.exists():
        return {
            "window": window,
            "classified": 0,
            "counts": counts,
            "shares": dict.fromkeys(ENUM_VALUES, 0.0),
            "pending": 0,
            "non_canonical": [],
        }

    text = log_path.read_text(encoding="utf-8")
    post_cutover: list[tuple[str, str]] = []
    for line in text.splitlines():
        cells = _row_timestamp_and_retrospective(line)
        if cells is None:
            continue
        timestamp, retrospective = cells
        if timestamp[:10] < ENUM_CUTOFF_DATE:
            continue
        post_cutover.append((timestamp, retrospective))

    pending = 0
    non_canonical: list[dict[str, str]] = []
    for timestamp, retrospective in post_cutover[-window:]:
        token = _classify_token(retrospective)
        if token in counts:
            counts[token] += 1
        elif token == ENUM_PENDING:
            pending += 1
        else:
            non_canonical.append({"timestamp": timestamp, "token": token})

    classified = sum(counts.values())
    shares = {value: (counts[value] / classified if classified else 0.0) for value in ENUM_VALUES}

    return {
        "window": window,
        "classified": classified,
        "counts": counts,
        "shares": shares,
        "pending": pending,
        "non_canonical": non_canonical,
    }


def _ca02_findings(distribution: dict[str, object], classified: int) -> list[dict[str, str]]:
    """CA02 findings for an already-above-threshold distribution: share WARNs,
    the zero-variance alarm, and one WARN per non-canonical row."""
    findings: list[dict[str, str]] = []
    shares = distribution["shares"]
    counts = distribution["counts"]

    for value in ("over-calibrated", "under-calibrated"):
        share = shares[value]
        if share > CA02_SHARE_THRESHOLD:
            findings.append(
                {
                    "check": "CA02",
                    "severity": "warn",
                    "entity": CALIBRATION_LOG_REL,
                    "message": (
                        f"{value} share is {share:.0%} of {classified} classified rows "
                        f"(threshold: {CA02_SHARE_THRESHOLD:.0%})"
                    ),
                }
            )

    if counts["correct"] == classified:
        findings.append(
            {
                "check": "CA02",
                "severity": "warn",
                "entity": CALIBRATION_LOG_REL,
                "message": (
                    f"zero-variance alarm: all {classified} classified rows read 'correct' -- "
                    "an instrument that never records an error is evidence of grading bias, "
                    "not of perfect calibration"
                ),
            }
        )

    for row in distribution["non_canonical"]:
        findings.append(
            {
                "check": "CA02",
                "severity": "warn",
                "entity": row["timestamp"],
                "message": f"non-canonical Retrospective token {row['token']!r} at {row['timestamp']}",
            }
        )

    return findings


# -- Family envelope (CA02, CA03) ----------------------------------------------


def classify(repo_root: Path) -> dict:
    """Return the CA02/CA03 family envelope: skipped/examined/findings/info/bound.

    CA02 excludes unclassified rows (pending/non-canonical) from its denominator
    (see `compute_enum_distribution`) and skips below `CA02_MIN_CLASSIFIED`. CA03 wraps `compute_coverage` as a family row. Both
    skip with `substrate-absent` when calibration_log.md itself is absent.
    """
    log_present = (repo_root / CALIBRATION_LOG_REL).exists()

    coverage = compute_coverage(repo_root)
    enum_compliance = compute_enum_compliance(repo_root)
    distribution = compute_enum_distribution(repo_root)

    findings: list[dict[str, str]] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    if not log_present:
        skipped["CA02"] = {"reason": "substrate-absent"}
        skipped["CA03"] = {"reason": "substrate-absent"}
    else:
        classified = distribution["classified"]
        examined["CA02"] = {"classified": classified, "window": distribution["window"]}
        examined["CA03"] = {"uncalibrated_commits": coverage["uncalibrated_commits"]}

        if classified < CA02_MIN_CLASSIFIED:
            skipped["CA02"] = {"reason": "below-threshold", "classified": classified}
        else:
            findings.extend(_ca02_findings(distribution, classified))

        if not coverage["covered"]:
            findings.append(
                {
                    "check": "CA03",
                    "severity": "warn",
                    "entity": CALIBRATION_LOG_REL,
                    "message": coverage["details"],
                }
            )

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": skipped,
        "examined": examined,
        "findings": findings,
        "info": {"coverage": coverage, "enum_compliance": enum_compliance},
        "withheld": [],
        "bound": {
            "CA02": (
                "CA02 clean means the Retrospective enum distribution over the last "
                "20 post-cutover rows stays within band, with no non-canonical tokens."
            ),
            "CA03": (
                "CA03 clean means recent task-completing commits are covered by a "
                "calibration_log.md row."
            ),
        },
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

    # The family envelope carries coverage/enum-compliance under info -- reused for
    # --check and human mode rather than recomputed, see classify()'s docstring.
    report = classify(repo_root)
    result = report["info"]["coverage"]
    enum_result = report["info"]["enum_compliance"]

    if args.json:
        print(json.dumps(report, indent=2))
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
