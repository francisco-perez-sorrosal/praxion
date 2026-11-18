"""The selection audit's own time bound, read from the one place that declares it.

The audit traces a run of the whole default suite, so it needs a bound of its own: the step loop's
`gate-timeout-seconds` answers a different question (how long a pocket's gate may run) and sharing
it would let the two drift together. The bound is declared in the root `pyproject.toml`:

    [tool.praxion.gate-liveness]
    selection-audit-timeout-seconds = 5400

`read_audit_bound` is the one reader. It parses the file once and returns an `AuditBound`, which is
`Declared` with a positive whole number of seconds or `Undeclared` with the reason it is not. A
missing table, a missing key, a value that is not a whole number above zero, a file that is
unreadable or not TOML, and an interpreter without `tomllib` are each an `Undeclared` that says
which, so a consumer can fail its verdict naming the key. There is no fallback to another bound.

Stdlib-only and 3.9-safe at runtime. Tests: `scripts/gate_probes/test_suite_bound.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    tomllib = None  # type: ignore[assignment]

_PYPROJECT = "pyproject.toml"
_TABLE = ("tool", "praxion", "gate-liveness")
DECLARATION_KEY = "selection-audit-timeout-seconds"
_DECLARATION = f"[{'.'.join(_TABLE)}] {DECLARATION_KEY}"


@dataclass(frozen=True)
class Declared:
    """The audit's bound, a positive whole number of seconds."""

    seconds: int


@dataclass(frozen=True)
class Undeclared:
    """No usable bound; `reason` says which of the causes it is."""

    reason: str


AuditBound = Union[Declared, Undeclared]  # noqa: UP007 -- runtime value, 3.9 floor


def read_audit_bound(repo_root: Path) -> AuditBound:
    if tomllib is None:
        return Undeclared(f"{_DECLARATION} not read: this interpreter has no tomllib")
    path = Path(repo_root) / _PYPROJECT
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return Undeclared(f"{_PYPROJECT} unreadable ({exc})")
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return Undeclared(f"{_PYPROJECT} is not TOML ({exc})")
    return _bound_from(data)


def _bound_from(data: dict[str, Any]) -> AuditBound:
    table: Any = data
    for name in _TABLE:
        table = table.get(name) if isinstance(table, dict) else None
    if not isinstance(table, dict):
        return Undeclared(f"{_PYPROJECT} has no [{'.'.join(_TABLE)}] table")
    if DECLARATION_KEY not in table:
        return Undeclared(f"{_DECLARATION} is missing")
    value = table[DECLARATION_KEY]
    # bool is an int in Python; `true` is not a number of seconds.
    if isinstance(value, bool) or not isinstance(value, int):
        return Undeclared(f"{_DECLARATION} is not a whole number of seconds: {value!r}")
    if value <= 0:
        return Undeclared(f"{_DECLARATION} is not above zero: {value}")
    return Declared(value)
