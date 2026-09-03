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
from pathlib import Path

import _sidecar_manifest as manifests
import _sidecar_render as render
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


def require_sidecar(context: Context, project_id: str) -> tuple[Path, manifests.Manifest]:
    """The sidecar `project_id` names, and its validated manifest.

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
