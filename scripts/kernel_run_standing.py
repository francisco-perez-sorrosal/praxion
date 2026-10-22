"""What a lineage stands on for one role, and the typed reads both flip-gate readers parse it with.

The run index (`kernel_run_index`) and a cited run's results files (`kernel_run_evidence`) each
record a role's standing in JSON and each is read at the commit gate. They read it through this
one definition, so a standing one accepts is a standing the other accepts: the value, its closed
label set, and the rules a recorded standing must keep.

Stdlib only, and no import of the eval package or `kernel_model`: the gate runs under a bare
interpreter, and a leaf that reached either would take the third-party reads with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, get_args

Flip = Literal["clear", "not clear", "underpowered"]  # a closed lineage already reads "not clear"
FLIP_LABELS: tuple[Flip, ...] = get_args(Flip)
CLEAR: Flip = "clear"
NOT_CLEAR: Flip = "not clear"
UNDERPOWERED: Flip = "underpowered"


class ShapeError(ValueError):
    """A recorded value is not the shape it must be; the message names the field and why."""


@dataclass(frozen=True)
class Standing:
    """What a lineage reached for one role it measured, and the checks its verdict scored (sorted,
    unique)."""

    complete_pairs: int
    flip: Flip
    scored_checks: tuple[str, ...]


def read_standing(pairs: Any, flip: Any, scored: Any) -> Standing:
    """The standing the three recorded figures state; raises `ShapeError` for any that cannot be."""
    count = as_count(pairs, "complete_pairs")
    if flip not in FLIP_LABELS:
        raise ShapeError(f"flip {flip!r} is none of {', '.join(FLIP_LABELS)}")
    checks = as_sorted_unique_texts(scored, "scored_checks")
    if flip == UNDERPOWERED and checks:
        raise ShapeError(f"an underpowered standing scored no check, yet lists {list(checks)!r}")
    return Standing(count, flip, checks)


# -- Typed reads of untrusted JSON: each names the field it was reading when it refuses ----------


def as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ShapeError(f"{field} {value!r} is not a mapping")
    return value


def as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ShapeError(f"{field} {value!r} is not a list")
    return value


def as_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ShapeError(f"{field} {value!r} is not text")
    return value


def as_count(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:  # a bool is an int to isinstance, and no count
        raise ShapeError(f"{field} {value!r} is not a count")
    return value


def as_sorted_unique_texts(value: Any, field: str) -> tuple[str, ...]:
    texts = tuple(as_text(item, field) for item in as_list(value, field))
    if list(texts) != sorted(set(texts)):
        raise ShapeError(f"{field} {list(texts)!r} are not sorted and unique")
    return texts
