#!/usr/bin/env python3
"""DL01/DL02/SH01/SH02/CA01: decision-log, spec-health and calibration corpus checks.

One substrate walk over `.ai-state/decisions/`, `.ai-state/specs/` and
`.ai-state/calibration_log.md`, amortized across five checks (`DL03` is
**not** here -- it re-points to `regenerate_adr_index.py --check`, a
functionally-complete existing script, not a new corpus walk).

* **DL01** (warn) -- `.ai-state/decisions/` has ADR files in either lifecycle
  stage whenever `.ai-state/specs/` holds archived specs. A **three-way OR**,
  evaluated explicitly rather than folded into an AND: (a) a finalized ADR
  (`^\\d{3}-.+\\.md$`) exists, OR (b) a draft fragment
  (`^\\d{8}-\\d{4}-[a-z0-9-]+-[a-z0-9-]+-[a-z0-9-]+\\.md$`) exists, OR (c) no
  archived specs exist at all -- in which case the check has nothing to
  reconcile and passes vacuously. Only when specs exist and *neither* ADR
  form is present does the check fire: a project doing spec-driven work that
  has recorded zero decisions.
* **DL02** (fail) -- every ADR (finalized or draft) carries all eight
  required frontmatter fields (`id`, `title`, `status`, `category`, `date`,
  `summary`, `tags`, `made_by`), **present and non-empty**. An empty `tags:
  []` counts as absent, the same standard S02 applies to agent frontmatter.
  This is deliberately narrower than `check_adr_frontmatter_promotion.py`,
  which already owns the `id`-format / `status`-transition clause for
  finalized ADRs (td-103) -- re-deriving that here would duplicate it.
* **SH01** (warn/fail) -- persistent specs' path-bearing columns resolve.
  **Convention enforced:** in the Traceability Matrix and Requirements
  section of a spec, the column whose header names *implementation* (matched
  case-insensitively on the substring "implement" -- "Implementation",
  "Implementing artifact", ...) holds repo-root-relative file/dir paths only.
  A cell with no backtick-quoted token is itself a non-conforming finding
  (warn) -- prose masquerading as a path claim. A backtick token that is not
  path-shaped (a `::` pointer, a glob, a shell command, a branch name) is
  the same non-conforming finding (warn) -- those belong in an adjacent
  prose column (Test(s)/Notes/Verification), which this check never scans.
  A path-shaped token that does not resolve on disk is a dangling reference
  (fail). An em-dash cell (`—`, optionally with trailing parenthetical
  prose) claims no path and is skipped.
* **SH02** (fail) -- every persistent spec's `## Traceability...` section
  contains a markdown table with >=1 data row. A section with prose only (no
  table, or a table with a header and separator but zero data rows) fires.
* **CA01** (fail) -- `.ai-state/calibration_log.md` exists, its header
  matches the registered `calibration` table's columns, and it holds >=1
  data row. Reuses `state_ledger_schema`'s already-registered `LedgerSpec`
  for this file (`td-195`) rather than re-declaring the column tuple.

Skip conditions, per check independently (DS-A, keyed):
`.ai-state/decisions/` absent -> DL01, DL02 skip; `.ai-state/specs/` absent
or holding no `SPEC_*.md` -> SH01, SH02 skip; `.ai-state/calibration_log.md`
absent -> CA01 skips. PyYAML absence (GL05) skips only DL02 -- the other
four checks need no YAML parser and keep running.

Invocation:

    check_state_corpus.py                  # human-readable summary
    check_state_corpus.py --json           # machine-readable envelope
    check_state_corpus.py --check          # exit 1 on any finding
    check_state_corpus.py --repo-root DIR  # operate on another checkout
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging
from state_ledger_schema import LEDGERS, parse_ledger, split_row

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_state_corpus"

CHECK_IDS: tuple[str, ...] = ("DL01", "DL02", "SH01", "SH02", "CA01")

_FINALIZED_ADR = re.compile(r"^\d{3}-.+\.md$")
_DRAFT_FRAGMENT = re.compile(r"^\d{8}-\d{4}-[a-z0-9-]+-[a-z0-9-]+-[a-z0-9-]+\.md$")
_REQUIRED_ADR_FIELDS = ("id", "title", "status", "category", "date", "summary", "tags", "made_by")
_ADR_FRONTMATTER = re.compile(r"\A---\n(.*?\n)---(?:\n|\Z)", re.DOTALL)

_SECTION_HEADING = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
_SEPARATOR_ROW = re.compile(r"^\|[\s:|-]+\|?\s*$")
_BACKTICK_TOKEN = re.compile(r"`([^`]+)`")
_PATH_SHAPE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
_HAS_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,10}$")
_CALIBRATION_LOG_SUFFIX = "calibration_log.md"

logger = logging.getLogger(SCRIPT_NAME)


class MissingParserError(RuntimeError):
    """Raised when PyYAML is absent from the running interpreter."""


def _require_yaml() -> Any:
    """Import PyYAML, or raise naming the interpreter that lacks it (GL05-deferred)."""
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via canary
        raise MissingParserError(
            f"PyYAML is required to parse ADR frontmatter, and {sys.executable} does "
            f"not have it. Run under the project environment (e.g. `uv run --with "
            f"pyyaml python {Path(__file__).name}`) or install pyyaml."
        ) from exc
    return yaml


# -- DL01/DL02: decision log ------------------------------------------------------


def _check_dl01(
    archived_specs: list[Path], finalized: list[Path], drafts: list[Path]
) -> list[dict]:
    if not archived_specs:
        return []  # arm 3: no archived specs -- nothing to reconcile
    if finalized or drafts:
        return []  # arm 1 or arm 2 satisfied
    return [
        {
            "check": "DL01",
            "severity": "warn",
            "entity": ".ai-state/decisions/",
            "message": (
                f"{len(archived_specs)} archived spec(s) exist under .ai-state/specs/ "
                "but .ai-state/decisions/ has no ADR files in either lifecycle stage"
            ),
        }
    ]


def _check_dl02(adr_path: Path, repo_root: Path, yaml_module: Any) -> list[dict]:
    rel = adr_path.relative_to(repo_root).as_posix()
    text = adr_path.read_text(encoding="utf-8")
    match = _ADR_FRONTMATTER.match(text)
    if match is None:
        return [
            {
                "check": "DL02",
                "severity": "fail",
                "entity": rel,
                "message": f"{rel}: no YAML frontmatter block",
            }
        ]
    try:
        data = yaml_module.safe_load(match.group(1))
    except yaml_module.YAMLError:
        return [
            {
                "check": "DL02",
                "severity": "fail",
                "entity": rel,
                "message": f"{rel}: frontmatter does not parse as YAML",
            }
        ]
    if not isinstance(data, dict):
        return [
            {
                "check": "DL02",
                "severity": "fail",
                "entity": rel,
                "message": f"{rel}: frontmatter is not a mapping",
            }
        ]
    missing = [field for field in _REQUIRED_ADR_FIELDS if not data.get(field)]
    if not missing:
        return []
    return [
        {
            "check": "DL02",
            "severity": "fail",
            "entity": rel,
            "message": f"{rel}: missing or empty frontmatter field(s): {', '.join(missing)}",
        }
    ]


# -- SH01/SH02: spec health --------------------------------------------------------


def _sections(text: str) -> list[tuple[str, str]]:
    """Return `(heading, body)` for each H2 section, in document order."""
    headings = list(_SECTION_HEADING.finditer(text))
    result = []
    for index, heading in enumerate(headings):
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        result.append((heading.group(1).strip(), text[start:end]))
    return result


def _tables(body: str) -> list[tuple[list[str], list[list[str]]]]:
    """Return every `(header_cells, data_rows)` markdown table found in `body`."""
    lines = body.splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index < len(lines):
        if (
            _TABLE_ROW.match(lines[index])
            and index + 1 < len(lines)
            and _SEPARATOR_ROW.match(lines[index + 1])
        ):
            header = split_row(lines[index])
            cursor = index + 2
            rows: list[list[str]] = []
            while cursor < len(lines) and _TABLE_ROW.match(lines[cursor]):
                rows.append(split_row(lines[cursor]))
                cursor += 1
            tables.append((header, rows))
            index = cursor
        else:
            index += 1
    return tables


def _looks_like_path_token(token: str) -> bool:
    if not _PATH_SHAPE.match(token):
        return False
    return bool(_HAS_EXTENSION.search(token)) or token.endswith("/")


def _check_path_cell(spec_rel: str, repo_root: Path, cell: str) -> list[dict]:
    stripped = cell.strip()
    if not stripped or stripped.startswith("—") or stripped == "-":
        return []  # no path claimed
    tokens = _BACKTICK_TOKEN.findall(stripped)
    if not tokens:
        return [
            {
                "check": "SH01",
                "severity": "warn",
                "entity": spec_rel,
                "message": f"{spec_rel}: path-column cell '{stripped}' carries no backtick-quoted path",
            }
        ]
    findings: list[dict] = []
    for token in tokens:
        if not _looks_like_path_token(token):
            findings.append(
                {
                    "check": "SH01",
                    "severity": "warn",
                    "entity": spec_rel,
                    "message": f"{spec_rel}: path-column token `{token}` is not a repo-root-relative path",
                }
            )
            continue
        if not (repo_root / token).exists():
            findings.append(
                {
                    "check": "SH01",
                    "severity": "fail",
                    "entity": spec_rel,
                    "message": f"{spec_rel}: path-column reference `{token}` does not resolve",
                }
            )
    return findings


def _check_sh01(spec_path: Path, repo_root: Path) -> list[dict]:
    spec_rel = spec_path.relative_to(repo_root).as_posix()
    text = spec_path.read_text(encoding="utf-8")
    findings: list[dict] = []
    for heading, body in _sections(text):
        lowered = heading.lower()
        if not (lowered.startswith("traceability") or lowered.startswith("requirements")):
            continue
        for header, rows in _tables(body):
            path_columns = [i for i, name in enumerate(header) if "implement" in name.lower()]
            if not path_columns:
                continue
            for row in rows:
                for col in path_columns:
                    if col < len(row):
                        findings.extend(_check_path_cell(spec_rel, repo_root, row[col]))
    return findings


def _check_sh02(spec_path: Path, repo_root: Path) -> list[dict]:
    spec_rel = spec_path.relative_to(repo_root).as_posix()
    text = spec_path.read_text(encoding="utf-8")
    trace_bodies = [
        body for heading, body in _sections(text) if heading.lower().startswith("traceability")
    ]
    if not trace_bodies:
        return [
            {
                "check": "SH02",
                "severity": "fail",
                "entity": spec_rel,
                "message": f"{spec_rel}: no '## Traceability...' section found",
            }
        ]
    for body in trace_bodies:
        for _header, rows in _tables(body):
            if rows:
                return []
    return [
        {
            "check": "SH02",
            "severity": "fail",
            "entity": spec_rel,
            "message": f"{spec_rel}: Traceability section has no matrix with >=1 requirement row",
        }
    ]


# -- CA01: calibration accuracy -----------------------------------------------------


def _calibration_spec():
    return next(spec for spec in LEDGERS if spec.path.endswith(_CALIBRATION_LOG_SUFFIX))


def _check_ca01(repo_root: Path) -> list[dict]:
    parsed = parse_ledger(repo_root, _calibration_spec())
    if "calibration" in parsed.missing_tables:
        return [
            {
                "check": "CA01",
                "severity": "fail",
                "entity": ".ai-state/calibration_log.md",
                "message": ".ai-state/calibration_log.md: header row does not match the expected columns",
            }
        ]
    if not parsed.rows:
        return [
            {
                "check": "CA01",
                "severity": "fail",
                "entity": ".ai-state/calibration_log.md",
                "message": ".ai-state/calibration_log.md: no data rows",
            }
        ]
    return []


# -- Envelope (DS-A, keyed) -------------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    # -- decisions family (DL01, DL02) --------------------------------------
    decisions_dir = repo_root / ".ai-state" / "decisions"
    specs_dir = repo_root / ".ai-state" / "specs"
    if not decisions_dir.is_dir():
        reason = {"reason": "substrate-absent", "path": str(decisions_dir)}
        skipped["DL01"] = reason
        skipped["DL02"] = reason
    else:
        finalized = sorted(p for p in decisions_dir.glob("*.md") if _FINALIZED_ADR.match(p.name))
        drafts_dir = decisions_dir / "drafts"
        drafts = (
            sorted(p for p in drafts_dir.glob("*.md") if _DRAFT_FRAGMENT.match(p.name))
            if drafts_dir.is_dir()
            else []
        )
        archived_specs = sorted(specs_dir.glob("SPEC_*.md")) if specs_dir.is_dir() else []
        examined["DL01"] = {
            "finalized": len(finalized),
            "drafts": len(drafts),
            "archived_specs": len(archived_specs),
        }
        findings.extend(_check_dl01(archived_specs, finalized, drafts))

        adr_files = finalized + drafts
        if not adr_files:
            examined["DL02"] = {"adrs": 0}
        else:
            try:
                yaml_module = _require_yaml()
            except MissingParserError as exc:
                skipped["DL02"] = {"reason": "missing-yaml-parser", "path": str(exc)}
            else:
                examined["DL02"] = {"adrs": len(adr_files)}
                for adr in adr_files:
                    findings.extend(_check_dl02(adr, repo_root, yaml_module))

    # -- spec health (SH01, SH02) --------------------------------------------
    persistent_specs = sorted(specs_dir.glob("SPEC_*.md")) if specs_dir.is_dir() else []
    if not persistent_specs:
        reason = {"reason": "substrate-absent", "path": str(specs_dir)}
        skipped["SH01"] = reason
        skipped["SH02"] = reason
    else:
        examined["SH01"] = {"specs": len(persistent_specs)}
        examined["SH02"] = {"specs": len(persistent_specs)}
        for spec in persistent_specs:
            findings.extend(_check_sh01(spec, repo_root))
            findings.extend(_check_sh02(spec, repo_root))

    # -- calibration accuracy (CA01) -----------------------------------------
    calibration_path = repo_root / ".ai-state" / "calibration_log.md"
    if not calibration_path.is_file():
        skipped["CA01"] = {"reason": "substrate-absent", "path": str(calibration_path)}
    else:
        examined["CA01"] = {"present": True}
        findings.extend(_check_ca01(repo_root))

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": skipped,
        "examined": examined,
        "findings": findings,
        "info": {},
        "withheld": [],
        "bound": {
            "DL01": "DL01 clean means specs-with-no-ADRs drift never occurs.",
            "DL02": "DL02 clean means every ADR carries all 8 required, non-empty fields.",
            "SH01": "SH01 clean means every spec's implementation-column path resolves.",
            "SH02": "SH02 clean means every spec carries a non-empty traceability matrix.",
            "CA01": "CA01 clean means calibration_log.md parses with >=1 data row.",
        },
    }


# -- CLI ----------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: decision-log, spec-health and calibration corpus checks. "
            "Called by sentinel DL01/DL02/SH01/SH02/CA01."
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
