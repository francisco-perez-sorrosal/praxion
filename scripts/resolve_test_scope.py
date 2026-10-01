#!/usr/bin/env python3
"""Derived test selection: which tests does this change need?

    python3 scripts/resolve_test_scope.py [--changed PATH ... | --changed-from REF | --full]
                                          [--json [--per-path]] [--repo-root DIR]

Input is exactly one mode: explicit paths, the branch diff `REF...HEAD` plus
the working tree, the full suite, or (no mode) the working tree alone -- the
tracked diff against `HEAD` plus untracked files. Untracked files always count
as changed: a new source file is invisible to `git diff`, and omitting it would
under-select exactly when the blast radius is least known. Renames are split
into the old path (deleted) and the new one (added), and a deleted file is
never emitted as a test target -- its surviving dependents are.

The flow: changed set -> global widen triggers -> partition by pocket (the
longest matching root) -> Python derivation (`_python_selection`) or the
pocket's native adapter -> unmapped paths through the non-source predicate ->
one `Selection` per pocket. Contract:
`skills/testing-strategy/references/test-selection.md`.


The safety property
-------------------
**A change the resolver cannot account for widens the run; it never narrows
it.** Returning "no tests" for a change nothing covers is a false all-clear
(`rules/swe/gate-liveness.md`). So every pocket runs its full suite when:

- a changed path is not a test, reaches no test, and is not non-source
  (`unmapped-path`);
- a resolver source file changed (`selector-changed`) -- the selector never
  vouches for its own edits;
- the declared list changed (`declared-deps-changed`) or fails to parse or
  validate (`declared-deps-invalid`) -- an entry is never dropped silently.

A pocket's own runner configuration or lockfile changing widens that pocket
alone (`pocket-config-changed`), as does a pocket no adapter can derive for
(`no-adapter`).


The non-source predicate (and why it is this narrow)
----------------------------------------------------
Applied only to paths that reached no test, and every exemption is reported
under `ignored_non_source` rather than applied invisibly:

1. `git-ignored` -- inside `.git/`, or `git check-ignore` says the project
   ignores it. No taste involved: the project already declared it untracked.
2. `root-narrative` -- a root-level community-health file (`README*`,
   `CHANGELOG*`, `CONTRIBUTING*`, `CODE_OF_CONDUCT*`, `SECURITY*`, `LICENSE*`,
   `NOTICE*`, `AUTHORS*`). Root-scoped on purpose: a nested prose file may be
   a fixture, and `CLAUDE.md` is measured by a token-budget gate.
3. `declared-inert` -- an `[[inert]]` entry in `tests/declared-deps.toml`,
   the reviewable replacement for per-call exemptions.

`docs/` and `.ai-state/` are deliberately not exempt: tests read both.


Output
------
`--json` emits the schema-2 object; otherwise runnable, runner-prefixed
commands go to stdout and context to stderr, so `resolve_test_scope.py | sh -e`
runs the selection. `--changed ... --json --per-path` answers many paths from
one process: one single-line schema-2 object per distinct path, in sorted
order, each exactly what `--changed <path> --json` prints for that path alone
(the same payload, compactly serialized). Any other combination is a usage
error. Exit codes: 0 resolved (widened included), 2 usage or
internal error -- callers treat 2 as "run the full suite".

Stdlib-only: agent prose and hooks invoke it through a bare `python3`, so a
third-party import here or in a private sibling would be a gate-liveness GL05
finding. Tests and canaries: `scripts/test_resolve_test_scope.py`.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _declared_deps import (  # noqa: E402
    EMPTY,
    DeclaredDeps,
    DeclaredDepsError,
    classify_path,
    parse,
    validate_against_inventory,
)
from _native_selection import ADAPTERS as _NATIVE_ADAPTERS  # noqa: E402
from _native_selection import Selected as _NativeSelected  # noqa: E402
from _native_selection import Widen as _NativeWiden  # noqa: E402
from _native_selection import select as _select_native  # noqa: E402
from _python_selection import (  # noqa: E402
    Derivation,
    Graph,
    SelectedTest,
    build_graph,
    derive,
    estimate_tests,
    needs_serial,
)
from _repo_root import resolve_repo_root  # noqa: E402
from _test_inventory import (  # noqa: E402
    INVENTORY_GIT_ARGS,
    POCKET_CONFIG_FILES,
    CollectionScope,
    Pocket,
    discover_pockets,
    full_suite_argv,
    is_any_test_file,
    matches_glob,
    pocket_of,
    under,
    workflow_collection_scope,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_VERSION = 2
DECLARED_DEPS_PATH = "tests/declared-deps.toml"
WORKFLOWS_DIR = ".github/workflows"

# The resolver's own sources. Edits to any of them widen: a selector cannot
# vouch for a change to itself.
SELECTOR_FILES = frozenset(
    f"scripts/{name}"
    for name in (
        "resolve_test_scope.py",
        "_declared_deps.py",
        "_test_inventory.py",
        "_python_selection.py",
        "_native_selection.py",
        "_repo_root.py",
    )
)

ROOT_NARRATIVE_GLOBS = (
    "README*",
    "CHANGELOG*",
    "CONTRIBUTING*",
    "CODE_OF_CONDUCT*",
    "SECURITY*",
    "LICENSE*",
    "NOTICE*",
    "AUTHORS*",
)

SOURCE_EXPLICIT = "explicit"
SOURCE_WORKING_TREE = "working-tree"
SOURCE_FULL = "full-requested"

RULE_GIT_IGNORED = "git-ignored"
RULE_ROOT_NARRATIVE = "root-narrative"
RULE_DECLARED_INERT = "declared-inert"

REASON_UNMAPPED = "unmapped-path"
REASON_SELECTOR = "selector-changed"
REASON_DEPS_CHANGED = "declared-deps-changed"
REASON_DEPS_INVALID = "declared-deps-invalid"
REASON_POCKET_CONFIG = "pocket-config-changed"
REASON_NO_ADAPTER = "no-adapter"
REASON_FULL = "full-requested"

EXIT_OK = 0
EXIT_ERROR = 2


class ResolverError(RuntimeError):
    """A failure the caller must treat as "run the full suite" (exit 2)."""


# --- Values ----------------------------------------------------------------------


@dataclass(frozen=True)
class ChangedSet:
    paths: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class Widen:
    reason: str
    paths: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class Ignored:
    path: str
    rule: str


@dataclass(frozen=True)
class Tests:
    tests: tuple[SelectedTest, ...]
    serial: bool


@dataclass(frozen=True)
class Native:
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Full:
    pass


@dataclass(frozen=True)
class Nothing:
    pass


Selection = Tests | Native | Full | Nothing


@dataclass(frozen=True)
class PocketResult:
    pocket: Pocket
    selection: Selection


@dataclass(frozen=True)
class Resolution:
    changed: ChangedSet
    widen: tuple[Widen, ...]
    ignored: tuple[Ignored, ...]
    pockets: tuple[PocketResult, ...]

    @property
    def decision(self) -> str:
        if self.widen:
            return "widened"
        if all(isinstance(result.selection, Nothing) for result in self.pockets):
            return "nothing-to-run"
        return "selected"


# --- Resolution ------------------------------------------------------------------


def resolve_each(repo_root: Path, paths: Sequence[str], files: Sequence[str]) -> list[Resolution]:
    """`resolve` of each path alone, over one import graph instead of one per path."""
    declared, _ = _load_declared(repo_root, files)
    graph = build_graph(
        repo_root, files, declared, _python_roots(discover_pockets(repo_root, files))
    )
    return [
        resolve(repo_root, ChangedSet((path,), SOURCE_EXPLICIT), files, graph=graph)
        for path in paths
    ]


def resolve(
    repo_root: Path, changed: ChangedSet, files: Sequence[str], *, graph: Graph | None = None
) -> Resolution:
    """The whole decision for one changed set over the repo's tracked+untracked files.

    A `graph` over `files` (from `build_graph`) spares the derivation its rebuild.
    """
    pockets = discover_pockets(repo_root, files)
    if changed.source == SOURCE_FULL:
        widen = (Widen(REASON_FULL, (), "full suite requested"),)
        return _all_full(changed, widen, (), pockets)
    declared, invalid = _load_declared(repo_root, files)
    repo_widen = (*invalid, *_trigger_widens(changed.paths))
    config_widen = _pocket_config_widens(changed.paths, pockets)
    if repo_widen:  # every pocket runs in full already; deriving would change nothing
        return _all_full(changed, (*repo_widen, *config_widen.values()), (), pockets)
    derivation = _derive(repo_root, changed.paths, files, pockets, declared, graph)
    # Config paths still feed the derivation (another pocket's test may read them),
    # but their own pocket is already widened, so they never count as unmapped.
    accounted = derivation.mapped | {p for w in config_widen.values() for p in w.paths}
    unmapped = [p for p in changed.paths if p not in accounted and _is_python_owned(p, pockets)]
    ignored = _classify_non_source(unmapped, repo_root, declared)
    exempt = {entry.path for entry in ignored}
    escaping = tuple(path for path in unmapped if path not in exempt)
    if escaping:
        detail = "changed path(s) reach no test and are not non-source"
        widen = (Widen(REASON_UNMAPPED, escaping, detail), *config_widen.values())
        return _all_full(changed, widen, ignored, pockets)
    # A deleted test still accounts for its own change (it is `mapped`), but a
    # runner handed a missing path fails the whole command.
    surviving = tuple(t for t in derivation.tests if (repo_root / t.path).is_file())
    results, native_widen = _per_pocket(repo_root, pockets, changed.paths, surviving, config_widen)
    return Resolution(changed, (*config_widen.values(), *native_widen), ignored, results)


def _derive(
    repo_root: Path,
    paths: tuple[str, ...],
    files: Sequence[str],
    pockets: tuple[Pocket, ...],
    declared: DeclaredDeps,
    graph: Graph | None,
) -> Derivation:
    workflows = workflow_collection_scope(repo_root / WORKFLOWS_DIR)
    return derive(
        repo_root,
        paths,
        declared,
        files=files,
        pocket_roots=_python_roots(pockets),
        is_runnable=lambda test: _is_runnable(test, pockets, workflows),
        graph=graph,
    )


def _python_roots(pockets: tuple[Pocket, ...]) -> tuple[str, ...]:
    return tuple(pocket.root for pocket in pockets if pocket.ecosystem == "python") or (".",)


def _per_pocket(
    repo_root: Path,
    pockets: tuple[Pocket, ...],
    paths: tuple[str, ...],
    tests: tuple[SelectedTest, ...],
    config_widen: dict[str, Widen],
) -> tuple[tuple[PocketResult, ...], tuple[Widen, ...]]:
    results: list[PocketResult] = []
    widens: list[Widen] = []
    for pocket in pockets:
        own_tests = tuple(t for t in tests if pocket_of(t.path, pockets) == pocket)
        if pocket.root in config_widen:
            results.append(PocketResult(pocket, Full()))
        elif pocket.ecosystem == "python":
            results.append(PocketResult(pocket, _python_selection(repo_root, pocket, own_tests)))
        else:
            own_paths = [p for p in paths if pocket_of(p, pockets) == pocket]
            own_paths += [t.path for t in own_tests]
            selection, widen = _native_selection(repo_root, pocket, tuple(dict.fromkeys(own_paths)))
            results.append(PocketResult(pocket, selection))
            widens.extend(widen)
    return tuple(results), tuple(widens)


def _python_selection(
    repo_root: Path, pocket: Pocket, tests: tuple[SelectedTest, ...]
) -> Selection:
    if not tests:
        return Nothing()
    count = estimate_tests(repo_root, (t.path for t in tests))
    return Tests(tests, needs_serial(count, pocket.xdist))


def _native_selection(
    repo_root: Path, pocket: Pocket, paths: tuple[str, ...]
) -> tuple[Selection, tuple[Widen, ...]]:
    """Hand a non-Python pocket's changed paths to its ecosystem's own tool."""
    if not paths:
        return Nothing(), ()
    relative = tuple(_pocket_relative(p, pocket.root) for p in paths)
    outcome = _select_native(
        pocket.framework, repo_root / pocket.root, pocket.runner_prefix, relative
    )
    if isinstance(outcome, _NativeSelected):
        return Native(outcome.argv), ()
    assert isinstance(outcome, _NativeWiden)
    detail = f"{outcome.detail} for the {pocket.framework} pocket at {pocket.root}"
    return Full(), (Widen(outcome.reason, paths, detail),)


def _all_full(
    changed: ChangedSet,
    widen: tuple[Widen, ...],
    ignored: tuple[Ignored, ...],
    pockets: tuple[Pocket, ...],
) -> Resolution:
    return Resolution(changed, widen, ignored, tuple(PocketResult(p, Full()) for p in pockets))


def _load_declared(repo_root: Path, files: Sequence[str]) -> tuple[DeclaredDeps, tuple[Widen, ...]]:
    try:
        declared = parse(repo_root / DECLARED_DEPS_PATH)
        validate_against_inventory(declared, (f for f in files if is_any_test_file(f)))
    except DeclaredDepsError as exc:
        return EMPTY, (Widen(REASON_DEPS_INVALID, (DECLARED_DEPS_PATH,), str(exc)),)
    return declared, ()


def _trigger_widens(paths: Iterable[str]) -> tuple[Widen, ...]:
    paths = tuple(paths)
    triggers = (
        (
            REASON_SELECTOR,
            tuple(p for p in paths if p in SELECTOR_FILES),
            "a resolver source changed",
        ),
        (
            REASON_DEPS_CHANGED,
            tuple(p for p in paths if p == DECLARED_DEPS_PATH),
            "the declared list changed",
        ),
    )
    return tuple(Widen(reason, hits, detail) for reason, hits, detail in triggers if hits)


def _pocket_config_widens(paths: Iterable[str], pockets: tuple[Pocket, ...]) -> dict[str, Widen]:
    """Pocket root -> widen, for each pocket whose runner config or lockfile changed."""
    hits: dict[str, list[str]] = {}
    for path in paths:
        pocket = pocket_of(path, pockets)
        directory, _, name = path.rpartition("/")
        if pocket is None or (directory or ".") != pocket.root:
            continue
        if name in POCKET_CONFIG_FILES.get(pocket.ecosystem, frozenset()):
            hits.setdefault(pocket.root, []).append(path)
    return {
        root: Widen(
            REASON_POCKET_CONFIG, tuple(found), f"runner configuration of pocket {root} changed"
        )
        for root, found in hits.items()
    }


def _is_runnable(test: str, pockets: tuple[Pocket, ...], workflows: CollectionScope) -> bool:
    """Would any runner collect this test? Fixture files named like tests are not run."""
    pocket = pocket_of(test, pockets)
    if pocket is None:
        return False
    if pocket.ecosystem != "python":
        return True
    return pocket.collection.covers(test) or workflows.covers(test)


def _is_python_owned(path: str, pockets: tuple[Pocket, ...]) -> bool:
    """Paths in native pockets belong to their adapter; everything else to derivation."""
    pocket = pocket_of(path, pockets)
    return pocket is None or pocket.ecosystem == "python"


def _classify_non_source(
    paths: Sequence[str], repo_root: Path, declared: DeclaredDeps
) -> tuple[Ignored, ...]:
    ignored: dict[str, str] = {}
    undecided: list[str] = []
    for path in paths:
        if path == ".git" or path.startswith(".git/"):
            ignored[path] = RULE_GIT_IGNORED
        elif "/" not in path and any(matches_glob(path, g) for g in ROOT_NARRATIVE_GLOBS):
            ignored[path] = RULE_ROOT_NARRATIVE
        elif classify_path(declared, path) == "inert":
            ignored[path] = RULE_DECLARED_INERT
        else:
            undecided.append(path)
    for path in _git_ignored(undecided, repo_root):
        ignored[path] = RULE_GIT_IGNORED
    return tuple(Ignored(path, rule) for path, rule in sorted(ignored.items()))


# --- Git plumbing ----------------------------------------------------------------


def _git_paths(args: list[str], repo_root: Path) -> list[str]:
    """NUL-separated path output of a git command, or a loud failure."""
    try:
        result = subprocess.run(
            ["git", *args, "-z"], cwd=repo_root, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise ResolverError("git is not installed") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown error"
        raise ResolverError(f"`git {' '.join(args)}` failed: {detail}")
    return [path for path in result.stdout.split("\0") if path]


def _git_ignored(paths: Sequence[str], repo_root: Path) -> tuple[str, ...]:
    """Paths the project's `.gitignore` excludes. Unavailable git => none (they widen)."""
    if not paths:
        return ()
    # Paths go on stdin: the changed set is unbounded, and exit 1 means "none ignored".
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=repo_root,
        input="\n".join(paths),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return ()
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def repo_files(repo_root: Path) -> list[str]:
    """Tracked plus untracked, non-ignored files."""
    return _git_paths(list(INVENTORY_GIT_ARGS), repo_root)


