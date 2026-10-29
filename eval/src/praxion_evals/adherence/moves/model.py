"""The closed values of a move: its declaration, its arms, and what one session leaves behind.

Every value is frozen and every invariant is enforced where the value is built, so the
interior never re-validates. Raw text is parsed once, at the declaration boundary, into
these types; a sum is a union of frozen dataclasses matched exhaustively with ``assert_never``.

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Literal, assert_never, get_args

from praxion_evals.adherence.model import Failed, Passed, _frozen, _non_empty, _one_of, _require

MoveArm = Literal["full", "lean", "floor"]
RunKind = Literal["floor", "paired"]
FixtureKind = Literal["managed", "unmanaged"]
Channel = Literal["session_start", "path_matched", "hook_context", "gate_refusal", "project_gating"]
HookRepeat = Literal["each", "once"]
ArrivalTiming = Literal["before composition", "before execution", "after execution"]
History = Literal["right_first_time", "repaired", "not_repaired", "never_taken"]

MOVE_ARMS: tuple[MoveArm, ...] = get_args(MoveArm)

# The only place a run's arms are derived.
ARMS_OF: Mapping[RunKind, tuple[MoveArm, ...]] = MappingProxyType(
    {"floor": ("floor",), "paired": ("full", "lean")}
)

GOVERNED_CHECK_COUNTS = (1, 2)
EVAL_LEDGER = ".ai-state/eval_ledger"  # the eval's own record, never a rule of a checkout

_MOVE_NAME = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class MoveName:
    value: str

    def __post_init__(self) -> None:
        _require(
            bool(_MOVE_NAME.fullmatch(self.value)),
            f"a move name is lowercase words joined by hyphens, got {self.value!r}",
        )


@dataclass(frozen=True)
class RelPath:
    """A path inside the checkout, in normal form; ``parse`` is the only way to make one from text."""

    value: str

    def __post_init__(self) -> None:
        _require(
            _normalised(self.value) == self.value,
            f"a relative path must be in normal form, got {self.value!r}",
        )

    @classmethod
    def parse(cls, text: str) -> RelPath:
        return cls(_normalised(text))


def _normalised(text: str) -> str:
    _non_empty(text, "a relative path")
    _require("\\" not in text, f"a relative path uses forward slashes, got {text!r}")
    _require(not posixpath.isabs(text), f"a relative path is not absolute, got {text!r}")
    normal = posixpath.normpath(text)
    _require(
        normal != "." and normal != ".." and not normal.startswith("../"),
        f"a relative path stays inside the checkout, got {text!r}",
    )
    _require(
        normal != EVAL_LEDGER and not normal.startswith(f"{EVAL_LEDGER}/"),
        f"a relative path is never under {EVAL_LEDGER}, got {text!r}",
    )
    return normal


# Arm changes: what an arm's copy differs by, and nothing else


@dataclass(frozen=True)
class Write:
    path: RelPath
    source: Path
    sha256: str

    def __post_init__(self) -> None:
        _require(bool(_SHA256.fullmatch(self.sha256)), "a write carries the sha256 of its content")


@dataclass(frozen=True)
class Remove:
    path: RelPath


@dataclass(frozen=True)
class KernelDerive:
    """The moved rule's resident kernel: the lines beginning with each prefix, no more."""

    path: RelPath
    prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(bool(self.prefixes), "a kernel derive names at least one line prefix")
        for prefix in self.prefixes:
            _non_empty(prefix, "a kernel line prefix")
        _require(len(set(self.prefixes)) == len(self.prefixes), "kernel line prefixes are distinct")


@dataclass(frozen=True)
class ManifestRowRemoved:  # computed from the checkout's rule manifest
    path: RelPath


@dataclass(frozen=True)
class HookRegistered:  # computed from the checkout's hook registry
    path: RelPath


Derive = KernelDerive | ManifestRowRemoved | HookRegistered
ArmChange = Write | Remove | Derive


