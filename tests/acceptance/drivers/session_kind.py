"""Driver for sessions of a known kind, and for what the spawn tally leaves out.

A headless session is a Claude Code session started non-interactively (`claude -p`, or an
Agent SDK host); an interactive session is one a person types into. Scenarios plant spawns
from either kind through the observation harness (`observation_harness.Session`), then read
the tally through `spawn_tally`.

Bound here, because the specification or the base commit fixes them:

- a session with no evidence of its kind is today's harness session, unchanged: its rows
  carry nothing about how the session was started, as rows written before this change;
- the tally is `spawn_tally.spawn_count`, run as a command with `--json`.

Not yet bound (each raises until a binding step binds it to the designed interface):

- how a session shows the hooks that it was started non-interactively, or that a person
  types into it;
- where the tally's report lists the agents it left out of every slug, with the reason
  each was left out.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.observation_harness import HookHarness, Session


class UnboundDriverError(NotImplementedError):
    """A boundary assumption no binding step has bound to the designed interface yet."""


def unknown_kind_session(scratch: Path, session_id: str, cwd: Path) -> Session:
    """A session whose kind nothing shows: today's harness session."""
    return Session(HookHarness(scratch), session_id, cwd)


def headless_session(scratch: Path, session_id: str, cwd: Path) -> Session:
    """A session started non-interactively, as Claude Code shows that to the hooks."""
    raise UnboundDriverError(
        "a session started non-interactively (claude -p, or an Agent SDK host) shows the "
        "hooks that it is headless, so the spawns it makes carry that evidence"
    )


def interactive_session(scratch: Path, session_id: str, cwd: Path) -> Session:
    """A session a person types into, as Claude Code shows that to the hooks."""
    raise UnboundDriverError(
        "a session a person types into is recorded the way an interactive session is, "
        "whatever evidence of its kind the hooks see"
    )


def left_out(report: dict) -> dict[str, str]:
    """Each agent the tally left out of every slug, mapped to the reason it gives."""
    raise UnboundDriverError(
        "the tally's report lists, apart from the charged and unattributed agents, each "
        f"agent it left out of every slug with the reason it was left out: {sorted(report)}"
    )
