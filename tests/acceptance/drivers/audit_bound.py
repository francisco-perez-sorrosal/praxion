"""Driver for the selection audit's own time bound: where it is declared, read and changed.

The audit holds its traced run of the default suite to a bound of its own, longer than the step
loop's `gate-timeout-seconds`, declared in exactly one place that the audit and the whole-suite
scenarios both read. Where that place is, and how a scenario sets a short bound in a scratch copy,
are the design's to choose; until a binding step names them, both functions raise.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.gate_liveness import RepoCopy

UNBOUND = (
    "unbound: the selection audit's own time bound (the one place it is declared, which the "
    "audit and the whole-suite scenarios both read) is not bound to this driver yet"
)


def declared_audit_bound_seconds(root: Path) -> int:
    """The bound the selection audit holds its traced run to, as declared under `root`."""
    raise NotImplementedError(UNBOUND)


def declare_audit_bound(copy: RepoCopy, seconds: int) -> None:
    """Declare, in a scratch copy, the bound the audit holds its traced run to."""
    raise NotImplementedError(UNBOUND)
