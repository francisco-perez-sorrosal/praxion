"""`--help` on the skill-crafting scripts documents the options and exits 0.

The skill teaches authors that a bundled script "documents itself through `--help`"; a script that
reads `--help` as a skill path answers with a misleading directory error instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
VALIDATOR = SCRIPTS / "validate.py"
PACKAGER = SCRIPTS / "package_skill.py"
SCAFFOLD = SCRIPTS / "init_skill.py"

# Each script's help names its accepted arguments.
ACCEPTED_ARGUMENTS = [
    pytest.param(VALIDATOR, ["<skill-directory>", "--all"], id="validate"),
    pytest.param(PACKAGER, ["<path/to/skill-folder>", "[output-directory]"], id="package_skill"),
    pytest.param(SCAFFOLD, ["<skill-name>", "--path <output-directory>"], id="init_skill"),
]


def run_script(script: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *argv],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("flag", ["--help", "-h"])
@pytest.mark.parametrize(("script", "accepted"), ACCEPTED_ARGUMENTS)
def test_help_prints_the_accepted_arguments_to_stdout_and_exits_zero(script, accepted, flag):
    result = run_script(script, flag)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith("Usage:")
    for argument in accepted:
        assert argument in result.stdout, f"{argument!r} missing from the help text"


@pytest.mark.parametrize(("script", "accepted"), ACCEPTED_ARGUMENTS)
def test_help_states_that_errors_set_a_non_zero_exit_and_warnings_do_not(script, accepted):
    result = run_script(script, "--help")

    assert "error" in result.stdout.lower()
    assert "non-zero" in result.stdout.lower()


def test_validate_help_says_warnings_leave_the_exit_status_alone():
    result = run_script(VALIDATOR, "--help")

    assert "warning" in result.stdout.lower()


def test_validate_without_arguments_still_prints_usage_to_stderr_and_fails():
    result = run_script(VALIDATOR)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Usage:" in result.stderr


def test_package_skill_without_arguments_still_prints_usage_to_stdout_and_fails():
    result = run_script(PACKAGER)

    assert result.returncode == 1
    assert "Usage:" in result.stdout


def test_a_path_that_is_not_a_directory_is_still_an_error(tmp_path):
    result = run_script(VALIDATOR, str(tmp_path / "absent"))

    assert result.returncode == 1
    assert "is not a directory" in result.stderr
