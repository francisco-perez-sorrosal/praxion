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

**T01 and T04 extend the same shape to the skill surface.** T01 applies T03's
own standard warn/fail pair (independently valued: warn 400 / fail 600) to
`skills/*/SKILL.md`; T04 flags any `skills/*/references/*.md` file over 800
lines, WARN-only (the catalogue row states one bound, not a pair).
`classify()` composes all three into one envelope
(`findings`/`skipped`/`examined`/`bound`, keyed by check id) -- `run_t03()`
itself is untouched, still a flat finding list, so no existing caller of that
function sees a different shape.

Invocation:

    check_agent_prompt_size.py                  # human-readable summary
    check_agent_prompt_size.py --json           # machine-readable JSON envelope
    check_agent_prompt_size.py --check          # exit 1 when any finding, else 0
    check_agent_prompt_size.py --repo-root DIR  # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when >=1 finding is present.
A check whose substrate (`agents/` or `skills/`) is absent contributes no
findings and no exit-code weight.
Exit code 2 when the resolved root is a plugin-cache path.

Invoked by the sentinel's T dimension (`--json`, family-dispatched); also
runnable standalone.

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

# The check ids this script's row surface declares -- a literal tuple so the row/
# registry/script Triangle in `tests/test_sentinel_check_triangle.py` can read it via
# AST without importing this module. Additive only: a new id lands here in the same
# commit that writes its row.
CHECK_IDS: tuple[str, ...] = ("T01", "T03", "T04")

SCRIPT_NAME = "check_agent_prompt_size"

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

# T01: SKILL.md line-count ceiling -- same warn/fail shape as T03's standard pair,
# independently valued per the catalogue row ("under 500 lines (warn 400, fail 600)").
_SKILL_WARN = 400
_SKILL_FAIL = 600

# T04: reference-file ceiling -- WARN only, no fail tier (the catalogue row states a
# single "no single reference file >800 lines" bound).
_REFERENCE_WARN_LINES = 800

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
                "check": "T03",
                "severity": severity,
                "entity": rel,
                "message": (
                    f"{rel}: {line_count} lines, at or past {severity} ceiling "
                    f"(warn {warn} / fail {fail}, {note})"
                ),
            }
        )
    return findings


def run_t01(repo_root: Path) -> tuple[list[dict], dict]:
    """Return one finding per `skills/*/SKILL.md` file at or past its warn ceiling.

    Same warn/fail-ceiling shape as T03's standard pair, over a different
    population and its own thresholds (`_SKILL_WARN`/`_SKILL_FAIL`).
    """
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        logger.info("T01 skip: skills/ absent at %s", repo_root)
        return [], {"files_examined": 0}

    findings: list[dict] = []
    paths = sorted(skills_dir.glob("*/SKILL.md"))
    for path in paths:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count < _SKILL_WARN:
            continue
        severity = "fail" if line_count >= _SKILL_FAIL else "warn"
        rel = path.relative_to(repo_root).as_posix()
        findings.append(
            {
                "check": "T01",
                "severity": severity,
                "entity": rel,
                "message": (
                    f"{rel}: {line_count} lines, at or past {severity} ceiling "
                    f"(warn {_SKILL_WARN} / fail {_SKILL_FAIL})"
                ),
            }
        )
    return findings, {"files_examined": len(paths)}


def run_t04(repo_root: Path) -> tuple[list[dict], dict]:
    """Return a WARN finding per `skills/*/references/*.md` file over 800 lines.

    Single-threshold, unlike T01/T03: the catalogue row states one bound, not a
    warn/fail pair.
    """
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        logger.info("T04 skip: skills/ absent at %s", repo_root)
        return [], {"files_examined": 0}

    findings: list[dict] = []
    paths = sorted(skills_dir.glob("*/references/*.md"))
    for path in paths:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count <= _REFERENCE_WARN_LINES:
            continue
        rel = path.relative_to(repo_root).as_posix()
        findings.append(
            {
                "check": "T04",
                "severity": "warn",
                "entity": rel,
                "message": f"{rel}: {line_count} lines, exceeds the "
                f"{_REFERENCE_WARN_LINES}-line ceiling",
            }
        )
    return findings, {"files_examined": len(paths)}


def classify(repo_root: Path) -> dict:
    """T01 + T03 + T04 in one envelope -- see module docstring for the shape.

    `run_t03()` is untouched -- still a flat finding list, so every existing
    caller (canaries, `agents/sentinel.md`'s prior single-check wiring) keeps
    seeing byte-identical output. This function only widens the surface
    `main()`'s `--json` and the sentinel's family dispatch actually consume,
    per check id, and each check carries its own substrate: T01/T04 need
    `skills/`, T03 needs `agents/` -- independent, not a shared gate.
    """
    agents_dir, skills_dir = repo_root / "agents", repo_root / "skills"

    t01_findings, t01_examined = run_t01(repo_root)
    t03_findings = run_t03(repo_root)
    t04_findings, t04_examined = run_t04(repo_root)

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "findings": t01_findings + t03_findings + t04_findings,
        "skipped": {
            "T01": None if skills_dir.is_dir() else "substrate absent (skills/)",
            "T03": None if agents_dir.is_dir() else "substrate absent (agents/)",
            "T04": None if skills_dir.is_dir() else "substrate absent (skills/)",
        },
        "examined": {
            "T01": t01_examined,
            "T03": {"files_examined": len(list(agents_dir.glob("*.md")))}
            if agents_dir.is_dir()
            else None,
            "T04": t04_examined,
        },
        "bound": {
            "T01": f"T01 clean means every skills/*/SKILL.md sits under its warn "
            f"line-count ceiling (warn {_SKILL_WARN} / fail {_SKILL_FAIL}).",
            "T03": "T03 clean means every agents/*.md sits under its warn line-count "
            "ceiling (standard, verifier.md's fixed pair, or sentinel.md's derived pair).",
            "T04": "T04 clean means no skills/*/references/*.md file exceeds "
            f"{_REFERENCE_WARN_LINES} lines.",
        },
    }


# -- CLI --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_agent_prompt_size",
        description=(
            "Advisory: flag agents/*.md (T03), skills/*/SKILL.md (T01) and "
            "skills/*/references/*.md (T04) files at or past their line-count "
            "ceiling. Called by sentinel's T dimension."
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
        help="Exit 1 when any T01/T03/T04 finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(findings: list[dict]) -> str:
    if not findings:
        return "check_agent_prompt_size: no T01/T03/T04 violations found."
    lines = [f"{len(findings)} file(s) at or past their warn ceiling:"]
    for f in findings:
        lines.append(f"  - [{f['check']}] {f['message']}")
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)
    findings = report["findings"]

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        summary = _format_human(findings)
        if findings:
            print(summary, file=sys.stderr)
        else:
            print(summary)

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
