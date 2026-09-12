#!/usr/bin/env python3
"""BC01/BC03/BC04: behavioral-contract family.

Three checks, one shared concern: the four-behavior agent behavioral
contract is single-sourced in one always-loaded rule, and that
single-sourcing has not silently drifted.

* **BC01** (fail) -- `rules/swe/agent-behavioral-contract.md` exists, carries
  no `paths:` YAML frontmatter key (so it stays always-loaded rather than
  path-scoped), and names all four canonical behaviors: Surface Assumptions,
  Register Objection, Stay Surgical, Simplicity First.
* **BC03** (fail) -- every one of the 14 contract-bound agents cites
  `rules/swe/agent-behavioral-contract.md` somewhere in its own `.md` file,
  and no agent outside that list cites it. Both directions are reported:
  a missing citation (a contract-bound agent that dropped the pointer) and
  an extra one (an agent added to the citing set without updating this
  canonical enumeration) are both drift.
* **BC04** (fail) -- `skills/code-review/references/report-template.md`
  carries a `### Behavioral Contract Findings` subsection naming all six
  canonical tags: `[UNSURFACED-ASSUMPTION]`, `[MISSING-OBJECTION]`,
  `[NON-SURGICAL]`, `[SCOPE-CREEP]`, `[BLOAT]`, `[DEAD-CODE-UNREMOVED]`.

`_BC03_EXPECTED_AGENTS` below is the canonical enumeration of contract-bound
agents -- a future single-sourcing pass (tracked separately) should have
every other citer of this list (this rule's own prose, agent prompts) read
from this one place rather than re-typing it; this script does not attempt
that restructuring itself.

All three checks are unconditional: the contract is an always-loaded
ecosystem invariant, not a feature gated by presence of specs or ADRs, so
none of the three ever skips.

Invocation:

    check_behavioral_contract.py                  # human-readable summary
    check_behavioral_contract.py --json           # machine-readable envelope
    check_behavioral_contract.py --check          # exit 1 on any finding
    check_behavioral_contract.py --repo-root DIR  # operate on another checkout

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
SCRIPT_NAME = "check_behavioral_contract"

CHECK_IDS: tuple[str, ...] = ("BC01", "BC03", "BC04")

_BC_RULE_REL = "rules/swe/agent-behavioral-contract.md"
_REPORT_TEMPLATE_REL = "skills/code-review/references/report-template.md"
_AGENTS_DIR_REL = "agents"

# Files under agents/ that are not agent definitions -- excluded from BC03's
# citing/expected comparison for the same reason F01 excludes them from its
# agents/ glob: neither is the artifact type the directory names.
_EXCLUDED_AGENT_FILES = {"README.md", "CLAUDE.md"}

_BEHAVIOR_NAMES: tuple[str, ...] = (
    "Surface Assumptions",
    "Register Objection",
    "Stay Surgical",
    "Simplicity First",
)

# The canonical enumeration of the 14 agents that write, plan, or review
# code -- see the module docstring for the single-sourcing note.
_BC03_EXPECTED_AGENTS = frozenset(
    {
        "researcher",
        "systems-architect",
        "implementation-planner",
        "context-engineer",
        "implementer",
        "test-engineer",
        "verifier",
        "doc-engineer",
        "sentinel",
        "cicd-engineer",
        "interface-designer",
        "architect-validator",
        "agentic-transactions-architect",
        "discipline-consultant",
    }
)

_BC04_TAGS: tuple[str, ...] = (
    "[UNSURFACED-ASSUMPTION]",
    "[MISSING-OBJECTION]",
    "[NON-SURGICAL]",
    "[SCOPE-CREEP]",
    "[BLOAT]",
    "[DEAD-CODE-UNREMOVED]",
)

_BC04_HEADING = re.compile(r"^###\s*Behavioral Contract Findings\b")
_HEADING_BOUNDARY = re.compile(r"^#{1,3}\s")

logger = logging.getLogger(SCRIPT_NAME)


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _has_paths_frontmatter(text: str) -> bool:
    """True if `text` opens with a YAML frontmatter block declaring `paths:`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        if line.startswith("paths:"):
            return True
    return False


# -- BC01: contract rule exists, always-loaded, names all four behaviors ----


