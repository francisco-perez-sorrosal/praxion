"""Which git repository owns `.ai-state/`? -- the single answer, for every consumer.

Under sidecar placement `.ai-state/` is a relative symlink into a **state
mount**: a real directory at `<checkout>/.praxion/` that is a `git worktree` of
a separate sidecar repository. Consumers that stage, commit or rename state
files must therefore run git against the mount, not the project -- and must
refuse outright when the shadow dangles or leads somewhere that is not this
project's sidecar. `resolve_placement()` answers with a four-variant sum type
so each of those cases is named and carries its evidence;
`require_writable_placement()` narrows it to the two writable variants and
raises, so a state-mutating caller cannot silently take the permissive path.

Discovery is stdlib-only and subprocess-free on both happy paths: an `InRepo`
project costs one `lstat`, and a mounted one costs a handful of file reads
(the mount's `.git` pointer, its `HEAD`, the manifest, the project's git
config). That budget is load-bearing -- this module is imported by finalize
scripts and session hooks in consumer projects whose interpreter may lack
PyYAML entirely, which is also why the manifest is read with a line parser for
the frozen `{schema, project.id, project.origin}` triple and nothing more.
Widening to the full manifest is a deliberate, separate call into
`_sidecar_manifest.py`, which may import PyYAML because its callers can.

Imported (not executed) as a sibling module -- `scripts/` is on `sys.path[0]`
for every script that lives beside it, exactly like `_repo_root.py`.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Union

__all__ = [
    "Dangling",
    "Foreign",
    "ForeignReason",
    "InRepo",
    "Placement",
    "SidecarIdentity",
    "SidecarOwned",
    "UnwritablePlacementError",
    "WritablePlacement",
    "require_writable_placement",
    "resolve_placement",
]

_STATE_DIR_NAME = ".ai-state"
_GIT_ENTRY_NAME = ".git"
_GITDIR_KEY = "gitdir"
_WORKTREES_SEGMENT = "worktrees"
_HEAD_REF_PREFIX = "ref: refs/heads/"
_MANIFEST_NAME = "praxion-sidecar.yaml"
_SCHEMA_KEY = "schema"
_PROJECT_KEY = "project"
_SUPPORTED_SCHEMA = 1
_NULL_SCALARS = frozenset({"", "null", "~"})


class ForeignReason(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11; see the `Placement` note
    """Why a resolved shadow is not this project's state sidecar (closed set)."""

    NO_MANIFEST = "no-manifest"
    MANIFEST_UNREADABLE = "manifest-unreadable"
    SCHEMA_TOO_NEW = "schema-too-new"
    IDENTITY_MISMATCH = "identity-mismatch"
    NOT_A_GIT_REPO = "not-a-git-repo"
    UNRECOGNIZED_MOUNT = "unrecognized-mount"


@dataclasses.dataclass(frozen=True)
class SidecarIdentity:
    """The frozen manifest triple -- exactly what the line parser can always read.

    Never a manifest: the fields a hot-path reader cannot produce would be
    indistinguishable from legitimately-absent ones.
    """

    schema: int
    id: str
    origin: str | None


@dataclasses.dataclass(frozen=True)
class InRepo:
    """`.ai-state/` is an ordinary directory -- the project owns its own state."""

    project_root: Path
    state_dir: Path
    state_git_root: Path


@dataclasses.dataclass(frozen=True)
class SidecarOwned:
    """`.ai-state/` shadows a state mount that belongs to this project's sidecar.

    `state_git_root` is the **mount**, never the sidecar root outside the
    checkout: git refuses paths beyond a symlink, so every `git -C` for state
    runs here, with mount realpaths. `sidecar_common_dir` identifies the
    sidecar across all of its worktrees and is the only field that points
    outside `project_root`.
    """

    project_root: Path
    state_dir: Path
    mount_dir: Path
    state_git_root: Path
    sidecar_common_dir: Path
    branch: str
    identity: SidecarIdentity


@dataclasses.dataclass(frozen=True)
class Dangling:
    """The shadow is a symlink whose target does not exist.

    Usually an unmaterialised mount awaiting the SessionStart heal -- a
    recoverable state, which is why it is distinct from `Foreign`.
    `link_path` is the shadow resolved as far as the filesystem allows;
    `link_target` is the target the symlink itself records, made absolute.
    """

    project_root: Path
    link_path: Path
    link_target: Path


@dataclasses.dataclass(frozen=True)
class Foreign:
    """The shadow resolves, but not into this project's sidecar.

    `resolved_target` is the mount slot that was inspected and refused -- the
    directory the reason is about, whereas `link_path` is the resolved shadow
    itself.
    """

    project_root: Path
    link_path: Path
    resolved_target: Path
    reason: ForeignReason


