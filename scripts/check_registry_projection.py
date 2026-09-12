#!/usr/bin/env python3
"""X01/X02/X05/X06/EC01/EC02: registry-projection family.

Six checks, one shared shape: project a manifest or table against filesystem
reality.

* **X01** (fail) -- every path in `.claude-plugin/plugin.json`'s `agents` array
  resolves to an existing `.md` file.
* **X02** (fail) -- `skills/` has skill dirs, each holding a `SKILL.md`;
  `commands/` has command files that are non-empty. A registered directory
  holding nothing loadable is the failure this catches -- the directory
  existing is not evidence it ships anything.
* **X05** (fail) -- agent names in the Agent Roster table
  (`skills/software-planning/references/coordination-details.md`'s
  `## Agent Roster`) match `agents/*.md` file stems 1:1, both directions.
* **X06** (fail) -- agent names in `agents/README.md`'s agent table (the one
  with a `Description` header -- not the `## Loop Participation` table further
  down, which has a different header shape) match `agents/*.md` file stems
  1:1, both directions.
* **EC01** (fail) -- agent names in the pipeline-diagram source
  (`agents/diagrams/agent-pipeline-flowchart/src/agent-pipeline-flowchart.mmd`)
  each resolve to an existing agent file. One-directional: the diagram depicts
  the *forward* pipeline only, so an agent legitimately absent from it (e.g.
  `roadmap-cartographer`, an on-demand audit tool outside the forward flow) is
  not itself a finding.
* **EC02** (warn) -- every skill, command, and rule is referenced by at least
  one of `agents/*.md`, root `CLAUDE.md`, `claude/config/CLAUDE.md.tmpl`, or
  `rules/**/*.md`. Reference detection is a plain substring search against the
  concatenated text of those surfaces -- deliberately liberal, since EC02 is
  advisory (WARN): a missed reference (false negative) is the safe direction
  of error here, not a phantom orphan (false positive) that would teach a
  reader to ignore the dimension. A rule is excluded from its own haystack
  when checked, so a rule cannot "reference" itself merely by existing.

`agents/*.md` and `commands/*.md` each exclude `README.md` and `CLAUDE.md` --
neither is the artifact type its glob names (an index page and a
project-instructions file, respectively); the same exclusion X01's sibling
C05 already applies to agents. `rules/**/*.md` excludes `README.md` from the
*artifact* list (it is a catalog page, not a rule) but keeps it in the
*surface* list EC02 searches, since it is a legitimate place a rule name
could be cited.

Skip conditions (DS-A, keyed): each check skips independently when its own
substrate file/dir is absent -- the six checks read six different surfaces
and one surface's absence says nothing about the other five.

Invocation:

    check_registry_projection.py                  # human-readable summary
    check_registry_projection.py --json           # machine-readable envelope
    check_registry_projection.py --check          # exit 1 on any finding
    check_registry_projection.py --repo-root DIR  # operate on another checkout

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
SCRIPT_NAME = "check_registry_projection"

CHECK_IDS: tuple[str, ...] = ("X01", "X02", "X05", "X06", "EC01", "EC02")

_PLUGIN_JSON_REL = ".claude-plugin/plugin.json"
_ROSTER_REL = "skills/software-planning/references/coordination-details.md"
_README_REL = "agents/README.md"
_AGENTS_DIR_REL = "agents"
_SKILLS_DIR_REL = "skills"
_COMMANDS_DIR_REL = "commands"
_RULES_DIR_REL = "rules"
_DIAGRAM_REL = "agents/diagrams/agent-pipeline-flowchart/src/agent-pipeline-flowchart.mmd"
_CLAUDE_MD_REL = "CLAUDE.md"
_CLAUDE_TMPL_REL = "claude/config/CLAUDE.md.tmpl"

# Neither file is the artifact type its directory's glob names: an index page
# and a project-instructions file, not an agent/command/rule.
_EXCLUDED_META_FILES = {"README.md", "CLAUDE.md"}

_H2_HEADING = re.compile(r"^##\s")
_ROSTER_HEADING = re.compile(r"^##\s*Agent Roster\b")
_ROSTER_ROW_NAME = re.compile(r"^\|\s*`([a-z][a-z0-9-]*)`")
_README_TABLE_HEADER = re.compile(r"^\|\s*Agent\s*\|\s*Description\s*\|")
_MERMAID_NODE_RE = re.compile(r'\["([a-z][a-z0-9-]*)')

logger = logging.getLogger(SCRIPT_NAME)


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _agent_file_stems(repo_root: Path) -> set[str] | None:
    agents_dir = repo_root / _AGENTS_DIR_REL
    if not agents_dir.is_dir():
        return None
    return {p.stem for p in agents_dir.glob("*.md") if p.name not in _EXCLUDED_META_FILES}


# -- X01: plugin.json agent paths resolve --------------------------------------


def _check_x01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
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
    findings: list[dict] = []
    for entry in agents:
        if not isinstance(entry, str):
            findings.append(
                {
                    "check": "X01",
                    "severity": "fail",
                    "entity": str(entry),
                    "message": "agents array entry is not a string path",
                }
            )
            continue
        if not (repo_root / entry.lstrip("./")).is_file():
            findings.append(
                {
                    "check": "X01",
                    "severity": "fail",
                    "entity": entry,
                    "message": f"'{entry}' does not resolve to an existing file",
                }
            )
    return findings, None, {"agents_count": len(agents)}


# -- X02: skills/commands hold loadable artifacts --------------------------------


def _check_x02(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    skills_dir = repo_root / _SKILLS_DIR_REL
    commands_dir = repo_root / _COMMANDS_DIR_REL
    if not skills_dir.is_dir() and not commands_dir.is_dir():
        return (
            [],
            {"reason": "substrate-absent", "path": f"{skills_dir} and {commands_dir}"},
            None,
        )

    findings: list[dict] = []
    examined: dict = {}

    if skills_dir.is_dir():
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        examined["skill_dirs"] = len(skill_dirs)
        for d in skill_dirs:
            if not (d / "SKILL.md").is_file():
                findings.append(
                    {
                        "check": "X02",
                        "severity": "fail",
                        "entity": f"skills/{d.name}",
                        "message": f"skill dir '{d.name}' has no SKILL.md",
                    }
                )

    if commands_dir.is_dir():
        command_files = [f for f in commands_dir.glob("*.md") if f.name not in _EXCLUDED_META_FILES]
        examined["command_files"] = len(command_files)
        for f in command_files:
            if f.stat().st_size == 0:
                findings.append(
                    {
                        "check": "X02",
                        "severity": "fail",
                        "entity": f"commands/{f.name}",
                        "message": f"command file '{f.name}' is empty",
                    }
                )

    return findings, None, examined


# -- X05/X06: roster/README table matches agents/ 1:1 ----------------------------


def _heading_span(text: str, heading: re.Pattern[str]) -> list[str] | None:
    """Lines from a matched heading through the line before the next `## ` heading."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if heading.match(line))
    except StopIteration:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _H2_HEADING.match(line):
            break
        body.append(line)
    return body


