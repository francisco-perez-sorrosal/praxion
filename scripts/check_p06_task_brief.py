#!/usr/bin/env python3
"""Detect P06 violations: Standard/Full pipeline slugs missing TASK_BRIEF.md.

The P06 sentinel check flags any `.ai-work/<slug>/` directory that contains
`SYSTEMS_PLAN.md` (indicating a Standard/Full pipeline ran — the architect only
runs there) but no `TASK_BRIEF.md` (indicating the brief was never produced by
the orchestrator's Intake Clarity Gate). A file-existence check — no LLM required.

Skip conditions (exit 0, empty findings):
  - `.ai-work/` is absent from `repo_root`

No tech-debt ledger row is written; this emits a finding only, consistent
with the CA03/SH08/RD01 pattern.

Invocation:

    check_p06_task_brief.py                  # human-readable summary
    check_p06_task_brief.py --json           # machine-readable JSON array
    check_p06_task_brief.py --check          # exit 1 when any finding, else 0
    check_p06_task_brief.py --repo-root DIR  # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when ≥1 finding is present.
Always 0 when `.ai-work/` is absent.
Exit code 2 when the resolved root is a plugin-cache path.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

AI_WORK_REL = ".ai-work"

CHECK_ID = "P06"
SEVERITY = "warn"

logger = logging.getLogger("check_p06_task_brief")


# -- Core detection -----------------------------------------------------------


def run_p06(repo_root: Path) -> list[dict]:
    """Return one finding per slug in .ai-work/ that has SYSTEMS_PLAN.md but no TASK_BRIEF.md.

    Parameters
    ----------
    repo_root:
        Repository root (contains `.ai-work/`).

    Returns
    -------
    A list of sentinel finding dicts. Each finding has:
        {
            "check": "P06",
            "severity": "warn",
            "message": str,
        }
    Returns [] when `.ai-work/` is absent or when every slug has TASK_BRIEF.md.
    """
    ai_work = repo_root / AI_WORK_REL
    if not ai_work.is_dir():
        logger.info("P06 skip: .ai-work/ absent at %s", repo_root)
        return []

    findings: list[dict] = []
    for slug_dir in sorted(ai_work.iterdir()):
        if not slug_dir.is_dir():
            continue
        if _is_p06_violation(slug_dir):
            findings.append(
                {
                    "check": CHECK_ID,
                    "severity": SEVERITY,
                    "message": (
                        f"TASK_BRIEF.md absent in .ai-work/{slug_dir.name}/ "
                        f"(SYSTEMS_PLAN.md present — Standard/Full tier implied). "
                        f"The orchestrator's Intake Clarity Gate must produce "
                        f"TASK_BRIEF.md before the first agent spawn."
                    ),
                }
            )

    return findings


def _is_p06_violation(slug_dir: Path) -> bool:
    """Return True when a slug dir has SYSTEMS_PLAN.md and no TASK_BRIEF.md."""
    return (slug_dir / "SYSTEMS_PLAN.md").exists() and not (slug_dir / "TASK_BRIEF.md").exists()


# -- CLI ----------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_p06_task_brief",
        description=(
            "Advisory: flag .ai-work/<slug>/ directories that contain "
            "SYSTEMS_PLAN.md (Standard/Full tier implied) but no TASK_BRIEF.md. "
            "Runs standalone — no /sentinel invocation required. Called by sentinel P06."
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
        help="Exit 1 when any P06 finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _format_human(findings: list[dict]) -> str:
    if not findings:
        return "check_p06_task_brief: no P06 violations found."
    lines = [f"P06 WARN ({len(findings)} slug(s) missing TASK_BRIEF.md):"]
    for f in findings:
        lines.append(f"  - {f['message']}")
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    findings = run_p06(repo_root)

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        report = _format_human(findings)
        if findings:
            print(report, file=sys.stderr)
        else:
            print(report)

    return 1 if (args.check and findings) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    _configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_p06_task_brief: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
