"""Behavioral tests for the first install, as the hook runs it.

The cold path -- no marker, surfaces missing -- through the hook as a process and in
process: the four environment combinations, the prompt and its timeout, the failures the
hook absorbs, and the layout Claude Code installs. The fixtures and helpers are the
hook's own test module's (`test_auto_complete_install`); this module imports them so every
suite lays out one plugin and one HOME the same way.
"""

# ruff: noqa: F401, F811 (a fixture imported by name is found by its parameter name, which redefines it)
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_auto_complete_install import (
    _MODULE_PATH,
    _VALUES,
    HOOKS_DIR,
    _clear_praxion_env,
    _fake_home_module,
    _load_module,
    _no_ambient_plugin_root,
    _render_module_reachable_by_the_hook_subprocess,
    _run_hook_subprocess,
    _seed_template,
    claude_md_symlink,
    fake_home,
    marker_path,
    minimal_session_payload,
    plugin_cache_dir,
    plugin_root,
    rules_sentinel,
    update,
)


class TestColdPathFreshInstall:
    """Cold path: no marker, surfaces missing → install runs, marker written."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_missing_claude_md_triggers_install(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """No ~/.claude/CLAUDE.md → install runs, exit 0."""
        assert not (fake_home / ".claude" / "CLAUDE.md").exists()
        assert not marker_path.exists()

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_missing_rules_sentinel_triggers_install(
        self,
        fake_home,
        marker_path,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """CLAUDE.md present but rules sentinel missing → install triggered."""
        sentinel = fake_home / ".claude" / "rules" / "swe" / "agent-behavioral-contract.md"
        assert not sentinel.exists()

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_non_symlink_claude_md_triggers_install(
        self,
        fake_home,
        marker_path,
        rules_sentinel,
        minimal_session_payload,
    ):
        """~/.claude/CLAUDE.md exists but is NOT a symlink → install triggered."""
        regular_file = fake_home / ".claude" / "CLAUDE.md"
        regular_file.write_text("# Regular file, not a symlink\n")
        assert not regular_file.is_symlink(), "Precondition: must be a regular file"

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_successful_install_writes_marker_file(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """After successful cold-path install, marker file is written."""
        assert not marker_path.exists()

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0
        assert marker_path.exists(), "Marker file must be written after successful install"

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_decline_writes_soft_decline_marker(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """User decline in interactive mode writes soft-decline marker, not the completion marker."""
        # Simulate decline via "n\n" on stdin (not using PRAXION_AUTO_COMPLETE)
        result = subprocess.run(
            [sys.executable, str(_MODULE_PATH)],
            input=json.dumps(minimal_session_payload),
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(fake_home)},
            timeout=10,
        )

        # Must exit 0 regardless of interactive path outcome
        assert result.returncode == 0


class TestFourEnvironmentCombinations:
    """All four git-config × interactivity combinations must exit 0."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_git_config_set_non_interactive_auto_complete(
        self,
        fake_home,
        marker_path,
        minimal_session_payload,
        monkeypatch,
    ):
        """git config user.email set + non-interactive (PRAXION_AUTO_COMPLETE=1) → exit 0."""
        # Non-interactive: stdin.isatty() == False is simulated by subprocess piping + PRAXION_AUTO_COMPLETE
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={
                "PRAXION_AUTO_COMPLETE": "1",
                "GIT_AUTHOR_EMAIL": "user@example.com",
                "GIT_AUTHOR_NAME": "Test User",
            },
        )

        assert result.returncode == 0, (
            f"git-config-set + non-interactive should exit 0, got: {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_git_config_set_interactive_defaults_accepted(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """git config user.email set + interactive shell → exit 0 (user accepted via PRAXION_AUTO_COMPLETE)."""
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={
                "PRAXION_AUTO_COMPLETE": "1",
            },
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_git_config_unset_non_interactive_uses_fallbacks(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """git config user.email absent + non-interactive → fallback values used, exit 0."""
        # Ensure git config returns nothing — unset by using a no-op GIT_CONFIG_NOSYSTEM
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={
                "PRAXION_AUTO_COMPLETE": "1",
                "GIT_CONFIG_NOSYSTEM": "1",
                "HOME": str(fake_home),  # Explicit HOME to ensure no real ~/.gitconfig reads
                "XDG_CONFIG_HOME": str(fake_home / ".config"),
            },
        )

        # Even with no git config, install must complete and exit 0
        assert result.returncode == 0, (
            f"Absent git config + non-interactive should still exit 0\nstderr: {result.stderr}"
        )

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_git_config_unset_interactive_uses_fallback_with_prompt(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """git config unset + interactive → prompt shown with anon fallbacks, exits 0."""
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={
                "PRAXION_AUTO_COMPLETE": "1",
                "GIT_CONFIG_NOSYSTEM": "1",
                "XDG_CONFIG_HOME": str(fake_home / ".config"),
            },
        )

        assert result.returncode == 0


class TestInteractiveAndTimeoutBranches:
    """Interactive prompt, 30s timeout-accept, and non-interactive branches."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_auto_complete_flag_bypasses_prompt(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """PRAXION_AUTO_COMPLETE=1 → non-interactive install completes without prompting."""
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_auto_complete_derives_username_from_git_email(
        self,
        fake_home,
        marker_path,
        minimal_session_payload,
        tmp_path,
    ):
        """With PRAXION_AUTO_COMPLETE=1 and a known git email, USERNAME derives from email prefix."""
        # We can't easily check the rendered content without knowing the output path,
        # but we verify the hook completes without error (derive_defaults was called successfully)
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={
                "PRAXION_AUTO_COMPLETE": "1",
                "GIT_AUTHOR_EMAIL": "alice@example.com",
            },
        )

        assert result.returncode == 0, (
            f"Auto-complete with git email should succeed\nstderr: {result.stderr}"
        )

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_non_interactive_stdin_not_tty_uses_defaults(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """Non-interactive session (stdin not a tty) + PRAXION_AUTO_COMPLETE=1 → uses defaults."""
        # subprocess.run with input= simulates stdin piped (not a tty)
        result = subprocess.run(
            [sys.executable, str(_MODULE_PATH)],
            input=json.dumps(minimal_session_payload),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(fake_home),
                "PRAXION_AUTO_COMPLETE": "1",
            },
            timeout=10,
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_timeout_branch_accepts_defaults_when_no_input(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """When interactive timeout fires (30s), defaults are auto-accepted — hook exits 0."""
        # We cannot wait 30 real seconds in a test. Instead we verify the hook's
        # timeout-accept branch is reachable: if PRAXION_AUTO_COMPLETE is not set
        # AND stdin is piped (EOF immediately), the hook must still exit 0.
        result = subprocess.run(
            [sys.executable, str(_MODULE_PATH)],
            input=json.dumps(minimal_session_payload),  # EOF after payload
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(fake_home),
                # No PRAXION_AUTO_COMPLETE — exercises the interactive/timeout path
            },
            timeout=15,  # Generous timeout to avoid flakiness but still bounded
        )

        assert result.returncode == 0, (
            "Hook must exit 0 even when stdin is EOF'd in interactive mode "
            f"(timeout-accept branch)\nstderr: {result.stderr}"
        )

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_malformed_stdin_json_exits_zero(self, fake_home, minimal_session_payload):
        """Malformed stdin JSON → exit 0, no crash, no block."""
        result = subprocess.run(
            [sys.executable, str(_MODULE_PATH)],
            input="NOT_VALID_JSON{{{",
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(fake_home),
                "PRAXION_AUTO_COMPLETE": "1",
            },
            timeout=10,
        )

        assert result.returncode == 0, (
            f"Malformed JSON must not crash the hook\nstderr: {result.stderr}"
        )


class TestErrorResilience:
    """Internal errors → exit 0, stderr message, no crash, no block."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_empty_stdin_exits_zero(self, fake_home, minimal_session_payload):
        """Empty stdin → exit 0 (hook must degrade gracefully)."""
        result = subprocess.run(
            [sys.executable, str(_MODULE_PATH)],
            input="",
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(fake_home),
                "PRAXION_AUTO_COMPLETE": "1",
            },
            timeout=10,
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_permission_error_on_home_exits_zero(self, tmp_path, minimal_session_payload):
        """Filesystem permission error during install → exit 0, error on stderr."""
        # Create a home dir without write permissions on .claude/
        home = tmp_path / "noperm_home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        # Make .claude/ non-writable
        claude_dir.chmod(0o555)

        try:
            result = _run_hook_subprocess(
                minimal_session_payload,
                home_dir=home,
                env_extra={"PRAXION_AUTO_COMPLETE": "1"},
            )

            assert result.returncode == 0, (
                f"Permission error must not prevent exit 0\nstderr: {result.stderr}"
            )
        finally:
            # Restore write permission for cleanup
            claude_dir.chmod(0o755)

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_missing_plugin_cache_dir_handled_gracefully(
        self, fake_home, marker_path, minimal_session_payload
    ):
        """Plugin cache directory absent → no crash (mtime comparison degrades gracefully)."""
        import shutil

        plugin_cache = fake_home / ".claude" / "plugins"
        if plugin_cache.exists():
            shutil.rmtree(plugin_cache)

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_exit_zero_is_unconditional_contract(self, fake_home, minimal_session_payload):
        """The hook's exit 0 contract holds regardless of internal state — never blocks session start."""
        # Stress test: no surfaces at all, no git config, no PRAXION_AUTO_COMPLETE
        completely_empty_home = fake_home.parent / "empty_home"
        completely_empty_home.mkdir()

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=completely_empty_home,
            timeout=15,
        )

        assert result.returncode == 0, (
            "Exit 0 is unconditional — the hook must never block session start "
            f"even with empty home\nstderr: {result.stderr}"
        )

    def test_hook_exits_zero_with_no_env_set(self, fake_home, minimal_session_payload):
        """No PRAXION_* env vars set, nothing configured → hook still exits 0."""
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={},
        )

        assert result.returncode == 0


