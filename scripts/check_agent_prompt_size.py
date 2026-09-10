#!/usr/bin/env python3
"""T03: agent prompt line-count ceilings -- one derived, the rest fixed.

Every `agents/*.md` file except the two catalog files (`CLAUDE.md`,
`README.md` -- glue/index content, not an agent definition; same exclusion
`strip_progress_mandate.py::AGENT_FILES` uses for the same reason) is measured
against a warn/fail line-count pair:

    standard             warn 400 / fail 500 -- the population's median size
    agents/verifier.md   warn 550 / fail 700 -- fixed; its bulk is a
                          comprehensive Process plus a tested-in-place
                          rework-spawn contract, neither of which grows with a
                          table, so forcing it under 500 risks a dead gate or
                          gutting tested substance
    agents/sentinel.md   DERIVED, never fixed. `S` = the line span of its
                          `## Check Catalog` heading through the line before
                          the next `## ` heading. Ceiling = warn `S + 300` /
                          fail `S + 400` -- precisely the standard pair applied
                          to everything *outside* the catalog, so the
                          exception introduces no numeral of its own. `S` is
                          recomputed every run (`_catalog_span`, mirroring
                          `awk '/^## Check Catalog/{n=NR} /^## /{if(n&&NR>n)
                          {print NR-n; exit}}'`), never hardcoded -- a
                          monotonically growing catalog outgrows any fixed
                          ceiling eventually, whereas here each added row
                          lifts the ceiling by exactly what it consumed, so
                          headroom is invariant under catalog growth
                          (`test_catalog_growth_alone_leaves_the_verdict_unchanged`)
                          and only discretionary prose can breach it
                          (`test_shrinking_catalog_growing_prose_flips_the_derived_verdict`).

Advisory by construction -- **default exit 0 even with findings**. The live
repo's `agents/sentinel.md` is measured today at `S=352` (warn 652), against a
680-line file: already in WARN. This script must never be wired as a
blocking pre-commit gate; the safety is the script's own default exit code,
not special pre-commit syntax. `--check` remains the opt-in for a future
deliberate cleanup pass.

Invocation:

    check_agent_prompt_size.py                  # human-readable summary
    check_agent_prompt_size.py --json           # machine-readable JSON array
    check_agent_prompt_size.py --check          # exit 1 when any finding, else 0
    check_agent_prompt_size.py --repo-root DIR  # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when >=1 finding is present.
Always 0 when `agents/` is absent.
Exit code 2 when the resolved root is a plugin-cache path.

Invoked by the sentinel's T dimension (`--json`); also runnable standalone.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md § Pragmatism.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent

CHECK_ID = "T03"

# Catalog/glue files, not agent definitions -- same exclusion
# `strip_progress_mandate.py::AGENT_FILES` uses, for the same reason.
_CATALOG_FILES = frozenset({"CLAUDE.md", "README.md"})

_STANDARD_WARN = 400
_STANDARD_FAIL = 500

# Fixed exception: `agents/verifier.md` encodes a comprehensive Process plus a
# tested-in-place rework-spawn contract, neither of which grows with a table.
_FIXED_THRESHOLDS: dict[str, tuple[int, int]] = {"verifier.md": (550, 700)}

_DERIVED_MARGIN_WARN = 300
_DERIVED_MARGIN_FAIL = 400

_CATALOG_HEADING_RE = re.compile(r"^## Check Catalog")
_H2_RE = re.compile(r"^## ")

logger = logging.getLogger("check_agent_prompt_size")


# -- Core detection -------------------------------------------------------------


def _catalog_span(text: str) -> int | None:
    """Return `S`: the `## Check Catalog` heading's line span through the line
    before the next `## ` heading.

    Mirrors `awk '/^## Check Catalog/{n=NR} /^## /{if(n&&NR>n){print NR-n; exit}}'`
    line-for-line so the row's own reproduction recipe and this function never
    silently diverge. None when no catalog heading is found, or the catalog
    runs to end-of-file with no following `## ` heading.
    """
    catalog_line: int | None = None
    for i, line in enumerate(text.splitlines(), start=1):
        if _CATALOG_HEADING_RE.match(line):
            catalog_line = i
        if _H2_RE.match(line) and catalog_line is not None and i > catalog_line:
            return i - catalog_line
    return None


def _thresholds_for(path: Path, text: str) -> tuple[int, int, str]:
    """Return `(warn, fail, note)` for one agent file.

    `note` names how the pair was produced ("standard" / "fixed" /
    "derived S=<n>") so a finding's message shows its own derivation instead
    of a bare pair of numbers.
    """
    if path.name in _FIXED_THRESHOLDS:
        warn, fail = _FIXED_THRESHOLDS[path.name]
        return warn, fail, "fixed"
    if path.name == "sentinel.md":
        span = _catalog_span(text)
        if span is not None:
            return span + _DERIVED_MARGIN_WARN, span + _DERIVED_MARGIN_FAIL, f"derived S={span}"
        # No catalog heading found -- fall back to the standard pair rather than
        # stop checking the one file the derived form exists for.
        logger.warning("T03: sentinel.md has no `## Check Catalog` span; using standard pair")
    return _STANDARD_WARN, _STANDARD_FAIL, "standard"


def run_t03(repo_root: Path) -> list[dict]:
    """Return one finding per `agents/*.md` file at or past its warn ceiling.

    Parameters
    ----------
    repo_root:
        Repository root (contains `agents/`).

    Returns
    -------
    A list of sentinel finding dicts. Each finding has:
        {
            "check": "T03",
            "severity": "warn" | "fail",
            "entity": str,   # path relative to repo_root, e.g. "agents/sentinel.md"
            "message": str,
        }
    Returns [] when `agents/` is absent or every file is within range.
    """
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        logger.info("T03 skip: agents/ absent at %s", repo_root)
        return []

    findings: list[dict] = []
    for path in sorted(agents_dir.glob("*.md")):
        if path.name in _CATALOG_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        warn, fail, note = _thresholds_for(path, text)
        if line_count < warn:
            continue
        severity = "fail" if line_count >= fail else "warn"
        rel = path.relative_to(repo_root).as_posix()
        findings.append(
            {
                "check": CHECK_ID,
                "severity": severity,
                "entity": rel,
                "message": (
                    f"{rel}: {line_count} lines, at or past {severity} ceiling "
                    f"(warn {warn} / fail {fail}, {note})"
                ),
            }
        )
    return findings


# -- CLI --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_agent_prompt_size",
        description=(
            "Advisory: flag agents/*.md files at or past their warn line-count "
            "ceiling (standard, agents/verifier.md's fixed pair, or "
            "agents/sentinel.md's derived pair). Called by sentinel T03."
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
        help="Exit 1 when any T03 finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(findings: list[dict]) -> str:
    if not findings:
        return "check_agent_prompt_size: no T03 violations found."
    lines = [f"T03 ({len(findings)} agent file(s) at or past their warn ceiling):"]
    for f in findings:
        lines.append(f"  - {f['message']}")
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    findings = run_t03(repo_root)

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
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_agent_prompt_size: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
