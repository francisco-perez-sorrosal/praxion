"""The three verbs that change *where* state lives, or where it may be pushed.

`publish` and `absorb` are the same move in opposite directions, and they share
one primitive: `graft_state_history`. Both repositories already keep their state
under the same `.ai-state/` prefix, so moving it is a single unrelated-histories
merge that adopts the other side's `.ai-state/` subtree wholesale -- the merge's
tree is then identical to the source's at that path, which is exactly the
condition git's default history simplification needs to keep following the
source's commits through `git log -- .ai-state`.

That is why neither verb uses `git subtree add`, despite the design naming it:
`subtree add` merges a *split* history whose paths sit at the root, so the
resulting merge is TREESAME to neither parent at `.ai-state/` and `git log --
.ai-state` stops dead at the import commit. Verified empirically, both ways,
before this module was written; the history is the whole point of the move, so
the mechanism that preserves it wins over the mechanism that was named.

`publish` performs the one sanctioned commit to the *project* repository in the
whole CLI -- the import merge itself. It is operator-confirmed (`--yes`), never
automatic, and the confirmation text says so in as many words.

`remote` shares this file because it belongs to the same question -- where may
this project's intelligence go? -- and because its host gate is the same kind of
boundary refusal as `publish`'s.
"""

from __future__ import annotations

import dataclasses
import shutil
from datetime import datetime, timezone
from pathlib import Path

import _sidecar_git as gitp
import _sidecar_identity as identity
import _sidecar_init as initializer
import _sidecar_inputs as inputs
import _sidecar_link as linker
import _sidecar_manifest as manifests
import _sidecar_mount as mounts
import _sidecar_render as render
from _sidecar_cli import Context, EnvironmentProblem, refusal
from _sidecar_mergeback import DRY_RUN_TRAILER, Report

STATE_DIRNAME = mounts.STATE_DIRNAME
PRE_PUBLISH_TAG_PREFIX = "praxion/pre-publish/"
_TAG_TIMESTAMP = "%Y%m%d-%H%M%S"
RETIRED_SUFFIX = ".published-"

PUBLISH_CONFIRMATION = (
    "publish moves every shadowed path into the project repository and removes "
    "the sidecar's mounts.\nThis creates one merge commit in the *project* repo — "
    "the only commit praxion-sidecar ever makes there."
)
ABSORB_CONFIRMATION = (
    "absorb moves the project's committed .ai-state/ into a sidecar outside the "
    "repository.\nThe removal is left staged for you to commit; absorb never "
    "commits to the project repo."
)


# --- the shared primitive ---------------------------------------------------


def graft_state_history(target: Path, source: Path, ref: str, message: str) -> None:
    """Adopt ``source``'s ``.ai-state/`` subtree into ``target``, with history.

    ``-s ours`` keeps every other path in the target untouched; the checkout
    that follows replaces exactly one directory. The result is one merge commit
    whose second parent is the source's history and whose `.ai-state/` tree is
    the source's, byte for byte.
    """
    gitp.run_or_raise(target, EnvironmentProblem, "fetch", "-q", str(source), ref)
    gitp.run_or_raise(
        target,
        EnvironmentProblem,
        "merge",
        "-q",
        "--no-commit",
        "--no-ff",
        "--allow-unrelated-histories",
        "-s",
        "ours",
        "FETCH_HEAD",
    )
    gitp.run_or_raise(target, EnvironmentProblem, "checkout", "FETCH_HEAD", "--", STATE_DIRNAME)
    gitp.run_or_raise(
        target, EnvironmentProblem, *gitp.identity_args(target), "commit", "-q", "-m", message
    )


# --- publish ----------------------------------------------------------------


