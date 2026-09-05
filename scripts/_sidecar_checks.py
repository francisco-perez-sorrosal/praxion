"""The D3 check registry -- one ordered list, evaluated once, projected twice.

`evaluate_checks()` is the single source of "is this healthy" for sidecar
placement (`INTERFACE_DESIGN.md` sec. 7.3, D3): `path_states()`,
`render_doctor_json()` and `render_doctor_text()` are thin projections of
the same list this module returns -- never a second "healthy" drifting
inside a renderer.

**Pure by construction.** Every fact arrives pre-classified in `CheckInputs`
-- no git, filesystem or environment read here; that classification belongs
to the CLI wiring layer that builds a `CheckInputs`. This is asserted
directly: the test suite makes `subprocess.run` and the `os.stat` family
raise inside a call and confirms nothing breaks.

"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from enum import Enum

import _sidecar_commit
import _sidecar_convergence
import _sidecar_mount
import _state_repo

# Fix strings are module constants, not scattered literals -- one place a
# reader (or a future row) confirms the exact command against.
_LINK_FIX = "praxion-sidecar link"
_HOOKS_PATH_FIX = "scripts/upgrade_project_pins.sh"
_SIDECAR_REPO_FIX = "praxion-sidecar commit"
_REMOTE_POLICY_FIX = "praxion-sidecar remote --clear, or re-set"
_MOUNT_ORPHANED_FIX = "praxion-sidecar link --prune"
_MERGE_BACK_FIX_TEMPLATE = "praxion-sidecar merge-back --from {branch}"
_COMMIT_LOCK_WAIT_FIX = "re-run: praxion-sidecar doctor"
_RELINK_FIX = "rm .ai-state && praxion-sidecar link"

# `sidecar-repo`'s WARN threshold (INTERFACE_DESIGN.md sec. 7.3): named so
# the number "50 unpushed" appears exactly once.
_UNPUSHED_COMMITS_WARN_THRESHOLD = 50
_SCHEMA_VERSION = 1


class Verdict(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """Pass/warn/fail. Never compared directly with `<`/`>` -- the `str`
    mixin's own rich comparisons are lexicographic ("warn" would outrank
    "fail"), so `overall_verdict` keys `max()` off `_VERDICT_SEVERITY`
    instead of relying on `Verdict` ordering itself."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


_VERDICT_SEVERITY = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.FAIL: 2}


@dataclasses.dataclass(frozen=True)
class CheckResult:
    """One `doctor` row. A passing row carries neither `why` nor `fix`; a
    non-passing row always carries a `fix` -- `why` is optional, since some
    rows are self-explanatory from `detail` alone."""

    id: str
    verdict: Verdict
    detail: str
    why: str | None
    fix: str | None

    def __post_init__(self) -> None:
        if self.verdict is Verdict.PASS:
            if self.why is not None or self.fix is not None:
                raise ValueError(f"a pass row must carry neither `why` nor `fix` (id={self.id!r})")
        elif self.fix is None:
            raise ValueError(f"a non-pass row must carry a `fix` (id={self.id!r})")


def _row(
    cid: str, verdict: Verdict, detail: str, *, why: str | None = None, fix: str | None = None
) -> CheckResult:
    return CheckResult(id=cid, verdict=verdict, detail=detail, why=why, fix=fix)


