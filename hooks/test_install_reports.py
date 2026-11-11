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
import os
import sys

import pytest
from test_auto_complete_install import (
    _cached_version,
    _fake_home_module,
    _no_ambient_plugin_root,
    _render_module_reachable_by_the_hook_subprocess,
    _seed_template,
    claude_md_symlink,
    fake_home,
    marker_path,
    plugin_cache_dir,
    plugin_root,
    rules_sentinel,
    update,
)

_NOTICE = "python3 at /p falls short."
_COMPLETED = "[Praxion] Auto-install complete."
_FINISH_BY_HAND = "run /praxion-complete-install to complete it."


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


def _message_and_error(capsys) -> tuple[list[str], str]:
    """The lines of the one `systemMessage` on standard output, and standard error."""
    captured = capsys.readouterr()
    return json.loads(captured.out)["systemMessage"].splitlines(), captured.err


@pytest.fixture
def first_install(monkeypatch, fake_home):
    """The hook module over a home with no surfaces and no marker, asking nothing."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
    module = _fake_home_module(monkeypatch, fake_home)
    monkeypatch.setattr(module, "interpreter_notice", lambda: None)
    return module


class TestFirstInstallReports:
    def test_a_completed_first_install_reaches_the_message_and_not_standard_error(
        self, capsys, first_install, plugin_root
    ):
        _seed_template(plugin_root)

        first_install.main()

        assert _message_and_error(capsys) == ([_COMPLETED], "")

    def test_a_failed_first_install_reaches_the_message_and_not_standard_error(
        self, capsys, first_install
    ):
        first_install.main()  # no template is seeded: the render fails

        assert _message_and_error(capsys) == (
            [f"[Praxion] Auto-install could not finish (FileNotFoundError); {_FINISH_BY_HAND}"],
            "",
        )


@pytest.fixture
def update_run(monkeypatch, fake_home, plugin_cache_dir, marker_path):
    """The hook module over a home whose marker is older than the cache, asking nothing."""
    marker_path.write_text("")
    os.utime(marker_path, (1_000_000, 1_000_000))
    os.utime(plugin_cache_dir, (2_000_000, 2_000_000))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
    return _fake_home_module(monkeypatch, fake_home)


class TestUpdateReports:
    def test_a_failed_refresh_after_a_floor_notice_gives_two_lines_notice_first(
        self, monkeypatch, capsys, update_run
    ):
        monkeypatch.setattr(update_run, "interpreter_notice", lambda: _NOTICE)

        def fails(_home, _root) -> None:
            raise PermissionError("/home/someone/private-value")

        monkeypatch.setattr(update, "_UPDATE_STEPS", (fails,))

        update_run.main()

        assert _message_and_error(capsys) == (
            [
                f"[Praxion] {_NOTICE}",
                f"[Praxion] Update refresh could not finish (PermissionError); {_FINISH_BY_HAND}",
            ],
            "",
        )

    def test_the_completion_line_of_a_dangling_link_set_up_again_is_gathered(
        self, monkeypatch, capsys, update_run, fake_home, plugin_root
    ):
        monkeypatch.setattr(update_run, "interpreter_notice", lambda: None)
        _seed_template(plugin_root)
        gone = _cached_version(fake_home, "9.9.8") / "claude" / "config" / "CLAUDE.md"
        (fake_home / ".claude" / "CLAUDE.md").symlink_to(gone)

        update_run.main()

        assert _message_and_error(capsys) == ([_COMPLETED], "")