@dataclass(frozen=True)
class ArmChanges:
    """Per-arm changes; the full arm is today's delivery, so it has no slot to hold one."""

    lean: tuple[ArmChange, ...] = ()
    floor: tuple[ArmChange, ...] = ()

    def __post_init__(self) -> None:
        for arm in ("lean", "floor"):
            paths = [change.path for change in self.for_arm(arm)]
            _require(len(set(paths)) == len(paths), f"the {arm} arm changes a path once")

    @classmethod
    def of(cls, by_arm: Mapping[str, Iterable[ArmChange]]) -> ArmChanges:
        for arm in by_arm:
            _one_of(arm, MOVE_ARMS, "an arm")
        _require(not tuple(by_arm.get("full", ())), "the full arm declares no change")
        return cls(lean=tuple(by_arm.get("lean", ())), floor=tuple(by_arm.get("floor", ())))

    def for_arm(self, arm: MoveArm) -> tuple[ArmChange, ...]:
        match arm:
            case "full":
                return ()
            case "lean":
                return self.lean
            case "floor":
                return self.floor
            case _:
                assert_never(arm)


# Deliveries: the lean arm's channels, each naming the rule file it reads


@dataclass(frozen=True)
class SessionStart:
    channel: ClassVar[Channel] = "session_start"
    file: RelPath
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathMatched:
    channel: ClassVar[Channel] = "path_matched"
    file: RelPath
    globs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(bool(self.globs), "a path-matched delivery names at least one glob")


@dataclass(frozen=True)
class HookContext:
    channel: ClassVar[Channel] = "hook_context"
    event: str
    matcher: str
    reads: RelPath
    repeat: HookRepeat

    def __post_init__(self) -> None:
        _non_empty(self.event, "a hook event")
        _non_empty(self.matcher, "a hook matcher")


@dataclass(frozen=True)
class GateRefusal:
    channel: ClassVar[Channel] = "gate_refusal"
    matcher: str
    reads: RelPath

    def __post_init__(self) -> None:
        _non_empty(self.matcher, "a gate matcher")


@dataclass(frozen=True)
class ProjectGating:
    channel: ClassVar[Channel] = "project_gating"
    kind: str

    def __post_init__(self) -> None:
        _non_empty(self.kind, "a project gating kind")


Delivery = SessionStart | PathMatched | HookContext | GateRefusal | ProjectGating


# Governed checks, fixture scope, launch options


@dataclass(frozen=True)
class GovernedCheck:
    name: str
    rule_file: RelPath
    section: str
    phrases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.name, "a governed check's name")
        _non_empty(self.section, "a governed check's section")
        for phrase in self.phrases:
            _non_empty(phrase, "a governed phrase")


@dataclass(frozen=True)
class GovernedChecks:
    checks: tuple[GovernedCheck, ...]

    def __post_init__(self) -> None:
        _require(
            len(self.checks) in GOVERNED_CHECK_COUNTS,
            f"a move declares one or two governed checks, got {len(self.checks)}",
        )
        _require(len({c.name for c in self.checks}) == len(self.checks), "check names are distinct")


@dataclass(frozen=True)
class BothKinds: ...


@dataclass(frozen=True)
class OnlyKind:
    kind: FixtureKind


FixtureScope = BothKinds | OnlyKind


def admits(scope: FixtureScope, kind: FixtureKind) -> bool:
    match scope:
        case BothKinds():
            return True
        case OnlyKind(kind=only):
            return only == kind
        case _:
            assert_never(scope)


@dataclass(frozen=True)
class LaunchOptions:
    """One arm's launch overrides; ``None`` leaves the entry's default, field by field."""

    model: str | None = None
    effort: str | None = None
    attribution: str | None = None
    user_instructions: str | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None:
                _non_empty(value, f"the launch option {field.name}")


@dataclass(frozen=True)
class Pinned:
    """The settings one arm runs under, resolved; the paired arms must carry equal ones."""

    commit_attribution: str
    model: str
    effort: str
    user_instructions: str  # the digest of the rendered user instructions

    def __post_init__(self) -> None:
        for field in fields(self):
            _non_empty(getattr(self, field.name), f"the pinned {field.name}")

    def differences(self, other: Pinned) -> tuple[str, ...]:
        return tuple(
            f.name for f in fields(self) if getattr(self, f.name) != getattr(other, f.name)
        )


