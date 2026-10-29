"""Parse a move's declaration file at the boundary into the frozen values of ``model``.

A declaration is JSON in a kit directory (``kits/<move>/declaration.json``) or at an operator's
path, with the files its arms write beside it. This is the only place the raw text is read:
every refusal below is raised here, as a ``DeclarationError`` naming the file and the value,
and the interior receives a ``MoveDeclaration`` it never re-checks.

``load`` parses a file and touches no checkout. A governed check's section is checked against
the checkout where one is in hand (the arm build calls ``check_sections``; ``load`` does it when
given a checkout), because a kit's rule files live in the checkout it is measured on.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxion_evals.adherence.moves.model import (
    MOVE_ARMS,
    ArmChange,
    ArmChanges,
    BothKinds,
    Delivery,
    FixtureScope,
    GateRefusal,
    GovernedCheck,
    GovernedChecks,
    HookContext,
    HookRegistered,
    KernelDerive,
    LaunchOptions,
    ManifestRowRemoved,
    ManifestRowScoped,
    MoveArm,
    MoveDeclaration,
    MoveName,
    OnlyKind,
    PathMatched,
    ProjectGating,
    RelPath,
    Remove,
    SessionStart,
    Write,
    holds_phrase,
)

SCHEMA = "move-declaration/1"
DECLARATION_FILE = "declaration.json"
KITS_ROOT = Path(__file__).parent / "kits"
LAUNCH_SETTINGS = ("model", "effort", "attribution", "user_instructions")
FIXTURE_SCOPES = ("both", "managed", "unmanaged")

Json = Mapping[str, Any]


class DeclarationError(ValueError):
    """A declaration that cannot be built into a ``MoveDeclaration``; the message names why."""


def load(path: Path, checkout: Path | None = None) -> MoveDeclaration:
    """Parse the declaration at ``path``; with a ``checkout``, also hold its sections to it."""
    try:
        declaration = _declaration(_read_json(path), path.parent)
    except (ValueError, TypeError) as error:
        raise DeclarationError(f"{path}: {error}") from error
    if checkout is not None:
        check_sections(declaration, checkout)
    return declaration


def kit(name: str, checkout: Path | None = None) -> MoveDeclaration:
    """The declaration the kit named ``name`` ships; the kit's move is the name it is filed under."""
    try:
        MoveName(name)
    except ValueError as error:
        raise DeclarationError(f"no move kit is named {name!r}: {error}") from error
    path = KITS_ROOT / name / DECLARATION_FILE
    if not path.is_file():
        raise DeclarationError(f"no move kit is named {name!r}: {path} does not exist")
    declaration = load(path, checkout)
    if declaration.move.value != name:
        raise DeclarationError(
            f"{path}: the kit {name!r} declares the move {declaration.move.value!r}"
        )
    return declaration


def check_sections(declaration: MoveDeclaration, checkout: Path) -> None:
    """Refuse a governed check whose section is no heading of its rule file in ``checkout``,
    or whose declared phrase that section does not hold."""
    for check in declaration.checks.checks:
        rule = checkout / check.rule_file.value
        if not rule.is_file():
            raise DeclarationError(
                f"the check {check.name!r} names the rule file {check.rule_file.value}, "
                f"which the checkout does not hold"
            )
        span = _section_span(rule.read_text(encoding="utf-8"), check.section)
        if span is None:
            raise DeclarationError(
                f"the check {check.name!r} names the section {check.section!r}, "
                f"which {check.rule_file.value} does not hold"
            )
        for phrase in check.phrases:
            if not holds_phrase(span, phrase):
                raise DeclarationError(
                    f"the check {check.name!r} declares the phrase {phrase!r}, which the "
                    f"section {check.section!r} of {check.rule_file.value} does not hold"
                )


def _section_span(text: str, section: str) -> str | None:
    """The heading line of ``section`` through the line before the next heading of the same or
    a higher level (sub-headings included); None when no heading names it."""
    lines = text.splitlines()
    headings = markdown_headings(lines)
    for start, heading in enumerate(headings):
        if heading and heading.title == section:
            return section_text(lines, headings, start, heading.level)
    return None


# -- Markdown headings ------------------------------------------------------------------------

