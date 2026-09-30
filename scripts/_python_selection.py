"""Python test selection derived from the code itself.

Nodes are repo-relative files; an edge "A depends on B" comes from one of four
sources, listed in attribution order:

1. **layout** -- `dir/test_foo.py` / `dir/foo_test.py` depend on `foo.py`, the
   nearest one by longest common directory suffix (ties select all), and every
   test under a `conftest.py`'s directory depends on that `conftest.py`;
2. **import** -- `ast.Import`/`ast.ImportFrom` (relative too) and
   `importlib.import_module("<literal>")`, resolved sibling-first, then from
   the pocket root / pytest `pythonpath` / `src`, then by flat stem across the
   pocket (an ambiguous stem connects to every match);
3. **path-literal** -- any string constant in any pocket module, in one of
   five classes. With a `/`: a path suffix (of the file or of one of its
   directories), or a glob when it has wildcards. Without a `/`: an exact
   basename, or a basename pattern (`*.md`) matching the basename of a changed
   path at any depth. A wildcard literal with no letter or digit outside its
   wildcards (`*`, `.*`, `*.*`) names no file. Suffixes, globs and exact
   basenames are *named* edges that hold at every hop; a basename pattern
   holds only as the first hop out of a changed path, so it never connects
   through an intermediate module;
4. **declared** -- `tests/declared-deps.toml` entries.

A changed path selects every test that reaches it through reverse
reachability over all four sources -- a union, never first-match, because
stopping at the first source to connect drops the tests of modules that
import the changed one. The order above only decides the `via` attribution:
the kind of the first hop out of the changed path, along the test's shortest
path to it.

Data files narrow, code widens: a changed file reached only by a basename
pattern selects its readers, but stands in for the full suite only when it is
not source code. A pattern is a guess about which files a module reads, so a
source file it happens to match is still unaccounted for and widens; its
readers run within that full run.

Dynamic imports beyond the literal `import_module` form are invisible here;
the resolver widens unmapped paths and the full suite backstops the rest.
Stdlib-only: it runs under a bare `python3` (gate-liveness GL05).
"""

from __future__ import annotations

import ast
import functools
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _declared_deps import DeclaredDeps, dep_entries_for  # noqa: E402
from _test_inventory import (  # noqa: E402
    glob_body,
    has_wildcard,
    is_any_test_file,
    is_source_code,
    join_rel,
    matches_glob,
    read_pytest_options,
    under,
    walk_files,
)

SERIAL_BELOW_TESTS = 20
VIA_ORDER = ("layout", "import", "path-literal", "declared")
_VIA_RANK = {"self": -1, **{via: rank for rank, via in enumerate(VIA_ORDER)}}
_PATTERN_RANK = _VIA_RANK["path-literal"]
_TEST_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+test_", re.MULTILINE)
_MAX_LITERAL = 300


@dataclass(frozen=True)
class SelectedTest:
    path: str
    via: str
    because: str


@dataclass(frozen=True)
class Derivation:
    """Selected tests, plus the changed paths they account for.

    A path counts when it reached a test, except a source-code path that only
    its own basename-pattern readers reached: that one still widens.
    """

    tests: tuple[SelectedTest, ...]
    mapped: frozenset[str]


def select(root: Path, changed: Iterable[str], deps: DeclaredDeps) -> tuple[SelectedTest, ...]:
    """The tests a change selects, over every file under `root`."""
    return derive(root, changed, deps).tests


def derive(
    root: Path,
    changed: Iterable[str],
    deps: DeclaredDeps,
    *,
    files: Sequence[str] | None = None,
    pocket_roots: Sequence[str] = (".",),
    is_runnable: Callable[[str], bool] = lambda _path: True,
) -> Derivation:
    """Every runnable test reachable from a changed path, attributed."""
    changed_paths = sorted(set(changed))
    universe = tuple(walk_files(root)) if files is None else tuple(files)
    graph = _Graph(root, universe, changed_paths, deps, pocket_roots)
    best: dict[str, tuple[int, SelectedTest]] = {}
    mapped: set[str] = set()
    for path in changed_paths:
        reached = _reach(graph, path, is_runnable)
        for test, via in reached.items():
            rank = _VIA_RANK[via]
            if test not in best or rank < best[test][0]:
                best[test] = (rank, SelectedTest(test, via, path))
        if reached and _accounted_for(graph, path, is_runnable):
            mapped.add(path)
    tests = tuple(best[test][1] for test in sorted(best))
    return Derivation(tests, frozenset(mapped))


