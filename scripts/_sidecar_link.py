"""Shadow-symlink projection into the state mount (DS-5 / DS-6).

``link()`` drives two things from one call, in a fixed order that is
itself a safety property: the **mount** (``_sidecar_mount.py``'s real
``git worktree`` at ``<checkout>/.praxion``) and the **projection** of its
paths onto ``.ai-state``, ``CLAUDE.local.md``,
``.claude/settings.local.json``, and ``CLAUDE.md`` when shadowed.

The exclude block is written *before* the mount exists -- a mount that
survives even one ``git add -A`` unexcluded records a gitlink in the
project's index, shipping a broken submodule reference on the next push.
Shadow targets are relative (``.praxion/.ai-state``, or one level down
``../.praxion/settings.local.json``) so every shadow's realpath resolves
*inside* its own checkout, never into whichever mount happens to sit at
that relative path in a different one.

There is no unlink branch: a shadow is created only from an ``Absent``
slot; anything else lands in ``LinkResult.skipped``, untouched -- the
property that keeps a ``post-checkout`` hook firing on every branch switch
from churning the tree, since a clean re-run performs zero writes.

Sequence: classify the mount (refuse before any write if something
foreign occupies it); rewrite ``info/exclude`` in the *common* git dir if
it would change; create the mount if ``Absent``; create shadow symlinks
from ``Absent`` slots; converge state branches, main checkout only.
Gathering and computing run unconditionally; every effect is gated behind
one ``if not dry_run``.
"""

from __future__ import annotations

import dataclasses
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Union

import _sidecar_git as gitp
import _sidecar_manifest
import _sidecar_mount
from _git_runner import git_output, run_git

# Runs of characters git ref names forbid (whitespace, `~^:?*[\`) or a `..`
# run -- collapsed to a single `-` by `_sanitize_branch_component`. Not a
# complete ref-name validator by itself; `git check-ref-format` is.
_ILLEGAL_REF_RUN = re.compile(r"[\s~^:?*\[\\]+|\.\.+")

__all__ = [
    "Absent",
    "LinkElsewhere",
    "LinkRefused",
    "LinkResult",
    "LinkToThisSidecar",
    "RealPath",
    "ShadowSlotState",
    "classify_shadow_slot",
    "exclude_lines",
    "link",
    "remove_exclude_block",
    "rewrite_exclude_block",
    "shadow_target",
    "sidecar_branch_for",
]

_MAIN_BRANCH = "main"
_WORKTREE_BRANCH_PREFIX = "wt/"
_BLOCK_START = "# >>> praxion:sidecar >>>"
_BLOCK_END = "# <<< praxion:sidecar <<<"


