"""The world, read once into the shapes `status` and `doctor` consume.

`_sidecar_checks` is pure by construction -- it performs no git, filesystem or
environment read, and its module docstring names "the CLI wiring layer" as the
owner of that classification. This module *is* that layer: every `CheckInputs`
field arrives here already classified, so the registry stays a function of its
inputs and there is exactly one place where "what is on disk" becomes "what
the registry judges".

`gather()` returns two things because two questions are being answered:
`CheckInputs` for the D3 registry, and `Facts` for the parts of a `status`
report no check row has an opinion about (where the sidecar is, which checkout
this is, when the last commit landed).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import _sidecar_checks as checks
import _sidecar_commit
import _sidecar_convergence as convergence
import _sidecar_git as gitp
import _sidecar_identity as identity
import _sidecar_link as linker
import _sidecar_manifest as manifests
import _sidecar_mount as mounts
import _sidecar_render as render
import _state_repo
import install_git_hooks
from _git_runner import git_output
from _sidecar_cli import Context, Refused, refusal, require_sidecar

_WORKTREE_PREFIX = "worktree "


@dataclasses.dataclass(frozen=True)
class Facts:
    """The report-only facts `status` renders and no check row consumes.

    `sidecar` and `manifest` are absent together under in-repo placement --
    they are the sidecar half of the report, and `status_of` keys the payload's
    whole shape off their presence.
    """

    checkout: render.Checkout
    origin: str | None
    sidecar: render.SidecarFacts | None
    manifest: manifests.Manifest | None


def gather(context: Context) -> tuple[checks.CheckInputs, Facts]:
    """Classify this checkout: the registry's inputs, and the report's facts.

    **Total over the resolver's five variants.** The three that carry
    no sidecar of this project's -- `Dangling`, `Foreign`, `NotYetLinked` --
    are classified into the `placement` row rather than raised, so `doctor`
    reports them (in JSON when asked) instead of refusing before its first
    row. `status` narrows this itself, through `require_reportable_placement`.
    """
    placement = _state_repo.resolve_placement(context.checkout)
    checkout = _checkout_facts(context.checkout)
    if not isinstance(placement, _state_repo.SidecarOwned):
        facts = Facts(
            checkout=checkout,
            origin=observed_origin(context.checkout),
            sidecar=None,
            manifest=None,
        )
        return _hooks_only_inputs(context, placement), facts

    project_id = identity.slug(identity.derive_project_id(context.checkout))
    sidecar, manifest = require_sidecar(context, project_id)
    mount = placement.state_git_root
    repo_state = _sidecar_repo_state(mount)
    inputs = checks.CheckInputs(
        placement=placement,
        exclude_block=_exclude_block_state(context.checkout, manifest),
        shadow_slots=_shadow_states(context.checkout, manifest),
        shared_slots=_shared_states(context.checkout, manifest),
        untouched_paths=_untouched_reasons(manifest),
        hooks_status=_hooks_status(context.checkout),
        mount=mounts.classify_mount(
            context.checkout, expected_common_dir=(sidecar / ".git").resolve()
        ),
        branches=_branch_states(sidecar, context.checkout),
        orphaned_mounts=_orphaned_mount_names(sidecar),
        mount_mid_merge=gitp.merge_in_progress(mount),
        sidecar_repo=repo_state,
        remote=_remote_state(manifest, context.checkout),
        guards_roots_stale=context.checkout
        not in {Path(root).resolve() for root in manifest.project.roots},
        lock_state=_sidecar_commit.read_lock_state(mount),
        unresolved_placement=None,
    )
    facts = Facts(
        checkout=checkout,
        origin=manifest.project.origin,
        sidecar=render.SidecarFacts(
            root=sidecar,
            branch=placement.branch,
            dirty_files=repo_state.dirty_files,
            unpushed_commits=repo_state.unpushed_commits,
            last_commit_at=git_output(mount, "log", "-1", "--format=%cI"),
        ),
        manifest=manifest,
    )
    return inputs, facts


def status_of(context: Context, inputs: checks.CheckInputs, facts: Facts, results: list):
    """Project the registry's verdict and the report facts into one `Status`."""
    failed = _failed_check_ids(results)
    tally = checks.counts(results)
    healthy = checks.overall_verdict(results) is checks.Verdict.PASS
    if facts.manifest is None or facts.sidecar is None:
        return render.InRepoStatus(
            project_root=context.checkout,
            origin=facts.origin,
            checkout=facts.checkout,
            healthy=healthy,
            failed_checks=failed,
            counts=tally,
            placement_note=_placement_note(results),
        )
    return render.SidecarStatus(
        project_root=context.checkout,
        origin=facts.origin,
        project_id=facts.manifest.project.id,
        checkout=facts.checkout,
        sidecar=facts.sidecar,
        remote=_remote_facts(inputs.remote),
        autocommit=facts.manifest.autocommit.value,
        paths=tuple(checks.path_states(inputs)),
        healthy=healthy,
        failed_checks=failed,
        counts=tally,
    )


