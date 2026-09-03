"""DS-7 project identity -- the one place a sidecar slug is derived.

Identity answers "which sidecar does this checkout belong to". It is computed
**once, at `praxion-sidecar init`**, recorded in the manifest, and thereafter
only ever *compared* (`_state_repo.py` compares; it never derives). A second
derivation site would be a second source of truth waiting to disagree the
first time an operator changes a remote URL.

Two kinds, because two populations need two anchors:

    ProjectId = OriginDerived { url, host, owner, repo }   -- github.com--acme--billing
              | PathDerived   { hash }                     -- local--<sha256(realpath)[:12]>

`OriginDerived` normalizes `remote.origin.url` so the SSH and HTTPS spellings
of one repository land on one slug. `PathDerived` is the remote-less fallback,
hashed off the **main worktree's** realpath so every linked worktree of one
project resolves to the same sidecar -- the property that makes the mount
lifecycle work at all.

Normalization is not re-implemented here: `_state_repo._normalize_origin` is
the existing owner of "SSH and HTTPS spell the same repo", and it is the
function the resolver's own identity comparison runs. Deriving through a
second normalizer would let `init` record a slug the resolver later refuses.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Union

import _state_repo

# The sanitized alphabet (DS-7). `/` becomes `--` *before* this runs, so the
# separator survives it; every other disallowed run collapses to a single `-`.
_DISALLOWED_RUN = re.compile(r"[^a-z0-9._-]+")
_ID_ALLOWED = re.compile(r"\A[a-z0-9._-]+\Z")
_PATH_SEPARATOR = "--"

# Enough hex to make a collision between two checkouts on one machine a
# non-event, short enough to stay a readable directory name.
_PATH_HASH_LENGTH = 12
_LOCAL_PREFIX = "local--"

# A slug is a directory name under `${PRAXION_SIDECAR_ROOT}`; these two would
# escape it even though every character is on the allowlist.
_RESERVED_IDS = frozenset({".", ".."})

# `host/owner/repo` -- the minimum a normalized origin must yield before it can
# name a repository rather than merely a server.
_MIN_ORIGIN_SEGMENTS = 3


class InvalidProjectId(ValueError):  # noqa: N818 - a rejected value, not a runtime failure
    """A project id that may not be used as a sidecar directory name.

    `.reason` is the machine-readable enforcement-point identifier, matching
    `_sidecar_manifest.ManifestError`'s shape; the message is for the operator.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class OriginDerived:
    """Identity anchored on `remote.origin.url`.

    `url` is the remote **verbatim**, because that is what the manifest
    records and what the resolver re-normalizes for its comparison; the three
    normalized components exist so `slug()` never has to re-parse it.
    """

    url: str
    host: str
    owner: str
    repo: str

    def __post_init__(self) -> None:
        if not (self.url and self.host and self.owner and self.repo):
            raise InvalidProjectId(
                "origin-incomplete",
                f"`{self.url}` does not name a repository (host/owner/repo)",
            )


@dataclasses.dataclass(frozen=True)
class PathDerived:
    """Identity for a remote-less project: a hash of the main worktree realpath."""

    hash: str

    def __post_init__(self) -> None:
        if not re.fullmatch(rf"[0-9a-f]{{{_PATH_HASH_LENGTH}}}", self.hash):
            raise InvalidProjectId(
                "path-hash-malformed",
                f"`{self.hash}` is not a {_PATH_HASH_LENGTH}-character lowercase hex digest",
            )


# `Union`, not `X | Y`: a runtime alias in that form needs 3.10, and `scripts/`
# targets 3.9+ -- the same constraint `_state_repo.Placement` documents.
ProjectId = Union[OriginDerived, PathDerived]  # noqa: UP007


