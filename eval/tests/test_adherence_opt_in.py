"""The adherence eval stays operator-invoked: only its own console entry reaches it.

Every adherence session spends API money, so nothing that runs unasked (a hook,
a workflow, the pre-commit configuration, an agent prompt, a repository script,
the plain ``/eval-praxion`` harness) may name the package or its console entry,
and no module outside the package may import it. A structural promise made
executable, like the live runner's.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "eval" / "src"
_PACKAGE = _SRC / "praxion_evals" / "adherence"
_CLI = _PACKAGE / "cli.py"
_ADHERENCE_REFERENCES = ("praxion_evals.adherence", "praxion-evals-adherence")
_AUTOMATION_SURFACES = (
    "hooks",
    ".github/workflows",
    ".pre-commit-config.yaml",
    "agents",
    "scripts",
    "skills/eval-praxion",
    "eval/src/praxion_evals/harness",
)
_SCANNED_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".json", ".md", ".toml"}
# Names the console entry as data and starts nothing: the commit gate compares the `entry`
# field of a ledger run to it, so a flip rests only on a run of this eval.
_NAMES_THE_ENTRY_AS_DATA = ("scripts/check_kernel_manifest.py",)


def _files_under(surface: str) -> list[Path]:
    root = _REPO_ROOT / surface
    if root.is_file():
        return [root]
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in _SCANNED_SUFFIXES and "__pycache__" not in path.parts
    )


def _source_files() -> list[Path]:
    return sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> set[str]:
    package = path.relative_to(_SRC).with_suffix("").parts[:-1]
    return _imports_of(path.read_text(encoding="utf-8"), package)


def _imports_of(source: str, package: tuple[str, ...]) -> set[str]:
    """Absolute dotted names a module imports, relative imports resolved against its package."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else ()
            module = ".".join((*base, *([node.module] if node.module else [])))
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    return imported


def _is_within(name: str, module: str) -> bool:
    return name == module or name.startswith(module + ".")


@pytest.mark.parametrize("surface", _AUTOMATION_SURFACES)
def test_automation_surface_never_references_the_adherence_eval(surface: str) -> None:
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in _files_under(surface)
        if str(path.relative_to(_REPO_ROOT)) not in _NAMES_THE_ENTRY_AS_DATA
        and any(
            ref in path.read_text(encoding="utf-8", errors="replace")
            for ref in _ADHERENCE_REFERENCES
        )
    ]

    assert offenders == [], f"{surface} reaches the paid adherence eval: {offenders}"


@pytest.mark.parametrize("surface", _AUTOMATION_SURFACES)
def test_each_automation_surface_is_actually_scanned(surface: str) -> None:
    assert _files_under(surface), f"{surface} yielded no files: the guard would pass vacuously"


def test_no_module_but_the_console_entry_imports_the_console_entry() -> None:
    importers = [
        str(path.relative_to(_SRC))
        for path in _source_files()
        if path != _CLI
        and any(_is_within(m, "praxion_evals.adherence.cli") for m in _imported_modules(path))
    ]

    assert importers == [], f"modules importing the adherence console entry: {importers}"


def test_no_module_outside_the_package_imports_the_adherence_eval() -> None:
    importers = [
        str(path.relative_to(_SRC))
        for path in _source_files()
        if not path.is_relative_to(_PACKAGE)
        and any(_is_within(m, "praxion_evals.adherence") for m in _imported_modules(path))
    ]

    assert importers == [], f"modules outside the package importing it: {importers}"


def test_the_import_scan_sees_a_relative_import_of_the_console_entry() -> None:
    seen = _imports_of("from . import cli\nfrom .cli import main\n", ("praxion_evals", "adherence"))

    assert "praxion_evals.adherence.cli" in seen
