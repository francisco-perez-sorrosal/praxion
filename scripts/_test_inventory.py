"""Test inventory: pockets, test-file naming conventions and collection scope.

A *pocket* is a directory holding one ecosystem's runner configuration (a
`pyproject.toml`, a `package.json`, a `Cargo.toml`, ...). Every changed path
belongs to the pocket with the longest matching root, and every emitted runner
command runs from that pocket's root with its runner prefix (`uv run`,
`pnpm exec`, ...) -- the detection table `/test` used to carry lives here now.

*Collection scope* answers "would any runner actually collect this test file?"
Two sources, and a file is collected when either covers it:

- the pocket's pytest configuration (`testpaths` x `python_files`), read with
  `tomllib`/`configparser` -- exact for pytest;
- a path or glob literal a CI workflow passes to a runner (`pytest fitness/`,
  `bash tests/foo.sh`) -- a textual heuristic, not a YAML parse.

Shared by `resolve_test_scope.py` (it never selects a test no runner collects)
and the gate-liveness uncollected-test check.

The segment-aware glob engine lives here as the lowest shared layer. `fnmatch`
is unusable for paths (its `*` crosses `/`) and `PurePath.full_match` is 3.13+,
so globs compile to regexes segment by segment: `**` as a whole segment spans
zero or more segments (as the final segment, everything below); `*` and `?`
never cross `/`; an unterminated `[` is a literal; a wildcard-free pattern
matches exactly that path.

Stdlib-only: it runs under a bare `python3` (gate-liveness GL05).
"""

from __future__ import annotations

import configparser
import functools
import json
import os
import re
import shlex
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# --- Glob engine ---------------------------------------------------------------


