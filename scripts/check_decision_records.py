#!/usr/bin/env python3
"""Judge decision-record changes from the command line.

The decision-record gate's pure core (``_decision_records.py``) decides, from values alone,
whether a change leaves a record finalize cannot carry. This command gathers those values from a
git repository and renders the verdict, so the pre-commit hook and the commit gate share one
judgement with the write hook.

  PATH...     each file's working-tree text, judged against its ``HEAD`` blob (or none).
  --staged    each staged file's index blob, judged against its ``HEAD`` blob (or none).
  (neither)   under ``PRAXION_COMMIT_PAYLOAD=1``, stdin carries the PreToolUse Bash payload and
              the commit-to-be is judged: see "Commit payload" below.

Relative paths are repo-root relative. Deleted paths are not judged: nothing is left to refuse.
The branch decides whether a numbered record may appear (``main`` or ``master`` is where finalize
promotes), and the numbered records the default branch already holds are allowed through (a merge
or a rebase brings them in). "The default branch" is read as ``main`` or ``master``, local or
remote-tracking (``origin/main``): a branch merges the remote's tip while its own local ``main`` is
behind. A repository with a differently named default branch is not recognised, and a numbered
record is refused on every branch of it.

Commit payload: a PreToolUse hook fires before any command of the Bash call runs, so the index
alone misses a record that ``git add x && git commit`` stages. The scope is the one the
id-citation gate uses (``_commit_scope.hook_scope_files``); when the call restages (a ``git add``
before the commit, or ``-a``) a path is judged by its working-tree text, else by its index blob.
A command that is no ``git commit`` exits 0 silently, findings print to stderr as the commit
refusal text, a clean commit prints nothing. A payload or scope the gate cannot read passes with
one stderr line, never a block on a transient, as the id-citation gate does. Declared limits:
  - a record the same call itself creates or rewrites (heredoc, ``cp``, ``mv``, ``sed -i``) is not
    on disk when the hook fires, so only a write from an earlier call is seen;
  - ``git add -u`` names no pathspec, so a tracked edit it would stage is not judged at all: only
    what the index already holds is seen, whatever the working tree says;
  - a commit spelled so the segment splitter cannot see it is not seen: inside a wrapper shell
    (``bash -c "git commit"``), after a pipe (``echo m | git commit -F -``), after ``&`` or inside
    ``$(...)``, under ``xargs``, or behind a quoted environment prefix (``FOO="a b" git commit``).
    The pre-commit hook judges the true staged set whatever the spelling, and the write hook
    refuses the Write or Edit itself, so the residual is a record a shell wrote, committed in one
    of these spellings (td-528 tracks catching them; the id-citation gate shares the blind spot);
  - ``git commit -- PATH`` is judged by the staged set, not by PATH's working-tree text;
  - ``git -C DIR commit`` and ``--git-dir`` judge the payload's cwd repository, not DIR's;
  - a path staged with further unstaged edits is judged by its working-tree text whenever the call
    restages anything.

Exit codes: 0 clean, 1 findings, 2 input error. A gate that cannot read its input never passes:
a missing file, a path outside the repository, a directory that is no repository and a
plugin-cache root are all exit 2 (the commit payload mode excepted, as above).

Usage:
    python3 scripts/check_decision_records.py PATH [PATH ...]
    python3 scripts/check_decision_records.py --staged
    python3 scripts/check_decision_records.py --json --repo-root DIR PATH

Stdlib-only and 3.9-safe: the ambient ``python3`` runs it. The repo root is ``--repo-root`` or
the git toplevel of the cwd, never ``__file__``: hooks run it through a symlink into the plugin.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from _commit_scope import (
    _COMMAND_SEPARATOR,
    _COMMIT_ALL_FLAG,
    _PAYLOAD_ENV,
    _same_call_add_pathspecs,
    hook_scope_files,
)
from _decision_record_refusal import CORRECT_FORM, commit_refusal_text, find_rule_text
from _decision_records import (
    DECISIONS_PARTS,
    Change,
    Context,
    Numbered,
    Outside,
    Refused,
    TopLevel,
    classify_name,
    classify_path,
    judge_change,
)
from _git_runner import run_git
from _repo_root import is_plugin_cache_path, resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_INPUT_ERROR = 2

JSON_SCHEMA = 1
MAIN_BRANCHES = ("main", "master")
DECISIONS_DIR = "/".join(DECISIONS_PARTS)
_DEFAULT_BRANCH_REF = re.compile(
    rf"refs/heads/(?:{'|'.join(MAIN_BRANCHES)})|refs/remotes/.+/(?:{'|'.join(MAIN_BRANCHES)})"
)
NAME_SEPARATOR = "\0"
# A command segment that is a `git commit`: after any `VAR=value` prefixes, shell openers (`(`, `!`,
# `if`, `time`...) and wrapper words, the git executable, git's global options, then `commit`.
_SHELL_ARGUMENT = r"""(?:"[^"]*"|'[^']*'|\S+)"""
_SEGMENT_PREFIX = (
    r"(?:[(!{]\s*|\w+=\S*\s+"
    r"|(?:if|then|else|elif|do|while|until|time|command|exec|env|nohup|sudo)\s+)*"
)
_GIT_GLOBAL_OPTION = (
    rf"(?:-[cC]\s+{_SHELL_ARGUMENT}"
    rf"|--(?:git-dir|work-tree|namespace)\s+{_SHELL_ARGUMENT}"
    r"|--[\w-]+(?:=\S*)?|-p)\s+"
)
_GIT_COMMIT_SEGMENT = re.compile(
    rf"\s*{_SEGMENT_PREFIX}(?:\S*/)?git\s+(?:{_GIT_GLOBAL_OPTION})*commit(?:[\s;)}}]|$)"
)


