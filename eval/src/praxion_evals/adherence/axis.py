"""The axes a role eval can compare along, and the arms legal on each.

``inherited-context`` is the default axis, the lean-spawn pilot's ``full`` against
``lean``. ``refactoring-delivery`` compares a role that preloads the refactoring
skill (``preloaded``) with one that receives it by marked delivery (``delivered``).
The arm names are disjoint, so an arm belongs to exactly one axis and a pairing of
an arm with the other axis is refused where it would be built, never downstream.

Pure, and imports nothing from the eval, so ``model`` can build on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, get_args

Axis = Literal["inherited-context", "refactoring-delivery"]
InheritedContextArm = Literal["full", "lean"]
RefactoringDeliveryArm = Literal["preloaded", "delivered"]
SessionArm = InheritedContextArm | RefactoringDeliveryArm

AXES: tuple[Axis, ...] = get_args(Axis)
DEFAULT_AXIS: Axis = "inherited-context"

ARMS_BY_AXIS: MappingProxyType[str, tuple[SessionArm, ...]] = MappingProxyType(
    {
        "inherited-context": get_args(InheritedContextArm),
        "refactoring-delivery": get_args(RefactoringDeliveryArm),
    }
)
SESSION_ARMS: tuple[str, ...] = (*get_args(InheritedContextArm), *get_args(RefactoringDeliveryArm))


@dataclass(frozen=True)
class Positions:
    """Which of an axis's two arms is the comparison's baseline and which its treatment."""

    baseline: SessionArm
    treatment: SessionArm


POSITIONS: MappingProxyType[str, Positions] = MappingProxyType(
    {
        "inherited-context": Positions("full", "lean"),
        "refactoring-delivery": Positions("preloaded", "delivered"),
    }
)

# The arms whose session is owed the injected kernel. The default axis's full arm keeps its
# instruction layer, so only lean is; both definitions the refactoring move changes omit that layer,
# so both of its arms are.
KERNEL_OWED: MappingProxyType[str, tuple[SessionArm, ...]] = MappingProxyType(
    {
        "inherited-context": ("lean",),
        "refactoring-delivery": ("preloaded", "delivered"),
    }
)

# The two definitions the refactoring move changes; scripts/refactoring_move.py names the same
# two, so a change to either list must change both.
MOVE_SITES: tuple[str, ...] = ("agents/implementer.md", "agents/test-engineer.md")


def axis_of(arm: SessionArm) -> Axis:
    """The axis an arm belongs to; total, because the arm names are disjoint."""
    return DEFAULT_AXIS if arm in ARMS_BY_AXIS[DEFAULT_AXIS] else "refactoring-delivery"


def arm_on(axis: Axis, default_arm: SessionArm) -> SessionArm:
    """The arm of ``axis`` standing where ``default_arm`` stands in the default axis."""
    return ARMS_BY_AXIS[axis][ARMS_BY_AXIS[DEFAULT_AXIS].index(default_arm)]


def patched_paths(role: str, arm: SessionArm, turn_cap: int | None) -> tuple[str, ...]:
    """The files an arm's plugin copy changes, sorted and without duplicates.

    A turn cap and the lean arm both change the role's own definition; the delivered arm
    changes the two move sites. The default axis's full arm, uncapped, changes nothing.
    """
    definition = f"agents/{role}.md"
    changed: set[str] = set()
    if turn_cap is not None or arm == "lean":
        changed.add(definition)
    if arm == "delivered":
        changed.update(MOVE_SITES)
    return tuple(sorted(changed))


def check_patched(
    role: str, arm: SessionArm, turn_cap: int | None, patched: tuple[str, ...]
) -> None:
    """Refuse a build whose patched files are not exactly those its arm and cap change."""
    expected = patched_paths(role, arm, turn_cap)
    if patched == expected:
        return
    if axis_of(arm) == DEFAULT_AXIS:
        raise ValueError(f"an arm build patches agents/{role}.md exactly when it is lean or capped")
    raise ValueError(f"an arm build patches exactly {list(expected)}, got {list(patched)}")


def check_axis(axis: object) -> None:
    """Refuse an axis that is not one of the known ones, naming it and them."""
    if axis not in AXES:
        raise ValueError(f"an axis must be one of {list(AXES)}, got {axis!r}")


def check_axis_arm(axis: str, arm: str) -> None:
    """Refuse an unknown axis, and an arm that is not one of that axis's."""
    check_axis(axis)
    if arm not in ARMS_BY_AXIS[axis]:
        raise ValueError(f"the {axis} axis has arms {list(ARMS_BY_AXIS[axis])}, got {arm!r}")
