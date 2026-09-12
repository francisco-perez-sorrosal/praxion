#!/usr/bin/env python3
"""V01/V02/V03/V04: sentinel's own self-verification dimension.

"The sentinel includes itself in the audit" (`agents/sentinel.md` § Self-Verification
(V)) -- these four checks confirm the auditor is itself wired into the ecosystem it
audits, rather than trusting that by assumption:

* **V01** (fail) -- `./agents/sentinel.md` is present in `.claude-plugin/plugin.json`'s
  `agents` array.
* **V02** (fail) -- `skills/software-planning/references/coordination-details.md`'s
  `## Agent Roster` table (the roster's home since its PW-5 relocation out of the
  always-loaded coordination rule) has a row citing `sentinel`.
* **V03** (fail) -- `agents/README.md`'s agent table has a row citing `sentinel`.
* **V04** (fail) -- `agents/sentinel.md` has a `## Check Catalog` heading, at least
  one check-ID table row beneath it, and at least one check-ID table row under every
  `###` dimension heading the catalog itself declares. A dimension heading with
  nothing under it is the failure this check exists to catch: the catalog still lists
  the dimension, the sweep still reports on it, and nothing under it ever runs -- a
  hollow pass that hides every other failure.

V04's catalog-span detection mirrors `check_agent_prompt_size.py`'s
`_CATALOG_HEADING_RE`/span logic line-for-line (copied, not imported -- each script
in this family stays a flat, independently-readable file per the T03/HK01 precedent;
importing a sibling script for one regex would couple two unrelated liveness checks).

Skip conditions (DS-A, keyed): each of V01-V04 skips independently when its own
substrate file is absent or unreadable -- the four checks read four different files
and one file's absence says nothing about the other three.

Invocation:

    check_sentinel_self_audit.py                  # human-readable summary
    check_sentinel_self_audit.py --json           # machine-readable envelope
    check_sentinel_self_audit.py --check          # exit 1 on any finding
    check_sentinel_self_audit.py --repo-root DIR  # operate on another checkout

Exit code: 0 by default (advisory), 1 with --check when any finding is present.
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
SCRIPT_NAME = "check_sentinel_self_audit"

CHECK_IDS: tuple[str, ...] = ("V01", "V02", "V03", "V04")

_PLUGIN_JSON_REL = ".claude-plugin/plugin.json"
_ROSTER_REL = "skills/software-planning/references/coordination-details.md"
_README_REL = "agents/README.md"
_SENTINEL_REL = "agents/sentinel.md"

_SENTINEL_AGENT_ENTRY = "./agents/sentinel.md"
_ROSTER_HEADING = re.compile(r"^##\s*Agent Roster\b")
_H2_HEADING = re.compile(r"^##\s")
_H3_HEADING = re.compile(r"^###\s+(.+)$")

# Copied from `check_agent_prompt_size.py`'s `_CATALOG_HEADING_RE` -- see module
# docstring for why this is a copy, not an import.
_CATALOG_HEADING_RE = re.compile(r"^## Check Catalog")

# A check-ID table row's first cell: 1-3 letters then 1-3 digits (V01, HK01, T03,
# AC13) -- distinguishes a data row from the header (`ID`) and separator (`---`)
# rows of the same table without hand-listing every dimension's ID prefix.
_CHECK_ID_CELL = re.compile(r"^[A-Za-z]{1,3}[0-9]{1,3}$")

logger = logging.getLogger(SCRIPT_NAME)


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


# -- V01: plugin.json registration --------------------------------------------


def _check_v01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _PLUGIN_JSON_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], {"reason": "unparseable", "detail": str(exc)}, None
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, list):
        agents = []
    examined = {"agents_count": len(agents)}
    if _SENTINEL_AGENT_ENTRY in agents:
        return [], None, examined
    finding = {
        "check": "V01",
        "severity": "fail",
        "entity": str(path),
        "message": f"'{_SENTINEL_AGENT_ENTRY}' not found in plugin.json's agents array",
    }
    return [finding], None, examined


# -- V02/V03: table-row citation -----------------------------------------------


def _agent_roster_span(text: str) -> list[str] | None:
    """Lines from `## Agent Roster` through the line before the next `## ` heading."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _ROSTER_HEADING.match(line))
    except StopIteration:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _H2_HEADING.match(line):
            break
        body.append(line)
    return body


def _has_sentinel_row(lines: list[str]) -> bool:
    return any(line.startswith("|") and "`sentinel`" in line.lower() for line in lines)