def publish(
    context: Context, sidecar: Path, manifest: manifests.Manifest, *, dry_run: bool
) -> Report:
    """Move the sidecar's state into the project repo and dismantle the sidecar."""
    checkout = context.checkout
    _require_clean_project(checkout, "publish")
    _require_every_branch_merged(sidecar)
    mounts_to_remove = inputs.sidecar_mounts(sidecar)
    _require_every_mount_removable(mounts_to_remove)
    mounted = [inputs.checkout_of(mount) for mount in mounts_to_remove]
    if dry_run:
        return Report((*_publish_plan(checkout, sidecar, mounted), DRY_RUN_TRAILER))

    tag = _tag_pre_publish(sidecar)
    keepsakes = _read_shadowed_files(checkout, manifest)
    # The import runs FIRST, while everything it might have to be undone
    # against is still standing: it is the only step here that can fail, and
    # a failure after the teardown would leave a checkout with no mount, no
    # exclude block and no state -- unrecoverable by any command this CLI has.
    _import_state_history(checkout, sidecar)
    _dismantle_sidecar(checkout, sidecar, manifest, mounted, keepsakes)
    retired = _retire_sidecar(sidecar)
    return Report(
        (
            f"Published {STATE_DIRNAME}/ into {checkout} with its full history.",
            f"Removed {len(mounted)} mount(s) and every wt/* state branch.",
            *_keepsake_notice(keepsakes),
            f"The old sidecar is kept as a backup at {render.abbreviate_home(retired)}, "
            f"tagged {tag} — delete it once you trust the published history.",
            "Next: praxion-sidecar status",
        )
    )


def _retire_sidecar(sidecar: Path) -> Path:
    """Move the published sidecar out of the identity slot, keeping the bytes.

    The sidecar is worth keeping -- it is the only copy of the state that
    existed before the import merge -- but keeping it *at its canonical path*
    makes the slot look occupied to everything that derives it from the project
    id. `absorb`, publish's own documented inverse, then refuses with "already
    initialised for this project", so a published project could never go back.
    Renaming keeps the backup and frees the slot, which is what makes
    publish -> commit -> absorb a real round trip.
    """
    stamp = datetime.now(timezone.utc).strftime(_TAG_TIMESTAMP)
    retired = sidecar.with_name(f"{sidecar.name}{RETIRED_SUFFIX}{stamp}")
    attempt = 1
    while retired.exists():
        attempt += 1
        retired = sidecar.with_name(f"{sidecar.name}{RETIRED_SUFFIX}{stamp}-{attempt}")
    sidecar.rename(retired)
    return retired


def _keepsake_notice(keepsakes: dict[str, str]) -> tuple[str, ...]:
    """Name the machine-local files publish turned back into plain files.

    They were shadows, so the project never tracked them and the exclude block
    that hid them is gone -- they now show up as untracked. Saying so is the
    difference between a deliberate outcome and a surprise in `git status`.
    """
    if not keepsakes:
        return ()
    return (
        f"Left {', '.join(sorted(keepsakes))} as untracked local file(s) — "
        "add them to .gitignore if you keep them.",
    )


def _import_state_history(checkout: Path, sidecar: Path) -> None:
    """Land the sidecar's state, and its history, in the project repository.

    The one commit praxion-sidecar ever makes in a project repo -- and the
    only reversible-but-fallible step publish has, which is why it runs before
    any teardown. The `.ai-state` shadow has to go first regardless (git would
    otherwise follow the symlink and write the imported tree *into the mount*),
    so it is restored on the way out: a failed publish leaves the checkout
    exactly as it found it, with no `--abort` for the operator to remember.

    The merge is `-s ours`, so it cannot conflict; a failure here is a
    rejecting pre-commit hook or a git error, and neither leaves partial work
    worth preserving.
    """
    state_link = checkout / STATE_DIRNAME
    if state_link.is_symlink():
        state_link.unlink()
    try:
        graft_state_history(
            checkout, sidecar, "main", "chore(state): publish Praxion state into the repository."
        )
    except (EnvironmentProblem, OSError) as error:
        gitp.succeeds(checkout, "merge", "--abort")
        _restore_state_shadow(checkout)
        raise EnvironmentProblem(
            "\n".join(
                [
                    "Publishing stopped while importing the state history — nothing was published.",
                    str(error),
                    "The merge was rolled back; mounts, branches, shadows and the exclude "
                    "block are untouched.",
                    "Fix the cause above, then re-run:  praxion-sidecar publish --yes",
                ]
            )
        ) from error


def _restore_state_shadow(checkout: Path) -> None:
    """Put the `.ai-state` shadow back, unless something already occupies it."""
    slot = checkout / STATE_DIRNAME
    if slot.exists() or slot.is_symlink():
        return
    slot.symlink_to(linker.shadow_target(STATE_DIRNAME), target_is_directory=True)