def changed_paths(args: argparse.Namespace, repo_root: Path) -> ChangedSet:
    if args.full:
        return ChangedSet((), SOURCE_FULL)
    if args.changed:
        normalized = {_normalize(path, repo_root) for path in args.changed}
        return ChangedSet(tuple(sorted(normalized)), SOURCE_EXPLICIT)
    # The working tree always counts: a branch diff alone would report "nothing
    # to run" for an edit not yet committed -- the most common moment to ask.
    changed = {*_git_diff_names(["HEAD"], repo_root), *_git_untracked(repo_root)}
    source = SOURCE_WORKING_TREE
    if args.changed_from:
        changed |= set(_git_diff_names([f"{args.changed_from}...HEAD"], repo_root))
        source = f"git-diff:{args.changed_from}...HEAD+{SOURCE_WORKING_TREE}"
    return ChangedSet(tuple(sorted(changed)), source)


def _git_diff_names(revisions: list[str], repo_root: Path) -> list[str]:
    """Changed paths, a rename counted as its old path deleted plus its new one added.

    Rename detection would hide the old path, and a test still reading it is
    exactly the one the rename breaks.
    """
    return _git_paths(["diff", "--name-only", "--no-renames", *revisions], repo_root)


def _git_untracked(repo_root: Path) -> list[str]:
    return _git_paths(["ls-files", "--others", "--exclude-standard"], repo_root)