@dataclass(frozen=True)
class MoveDeclaration:
    move: MoveName
    moved_rule: RelPath
    checks: GovernedChecks
    arms: ArmChanges
    deliveries: tuple[Delivery, ...]
    fixture_scope: FixtureScope
    launch: Mapping[MoveArm, LaunchOptions]

    def __post_init__(self) -> None:
        _require(set(self.launch) <= set(MOVE_ARMS), "launch options name only the three arms")
        _frozen(self, "launch", {arm: self.launch.get(arm, LaunchOptions()) for arm in MOVE_ARMS})


# What one session leaves behind


@dataclass(frozen=True)
class Arrived:
    timing: ArrivalTiming


@dataclass(frozen=True)
class NeverArrived: ...


@dataclass(frozen=True)
class Unknown: ...  # the record could not say; never the same as NeverArrived


Arrival = Arrived | NeverArrived | Unknown


@dataclass(frozen=True)
class NothingToGrade:
    """The end state holds nothing the check governs, such as a session that made no commit.

    A pair reads it as a failure, since the arm left undone the task the check governs; a floor
    counts it apart, since it shows nothing of whether the check can see the rule's absence.
    """

    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "why nothing was left to grade")


Outcome = Literal["passed", "failed"]


@dataclass(frozen=True)
class Grade:
    """A governed check's grade of an end state: it fails exactly when it names a failed part."""

    outcome: Outcome
    failed_parts: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(
            (self.outcome == "failed") == bool(self.failed_parts),
            "a grade fails exactly when it names a failed part",
        )

    @classmethod
    def of(cls, failed_parts: Sequence[str]) -> Grade:
        parts = tuple(dict.fromkeys(failed_parts))
        return cls("failed" if parts else "passed", parts)


FinalState = Passed | Failed | NothingToGrade


@dataclass(frozen=True)
class CheckTrigger:
    """What arrived for one governed check, when, and what it left; ``history`` is ``None``
    only for a record that could not be read, where every arrival is unknown too."""

    check: str
    arrivals: Mapping[Channel, Arrival]
    final: FinalState | None
    history: History | None
    refusals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.check, "a trigger record's check")
        if self.history is None:
            _require(
                bool(self.arrivals) and all(isinstance(a, Unknown) for a in self.arrivals.values()),
                "a record with no history is unreadable, so every arrival is unknown",
            )
        for reason in self.refusals:
            _non_empty(reason, "a gate refusal's reason")
        _frozen(self, "arrivals", self.arrivals)

    @classmethod
    def unreadable(cls, check: str, channels: Iterable[Channel]) -> CheckTrigger:
        return cls(check, {channel: Unknown() for channel in channels}, None, None)

    @property
    def trigger_failure(self) -> bool:
        """Derived, never stored: the check failed and no channel ever delivered its text."""
        return (
            isinstance(self.final, Failed)
            and bool(self.arrivals)
            and all(isinstance(a, NeverArrived) for a in self.arrivals.values())
        )


@dataclass(frozen=True)
class Take:
    """Whether a session's arm took, so its session may be scored."""

    scored: bool
    reason: str | None  # why scoring was refused; None exactly when scored
    trigger_failure: bool = False  # scored, and the point-of-use text never arrived

    def __post_init__(self) -> None:
        _require(self.scored == (self.reason is None), "a take has a reason exactly when refused")
        _require(
            self.scored or not self.trigger_failure, "only a scored take can be a trigger failure"
        )
        if self.reason is not None:
            _non_empty(self.reason, "a refusal's reason")

    @classmethod
    def taken(cls, trigger_failure: bool = False) -> Take:
        return cls(True, None, trigger_failure)

    @classmethod
    def refused(cls, reason: str) -> Take:
        return cls(False, reason)
