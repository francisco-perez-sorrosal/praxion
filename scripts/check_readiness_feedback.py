#!/usr/bin/env python3
"""Detect below-floor agent-readiness level and route it to the sentinel feedback edge.

Called by sentinel RD01 (which wires this check into the Pass-1 auto block),
but runs standalone too — no sentinel infrastructure required.

The readiness level lives at `readiness.data.adjusted_level` in the latest
`.ai-state/metrics_reports/METRICS_REPORT_*.json` file (root-embedded per dec-213;
the `adjusted_level` key folds any configured `pillar_weights` tuning). When
`adjusted_level` is absent, falls back to `readiness.data.level`.

A level below `READINESS_FLOOR` (3, the Practiced production-discipline threshold)
means CI, tests, pre-commit, contributing guide, container, observability,
type-checker, and dep-scanning are not all in place. The finding is an informational
signal for the `sentinel → promethean` feedback edge — sentinel reads it as Important,
promethean uses it for ideation. No tech-debt ledger row is written.

Conditional-activation on absent substrate: when
`.ai-state/metrics_reports/METRICS_REPORT_*.json` is absent, no verdict is
produced (skip-with-INFO, exit 0). A project that has never run `/project-metrics`
has no readiness signal and must not be penalised at bootstrap.

Invocation:

    check_readiness_feedback.py                 # summary to stdout
    check_readiness_feedback.py --json          # machine-readable JSON
    check_readiness_feedback.py --check         # exit 1 when below_threshold
    check_readiness_feedback.py --repo-root DIR # operate on another checkout (tests)
    check_readiness_feedback.py --verbose       # enable DEBUG logging

Exit code: 0 by default (advisory). With --check, 1 when below_threshold.
Always 0 when metrics_reports/ is absent (no substrate).
Exit code 2 when the resolved root is a plugin-cache path.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

METRICS_REPORTS_REL = ".ai-state/metrics_reports"

# Readiness levels map loosely to the project-metrics "Practiced" threshold.
# Level 1 = Bootstrapped, 2 = Developing, 3 = Practiced (production floor),
# 4 = Mature, 5 = Factory.  We flag when < 3.
READINESS_FLOOR = 3

# Exact string that signals a mechanical-only run (LLM tier was skipped).
_MECHANICAL_ONLY_NOTE = "mechanical-only"

logger = logging.getLogger("check_readiness_feedback")


# -- Report resolution --------------------------------------------------------


def _latest_report(metrics_dir: Path) -> Path | None:
    """Return the lexicographically newest METRICS_REPORT_*.json in *metrics_dir*.

    Files are named `METRICS_REPORT_YYYY-MM-DD_HH-MM-SS[_suffix].json`, which is
    lexicographically chronological — no mtime dependency.  Returns None when the
    directory is absent or empty.
    """
    if not metrics_dir.is_dir():
        return None
    candidates = sorted(metrics_dir.glob("METRICS_REPORT_*.json"))
    return candidates[-1] if candidates else None


# -- Readiness parsing --------------------------------------------------------


def _extract_readiness(report_path: Path) -> dict[str, object]:
    """Parse the readiness block from *report_path* and return a verdict dict.

    Returns a dict with keys:
        below_threshold (bool)
        adjusted_level (int | None)
        threshold (int)
        note (str | None)
        mechanical_only (bool)
        report_file (str)
        details (str)

    Falls back gracefully on missing keys without raising.
    """
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not parse %s: %s", report_path, exc)
        return _skip_verdict(str(report_path), f"unparseable report: {exc}")

    readiness = raw.get("readiness", {})
    data = readiness.get("data", {})

    # Prefer adjusted_level (folds pillar_weights tuning); fall back to level.
    adjusted_level: int | None = data.get("adjusted_level")
    if adjusted_level is None:
        adjusted_level = data.get("level")

    note: str | None = data.get("note")
    mechanical_only: bool = note == _MECHANICAL_ONLY_NOTE

    if adjusted_level is None:
        return _skip_verdict(
            str(report_path),
            "readiness.data.adjusted_level / readiness.data.level absent — skip-with-INFO",
        )

    below_threshold = int(adjusted_level) < READINESS_FLOOR

    if below_threshold:
        annotation = (
            " (mechanical-only — LLM tier skipped; level is a floor)" if mechanical_only else ""
        )
        details = (
            f"Readiness level {adjusted_level} is below the production floor"
            f" {READINESS_FLOOR} (Practiced).{annotation}"
            " Missing production-discipline criteria include CI, tests, pre-commit,"
            " contributing guide, container, observability, type-checker, and dep-scanning."
            " Run `/project-metrics` to reassess and `/project-metrics --llm` for a full score."
        )
    else:
        details = (
            f"Readiness level {adjusted_level} meets the production floor {READINESS_FLOOR}"
            " (Practiced). No action required."
        )

    return {
        "below_threshold": below_threshold,
        "adjusted_level": adjusted_level,
        "threshold": READINESS_FLOOR,
        "note": note,
        "mechanical_only": mechanical_only,
        "report_file": str(report_path),
        "details": details,
    }


def _skip_verdict(report_file: str, reason: str) -> dict[str, object]:
    """Return a skip-with-INFO (substrate absent or unparseable) verdict."""
    return {
        "below_threshold": False,
        "adjusted_level": None,
        "threshold": READINESS_FLOOR,
        "note": None,
        "mechanical_only": False,
        "report_file": report_file,
        "details": f"skip-with-INFO: {reason}",
    }


# -- Main computation ---------------------------------------------------------


def compute_readiness_verdict(repo_root: Path) -> dict[str, object]:
    """Return a readiness-feedback verdict dict for *repo_root*."""
    metrics_dir = repo_root / METRICS_REPORTS_REL
    report_path = _latest_report(metrics_dir)

    if report_path is None:
        logger.info(
            "RD01 skip-with-INFO: .ai-state/metrics_reports/ absent or empty — "
            "no readiness signal for this project"
        )
        return _skip_verdict(
            str(metrics_dir),
            ".ai-state/metrics_reports/ absent or contains no METRICS_REPORT_*.json",
        )

    logger.debug("Latest metrics report: %s", report_path)
    return _extract_readiness(report_path)


# -- Reporting ----------------------------------------------------------------


def _format_human(result: dict[str, object]) -> str:
    below = result["below_threshold"]
    details = result["details"]
    if not below:
        return f"check_readiness_feedback: {details}"
    return (
        "\n"
        + "=" * 72
        + "\n"
        + "READINESS BELOW PRODUCTION FLOOR — RD01 Important\n"
        + "=" * 72
        + f"\n{details}\n"
        + "=" * 72
        + "\n"
    )


# -- Orchestration ------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_readiness_feedback",
        description=(
            "Advisory: flag when the latest METRICS_REPORT_*.json shows"
            " readiness.data.adjusted_level < 3 (below the Practiced production floor)."
            " Runs standalone — no /sentinel invocation required. Called by sentinel RD01."
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
        help="Exit 1 when below_threshold (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2
    result = compute_readiness_verdict(repo_root)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        report = _format_human(result)
        below = result["below_threshold"]
        print(report, file=sys.stdout if not below else sys.stderr)

    return 1 if (args.check and result["below_threshold"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_readiness_feedback: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
