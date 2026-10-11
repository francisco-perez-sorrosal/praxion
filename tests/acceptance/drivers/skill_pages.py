"""Driver for reading the skill-authoring skill's pages the way an author or an agent meets them.

Pages are plain Markdown. Headings inside fenced code blocks are examples, not structure, so
every structural read ignores fenced blocks. A *section* runs from its heading to the next
heading of the same or a higher level.

Contracts this driver assumes, in consumer terms:

* the entry page names each of its topics in a level-2 or level-3 heading using the topic's
  ordinary word (see `ENTRY_TOPICS`), and a heading about directory layout or packaging uses one
  of the words in `LAYOUT_TOPIC`;
* the closing checklist is the entry page's last level-2 section and its items are Markdown list
  items, one checkable statement per item;
* a reference page "opens with a list of its contents" when, within its first 30 lines, it has a
  `Contents` heading or label, or at least three list items linking to anchors on the same page;
* the schema reference defines the accepted field set in the part of the page before its
  validation section, as `### `<field>`` headings and as table rows whose first cell is a
  backticked field name; its validation section is the first level-2 heading naming validation,
  and the name pattern is quoted there as a backticked regular expression anchored with `^` and `$`.

Nothing here imports the system under test.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / "skills" / "skill-crafting"
ENTRY_PAGE = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"

# The entry page's topics, in the order a reader must meet them.
ENTRY_TOPICS = {
    "invocation modes": r"invo",
    "eval-first creation loop": r"\beval|creat",
    "degrees of freedom and gotchas": r"freedom|gotcha|specificity",
    "scripts designed for agents": r"script",
    "runtime lifecycle facts": r"lifecycle|runtime",
    "portability between hosts": r"portab|host",
    "closing checklist": r"checklist",
}
LAYOUT_TOPIC = r"layout|anatomy|structure|director|packag"

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(?P<text>.+)$")


def read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"{path.relative_to(REPO_ROOT)} does not exist")
    return path.read_text(encoding="utf-8")


def reference(name: str) -> Path:
    return REFERENCES / name


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    loaded = yaml.safe_load(text.split("---", 2)[1])
    return loaded if isinstance(loaded, dict) else {}


def body(text: str) -> str:
    return text.split("---", 2)[2] if text.startswith("---") else text


def unfenced_lines(text: str) -> list[str]:
    """The page's lines with every fenced block blanked out (line numbers preserved)."""
    lines, inside = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            inside = not inside
            lines.append("")
            continue
        lines.append("" if inside else line)
    return lines


def headings(text: str, levels: tuple[int, ...] = (2, 3)) -> list[tuple[int, str, int]]:
    """`(level, title, line index)` for every heading of the given levels, outside fences."""
    found = []
    for index, line in enumerate(unfenced_lines(text)):
        match = _HEADING.match(line)
        if match and len(match.group(1)) in levels:
            found.append((len(match.group(1)), match.group(2).replace("`", ""), index))
    return found


def first_heading(text: str, pattern: str, levels: tuple[int, ...] = (2, 3)):
    return next((h for h in headings(text, levels) if re.search(pattern, h[1], re.I)), None)


def section(text: str, pattern: str, topic: str, levels: tuple[int, ...] = (2, 3)) -> str:
    """The first section whose heading matches `pattern`; fails naming `topic` when none does."""
    found = first_heading(text, pattern, levels)
    if found is None:
        titles = [h[1] for h in headings(text, levels)]
        raise AssertionError(f"no heading names the {topic} (headings: {titles})")
    level, _, start = found
    lines = unfenced_lines(text)
    raw = text.splitlines()
    end = len(raw)
    for index in range(start + 1, len(lines)):
        match = _HEADING.match(lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(raw[start:end])


def last_h2_section(text: str) -> tuple[str, str]:
    h2 = headings(text, (2,))
    if not h2:
        raise AssertionError("the page has no level-2 heading")
    _, title, start = h2[-1]
    return title, "\n".join(text.splitlines()[start:])


def list_items(text: str) -> list[str]:
    return [m.group("text") for line in unfenced_lines(text) if (m := _LIST_ITEM.match(line))]


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text.replace("`", "")) if p.strip()]


def sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text.replace("`", ""))
    return [s for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]


def link_targets(text: str) -> list[str]:
    return re.findall(r"\]\(([^)\s#]*)(?:#[^)\s]*)?\)", text)


def links_to_reference(text: str, page: str) -> bool:
    targets = {t.removeprefix("./") for t in link_targets(text)}
    return f"references/{page}" in targets


def opens_with_contents(text: str) -> bool:
    head = unfenced_lines(body(text))[:30]
    labelled = any(
        re.match(r"^\s*(#+\s*|\*\*)?(table of )?contents\b", line, re.I) for line in head
    )
    anchored = sum(1 for line in head if _LIST_ITEM.match(line) and "](#" in line)
    return labelled or anchored >= 3


# --- the schema reference ----------------------------------------------------------------------


def schema_text() -> str:
    return read(reference("schema.md"))


def schema_validation_section() -> str:
    return section(schema_text(), r"validat", "validator's documentation", levels=(2,))


def schema_field_keys() -> set[str]:
    text = schema_text()
    found = first_heading(text, r"validat", (2,))
    lines = unfenced_lines(text)[: found[2] if found else None]
    keys = set()
    for line in lines:
        heading = re.match(r"^###\s+`([\w-]+)`", line)
        row = re.match(r"^\|\s*`([\w-]+)`\s*\|", line)
        if heading or row:
            keys.add((heading or row).group(1))
    return keys


def schema_name_pattern() -> re.Pattern:
    match = re.search(r"`/?(\^[^`]*?\$)/?`", schema_validation_section())
    if match is None:
        raise AssertionError("the validation section quotes no anchored name pattern")
    return re.compile(match.group(1))


# --- the repository at large -------------------------------------------------------------------


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return [f for f in result.stdout.split("\0") if f]


def read_tracked(relative: str) -> str | None:
    path = REPO_ROOT / relative
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
