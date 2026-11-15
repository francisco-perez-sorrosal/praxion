"""Grade a session's refactoring end state by what it leaves in the repository, never by what it says.

The workspace is a git repository whose root commit is the template's ``start/``; its end state is
the working tree, whatever the session committed on top of that root. Each check is one clause of
the refactoring skill's verification checklist (the implementer's) or of the pre-refactor contract
(the test-engineer's). The account a session gives of its own work is accepted and never read.

The checks name no template. A template says only where the code moves, in the ``refactoring.toml``
of its ``start/`` (a staged pool workspace holds none, and is handed the file). What moved is
derived from the end state: whatever the target module defines.
"""

from __future__ import annotations

import ast
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from praxion_evals.adherence.model import Role

MANIFEST = "refactoring.toml"
SOURCE_ROOT = "src"  # a leading directory that is not part of a module's dotted name
TEST_TIMEOUT_SECONDS = 120
PYTEST_TESTS_FAILED = 1  # pytest's exit code for "the tests ran and some failed"; 0 is all passed
ERROR_DETAIL_LINES = 8
GIT_TIMEOUT_SECONDS = 60
# Environment that would leak the eval's own pytest and coverage settings into the graded one.
_FOREIGN_ENV_PREFIXES = ("PYTEST_", "COV_CORE", "COVERAGE")


class PytestRunError(Exception):
    """The task repository's tests reached no verdict: a timeout, or an exit code that says the
    run itself broke. Such an item is errored, never failed: it is no finding about the session."""


@dataclass(frozen=True)
class RefactoringGrade:
    failed: tuple[str, ...]  # checklist items that do not hold, in checklist order
    errored: Mapping[str, str] = MappingProxyType({})  # items that could not be judged, and why

    @property
    def passed(self) -> bool:
        return not self.failed and not self.errored


def grade_workspace(
    role: Role, workspace: Path, account: str, *, manifest: Path | None = None
) -> RefactoringGrade:
    """Grade the end state against the role's checklist; ``account`` is never read.

    Comparisons are against the root commit, so a committed change counts. The move is read from
    ``manifest`` when given, else from the root commit.
    """
    checks = CHECKLISTS.get(role)
    if checks is None:
        raise ValueError(f"no refactoring grader is written for {role} yet")
    base = _root_commit(workspace)
    evidence = Evidence(
        workspace,
        base,
        _read_move(workspace, base, manifest),
        _parse_python(workspace),
        _changed_paths(workspace, base),
    )
    failed: list[str] = []
    errored: dict[str, str] = {}
    for item, holds in checks:
        try:
            if not holds(evidence):
                failed.append(item)
        except PytestRunError as error:
            errored[item] = str(error)
    return RefactoringGrade(tuple(failed), MappingProxyType(errored))


# -- What the workspace holds ---------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """Where the code moves from and to, and where its tests live (paths relative to the root)."""

    source: str
    target: str
    tests: str
    # Names the move relocates. Only the test-engineer's grade needs them, because its end state
    # is read before the target exists, so what moves cannot yet be derived from it.
    moving: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Move:
        raw = tomllib.loads(text)
        missing = [
            key for key in ("source", "target", "tests") if not isinstance(raw.get(key), str)
        ]
        if missing:
            raise ValueError(f"{MANIFEST} lacks a string for {', '.join(missing)}")
        moving = raw.get("moving", [])
        if not (isinstance(moving, list) and all(isinstance(name, str) for name in moving)):
            raise ValueError(f"{MANIFEST} lacks a list of strings for moving")
        return cls(raw["source"], raw["target"], raw["tests"], tuple(moving))


@dataclass(frozen=True)
class Evidence:
    workspace: Path
    base: str  # the workspace's root commit: the starting point every comparison is made against
    move: Move
    trees: Mapping[str, ast.Module]  # every parsable Python file of the working tree, by path
    changed: tuple[str, ...]  # paths that differ from the base commit, sorted

    @property
    def source(self) -> ast.Module | None:
        return self.trees.get(self.move.source)

    @property
    def target(self) -> ast.Module | None:
        return self.trees.get(self.move.target)

    @property
    def arrived(self) -> frozenset[str]:
        """The names the target defines: what the move put there."""
        return _defined_names(self.target) if self.target else frozenset()

    @property
    def authored_tests(self) -> Mapping[str, frozenset[str]]:
        """The test functions the session added, by changed file under the tests directory."""
        authored: dict[str, frozenset[str]] = {}
        for path in self.changed:
            tree = self.trees.get(path)
            if tree is None or not PurePosixPath(path).is_relative_to(self.move.tests):
                continue
            started = _committed_tree(self.workspace, self.base, path)
            added = _test_names(tree) - _test_names(started)
            if added:
                authored[path] = added
        return MappingProxyType(authored)


