"""The always-loaded guidance, found and cut: sources, sections and parts.

The kernel generator and its manifest checker both begin from the same question:
which text does every session of the main agent carry, and how is that text
divided? This module answers it from the repository alone, in plain values, and
decides nothing about who the text is for (that is the audience manifest's job).

What is always loaded -- found by reading the tree, never from a list, so a new
rule without a path scope is covered the day it is written:

- every `rules/**/*.md` whose frontmatter declares no `paths:` key, except the
  directory guides (`README.md`, `CLAUDE.md`), which are not rules;
- the user-level template `claude/config/CLAUDE.md.tmpl` (the source, never its
  render under `claude/config/CLAUDE.md`);
- the checkout's own root `CLAUDE.md`.

Those three belong to a plugin checkout. A managed project's own `CLAUDE.md` is
never classified: the repository must carry the user template to be read at all,
and any other root is refused loudly rather than read as an empty set (an empty
set would let a totality gate pass over nothing).

How text is cut, so that a pin taken by one tool equals the pin checked by another:

- a *section* runs from a heading of level two to four (code fences respected,
  frontmatter skipped) to the line before the next such heading; its text is the
  exact bytes of the file, and its sha is the sha1 of them;
- a *part* of a section starts at the one line that begins with its prefix and
  runs to the next part or the section's end. Text between the heading and the
  first part is a leading part with no prefix, unless it is only blank lines.

Stdlib-only, like the generator it serves, so a bare `python3` can run it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from _markdown_tables import code_mask

USER_TEMPLATE = "claude/config/CLAUDE.md.tmpl"
PROJECT_INSTRUCTIONS = "CLAUDE.md"
RULES_DIR = "rules"

# A directory guide documents a tree; it is not a rule and is never always loaded.
_DIRECTORY_GUIDES = frozenset({"README.md", "CLAUDE.md"})

_FRONTMATTER_DELIMITER = "---"
_PATHS_KEY = re.compile(r"""^["']?paths["']?\s*:""")  # top level only: no leading space
_HEADING = re.compile(r"^(#{2,4})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_LINE = re.compile(r"[^\n]*\n|[^\n]+")  # keeps every line ending, and splits on \n alone

_ABSENT = "absent"
_AMBIGUOUS = "ambiguous"


class NotAPluginCheckoutError(ValueError):
    """The root carries no user template, so none of its guidance is ours to classify."""


class PartPrefixError(ValueError):
    """A part prefix that does not pick out exactly one line of its section."""

    def __init__(self, section: Section, prefix: str, kind: str) -> None:
        reason = {
            _ABSENT: "starts no line of the section",
            _AMBIGUOUS: "does not pick out one part of the section",
        }[kind]
        super().__init__(f"part prefix {prefix!r} {reason}: {section.source} '{section.heading}'")
        self.prefix = prefix
        self.kind = kind


@dataclass(frozen=True)
class Section:
    source: str  # repository-relative path of the file
    level: int  # 2 to 4
    heading: str  # the heading's text without hashes
    text: str  # exact bytes, heading line through the line before the next heading

    @property
    def sha(self) -> str:
        return sha1_hex(self.text)


@dataclass(frozen=True)
class Part:
    source: str
    heading: str  # the section's heading
    prefix: str | None  # None for text that precedes the first prefixed part
    text: str

    @property
    def sha(self) -> str:
        return sha1_hex(self.text)


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()


# -- Pure: cutting text -----------------------------------------------------------


def split_sections(source: str, text: str) -> tuple[Section, ...]:
    lines = _lines(text)
    body_start = _frontmatter_end(lines)
    body = lines[body_start:]
    in_code = code_mask([_without_ending(line) for line in body])
    headings = [
        (body_start + index, len(match.group(1)), match.group(2))
        for index, line in enumerate(body)
        if not in_code[index] and (match := _HEADING.match(_without_ending(line)))
    ]
    ends = [start for start, _, _ in headings[1:]] + [len(lines)]
    return tuple(
        Section(source, level, heading, "".join(lines[start:end]))
        for (start, level, heading), end in zip(headings, ends, strict=True)
    )


def split_parts(section: Section, prefixes: Iterable[str]) -> tuple[Part, ...]:
    """The parts of `section`, in document order; refuses a prefix that is not unique."""
    lines = _lines(section.text)
    starts = sorted((_line_starting_with(section, lines, prefix), prefix) for prefix in prefixes)
    firsts = [start for start, _ in starts]
    for (start, prefix), previous in zip(starts[1:], firsts, strict=False):
        if start == previous:
            raise PartPrefixError(section, prefix, _AMBIGUOUS)
    ends = firsts[1:] + [len(lines)]
    lead_end = firsts[0] if firsts else len(lines)
    parts = [
        Part(section.source, section.heading, prefix, "".join(lines[start:end]))
        for (start, prefix), end in zip(starts, ends, strict=True)
    ]
    if any(line.strip() for line in lines[1:lead_end]):  # more than blank lines after the heading
        parts.insert(0, Part(section.source, section.heading, None, "".join(lines[:lead_end])))
    return tuple(parts)


def is_path_scoped(text: str) -> bool:
    """True when the frontmatter declares a top-level `paths` key (the rule loads on demand)."""
    lines = _lines(text)
    body_start = _frontmatter_end(lines)
    declared = lines[1 : body_start - 1] if body_start else []
    return any(_PATHS_KEY.match(line) for line in declared)


def _lines(text: str) -> list[str]:
    return _LINE.findall(text)


def _without_ending(line: str) -> str:
    return line.rstrip("\r\n")


def _frontmatter_end(lines: list[str]) -> int:
    """The index of the first line after the frontmatter; 0 when there is none."""
    if not lines or _without_ending(lines[0]).rstrip() != _FRONTMATTER_DELIMITER:
        return 0
    for index in range(1, len(lines)):
        if _without_ending(lines[index]).rstrip() == _FRONTMATTER_DELIMITER:
            return index + 1
    return 0  # never closed: not frontmatter, so its lines are read as text


def _line_starting_with(section: Section, lines: list[str], prefix: str) -> int:
    matches = [i for i in range(1, len(lines)) if lines[i].startswith(prefix)]
    if len(matches) != 1:
        raise PartPrefixError(section, prefix, _ABSENT if not matches else _AMBIGUOUS)
    return matches[0]


# -- Edge: reading the repository -------------------------------------------------


def always_loaded_sources(root: Path) -> tuple[str, ...]:
    """Repository-relative paths of the always-loaded sources: rules, template, project file."""
    if not (root / USER_TEMPLATE).is_file():
        raise NotAPluginCheckoutError(f"{root} has no {USER_TEMPLATE}: not a plugin checkout")
    rules = sorted(
        path.relative_to(root).as_posix()
        for path in (root / RULES_DIR).rglob("*.md")
        if path.name not in _DIRECTORY_GUIDES and not is_path_scoped(_read(path))
    )
    project = [PROJECT_INSTRUCTIONS] if (root / PROJECT_INSTRUCTIONS).is_file() else []
    return (*rules, USER_TEMPLATE, *project)


def load_sections(root: Path, source: str) -> tuple[Section, ...]:
    return split_sections(source, _read(root / source))


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")  # bytes as written: a sha must not depend on newlines
