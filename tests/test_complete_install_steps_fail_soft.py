"""The hand path's step sequence survives a failing step before the instructions step.

`complete_install_from_plugin` in `install_claude.sh` runs its steps under `set -e`. Each
scenario runs that function's own text under bash with every step it calls replaced by a stub
that records its name, one stub failing, and asserts the instructions step and the closing
report still run. Nothing here touches a home directory or a plugin.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parent.parent / "install_claude.sh"
_FUNCTION_RE = re.compile(
    r"^complete_install_from_plugin\(\) \{\n.*?^\}\n", re.MULTILINE | re.DOTALL
)
_STEPS = (
    "complete_install_intro",
    "complete_install_rules_step",
    "complete_install_scripts_step",
    "complete_install_instructions_step",
    "complete_install_report",
)


def _run_with_failing(failing: str) -> subprocess.CompletedProcess:
    stubs = "".join(f'{name}() {{ echo "ran {name}"; }}\n' for name in _STEPS)
    stubs += 'legacy_chub_cleanup_claude() { echo "ran legacy"; }\n'
    stubs += 'warn() { echo "warn: $*"; }\n'
    stubs += f'{failing}() {{ echo "ran {failing}"; return 1; }}\n'
    function = _FUNCTION_RE.search(INSTALLER.read_text(encoding="utf-8")).group(0)
    script = "set -euo pipefail\n" + stubs + function + "complete_install_from_plugin\n"
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)


def test_a_failing_leftover_cleanup_still_runs_the_instructions_step_and_the_report() -> None:
    done = _run_with_failing("legacy_chub_cleanup_claude")

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-3:] == [
        "warn: Leftover-state cleanup could not finish; run this command again to retry it",
        "ran complete_install_instructions_step",
        "ran complete_install_report",
    ], done.stdout


@pytest.mark.parametrize("step", ["complete_install_intro"])
def test_a_step_outside_the_fail_soft_set_still_stops_the_command(step: str) -> None:
    done = _run_with_failing(step)

    assert done.returncode != 0, done.stdout
    assert "ran complete_install_instructions_step" not in done.stdout, done.stdout
