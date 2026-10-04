"""Driver that onboards a fresh project with the architecture-as-code capability.

Unbound until a binding step: onboarding's architecture-as-code phase is carried
out by an agent following the onboarding procedure, so which installer the
scenarios call, where the installed model and renders live, and which single
documented command regenerates the renders are design decisions. A binding step
wires these four functions to the designed installation; every scenario that
uses them stays red until then.

A fresh project here is a git repository with one commit and nothing else.
"""

from __future__ import annotations

from pathlib import Path

_UNBOUND = (
    "Unbound driver: onboarding with the architecture-as-code capability does not yet "
    "install, by a step a test can run, a category vocabulary, an example view and "
    "one documented command that regenerates the project's renders locally."
)


def onboard_with_aac(project: Path) -> None:
    """Run onboarding's architecture-as-code installation against `project`."""
    raise NotImplementedError(_UNBOUND)


def regeneration_command(project: Path) -> str:
    """The one documented shell command that regenerates the project's renders."""
    raise NotImplementedError(_UNBOUND)


def model_workspace(project: Path) -> Path:
    """The directory holding the installed model source (the example view's workspace)."""
    raise NotImplementedError(_UNBOUND)


def render_dir(project: Path) -> Path:
    """The directory the regeneration writes the example view's renders to."""
    raise NotImplementedError(_UNBOUND)
