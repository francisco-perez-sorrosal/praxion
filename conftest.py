"""Session isolation shared by every root test tree (tests, scripts, hooks, skills).

A Claude Code session exports its own plugin root to every command it runs, and
for a clone install that root is this checkout. A test that reaches the hook's
first-install render without isolating itself then writes the default identity
into `claude/config/CLAUDE.md`, which is the operator's live global
instructions. CI never sets the variable, so dropping it makes every local run
see what CI sees. A test that needs a plugin root sets its own.
"""

from __future__ import annotations

import os

AMBIENT_SESSION_VARIABLES = ("CLAUDE_PLUGIN_ROOT",)


def pytest_configure() -> None:
    """Drop the session's variables before collection, in the controller and in
    every xdist worker, so test subprocesses inherit the clean environment too."""
    for name in AMBIENT_SESSION_VARIABLES:
        os.environ.pop(name, None)
