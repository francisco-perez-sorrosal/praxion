"""Guards that the judgement half of the goal recorder (``scripts/_goal_record.py``) stays pure.

The recorder's top-level statements before ``BASELINE_REQUEST`` are the judgement; none of them may
use a name bound from a module that reads files, a repository, a process or the clock. The shell
half after it does, so the guard can fail. Its behaviour through the `record` verb is in
``scripts/test_goal_record.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

EFFECTFUL_MODULES = {
    "os", "io", "subprocess", "pathlib", "shutil", "tempfile", "socket", "time", "datetime", "glob",
}  # fmt: skip
SHELL_STARTS_AT = "BASELINE_REQUEST"  # the first name of the shell section of the module


def recorder_tree() -> ast.Module:
    return ast.parse((SCRIPT_DIR / "_goal_record.py").read_text(encoding="utf-8"))


def is_effectful(module: str) -> bool:
    root = module.split(".")[0]
    return root in EFFECTFUL_MODULES or root.startswith("_step_loop") or root == "iteration_ledger"


def effectful_names(tree: ast.Module) -> set[str]:
    """Every name the module binds from a module that reads files, a repository, a process or
    the clock: the standard ones above and the driver's own adapters and ledger."""
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    return {
        (alias.asname or alias.name.split(".")[0])
        for node in imports
        for alias in node.names
        if is_effectful(node.module or "" if isinstance(node, ast.ImportFrom) else alias.name)
    }


def names_used(nodes: list[ast.stmt]) -> set[str]:
    return {n.id for node in nodes for n in ast.walk(node) if isinstance(n, ast.Name)}


def halves(tree: ast.Module) -> tuple[list[ast.stmt], list[ast.stmt]]:
    """The module's top-level statements before and after the shell section starts."""
    code = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom, ast.If))]
    edge = next(
        n.lineno
        for n in code
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", "") == SHELL_STARTS_AT for t in n.targets)
    )
    return [n for n in code if n.lineno < edge], [n for n in code if n.lineno >= edge]


def test_the_judgement_half_of_the_recorder_uses_nothing_that_has_an_effect():
    tree = recorder_tree()
    judgement, _ = halves(tree)

    assert names_used(judgement).isdisjoint(effectful_names(tree))


def test_the_shell_half_of_the_recorder_does_use_effects_so_the_guard_can_fail():
    tree = recorder_tree()
    _, shell = halves(tree)

    assert names_used(shell) & effectful_names(tree)
