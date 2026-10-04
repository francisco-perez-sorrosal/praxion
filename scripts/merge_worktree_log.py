#!/usr/bin/env python3
"""Merge a worktree's observation-log rows into the main checkout's log.

A worktree's log dies with ``git worktree remove``; this copies what it recorded
into the main checkout's log first, skipping every row the main log already holds,
so a run can be repeated. Two ways in, one code path:

    merge_worktree_log.py --worktree PATH   # one named worktree (/merge-worktree)
    merge_worktree_log.py --merged          # every worktree the merge that just
                                            # ran brought in (the finalize hooks)
    merge_worktree_log.py --merged --before REV
    merge_worktree_log.py --merged --before REV --skip-unresolvable-before

``--merged`` takes a linked worktree that holds a log, whose HEAD the main
checkout's HEAD contains and REV (default ``ORIG_HEAD``, the state before the
merge) does not. So only the worktrees a merge, pull or rebase brought in are copied: a
worktree that has not committed anything, or whose branch an earlier merge already
took in, is left to ``--worktree`` at teardown, so a running pipeline's half
session is not copied. One case escapes: a worktree branched from ``origin/main``
while the local main was behind is brought in by the next pull, commits or not,
and its running agents show as unstopped in P03 until a later merge copies the
rest (an accepted leftover, named in the decision record). REV is resolved once
a worktree holds a log; an unresolvable one is an input error, or, with
``--skip-unresolvable-before`` (what the finalize hooks pass), a one-line named
skip that exits 0.

Three finalize hooks run ``--merged``: post-merge after ``git merge`` and
``git pull`` (REV ``ORIG_HEAD``); post-commit after a merge finished by
``git commit`` or ``git merge --continue`` following a conflict or
``--no-commit`` (REV the new commit's first parent, exact even when ``ORIG_HEAD``
was overwritten); post-rewrite after a rebase finishes, ``git pull --rebase``
included (REV ``ORIG_HEAD``, the tip the branch held when the rebase began). A
squash merge is the one merge no hook recognises, because the squashed commit is
not the worktree's HEAD; ``--worktree`` at teardown and P14 cover it.

``--repo-root`` is any checkout of the repository (default: the git toplevel of
the working directory). It is never derived from this file's location: managed
projects run this from the plugin cache, and the plugin's own checkout is not
theirs.

The recording mode is resolved key by key, the way Claude Code writes a
settings ``env`` over the shell's: each of ``PRAXION_OBSERVATION_LOG`` and
``PRAXION_DISABLE_OBSERVABILITY`` comes from the main checkout's
``.claude/settings.local.json`` ``env``, else its ``.claude/settings.json``
``env``, else the process environment. A git hook sees only the shell's
variables, so the files supply what a session would see. User-scope and
managed-policy settings are not read.

``--merged`` is quiet when nothing happened (no worktree holds a log, every row is
already held, recording is off) and speaks only for a worktree that gained rows or
could not be merged, so a merge or pull in a project with no pipelines prints
nothing.

Exit code: 0 merged, nothing to merge, recording off, or skipped
(``--skip-unresolvable-before``); 1 when any worktree
could not be merged whole (a segment or its directory unreadable or missing, the
main log unreadable or unwritable, an internal error); 2 for an input error.
``--json`` prints one object per run: for ``--worktree`` the report below plus
``mode_source`` and ``notes``, for ``--merged`` an envelope ``{"schema", "main",
"mode", "mode_source", "notes", "worktrees": [report, ...], "error"}``, plus
``"skipped": "cannot resolve REV"`` on a skipped run.

    {"schema": 1, "main", "worktree", "mode", "outcome", "copied", "skipped",
     "malformed", "unreadable": [path, ...], "reason"}

``mode_source`` is the highest-precedence source that supplied a mode key -- a
settings file, else "process" -- or "default"; ``notes`` names a settings file
that could not be used.

Standard library only, and 3.9-safe: the finalize hooks run it under whatever
interpreter the project has.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path

from _repo_root import git_toplevel_from_cwd, is_plugin_cache_path

SCRIPT_DIR = Path(__file__).resolve().parent

# hooks/ is a sibling of this file's scripts/ directory, in the repository and in
# the installed plugin alike.
sys.path.insert(0, str(SCRIPT_DIR.parent / "hooks"))
from _observation_log import checkouts, merge_in, modes  # noqa: E402 (after sys.path injection)

SCHEMA_VERSION = 1
EXIT_OK, EXIT_DEGRADED, EXIT_INPUT_ERROR = 0, 1, 2
DEFAULT_BEFORE = "ORIG_HEAD"

# The two keys that decide the recording mode, as `modes.resolve_mode` reads them.
MODE_KEYS = (modes.SETTING, "PRAXION_DISABLE_OBSERVABILITY")
# Lowest precedence first: a later file overrides an earlier one, key by key.
SETTINGS_FILES = (".claude/settings.json", ".claude/settings.local.json")
PROCESS_SOURCE, DEFAULT_SOURCE = "process", "default"

# `env` is what `merge_in` resolves the mode from; `source` says where it came from;
# `notes` names each settings file that was skipped and why.
Recording = namedtuple("Recording", ("env", "source", "notes"))


@dataclass(frozen=True)
class BroughtIn:
    """The linked worktrees the merge just run brought in (possibly none)."""

    targets: tuple


@dataclass(frozen=True)
class UnresolvableBefore:
    """Some worktree holds a log, but the before-revision names no commit."""

    rev: str

    @property
    def reason(self) -> str:
        return f"cannot resolve {self.rev}"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="merge_worktree_log",
        description="Copy a worktree's observation-log rows into the main checkout's log.",
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--worktree", metavar="PATH", help="One worktree of this repository.")
    which.add_argument(
        "--merged",
        action="store_true",
        help="Every linked worktree holding a log that the merge just run brought in.",
    )
    parser.add_argument(
        "--before",
        metavar="REV",
        default=None,
        help=f"With --merged: the revision before the merge (default: {DEFAULT_BEFORE}).",
    )
    parser.add_argument(
        "--skip-unresolvable-before",
        action="store_true",
        help="With --merged: an unresolvable REV is a named skip that exits 0, not an input error.",
    )
    parser.add_argument("--repo-root", default=None, help="Any checkout. Default: found via git.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.before is not None and not args.merged:
        parser.error("--before applies to --merged")
    if args.skip_unresolvable_before and not args.merged:
        parser.error("--skip-unresolvable-before applies to --merged")
    return args


def _run(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve() if args.repo_root else git_toplevel_from_cwd()
    if root is None:
        return _input_error(args, "not inside a git repository")
    if is_plugin_cache_path(root):
        return _input_error(args, f"refusing to operate on a plugin-cache path: {root}")
    listing = checkouts.repository_checkouts(root)
    if listing.error is not None:
        return _input_error(args, listing.error)
    main, linked = listing.checkouts[0], listing.checkouts[1:]
    recording = _recording(main.root)
    if args.merged:
        outcome = _brought_in(main, linked, args.before or DEFAULT_BEFORE)
        if isinstance(outcome, UnresolvableBefore):
            if args.skip_unresolvable_before:
                return _print_skip(args, main, outcome, recording)
            return _input_error(args, outcome.reason, recording)
        targets = outcome.targets
    else:
        targets, error = _named(linked, args.worktree)
        if error is not None:
            return _input_error(args, error, recording)

    reports = merge_in.merge_worktree_logs(
        main.state_dir, [target.state_dir for target in targets], env=recording.env
    )
    entries = [(targets[index], report) for index, report in enumerate(reports)]
    if args.merged:
        entries = [(target, report) for target, report in entries if _worth_saying(report)]
    _print_run(args, main, entries, recording)
    return EXIT_DEGRADED if any(r.outcome == merge_in.DEGRADED for _, r in entries) else EXIT_OK


def _brought_in(main, linked, before: str) -> BroughtIn | UnresolvableBefore:
    """The linked worktrees the merge just run brought in, or the revision that named no commit.

    Cheapest test first, so the common case (no worktree holds a log) costs one
    scan per worktree and no git question at all.
    """
    holding = [target for target in linked if merge_in.holds_log(target.state_dir)]
    if not holding:
        return BroughtIn(())
    boundary = checkouts.resolve_commit(main.root, before)
    if boundary is None:
        return UnresolvableBefore(before)
    return BroughtIn(
        tuple(
            target
            for target in holding
            if checkouts.contains(main.root, target.head)
            and not checkouts.contains(main.root, target.head, within=boundary)
        )
    )


def _named(linked, path: str):
    """`([the linked worktree at path], None)`, or `([], why not)`."""
    wanted = Path(path).resolve()
    named = [target for target in linked if target.root.resolve() == wanted]
    return (named, None) if named else ([], f"not a worktree of this repository: {path}")


def _worth_saying(report) -> bool:
    """A worktree that gained rows or could not be merged; anything else is a no-op."""
    return report.outcome == merge_in.DEGRADED or report.copied > 0


# -- The recording mode as the project sets it ------------------------------------


def _recording(main_root: Path | None) -> Recording:
    """The mode keys in effect, key by key: each settings file over the process, local last."""
    layers = [(PROCESS_SOURCE, {key: os.environ[key] for key in MODE_KEYS if key in os.environ})]
    notes: list[str] = []
    if main_root is not None:
        for filename in SETTINGS_FILES:
            supplied, note = _settings_mode_keys(main_root / filename, filename)
            if note is not None:
                notes.append(note)
            layers.append((filename, supplied))
    env: dict[str, str] = {}
    source = DEFAULT_SOURCE
    for label, supplied in layers:  # lowest precedence first
        if supplied:
            env.update(supplied)
            source = label
    return Recording(env, source, tuple(notes))


def _settings_mode_keys(path: Path, label: str) -> tuple[dict[str, str], str | None]:
    """`(the mode keys the file's env block sets, None)`, or `({}, why it was skipped)`.

    A file that is not there is not a problem; one that is there and unusable is
    skipped, and said so, because the mode then falls back to a default the
    project may not have chosen.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, None
    except OSError as exc:
        return {}, f"{label}: cannot be read ({exc})"
    try:
        settings = json.loads(text)
    except ValueError as exc:
        return {}, f"{label}: is not valid JSON ({exc})"
    if not isinstance(settings, dict):
        return {}, f"{label}: is not an object"
    env = settings.get("env")
    if env is None:
        return {}, None  # a settings file without an env block is the common case, not a defect
    if not isinstance(env, dict):
        return {}, f"{label}: env is not an object"
    return {key: str(env[key]) for key in MODE_KEYS if key in env}, None


