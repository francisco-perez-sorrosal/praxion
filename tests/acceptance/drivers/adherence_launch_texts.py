"""Driver for what each session the adherence eval launches receives at its start.

Unbound until its binding step. The binding runs the eval through `adherence_runs` with every
launch answered by `stand_in_claude` and, at each launch before answering, reads what that
session would receive with `session_start_text`: the instruction files of the launch's
configuration directory (`CLAUDE_CONFIG_DIR`, else its HOME's `.claude`) and of its working
directory, plus the `SessionStart` hooks of its `--plugin-dir` copy run in that directory; and
what the role it spawns would receive, by `session_start_text.spawn_start` against the same
plugin copy. Readings are masked to tokens per launch and paired, by arm, task and proof, with
the readings the same run gave at the pipeline base, frozen under
`tests/acceptance/fixtures/project_gating/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError

_UNBOUND = (
    "the reading of what each adherence-eval launch receives at start (its configuration "
    "directory, its working directory and its plugin copy's session-start hooks), paired with "
    "the base's readings of the same launches, is not bound yet"
)


@dataclass(frozen=True)
class LaunchTexts:
    def session_pairs(self, arm: str) -> dict[str, tuple[str, str]]:
        """Launch key -> (today's process text, this run's), for every session of `arm`."""
        raise UnboundDriverError(_UNBOUND)

    def role_pairs(self, arm: str) -> dict[str, tuple[str, str]]:
        """Launch key -> (today's, this run's) process text of the role the session spawned."""
        raise UnboundDriverError(_UNBOUND)

    def graded_checks(self) -> dict[str, list[str]]:
        raise UnboundDriverError(_UNBOUND)

    def todays_graded_checks(self) -> dict[str, list[str]]:
        raise UnboundDriverError(_UNBOUND)


def run_recording_launch_texts(workspace: Path) -> LaunchTexts:
    """The run, once bound; until then every reading of it raises."""
    return LaunchTexts()
