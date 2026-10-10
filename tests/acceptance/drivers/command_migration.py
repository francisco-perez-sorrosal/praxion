"""Driver for the workflow-to-skill migration: the frozen before-state and the skills after it.

The before-state is `tests/acceptance/fixtures/command_migration/manifest.json`, generated once
from the workflow files as they stood before the move and never from repository history (a
shallow CI clone lacks it). The after-state is read the way Claude Code reads it: a skill's
`SKILL.md`, its frontmatter as YAML and also as raw lines (the spec fixes how some fields are
written, not only what they parse to), and its body as the text the harness renders.

Rendering follows the harness's argument substitution as the spec states it: `$ARGUMENTS` is
the whole argument text, `$ARGUMENTS[N]` and `$N` are the N-th shell-style token counted from
zero (an absent token renders empty), a placeholder preceded by a backslash is left alone,
`${...}` is never an argument placeholder, and a body with no placeholder at all gets the
arguments appended. Nothing here imports the system under test.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests" / "acceptance" / "fixtures" / "command_migration"

_PLACEHOLDER = re.compile(r"(?<!\\)\$(ARGUMENTS\[(\d+)\]|ARGUMENTS|(\d+))")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_SCRIPT = re.compile(r"(scripts/[\w./-]*[\w-])")
DOLLAR_AMOUNT = re.compile(r"(?<!\\)\$(\d{2,}|\d+[.,-]\d)")
SHELL_DEFAULT = re.compile(r"\$\{(ARGUMENTS(\[\d+\])?|\d+)\s*:?[-=+?]")


def manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def workflows() -> list[dict]:
    return manifest()["workflows"]


def workflow(name: str) -> dict:
    return next(w for w in workflows() if w["name"] == name)


def names(invocation: str | None = None) -> list[str]:
    return [w["name"] for w in workflows() if invocation in (None, w["invocation"])]


def skill_path(name: str) -> Path:
    return REPO_ROOT / "skills" / name / "SKILL.md"


def skill_text(name: str) -> str:
    path = skill_path(name)
    if not path.is_file():
        raise AssertionError(f"the workflow {name!r} has no skill at skills/{name}/SKILL.md")
    return path.read_text(encoding="utf-8")


def frontmatter_block(text: str) -> str:
    if not text.startswith("---"):
        raise AssertionError("the skill opens with no frontmatter block")
    return text.split("---", 2)[1]


def frontmatter(text: str) -> dict:
    loaded = yaml.safe_load(frontmatter_block(text))
    return loaded if isinstance(loaded, dict) else {}


def frontmatter_lines(text: str, key: str) -> list[str]:
    """The raw frontmatter lines that open `key:`."""
    return [ln for ln in frontmatter_block(text).splitlines() if ln.startswith(f"{key}:")]


def body(text: str) -> str:
    return text.split("---", 2)[2] if text.startswith("---") else text


def tool_set(value) -> set[str]:
    if value is None:
        return set()
    items = value if isinstance(value, list) else [value]
    return {str(item).strip() for item in items}


def reads_arguments(text: str) -> bool:
    return bool(_PLACEHOLDER.search(body(text)))


def render(text: str, arguments: str) -> str:
    """The body as the harness hands it to the model for `/<name> <arguments>`."""
    tokens = shlex.split(arguments)
    content = body(text)

    def substitute(match: re.Match) -> str:
        index = match.group(2) or match.group(3)
        if index is None:
            return arguments
        position = int(index)
        return tokens[position] if position < len(tokens) else ""

    if not _PLACEHOLDER.search(content):
        return f"{content}\n\nARGUMENTS: {arguments}"
    return _PLACEHOLDER.sub(substitute, content)


def fenced_blocks(text: str, language: str = "bash") -> list[str]:
    blocks, current, inside = [], [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            if inside:
                blocks.append("\n".join(current))
                current, inside = [], False
            elif line.strip().lstrip("`~").strip() in (language, "sh", "shell"):
                inside = True
            continue
        if inside:
            current.append(line)
    return blocks


def heading_outline(text: str) -> list[str]:
    """Headings outside code fences, with artifact-kind wording folded (command -> skill)."""
    outline, fenced = [], False
    for line in body(text).splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced and re.match(r"^#{1,6}\s", line):
            outline.append(fold_kind(line.rstrip()))
    return outline


def fold_kind(text: str) -> str:
    return re.sub(r"\bcommand(s?)\b", r"skill\1", text, flags=re.IGNORECASE).lower()


def scripts_referenced(text: str) -> set[str]:
    """Repository scripts the body names, compared as the file each resolves to."""
    found = set()
    for tail in _SCRIPT.findall(body(text)):
        if (REPO_ROOT / tail).is_file():
            found.add(tail)
    return found


def link_targets(text: str, name: str) -> list[str]:
    """Each relative link of the skill body, as the repository path it resolves to."""
    resolved = []
    for target in _LINK.findall(body(text)):
        if re.match(r"^(https?:|mailto:|#|\{)", target):
            continue
        path = target.partition("#")[0]
        absolute = (REPO_ROOT / "skills" / name / path).resolve()
        try:
            resolved.append(absolute.relative_to(REPO_ROOT).as_posix())
        except ValueError:
            resolved.append(str(absolute))
    return resolved


def expected_link_target(before: str) -> str:
    """Where a link that resolved to `before` must resolve now: a workflow file's skill."""
    match = re.fullmatch(r"commands/([a-z0-9-]+)\.md", before)
    return f"skills/{match.group(1)}/SKILL.md" if match else before


def canonical_fence(text: str) -> str:
    start = "<!-- canonical-content-start -->\n"
    end = "<!-- canonical-content-end -->"
    if start not in text or end not in text:
        raise AssertionError("no canonical-content fence in the skill")
    return text.split(start, 1)[1].split(end, 1)[0]
