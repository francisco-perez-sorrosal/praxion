"""The git and command adapters of the step-loop driver: the only module that touches the
repository or runs a command.

* **Git**: `commit_paths`, the commit by explicit path. A declared path (a file or a directory,
  spelled any way git accepts) is normalised once and expanded to the changed files under it;
  filtering, staging, the commit and the snapshots all work on those file names. A row already
  staged outside them is tolerated and stays staged (a path-limited commit never takes it) and
  the snapshot records it. After the commit its file set must equal the staged files and the
  tree outside them must be unchanged; otherwise the disturbance is reported with both
  snapshots and nothing is unstaged, reset or restored for the caller. Outer-loop files (under
  `tests/acceptance/` or `tests/e2e/`, or named by any step's `Read-only:`) are withheld
  whatever the plan declares.
* **Scope**: `tree_patch`, the whole tree's difference from `HEAD` (the index untouched), and
  `restore_paths`, which returns a declared scope to `HEAD` and touches nothing else.
* **Runner**: the `Check:` command and the derived test scope. Each invocation the resolver
  lists runs and comes back on its own; merging them is the caller's job. No runner is asked to
  colour, and each command leads a process group that a timeout kills whole.

Every git call goes through `_git_runner.run_git`; from `commit_paths`, a git that cannot run is
`CommitInterrupted` and one that refuses a command is `CommitRefused`. Pathspecs are
`:(literal)` magic, not a global flag, which git would export to every hook the commit runs.
"""

from __future__ import annotations

import contextlib
import json
import os
import posixpath
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from _git_runner import GIT_TIMEOUT_SECONDS, GitUnavailableError, run_git

OUTER_LOOP_PREFIXES = ("tests/acceptance/", "tests/e2e/")
# The commit runs the repository's hooks (about twenty, installing environments on a first
# run): a bound of its own, not the thirty seconds of plain plumbing.
COMMIT_TIMEOUT_SECONDS = 600.0
RUN_TIMEOUT_SECONDS = 540.0
RESOLVER_TIMEOUT_SECONDS = 60.0
KILL_GRACE_SECONDS = 5.0
FAILURE_TAIL_LINES = 20
HOOK_WORDS_LIMIT = 300
HOOK_WORDS_FALLBACK_LINES = 5
_CUT_MARKER = "…"
_COLOUR = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_HOOK_VERDICTS = ("Passed", "Failed", "Skipped")
_HOOK_FAILED = "Failed"
_DOT_RUN = "..."
_HOOK_BOOKKEEPING = ("- hook id:", "- exit code:")
RESOLVER = Path(__file__).resolve().with_name("resolve_test_scope.py")
_LITERAL_PATHSPEC = ":(literal)"
_NODE_SEPARATOR = "::"
_STATUS_PATH_OFFSET = 3  # porcelain v1: two status letters and a space precede the path
_UNTRACKED_DIRECTORY_MARK = "/"
_GIT_DIRECTORY = ".git/"
_SCRATCH_DIRECTORY = ".ai-work"  # pipeline documents: never part of a tree patch
_EXCLUDE_AI_WORK = f":(exclude,literal){_SCRATCH_DIRECTORY}"
# Fixed whatever the user's git config says: `git apply -p1` reads no colour, helper or prefix.
_PATCH_FORMAT = (
    "--binary --no-color --no-ext-diff --no-textconv --src-prefix=a/ --dst-prefix=b/"
).split()
_MISSING = " missing"  # the end of `git cat-file --batch-check`'s line for an absent object
_DELETED = "deleted"
_NOT_A_FILE = "not-a-file"
_NO_COLOUR_ENV = {"NO_COLOR": "1", "PY_COLORS": "0"}
_FORCED_COLOUR_VARS = ("FORCE_COLOR", "CLICOLOR_FORCE")

Entries = tuple[tuple[str, str], ...]


class GitCommandError(RuntimeError):
    """git ran and refused a command the driver needs to succeed."""


class OutsideRepoError(ValueError):
    """A declared path (or `Read-only:` entry) that leaves the repository."""


