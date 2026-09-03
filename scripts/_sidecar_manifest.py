"""Sidecar manifest smart constructor -- the single full-YAML reader/writer of
`praxion-sidecar.yaml` (`SYSTEMS_PLAN.md` DS-2).

`load_manifest()` is the *only* place in the codebase that parses the full
manifest; `_state_repo.py`'s stdlib line parser reads only the frozen
`{schema, project.id, project.origin}` triple, on the hot path, in consumer
interpreters that may lack PyYAML. This module is the deliberate, separate
widening a caller reaches for when it needs `paths`/`autocommit`/`remote` --
never imported by a hook or finalize script.

`yaml` is imported lazily, inside `_require_yaml()`, rather than at module
scope: a consumer interpreter without PyYAML must get a named, actionable
`ManifestError` (naming `sys.executable` and the install fix) the moment
this module's widening is actually reached, never a raw
`ModuleNotFoundError` traceback surfacing out of a bare `import yaml` at
import time (IF-17).

`Manifest` is constructible only through `load_manifest()`: every invariant
DS-2 names (closed enums, the `PathEntry` intent-discriminated sum, the
`_NEVER_SHADOW` ancestor rule, excludes/shadow/share disjointness, the
on-disk `kind` cross-check, the schema-first evolution contract) is enforced
at exactly one site inside the parse, and a violation raises `ManifestError`
with a named `.reason` rather than defaulting or repairing silently.

The manifest lives at `<sidecar-common-dir>/praxion-sidecar.yaml` -- the
sidecar's git *common* directory, never inside a mount's tracked working
tree (DS-2's location amendment): a tracked manifest would appear inside
every worktree with a machine-local `roots:` list, generating cross-branch
merge conflicts the common directory does not have.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import yaml

__all__ = [
    "NEVER_SHADOW",
    "SHADOWABLE_PATHS",
    "Autocommit",
    "Intent",
    "Manifest",
    "ManifestError",
    "PathEntry",
    "ProjectIdentity",
    "PushPolicy",
    "RemoteConfig",
    "ShadowEntry",
    "ShadowKind",
    "ShareEntry",
    "UntouchedEntry",
    "UntouchedReason",
    "block_target",
    "load_manifest",
    "manifest_path",
    "write_manifest",
]

_MANIFEST_FILENAME = "praxion-sidecar.yaml"
_SUPPORTED_SCHEMA = 1
_CLAUDE_MD_PATH = "CLAUDE.md"
_CLAUDE_LOCAL_MD_PATH = "CLAUDE.local.md"

# Illegal shadow targets and their ancestors (DS-2): shadowing `.claude` itself
# (or `.git`, `.praxion`, the repo root) would ask a consumer to symlink a
# directory something else depends on being real -- Claude Code refuses
# worktree creation when `.claude` is a symlink. `.praxion` is the state mount
# itself, so shadowing it would ask the mount to link into its own contents.
NEVER_SHADOW = frozenset({".claude", ".git", ".", ".praxion"})

# The D8 CLI allowlist, reused here as the ancestor-rule carve-out: a path on
# this list may be shadowed even when a `NEVER_SHADOW` member is its ancestor,
# because only the leaf becomes a symlink -- `.claude/settings.local.json`
# leaves `.claude/` itself a real directory.
SHADOWABLE_PATHS = frozenset(
    {
        ".ai-state",
        "CLAUDE.md",
        "CLAUDE.local.md",
        ".claude/settings.local.json",
        "docs/architecture.md",
        "architecture/",
        "fitness/",
    }
)


class Intent(str, Enum):  # noqa: UP042 -- StrEnum needs 3.11; scripts/ targets 3.9+
    """The one placement decision per `paths:` entry (DS-2)."""

    SHADOW = "shadow"
    SHARE = "share"
    UNTOUCHED = "untouched"


class ShadowKind(str, Enum):  # noqa: UP042
    DIR = "dir"
    FILE = "file"


class UntouchedReason(str, Enum):  # noqa: UP042
    PREEXISTING_TEAM_FILE = "preexisting-team-file"
    OPERATOR_CHOICE = "operator-choice"


class Autocommit(str, Enum):  # noqa: UP042
    ON_FINALIZE_AND_STOP = "on-finalize-and-stop"
    ON_FINALIZE = "on-finalize"
    MANUAL = "manual"


class PushPolicy(str, Enum):  # noqa: UP042
    NEVER = "never"
    ON_AUTOCOMMIT = "on-autocommit"


class ManifestError(Exception):
    """A refusal from the manifest smart constructor.

    `.reason` is the machine-readable, named enforcement-point identifier;
    the exception message is the human-readable explanation.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ShadowEntry:
    """`intent: shadow` -- a symlink into the sidecar plus its own exclude entry."""

    kind: ShadowKind