class ExcludeBlockState(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """Is the Praxion block in `.git/info/exclude`, and does it match?"""

    ABSENT = "absent"
    CURRENT = "current"
    DRIFTED = "drifted"


class UnresolvedReason(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """Why a checkout does not resolve into its own sidecar.

    A **whole-checkout** fact, deliberately distinct from `ShadowState`: the
    per-slot `shadow:<path>` rows are driven by manifest entries, and in each
    of these three states there is no manifest of this project's to read. A
    `shadow:.ai-state` row here would claim a slot the manifest never declared
    and would collide with the real per-slot row under sidecar placement.
    """

    DANGLING = "dangling"
    FOREIGN = "foreign"
    UNLINKED = "unlinked"


@dataclasses.dataclass(frozen=True)
class UnresolvedPlacement:
    """One unresolved placement, with the evidence its row names.

    `evidence` is the recorded target (`DANGLING`), the refusal reason and
    the path it was read from (`FOREIGN`), or the sidecar that exists for
    this checkout's identity (`UNLINKED`).
    """

    reason: UnresolvedReason
    evidence: str


class ShadowState(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """A resolved `intent: shadow` slot -- pre-resolved by the CLI wiring
    layer (module docstring), never derived here."""

    LINKED = "linked"
    MISSING = "missing"
    DANGLING = "dangling"
    BLOCKED = "blocked"
    FOREIGN = "foreign"


class SharedState(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """A resolved `intent: share` slot."""

    SHARED = "shared"
    UNEXPECTED_SYMLINK = "unexpected-symlink"


@dataclasses.dataclass(frozen=True)
class SidecarRepoState:
    """The sidecar's own git health -- three facts, nothing derived."""

    is_git_repo: bool
    dirty_files: int
    unpushed_commits: int


@dataclasses.dataclass(frozen=True)
class RemoteState:
    """The sidecar's configured remote. `remote is None` on `CheckInputs`
    means no remote at all -- this type never represents that case itself,
    so "push policy set with no remote" stays unrepresentable."""

    url: str
    push: str
    host_matches_origin: bool
    foreign_host_ack: bool


@dataclasses.dataclass(frozen=True)
class CheckInputs:
    """Everything `evaluate_checks` needs, already classified.

    `mount` is carried for parity with the mount-classification pipeline and
    future consumers (`status`'s sidecar block) -- no row reads it directly,
    since the convergence facts it would drive (`branches`,
    `orphaned_mounts`, `mount_mid_merge`) already arrive pre-derived from it.
    Under every non-`SidecarOwned` placement, `exclude_block`/`sidecar_repo`
    are `None`; `evaluate_checks` gates on `placement`'s type rather than
    re-deriving "nothing applies" from empty collections. `placement` spans
    the resolver's full five-variant sum type because `doctor` is total over
    placements: an unresolved one is *reported* (through
    `unresolved_placement`), never a reason to emit no rows at all.
    """

    placement: _state_repo.Placement
    exclude_block: ExcludeBlockState | None
    shadow_slots: Mapping[str, ShadowState]
    shared_slots: Mapping[str, SharedState]
    untouched_paths: Mapping[str, str]
    hooks_status: Mapping[str, object]
    mount: _sidecar_mount.StateMountState
    branches: Mapping[str, _sidecar_convergence.StateBranchState]
    orphaned_mounts: tuple[str, ...]
    mount_mid_merge: bool
    sidecar_repo: SidecarRepoState | None
    remote: RemoteState | None
    guards_roots_stale: bool
    lock_state: _sidecar_commit.SidecarCommit | None
    unresolved_placement: UnresolvedPlacement | None


def evaluate_checks(inputs: CheckInputs) -> list[CheckResult]:
    """The D3 single source, pinned row order (the four lists below). Under
    every non-sidecar placement only `placement`/`hooks-path`/`hooks-chained`
    apply -- P0's hook chain runs with or without a sidecar
    (INTERFACE_DESIGN.md sec. 7.3)."""
    is_sidecar = isinstance(inputs.placement, _state_repo.SidecarOwned)
    row_funcs = (
        _PLACEMENT_ROW_FUNCS
        + (_SIDECAR_HEAD_ROW_FUNCS if is_sidecar else [])
        + _HOOK_ROW_FUNCS
        + (_SIDECAR_TAIL_ROW_FUNCS if is_sidecar else [])
    )
    rows: list[CheckResult] = []
    for row_func in row_funcs:
        rows.extend(row_func(inputs))
    return rows


# --- row functions, in the table's pinned order -----------------------------

# A `{path}`-templated (verdict, detail, why, fix) spec per state; one table
# entry serves every path. `str.format` on a template with no `{path}`
# (e.g. `_LINK_FIX`) is a harmless no-op.
_RowSpec = tuple[Verdict, str, "str | None", "str | None"]

_EXCLUDE_BLOCK_ROWS: dict[ExcludeBlockState, _RowSpec] = {
    ExcludeBlockState.CURRENT: (
        Verdict.PASS,
        "Praxion entries current in .git/info/exclude",
        None,
        None,
    ),
    ExcludeBlockState.ABSENT: (
        Verdict.FAIL,
        "no Praxion entries in .git/info/exclude",
        "never written, or removed",
        _LINK_FIX,
    ),
    ExcludeBlockState.DRIFTED: (
        Verdict.WARN,
        "the exclude block has drifted from the manifest",
        "the manifest changed since it was written",
        _LINK_FIX,
    ),
}

_PLACEMENT_ROWS: dict[UnresolvedReason, _RowSpec] = {
    UnresolvedReason.DANGLING: (
        Verdict.FAIL,
        ".ai-state is a dangling symlink, recorded target {evidence}",
        "the mount it records was removed, or was never materialised here",
        _LINK_FIX,
    ),
    UnresolvedReason.FOREIGN: (
        Verdict.FAIL,
        ".ai-state does not resolve into this project's sidecar ({evidence})",
        "linked by a different sidecar, or the sidecar was recreated",
        _RELINK_FIX,
    ),
    UnresolvedReason.UNLINKED: (
        Verdict.WARN,
        "this checkout reads as in-repo, but a sidecar for its identity exists at {evidence}",
        "the shadow was removed (a git clean), or this checkout was never linked",
        # `link` creates only from an empty slot, so a real directory in the
        # way has to be moved aside by hand first -- say so, or the printed
        # fix is inert exactly when it is needed.
        f"{_LINK_FIX}  (a real .ai-state directory here must be moved aside first)",
    ),
}

_SHADOW_ROWS: dict[ShadowState, _RowSpec] = {
    ShadowState.LINKED: (Verdict.PASS, "{path} -> sidecar", None, None),
    ShadowState.MISSING: (Verdict.WARN, "{path} is missing in this checkout", None, _LINK_FIX),
    ShadowState.DANGLING: (Verdict.WARN, "{path} is a dangling symlink", None, _LINK_FIX),
    ShadowState.BLOCKED: (
        Verdict.FAIL,
        "a real file occupies the {path} slot, not a symlink",
        "a git pull or a local edit brought a real file into a shadowed slot",
        "mv {path} {path}.team && praxion-sidecar link",
    ),
    ShadowState.FOREIGN: (
        Verdict.FAIL,
        "{path} is a symlink pointing outside this sidecar",
        "linked by a different sidecar, or the sidecar was recreated",
        _LINK_FIX,
    ),
}

_SHARED_ROWS: dict[SharedState, _RowSpec] = {
    SharedState.SHARED: (Verdict.PASS, "{path} committed in the project repo", None, None),
    SharedState.UNEXPECTED_SYMLINK: (
        Verdict.WARN,
        "{path} is a symlink but is declared shared",
        None,
        _LINK_FIX,
    ),
}


def _templated_row(cid: str, path: str, spec: _RowSpec) -> CheckResult:
    verdict, detail, why, fix = spec
    return _row(
        cid,
        verdict,
        detail.format(path=path),
        why=why.format(path=path) if why is not None else None,
        fix=fix.format(path=path) if fix is not None else None,
    )


def _rows_placement(inputs: CheckInputs) -> list[CheckResult]:
    """The totality row: a checkout that does not resolve into its own
    sidecar is *reported*, never a refusal that suppresses every other row.

    No row at all when the placement resolves -- like `mount-orphaned` and
    `commit-lock`, this one exists to name a problem, and a row that cannot
    fail is noise (the `hooks-chained` lesson).
    """
    state = inputs.unresolved_placement
    if state is None:
        return []
    verdict, detail, why, fix = _PLACEMENT_ROWS[state.reason]
    return [
        _row(
            "placement",
            verdict,
            detail.format(evidence=state.evidence),
            why=why,
            fix=fix,
        )
    ]


def _rows_exclude_block(inputs: CheckInputs) -> list[CheckResult]:
    return [_templated_row("exclude-block", "", _EXCLUDE_BLOCK_ROWS[inputs.exclude_block])]


def _rows_shadow_slots(inputs: CheckInputs) -> list[CheckResult]:
    return [
        _templated_row(f"shadow:{path}", path, _SHADOW_ROWS[state])
        for path, state in inputs.shadow_slots.items()
    ]


def _rows_shared_slots(inputs: CheckInputs) -> list[CheckResult]:
    return [
        _templated_row(f"shared:{path}", path, _SHARED_ROWS[state])
        for path, state in inputs.shared_slots.items()
    ]


def _rows_hooks_path(inputs: CheckInputs) -> list[CheckResult]:
    """PASS: every slot fires. WARN: some do (a partial, stale chain). FAIL:
    none do, or the path is unresolvable. Judged by slot counts, not
    `hooks_path_state` names -- `"Unset"` (a plain install) and
    `"PraxionWrapper"` (an adopted foreign `core.hooksPath`) are both a
    healthy chain when nothing is stale, and both can go partially stale."""
    status = inputs.hooks_status
    state_name = status.get("hooks_path_state")
    cannot_fire = status.get("cannot_fire") or []

    if state_name == "Unresolvable":
        reason = status.get("reason", "core.hooksPath cannot be resolved")
        detail = f"core.hooksPath is unresolvable ({reason})"
        why = "core.hooksPath was re-pointed to something Praxion's chain cannot use"
        return [_row("hooks-path", Verdict.FAIL, detail, why=why, fix=_HOOKS_PATH_FIX)]
    if not cannot_fire:
        detail = "core.hooksPath resolves cleanly; every hook slot can fire"
        return [_row("hooks-path", Verdict.PASS, detail)]
    total_slots = len(status.get("slots") or [])
    if total_slots and len(cannot_fire) < total_slots:
        detail = f"{len(cannot_fire)} of {total_slots} hook slot(s) stale: {', '.join(cannot_fire)}"
        why = "a hook slot was deleted or never installed for these names"
        return [_row("hooks-path", Verdict.WARN, detail, why=why, fix=_HOOKS_PATH_FIX)]
    detail = f"no Praxion hook can fire ({state_name})"
    why = "core.hooksPath was re-pointed to a non-Praxion directory with no chain"
    return [_row("hooks-path", Verdict.FAIL, detail, why=why, fix=_HOOKS_PATH_FIX)]


def _rows_hooks_chained(inputs: CheckInputs) -> list[CheckResult]:
    """FAIL naming any wrapper slot whose Praxion chain call is missing from
    its body (`install_git_hooks.build_status()`'s per-slot `chain_intact`);
    PASS when every wrapper slot's chain call is present; no row at all when
    no wrapper file exists to check -- a plain, non-chaining install has
    nothing composed with it to lose a chain call from."""
    slots = inputs.hooks_status.get("slots") or []
    checked = [slot for slot in slots if "chain_intact" in slot]
    if not checked:
        return []
    broken = [slot["name"] for slot in checked if not slot["chain_intact"]]
    if broken:
        detail = f"chain call missing from: {', '.join(broken)}"
        why = "the wrapper body was hand-edited, or a stale wrapper predates a template change"
        return [_row("hooks-chained", Verdict.FAIL, detail, why=why, fix=_HOOKS_PATH_FIX)]
    return [_row("hooks-chained", Verdict.PASS, "chain call intact in every wrapper slot")]


def _rows_sidecar_repo(inputs: CheckInputs) -> list[CheckResult]:
    state = inputs.sidecar_repo
    if state is None:
        raise AssertionError("sidecar_repo must be set under SidecarOwned placement")
    if not state.is_git_repo:
        detail = "the sidecar is not a git repository"
        why = "init never ran, or the sidecar directory was removed"
        return [_row("sidecar-repo", Verdict.FAIL, detail, why=why, fix=_SIDECAR_REPO_FIX)]
    if state.dirty_files > 0:
        detail = f"{state.dirty_files} file(s) uncommitted in the sidecar"
        return [_row("sidecar-repo", Verdict.WARN, detail, fix=_SIDECAR_REPO_FIX)]
    if state.unpushed_commits > _UNPUSHED_COMMITS_WARN_THRESHOLD:
        detail = f"{state.unpushed_commits} commits unpushed in the sidecar"
        return [_row("sidecar-repo", Verdict.WARN, detail, fix=_SIDECAR_REPO_FIX)]
    return [_row("sidecar-repo", Verdict.PASS, "clean, no unusual backlog")]


def _rows_state_unmerged(inputs: CheckInputs) -> list[CheckResult]:
    return [
        _row(
            "state-unmerged",
            Verdict.WARN,
            f"{branch}: not converged ({getattr(state.reason, 'value', state.reason)})",
            fix=_MERGE_BACK_FIX_TEMPLATE.format(branch=branch),
        )
        for branch, state in inputs.branches.items()
        if isinstance(state, _sidecar_convergence.UnmergedIneligible)
    ]


def _rows_state_eligible(inputs: CheckInputs) -> list[CheckResult]:
    why = "a convergence channel was skipped, or a prior run aborted"
    return [
        _row(
            "state-eligible",
            Verdict.WARN,
            f"{branch}: eligible to converge but not yet merged",
            why=why,
            fix=_LINK_FIX,
        )
        for branch, state in inputs.branches.items()
        if isinstance(state, _sidecar_convergence.UnmergedEligible)
    ]


def _rows_mount_orphaned(inputs: CheckInputs) -> list[CheckResult]:
    return [
        _row(
            "mount-orphaned",
            Verdict.WARN,
            f"{name}: sidecar worktree entry has no project checkout behind it",
            fix=_MOUNT_ORPHANED_FIX,
        )
        for name in inputs.orphaned_mounts
    ]


def _rows_mount_conflict(inputs: CheckInputs) -> list[CheckResult]:
    if not inputs.mount_mid_merge:
        return []
    # Non-accusatory wording (ARCH_WT_RULING.md sec. 14, objection 5): the
    # explicit `merge-back --from` is a *sanctioned* way to reach this state,
    # and a read-only doctor cannot tell in-progress resolution from an
    # abandoned mount -- state the fact and both exits, never a violation.
    detail = "the sidecar mount is mid-merge"
    why = (
        "an explicit merge-back --from run left the merge unresolved -- a read-only "
        "doctor cannot tell in-progress resolution from an abandoned mount"
    )
    fix = "resolve the conflict and commit in the mount, or abort the merge in the mount"
    return [_row("mount-conflict", Verdict.FAIL, detail, why=why, fix=fix)]


def _rows_remote_policy(inputs: CheckInputs) -> list[CheckResult]:
    remote = inputs.remote
    if remote is None:
        return [_row("remote-policy", Verdict.PASS, "no remote configured")]
    if not remote.host_matches_origin and not remote.foreign_host_ack:
        detail = f"remote host does not match the project origin host ({remote.url})"
        why = "a foreign-host remote was set without an acknowledged --allow-foreign-host"
        return [_row("remote-policy", Verdict.FAIL, detail, why=why, fix=_REMOTE_POLICY_FIX)]
    # No upstream check: the autocommit push names the remote and the branch
    # explicitly, so a missing tracking configuration cannot make it misfire.
    return [_row("remote-policy", Verdict.PASS, f"remote configured ({remote.url})")]


def _rows_manifest_roots(inputs: CheckInputs) -> list[CheckResult]:
    """The manifest's `project.roots` (the identity anchor) names this
    checkout -- WARN when it does not, since the checkout was moved or the
    manifest predates it (`link` re-derives and re-writes `roots`)."""
    if inputs.guards_roots_stale:
        detail = "roots: this checkout is not among the manifest's recorded roots"
        return [_row("manifest-roots", Verdict.WARN, detail, fix=_LINK_FIX)]
    return [
        _row("manifest-roots", Verdict.PASS, "roots: this checkout is recorded in the manifest")
    ]


def _rows_commit_lock(inputs: CheckInputs) -> list[CheckResult]:
    """The per-mount commit lock (`_sidecar_commit.read_lock_state`) --
    WARN on a held or abandoned lock, no row on `Idle` (nothing to report)."""
    state = inputs.lock_state
    if state is None or isinstance(state, _sidecar_commit.Idle):
        return []
    if isinstance(state, _sidecar_commit.Committing):
        detail = f"commit lock held by pid {state.holder_pid} since {state.since}"
        why = "a commit is in progress -- normal under contention, expected to clear quickly"
        return [_row("commit-lock", Verdict.WARN, detail, why=why, fix=_COMMIT_LOCK_WAIT_FIX)]
    detail = f"commit lock abandoned by pid {state.holder_pid} since {state.since}"
    why = "the holder died before releasing -- the next committer overwrites the stale record"
    return [_row("commit-lock", Verdict.WARN, detail, why=why, fix=_SIDECAR_REPO_FIX)]


# The pinned row order: placement, exclude-block, shadow:<path>*,
# shared:<path>*, hooks-path, hooks-chained, sidecar-repo, then the four
# convergence rows, then remote-policy, manifest-roots, commit-lock.
# Split into four lists only for the non-sidecar gate in `evaluate_checks` --
# `_PLACEMENT_ROW_FUNCS` and `_HOOK_ROW_FUNCS` run under every placement.
_PLACEMENT_ROW_FUNCS = [_rows_placement]
_SIDECAR_HEAD_ROW_FUNCS = [_rows_exclude_block, _rows_shadow_slots, _rows_shared_slots]
_HOOK_ROW_FUNCS = [_rows_hooks_path, _rows_hooks_chained]
_SIDECAR_TAIL_ROW_FUNCS = [
    _rows_sidecar_repo,
    _rows_state_unmerged,
    _rows_state_eligible,
    _rows_mount_orphaned,
    _rows_mount_conflict,
    _rows_remote_policy,
    _rows_manifest_roots,
    _rows_commit_lock,
]


# --- reductions + renderings -------------------------------------------------


def overall_verdict(results: Sequence[CheckResult]) -> Verdict:
    """The worst verdict across all rows; an empty result set is vacuously
    healthy. Keys off `_VERDICT_SEVERITY` rather than comparing `Verdict`
    members directly -- see the class docstring."""
    if not results:
        return Verdict.PASS
    return max(results, key=lambda row: _VERDICT_SEVERITY[row.verdict]).verdict


def counts(results: Sequence[CheckResult]) -> dict[str, int]:
    tally = {verdict.value: 0 for verdict in Verdict}
    for row in results:
        tally[row.verdict.value] += 1
    return tally


def render_doctor_json(results: Sequence[CheckResult]) -> dict:
    """`doctor --json` (INTERFACE_DESIGN.md sec. 7.2). Pass rows omit `why`/
    `fix` entirely rather than null-filling them."""
    return {
        "schema": _SCHEMA_VERSION,
        "verdict": overall_verdict(results).value,
        "counts": counts(results),
        "checks": [_row_to_json(row) for row in results],
    }


def _row_to_json(row: CheckResult) -> dict:
    payload: dict[str, object] = {"id": row.id, "verdict": row.verdict.value, "detail": row.detail}
    if row.why is not None:
        payload["why"] = row.why
    if row.fix is not None:
        payload["fix"] = row.fix
    return payload


_VERDICT_TOKENS = {Verdict.PASS: "PASS", Verdict.WARN: "WARN", Verdict.FAIL: "FAIL"}
_VERDICT_ANSI_CODES = {Verdict.PASS: "32", Verdict.WARN: "33", Verdict.FAIL: "31"}
_ANSI_RESET = "\x1b[0m"


def render_doctor_text(results: Sequence[CheckResult], *, color: bool) -> str:
    """`doctor`'s table (INTERFACE_DESIGN.md sec. 3.2): 4-char verdict token,
    two-space gutter, a stable check name, a truncatable detail; `why`/`fix`
    sub-lines only on non-pass rows. Color wraps the verdict token only --
    stripping `\\x1b[...m` escapes from a colored render reproduces the
    plain render exactly, so color is never a second source of content."""
    lines: list[str] = []
    for row in results:
        lines.append(_verdict_line(row, color=color))
        if row.why is not None:
            lines.append(f"      why   {row.why}")
        if row.fix is not None:
            lines.append(f"      fix   {row.fix}")

    tally = counts(results)
    summary = (
        f"{tally[Verdict.FAIL.value]} failed · "
        f"{tally[Verdict.WARN.value]} warnings · "
        f"{tally[Verdict.PASS.value]} passed."
    )
    tail = (
        "Healthy."
        if overall_verdict(results) is Verdict.PASS
        else "Fix the failures above, then re-run: praxion-sidecar doctor"
    )
    lines.extend(["", summary, tail])
    return "\n".join(lines)


def _verdict_line(row: CheckResult, *, color: bool) -> str:
    token = _VERDICT_TOKENS[row.verdict]
    if color:
        token = f"\x1b[{_VERDICT_ANSI_CODES[row.verdict]}m{token}{_ANSI_RESET}"
    return f"{token}  {row.id}  {row.detail}"


def path_states(inputs: CheckInputs) -> list[dict]:
    """`status --json`'s `paths[]` projection (INTERFACE_DESIGN.md sec. 7.1).
    Shadow/share rows carry `state`; untouched rows carry `reason` instead --
    never both, since the `state` domain is keyed by `intent`."""
    rows: list[dict] = []
    for path, state in inputs.shadow_slots.items():
        rows.append({"path": path, "intent": "shadow", "state": state.value})
    for path, state in inputs.shared_slots.items():
        rows.append({"path": path, "intent": "share", "state": state.value})
    for path, reason in inputs.untouched_paths.items():
        rows.append({"path": path, "intent": "untouched", "reason": reason})
    return rows
