"""Where Praxion states diagram rules, and what toolchain versions those places state.

A stated toolchain version is an exact `x.y.z` version within 40 characters after
the tool's name (`likec4` as a word, not an org-scoped package such as
`@likec4/cli`; `d2`/`d2lang` as a word) with no other tool named in between, in any text file git tracks or would
track outside pipeline state, tests, changelogs and lockfiles, plus the version each
drift-gate workflow's install steps pin. Ranges (`^1.56`) are not exact versions.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.acceptance.drivers.diagram_regen import DRIFT_JOB, pins_in_workflow

REPO_ROOT = Path(__file__).resolve().parents[3]
PRAXION_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "architecture.yml"
ONBOARDING_WORKFLOW_TEMPLATE = REPO_ROOT / "claude" / "aac-templates" / "architecture.yml.tmpl"
ARCHITECT_INSTRUCTIONS = REPO_ROOT / "agents" / "systems-architect.md"
_TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".sh", ".tmpl", ".frag", ".c4", ".toml", ".txt", ".py"}
_TOOL_NAMES = {
    "likec4": re.compile(r"(?<![@\w])likec4(?![/\w])", re.I),
    "d2": re.compile(r"\bd2(?:lang)?\b", re.I),
}
_VERSION_AFTER_TOOL = re.compile(r"^.{0,40}?\bv?(\d+\.\d+\.\d+)\b")


def stated_versions(tool: str) -> dict[str, set[str]]:
    """version -> the places (path:line) that state it for `tool`."""
    found: dict[str, set[str]] = {}
    for path in _text_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for version in _versions_on_line(line, tool):
                found.setdefault(version, set()).add(f"{path.relative_to(REPO_ROOT)}:{number}")
    for workflow in (PRAXION_WORKFLOW, ONBOARDING_WORKFLOW_TEMPLATE):
        pinned = getattr(pins_in_workflow(workflow, DRIFT_JOB), tool)
        if pinned:
            found.setdefault(pinned, set()).add(f"{workflow.relative_to(REPO_ROOT)} (install step)")
    return found


def _versions_on_line(line: str, tool: str) -> list[str]:
    """Exact versions that follow the tool's name closely, with no other tool named between."""
    others = [p for name, p in _TOOL_NAMES.items() if name != tool]
    versions = []
    for match in _TOOL_NAMES[tool].finditer(line):
        after = _VERSION_AFTER_TOOL.match(line[match.end() :])
        if after and not any(
            o.search(line[match.end() : match.end() + after.end()]) for o in others
        ):
            versions.append(after.group(1))
    return versions


def _text_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    files = []
    for rel in filter(None, listed):
        path = Path(rel)
        if (
            path.parts[0] in (".ai-state", ".ai-work", "tests", "node_modules")
            or "node_modules" in path.parts
        ):
            continue
        if path.name.upper().startswith("CHANGELOG") or "lock" in path.name.lower():
            continue
        if path.suffix in _TEXT_SUFFIXES and (REPO_ROOT / path).is_file():
            files.append(REPO_ROOT / path)
    return files


def markdown_links(document: Path) -> list[Path]:
    text = document.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(\s*<?([^)\s>#]+)", text)
    return [
        (document.parent / target).resolve()
        for target in targets
        if not re.match(r"[a-z]+://", target)
    ]