def _dismantle_sidecar(
    checkout: Path,
    sidecar: Path,
    manifest: manifests.Manifest,
    mounted: list[Path],
    keepsakes: dict[str, str],
) -> None:
    """Remove the sidecar plumbing, now that the project owns the state.

    Runs only after the import commit exists, so every step here is a pure
    removal of something the project no longer needs -- nothing in it can
    strand state that is not already committed.
    """
    for owner in mounted:
        mounts.prune_mount(sidecar, owner)
        _remove_shadow_links(owner, manifest)
    _delete_state_branches(sidecar)
    _restore_as_real_files(checkout, keepsakes)
    linker.remove_exclude_block(_exclude_path(checkout))


def _publish_plan(checkout: Path, sidecar: Path, mounted: list[Path]) -> tuple[str, ...]:
    return (
        f"Would import {render.abbreviate_home(sidecar)} (main) into "
        f"{checkout}/{STATE_DIRNAME} as one merge commit.",
        f"Would remove {len(mounted)} mount(s), every wt/* branch, and the exclude block.",
        f"Would keep the old sidecar as a backup, renamed with a {RETIRED_SUFFIX}<timestamp> suffix.",
    )


def _tag_pre_publish(sidecar: Path) -> str:
    """Mark the exact commit the project is about to import, so it is findable."""
    tag = PRE_PUBLISH_TAG_PREFIX + datetime.now(timezone.utc).strftime(_TAG_TIMESTAMP)
    gitp.run_or_raise(sidecar, EnvironmentProblem, "tag", "-f", tag, "main")
    return tag


def _require_every_branch_merged(sidecar: Path) -> None:
    """Publishing exports ``main``; anything not in it would be left behind."""
    stranded = [
        branch
        for branch in gitp.branches_with_prefix(sidecar, mounts.STATE_BRANCH_PREFIX)
        if not gitp.is_ancestor(sidecar, branch, "main")
    ]
    if not stranded:
        return
    raise refusal(
        f"Refusing to publish: {len(stranded)} state branch(es) carry work main does not.",
        "publish exports main only — " + ", ".join(stranded) + " would be left behind.",
        "Converge them first:  praxion-sidecar merge-back --auto",
    )


def _require_every_mount_removable(mounts_to_remove: list[Path]) -> None:
    """Every refusal publish can raise must be raised *before* the import.

    The teardown removes each mount, and `prune_mount` rightly refuses a mount
    with uncommitted work -- but it runs *after* the import commit, so that
    refusal used to leave the project reporting `in-repo` while a live
    `.praxion`, every `wt/*` branch and the exclude block were all still
    standing: a state neither placement describes and no verb can undo.
    Checking every mount here makes the whole verb all-or-nothing, and lists
    *every* offender at once rather than making the operator discover them one
    failed publish at a time.
    """
    offenders: list[tuple[Path, str]] = []
    for mount in mounts_to_remove:
        if gitp.merge_in_progress(mount):
            offenders.append((mount, "is mid-merge"))
            continue
        status = gitp.porcelain_status(mount)
        if status is None:
            offenders.append((mount, "could not be read by git"))
        elif status.strip():
            offenders.append((mount, "has uncommitted changes"))
    if not offenders:
        return
    raise refusal(
        f"Refusing to publish: {len(offenders)} state mount(s) are not safe to remove.",
        "publish removes every mount, and removing one with unsaved state would "
        "destroy work no commit holds — so nothing has been published.",
        *(
            f"{render.abbreviate_home(mount)} {problem} — "
            f"commit it:  praxion-sidecar commit   (run from {inputs.checkout_of(mount)})"
            for mount, problem in offenders
        ),
    )


def _delete_state_branches(sidecar: Path) -> None:
    for branch in gitp.branches_with_prefix(sidecar, mounts.STATE_BRANCH_PREFIX):
        mounts.drop_branch(sidecar, branch)


def _read_shadowed_files(checkout: Path, manifest: manifests.Manifest) -> dict[str, str]:
    """Read every shadowed *file* before its mount disappears underneath it.

    The state directory is excluded: the import merge brings it back as real,
    tracked content. These others are machine-local files the project never
    tracked, so publish leaves them as plain files rather than losing them.
    """
    contents = {}
    for relpath, entry in manifest.paths.items():
        if not isinstance(entry, manifests.ShadowEntry) or relpath == STATE_DIRNAME:
            continue
        slot = checkout / relpath
        if slot.is_symlink() and slot.is_file():
            contents[relpath] = slot.read_text(encoding="utf-8")
    return contents


