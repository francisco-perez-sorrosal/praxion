"""The two arms of a role, and the proof that the lean one really is lean.

The refactoring move's arms are proven differently, by what the role's own record holds
(``decide_delivery_proof``); the nonce below belongs to the ordinary proof alone.

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

import secrets
import shutil
import tempfile
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from praxion_evals.adherence import grade
from praxion_evals.adherence.axis import SESSION_ARMS, SessionArm
from praxion_evals.adherence.model import (
    ARMS,
    ROLES,
    Arm,
    ArmBuild,
    NotBuilt,
    Role,
    SessionEvidence,
)
from praxion_evals.live.materialize import (
    Materialization,
    digest_entries,
    frontmatter_closing,
    install_user_scope,
    make_read_only,
    make_writable,
    materialize_path,
    remove_tree,
    tree_entries,
)
from praxion_evals.live.session import SandboxPaths, SessionRun, session_error

OMIT_CLAUDE_MD_KEY = "omitClaudeMd"
MAX_TURNS_KEY = "maxTurns"

PROOF_LABEL = "PRXARM"
NO_MARKER_REPLY = "NO-MARKER"
NONCE_BYTES = 8

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
    turn_cap: int | None = None,
) -> ArmBuild:
    """Copy ``original`` to ``dest`` as ``role``'s ``arm``, verified and read-only.

    ``dest`` must not exist yet (an existing one is refused and left alone).
    ``original`` is only read. A build that fails, the copy itself included,
    leaves nothing at ``dest``, so the caller can retry.
    """
    if turn_cap is not None and turn_cap < 1:
        raise ArmCopyError(f"a turn cap must be at least 1, not {turn_cap}")
    require_regular_definition(original.root, role)
    if dest.exists() or dest.is_symlink():
        raise ArmCopyError(f"{dest} already exists; a copy is built into a fresh directory")
    try:
        shutil.copytree(original.root, dest, symlinks=True)
        return _patch_and_seal(original, dest, role, arm, turn_cap)
    except BaseException:
        remove_tree(dest)
        raise


def _patch_and_seal(
    original: Materialization, dest: Path, role: Role, arm: Arm, turn_cap: int | None
) -> ArmBuild:
    definition = definition_path(role)
    make_writable(dest)
    settings = _settings_for(arm, turn_cap)
    if settings:
        path = dest / definition
        text = path.read_bytes().decode("utf-8")
        if arm == "lean" and _carries_flag(text):
            # A switched role's full arm would carry the flag too: the two arms would be the
            # same configuration, and a run would compare nothing. Say so, rather than report
            # the copy "unchanged where it should differ".
            raise ArmCopyError(
                f"{definition} already sets {OMIT_CLAUDE_MD_KEY}: the role is switched in this "
                "checkout, so it has no full arm to compare against"
            )
        patched_text = _with_settings(text, settings)
        path.write_bytes(patched_text.encode("utf-8"))
    after = tree_entries(dest)
    patched = _diff_entries(
        tree_entries(original.root), after, expected=(definition,) if settings else ()
    )
    make_read_only(dest)
    return ArmBuild(
        role=role,
        arm=arm,
        copy_root=dest,
        turn_cap=turn_cap,
        tree_digest=digest_entries(after),
        patched=patched,
    )


def build_refactoring_arm(checkout: Path, arm: SessionArm, dest: Path) -> Path:
    """The refactoring move's ``arm`` built from ``checkout`` at ``dest``, shown for every pooled role.

    The checkout is materialized as the eval does (its tracked and unignored files, never its
    environments), so the checkout is only read. The move changes both roles' definitions, so an
    uncapped copy does not depend on the role it is built for. Returns the copy's root.
    """
    # Imported here: refactoring_arms imports this module for its error and helpers.
    from praxion_evals.adherence import refactoring_arms, refactoring_tasks

    scratch = Path(tempfile.mkdtemp(prefix="refactoring-arm-"))
    try:
        original = materialize_path(checkout, scratch / "original")
        roles = tuple(refactoring_tasks.POOLS)
        built = refactoring_arms.build_refactoring_copy(original, dest, roles[0], arm, None)
        try:
            for role in roles:
                refactoring_arms.verify_arm(built.copy_root, arm, role)
        except BaseException:
            remove_tree(dest)
            raise
        return built.copy_root
    finally:
        remove_tree(scratch)


def definition_path(role: str) -> str:
    if role not in ROLES:
        raise ArmCopyError(f"unknown role {role!r}")
    return f"agents/{role}.md"


def require_regular_definition(root: Path, role: str) -> None:
    """Refuse a checkout whose ``role`` definition is not a regular file: a patch written through
    a link would reach the file it points to, which may be the checkout under test."""
    definition = definition_path(role)
    source = root / definition
    if source.is_symlink() or not source.is_file():
        raise ArmCopyError(f"the checkout has no regular file {definition}")


def _settings_for(arm: Arm, turn_cap: int | None) -> dict[str, str]:
    """The frontmatter keys an arm's copy sets, in the order they are written."""
    settings: dict[str, str] = {}
    if arm == "lean":
        settings[OMIT_CLAUDE_MD_KEY] = "true"
    if turn_cap is not None:
        settings[MAX_TURNS_KEY] = str(turn_cap)
    return settings