@dataclass(frozen=True)
class ShareEntry:
    """`intent: share` -- Praxion writes it and it is committed in the project."""


@dataclass(frozen=True)
class UntouchedEntry:
    """`intent: untouched` -- no Praxion writer may target this path."""

    reason: UntouchedReason | None = None


# A flat `PathEntry{intent, kind, reason}` record would make `{intent: share,
# kind: file}` representable and catch it only by scattered validation
# (DS-2). `Union`, not `X | Y`: a runtime alias in that form needs 3.10, and
# scripts/ targets 3.9+ -- same reasoning as `_state_repo.py`'s `Placement`.
PathEntry = Union[ShadowEntry, ShareEntry, UntouchedEntry]  # noqa: UP007


@dataclass(frozen=True)
class ProjectIdentity:
    origin: str | None
    id: str
    roots: list[Path]


@dataclass(frozen=True)
class RemoteConfig:
    """A nullable *object*, never an object with a nullable `url` (DS-2):
    `{url: null, push: on-autocommit}` would parse cleanly and mean nothing."""

    url: str
    push: PushPolicy
    foreign_host_ack: bool = False


@dataclass(frozen=True)
class Manifest:
    schema: int
    project: ProjectIdentity
    paths: dict[str, PathEntry]
    excludes: list[str]
    autocommit: Autocommit
    remote: RemoteConfig | None


def manifest_path(sidecar_common_dir: Path) -> Path:
    """The manifest's fixed location: `<sidecar-common-dir>/praxion-sidecar.yaml`."""
    return sidecar_common_dir / _MANIFEST_FILENAME


def _require_yaml() -> ModuleType:
    """Import PyYAML, or raise a named, actionable `ManifestError`.

    The interpreter running a hook or the finalize chain may not have PyYAML
    installed (they never reach this module); an interpreter that reaches
    for the manifest's full parse -- `praxion-sidecar`'s own entry point,
    chiefly -- must instead. A raw `ModuleNotFoundError` traceback here would
    both violate the "loud, named failure" promise and, for a hook shelling
    out with `#!/usr/bin/env python3`, no-op silently (IF-17).
    """
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise ManifestError(
            "pyyaml-missing",
            f"PyYAML is not installed for {sys.executable} -- install it into that "
            "interpreter (`python3 -m pip install pyyaml`), or re-run this command "
            "with the interpreter the Praxion plugin ships (its own venv, when one "
            "exists).",
        ) from error
    return yaml


def load_manifest(path: Path) -> Manifest:
    """Parse, validate and return the manifest at `path`, or raise `ManifestError`.

    `schema` is read and refused first, before any other key is trusted
    (DS-2's evolution contract) -- a future schema that relocated a field
    must not let this parser succeed with a confident wrong result.
    """
    yaml = _require_yaml()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    schema = _require_schema(data)

    # `path` is `<sidecar_root>/.git/praxion-sidecar.yaml`; the sidecar's
    # working tree -- where the on-disk `kind` cross-check looks -- is two
    # levels up.
    sidecar_root = path.parent.parent
    project = _parse_project(data.get("project") or {})
    paths = _parse_paths(data.get("paths") or {}, sidecar_root=sidecar_root)
    excludes = [str(entry) for entry in (data.get("excludes") or [])]
    _require_excludes_disjoint(excludes, paths)
    autocommit = _parse_enum(Autocommit, data.get("autocommit"), field_name="autocommit")
    remote = _parse_remote(data.get("remote"))

    return Manifest(
        schema=schema,
        project=project,
        paths=paths,
        excludes=excludes,
        autocommit=autocommit,
        remote=remote,
    )