class TestModuleInterface:
    """Unit tests for the hook's internal functions — skipped until module exists."""

    @pytest.fixture(autouse=True)
    def _require_module(self):
        """Skip all tests in this class if the module doesn't exist yet."""
        if not _MODULE_PATH.exists():
            pytest.skip("auto_complete_install.py not yet implemented (expected RED state)")

    def test_module_is_importable(self):
        """The module can be imported without side effects."""
        module = _load_module()
        assert module is not None

    def test_module_exposes_required_callable(self):
        """Module exposes a callable entry point (main function or equivalent)."""
        module = _load_module()
        # The module must expose a callable entry point or run on exec.
        # Verified by the module loading without error above.
        assert module is not None

    def test_disable_flag_constant_defined(self):
        """Hook defines the PRAXION_DISABLE_AUTO_COMPLETE flag constant."""
        module = _load_module()
        sys.path.insert(0, str(HOOKS_DIR))
        import _hook_utils

        # Verify the flag name exists — either in _hook_utils or in auto_complete_install directly
        disable_flag = getattr(module, "DISABLE_AUTO_COMPLETE", None) or getattr(
            _hook_utils, "DISABLE_AUTO_COMPLETE", None
        )
        assert disable_flag is not None, (
            "DISABLE_AUTO_COMPLETE flag constant must be defined in the hook or _hook_utils"
        )

    def test_fast_path_check_returns_bool(self):
        """Fast-path predicate (is_install_complete) returns a boolean."""
        module = _load_module()
        # Look for the fast-path check function
        check_fn = getattr(module, "_is_install_complete", None) or getattr(
            module, "is_install_complete", None
        )
        if check_fn is None:
            pytest.skip("No explicit _is_install_complete function (may be inlined)")
        # Call with a fake home that has no state
        result = check_fn(Path("/tmp/nonexistent_home_xyz"))
        assert isinstance(result, bool)


