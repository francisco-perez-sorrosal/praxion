"""Everything `praxion-sidecar` shows an operator or a program.

Split out so the CLI itself stays what it should be -- argparse, exit-code
mapping, and gathering facts from git and the filesystem. The rule the split
enforces: **nothing in here reads the world**. Every function takes already-
gathered facts and returns text or a JSON-ready dict, so a rendering can never
become a second, quietly-disagreeing source of truth about the project's state
(the same discipline `_sidecar_checks.py` applies to its own two renderings).

`doctor`'s table is *not* here -- it belongs with the check registry that
produces it (`_sidecar_checks.render_doctor_text` / `render_doctor_json`), for
exactly that reason. This module owns `status`, `init`'s section report, the
help text, and the two presentation gates (color, `~`-abbreviation).
"""

from __future__ import annotations

import dataclasses
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Union

_SCHEMA_VERSION = 1

# The status report's two columns: a label gutter wide enough for `Autocommit`,
# and an inventory path column wide enough for `.claude/settings.local.json`.
_LABEL_WIDTH = 12
_PATH_WIDTH = 38
_INDENT = "  "
_NONE_MARK = "—"

SHORT_USAGE = (
    "Usage: praxion-sidecar {init|link|status|doctor|commit|publish|absorb|remote} [options]\n"
    "Run 'praxion-sidecar --help' for examples and the full option reference."
)

HELP = """praxion-sidecar — keep Praxion's project intelligence outside a team repository.

USAGE
  praxion-sidecar <command> [options]

EXAMPLES
  # Is this project on a sidecar, and is it clean?
  praxion-sidecar status

  # Something looks wrong — what exactly, and how do I fix it?
  praxion-sidecar doctor

  # A worktree is missing its links (also run automatically by post-checkout)
  praxion-sidecar link

  # Keep docs/architecture.md in the team repo, shadow everything else (the default)
  praxion-sidecar init --share docs/architecture.md

  # The team wants Praxion after all — move the state in, with history
  praxion-sidecar publish

COMMANDS
  init      Create the sidecar, move state into it, write .git/info/exclude, link
  link      Reconcile exclude block + shadow symlinks + hook chain into this checkout
  status    Placement, sidecar location, shadow inventory, clean/dirty  [--json]
  doctor    Per-check PASS/WARN/FAIL with one-line fixes; no network I/O  [--json]
  commit    Commit the sidecar working tree; no-op when clean
  publish   Sidecar -> project repo via git subtree (history preserved)
  absorb    Project repo -> sidecar (the inverse of publish)
  remote    Print the sidecar remote; set it with a URL argument

PLACEMENT OPTIONS  (init, absorb)
  --shadow <relpath>   Keep this path in the sidecar, symlinked + excluded. Repeatable.
  --share  <relpath>   Keep this path committed in the project repo. Repeatable.
                       Allowed: .ai-state, CLAUDE.md, CLAUDE.local.md,
                       .claude/settings.local.json, docs/architecture.md,
                       architecture/, fitness/
                       Defaults: everything above is shadowed EXCEPT
                         docs/architecture.md  -> shared (a plain doc the team benefits
                                                  from; it must cite ADRs by id text,
                                                  never by .ai-state/ path)
                         CLAUDE.md             -> shadowed only if the repo has none.
                                                  A pre-existing CLAUDE.md is never
                                                  touched and Praxion's blocks go to the
                                                  shadowed CLAUDE.local.md instead.
                                                  Use --share CLAUDE.md to commit one.

REMOTE OPTIONS  (remote)
  --push <never|on-autocommit>   When to push the sidecar (default: never)
  --allow-foreign-host           Permit a remote host that differs from the project
                                 origin's host. Refused without this flag: on a work
                                 machine, project intelligence must not leave the
                                 boundary the code lives in.
  --clear                        Remove the remote

COMMON OPTIONS
  --dry-run        Print what would change; mutate nothing (all mutating commands)
  --json           Machine-readable output; implies --quiet (status, doctor only)
  --quiet, -q      Suppress informational output; errors still go to stderr
  --verbose, -v    Per-check detail
  --yes, -y        Accept destructive operations without confirming (publish, absorb)
  --help, -h       Show this help

ENVIRONMENT
  PRAXION_SIDECAR_ROOT   Where sidecars live (default: ~/.praxion/sidecars)
  NO_COLOR               Disable color (also disabled when stdout is not a TTY)

EXIT CODES
  0  success, healthy, or nothing to do
  1  actionable: doctor found drift, or --dry-run found pending work
  2  usage error
  3  refused on safety grounds (the message always names the exact fix)
  4  environment: not a git repo, no manifest, sidecar unreadable, git failed

Nothing here ever commits to the *project* repo. Only the sidecar autocommits."""