def write_manifest(path: Path, manifest: Manifest) -> None:
    """Serialize `manifest` to `path`, atomically.

    `sort_keys=False` on a hand-ordered dict keeps `schema` the first key and
    `project.{origin,id,roots}` top level under `project` -- the frozen
    triple's positional stability, which is what lets the stdlib line parser
    in `_state_repo.py` trust its own reading of the same file.
    """
    yaml = _require_yaml()
    _register_flow_sequence_representer(yaml)
    data = {
        "schema": manifest.schema,
        "project": {
            "origin": manifest.project.origin,
            "id": manifest.project.id,
            "roots": _FlowSequence(str(root) for root in manifest.project.roots),
        },
        "paths": {relpath: _dump_path_entry(entry) for relpath, entry in manifest.paths.items()},
        "excludes": list(manifest.excludes),
        "autocommit": manifest.autocommit.value,
        "remote": _dump_remote(manifest.remote),
    }
    _write_atomic(path, yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def block_target(manifest: Manifest, project_root: Path, path: str = _CLAUDE_MD_PATH) -> Path:
    """Where a Praxion block writer for `path` must write (DS-8).

    `CLAUDE.md` is the only path with a fallback: `untouched` redirects to the
    shadowed `CLAUDE.local.md` (the team's tracked file is never touched);
    `shadow`/`share` both target `CLAUDE.md` itself. Every other path has no
    redirect -- an `untouched` intent there means no Praxion writer may target
    it at all, so this raises rather than silently picking a location.
    """
    entry = manifest.paths.get(path)
    if path == _CLAUDE_MD_PATH:
        if isinstance(entry, UntouchedEntry):
            return project_root / _CLAUDE_LOCAL_MD_PATH
        return project_root / _CLAUDE_MD_PATH
    if isinstance(entry, UntouchedEntry):
        raise ManifestError(
            "path-is-untouched",
            f"`{path}` is `untouched` -- no Praxion writer may target it "
            f"(only `{_CLAUDE_MD_PATH}` has a fallback redirect)",
        )
    return project_root / path


# --- Loader internals --------------------------------------------------------


def _require_schema(data: dict) -> int:
    if "schema" not in data:
        raise ManifestError("schema-missing", "manifest is missing the required `schema` key")
    schema = data["schema"]
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise ManifestError(
            "schema-not-integer", "`schema` must be an integer, e.g. `schema: 1`, not a string"
        )
    if schema != _SUPPORTED_SCHEMA:
        raise ManifestError(
            "schema-unsupported",
            f"manifest schema {schema} is not supported by this version of praxion-sidecar -- "
            "upgrade the plugin to a version that supports this schema",
        )
    return schema


def _parse_project(raw: dict) -> ProjectIdentity:
    project_id = raw.get("id")
    if not project_id:
        raise ManifestError("project-id-missing", "`project.id` is required and must not be empty")
    roots = [Path(str(root)) for root in (raw.get("roots") or [])]
    return ProjectIdentity(origin=raw.get("origin"), id=project_id, roots=roots)


def _parse_paths(raw: dict, *, sidecar_root: Path) -> dict[str, PathEntry]:
    return {
        relpath: _build_path_entry(relpath, entry_raw or {}, sidecar_root=sidecar_root)
        for relpath, entry_raw in raw.items()
    }


def _build_path_entry(relpath: str, raw: dict, *, sidecar_root: Path) -> PathEntry:
    intent = _parse_enum(Intent, raw.get("intent"), field_name="intent")
    has_kind = "kind" in raw

    if intent is Intent.SHADOW:
        if not has_kind:
            raise ManifestError(
                "kind-required", f"`{relpath}`: shadow entries require a `kind` (dir|file)"
            )
        kind = _parse_enum(ShadowKind, raw["kind"], field_name="kind")
        if _is_illegal_shadow_path(relpath):
            raise ManifestError(
                "illegal-shadow-path",
                f"`{relpath}` may never be shadowed -- it is, or is inside, a path that must "
                "stay a real directory",
            )
        _require_kind_matches_on_disk(sidecar_root, relpath, kind)
        return ShadowEntry(kind=kind)

    if has_kind:
        raise ManifestError(
            "kind-not-allowed",
            f"`{relpath}`: `kind` is only valid for shadow entries, not `{intent.value}`",
        )
    if intent is Intent.SHARE:
        return ShareEntry()

    reason_raw = raw.get("reason")
    reason = (
        _parse_enum(UntouchedReason, reason_raw, field_name="reason")
        if reason_raw is not None
        else None
    )
    return UntouchedEntry(reason=reason)


def _is_illegal_shadow_path(relpath: str) -> bool:
    """The `_NEVER_SHADOW` ancestor rule, carved out for `SHADOWABLE_PATHS`.

    Illegal iff `relpath` itself is a `NEVER_SHADOW` member, or a strict
    ancestor of `relpath` is -- unless `relpath` is itself allowlisted, which
    is what lets `.claude/settings.local.json` shadow while `.claude` cannot:
    only the leaf becomes a symlink, `.claude/` stays a real directory.
    """
    if relpath in NEVER_SHADOW:
        return True
    if relpath in SHADOWABLE_PATHS:
        return False
    segments = relpath.split("/")
    ancestors = ("/".join(segments[:depth]) for depth in range(1, len(segments)))
    return any(ancestor in NEVER_SHADOW for ancestor in ancestors)


def _require_kind_matches_on_disk(sidecar_root: Path, relpath: str, kind: ShadowKind) -> None:
    """Cross-check `kind` against the sidecar's on-disk entry, when one exists.

    `link` needs `kind` *before* the target exists, to know whether to
    materialize a dir or file symlink -- so absence is accepted, not refused.
    A present-but-wrong-shaped entry is the boolean-blind field this schema
    is otherwise designed to avoid, so it is refused.
    """
    target = sidecar_root / relpath
    if not target.exists():
        return
    is_dir = target.is_dir()
    if (kind is ShadowKind.DIR) != is_dir:
        on_disk = "directory" if is_dir else "file"
        raise ManifestError(
            "kind-mismatch-on-disk",
            f"`{relpath}` is declared `kind: {kind.value}` but the sidecar's on-disk entry "
            f"is a {on_disk}",
        )


def _require_excludes_disjoint(excludes: list[str], paths: dict[str, PathEntry]) -> None:
    """`excludes:` lists NON-shadow exclusions only (DS-2 / CH-03).

    A `share` path in `excludes:` would be listed in the generated
    `.git/info/exclude` block, git would ignore it, and the file Praxion was
    told to share would be silently never committed -- the sharp case this
    disjointness enforces.
    """
    exclude_set = set(excludes)
    shadow_paths = {relpath for relpath, entry in paths.items() if isinstance(entry, ShadowEntry)}
    overlap_shadow = exclude_set & shadow_paths
    if overlap_shadow:
        raise ManifestError(
            "excludes-overlap-shadow",
            f"`excludes:` lists {sorted(overlap_shadow)}, already a shadow path -- shadow "
            "paths are excluded automatically and must not be listed again",
        )
    share_paths = {relpath for relpath, entry in paths.items() if isinstance(entry, ShareEntry)}
    overlap_share = exclude_set & share_paths
    if overlap_share:
        raise ManifestError(
            "excludes-overlap-share",
            f"`excludes:` lists {sorted(overlap_share)}, a `share` path -- excluding it would "
            "silently stop it from ever being committed",
        )


def _parse_remote(raw: dict | None) -> RemoteConfig | None:
    if raw is None:
        return None
    url = raw.get("url")
    if url is None:
        raise ManifestError(
            "remote-url-required", "`remote.url` is required when `remote` is not null"
        )
    push = _parse_enum(PushPolicy, raw.get("push"), field_name="remote.push")
    return RemoteConfig(
        url=url, push=push, foreign_host_ack=bool(raw.get("foreign_host_ack", False))
    )


def _parse_enum(enum_cls: type[Enum], raw_value: object, *, field_name: str) -> Enum:
    """A closed-enum field: refuse an unrecognized value rather than default.

    Shared across all five closed-enum fields (`intent`, `kind`, `reason`,
    `autocommit`, `remote.push`) -- the failure mode is identical, so one
    named reason (`unknown-enum-value`) serves all of them (DS-2).
    """
    if raw_value is not None:
        try:
            return enum_cls(raw_value)
        except ValueError:
            pass
    valid = ", ".join(member.value for member in enum_cls)
    raise ManifestError(
        "unknown-enum-value",
        f"`{field_name}: {raw_value}` is not recognized (expected one of: {valid})",
    )


# --- Writer internals ---------------------------------------------------------


# `roots` is DS-7's only identity anchor for a remote-less project and must
# stay parseable by `_state_repo.py`'s stdlib reader (belt: `_flow_list`
# understands `[a, b]` directly; braces: it also now reads a block sequence,
# but flow keeps the written file maximally simple either way). A marker
# subclass plus a one-off representer forces flow style on just this one
# list, without flipping the whole document (which stays block-style, per
# the frozen triple's positional-stability contract).
class _FlowSequence(list):
    """Marker: serialize this list flow-style even in a block-style document."""


def _represent_flow_sequence(dumper: yaml.Dumper, data: _FlowSequence) -> yaml.Node:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", list(data), flow_style=True)


_flow_sequence_representer_registered = False


def _register_flow_sequence_representer(yaml: ModuleType) -> None:
    """Register `_FlowSequence`'s one-off representer, once.

    Deferred alongside the rest of PyYAML's usage (`_require_yaml()`) rather
    than run at module import time -- registration needs the `yaml` module
    object, which a consumer interpreter lacking PyYAML must never be forced
    to import just to load this module (IF-17). Idempotent: `write_manifest`
    calls this on every invocation, and `add_representer` tolerates being
    called twice with the same mapping.
    """
    global _flow_sequence_representer_registered
    if _flow_sequence_representer_registered:
        return
    yaml.SafeDumper.add_representer(_FlowSequence, _represent_flow_sequence)
    _flow_sequence_representer_registered = True


def _dump_path_entry(entry: PathEntry) -> dict:
    if isinstance(entry, ShadowEntry):
        return {"intent": Intent.SHADOW.value, "kind": entry.kind.value}
    if isinstance(entry, ShareEntry):
        return {"intent": Intent.SHARE.value}
    result: dict = {"intent": Intent.UNTOUCHED.value}
    if entry.reason is not None:
        result["reason"] = entry.reason.value
    return result


def _dump_remote(remote: RemoteConfig | None) -> dict | None:
    if remote is None:
        return None
    return {
        "url": remote.url,
        "push": remote.push.value,
        "foreign_host_ack": remote.foreign_host_ack,
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` via a same-directory temp file + `os.replace`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
