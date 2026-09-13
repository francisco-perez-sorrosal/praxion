#!/usr/bin/env python3
"""BC01/BC03/BC04/BC05: behavioral-contract family.

Four checks, one shared concern: the four-behavior agent behavioral
contract is single-sourced in one always-loaded rule, and that
single-sourcing has not silently drifted.

* **BC01** (fail) -- `rules/swe/agent-behavioral-contract.md` exists, carries
  no `paths:` YAML frontmatter key (so it stays always-loaded rather than
  path-scoped), and names all four canonical behaviors: Surface Assumptions,
  Register Objection, Stay Surgical, Simplicity First.
* **BC03** (fail) -- every one of the contract-bound agents (the roster in
  `_BC03_EXPECTED_AGENTS`) cites
  `rules/swe/agent-behavioral-contract.md` somewhere in its own `.md` file,
  and no agent outside that list cites it. Both directions are reported:
  a missing citation (a contract-bound agent that dropped the pointer) and
  an extra one (an agent added to the citing set without updating this
  canonical enumeration) are both drift.
* **BC04** (fail) -- `skills/code-review/references/report-template.md`
  carries a `### Behavioral Contract Findings` subsection naming all six
  canonical tags: `[UNSURFACED-ASSUMPTION]`, `[MISSING-OBJECTION]`,
  `[NON-SURGICAL]`, `[SCOPE-CREEP]`, `[BLOAT]`, `[DEAD-CODE-UNREMOVED]`.
* **BC05** (fail) -- one wording of the four behavior *definitions* exists in
  the working tree. The rule is the source; every other file carrying the
  definitions in *definition shape* (a markdown bullet opening with the bolded
  behavior name and a separator) is either a registered consumer whose lines
  are byte-identical to the source's in the source's own order, or an
  allowlisted exception. A file that is none of those three and carries three
  or more of the behaviors in definition shape is a new, unregistered wording
  -- the defect BC05 exists to catch. The scan is totalising: every file under
  the repository root is read, minus the declared out-of-scope prefixes, so a
  restatement cannot hide in a file type nobody thought to glob for.

Definition shape is a deliberately narrow predicate. Measured over the whole
tree, it selects the six files that actually restate the definitions with zero
false positives: every "c mention" site (an agent prompt naming a behavior, a
report template's tag list, an installer's name-only list) scores zero.

Declared limits -- accepted false negatives of the definition-shape predicate,
deliberately, so it stays a precise extractor rather than growing into a fuzzy
matcher that would need an allowlist of its own:

- `**Surface Assumptions.**` -- a period inside the bold span: the predicate
  requires the separator *after* the closing `**`.
- a numbered-list or heading restatement (`1. **Stay Surgical** -- ...`,
  `### Stay Surgical`): the bullet marker must be `-` or `*`.
- a restatement carrying no separator at all (`- **Stay Surgical** touch only
  what the change requires`) -- before this pipeline the two Codex sites' terse
  bullets scored two of four for exactly this reason; they are byte-bound
  consumers now.
- an indent deeper than eight spaces before the bullet marker (`         - **Stay
  Surgical** — ...`, nine spaces): the predicate allows at most eight.
- an EN-dash separator (`- **Stay Surgical** – ...`): only the em-dash, colon,
  hyphen and opening parenthesis are recognised after the closing `**`.
- prose and string-literal restatements, including the subagent-context hook's
  Python preamble: both allowlist entries score zero under the predicate today,
  which is why the allowlist is tested through a planted copy rather than
  through its live entries.
- anything under the out-of-scope prefixes in `_BC05_OUT_OF_SCOPE`: the
  pipeline and report trees (`.ai-state/`, `.ai-work/`), the eval corpus
  (`eval/`) whose fixtures quote the contract on purpose, two analysis
  document trees, and the two gitignored scratch trees (`tmp/`,
  `.claude/worktrees/`) that are not part of the tree BC05 governs. The scan
  walks the working tree minus those prefixes, not the index of tracked
  files: an untracked scratch copy outside them reddens the check locally
  (visible, never hidden) and cannot do so in CI.

`_BC03_EXPECTED_AGENTS` below is the canonical enumeration of contract-bound
agents -- a future single-sourcing pass (tracked separately) should have
every other citer of this list (this rule's own prose, agent prompts) read
from this one place rather than re-typing it; this script does not attempt
that restructuring itself.

All four checks are unconditional: the contract is an always-loaded
ecosystem invariant, not a feature gated by presence of specs or ADRs, so
none of the four ever skips.

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
import os
import re
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_behavioral_contract"

CHECK_IDS: tuple[str, ...] = ("BC01", "BC03", "BC04", "BC05")

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

# The canonical enumeration of the agents that write, plan, or review
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

# The files permitted to carry the four definitions in definition shape, byte-identical
# to the rule's own lines. Every entry is governed identically, so the registry is a flat
# set of repo-relative POSIX paths rather than a record with fields nothing reads.
_BC05_CONSUMERS: frozenset[str] = frozenset(
    {
        "claude/canonical-blocks/behavioral-contract.md",
        "skills/onboard-project/references/claude-md-blocks.md",
        "README.md",
        "codex/config/AGENTS.md.tmpl",
        "AGENTS.md",
    }
)

# Permitted to restate the definitions in their own deliberately distinct prose. Both
# entries score zero under the definition-shape predicate today (see the module
# docstring's declared limits); they are listed so a future reshaping of either file
# does not redden the gate, and the allowlist *mechanism* is proven by a planted copy.
_BC05_ALLOWLIST: frozenset[str] = frozenset(
    {
        "hooks/inject_subagent_context.py",
        "skills/software-planning/references/behavioral-contract.md",
    }
)

# Path prefixes BC05 does not govern. The first five are the declared policy scope
# (pipeline state, report trees, the eval corpus whose fixtures quote the contract on
# purpose, and two analysis document trees); the last two are gitignored scratch trees
# that are not part of the working tree BC05 reasons about -- without them the scan
# reports every nested worktree's own copies as unregistered wordings.
_BC05_OUT_OF_SCOPE: tuple[str, ...] = (
    ".ai-state/",
    ".ai-work/",
    "eval/",
    "docs/context-prj-comparison-",
    "docs/independent-analysis/",
    "tmp/",
    ".claude/worktrees/",
)

# Directory names never descended into: version control, dependency trees and caches.
# None can carry a tracked restatement, and walking them costs seconds per run.
_BC05_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".next",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)

# Three of four, not four: a file restating most of the contract is already a second
# wording, and the pre-pipeline Codex sites showed four-of-four is not reachable for terse
# copy (they are byte-bound consumers now).
_BC05_UNREGISTERED_THRESHOLD = 3

# Definition shape: a markdown bullet opening with the bolded behavior name, then a
# separator (em-dash, colon, hyphen or an opening parenthesis). Narrow on purpose --
# see the module docstring's declared limits for what it deliberately cannot see.
_BC05_DEFINITION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rf"^[ \t]{{0,8}}[-*][ \t]+\*\*{re.escape(name)}\*\*[ \t]*(—|:|-|\()"))
    for name in _BEHAVIOR_NAMES
)

logger = logging.getLogger(SCRIPT_NAME)


def _read_text(path: Path) -> str | None:
    """`None` when `path` is absent, unreadable, or not UTF-8 text.

    BC05's totalising scan reads every file in the tree, so undecodable bytes are an
    ordinary outcome rather than an error: nothing that fails to decode can carry a
    markdown bullet or a behavior name. A *registered* path's absence is a finding
    instead -- `_bc05_consumer_findings` tests for it explicitly.
    """
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


_PATHS_KEY_RE = re.compile(r'^["\']?paths["\']?\s*:')


def _has_paths_frontmatter(text: str) -> bool:
    """True if `text` opens with a YAML frontmatter block declaring `paths:`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        # A YAML key may be quoted or carry space before the colon (`"paths": …`,
        # `paths : …`): normalise the key the way a parser would, stdlib-only,
        # so the check agrees with regenerate_rules_manifest.py's yaml.safe_load
        # (light-review F1, W-1). Top-level keys only: an indented `paths:` is a
        # nested value, not the scoping key.
        if _PATHS_KEY_RE.match(line):
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