def _root_commit(workspace: Path) -> str:
    """The one parentless commit: the template's ``start/``, which a session cannot rewrite."""
    try:
        roots = _git(workspace, "rev-list", "--max-parents=0", "HEAD").decode().split()
    except subprocess.CalledProcessError:
        roots = []  # an unborn HEAD has no commit at all
    if len(roots) != 1:
        raise ValueError(f"the workspace has {len(roots)} root commits, not one starting commit")
    return roots[0]


def _read_move(workspace: Path, base: str, manifest: Path | None) -> Move:
    if manifest is not None:
        return Move.parse(manifest.read_text(encoding="utf-8"))
    try:
        return Move.parse(_git(workspace, "show", f"{base}:{MANIFEST}").decode("utf-8"))
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{MANIFEST} is not committed in the starting commit") from error


def _parse_python(workspace: Path) -> dict[str, ast.Module]:
    trees: dict[str, ast.Module] = {}
    for path in sorted(workspace.rglob("*.py")):
        relative = path.relative_to(workspace)
        if _is_scratch(relative.parts):
            continue
        try:
            trees[relative.as_posix()] = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError):
            continue  # a file that does not parse is the tests' finding, not this module's
    return trees


def _changed_paths(workspace: Path, base: str) -> tuple[str, ...]:
    """Paths that differ from the base commit, committed or not, staged or not, new files included."""
    tracked = _git(workspace, "diff", base, "--name-only", "--no-renames", "-z")
    untracked = _git(workspace, "ls-files", "--others", "--exclude-standard", "-z")
    paths = {path for path in (tracked + untracked).decode("utf-8").split("\0") if path}
    return tuple(sorted(path for path in paths if not _is_scratch(PurePosixPath(path).parts)))


def _is_scratch(parts: tuple[str, ...]) -> bool:
    """Whether a path lives in a hidden or bytecode-cache directory: tooling's, not the session's."""
    return any(part.startswith(".") or part == "__pycache__" for part in parts[:-1])


def _committed_tree(workspace: Path, base: str, path: str) -> ast.Module | None:
    try:
        return ast.parse(_git(workspace, "show", f"{base}:{path}").decode("utf-8"))
    except (subprocess.CalledProcessError, SyntaxError, ValueError):
        return None  # the base commit has no such file, or none that parses


# -- The implementer's checklist ------------------------------------------------------------------


def _tests_still_pass(evidence: Evidence) -> bool:
    return _pytest_passes(evidence.workspace)


def _behaviour_is_unchanged(evidence: Evidence) -> bool:
    """The starting commit's tests, run against the end state's code.

    A session that changed behaviour and rewrote the tests to match passes its own tests; the
    tests it started from are the behaviour it was asked to keep.
    """
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "repository"
        shutil.copytree(
            evidence.workspace, copy, ignore=shutil.ignore_patterns(".git", "__pycache__")
        )
        shutil.rmtree(copy / evidence.move.tests, ignore_errors=True)
        archive = _git(evidence.workspace, "archive", evidence.base, evidence.move.tests)
        with tarfile.open(fileobj=io.BytesIO(archive)) as original:
            original.extractall(copy, filter="data")
        return _pytest_passes(copy)


def _every_call_site_is_re_wired(evidence: Evidence) -> bool:
    """Something arrived in the target, and nothing outside it and the source still asks the source.

    A caller is stale when it imports from the source a name the target now defines (served by a
    shim or a duplicate), or a name the source no longer binds at all.
    """
    if not evidence.arrived:
        return False
    source_module = _module_name(evidence.move.source)
    kept = (
        _defined_names(evidence.source) | _imported_names(evidence.source)
        if evidence.source
        else frozenset()
    )
    return not any(
        _is_stale(path, tree, source_module, evidence.arrived, kept)
        for path, tree in evidence.trees.items()
        if path not in (evidence.move.source, evidence.move.target)
    )