# --- The commit by explicit path ---------------------------------------------------------


@dataclass(frozen=True)
class TreeSnapshot:
    """The tree outside a set of files: (path, token) pairs, and the unstaged diff as a patch.

    Tokens: git's raw index row (`staged`), the worktree blob id (`unstaged`, `untracked`; the
    blob is computed, not stored, so the patch text restores no untracked file). The patch
    takes no part in equality.
    """

    staged: Entries
    unstaged: Entries
    untracked: Entries
    unstaged_diff: str = field(default="", compare=False)

    def paths_differing(self, other: TreeSnapshot) -> tuple[str, ...]:
        mine, theirs = self._tagged(), other._tagged()
        return tuple(sorted({path for _, path, _ in mine ^ theirs}))

    def patch_text(self) -> str:
        """The snapshot as text for `TREE_SNAPSHOT_<request>.patch`: hashes, and the diff."""
        lines = ["# staged outside the pathspec"]
        lines += [f"#   {path}  {row}" for path, row in self.staged]
        lines.append("# untracked outside the pathspec (path, blob id)")
        lines += [f"#   {path}  {blob}" for path, blob in self.untracked]
        lines.append("# unstaged diff outside the pathspec")
        return "\n".join(lines) + "\n" + self.unstaged_diff

    def _tagged(self) -> frozenset[tuple[str, str, str]]:
        kinds = (
            ("staged", self.staged),
            ("unstaged", self.unstaged),
            ("untracked", self.untracked),
        )
        return frozenset((kind, path, token) for kind, entries in kinds for path, token in entries)


@dataclass(frozen=True)
class Committed:
    """The commit holds exactly the files and the tree outside them is as it was."""

    sha: str
    files: tuple[str, ...]
    withheld: tuple[str, ...]


@dataclass(frozen=True)
class NothingToCommit:
    """None of the paths differs from HEAD once the outer-loop files are withheld."""

    withheld: tuple[str, ...]


@dataclass(frozen=True)
class CommitRefused:
    """The hooks, git or a lock refused (after the one re-stage retry); the files stay staged."""

    detail: str


@dataclass(frozen=True)
class CommitInterrupted:
    """git could not run to completion (the commit outlived its bound, or git vanished).

    The declared files stay staged, `index.lock` may be left behind (`index_locked`), and the
    hooks git started may still be running and writing. `after` is the snapshot taken then.
    """

    detail: str
    after: TreeSnapshot
    index_locked: bool


@dataclass(frozen=True)
class TreeDisturbed:
    """The commit touched more than its files: `paths` moved, `sha` is the commit if any."""

    before: TreeSnapshot
    after: TreeSnapshot
    paths: tuple[str, ...]
    sha: str | None


CommitOutcome = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    Committed, NothingToCommit, CommitRefused, CommitInterrupted, TreeDisturbed
]


@dataclass(frozen=True)
class _Job:
    paths: tuple[str, ...]
    withheld: tuple[str, ...]
    message: str
    before: TreeSnapshot
    timeout: float


def commit_paths(
    repo: Path,
    paths: Iterable[str],
    message: str,
    read_only: Iterable[str] = (),
    commit_timeout: float = COMMIT_TIMEOUT_SECONDS,
) -> CommitOutcome:
    """Commit the changed files under `paths` (minus the outer-loop files), touching no other."""
    kept, withheld = split_outer_loop(paths_differing_from_head(repo, paths), read_only, repo)
    if not kept:
        return NothingToCommit(withheld)
    before = snapshot_outside(repo, frozenset(kept))
    return _commit_and_judge(repo, _Job(kept, withheld, message, before, commit_timeout))


def paths_differing_from_head(repo: Path, paths: Iterable[str]) -> tuple[str, ...]:
    """The files under the given paths (directories expand) that differ from HEAD, sorted."""
    wanted = tuple(normalise_path(p, repo) for p in paths)
    if not wanted:
        return ()
    status = _git(
        repo,
        *("status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"),
        "--",
        *_specs(wanted),
    )
    return tuple(sorted({entry[_STATUS_PATH_OFFSET:] for entry in _lines(status)}))