def _remove_shadow_links(checkout: Path, manifest: manifests.Manifest) -> None:
    for relpath, entry in manifest.paths.items():
        slot = checkout / relpath
        if isinstance(entry, manifests.ShadowEntry) and slot.is_symlink():
            slot.unlink()


def _restore_as_real_files(checkout: Path, contents: dict[str, str]) -> None:
    for relpath, text in contents.items():
        slot = checkout / relpath
        slot.parent.mkdir(parents=True, exist_ok=True)
        slot.write_text(text, encoding="utf-8")


# --- absorb -----------------------------------------------------------------


def absorb(context: Context, *, shadows: list[str], shares: list[str], dry_run: bool) -> Report:
    """Move the project's committed state into a new sidecar, then mount it."""
    checkout = context.checkout
    _require_tracked_state_dir(checkout)
    _require_clean_project(checkout, "absorb")
    project_id = identity.derive_project_id(checkout)
    slug = identity.slug(project_id)
    sidecar = context.sidecar_dir(slug)
    initializer.require_free_sidecar(sidecar, project_id, slug)
    manifest = initializer.build_manifest(checkout, project_id, slug, shadows, shares)
    adopted = _read_real_shadow_files(checkout, manifest)
    if dry_run:
        return Report(
            (
                f"Would move {checkout}/{STATE_DIRNAME} into "
                f"{render.abbreviate_home(sidecar)} with its history.",
                *_adoption_plan(adopted),
                "Would leave the removal staged for you to commit.",
                DRY_RUN_TRAILER,
            )
        )

    initializer.create_repo(sidecar, manifest, slug)
    manifests.write_manifest(manifests.manifest_path(sidecar / ".git"), manifest)
    _absorb_history(sidecar, checkout, adopted)
    _untrack_state_dir(checkout)
    _free_shadow_slots(checkout, adopted)
    linker.link(checkout, sidecar, initializer.reload_manifest(sidecar), dry_run=False)
    return Report(
        (
            f"Absorbed {STATE_DIRNAME}/ into {render.abbreviate_home(sidecar)} with its history.",
            *_adoption_notice(adopted),
            f"{checkout}/{STATE_DIRNAME} is now a symlink; its removal is staged, not committed.",
            "Review and commit it yourself:  git commit -m 'chore: move Praxion state to a sidecar'",
            "Next: praxion-sidecar doctor",
        )
    )


def _absorb_history(sidecar: Path, checkout: Path, adopted: dict[str, str]) -> None:
    """Graft onto ``main`` rather than the detached HEAD ``create_repo`` leaves.

    The sidecar detaches so the main checkout's mount can claim ``main``; the
    mount does not exist yet here, so re-attaching briefly is safe and is the
    only way the merge -- and the shadow files adopted with it -- land on the
    branch that mount will check out.
    """
    gitp.run_or_raise(sidecar, EnvironmentProblem, "checkout", "-q", "main")
    graft_state_history(
        sidecar, checkout, "HEAD", "chore(state): absorb the project's .ai-state/ with history."
    )
    _adopt_shadow_files(sidecar, adopted)
    gitp.run_or_raise(sidecar, EnvironmentProblem, "checkout", "-q", "--detach")


def _read_real_shadow_files(checkout: Path, manifest: manifests.Manifest) -> dict[str, str]:
    """Every shadowed *file* that is a real file in the checkout right now.

    The mirror image of publish's `_read_shadowed_files`, and the reason absorb
    is publish's inverse rather than a partial one: publish turns each of these
    back into a plain file, so a round trip that only re-shadowed the state
    directory left them behind as real files `link` then refuses to reclaim.
    The state directory is excluded here for the same reason it is there -- it
    moves through the history graft, not by copying bytes.
    """
    contents = {}
    for relpath, entry in manifest.paths.items():
        if not isinstance(entry, manifests.ShadowEntry) or relpath == STATE_DIRNAME:
            continue
        slot = checkout / relpath
        if slot.is_file() and not slot.is_symlink():
            contents[relpath] = slot.read_text(encoding="utf-8")
    return contents


