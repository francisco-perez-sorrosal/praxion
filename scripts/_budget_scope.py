"""Which manifest rows a session in a given directory is served.

The budget counts what a session loads. A row marked ``project_scope: managed``
reaches only a managed project, so a directory outside one is measured without
it. Whether a directory is managed is the hooks' own predicate, imported by
path rather than restated, so the budget and the delivery cannot disagree.

Stdlib-only, like ``measure_token_budget``.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import ModuleType

_SCOPE_FILE = Path("hooks") / "_project_scope.py"
_SCOPE_MODULE = "_budget_scope_project_scope"  # private, so no importer's `_project_scope` is taken
MANAGED_ONLY = "managed"  # the only `project_scope` value that restricts a row


def _hooks_scope_module() -> ModuleType:
    """The hooks' `_project_scope`, loaded from its file so no importer's `sys.path` changes.

    hooks/ sits beside scripts/ under the plugin root: the nearest ancestor that holds the
    module, not a fixed parent, since the mutation sensor runs a copy one level deeper.
    """
    here = Path(__file__).resolve()
    root = next((p for p in here.parents if (p / _SCOPE_FILE).is_file()), None)
    spec = root and importlib.util.spec_from_file_location(_SCOPE_MODULE, root / _SCOPE_FILE)
    if not spec or spec.loader is None:
        raise ImportError(
            f"no directory above {here.parent} holds {_SCOPE_FILE.as_posix()}, the hooks'"
            " managed-project predicate the budget counts by"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SCOPE_MODULE] = module  # registered under its own name, as an import does
    spec.loader.exec_module(module)
    return module


_scope = _hooks_scope_module()
Managed, scope_of = _scope.Managed, _scope.scope_of


def loaded_rows(repo_root: Path, rows: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    """The manifest ``rows`` a session started in ``repo_root`` is served, in order.

    A managed directory is served all of them. Any other drops the managed-only
    ones; an unknown scope value stays, as in the hooks, so a damaged row never
    silently drops a rule.
    """
    if isinstance(scope_of(str(repo_root.absolute())), Managed):
        return list(rows)
    return [row for row in rows if row.get("project_scope") != MANAGED_ONLY]