def normalise_path(raw: str, root: Path | None = None) -> str:
    """The repo-relative, `normpath`-clean form of a path; one leaving the repo is an error."""
    relative = raw
    if root is not None and os.path.isabs(raw):  # the shorter relpath is the one that stays inside
        relative = min((os.path.relpath(raw, base) for base in (root, root.resolve())), key=len)
    clean = posixpath.normpath(relative)
    if clean.startswith("/") or clean == ".." or clean.startswith("../"):
        raise OutsideRepoError(f"{raw!r} is outside the repository")
    return clean


def split_outer_loop(
    paths: Iterable[str], read_only: Iterable[str] = (), root: Path | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(kept, withheld), both normalised: outer-loop files leave the set whatever the plan says.

    `paths` are files (`commit_paths` expands directories first). A `Read-only:` entry is a
    path, a directory or `path::node`, cut at the first `::` only, so `weird[1].txt` is a path.
    """
    named = tuple(normalise_path(entry.split(_NODE_SEPARATOR, 1)[0], root) for entry in read_only)
    clean = tuple(normalise_path(p, root) for p in paths)
    withheld = tuple(p for p in clean if _is_outer_loop(p, named))
    return tuple(p for p in clean if p not in withheld), withheld


def snapshot_outside(repo: Path, files: frozenset[str]) -> TreeSnapshot:
    """The index rows, unstaged edits and untracked files of every path not in `files`."""
    raw = _lines(_git(repo, "diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev"))
    staged = tuple(sorted(zip(raw[1::2], raw[0::2])))  # noqa: B905 -- strict= is 3.10+
    modified = [p for p in _lines(_git(repo, "diff", "--name-only", "-z")) if p not in files]
    others = _lines(_git(repo, "ls-files", "--others", "--exclude-standard", "-z"))
    untracked = [p for p in others if not p.endswith(_UNTRACKED_DIRECTORY_MARK) and p not in files]
    diff = _git(repo, "diff", "--binary", "--", *_specs(modified)) if modified else ""
    return TreeSnapshot(
        staged=tuple((path, row) for path, row in staged if path not in files),
        unstaged=_worktree_blobs(repo, modified),
        untracked=_worktree_blobs(repo, untracked),
        unstaged_diff=diff,
    )


def restore_paths(repo: Path, paths: Iterable[str]) -> tuple[str, ...]:
    """Return the changed files under `paths` to `HEAD` and name them.

    A tracked file goes back in the index and the work tree; an untracked one is removed, and
    so is each directory that removal left empty (an empty directory still imports as a
    namespace package). Nothing outside `paths` is touched. This is the driver's one
    destructive operation: it runs over a step's declared `Files:` only, and only after
    `tree_patch` has been written. A path that is absolute, climbs out of the repository, is
    the repository itself or lies under `.git/` is refused before anything is touched.
    """
    scope = tuple(_restorable(p) for p in paths)
    changed = paths_differing_from_head(repo, scope)
    tracked = _present_in_head(repo, changed)
    gone = tuple(p for p in changed if p not in tracked)
    if tracked:
        _git(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", *_specs(tracked))
    if gone:
        _git(repo, "rm", "--cached", "--force", "--quiet", "--ignore-unmatch", "--", *_specs(gone))
        for path in gone:
            _remove_with_empty_parents(repo, path)
    return changed


def tree_patch(repo: Path) -> str:
    """The whole tree's difference from `HEAD` as one patch: staged, unstaged and untracked
    files alike, nothing under `.ai-work/`. The index is read, never written."""
    tracked = _patch(repo, "HEAD", "--no-renames", "--", _EXCLUDE_AI_WORK)
    others = _lines(_git(repo, "ls-files", "--others", "--exclude-standard", "-z"))
    new_files = [p for p in others if not (p.endswith(_UNTRACKED_DIRECTORY_MARK) or _is_scratch(p))]
    return tracked + "".join(_patch(repo, "--no-index", "--", os.devnull, p) for p in new_files)


def _restorable(raw: str) -> str:
    clean = normalise_path(raw)
    if clean == "." or (clean + "/").lower().startswith(_GIT_DIRECTORY):
        raise OutsideRepoError(f"{raw!r} is not a path a restore may touch")
    return clean


def _present_in_head(repo: Path, paths: tuple[str, ...]) -> tuple[str, ...]:
    if not paths:
        return ()
    asked = "".join(f"HEAD:{path}\n" for path in paths)
    answers = _git(repo, "cat-file", "--batch-check", stdin=asked).splitlines()
    return tuple(paths[i] for i, answer in enumerate(answers) if not answer.endswith(_MISSING))


def _is_scratch(path: str) -> bool:
    return (path + "/").startswith(_SCRATCH_DIRECTORY + "/")


def _patch(repo: Path, *args: str) -> str:
    """`git diff` as the bytes git wrote, decoded losslessly: the runner's text mode would
    turn a bare CR or a non-UTF-8 byte into text `git apply` rejects. Write it back with
    `surrogateescape`."""
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "patch"
        done = _run(repo, "diff", *_PATCH_FORMAT, f"--output={target}", *args)
        if done.returncode not in (0, 1):  # 1 is "the files differ" under --no-index
            raise GitCommandError(f"git diff failed: {_tail(done.stderr)}")
        return target.read_bytes().decode("utf-8", "surrogateescape")


def _remove_with_empty_parents(repo: Path, path: str) -> None:
    (repo / path).unlink(missing_ok=True)
    for parent in Path(path).parents[:-1]:  # the last one is the repository itself
        try:
            (repo / parent).rmdir()
        except OSError:  # not empty (or gone): what is left is not ours
            return


def _commit_and_judge(repo: Path, job: _Job) -> CommitOutcome:
    try:
        _stage(repo, job.paths)
        staged = _git(
            repo, "diff", "--cached", "--name-only", "--no-renames", "-z", "--", *_specs(job.paths)
        )
        expected = frozenset(_lines(staged))
        refused = _commit_with_retry(repo, job) if expected else None
    except GitCommandError as exc:
        return CommitRefused(str(exc))
    except GitUnavailableError as exc:
        after = snapshot_outside(repo, frozenset(job.paths))
        return CommitInterrupted(str(exc), after, _index_locked(repo))
    if not expected:
        return NothingToCommit(job.withheld)
    after = snapshot_outside(repo, frozenset(job.paths))
    if after != job.before:
        sha = _head_sha(repo) if refused is None else None
        return TreeDisturbed(job.before, after, job.before.paths_differing(after), sha)
    if refused is not None:
        return CommitRefused(refused)
    return _verified(repo, job, expected)


def _is_outer_loop(path: str, named: tuple[str, ...]) -> bool:
    if (path + "/").startswith(OUTER_LOOP_PREFIXES):
        return True
    return any(path == one or path.startswith(one + "/") for one in named)


def _specs(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(_LITERAL_PATHSPEC + path for path in paths)


def _stage(repo: Path, paths: tuple[str, ...]) -> None:
    """Stage what exists in the work tree or the index; a deletion or move already staged
    (`git rm`, `git mv`) names a path in neither, which `git add` refuses and needs nothing."""
    indexed = frozenset(_lines(_git(repo, "ls-files", "--cached", "-z", "--", *_specs(paths))))
    present = [p for p in paths if p in indexed or os.path.lexists(repo / p)]
    if present:
        _git(repo, "add", "--all", "--", *_specs(present))


def _commit_with_retry(repo: Path, job: _Job) -> str | None:
    """None on success, else git's own words. Hooks that rewrote files get one re-stage."""
    attempt = _try_commit(repo, job)
    if attempt is not None and _lines(
        _git(repo, "diff", "--name-only", "-z", "--", *_specs(job.paths))
    ):
        _stage(repo, job.paths)
        attempt = _try_commit(repo, job)
    return attempt


def _try_commit(repo: Path, job: _Job) -> str | None:
    done = _run(repo, "commit", "-m", job.message, "--", *_specs(job.paths), timeout=job.timeout)
    if done.returncode == 0:
        return None
    return hook_words(done.stdout + done.stderr)


def _verified(repo: Path, job: _Job, expected: frozenset[str]) -> Union[Committed, TreeDisturbed]:  # noqa: UP007 -- runtime value, 3.9 floor
    """The commit just made, if its file set is exactly what was staged."""
    sha = _head_sha(repo)
    listing = _git(
        repo,
        "diff-tree",
        "--root",
        "-r",
        "--no-renames",
        "--no-commit-id",
        "--name-only",
        "-z",
        sha,
    )
    files = frozenset(_lines(listing))
    if files != expected:
        return TreeDisturbed(job.before, job.before, tuple(sorted(files ^ expected)), sha)
    return Committed(sha, tuple(sorted(files)), job.withheld)


def _head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "--verify", "HEAD").strip()


