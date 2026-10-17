"""What a run was measured on.

``MeasuredIdentity`` is the checkout's tree, the model a session reported, the seed, the planned
tasks, the launch orders, the declared settings and, per role, the definition and kernel the role
ran with. ``diff`` names every way two of them differ, so a continuation can be refused for a
stated reason and an earlier run can be set apart from another by how it differs.

``diff`` is pure. Measuring a checkout (or one commit of it) reads files and runs git; the
wire form of an identity is ``run.identity`` in the results file.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, assert_never

import yaml

from praxion_evals.adherence.grade import KERNEL_ACTIVE_STATUSES, KERNEL_LEDGER
from praxion_evals.adherence.model import DeclaredSettings
from praxion_evals.adherence.results import RunResults

_Json = Mapping[str, Any]


def _field(data: _Json, key: str, what: str) -> Any:
    if key not in data:
        raise ValueError(f"{what} lacks {key!r}")
    return data[key]


# ---------------------------------------------------------------------------
# What the run was measured on
# ---------------------------------------------------------------------------

# Paths (fnmatch patterns over repository-relative paths) the tree digest leaves out. Results
# files and the run index: committing one never changes what a later run was measured on.
# Hook-written telemetry: rewritten on every session and tracked, and no session reads it as
# guidance. Every other path counts, the adoption ledger included.
RESULTS_DIR = ".ai-state/eval_ledger/adherence/"
UNCOUNTED_PATHS: tuple[str, ...] = (RESULTS_DIR + "*", ".ai-state/observations*.jsonl")
KERNEL_INDEX = "claude/kernels/index.json"
DIGEST_SHOWN = 12  # characters of a digest a difference names

# A repository-relative path's bytes, or None when the source has nothing there.
Reader = Callable[[str], bytes | None]


@dataclass(frozen=True)
class RoleIdentity:
    """What a role ran with: its definition's digest and the kernel version it received, or
    ``None`` when the role was not adopted (delivered nothing) at the checkout."""

    definition_sha: str
    kernel: str | None


@dataclass(frozen=True)
class UnknownIdentity:
    """A role whose identity could not be read: a commit that is not reachable, a definition
    that is gone. It matches nothing, itself included."""

    reason: str


RoleIdentityOrUnknown = RoleIdentity | UnknownIdentity


@dataclass(frozen=True)
class MeasuredIdentity:
    """Everything a run was measured on that a continuation must reproduce.

    ``tree`` is ``None`` for a file written before identity was recorded; ``model`` is ``None``
    until a session reports one (the alias a run asked for is not a resolved model).
    """

    tree: str | None
    model: str | None
    seed: int
    tasks: Mapping[str, tuple[str, ...]]  # the planned task ids, by role
    launch_orders: Mapping[str, Mapping[str, tuple[str, ...]]]  # by role, then task id
    declared: DeclaredSettings
    roles: Mapping[str, RoleIdentityOrUnknown]


def measured_identity(recorded: RunResults, repo: Path) -> MeasuredIdentity:
    """The identity a results file recorded. A file written before identity was recorded has
    none, so each role's identity is derived from the commit it ran at, looked up in ``repo``."""
    extra = recorded.run.extra
    identity = extra.get("identity")
    if identity is None:
        commit = _field(_field(extra, "checkout", "a run"), "commit", "a checkout")
        read = at_commit(repo, commit)
        roles = {role: role_identity(read, role) for role in _field(extra, "roles", "a run")}
        tree = model = None
    else:
        what = "a run identity"
        roles = {role: _role_from_json(e) for role, e in _field(identity, "roles", what).items()}
        tree, model = _field(identity, "tree", what), _field(identity, "model", what)
    return MeasuredIdentity(
        tree=tree,
        model=model,
        seed=_field(extra, "seed", "a run"),
        tasks={role: tuple(ids) for role, ids in _field(extra, "tasks", "a run").items()},
        launch_orders={
            role: {task: tuple(order) for task, order in per_task.items()}
            for role, per_task in extra.get("launch_order", {}).items()
        },
        declared=recorded.settings,
        roles=roles,
    )


def diff(a: MeasuredIdentity, b: MeasuredIdentity) -> tuple[str, ...]:
    """Every way ``a`` and ``b`` differ, one line each; empty when nothing differs.

    A model that either run has not reported yet is not a difference: it is compared once both
    are known. Neither is a launch order or a role only one of them recorded, since a run that
    has not reached a task has drawn nothing for it. A role whose identity is unknown is
    always reported.
    """
    found = list(_differences("tree", _abbreviated(a.tree), _abbreviated(b.tree)))
    if a.model is not None and b.model is not None:
        found += _differences("model", a.model, b.model)
    found += _differences("seed", a.seed, b.seed)
    found += _differences("tasks", a.tasks, b.tasks)
    found += _launch_order_differences(a.launch_orders, b.launch_orders)
    found += _differences("declared", a.declared, b.declared)
    for role in sorted(a.roles.keys() & b.roles.keys()):
        found += _role_differences(role, a.roles[role], b.roles[role])
    return tuple(found)


def _launch_order_differences(
    a: Mapping[str, Mapping[str, tuple[str, ...]]], b: Mapping[str, Mapping[str, tuple[str, ...]]]
) -> Iterator[str]:
    for role in sorted(a.keys() & b.keys()):
        shared = a[role].keys() & b[role].keys()
        yield from _differences(
            f"launch_orders.{role}",
            {task: a[role][task] for task in shared},
            {task: b[role][task] for task in shared},
        )