def _carries_flag(definition: str) -> bool:
    """Whether the definition's frontmatter already sets ``omitClaudeMd`` to true."""
    lines = definition.splitlines()
    try:
        closing = frontmatter_closing(lines)
    except ValueError:
        return False
    return any(
        line.startswith(f"{OMIT_CLAUDE_MD_KEY}:")
        and line.split(":", 1)[1].strip().lower() == "true"
        for line in lines[1:closing]
    )


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
    try:
        closing = frontmatter_closing(lines)
    except ValueError as exc:
        raise ArmCopyError(f"the agent definition has {exc}") from exc
    new_line = f"{key}: {value}\n"
    existing = next((i for i in range(1, closing) if lines[i].startswith(f"{key}:")), None)
    if existing is None:
        lines.insert(closing, new_line)
    else:
        lines[existing] = new_line
    return "".join(lines)


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
    return _diff_entries(tree_entries(original), tree_entries(copy), expected=expected)


def _diff_entries(
    before: Mapping[str, str], after: Mapping[str, str], *, expected: Collection[str]
) -> tuple[str, ...]:
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


def prepare_proof_home(original: Materialization, template: Path) -> str:
    """Install the original's user scope at ``template`` and plant the nonce there; return it."""
    install_user_scope(original.root, template)
    return plant_proof_marker(SandboxPaths(template))


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


def observe_proof(evidence: SessionEvidence, real_home: Path) -> ProofObservation | NotBuilt:
    """What the proof session's role answered, or why nothing was observed."""
    unobserved = unobserved_proof(evidence, real_home)
    if unobserved is not None:
        return unobserved
    return ProofObservation(
        answer=evidence.role_return or "",
        first_request_tokens=grade.first_request_tokens(evidence),
    )


def unobserved_proof(evidence: SessionEvidence, real_home: Path) -> NotBuilt | None:
    """Why a proof session shows nothing of its role: it ended in an error, or spawned no role."""
    run = SessionRun("", "", None if evidence.timed_out else evidence.exit_code)
    error = session_error(evidence.envelope, run, evidence.plugin_copy, real_home=real_home)
    if error is not None:
        return NotBuilt(f"the proof session ended in {error.kind}: {error.detail}")
    if evidence.spawn_id is None:
        return NotBuilt("the role was never spawned in the proof session")
    return None


@dataclass(frozen=True)
class DeliveryObservation:
    """What a proof spawn's own record holds of the skill, and its first request's size."""

    delivered_blocks: int  # labelled blocks whose digest is the body installed in the arm's copy
    stray_labels: int  # labelled blocks whose digest is not
    preload_messages: int  # harness preload messages for the refactoring skill
    first_request_tokens: int | None  # recorded, never decisive


@dataclass(frozen=True)
class ArmProven:
    """One arm shown to be what it claims.

    ``first_request_tokens`` is the figure recorded for the arm; ``cross_checked``
    says whether the other arm was in the run, so that the token comparison held
    as well as the nonce. The refactoring move's arms are never cross-checked.
    """

    arm: SessionArm
    first_request_tokens: int | None
    cross_checked: bool

    def __post_init__(self) -> None:
        if self.arm not in SESSION_ARMS:
            raise ValueError(f"a proven arm must be one of {list(SESSION_ARMS)}, got {self.arm!r}")
        tokens = self.first_request_tokens
        if tokens is not None and tokens < 0:
            raise ValueError(f"a first request cannot hold {tokens} tokens")
        if self.cross_checked and tokens is None:
            raise ValueError("a token cross-check needs the arm's first-request figure")


ArmVerdict = ArmProven | NotBuilt


def decide_proof(
    nonce: str, observed: Mapping[Arm, ProofObservation | None]
) -> dict[Arm, ArmVerdict]:
    """One verdict per observed arm; ``None`` marks a role that was never spawned.

    Full is proven when the role echoes the nonce. Lean is proven when its answer
    is the declared no-marker reply: the nonce's absence alone would also certify
    a spawn that errored, came back empty or never looked at its context. When
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
    if arm == "lean" and seen.answer.strip() != NO_MARKER_REPLY:
        return NotBuilt(
            f"the lean arm's role did not answer exactly {NO_MARKER_REPLY}: its search is unobserved"
        )
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


# What a proof spawn's record must hold per arm: (matching blocks, stray labels, preload messages).
_DELIVERY_WANTED = {"delivered": (1, 0, 0), "preloaded": (0, 0, 1)}


def decide_delivery_proof(
    observed: Mapping[SessionArm, DeliveryObservation | None],
) -> dict[SessionArm, ArmVerdict]:
    """One verdict per observed arm of the refactoring move; ``None`` marks a role never spawned.

    ``delivered`` is proven by exactly one matching block, no stray label and no preload
    message; ``preloaded`` by exactly one preload message and no block of either kind. The
    nonce plays no part and nothing is cross-checked: the figure is recorded, never decisive.
    """
    unknown = [arm for arm in observed if arm not in _DELIVERY_WANTED]
    if unknown:
        raise ValueError(f"unknown arms {sorted(unknown)}")
    return {arm: _judge_delivery(arm, seen) for arm, seen in observed.items()}


def _judge_delivery(arm: SessionArm, seen: DeliveryObservation | None) -> ArmVerdict:
    if seen is None:
        return NotBuilt(f"the role was never spawned in the {arm} proof session")
    held = (seen.delivered_blocks, seen.stray_labels, seen.preload_messages)
    if held == _DELIVERY_WANTED[arm]:
        return ArmProven(arm, seen.first_request_tokens, cross_checked=False)
    return NotBuilt(
        f"the {arm} arm's role record holds (matching blocks, stray labels, preload messages)"
        f" = {held}, and the arm needs {_DELIVERY_WANTED[arm]}"
    )