def _accounted_for(graph: _Graph, path: str, is_runnable: Callable[[str], bool]) -> bool:
    """A path that reached a test stands in for the full suite, unless only a pattern reached it."""
    if not is_source_code(path) or not graph.pattern_readers(path):
        return True
    return bool(_reach(graph, path, is_runnable, patterns=False))


def _reach(
    graph: _Graph, start: str, is_runnable: Callable[[str], bool], *, patterns: bool = True
) -> dict[str, str]:
    """Tests reaching `start`, each tagged with the kind of its first hop out of `start`.

    Level-order search: a test is attributed along its shortest path, so a
    direct edge is reported as itself; among equally short paths the
    higher-priority first hop wins. With `patterns`, the first hop also
    includes the modules whose basename pattern matches `start`; after it the
    search follows named edges only.
    """
    found: dict[str, str] = {}
    if is_any_test_file(start) and is_runnable(start):
        found[start] = "self"
    frontier: dict[str, int] = {}
    for rank, via in enumerate(VIA_ORDER):
        for node in graph.dependents(start, via):
            frontier[node] = min(frontier.get(node, rank), rank)
    if patterns:
        for node in graph.pattern_readers(start):
            frontier[node] = min(frontier.get(node, _PATTERN_RANK), _PATTERN_RANK)
    visited = {start, *frontier}
    while frontier:
        following: dict[str, int] = {}
        for node, rank in frontier.items():
            if is_any_test_file(node) and is_runnable(node):
                found.setdefault(node, VIA_ORDER[rank])
            for kind in VIA_ORDER:
                for dependent in graph.dependents(node, kind):
                    if dependent not in visited:
                        following[dependent] = min(following.get(dependent, rank), rank)
        visited.update(following)
        frontier = following
    return found


def count_tests(source: str) -> int:
    """`def test_` / `async def test_` occurrences -- the serial-threshold estimate."""
    return len(_TEST_DEF.findall(source))


def needs_serial(test_count: int, xdist_enabled: bool) -> bool:
    """Tiny selections skip xdist worker start-up; only meaningful when xdist is on."""
    return xdist_enabled and test_count <= SERIAL_BELOW_TESTS


