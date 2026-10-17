"""A calibration run over a scripted `claude`: it measures the full arm against itself, and a
later run declares the allowances it gives only when the two runs measured the same thing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import tests.test_adherence_cli as cli_tests
from praxion_evals.adherence import cli, results
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.model import allowance_key
from tests.test_adherence_cli import REPO_ROOT, ROLE, SMALL_RUN, Script

# The fixtures that stand a scripted `claude` in for the paid sessions and keep the live checkout's
# role unswitched, shared with the paid-loop tests of the command line.
paid = cli_tests.paid
unswitched_checkout = cli_tests.unswitched_checkout
COMMIT = "f" * 40


def test_a_calibration_run_records_the_full_arm_twice_and_declares_the_allowances_it_gives(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    code, calibration = cli_tests._run(tmp_path, "--calibration", name="calibration.json")

    assert code == 0
    assert calibration.run.extra["calibration"] is True
    assert cli_tests._sessions(calibration) == [("full", "Measured"), ("lean", "Measured")]
    assert {"lean" in s.plugin_dir.name for s in script.specs} == {False}
    source, allowances = cli.calibrated_allowances(
        tmp_path / "calibration.json", _config(), cli.plan_tasks(_config()), _commit(calibration)
    )
    mechanical = {
        allowance_key(c.name, ROLE) for c in check_catalog(ROLE) if c.kind == "mechanical"
    }
    assert source == calibration.run.id
    assert set(allowances) <= mechanical
    declared = cli_tests._run(
        tmp_path,
        "--calibration-run",
        str(tmp_path / "calibration.json"),
        "--max-total-usd",
        "0.5",
        name="declared.json",
    )[1]
    assert declared.settings.allowance_source == calibration.run.id
    assert dict(declared.settings.allowances) == allowances


def test_a_results_file_that_is_not_a_calibration_run_gives_no_allowances(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    cli_tests._run(tmp_path, "--max-total-usd", "0.5", name="ordinary.json")

    with pytest.raises(ValueError, match="not a calibration run"):
        cli.calibrated_allowances(
            tmp_path / "ordinary.json", _config(), cli.plan_tasks(_config()), COMMIT
        )


def _config(*options: str) -> cli.RunConfig:
    return cli.parse_config([str(REPO_ROOT), "--role", ROLE, *SMALL_RUN, *options])


def _commit(loaded: results.RunResults) -> str:
    return loaded.run.extra["checkout"]["commit"]


def test_a_calibration_run_from_another_checkout_is_refused_with_the_reason(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    calibration = cli_tests._run(tmp_path, "--calibration", name="calibration.json")[1]
    elsewhere = "0" * 40

    with pytest.raises(
        ValueError, match=f"measured checkout {_commit(calibration)}, not {elsewhere}"
    ):
        cli.calibrated_allowances(
            tmp_path / "calibration.json", _config(), cli.plan_tasks(_config()), elsewhere
        )


def test_a_calibration_run_that_lacks_a_named_role_is_refused_before_any_launch(
    paid: Callable[[Script], None], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = Script()
    paid(script)
    cli_tests._run(tmp_path, "--calibration", name="calibration.json")
    launched = len(script.specs)
    argv = [
        str(REPO_ROOT),
        "--role",
        ROLE,
        "--role",
        "verifier",
        "--output",
        str(tmp_path / "flip.json"),
        "--calibration-run",
        str(tmp_path / "calibration.json"),
        *SMALL_RUN,
    ]

    assert cli.main(argv) == cli.EXIT_USAGE
    assert "has no pairs of verifier" in capsys.readouterr().err
    assert len(script.specs) == launched
    assert not (tmp_path / "flip.json").exists()


def _flip_argv(tmp_path: Path, *options: str) -> list[str]:
    return [
        str(REPO_ROOT),
        "--role",
        ROLE,
        "--output",
        str(tmp_path / "flip.json"),
        "--calibration-run",
        str(tmp_path / "calibration.json"),
        *SMALL_RUN,
        *options,
    ]


@pytest.mark.parametrize(
    ("calibration_options", "flip_options", "reason"),
    [
        (["--seed", "8"], [], "measured seed 8, not 7"),
        (
            ["--required-pairs", "2"],
            ["--required-pairs", "2", "--max-tasks", "1"],
            f"measured the {ROLE} on 2 tasks, not the 1 planned",
        ),
        (
            ["--required-pairs", "2", "--max-tasks", "1"],
            [],
            "declared a pair target of 2, not 1",
        ),
    ],
    ids=["seed", "task list", "pair target"],
)
def test_a_calibration_run_on_another_seed_task_list_or_pair_target_is_refused_before_any_launch(
    paid: Callable[[Script], None],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    calibration_options: list[str],
    flip_options: list[str],
    reason: str,
) -> None:
    script = Script()
    paid(script)
    cli_tests._run(tmp_path, "--calibration", *calibration_options, name="calibration.json")
    launched = len(script.specs)

    assert cli.main(_flip_argv(tmp_path, *flip_options)) == cli.EXIT_USAGE
    assert reason in capsys.readouterr().err
    assert len(script.specs) == launched
    assert not (tmp_path / "flip.json").exists()
