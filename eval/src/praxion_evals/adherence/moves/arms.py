"""Build and check a move's three arms over the runner's own copy of the checkout.

Each arm is a copy of the checkout with only that arm's declared changes applied: a ``write`` puts
the declared file in, a ``remove`` takes one out, and a ``derive`` computes a file from the
checkout's current content so the kit never holds a copy of it that could drift:

- ``kernel``: the moved rule's body lines that begin with each declared prefix, one line per
  prefix (a prefix matching none or two lines is refused), under the rule's own title line;
- ``manifest_row_removed``: the moved rule's manifest row, removed, or pointed at the arm's kernel
  file when it derives one (same id, core flag and install kind, so the project's rule disable list
  reaches the kernel exactly as it reached the rule);
- ``hook_registered``: the hook registry with the arm's written hook scripts registered under
  every declared hook-context delivery.

``plan`` is the one place an arm's expected files are computed; ``build`` applies it and
``check_copy`` compares a given copy against it, so the builder and the checker cannot disagree.
The checkout is only read.

A lean copy is then observed, never trusted from its declaration: what is resident at session
start comes from running the copy's own linker and rule injection, and the arm is refused when a
line of the moved rule is neither resident nor delivered by a declared channel (the move
relocates text, it never cuts it). A path-matched delivery is held to the file's own ``paths:``
frontmatter; the manifest row that would link it for a real session is not synthesised here.

Two more refusals close the build: the lean copy must reach every host without hooks as much of
the moved rule as the checkout does (``reach``), and the arms must run under equal competing
settings (``pinning``), which the arm set then carries as one value.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from praxion_evals.adherence.arms import ArmCopyError, verify_copy_diff
from praxion_evals.adherence.moves import observe, pinning, reach
from praxion_evals.adherence.moves.declaration import DeclarationError, check_sections
from praxion_evals.adherence.moves.model import (
    MOVE_ARMS,
    ArmChange,
    GateRefusal,
    HookContext,
    HookRegistered,
    KernelDerive,
    ManifestRowRemoved,
    MoveArm,
    MoveDeclaration,
    PathMatched,
    Pinned,
    ProjectGating,
    Remove,
    SessionStart,
    Write,
)
from praxion_evals.live.materialize import copy_listed

ORIGINAL_DIRNAME = "original"  # beside the arm copies; never an arm's name
HOOK_SCRIPT = re.compile(r"hooks/[^/]+\.py")
HOOK_TIMEOUT_SECONDS = 5
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ROW_START = "- id:"
_TITLE = "## "


class ArmError(ValueError):
    """An arm that cannot be built or a copy that is not its declaration; names the file or line."""


@dataclass(frozen=True)
class AppliedChange:
    path: str
    sha256: str | None  # the digest of the content the arm holds there; None for a removal


@dataclass(frozen=True)
class BuiltArm:
    """One arm's copy, its changes, and what its own copy has resident at session start."""

    copy: Path
    changes: tuple[AppliedChange, ...]
    session_start: tuple[str, ...]  # observed, not declared: what the take proof expects


@dataclass(frozen=True)
class ArmSet:
    arms: dict[MoveArm, BuiltArm]
    pinned: Pinned  # the one set of competing settings every arm runs under


@dataclass(frozen=True)
class ArmRefusal:
    reason: str


@dataclass(frozen=True)
class Planned:
    path: str
    content: bytes | None  # None: the arm removes the file

    @property
    def sha256(self) -> str | None:
        return None if self.content is None else hashlib.sha256(self.content).hexdigest()


def build(
    declaration: MoveDeclaration,
    checkout: Path,
    workspace: Path,
    *,
    model: str = pinning.DEFAULT_MODEL,
    effort: str = pinning.DEFAULT_EFFORT,
) -> ArmSet | ArmRefusal:
    """Copy ``checkout``'s tracked and unignored files once under ``workspace``, then copy that
    once per arm and apply the arm's declared changes.

    The ignored trees of a working checkout (linked worktrees, virtual environments, caches) never
    reach an arm, as they never reach a role's copy. The lean copy must still reach every hook-less
    host as the checkout does, and the arms must run under equal competing settings (``model`` and
    ``effort`` are the run's own).
    """
    original = workspace / ORIGINAL_DIRNAME
    made: list[Path] = [original]
    try:
        copy_listed(checkout, original)
        check_sections(declaration, original)
        plans = {arm: plan(declaration, arm, original) for arm in MOVE_ARMS}
        built: dict[MoveArm, BuiltArm] = {}
        for arm in MOVE_ARMS:
            made.append(workspace / arm)
            built[arm] = _build_arm(declaration, arm, plans[arm], original, workspace / arm)
        pinned = pinning.pin(
            declaration, {arm: built[arm].copy for arm in MOVE_ARMS}, model=model, effort=effort
        )
    except (
        DeclarationError,
        ArmError,
        reach.ReachError,
        pinning.PinningError,
        subprocess.CalledProcessError,
    ) as error:
        for copy in made:
            shutil.rmtree(copy, ignore_errors=True)
        return ArmRefusal(str(error))
    return ArmSet(built, pinned)


