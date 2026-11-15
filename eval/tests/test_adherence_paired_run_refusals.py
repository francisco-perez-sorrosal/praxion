"""The paired run refuses in its own words, names the option it declines, and a stopped run blocks
only a fresh run of its own axis. The ordinary comparison's command-line refusals keep argparse's
form."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxion_evals.adherence import cli
from praxion_evals.adherence.axis import DEFAULT_AXIS
from praxion_evals.adherence.lineage import SpendRefused, pending_stop
from tests.adherence_run_support import scripted_checkout
from tests.test_adherence_paired_run_lifecycle import (
    PAIRED,
    ROLE,
    TASKS,
    _cli,
    _planted,
    _snapshot,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")

USAGE = "usage: "
AXIS_OPTIONS = ("--role", ROLE, "--axis", PAIRED)


def _refusal(capsys: pytest.CaptureFixture[str], tmp_path: Path, *options: str) -> str:
    output = tmp_path / "out.json"
    with pytest.raises(SystemExit) as stopped:
        cli.parse_config([*options, "--output", str(output)])
    assert stopped.value.code == cli.EXIT_USAGE
    assert not output.exists()
    return capsys.readouterr().err


@pytest.mark.parametrize(
    ("options", "named"),
    [
        (("--calibration",), "--calibration"),
        (("--arm", "full"), "full"),
        (("--arm", "preloaded", "--arm", "lean"), "lean"),
    ],
)
def test_a_refusal_of_the_paired_run_is_one_line_in_the_runs_own_words(
    capsys, tmp_path, options, named
):
    err = _refusal(capsys, tmp_path, *AXIS_OPTIONS, *options)

    assert err.startswith(f"{cli.PROG}: ")
    assert len(err.strip().splitlines()) == 1
    assert named in err
    assert USAGE not in err


def test_an_ordinary_command_line_refusal_still_prints_argparses_usage(capsys, tmp_path):
    err = _refusal(capsys, tmp_path, "--role", ROLE, "--arm", "preloaded")

    assert err.startswith(USAGE)
    assert "--arm preloaded is an arm of the refactoring-delivery axis" in err


def test_a_refusal_unrelated_to_the_axis_still_prints_argparses_usage(capsys, tmp_path):
    err = _refusal(capsys, tmp_path, *AXIS_OPTIONS, "--judge-golden", "--no-judge")

    assert err.startswith(USAGE)


def test_continuing_a_stopped_paired_run_names_the_option_and_says_to_close_and_start_afresh(
    tmp_path, capsys
):
    directory = _planted(tmp_path, "paired-1", PAIRED, SpendRefused(TASKS))
    before = _snapshot(directory)

    code = _cli(directory, "--continue", "paired-1")

    err = capsys.readouterr().err
    assert code == cli.EXIT_USAGE
    assert "--continue" in err
    assert "close it (--close paired-1 --reason TEXT) and start a fresh run" in err
    assert USAGE not in err
    assert _snapshot(directory) == before


STOPPED = f"run stopped-1 of {ROLE} stopped and was neither continued nor closed; "
CLOSE_IT = "close it (--close stopped-1 --reason TEXT)"


@pytest.mark.parametrize(
    ("axis", "refusal"),
    [
        (
            DEFAULT_AXIS,
            f"{STOPPED}continue it (--continue stopped-1) or {CLOSE_IT} before starting a fresh run",
        ),
        (PAIRED, f"{STOPPED}{CLOSE_IT} before starting a fresh run"),
    ],
)
def test_a_stopped_run_blocks_a_fresh_run_of_its_own_axis_in_full_words(tmp_path, axis, refusal):
    directory = _planted(tmp_path, "stopped-1", axis, SpendRefused(TASKS))
    config = cli.parse_config(_fresh(directory, axis))

    with pytest.raises(ValueError, match="stopped and was neither") as raised:
        cli._refuse_beside_stopped_run(config)

    assert str(raised.value) == refusal


@pytest.mark.parametrize(
    ("stopped_axis", "fresh_axis"), [(PAIRED, DEFAULT_AXIS), (DEFAULT_AXIS, PAIRED)]
)
def test_a_stopped_run_does_not_block_a_fresh_run_of_the_other_axis(
    tmp_path, stopped_axis, fresh_axis
):
    directory = _planted(tmp_path, "stopped-1", stopped_axis, SpendRefused(TASKS))
    config = cli.parse_config(_fresh(directory, fresh_axis))

    cli._refuse_beside_stopped_run(config)

    assert pending_stop(directory, ROLE, fresh_axis) is None
    assert pending_stop(directory, ROLE, stopped_axis) is not None


def _fresh(directory: Path, axis: str) -> list[str]:
    return [
        str(scripted_checkout()),
        "--role",
        ROLE,
        "--axis",
        axis,
        "--output",
        str(directory / "new.json"),
    ]
