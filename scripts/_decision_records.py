"""The decision-record gate's pure core: classify a path, judge a change, decide a verdict.

A decision record is a Markdown file under ``.ai-state/decisions/``. The shapes the
finalize chain promotes are narrow (a fragment named ``<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md``
directly under ``drafts/``, a ``dec-draft-<hash>`` id, one of four categories), and a record
outside them is stranded or numbered wrongly at merge. This module decides, from values alone,
whether a change to one leaves such a record behind. Adapters parse their input into
``Change`` and ``Read`` values and render the verdict; nothing here reads a file, a rule, a
branch or a clock, so the same judgement serves the write hook, the commit gate and the
pre-commit hook.

Existing debt is never judged: for a file that existed before the change, placement, name and
id are left alone and the category is judged only as *lost* (valid before, not valid after).

Stdlib-only and 3.9-safe (no runtime ``X | Y`` unions, no ``match``): the ambient ``python3``
runs it.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Union

# -- Where a record may live --------------------------------------------------------------

STATE_DIR = ".ai-state"
DECISIONS_DIR = f"{STATE_DIR}/decisions"
DECISIONS_PARTS = (STATE_DIR, "decisions")
DRAFTS_SUBDIR = "drafts"
INDEX_NAME = "DECISIONS_INDEX.md"
NON_RECORD_NAMES = frozenset({INDEX_NAME, "CLAUDE.md", "README.md"})
MARKDOWN_SUFFIX = ".md"

# -- The shapes finalize promotes (scripts/finalize_adrs_fragments.py and finalize_adrs.py) --
# ASCII digits only: ``\d`` would also take digits finalize has no use for.

FRAGMENT_NAME = re.compile(r"(?P<stamp>[0-9]{8}-[0-9]{4})-(?P<rest>[a-z0-9-]+)\.md")
STAMP_FORMAT = "%Y%m%d-%H%M"
# user, branch and slug: finalize refuses a name with fewer tokens after the stamp.
MIN_FRAGMENT_TOKENS = 3
NUMBERED_NAME = re.compile(r"(?P<number>[0-9]{3})-.+\.md")
DRAFT_ID = re.compile(r"dec-draft-(?P<hash>[0-9a-f]{8})")
NUMBERED_ID = re.compile(r"dec-(?P<number>[0-9]{3,})")

CATEGORIES = ("architectural", "behavioral", "implementation", "configuration")

_FRONTMATTER_FENCE = "---"
_FRONTMATTER_KEY = re.compile(r"(?P<key>id|category):[ \t]*(?P<value>.*?)[ \t]*")
_INLINE_COMMENT = re.compile(r"(?:^|\s)#")
_QUOTES = ("'", '"')
_BYTE_ORDER_MARK = "﻿"


# -- The closed vocabulary ----------------------------------------------------------------


class Defect(Enum):
    """Why a change is refused. Additive evolution only: consumers key on ``value``."""

    MISPLACED = "misplaced"
    NESTED = "nested"
    SELF_NUMBERED = "self-numbered"
    MALFORMED_NAME = "malformed-name"
    MALFORMED_ID = "malformed-id"
    SELF_PICKED_ID = "self-picked-id"
    NO_CATEGORY = "no-category"
    INVALID_CATEGORY = "invalid-category"
    CATEGORY_LOST = "category-lost"
    UNBOUNDED_INDEX_READ = "unbounded-index-read"


@dataclass(frozen=True)
class Outside:
    """A path that is not under the decisions directory."""


@dataclass(frozen=True)
class NonRecord:
    """A file under the decisions directory that is no record: the index, a guide, non-Markdown."""


@dataclass(frozen=True)
class Draft:
    """A record directly inside ``drafts/``."""

    name: str


@dataclass(frozen=True)
class TopLevel:
    """A record directly inside the decisions directory."""

    name: str


@dataclass(frozen=True)
class Nested:
    """A record in any other subdirectory."""

    subdir: str
    name: str


RecordPath = Union[Outside, NonRecord, Draft, TopLevel, Nested]  # noqa: UP007 -- runtime alias on 3.9


@dataclass(frozen=True)
class Fragment:
    stamp: datetime


@dataclass(frozen=True)
class Numbered:
    number: int


@dataclass(frozen=True)
class OtherName:
    text: str


NameForm = Union[Fragment, Numbered, OtherName]  # noqa: UP007 -- runtime alias on 3.9


@dataclass(frozen=True)
class DraftId:
    hash: str


@dataclass(frozen=True)
class NumberedId:
    number: int


@dataclass(frozen=True)
class OtherId:
    text: str


@dataclass(frozen=True)
class NoId:
    pass


IdForm = Union[DraftId, NumberedId, OtherId, NoId]  # noqa: UP007 -- runtime alias on 3.9


@dataclass(frozen=True)
class ValidCategory:
    value: str


@dataclass(frozen=True)
class MissingCategory:
    pass


@dataclass(frozen=True)
class InvalidCategory:
    text: str


CategoryForm = Union[ValidCategory, MissingCategory, InvalidCategory]  # noqa: UP007 -- runtime alias on 3.9


@dataclass(frozen=True)
class Change:
    """A write: ``before`` is ``None`` when the file does not exist yet."""

    path: str
    before: str | None
    after: str


@dataclass(frozen=True)
class Read:
    """A read of ``path``; ``bounded`` when the read carries a line limit."""

    path: str
    bounded: bool


@dataclass(frozen=True)
class Context:
    """What a verdict may depend on besides the change itself.

    ``on_main`` is the finalize predicate (branch ``main`` or ``master``); ``default_holds`` the
    numbered paths the default branch already holds (commit time only).
    """

    on_main: bool
    default_holds: frozenset[str]


# A session's write never creates a numbered record: only finalize at merge to main does.
WRITE_TIME_CONTEXT = Context(on_main=False, default_holds=frozenset())


@dataclass(frozen=True)
class Allowed:
    pass


@dataclass(frozen=True)
class Refused:
    path: str
    defects: tuple[Defect, ...]

    def __post_init__(self) -> None:
        if not self.defects:
            raise ValueError("a refusal must name at least one defect")


Verdict = Union[Allowed, Refused]  # noqa: UP007 -- runtime alias on 3.9


def decide(path: str, defects: tuple[Defect, ...]) -> Verdict:
    return Refused(path, defects) if defects else Allowed()


# -- Judging ------------------------------------------------------------------------------


def judge_change(change: Change, context: Context) -> Verdict:
    """Whether a write leaves the decisions directory in a shape finalize can carry."""
    return decide(change.path, _change_defects(change, context))


def judge_read(read: Read) -> Verdict:
    """A whole read of the decisions index is refused; every other read is allowed."""
    parts = _decisions_parts(read.path)
    is_index = parts is not None and len(parts) == 1 and parts[0].lower() == INDEX_NAME.lower()
    if is_index and not read.bounded:
        return Refused(read.path, (Defect.UNBOUNDED_INDEX_READ,))
    return Allowed()


def _change_defects(change: Change, context: Context) -> tuple[Defect, ...]:
    record_path = classify_path(change.path)
    if isinstance(record_path, (Outside, NonRecord)):
        return ()
    after = read_frontmatter(change.after)
    if change.before is not None:
        return _existing_record_defects(read_frontmatter(change.before), after)
    return _new_record_defects(record_path, change.path, after, context)


def _existing_record_defects(before: Frontmatter, after: Frontmatter) -> tuple[Defect, ...]:
    held_valid = isinstance(parse_category(before.category), ValidCategory)
    still_valid = isinstance(parse_category(after.category), ValidCategory)
    return (Defect.CATEGORY_LOST,) if held_valid and not still_valid else ()


def _new_record_defects(
    record_path: RecordPath, path: str, after: Frontmatter, context: Context
) -> tuple[Defect, ...]:
    if isinstance(record_path, TopLevel) and isinstance(classify_name(record_path.name), Numbered):
        # Promotion on main, or a record the default branch already holds (a merge, a rebase):
        # finalize's own output and old records, whose frontmatter is not this gate's to judge.
        if context.on_main or path in context.default_holds:
            return ()
    return (
        _placement_defects(record_path)
        + _draft_defects(record_path, after)
        + _category_defects(after)
    )


def _placement_defects(record_path: RecordPath) -> tuple[Defect, ...]:
    if isinstance(record_path, Nested):
        return (Defect.NESTED,)
    if isinstance(record_path, TopLevel):
        numbered = isinstance(classify_name(record_path.name), Numbered)
        return (Defect.SELF_NUMBERED if numbered else Defect.MISPLACED,)
    return ()


def _draft_defects(record_path: RecordPath, after: Frontmatter) -> tuple[Defect, ...]:
    if not isinstance(record_path, Draft):
        return ()
    name = () if isinstance(classify_name(record_path.name), Fragment) else (Defect.MALFORMED_NAME,)
    return name + _id_defects(parse_id(after.id))


def _id_defects(id_form: IdForm) -> tuple[Defect, ...]:
    if isinstance(id_form, DraftId):
        return ()
    return (Defect.SELF_PICKED_ID,) if isinstance(id_form, NumberedId) else (Defect.MALFORMED_ID,)


def _category_defects(after: Frontmatter) -> tuple[Defect, ...]:
    form = parse_category(after.category)
    if isinstance(form, MissingCategory):
        return (Defect.NO_CATEGORY,)
    return (Defect.INVALID_CATEGORY,) if isinstance(form, InvalidCategory) else ()


# -- Parsing at the boundary --------------------------------------------------------------


def classify_path(relpath: str) -> RecordPath:
    """Map a repo-relative path to exactly one variant."""
    parts = _decisions_parts(relpath)
    if parts is None:
        return Outside()
    name = parts[-1]
    if not name.lower().endswith(MARKDOWN_SUFFIX) or name in NON_RECORD_NAMES:
        return NonRecord()
    if len(parts) == 1:
        return TopLevel(name)
    if len(parts) == 2 and parts[0] == DRAFTS_SUBDIR:
        return Draft(name)
    return Nested("/".join(parts[:-1]), name)


def _decisions_parts(relpath: str) -> tuple[str, ...] | None:
    """The path's components below the decisions directory, or ``None`` outside it."""
    parts = posixpath.normpath(relpath.replace("\\", "/")).split("/")
    # Case-folded: on a case-insensitive filesystem `.AI-State/Decisions` is the same directory.
    inside = tuple(part.lower() for part in parts[:2]) == DECISIONS_PARTS
    return tuple(parts[2:]) if inside and len(parts) > 2 else None


