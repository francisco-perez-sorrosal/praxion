"""A calibration run over a scripted `claude`: it measures the full arm against itself and reports
the net discordance of each check as a slot-order check; a later run takes no allowance from it."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import tests.test_adherence_cli as cli_tests
from praxion_evals.adherence import cli, report
from praxion_evals.adherence.model import OWN_DISCORDANCE_EXACT
from tests.test_adherence_cli import Script

# The fixtures that stand a scripted `claude` in for the paid sessions and keep the live checkout's
# role unswitched, shared with the paid-loop tests of the command line.
paid = cli_tests.paid
unswitched_checkout = cli_tests.unswitched_checkout


def test_a_calibration_run_records_the_full_arm_twice_and_reports_no_allowance(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    code, calibration = cli_tests._run(tmp_path, "--calibration", name="calibration.json")

    assert code == 0
    assert calibration.run.extra["calibration"] is True
    assert cli_tests._sessions(calibration) == [("full", "Measured"), ("lean", "Measured")]
    assert {"lean" in s.plugin_dir.name for s in script.specs} == {False}
    text = report.render(calibration)
    assert "slot-order check: b - c = " in text
    assert not any(line.strip().startswith("allowance:") for line in text.splitlines())
    assert "; noise allowance" not in text
    assert "mechanical noise allowances: none declared" in text


def test_a_run_given_a_calibration_file_takes_no_allowance_from_it_and_says_so(
    paid: Callable[[Script], None], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paid(Script())
    cli_tests._run(tmp_path, "--calibration", name="calibration.json")
    capsys.readouterr()

    declared = cli_tests._run(
        tmp_path,
        "--calibration-run",
        str(tmp_path / "calibration.json"),
        "--max-total-usd",
        "0.5",
        name="declared.json",
    )[1]

    assert declared.settings.allowance_method == OWN_DISCORDANCE_EXACT
    assert declared.settings.allowance_source is None
    assert dict(declared.settings.allowances) == {}
    assert cli.CALIBRATION_RUN_NOTE in capsys.readouterr().err


def test_a_calibration_file_is_never_read(paid: Callable[[Script], None], tmp_path: Path) -> None:
    script = Script()
    paid(script)
    unreadable = tmp_path / "not-a-results-file.json"
    unreadable.write_text("{")

    code, declared = cli_tests._run(tmp_path, "--calibration-run", str(unreadable), name="d.json")

    assert code == 0
    assert declared.settings.allowance_method == OWN_DISCORDANCE_EXACT
