"""Behavioral tests for hooks/_interpreter_floor.py and the first-session notice.

The floor is what every Praxion hook needs from the `python3` it runs under.
The module is judged by that interpreter, however old, so it is also held to
syntax Python 3.7 parses.
"""

# ruff: noqa: F401, F811 (a fixture imported by name is found by its parameter name, which redefines it)
from __future__ import annotations

import ast
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))
import _interpreter_floor as floor  # noqa: E402 (after sys.path injection)
from test_auto_complete_install import (  # noqa: E402 (after sys.path injection)
    _fake_home_module,
    _no_ambient_plugin_root,
    claude_md_symlink,
    fake_home,
    marker_path,
    rules_sentinel,
)

_MODULE_PATH = HOOKS_DIR / "_interpreter_floor.py"
_STOCK_MACOS = (3, 9, 6, "final", 0)


def _importable(*modules: str):
    return lambda module: module in modules


class TestShortfalls:
    def test_an_interpreter_below_the_floor_is_named_with_its_version(self):
        found = floor.shortfalls(_STOCK_MACOS, _importable("yaml"))

        assert found == ("Python 3.9.6, needs 3.11 or newer",)

    def test_a_missing_pyyaml_is_named_by_the_distribution_to_install(self):
        found = floor.shortfalls((3, 11, 0, "final", 0), _importable())

        assert found == ("PyYAML is not importable",)

    def test_both_shortfalls_are_named_together(self):
        found = floor.shortfalls(_STOCK_MACOS, _importable())

        assert found == ("Python 3.9.6, needs 3.11 or newer", "PyYAML is not importable")

    def test_an_interpreter_at_the_floor_with_pyyaml_falls_short_of_nothing(self):
        assert floor.shortfalls((3, 11, 0, "final", 0), _importable("yaml")) == ()

    def test_a_newer_interpreter_meets_the_floor(self):
        assert floor.shortfalls((3, 13, 1, "final", 0), _importable("yaml")) == ()


class TestDescribe:
    def test_names_the_interpreter_what_it_lacks_and_the_way_out(self):
        line = floor.describe("/usr/bin/python3", ("Python 3.9.6, needs 3.11 or newer",))

        assert line == (
            "python3 at /usr/bin/python3 falls short of what Praxion's hooks need: "
            "Python 3.9.6, needs 3.11 or newer. "
            "Put a Python 3.11 or newer with PyYAML first on PATH."
        )

    def test_the_notice_is_none_when_nothing_falls_short(self):
        assert floor.notice((3, 12, 0, "final", 0), _importable("yaml"), "/x/python3") is None

    def test_the_notice_describes_every_shortfall(self):
        line = floor.notice(_STOCK_MACOS, _importable(), "/usr/bin/python3")

        assert line is not None
        assert "Python 3.9.6, needs 3.11 or newer; PyYAML is not importable." in line


class TestCommandLine:
    def test_exits_one_and_prints_the_line_below_the_floor(self, capsys):
        status = floor.main(version=_STOCK_MACOS, importable=_importable(), executable="/p")

        assert status == 1
        assert capsys.readouterr().out == floor.notice(_STOCK_MACOS, _importable(), "/p") + "\n"

    def test_exits_zero_silently_at_the_floor(self, capsys):
        status = floor.main(version=(3, 11, 2, "final", 0), importable=_importable("yaml"))

        assert status == 0
        assert capsys.readouterr().out == ""

    def test_runs_as_a_script_under_the_suite_interpreter(self):
        result = subprocess.run(
            [sys.executable, str(_MODULE_PATH)], capture_output=True, text=True, check=False
        )

        assert (result.returncode, result.stdout) == (0, "")


def test_the_module_parses_as_python_3_7():
    """The interpreter being judged parses this file first, so it must read it."""
    ast.parse(_MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 7))


class TestFirstSessionNotice:
    """The hook tells the user once per version, on the run that writes the marker."""

    @staticmethod
    def _run(module, monkeypatch, line: str | None) -> None:
        monkeypatch.setattr(module, "interpreter_notice", lambda: line)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        module._run()

    def test_a_shortfall_reaches_the_user_as_a_system_message(
        self, monkeypatch, capsys, fake_home, claude_md_symlink, rules_sentinel, marker_path
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        self._run(module, monkeypatch, "python3 at /p falls short.")

        assert json.loads(capsys.readouterr().out) == {
            "systemMessage": "[Praxion] python3 at /p falls short."
        }
        assert marker_path.exists()

    def test_an_interpreter_that_meets_the_floor_prints_nothing(
        self, monkeypatch, capsys, fake_home, claude_md_symlink, rules_sentinel
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        self._run(module, monkeypatch, None)

        assert capsys.readouterr().out == ""

    def test_a_session_after_the_marker_is_not_told_again(
        self, monkeypatch, capsys, fake_home, claude_md_symlink, rules_sentinel
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        self._run(module, monkeypatch, None)

        self._run(module, monkeypatch, "python3 at /p falls short.")

        assert capsys.readouterr().out == ""