def _segment_regex(segment: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            end = index + 1
            if end < len(segment) and segment[end] in "!^":
                end += 1
            if end < len(segment) and segment[end] == "]":
                end += 1
            while end < len(segment) and segment[end] != "]":
                end += 1
            if end >= len(segment):
                out.append(re.escape("["))
                index += 1
                continue
            # Backslashes and a stray `[` are literal inside a glob class; escaped so
            # the class never becomes an invalid (or different) regex.
            body = segment[index + 1 : end].replace("\\", "\\\\").replace("[", "\\[")
            out.append("[" + ("^" + body[1:] if body[:1] in ("!", "^") else body) + "]")
            index = end + 1
        else:
            out.append(re.escape(char))
            index += 1
    return "".join(out)


@functools.lru_cache(maxsize=4096)
def glob_body(pattern: str) -> str:
    """The unanchored regex body for a repo-relative glob."""
    segments = pattern.strip("/").split("/")
    parts: list[str] = []
    for position, segment in enumerate(segments):
        last = position == len(segments) - 1
        if segment == "**":
            parts.append(".+" if last else "(?:[^/]+/)*")
            continue
        parts.append(_segment_regex(segment))
        if not last:
            parts.append("/")
    return "".join(parts)


@functools.lru_cache(maxsize=4096)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """A full-match regex for a repo-relative glob (an unreadable one matches literally)."""
    try:
        return re.compile(glob_body(pattern) + r"\Z")
    except re.error:
        return re.compile(re.escape(pattern) + r"\Z")


def matches_glob(path: str, pattern: str) -> bool:
    return glob_to_regex(pattern).match(path) is not None


def has_wildcard(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def join_rel(root: str, rel: str) -> str:
    """Join a pocket root and a pocket-relative path into a repo-relative one."""
    rel = rel.strip("/").removeprefix("./")
    if root in ("", "."):
        return rel
    return f"{root}/{rel}" if rel and rel != "." else root


def under(path: str, root: str) -> bool:
    return root in ("", ".") or path == root or path.startswith(root + "/")


# --- Naming conventions --------------------------------------------------------

_JS_EXTENSIONS = r"(?:ts|tsx|js|jsx|mjs|cjs|mts|cts)"
_TEST_NAME = {
    "python": re.compile(r"(?:test_[^/]*|[^/]*_test)\.py\Z"),
    "typescript": re.compile(rf"[^/]*\.(?:test|spec)\.{_JS_EXTENSIONS}\Z"),
    "rust": re.compile(r"(?:^|.*/)tests/(?:[^/]+/)*[^/]+\.rs\Z"),
    "go": re.compile(r"[^/]*_test\.go\Z"),
    "jvm": re.compile(r"[^/]*(?:Test|Tests|IT)\.(?:java|kt)\Z"),
}
_TEST_NAME["monorepo"] = _TEST_NAME["typescript"]
ECOSYSTEMS = tuple(_TEST_NAME)


def is_test_file(path: str, ecosystem: str) -> bool:
    """Does `path` follow `ecosystem`'s test-file naming convention?"""
    rule = _TEST_NAME.get(ecosystem)
    if rule is None:
        return False
    target = path if ecosystem == "rust" else path.rsplit("/", 1)[-1]
    return rule.match(target) is not None


def is_any_test_file(path: str) -> bool:
    return any(is_test_file(path, ecosystem) for ecosystem in ECOSYSTEMS)


# --- Collection scope ----------------------------------------------------------


@dataclass(frozen=True)
class CollectionScope:
    """Repo-relative globs; a path is in scope when any of them matches."""

    patterns: tuple[str, ...]

    def covers(self, path: str) -> bool:
        return any(matches_glob(path, pattern) for pattern in self.patterns)


def is_collected(path: str, scopes: Iterable[CollectionScope]) -> bool:
    return any(scope.covers(path) for scope in scopes)


PYTEST_DEFAULT_FILES = ("test_*.py", "*_test.py")
_INI_SECTIONS = (("pytest.ini", "pytest"), ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest"))


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return value.split()
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def read_pytest_options(pocket_dir: Path) -> dict[str, object] | None:
    """The pocket's pytest options, `{}` for config without a pytest section,
    or None when the directory holds no Python config at all."""
    pyproject = pocket_dir / "pyproject.toml"
    if pyproject.is_file():
        options = _pyproject_pytest_options(pyproject)
        if options:
            return options
    for name, section in _INI_SECTIONS:
        ini = pocket_dir / name
        if not ini.is_file():
            continue
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(ini, encoding="utf-8")
        except configparser.Error:
            continue
        if parser.has_section(section):
            return dict(parser.items(section))
    return {} if pyproject.is_file() else None


def _pyproject_pytest_options(pyproject: Path) -> dict[str, object]:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return options if isinstance(options, dict) else {}


def scope_from_options(options: dict[str, object] | None, pocket_root: str) -> CollectionScope:
    """`testpaths` x `python_files`, rooted at the pocket. None -> covers nothing."""
    if options is None:
        return CollectionScope(())
    testpaths = _as_list(options.get("testpaths")) or ["."]
    python_files = _as_list(options.get("python_files")) or list(PYTEST_DEFAULT_FILES)
    patterns: list[str] = []
    for testpath in testpaths:
        base = join_rel(pocket_root, testpath)
        if testpath.endswith(".py"):
            patterns.append(base)
            continue
        prefix = f"{base}/**" if base not in ("", ".") else "**"
        patterns.extend(f"{prefix}/{name}" for name in python_files)
    return CollectionScope(tuple(patterns))


def pytest_collection_scope(pyproject: Path, pocket_root: str = ".") -> CollectionScope:
    """The collection scope a `pyproject.toml` declares; an absent file covers nothing."""
    if not pyproject.is_file():
        return CollectionScope(())
    return scope_from_options(_pyproject_pytest_options(pyproject), pocket_root)


_RUNNER_WORDS = frozenset(
    {"pytest", "py.test", "bash", "sh", "vitest", "jest", "mocha", "bats", "tox", "nox"}
)
_COMMAND_SEPARATORS = re.compile(r"&&|\|\||;|\|")


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return segment.split()


def _workflow_patterns(line: str) -> list[str]:
    patterns: list[str] = []
    for segment in _COMMAND_SEPARATORS.split(line):
        tokens = [token.strip("()'\"") for token in _tokens(segment)]
        if not any(token.rsplit("/", 1)[-1] in _RUNNER_WORDS for token in tokens):
            continue
        for token in tokens:
            if "/" not in token or token.startswith(("-", "$", "http")) or "://" in token:
                continue
            path = token.removeprefix("./")
            if path.endswith("/"):
                patterns.append(path.rstrip("/") + "/**")
            elif has_wildcard(path):
                patterns.append(path)
            else:
                patterns.extend((path, f"{path}/**"))
    return patterns


def workflow_collection_scope(workflows_dir: Path) -> CollectionScope:
    """Path and glob literals CI workflows hand to a test runner."""
    if not workflows_dir.is_dir():
        return CollectionScope(())
    patterns: list[str] = []
    for workflow in sorted(workflows_dir.glob("*.y*ml")):
        try:
            text = workflow.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            patterns.extend(_workflow_patterns(line))
    return CollectionScope(tuple(dict.fromkeys(patterns)))


# --- Pockets -------------------------------------------------------------------

# Checked in order; the first ecosystem whose marker sits in a directory wins, so
# a directory is one pocket (a Python project with a tooling `package.json` stays
# Python).
_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("monorepo", ("nx.json", "turbo.json", "pants.toml")),
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini", "tox.ini")),
    ("typescript", ("package.json",)),
    ("rust", ("Cargo.toml",)),
    ("go", ("go.mod",)),
    ("jvm", ("pom.xml", "build.gradle", "build.gradle.kts")),
)

# Runner configuration and lockfiles: a change to one invalidates the pocket's
# selection, because it can change what runs or how.
POCKET_CONFIG_FILES: dict[str, frozenset[str]] = {
    "python": frozenset(
        {
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "pytest.ini",
            "tox.ini",
            "uv.lock",
            "poetry.lock",
            "pixi.toml",
            "pixi.lock",
            "requirements.txt",
        }
    ),
    "typescript": frozenset(
        {
            "package.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "package-lock.json",
            "tsconfig.json",
            "vitest.config.ts",
            "vitest.config.js",
            "vitest.config.mts",
            "jest.config.js",
            "jest.config.ts",
            "jest.config.cjs",
            "jest.config.mjs",
        }
    ),
    "rust": frozenset({"Cargo.toml", "Cargo.lock"}),
    "go": frozenset({"go.mod", "go.sum"}),
    "jvm": frozenset(
        {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
    ),
    "monorepo": frozenset(
        {"nx.json", "turbo.json", "pants.toml", "package.json", "pnpm-lock.yaml", "yarn.lock"}
    ),
}

_SKIP_DIRS = frozenset({"node_modules", "__pycache__", "venv", "target", "dist", "build"})


@dataclass(frozen=True)
class Pocket:
    root: str
    ecosystem: str
    framework: str
    runner_prefix: tuple[str, ...]
    collection: CollectionScope
    xdist: bool = False


def walk_files(root: Path) -> Iterable[str]:
    """Repo-relative file paths under `root`, skipping dot-dirs and build output."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for name in filenames:
            yield name if rel_dir == "." else f"{rel_dir}/{name}"


def discover_pockets(root: Path, files: Iterable[str] | None = None) -> tuple[Pocket, ...]:
    """Every pocket under `root`, from ecosystem markers among `files`
    (default: a filesystem walk skipping dot-dirs and build output)."""
    names_by_dir: dict[str, set[str]] = {}
    for path in walk_files(root) if files is None else files:
        directory, _, name = path.rpartition("/")
        names_by_dir.setdefault(directory or ".", set()).add(name)
    pockets = []
    for directory in sorted(names_by_dir):
        ecosystem = _ecosystem_of(names_by_dir[directory])
        if ecosystem is not None:
            pockets.append(_build_pocket(root, directory, ecosystem))
    return tuple(pockets)


def _ecosystem_of(names: set[str]) -> str | None:
    for ecosystem, markers in _MARKERS:
        if names.intersection(markers):
            return ecosystem
    return None


def _build_pocket(repo_root: Path, root: str, ecosystem: str) -> Pocket:
    pocket_dir = repo_root / root
    if ecosystem != "python":
        framework = _framework(pocket_dir, ecosystem)
        return Pocket(
            root,
            ecosystem,
            framework,
            _runner_prefix(pocket_dir, ecosystem),
            CollectionScope((join_rel(root, "**"),)),
        )
    options = read_pytest_options(pocket_dir)
    addopts = _as_list((options or {}).get("addopts"))
    return Pocket(
        root,
        "python",
        "pytest",
        _runner_prefix(pocket_dir, "python"),
        scope_from_options(options, root),
        xdist=any(_is_xdist_flag(opt) for opt in addopts),
    )


def _is_xdist_flag(option: str) -> bool:
    return option in ("-n", "--numprocesses") or option.startswith(("-n", "--numprocesses="))


def _file_mentions(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _runner_prefix(pocket_dir: Path, ecosystem: str) -> tuple[str, ...]:
    """Run through the project's environment manager, never a bare framework."""
    pyproject = pocket_dir / "pyproject.toml"
    if ecosystem == "python":
        if (pocket_dir / "pixi.toml").is_file() or _file_mentions(pyproject, "[tool.pixi"):
            return ("pixi", "run")
        if (pocket_dir / "uv.lock").is_file() or _file_mentions(pyproject, "[tool.uv"):
            return ("uv", "run")
        if (pocket_dir / "poetry.lock").is_file() or _file_mentions(pyproject, "[tool.poetry"):
            return ("poetry", "run")
        return ("python", "-m")
    if ecosystem in ("typescript", "monorepo"):
        if (pocket_dir / "pnpm-lock.yaml").is_file():
            return ("pnpm", "exec")
        if (pocket_dir / "yarn.lock").is_file():
            return ("yarn",)
        return ("npx",)
    return ()


def _framework(pocket_dir: Path, ecosystem: str) -> str:
    if ecosystem == "typescript":
        return _js_framework(pocket_dir / "package.json")
    if ecosystem == "jvm":
        return "maven" if (pocket_dir / "pom.xml").is_file() else "gradle"
    if ecosystem == "monorepo":
        for name, framework in (
            ("nx.json", "nx"),
            ("turbo.json", "turbo"),
            ("pants.toml", "pants"),
        ):
            if (pocket_dir / name).is_file():
                return framework
    return {"rust": "cargo", "go": "go"}.get(ecosystem, "unknown")


def _js_framework(package_json: Path) -> str:
    try:
        manifest = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    declared: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        section = manifest.get(key)
        if isinstance(section, dict):
            declared.update(section)
    for framework in ("vitest", "jest"):
        if framework in declared:
            return framework
    return "unknown"


_FULL_SUITE: dict[str, tuple[str, ...]] = {
    "pytest": ("pytest",),
    "vitest": ("vitest", "run"),
    "jest": ("jest",),
    "cargo": ("cargo", "test"),
    "go": ("go", "test", "./..."),
    "maven": ("mvn", "test"),
    "gradle": ("gradle", "test"),
    "nx": ("nx", "run-many", "-t", "test"),
    "turbo": ("turbo", "run", "test"),
    "pants": ("pants", "test", "::"),
}


def full_suite_argv(pocket: Pocket) -> tuple[str, ...]:
    """The runner-prefixed command for the pocket's whole suite."""
    command = _FULL_SUITE.get(pocket.framework)
    if command is not None:
        return (*pocket.runner_prefix, *command)
    # No detectable framework: fall back to the package manager's own test script.
    manager = pocket.runner_prefix[:1]
    return (*(manager if manager in (("pnpm",), ("yarn",)) else ("npm",)), "test")


def pocket_of(path: str, pockets: Iterable[Pocket]) -> Pocket | None:
    """The pocket with the longest root containing `path`."""
    containing = [pocket for pocket in pockets if under(path, pocket.root)]
    return max(containing, key=lambda pocket: _root_depth(pocket.root), default=None)


def _root_depth(root: str) -> int:
    return -1 if root in ("", ".") else len(root)
