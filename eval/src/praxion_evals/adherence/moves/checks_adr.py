"""The decision records a session leaves in a repository, parsed once into values.

The adr-conventions move's two governed checks grade these records, never the session's words. This
module reads the end state and does no grading: each record's file name, id and category are
classified into closed sum types whose variants are disjoint, so a grader can fail one part of the
rule without failing another.

A decision record is a Markdown file in the end-state tree that the baseline tree did not hold,
outside ``.git/`` and ``.ai-work/``. Discovery walks the filesystem and ignores ``.gitignore``, so a
record a session wrote under an ignored path is still a record.

The fixture's branch is fixed by the fixture, so the fragment schema's branch segment is judged
against it: a stamp-shaped name carrying another branch is ``OtherName``, never numbered.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from praxion_evals.adherence.moves.checks_git import BASELINE_REF
from praxion_evals.adherence.moves.fixture_project import git
from praxion_evals.adherence.moves.model import holds_phrase

BRANCH_REF = (
    "refs/fixture/branch"  # a symbolic ref to the branch heads/<name> the session starts on
)
_HEADS_PREFIX = "refs/heads/"

DRAFTS_DIR = ".ai-state/decisions/drafts"
_EXCLUDED_ROOTS = frozenset({".git", ".ai-work"})
BRANCH_SEGMENT_LIMIT = 40

_STAMP_FORMAT = "%Y%m%d-%H%M"
_STAMP_SHAPED = re.compile(r"(?P<stamp>\d{8}-\d{4})-(?P<rest>.+)\.md")
_NUMBERED = re.compile(r"(?P<number>\d+)-(?P<slug>.+)\.md")
_DRAFT_ID = re.compile(r"dec-draft-(?P<hex8>[0-9a-f]{8})")
_NUMBERED_ID = re.compile(r"dec-(?P<number>\d+)")
_HEADING = re.compile(r"(?P<hashes>#{1,6})\s+(?P<title>.*?)\s*")
_FRONTMATTER_FENCE = "---"

DISCONFIRMATION_HEADING = "disconfirmation"
DISCONFIRMATION_ITEMS = ("falsifier", "steelmanned runner-up", "reversal trigger")


# -- Values -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fragment:
    stamp: datetime
    rest: str  # "<user>-<branch segment>-<slug>": the segment lies between two non-empty sides


@dataclass(frozen=True)
class NumberedName:
    number: int
    slug: str


@dataclass(frozen=True)
class OtherName:
    text: str


NameForm = Fragment | NumberedName | OtherName


@dataclass(frozen=True)
class DraftId:
    hex8: str


@dataclass(frozen=True)
class NumberedId:
    number: int


@dataclass(frozen=True)
class OtherId:
    text: str


@dataclass(frozen=True)
class NoId: ...


IdForm = DraftId | NumberedId | OtherId | NoId


@dataclass(frozen=True)
class DecisionRecord:
    path: str  # repo-relative, POSIX separators
    in_drafts: bool  # the record's parent is exactly the draft directory
    name: NameForm
    id: IdForm
    category: str | None  # as written; its comparison is the grader's
    disconfirmed: bool  # a Disconfirmation section naming a falsifier, runner-up and trigger


# -- Reading the end state --------------------------------------------------------------------


def baseline_paths(repo: Path) -> frozenset[str]:
    """The paths the fixture's baseline tree holds: what is not a record the session left."""
    listing = git(repo, "ls-tree", "-r", "-z", "--name-only", BASELINE_REF)
    return frozenset(path for path in listing.split("\0") if path)


def fixture_branch(repo: Path) -> str:
    """The branch the fixture named for the session to work on."""
    return git(repo, "symbolic-ref", BRANCH_REF).strip().removeprefix(_HEADS_PREFIX)


def read_records(repo: Path, *, before: frozenset[str], branch: str) -> tuple[DecisionRecord, ...]:
    """Every Markdown file now in ``repo`` that ``before`` did not hold, as a record, in path order."""
    return tuple(
        _parse_record(repo, path, branch)
        for path in sorted(_markdown_paths(repo))
        if path not in before
    )


def _markdown_paths(repo: Path) -> list[str]:
    found: list[str] = []
    for directory, subdirectories, filenames in os.walk(repo):
        relative_dir = Path(directory).relative_to(repo)
        if relative_dir == Path("."):
            subdirectories[:] = [d for d in subdirectories if d not in _EXCLUDED_ROOTS]
        found += [
            (relative_dir / name).as_posix() for name in filenames if name.lower().endswith(".md")
        ]
    return found