def _normalize(raw: str, repo_root: Path) -> str:
    """Repo-relative POSIX form. An out-of-tree path is an error, not a silent drop."""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(repo_root.resolve())
        except ValueError as exc:
            raise ResolverError(f"path {raw!r} is outside the repo root") from exc
    return candidate.as_posix().removeprefix("./")


# --- Output ----------------------------------------------------------------------


def to_payload(resolution: Resolution) -> dict[str, object]:
    """The schema-2 object. The human form renders from this, so the two cannot drift."""
    return {
        "schema": SCHEMA_VERSION,
        "changed": {"source": resolution.changed.source, "paths": list(resolution.changed.paths)},
        "decision": resolution.decision,
        "widen": [
            {"reason": w.reason, "paths": list(w.paths), "detail": w.detail}
            for w in resolution.widen
        ],
        "ignored_non_source": [{"path": i.path, "rule": i.rule} for i in resolution.ignored],
        "pockets": [_pocket_payload(result) for result in resolution.pockets],
    }


def _pocket_payload(result: PocketResult) -> dict[str, object]:
    pocket, selection = result.pocket, result.selection
    tests = selection.tests if isinstance(selection, Tests) else ()
    return {
        "root": pocket.root,
        "ecosystem": pocket.ecosystem,
        "adapter": _adapter_name(pocket),
        "selection": _selection_name(selection),
        "tests": [{"path": t.path, "via": t.via, "because": t.because} for t in tests],
        "invocations": [{"cwd": pocket.root, "argv": list(argv)} for argv in _invocations(result)],
    }