# `status --json`'s `failed_checks` entries are bare check ids by default
# (`row.id`) -- fine for every check except the two convergence rows,
# which emit one row PER BRANCH but all share the same bare id
# ("state-unmerged"/"state-eligible"), so the branch identity that
# `_sidecar_checks.py` puts in `row.detail` (formatted `"{branch}: ..."`)
# would otherwise be lost on the way into the JSON payload. This is the
# STATUS payload's own minimal projection choice -- `_sidecar_checks.py`'s
# row id and `doctor`'s own JSON/table renderings are untouched.
_BRANCH_SUFFIXED_CHECK_IDS = frozenset({"state-unmerged", "state-eligible"})

_PLACEMENT_CHECK_ID = "placement"


def _placement_note(results: list) -> str | None:
    """`status`'s one-line qualifier, lifted from the `placement` row itself.

    Read off the row rather than re-composed here, so an in-repo report can
    never claim plain in-repo placement in wording the check registry has
    already contradicted.
    """
    return next((row.detail for row in results if row.id == _PLACEMENT_CHECK_ID), None)


def _failed_check_ids(results: list) -> tuple[str, ...]:
    ids: list[str] = []
    for row in results:
        if row.verdict is checks.Verdict.PASS:
            continue
        if row.id in _BRANCH_SUFFIXED_CHECK_IDS:
            branch = row.detail.split(":", 1)[0]
            ids.append(f"{row.id}:{branch}")
        else:
            ids.append(row.id)
    return tuple(ids)


def unresolvable_placement(placement: _state_repo.Placement, action: str = "report") -> Refused:
    """The three unwritable variants -- reportable states, but not *by* status.

    `action` names the verb that is refusing (`report` for status, `commit`
    for commit) so the first line of the refusal tells the operator which
    command declined, not which command the helper was written for.

    All three mean the checkout's `.ai-state` does not resolve into a sidecar
    this command can report on, so there is no honest report to render.
    `link` is the repair for the first two -- `NotYetLinked` is a worktree
    whose mount was never created and `Dangling` a shadow whose mount went
    away -- and the third is the operator's decision.
    """
    if isinstance(placement, _state_repo.NotYetLinked):
        return refusal(
            f"Refusing to {action}: this checkout has no .ai-state yet.",
            f"It is a worktree of {placement.main_checkout_root}, whose sidecar is "
            f"{placement.sidecar_common_dir.parent} — but no state mount has been "
            "created here.",
            "Materialise it:  praxion-sidecar link",
        )
    if isinstance(placement, _state_repo.Dangling):
        return refusal(
            f"Refusing to {action}: .ai-state is a dangling symlink.",
            f"It records {placement.link_target}, which does not exist — usually a mount "
            "that has not been materialised in this checkout yet.",
            "Materialise it:  praxion-sidecar link",
        )
    return refusal(
        f"Refusing to {action}: .ai-state points at a different sidecar.",
        f"found:    {placement.link_path}\nreason:   {placement.reason.value}",
        "Remove it and re-link:  rm .ai-state && praxion-sidecar link",
    )


def require_reportable_placement(placement: _state_repo.Placement) -> None:
    """`status`'s own narrowing: it renders a placement, so it needs one.

    `doctor` is total (it reports the unresolved variants as a row); `status`
    describes *where this project's state lives*, and for the three variants
    below there is no honest answer to render -- so the refusal stays here,
    at the one verb whose report depends on it, instead of inside `gather`
    where it would suppress `doctor`'s rows too.
    """
    if not isinstance(placement, (_state_repo.InRepo, _state_repo.SidecarOwned)):
        raise unresolvable_placement(placement)


