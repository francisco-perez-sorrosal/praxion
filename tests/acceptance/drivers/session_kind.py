"""Driver for sessions of a known kind, and for what the spawn tally leaves out.

A headless session is a Claude Code session started non-interactively (`claude -p`, or an
Agent SDK host); an interactive session is one a person types into. Scenarios plant spawns
from either kind through the observation harness (`observation_harness.Session`), then read
the tally through `spawn_tally`.

How the kinds are shown to the hooks: Claude Code names how it was started in the
`CLAUDE_CODE_ENTRYPOINT` environment variable and the checkout it runs in in
`CLAUDE_PROJECT_DIR`; those two are all the hooks read. A session with no evidence of its
kind sets neither, which is today's harness session, as rows written before sessions
carried their kind.

The tally is `spawn_tally.spawn_count`, run as a command with `--json`; the agents it leaves
out of every slug are the `left_out` list of that report.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.observation_harness import HookHarness, Session

ENTRYPOINT_VARIABLE = "CLAUDE_CODE_ENTRYPOINT"
PROJECT_DIR_VARIABLE = "CLAUDE_PROJECT_DIR"
HEADLESS_ENTRYPOINT = "sdk-cli"
INTERACTIVE_ENTRYPOINT = "cli"
LEFT_OUT_KEY = "left_out"


def unknown_kind_session(scratch: Path, session_id: str, cwd: Path) -> Session:
    """A session whose kind nothing shows: today's harness session."""
    return Session(HookHarness(scratch), session_id, cwd)


def headless_session(scratch: Path, session_id: str, cwd: Path) -> Session:
    """A session started non-interactively, as Claude Code shows that to the hooks."""
    return _session_started_as(HEADLESS_ENTRYPOINT, scratch, session_id, cwd)


def interactive_session(scratch: Path, session_id: str, cwd: Path) -> Session:
    """A session a person types into, as Claude Code shows that to the hooks."""
    return _session_started_as(INTERACTIVE_ENTRYPOINT, scratch, session_id, cwd)


def left_out(report: dict) -> dict[str, str]:
    """Each agent the tally left out of every slug, mapped to the reason it gives."""
    assert LEFT_OUT_KEY in report, (
        f"the tally's report lists no `{LEFT_OUT_KEY}` key for the agents it left out of "
        f"every slug; its keys are {sorted(report)}"
    )
    return {entry["agent_id"]: entry["reason"] for entry in report[LEFT_OUT_KEY]}


def _session_started_as(entrypoint: str, scratch: Path, session_id: str, cwd: Path) -> Session:
    environment = {ENTRYPOINT_VARIABLE: entrypoint, PROJECT_DIR_VARIABLE: str(cwd)}
    return Session(HookHarness(scratch, extra_env=environment), session_id, cwd)