def _adapter_name(pocket: Pocket) -> str:
    if pocket.ecosystem == "python":
        return "python-derived"
    return pocket.framework if pocket.framework in _NATIVE_ADAPTERS else "none"


def _selection_name(selection: Selection) -> str:
    if isinstance(selection, Tests):
        return "tests"
    if isinstance(selection, Native):
        return "native"
    if isinstance(selection, Full):
        return "full"
    return "nothing"


def _invocations(result: PocketResult) -> tuple[tuple[str, ...], ...]:
    pocket, selection = result.pocket, result.selection
    if isinstance(selection, Tests):
        serial = ("-n", "0") if selection.serial else ()
        paths = tuple(_pocket_relative(t.path, pocket.root) for t in selection.tests)
        return ((*pocket.runner_prefix, "pytest", *serial, *paths),)
    if isinstance(selection, Native):
        return (selection.argv,)
    if isinstance(selection, Full):
        return (full_suite_argv(pocket),)
    return ()


def _pocket_relative(path: str, root: str) -> str:
    return path if root in ("", ".") or not under(path, root) else path[len(root) + 1 :]


def print_human(payload: dict[str, object]) -> None:
    """Commands to stdout, context to stderr -- so the output stays pipe-safe."""

    def note(text: str) -> None:
        print(text, file=sys.stderr)

    changed = payload["changed"]
    note(f"# changed-set source: {changed['source']} ({len(changed['paths'])} path(s))")
    note(f"# decision: {payload['decision']}")
    for entry in payload["ignored_non_source"]:
        note(f"# ignored (non-source, {entry['rule']}): {entry['path']}")
    for widen in payload["widen"]:
        note(f"# WIDENED ({widen['reason']}): {widen['detail']}")
        for path in widen["paths"]:
            note(f"#   {path}")
    commands = 0
    for pocket in payload["pockets"]:
        note(f"# pocket {pocket['root']} ({pocket['ecosystem']}): {pocket['selection']}")
        for test in pocket["tests"]:
            note(f"#   {test['path']}  [{test['via']} <- {test['because']}]")
        for invocation in pocket["invocations"]:
            command = " ".join(shlex.quote(part) for part in invocation["argv"])
            cwd = invocation["cwd"]
            print(command if cwd == "." else f"(cd {shlex.quote(cwd)} && {command})")
            commands += 1
    if not commands:
        note("# nothing to run")


