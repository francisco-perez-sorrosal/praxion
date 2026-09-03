"""Bringing a sidecar into existence -- everything `init` does before `link`.

Four steps, in this order and no other (`ARCH_WT_RULING.md` sec. 5): refuse a
slug that already belongs to someone else, build the DS-2 manifest from the
defaults plus the operator's placement flags, create and seed the repository,
then re-read the manifest through its own smart constructor.

The last step is not ceremony. `init` constructs a `Manifest` in memory, and
`write_manifest` does not validate -- so writing and then loading is what puts
the DS-2 factory (illegal shadow paths, `kind` cross-checks, exclude
disjointness) between a fresh manifest and the reconciler that acts on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import _sidecar_git as gitp
import _sidecar_identity as identity
import _sidecar_link as linker
import _sidecar_manifest as manifests
import _sidecar_mount as mounts
import _sidecar_render as render
import _state_repo
from _git_runner import git_output
from _sidecar_cli import EnvironmentProblem, UsageError, refusal

# DS-2's default placement set, in the order `status` and the manifest render
# them. `CLAUDE.md` sits second because its intent is a three-state decision
# made from repo state (DS-8), not a default -- see `_claude_md_entry`.
DEFAULT_SHADOWS = (".ai-state", "CLAUDE.local.md", ".claude/settings.local.json")
DEFAULT_SHARES = ("docs/architecture.md",)
DEFAULT_EXCLUDES = (".ai-work/", ".claude/worktrees/", "tmp/")
DIR_SHADOW_PATHS = frozenset({".ai-state", "architecture/", "fitness/"})
CLAUDE_MD = "CLAUDE.md"

# What a freshly seeded shadow file holds, keyed by the sidecar-side leaf name
# -- which is what `shadow_target()` actually links to, not the project relpath.
SEED_CONTENT = {
    "CLAUDE.md": "<!-- Praxion writes its CLAUDE.md blocks here. -->\n",
    "CLAUDE.local.md": "<!-- Praxion writes its CLAUDE.md blocks here. -->\n",
    "settings.local.json": "{}\n",
}

PATH_COLUMN = 30

# The sidecar's own semantic merge routing, byte-identical to what onboarding
# Phase 3 writes into a project. It has to live in the *sidecar* too: under the
# state mount, `.ai-state/` is the sidecar's tracked tree, so a `merge-back`
# between two mounts merges `observations.jsonl` inside the sidecar repository
# -- and without this routing git would reconcile an append-only event log with
# its default line-based 3-way strategy and corrupt it on the first concurrent
# session.
GITATTRIBUTES_HEADER = (
    "# Praxion semantic merge drivers — see rules/swe/agent-intermediate-documents.md"
)
OBSERVATIONS_ATTRIBUTE = ".ai-state/observations.jsonl merge=observations-jsonl"
OBSERVATIONS_DRIVER_KEY = "merge.observations-jsonl.driver"
MERGE_DRIVER_SCRIPT = "merge_driver_observations.py"


def require_free_sidecar(sidecar: Path, project_id: identity.ProjectId, slug: str) -> None:
    """R7 -- refuse a slug that already names some *other* project's sidecar.

    The collision is real (two repositories can normalise to one slug, and
    `--id` invites the operator to pick one deliberately), and reclaiming a
    sidecar in place would silently re-key another project's whole history.
    """
    if not sidecar.exists():
        return
    recorded = _recorded_origin(manifests.manifest_path(sidecar / ".git"))
    if recorded is not None and _same_origin(recorded, identity.recorded_origin(project_id)):
        raise refusal(
            f"Refusing to init: {render.abbreviate_home(sidecar)} is already initialised "
            "for this project.",
            "init creates a sidecar; re-running it would rewrite an existing history.",
            "Reconcile this checkout against it instead:  praxion-sidecar link",
        )
    owner = recorded if recorded is not None else "another project"
    raise refusal(
        f"Refusing to init: {render.abbreviate_home(sidecar)} already belongs to {owner}.",
        "The project-id derivation collided (both repos normalise to the same slug).",
        f"Pick an explicit id:  praxion-sidecar init --id {slug}-2",
    )


def _recorded_origin(manifest_path: Path) -> str | None:
    """The `project.origin` an existing manifest records, or None when unreadable."""
    if not manifest_path.is_file():
        return None
    try:
        return manifests.load_manifest(manifest_path).project.origin or "a remote-less project"
    except manifests.ManifestError:
        return None


def _same_origin(recorded: str, ours: str | None) -> bool:
    if ours is None:
        return False
    return _state_repo.normalize_origin(recorded) == _state_repo.normalize_origin(ours)


def build_manifest(
    checkout: Path,
    project_id: identity.ProjectId,
    slug: str,
    shadow_overrides: Sequence[str],
    share_overrides: Sequence[str],
) -> manifests.Manifest:
    """The DS-2 manifest for a fresh sidecar: defaults, then the operator's flags."""
    validate_placement_flags(shadow_overrides, share_overrides, checkout=checkout)
    paths: dict[str, manifests.PathEntry] = {}
    for relpath in DEFAULT_SHADOWS[:1]:
        paths[relpath] = manifests.ShadowEntry(kind=_shadow_kind(relpath))
    paths[CLAUDE_MD] = _claude_md_entry(checkout)
    for relpath in DEFAULT_SHADOWS[1:]:
        paths[relpath] = manifests.ShadowEntry(kind=_shadow_kind(relpath))
    for relpath in DEFAULT_SHARES:
        paths[relpath] = manifests.ShareEntry()
    for relpath in share_overrides:
        paths[relpath] = manifests.ShareEntry()
    for relpath in shadow_overrides:
        paths[relpath] = manifests.ShadowEntry(kind=_shadow_kind(relpath))

    return manifests.Manifest(
        schema=1,
        project=manifests.ProjectIdentity(
            origin=identity.recorded_origin(project_id),
            id=slug,
            roots=[identity.main_worktree_root(checkout)],
        ),
        paths=paths,
        excludes=list(DEFAULT_EXCLUDES),
        autocommit=manifests.Autocommit.ON_FINALIZE_AND_STOP,
        remote=None,
    )