def check_copy(
    declaration: MoveDeclaration, arm: MoveArm, copy: Path, checkout: Path
) -> str | None:
    """The refusal the runner gives ``copy`` as ``arm``'s copy (None: it is exactly the declaration).

    Judged, as ``build`` judges it, against the checkout's tracked and unignored files.
    """
    with tempfile.TemporaryDirectory() as scratch:
        original = Path(scratch) / ORIGINAL_DIRNAME
        copy_listed(checkout, original)
        try:
            _verify_copy(original, copy, plan(declaration, arm, original))
        except ArmError as error:
            return str(error)
    return None


# -- What an arm's copy must hold -------------------------------------------------------------


def plan(declaration: MoveDeclaration, arm: MoveArm, checkout: Path) -> tuple[Planned, ...]:
    """The files ``arm`` changes and the content each must hold, computed from the checkout."""
    siblings = declaration.arms.for_arm(arm)
    return tuple(_planned(change, siblings, declaration, checkout) for change in siblings)


def _planned(
    change: ArmChange, siblings: Sequence[ArmChange], declaration: MoveDeclaration, checkout: Path
) -> Planned:
    match change:
        case Write(path=path, source=source, sha256=declared):
            content = _read_bytes(source)
            if hashlib.sha256(content).hexdigest() != declared:
                raise ArmError(f"{path.value}: its source {source} changed since it was declared")
            return Planned(path.value, content)
        case Remove(path=path):
            if not (checkout / path.value).is_file():
                raise ArmError(f"{path.value}: the arm removes a file the checkout does not hold")
            return Planned(path.value, None)
        case KernelDerive(path=path):
            return Planned(path.value, kernel_text(change, declaration, checkout).encode())
        case ManifestRowRemoved(path=path):
            return Planned(path.value, _manifest(path.value, siblings, declaration, checkout))
        case HookRegistered(path=path):
            return Planned(path.value, _hook_registry(path.value, siblings, declaration, checkout))
        case _:
            assert_never(change)


def kernel_text(change: KernelDerive, declaration: MoveDeclaration, checkout: Path) -> str:
    rule = declaration.moved_rule.value
    body = [line.rstrip() for line in _body(_read_text(checkout / rule)) if line.strip()]
    for prefix in change.prefixes:
        hits = sum(line.startswith(prefix) for line in body)
        if hits != 1:
            raise ArmError(
                f"{change.path.value}: the kernel prefix {prefix!r} matches {hits} lines of "
                f"{rule}, not one"
            )
    # The title stays: the Codex bridge refuses a rule file with no level-2 heading.
    title = next((line for line in body if line.startswith(_TITLE)), None)
    return "".join(
        f"{line}\n" for line in body if line == title or line.startswith(change.prefixes)
    )


def _manifest(
    path: str, siblings: Sequence[ArmChange], declaration: MoveDeclaration, checkout: Path
) -> bytes:
    moved = declaration.moved_rule.value
    kernels = [c for c in siblings if isinstance(c, KernelDerive)]
    if len(kernels) > 1:
        raise ArmError(f"{path}: the moved rule's row can point at one kernel, not {len(kernels)}")
    lines = _read_text(checkout / path).splitlines(keepends=True)
    start, end = _row_span(lines, moved, path)
    row = lines[start:end]
    if kernels:
        text = kernel_text(kernels[0], declaration, checkout)
        row = [_repoint(line, kernels[0].path.value, len(text)) for line in row]
    else:
        row = []
    return "".join([*lines[:start], *row, *lines[end:]]).encode()


def _row_span(lines: Sequence[str], rule: str, manifest: str) -> tuple[int, int]:
    starts = [i for i, line in enumerate(lines) if line.startswith(_ROW_START)]
    bounds = zip(starts, [*starts[1:], len(lines)], strict=True)
    for start, end in bounds:
        if f"  path: {rule}\n" in lines[start:end]:
            return start, end
    raise ArmError(f"{manifest}: the manifest holds no row for {rule}")


def _repoint(line: str, kernel: str, chars: int) -> str:
    if line.startswith("  path:"):
        return f"  path: {kernel}\n"
    if line.startswith("  chars:"):
        return f"  chars: {chars}\n"
    return line


def _hook_registry(
    path: str, siblings: Sequence[ArmChange], declaration: MoveDeclaration, checkout: Path
) -> bytes:
    scripts = hook_scripts(siblings)
    slots = (
        dict.fromkeys(  # one registration per event and matcher, however many deliveries share it
            (d.event, d.matcher) for d in declaration.deliveries if isinstance(d, HookContext)
        )
    )
    if not scripts or not slots:
        raise ArmError(
            f"{path}: a registration needs a written hook script (found {scripts}) "
            f"and a hook-context delivery (found {len(slots)})"
        )
    try:
        registry = json.loads(_read_text(checkout / path))
        for event, matcher in slots:
            registry["hooks"].setdefault(event, []).append(
                {"matcher": matcher, "hooks": [_command_hook(script) for script in scripts]}
            )
    except (ValueError, KeyError, AttributeError, TypeError) as error:
        raise ArmError(f"{path}: the hook registry cannot be extended: {error!r}") from error
    return (json.dumps(registry, indent=2) + "\n").encode()


