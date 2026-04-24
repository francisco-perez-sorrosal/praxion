"""Shared percentile helper used across collectors.

Percentile policy: ``statistics.quantiles(..., method="inclusive")`` from the
standard library. Inclusive method never exceeds ``max(data)``, which matches
user intuition for discrete integer metrics (CCN, cognitive complexity) better
than the default exclusive method. Stdlib-only — no numpy dependency.

Extracted from the original lizard/complexipy collector copies once the helper
had two identical call sites; future percentile consumers (e.g., a trends
rollup) can import from here rather than duplicating again.
"""

from __future__ import annotations

import statistics

__all__ = ["p_nth"]


def p_nth(data: list[int | float], n: int) -> float | None:
    """Return the ``n``th percentile (``1 <= n <= 99``) via stdlib inclusive method.

    Empty input yields ``None``. A single data point yields ``float(max(data))``
    because ``statistics.quantiles`` raises ``StatisticsError`` below two
    points; the single-value case degenerates to that value anyway.
    """

    if not data:
        return None
    if len(data) < 2:
        return float(max(data))
    cuts = statistics.quantiles(data, n=100, method="inclusive")
    return cuts[n - 1]