def _role_differences(role: str, a: RoleIdentityOrUnknown, b: RoleIdentityOrUnknown) -> list[str]:
    if isinstance(a, UnknownIdentity):
        return [f"roles.{role}: identity unknown ({a.reason})"]
    if isinstance(b, UnknownIdentity):
        return [f"roles.{role}: identity unknown ({b.reason})"]
    return [
        *_differences(
            f"roles.{role}.definition",
            _abbreviated(a.definition_sha),
            _abbreviated(b.definition_sha),
        ),
        *_differences(f"roles.{role}.kernel", a.kernel, b.kernel),
    ]


def _abbreviated(digest: str | None) -> str | None:
    return None if digest is None else digest[:DIGEST_SHOWN]


def _differences(label: str, a: Any, b: Any) -> Iterator[str]:
    """One line per leaf that differs, named by its path (``declared.stop_rule.count``)."""
    if is_dataclass(a) and type(a) is type(b):
        for each in fields(a):
            yield from _differences(
                f"{label}.{each.name}", getattr(a, each.name), getattr(b, each.name)
            )
    elif isinstance(a, Mapping) and isinstance(b, Mapping):
        for key in sorted(a.keys() | b.keys()):
            yield from _differences(f"{label}.{key}", a.get(key), b.get(key))
    elif a != b:
        yield f"{label}: {_shown(a)} -> {_shown(b)}"


def _shown(value: Any) -> str:
    if isinstance(value, set | frozenset):
        value = sorted(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


# --- measuring a checkout, or one commit of it ---


def current_identity(checkout: Path, roles: Sequence[str]) -> dict[str, Any]:
    """The identity record a run writes when it begins: the checkout's tree and each role's
    identity there. The model is ``None`` until the first session reports one."""
    read = working_tree(checkout)
    return {
        "tree": tree_digest(checkout),
        "model": None,
        "roles": {role: _role_to_json(role_identity(read, role)) for role in roles},
    }


def tree_digest(checkout: Path) -> str:
    """sha256 over the sorted ``(path, blob id)`` of every file git tracks, or would add because
    it is not ignored, outside ``UNCOUNTED_PATHS``, with the contents the working tree holds now.

    An ignored file is not part of the identity: scratch space and build output are not what
    the roles run on. The blob id is git's (sha1 of ``blob <size>`` NUL and the content),
    computed here so the digest does not depend on git's line-ending filters or the platform.
    """
    listed = _git(checkout, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    digest = hashlib.sha256()
    for path in sorted(set(listed.split(b"\0")) - {b""}):
        name = os.fsdecode(path)
        if any(fnmatchcase(name, pattern) for pattern in UNCOUNTED_PATHS):
            continue
        blob = _blob_id(checkout / name)
        if blob is not None:  # a tracked file deleted from the tree, or a submodule, has none
            digest.update(blob.encode() + b"\t" + path + b"\0")
    return digest.hexdigest()


def _blob_id(path: Path) -> str | None:
    if path.is_symlink():
        content = os.fsencode(os.readlink(path))
    elif path.is_file():
        content = path.read_bytes()
    else:
        return None
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


def working_tree(checkout: Path) -> Reader:
    def read(path: str) -> bytes | None:
        try:
            return (checkout / path).read_bytes()
        except OSError:
            return None

    return read


def at_commit(repo: Path, commit: str) -> Reader:
    def read(path: str) -> bytes | None:
        try:
            return _git(repo, "show", f"{commit}:{path}")
        except ValueError:  # the commit is not reachable in this repository, or lacks the path
            return None

    return read


def role_identity(read: Reader, role: str) -> RoleIdentityOrUnknown:
    path = f"agents/{role}.md"
    definition = read(path)
    if definition is None:
        return UnknownIdentity(f"{path} cannot be read")
    kernel = None
    if _receives_kernel(read, role):
        kernel = _kernel_version(read)
        if kernel is None:
            return UnknownIdentity(f"{role} receives a kernel but {KERNEL_INDEX} cannot be read")
    return RoleIdentity(hashlib.sha256(definition).hexdigest(), kernel)


def _receives_kernel(read: Reader, role: str) -> bool:
    """Whether the adoption ledger has the role receiving a kernel at spawn. Mirrors the
    delivering hook: a ledger that is absent or does not read, or a role at no delivering
    status, hands over nothing."""
    ledger = read(str(KERNEL_LEDGER))
    try:
        roles = (yaml.safe_load(ledger) or {}).get("roles") if ledger is not None else None
    except (yaml.YAMLError, AttributeError):
        return False
    entry = roles.get(role) if isinstance(roles, dict) else None
    return isinstance(entry, dict) and entry.get("status") in KERNEL_ACTIVE_STATUSES


def _kernel_version(read: Reader) -> str | None:
    index = read(KERNEL_INDEX)
    try:
        version = json.loads(index).get("kernel_version") if index is not None else None
    except (ValueError, AttributeError):
        return None
    return version if isinstance(version, str) else None


def _git(repo: Path, *args: str) -> bytes:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError(f"`git {' '.join(args)}` failed in {repo}") from error
    return done.stdout


# --- the wire form: ``run.identity`` in the results file ---


def _role_to_json(identity: RoleIdentityOrUnknown) -> dict[str, Any]:
    match identity:
        case RoleIdentity(definition_sha=sha, kernel=kernel):
            return {"definition_sha": sha, "kernel": kernel}
        case UnknownIdentity(reason=reason):
            return {"unknown": reason}
        case _:
            assert_never(identity)


def _role_from_json(data: _Json) -> RoleIdentityOrUnknown:
    if "unknown" in data:
        return UnknownIdentity(data["unknown"])
    what = "a role identity"
    return RoleIdentity(_field(data, "definition_sha", what), _field(data, "kernel", what))