# -- BC03: exactly the roster of contract-bound agents cite the rule ----------


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


# -- BC05: one wording of the four definitions, repo-wide -----------------------


def _check_bc05(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    sites, files_scanned = _bc05_scan(repo_root)
    source_pairs = sites.get(_BC_RULE_REL, ())

    source_findings = _bc05_source_findings(source_pairs)
    # A source that does not parse into its own four lines cannot bind anything.
    # Saying so once is louder than five consumer findings derived from one cause.
    consumer_findings = (
        [] if source_findings else _bc05_consumer_findings(repo_root, sites, source_pairs)
    )
    findings = source_findings + consumer_findings + _bc05_unregistered_findings(sites)

    examined = {
        "files_scanned": files_scanned,
        "consumers": len(_BC05_CONSUMERS),
        "definition_sites": sum(len(pairs) for pairs in sites.values()),
        "distinct_wordings": _bc05_distinct_wordings(sites),
    }
    return findings, None, examined


def _definition_lines(text: str) -> tuple[tuple[str, str], ...]:
    """`text`'s definition-shape lines, as (behavior, line) pairs in order of appearance.

    Parsed once, at the point of read: the comparator never sees raw file text, and
    the order is carried by the tuple so a reordering is a divergence like any other.
    """
    found: list[tuple[str, str]] = []
    for line in text.splitlines():
        for name, pattern in _BC05_DEFINITION_PATTERNS:
            if pattern.match(line):
                found.append((name, line))
                break
    return tuple(found)


def _bc05_scan(repo_root: Path) -> tuple[dict[str, tuple[tuple[str, str], ...]], int]:
    """Every in-scope file's definition-shape lines, keyed by repo-relative POSIX path.

    Totalising by construction: no suffix filter and no include list, so a restatement
    cannot hide in a file type nobody thought to glob for. Returns the sites that
    carry at least one definition-shape line, plus the number of files examined.
    """
    sites: dict[str, tuple[tuple[str, str], ...]] = {}
    files_scanned = 0
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _BC05_SKIP_DIRS)
        for filename in sorted(filenames):
            rel = (Path(dirpath) / filename).relative_to(repo_root).as_posix()
            if rel.startswith(_BC05_OUT_OF_SCOPE):
                continue
            files_scanned += 1
            text = _read_text(repo_root / rel)
            pairs = _definition_lines(text) if text is not None else ()
            if pairs:
                sites[rel] = pairs
    return sites, files_scanned