class InputError(Exception):
    """The gate cannot read what it was asked to judge."""


# -- Command line -------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.payload:
        return _judge_commit_payload(sys.stdin.read())
    try:
        root = _resolve_root(args.repo_root)
        context = _gather_context(root)
        changes = _staged_changes(root) if args.staged else _path_changes(root, args.paths)
    except (InputError, OSError) as error:
        sys.stderr.write(f"check_decision_records: {error}\n")
        return EXIT_INPUT_ERROR
    refusals = _refusals(changes, context)
    sys.stdout.write(_render_json(refusals) if args.json else _render_text(refusals))
    return EXIT_FINDINGS if refusals else EXIT_CLEAN


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    # The module docstring is the help text: one description, nothing per option to drift from it.
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-root")
    args = parser.parse_args(argv)
    explicit = args.staged or bool(args.paths)
    args.payload = not explicit and bool(os.environ.get(_PAYLOAD_ENV))
    if args.staged == bool(args.paths) and not args.payload:
        parser.error("give either --staged or one or more PATH arguments")
    return args


def _refusals(changes: list[Change], context: Context) -> list[Refused]:
    verdicts = (judge_change(change, context) for change in changes)
    return [verdict for verdict in verdicts if isinstance(verdict, Refused)]


# -- The commit payload -------------------------------------------------------------------


