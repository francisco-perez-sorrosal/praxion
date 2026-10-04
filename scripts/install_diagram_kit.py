#!/usr/bin/env python3
"""Install the architecture-diagram kit into a project: model, command and CI drift gate.

    python3 install_diagram_kit.py --project-root DIR [--plugin-root DIR]
                                   [--diagrams-dir REL] [--dry-run]

    --project-root   the git repository to install into (required; never inferred)
    --plugin-root    where the kit's templates and command live; default: the checkout this
                     script runs from
    --diagrams-dir   the project's diagrams directory, relative to the project; default
                     `docs/diagrams`
    --dry-run        report what would be installed and write nothing

Each item is installed only when absent, so a second run changes no file:

- `<diagrams>/architecture/src/_spec.c4` and `architecture.c4`: the style kit and the example
  model, together, and only when no `*.c4` exists under the diagrams directory;
- `scripts/regenerate_diagrams.py` and the sibling modules it imports, as one set: skipped as
  a unit when the command is already present, so a project never holds a mixed-version set;
- `.github/workflows/architecture.yml`, from the CI template with the project's diagrams
  directory and Python lower bound filled in.

Stdout is one line per item, `installed <path>` (`would install <path>` under `--dry-run`) or
`skipped <path> (<reason>)`. Exit 0 when every item was installed or skipped; exit 2 when a
precondition failed (usage errors included), with nothing written. The installer never
renders and never runs git; the project's CI runs the same command the project now holds.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

EXIT_OK = 0
EXIT_PRECONDITION = 2

DEFAULT_DIAGRAMS_DIR = "docs/diagrams"
DEFAULT_PYTHON = "3.13"
ARCHITECTURE_DOCS = "**/DESIGN.md + docs/architecture.md"
PLUGIN_DIR_IN_PROJECT = "."

TEMPLATES = Path("claude") / "aac-templates"
STYLE_KIT_TEMPLATE = TEMPLATES / "likec4-style-kit.c4.tmpl"
EXAMPLE_TEMPLATE = TEMPLATES / "likec4-example-model.c4.tmpl"
WORKFLOW_TEMPLATE = TEMPLATES / "architecture.yml.tmpl"
COMMAND = Path("scripts") / "regenerate_diagrams.py"
WORKFLOW = Path(".github") / "workflows" / "architecture.yml"
MODEL_DIR = Path("architecture") / "src"

_MARKER = re.compile(r"\{\{(PROJECT_[A-Z_]+)\}\}")
_REQUIRES_PYTHON = re.compile(r"""^requires-python\s*=\s*["']\s*>=\s*(\d+\.\d+)""", re.MULTILINE)


class PreconditionError(Exception):
    """The project or plugin cannot be served; nothing has been written."""


@dataclass(frozen=True)
class Item:
    """One file the installer may write: where, what, and why it will be left alone (if so)."""

    path: Path  # relative to the project root
    content: bytes
    skip_reason: str | None = None


# --- command line -----------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project = Path(args.project_root)
    plugin = Path(args.plugin_root) if args.plugin_root else _shipped_from()
    try:
        diagrams = _diagrams_dir(args.diagrams_dir)
        _check_project(project)
        items = plan(project, plugin, diagrams)
    except PreconditionError as refusal:
        print(f"install_diagram_kit: {refusal}", file=sys.stderr)
        return EXIT_PRECONDITION
    for item in items:
        _install(project, item, args.dry_run)
    return EXIT_OK


def _shipped_from() -> Path:
    """The plugin checkout this script was shipped in (its source, never its target)."""
    return Path(__file__).resolve().parent.parent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project-root", required=True, help="the git repository to install into")
    parser.add_argument("--plugin-root", help="where the kit's templates and command live")
    parser.add_argument(
        "--diagrams-dir",
        default=DEFAULT_DIAGRAMS_DIR,
        help=f"diagrams directory, relative to the project (default {DEFAULT_DIAGRAMS_DIR})",
    )
    parser.add_argument("--dry-run", action="store_true", help="write nothing")
    return parser


