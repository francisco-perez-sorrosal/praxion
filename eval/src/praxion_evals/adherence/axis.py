"""The axes a role eval can compare along, and the arms legal on each.

``inherited-context`` is the default axis, the lean-spawn pilot's ``full`` against
``lean``. ``refactoring-delivery`` compares a role that preloads the refactoring
skill (``preloaded``) with one that receives it by marked delivery (``delivered``).
The arm names are disjoint, so an arm belongs to exactly one axis and a pairing of
an arm with the other axis is refused where it would be built, never downstream.

Pure, and imports nothing from the eval, so ``model`` can build on it.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, get_args

Axis = Literal["inherited-context", "refactoring-delivery"]
InheritedContextArm = Literal["full", "lean"]
RefactoringDeliveryArm = Literal["preloaded", "delivered"]
SessionArm = InheritedContextArm | RefactoringDeliveryArm

AXES: tuple[str, ...] = get_args(Axis)
DEFAULT_AXIS: Axis = "inherited-context"

ARMS_BY_AXIS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        "inherited-context": get_args(InheritedContextArm),
        "refactoring-delivery": get_args(RefactoringDeliveryArm),
    }
)


def check_axis_arm(axis: str, arm: str) -> None:
    """Refuse an unknown axis, and an arm that is not one of that axis's."""
    if axis not in ARMS_BY_AXIS:
        raise ValueError(f"an axis must be one of {list(AXES)}, got {axis!r}")
    if arm not in ARMS_BY_AXIS[axis]:
        raise ValueError(f"the {axis} axis has arms {list(ARMS_BY_AXIS[axis])}, got {arm!r}")
