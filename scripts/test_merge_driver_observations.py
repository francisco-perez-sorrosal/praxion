"""Tests for merge_driver_observations.py's graceful-degradation contract.

Run: ``python3 scripts/test_merge_driver_observations.py`` or ``pytest``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import merge_driver_observations as mdo  # noqa: E402


def test_main_exits_cleanly_when_ours_path_absent(tmp_path, capsys):
    """git never invokes this driver on the raw WAL once it leaves tracking
    (merge drivers apply only to tracked, conflicted paths). Still, a caller
    pointing it at a fresh-clone-shaped absent path must fail loud-but-clean
    -- exit 1 with a message on stderr, never a traceback."""
    ours = tmp_path / "observations.jsonl"  # never created
    theirs = tmp_path / "observations.jsonl.theirs"
    theirs.write_text("", encoding="utf-8")
    ancestor = tmp_path / "observations.jsonl.base"
    ancestor.write_text("", encoding="utf-8")

    # main() reads argv directly, the way git invokes a merge driver.
    original_argv = sys.argv
    try:
        sys.argv = [
            "merge_driver_observations.py",
            str(ancestor),
            str(ours),
            str(theirs),
        ]
        exit_code = mdo.main()
    finally:
        sys.argv = original_argv

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Cannot read input files" in err


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
