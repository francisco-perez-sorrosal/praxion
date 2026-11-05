"""Which manifest rows a session in a given directory is served.

The budget counts what a session loads. A row marked ``project_scope: managed``
reaches only a managed project, so a directory outside one is measured without
it. Whether a directory is managed is the hooks' own predicate, imported by
path rather than restated, so the budget and the delivery cannot disagree.

Stdlib-only, like ``measure_token_budget``.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

# hooks/ sits beside scripts/ under the plugin root. The nearest ancestor that
# holds it, not a fixed parent: the mutation sensor runs a copy one level deeper.
_PLUGIN_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "hooks" / "_project_scope.py").is_file()
)
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))
from _project_scope import Managed, scope_of  # noqa: E402 (after sys.path injection)

MANAGED_ONLY = "managed"  # the only `project_scope` value that restricts a row


def loaded_rows(repo_root: Path, rows: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    """The manifest ``rows`` a session started in ``repo_root`` is served, in order.

    A managed directory is served all of them. Any other drops the managed-only
    ones; an unknown scope value stays, as in the hooks, so a damaged row never
    silently drops a rule.
    """
    if isinstance(scope_of(str(repo_root.absolute())), Managed):
        return list(rows)
    return [row for row in rows if row.get("project_scope") != MANAGED_ONLY]