class LinkRefused(Exception):  # noqa: N818 - a refusal to act, not a failure mid-operation
    """A checkout's mount slot cannot be claimed; nothing was written."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- ShadowSlotState (DS-6) ---


@dataclasses.dataclass(frozen=True)
class Absent:
    """Nothing occupies the shadow slot -- the only state ``link()`` acts on."""


@dataclasses.dataclass(frozen=True)
class LinkToThisSidecar:
    """Already a correct relative symlink into this mount -- a no-op."""


@dataclasses.dataclass(frozen=True)
class LinkElsewhere:
    """A symlink occupies the slot, pointing somewhere other than this mount."""

    target: str


@dataclasses.dataclass(frozen=True)
class RealPath:
    """A real file or directory occupies the slot."""

    kind: str  # "file" | "dir"


# `Union`, not `X | Y`: this module is imported under the 3.9 floor
# `pyproject.toml` pins for `scripts/` -- same reasoning as `_sidecar_mount.py`.
ShadowSlotState = Union[Absent, LinkToThisSidecar, LinkElsewhere, RealPath]  # noqa: UP007


def shadow_target(relpath: str) -> str:
    """The relative symlink target for a shadow slot at ``relpath``: one
    ``../`` per directory level before the leaf, so it always resolves
    inside the checkout (``.ai-state`` -> ``.praxion/.ai-state``;
    ``.claude/settings.local.json`` -> ``../.praxion/settings.local.json``).
    """
    parts = Path(relpath).parts
    climb = "../" * (len(parts) - 1)
    return f"{climb}{_sidecar_mount.MOUNT_DIRNAME}/{parts[-1]}"


def classify_shadow_slot(checkout: Path, relpath: str, expected_target: str) -> ShadowSlotState:
    """Name whatever occupies ``<checkout>/<relpath>``, comparing the
    symlink's raw target *string* -- never its resolved realpath, so an
    absolute symlink that happens to point at the right file is still
    ``LinkElsewhere`` (see the module docstring).
    """
    slot = Path(checkout) / relpath
    if slot.is_symlink():
        target = os.readlink(slot)
        return LinkToThisSidecar() if target == expected_target else LinkElsewhere(target=target)
    if not slot.exists():
        return Absent()
    return RealPath(kind="dir" if slot.is_dir() else "file")


# --- sidecar_branch_for ---


def _linked_worktree_git_dir(checkout: Path) -> Path | None:
    """The project's own per-worktree git dir, or ``None`` for a main
    checkout -- a real ``.git`` directory can't be read as a pointer file,
    which is the same signal that distinguishes it from a linked worktree.
    """
    return gitp.read_gitdir_pointer(Path(checkout) / ".git")


def _sanitize_branch_component(name: str) -> str:
    """Best-effort mapping of a checkout directory name onto a git ref-name
    component: illegal runs collapse to one ``-``, repeats of ``-``
    collapse further, and a leading ``-``/``.`` is stripped. Not a
    guarantee -- a name that is entirely illegal characters can still
    collapse to empty; the caller validates the result.
    """
    sanitized = _ILLEGAL_REF_RUN.sub("-", name)
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    return sanitized.lstrip(".")


def _is_valid_branch_name(checkout: Path, candidate: str) -> bool:
    """Whether git itself accepts ``candidate`` as a branch name."""
    if not candidate:
        return False
    return run_git(checkout, "check-ref-format", "--branch", candidate).returncode == 0


def sidecar_branch_for(checkout: Path) -> str:
    """The sidecar branch this checkout's mount belongs on.

    ``main`` for the main checkout; ``wt/<checkout-dir-name>`` for a linked
    worktree, mirroring the project's own worktree-directory naming --
    sanitised and validated against git's own ref-name rules first, since a
    worktree directory name is operator-chosen and not itself constrained
    to be a legal ref-name component.
    """
    checkout = Path(checkout)
    if _linked_worktree_git_dir(checkout) is None:
        return _MAIN_BRANCH
    candidate = f"{_WORKTREE_BRANCH_PREFIX}{_sanitize_branch_component(checkout.name)}"
    if not _is_valid_branch_name(checkout, candidate):
        raise LinkRefused(
            f"{checkout.name!r} cannot be turned into a valid sidecar branch name "
            f"(tried {candidate!r})"
        )
    return candidate


def _base_sidecar_branch(checkout: Path) -> str:
    """The sidecar branch mounted in the checkout this worktree was created
    from -- read via ``.git`` pointer files and the mount's own ``HEAD``,
    never git-invoked. Falls back to ``main`` (always correct) when the
    base checkout or its mount can't be identified this way.
    """
    worktree_git_dir = _linked_worktree_git_dir(checkout)
    if worktree_git_dir is None:
        return _MAIN_BRANCH
    project_common_dir = gitp.common_dir_of_worktree(worktree_git_dir)
    if project_common_dir is None:
        return _MAIN_BRANCH
    base_checkout = project_common_dir.parent
    base_mount_git_dir = gitp.read_gitdir_pointer(
        base_checkout / _sidecar_mount.MOUNT_DIRNAME / ".git"
    )
    if base_mount_git_dir is None:
        return _MAIN_BRANCH
    return gitp.head_branch(base_mount_git_dir) or _MAIN_BRANCH


def _current_project_branch(checkout: Path) -> str | None:
    """This checkout's current git branch, or ``None`` when detached.

    ``HEAD`` is not a stable identity -- it tracks whatever the project
    checkout has checked out at classification time, not the branch that
    existed when the mount was created -- so a detached checkout gets no
    mapping at all (``None``) rather than the misleading literal ``"HEAD"``.
    """
    branch = git_output(checkout, "rev-parse", "--abbrev-ref", "HEAD")
    return None if branch in (None, "HEAD") else branch


def _clear_project_branch_mapping(sidecar_root: Path, branch: str) -> None:
    """Undo ``create_mount``'s branch-config write for a detached-HEAD
    project checkout: ``create_mount`` always records *some* value, so this
    removes it afterward, leaving the branch with genuinely no mapping --
    which ``_sidecar_mount``'s own classifier already reports as
    ``MappingMissing`` rather than a misleadingly-resolvable one.
    """
    key = gitp.branch_config_key(branch, _sidecar_mount.PROJECT_BRANCH_CONFIG_SUFFIX)
    run_git(sidecar_root, "config", "--unset", key)


# --- .git/info/exclude (DS-5) ---


def _split_block(text: str) -> tuple[str, str]:
    """``text`` split into (before the block, after the block). The one
    trailing newline right after the end marker is consumed as part of the
    block, so ``before + block + after`` never doubles up at the seam.
    """
    start = text.find(_BLOCK_START)
    if start == -1:
        return text, ""
    end = text.find(_BLOCK_END, start)
    if end == -1:
        return text[:start], ""
    end += len(_BLOCK_END)
    after = text[end:]
    if after.startswith("\n"):
        after = after[1:]
    return text[:start], after


def _build_block(lines: Sequence[str]) -> str:
    body = "\n".join(lines)
    return f"{_BLOCK_START}\n{body}\n{_BLOCK_END}\n"


def _compute_new_exclude_text(exclude_path: Path, lines: Sequence[str]) -> tuple[str, str]:
    """The exclude file's current text and what it would become -- a pure
    read, so a caller can decide whether a write is needed before making one.
    """
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    before, after = _split_block(existing)
    if before and not before.endswith("\n"):
        before += "\n"
    return existing, before + _build_block(lines) + after


def rewrite_exclude_block(exclude_path: Path, lines: Sequence[str]) -> bool:
    """Replace the ``praxion:sidecar`` block in ``exclude_path`` wholesale.

    A no-op (no write, ``False``) when the file already holds exactly this
    block; content outside the markers is preserved byte for byte.
    """
    exclude_path = Path(exclude_path)
    existing, new_text = _compute_new_exclude_text(exclude_path, lines)
    if exclude_path.exists() and new_text == existing:
        return False
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    exclude_path.write_text(new_text, encoding="utf-8")
    return True


def remove_exclude_block(exclude_path: Path) -> bool:
    """Delete the ``praxion:sidecar`` block, leaving every other line
    untouched. ``False`` when the file has no such block.
    """
    exclude_path = Path(exclude_path)
    if not exclude_path.exists():
        return False
    existing = exclude_path.read_text(encoding="utf-8")
    if _BLOCK_START not in existing:
        return False
    before, after = _split_block(existing)
    if before and not before.endswith("\n"):
        before += "\n"
    exclude_path.write_text(before + after, encoding="utf-8")
    return True


def exclude_lines(manifest: _sidecar_manifest.Manifest) -> list[str]:
    """The ``praxion:sidecar`` exclude lines, in order: ``/.praxion/``
    first, then one anchored entry per ``shadow`` path (``share`` and
    ``untouched`` are never excluded), then the manifest's own
    ``excludes:`` verbatim.
    """
    lines = [f"/{_sidecar_mount.MOUNT_DIRNAME}/"]
    lines.extend(
        f"/{relpath}"
        for relpath, entry in manifest.paths.items()
        if isinstance(entry, _sidecar_manifest.ShadowEntry)
    )
    lines.extend(manifest.excludes)
    return lines


def _project_common_git_dir(checkout: Path) -> Path:
    """The git directory shared by every worktree of ``checkout``'s
    project -- a main checkout's own ``.git``, or a linked worktree's
    derived from its ``.git`` pointer -- so a write here lands in the one
    ``info/exclude`` every worktree honours.
    """
    worktree_git_dir = _linked_worktree_git_dir(checkout)
    if worktree_git_dir is None:
        return Path(checkout) / ".git"
    common_dir = gitp.common_dir_of_worktree(worktree_git_dir)
    return common_dir if common_dir is not None else Path(checkout) / ".git"


def _foreign_mount_reason(checkout: Path, state: _sidecar_mount.StateMountState) -> str:
    mount = Path(checkout) / _sidecar_mount.MOUNT_DIRNAME
    if isinstance(state, _sidecar_mount.ForeignDir):
        return f"{mount} cannot be used as the state mount: {state.reason}"
    if isinstance(state, _sidecar_mount.ForeignRepo):
        return (
            f"{mount} cannot be used as the state mount: it is a worktree of {state.git_common_dir}"
        )
    return f"{mount} cannot be used as the state mount"


def _ensure_real_parent_dir(checkout: Path, relpath: str) -> None:
    """``mkdir -p`` a shadow slot's parent as a real directory (DS-6): it
    must never itself become a symlink, or the checkout's ``.claude`` (say)
    would stop being the real directory Claude Code requires.
    """
    (Path(checkout) / relpath).parent.mkdir(parents=True, exist_ok=True)


# --- LinkResult ---


@dataclasses.dataclass(frozen=True)
class LinkResult:
    """What a ``link()`` run did, or would do under ``dry_run``. ``refused``
    is reserved for a future per-slot refusal channel -- today every
    refusal is whole-mount and raises ``LinkRefused`` instead, so this is
    always empty.
    """

    created_mount: bool = False
    linked: list[str] = dataclasses.field(default_factory=list)
    skipped: list[tuple[str, ShadowSlotState]] = dataclasses.field(default_factory=list)
    exclude_changed: bool = False
    refused: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class _LinkPlan:
    """Everything ``link()`` needs to decide, gathered by pure reads so a
    dry run and a real run agree on the same answer: built once by
    ``_plan_link``, applied only by a real run's ``_apply_link``.
    """

    created_mount: bool
    exclude_path: Path
    new_exclude_text: str
    exclude_changed: bool
    shadow_entries: list[tuple[str, _sidecar_manifest.PathEntry]]
    slot_states: dict[str, ShadowSlotState]


def _plan_link(
    checkout: Path, sidecar_root: Path, manifest: _sidecar_manifest.Manifest
) -> _LinkPlan:
    """Classify the mount and every shadow slot; compute the exclude
    block's would-be text. Raises ``LinkRefused`` before anything is
    written when the mount slot is foreign.
    """
    expected_common_dir = (sidecar_root / ".git").resolve()
    mount_state = _sidecar_mount.classify_mount(checkout, expected_common_dir=expected_common_dir)
    if isinstance(mount_state, (_sidecar_mount.ForeignDir, _sidecar_mount.ForeignRepo)):
        raise LinkRefused(_foreign_mount_reason(checkout, mount_state))

    exclude_path = _project_common_git_dir(checkout) / "info" / "exclude"
    existing_exclude, new_exclude_text = _compute_new_exclude_text(
        exclude_path, exclude_lines(manifest)
    )
    shadow_entries = [
        (relpath, entry)
        for relpath, entry in manifest.paths.items()
        if isinstance(entry, _sidecar_manifest.ShadowEntry)
    ]
    slot_states = {
        relpath: classify_shadow_slot(checkout, relpath, shadow_target(relpath))
        for relpath, _entry in shadow_entries
    }
    return _LinkPlan(
        created_mount=isinstance(mount_state, _sidecar_mount.Absent),
        exclude_path=exclude_path,
        new_exclude_text=new_exclude_text,
        exclude_changed=not (exclude_path.exists() and new_exclude_text == existing_exclude),
        shadow_entries=shadow_entries,
        slot_states=slot_states,
    )


def _apply_link(
    plan: _LinkPlan,
    checkout: Path,
    sidecar_root: Path,
    create_mount_fn: Callable[..., None],
    converge_fn: Callable[..., object],
) -> None:
    """Every write ``link()``'s plan calls for, in the module docstring's
    fixed order: exclude block before mount, mount before shadows,
    convergence last and only for the main checkout.
    """
    if plan.exclude_changed:
        plan.exclude_path.parent.mkdir(parents=True, exist_ok=True)
        plan.exclude_path.write_text(plan.new_exclude_text, encoding="utf-8")
    if plan.created_mount:
        branch = sidecar_branch_for(checkout)
        base_branch = None if branch == _MAIN_BRANCH else _base_sidecar_branch(checkout)
        project_branch = _current_project_branch(checkout)
        create_mount_fn(
            sidecar_root,
            checkout,
            branch,
            project_branch=project_branch or "HEAD",
            base_branch=base_branch,
        )
        if project_branch is None:
            _clear_project_branch_mapping(sidecar_root, branch)
    for relpath, entry in plan.shadow_entries:
        if isinstance(plan.slot_states[relpath], Absent):
            _ensure_real_parent_dir(checkout, relpath)
            target_is_dir = entry.kind == _sidecar_manifest.ShadowKind.DIR
            (checkout / relpath).symlink_to(shadow_target(relpath), target_is_dir)
    if _linked_worktree_git_dir(checkout) is None:
        converge_fn(sidecar_root, checkout, checkout, dry_run=False)


def link(
    checkout: Path,
    sidecar_root: Path,
    manifest: _sidecar_manifest.Manifest,
    *,
    converge: Callable[..., object] | None = None,
    dry_run: bool = False,
    create_mount: Callable[..., None] | None = None,
) -> LinkResult:
    """Mount and project the sidecar into ``checkout``. ``_plan_link``
    always runs; ``_apply_link`` runs only when ``not dry_run``, so a dry
    run reports the exact shape a real run would produce without writing a
    byte. ``create_mount``/``converge`` default to
    ``_sidecar_mount.create_mount``/``_sidecar_mount.converge``; tests
    inject doubles to observe call-time ordering.
    """
    checkout = Path(checkout)
    sidecar_root = Path(sidecar_root)
    plan = _plan_link(checkout, sidecar_root, manifest)

    if not dry_run:
        create_mount_fn = create_mount if create_mount is not None else _sidecar_mount.create_mount
        converge_fn = converge if converge is not None else _sidecar_mount.converge
        _apply_link(plan, checkout, sidecar_root, create_mount_fn, converge_fn)

    linked = [
        relpath
        for relpath, _entry in plan.shadow_entries
        if isinstance(plan.slot_states[relpath], Absent)
    ]
    skipped = [
        (relpath, plan.slot_states[relpath])
        for relpath, _entry in plan.shadow_entries
        if not isinstance(plan.slot_states[relpath], Absent)
    ]
    return LinkResult(
        created_mount=plan.created_mount,
        linked=linked,
        skipped=skipped,
        exclude_changed=plan.exclude_changed,
        refused=[],
    )