def _adopt_shadow_files(sidecar: Path, adopted: dict[str, str]) -> None:
    """Write the adopted files at the leaves their shadows will point at.

    The leaf comes from `shadow_target()`, not from `relpath`: shadows are
    flattened into the mount root, and re-deriving that here would be a second,
    silently-divergent answer to where a shadow actually points.
    """
    if not adopted:
        return
    leaves = []
    for relpath, text in adopted.items():
        leaf = Path(linker.shadow_target(relpath)).name
        (sidecar / leaf).write_text(text, encoding="utf-8")
        leaves.append(leaf)
    gitp.run_or_raise(sidecar, EnvironmentProblem, "add", "--", *leaves)
    # A file whose bytes already match what `init` seeded stages nothing, and
    # git refuses an empty commit -- so the adoption is simply already done.
    if gitp.succeeds(sidecar, "diff", "--cached", "--quiet"):
        return
    gitp.run_or_raise(
        sidecar,
        EnvironmentProblem,
        *gitp.identity_args(sidecar),
        "commit",
        "-q",
        "-m",
        "chore(state): absorb the project's local shadow files.",
    )


def _free_shadow_slots(checkout: Path, adopted: dict[str, str]) -> None:
    """Empty each adopted slot so `link` sees the ``Absent`` it creates from.

    Tracked files have their removal *staged and not committed*, exactly as
    `_untrack_state_dir` does for the state directory: absorb never commits to
    the project repository, and the operator records the whole move at once.
    """
    for relpath in adopted:
        if gitp.succeeds(checkout, "ls-files", "--error-unmatch", "--", relpath):
            gitp.run_or_raise(checkout, EnvironmentProblem, "rm", "-q", "--cached", "--", relpath)
        (checkout / relpath).unlink()


def _adoption_plan(adopted: dict[str, str]) -> tuple[str, ...]:
    if not adopted:
        return ()
    return (f"Would move {', '.join(sorted(adopted))} into the sidecar and shadow them.",)


def _adoption_notice(adopted: dict[str, str]) -> tuple[str, ...]:
    if not adopted:
        return ()
    return (f"Moved {', '.join(sorted(adopted))} into the sidecar; each is now a symlink.",)


def _untrack_state_dir(checkout: Path) -> None:
    """Stage the removal, delete the directory -- and commit nothing (D1)."""
    gitp.run_or_raise(checkout, EnvironmentProblem, "rm", "-r", "-q", "--cached", STATE_DIRNAME)
    shutil.rmtree(checkout / STATE_DIRNAME)


def _require_tracked_state_dir(checkout: Path) -> None:
    slot = checkout / STATE_DIRNAME
    if not slot.is_dir() or slot.is_symlink():
        raise refusal(
            f"Refusing to absorb: {STATE_DIRNAME}/ is not a real directory in this repo.",
            "absorb moves committed project state out; there is nothing here to move.",
            "To start a sidecar from scratch instead:  praxion-sidecar init",
        )
    tracked = gitp.succeeds(checkout, "cat-file", "-e", f"HEAD:{STATE_DIRNAME}")
    if not tracked:
        raise refusal(
            f"Refusing to absorb: {STATE_DIRNAME}/ is not committed in this repo.",
            "absorb preserves history, and untracked scratch state has none to preserve.",
            f"Commit it first, or:  rm -rf {STATE_DIRNAME} && praxion-sidecar init",
        )


# --- remote -----------------------------------------------------------------


def remote(
    context: Context,
    sidecar: Path,
    manifest: manifests.Manifest,
    *,
    url: str | None,
    push: str,
    clear: bool,
    allow_foreign_host: bool,
) -> Report:
    """Show, set or clear the sidecar's remote. Never pushes anything."""
    if clear:
        return _clear_remote(sidecar, manifest)
    if url is None:
        return _show_remote(manifest)
    return _set_remote(context, sidecar, manifest, url, push, allow_foreign_host)


def _show_remote(manifest: manifests.Manifest) -> Report:
    if manifest.remote is None:
        return Report(
            (
                "No remote configured. Push policy: never.",
                "Set one with:  praxion-sidecar remote git@github.com:acme/<project>-praxion.git",
            )
        )
    return Report((f"Remote: {manifest.remote.url}. Push policy: {manifest.remote.push.value}.",))


