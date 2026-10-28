"""The settings that compete with a moved rule, held equal in every arm.

The harness's own commit-attribution instruction, the model, the effort and the rendered user
instruction file all bear on whether a session follows a rule, so an arm that differed in any of
them would measure that difference and call it the move. ``pin`` resolves each arm's four settings
(a declared launch option, else the entry's default), renders each arm's user instructions the way
a session sandbox does, and returns the one ``Pinned`` value the arms share, or refuses naming the
first setting two arms differ in. The returned value being single is the invariant: unequal arms
have no representation downstream.

A session sandbox holds only the rendered user instructions and the arm's plugin directory. A
``MEMORY.md`` anywhere in it is an index the session would read as one more instruction source, so
a sandbox carrying one is refused.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

from praxion_evals.adherence.moves.model import (
    MOVE_ARMS,
    LaunchOptions,
    MoveArm,
    MoveDeclaration,
    Pinned,
)
from praxion_evals.live.materialize import install_user_scope
from praxion_evals.live.session import SandboxPaths

DEFAULT_ATTRIBUTION = "harness default"  # the competing instruction users actually face
DEFAULT_MODEL = "opus"  # the adherence entry's defaults
DEFAULT_EFFORT = "medium"
MEMORY_INDEX = "MEMORY.md"
RENDERED_INSTRUCTIONS = "CLAUDE.md"
STDERR_TAIL_CHARS = 300
DIGEST_CHARS = 12

_LABELS = {
    "commit_attribution": "commit-attribution setting",
    "model": "model",
    "effort": "effort",
    "user_instructions": "user instruction file",
}


class PinningError(ValueError):
    """Arms that differ in a pinned setting, or a sandbox holding a memory index; names which."""


def pin(
    declaration: MoveDeclaration,
    copies: Mapping[MoveArm, Path],
    *,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
) -> Pinned:
    """The settings every arm runs under, or a refusal naming the setting two arms differ in."""
    entry = Pinned(DEFAULT_ATTRIBUTION, model, effort, "entry default")
    with tempfile.TemporaryDirectory(prefix="moves-pin-") as scratch:
        resolved: dict[MoveArm, Pinned] = {}
        for arm in MOVE_ARMS:
            if arm in copies:
                options = declaration.launch[arm]
                resolved[arm] = _resolve(options, copies[arm], Path(scratch) / arm, entry, arm)
    return require_equal(resolved)


def require_equal(pinned: Mapping[MoveArm, Pinned]) -> Pinned:
    """The one value every arm shares; the first arm in ``MOVE_ARMS`` order is the reference."""
    reference_arm: MoveArm = next(arm for arm in MOVE_ARMS if arm in pinned)
    reference = pinned[reference_arm]
    for arm, other in pinned.items():
        differing = reference.differences(other)
        if differing:
            setting = differing[0]
            raise PinningError(
                f"the {arm} and {reference_arm} arms differ in the {_LABELS[setting]}: "
                f"{_shown(setting, getattr(other, setting))} against "
                f"{_shown(setting, getattr(reference, setting))}"
            )
    return reference


def require_no_memory(home: Path, arm: MoveArm) -> None:
    """Refuse a sandbox home carrying a memory index anywhere under it."""
    found = sorted(home.rglob(MEMORY_INDEX))
    if found:
        raise PinningError(
            f"the {arm} arm's sandbox carries a {MEMORY_INDEX} ({found[0]}), "
            "an instruction source that is not pinned"
        )


# -- Resolving one arm ------------------------------------------------------------------------


def _resolve(
    options: LaunchOptions, copy: Path, scratch: Path, entry: Pinned, arm: MoveArm
) -> Pinned:
    paths = SandboxPaths(scratch)
    _install(copy, scratch, arm)
    require_no_memory(paths.home, arm)
    instructions = options.user_instructions
    if instructions is None:
        instructions = (paths.config_dir / RENDERED_INSTRUCTIONS).read_text(encoding="utf-8")
    return Pinned(
        options.attribution or entry.commit_attribution,
        options.model or entry.model,
        options.effort or entry.effort,
        hashlib.sha256(instructions.encode()).hexdigest(),
    )


def _install(copy: Path, scratch: Path, arm: MoveArm) -> None:
    """Populate a sandbox home as the session sandbox does; the user instructions render here."""
    try:
        install_user_scope(copy, scratch)
    except subprocess.CalledProcessError as error:
        tail = error.stderr.decode(errors="replace").strip()[-STDERR_TAIL_CHARS:]
        raise PinningError(
            f"the {arm} arm's user instructions cannot be rendered: exited {error.returncode}: {tail}"
        ) from error
    except OSError as error:
        raise PinningError(f"the {arm} arm's sandbox cannot be built: {error}") from error


def _shown(setting: str, value: str) -> str:
    return value[:DIGEST_CHARS] if setting == "user_instructions" else value