def _no_dead_code_remains(evidence: Evidence) -> bool:
    """No copy of moved code stays in the source, and neither module imports what it never uses."""
    arrived = evidence.arrived
    unused = [
        _unused_imports(tree) - arrived  # an unused import of a moved name is a shim, not dead
        for tree in (evidence.source, evidence.target)
        if tree
    ]
    copies = _leftover_copies(evidence.source, arrived) if evidence.source else frozenset()
    return not copies and not any(unused)


def _no_transitional_shim_remains(evidence: Evidence) -> bool:
    """The source offers no moved name: no forwarder, no alias, no re-export."""
    return not (evidence.source and _shims(evidence.source, evidence.arrived))


# -- The test-engineer's checklist ----------------------------------------------------------------


def _characterization_tests_come_first(evidence: Evidence) -> bool:
    """Tests were added and nothing outside the tests directory differs from the starting commit.

    The workspace shows the end state only, so "before any structural change" is read as "no
    structural change at all": the session's whole diff is tests.
    """
    outside = [
        path
        for path in evidence.changed
        if not PurePosixPath(path).is_relative_to(evidence.move.tests)
    ]
    return bool(evidence.authored_tests) and not outside


def _characterization_tests_pin_the_public_surface(evidence: Evidence) -> bool:
    """The tests the session added never name what the move relocates: they would break when it moves.

    A test that was already there is not the session's, whatever it names.
    """
    if not evidence.move.moving:
        raise ValueError(f"{MANIFEST} names no moving code to keep the tests off")
    moving = frozenset(evidence.move.moving)
    return bool(evidence.authored_tests) and not any(
        _mentions(function, _moving_bindings(evidence.trees[path], moving))
        for path, added in evidence.authored_tests.items()
        for function in _test_functions(evidence.trees[path])
        if function.name in added
    )


CHECKLISTS: Mapping[Role, tuple[tuple[str, Callable[[Evidence], bool]], ...]] = MappingProxyType(
    {
        "implementer": (
            ("the tests still pass", _tests_still_pass),
            ("behaviour is unchanged", _behaviour_is_unchanged),
            ("every call site is re-wired", _every_call_site_is_re_wired),
            ("no dead code remains", _no_dead_code_remains),
            ("no transitional shim remains", _no_transitional_shim_remains),
        ),
        "test-engineer": (
            (
                "characterization tests exist before any structural change",
                _characterization_tests_come_first,
            ),
            (
                "characterization tests pin behaviour through the public surface",
                _characterization_tests_pin_the_public_surface,
            ),
        ),
    }
)


# -- Reading Python without running it ------------------------------------------------------------


def _module_name(path: str) -> str:
    parts = PurePosixPath(path).with_suffix("").parts
    if parts[0] == SOURCE_ROOT:
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _defined_names(tree: ast.Module | None) -> frozenset[str]:
    """Top-level functions, classes and assigned names, dunders aside."""
    names: set[str] = set()
    for node in tree.body if tree else ():
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            names |= _assigned_names(node)
    return frozenset(name for name in names if not name.startswith("__"))


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _test_functions(tree: ast.Module | None) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function, method included, that pytest would collect by its name."""
    return [
        node
        for node in ast.walk(tree or ast.Module([], []))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")
    ]


def _test_names(tree: ast.Module | None) -> frozenset[str]:
    return frozenset(function.name for function in _test_functions(tree))


def _moving_bindings(tree: ast.Module, moving: frozenset[str]) -> frozenset[str]:
    """``moving`` plus the aliases the module's top-level imports bind it to."""
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    return moving | {a.asname for i in imports for a in i.names if a.asname and a.name in moving}