def _set_remote(
    context: Context,
    sidecar: Path,
    manifest: manifests.Manifest,
    url: str,
    push: str,
    allow_foreign_host: bool,
) -> Report:
    project_host = inputs._host_of(inputs.observed_origin(context.checkout))  # noqa: SLF001
    remote_host = inputs._host_of(url)  # noqa: SLF001
    foreign = project_host is not None and remote_host != project_host
    if foreign and not allow_foreign_host:
        raise refusal(
            f"Refusing to set the sidecar remote: host {remote_host} does not match "
            f"the project origin's host {project_host}.",
            "Project intelligence would leave the boundary the code lives in — "
            "on a work machine that is a data-boundary breach.",
            "If both hosts are inside your organisation, re-run with:  --allow-foreign-host",
        )

    _write_git_remote(sidecar, url)
    policy = manifests.PushPolicy(push)
    updated = dataclasses.replace(
        manifest,
        remote=manifests.RemoteConfig(url=url, push=policy, foreign_host_ack=foreign),
    )
    manifests.write_manifest(manifests.manifest_path(sidecar / ".git"), updated)
    return Report(
        (f"Remote set: {url} ({_host_note(remote_host, foreign)}). Push policy: {policy.value}.",)
    )


def _host_note(remote_host: str | None, foreign: bool) -> str:
    if foreign:
        return f"host {remote_host} is foreign to the project origin, acknowledged"
    return f"host {remote_host} matches the project origin"


def _clear_remote(sidecar: Path, manifest: manifests.Manifest) -> Report:
    # A sidecar with no `origin` is already in the requested state, so git's
    # refusal to remove one is success here, not an error to surface.
    gitp.succeeds(sidecar, "remote", "remove", "origin")
    updated = dataclasses.replace(manifest, remote=None)
    manifests.write_manifest(manifests.manifest_path(sidecar / ".git"), updated)
    return Report(("Remote cleared. Push policy: never.",))


def _write_git_remote(sidecar: Path, url: str) -> None:
    """Set `origin`, whether or not one is already configured."""
    if gitp.succeeds(sidecar, "remote", "get-url", "origin"):
        gitp.run_or_raise(sidecar, EnvironmentProblem, "remote", "set-url", "origin", url)
        return
    gitp.run_or_raise(sidecar, EnvironmentProblem, "remote", "add", "origin", url)


# --- shared preconditions ---------------------------------------------------


def _require_clean_project(checkout: Path, verb: str) -> None:
    """R6 -- the import merge would otherwise mix the operator's work in."""
    status = gitp.porcelain_status(checkout)
    if status is not None and not status.strip():
        return
    raise refusal(
        f"Refusing to {verb}: the project working tree has uncommitted changes.",
        "The state move rewrites the index and would mix your work into it.",
        *_clean_project_fixes(verb, status),
    )


def _clean_project_fixes(verb: str, status: str | None) -> tuple[str, ...]:
    """Name the *specific* blocker when it is one Praxion itself just staged.

    Right after `absorb`, `.ai-state/`'s removal is staged and deliberately
    uncommitted (D1: absorb never commits to the project repo). Telling that
    operator to `git stash` is advice that would stash Praxion's own half-done
    move; what they actually need to hear is the sentence absorb already
    printed.
    """
    if status and _has_staged_state_change(status):
        return (
            f"{STATE_DIRNAME}/ has staged, uncommitted changes — this is the state move "
            "itself, waiting to be recorded.",
            "Commit the adoption first:  git commit -m 'chore: move Praxion state to a sidecar'",
        )
    return (f"Commit or stash, then re-run:  git stash && praxion-sidecar {verb}",)


def _has_staged_state_change(status: str) -> bool:
    """Whether `status --porcelain` shows an index-side change under the state dir.

    Porcelain v1: two status columns, then a space, then the path; column 0 is
    the index. `?` there is untracked, ` ` is unstaged-only -- neither is a
    staged change.
    """
    for line in status.splitlines():
        if len(line) < 4 or line[0] in " ?":
            continue
        path = line[3:].split(" -> ")[-1].strip('"')
        if path == STATE_DIRNAME or path.startswith(f"{STATE_DIRNAME}/"):
            return True
    return False


def _exclude_path(checkout: Path) -> Path:
    # The one `info/exclude` every worktree of this project honours; the same
    # derivation `link` writes through.
    return linker._project_common_git_dir(checkout) / "info" / "exclude"  # noqa: SLF001
