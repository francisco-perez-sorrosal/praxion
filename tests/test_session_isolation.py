"""A test run never sees the Claude Code session it was started from.

A session exports its own plugin root to every command it runs. For a clone
install that root is this checkout, so a hook test that reaches the
first-install render without isolating itself writes into the checkout's
`claude/config/CLAUDE.md`, which is the operator's live global instructions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INNER_RUN_TIMEOUT_SECONDS = 120  # one test in a fresh interpreter; collection dominates


def test_no_test_sees_the_session_plugin_root() -> None:
    assert "CLAUDE_PLUGIN_ROOT" not in os.environ


def test_a_run_started_inside_a_session_drops_its_plugin_root(tmp_path: Path) -> None:
    inner = f"{Path(__file__).resolve()}::test_no_test_sees_the_session_plugin_root"
    session_env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(tmp_path)}

    result = subprocess.run(
        [sys.executable, "-m", "pytest", inner, "-q", "-n", "0", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        env=session_env,
        capture_output=True,
        text=True,
        timeout=INNER_RUN_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
