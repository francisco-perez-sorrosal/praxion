"""`detect_duplication.py` is an advisory PostToolUse hook: it reports structural
duplication in a written Python or Markdown file as `additionalContext`, stays
silent on a clean file, and never fails the tool call whatever it is handed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parent / "detect_duplication.py"

DUPLICATED_FUNCTIONS = """\
def first(items):
    total = 0
    for item in items:
        total += item.price
        total += item.tax
    return total


def second(items):
    total = 0
    for item in items:
        total += item.price
        total += item.tax
    return total
"""

DISTINCT_FUNCTIONS = """\
def parse(text):
    return text.split(",")


def render(parts):
    joined = "-".join(parts)
    upper = joined.upper()
    padded = upper.ljust(20)
    return padded
"""

REPEATED_SECTIONS = """\
# Title

## Install

Download the archive.
Unpack it somewhere.
Run the installer.
Restart the shell.
Check the version.

## Reinstall

Download the archive.
Unpack it somewhere.
Run the installer.
Restart the shell.
Check the version.
"""

DISTINCT_SECTIONS = """\
# Title

## Install

Download the archive.

## Usage

Run the tool.
"""


def _run(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _written(path: Path) -> subprocess.CompletedProcess[str]:
    return _run(json.dumps({"tool_input": {"file_path": str(path)}}))


def _context(result: subprocess.CompletedProcess[str]) -> str:
    return json.loads(result.stdout)["additionalContext"]


def test_two_near_identical_functions_are_reported_with_their_lines(tmp_path: Path) -> None:
    source = tmp_path / "dup.py"
    source.write_text(DUPLICATED_FUNCTIONS, encoding="utf-8")

    result = _written(source)

    assert result.returncode == 0
    assert "Similar functions: first() at lines 1-6 and second() at lines 9-14" in _context(result)


def test_a_python_file_without_duplication_produces_no_output(tmp_path: Path) -> None:
    source = tmp_path / "clean.py"
    source.write_text(DISTINCT_FUNCTIONS, encoding="utf-8")

    result = _written(source)

    assert (result.returncode, result.stdout) == (0, "")


def test_a_python_file_with_a_syntax_error_produces_no_output(tmp_path: Path) -> None:
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n", encoding="utf-8")

    result = _written(source)

    assert (result.returncode, result.stdout) == (0, "")


def test_the_same_content_under_two_markdown_headings_is_reported(tmp_path: Path) -> None:
    document = tmp_path / "doc.md"
    document.write_text(REPEATED_SECTIONS, encoding="utf-8")

    result = _written(document)

    assert result.returncode == 0
    assert 'Duplicate section content under: "## Install" (line 3), "## Reinstall" (line 11)' in (
        _context(result)
    )


def test_a_markdown_file_without_duplication_produces_no_output(tmp_path: Path) -> None:
    document = tmp_path / "clean.md"
    document.write_text(DISTINCT_SECTIONS, encoding="utf-8")

    result = _written(document)

    assert (result.returncode, result.stdout) == (0, "")


def test_a_file_of_another_kind_is_not_analyzed(tmp_path: Path) -> None:
    other = tmp_path / "dup.txt"
    other.write_text(DUPLICATED_FUNCTIONS, encoding="utf-8")

    result = _written(other)

    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.parametrize(
    "stdin",
    [
        "not json",
        "",
        "[]",
        "{}",
        '{"tool_input": {}}',
        '{"tool_input": {"file_path": "/no/such/file.py"}}',
    ],
)
def test_input_it_cannot_use_exits_zero_in_silence(stdin: str) -> None:
    result = _run(stdin)

    assert (result.returncode, result.stdout) == (0, "")
