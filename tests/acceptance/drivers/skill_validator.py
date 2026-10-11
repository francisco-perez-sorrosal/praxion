"""Driver for the skill-authoring command-line tools: the validator, the scaffold, the packager.

Each tool runs as a subprocess on skills written into a temporary directory, never on the
repository's own skills unless a scenario asks for the whole tree. A whole-tree run (`--all`)
happens in a sandbox: a fresh git repository holding a copy of the shipped `skill-crafting`
skill (the validator lives inside it and validates every `skills/<name>/` beside it) plus the
probe skills a scenario adds, so a run never depends on the state of the other shipped skills.

Reading the output is the contract this driver assumes, stated in consumer terms:

* the exit status is 0 when no skill has an error and non-zero otherwise;
* a finding is either a list item (`- `, `* ` or `•`) under a header line that names its
  severity (`error` or `warning`, any case) and ends with a colon, or a line that itself opens
  with the severity word (optionally after a warning or error glyph);
* a finding belongs to the skill named on its own line or, failing that, to the nearest
  preceding skill header: `Validating skill: <name>` or a bare `<name>:` line.

Nothing here imports the system under test.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_CRAFTING = REPO_ROOT / "skills" / "skill-crafting"
VALIDATOR = SKILL_CRAFTING / "scripts" / "validate.py"
SCAFFOLD = SKILL_CRAFTING / "scripts" / "init_skill.py"
PACKAGER = SKILL_CRAFTING / "scripts" / "package_skill.py"

_ITEM = re.compile(r"^\s*(?:[-*•])\s+(?P<text>.+)$")
_SEVERITY_OPENER = re.compile(
    r"^\s*(?:⚠️?|❌|✗)?\s*(?P<severity>warning|warn|error)s?\b[\s:–-]*(?P<text>.*)$", re.IGNORECASE
)
_SKILL_HEADER = re.compile(
    r"^\s*(?:Validating(?: skill)?:?\s+(?P<a>[\w.-]+)|(?P<b>[a-z0-9][\w.-]*):)\s*$"
)


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" or "warning"
    skill: str | None
    text: str


@dataclass(frozen=True)
class Run:
    exit_code: int
    output: str

    def findings(self, known_skills: tuple[str, ...] = ()) -> list[Finding]:
        return _parse(self.output, known_skills)

    def errors(self, skill: str | None = None) -> list[str]:
        return _select(self, "error", skill)

    def warnings(self, skill: str | None = None) -> list[str]:
        return _select(self, "warning", skill)

    def describe(self) -> str:
        return f"exit {self.exit_code}; output:\n{self.output[-3000:]}"


def _select(run: Run, severity: str, skill: str | None) -> list[str]:
    known = (skill,) if skill else ()
    return [
        f.text
        for f in run.findings(known)
        if f.severity == severity and (skill is None or f.skill == skill)
    ]


def _parse(output: str, known_skills: tuple[str, ...]) -> list[Finding]:
    findings: list[Finding] = []
    severity: str | None = None
    skill: str | None = None
    for raw in output.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        named = next(
            (s for s in known_skills if re.search(rf"(?<![\w-]){re.escape(s)}(?![\w-])", line)),
            None,
        )
        item = _ITEM.match(line)
        if item and severity:
            findings.append(Finding(severity, named or skill, item.group("text").strip()))
            continue
        stripped = line.strip()
        if stripped.endswith(":") and re.search(r"error|warn", stripped, re.IGNORECASE):
            severity = "warning" if re.search(r"warn", stripped, re.IGNORECASE) else "error"
            continue
        header = _SKILL_HEADER.match(line)
        if header and not item:
            skill = header.group("a") or header.group("b")
            continue
        opener = _SEVERITY_OPENER.match(line)
        if opener and opener.group("text").strip():
            kind = "warning" if opener.group("severity").lower().startswith("warn") else "error"
            findings.append(Finding(kind, named or skill, opener.group("text").strip()))
            continue
        if re.match(r"^\s*(PASSED|FAILED|OK)\b", line):
            severity = None
    return findings


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))}


def _run(args: list[str], cwd: Path) -> Run:
    result = subprocess.run(
        [sys.executable, *args], cwd=cwd, env=_env(), capture_output=True, text=True, timeout=300
    )
    return Run(result.returncode, result.stdout + result.stderr)


# --- building probe skills ---------------------------------------------------------------------


def skill_md(
    name: str,
    *,
    description: str = "Use when probing the skill validator with a minimal skill.",
    extra: str = "",
    body: str = "# Probe\n\nA probe skill.\n",
) -> str:
    """A `SKILL.md` whose frontmatter is written verbatim: `extra` is raw YAML lines."""
    lines = ["---", f"name: {name}", f"description: {description}"]
    if extra:
        lines.append(extra.rstrip("\n"))
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def write_skill(parent: Path, directory: str, text: str) -> Path:
    skill_dir = parent / directory
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def long_body(lines: int) -> str:
    return "# Probe\n\n" + "\n".join(f"Line {i} of a long probe body." for i in range(lines)) + "\n"


# --- running the tools -------------------------------------------------------------------------


def validate(skill_dir: Path) -> Run:
    """`validate.py <skill-directory>`, run from the skill's parent directory."""
    return _run([str(VALIDATOR), str(skill_dir)], cwd=skill_dir.parent)