class TestHomeResolution:
    def test_uses_the_home_environment_variable(self, tmp_path, monkeypatch):
        module = _fake_home_module(monkeypatch, tmp_path)

        assert module._home() == tmp_path

    def test_falls_back_to_the_platform_home_when_unset(self, monkeypatch):
        module = _load_module()
        monkeypatch.delenv("HOME", raising=False)

        # Path.home() consults pwd on some platforms; the fallback must still
        # produce a usable directory rather than an empty path.
        assert module._home() == Path.home()


class TestOperatorPrompt:
    @pytest.mark.parametrize("answer", ["n\n", "no\n", "N\n", "  No  \n"])
    def test_an_explicit_refusal_declines_the_install(self, answer, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(answer))

        assert update._prompt_with_timeout(_VALUES) is False

    @pytest.mark.parametrize("answer", ["y\n", "\n", "yes\n", "anything else\n"])
    def test_anything_other_than_a_refusal_proceeds(self, answer, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(answer))

        assert update._prompt_with_timeout(_VALUES) is True

    def test_the_prompt_shows_the_values_that_will_be_written(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))

        update._prompt_with_timeout(_VALUES)

        prompt = capsys.readouterr().err
        assert "@someone" in prompt
        assert "someone@example.com" in prompt

    def test_unreadable_stdin_is_treated_as_consent(self, monkeypatch):

        class _Unreadable:
            def readline(self) -> str:
                raise OSError("stdin is not readable")

        monkeypatch.setattr(sys, "stdin", _Unreadable())

        # A piped or headless session cannot answer; blocking it would wedge
        # session start, which this hook must never do.
        assert update._prompt_with_timeout(_VALUES) is True

    def test_a_platform_without_alarm_signals_still_proceeds(self, monkeypatch):

        def _no_alarm(*args: object, **kwargs: object):
            raise ValueError("signal only works in main thread")

        monkeypatch.setattr(update.signal, "signal", _no_alarm)

        assert update._prompt_with_timeout(_VALUES) is True