def hook_scripts(changes: Sequence[ArmChange]) -> list[str]:
    """The hook scripts an arm writes into its copy."""
    return [
        c.path.value
        for c in changes
        if isinstance(c, Write) and HOOK_SCRIPT.fullmatch(c.path.value)
    ]


def _command_hook(script: str) -> dict[str, object]:
    return {
        "type": observe.COMMAND_HOOK,
        "command": f"python3 ${{CLAUDE_PLUGIN_ROOT}}/{script}",
        "timeout": HOOK_TIMEOUT_SECONDS,
    }


# -- Building and verifying one copy ----------------------------------------------------------


def _build_arm(
    declaration: MoveDeclaration,
    arm: MoveArm,
    planned: Sequence[Planned],
    checkout: Path,
    copy: Path,
) -> BuiltArm:
    if copy.exists():
        raise ArmError(f"{copy} already exists; an arm is built into a fresh directory")
    shutil.copytree(checkout, copy, symlinks=True)
    for change in planned:
        _apply(copy / change.path, change.content)
    _verify_copy(checkout, copy, planned)
    observed = observe.session_start(copy)
    if isinstance(observed, observe.Refused):
        raise ArmError(f"the {arm} arm's session start cannot be observed: {observed.reason}")
    if arm == "lean":
        reach.require_reach(declaration, checkout, copy, hook_scripts(declaration.arms.lean))
        _require_relocation(declaration, checkout, copy, observed.lines)
    _drop_bytecode(copy, checkout)
    changes = tuple(AppliedChange(change.path, change.sha256) for change in planned)
    return BuiltArm(copy, changes, observed.lines)


def _apply(target: Path, content: bytes | None) -> None:
    target.unlink(missing_ok=True)  # a link is replaced, never written through
    if content is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _verify_copy(checkout: Path, copy: Path, planned: Sequence[Planned]) -> None:
    try:
        verify_copy_diff(checkout, copy, expected=[change.path for change in planned])
    except ArmCopyError as error:
        raise ArmError(str(error)) from error
    for change in planned:
        target = copy / change.path
        if change.content is not None and (
            target.is_symlink() or target.read_bytes() != change.content
        ):
            raise ArmError(f"{change.path}: the copy does not hold the content the arm declares")


def _drop_bytecode(copy: Path, checkout: Path) -> None:
    """Observing runs the copy's hooks, which leave bytecode caches the checkout does not hold."""
    for cache in sorted(copy.rglob("__pycache__")):
        if not (checkout / cache.relative_to(copy)).exists():
            shutil.rmtree(cache, ignore_errors=True)


# -- A move relocates text, it never cuts it --------------------------------------------------


def _require_relocation(
    declaration: MoveDeclaration, checkout: Path, copy: Path, resident: Sequence[str]
) -> None:
    """Refuse a lean copy leaving a line of the moved rule neither resident nor delivered."""
    reached = {line.strip() for line in resident}
    for delivery in declaration.deliveries:
        match delivery:
            case SessionStart(file=file, lines=declared):
                expected = declared or _prose(file_lines(copy, file.value))
                _require_resident(file.value, expected, reached)
            case PathMatched(file=file, globs=globs):
                _require_path_scoped(copy, file.value, globs)
                reached.update(file_lines(copy, file.value))
            case HookContext(reads=file) | GateRefusal(reads=file):
                reached.update(file_lines(copy, file.value))
            case ProjectGating():
                pass
            case _:
                assert_never(delivery)
    rule = declaration.moved_rule.value
    for line in _prose(file_lines(checkout, rule)):
        if line not in reached:
            raise ArmError(
                f'the lean arm leaves this line of {rule} neither resident nor delivered: "{line}"'
            )


def _require_resident(file: str, expected: Sequence[str], reached: set[str]) -> None:
    for line in expected:
        if line not in reached:
            raise ArmError(
                f'{file} is declared resident but this line is not at session start: "{line}"'
            )


def _require_path_scoped(copy: Path, file: str, globs: Sequence[str]) -> None:
    match = _FRONTMATTER.match(_read_text(copy / file))
    scoped = match.group(1) if match else ""
    missing = [glob for glob in globs if glob not in scoped]
    if not re.search(r"^paths\s*:", scoped, re.MULTILINE) or missing:
        raise ArmError(
            f"{file} is declared path-matched but its paths: frontmatter lacks {missing or globs}"
        )


# -- Reading ----------------------------------------------------------------------------------


def file_lines(root: Path, relpath: str) -> list[str]:
    """The non-blank lines of a rule file's body, stripped; a file the copy lacks is a refusal."""
    return [line.strip() for line in _body(_read_text(root / relpath)) if line.strip()]


def _prose(lines: Sequence[str]) -> list[str]:
    return [line for line in lines if not line.startswith("#")]


def _body(text: str) -> list[str]:
    return _FRONTMATTER.sub("", text, count=1).splitlines()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        raise ArmError(f"{path} cannot be read: {error}") from error


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ArmError(f"{path} cannot be read: {error}") from error