def _mentions(tree: ast.AST, names: frozenset[str]) -> bool:
    """Whether any import, name, attribute or string literal of the tree names one of ``names``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name in names for a in node.names):
            return True
        if isinstance(node, ast.Name) and node.id in names:
            return True
        if isinstance(node, ast.Attribute) and node.attr in names:
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if names & set(node.value.split(".")):  # a dotted target of a patch names it too
                return True
    return False


def _imported_names(tree: ast.Module | None) -> frozenset[str]:
    """The names top-level imports bind (``__future__`` aside)."""
    names: set[str] = set()
    for node in tree.body if tree else ():
        if isinstance(node, ast.Import):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            names |= {a.asname or a.name for a in node.names if a.name != "*"}
    return frozenset(names)


def _unused_imports(tree: ast.Module) -> frozenset[str]:
    loaded = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return _imported_names(tree) - loaded - _exported_names(tree)


def _exported_names(tree: ast.Module) -> frozenset[str]:
    """The strings of a top-level ``__all__``."""
    exported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and "__all__" in _assigned_names(node):
            if isinstance(node.value, ast.List | ast.Tuple):
                exported |= {
                    item.value
                    for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
    return frozenset(exported)


def _shims(source: ast.Module, arrived: frozenset[str]) -> frozenset[str]:
    """Moved names the source still offers without owning them."""
    shims: set[str] = set()
    for node in source.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in arrived and _only_calls(node, arrived):
                shims.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            if isinstance(node.value, ast.Name | ast.Attribute):
                shims |= _assigned_names(node) & arrived
    return (
        frozenset(shims) | (_unused_imports(source) & arrived) | (_exported_names(source) & arrived)
    )


def _leftover_copies(source: ast.Module, arrived: frozenset[str]) -> frozenset[str]:
    """Moved names the source still defines with a body of its own: the old code, left behind."""
    copies: set[str] = set()
    for node in source.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in arrived and not _only_calls(node, arrived):
                copies.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if node.name in arrived:
                copies.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            if not isinstance(node.value, ast.Name | ast.Attribute):
                copies |= _assigned_names(node) & arrived
    return frozenset(copies)


def _only_calls(function: ast.FunctionDef | ast.AsyncFunctionDef, callees: frozenset[str]) -> bool:
    """Whether the body is nothing but one call to one of ``callees``: a forwarder."""
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # the docstring
    if len(body) != 1 or not isinstance(body[0], ast.Return | ast.Expr):
        return False
    call = body[0].value
    return isinstance(call, ast.Call) and _last_name(call.func) in callees


def _last_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def _is_stale(
    path: str,
    tree: ast.Module,
    source_module: str,
    arrived: frozenset[str],
    kept: frozenset[str],
) -> bool:
    leaf = source_module.rsplit(".", 1)[-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _resolved_module(node, path) == source_module:
            if any(a.name in arrived or (a.name != "*" and a.name not in kept) for a in node.names):
                return True
        elif isinstance(node, ast.Attribute) and node.attr in arrived:
            owner = _dotted(node.value)
            if owner in (source_module, leaf) or owner.endswith(f".{leaf}"):
                return True
    return False


def _resolved_module(node: ast.ImportFrom, importer: str) -> str:
    if node.level == 0:
        return node.module or ""
    package = _module_name(importer).split(".")
    if not importer.endswith("__init__.py"):
        package = package[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


# -- Running things -------------------------------------------------------------------------------


def _pytest_passes(root: Path) -> bool:
    """Whether the repository's tests pass; ``PytestRunError`` when the run reached no verdict."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_FOREIGN_ENV_PREFIXES)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        # A base of its own: sessions graded at once would else share pytest's numbered root.
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        command += ["--basetemp", str(Path(scratch) / "basetemp")]
        try:
            run = subprocess.run(
                command, cwd=root, env=env, capture_output=True, timeout=TEST_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as error:
            ran = f"pytest did not finish within {TEST_TIMEOUT_SECONDS} s"
            raise PytestRunError(f"{ran}\n{_tail(error.output)}") from error
    if run.returncode not in (0, PYTEST_TESTS_FAILED):
        ran = f"pytest exited {run.returncode}"
        raise PytestRunError(f"{ran}\n{_tail(run.stdout + run.stderr)}")
    return run.returncode == 0


def _tail(output: bytes | None) -> str:
    lines = (output or b"").decode("utf-8", errors="replace").strip().splitlines()
    return "\n".join(lines[-ERROR_DETAIL_LINES:])


def _git(workspace: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    ).stdout
