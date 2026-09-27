"""The observation log has no private readers.

The registry's invariant: the set of code consumers of the log equals the set
of non-test modules importing `_observation_log.reader`. Two checks enforce it:

- the import check parses every candidate module and asserts its reader
  importers equal the `code` entries of `registry.CONSUMERS` -- a module
  calling `reader.read_rows` without being declared fails here;
- the filename check flags any `.py` file -- outside the owner package and a
  named allowlist -- whose source references the log filename literal
  (`reader.LOG_FILENAME`) directly, which is how a reader could bypass the
  owner package altogether.

Declared limit: an import built from a computed string (`importlib`,
`__import__`) is invisible to both checks; none exist today.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from hooks._observation_log import reader, registry
from hooks._observation_log.modes import Mode

REPO_ROOT = Path(__file__).resolve().parent.parent

OWNER_PACKAGE_PREFIX = "hooks/_observation_log/"

# Modules that name the log file without reading its rows, so they
# legitimately stay outside the owner reader. Filename check only: a module
# that imports the reader is a reader and must be declared regardless.
ALLOWLIST = frozenset(
    {
        "scripts/merge_driver_observations.py",  # whole-file merge with a dedup key
        "scripts/reconcile_ai_state.py",  # whole-file merge with a dedup key
        "scripts/_sidecar_init.py",  # writes the .gitattributes string
        "eval/src/praxion_evals/live/scenarios.py",  # hook-byproduct file list
        "scripts/check_gate_liveness.py",  # the liveness checker itself
    }
)

# Importer -> the declared consumer it belongs under. The cost collector's
# read pass was split out of its entry module for size (td-237); the registry
# declares the component under the entry module.
_COMPANION_MODULES = {
    "scripts/project_metrics/collectors/cost_collector_read.py": (
        "scripts/project_metrics/collectors/cost_collector.py"
    ),
}

# Test modules and pytest conftest files are test support, not consumers.
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]+|conftest)\.py$")
_EXCLUDED_DIR_MARKERS = (".venv/", "/plugins/cache/", "/.claude/worktrees/", "/node_modules/")


def _candidate_modules(root: Path) -> Iterator[tuple[str, Path]]:
    """(repo-relative path, path) of every non-test .py file outside the
    owner package and excluded dirs -- the walk both checks share."""
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(OWNER_PACKAGE_PREFIX) or _TEST_FILE_RE.search(rel):
            continue
        if any(marker in f"/{rel}" for marker in _EXCLUDED_DIR_MARKERS):
            continue
        yield rel, path


def _referencing_modules(root: Path) -> list[str]:
    """Candidate modules outside the allowlist whose source references the
    log filename literal."""
    return [
        rel
        for rel, path in _candidate_modules(root)
        if rel not in ALLOWLIST
        and reader.LOG_FILENAME in path.read_text(encoding="utf-8", errors="replace")
    ]


def _imports_reader(tree: ast.AST) -> bool:
    """Whether any import in `tree`, at any depth, binds the owner reader --
    bare, `hooks.`-prefixed, relative, or aliased."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[-2:] == ["_observation_log", "reader"]:
                return True
            if parts[-1] == "_observation_log" and any(a.name == "reader" for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[-2:] == ["_observation_log", "reader"] for a in node.names):
                return True
    return False


def _reader_importers(root: Path) -> tuple[frozenset[str], tuple[str, ...]]:
    """(candidate modules importing the reader, candidates that failed to
    parse). Only sources naming `_observation_log` are parsed -- every static
    import form spells it."""
    importers, unparseable = set(), []
    for rel, path in _candidate_modules(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "_observation_log" not in text:
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            unparseable.append(rel)
            continue
        if _imports_reader(tree):
            importers.add(rel)
    return frozenset(importers), tuple(unparseable)


def _declared_code_modules(consumers) -> frozenset[str]:
    """Module paths of the `code` consumers; the `#need` fragment drops
    because the registry is need-grain and this equality is file-grain."""
    return frozenset(c.name.partition("#")[0] for c in consumers if c.kind == "code")


def _consumer_equality_delta(importers, consumers, companions) -> tuple[list[str], list[str]]:
    """Pure: (undeclared importers, declared modules importing nothing), each
    sorted; both empty when the two sets are equal."""
    mapped = {companions.get(rel, rel) for rel in importers}
    declared = _declared_code_modules(consumers)
    return sorted(mapped - declared), sorted(declared - mapped)


def test_no_undeclared_module_references_the_log_filename_directly() -> None:
    findings = _referencing_modules(REPO_ROOT)

    assert findings == [], (
        "these modules reference the log filename outside the owner package "
        f"and its allowlist: {findings}"
    )


def test_canary_a_synthetic_undeclared_reader_is_caught(tmp_path: Path) -> None:
    """Gate-liveness canary: a module outside the owner package and the
    allowlist that references the log filename directly must be flagged.
    """
    rogue = tmp_path / "scripts" / "rogue_reader.py"
    rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_text(f'path = "{reader.LOG_FILENAME}"\n', encoding="utf-8")

    findings = _referencing_modules(tmp_path)

    assert findings == ["scripts/rogue_reader.py"]


def test_reader_importers_equal_declared_code_consumers() -> None:
    importers, unparseable = _reader_importers(REPO_ROOT)

    assert unparseable == (), f"candidate modules failed to parse: {unparseable}"
    assert set(_COMPANION_MODULES) <= importers, "a companion no longer imports the reader"
    assert set(_COMPANION_MODULES.values()) <= _declared_code_modules(registry.CONSUMERS), (
        "a companion maps to an undeclared module"
    )
    undeclared, unimported = _consumer_equality_delta(
        importers, registry.CONSUMERS, _COMPANION_MODULES
    )
    assert (undeclared, unimported) == ([], []), (
        f"reader importers not declared in registry.CONSUMERS: {undeclared}; "
        f"declared code consumers that do not import the reader: {unimported}"
    )


@pytest.mark.parametrize(
    "import_line",
    [
        "from _observation_log import reader",
        "from hooks._observation_log import reader as r",
        "from hooks._observation_log.reader import read_rows",
        "import _observation_log.reader",
        "def load():\n    from _observation_log import reader\n    return reader",
    ],
)
def test_canary_a_synthetic_undeclared_importer_is_caught(tmp_path: Path, import_line: str) -> None:
    """Gate-liveness canary: an undeclared module that imports the reader
    without naming the log filename must fail the equality check -- and slip
    past the filename check, which is the gap the import check closes.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("declared_reader.py", "rogue_reader.py"):
        (scripts / name).write_text(f"{import_line}\n", encoding="utf-8")
    declared = [registry.ConsumerSpec("scripts/declared_reader.py", "code", {}, Mode.STANDARD)]

    importers, unparseable = _reader_importers(tmp_path)

    assert unparseable == ()
    assert _consumer_equality_delta(importers, declared, {}) == (["scripts/rogue_reader.py"], [])
    assert _referencing_modules(tmp_path) == []