def _bc05_source_findings(source_pairs: tuple[tuple[str, str], ...]) -> list[dict]:
    expected = len(_BEHAVIOR_NAMES)
    if len(source_pairs) == expected:
        return []
    return [
        _bc05_finding(
            _BC_RULE_REL,
            f"'{_BC_RULE_REL}' carries {len(source_pairs)} of the {expected} behaviors in "
            "definition shape -- BC05 has no source to bind its consumers to",
        )
    ]


def _bc05_consumer_findings(
    repo_root: Path,
    sites: dict[str, tuple[tuple[str, str], ...]],
    source_pairs: tuple[tuple[str, str], ...],
) -> list[dict]:
    findings: list[dict] = []
    for rel in sorted(_BC05_CONSUMERS):
        if not (repo_root / rel).is_file():
            findings.append(
                _bc05_finding(
                    rel,
                    f"registered BC05 consumer '{rel}' does not exist -- the registry "
                    "names a file the tree no longer carries",
                )
            )
            continue
        pairs = sites.get(rel, ())
        if len(pairs) != len(source_pairs):
            findings.append(
                _bc05_finding(
                    rel,
                    f"'{rel}' carries {len(pairs)} definition-shape behavior lines, "
                    f"{_BC_RULE_REL} carries {len(source_pairs)}",
                )
            )
            continue
        findings.extend(_bc05_divergence_findings(rel, pairs, source_pairs))
    return findings