def classify_name(name: str) -> NameForm:
    """A fragment name finalize would promote, a numbered name, or neither."""
    fragment = FRAGMENT_NAME.fullmatch(name)
    if fragment is not None:
        stamp = _parse_stamp(fragment.group("stamp"))
        if stamp is not None and len(fragment.group("rest").split("-")) >= MIN_FRAGMENT_TOKENS:
            return Fragment(stamp)
    numbered = NUMBERED_NAME.fullmatch(name)
    if numbered is not None:
        return Numbered(int(numbered.group("number")))
    return OtherName(name)


def _parse_stamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, STAMP_FORMAT)
    except ValueError:
        return None


def parse_id(value: str | None) -> IdForm:
    """The raw ``id`` value: unquoted and comment-free, as finalize reads it, or it is not a draft id."""
    if not value:
        return NoId()
    draft = DRAFT_ID.fullmatch(value)
    if draft is not None:
        return DraftId(draft.group("hash"))
    numbered = NUMBERED_ID.fullmatch(value)
    if numbered is not None:
        return NumberedId(int(numbered.group("number")))
    return OtherId(value)


def parse_category(value: str | None) -> CategoryForm:
    if not value:
        return MissingCategory()
    return ValidCategory(value) if value in CATEGORIES else InvalidCategory(value)


@dataclass(frozen=True)
class Frontmatter:
    """The two fields the gate judges, raw: ``id`` as written, ``category`` unquoted and uncommented."""

    id: str | None
    category: str | None


def read_frontmatter(text: str) -> Frontmatter:
    """Read ``id`` and ``category`` from a leading ``---`` block; the first of each key wins.

    Line-based on purpose: the gate must not depend on a YAML library, and finalize itself
    reads ``id`` with a line pattern. A block never closed is read to the end of the text.
    """
    lines = text.lstrip(_BYTE_ORDER_MARK).splitlines()
    if not lines or lines[0].rstrip() != _FRONTMATTER_FENCE:
        return Frontmatter(None, None)
    found: dict[str, str] = {}
    for line in lines[1:]:
        if line.rstrip() == _FRONTMATTER_FENCE:
            break
        match = _FRONTMATTER_KEY.fullmatch(line)
        if match is not None:
            found.setdefault(match.group("key"), match.group("value"))
    return Frontmatter(found.get("id") or None, _clean_category(found.get("category")))


def _clean_category(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = _INLINE_COMMENT.split(raw, maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES:
        value = value[1:-1]
    return value or None
