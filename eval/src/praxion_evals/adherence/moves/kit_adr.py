"""The adr-conventions kit's fixtures: a managed project in the older habit of recording decisions.

A session is asked to record a decision its branch made, in a scratch project whose own records
follow the habit the moved rule replaced: numbered ``NNN-slug.md`` files with an ``id`` of
``dec-NNN``, no ``category`` and no Disconfirmation. A session that copies the project rather than
the rule numbers its record, leaves it outside the draft directory and names no category. The two
governed checks grade those records (``checks_adr``), never the session's words.

The fixture's branch is fixed by the fixture and named by ``checks_adr.BRANCH_REF``, so the
fragment schema's branch segment can be judged against it. The history ends at
``checks_git.BASELINE_REF``, so the records a session leaves are those the baseline tree lacks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from praxion_evals.adherence.moves.checks_adr import BRANCH_REF
from praxion_evals.adherence.moves.checks_git import BASELINE_REF
from praxion_evals.adherence.moves.fixture_project import (
    IDENTITY,
    Files,
    git,
    project_instructions,
    write_files,
)
from praxion_evals.adherence.moves.model import FixtureKind, MoveDeclaration, admits
from praxion_evals.adherence.moves.tasks import MoveTask

FIXTURE_KIND: FixtureKind = "managed"  # a decision record belongs to a project that keeps state

# A project that keeps decision records is not a sidecar project and is not mid-hackathon.
EXCLUDED_BLOCKS = frozenset({"sidecar-placement.md", "hackathon-mode.md"})

BASELINE_BRANCH = "main"
_RESERVED_BRANCHES = frozenset({BASELINE_BRANCH, "master"})
_BRANCH_FORM = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MIN_PRIOR_RECORDS = 2

DECISIONS_DIRECTORY = ".ai-state/decisions"
DECISIONS_INDEX = f"{DECISIONS_DIRECTORY}/DECISIONS_INDEX.md"
PROJECT_INSTRUCTIONS = "CLAUDE.md"
GITIGNORE = ".gitignore"
IGNORED_WORK = "# AI assistants\n.ai-work/\n"
_INDEX_HEADER = (
    "# Decisions Index\n\n"
    "Auto-generated from ADR frontmatter. Do not edit manually.\n"
    "Regenerate: `python scripts/regenerate_adr_index.py`\n\n"
    "| ID | Title | Status |\n"
    "|----|-------|--------|\n"
)


# -- The fixtures -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Architectural:
    component: str  # the component added, removed, split or merged: the falsifier's name


@dataclass(frozen=True)
class WithinComponent:
    component: str  # the one component the change stays inside


DecisionSort = Architectural | WithinComponent  # coverage bookkeeping only; never graded


@dataclass(frozen=True)
class PriorRecord:
    number: int
    slug: str
    title: str
    body: str

    @property
    def decision_id(self) -> str:
        return f"dec-{self.number:03d}"

    @property
    def path(self) -> str:
        return f"{DECISIONS_DIRECTORY}/{self.number:03d}-{self.slug}.md"

    def render(self) -> str:
        frontmatter = f"id: {self.decision_id}\ntitle: {json.dumps(self.title)}\nstatus: accepted"
        return f"---\n{frontmatter}\n---\n\n{self.body.strip()}\n"


@dataclass(frozen=True)
class AdrFixture:
    name: str
    branch: str  # the session's branch; sanitisation leaves it as written
    summary: str  # the decision, the options weighed and why, in clauses; never a rule line
    sort: DecisionSort
    prior: tuple[PriorRecord, ...]  # the project's own records, numbered 1..n
    source: Files  # the code the decision concerns
    history: tuple[str, ...]  # the project's commit subjects, oldest first

    def __post_init__(self) -> None:
        if not _BRANCH_FORM.fullmatch(self.branch) or self.branch in _RESERVED_BRANCHES:
            raise ValueError(f"{self.name}: {self.branch!r} is not a branch a session works on")
        if len(self.prior) < MIN_PRIOR_RECORDS:
            raise ValueError(f"{self.name}: a project's habit shows in at least two records")
        if [record.number for record in self.prior] != list(range(1, len(self.prior) + 1)):
            raise ValueError(f"{self.name}: the prior records are numbered 1..n in order")
        if len({record.slug for record in self.prior}) != len(self.prior):
            raise ValueError(f"{self.name}: the prior records have distinct slugs")
        if not self.history:
            raise ValueError(f"{self.name}: a fixture commits a history of its own")

    def committed(self) -> Files:
        """The tracked files the history leaves: the source, the records and their index."""
        index = _INDEX_HEADER + "".join(
            f"| {r.decision_id} | {r.title} | accepted |\n" for r in self.prior
        )
        return (
            *self.source,
            (PROJECT_INSTRUCTIONS, project_instructions(EXCLUDED_BLOCKS)),
            (GITIGNORE, IGNORED_WORK),
            *((record.path, record.render()) for record in self.prior),
            (DECISIONS_INDEX, index),
        )


FIXTURES: tuple[AdrFixture, ...] = ()


# -- Building ---------------------------------------------------------------------------------


def build_fixture(declaration: MoveDeclaration, task: MoveTask, where: Path) -> Path:
    """Build ``task``'s repository at ``where`` (absent or empty) and return it.

    Raises ``ValueError`` for a task of no fixture here, for a declaration that does not admit a
    managed fixture, or for a ``where`` that holds something already.
    """
    fixture = _fixture_of(task)
    if not admits(declaration.fixture_scope, FIXTURE_KIND):
        raise ValueError(f"the declaration does not admit the {FIXTURE_KIND} fixture kind")
    where.mkdir(parents=True, exist_ok=True)
    if any(where.iterdir()):
        raise ValueError(f"{where} is not empty")
    git(where, "init", "--quiet", "-b", BASELINE_BRANCH)
    for key, value in IDENTITY:
        git(where, "config", key, value)
    _commit_history(where, fixture)
    git(where, "update-ref", BASELINE_REF, "HEAD")
    git(where, "symbolic-ref", BRANCH_REF, f"refs/heads/{fixture.branch}")
    git(where, "checkout", "--quiet", "-b", fixture.branch)
    return where


def _commit_history(where: Path, fixture: AdrFixture) -> None:
    """The first commit holds the project; the later ones only add to the history's length."""
    write_files(where, fixture.committed())
    git(where, "add", "--all")
    first, *rest = fixture.history
    git(where, "commit", "--quiet", "-m", first)
    for subject in rest:
        git(where, "commit", "--quiet", "--allow-empty", "-m", subject)


def _fixture_of(task: MoveTask) -> AdrFixture:
    for fixture in FIXTURES:
        if fixture.name == task.fixture:
            return fixture
    raise ValueError(f"the adr-conventions kit has no fixture named {task.fixture!r}")
