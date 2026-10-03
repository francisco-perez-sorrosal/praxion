"""The live evaluation never counts a file the log keeps beside itself as a scenario's change.

After real rotations, every file in the state directory that belongs to the log
(the active log, every archive, anything else kept beside it) appears in a
sandbox as created; the evaluation's file-change check drops all of them and
still sees a real source change made beside them.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.live_eval import lightweight_fix_judgement
from tests.acceptance.drivers.log_segments import (
    files_beside_log,
    listed_archives,
    rotate_times,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session, new_checkout

SESSION_ID = "5e551011-0000-4000-8000-0000000f0001"
REAL_CHANGE = "scripts/paginate.py"


def test_the_live_evaluation_drops_every_file_beside_the_log_and_keeps_a_real_change(
    tmp_path: Path,
) -> None:
    checkout = new_checkout(tmp_path / "sandbox")
    rotate_times(
        Session(HookHarness(tmp_path / "harness"), SESSION_ID, checkout), state_dir_of(checkout), 3
    )
    assert len(listed_archives(state_dir_of(checkout))) >= 2, (
        "three rotations kept fewer than two archives"
    )
    created = {f".ai-state/{p.name}": "" for p in files_beside_log(state_dir_of(checkout))}

    judgement = lightweight_fix_judgement({**created, REAL_CHANGE: "fixed\n"})

    assert (judgement.kind, judgement.value) == ("Captured", [REAL_CHANGE])
