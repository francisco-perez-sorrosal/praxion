"""The hand path's scripts step links into `~/.local/bin` without replacing what is not its own.

`link_user_scripts` in `install_claude.sh` runs under bash against a scratch home and a scratch
plugin root: the function's own text, with the shared predicate beside it and `warn` replaced by
a stub that prints. A free name is linked and a link already to the offered script is kept; a
regular file the person owns and a link to anything else stay exactly as they were, each named
in a skip line. Nothing here touches a real home or plugin.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parent.parent / "install_claude.sh"
_OFFERED = "praxion-tool"


def _function(name: str) -> str:
    pattern = rf"^{name}\(\) \{{\n.*?^\}}\n"
    return re.search(
        pattern, INSTALLER.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL
    ).group(0)


@pytest.fixture
def plugin(tmp_path: Path) -> Path:
    scripts = tmp_path / "plugin" / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / _OFFERED
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    return tmp_path / "plugin"


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    path = tmp_path / "home" / ".local" / "bin"
    path.mkdir(parents=True)
    return path


def _link_scripts(tmp_path: Path, plugin: Path) -> subprocess.CompletedProcess:
    script = (
        "set -euo pipefail\n"
        'warn() { echo "warn: $*"; }\n'
        'info() { echo "info: $*"; }\n'
        + _function("script_is_user_facing")
        + _function("link_user_scripts")
        + f'SCRIPT_DIR="{plugin}"\nlink_user_scripts\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path / "home")},
        timeout=30,
    )


def test_a_free_name_is_linked_and_counted(tmp_path: Path, plugin: Path, bin_dir: Path) -> None:
    done = _link_scripts(tmp_path, plugin)

    assert done.returncode == 0, done.stderr
    assert (bin_dir / _OFFERED).readlink() == plugin / "scripts" / _OFFERED
    assert done.stdout.splitlines()[-1] == "1"


def test_a_link_already_to_the_offered_script_is_kept_and_counted(
    tmp_path: Path, plugin: Path, bin_dir: Path
) -> None:
    (bin_dir / _OFFERED).symlink_to(plugin / "scripts" / _OFFERED)
    inode = (bin_dir / _OFFERED).lstat().st_ino

    done = _link_scripts(tmp_path, plugin)

    assert (bin_dir / _OFFERED).lstat().st_ino == inode
    assert done.stdout.splitlines()[-1] == "1"


def test_a_regular_file_the_person_owns_is_left_byte_identical_and_named(
    tmp_path: Path, plugin: Path, bin_dir: Path
) -> None:
    (bin_dir / _OFFERED).write_text("mine\n")

    done = _link_scripts(tmp_path, plugin)

    assert done.returncode == 0, done.stderr
    assert (bin_dir / _OFFERED).read_text() == "mine\n"
    assert not (bin_dir / _OFFERED).is_symlink()
    assert f"warn: {_OFFERED} left alone" in done.stderr
    assert done.stdout.splitlines()[-1] == "0"


def test_a_link_to_a_clone_checkout_is_left_pointing_there_and_named(
    tmp_path: Path, plugin: Path, bin_dir: Path
) -> None:
    clone_script = tmp_path / "clone" / "scripts" / _OFFERED
    clone_script.parent.mkdir(parents=True)
    clone_script.write_text("#!/bin/sh\n")
    (bin_dir / _OFFERED).symlink_to(clone_script)

    done = _link_scripts(tmp_path, plugin)

    assert (bin_dir / _OFFERED).readlink() == clone_script
    assert f"warn: {_OFFERED} left alone" in done.stderr
    assert done.stdout.splitlines()[-1] == "0"