# `Union`, not `X | Y`: a runtime alias in that form needs 3.10, and this module
# is imported by git hooks in consumer projects whose interpreter Praxion does
# not choose (`scripts/**` targets 3.9+ -- see the per-file-ignores note in
# `pyproject.toml`). The same constraint keeps `ForeignReason` off `StrEnum`.
Placement = Union[InRepo, SidecarOwned, Dangling, Foreign]  # noqa: UP007
WritablePlacement = Union[InRepo, SidecarOwned]  # noqa: UP007


class UnwritablePlacementError(RuntimeError):
    """A state-mutating caller asked for a placement that must not be written to."""


def resolve_placement(project_root: Path) -> Placement:
    """Classify who owns `<project_root>/.ai-state/`.

    Readers may degrade on `Dangling` / `Foreign`; writers call
    `require_writable_placement()` instead. Every returned path is fully
    resolved here, once, so consumers compare resolver-supplied paths with
    each other and never have to get macOS `/System/Volumes/Data` aliasing
    right independently.
    """
    root = project_root.resolve()
    slot = root / _STATE_DIR_NAME
    if not slot.is_symlink():
        return InRepo(project_root=root, state_dir=slot, state_git_root=root)

    link_path = slot.resolve()
    if not link_path.exists():
        return Dangling(project_root=root, link_path=link_path, link_target=_readlink(slot))
    try:
        return _sidecar_owned(root, link_path)
    except _MountRefusalError as refusal:
        return Foreign(
            project_root=root,
            link_path=link_path,
            resolved_target=link_path.parent,
            reason=refusal.reason,
        )


def require_writable_placement(project_root: Path) -> WritablePlacement:
    """`resolve_placement()` for state-mutating callers -- raises on the error variants.

    The obligation lives in the API rather than in a convention each caller
    remembers: there is no way to reach a `Dangling` or `Foreign` placement
    through this entry point and write into it anyway.
    """
    placement = resolve_placement(project_root)
    if isinstance(placement, (InRepo, SidecarOwned)):
        return placement
    if isinstance(placement, Dangling):
        raise UnwritablePlacementError(
            f"{_STATE_DIR_NAME} is dangling: {placement.link_path} does not exist "
            f"(recorded target {placement.link_target})"
        )
    raise UnwritablePlacementError(
        f"{_STATE_DIR_NAME} resolves to {placement.link_path}, which is not this "
        f"project's state sidecar ({placement.reason.value}): {placement.resolved_target}"
    )