# --- presentation gates ------------------------------------------------------


def use_color(stream: object = None) -> bool:
    """Color is the exception, not the default (`tui-design` canon).

    Three independent opt-outs, any one of which is decisive: a non-TTY
    destination (a pipe, a CI log, a file), `NO_COLOR`, and `TERM=dumb`.
    """
    target = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    isatty = getattr(target, "isatty", None)
    return bool(isatty and isatty())


def abbreviate_home(path: Path) -> str:
    """`~`-abbreviate an absolute path, for sidecar locations outside the repo."""
    text = str(path)
    home = str(Path.home())
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        return "~" + text[len(home) :]
    return text


# --- status facts ------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Checkout:
    """Which of the project's checkouts this command ran in."""

    root: Path
    kind: str  # "main" | "worktree"
    index: int
    total: int


@dataclasses.dataclass(frozen=True)
class SidecarFacts:
    """The sidecar repository's own state -- read locally, never over the network."""

    root: Path
    branch: str
    dirty_files: int
    unpushed_commits: int
    last_commit_at: str | None


@dataclasses.dataclass(frozen=True)
class RemoteFacts:
    url: str
    push: str
    host_matches_origin: bool


@dataclasses.dataclass(frozen=True)
class InRepoStatus:
    """`.ai-state/` is committed in the project -- a healthy answer, not an error."""

    project_root: Path
    origin: str | None
    checkout: Checkout
    healthy: bool
    failed_checks: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class SidecarStatus:
    """Sidecar placement. The four keys `InRepoStatus` has no meaning for --
    `sidecar`, `remote`, `autocommit`, `paths` -- live here and only here, so
    the JSON payload omits them under `in-repo` rather than null-filling them
    (INTERFACE_DESIGN.md sec. 7.1)."""

    project_root: Path
    origin: str | None
    project_id: str
    checkout: Checkout
    sidecar: SidecarFacts
    remote: RemoteFacts | None
    autocommit: str
    paths: tuple[dict, ...]
    healthy: bool
    failed_checks: tuple[str, ...]


# `Union`, not `X | Y`: a runtime alias in that form needs 3.10 and `scripts/`
# targets 3.9+ -- the pin `_state_repo.Placement` documents.
Status = Union[InRepoStatus, SidecarStatus]  # noqa: UP007


# --- status renderings -------------------------------------------------------


def status_json(status: Status) -> dict:
    """`status --json` (INTERFACE_DESIGN.md sec. 7.1)."""
    payload: dict = {
        "schema": _SCHEMA_VERSION,
        "placement": "sidecar" if isinstance(status, SidecarStatus) else "in-repo",
        "project": {"root": str(status.project_root), "origin": status.origin},
        "checkout": {
            "root": str(status.checkout.root),
            "kind": status.checkout.kind,
            "total_checkouts": status.checkout.total,
        },
    }
    if isinstance(status, SidecarStatus):
        payload["project"]["id"] = status.project_id
        payload["sidecar"] = {
            "root": str(status.sidecar.root),
            "branch": status.sidecar.branch,
            "dirty_files": status.sidecar.dirty_files,
            "unpushed_commits": status.sidecar.unpushed_commits,
            "last_commit_at": status.sidecar.last_commit_at,
        }
        payload["remote"] = (
            None
            if status.remote is None
            else {
                "url": status.remote.url,
                "push": status.remote.push,
                "host_matches_origin": status.remote.host_matches_origin,
            }
        )
        payload["autocommit"] = status.autocommit
        payload["paths"] = list(status.paths)
    payload["healthy"] = status.healthy
    payload["failed_checks"] = list(status.failed_checks)
    return payload