def _check_bc01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _BC_RULE_REL
    text = _read_text(path)
    if text is None:
        finding = {
            "check": "BC01",
            "severity": "fail",
            "entity": _BC_RULE_REL,
            "message": f"'{_BC_RULE_REL}' does not exist",
        }
        return [finding], None, {"behaviors_examined": 0}

    findings: list[dict] = []
    if _has_paths_frontmatter(text):
        findings.append(
            {
                "check": "BC01",
                "severity": "fail",
                "entity": _BC_RULE_REL,
                "message": f"'{_BC_RULE_REL}' carries a `paths:` key -- it must stay "
                "always-loaded, not path-scoped",
            }
        )
    for behavior in _BEHAVIOR_NAMES:
        if behavior not in text:
            findings.append(
                {
                    "check": "BC01",
                    "severity": "fail",
                    "entity": behavior,
                    "message": f"'{behavior}' is not named in {_BC_RULE_REL}",
                }
            )
    return findings, None, {"behaviors_examined": len(_BEHAVIOR_NAMES)}


# -- BC03: exactly the 14 contract-bound agents cite the rule ---------------


def _bc03_citing_agents(repo_root: Path) -> tuple[set[str], int]:
    agents_dir = repo_root / _AGENTS_DIR_REL
    citing: set[str] = set()
    examined = 0
    if not agents_dir.is_dir():
        return citing, examined
    for f in sorted(agents_dir.glob("*.md")):
        if f.name in _EXCLUDED_AGENT_FILES:
            continue
        examined += 1
        text = _read_text(f)
        if text and _BC_RULE_REL in text:
            citing.add(f.stem)
    return citing, examined


def _check_bc03(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    citing, examined = _bc03_citing_agents(repo_root)
    missing = sorted(_BC03_EXPECTED_AGENTS - citing)
    extra = sorted(citing - _BC03_EXPECTED_AGENTS)

    findings: list[dict] = [
        {
            "check": "BC03",
            "severity": "fail",
            "entity": name,
            "message": f"'{name}' is a contract-bound agent but does not cite {_BC_RULE_REL}",
        }
        for name in missing
    ]
    findings.extend(
        {
            "check": "BC03",
            "severity": "fail",
            "entity": name,
            "message": f"'{name}' cites {_BC_RULE_REL} but is not in the canonical "
            "contract-bound agent list",
        }
        for name in extra
    )
    return findings, None, {"agents_examined": examined}


# -- BC04: report-template tag vocabulary is complete ------------------------


def _bc04_findings_span(text: str) -> str | None:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _BC04_HEADING.match(line))
    except StopIteration:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _HEADING_BOUNDARY.match(line):
            break
        body.append(line)
    return "\n".join(body)


def _check_bc04(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _REPORT_TEMPLATE_REL
    text = _read_text(path)
    if text is None:
        finding = {
            "check": "BC04",
            "severity": "fail",
            "entity": _REPORT_TEMPLATE_REL,
            "message": f"'{_REPORT_TEMPLATE_REL}' does not exist",
        }
        return [finding], None, {"tags_examined": 0}

    span = _bc04_findings_span(text)
    if span is None:
        finding = {
            "check": "BC04",
            "severity": "fail",
            "entity": "### Behavioral Contract Findings",
            "message": f"heading not found in {_REPORT_TEMPLATE_REL}",
        }
        return [finding], None, {"tags_examined": 0}

    findings = [
        {
            "check": "BC04",
            "severity": "fail",
            "entity": tag,
            "message": f"'{tag}' missing from the Behavioral Contract Findings "
            f"subsection of {_REPORT_TEMPLATE_REL}",
        }
        for tag in _BC04_TAGS
        if tag not in span
    ]
    return findings, None, {"tags_examined": len(_BC04_TAGS)}


# -- Envelope (DS-A, keyed) -----------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    for check_id, fn in (
        ("BC01", _check_bc01),
        ("BC03", _check_bc03),
        ("BC04", _check_bc04),
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
            "BC01": f"BC01 clean means {_BC_RULE_REL} exists, is always-loaded, "
            "and names all four behaviors.",
            "BC03": "BC03 clean means exactly the 14 contract-bound agents cite "
            "the rule -- no fewer, no more.",
            "BC04": "BC04 clean means the report template's Behavioral Contract "
            "Findings subsection names all six canonical tags.",
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=("Advisory: behavioral-contract checks. Called by sentinel BC01/BC03/BC04."),
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
