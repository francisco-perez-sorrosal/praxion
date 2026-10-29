"""Planted projects and decision records for grading the adr-conventions move with no session.

A planted project is a managed project in a git repository of its own, under a git identity,
checked out on a named branch other than its default, whose decision directory holds two
records in the *older habit* (each named by a record number and a slug at the top of the
decision directory, with a numbered id and no `category`) and a `DECISIONS_INDEX.md` listing
them. A scenario keeps the project as it was built (`fixture`) and changes a copy of it
(`project`), as a session would, then asks a governed check to grade the copy against it.

Every record is written from the moved rule's own words: a draft fragment directly under the
draft directory, named `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`, whose frontmatter id is the
draft form with an eight-character hexadecimal hash, a `category` among the four values, and,
on an architectural record, a section headed Disconfirmation naming a falsifier, a steelmanned
runner-up and a reversal trigger. A known-bad record is that record with one field changed.

Nothing here is unbound.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

DECISIONS_DIR = ".ai-state/decisions"
DRAFTS_DIR = f"{DECISIONS_DIR}/drafts"
INDEX_FILE = f"{DECISIONS_DIR}/DECISIONS_INDEX.md"
GIT_IDENTITY = {"user.name": "Fixture Person", "user.email": "fixture@example.invalid"}
USER = "fixture-person"
BRANCH = "record-storage-choice"
DEFAULT_BRANCH = "main"
STAMP = "20261029-1430"
SLUG = "adopt-sqlite-for-the-cache"
DRAFT_HASH = "3f9a0c1e"
NEXT_NUMBER = "043"  # the record number after the planted ones

OLDER_RECORDS = {
    "041-keep-orders-in-postgres.md": ("041", "Keep orders in Postgres"),
    "042-retry-webhooks-with-backoff.md": ("042", "Retry webhooks with backoff"),
}


def draft_id(hash_: str = DRAFT_HASH) -> str:
    return f"dec-draft-{hash_}"


def numbered_id(number: str = NEXT_NUMBER) -> str:
    return f"dec-{number}"


def fragment_name(
    *, stamp: str = STAMP, user: str = USER, branch: str = BRANCH, slug: str = SLUG
) -> str:
    return f"{stamp}-{user}-{branch}-{slug}.md"


# -- The planted project ----------------------------------------------------------------------


@dataclass(frozen=True)
class Planted:
    fixture: Path  # the project as it was built, never changed
    project: Path  # the copy a scenario changes as a session would


def planted_project(workspace: Path) -> Planted:
    fixture = workspace / "fixture"
    (fixture / DECISIONS_DIR).mkdir(parents=True)
    (fixture / "CLAUDE.md").write_text("# Orders service\n\nA small service.\n", encoding="utf-8")
    for name, (number, title) in OLDER_RECORDS.items():
        (fixture / DECISIONS_DIR / name).write_text(_older_record(number, title), encoding="utf-8")
    rows = "".join(f"| dec-{n} | {t} | `{f}` |\n" for f, (n, t) in OLDER_RECORDS.items())
    index = "# Decisions\n\n| id | title | file |\n|---|---|---|\n" + rows
    (fixture / INDEX_FILE).write_text(index, encoding="utf-8")
    git(fixture, "init", "-q", "-b", DEFAULT_BRANCH)
    for key, value in GIT_IDENTITY.items():
        git(fixture, "config", key, value)
    git(fixture, "add", "-A")
    git(fixture, "commit", "-q", "-m", "Start the orders service")
    git(fixture, "checkout", "-q", "-b", BRANCH)
    project = workspace / "project"
    shutil.copytree(fixture, project, symlinks=True)
    return Planted(fixture, project)


def _older_record(number: str, title: str) -> str:
    return (
        f"---\nid: dec-{number}\ntitle: {title}\nstatus: accepted\ndate: 2026-09-01\n---\n\n"
        f"# {title}\n\n## Context\n\nThe service needed a choice.\n\n"
        "## Decision\n\nWe chose the simpler path.\n\n## Consequences\n\nFewer moving parts.\n"
    )


def git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


# -- Records ----------------------------------------------------------------------------------

DISCONFIRMATION_ITEMS = ("Falsifier", "Steelmanned runner-up", "Reversal trigger")


@dataclass(frozen=True)
class Record:
    """A decision record a session might leave; `None` leaves a field out of the file."""

    relpath: str
    id: str | None
    category: str | None
    disconfirmation_heading: str | None = None  # the heading text, when the section is there
    disconfirmation_items: tuple[str, ...] = DISCONFIRMATION_ITEMS
    title: str = "Adopt SQLite for the cache"

    def text(self) -> str:
        front = [f"id: {self.id}"] if self.id is not None else []
        front += [f"title: {self.title}", "status: proposed", "date: 2026-10-29"]
        front += [f"category: {self.category}"] if self.category is not None else []
        body = [
            f"# {self.title}",
            "## Context\n\nThe cache lost entries on every restart.",
            "## Decision\n\nKeep the cache in a SQLite file beside the service.",
            "## Considered Options\n\n- An in-memory map.\n- A SQLite file.",
            "## Consequences\n\nEntries survive a restart; one more file to back up.",
        ]
        if self.disconfirmation_heading is not None:
            items = "\n".join(f"- **{item}** -- named here." for item in self.disconfirmation_items)
            body.append(f"## {self.disconfirmation_heading}\n\n{items}")
        return "---\n" + "\n".join(front) + "\n---\n\n" + "\n\n".join(body) + "\n"


def conforming(sort: str = "architectural") -> Record:
    """A draft fragment written as the moved rule says, for a decision of `sort`."""
    architectural = sort == "architectural"
    return Record(
        relpath=f"{DRAFTS_DIR}/{fragment_name()}",
        id=draft_id(),
        category="architectural" if architectural else "behavioral",
        disconfirmation_heading="Disconfirmation" if architectural else None,
    )


def older_habit() -> Record:
    """A record numbered after the project's own and written like them."""
    return Record(
        relpath=f"{DECISIONS_DIR}/{NEXT_NUMBER}-{SLUG}.md", id=numbered_id(), category=None
    )


def with_changes(record: Record, **changes: object) -> Record:
    return replace(record, **changes)  # type: ignore[arg-type]


def leave(project: Path, *records: Record) -> None:
    """Write each record into the project, as a session leaves it (uncommitted)."""
    for record in records:
        path = project / record.relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.text(), encoding="utf-8")


def leave_then_move(project: Path, first: Record, final: Record) -> None:
    """Commit `first`, then move and rewrite it into `final`, committing again."""
    leave(project, first)
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Record the cache decision")
    (project / final.relpath).parent.mkdir(parents=True, exist_ok=True)
    git(project, "mv", first.relpath, final.relpath)
    leave(project, final)
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Move the cache decision into the drafts")