def validate_repository() -> Run:
    """`validate.py --all` over the repository's own skills."""
    return _run([str(VALIDATOR), "--all"], cwd=REPO_ROOT)


def validate_tree(sandbox: Path, skills: dict[str, str]) -> Run:
    """`validate.py --all` in a sandbox holding the shipped authoring skill and `skills`."""
    root = sandbox / "repo"
    (root / "skills").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SKILL_CRAFTING,
        root / "skills" / "skill-crafting",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )
    for name, text in skills.items():
        write_skill(root / "skills", name, text)
    subprocess.run(
        ["git", "init", "-q"], cwd=root, env=_env(), capture_output=True, check=True, timeout=60
    )
    copied_validator = root / "skills" / "skill-crafting" / "scripts" / "validate.py"
    return _run([str(copied_validator), "--all"], cwd=root)


def scaffold(name: str, out_dir: Path) -> Run:
    """`init_skill.py <name> --path <out_dir>`; the skill lands at `<out_dir>/<name>/`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return _run([str(SCAFFOLD), name, "--path", str(out_dir)], cwd=out_dir)


def package(skill_dir: Path, out_dir: Path) -> Run:
    """`package_skill.py <skill_dir> <out_dir>`; the archive lands at `<out_dir>/<name>.skill`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return _run([str(PACKAGER), str(skill_dir), str(out_dir)], cwd=skill_dir.parent)


def mentions(line: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", line) is not None


def unknown_field_errors(run: Run, field: str) -> list[str]:
    """The error lines that report `field` as unknown."""
    return [
        e
        for e in run.errors()
        if re.search(r"unknown|unrecogni[sz]ed", e, re.I) and mentions(e, field)
    ]


# --- skills the validator must reject ----------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    """A skill directory name, its `SKILL.md` text, and the probe values a message may echo."""

    directory: str
    text: str
    values: tuple[str, ...] = ()


_PROBE = "probe-skill"
_LONG_NAME = "a" * 65


def rejection_probes() -> dict[str, Probe]:
    """Each defect the validator rejects with an error, as a minimal skill carrying only it."""
    return {
        "missing frontmatter": Probe(_PROBE, "# Probe\n\nNo frontmatter at all.\n"),
        "unterminated frontmatter": Probe(
            _PROBE, f"---\nname: {_PROBE}\ndescription: Use when probing.\n# Probe\n"
        ),
        "missing name": Probe(_PROBE, "---\ndescription: Use when probing.\n---\n# Probe\n"),
        "name not matching its directory": Probe(
            _PROBE, skill_md("other-name"), (_PROBE, "other-name")
        ),
        "malformed name": Probe("Probe_Skill", skill_md("Probe_Skill"), ("Probe_Skill",)),
        "over-long name": Probe(_LONG_NAME, skill_md(_LONG_NAME), (_LONG_NAME,)),
        "consecutive hyphens in the name": Probe(
            "probe--skill", skill_md("probe--skill"), ("probe--skill",)
        ),
        "missing description": Probe(_PROBE, f"---\nname: {_PROBE}\n---\n# Probe\n"),
        "over-long description": Probe(_PROBE, skill_md(_PROBE, description="d" * 1025)),
        "angle brackets in the description": Probe(
            _PROBE, skill_md(_PROBE, description="Use when probing <brackets>."), ("<brackets>",)
        ),
        "over-long compatibility": Probe(
            _PROBE, skill_md(_PROBE, extra=f"compatibility: {'c' * 501}")
        ),
        "unknown field": Probe(_PROBE, skill_md(_PROBE, extra="bogus-key: 1"), ("bogus-key",)),
    }