def validate_placement_flags(
    shadows: Sequence[str], shares: Sequence[str], *, checkout: Path | None = None
) -> None:
    """D8 -- an allowlist, not arbitrary paths, with `.claude` taught explicitly.

    `.claude` is checked before the allowlist so a plausible mistake gets its
    real reason (Claude Code refuses to create a worktree when `.claude/` is a
    symlink) rather than the generic "not on the list".

    `checkout`, when given, also enforces the tracked-path refusal -- last,
    so a misspelled or never-shadowable path still gets its own message. The
    boundary is here rather than in `link` because `link` acts only on
    `Absent` slots, so a tracked file would be silently skipped after the
    manifest had already recorded an intent the disk contradicts.
    """
    for relpath in shadows:
        if relpath.rstrip("/") in manifests.NEVER_SHADOW:
            raise refusal(
                "Refusing to shadow .claude/: Claude Code refuses to create a worktree "
                "when .claude/ is a symlink.",
                "Shadowing it would break every pipeline worktree on this project.",
                "Shadow the file instead:  --shadow .claude/settings.local.json",
            )
    for flag, values in (("--shadow", shadows), ("--share", shares)):
        for relpath in values:
            if relpath not in manifests.SHADOWABLE_PATHS:
                allowed = "\n".join(f"  {entry}" for entry in sorted(manifests.SHADOWABLE_PATHS))
                raise UsageError(
                    f"Usage error: {flag} {relpath} is not a shadowable path.\n{allowed}\n"
                    "Run 'praxion-sidecar --help' for the placement options."
                )
    both = sorted(set(shadows) & set(shares))
    if both:
        raise UsageError(
            f"Usage error: {', '.join(both)} was passed to both --shadow and --share.\n"
            "Each path has exactly one intent. Pass it to one flag only."
        )
    if checkout is not None:
        _refuse_tracked_shadows(checkout, shadows)


