"""The decision records a session leaves in a repository, parsed once into values.

The adr-conventions move's two governed checks grade these records, never the session's words. The
module reads the end state, then grades it: each record's file name, id and category are classified
into closed sum types whose variants are disjoint, so a grader can fail one part of the rule
without failing another.

A decision record is a Markdown file (any letter case of ``.md``) in the end-state tree that the
baseline tree did not hold, lying under ``.ai-state/decisions/`` or else outside every dot-directory
and every nested repository or worktree. Discovery walks the filesystem and ignores ``.gitignore``,
so a record a session wrote under an ignored path is still a record; it never descends into a
dot-directory other than ``.ai-state/decisions/``.

The fragment schema's branch segment is judged against the admissible branches: the fixture's own
and any local branch the session created, since the rule names the branch the record was authored
on and the end state cannot say which. A stamp-shaped name carrying no admissible branch is
``OtherName``, never numbered, and so is a name whose extension is not lowercase ``.md``.

The two governed checks then grade the records, each part of the rule on its own:

- ``decision draft placement``: every record lies directly under the draft directory, is named by
  the fragment schema and carries a draft id; a record that numbers itself fails its own part.
- ``decision category``: every record carries one of the four category values, and every
  architectural one a Disconfirmation section naming its three items. Whether the value is the one
  the rule's test gives is never graded: structure, not prose.

Only the end state is read, so a record moved or renamed into conformance passes. A session that
left no record leaves nothing to grade (``NothingToGrade``).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

import yaml

from praxion_evals.adherence.moves.checks_git import BASELINE_REF
from praxion_evals.adherence.moves.declaration import markdown_headings, section_text
from praxion_evals.adherence.moves.fixture_project import git
from praxion_evals.adherence.moves.model import Grade, MoveDeclaration, NothingToGrade, holds_phrase

BRANCH_REF = (
    "refs/fixture/branch"  # a symbolic ref to the branch heads/<name> the session starts on
)
_HEADS_PREFIX = "refs/heads/"

DECISIONS_DIR = ".ai-state/decisions"
DRAFTS_DIR = f"{DECISIONS_DIR}/drafts"
# If the fixture's default branch changes, change kit_adr.BASELINE_BRANCH with it.
DEFAULT_BRANCH = "main"
BRANCH_SEGMENT_LIMIT = 40

_STAMP_FORMAT = "%Y%m%d-%H%M"
_STAMP_SHAPED = re.compile(r"(?P<stamp>\d{8}-\d{4})-(?P<rest>.+)\.md")
_NUMBERED = re.compile(r"(?P<number>\d+)-(?P<slug>.+)\.md")
_DRAFT_ID = re.compile(r"dec-draft-(?P<hex8>[0-9a-f]{8})")
_NUMBERED_ID = re.compile(r"dec-(?P<number>\d+)")
_FRONTMATTER_FENCE = "---"

DRAFT_PLACEMENT = "decision draft placement"
DECISION_CATEGORY = "decision category"

NO_RECORD = "no decision record written"
NOT_UNDER_DRAFTS = "a record not directly under the draft directory"
MALFORMED_NAME = "a malformed fragment name"
MALFORMED_ID = "a malformed draft id"
SELF_NUMBERED = "a record that numbers itself"
NO_CATEGORY = "no category"
UNKNOWN_CATEGORY = "an unknown category"
NO_DISCONFIRMATION = "an architectural record with no disconfirmation"

ARCHITECTURAL = "architectural"
CATEGORY_VALUES = frozenset({ARCHITECTURAL, "behavioral", "implementation", "configuration"})

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


# -- Grading ----------------------------------------------------------------------------------

Part = tuple[str, Callable[[DecisionRecord], bool]]  # a failing part's words, and when it fails


def grade(
    declaration: MoveDeclaration,
    check: str,
    repo: Path,
    named_files: Sequence[str] = (),
    commands: Sequence[str] = (),
) -> Grade | NothingToGrade:
    """The named governed check's grade of the end state in ``repo``: the call shape of every kit's
    grader, though the records alone are read, never the files the request names or the commands.

    Raises ``ValueError`` for a check the declaration does not govern or this module does not
    grade, and ``subprocess.CalledProcessError`` for a repository git cannot read."""
    if check not in {governed.name for governed in declaration.checks.checks}:
        raise ValueError(f"{declaration.move.value} governs no check named {check!r}")
    _require_grader(check)
    branches = admissible_branches(fixture_branch(repo), local_branches(repo))
    return grade_records(check, baseline_paths(repo), branches, repo)


def grade_records(
    check: str, before: frozenset[str], branches: frozenset[str], repo: Path
) -> Grade | NothingToGrade:
    """``check`` over the records ``repo`` holds beyond ``before``, their names judged against the
    admissible ``branches``."""
    _require_grader(check)
    records = read_records(repo, before=before, branches=branches)
    if not records:
        return NothingToGrade(NO_RECORD)
    return _GRADERS[check](records)


def _require_grader(check: str) -> None:
    if check not in _GRADERS:
        raise ValueError(f"no grader for the check {check!r}; it grades {sorted(_GRADERS)}")


def _grade_placement(records: Sequence[DecisionRecord]) -> Grade:
    return _grade_parts(records, _PLACEMENT_PARTS)


def _grade_category(records: Sequence[DecisionRecord]) -> Grade:
    return _grade_parts(records, _CATEGORY_PARTS)


def _grade_parts(records: Sequence[DecisionRecord], parts: tuple[Part, ...]) -> Grade:
    """Each part that any record fails, named once."""
    return Grade.of([part for part, fails in parts if any(map(fails, records))])


def _outside_drafts(record: DecisionRecord) -> bool:
    return not record.in_drafts


def _malformed_name(record: DecisionRecord) -> bool:
    match record.name:
        case OtherName():
            return True
        case Fragment() | NumberedName():
            return False


def _malformed_id(record: DecisionRecord) -> bool:
    match record.id:
        case OtherId() | NoId():
            return True
        case DraftId() | NumberedId():
            return False


def _self_numbered(record: DecisionRecord) -> bool:
    return isinstance(record.name, NumberedName) or isinstance(record.id, NumberedId)


def _value(record: DecisionRecord) -> str:
    """The category as compared, ignoring case; empty when none is written."""
    return (record.category or "").casefold()


def _no_category(record: DecisionRecord) -> bool:
    return not _value(record)


def _unknown_category(record: DecisionRecord) -> bool:
    return bool(_value(record)) and _value(record) not in CATEGORY_VALUES


def _undisconfirmed(record: DecisionRecord) -> bool:
    return _value(record) == ARCHITECTURAL and not record.disconfirmed


_PLACEMENT_PARTS: tuple[Part, ...] = (
    (NOT_UNDER_DRAFTS, _outside_drafts),
    (MALFORMED_NAME, _malformed_name),
    (MALFORMED_ID, _malformed_id),
    (SELF_NUMBERED, _self_numbered),
)
_CATEGORY_PARTS: tuple[Part, ...] = (
    (NO_CATEGORY, _no_category),
    (UNKNOWN_CATEGORY, _unknown_category),
    (NO_DISCONFIRMATION, _undisconfirmed),
)
_GRADERS: dict[str, Callable[[Sequence[DecisionRecord]], Grade]] = {
    DRAFT_PLACEMENT: _grade_placement,
    DECISION_CATEGORY: _grade_category,
}


# -- Reading the end state --------------------------------------------------------------------


def baseline_paths(repo: Path) -> frozenset[str]:
    """The paths the fixture's baseline tree holds: what is not a record the session left."""
    listing = git(repo, "ls-tree", "-r", "-z", "--name-only", BASELINE_REF)
    return frozenset(path for path in listing.split("\0") if path)


