#!/usr/bin/env python3
"""C01/C02/C03/C04/C05/N01/N02/N03/S01/S02/S03/S04: artifact-conformance family.

Twelve checks, one shared shape: does an artifact (skill dir, agent file, command
file, rule file, plugin manifest) carry the shape its own crafting spec demands.

**Completeness (C)**

* **C01** (fail) -- every `skills/*/` dir holds a `SKILL.md`.
* **C02** (warn) -- every `SKILL.md` declares `description` in frontmatter.
* **C03** (fail) -- every `agents/*.md` (excl. `README.md`) declares `name`,
  `description`, `tools` in frontmatter.
* **C04** (warn) -- every `commands/*.md` carries a non-empty, non-placeholder
  `description` (frontmatter field, or a header comment when frontmatter is
  absent). Placeholder = empty, `TODO`, `TBD`, or an angle-bracket stub
  (`<...>`). Whether the text is *accurate* is C02/S01's judgment -- this
  guarantees there is something for them to judge.
* **C05** (fail) -- `.claude-plugin/plugin.json`'s `agents` array count equals
  the `agents/*.md` file count (excl. `README.md`).

**Consistency (N)**

* **N01** (warn) -- skill dirs are lowercase kebab-case; a crafting skill
  (body mentions "crafting a" or the dir name literally ends `-crafting`)
  should end `-crafting`; a language skill (dir name matches a known language
  token) should end `-development`. This is a naming *heuristic*, not a
  semantic classifier -- it flags the two suffix families the corpus already
  uses and stays silent on skills that are neither.
* **N02** (warn) -- `agents/*.md` (excl. `README.md`) file stems are lowercase
  kebab-case.
* **N03** (warn) -- SKILL.md and agent frontmatter use only keys the crafting
  specs recognise (`_SKILL_FRONTMATTER_KEYS`, `_AGENT_FRONTMATTER_KEYS` below).
  An unrecognized key is a WARN, not a FAIL -- the specs are read at commit
  time, not live, so a legitimately new field would false-FAIL until this
  script's constant is updated.

**Spec Compliance (S)**

* **S01** (fail) -- `SKILL.md` frontmatter `description` is present and
  non-empty (S02's skill-side counterpart to C02's presence-only check).
* **S02** (fail) -- agent frontmatter `name`/`description`/`tools` are all
  present and non-empty.
* **S03** (fail) -- `rules/**/*.md` (excl. `README.md`) starts with a `##`
  heading as its first non-blank line.
* **S04** (warn) -- a command using `$ARGUMENTS`-style substitution names it in
  content. This check only has evidence of *presence*: a command that uses
  `$ARGUMENTS`/`$1`/`$name` substitution necessarily contains the token, so
  there is nothing to flag from the content side. What it actually checks is
  the declared-but-unused direction -- an `argument-hint` frontmatter field
  promising arguments that the body never substitutes -- since a command can
  declare a hint for autocomplete purposes alone. Limitation: it cannot detect
  a command that consumes `$ARGUMENTS` without ever declaring `argument-hint`;
  that shape has no unused-declaration signal to key on.

**Parsing boundary.** This script re-implements (does not import) the minimal
frontmatter splitter `check_frontmatter_parses.py` uses (`---` delimited
block, `yaml.safe_load`) -- that script owns *parseability* (does the block
load at all); this one owns *presence/shape* (do the loaded fields carry the
right keys and content) and never re-derives a parseability verdict of its
own. A file whose frontmatter fails to load is treated as having no
frontmatter here (empty dict) -- `check_frontmatter_parses.py` is the check
that already reports the parse failure itself.

Skip conditions (DS-A, keyed): each check skips independently when its own
substrate dir/file is absent.

Invocation:

    check_artifact_conformance.py                  # human-readable summary
    check_artifact_conformance.py --json           # machine-readable envelope
    check_artifact_conformance.py --check          # exit 1 on any finding
    check_artifact_conformance.py --repo-root DIR  # operate on another checkout

Exit code: 0 by default (advisory), 1 with --check when any finding is present.
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

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_artifact_conformance"

CHECK_IDS: tuple[str, ...] = (
    "C01",
    "C02",
    "C03",
    "C04",
    "C05",
    "N01",
    "N02",
    "N03",
    "S01",
    "S02",
    "S03",
    "S04",
)

# Neither is the artifact type its directory's glob names: an index page and a
# project-instructions file, not an agent/command/rule (same exclusion
# check_registry_projection.py applies to agents/commands).
_EXCLUDED_META_FILES = {"README.md", "CLAUDE.md"}

# -- frontmatter splitter (mirrors check_frontmatter_parses.py; not imported --
# that script owns parseability, this one owns presence/shape) --------------

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_OPENS_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n")


def _load_frontmatter(text: str) -> dict[str, Any]:
    """Return the parsed frontmatter mapping, or `{}` if absent/unparseable.

    Parse failures are silently folded into "no frontmatter" -- reporting them
    is `check_frontmatter_parses.py`'s job, not this script's.
    """
    if not _OPENS_FRONTMATTER_RE.match(text):
        return {}
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(match.group(1))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _agent_files(repo_root: Path) -> list[Path] | None:
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        return None
    return sorted(p for p in agents_dir.glob("*.md") if p.name not in _EXCLUDED_META_FILES)


def _skill_dirs(repo_root: Path) -> list[Path] | None:
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return None
    return sorted(d for d in skills_dir.iterdir() if d.is_dir())


# -- C01: every skill dir has SKILL.md ---------------------------------------


def _check_c01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    dirs = _skill_dirs(repo_root)
    if dirs is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "skills")}, None
    findings = [
        {
            "check": "C01",
            "severity": "fail",
            "entity": f"skills/{d.name}",
            "message": f"skill dir '{d.name}' has no SKILL.md",
        }
        for d in dirs
        if not (d / "SKILL.md").is_file()
    ]
    return findings, None, {"skill_dirs": len(dirs)}


# -- C02/S01: SKILL.md has description ---------------------------------------


def _skill_md_files(repo_root: Path) -> list[Path] | None:
    dirs = _skill_dirs(repo_root)
    if dirs is None:
        return None
    return [d / "SKILL.md" for d in dirs if (d / "SKILL.md").is_file()]


def _check_description_field(
    repo_root: Path, check_id: str, severity: str
) -> tuple[list[dict], dict | None, dict | None]:
    files = _skill_md_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "skills")}, None
    findings: list[dict] = []
    for path in files:
        text = _read_text(path)
        fm = _load_frontmatter(text or "")
        description = fm.get("description")
        if not (isinstance(description, str) and description.strip()):
            findings.append(
                {
                    "check": check_id,
                    "severity": severity,
                    "entity": str(path.relative_to(repo_root)),
                    "message": f"{path.parent.name}/SKILL.md has no non-empty `description` field",
                }
            )
    return findings, None, {"skill_md_files": len(files)}


# -- C03/S02: agent frontmatter has name/description/tools -------------------

_AGENT_REQUIRED_FIELDS = ("name", "description", "tools")


def _check_agent_required_fields(
    repo_root: Path, check_id: str, severity: str
) -> tuple[list[dict], dict | None, dict | None]:
    files = _agent_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "agents")}, None
    findings: list[dict] = []
    for path in files:
        text = _read_text(path)
        fm = _load_frontmatter(text or "")
        missing = [
            f
            for f in _AGENT_REQUIRED_FIELDS
            if not (isinstance(fm.get(f), str) and fm.get(f).strip())
        ]
        for field in missing:
            findings.append(
                {
                    "check": check_id,
                    "severity": severity,
                    "entity": str(path.relative_to(repo_root)),
                    "message": f"{path.name} is missing non-empty `{field}` in frontmatter",
                }
            )
    return findings, None, {"agent_files": len(files)}


# -- C04: command description non-empty and non-placeholder -----------------

_PLACEHOLDER_RE = re.compile(r"^\s*(TODO|TBD)\s*$", re.IGNORECASE)
_ANGLE_STUB_RE = re.compile(r"^\s*<.*>\s*$")
_HEADER_COMMENT_RE = re.compile(r"^\s*<!--\s*(.+?)\s*-->\s*$")


def _is_placeholder(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return bool(_PLACEHOLDER_RE.match(stripped) or _ANGLE_STUB_RE.match(stripped))


def _command_files(repo_root: Path) -> list[Path] | None:
    commands_dir = repo_root / "commands"
    if not commands_dir.is_dir():
        return None
    return sorted(f for f in commands_dir.glob("*.md") if f.name not in _EXCLUDED_META_FILES)


def _check_c04(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    files = _command_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "commands")}, None
    findings: list[dict] = []
    for path in files:
        text = _read_text(path) or ""
        fm = _load_frontmatter(text)
        description = fm.get("description")
        if isinstance(description, str) and not _is_placeholder(description):
            continue
        header_comment = _leading_header_comment(text, fm)
        if header_comment is not None and not _is_placeholder(header_comment):
            continue
        findings.append(
            {
                "check": "C04",
                "severity": "warn",
                "entity": str(path.relative_to(repo_root)),
                "message": (
                    f"{path.name} has no non-placeholder `description` field or header comment"
                ),
            }
        )
    return findings, None, {"command_files": len(files)}


def _leading_header_comment(text: str, fm: dict[str, Any]) -> str | None:
    """Return the first `<!-- ... -->` comment line after any frontmatter block, else None."""
    body = text
    if fm:
        match = _FRONTMATTER_RE.match(text)
        if match is not None:
            body = text[match.end() :]
    for line in body.splitlines():
        if not line.strip():
            continue
        comment = _HEADER_COMMENT_RE.match(line)
        return comment.group(1) if comment else None
    return None


# -- C05: plugin.json agent count == agents/*.md count -----------------------


def _check_c05(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    plugin_json = repo_root / ".claude-plugin" / "plugin.json"
    text = _read_text(plugin_json)
    if text is None:
        return [], {"reason": "substrate-absent", "path": str(plugin_json)}, None
    files = _agent_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "agents")}, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], {"reason": "unparseable", "detail": str(exc)}, None
    agents = data.get("agents") if isinstance(data, dict) else None
    plugin_count = len(agents) if isinstance(agents, list) else 0
    file_count = len(files)
    if plugin_count == file_count:
        return [], None, {"plugin_agents": plugin_count, "agent_files": file_count}
    finding = {
        "check": "C05",
        "severity": "fail",
        "entity": str(plugin_json.relative_to(repo_root)),
        "message": (
            f"plugin.json lists {plugin_count} agent(s) but agents/*.md has "
            f"{file_count} file(s) (excl. README.md)"
        ),
    }
    return [finding], None, {"plugin_agents": plugin_count, "agent_files": file_count}


# -- N01: skill dir naming convention ----------------------------------------

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Language tokens the corpus's `-development` skills name (python, typescript
# today). A heuristic list, not an exhaustive language registry -- a new
# language skill not named here is simply not checked by the second half of
# N01, not flagged as wrong.
_LANGUAGE_TOKENS = ("python", "typescript", "rust", "go", "javascript")


# The corpus's actual `-crafting` skills describe themselves as "Creating and
# managing <artifact>s" (commands, rules) or "Creating, testing, and
# registering <artifact>s" (hooks) or "Building <artifact>s" (MCP servers) as
# the OPENING clause -- the "what it does" part of the three-part description
# structure schema.md prescribes -- of their own `description` field; none use
# the literal word "crafting" anywhere. Scoped to that opening clause alone
# (the text before the first "Triggers:", schema.md's "when to trigger" part)
# so a match inside the trigger-terms list -- e.g. "Triggers: authoring
# fitness rules" naming an unrelated verb, or "building multi-agent systems"
# as one trigger phrase among many -- cannot false-positive a skill whose own
# stated purpose is something else.
_CRAFTING_DESCRIPTION_RE = re.compile(
    r"\b(creating|building|authoring)\b.{0,60}\b(skills?|agents?|commands?|rules?|hooks?|mcp servers?)\b",
    re.IGNORECASE,
)
_TRIGGERS_CLAUSE_RE = re.compile(r"\bTriggers:", re.IGNORECASE)


def _looks_like_crafting_skill(dir_name: str, description: str) -> bool:
    """Heuristic only: a dir literally ending `-crafting`, or a description's
    opening clause reading as authoring guidance for another artifact family,
    is a crafting skill. False negatives (a crafting skill phrased differently,
    or one for an artifact family outside the fixed word list) are expected
    and not flagged -- this signal only fires positive.
    """
    if dir_name.endswith("-crafting"):
        return True
    trigger_start = _TRIGGERS_CLAUSE_RE.search(description)
    opening = description[: trigger_start.start()] if trigger_start else description
    return bool(_CRAFTING_DESCRIPTION_RE.search(opening))


def _looks_like_language_skill(dir_name: str) -> bool:
    stem = dir_name.removesuffix("-development")
    return stem in _LANGUAGE_TOKENS


def _check_n01(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    dirs = _skill_dirs(repo_root)
    if dirs is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "skills")}, None
    findings: list[dict] = []
    for d in dirs:
        name = d.name
        if not _KEBAB_RE.match(name):
            findings.append(
                {
                    "check": "N01",
                    "severity": "warn",
                    "entity": f"skills/{name}",
                    "message": f"skill dir '{name}' is not lowercase kebab-case",
                }
            )
            continue
        fm = _load_frontmatter(_read_text(d / "SKILL.md") or "")
        description = fm.get("description") if isinstance(fm.get("description"), str) else ""
        if _looks_like_crafting_skill(name, description) and not name.endswith("-crafting"):
            findings.append(
                {
                    "check": "N01",
                    "severity": "warn",
                    "entity": f"skills/{name}",
                    "message": f"skill dir '{name}' reads as a crafting skill but "
                    "does not end `-crafting`",
                }
            )
        if _looks_like_language_skill(name) and not name.endswith("-development"):
            findings.append(
                {
                    "check": "N01",
                    "severity": "warn",
                    "entity": f"skills/{name}",
                    "message": f"skill dir '{name}' names a known language token "
                    "but does not end `-development`",
                }
            )
    return findings, None, {"skill_dirs": len(dirs)}


# -- N02: agent file naming convention ---------------------------------------


def _check_n02(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    files = _agent_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "agents")}, None
    findings = [
        {
            "check": "N02",
            "severity": "warn",
            "entity": str(f.relative_to(repo_root)),
            "message": f"agent file stem '{f.stem}' is not lowercase kebab-case",
        }
        for f in files
        if not _KEBAB_RE.match(f.stem)
    ]
    return findings, None, {"agent_files": len(files)}


# -- N03: frontmatter uses only recognized keys ------------------------------

# Source: skills/skill-crafting/references/schema.md -- portable core (name,
# description, license, compatibility, metadata, allowed-tools) plus the
# "Claude Code Frontmatter Superset" and "Praxion staleness fields" tables.
_SKILL_FRONTMATTER_KEYS = frozenset(
    {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
        "when_to_use",
        "disable-model-invocation",
        "user-invocable",
        "paths",
        "context",
        "agent",
        "model",
        "effort",
        "argument-hint",
        "arguments",
        "hooks",
        "shell",
        "staleness_sensitive_sections",
        "staleness_threshold_days",
    }
)

# Source: skills/agent-crafting/SKILL.md "Configuration Fields Summary" table.
_AGENT_FRONTMATTER_KEYS = frozenset(
    {
        "name",
        "description",
        "tools",
        "disallowedTools",
        "model",
        "permissionMode",
        "color",
        "skills",
        "hooks",
        "memory",
        "mcpServers",
        "maxTurns",
        "effort",
        "background",
        "isolation",
        "initialPrompt",
    }
)


def _check_n03(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    skill_files = _skill_md_files(repo_root)
    agent_files = _agent_files(repo_root)
    if skill_files is None and agent_files is None:
        return (
            [],
            {
                "reason": "substrate-absent",
                "path": f"{repo_root / 'skills'} and {repo_root / 'agents'}",
            },
            None,
        )
    findings: list[dict] = []
    examined = {"skill_md_files": 0, "agent_files": 0}
    for path, allowed, label in (
        *((f, _SKILL_FRONTMATTER_KEYS, "SKILL.md") for f in (skill_files or [])),
        *((f, _AGENT_FRONTMATTER_KEYS, "agent") for f in (agent_files or [])),
    ):
        examined["skill_md_files" if label == "SKILL.md" else "agent_files"] += 1
        fm = _load_frontmatter(_read_text(path) or "")
        for key in sorted(set(fm) - allowed):
            findings.append(
                {
                    "check": "N03",
                    "severity": "warn",
                    "entity": str(path.relative_to(repo_root)),
                    "message": f"{label} frontmatter key `{key}` is not recognized by the crafting spec",
                }
            )
    return findings, None, examined


# -- S03: rule files start with a `##` heading -------------------------------


def _rule_files(repo_root: Path) -> list[Path] | None:
    rules_dir = repo_root / "rules"
    if not rules_dir.is_dir():
        return None
    return sorted(f for f in rules_dir.glob("**/*.md") if f.name not in _EXCLUDED_META_FILES)


_H2_HEADING_RE = re.compile(r"^##\s")


def _strip_frontmatter(text: str) -> str:
    """Return `text` with a leading `---`-delimited frontmatter block removed.

    Rule files may carry their own frontmatter (`paths:`, `core:`, `load:`) ahead
    of the `##` heading S03 checks for -- the heading is the first non-blank line
    of the *body*, not of the file.
    """
    match = _FRONTMATTER_RE.match(text)
    return text[match.end() :] if match else text


def _check_s03(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    files = _rule_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "rules")}, None
    findings: list[dict] = []
    for path in files:
        body = _strip_frontmatter(_read_text(path) or "")
        first_non_blank = next((line for line in body.splitlines() if line.strip()), "")
        if not _H2_HEADING_RE.match(first_non_blank):
            findings.append(
                {
                    "check": "S03",
                    "severity": "fail",
                    "entity": str(path.relative_to(repo_root)),
                    "message": f"{path.relative_to(repo_root)}'s first non-blank line is not a `##` heading",
                }
            )
    return findings, None, {"rule_files": len(files)}


# -- S04: commands with argument-hint actually substitute it -----------------

# Any of these appearing in a command body is evidence the command consumes
# positional/named arguments. Limitation (see module docstring): a command
# that uses one of these WITHOUT declaring `argument-hint` has no signal here.
_SUBSTITUTION_RE = re.compile(r"\$ARGUMENTS\b|\$\d+\b|\$\{CLAUDE_[A-Z_]+\}")


def _check_s04(repo_root: Path) -> tuple[list[dict], dict | None, dict | None]:
    files = _command_files(repo_root)
    if files is None:
        return [], {"reason": "substrate-absent", "path": str(repo_root / "commands")}, None
    findings: list[dict] = []
    examined = 0
    for path in files:
        text = _read_text(path) or ""
        fm = _load_frontmatter(text)
        hint = fm.get("argument-hint")
        if not (isinstance(hint, str) and hint.strip()):
            continue
        examined += 1
        if not _SUBSTITUTION_RE.search(text):
            findings.append(
                {
                    "check": "S04",
                    "severity": "warn",
                    "entity": str(path.relative_to(repo_root)),
                    "message": (
                        f"{path.name} declares `argument-hint` but its content never "
                        "substitutes $ARGUMENTS/$N"
                    ),
                }
            )
    return findings, None, {"command_files_with_hint": examined}


# -- Envelope (DS-A, keyed) -----------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    for check_id, fn in (
        ("C01", _check_c01),
        ("C02", lambda r: _check_description_field(r, "C02", "warn")),
        ("C03", lambda r: _check_agent_required_fields(r, "C03", "fail")),
        ("C04", _check_c04),
        ("C05", _check_c05),
        ("N01", _check_n01),
        ("N02", _check_n02),
        ("N03", _check_n03),
        ("S01", lambda r: _check_description_field(r, "S01", "fail")),
        ("S02", lambda r: _check_agent_required_fields(r, "S02", "fail")),
        ("S03", _check_s03),
        ("S04", _check_s04),
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
            "C01": "C01 clean means every skills/*/ dir has a SKILL.md.",
            "C02": "C02 clean means every SKILL.md declares a description field.",
            "C03": "C03 clean means every agents/*.md declares name/description/tools.",
            "C04": "C04 clean means every command has a non-placeholder description or header comment.",
            "C05": "C05 clean means plugin.json's agents count equals agents/*.md's file count.",
            "N01": "N01 clean means skill dirs are kebab-case with the right family suffix.",
            "N02": "N02 clean means agent file stems are kebab-case.",
            "N03": "N03 clean means SKILL.md/agent frontmatter uses only spec-recognized keys.",
            "S01": "S01 clean means every SKILL.md description is present and non-empty.",
            "S02": "S02 clean means every agent's name/description/tools are present and non-empty.",
            "S03": "S03 clean means every rule file's first non-blank line is a `##` heading.",
            "S04": "S04 clean means every command declaring argument-hint substitutes it in content.",
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: artifact-conformance checks. Called by sentinel "
            "C01/C02/C03/C04/C05/N01/N02/N03/S01/S02/S03/S04."
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


logger = logging.getLogger(SCRIPT_NAME)


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