# -- Output -------------------------------------------------------------------


def _print_run(args, main, entries, recording: Recording) -> None:
    if args.json:
        print(json.dumps(_as_json(args, main, entries, None, recording), indent=2))
        return
    for target, report in entries:
        for line in _human_lines(target, report):
            print(line)
    if entries:  # a project with no pipelines hears nothing, whatever its settings hold
        for note in recording.notes:
            print(f"merge_worktree_log: note: {note}", file=sys.stderr)


def _print_skip(args, main, skipped: UnresolvableBefore, recording: Recording) -> int:
    if args.json:
        print(json.dumps(_as_json(args, main, [], None, recording, skipped.reason), indent=2))
    else:
        print(
            f"merge-in skipped: {skipped.reason}; worktree logs are left to /merge-worktree and P14"
        )
    return EXIT_OK


def _as_json(
    args, main, entries, error: str | None, recording: Recording, skipped: str | None = None
) -> dict:
    reports = [_report_json(main, target, report) for target, report in entries]
    provenance = {"mode_source": recording.source, "notes": list(recording.notes)}
    if args.merged:
        envelope = {
            "schema": SCHEMA_VERSION,
            "main": str(main.root) if main else None,
            "mode": modes.resolve_mode(recording.env)[0].value,
            **provenance,
            "worktrees": reports,
            "error": error,
        }
        return envelope if skipped is None else {**envelope, "skipped": skipped}
    if reports:
        return {**reports[0], **provenance}
    return {"schema": SCHEMA_VERSION, "error": error}