def _refuse_tracked_shadows(checkout: Path, shadows: Sequence[str]) -> None:
    """Shadowing a **tracked** path is a team-visible removal -- refuse it.

    `git ls-files -- <path>` rather than `--error-unmatch`: the latter reports
    a tracked *directory* as unmatched, and the allowlist admits directory
    slots. A non-empty listing is the tracked answer for both shapes.
    """
    for relpath in shadows:
        if not git_output(checkout, "ls-files", "--", relpath):
            continue
        raise refusal(
            f"{relpath} is tracked in this repository; sidecar placement cannot "
            "hide a tracked file.",
            "Removing it from the project would be a deletion every teammate sees, "
            "which init will not make on your behalf.",
            f"Keep it shared, or remove it from the repository first "
            f"(git rm --cached {relpath}, commit), then praxion-sidecar link.",
        )


def _claude_md_entry(checkout: Path) -> manifests.PathEntry:
    """DS-8: a tracked `CLAUDE.md` is the team's file and is never touched."""
    if git_output(checkout, "ls-files", "--", CLAUDE_MD):
        return manifests.UntouchedEntry(reason=manifests.UntouchedReason.PREEXISTING_TEAM_FILE)
    return manifests.ShadowEntry(kind=manifests.ShadowKind.FILE)


def _shadow_kind(relpath: str) -> manifests.ShadowKind:
    if relpath in DIR_SHADOW_PATHS:
        return manifests.ShadowKind.DIR
    return manifests.ShadowKind.FILE


def sections(
    sidecar: Path, manifest: manifests.Manifest, plan: linker.LinkResult
) -> list[tuple[str, list[str]]]:
    """`init`'s five `[n/N]` sections (INTERFACE_DESIGN.md sec. 3.3).

    Section 3 is titled *Seed* rather than the mockup's *Move*: R1 refuses an
    `init` whose `.ai-state/` is a real directory, so at `init` there is never
    anything to move -- `absorb` owns the move path.
    """
    shadows = _by_intent(manifest, manifests.ShadowEntry)
    shares = _by_intent(manifest, manifests.ShareEntry)
    untouched = _by_intent(manifest, manifests.UntouchedEntry)
    seeded = [f"{relpath:<{PATH_COLUMN}} created in the sidecar" for relpath in shadows]
    seeded += [f"{relpath:<{PATH_COLUMN}} shared (stays in the project repo)" for relpath in shares]
    seeded += [
        f"{relpath:<{PATH_COLUMN}} untouched (pre-existing team file)" for relpath in untouched
    ]
    excludes = linker.exclude_lines(manifest)
    return [
        (
            "Sidecar repository",
            [f"create {render.abbreviate_home(sidecar)} (git init, branch main)"],
        ),
        (
            "Manifest",
            [
                f"write praxion-sidecar.yaml — {len(shadows)} shadowed, "
                f"{len(shares)} shared, {len(untouched)} untouched"
            ],
        ),
        ("Seed state in the sidecar", seeded),
        (
            "Project exclusions",
            [f"{'.git/info/exclude':<{PATH_COLUMN}} +{len(excludes)} Praxion entries"],
        ),
        ("Link into this checkout", [f"{relpath} -> sidecar" for relpath in plan.linked] or ["—"]),
    ]


def _by_intent(manifest: manifests.Manifest, variant: type) -> list[str]:
    return [relpath for relpath, entry in manifest.paths.items() if isinstance(entry, variant)]


def merge_driver_command() -> str:
    """The `%O %A %B` invocation git runs for `observations-jsonl`.

    The driver's path is resolved from **this file's own location**, which is
    the live install path for both shapes Praxion runs in: a plugin checkout
    (`.../praxion/<version>/scripts/`) and a self-hosted repository. `resolve()`
    follows the installer's symlinks, so a `~/.claude/scripts/` entry point
    still records the real plugin path -- the same live-path property
    onboarding Phase 3 gets from its pre-flight `${PLUGIN_INSTALL_PATH}`, and
    the reason a version upgrade re-registers rather than skips.
    """
    driver = Path(__file__).resolve().parent / MERGE_DRIVER_SCRIPT
    return f"python3 {driver} %O %A %B"