_HEADING = re.compile(r"(?P<hashes>#{1,6})\s+(?P<title>.*?)\s*")
_FENCE = re.compile(r" {0,3}(?P<run>`{3,}|~{3,})(?P<rest>.*)")


@dataclass(frozen=True)
class Heading:
    level: int
    title: str


def markdown_headings(lines: Sequence[str]) -> list[Heading | None]:
    """Each line's heading, or None for a line that is none. Fenced code holds no headings: a fence
    opens on three or more backticks or tildes indented up to three spaces and closes on the same
    character at least as many times with nothing after; an unclosed fence runs to the end."""
    found: list[Heading | None] = []
    open_run: str | None = None
    for line in lines:
        fence = _FENCE.fullmatch(line)
        if open_run is None:
            open_run = fence["run"] if fence else None
            found.append(None if fence else _heading(line))
        else:
            found.append(None)
            if fence and _closes(fence, open_run):
                open_run = None
    return found


def section_text(
    lines: Sequence[str], headings: Sequence[Heading | None], start: int, level: int
) -> str:
    """The section whose heading of ``level`` is line ``start``: through the line before the next
    heading of the same or a higher level, sub-headings included."""
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if (heading := headings[i]) is not None and heading.level <= level
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _closes(fence: re.Match[str], open_run: str) -> bool:
    run = fence["run"]
    return run[0] == open_run[0] and len(run) >= len(open_run) and not fence["rest"].strip()


def _heading(line: str) -> Heading | None:
    found = _HEADING.fullmatch(line)
    return Heading(len(found["hashes"]), found["title"]) if found else None


# -- The declaration ------------------------------------------------------------------------


def _read_json(path: Path) -> Json:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"the declaration cannot be read: {error}") from error
    try:
        return _object(json.loads(text), "the declaration")
    except json.JSONDecodeError as error:
        raise ValueError(f"the declaration is not JSON: {error}") from error


def _declaration(raw: Json, directory: Path) -> MoveDeclaration:
    schema = _text(raw, "schema")
    _require(schema == SCHEMA, f"the schema is {schema!r}, not {SCHEMA!r}")
    return MoveDeclaration(
        move=MoveName(_text(raw, "move")),
        moved_rule=RelPath.parse(_text(raw, "moved_rule")),
        checks=GovernedChecks(tuple(_check(c) for c in _items(raw, "checks"))),
        arms=_arm_changes(_field_object(raw, "arms"), directory),
        deliveries=tuple(_delivery(d) for d in _items(raw, "deliveries")),
        fixture_scope=_fixture_scope(_text(raw, "fixture_scope")),
        launch=_launch(_object(raw.get("launch", {}), "launch"), directory),
    )


def _check(raw: object) -> GovernedCheck:
    check = _object(raw, "a governed check")
    return GovernedCheck(
        name=_text(check, "name"),
        rule_file=RelPath.parse(_text(check, "rule_file")),
        section=_text(check, "section"),
        phrases=_texts(check, "phrases", required=False),
    )


def _fixture_scope(word: str) -> FixtureScope:
    _require(
        word in FIXTURE_SCOPES, f"the fixture scope is one of {list(FIXTURE_SCOPES)}, got {word!r}"
    )
    return BothKinds() if word == "both" else OnlyKind(word)  # type: ignore[arg-type]


def _launch(raw: Json, directory: Path) -> dict[MoveArm, LaunchOptions]:
    for arm in raw:
        _require(arm in MOVE_ARMS, f"launch options name an arm of {list(MOVE_ARMS)}, got {arm!r}")
    return {
        arm: _launch_options(_object(raw[arm], f"the {arm} launch"), directory)
        for arm in MOVE_ARMS
        if arm in raw
    }


def _launch_options(raw: Json, directory: Path) -> LaunchOptions:
    for setting in raw:
        _require(
            setting in LAUNCH_SETTINGS,
            f"a launch option is one of {list(LAUNCH_SETTINGS)}, got {setting!r}",
        )
    values = {setting: _optional_text(raw, setting) for setting in LAUNCH_SETTINGS}
    file = values["user_instructions"]
    if file is not None:  # the declaration names a file beside it; the value is its text
        values["user_instructions"] = _beside(
            directory, file, "the user instruction file"
        ).read_text(encoding="utf-8")
    return LaunchOptions(**values)