def status_text(status: Status) -> str:
    """`status`'s report (INTERFACE_DESIGN.md sec. 3.1)."""
    lines = [
        _field("Placement", "sidecar" if isinstance(status, SidecarStatus) else "in-repo"),
        _field("Project", str(status.project_root), _origin_note(status.origin)),
        _field("Checkout", str(status.checkout.root), _checkout_note(status.checkout)),
    ]
    if isinstance(status, SidecarStatus):
        lines.extend(_sidecar_block(status))
    else:
        lines.append(_field("State", ".ai-state/", "committed in this repo"))
    lines.extend(["", *_health_lines(status)])
    return "\n".join(lines)


def _sidecar_block(status: SidecarStatus) -> list[str]:
    facts = status.sidecar
    dirty = "clean" if facts.dirty_files == 0 else f"{facts.dirty_files} files uncommitted"
    lines = [
        _field("Sidecar", abbreviate_home(facts.root)),
        _continuation(
            f"branch {facts.branch} · {dirty} · {facts.unpushed_commits} commits unpushed"
        ),
        _field("Autocommit", status.autocommit),
    ]
    if status.remote is None:
        lines.append(_field("Remote", "none", "(push: never)"))
    else:
        lines.append(_field("Remote", status.remote.url, f"(push: {status.remote.push})"))
    lines.append("")
    lines.extend(_inventory(status.paths))
    return lines


def _inventory(paths: Sequence[dict]) -> list[str]:
    """The Shadowed / Shared / Untouched blocks, one label per group."""
    groups = [
        ("Shadowed", "shadow", _shadow_note),
        ("Shared", "share", _share_note),
        ("Untouched", "untouched", _untouched_note),
    ]
    lines: list[str] = []
    for label, intent, note_of in groups:
        rows = [row for row in paths if row.get("intent") == intent]
        if not rows:
            lines.append(_field(label, _NONE_MARK))
            continue
        for position, row in enumerate(rows):
            body = f"{row['path']:<{_PATH_WIDTH}} {note_of(row)}".rstrip()
            lines.append(_field(label, body) if position == 0 else _continuation(body))
    return lines


def _health_lines(status: Status) -> list[str]:
    if not status.healthy:
        count = len(status.failed_checks)
        return [_continuation(f"{count} problem(s) found. Run: praxion-sidecar doctor")]
    if isinstance(status, InRepoStatus):
        return [
            _continuation("Healthy. For pin drift, run: scripts/upgrade_project_pins.sh --check")
        ]
    if status.checkout.total > 1:
        tail = (
            f" State is shared live across {status.checkout.total} checkouts — no branch isolation."
        )
        return [_continuation(f"Healthy.{tail}")]
    return [_continuation("Healthy.")]


def _field(label: str, value: str, note: str | None = None) -> str:
    body = f"{_INDENT}{label:<{_LABEL_WIDTH}}{value}"
    return f"{body}  {note}" if note else body


def _continuation(body: str) -> str:
    return f"{_INDENT}{'':<{_LABEL_WIDTH}}{body}"


def _origin_note(origin: str | None) -> str:
    return f"(origin {origin})" if origin else "(no remote)"


def _checkout_note(checkout: Checkout) -> str:
    kind = "main checkout" if checkout.kind == "main" else "linked worktree"
    return f"({kind}, {checkout.index} of {checkout.total})"


def _shadow_note(row: dict) -> str:
    return str(row.get("state", ""))


def _share_note(row: dict) -> str:
    return (
        "committed in the project repo"
        if row.get("state") == "shared"
        else str(row.get("state", ""))
    )


def _untouched_note(row: dict) -> str:
    reason = row.get("reason")
    if reason == "preexisting-team-file":
        return "pre-existing team file — Praxion blocks go to CLAUDE.local.md"
    return str(reason or "")


# --- init's section report ---------------------------------------------------


def sectioned_report(header: str, sections: Sequence[tuple[str, Sequence[str]]]) -> str:
    """`init`'s `[n/N] <title>` body (INTERFACE_DESIGN.md sec. 3.3).

    The same body is printed by a real run and by `--dry-run` -- only the
    trailer differs, which is what makes a dry run a trustworthy preview
    rather than a separate, drift-prone rendering.
    """
    lines = [header, ""]
    total = len(sections)
    for position, (title, body) in enumerate(sections, start=1):
        lines.append(f"[{position}/{total}] {title}")
        lines.extend(f"{_INDENT}{entry}" for entry in body)
    return "\n".join(lines)