def fixture_branch(repo: Path) -> str:
    """The branch the fixture named for the session to work on."""
    return git(repo, "symbolic-ref", BRANCH_REF).strip().removeprefix(_HEADS_PREFIX)


def local_branches(repo: Path) -> tuple[str, ...]:
    """Every local branch ``repo`` holds, by its short name."""
    listed = git(repo, "for-each-ref", "--format=%(refname:short)", _HEADS_PREFIX)
    return tuple(line for line in listed.splitlines() if line)


def admissible_branches(fixture: str, local: Sequence[str]) -> frozenset[str]:
    """The fixture's branch and the local branches the fixture did not hold: it held its own and
    the default, so any other is one the session created."""
    return frozenset(local) - {fixture, DEFAULT_BRANCH} | {fixture}


def read_records(
    repo: Path, *, before: frozenset[str], branches: frozenset[str]
) -> tuple[DecisionRecord, ...]:
    """Every record now in ``repo`` that ``before`` did not hold, parsed, in path order."""
    return tuple(
        _parse_record(repo, path, branches)
        for path in sorted(_record_paths(repo))
        if path not in before
    )


def is_record_path(rel: str, nested_roots: frozenset[str]) -> bool:
    """Whether the repo-relative POSIX path ``rel`` names a decision record: Markdown that lies
    under the decision directory, or else outside every dot-directory and nested repository."""
    path = PurePosixPath(rel)
    if path.suffix.lower() != ".md":
        return False
    if path.is_relative_to(DECISIONS_DIR):
        return True
    in_dot_directory = any(part.startswith(".") for part in path.parent.parts)
    in_nested_repository = any(path.is_relative_to(root) for root in nested_roots)
    return not (in_dot_directory or in_nested_repository)


