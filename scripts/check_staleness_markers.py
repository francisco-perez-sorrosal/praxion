#!/usr/bin/env python3
"""F07/F08/F09: skill staleness-marker discipline (`rules/swe/staleness-policy.md`).

Every skill declares its drift-prone sections in `SKILL.md` frontmatter
(`staleness_sensitive_sections`); each cataloged heading carries a
`<!-- last-verified: YYYY-MM-DD -->` HTML comment directly below it (no blank
line between). Three findings, one substrate walk:

* **F07** (WARN) -- a cataloged heading has no marker comment on the line
  below it at all (the "never verified" cold-start state).
* **F08** (WARN, escalating to FAIL beyond 2x the threshold) -- a marker's
  date is older than `staleness_threshold_days` (default 120; per-skill
  override in frontmatter).
* **F09** (FAIL) -- a marker exists but does not parse: an invalid date, a
  future date, or unrecognized comment syntax.

**Heading resolution follows progressive disclosure.** A cataloged heading's
text is matched against `SKILL.md` first, then the skill's `references/*.md`
(alphabetical), then its `contexts/*.md` (alphabetical) -- the first file
containing the heading is authoritative, since a section legitimately moves
out of `SKILL.md` under progressive disclosure and a marker found there is a
PASS, not a miss.

**`permanent` markers never age.** `<!-- last-verified: permanent -->` is
excluded from F08 entirely (reserved for structural/naming conventions, per
the policy).

**One narrow F09 exclusion: the template placeholder.** A marker whose date
is the literal token `[YYYY-MM-DD]`, sitting in a `_`-prefixed blank-slate
template file directly under a skill's `references/` directory, names no
date and cannot age -- it is a template placeholder, not a marker, and is
excluded from F07/F08/F09 and from the skill's marker count. The exclusion
keys on the placeholder token *and* the `_`-filename convention together,
precisely so a typo'd real date can never be mistaken for a template. Any
other unparseable date is still F09.

Skip conditions (exit 0, `skipped.<id>` set for all three ids): `skills/` is
absent from `repo_root`.

PyYAML dependency (gate-liveness GL05): deferred behind `_require_yaml`, same
pattern as `check_frontmatter_parses.py` -- a bare `python3` invocation
without PyYAML raises naming `sys.executable` instead of reporting clean.

Invocation:

    check_staleness_markers.py                  # human-readable summary
    check_staleness_markers.py --json           # machine-readable envelope
    check_staleness_markers.py --check          # exit 1 on any finding
    check_staleness_markers.py --repo-root DIR  # operate on another checkout

Exit code: 0 by default (advisory), 1 with --check when findings exist, 2
when PyYAML is unavailable or the resolved root is a plugin-cache path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_staleness_markers"

CHECK_IDS: tuple[str, ...] = ("F07", "F08", "F09")

_DEFAULT_THRESHOLD_DAYS = 120
_PERMANENT = "permanent"
_PLACEHOLDER_DATE = "[YYYY-MM-DD]"

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_MARKER_PREFIX = re.compile(r"<!--\s*last-verified\s*:")
_MARKER_FULL = re.compile(r"^\s*<!--\s*last-verified:\s*(?P<body>.+?)\s*-->\s*$")
_DATE_TOKEN = re.compile(r"^(?P<date>\S+)(?:\s+by:\s*\S+)?(?:\s+note:\s*.*)?$")

logger = logging.getLogger(SCRIPT_NAME)


class MissingParserError(RuntimeError):
    """Raised when PyYAML is absent from the running interpreter."""


def _require_yaml() -> Any:
    """Import PyYAML, or raise naming the interpreter that lacks it.

    Deferred rather than module-level so this file stays importable under an
    interpreter without PyYAML (GL05) -- only the code path that actually
    needs a parser fails, and it fails loudly rather than reporting clean.
    """
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via canary
        raise MissingParserError(
            f"PyYAML is required to read staleness_sensitive_sections, and "
            f"{sys.executable} does not have it. Run under the project environment "
            f"(e.g. `uv run --with pyyaml python {Path(__file__).name}`) or install "
            "pyyaml into the interpreter above."
        ) from exc
    return yaml


# -- Frontmatter -----------------------------------------------------------------


def _load_skill_config(skill_md: Path, yaml_module: Any) -> tuple[list[str], int] | None:
    """Return `(cataloged_headings, threshold_days)`, or None if not applicable.

    None covers: no frontmatter, unparseable frontmatter, not a mapping, or no
    `staleness_sensitive_sections` list -- a skill with none of these declared
    simply contributes no sections to the walk, not a withheld entry.
    """
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    try:
        data = yaml_module.safe_load(match.group(1))
    except yaml_module.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    sections = data.get("staleness_sensitive_sections")
    if not isinstance(sections, list) or not sections:
        return None
    threshold = data.get("staleness_threshold_days", _DEFAULT_THRESHOLD_DAYS)
    if not isinstance(threshold, int):
        threshold = _DEFAULT_THRESHOLD_DAYS
    return [str(s) for s in sections], threshold


# -- Heading resolution (SKILL.md -> references/ -> contexts/) -------------------


def _line_below_heading(text: str, heading: str) -> str | None:
    """Return the line directly below the first h2/h3 `heading`, or None if absent.

    An empty string is a legal return (the heading is the file's last line --
    no marker line follows, which is itself a missing-marker state).
    """
    pattern = re.compile(rf"^#{{2,3}}\s+{re.escape(heading)}\s*$")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if pattern.match(line):
            return lines[index + 1] if index + 1 < len(lines) else ""
    return None


def _locate_marker_line(skill_dir: Path, heading: str) -> tuple[Path, str] | None:
    """Search SKILL.md, then references/*.md, then contexts/*.md for `heading`."""
    candidates = [skill_dir / "SKILL.md"]
    for sub in ("references", "contexts"):
        sub_dir = skill_dir / sub
        if sub_dir.is_dir():
            candidates.extend(sorted(sub_dir.glob("*.md")))

    for path in candidates:
        if not path.is_file():
            continue
        marker_line = _line_below_heading(path.read_text(encoding="utf-8"), heading)
        if marker_line is not None:
            return path, marker_line
    return None


# -- Marker parsing ----------------------------------------------------------------


@dataclass(frozen=True)
class _MarkerStatus:
    """One marker's classification: kind plus the data each kind carries."""

    kind: str  # "missing" | "permanent" | "placeholder-excluded" | "valid" | "malformed"
    date: dt.date | None = None
    detail: str = ""


def _is_template_placeholder(resolved_path: Path) -> bool:
    """True iff `resolved_path` is a `_`-prefixed file directly under a `references/` dir.

    Both conditions together, deliberately -- keys on the placeholder token
    *and* the filename convention so a typo'd real date is never excused.
    """
    return resolved_path.parent.name == "references" and resolved_path.name.startswith("_")


def _parse_marker(line: str, resolved_path: Path, today: dt.date) -> _MarkerStatus:
    if not _MARKER_PREFIX.search(line):
        return _MarkerStatus(kind="missing")

    full_match = _MARKER_FULL.match(line)
    if full_match is None:
        return _MarkerStatus(kind="malformed", detail="marker comment syntax does not parse")

    date_match = _DATE_TOKEN.match(full_match.group("body"))
    if date_match is None:
        return _MarkerStatus(kind="malformed", detail="marker fields are out of the mandated order")

    token = date_match.group("date")

    if token == _PERMANENT:
        return _MarkerStatus(kind="permanent")

    if token == _PLACEHOLDER_DATE:
        if _is_template_placeholder(resolved_path):
            return _MarkerStatus(kind="placeholder-excluded")
        return _MarkerStatus(
            kind="malformed", detail=f"unresolved template placeholder {_PLACEHOLDER_DATE}"
        )

    try:
        date_value = dt.date.fromisoformat(token)
    except ValueError:
        return _MarkerStatus(kind="malformed", detail=f"'{token}' is not a valid YYYY-MM-DD date")

    if date_value > today:
        return _MarkerStatus(kind="malformed", detail=f"marker date {token} is in the future")

    return _MarkerStatus(kind="valid", date=date_value)


def _check_section(
    entity: str, status: _MarkerStatus, threshold_days: int, today: dt.date
) -> list[dict]:
    if status.kind == "missing":
        return [
            {
                "check": "F07",
                "severity": "warn",
                "entity": entity,
                "message": (
                    f"{entity}: cataloged section has no <!-- last-verified: --> marker "
                    "on the line below its heading"
                ),
            }
        ]
    if status.kind in ("permanent", "placeholder-excluded"):
        return []
    if status.kind == "malformed":
        return [
            {
                "check": "F09",
                "severity": "fail",
                "entity": entity,
                "message": f"{entity}: marker is invalid -- {status.detail}",
            }
        ]

    assert status.date is not None  # "valid" always carries a date
    age_days = (today - status.date).days
    if age_days > threshold_days * 2:
        return [
            {
                "check": "F08",
                "severity": "fail",
                "entity": entity,
                "message": (
                    f"{entity}: marker is {age_days}d old, exceeds 2x the "
                    f"{threshold_days}d threshold"
                ),
            }
        ]
    if age_days > threshold_days:
        return [
            {
                "check": "F08",
                "severity": "warn",
                "entity": entity,
                "message": f"{entity}: marker is {age_days}d old, exceeds the {threshold_days}d threshold",
            }
        ]
    return []


# -- Envelope (DS-A, keyed) -------------------------------------------------------


def classify(repo_root: Path) -> dict:
    """Build the F07/F08/F09 envelope over every skill's cataloged sections."""
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return _skipped_report("substrate-absent", str(skills_dir))

    yaml_module = _require_yaml()
    findings: list[dict] = []
    withheld: list[str] = []
    sections_examined = 0
    today = dt.date.today()

    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        config = _load_skill_config(skill_md, yaml_module)
        if config is None:
            continue
        headings, threshold_days = config

        for heading in headings:
            located = _locate_marker_line(skill_dir, heading)
            if located is None:
                withheld.append(
                    f"{skill_dir.name}::{heading}: heading not found in SKILL.md, "
                    "references/, or contexts/"
                )
                continue
            resolved_path, marker_line = located
            sections_examined += 1
            status = _parse_marker(marker_line, resolved_path, today)
            entity = f"{skill_dir.name}::{heading} ({resolved_path.relative_to(repo_root)})"
            findings.extend(_check_section(entity, status, threshold_days, today))

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": dict.fromkeys(CHECK_IDS),
        "examined": {cid: {"sections": sections_examined} for cid in CHECK_IDS},
        "findings": findings,
        "info": {},
        "withheld": withheld,
        "bound": {
            "F07": "F07 clean means every cataloged section carries a marker.",
            "F08": "F08 clean means every marker is within its skill's staleness threshold.",
            "F09": "F09 clean means every marker parses and is not future-dated.",
        },
    }


def _skipped_report(reason: str, path: str) -> dict:
    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {cid: {"reason": reason, "path": path} for cid in CHECK_IDS},
        "examined": dict.fromkeys(CHECK_IDS),
        "findings": [],
        "info": {},
        "withheld": [],
        "bound": {
            cid: f"{cid} did not run; no staleness conclusion can be drawn." for cid in CHECK_IDS
        },
    }


# -- CLI ----------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: flag missing/stale/malformed staleness markers on skills' "
            "cataloged sections. Called by sentinel F07/F08/F09."
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
        sections = report["examined"]["F07"]["sections"] if report["examined"]["F07"] else 0
        return f"{SCRIPT_NAME}: no staleness violations across {sections} cataloged section(s)."
    lines = [f"{SCRIPT_NAME}: {len(findings)} finding(s):"]
    lines.extend(f"  - [{f['check']}/{f['severity']}] {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    try:
        report = classify(repo_root)
    except MissingParserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

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