def _row_names(lines: list[str], pattern: re.Pattern[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        match = pattern.match(line)
        if match:
            names.add(match.group(1))
    return names


def _readme_agent_table_rows(text: str) -> list[str] | None:
    """Rows of the agent table (`| Agent | Description | ... |`), header/separator excluded.

    Distinct from `## Loop Participation`'s table further down, which shares the
    `Agent` first column but a different second-column header
    (`Forward pipeline role`) -- matching on the `Description` header keeps the
    two from being conflated.
    """
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _README_TABLE_HEADER.match(line))
    except StopIteration:
        return None
    rows: list[str] = []
    i = start + 2  # skip header row + `|---|---|` separator row
    while i < len(lines) and lines[i].startswith("|"):
        rows.append(lines[i])
        i += 1
    return rows


def _two_way_findings(check_id: str, table_names: set[str], file_stems: set[str]) -> list[dict]:
    findings: list[dict] = []
    for name in sorted(table_names - file_stems):
        findings.append(
            {
                "check": check_id,
                "severity": "fail",
                "entity": name,
                "message": f"table names `{name}` with no matching agents/{name}.md",
            }
        )
    for name in sorted(file_stems - table_names):
        findings.append(
            {
                "check": check_id,
                "severity": "fail",
                "entity": name,
                "message": f"agents/{name}.md has no matching table row",
            }
        )
    return findings


def _check_x05(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _ROSTER_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None
    span = _heading_span(text, _ROSTER_HEADING)
    if span is None:
        finding = {
            "check": "X05",
            "severity": "fail",
            "entity": str(path),
            "message": "'## Agent Roster' heading not found",
        }
        return [finding], None, None
    file_stems = _agent_file_stems(repo_root)
    if file_stems is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / _AGENTS_DIR_REL)}, None
    roster_names = _row_names(span, _ROSTER_ROW_NAME)
    findings = _two_way_findings("X05", roster_names, file_stems)
    return findings, None, {"roster_names": len(roster_names), "file_stems": len(file_stems)}


