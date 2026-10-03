#!/usr/bin/env python3
"""Merge a worktree's observation-log rows into the main checkout's log.

A worktree's log dies with ``git worktree remove``; this copies what it recorded
into the main checkout's log first, skipping every row the main log already holds,
so a run can be repeated. Two ways in, one code path:

    merge_worktree_log.py --worktree PATH   # one named worktree (/merge-worktree)
    merge_worktree_log.py --merged          # every worktree the main checkout's
                                            # HEAD already contains (post-merge hook)

``--repo-root`` is any checkout of the repository (default: the git toplevel of
the working directory). It is never derived from this file's location: managed
projects run this from the plugin cache, and the plugin's own checkout is not
theirs.

``--merged`` is quiet when nothing happened (no worktree holds a log, every row is
already held, recording is off) and speaks only for a worktree that gained rows or
could not be merged, so a merge or pull in a project with no pipelines prints
nothing.

Exit code: 0 merged, nothing to merge, or recording off; 1 when any worktree
could not be merged whole (a segment unreadable or missing, the main log
unreadable or unwritable); 2 for an input error. ``--json`` prints one object
per run: for ``--worktree`` the report below, for ``--merged`` an envelope
``{"schema", "main", "mode", "worktrees": [report, ...], "error"}``.

    {"schema": 1, "main", "worktree", "mode", "outcome", "copied", "skipped",
     "malformed", "unreadable": [path, ...], "reason"}

Standard library only, and 3.9-safe: the post-merge hook runs it under whatever
interpreter the project has.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from _repo_root import git_toplevel_from_cwd, is_plugin_cache_path

SCRIPT_DIR = Path(__file__).resolve().parent

# hooks/ is a sibling of this file's scripts/ directory, in the repository and in
# the installed plugin alike.
sys.path.insert(0, str(SCRIPT_DIR.parent / "hooks"))
from _observation_log import checkouts, merge_in, modes  # noqa: E402 (after sys.path injection)

SCHEMA_VERSION = 1
EXIT_OK, EXIT_DEGRADED, EXIT_INPUT_ERROR = 0, 1, 2


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
        help="Every linked worktree whose HEAD the main checkout's HEAD contains.",
    )
    parser.add_argument("--repo-root", default=None, help="Any checkout. Default: found via git.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


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
    targets = _contained(main, linked) if args.merged else _named(linked, args.worktree)
    if targets is None:
        return _input_error(args, f"not a worktree of this repository: {args.worktree}")

    reports = merge_in.merge_worktree_logs(
        main.state_dir, [target.state_dir for target in targets], env=os.environ
    )
    entries = [(targets[index], report) for index, report in enumerate(reports)]
    if args.merged:
        entries = [(target, report) for target, report in entries if _worth_saying(report)]
    _print_run(args, main, entries, error=None)
    return EXIT_DEGRADED if any(r.outcome == merge_in.DEGRADED for _, r in entries) else EXIT_OK


def _contained(main, linked):
    """The linked worktrees whose HEAD is already part of the main checkout's HEAD."""
    return [target for target in linked if checkouts.contains(main.root, target.head)]


def _named(linked, path: str):
    """`[the linked worktree at path]`, or None when no linked worktree is there."""
    wanted = Path(path).resolve()
    return [target for target in linked if target.root.resolve() == wanted] or None


def _worth_saying(report) -> bool:
    """A worktree that gained rows or could not be merged; anything else is a no-op."""
    return report.outcome == merge_in.DEGRADED or report.copied > 0


# -- Output -------------------------------------------------------------------


def _print_run(args, main, entries, *, error: str | None) -> None:
    if args.json:
        print(json.dumps(_as_json(args, main, entries, error), indent=2))
        return
    for target, report in entries:
        for line in _human_lines(target, report):
            print(line)


def _as_json(args, main, entries, error: str | None) -> dict:
    reports = [_report_json(main, target, report) for target, report in entries]
    if args.merged:
        mode = modes.resolve_mode(os.environ)[0].value
        main_root = str(main.root) if main else None
        return {
            "schema": SCHEMA_VERSION,
            "main": main_root,
            "mode": mode,
            "worktrees": reports,
            "error": error,
        }
    return reports[0] if reports else {"schema": SCHEMA_VERSION, "error": error}


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


def _input_error(args: argparse.Namespace, message: str) -> int:
    print(f"merge_worktree_log: {message}", file=sys.stderr)
    if args.json:
        print(json.dumps(_as_json(args, None, [], message), indent=2))
    return EXIT_INPUT_ERROR


def main(argv: list[str] | None = None) -> None:
    sys.exit(_run(_parse_args(argv)))


if __name__ == "__main__":
    main()
