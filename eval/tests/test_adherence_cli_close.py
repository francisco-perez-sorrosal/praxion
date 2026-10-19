"""A stopped run is continued or closed, never left beside a fresh one: closing records the reason
in the run's own results file, and a fresh run beside a continuable stopped run is refused naming it."""

from __future__ import annotations

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
    ending_of,
)
from tests.adherence_run_support import (
    REASON,
    ROLE,
    SMALL_RUN,
    STOPPED_BOTH_ARMS,
    STOPPED_ONE_ARM,
    Script,
    close_run,
    dry_run,
    ended_as,
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