def _check_x06(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _README_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None
    rows = _readme_agent_table_rows(text)
    if rows is None:
        finding = {
            "check": "X06",
            "severity": "fail",
            "entity": str(path),
            "message": "agent table (`| Agent | Description | ... |`) not found",
        }
        return [finding], None, None
    file_stems = _agent_file_stems(repo_root)
    if file_stems is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / _AGENTS_DIR_REL)}, None
    table_names = _row_names(rows, _ROSTER_ROW_NAME)
    findings = _two_way_findings("X06", table_names, file_stems)
    return findings, None, {"table_names": len(table_names), "file_stems": len(file_stems)}


# -- EC01: pipeline diagram agents have files ------------------------------------


def _check_ec01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _DIAGRAM_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None
    file_stems = _agent_file_stems(repo_root)
    if file_stems is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / _AGENTS_DIR_REL)}, None
    diagram_names = sorted(set(_MERMAID_NODE_RE.findall(text)))
    findings = [
        {
            "check": "EC01",
            "severity": "fail",
            "entity": name,
            "message": f"diagram node '{name}' has no matching agents/{name}.md",
        }
        for name in diagram_names
        if name not in file_stems
    ]
    return findings, None, {"diagram_names": len(diagram_names)}


# -- EC02: no orphaned artifacts --------------------------------------------------


def _reference_pairs(repo_root: Path) -> list[tuple[Path, str]]:
    """`(path, text)` for every reference surface EC02 searches, unreadable ones dropped."""
    agents_dir = repo_root / _AGENTS_DIR_REL
    rules_dir = repo_root / _RULES_DIR_REL
    candidate_paths = [repo_root / _CLAUDE_MD_REL, repo_root / _CLAUDE_TMPL_REL]
    if agents_dir.is_dir():
        candidate_paths.extend(sorted(agents_dir.glob("*.md")))
    if rules_dir.is_dir():
        candidate_paths.extend(sorted(rules_dir.glob("**/*.md")))
    # Widened surfaces (P2.1 residual wrap-up): a skill named by a command, by another
    # skill, or by the docs tree is not an orphan -- the narrower agents+CLAUDE.md+rules
    # set produced 30 false "orphans" per sweep against a corpus where every one of them
    # was referenced somewhere shipped. Each artifact's OWN files are excluded from its
    # haystack by the per-artifact callers below, so a skill cannot reference itself.
    for rel in (_COMMANDS_DIR_REL, _SKILLS_DIR_REL, "docs"):
        d = repo_root / rel
        if d.is_dir():
            candidate_paths.extend(sorted(d.glob("**/*.md")))
    pairs: list[tuple[Path, str]] = []
    for p in candidate_paths:
        text = _read_text(p)
        if text is not None:
            pairs.append((p, text))
    return pairs


def _haystack_excluding(pairs: list[tuple[Path, str]], own: Path) -> str:
    """Every reference surface's text except files under (or equal to) `own`."""
    return "\n".join(text for p, text in pairs if not (p == own or p.is_relative_to(own)))