def _report_json(main, target, report) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "main": str(main.root),
        "worktree": str(target.root),
        "mode": report.mode.value,
        "outcome": report.outcome,
        "copied": report.copied,
        "skipped": report.skipped,
        "malformed": report.malformed,
        "unreadable": list(report.unreadable),
        "reason": report.reason,
    }


def _human_lines(target, report) -> list[str]:
    name = target.name
    if report.outcome == merge_in.RECORDING_OFF:
        return [f"merge-in {name}: recording is off (mode {report.mode.value}); nothing merged"]
    if report.outcome == merge_in.NOTHING_TO_MERGE:
        return [f"merge-in {name}: no log to merge"]
    counts = f"copied {report.copied}, already held {report.skipped}, malformed {report.malformed}"
    lines = [f"merge-in {name}: {counts}"]
    if report.reason is not None:
        lines.append(f"reason: {report.reason}")
    return lines


def _input_error(args: argparse.Namespace, message: str, recording: Recording | None = None) -> int:
    print(f"merge_worktree_log: {message}", file=sys.stderr)
    if args.json:
        recording = recording or _recording(None)
        print(json.dumps(_as_json(args, None, [], message, recording), indent=2))
    return EXIT_INPUT_ERROR


def main(argv: list[str] | None = None) -> None:
    sys.exit(_run(_parse_args(argv)))


if __name__ == "__main__":
    main()