def derive_project_id(project_root: Path) -> ProjectId:
    """Derive `project_root`'s identity. Called once, at `init`.

    A configured `remote.origin.url` that normalizes to at least
    `host/owner/repo` yields `OriginDerived`; anything else -- no remote, or a
    remote naming only a server -- falls back to the path hash, so a project
    always has exactly one identity rather than an error state at `init`.
    """
    main_root = main_worktree_root(project_root)
    origin = _configured_origin(project_root)
    if origin is not None:
        normalized = _state_repo._normalize_origin(origin)  # noqa: SLF001 -- see module docstring
        components = _split_normalized(normalized)
        if components is not None:
            host, owner, repo = components
            return OriginDerived(url=origin, host=host, owner=owner, repo=repo)
    digest = hashlib.sha256(str(main_root).encode("utf-8")).hexdigest()
    return PathDerived(hash=digest[:_PATH_HASH_LENGTH])


def slug(project_id: ProjectId) -> str:
    """The sidecar directory name for `project_id` (DS-7's sanitized form)."""
    if isinstance(project_id, PathDerived):
        return f"{_LOCAL_PREFIX}{project_id.hash}"
    return sanitize(f"{project_id.host}/{project_id.owner}/{project_id.repo}")


def recorded_origin(project_id: ProjectId) -> str | None:
    """What `project.origin` holds in the manifest: the remote verbatim, or null.

    Verbatim rather than normalized because the resolver normalizes *both*
    sides before comparing -- recording the normalized form would throw away
    the only spelling an operator can recognise in a `status` report.
    """
    return project_id.url if isinstance(project_id, OriginDerived) else None


def main_worktree_root(project_root: Path) -> Path:
    """The realpath of the project's **main** worktree, for any checkout of it.

    Every linked worktree shares one git common dir, so its parent is the main
    worktree -- which is why all worktrees of one project derive one identity
    without any of them having to know it is not the main one.
    """
    common_dir = _state_repo._project_git_common_dir(project_root)  # noqa: SLF001
    if common_dir is None:
        raise InvalidProjectId(
            "not-a-git-checkout",
            f"`{project_root}` has no readable git directory",
        )
    return common_dir.parent.resolve()


def validate_id_override(raw: str) -> str:
    """Check an operator-supplied `--id <slug>` before it names a directory.

    Validated, never silently sanitized: `--id Acme/Billing` quietly becoming
    `acme--billing` would hand back a slug the operator did not ask for, and
    the whole point of the escape hatch is that they chose it.
    """
    candidate = raw.strip()
    if not candidate or not _ID_ALLOWED.match(candidate) or candidate in _RESERVED_IDS:
        raise InvalidProjectId(
            "id-not-sanitized",
            f"--id {raw} is not a valid sidecar id (allowed: lowercase a-z, 0-9, `.`, `_`, `-`)",
        )
    return candidate


def sanitize(text: str) -> str:
    """DS-7's sanitizer: lowercase, `/` -> `--`, every other disallowed run -> `-`."""
    lowered = text.lower().replace("/", _PATH_SEPARATOR)
    return _DISALLOWED_RUN.sub("-", lowered)


def _configured_origin(project_root: Path) -> str | None:
    """`remote.origin.url` as configured, read from the git common dir."""
    common_dir = _state_repo._project_git_common_dir(project_root)  # noqa: SLF001
    if common_dir is None:
        return None
    url = _state_repo._remote_origin_url(common_dir)  # noqa: SLF001
    return url or None


def _split_normalized(normalized: str | None) -> tuple[str, str, str] | None:
    """`host/owner/repo` from a normalized origin, or None when it names no repo.

    A nested group (`gitlab.com/team/sub/billing`) keeps its depth in `owner`,
    so the slug stays a faithful, collision-free rendering of the path.
    """
    if not normalized:
        return None
    segments = [segment for segment in normalized.split("/") if segment]
    if len(segments) < _MIN_ORIGIN_SEGMENTS:
        return None
    return segments[0], "/".join(segments[1:-1]), segments[-1]