# -- Arm changes ----------------------------------------------------------------------------


def _arm_changes(raw: Json, directory: Path) -> ArmChanges:
    by_arm = {arm: [_arm_change(c, directory) for c in _list(raw, arm)] for arm in raw}
    return ArmChanges.of(by_arm)  # refuses an unknown arm and a change on the full arm


def _arm_change(raw: object, directory: Path) -> ArmChange:
    change = _object(raw, "an arm change")
    op = _text(change, "op")
    path = RelPath.parse(_text(change, "path"))
    match op:
        case "write":
            source = _beside(directory, _text(change, "source"), "a write's source")
            return Write(path, source, hashlib.sha256(source.read_bytes()).hexdigest())
        case "remove":
            return Remove(path)
        case "derive":
            return _derive(change, path)
        case _:
            raise ValueError(f"an arm change is a write, remove or derive, got {op!r}")


def _derive(change: Json, path: RelPath) -> ArmChange:
    kind = _text(change, "kind")
    match kind:
        case "kernel":
            return KernelDerive(path, _texts(change, "lines"))
        case "manifest_row_removed":
            return ManifestRowRemoved(path)
        case "hook_registered":
            return HookRegistered(path)
        case "manifest_row_scoped":
            return ManifestRowScoped(path)
        case _:
            raise ValueError(
                f"a derive is kernel, manifest_row_removed, hook_registered or "
                f"manifest_row_scoped, got {kind!r}"
            )


def _beside(directory: Path, name: str, what: str) -> Path:
    """The file ``name`` in ``directory``; it exists and stays inside it."""
    file = (directory / name).resolve()
    _require(
        file.is_relative_to(directory.resolve()),
        f"{what} {name!r} lies outside the declaration's directory",
    )
    _require(file.is_file(), f"{what} {name!r} does not exist beside the declaration")
    return file


# -- Deliveries -----------------------------------------------------------------------------


def _delivery(raw: object) -> Delivery:
    delivery = _object(raw, "a delivery")
    channel = _text(delivery, "channel")
    match channel:
        case "session_start":
            return SessionStart(_rel(delivery, "file"), _texts(delivery, "lines", required=False))
        case "path_matched":
            return PathMatched(_rel(delivery, "file"), _texts(delivery, "globs"))
        case "hook_context":
            repeat = _text(delivery, "repeat")
            _require(repeat in ("each", "once"), f"a hook repeats each or once, got {repeat!r}")
            return HookContext(
                _text(delivery, "event"),
                _text(delivery, "matcher"),
                _rel(delivery, "reads"),
                repeat,  # type: ignore[arg-type]
            )
        case "gate_refusal":
            return GateRefusal(_text(delivery, "matcher"), _rel(delivery, "reads"))
        case "project_gating":
            return ProjectGating(_text(delivery, "kind"))
        case _:
            raise ValueError(f"a delivery channel is not {channel!r}")


# -- Reading values -------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object(value: object, what: str) -> Json:
    _require(isinstance(value, dict), f"{what} must be a JSON object")
    return value  # type: ignore[return-value]


def _field_object(raw: Json, key: str) -> Json:
    _require(key in raw, f"the field {key!r} is missing")
    return _object(raw[key], key)


def _text(raw: Json, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"the field {key!r} must be a string, got {value!r}")
    return value


def _optional_text(raw: Json, key: str) -> str | None:
    return None if raw.get(key) is None else _text(raw, key)


def _rel(raw: Json, key: str) -> RelPath:
    return RelPath.parse(_text(raw, key))


def _list(raw: Json, key: str) -> list[Any]:
    value = raw.get(key, [])
    _require(isinstance(value, list), f"the field {key!r} must be a list")
    return value


def _items(raw: Json, key: str) -> list[Any]:
    _require(key in raw, f"the field {key!r} is missing")
    return _list(raw, key)


def _texts(raw: Json, key: str, required: bool = True) -> tuple[str, ...]:
    values = _items(raw, key) if required else _list(raw, key)
    _require(all(isinstance(v, str) for v in values), f"the field {key!r} must list strings")
    return tuple(values)