def _parse_record(repo: Path, path: str, branch: str) -> DecisionRecord:
    text = (repo / path).read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _split_frontmatter(text)
    return DecisionRecord(
        path=path,
        in_drafts=Path(path).parent.as_posix() == DRAFTS_DIR,
        name=classify_name(Path(path).name, branch),
        id=classify_id(frontmatter.get("id")),
        category=_category(frontmatter.get("category")),
        disconfirmed=_disconfirmed(body),
    )


# -- Frontmatter ------------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict[object, object], str]:
    """The parsed frontmatter and the text after it; a file without readable frontmatter has an
    empty mapping, which reads as no id and no category."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, text
    closing = next(
        (i for i, line in enumerate(lines[1:], start=1) if line.strip() == _FRONTMATTER_FENCE), None
    )
    if closing is None:
        return {}, text
    body = "\n".join(lines[closing + 1 :])
    try:
        parsed = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError:
        return {}, body
    return (parsed if isinstance(parsed, dict) else {}), body


def _category(value: object) -> str | None:
    return None if value is None else str(value)


# -- Names ------------------------------------------------------------------------------------


def branch_segment(branch: str) -> str:
    """The branch as a fragment name writes it: lowercased, each run of characters other than
    lowercase letters, digits and hyphens made one hyphen, outer hyphens trimmed, cut to 40."""
    return _uncut_segment(branch)[:BRANCH_SEGMENT_LIMIT]


def _uncut_segment(branch: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", branch.lower()).strip("-")


def classify_name(filename: str, branch: str) -> NameForm:
    """Read a file name as a fragment of ``branch``, a record that numbers itself, or neither.

    A stamp-shaped name is never numbered: with an impossible date, the wrong branch or the branch
    uncut past the limit it is ``OtherName``, because it tried to be a fragment and failed."""
    stamped = _STAMP_SHAPED.fullmatch(filename)
    if stamped:
        return _fragment(filename, stamped["stamp"], stamped["rest"], branch)
    numbered = _NUMBERED.fullmatch(filename)
    if numbered:
        return NumberedName(int(numbered["number"]), numbered["slug"])
    return OtherName(filename)


def _fragment(filename: str, stamp_text: str, rest: str, branch: str) -> NameForm:
    try:
        stamp = datetime.strptime(stamp_text, _STAMP_FORMAT)
    except ValueError:
        return OtherName(filename)
    uncut = _uncut_segment(branch)
    carries_uncut = len(uncut) > BRANCH_SEGMENT_LIMIT and _between_sides(rest, uncut)
    if carries_uncut or not _between_sides(rest, branch_segment(branch)):
        return OtherName(filename)
    return Fragment(stamp, rest)


def _between_sides(rest: str, segment: str) -> bool:
    """Whether ``-segment-`` lies in ``rest`` with a non-empty user before and slug after."""
    return re.fullmatch(rf".+-{re.escape(segment)}-.+", rest) is not None


# -- Ids --------------------------------------------------------------------------------------


def classify_id(value: object) -> IdForm:
    """Read a frontmatter ``id`` as a draft id, a numbered id, some other text, or none."""
    if value is None:
        return NoId()
    text = str(value)
    draft = _DRAFT_ID.fullmatch(text)
    if draft:
        return DraftId(draft["hex8"])
    numbered = _NUMBERED_ID.fullmatch(text)
    if numbered:
        return NumberedId(int(numbered["number"]))
    return OtherId(text)


# -- Disconfirmation --------------------------------------------------------------------------


def _disconfirmed(body: str) -> bool:
    """Whether a heading holding ``disconfirmation`` has a section naming all three items."""
    return any(
        all(holds_phrase(span, item) for item in DISCONFIRMATION_ITEMS)
        for span in _disconfirmation_spans(body.splitlines())
    )


def _disconfirmation_spans(lines: list[str]) -> list[str]:
    """Each such section's text: its heading through the line before the next heading of the same
    or a higher level."""
    spans: list[str] = []
    for start, line in enumerate(lines):
        heading = _HEADING.fullmatch(line)
        if not heading or not holds_phrase(heading["title"], DISCONFIRMATION_HEADING):
            continue
        level = len(heading["hashes"])
        end = next(
            (i for i in range(start + 1, len(lines)) if _level(lines[i]) in range(1, level + 1)),
            len(lines),
        )
        spans.append("\n".join(lines[start:end]))
    return spans


def _level(line: str) -> int:
    heading = _HEADING.fullmatch(line)
    return len(heading["hashes"]) if heading else 0