def _index_locked(repo: Path) -> bool:
    done = run_git(repo, "rev-parse", "--git-path", "index.lock")
    return done.returncode == 0 and (repo / done.stdout.strip()).exists()


def _worktree_blobs(repo: Path, paths: list[str]) -> Entries:
    """Blob ids of the files as they are on disk; a file git cannot hash gets a marker."""
    marked = {p: _DELETED for p in paths if not os.path.lexists(repo / p)}
    marked |= {p: _NOT_A_FILE for p in paths if p not in marked and not (repo / p).is_file()}
    hashable = [p for p in paths if p not in marked]
    if hashable:  # a path holding a newline cannot ride --stdin-paths; none is expected
        ids = _git(
            repo, "hash-object", "--no-filters", "--stdin-paths", stdin="\n".join(hashable) + "\n"
        )
        marked |= dict(zip(hashable, ids.split()))  # noqa: B905 -- strict= is 3.10+
    return tuple(sorted(marked.items()))


def _run(
    repo: Path, *args: str, stdin: str | None = None, timeout: float = GIT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    return run_git(repo, *args, stdin=stdin, timeout=timeout)


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    done = _run(repo, *args, stdin=stdin)
    if done.returncode != 0:
        raise GitCommandError(f"git {' '.join(args[:3])} failed: {_tail(done.stderr)}")
    return done.stdout


def _lines(nul_separated: str) -> list[str]:
    return [part for part in nul_separated.split("\0") if part]


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-FAILURE_TAIL_LINES:])


