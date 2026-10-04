"""Driver that onboards a fresh project with the architecture-as-code capability.

Onboarding installs the capability with the diagram-kit installer
(`scripts/install_diagram_kit.py`); the driver runs that installer against the
project, offline, and exposes where the installed model and renders live and the one
documented command that regenerates the renders. A missing installer or a failing run
is an assertion failure carrying what the run printed, so a scenario reports the
missing capability rather than a driver error.

A fresh project here is a git repository with one commit and nothing else.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.acceptance.drivers.architecture_model import REPO_ROOT, offline_env

INSTALLER = REPO_ROOT / "scripts" / "install_diagram_kit.py"
_DIAGRAM_ROOT = Path("docs") / "diagrams" / "architecture"


def onboard_with_aac(project: Path) -> None:
    """Run onboarding's architecture-as-code installation against `project`."""
    assert INSTALLER.is_file(), (
        f"onboarding cannot install the architecture-as-code capability: "
        f"the installer {INSTALLER.relative_to(REPO_ROOT)} does not exist"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(INSTALLER),
            "--project-root",
            str(project),
            "--plugin-root",
            str(REPO_ROOT),
        ],
        cwd=project,
        env=offline_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"the diagram-kit installer failed (exit {result.returncode}):\n"
        f"{result.stdout[-1500:]}{result.stderr[-1500:]}"
    )


def regeneration_command(project: Path) -> str:
    """The one documented shell command that regenerates the project's renders."""
    return "python3 scripts/regenerate_diagrams.py"


def model_workspace(project: Path) -> Path:
    """The directory holding the installed model source (the example view's workspace)."""
    return project / _DIAGRAM_ROOT / "src"


def render_dir(project: Path) -> Path:
    """The directory the regeneration writes the example view's renders to."""
    return project / _DIAGRAM_ROOT / "rendered"
