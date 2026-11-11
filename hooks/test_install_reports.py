"""Behavioral tests for how the first-session hook reports to the user.

The hook gathers what it has to say and `main()` writes it as one `systemMessage` object on
standard output, the one channel a SessionStart hook has to the user. The fixtures and helpers
are the hook's own test module's (`test_auto_complete_install`); this module imports them so
every suite lays out one plugin and one HOME the same way.
"""

# ruff: noqa: F401, F811 (a fixture imported by name is found by its parameter name, which redefines it)
from __future__ import annotations

import io
import json
import sys

import pytest
from test_auto_complete_install import (
    _fake_home_module,
    _no_ambient_plugin_root,
    _render_module_reachable_by_the_hook_subprocess,
    claude_md_symlink,
    fake_home,
    marker_path,
    rules_sentinel,
)

_NOTICE = "python3 at /p falls short."


@pytest.fixture
def hook(monkeypatch, fake_home, claude_md_symlink, rules_sentinel):
    """The hook module over a home whose surfaces are installed, fed an empty payload."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    return _fake_home_module(monkeypatch, fake_home)


class TestNothingToReport:
    def test_a_run_with_nothing_to_report_writes_to_neither_stream(self, monkeypatch, capsys, hook):
        monkeypatch.setattr(hook, "interpreter_notice", lambda: None)

        hook.main()

        captured = capsys.readouterr()
        assert (captured.out, captured.err) == ("", "")


class TestOneSystemMessage:
    def test_the_whole_of_standard_output_is_one_object_with_one_field(
        self, monkeypatch, capsys, hook
    ):
        monkeypatch.setattr(hook, "interpreter_notice", lambda: _NOTICE)

        hook.main()

        out = capsys.readouterr().out
        assert out.endswith("\n")
        assert json.loads(out) == {"systemMessage": f"[Praxion] {_NOTICE}"}

    def test_a_notice_gathered_before_an_unexpected_failure_is_still_emitted(
        self, monkeypatch, capsys, hook
    ):
        monkeypatch.setattr(hook, "interpreter_notice", lambda: _NOTICE)

        def explodes(*_args) -> bool:
            raise RuntimeError("catastrophic failure after the notice")

        monkeypatch.setattr(hook, "_is_update_run", explodes)

        hook.main()  # must not raise

        assert json.loads(capsys.readouterr().out) == {"systemMessage": f"[Praxion] {_NOTICE}"}

    def test_a_failing_write_is_absorbed(self, monkeypatch, hook):
        monkeypatch.setattr(hook, "interpreter_notice", lambda: _NOTICE)

        class _ClosedPipe:
            def write(self, _text: str) -> int:
                raise BrokenPipeError

            def flush(self) -> None:
                raise BrokenPipeError

        monkeypatch.setattr(sys, "stdout", _ClosedPipe())

        hook.main()  # must not raise