def hook_words(output: str) -> str:
    """The refusing hook's own words from a commit's whole output, as one bounded line.

    pre-commit prints one status line per hook, then the failing hook's report; every section
    that opens at a `Failed` status line and runs to the next status line is kept, minus its
    bookkeeping and blank lines. Output with no such section (a plain hook, another hook
    manager, git itself) yields its last non-blank lines.
    """
    lines = [_COLOUR.sub("", line).strip() for line in output.splitlines()]
    kept = _failed_sections(lines) or [line for line in lines if line][-HOOK_WORDS_FALLBACK_LINES:]
    words = " ".join(kept)
    if len(words) <= HOOK_WORDS_LIMIT:
        return words
    return words[: HOOK_WORDS_LIMIT - len(_CUT_MARKER)] + _CUT_MARKER


def _hook_verdict(line: str) -> str | None:
    """The verdict of a pre-commit status line (`name....(note)Verdict`), else None.

    Plain suffix tests, not a pattern: a hook may print an unbroken run of dots, and a pattern
    that backtracks on it would stall the driver after the commit's own timeout has closed.
    """
    verdict = next((word for word in _HOOK_VERDICTS if line.endswith(word)), None)
    if verdict is None:
        return None
    head = line[: -len(verdict)]
    if head.endswith(")") and "(" in head:
        head = head[: head.rfind("(")]
    named = head.rstrip(".")
    return verdict if named and head.endswith(_DOT_RUN) else None


def _failed_sections(lines: list[str]) -> list[str]:
    kept: list[str] = []
    failing = False
    for line in lines:
        verdict = _hook_verdict(line)
        if verdict:
            failing = verdict == _HOOK_FAILED
        if failing and line and not line.startswith(_HOOK_BOOKKEEPING):
            kept.append(line)
    return kept