def _check_ec02_skills(repo_root: Path, pairs: list[tuple[Path, str]]) -> tuple[list[dict], int]:
    """`(findings, examined_count)` for every skill dir against the other surfaces' text."""
    findings: list[dict] = []
    examined = 0
    skills_dir = repo_root / _SKILLS_DIR_REL
    if not skills_dir.is_dir():
        return findings, examined
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").is_file():
            continue
        examined += 1
        if d.name not in _haystack_excluding(pairs, d):
            findings.append(
                {
                    "check": "EC02",
                    "severity": "warn",
                    "entity": f"skills/{d.name}",
                    "message": f"skill '{d.name}' is not referenced by any agent, CLAUDE.md, rule, command, skill or doc",
                }
            )
    return findings, examined


def _check_ec02_commands(repo_root: Path, pairs: list[tuple[Path, str]]) -> tuple[list[dict], int]:
    """`(findings, examined_count)` for every command file against the other surfaces' text."""
    findings: list[dict] = []
    examined = 0
    commands_dir = repo_root / _COMMANDS_DIR_REL
    if not commands_dir.is_dir():
        return findings, examined
    for f in sorted(commands_dir.glob("*.md")):
        if f.name in _EXCLUDED_META_FILES:
            continue
        examined += 1
        if f.stem not in _haystack_excluding(pairs, f):
            findings.append(
                {
                    "check": "EC02",
                    "severity": "warn",
                    "entity": f"commands/{f.name}",
                    "message": f"command '{f.stem}' is not referenced by any agent, CLAUDE.md, rule, command, skill or doc",
                }
            )
    return findings, examined


def _check_ec02_rules(repo_root: Path, pairs: list[tuple[Path, str]]) -> tuple[list[dict], int]:
    """`(findings, examined_count)` for every rule, checked against the other pairs' text."""
    findings: list[dict] = []
    examined = 0
    rules_dir = repo_root / _RULES_DIR_REL
    for path, _ in pairs:
        if not path.is_relative_to(rules_dir) or path.name in _EXCLUDED_META_FILES:
            continue
        examined += 1
        other_text = "\n".join(text for p, text in pairs if p != path)
        if path.stem not in other_text:
            findings.append(
                {
                    "check": "EC02",
                    "severity": "warn",
                    "entity": str(path.relative_to(repo_root)),
                    "message": f"rule '{path.stem}' is not referenced by any agent, "
                    "CLAUDE.md, or another rule",
                }
            )
    return findings, examined


def _check_ec02(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    pairs = _reference_pairs(repo_root)
    if not pairs:
        return (
            [],
            {"reason": "substrate-absent", "path": "agents/CLAUDE.md/rules surfaces"},
            None,
        )
    findings: list[dict] = []
    examined = {"skills": 0, "commands": 0, "rules": 0}

    skill_findings, examined["skills"] = _check_ec02_skills(repo_root, pairs)
    findings.extend(skill_findings)

    command_findings, examined["commands"] = _check_ec02_commands(repo_root, pairs)
    findings.extend(command_findings)

    rule_findings, examined["rules"] = _check_ec02_rules(repo_root, pairs)
    findings.extend(rule_findings)

    return findings, None, examined


# -- Envelope (DS-A, keyed) -----------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    for check_id, fn in (
        ("X01", _check_x01),
        ("X02", _check_x02),
        ("X05", _check_x05),
        ("X06", _check_x06),
        ("EC01", _check_ec01),
        ("EC02", _check_ec02),
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
            "X01": "X01 clean means every plugin.json agents-array path resolves to a file.",
            "X02": (
                "X02 clean means every skill dir has a SKILL.md and every command "
                "file is non-empty."
            ),
            "X05": "X05 clean means the Agent Roster table and agents/*.md agree 1:1.",
            "X06": "X06 clean means agents/README.md's agent table and agents/*.md agree 1:1.",
            "EC01": "EC01 clean means every pipeline-diagram node resolves to an agent file.",
            "EC02": "EC02 clean means every skill/command/rule is referenced somewhere.",
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: registry-projection checks. Called by sentinel X01/X02/X05/X06/EC01/EC02."
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
