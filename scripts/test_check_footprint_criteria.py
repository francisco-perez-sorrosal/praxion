"""Tests for `check_footprint_criteria.py` -- the command shell of the footprint check.

The grammars and the finding table are tested where they live, in
`test__footprint_grammar.py` and `test__markdown_tables.py`. This file gains the
judge, the git edge and the CLI as they land.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_footprint_criteria.py"


def test_script_is_an_executable_python3_command():
    source = SCRIPT.read_text(encoding="utf-8")

    assert source.startswith("#!/usr/bin/env python3\n")
    assert os.access(SCRIPT, os.X_OK), "the script is not executable"


def test_docstring_points_at_the_grammar_it_does_not_restate():
    docstring = ast.get_docstring(ast.parse(SCRIPT.read_text(encoding="utf-8")))

    assert "_footprint_grammar.py" in docstring


def test_interim_main_exits_nonzero_and_names_the_reason():
    """Until the stages exist, running the command must not read as a clean pass."""
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "any-slug"], capture_output=True, text=True, check=False
    )

    assert run.returncode == 2
    assert "stages not implemented" in run.stderr