# --- CLI -------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Derive the tests a change needs.",
        epilog="A change the resolver cannot account for widens the run; it never narrows it.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--changed", nargs="+", action="extend", metavar="PATH", help="explicit paths"
    )
    mode.add_argument(
        "--changed-from",
        metavar="REF",
        help="REF...HEAD plus uncommitted edits and untracked files",
    )
    mode.add_argument("--full", action="store_true", help="the full suite for every pocket")
    parser.add_argument("--json", action="store_true", help="emit the schema-2 object")
    parser.add_argument(
        "--per-path",
        action="store_true",
        help="with --changed --json: one single-line schema-2 object per path",
    )
    parser.add_argument("--repo-root", help="repo root override")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse reports usage errors by exiting; keep the int contract
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    if args.per_path and not (args.changed and args.json):
        print("error: --per-path needs --changed and --json", file=sys.stderr)
        return EXIT_ERROR
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    try:
        changed = changed_paths(args, repo_root)
        files = repo_files(repo_root)
        if args.per_path:
            payloads = [to_payload(each) for each in resolve_each(repo_root, changed.paths, files)]
        else:
            payloads = [to_payload(resolve(repo_root, changed, files))]
    except ResolverError as exc:
        print(f"error: {exc} -- run the full suite", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # an internal defect must still honour "2 means run everything"
        print(f"internal error: {exc!r} -- run the full suite", file=sys.stderr)
        return EXIT_ERROR
    if args.per_path:
        for payload in payloads:
            print(json.dumps(payload))
    elif args.json:
        print(json.dumps(payloads[0], indent=2))
    else:
        print_human(payloads[0])
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
