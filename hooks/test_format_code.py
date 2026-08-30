"""Characterization tests for the format hook's `.py` behavior.

Pins the hook's observable behavior on `.py` input across the extraction of
`hooks/_lang_tools.py` and the hook rename that produced `format_code.py`. Per
`skills/refactoring/SKILL.md`, this is the safety net for that restructuring --
these assertions held before the rename and hold unchanged after it, which is
the proof that Python formatting did not regress.

Invokes the hook as a real subprocess (matching the PostToolUse Write|Edit
contract: a JSON payload with `tool_input.file_path` on stdin) rather than
importing internals, per `rules/swe/testing-conventions.md § Fixtures Under
Gitignored Paths` -- fixtures are built at runtime under `tmp_path`, never
committed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_PATH = HOOKS_DIR / "format_code.py"

BADLY_FORMATTED_PYTHON = "def   foo( x,y ):\n    return x+y\n"


def _payload_for(file_path: Path) -> dict:
    return {"tool_input": {"file_path": str(file_path)}}


def _run_hook(
    payload: dict, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke the format hook as a subprocess with a JSON payload on stdin."""
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_formats_a_badly_formatted_python_file(tmp_path: Path) -> None:
    """A `.py` file with `ruff` on PATH is rewritten to ruff's formatted form."""
    target = tmp_path / "messy.py"
    target.write_text(BADLY_FORMATTED_PYTHON, encoding="utf-8")

    result = _run_hook(_payload_for(target))

    assert result.returncode == 0
    formatted = target.read_text(encoding="utf-8")
    assert formatted != BADLY_FORMATTED_PYTHON, "ruff format must rewrite the messy file"
    assert formatted == "def foo(x, y):\n    return x + y\n"


def test_reports_changed_line_count_via_additional_context(tmp_path: Path) -> None:
    """A reformatted file reports its changed-line count as `additionalContext` JSON."""
    target = tmp_path / "messy.py"
    target.write_text(BADLY_FORMATTED_PYTHON, encoding="utf-8")

    result = _run_hook(_payload_for(target))

    report = json.loads(result.stdout)
    assert "messy.py" in report["additionalContext"]
    match = re.search(r"\((\d+) lines changed\)", report["additionalContext"])
    assert match is not None, report["additionalContext"]
    assert int(match.group(1)) > 0


def test_silently_exits_when_ruff_is_unresolvable(tmp_path: Path) -> None:
    """No `ruff`/`uv`/`pixi` on PATH: exit 0, no `additionalContext`, file untouched.

    The hook must never block agent execution -- an unresolvable formatter is a
    silent no-op, not an error.
    """
    target = tmp_path / "messy.py"
    target.write_text(BADLY_FORMATTED_PYTHON, encoding="utf-8")
    empty_path_dir = tmp_path / "empty-path"
    empty_path_dir.mkdir()

    result = _run_hook(_payload_for(target), env={"PATH": str(empty_path_dir)})

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert target.read_text(encoding="utf-8") == BADLY_FORMATTED_PYTHON


def test_ignores_a_file_with_an_unhandled_extension(tmp_path: Path) -> None:
    """A `.txt` file is never touched -- the dispatch gate is extension-scoped."""
    target = tmp_path / "notes.txt"
    original = "not   python at all\n"
    target.write_text(original, encoding="utf-8")

    result = _run_hook(_payload_for(target))

    assert result.returncode == 0
    assert result.stdout == ""
    assert target.read_text(encoding="utf-8") == original


def test_ignores_a_python_path_that_does_not_exist(tmp_path: Path) -> None:
    """A `.py` path with no file on disk is a silent no-op, not a crash."""
    missing = tmp_path / "does_not_exist.py"

    result = _run_hook(_payload_for(missing))

    assert result.returncode == 0
    assert result.stdout == ""