def _hooks_only_inputs(context: Context, placement: _state_repo.Placement) -> checks.CheckInputs:
    """Every non-sidecar placement: the two P0 hook rows (sec. 7.3), plus the
    `placement` row when this checkout does not resolve into its own sidecar."""
    return checks.CheckInputs(
        placement=placement,
        exclude_block=None,
        shadow_slots={},
        shared_slots={},
        untouched_paths={},
        hooks_status=_hooks_status(context.checkout),
        mount=mounts.classify_mount(context.checkout),
        branches={},
        orphaned_mounts=(),
        mount_mid_merge=False,
        sidecar_repo=None,
        remote=None,
        guards_roots_stale=False,
        lock_state=None,
        unresolved_placement=_unresolved_placement(context, placement),
    )


def _unresolved_placement(
    context: Context, placement: _state_repo.Placement
) -> checks.UnresolvedPlacement | None:
    """The `placement` row's evidence, or `None` when the placement is fine.

    Read-only and offline by construction: the `InRepo` arm's only question
    is whether a sidecar *file* exists at the configured root for this
    checkout's derived identity -- the shape where a `git clean -ffdx`
    removed the shadow and the checkout silently reads as in-repo again.
    """
    if isinstance(placement, _state_repo.Dangling):
        return checks.UnresolvedPlacement(
            reason=checks.UnresolvedReason.DANGLING, evidence=str(placement.link_target)
        )
    if isinstance(placement, _state_repo.Foreign):
        return checks.UnresolvedPlacement(
            reason=checks.UnresolvedReason.FOREIGN,
            evidence=f"{placement.reason.value}: {placement.resolved_target}",
        )
    if isinstance(placement, _state_repo.NotYetLinked):
        return checks.UnresolvedPlacement(
            reason=checks.UnresolvedReason.UNLINKED,
            evidence=render.abbreviate_home(placement.sidecar_common_dir.parent),
        )
    sidecar = _sidecar_for_identity(context)
    if sidecar is None:
        return None
    return checks.UnresolvedPlacement(
        reason=checks.UnresolvedReason.UNLINKED, evidence=render.abbreviate_home(sidecar)
    )


def _sidecar_for_identity(context: Context) -> Path | None:
    """The sidecar this checkout's identity would use, if one exists there."""
    try:
        slug = identity.slug(identity.derive_project_id(context.checkout))
    except identity.InvalidProjectId:
        return None
    sidecar = context.sidecar_dir(slug)
    return sidecar if manifests.manifest_path(sidecar / ".git").is_file() else None


# --- the project side --------------------------------------------------------


def worktree_paths(repo: Path) -> list[Path]:
    """Every worktree `repo` has registered, in git's own listing order."""
    listing = git_output(repo, "worktree", "list", "--porcelain") or ""
    return [
        Path(line[len(_WORKTREE_PREFIX) :])
        for line in listing.splitlines()
        if line.startswith(_WORKTREE_PREFIX)
    ]


def sidecar_mounts(sidecar: Path) -> list[Path]:
    """Every `<checkout>/.praxion-state` the sidecar has registered as a worktree."""
    return [path for path in worktree_paths(sidecar) if path.name == mounts.MOUNT_DIRNAME]


def checkout_of(mount: Path) -> Path:
    return mount.parent


def observed_origin(checkout: Path) -> str | None:
    return git_output(checkout, "config", "--get", "remote.origin.url")


def _checkout_facts(checkout: Path) -> render.Checkout:
    paths = [path.resolve() for path in worktree_paths(checkout)] or [checkout]
    index = paths.index(checkout) + 1 if checkout in paths else 1
    kind = "worktree" if (checkout / ".git").is_file() else "main"
    return render.Checkout(root=checkout, kind=kind, index=index, total=len(paths))


def _exclude_block_state(checkout: Path, manifest: manifests.Manifest) -> checks.ExcludeBlockState:
    exclude_path = linker.project_common_git_dir(checkout) / "info" / "exclude"
    existing, expected = linker.compute_new_exclude_text(
        exclude_path, linker.exclude_lines(manifest)
    )
    if linker.BLOCK_START not in existing:
        return checks.ExcludeBlockState.ABSENT
    return (
        checks.ExcludeBlockState.CURRENT
        if existing == expected
        else checks.ExcludeBlockState.DRIFTED
    )