def _diagrams_dir(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise PreconditionError(f"--diagrams-dir must be a directory inside the project: {raw!r}")
    return path


def _check_project(project: Path) -> None:
    if not project.is_dir():
        raise PreconditionError(f"project root is not a directory: {project}")
    if not (project / ".git").exists():
        raise PreconditionError(f"not a git repository: {project}")


def _install(project: Path, item: Item, dry_run: bool) -> None:
    if item.skip_reason is not None:
        print(f"skipped {item.path} ({item.skip_reason})")
        return
    if not dry_run:
        target = project / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
    print(f"{'would install' if dry_run else 'installed'} {item.path}")


# --- the plan: read the project and the plugin, decide each item ------------------------------


def plan(project: Path, plugin: Path, diagrams: PurePosixPath) -> list[Item]:
    _check_plugin(plugin)
    return [
        *_model_items(project, plugin, diagrams),
        *_command_items(project, plugin),
        _workflow_item(project, plugin, diagrams),
    ]


def _check_plugin(plugin: Path) -> None:
    for source in (STYLE_KIT_TEMPLATE, EXAMPLE_TEMPLATE, WORKFLOW_TEMPLATE, COMMAND):
        if not (plugin / source).is_file():
            raise PreconditionError(f"plugin root {plugin} does not hold {source}")


def _model_items(project: Path, plugin: Path, diagrams: PurePosixPath) -> list[Item]:
    existing = sorted((project / diagrams).rglob("*.c4"))
    reason = (
        f"a model already exists: {existing[0].relative_to(project).as_posix()}"
        if existing
        else None
    )
    source_dir = Path(diagrams) / MODEL_DIR
    return [
        Item(source_dir / "_spec.c4", (plugin / STYLE_KIT_TEMPLATE).read_bytes(), reason),
        Item(source_dir / "architecture.c4", (plugin / EXAMPLE_TEMPLATE).read_bytes(), reason),
    ]


def _command_items(project: Path, plugin: Path) -> list[Item]:
    reason = (
        "the command is already installed; its set is kept as it is"
        if (project / COMMAND).exists()
        else None
    )
    modules = [
        COMMAND,
        *(COMMAND.parent / path.name for path in _sibling_imports(plugin / COMMAND)),
    ]
    return [Item(module, (plugin / module).read_bytes(), reason) for module in modules]


def _sibling_imports(command: Path) -> list[Path]:
    """The modules `command` imports from its own directory, transitively, sorted by name."""
    found: dict[str, Path] = {}
    pending = [command]
    while pending:
        tree = ast.parse(pending.pop().read_text(encoding="utf-8"))
        for name in _imported_names(tree):
            module = command.parent / f"{name}.py"
            if name not in found and module.is_file():
                found[name] = module
                pending.append(module)
    return [found[name] for name in sorted(found)]


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _workflow_item(project: Path, plugin: Path, diagrams: PurePosixPath) -> Item:
    values = {
        "PROJECT_PATHS_DIAGRAMS": str(diagrams),
        "PROJECT_PATHS_ARCHITECTURE_DOCS": ARCHITECTURE_DOCS,
        "PROJECT_PYTHON_VERSION": _python_lower_bound(project),
        "PROJECT_PLUGIN_DIR": PLUGIN_DIR_IN_PROJECT,
    }
    template = (plugin / WORKFLOW_TEMPLATE).read_text(encoding="utf-8")
    reason = f"{WORKFLOW} already exists" if (project / WORKFLOW).exists() else None
    return Item(WORKFLOW, render(template, values).encode("utf-8"), reason)


def _python_lower_bound(project: Path) -> str:
    pyproject = project / "pyproject.toml"
    if not pyproject.is_file():
        return DEFAULT_PYTHON
    found = _REQUIRES_PYTHON.search(pyproject.read_text(encoding="utf-8"))
    return found.group(1) if found else DEFAULT_PYTHON


def render(template: str, values: Mapping[str, str]) -> str:
    """Fill every `{{PROJECT_*}}` marker; comment lines document the template and stay as written."""

    def fill(marker: re.Match[str]) -> str:
        if marker.group(1) not in values:
            raise PreconditionError(
                f"the workflow template holds an unknown marker {marker.group(0)}"
            )
        return values[marker.group(1)]

    return "".join(
        line if line.lstrip().startswith("#") else _MARKER.sub(fill, line)
        for line in template.splitlines(keepends=True)
    )


if __name__ == "__main__":
    sys.exit(main())