def _judge_commit_payload(raw: str) -> int:
    """Judge the commit a Bash payload is about to run; every doubt but a finding passes."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return _pass_safe("the hook payload is unreadable")
    command = _payload_command(payload)
    if not _is_git_commit(command):
        return EXIT_CLEAN
    scope = hook_scope_files(payload, Path.cwd())
    if not isinstance(scope, tuple):  # under the payload signal: no repository, or git contended
        return _pass_safe("the commit scope is unavailable")
    root, files = scope
    try:
        if is_plugin_cache_path(root):
            raise InputError(f"refusing to run against a plugin-cache root: {root}")
        context = _gather_context(root)
        changes = _commit_changes(root, files, restages=_restages(command))
    except (InputError, OSError) as error:
        return _pass_safe(str(error))
    refusals = _refusals(changes, context)
    if refusals:
        sys.stderr.write(commit_refusal_text(refusals, find_rule_text()) + "\n")
    return EXIT_FINDINGS if refusals else EXIT_CLEAN


def _pass_safe(reason: str) -> int:
    sys.stderr.write(f"check_decision_records: {reason}; passing.\n")
    return EXIT_CLEAN


def _payload_command(payload: object) -> str:
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return command if isinstance(command, str) else ""


def _is_git_commit(command: str) -> bool:
    # A pattern per segment, not shlex: a commit message heredoc leaves the first line's quote open.
    return any(_GIT_COMMIT_SEGMENT.match(segment) for segment in _COMMAND_SEPARATOR.split(command))


def _restages(command: str) -> bool:
    """Whether the call itself moves working-tree text into the index before the commit."""
    return _same_call_add_pathspecs(command) is not None or bool(_COMMIT_ALL_FLAG.search(command))


def _commit_changes(root: Path, files: list[Path], restages: bool) -> list[Change]:
    rels = (file.relative_to(root).as_posix() for file in files)
    return [
        Change(rel, _head_text(root, rel), _commit_text(root, rel, restages))
        for rel in rels
        if not isinstance(classify_path(rel), Outside)
    ]


def _commit_text(root: Path, rel: str, restages: bool) -> str:
    if restages:
        try:
            return _working_text(root, rel)
        except InputError:
            pass  # gone from the working tree: the index blob is what the commit would record
    return _index_text(root, rel)


# -- Rendering ----------------------------------------------------------------------------


def _render_text(refusals: list[Refused]) -> str:
    rows = (f"{r.path}: {_defect_names(r)} -- {CORRECT_FORM}\n" for r in refusals)
    return "".join(rows)


def _render_json(refusals: list[Refused]) -> str:
    findings = [{"path": r.path, "defects": [d.value for d in r.defects]} for r in refusals]
    return json.dumps({"schema": JSON_SCHEMA, "findings": findings}) + "\n"


def _defect_names(refused: Refused) -> str:
    return ", ".join(defect.value for defect in refused.defects)


# -- Gathering: the root and the context --------------------------------------------------


def _resolve_root(cli_repo_root: str | None) -> Path:
    root = resolve_repo_root(
        cli_repo_root, script_dir=SCRIPT_DIR, on_fallback=_refuse_script_relative_root
    )
    if is_plugin_cache_path(root):
        raise InputError(f"refusing to run against a plugin-cache root: {root}")
    return root


def _refuse_script_relative_root(fallback: Path) -> None:
    raise InputError(f"not inside a git repository and no --repo-root given (not {fallback})")


def _gather_context(root: Path) -> Context:
    branch = _current_branch(root)
    return Context(on_main=branch in MAIN_BRANCHES, default_holds=_default_branch_records(root))


def _current_branch(root: Path) -> str:
    # `symbolic-ref` answers on an unborn branch, where `rev-parse HEAD` has no commit to name.
    for command in (("rev-parse", "--abbrev-ref", "HEAD"), ("symbolic-ref", "--short", "HEAD")):
        result = run_git(root, *command)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise InputError(f"cannot read the current branch of {root}: not a git repository?")


def _default_branch_records(root: Path) -> frozenset[str]:
    """The numbered record paths any default-branch ref holds; empty with none.

    A default-branch ref is local ``main``/``master`` or a remote-tracking one
    (``refs/remotes/<remote>/main|master``). Both count because a branch merges
    ``origin/main`` while the local ``main`` is behind, and the record that merge
    brings in is one the default branch already holds.
    """
    records: set[str] = set()
    for ref in _default_branch_refs(root):
        listing = run_git(root, "ls-tree", "-z", "--name-only", ref, f"{DECISIONS_DIR}/")
        if listing.returncode != 0:
            raise InputError(f"cannot list {DECISIONS_DIR}/ on {ref}: {listing.stderr.strip()}")
        records.update(path for path in listing.stdout.split(NAME_SEPARATOR) if _is_numbered(path))
    return frozenset(records)


def _default_branch_refs(root: Path) -> list[str]:
    listing = run_git(root, "for-each-ref", "--format=%(refname)", "refs/heads/", "refs/remotes/")
    if listing.returncode != 0:
        raise InputError(f"cannot list the branches of {root}: {listing.stderr.strip()}")
    return [ref for ref in listing.stdout.splitlines() if _DEFAULT_BRANCH_REF.fullmatch(ref)]


def _is_numbered(path: str) -> bool:
    record_path = classify_path(path)
    return isinstance(record_path, TopLevel) and isinstance(
        classify_name(record_path.name), Numbered
    )


# -- Gathering: the changes ---------------------------------------------------------------


def _path_changes(root: Path, raw_paths: list[str]) -> list[Change]:
    changes = []
    for raw in raw_paths:
        rel = _repo_relative(root, raw)
        changes.append(Change(rel, _head_text(root, rel), _working_text(root, rel)))
    return changes


def _staged_changes(root: Path) -> list[Change]:
    # No rename detection: a renamed record is an added path and a deleted one, as a commit sees it.
    listing = run_git(
        root, "diff", "--cached", "--name-only", "--no-renames", "--diff-filter=ACMR", "-z"
    )
    if listing.returncode != 0:
        raise InputError(f"cannot list the staged set: {listing.stderr.strip()}")
    staged = (path for path in listing.stdout.split(NAME_SEPARATOR) if path)
    return [
        Change(path, _head_text(root, path), _index_text(root, path))
        for path in staged
        if not isinstance(classify_path(path), Outside)
    ]


def _repo_relative(root: Path, raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            raise InputError(f"{raw} is outside the repository {root}") from None
    rel = os.path.normpath(path.as_posix())
    if rel == ".." or rel.startswith("../"):
        raise InputError(f"{raw} is outside the repository {root}")
    return rel.replace(os.sep, "/")


def _head_text(root: Path, rel: str) -> str | None:
    """The ``HEAD`` blob's text, or ``None`` when ``HEAD`` does not hold the path."""
    result = run_git(root, "show", f"HEAD:{rel}")
    return result.stdout if result.returncode == 0 else None


def _index_text(root: Path, rel: str) -> str:
    result = run_git(root, "show", f":{rel}")
    if result.returncode != 0:
        raise InputError(f"cannot read the staged blob of {rel}: {result.stderr.strip()}")
    return result.stdout


def _working_text(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_bytes().decode("utf-8", errors="replace")
    except OSError as error:
        raise InputError(f"cannot read {rel}: {error}") from None


if __name__ == "__main__":
    sys.exit(main())