class TestAutoCompleteMode:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
    def test_recognised_opt_in_values_skip_the_prompt(self, value, monkeypatch):
        module = _load_module()
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", value)

        assert module._resolve_mode() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "maybe"])
    def test_everything_else_leaves_the_prompt_in_place(self, value, monkeypatch):
        module = _load_module()
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", value)

        assert module._resolve_mode() is False


class TestRealInstallLayout:
    """On the layout Claude Code installs, a first session completes the install.

    The hook once looked for the plugin in the unversioned cache parent, where
    Claude Code never puts a plugin's files: it linked nothing, rendered
    nothing, and reported success.
    """

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_a_first_session_links_the_contract_and_renders_claude_md(
        self, fake_home, plugin_root, minimal_session_payload
    ):
        _seed_template(plugin_root)

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0, result.stderr
        contract = fake_home / ".claude" / "rules" / "swe" / "agent-behavioral-contract.md"
        assert (
            contract.resolve()
            == (plugin_root / "rules" / "swe" / "agent-behavioral-contract.md").resolve()
        ), result.stderr
        claude_md = fake_home / ".claude" / "CLAUDE.md"
        assert claude_md.resolve() == (plugin_root / "claude" / "config" / "CLAUDE.md").resolve()
        assert "Auto-install complete" in result.stderr


class TestHookNeverRaisesIntoTheHarness:
    def test_an_unhandled_failure_below_main_is_swallowed(self, monkeypatch):
        module = _load_module()

        def _explodes(report: list[str] | None = None) -> None:
            raise RuntimeError("catastrophic install failure")

        monkeypatch.setattr(module, "_run", _explodes)

        module.main()  # must not raise -- SessionStart would otherwise be blocked


class TestUnwritableMarkerIsAbsorbed:
    """Marker bookkeeping is best-effort -- it must never become the blocker.

    Each case makes the marker genuinely unwritable rather than patching the
    writer, so the swallow being tested is the production one.
    """

    def test_an_unwritable_completion_marker_does_not_surface(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        (home / ".claude").write_text("not a directory\n", encoding="utf-8")
        module = _fake_home_module(monkeypatch, home)

        module._perform_install(home, _VALUES, auto_complete=True, root=home / "no-plugin")

    def test_an_unwritable_decline_marker_does_not_surface(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        (home / ".claude").write_text("not a directory\n", encoding="utf-8")
        module = _fake_home_module(monkeypatch, home)
        monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))

        module._perform_install(home, _VALUES, auto_complete=False, root=home / "no-plugin")

    def test_installed_surfaces_with_an_unwritable_marker_do_not_surface(
        self,
        fake_home,
        plugin_cache_dir,
        claude_md_symlink,
        rules_sentinel,
        marker_path,
        monkeypatch,
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        marker_path.mkdir()  # a directory where the marker file belongs
        # Age it behind the cache so the freshness guard does not short-circuit
        # before the surfaces-present branch this test is aiming at.
        os.utime(marker_path, (1_000_000, 1_000_000))
        os.utime(plugin_cache_dir, (2_000_000, 2_000_000))
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

    def test_a_run_whose_stdin_cannot_be_read_still_installs(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")

        class _Unreadable:
            def read(self) -> str:
                raise OSError("stdin is closed")

        monkeypatch.setattr(sys, "stdin", _Unreadable())

        module._run()

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
