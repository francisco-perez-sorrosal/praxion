"""The shell confinement of a confined kit's session, as one value and its rendered settings.

The implementer's and the verifier's sessions run shell commands (the fixture's tests, the
formatter, the linter, git reads, Praxion's scripts). A command pattern cannot bound them,
because pytest runs code the role just wrote, so the harness's OS sandbox bounds them
instead. ``confinement_for`` builds the value from where the session runs and what the
operator's machine holds; ``settings_of`` renders it as the ``sandbox`` block the session is
started with (``--settings``). Every other role gets ``None`` and keeps its grant.

Two facts shape the paths:

- The session's ``HOME`` is its sandbox home, so a ``~`` entry would protect the wrong
  directory. Every path here is absolute and rooted in the operator's real home.
- The harness matches a path as spelled, and a symlinked prefix reaches the same file under
  another spelling. Each path therefore appears in its given spelling and in its realpath.

Reads are denied across the real home and re-opened only where a session needs them (the
runner's environment, the plugin copy, the run root); the narrower path wins. A credential
entry that an ``allow_read`` entry covers would be re-opened, so such a pair is refused.

The settings keys were last checked against code.claude.com/docs/en/sandboxing.md.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxion_evals.adherence.model import Role

CONFINED_ROLES: frozenset[Role] = frozenset({"implementer", "verifier"})

# Names under the operator's real home. The first layer of protection is `deny_read` over the
# whole home; these also hold where the harness's filesystem isolation is off (macOS).
CREDENTIAL_LOCATIONS: tuple[str, ...] = (
    ".ssh",
    ".aws",
    ".config/gcloud",
    ".azure",
    ".kube",
    ".docker",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials.toml",
    ".gem/credentials",
    ".config/gh",
    ".netrc",
    ".claude",
    ".claude.json",
)

# Dropped from a confined command's environment; the session process and its hooks keep them.
SESSION_CREDENTIAL_VARIABLES: tuple[str, ...] = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)

# Required, never unconfined (no fallback at startup, no retry), and commands inside run
# without a prompt. Fixed, so a "confined but optional" session cannot be built.
_FIXED_FLAGS: tuple[tuple[str, bool], ...] = (
    ("enabled", True),
    ("failIfUnavailable", True),
    ("allowUnsandboxedCommands", False),
    ("autoAllowBashIfSandboxed", True),
)
_DENY = "deny"


@dataclass(frozen=True)
class Places:
    """Where a confined session runs: the plugin copy it may read but never write, and the run
    root that holds its results."""

    run_root: Path
    plugin_copy: Path


@dataclass(frozen=True)
class Operator:
    """The operator's machine as the runner sees it.

    ``runner_prefix`` and ``runner_base_prefix`` are the runner interpreter's ``sys.prefix`` and
    ``sys.base_prefix``: the environment a session's tests run under. ``ambient_path`` is the
    directories of the PATH the runner was started with.
    """

    home: Path
    token_file: Path | None
    runner_prefix: Path
    runner_base_prefix: Path
    ambient_path: tuple[str, ...]


@dataclass(frozen=True)
class Confinement:
    """The paths, variables and program order of one confined session.

    Invariants, checked at construction: every path is absolute, and no ``allow_read`` entry
    covers a ``credential_files`` entry.
    """

    deny_write: tuple[str, ...]
    deny_read: tuple[str, ...]
    allow_read: tuple[str, ...]
    credential_files: tuple[str, ...]
    env_drops: tuple[str, ...]
    program_order: tuple[str, ...]

    def __post_init__(self) -> None:
        paths = (*self.deny_write, *self.deny_read, *self.allow_read, *self.credential_files)
        relative = [path for path in paths if not os.path.isabs(path)]
        if relative:
            raise ValueError(f"confinement paths must be absolute, got {relative}")
        swallowed = [
            (allowed, credential)
            for allowed in self.allow_read
            for credential in self.credential_files
            if _covers(allowed, credential)
        ]
        if swallowed:
            raise ValueError(f"an allow_read entry covers a credential entry: {swallowed}")


def confinement_for(role: Role, places: Places, operator: Operator) -> Confinement | None:
    """The confinement of `role`'s session; None for a role whose kit is not confined."""
    if role not in CONFINED_ROLES:
        return None
    credential_paths = [operator.home / name for name in CREDENTIAL_LOCATIONS]
    if operator.token_file is not None:
        credential_paths.append(operator.token_file)
    return Confinement(
        deny_write=_spellings([places.plugin_copy]),
        deny_read=_spellings([operator.home]),
        allow_read=_spellings(
            [
                operator.runner_prefix,
                operator.runner_base_prefix,
                places.plugin_copy,
                places.run_root,
            ]
        ),
        credential_files=_spellings(credential_paths),
        env_drops=SESSION_CREDENTIAL_VARIABLES,
        program_order=(
            str(places.plugin_copy / "scripts"),
            str(operator.runner_prefix / "bin"),
            *operator.ambient_path,
        ),
    )


def settings_of(confinement: Confinement) -> dict[str, Any]:
    """The `sandbox` settings block that puts `confinement` into force.

    No `network.allowedDomains`: a confined command opens no connection.
    """
    return {
        "sandbox": {
            **dict(_FIXED_FLAGS),
            "filesystem": {
                "denyWrite": list(confinement.deny_write),
                "denyRead": list(confinement.deny_read),
                "allowRead": list(confinement.allow_read),
            },
            "credentials": {
                "files": [{"path": path, "mode": _DENY} for path in confinement.credential_files],
                "envVars": [{"name": name, "mode": _DENY} for name in confinement.env_drops],
            },
        }
    }


def _spellings(paths: Iterable[Path]) -> tuple[str, ...]:
    """Each path as given, then as its realpath when that differs; first occurrence wins."""
    spelled = (spelling for path in paths for spelling in (str(path), os.path.realpath(path)))
    return tuple(dict.fromkeys(spelled))


def _covers(root: str, path: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)
