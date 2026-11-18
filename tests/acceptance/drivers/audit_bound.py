"""Driver for the selection audit's own time bound: where it is declared, read and changed.

The audit holds its traced run of the default suite to a bound of its own, longer than the step
loop's `gate-timeout-seconds`, declared in exactly one place that the audit and the whole-suite
scenarios both read: `[tool.praxion.gate-liveness] selection-audit-timeout-seconds` in the root
`pyproject.toml`. This driver reads and rewrites that key itself and never imports the
production reader, so the outer loop stays independent of the code it judges.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.acceptance.drivers.gate_liveness import RepoCopy

PYPROJECT = "pyproject.toml"
TABLE = ("tool", "praxion", "gate-liveness")
KEY = "selection-audit-timeout-seconds"
_DECLARATION_LINE = re.compile(rf"^{re.escape(KEY)} = \d+$", re.MULTILINE)


def declared_audit_bound_seconds(root: Path) -> int:
    """The bound the selection audit holds its traced run to, as declared under `root`."""
    table = tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))
    for name in TABLE:
        table = table[name]
    return int(table[KEY])


def declare_audit_bound(copy: RepoCopy, seconds: int) -> None:
    """Declare, in a scratch copy, the bound the audit holds its traced run to."""
    text = copy.read(PYPROJECT)
    found = _DECLARATION_LINE.findall(text)
    if len(found) != 1:
        raise AssertionError(f"expected one `{KEY} = <n>` line in {PYPROJECT}, found {len(found)}")
    copy.write(PYPROJECT, _DECLARATION_LINE.sub(f"{KEY} = {seconds}", text))
