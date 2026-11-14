"""The one owner of the skill-delivery decision: whether a delegation is served the refactoring skill.

The marker grammar is not defined here. It is the plan reader's `REFACTORING_TAG_PATTERN` in
`scripts/_plan_steps.py`, re-exported below as `MARKER_PATTERN`, so a plan step and a delegation
are matched by the same compiled object and no second copy of the grammar can drift.

Stdlib-only and Python 3.9-safe, like the hook modules that import script modules. The `scripts`
directory is found the way `hooks/guard_decision_records.py` finds it: next to the hook in the
plugin, or one level up from a mutation sensor's copy.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_DIR = "scripts"


def _scripts_dir() -> Path:
    """The `scripts` directory that ships beside this hook: `../scripts` in the plugin."""
    hook_dir = Path(__file__).resolve().parent
    nearest, one_up = (root / SCRIPTS_DIR for root in (hook_dir.parent, hook_dir.parent.parent))
    return nearest if nearest.is_dir() else one_up


MARKER_PATTERN: re.Pattern[str] | None
MARKER_IMPORT_ERROR: str | None = None

try:
    # Appended, never inserted first: the script modules must not shadow the standard library.
    sys.path.append(str(_scripts_dir()))
    from _plan_steps import REFACTORING_TAG_PATTERN as MARKER_PATTERN
except Exception as error:  # fail-open: a broken installation degrades the delivery, never a spawn
    MARKER_PATTERN = None
    MARKER_IMPORT_ERROR = f"{type(error).__name__}: {error}"