def ensure_merge_drivers(sidecar: Path) -> bool:
    """Route `.ai-state/observations.jsonl` through the semantic merge driver.

    Called from two places on purpose: `create_repo` (so the very first commit
    carries `.gitattributes`, and every mount materialises it) and `link` (so a
    re-cloned or hand-repaired sidecar, or one pinned to a previous plugin
    version, is reconciled -- `link` is the sole reconciler, D2).

    The registration is repo-local, in the sidecar's `.git/config`: correct,
    because the path is machine-specific and the sidecar never leaves this
    machine. Unlike Phase 3 there is no "refuse to overwrite a foreign driver"
    check -- the sidecar is a repository Praxion created for itself, so a
    differing value is a stale Praxion pin, not a user's own choice.
    """
    changed = _ensure_gitattributes(sidecar)
    command = merge_driver_command()
    if git_output(sidecar, "config", "--get", OBSERVATIONS_DRIVER_KEY) != command:
        gitp.run_or_raise(sidecar, EnvironmentProblem, "config", OBSERVATIONS_DRIVER_KEY, command)
        changed = True
    return changed


def _ensure_gitattributes(sidecar: Path) -> bool:
    """Append the routing line unless the exact line is already present."""
    path = sidecar / ".gitattributes"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if OBSERVATIONS_ATTRIBUTE in existing.splitlines():
        return False
    prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
    path.write_text(f"{prefix}{GITATTRIBUTES_HEADER}\n{OBSERVATIONS_ATTRIBUTE}\n", encoding="utf-8")
    return True


def create_repo(sidecar: Path, manifest: manifests.Manifest, slug: str) -> None:
    """`git init` the sidecar, route its merge drivers, seed it, commit, detach.

    The merge routing lands *before* the first commit so `.gitattributes` is
    tracked from the sidecar's first revision -- a mount created later
    materialises it automatically, which is what makes `merge-back` safe.

    Detaching is what frees `main` for the project's main checkout to claim as
    a mount (`ARCH_WT_RULING.md` sec. 5): git refuses to check a branch out in
    two worktrees at once, and that refusal is the invariant, not a rule this
    code has to remember.
    """
    sidecar.mkdir(parents=True, exist_ok=True)
    gitp.run_or_raise(sidecar, EnvironmentProblem, "init", "-q", "-b", "main")
    ensure_merge_drivers(sidecar)
    _seed_shadow_targets(sidecar, manifest)
    gitp.run_or_raise(sidecar, EnvironmentProblem, "add", "-A")
    gitp.run_or_raise(
        sidecar,
        EnvironmentProblem,
        *gitp.identity_args(sidecar),
        "commit",
        "-q",
        "-m",
        f"chore(sidecar): initialise {slug}",
    )
    gitp.run_or_raise(sidecar, EnvironmentProblem, "checkout", "--detach", "-q")


def _seed_shadow_targets(sidecar: Path, manifest: manifests.Manifest) -> None:
    """Materialise, in the sidecar, whatever each shadow symlink will point at.

    The leaf comes from `shadow_target()` rather than from `relpath`: shadows
    are flattened into the mount root (`.claude/settings.local.json` links to
    `../.praxion/settings.local.json`), and re-deriving that here would be a
    second, silently-divergent answer to where a shadow actually points.
    """
    for relpath, entry in manifest.paths.items():
        if not isinstance(entry, manifests.ShadowEntry):
            continue
        leaf = Path(linker.shadow_target(relpath)).name
        target = sidecar / leaf
        if entry.kind is manifests.ShadowKind.DIR:
            if leaf == mounts.STATE_DIRNAME:
                mounts.seed_skeleton(sidecar)
                continue
            target.mkdir(parents=True, exist_ok=True)
            (target / ".gitkeep").touch()
        elif not target.exists():
            target.write_text(SEED_CONTENT.get(leaf, ""), encoding="utf-8")


def reload_manifest(sidecar: Path) -> manifests.Manifest:
    """Re-read the manifest just written, so the smart constructor validates it."""
    try:
        return manifests.load_manifest(manifests.manifest_path(sidecar / ".git"))
    except manifests.ManifestError as error:
        raise refusal(
            f"Refusing to link: the manifest just written is invalid ({error.reason}).",
            str(error),
            "Adjust the placement flags and re-run:  praxion-sidecar init",
        ) from error