# --- The runner --------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandRun:
    """One command's output (stdout then stderr). `problem` is set iff it never exited."""

    argv: tuple[str, ...]
    cwd: str
    output: str
    returncode: int | None
    problem: str | None = None

    def __post_init__(self) -> None:
        if (self.returncode is None) != (self.problem is not None):
            raise ValueError("a run has a return code or a problem, never both and never neither")


@dataclass(frozen=True)
class ScopeRuns:
    """The derived scope: the resolver's decision and each invocation's own run."""

    decision: str
    runs: tuple[CommandRun, ...]


@dataclass(frozen=True)
class ScopeUnresolved:
    """The resolver itself failed (exit 2 means: run the full suite) or answered no JSON."""

    resolver: CommandRun


def run_check(repo: Path, command: str, timeout: float = RUN_TIMEOUT_SECONDS) -> CommandRun:
    """Run a step's `Check:` command (split like a shell would, run without one)."""
    return run_command(tuple(shlex.split(command)), repo, timeout)


def run_derived_scope(
    repo: Path, changed: Iterable[str], timeout: float = RUN_TIMEOUT_SECONDS
) -> Union[ScopeRuns, ScopeUnresolved]:  # noqa: UP007 -- runtime value, 3.9 floor
    """Resolve the test scope for `changed` and run every invocation it lists."""
    ask = (sys.executable, str(RESOLVER), "--repo-root", str(repo), "--changed", *changed, "--json")
    resolver = run_command(ask, repo, RESOLVER_TIMEOUT_SECONDS)
    plan = _read_plan(resolver)
    if plan is None:
        return ScopeUnresolved(resolver)
    invocations = [i for pocket in plan["pockets"] for i in pocket["invocations"]]
    runs = tuple(run_command(tuple(i["argv"]), repo / i["cwd"], timeout) for i in invocations)
    return ScopeRuns(str(plan["decision"]), runs)


def run_command(argv: tuple[str, ...], cwd: Path, timeout: float) -> CommandRun:
    """Run `argv` under a timeout with colour off; a run that cannot finish says why.

    The command leads its own process group and a timeout kills the whole group: a
    `uv run pytest` or a shell wrapper must not leave workers editing the tree after the
    driver has reported the run as over or been interrupted.
    """
    with sigterm_as_exit():
        try:
            proc = subprocess.Popen(
                argv, cwd=str(cwd), env=_no_colour_env(), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                start_new_session=True,
            )  # fmt: skip
        except OSError as exc:
            return CommandRun(argv, str(cwd), "", None, f"could not start: {exc}")
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            out, err = kill_group(proc)
            return CommandRun(argv, str(cwd), out + err, None, f"timed out after {timeout:g}s")
        except BaseException:  # an interrupt must not leave the runner editing the tree
            kill_group(proc)
            raise
        return CommandRun(argv, str(cwd), out + err, proc.returncode)


@contextlib.contextmanager
def sigterm_as_exit() -> Iterator[None]:
    """Let a SIGTERM reach `run_command`'s kill path as an exit, not as the default action."""
    if threading.current_thread() is not threading.main_thread():
        yield  # `signal.signal` works on the main thread only
        return
    previous = signal.signal(signal.SIGTERM, lambda signum, _frame: sys.exit(128 + signum))
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous or signal.SIG_DFL)


def kill_group(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """Kill the command's whole process group; what it had printed comes back."""
    with contextlib.suppress(ProcessLookupError):  # the group may already be gone
        os.killpg(proc.pid, signal.SIGKILL)
    try:
        return proc.communicate(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:  # a descendant left the group and holds the pipes
        return "", ""


def _read_plan(resolver: CommandRun) -> dict | None:
    if resolver.returncode != 0:
        return None
    try:
        plan = json.loads(resolver.output)
    except json.JSONDecodeError:
        return None
    return plan if isinstance(plan, dict) and "pockets" in plan else None


def _no_colour_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _FORCED_COLOUR_VARS}
    return {**env, **_NO_COLOUR_ENV}
