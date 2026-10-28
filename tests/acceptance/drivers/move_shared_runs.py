"""One computation of an expensive move outcome per test session, shared by every worker.

The root suite runs `-n auto --dist load`, so a module-scoped fixture runs again on every xdist
worker that receives one of that module's tests; each re-run of a move journey or an arm build
costs minutes. `share` computes an outcome once per session instead: the first caller holds a
file lock on the outcome's key, computes it for real in its own directories, and publishes the
result and the files the computation added to the directories it watches; every later caller with
the same key finds the entry and replays it into its own directories.

The key is every input the outcome depends on: the caller's `inputs` (the move, the run
arguments, the stand-in script) and a content digest of each watched directory as the call finds
it (the checkout, the stand-in's configuration and launch log). Two calls with different inputs
never share an entry, and a replay hands the caller its own copies of every file, with the
spelling of the producer's paths swapped for the caller's.

The entries live beside the pytest base temp every worker of one session shares: the parent of
a worker's base temp (`popen-gwN`) under xdist, the base temp itself otherwise. A caller whose
directories sit under no such base temp computes its outcome unshared.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHARED_DIR = "move-shared-runs"
_XDIST_BASETEMP = re.compile(r"popen-gw\d+")
_PLAIN_BASETEMP = re.compile(r"pytest-\d+")
_GIT_DIR = ".git"

# A snapshot maps a path relative to a watched root to ("dir", ""), ("link", target) or
# ("file", sha256 of the file's text with the root spellings tokenised).
Snapshot = dict[str, tuple[str, str]]


@dataclass(frozen=True)
class Roles:
    """Named paths whose spelling differs between callers, and the tokens that stand for them."""

    paths: Mapping[str, Path]

    def _spellings(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for role, path in self.paths.items():
            literal, real = str(path), str(path.resolve())
            pairs.append((f"@@{role}@@", literal))
            if real != literal:
                pairs.append((f"@@{role}-real@@", real))
        # A longer spelling first: one path may be spelled inside another.
        return sorted(pairs, key=lambda pair: len(pair[1]), reverse=True)

    def encode(self, data: bytes) -> bytes:
        for token, spelling in self._spellings():
            data = data.replace(spelling.encode(), token.encode())
        return data

    def decode(self, data: bytes) -> bytes:
        for token, spelling in self._spellings():
            data = data.replace(token.encode(), spelling.encode())
        return data

    def encode_text(self, text: str) -> str:
        return self.encode(text.encode()).decode()

    def decode_text(self, text: str) -> str:
        return self.decode(text.encode()).decode()


@dataclass(frozen=True)
class Watch:
    """A directory whose content is part of the key and whose additions a replay restores."""

    root: Path
    skip_git: bool = False  # the repository's own metadata is neither keyed nor replayed
    # A file under a `.git` inside this root that is a verbatim copy of the same file of the
    # `.git` here is replayed as a copy of the caller's own: a repository's index holds file
    # stats that differ between two builds of the same tree, and a copy must equal its original.
    mirrors: Path | None = None


def shared_root(anchor: Path) -> Path | None:
    """The directory every xdist worker of this session shares, or None outside a pytest base temp."""
    xdist = bool(os.environ.get("PYTEST_XDIST_WORKER"))
    pattern = _XDIST_BASETEMP if xdist else _PLAIN_BASETEMP
    for ancestor in (anchor.resolve(), *anchor.resolve().parents):
        if pattern.fullmatch(ancestor.name):
            return (ancestor.parent if xdist else ancestor) / SHARED_DIR
    return None


def share(
    anchor: Path,
    inputs: Mapping[str, Any],
    roles: Roles,
    watches: Mapping[str, Watch],
    produce: Callable[[], Any],
    *,
    unshareable_if_changed: Callable[[], str] = lambda: "",
) -> Any:
    """`produce()`'s JSON-able result, computed once per session for these inputs.

    `unshareable_if_changed` reads state a replay cannot restore (a repository's commits); an
    outcome that moved it is returned to its own caller but never published.
    """
    root = shared_root(anchor)
    if root is None:
        return produce()
    before = {name: _snapshot(watch, roles) for name, watch in watches.items()}
    digest = _key(inputs, roles, before)
    root.mkdir(parents=True, exist_ok=True)
    with _locked(root / f"{digest}.lock"):
        entry = root / digest
        if entry.is_dir():
            return _replay(entry, roles, watches)
        state = unshareable_if_changed()
        result = produce()
        if unshareable_if_changed() == state:
            after = {name: _snapshot(watch, roles) for name, watch in watches.items()}
            _publish(root, digest, roles, watches, before, after, result)
        return result


def normalize_arguments(
    args: list[str], roles: Roles, watched_roots: list[Path]
) -> list[str] | None:
    """`args` with the callers' own path spellings tokenised, for the key.

    A path argument inside a watched root is part of that root's content; a file outside is keyed
    by its content (a written declaration); any other path argument cannot be keyed, so None.
    """
    normalized = []
    for arg in args:
        text = roles.encode_text(arg)
        path = Path(arg)
        if text == arg and path.is_absolute() and path.exists():
            if not path.is_file() or any(root in path.parents for root in watched_roots):
                return None
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            text = f"file:{digest}"
        normalized.append(text)
    return normalized


def git_state(checkout: Path, git: Callable[..., str]) -> str:
    """What a replay cannot restore of a repository: its commits and refs."""
    return git(checkout, "rev-parse", "HEAD") + git(checkout, "for-each-ref")


def git_identity(checkout: Path, git: Callable[..., str]) -> str | None:
    """The repository content a run depends on beyond its files, or None if it is no repository."""
    try:
        return "|".join(
            [
                git(checkout, "rev-parse", "HEAD^{tree}"),
                git(checkout, "rev-list", "--count", "HEAD"),
                git(checkout, "status", "--porcelain=v1", "-z"),
            ]
        )
    except (subprocess.CalledProcessError, OSError):
        return None


# -- Keys and snapshots -----------------------------------------------------------------------


def _key(inputs: Mapping[str, Any], roles: Roles, before: Mapping[str, Snapshot]) -> str:
    material = {"inputs": inputs, "content": before}
    # A tokenised input never carries a caller's spelling, so equal inputs digest equally.
    text = roles.encode_text(json.dumps(material, sort_keys=True, default=str))
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _snapshot(watch: Watch, roles: Roles) -> Snapshot:
    snapshot: Snapshot = {}
    for directory, subdirs, files in os.walk(watch.root):
        base = Path(directory)
        if watch.skip_git and _GIT_DIR in subdirs:
            subdirs.remove(_GIT_DIR)
        for name in subdirs:
            path = base / name
            relpath = str(path.relative_to(watch.root))
            snapshot[relpath] = ("link", os.readlink(path)) if path.is_symlink() else ("dir", "")
        for name in files:
            path = base / name
            relpath = str(path.relative_to(watch.root))
            if path.is_symlink():
                snapshot[relpath] = ("link", os.readlink(path))
            else:
                text = roles.encode(path.read_bytes())
                snapshot[relpath] = ("file", hashlib.sha256(text).hexdigest())
    return snapshot


def _added(before: Snapshot, after: Snapshot) -> dict[str, tuple[str, str]]:
    return {rel: item for rel, item in after.items() if before.get(rel) != item}


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


# -- Publishing and replaying -----------------------------------------------------------------


def _publish(
    root: Path,
    digest: str,
    roles: Roles,
    watches: Mapping[str, Watch],
    before: Mapping[str, Snapshot],
    after: Mapping[str, Snapshot],
    result: Any,
) -> None:
    staging = root / f"{digest}.staging-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    meta: dict[str, Any] = {"result": json.loads(roles.encode_text(json.dumps(result)))}
    meta["trees"] = {}
    for name, watch in watches.items():
        added = _added(before[name], after[name])
        removed = sorted(set(before[name]) - set(after[name]))
        meta["trees"][name] = {"added": added, "removed": removed}
        for relpath, (kind, value) in added.items():
            stored = staging / name / relpath
            if kind == "dir":
                stored.mkdir(parents=True, exist_ok=True)
            elif kind == "link":
                stored.parent.mkdir(parents=True, exist_ok=True)
                meta["trees"][name]["added"][relpath] = (kind, roles.encode_text(value))
            else:
                source = watch.root / relpath
                mirrored = _mirrored_git_file(watch, relpath)
                if mirrored is not None:
                    meta["trees"][name]["added"][relpath] = ("mirror", mirrored)
                    continue
                stored.parent.mkdir(parents=True, exist_ok=True)
                stored.write_bytes(roles.encode(source.read_bytes()))
                shutil.copystat(source, stored)
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    staging.rename(root / digest)


def _replay(entry: Path, roles: Roles, watches: Mapping[str, Watch]) -> Any:
    meta = json.loads((entry / "meta.json").read_text(encoding="utf-8"))
    for name, tree in meta["trees"].items():
        root = watches[name].root
        for relpath in tree["removed"]:
            _remove(root / relpath)
        for relpath, (kind, value) in sorted(tree["added"].items()):
            target = root / relpath
            if kind == "dir":
                target.mkdir(parents=True, exist_ok=True)
            elif kind == "link":
                target.parent.mkdir(parents=True, exist_ok=True)
                _remove(target)
                target.symlink_to(roles.decode_text(value))
            elif kind == "mirror":
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_mirror_root(watches[name]) / value, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stored = entry / name / relpath
                target.write_bytes(roles.decode(stored.read_bytes()))
                shutil.copystat(stored, target)
    return json.loads(roles.decode_text(json.dumps(meta["result"])))


def _mirror_root(watch: Watch) -> Path:
    if watch.mirrors is None:
        raise ValueError(f"an entry mirrors a repository but {watch.root} watches none")
    return watch.mirrors


def _mirrored_git_file(watch: Watch, relpath: str) -> str | None:
    """The `.git/...` part of `relpath` when the file is a verbatim copy of the mirrored one."""
    parts = Path(relpath).parts
    if watch.mirrors is None or _GIT_DIR not in parts:
        return None
    inside = str(Path(*parts[parts.index(_GIT_DIR) :]))
    original = watch.mirrors / inside
    if original.is_file() and original.read_bytes() == (watch.root / relpath).read_bytes():
        return inside
    return None


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()
