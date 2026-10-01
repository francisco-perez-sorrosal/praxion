"""The footprint check, run as a PATH-installed copy runs it: through a symlink in another directory.

`install_claude.sh` links the executable into `~/.local/bin`, so the script's own location is
not where its private siblings (`_footprint_grammar.py`, `_markdown_tables.py`) sit; the
interpreter must resolve the link to find them, and the repository root must come from git.
This runs a subprocess, so it stays out of the mutation sensor's test set, whose sandbox copy
of the module is not runnable on its own.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_footprint_criteria.py"
PLAN = "# Plan\n\n## Acceptance Criteria\n\n- [ ] The change behaves\n"


def test_a_path_installed_symlink_resolves_the_private_siblings(tmp_path):
    project = tmp_path / "project"
    (project / ".ai-work" / "demo").mkdir(parents=True)
    (project / ".ai-work" / "demo" / "SYSTEMS_PLAN.md").write_text(PLAN, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    link = bin_dir / "check_footprint_criteria.py"
    link.symlink_to(SCRIPT)

    done = subprocess.run(
        [sys.executable, str(link), "demo", "--stage", "spec", "--json"],
        cwd=project,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["active"] is False
