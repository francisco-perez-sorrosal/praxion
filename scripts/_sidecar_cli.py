"""`praxion-sidecar`'s shared spine: the exit-code contract, and the checkout.

The exit-code contract (D1) is **one mapping, expressed as three exception
types**, so that every refusal in the CLI reaches the same `except` clause and
no verb can invent its own code. They live here rather than in the entry point
because `_sidecar_init` and `_sidecar_inputs` raise them too, and a contract
one caller can bypass is not a contract.

`Context` is the second shared thing: which checkout a verb runs in, and where
sidecars live on this machine. Both `require_*` gates below refuse with a
three-part message rather than returning a sentinel, so a verb body never
holds an unresolved checkout or an unvalidated manifest.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import _sidecar_manifest as manifests
import _sidecar_render as render
import _state_repo
from _git_runner import run_git

EXIT_OK = 0
EXIT_ACTIONABLE = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3
EXIT_ENVIRONMENT = 4

DEFAULT_SIDECAR_ROOT = Path("~/.praxion/sidecars")
SIDECAR_ROOT_ENV = "PRAXION_SIDECAR_ROOT"


class UsageError(Exception):
    """Wrong arguments, wrong usage -- exit 2."""


class Refused(Exception):  # noqa: N818 - a refusal to act, not a failure mid-operation
    """Understood and deliberately declined on safety grounds -- exit 3.

    Constructed only through `refusal()`, so every message is three-part
    (what / why / how) and ends with a command the operator can run.
    """


class EnvironmentProblem(Exception):  # noqa: N818 - see Refused
    """Praxion is not set up here, or the environment is broken -- exit 4."""


def refusal(what: str, why: str, *fixes: str) -> Refused:
    """Assemble the three-part refusal the error contract (sec. 4) mandates."""
    return Refused("\n".join([what, why, *fixes]))


def require_confirmation(verb: str, *, yes: bool, prompt: str) -> None:
    """Gate a destructive verb on an explicit yes (R12).

    Lives beside the exit contract because the *refusal* is the contract: a
    prompt nobody can answer is a usage error, never a wait. Every automated
    caller -- a hook, CI, a subprocess with no terminal -- therefore fails
    immediately and legibly instead of hanging on a read that will never return.
    """
    if yes:
        return
    if not sys.stdin.isatty():
        raise UsageError(
            f"Usage error: {verb} needs confirmation and stdin is not a terminal.\n"
            "In non-interactive mode, pass --yes to confirm."
        )
    print(prompt)
    if input(f"Type 'yes' to {verb}: ").strip().lower() != "yes":
        raise refusal(
            f"Refusing to {verb}: not confirmed.",
            "Nothing was modified.",
            f"Re-run when you are ready:  praxion-sidecar {verb} --yes",
        )


@dataclasses.dataclass(frozen=True)
class Context:
    """The checkout a verb runs in, plus where sidecars live on this machine."""

    checkout: Path
    sidecar_root: Path

    def sidecar_dir(self, project_id: str) -> Path:
        return self.sidecar_root / project_id


def sidecar_root() -> Path:
    configured = os.environ.get(SIDECAR_ROOT_ENV)
    root = Path(configured) if configured else DEFAULT_SIDECAR_ROOT
    return root.expanduser()


def require_context(cwd: Path) -> Context:
    """Resolve the checkout, or refuse with R8. Every verb starts here."""
    result = run_git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode != 0 or not result.stdout.strip():
        raise EnvironmentProblem(
            "\n".join(
                [
                    f"Cannot run here: {cwd} is not a git repository.",
                    "praxion-sidecar operates on a checkout; it derives the project "
                    "identity from the git origin.",
                    "Run it from inside your project, or:  git init",
                ]
            )
        )
    return Context(checkout=Path(result.stdout.strip()).resolve(), sidecar_root=sidecar_root())


def require_sidecar(
    context: Context, project_id: str, *, verb: str = "run"
) -> tuple[Path, manifests.Manifest]:
    """The sidecar this checkout belongs to, and its validated manifest.

    **Discovered, not derived** (DS-3). The mount in `<checkout>/.praxion` is
    a worktree of exactly one repository, and its git common dir names that
    repository unambiguously -- so a mounted checkout knows where its sidecar
    is regardless of what `PRAXION_SIDECAR_ROOT` says today. Deriving
    `<root>/<identity>` instead makes every read verb fail the moment the
    environment variable points somewhere else, on a project whose state is
    mounted, healthy and one `readlink` away.

    `<root>/<identity>` remains the answer for the one question discovery
    cannot answer: where a sidecar that does not exist yet should go. That is
    `init`'s and `absorb`'s question, and the fallback below serves the
    not-yet-mounted checkout (a fresh clone) that is about to ask it.

    `verb` only shapes the foreign-mount refusal, which names the command the
    operator actually ran.
    """
    common_dir = _discover_sidecar(context.checkout, verb=verb)
    if common_dir is not None:
        return _load_sidecar(common_dir.parent, manifests.manifest_path(common_dir))
    return _derived_sidecar(context, project_id)


def require_sidecar_repo(context: Context, project_id: str, *, verb: str = "run") -> Path:
    """The sidecar repository alone -- for verbs that read no manifest.

    `merge-back` merges and deletes *branches*: a git-level operation on the
    repository the mount already identifies. The manifest describes which
    paths are shadowed and when to autocommit, and none of that changes which
    branch merges into which. Demanding a valid manifest anyway would let a
    typo in an unrelated field stop convergence on every automatic channel --
    and, because a hook reads exit `4` as "not set up here, skip silently", it
    would stop it *quietly*. Identity is still enforced: a discovered sidecar
    got there by matching the manifest's origin/roots in the placement
    resolver.
    """
    common_dir = _discover_sidecar(context.checkout, verb=verb)
    if common_dir is not None:
        return common_dir.parent
    return _derived_sidecar_root(context, project_id)


def _discover_sidecar(checkout: Path, *, verb: str) -> Path | None:
    """The sidecar common dir this checkout's state mount belongs to, or `None`.

    Two placements answer: `SidecarOwned` (this checkout's own mount) and
    `NotYetLinked` (a worktree created a moment ago -- no mount of its own,
    creating it is what `link` is about to do, but the project's main checkout
    is mounted and every worktree of one project shares one sidecar). The
    resolver owns that second answer, so the first `link` in a new worktree is
    not forced through the environment variable.

    `None` means "this checkout has no mount to ask and no sibling that does"
    -- `InRepo` and `Dangling`, both of which the derived fallback handles. A
    `Foreign` mount is neither: it resolves into *some* sidecar that is not
    this project's, and silently reaching past it to the derived location
    would link a checkout to a sidecar its own `.ai-state` contradicts.
    """
    placement = _state_repo.resolve_placement(checkout)
    if isinstance(placement, (_state_repo.SidecarOwned, _state_repo.NotYetLinked)):
        return placement.sidecar_common_dir
    if isinstance(placement, _state_repo.Foreign):
        raise refusal(
            f"Refusing to {verb}: .ai-state points at a different sidecar.",
            f"found:    {placement.link_path}\nreason:   {placement.reason.value}",
            "Remove it and re-link:  rm .ai-state && praxion-sidecar link",
        )
    return None


def _derived_sidecar(context: Context, project_id: str) -> tuple[Path, manifests.Manifest]:
    """The derived sidecar and its manifest, for a checkout with no mount."""
    sidecar = _derived_sidecar_root(context, project_id)
    return _load_sidecar(sidecar, manifests.manifest_path(sidecar / ".git"))


def _derived_sidecar_root(context: Context, project_id: str) -> Path:
    """`<PRAXION_SIDECAR_ROOT>/<identity>` -- where a sidecar goes when there is
    no mount to discover one from.

    R9 (no sidecar) and R10 (a sidecar that is not a git repository) are the
    two shapes an operator actually hits, and they need different reactions --
    R9 means "this project uses in-repo placement, skip"; R10 means "the
    sidecar is broken, repair it" -- so they carry distinct messages under one
    exit code.
    """
    sidecar = context.sidecar_dir(project_id)
    path = manifests.manifest_path(sidecar / ".git")
    if not sidecar.is_dir():
        raise EnvironmentProblem(no_sidecar_message(path))
    if not (sidecar / ".git").exists():
        raise EnvironmentProblem(
            "\n".join(
                [
                    f"Sidecar at {render.abbreviate_home(sidecar)} is not a git repository.",
                    "Its .git/ was removed or the directory was created by hand — "
                    "autocommit and history are unavailable.",
                    "Re-initialise it (state files are preserved):  "
                    f"git -C {render.abbreviate_home(sidecar)} init",
                ]
            )
        )
    if not path.is_file():
        raise EnvironmentProblem(no_sidecar_message(path))
    return sidecar


def _load_sidecar(sidecar: Path, path: Path) -> tuple[Path, manifests.Manifest]:
    try:
        return sidecar, manifests.load_manifest(path)
    except manifests.ManifestError as error:
        raise EnvironmentProblem(
            "\n".join(
                [
                    f"The sidecar manifest at {render.abbreviate_home(path)} "
                    f"is unusable ({error.reason}).",
                    str(error),
                    "Repair the manifest, then:  praxion-sidecar doctor",
                ]
            )
        ) from error


def no_sidecar_message(manifest_path: Path) -> str:
    """R9 -- the message a hook reads as "not set up here, skip silently"."""
    return "\n".join(
        [
            "No sidecar for this project.",
            f"{render.abbreviate_home(manifest_path)} does not exist — "
            "this project uses in-repo placement.",
            "To move its state out:  praxion-sidecar absorb",
        ]
    )
