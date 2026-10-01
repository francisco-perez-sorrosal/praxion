"""The blocks shipped into managed projects stay in sync with their sources.

Prompt and template edits for footprint criteria may touch shipped content; the
existing drift check must still come back clean on the repository.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_CHECK = REPO_ROOT / "scripts" / "sync_canonical_blocks.py"


def test_the_shipped_block_drift_check_exits_clean() -> None:
    proc = subprocess.run(
        [sys.executable, str(SYNC_CHECK), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert proc.returncode == 0, f"shipped blocks drifted:\n{proc.stdout}{proc.stderr}"