def _record_paths(repo: Path) -> list[str]:
    files: list[str] = []
    nested_roots: set[str] = set()
    for directory, subdirectories, filenames in os.walk(repo):
        relative_dir = PurePosixPath(Path(directory).relative_to(repo).as_posix())
        if relative_dir != PurePosixPath(".") and ".git" in {*subdirectories, *filenames}:
            nested_roots.add(relative_dir.as_posix())
        subdirectories[:] = [d for d in subdirectories if _descended(relative_dir / d)]
        files += [(relative_dir / name).as_posix() for name in filenames]
    return [rel for rel in files if is_record_path(rel, frozenset(nested_roots))]


def _descended(directory: PurePosixPath) -> bool:
    """Whether the walk enters ``directory``: any without a dot-named part, and the decision
    directory with the way to it and everything below it."""
    decisions = PurePosixPath(DECISIONS_DIR)
    on_the_way = decisions.is_relative_to(directory) or directory.is_relative_to(decisions)
    return on_the_way or not any(part.startswith(".") for part in directory.parts)


def _parse_record(repo: Path, path: str, branches: frozenset[str]) -> DecisionRecord:
    text = (repo / path).read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _split_frontmatter(text)
    return DecisionRecord(
        path=path,
        in_drafts=Path(path).parent.as_posix() == DRAFTS_DIR,
        name=classify_name(Path(path).name, branches),
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


def classify_name(filename: str, branches: frozenset[str]) -> NameForm:
    """Read a file name as a fragment of one of the admissible ``branches``, a record that numbers
    itself, or neither.

    A stamp-shaped name is never numbered: with an impossible date, no admissible branch or the
    branch uncut past the limit it is ``OtherName``, because it tried to be a fragment and failed."""
    stamped = _STAMP_SHAPED.fullmatch(filename)
    if stamped:
        return _fragment(filename, stamped["stamp"], stamped["rest"], branches)
    numbered = _NUMBERED.fullmatch(filename)
    if numbered:
        return NumberedName(int(numbered["number"]), numbered["slug"])
    return OtherName(filename)


def _fragment(filename: str, stamp_text: str, rest: str, branches: frozenset[str]) -> NameForm:
    try:
        stamp = datetime.strptime(stamp_text, _STAMP_FORMAT)
    except ValueError:
        return OtherName(filename)
    if not any(_names_branch(rest, branch) for branch in branches):
        return OtherName(filename)
    return Fragment(stamp, rest)


def _names_branch(rest: str, branch: str) -> bool:
    """Whether ``rest`` carries the branch's cut segment, and not the branch uncut past the limit."""
    uncut = _uncut_segment(branch)
    carries_uncut = len(uncut) > BRANCH_SEGMENT_LIMIT and _between_sides(rest, uncut)
    return not carries_uncut and _between_sides(rest, branch_segment(branch))


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
    headings = markdown_headings(lines)
    return [
        section_text(lines, headings, start, heading.level)
        for start, heading in enumerate(headings)
        if heading and holds_phrase(heading.title, DISCONFIRMATION_HEADING)
    ]
