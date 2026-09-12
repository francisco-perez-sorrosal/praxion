#!/usr/bin/env python3
"""F01/F02/F05/X03/X09: path-resolution family.

Five checks, one shared question: does a path an artifact names actually
exist? Two extraction shapes cover them -- a generic repo-root-relative
detector (F01, F05) and a same-skill `references/` detector (F02) -- plus two
one-off table/section walkers (X03, X09).

* **F01** (warn) -- file paths referenced in `skills/*/SKILL.md`,
  `agents/*.md`, `commands/*.md`, and `rules/**/*.md` resolve to existing
  files. `README.md`/`CLAUDE.md` are excluded from the `agents/`/`commands/`
  globs for the same reason X01's sibling C05 excludes them: neither is the
  artifact type its directory's glob names.
* **F02** (fail) -- every bare `references/<name>.md` path a `SKILL.md`
  names, that is genuinely a same-skill reference (see extraction below),
  exists under that skill's own directory.
* **F05** (fail) -- Conditional on `.ai-state/SYSTEM_DEPLOYMENT.md`; every
  path the F01 detector finds in it resolves to an existing file or
  directory.
* **X03** (fail) -- Conditional on root `CLAUDE.md` carrying a `## Structure`
  or a `## Repository layout` heading (the live root `CLAUDE.md` uses the
  latter; either is accepted as the substrate -- check both, since a project
  is free to use either heading text for the same table shape). Every
  backtick-wrapped directory path in that section's table resolves to an
  existing directory.
* **X09** (fail) -- Conditional on `.ai-state/SYSTEM_DEPLOYMENT.md` carrying
  a `## 9. Decisions` heading. Every `dec-NNN` id referenced in that section
  resolves to a finalized `.ai-state/decisions/NNN-*.md` file.

F01/F05 detector shape and declared limits: a candidate is a backtick-quoted
token whose first whitespace-separated word either (a) contains a `/` and
ends in a recognized-looking extension, or (b) starts with `scripts/`,
`docs/`, or `.ai-state/`. Trailing non-path characters after the first `/`
(e.g. a Python call suffix in a code snippet, `foo.py:bar(x)`) are trimmed at
the first character outside `[\\w./-]`. Excluded outright: URLs (`://`),
home-relative (`~`), absolute (leading `/`), shell-variable (`$`), glob/
placeholder tokens containing `*`, `<`, or `{` anywhere in the raw word, and
bare `references/...` tokens (F02's scope, not F01's -- a bare
`references/foo.md` mention is relative to the *citing* file's directory,
not the repo root, so F01 would false-positive on every one). Accepted
declared false positives: a relative path anchored elsewhere than the repo
root (e.g. `../sibling/SKILL.md`) is still checked against the repo root and
will read as missing; a literal filename template using a placeholder
segment without bracket/brace/asterisk delimiters (e.g.
`SENTINEL_REPORT_YYYY-MM-DD_HH-MM-SS.md`) is indistinguishable from a real
missing file. F01 is WARN precisely because of this: a declared-limit
detector over-reports before it under-reports, and severity reflects that.

F02 extraction and declared limits: a `SKILL.md` commonly cites *other*
skills' `references/` files -- via a markdown link whose href carries the
other skill's path (`[text](../other-skill/references/x.md)`), via the
`` `skill` → `references/x.md` `` cross-reference table convention this
corpus uses, or via plain prose ("its `references/x.md` leaf"). The first
two are mechanically distinguishable and excluded: markdown-link hrefs are
resolved by href, not link text, and only kept when the href itself is a
bare `references/...md` (a `../`-prefixed or skill-qualified href is
cross-skill by construction); backtick-quoted bare mentions on a line
containing "→" are the table convention and are skipped. What remains
unresolvable by any mechanical rule is a bare `` `references/x.md` `` mention
in flowing prose that means another named skill without either marker --
this is a declared, accepted false positive (measured at 5 occurrences
against the live corpus; each is disambiguated by nearby prose, not by
document shape a script can key on).

Skip conditions (DS-A, keyed): F01 skips only if none of its four surfaces
exist. F02 skips if `skills/` is absent. F05 and X09 skip if
`.ai-state/SYSTEM_DEPLOYMENT.md` is absent (X09 additionally skips, with its
own reason, if that file lacks a `## 9. Decisions` heading). X03 skips if
`CLAUDE.md` is absent, or is present but has neither heading.

Invocation:

    check_path_resolution.py                  # human-readable summary
    check_path_resolution.py --json           # machine-readable envelope
    check_path_resolution.py --check          # exit 1 on any finding
    check_path_resolution.py --repo-root DIR  # operate on another checkout

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
SCRIPT_NAME = "check_path_resolution"

CHECK_IDS: tuple[str, ...] = ("F01", "F02", "F05", "X03", "X09")

_SKILLS_DIR_REL = "skills"
_AGENTS_DIR_REL = "agents"
_COMMANDS_DIR_REL = "commands"
_RULES_DIR_REL = "rules"
_CLAUDE_MD_REL = "CLAUDE.md"
_DEPLOYMENT_DOC_REL = ".ai-state/SYSTEM_DEPLOYMENT.md"
_DECISIONS_DIR_REL = ".ai-state/decisions"

# Neither file is the artifact type its directory's glob names: an index page
# and a project-instructions file, not an agent/command/rule.
_EXCLUDED_META_FILES = {"README.md", "CLAUDE.md"}

_H2_HEADING = re.compile(r"^##\s")
_STRUCTURE_HEADING = re.compile(r"^##\s*(?:Structure|Repository layout)\b")
_DECISIONS_HEADING = re.compile(r"^##\s*9\.\s*Decisions\b")
_TABLE_PATH_CELL = re.compile(r"^\|\s*`([^`]+)`")
_DEC_ID_RE = re.compile(r"dec-(\d+)")

logger = logging.getLogger(SCRIPT_NAME)


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


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


# -- F01/F05 shared candidate-path detector --------------------------------

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_PATH_CHAR_RE = re.compile(r"[\w./-]+")
_HAS_SLASH_AND_EXT = re.compile(r"^[\w.@/-]+/[\w.-]+\.[A-Za-z0-9]{1,6}$")
_BARE_ROOT_PREFIXES = ("scripts/", "docs/", ".ai-state/")
_F02_SCOPE_PREFIX = "references/"


def _first_path_token(raw: str) -> str | None:
    """First whitespace-separated word of `raw`, trimmed to its path-safe prefix.

    Returns None for URLs, home/absolute paths, shell variables, and anything
    carrying a glob/placeholder character (`*`, `<`, `{`) -- the placeholder
    check runs on the untrimmed word so a token like `NAME_<date>.md` is
    rejected outright rather than truncated into an unrelated short token.
    """
    parts = raw.split()
    word = parts[0] if parts else raw
    if not word or any(ch in word for ch in ("*", "<", "{")):
        return None
    if "://" in raw or word.startswith(("~", "/", "$")):
        return None
    match = _PATH_CHAR_RE.match(word)
    return match.group(0) if match else None


def _candidate_paths(text: str) -> set[str]:
    """Repo-root-relative path candidates from backtick-quoted tokens in `text`."""
    candidates: set[str] = set()
    for raw_match in _BACKTICK_RE.finditer(text):
        token = _first_path_token(raw_match.group(1).strip())
        if not token or token.startswith(_F02_SCOPE_PREFIX):
            continue
        if token.startswith(_BARE_ROOT_PREFIXES) or _HAS_SLASH_AND_EXT.match(token):
            candidates.add(token)
    return candidates


# -- F01: referenced files resolve (warn) -----------------------------------


def _f01_surface_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    skills_dir = repo_root / _SKILLS_DIR_REL
    agents_dir = repo_root / _AGENTS_DIR_REL
    commands_dir = repo_root / _COMMANDS_DIR_REL
    rules_dir = repo_root / _RULES_DIR_REL
    if skills_dir.is_dir():
        files.extend(sorted(skills_dir.glob("*/SKILL.md")))
    if agents_dir.is_dir():
        files.extend(
            sorted(p for p in agents_dir.glob("*.md") if p.name not in _EXCLUDED_META_FILES)
        )
    if commands_dir.is_dir():
        files.extend(
            sorted(p for p in commands_dir.glob("*.md") if p.name not in _EXCLUDED_META_FILES)
        )
    if rules_dir.is_dir():
        files.extend(sorted(rules_dir.glob("**/*.md")))
    return files


def _check_f01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    files = _f01_surface_files(repo_root)
    if not files:
        return [], {"reason": "substrate-absent", "path": "skills/agents/commands/rules"}, None

    findings: list[dict] = []
    candidates_examined = 0
    for f in files:
        text = _read_text(f)
        if text is None:
            continue
        rel = f.relative_to(repo_root)
        for token in sorted(_candidate_paths(text)):
            candidates_examined += 1
            if not (repo_root / token).exists():
                findings.append(
                    {
                        "check": "F01",
                        "severity": "warn",
                        "entity": f"{rel}:{token}",
                        "message": f"'{token}' referenced in {rel} does not resolve to an "
                        "existing file",
                    }
                )
    return (
        findings,
        None,
        {"files_examined": len(files), "candidates_examined": candidates_examined},
    )


# -- F02: skill `references/` paths resolve (fail) ---------------------------

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_BACKTICK_REF_RE = re.compile(r"`(references/[\w./-]+\.md)(?:#[\w-]+)?`")
_OWN_SKILL_HREF_RE = re.compile(r"^references/[\w./-]+\.md(?:#[\w-]+)?$")


def _f02_references(text: str) -> set[str]:
    """Bare `references/*.md` paths a `SKILL.md` names about *itself*.

    Cross-skill mentions are excluded via two mechanical markers: a markdown
    link is resolved by its href (a `../`-prefixed or skill-qualified href is
    cross-skill, a bare `references/...md` href is not), and a backtick-only
    mention on a line containing "→" is this corpus's own-skill-vs-other-skill
    table convention (`` `skill` → `references/x.md` ``). See the module
    docstring for the residual prose ambiguity this does not resolve.
    """
    refs: set[str] = set()

    def _consume_link(match: re.Match[str]) -> str:
        href = match.group(1).strip()
        if _OWN_SKILL_HREF_RE.match(href):
            refs.add(href.split("#", 1)[0])
        return " " * len(match.group(0))

    remainder = _MD_LINK_RE.sub(_consume_link, text)
    for line in remainder.splitlines():
        if "→" in line:
            continue
        for match in _BACKTICK_REF_RE.finditer(line):
            refs.add(match.group(1))
    return refs


def _check_f02(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    skills_dir = repo_root / _SKILLS_DIR_REL
    if not skills_dir.is_dir():
        return [], {"reason": "substrate-absent", "path": str(skills_dir)}, None

    findings: list[dict] = []
    refs_examined = 0
    skill_dirs = sorted(d for d in skills_dir.iterdir() if d.is_dir())
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        text = _read_text(skill_md)
        if text is None:
            continue
        for ref in sorted(_f02_references(text)):
            refs_examined += 1
            if not (skill_dir / ref).exists():
                findings.append(
                    {
                        "check": "F02",
                        "severity": "fail",
                        "entity": f"skills/{skill_dir.name}:{ref}",
                        "message": f"'{ref}' named in skills/{skill_dir.name}/SKILL.md does "
                        "not exist under that skill",
                    }
                )
    return findings, None, {"skill_dirs": len(skill_dirs), "refs_examined": refs_examined}


# -- F05: deployment doc referenced paths resolve (fail) --------------------


def _check_f05(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _DEPLOYMENT_DOC_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None

    findings: list[dict] = []
    candidates = sorted(_candidate_paths(text))
    for token in candidates:
        if not (repo_root / token).exists():
            findings.append(
                {
                    "check": "F05",
                    "severity": "fail",
                    "entity": token,
                    "message": f"'{token}' referenced in {_DEPLOYMENT_DOC_REL} does not "
                    "resolve to an existing file",
                }
            )
    return findings, None, {"candidates_examined": len(candidates)}


# -- X03: CLAUDE.md Structure/Repository-layout dirs exist (fail) -----------


def _check_x03(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _CLAUDE_MD_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None

    span = _heading_span(text, _STRUCTURE_HEADING)
    if span is None:
        return [], {"reason": "no-structure-section", "path": str(path)}, None

    dirs = sorted({m.group(1) for line in span if (m := _TABLE_PATH_CELL.match(line))})
    findings = [
        {
            "check": "X03",
            "severity": "fail",
            "entity": d,
            "message": f"'{d}' in CLAUDE.md's Structure/Repository-layout section does not "
            "resolve to an existing directory",
        }
        for d in dirs
        if not (repo_root / d).is_dir()
    ]
    return findings, None, {"dirs_examined": len(dirs)}


# -- X09: deployment doc ADR cross-references resolve (fail) ----------------


def _check_x09(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    path = repo_root / _DEPLOYMENT_DOC_REL
    text = _read_text(path)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(path)}, None

    span = _heading_span(text, _DECISIONS_HEADING)
    if span is None:
        return [], {"reason": "no-decisions-section", "path": str(path)}, None

    decisions_dir = repo_root / _DECISIONS_DIR_REL
    section_text = "\n".join(span)
    dec_ids = sorted({m.group(1) for m in _DEC_ID_RE.finditer(section_text)})
    findings: list[dict] = []
    for dec_id in dec_ids:
        if not decisions_dir.is_dir() or not any(decisions_dir.glob(f"{dec_id}-*.md")):
            findings.append(
                {
                    "check": "X09",
                    "severity": "fail",
                    "entity": f"dec-{dec_id}",
                    "message": f"'dec-{dec_id}' referenced in {_DEPLOYMENT_DOC_REL} Section 9 "
                    "has no finalized file in .ai-state/decisions/",
                }
            )
    return findings, None, {"dec_ids_examined": len(dec_ids)}


# -- Envelope (DS-A, keyed) -----------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    for check_id, fn in (
        ("F01", _check_f01),
        ("F02", _check_f02),
        ("F05", _check_f05),
        ("X03", _check_x03),
        ("X09", _check_x09),
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
            "F01": "F01 clean means every detected file-path reference resolves to a file.",
            "F02": "F02 clean means every skill's own `references/*.md` mention resolves.",
            "F05": "F05 clean means every detected path in SYSTEM_DEPLOYMENT.md resolves.",
            "X03": "X03 clean means every dir in CLAUDE.md's Structure/Repository-layout "
            "table exists.",
            "X09": "X09 clean means every dec-NNN in SYSTEM_DEPLOYMENT.md Section 9 has a "
            "finalized ADR file.",
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=("Advisory: path-resolution checks. Called by sentinel F01/F02/F05/X03/X09."),
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