def _shadow_states(checkout: Path, manifest: manifests.Manifest) -> dict[str, checks.ShadowState]:
    """One resolved state per `intent: shadow` slot.

    `LinkToThisSidecar` splits on whether the target resolves: a correct
    symlink into an unmaterialised mount is `dangling` (a WARN `link` repairs),
    not `linked` -- the distinction the registry's row set exists to make.
    """
    states: dict[str, checks.ShadowState] = {}
    for relpath, entry in manifest.paths.items():
        if not isinstance(entry, manifests.ShadowEntry):
            continue
        slot = linker.classify_shadow_slot(checkout, relpath, linker.shadow_target(relpath))
        if isinstance(slot, linker.LinkToThisSidecar):
            resolves = (checkout / relpath).exists()
            states[relpath] = checks.ShadowState.LINKED if resolves else checks.ShadowState.DANGLING
        elif isinstance(slot, linker.LinkElsewhere):
            states[relpath] = checks.ShadowState.FOREIGN
        elif isinstance(slot, linker.RealPath):
            states[relpath] = checks.ShadowState.BLOCKED
        else:
            states[relpath] = checks.ShadowState.MISSING
    return states


def _shared_states(checkout: Path, manifest: manifests.Manifest) -> dict[str, checks.SharedState]:
    return {
        relpath: (
            checks.SharedState.UNEXPECTED_SYMLINK
            if (checkout / relpath).is_symlink()
            else checks.SharedState.SHARED
        )
        for relpath, entry in manifest.paths.items()
        if isinstance(entry, manifests.ShareEntry)
    }


def _untouched_reasons(manifest: manifests.Manifest) -> dict[str, str]:
    default = manifests.UntouchedReason.OPERATOR_CHOICE.value
    return {
        relpath: (entry.reason.value if entry.reason else default)
        for relpath, entry in manifest.paths.items()
        if isinstance(entry, manifests.UntouchedEntry)
    }


def _hooks_status(checkout: Path) -> dict:
    """P0's hook-chain report -- but only once Praxion has hooks in this repo.

    `build_status` answers "can each Praxion hook slot fire", and in a repo
    that never installed them the honest answer is *not applicable* rather
    than "every slot is broken". The registry's row has no not-applicable
    state, so absence is expressed as an empty inventory: no slots, none
    stale. A repo with a partially-installed chain still reports it in full.
    """
    plugin_root = Path(__file__).resolve().parent.parent
    status = install_git_hooks.build_status(checkout, plugin_root)
    installed = any(slot.get("praxion_can_fire") for slot in status.get("slots") or [])
    adopted = status.get("hooks_path_state") != "Unset"
    return status if (installed or adopted) else {}


# --- the sidecar side --------------------------------------------------------


def _sidecar_repo_state(mount: Path) -> checks.SidecarRepoState:
    status = gitp.porcelain_status(mount) or ""
    dirty = len([line for line in status.splitlines() if line.strip()])
    return checks.SidecarRepoState(
        is_git_repo=True, dirty_files=dirty, unpushed_commits=_unpushed_commits(mount)
    )


def _unpushed_commits(mount: Path) -> int:
    """Commits ahead of the upstream, counted locally -- `doctor` never fetches.

    With no upstream configured there is nothing to be ahead *of*, so the
    answer is 0 rather than an estimate that would need the network to check.
    """
    if git_output(mount, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"):
        return int(git_output(mount, "rev-list", "--count", "@{upstream}..HEAD") or 0)
    return 0


def _branch_states(sidecar: Path, checkout: Path) -> dict:
    return {
        branch: convergence.classify_branch(sidecar, checkout, branch, checkout)
        for branch in gitp.branches_with_prefix(sidecar, mounts.STATE_BRANCH_PREFIX)
    }


def _orphaned_mount_names(sidecar: Path) -> tuple[str, ...]:
    return tuple(
        checkout_of(mount).name
        for mount in sidecar_mounts(sidecar)
        if not checkout_of(mount).is_dir()
    )


def _remote_state(manifest: manifests.Manifest, checkout: Path) -> checks.RemoteState | None:
    remote = manifest.remote
    if remote is None:
        return None
    return checks.RemoteState(
        url=remote.url,
        push=remote.push.value,
        host_matches_origin=_host_of(remote.url) == _host_of(observed_origin(checkout)),
        foreign_host_ack=remote.foreign_host_ack,
    )


def _host_of(url: str | None) -> str | None:
    normalized = _state_repo.normalize_origin(url) if url else None
    return normalized.partition("/")[0] if normalized else None


def _remote_facts(remote: checks.RemoteState | None) -> render.RemoteFacts | None:
    if remote is None:
        return None
    return render.RemoteFacts(
        url=remote.url, push=remote.push, host_matches_origin=remote.host_matches_origin
    )