def _bc05_divergence_findings(
    rel: str,
    pairs: tuple[tuple[str, str], ...],
    source_pairs: tuple[tuple[str, str], ...],
) -> list[dict]:
    """One finding per consumer line that is not the source's line, naming the behavior."""
    findings: list[dict] = []
    paired = zip(pairs, source_pairs, strict=True)  # equal length: the caller checked
    for position, (actual, expected) in enumerate(paired, start=1):
        if actual == expected:
            continue
        if actual[0] != expected[0]:
            message = (
                f"'{rel}' definition line {position} is '{actual[0]}' where "
                f"{_BC_RULE_REL} has '{expected[0]}' -- the lines must appear in the "
                "source's order"
            )
        else:
            message = f"'{rel}' line for '{expected[0]}' is not byte-identical to {_BC_RULE_REL}'s"
        findings.append(_bc05_finding(rel, message))
    return findings


def _bc05_unregistered_findings(sites: dict[str, tuple[tuple[str, str], ...]]) -> list[dict]:
    governed = _BC05_CONSUMERS | _BC05_ALLOWLIST | {_BC_RULE_REL}
    return [
        _bc05_finding(
            rel,
            f"'{rel}' carries {len(pairs)} of the {len(_BEHAVIOR_NAMES)} behaviors in "
            "definition shape but is neither the canonical rule, a registered BC05 "
            "consumer, nor allowlisted",
        )
        for rel, pairs in sorted(sites.items())
        if rel not in governed and len(pairs) >= _BC05_UNREGISTERED_THRESHOLD
    ]


def _bc05_distinct_wordings(sites: dict[str, tuple[tuple[str, str], ...]]) -> int:
    """The largest number of distinct wordings any one behavior carries across the scan.

    1 means one wording repo-wide (the goal); 0 means the scan found no site at all,
    which is itself reported rather than read as success -- a predicate that stopped
    matching would otherwise look identical to a clean corpus.
    """
    wordings: dict[str, set[str]] = {name: set() for name in _BEHAVIOR_NAMES}
    for rel, pairs in sites.items():
        if rel in _BC05_ALLOWLIST:
            continue
        for name, line in pairs:
            wordings[name].add(line)
    counts = [len(lines) for lines in wordings.values() if lines]
    return max(counts) if counts else 0


def _bc05_finding(entity: str, message: str) -> dict:
    return {"check": "BC05", "severity": "fail", "entity": entity, "message": message}


# -- Envelope (DS-A, keyed) -----------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    for check_id, fn in (
        ("BC01", _check_bc01),
        ("BC03", _check_bc03),
        ("BC04", _check_bc04),
        ("BC05", _check_bc05),
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
            "BC03": f"BC03 clean means exactly the {len(_BC03_EXPECTED_AGENTS)} contract-bound agents cite "
            "the rule -- no fewer, no more.",
            "BC04": "BC04 clean means the report template's Behavioral Contract "
            "Findings subsection names all six canonical tags.",
            "BC05": "BC05 clean means every file in the working tree (outside the declared "
            "out-of-scope prefixes) carrying ≥3 of the four behaviors in definition shape is the canonical rule, a registered "
            "consumer whose four lines are byte-identical to it in canonical order, or "
            "an allowlisted exception.",
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: behavioral-contract checks. Called by sentinel BC01/BC03/BC04/BC05."
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
