"""The adherence eval is reached only through its own console entry.

Every adherence session costs money, so its console entry sits beside
`praxion-evals-live` and nothing else -- `praxion-evals`, the `/eval-praxion`
skill, a hook, the pre-commit configuration or a workflow -- names or imports it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.acceptance.drivers.adherence_eval import (
    EVAL_PROJECT,
    REPO_ROOT,
    adherence_console_entry,
    declared_console_entries,
)

_PLACES_THAT_RUN_UNASKED = (
    REPO_ROOT / "hooks",
    REPO_ROOT / ".pre-commit-config.yaml",
    REPO_ROOT / ".github" / "workflows",
    REPO_ROOT / "skills" / "eval-praxion",
    EVAL_PROJECT / "src" / "praxion_evals" / "harness",
)


def _files_under(place: Path) -> list[Path]:
    if place.is_file():
        return [place]
    return sorted(p for p in place.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def _imported_modules(source: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def test_the_adherence_eval_has_its_own_console_entry_beside_the_live_runner():
    entries = declared_console_entries()

    entry = adherence_console_entry()

    assert {"praxion-evals", "praxion-evals-live"} <= set(entries)
    assert entry.target != entries["praxion-evals-live"], (
        "the adherence eval needs its own entry point, not the live runner's"
    )


def test_no_hook_workflow_pre_commit_config_or_eval_command_names_the_adherence_eval():
    entry = adherence_console_entry()
    names = (entry.name, entry.module, entry.module_path)

    mentions = [
        f"{path.relative_to(REPO_ROOT)} names {name!r}"
        for place in _PLACES_THAT_RUN_UNASKED
        for path in _files_under(place)
        for name in names
        if name in path.read_text(encoding="utf-8", errors="replace")
    ]

    assert mentions == [], (
        "the adherence eval is reachable from outside its console entry:\n" + "\n".join(mentions)
    )


def test_the_live_runner_does_not_import_the_adherence_eval():
    entry = adherence_console_entry()
    live_cli = EVAL_PROJECT / "src" / "praxion_evals" / "live" / "cli.py"

    imported = _imported_modules(live_cli)

    assert not {m for m in imported if m == entry.module or m.startswith(entry.module + ".")}, (
        f"praxion-evals-live imports the adherence eval's module {entry.module}"
    )
