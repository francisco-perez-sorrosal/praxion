"""The installer and the first-session hook offer the same scripts to the PATH.

`install_claude.sh`'s `script_is_user_facing` decides what a clone install and the
installer's hand path link into `~/.local/bin`; the hook's `offered_scripts` decides
what a marketplace install's first session links and what its update refresh keeps.
When the two disagree, one path links a script the other removes on its next run, so
they are held equal here over the repository's own `scripts/`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from test_auto_complete_install import update

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "install_claude.sh"
_PREDICATE = re.compile(r"^script_is_user_facing\(\) \{\n.*?^\}\n", re.MULTILINE | re.DOTALL)


def _installer_offers(scripts_dir: Path) -> list[str]:
    """The names the installer's own predicate passes, run by bash over `scripts_dir`."""
    function = _PREDICATE.search(INSTALLER.read_text(encoding="utf-8"))
    assert function, "script_is_user_facing() not found in install_claude.sh"
    loop = 'for f in "$1"/*; do script_is_user_facing "$f" && basename "$f"; done; true'
    result = subprocess.run(
        ["bash", "-c", function.group() + loop, "predicate", str(scripts_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(result.stdout.split())


def test_the_installer_and_the_hook_offer_the_same_scripts():
    hook = sorted(script.name for script in update.offered_scripts(REPO_ROOT))

    assert _installer_offers(REPO_ROOT / "scripts") == hook


def test_no_hook_script_is_offered_by_either_path():
    offered = set(_installer_offers(REPO_ROOT / "scripts")) | {
        script.name for script in update.offered_scripts(REPO_ROOT)
    }

    assert not {name for name in offered if name.endswith("-hook.sh")}, offered
