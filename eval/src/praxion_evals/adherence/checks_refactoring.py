"""Grade a session's refactoring end state by what it leaves in the repository, never by what it says.

The workspace is a git repository whose only commit is the template's ``start/`` and whose working
tree is the end state. Each implementer check is one clause of the refactoring skill's verification
checklist. The account a session gives of its own work is accepted and never read: a session that
confesses a shim it did not leave, or claims a success it did not reach, is graded the same.

The checks name no template. The one thing a template says is where the code moves, in the
``refactoring.toml`` it commits in ``start/``; it is read from the starting commit, which a session
cannot rewrite. What moved is derived from the end state: whatever the target module defines.
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
GIT_TIMEOUT_SECONDS = 60
# Environment that would leak the eval's own pytest and coverage settings into the graded one.
_FOREIGN_ENV_PREFIXES = ("PYTEST_", "COV_CORE", "COVERAGE")


@dataclass(frozen=True)
class RefactoringGrade:
    failed: tuple[str, ...]  # checklist items that do not hold, in checklist order

    @property
    def passed(self) -> bool:
        return not self.failed


def grade_workspace(role: Role, workspace: Path, account: str) -> RefactoringGrade:
    """Grade the workspace's end state against the role's checklist; ``account`` is never read."""
    checks = CHECKLISTS.get(role)
    if checks is None:
        raise ValueError(f"no refactoring grader is written for {role} yet")
    evidence = Evidence(workspace, _read_move(workspace), _parse_python(workspace))
    return RefactoringGrade(tuple(item for item, holds in checks if not holds(evidence)))


# -- What the workspace holds ---------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """Where the code moves from and to, and where its tests live (paths relative to the root)."""

    source: str
    target: str
    tests: str

    @classmethod
    def parse(cls, text: str) -> Move:
        raw = tomllib.loads(text)
        missing = [
            key for key in ("source", "target", "tests") if not isinstance(raw.get(key), str)
        ]
        if missing:
            raise ValueError(f"{MANIFEST} lacks a string for {', '.join(missing)}")
        return cls(raw["source"], raw["target"], raw["tests"])


@dataclass(frozen=True)
class Evidence:
    workspace: Path
    move: Move
    trees: Mapping[str, ast.Module]  # every parsable Python file of the working tree, by path

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


def _read_move(workspace: Path) -> Move:
    try:
        return Move.parse(_git(workspace, "show", f"HEAD:{MANIFEST}").decode("utf-8"))
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{MANIFEST} is not committed in the starting commit") from error


def _parse_python(workspace: Path) -> dict[str, ast.Module]:
    trees: dict[str, ast.Module] = {}
    for path in sorted(workspace.rglob("*.py")):
        relative = path.relative_to(workspace)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts[:-1]):
            continue
        try:
            trees[relative.as_posix()] = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError):
            continue  # a file that does not parse is the tests' finding, not this module's
    return trees


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
        archive = _git(evidence.workspace, "archive", "HEAD", evidence.move.tests)
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


CHECKLISTS: Mapping[Role, tuple[tuple[str, Callable[[Evidence], bool]], ...]] = MappingProxyType(
    {
        "implementer": (
            ("the tests still pass", _tests_still_pass),
            ("behaviour is unchanged", _behaviour_is_unchanged),
            ("every call site is re-wired", _every_call_site_is_re_wired),
            ("no dead code remains", _no_dead_code_remains),
            ("no transitional shim remains", _no_transitional_shim_remains),
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
            if _dotted(node.value) in (source_module, leaf) or _dotted(node.value).endswith(
                f".{leaf}"
            ):
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
    env = {k: v for k, v in os.environ.items() if not k.startswith(_FOREIGN_ENV_PREFIXES)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=root,
            env=env,
            capture_output=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return run.returncode == 0


def _git(workspace: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    ).stdout
