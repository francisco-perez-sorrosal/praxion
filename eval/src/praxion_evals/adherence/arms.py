"""The two arms of a role, and the proof that the lean one really is lean.

An arm is a runner-owned copy of the checkout under test. ``full`` is that copy
untouched; ``lean`` differs from it at one place only, the measured role's agent
definition, whose frontmatter gains ``omitClaudeMd: true`` (the switch a Phase 2
flip would make). A copy for an early-stop task also carries a lowered
``maxTurns`` there, in both arms. Everything else, the body of the definition
included, is byte-identical, and ``verify_copy_diff`` re-digests the copy against
the original to make that so rather than assume it. The copy is read-only once
built, and the checkout is never written.

An arm is scored only after it is proven. A fresh nonce is appended to the
instruction file installed in a proof sandbox; the role is spawned and asked to
quote it. The role that inherits the instruction files echoes the nonce; the one
launched without them cannot. The nonce echo is a self-report, so when both arms
are in the run it is cross-checked against telemetry: the lean first request must
be smaller than the full one.

The builders touch files; ``decide_proof`` and the frontmatter patch are pure.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from praxion_evals.adherence.model import ARMS, ROLES, Arm, ArmBuild, NotBuilt, Role
from praxion_evals.live.materialize import (
    Materialization,
    make_read_only,
    make_writable,
    tree_digest,
)
from praxion_evals.live.session import SandboxPaths

OMIT_CLAUDE_MD_KEY = "omitClaudeMd"
MAX_TURNS_KEY = "maxTurns"

PROOF_LABEL = "PRXARM"
NO_MARKER_REPLY = "NO-MARKER"
NONCE_BYTES = 8

_FRONTMATTER_FENCE = "---"
_INSTRUCTION_FILE = "CLAUDE.md"


class ArmCopyError(ValueError):
    """A copy differs from its original somewhere it must not, or cannot be patched."""


# ---------------------------------------------------------------------------
# Building a copy
# ---------------------------------------------------------------------------


def build_arm(
    original: Materialization,
    dest: Path,
    role: Role,
    arm: Arm,
    *,
    turn_cap: int | None = None,
) -> ArmBuild:
    """Copy ``original`` to ``dest`` as ``role``'s ``arm``, verified and read-only.

    ``dest`` must not exist yet. ``original`` is only read.
    """
    definition = definition_path(role)
    if not (original.root / definition).is_file():
        raise ArmCopyError(f"the checkout has no {definition}")
    shutil.copytree(original.root, dest, symlinks=True)
    make_writable(dest)
    settings = _settings_for(arm, turn_cap)
    if settings:
        path = dest / definition
        path.write_text(
            _with_settings(path.read_text(encoding="utf-8"), settings), encoding="utf-8"
        )
    patched = verify_copy_diff(original.root, dest, expected=(definition,) if settings else ())
    make_read_only(dest)
    return ArmBuild(
        role=role,
        arm=arm,
        copy_root=dest,
        turn_cap=turn_cap,
        tree_digest=tree_digest(dest),
        patched=patched,
    )


def definition_path(role: str) -> str:
    if role not in ROLES:
        raise ArmCopyError(f"unknown role {role!r}")
    return f"agents/{role}.md"


def _settings_for(arm: Arm, turn_cap: int | None) -> dict[str, str]:
    """The frontmatter keys an arm's copy sets, in the order they are written."""
    settings: dict[str, str] = {}
    if arm == "lean":
        settings[OMIT_CLAUDE_MD_KEY] = "true"
    if turn_cap is not None:
        settings[MAX_TURNS_KEY] = str(turn_cap)
    return settings


def _with_settings(definition: str, settings: Mapping[str, str]) -> str:
    for key, value in settings.items():
        definition = set_frontmatter_key(definition, key, value)
    return definition


def set_frontmatter_key(definition: str, key: str, value: str) -> str:
    """Set a top-level frontmatter key, changing no other line, the body included.

    An existing ``key:`` line is replaced in place; otherwise the line is added
    last in the block. Raises ``ArmCopyError`` when there is no frontmatter.
    """
    lines = definition.splitlines(keepends=True)
    closing = _frontmatter_end(lines)
    new_line = f"{key}: {value}\n"
    existing = next((i for i in range(1, closing) if lines[i].startswith(f"{key}:")), None)
    if existing is None:
        lines.insert(closing, new_line)
    else:
        lines[existing] = new_line
    return "".join(lines)


def _frontmatter_end(lines: list[str]) -> int:
    if not lines or lines[0].rstrip() != _FRONTMATTER_FENCE:
        raise ArmCopyError("the agent definition has no frontmatter")
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip() == _FRONTMATTER_FENCE), None
    )
    if closing is None:
        raise ArmCopyError("the agent definition's frontmatter is unterminated")
    return closing


# ---------------------------------------------------------------------------
# The copy diff
# ---------------------------------------------------------------------------