class _MountRefusalError(Exception):
    """Internal signal carrying the `Foreign` reason to report; never escapes."""

    def __init__(self, reason: ForeignReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _sidecar_owned(root: Path, link_path: Path) -> SidecarOwned:
    """Build `SidecarOwned`, or raise `_MountRefusalError` with the reason to report.

    The in-checkout realpath invariant is asserted here rather than assumed:
    the mount must be inside the project root (this is what keeps Claude
    Code's worktree isolation and the containment guards correct without
    modification) and the sidecar common dir must be outside it.
    """
    mount_dir = link_path.parent
    if not _is_inside(mount_dir, root):
        raise _MountRefusalError(ForeignReason.UNRECOGNIZED_MOUNT)
    per_worktree_dir, sidecar_common_dir = _mount_layout(mount_dir)
    if _is_inside(sidecar_common_dir, root):
        raise _MountRefusalError(ForeignReason.UNRECOGNIZED_MOUNT)
    branch = _worktree_branch(per_worktree_dir)
    identity, roots = _read_identity(sidecar_common_dir / _MANIFEST_NAME)
    _require_identity_match(root, identity, roots)
    return SidecarOwned(
        project_root=root,
        state_dir=link_path,
        mount_dir=mount_dir,
        state_git_root=mount_dir,
        sidecar_common_dir=sidecar_common_dir,
        branch=branch,
        identity=identity,
    )


def _mount_layout(mount_dir: Path) -> tuple[Path, Path]:
    """The mount's `(per-worktree git dir, sidecar common dir)`.

    `<mount>/.git` is a pointer file reading `gitdir: <sidecar>/.git/worktrees/
    <name>`; stripping the trailing two segments yields the common dir. A
    readable pointer of any other shape is refused rather than guessed at. The
    `git rev-parse` fallback runs only when the entry cannot be read as text
    at all -- a `.git` *directory*, or a permission error -- so it never costs
    a subprocess on the path this module is imported for.
    """
    git_entry = mount_dir / _GIT_ENTRY_NAME
    if not git_entry.exists():
        raise _MountRefusalError(ForeignReason.NOT_A_GIT_REPO)
    pointer_text = _read_text(git_entry)
    if pointer_text is None:
        layout = _mount_layout_via_git(mount_dir)
    else:
        gitdir = _gitdir_target(pointer_text, mount_dir)
        layout = None if gitdir is None else _split_linked_worktree(gitdir)
    if layout is None:
        raise _MountRefusalError(ForeignReason.UNRECOGNIZED_MOUNT)
    return layout


def _gitdir_target(pointer_text: str, base: Path) -> Path | None:
    """The absolute `gitdir:` target of a worktree `.git` pointer file."""
    key, separator, target = pointer_text.strip().partition(":")
    if key.strip() != _GITDIR_KEY or not separator or not target.strip():
        return None
    return _absolute(Path(target.strip()), base)


def _split_linked_worktree(gitdir: Path) -> tuple[Path, Path] | None:
    """Split `<common>/worktrees/<name>` into its two halves, or None."""
    if gitdir.parent.name != _WORKTREES_SEGMENT:
        return None
    return gitdir, gitdir.parent.parent


def _mount_layout_via_git(mount_dir: Path) -> tuple[Path, Path] | None:
    """The documented fallback -- correct, and deliberately never the primary path.

    `git rev-parse` walks *up* out of an unreadable mount and would happily
    answer for the project repository the mount sits inside, so the reported
    toplevel must be the mount itself, and its git dir must differ from its
    common dir (a standalone repo is not a sidecar worktree), before the
    answer is trusted.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel", "--git-dir", "--git-common-dir"],
            cwd=str(mount_dir),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 3:
        return None
    toplevel, git_dir, common_dir = (_absolute(Path(line.strip()), mount_dir) for line in lines)
    if toplevel != mount_dir.resolve() or git_dir == common_dir:
        return None
    return git_dir, common_dir


def _worktree_branch(per_worktree_dir: Path) -> str:
    """This checkout's sidecar branch, from the mount's own `HEAD`.

    A detached mount has no branch to name, and `link` never creates one, so
    it is refused rather than represented as an empty string.
    """
    head_text = _read_text(per_worktree_dir / "HEAD")
    if head_text is None or not head_text.startswith(_HEAD_REF_PREFIX):
        raise _MountRefusalError(ForeignReason.UNRECOGNIZED_MOUNT)
    return head_text.strip()[len(_HEAD_REF_PREFIX) :]


def _read_identity(manifest_path: Path) -> tuple[SidecarIdentity, list[str]]:
    """The frozen triple plus `roots:`, refusing on any parse difficulty.

    Order is the evolution contract, not a preference: `schema` is read and
    an unsupported value refused **before** any other line is trusted, so a
    future layout that relocated `project.id` cannot make this parser return a
    confident wrong identity -- the successful-but-wrong parse that
    "any difficulty means foreign" would not catch.
    """
    text = _read_text(manifest_path)
    if text is None:
        reason = (
            ForeignReason.MANIFEST_UNREADABLE
            if manifest_path.exists()
            else ForeignReason.NO_MANIFEST
        )
        raise _MountRefusalError(reason)
    schema = _parse_schema(text)
    if schema is None:
        raise _MountRefusalError(ForeignReason.MANIFEST_UNREADABLE)
    if schema != _SUPPORTED_SCHEMA:
        raise _MountRefusalError(ForeignReason.SCHEMA_TOO_NEW)
    project = _parse_project_block(text)
    project_id = _scalar(project.get("id", ""))
    if not project_id:
        raise _MountRefusalError(ForeignReason.MANIFEST_UNREADABLE)
    identity = SidecarIdentity(schema=schema, id=project_id, origin=_scalar(project.get("origin")))
    return identity, _flow_list(project.get("roots", ""))


def _require_identity_match(root: Path, identity: SidecarIdentity, roots: list[str]) -> None:
    """Compare recorded identity against the project -- never re-derive it.

    Two identity kinds need two comparisons: for a project with a remote,
    recorded origin versus observed origin; for a remote-less one, `origin` is
    null on both sides and would never mismatch, so membership of the
    project's realpath in the recorded `roots:` is the only anchor there.
    """
    if identity.origin is not None:
        observed = _observed_origin(root)
        if observed is None or observed != _normalize_origin(identity.origin):
            raise _MountRefusalError(ForeignReason.IDENTITY_MISMATCH)
        return
    if root not in {Path(recorded).resolve() for recorded in roots}:
        raise _MountRefusalError(ForeignReason.IDENTITY_MISMATCH)


def _observed_origin(project_root: Path) -> str | None:
    """This project's normalized `remote.origin.url`, read from its git config."""
    common_dir = _project_git_common_dir(project_root)
    if common_dir is None:
        return None
    url = _remote_origin_url(common_dir)
    return _normalize_origin(url) if url else None


def _project_git_common_dir(project_root: Path) -> Path | None:
    """The project's git common dir -- where remotes live, in a worktree too."""
    git_entry = project_root / _GIT_ENTRY_NAME
    if git_entry.is_dir():
        return git_entry
    pointer_text = _read_text(git_entry)
    if pointer_text is None:
        return None
    gitdir = _gitdir_target(pointer_text, project_root)
    if gitdir is None:
        return None
    linked = _split_linked_worktree(gitdir)
    return linked[1] if linked is not None else gitdir


def _remote_origin_url(git_common_dir: Path) -> str | None:
    """`remote.origin.url` from `.git/config`, with a line reader.

    Not `configparser`: git indents its keys, which configparser reads as
    continuation lines of the preceding section header and rejects.
    """
    text = _read_text(git_common_dir / "config")
    if text is None:
        return None
    in_origin = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_origin = stripped.replace('"', "").replace(" ", "").lower() == "[remoteorigin]"
            continue
        name, separator, value = stripped.partition("=")
        if in_origin and separator and name.strip() == "url":
            return value.strip()
    return None


def _normalize_origin(url: str) -> str | None:
    """Normalize a remote URL so SSH and HTTPS forms of one repo compare equal.

    Drops the scheme, credentials, a `.git` suffix and trailing slashes:
    `git@github.com:acme/billing` and `https://github.com/acme/billing.git`
    both become `github.com/acme/billing`.

    Case is folded across the **whole** result, not just the host. The
    recorded identity is derived once, sanitized to lowercase, and a remote
    re-added as `git@github.com:ACME/Billing.git` names the same repository on
    every host Praxion targets -- so preserving path case would refuse a
    legitimate project's every state write, which is the more expensive of the
    two errors here (the false match it admits needs two repositories on one
    host differing only in capitalisation).
    """
    text = url.strip()
    if not text:
        return None
    if "://" in text:
        text = text.partition("://")[2]
    elif ":" in text and not text.startswith("/"):
        text = text.replace(":", "/", 1)
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    host, separator, path = text.partition("/")
    if "@" in host:
        host = host.partition("@")[2]
    normalized = f"{host}/{path}" if separator else host
    return normalized.lower()


def _parse_schema(text: str) -> int | None:
    """The top-level `schema:` value as an int, or None when unusable."""
    for line in _top_level_lines(text):
        name, separator, value = line.partition(":")
        if separator and name.strip() == _SCHEMA_KEY:
            raw = _scalar(value)
            return int(raw) if raw is not None and raw.lstrip("-").isdigit() else None
    return None


def _parse_project_block(text: str) -> dict[str, str]:
    """The indented keys under the **top-level** `project:` mapping.

    Keyed on indentation so a `project:` renested under some other key in a
    future schema is not mistaken for this one -- which is what makes reading
    `schema` first a real refusal rather than a formality.
    """
    fields: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():
            inside = line.partition(":")[0].strip() == _PROJECT_KEY
            continue
        if inside:
            name, separator, value = line.strip().partition(":")
            if separator:
                fields[name.strip()] = value
    return fields


def _top_level_lines(text: str) -> list[str]:
    """Unindented, non-comment, non-blank lines."""
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line[:1].isspace() and not line.lstrip().startswith("#")
    ]


def _scalar(raw: str | None) -> str | None:
    """A YAML scalar the line parser can trust: unquoted, uncommented, null-aware."""
    if raw is None:
        return None
    value = raw.strip()
    if value[:1] in ("'", '"'):
        closing = value.find(value[0], 1)
        value = value[: closing + 1] if closing != -1 else value
    else:
        value = value.partition("#")[0].strip()
    if value.lower() in _NULL_SCALARS:
        return None
    return _unquote(value)


def _flow_list(raw: str) -> list[str]:
    """The items of a `[a, b]` flow sequence; anything else is an empty list."""
    text = raw.strip()
    start = text.find("[")
    end = text.find("]", start + 1)
    if start == -1 or end == -1:
        return []
    return [_unquote(item.strip()) for item in text[start + 1 : end].split(",") if item.strip()]


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _read_text(path: Path) -> str | None:
    """File contents, or None when the path cannot be read as text at all."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _readlink(link: Path) -> Path:
    """The recorded symlink target, made absolute against the link's directory."""
    return _absolute(Path(os.readlink(link)), link.parent)


def _absolute(path: Path, base: Path) -> Path:
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _is_inside(path: Path, ancestor: Path) -> bool:
    return path == ancestor or ancestor in path.parents
