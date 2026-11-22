"""A stopped run is continued or closed, never left beside a fresh one: closing records the reason
in the run's own results file, and a fresh run beside a continuable stopped run is refused naming it."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import (
    cli,
    results,
)
from praxion_evals.adherence.lineage import (
    Closed,
    Finished,
    SpendRefused,
    ending_of,
)
from praxion_evals.adherence.session_loop import OUTPUT_DIR
from tests.adherence_run_support import (
    PAIRED,
    PAIRED_ROLE,
    REASON,
    ROLE,
    SMALL_RUN,
    STOPPED_BOTH_ARMS,
    STOPPED_ONE_ARM,
    TASKS,
    Script,
    close_run,
    dry_run,
    ended_as,
    planted,
    scripted_checkout,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")


# ---------------------------------------------------------------------------
# A stopped run is continued or closed, never left beside a fresh one
# ---------------------------------------------------------------------------


def _fresh_run(tmp_path: Path) -> int:
    output = tmp_path / "fresh.json"
    return cli.main([str(scripted_checkout()), "--role", ROLE, "--output", str(output), *SMALL_RUN])


@pytest.mark.usefixtures("full_first")
def test_a_stopped_run_is_closed_with_a_reason_written_into_its_own_results_file(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)

    code = close_run(tmp_path, stopped.run.id, "--reason", REASON)

    ending = ending_of(results.load(tmp_path / "stopped.json"))
    assert code == 0
    assert isinstance(ending, Closed)
    assert (ending.reason, ending.stopped) == (REASON, STOPPED_BOTH_ARMS)
    assert ending.interim, "the closed run carries the per-check result it had reached"


@pytest.mark.parametrize("argv", [["--close", "20261020T000000Z-0badf1"], ["--reason", REASON]])
def test_a_close_and_its_reason_go_together(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.parse_config([*argv, "--role", ROLE])

    assert raised.value.code == 2


@pytest.mark.usefixtures("full_first")
def test_a_blank_reason_closes_nothing(paid: Callable[[Script], None], tmp_path: Path) -> None:
    paid(Script())
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)

    code = close_run(tmp_path, stopped.run.id, "--reason", "  ")

    assert code == 2
    assert ending_of(results.load(tmp_path / "stopped.json")) == STOPPED_BOTH_ARMS


@pytest.mark.usefixtures("full_first")
def test_a_run_that_did_not_stop_is_not_closed(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    finished = ended_as(tmp_path, Finished())

    code = close_run(tmp_path, finished.run.id, "--reason", REASON)

    assert code == 2
    assert ending_of(results.load(tmp_path / "stopped.json")) == Finished()


@pytest.mark.usefixtures("full_first")
def test_a_fresh_run_beside_a_continuable_stopped_run_is_refused_naming_it(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = Script()
    paid(script)
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)
    launched = len(script.specs)
    capsys.readouterr()

    code = _fresh_run(tmp_path)

    assert code == 2
    assert stopped.run.id in capsys.readouterr().err
    assert len(script.specs) == launched
    assert not (tmp_path / "fresh.json").exists()


@pytest.mark.usefixtures("full_first")
def test_a_fresh_run_starts_once_the_stopped_run_was_closed(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)
    close_run(tmp_path, stopped.run.id, "--reason", REASON)

    code = _fresh_run(tmp_path)

    assert code == 0
    assert (tmp_path / "fresh.json").exists()


@pytest.mark.usefixtures("full_first")
def test_a_stop_confined_to_one_arm_does_not_block_a_fresh_run(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    ended_as(tmp_path, STOPPED_ONE_ARM)

    code = _fresh_run(tmp_path)

    assert code == 0


@pytest.mark.usefixtures("full_first")
def test_a_dry_run_beside_a_stopped_run_is_not_refused(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    paid(Script())
    ended_as(tmp_path, STOPPED_BOTH_ARMS)
    capsys.readouterr()

    lines = dry_run(capsys, tmp_path, "--role", ROLE)

    assert lines, "the dry run still plans its sessions"


@pytest.mark.usefixtures("full_first")
def test_a_closed_run_is_listed_by_the_next_run_as_a_not_clear_interim_draw(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    stopped = ended_as(tmp_path, STOPPED_BOTH_ARMS)
    close_run(tmp_path, stopped.run.id, "--reason", REASON)

    _fresh_run(tmp_path)

    listed = results.earlier_listed(results.load(tmp_path / "fresh.json").run, ROLE)
    assert listed is not None
    assert listed.draws == (results.Draw((stopped.run.id,), "not clear", interim=True),)


# ---------------------------------------------------------------------------
# A stopped paired run is closed from its own directory, without --axis or --output
# ---------------------------------------------------------------------------


def paired_run_held(repository: Path, run_id: str) -> Path:
    """The paired results directory of ``repository``, holding one stopped run of that axis."""
    directory = repository / OUTPUT_DIR / PAIRED
    directory.mkdir(parents=True)
    planted_in = planted(repository / "scratch", run_id, PAIRED, SpendRefused(TASKS))
    shutil.move(planted_in / f"{run_id}.json", directory / f"{run_id}.json")
    return directory


def test_a_stopped_paired_run_is_closed_without_naming_its_axis(repository: Path) -> None:
    directory = paired_run_held(repository, "paired-1")

    code = cli.main([str(scripted_checkout()), "--close", "paired-1", "--reason", REASON])

    closed = ending_of(results.load(directory / "paired-1.json"))
    assert code == 0
    assert isinstance(closed, Closed)
    assert closed.reason == REASON
    assert "paired-1" in (directory / results.RUN_INDEX_NAME).read_text()


def test_a_stopped_paired_run_still_blocks_a_fresh_paired_run_until_it_is_closed(
    repository: Path,
) -> None:
    paired_run_held(repository, "paired-1")
    fresh = ["--role", PAIRED_ROLE, "--axis", PAIRED]

    config = cli.parse_config([str(scripted_checkout()), *fresh])
    with pytest.raises(ValueError, match="paired-1 of implementer stopped and was neither"):
        cli._refuse_beside_stopped_run(config)
    cli.main([str(scripted_checkout()), "--close", "paired-1", "--reason", REASON])

    cli._refuse_beside_stopped_run(config)  # no longer refuses: the run is closed