def verify_copy_diff(original: Path, copy: Path, *, expected: Collection[str]) -> tuple[str, ...]:
    """The paths where ``copy`` differs from ``original``; raises unless they are ``expected``.

    A path counts as different when its bytes (or link target) differ or it exists
    on one side only, so a stray file, a missing file and a changed file are all
    caught. An expected path that did not change is an error too: a lean copy
    identical to the full one would make the arms the same.
    """
    before, after = _entry_digests(original), _entry_digests(copy)
    differing = sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
    if set(differing) != set(expected):
        unexpected = sorted(set(differing) - set(expected))
        unchanged = sorted(set(expected) - set(differing))
        raise ArmCopyError(
            f"the copy differs from its original in {unexpected or 'nothing unexpected'}"
            f" and is unchanged where {unchanged or 'nothing'} should differ"
        )
    return tuple(differing)


def _entry_digests(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            digests[path.relative_to(root).as_posix()] = f"link:{os.readlink(path)}"
        elif path.is_file():
            payload = hashlib.sha256(path.read_bytes()).hexdigest()
            digests[path.relative_to(root).as_posix()] = f"file:{payload}"
    return digests


# ---------------------------------------------------------------------------
# The arm proof
# ---------------------------------------------------------------------------


def plant_proof_marker(sandbox: SandboxPaths) -> str:
    """Append a fresh nonce to the sandbox's installed instruction file; return the nonce.

    Call after ``install_user_scope``. The marker goes where ``omitClaudeMd``
    acts, the installed user instruction file, and never into an agent definition
    or the hook registration, which a role would read whichever arm it is in.
    """
    path = sandbox.config_dir / _INSTRUCTION_FILE
    if not path.is_file():
        raise ArmCopyError(
            f"{path} is not installed; plant the marker after the user-scope install"
        )
    nonce = secrets.token_hex(NONCE_BYTES)
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n\n{PROOF_LABEL}-{nonce}\n", encoding="utf-8"
    )
    return nonce


def proof_prompt() -> str:
    """The task text the spawned role receives; it never carries the nonce.

    The prompt reaches the role in both arms, so a nonce in it would let the lean
    role echo what it never inherited.
    """
    return (
        f"Look through the instruction files loaded into your context for a line that "
        f"begins `{PROOF_LABEL}-`. Reply with that whole line, verbatim, and nothing "
        f"else. If no such line is in your context, reply with exactly {NO_MARKER_REPLY}. "
        f"Do not use any tool."
    )


@dataclass(frozen=True)
class ProofObservation:
    """What a spawned role answered, and the size of its first request (if recorded)."""

    answer: str
    first_request_tokens: int | None


@dataclass(frozen=True)
class ArmProven:
    """One arm shown to be what it claims.

    ``first_request_tokens`` is the figure recorded for the arm; ``cross_checked``
    says whether the other arm was in the run, so that the token comparison held
    as well as the nonce.
    """

    arm: Arm
    first_request_tokens: int | None
    cross_checked: bool


ArmVerdict = ArmProven | NotBuilt


def decide_proof(
    nonce: str, observed: Mapping[Arm, ProofObservation | None]
) -> dict[Arm, ArmVerdict]:
    """One verdict per observed arm; ``None`` marks a role that was never spawned.

    Full is proven when the role echoes the nonce, lean when it does not. When
    both arms were observed and spawned, lean must also have the smaller first
    request, else it alone is not built: the nonce is a self-report and the
    tokens are the telemetry that backs it. A single-arm run has nothing to
    compare against, so it decides on the nonce and records the figure.
    """
    if not nonce:
        raise ValueError("a proof needs a non-empty nonce")
    unknown = [arm for arm in observed if arm not in ARMS]
    if unknown:
        raise ValueError(f"unknown arms {sorted(unknown)}")
    verdicts: dict[Arm, ArmVerdict] = {
        arm: _judge_arm(arm, nonce, seen) for arm, seen in observed.items()
    }
    full, lean = verdicts.get("full"), verdicts.get("lean")
    if isinstance(full, ArmProven) and isinstance(lean, ArmProven):
        verdicts["lean"] = _cross_check_tokens(full, lean)
        if isinstance(verdicts["lean"], ArmProven):
            verdicts["full"] = replace(full, cross_checked=True)
    return verdicts


def _judge_arm(arm: Arm, nonce: str, seen: ProofObservation | None) -> ArmVerdict:
    if seen is None:
        return NotBuilt(f"the role was never spawned in the {arm} proof session")
    echoed = nonce in seen.answer
    if arm == "full" and not echoed:
        return NotBuilt("the full arm's role did not echo the planted nonce: it inherits nothing")
    if arm == "lean" and echoed:
        return NotBuilt("the lean arm's role echoed the planted nonce: omitClaudeMd had no effect")
    return ArmProven(arm, seen.first_request_tokens, cross_checked=False)


def _cross_check_tokens(full: ArmProven, lean: ArmProven) -> ArmVerdict:
    if full.first_request_tokens is None or lean.first_request_tokens is None:
        return NotBuilt("a first-request token figure is missing, so the lean arm is unconfirmed")
    if not 0 < lean.first_request_tokens < full.first_request_tokens:
        return NotBuilt(
            f"the lean first request ({lean.first_request_tokens} tokens) is not smaller "
            f"than the full one ({full.first_request_tokens})"
        )
    return replace(lean, cross_checked=True)
