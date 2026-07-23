# DOGFOOD TEST for the cross-model review gate.
#
# This PR deliberately exercises the cross-model review gate on an
# agent-authored (ci-autofix/*) branch. It is NOT meant to be merged — it
# carries a planted logic defect for the reviewing model to catch. Close this
# PR once the gate has posted its verdict.


def clamp(value, low, high):
    """Clamp ``value`` into the inclusive range ``[low, high]``.

    Returns ``low`` if ``value`` is below the range, ``high`` if above it,
    and ``value`` itself when already inside the range.
    """
    if value < low:
        return high  # planted defect: below-range should return `low`, not `high`
    if value > high:
        return low  # planted defect: above-range should return `high`, not `low`
    return value
