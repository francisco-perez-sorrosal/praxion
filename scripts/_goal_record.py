"""The judgement of one goal iteration: kept as progress, left out, or stopped on a protected path.

Pure: counts, paths and line counts arrive by value, and nothing here opens a file, reads a
repository or starts a process, so the same evidence always gives the same answer. The shell
that gathers the evidence and acts on the answer lives elsewhere.

Judged in this order, the first that applies deciding:

1. A changed path under the protected set: `Protected`, whatever else holds.
2. A red gate: `Unkept`.
3. A regression against the reference reading (more failures or fewer passes): `Unkept`.
4. No path of the step's `Files:` differs from the last commit: `Unkept`.
5. The progress record gained no line: `Unkept`.
6. Otherwise: `Progressing`.

Runs on the bare `python3` the scripts are invoked with, so no `X | Y` at runtime.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Union

from _step_schema import Counts, parse_result_line

DEFAULT_PROTECTED = (
    "tests/acceptance/**",
    "tests/e2e/**",
    "CLAUDE.md",
    "rules/**",
    "agents/**",
    "skills/**",
    ".claude/**",
)
PROGRESS_HEADING = "## Progress record"
NODE_SEPARATOR = "::"

_DIRECTORY_SUFFIXES = ("/**", "/*", "/")
_GLOB_CHARACTERS = frozenset("*?[")
_PENDING_TOKEN_RE = re.compile(r"(?:^|\s)pending=(?P<count>[0-9]+)(?:\s|$)")
_SECTION_END_RE = re.compile(r"^#{1,2}[ \t]")


# --- The reading of a check run, and the reference it is compared with ---


@dataclass(frozen=True)
class Reading:
    """What a check run showed: the tests that passed and those that failed, pended or errored."""

    passes: int
    failures: int

    def __post_init__(self) -> None:
        if self.passes < 0 or self.failures < 0:
            raise ValueError("a reading cannot count fewer than none")

    def regressed_from(self, reference: Reading) -> bool:
        """Worse than `reference` on either count; equal counts are not worse."""
        return self.failures > reference.failures or self.passes < reference.passes


def reading_from_result(line: str) -> Reading | None:
    """A `Result:` line's counts as a reading; None for a line that is not a count line.

    A goal's own failing tests are `pending` on the line, so they count as failures here."""
    counts = parse_result_line(line)
    if not isinstance(counts, Counts):
        return None
    pending = _PENDING_TOKEN_RE.search(line)
    pended = int(pending["count"]) if pending else 0
    return Reading(counts.passed, counts.failed + pended + counts.errors)


def progress_line_count(wip_text: str) -> int:
    """The non-blank lines under `## Progress record`, up to the next heading; 0 without one."""
    count, inside = 0, False
    for line in wip_text.splitlines():
        if line.rstrip() == PROGRESS_HEADING:
            inside = True
        elif inside and _SECTION_END_RE.match(line):
            break
        elif inside and line.strip():
            count += 1
    return count


# --- The protected set ---


def protected_set(read_only: Iterable[str]) -> tuple[str, ...]:
    """The default set plus a step's `Read-only:` entries, each once, in order."""
    return tuple(dict.fromkeys((*DEFAULT_PROTECTED, *read_only)))


def is_protected(path: str, protected: Iterable[str]) -> bool:
    """Whether `path` is an entry itself, under an entry that names a directory, or matches a glob.

    A path matches an entry from its start, so `CLAUDE.md` is the root file only."""
    return any(_covers(entry, path) for entry in protected)


def changed_protected(changed: Iterable[str], protected: Iterable[str]) -> tuple[str, ...]:
    """The changed paths that are under the protected set, in the order given."""
    entries = tuple(protected)
    return tuple(path for path in changed if is_protected(path, entries))


def _covers(entry: str, path: str) -> bool:
    base = _entry_base(entry)
    return path == base or path.startswith(f"{base}/") or _glob_covers(entry, path)


def _entry_base(entry: str) -> str:
    """The path an entry names: a test node id protects its whole file."""
    base = entry.partition(NODE_SEPARATOR)[0].removeprefix("./")
    for suffix in _DIRECTORY_SUFFIXES:
        if base.endswith(suffix):
            return base.removesuffix(suffix)
    return base


def _glob_covers(entry: str, path: str) -> bool:
    return not _GLOB_CHARACTERS.isdisjoint(entry) and fnmatch.fnmatchcase(path, entry)


# --- The judgement ---


@dataclass(frozen=True)
class Progressing:
    """The iteration is kept: it commits."""


@dataclass(frozen=True)
class Unkept:
    """The iteration is not kept, for `reason`: it commits nothing."""

    reason: str


@dataclass(frozen=True)
class Protected:
    """The iteration changed `paths` under the protected set: a person decides."""

    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.paths:
            raise ValueError("a protected change names at least one path")


Judgement = Union[Progressing, Unkept, Protected]  # noqa: UP007 -- runtime value, 3.9 floor

RED_GATE = "the gate is red"
NO_FILE_CHANGED = "no path in Files: differs from the last commit"
NO_PROGRESS_LINE = "the progress record gained no line"


@dataclass(frozen=True)
class Evidence:
    """Everything the judgement reads about one iteration.

    `changed_files` are the step's `Files:` paths that differ from the last commit;
    `protected_changes` are the changed paths under the protected set; the progress counts are
    the lines of the progress record before the iteration and now."""

    red: bool
    reading: Reading
    reference: Reading
    changed_files: tuple[str, ...]
    progress_before: int
    progress_now: int
    protected_changes: tuple[str, ...] = ()


def judge(evidence: Evidence) -> Judgement:
    """Decide one iteration from `evidence`, by the order in this module's docstring."""
    if evidence.protected_changes:
        return Protected(evidence.protected_changes)
    if evidence.red:
        return Unkept(RED_GATE)
    if evidence.reading.regressed_from(evidence.reference):
        return Unkept(_regression_reason(evidence.reading, evidence.reference))
    if not evidence.changed_files:
        return Unkept(NO_FILE_CHANGED)
    if evidence.progress_now <= evidence.progress_before:
        return Unkept(NO_PROGRESS_LINE)
    return Progressing()


def _regression_reason(reading: Reading, reference: Reading) -> str:
    return (
        f"the check regressed: {reading.passes} passing and {reading.failures} failing, "
        f"against {reference.passes} passing and {reference.failures} failing"
    )
