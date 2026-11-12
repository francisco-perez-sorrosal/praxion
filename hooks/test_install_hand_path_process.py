"""The hand path's instructions entry run as its own process, the way the installer runs it.

These tests start the entry with `python3`, so the mutation sensor, which runs the unit
tests from a copied tree, is given the unit modules only; the step's Check runs these too.
The child's home and git config are scratch ones holding a made-up identity.
"""

# ruff: noqa: F811 (a fixture's parameter name redefines the name it is imported under)
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Fixtures are found by the name they are imported under, so each is imported though no code names it.
from test_auto_complete_install import (  # noqa: F401
    _NEW_TEMPLATE,
    HOOKS_DIR,
    _fill,
    _link_instructions,
    _no_ambient_plugin_root,
    _render_module_reachable_by_the_hook_subprocess,
    fake_home,
    plugin_cache_dir,
    plugin_root,
)
from test_install_hand_path import (  # noqa: F401
    _TYPED,
    INSTRUCTIONS,
    _link,
    _ruin,
    installed,
    previous,
)

# -- The command, as a process --------------------------------------------------------------------


_GIT_EMAIL = "isolated.person@example.invalid"
_GIT_USERNAME = "@isolated-person"


def _process(home: Path, root: Path, answers: str) -> subprocess.CompletedProcess:
    """Run the entry as the hook's own process: its git config is `home`'s, holding a made-up identity."""
    scratch_git_config = home / ".gitconfig"
    scratch_git_config.write_text(f"[user]\n\temail = {_GIT_EMAIL}\n", encoding="utf-8")
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "GIT_"))}
    environ.update(
        HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(scratch_git_config)
    )
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "_install_hand_path.py"), "--root", str(root)],
        input=answers,
        capture_output=True,
        text=True,
        env=environ,
        cwd=home,  # a repository's own config would otherwise be read
        timeout=60,
    )


def test_run_as_a_script_it_converses_on_standard_error_and_prints_one_line(
    fake_home, previous, installed
):
    _ruin(previous)
    _link_instructions(fake_home, previous)

    done = _process(
        fake_home, installed, "1\n" + "".join(f"{v}\n" for v in _TYPED.values()) + "y\n"
    )

    assert (done.returncode, done.stdout) == (
        0,
        f"{INSTRUCTIONS} set up (with the values given)\n",
    )
    assert "Choice [1]: " in done.stderr
    assert _link(fake_home).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TYPED)


def test_run_as_a_script_the_default_offered_comes_from_the_scratch_git_config_alone(
    fake_home, previous, installed
):
    _ruin(previous)
    _link_instructions(fake_home, previous)

    done = _process(fake_home, installed, "1\n\n")

    assert f"Username [{_GIT_USERNAME}]: " in done.stderr
    assert f"Email [{_GIT_EMAIL}]: " in done.stderr


def test_run_as_a_script_the_input_ending_exits_with_the_left_behind_status(
    fake_home, previous, installed
):
    _ruin(previous)
    _link_instructions(fake_home, previous)

    done = _process(fake_home, installed, "")

    assert done.returncode == 3
    assert done.stdout.count("\n") == 1
    assert "not set up: no answer" in done.stdout