def _check_v02(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _ROSTER_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None
    span = _agent_roster_span(text)
    if span is None:
        finding = {
            "check": "V02",
            "severity": "fail",
            "entity": str(path),
            "message": "'## Agent Roster' heading not found",
        }
        return [finding], None, None
    if _has_sentinel_row(span):
        return [], None, {"roster_lines": len(span)}
    finding = {
        "check": "V02",
        "severity": "fail",
        "entity": str(path),
        "message": "Agent Roster table has no row citing `sentinel`",
    }
    return [finding], None, {"roster_lines": len(span)}


def _check_v03(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _README_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None
    lines = text.splitlines()
    if _has_sentinel_row(lines):
        return [], None, {"lines": len(lines)}
    finding = {
        "check": "V03",
        "severity": "fail",
        "entity": str(path),
        "message": "agent table has no row citing `sentinel`",
    }
    return [finding], None, {"lines": len(lines)}


# -- V04: check-catalog presence and per-dimension population -----------------


def _catalog_span(lines: list[str]) -> tuple[int, int] | None:
    """(start, end) line-index range of the catalog body, end exclusive.

    Mirrors `check_agent_prompt_size.py`'s `_catalog_span` boundary logic: the
    catalog heading through the line before the next `## ` heading.
    """
    catalog_line: int | None = None
    for i, line in enumerate(lines):
        if _CATALOG_HEADING_RE.match(line):
            catalog_line = i
            continue
        if _H2_HEADING.match(line) and catalog_line is not None and i > catalog_line:
            return catalog_line + 1, i
    if catalog_line is not None:
        return catalog_line + 1, len(lines)
    return None


def _dimension_spans(body: list[str]) -> list[tuple[str, list[str]]]:
    """Every `### <name>` heading in `body`, paired with the lines beneath it up to
    the next `###`/`##` heading."""
    spans: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_lines: list[str] = []
    for line in body:
        match = _H3_HEADING.match(line)
        if match:
            if current_name is not None:
                spans.append((current_name, current_lines))
            current_name = match.group(1).strip()
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        spans.append((current_name, current_lines))
    return spans


def _has_check_row(lines: list[str]) -> bool:
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and _CHECK_ID_CELL.match(cells[0]):
            return True
    return False


def _check_v04(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _SENTINEL_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None

    lines = text.splitlines()
    span = _catalog_span(lines)
    if span is None:
        finding = {
            "check": "V04",
            "severity": "fail",
            "entity": str(path),
            "message": "'## Check Catalog' heading not found",
        }
        return [finding], None, None

    start, end = span
    body = lines[start:end]
    findings: list[dict] = []
    if not _has_check_row(body):
        findings.append(
            {
                "check": "V04",
                "severity": "fail",
                "entity": str(path),
                "message": "no check-ID rows found beneath '## Check Catalog'",
            }
        )

    dimensions = _dimension_spans(body)
    for name, dim_lines in dimensions:
        if not _has_check_row(dim_lines):
            findings.append(
                {
                    "check": "V04",
                    "severity": "fail",
                    "entity": f"### {name}",
                    "message": f"dimension '{name}' has no check-ID rows beneath its heading",
                }
            )

    examined = {"catalog_lines": end - start, "dimensions": len(dimensions)}
    return findings, None, examined


# -- Envelope (DS-A, keyed) -----------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    for check_id, fn in (
        ("V01", _check_v01),
        ("V02", _check_v02),
        ("V03", _check_v03),
        ("V04", _check_v04),
    ):
        check_findings, skip, examined_value = fn(repo_root)
        findings.extend(check_findings)
        skipped[check_id] = skip
        examined[check_id] = examined_value

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": skipped,
        "examined": examined,
        "findings": findings,
        "info": {},
        "withheld": [],
        "bound": {
            "V01": "V01 clean means plugin.json's agents array names agents/sentinel.md.",
            "V02": "V02 clean means the Agent Roster table has a sentinel row.",
            "V03": "V03 clean means agents/README.md's agent table has a sentinel row.",
            "V04": (
                "V04 clean means the Check Catalog heading is present, populated, "
                "and every declared dimension has at least one check-ID row."
            ),
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: sentinel's own self-verification checks. Called by sentinel V01/V02/V03/V04."
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
        help="Exit 1 when any finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    findings = report["findings"]
    if not findings:
        return f"{SCRIPT_NAME}: no findings across {', '.join(CHECK_IDS)}."
    lines = [f"{SCRIPT_NAME}: {len(findings)} finding(s):"]
    lines.extend(f"  - [{f['check']}/{f['severity']}] {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        print(text, file=sys.stderr if report["findings"] else sys.stdout)

    return 1 if (args.check and report["findings"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("%s: %s", SCRIPT_NAME, exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