def estimate_tests(root: Path, paths: Iterable[str]) -> int:
    total = 0
    for path in paths:
        try:
            total += count_tests((root / path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return total


# --- The graph -------------------------------------------------------------------


class _Graph:
    """Reverse edges ("who depends on this node?"), computed on demand per kind."""

    def __init__(
        self,
        root: Path,
        files: Sequence[str],
        changed: Sequence[str],
        deps: DeclaredDeps,
        pocket_roots: Sequence[str],
    ) -> None:
        self._deps = deps
        known = set(files) | set(changed)
        self._test_files = tuple(sorted(path for path in known if is_any_test_file(path)))
        self._py_tests_by_stem = _tests_by_stem(self._test_files)
        modules = sorted(path for path in known if path.endswith(".py"))
        resolver = _ImportResolver(root, known, pocket_roots)
        self._importers: dict[str, set[str]] = {}
        self._literals = _LiteralIndex()
        for module in modules:
            tree = _parse(root / module)
            if tree is None:
                continue
            for target in resolver.resolve_all(module, tree):
                self._importers.setdefault(target, set()).add(module)
            self._literals.add_module(module, tree)
        self.dependents = functools.lru_cache(maxsize=None)(self._dependents)

    def _dependents(self, node: str, via: str) -> tuple[str, ...]:
        if via == "layout":
            found = self._layout(node)
        elif via == "import":
            found = self._importers.get(node, set())
        elif via == "path-literal":
            found = self._literals.modules_matching(node)
        else:
            found = self._declared(node)
        return tuple(sorted(dependent for dependent in found if dependent != node))

    def pattern_readers(self, node: str) -> tuple[str, ...]:
        """Modules holding a slash-less wildcard literal that matches `node`'s basename."""
        return tuple(sorted(self._literals.pattern_readers(node)))

    def _layout(self, node: str) -> set[str]:
        directory, _, name = node.rpartition("/")
        if name == "conftest.py":
            return {
                test for test in self._test_files if test.endswith(".py") and under(test, directory)
            }
        if not name.endswith(".py") or is_any_test_file(node):
            return set()
        stem = directory.rpartition("/")[2] if name == "__init__.py" else name[: -len(".py")]
        candidates = self._py_tests_by_stem.get(stem, ())
        if not candidates:
            return set()
        scores = {test: _common_dir_suffix(node, test) for test in candidates}
        best = max(scores.values())
        return {test for test, score in scores.items() if score == best}

    def _declared(self, node: str) -> set[str]:
        found: set[str] = set()
        for entry in dep_entries_for(self._deps, node):
            for pattern in entry.tests:
                found.update(test for test in self._test_files if matches_glob(test, pattern))
        return found


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None


def _tests_by_stem(test_files: Iterable[str]) -> dict[str, tuple[str, ...]]:
    by_stem: dict[str, list[str]] = {}
    for test in test_files:
        name = test.rpartition("/")[2]
        if not name.endswith(".py"):
            continue
        stem = name[: -len(".py")]
        stem = stem[len("test_") :] if stem.startswith("test_") else stem[: -len("_test")]
        by_stem.setdefault(stem, []).append(test)
    return {stem: tuple(tests) for stem, tests in by_stem.items()}


def _common_dir_suffix(first: str, second: str) -> int:
    left = first.split("/")[:-1]
    right = second.split("/")[:-1]
    count = 0
    while count < min(len(left), len(right)) and left[-1 - count] == right[-1 - count]:
        count += 1
    return count


# --- Import edges ------------------------------------------------------------------


class _ImportResolver:
    """Maps a module's import statements to the pocket files they load."""

    def __init__(self, root: Path, known: set[str], pocket_roots: Sequence[str]) -> None:
        self._known = known
        self._pockets = tuple(sorted(pocket_roots, key=lambda r: -1 if r in ("", ".") else len(r)))
        self._bases = {pocket: _import_bases(root, pocket, known) for pocket in pocket_roots}
        self._by_stem: dict[str, list[str]] = {}
        for path in known:
            if path.endswith(".py"):
                self._by_stem.setdefault(_module_stem(path), []).append(path)

    def resolve_all(self, module: str, tree: ast.Module) -> set[str]:
        targets: set[str] = set()
        for name, level, names in _import_specs(tree):
            targets |= self._resolve(module, name, level, names)
        targets.discard(module)
        return targets

    def _resolve(self, module: str, name: str, level: int, names: tuple[str, ...]) -> set[str]:
        if level:
            base = _parent_dir(module, level)
            prefix = f"{name}." if name else ""
            found = self._files_at(base, name) if name else self._files_at(base, "__init__")
            for child in names:
                found |= self._files_at(base, prefix + child)
            return found
        found = self._resolve_dotted(module, name)
        for child in names:
            found |= self._resolve_dotted(module, f"{name}.{child}")
        return found

    def _resolve_dotted(self, module: str, dotted: str) -> set[str]:
        sibling_dir = module.rpartition("/")[0]
        pocket = self._pocket_of(module)
        for bases in ((sibling_dir,), self._bases.get(pocket, ())):
            found: set[str] = set()
            for base in bases:
                found |= self._files_at(base, dotted)
            if found:
                return found
        return self._flat_stem(pocket, dotted)

    def _files_at(self, base: str, dotted: str) -> set[str]:
        rel = dotted.replace(".", "/")
        candidates = [join_rel(base, f"{rel}.py"), join_rel(base, f"{rel}/__init__.py")]
        parts = rel.split("/")
        candidates += [
            join_rel(base, "/".join(parts[:i]) + "/__init__.py") for i in range(1, len(parts))
        ]
        return {path for path in candidates if path in self._known}

    def _flat_stem(self, pocket: str, dotted: str) -> set[str]:
        rel = dotted.replace(".", "/")
        suffixes = (f"{rel}.py", f"{rel}/__init__.py")
        return {
            path
            for path in self._by_stem.get(dotted.rpartition(".")[2], ())
            if under(path, pocket)
            and (path in suffixes or path.endswith(tuple("/" + s for s in suffixes)))
        }

    def _pocket_of(self, path: str) -> str:
        for pocket in reversed(self._pockets):
            if under(path, pocket):
                return pocket
        return "."


def _import_bases(root: Path, pocket: str, known: set[str]) -> tuple[str, ...]:
    options = read_pytest_options(root / pocket) or {}
    raw = options.get("pythonpath", [])
    extra = raw.split() if isinstance(raw, str) else [str(entry) for entry in raw]
    bases = [join_rel(pocket, "."), *(join_rel(pocket, entry) for entry in extra)]
    src = join_rel(pocket, "src")
    if any(path.startswith(src + "/") for path in known):
        bases.append(src)
    return tuple(dict.fromkeys(bases))


def _module_stem(path: str) -> str:
    directory, _, name = path.rpartition("/")
    return directory.rpartition("/")[2] if name == "__init__.py" else name[: -len(".py")]


def _parent_dir(module: str, level: int) -> str:
    parts = module.split("/")[:-1]
    return "/".join(parts[: len(parts) - (level - 1)]) if level > 1 else "/".join(parts)


def _import_specs(tree: ast.Module) -> Iterable[tuple[str, int, tuple[str, ...]]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0, ()
        elif isinstance(node, ast.ImportFrom):
            names = tuple(alias.name for alias in node.names if alias.name != "*")
            yield node.module or "", node.level, names
        elif isinstance(node, ast.Call) and _is_import_module_call(node):
            target = node.args[0].value  # type: ignore[attr-defined]
            if not target.startswith("."):
                yield target, 0, ()


def _is_import_module_call(node: ast.Call) -> bool:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return (
        name in ("import_module", "__import__")
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )


# --- Path-literal edges ------------------------------------------------------------


_LiteralClass = Literal["ignored", "exact-basename", "basename-pattern", "path-glob", "path-suffix"]
_BRACKET_CLASS = re.compile(r"\[[^\]]*\]")


def _literal_class(literal: str) -> _LiteralClass:
    """The one class of a normalized literal (leading `./` and `/` already removed).

    A slash-less wildcard literal needs a letter or digit outside its wildcards
    to name a file, so `*`, `.*` and `*.*` name none; a bracket class counts as
    wildcard, so `[a-z]*` names none either.
    """
    if literal in ("", "."):
        return "ignored"
    if "/" in literal:
        return "path-glob" if has_wildcard(literal) else "path-suffix"
    if not has_wildcard(literal):
        return "exact-basename"
    outside_wildcards = _BRACKET_CLASS.sub("", literal)
    return "basename-pattern" if any(ch.isalnum() for ch in outside_wildcards) else "ignored"


class _LiteralIndex:
    """String constants, indexed so a node looks up only candidate literals."""

    def __init__(self) -> None:
        self._by_basename: dict[str, set[str]] = {}
        self._by_last_segment: dict[str, list[tuple[str, str]]] = {}
        self._globs: list[tuple[re.Pattern[str], str]] = []
        self._basename_patterns: list[tuple[re.Pattern[str], str]] = []

    def add_module(self, module: str, tree: ast.Module) -> None:
        for literal in _string_constants(tree):
            normalized = literal.removeprefix("./").strip("/")
            kind = _literal_class(normalized)
            if kind == "exact-basename":
                self._by_basename.setdefault(normalized, set()).add(module)
            elif kind == "basename-pattern":
                _append_compiled(self._basename_patterns, "", normalized, module)
            elif kind == "path-glob":
                _append_compiled(self._globs, r"(?:.*/)?", normalized, module)
            elif kind == "path-suffix":
                last = normalized.rpartition("/")[2]
                self._by_last_segment.setdefault(last, []).append((normalized, module))

    def modules_matching(self, node: str) -> set[str]:
        """Holders of a *named* literal: exact basename, path suffix or path glob."""
        found = set(self._by_basename.get(node.rpartition("/")[2], ()))
        segments = node.split("/")
        for end in range(len(segments), 0, -1):  # the file itself, then each ancestor directory
            prefix = "/".join(segments[:end])
            for literal, module in self._by_last_segment.get(segments[end - 1], ()):
                if prefix == literal or prefix.endswith("/" + literal):
                    found.add(module)
        found.update(module for pattern, module in self._globs if pattern.match(node))
        return found

    def pattern_readers(self, node: str) -> set[str]:
        """Holders of a basename pattern that matches `node`'s basename, other than `node`."""
        name = node.rpartition("/")[2]
        return {
            module
            for pattern, module in self._basename_patterns
            if module != node and pattern.match(name)
        }


def _append_compiled(
    into: list[tuple[re.Pattern[str], str]], prefix: str, literal: str, module: str
) -> None:
    try:
        pattern = re.compile(prefix + glob_body(literal) + r"\Z")
    except re.error:  # a string no glob engine could read is not a glob
        return
    into.append((pattern, module))


def _string_constants(tree: ast.Module) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if len(value) <= _MAX_LITERAL and not any(ch.isspace() for ch in value):
                yield value
