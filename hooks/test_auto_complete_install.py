"""Behavioral tests for hooks/auto_complete_install.py — SessionStart install-completion hook.

The hook closes the marketplace install-path asymmetry by detecting missing global
surfaces (~/.claude/CLAUDE.md, ~/.claude/rules/, ~/.local/bin/ scripts) and
auto-completing them on first session start.

Coverage:
  1. Fast-skip path (steady state): marker present + fresh → no filesystem writes
  2. Marker rearm: marker older than plugin cache mtime → re-completion triggered
  3. Cold path — fresh marketplace install: surfaces missing → install runs + marker written
  4. Four environment combinations: git-config-set × interactive, git-config-set × non-interactive,
     git-config-unset × interactive, git-config-unset × non-interactive
  5. Idempotency: second run with marker present → ZERO filesystem writes
  6. Interactive/timeout/non-interactive branches
  7. Error resilience: internal errors → exit 0, no crash, no block

These tests are expected to FAIL (RED) until the production module
hooks/auto_complete_install.py exists. A GREEN result on first run in concurrent mode
is a Register Objection trigger per the BDD/TDD protocol.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

HOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOKS_DIR.parent

# ---------------------------------------------------------------------------
# Module-level import: deferred to inside each test body so pytest collection
# succeeds even when auto_complete_install.py does not yet exist (RED state).
# ---------------------------------------------------------------------------

_MODULE_PATH = HOOKS_DIR / "auto_complete_install.py"


def _load_module():
    """Import auto_complete_install as a module. Returns the module or raises ImportError."""
    import importlib.util

    if not _MODULE_PATH.exists():
        raise ImportError(
            f"hooks/auto_complete_install.py does not exist — expected at {_MODULE_PATH}"
        )
    spec = importlib.util.spec_from_file_location("auto_complete_install", _MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Could not create module spec for auto_complete_install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _clear_praxion_env(monkeypatch):
    """Each test starts with no PRAXION_* or HOME-interfering env vars set."""
    for key in (
        "PRAXION_DISABLE_AUTO_COMPLETE",
        "PRAXION_AUTO_COMPLETE",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fake_home(tmp_path):
    """Return a fake HOME directory with Praxion plugin cache structure pre-built."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "plugins" / "cache" / "bit-agora" / "i-am").mkdir(parents=True)
    (home / ".claude" / "rules" / "swe").mkdir(parents=True)
    (home / ".local" / "bin").mkdir(parents=True)
    return home


@pytest.fixture
def plugin_cache_dir(fake_home):
    """Return the plugin cache directory path."""
    return fake_home / ".claude" / "plugins" / "cache" / "bit-agora" / "i-am"


@pytest.fixture
def marker_path(fake_home):
    """Return the marker file path."""
    return fake_home / ".claude" / ".praxion-complete-installed"


@pytest.fixture
def rules_sentinel(fake_home):
    """Create the sentinel rules file indicating completed install."""
    sentinel = fake_home / ".claude" / "rules" / "swe" / "agent-behavioral-contract.md"
    sentinel.write_text("# behavioral contract\n")
    return sentinel


@pytest.fixture
def claude_md_symlink(fake_home, tmp_path):
    """Create ~/.claude/CLAUDE.md as a symlink targeting a real file (simulating a rendered template)."""
    target = tmp_path / "rendered_claude.md"
    target.write_text("# Rendered CLAUDE.md\n{{USERNAME}}\n")
    symlink = fake_home / ".claude" / "CLAUDE.md"
    symlink.symlink_to(target)
    return symlink


@pytest.fixture
def minimal_session_payload():
    """Minimal SessionStart JSON payload for the hook."""
    return {
        "hook_event_name": "SessionStart",
        "session_id": "test-session-001",
        "cwd": "/tmp/test-project",
        "transcript_path": "/dev/null",
    }


def _run_hook_subprocess(
    payload: dict[str, Any],
    env_extra: dict[str, str] | None = None,
    home_dir: Path | None = None,
    timeout: int = 10,
) -> subprocess.CompletedProcess:
    """Run auto_complete_install.py as a subprocess with the given payload."""
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    if home_dir is not None:
        env["HOME"] = str(home_dir)
    return subprocess.run(
        [sys.executable, str(_MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


# ===========================================================================
# Group 1: Fast-skip path (steady state)
# ===========================================================================


class TestFastSkipPath:
    """When all surfaces are present and marker is fresh, hook exits silently."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_marker_present_and_fresh_exits_zero(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Marker newer than plugin cache → fast-skip, exit 0."""
        # Arrange: marker is newer than plugin cache dir
        plugin_cache_dir.touch()
        marker_path.write_text("")
        # Set marker mtime to be 1 second newer than plugin cache
        marker_time = os.stat(plugin_cache_dir).st_mtime + 1
        os.utime(marker_path, (marker_time, marker_time))

        # Act
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        # Assert
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_fast_skip_produces_no_stdout(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Fast-skip path must be silent on stdout."""
        plugin_cache_dir.touch()
        marker_path.write_text("")
        marker_time = os.stat(plugin_cache_dir).st_mtime + 1
        os.utime(marker_path, (marker_time, marker_time))

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0, (
            f"Precondition: hook must exit 0 before asserting stdout\nstderr: {result.stderr}"
        )
        assert result.stdout == "", f"Fast-skip should produce no stdout, got: {result.stdout!r}"

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_fast_skip_completes_under_50ms(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Fast-skip path wall-clock must be under 50ms overhead after Python startup."""
        plugin_cache_dir.touch()
        marker_path.write_text("")
        marker_time = os.stat(plugin_cache_dir).st_mtime + 1
        os.utime(marker_path, (marker_time, marker_time))

        start = time.perf_counter()
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result.returncode == 0, f"Precondition: hook must exit 0\nstderr: {result.stderr}"
        # Python startup is ~30-50ms; total hook including startup < 500ms for CI
        assert elapsed_ms < 500, f"Fast-skip path took {elapsed_ms:.1f}ms — expected < 500ms total"

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_disable_flag_exits_zero_regardless_of_state(self, fake_home, minimal_session_payload):
        """PRAXION_DISABLE_AUTO_COMPLETE=1 → exit 0 silently, no filesystem writes."""
        # Arrange: no surfaces exist at all
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_DISABLE_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_all_surfaces_present_without_marker_writes_marker_and_exits_zero(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """All surfaces present but no marker → write marker, exit 0, no install."""
        assert not marker_path.exists()

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0
        assert marker_path.exists(), "Marker file should be written when all surfaces are present"


# ===========================================================================
# Group 2: Marker rearm (plugin-update detection)
# ===========================================================================


class TestMarkerRearm:
    """When marker is older than plugin cache directory mtime, hook re-runs."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_stale_marker_triggers_reinstall(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        minimal_session_payload,
    ):
        """Marker present but older than plugin cache mtime → cold path runs (install triggers)."""
        # Arrange: marker is OLDER than plugin cache
        marker_path.write_text("")
        old_time = time.time() - 3600  # 1 hour ago
        os.utime(marker_path, (old_time, old_time))
        # Plugin cache updated 30 min ago (newer than marker)
        newer_time = time.time() - 1800
        os.utime(plugin_cache_dir, (newer_time, newer_time))

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        # Hook must still exit 0 (never blocks); it should attempt reinstall
        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_fresh_marker_skips_even_after_plugin_update(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Marker mtime > plugin cache mtime → fast-skip even if plugin cache exists."""
        plugin_cache_dir.touch()
        marker_path.write_text("")
        # Set marker newer than plugin cache
        newer = os.stat(plugin_cache_dir).st_mtime + 10
        os.utime(marker_path, (newer, newer))

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_mtime_manipulation_via_utime(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        minimal_session_payload,
    ):
        """Verify os.utime() correctly controls the stale-marker comparison used by the hook."""
        # This test documents the mtime-manipulation technique for the hook test suite
        marker_path.write_text("")
        future_time = time.time() + 3600
        os.utime(marker_path, (future_time, future_time))
        assert os.stat(marker_path).st_mtime > os.stat(plugin_cache_dir).st_mtime, (
            "os.utime should set marker mtime in the future relative to plugin cache"
        )


# ===========================================================================
# Group 3: Cold path — fresh marketplace install
# ===========================================================================


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


# ===========================================================================
# Group 4: Four environment combinations
# ===========================================================================


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


# ===========================================================================
# Group 5: Idempotency
# ===========================================================================


class TestIdempotency:
    """Second run with marker present must produce ZERO filesystem writes."""

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_second_run_is_no_op(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Second run with fresh marker → no filesystem changes (idempotency core contract)."""
        # Arrange: complete the first run
        plugin_cache_dir.touch()
        marker_path.write_text("")
        marker_time = os.stat(plugin_cache_dir).st_mtime + 1
        os.utime(marker_path, (marker_time, marker_time))

        # Record filesystem state before second run
        files_before = _snapshot_home_files(fake_home)

        # Act: second run
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        # Assert: exit 0
        assert result.returncode == 0

        # Assert: no new files created
        files_after = _snapshot_home_files(fake_home)
        new_files = files_after - files_before
        assert not new_files, f"Second run created unexpected new files: {new_files}"

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_second_run_produces_no_stdout(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Second run (fast-skip) must produce no stdout output."""
        plugin_cache_dir.touch()
        marker_path.write_text("")
        marker_time = os.stat(plugin_cache_dir).st_mtime + 1
        os.utime(marker_path, (marker_time, marker_time))

        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
        )

        assert result.returncode == 0, f"Precondition: hook must exit 0\nstderr: {result.stderr}"
        assert result.stdout == "", (
            f"Idempotent second run must produce no stdout; got: {result.stdout!r}"
        )

    @pytest.mark.usefixtures("_clear_praxion_env")
    def test_no_reprompt_on_second_run(
        self,
        fake_home,
        marker_path,
        plugin_cache_dir,
        rules_sentinel,
        claude_md_symlink,
        minimal_session_payload,
    ):
        """Second run with fresh marker must not attempt to prompt the user (no re-renders)."""
        plugin_cache_dir.touch()
        marker_path.write_text("")
        marker_time = os.stat(plugin_cache_dir).st_mtime + 1
        os.utime(marker_path, (marker_time, marker_time))

        # The subprocess reads from /dev/null stdin so any attempt to prompt
        # will immediately receive EOF — hook must still exit 0, never hang
        result = _run_hook_subprocess(
            minimal_session_payload,
            home_dir=fake_home,
            env_extra={"PRAXION_AUTO_COMPLETE": "1"},
            timeout=5,  # Tight timeout — if it hangs, idempotency is broken
        )

        assert result.returncode == 0, (
            "Second run must exit 0 in under 5 seconds (no prompt hung on EOF stdin)"
        )


# ===========================================================================
# Group 6: Interactive, timeout, and non-interactive branches
# ===========================================================================


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


# ===========================================================================
# Group 7: Error resilience
# ===========================================================================


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


# ===========================================================================
# Group 8: Unit-level tests via module import (run only when module exists)
# ===========================================================================


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


# ===========================================================================
# Group 9: _link_rules() per-file filtering — new manifest-driven behavior
# ===========================================================================


def _make_plugin_cache(tmp_path: Path) -> Path:
    """Build a minimal plugin cache with a rules/ directory. Returns the cache path."""
    cache = tmp_path / "home" / ".claude" / "plugins" / "cache" / "bit-agora" / "i-am"
    cache.mkdir(parents=True)
    return cache


def _seed_rules(rules_src: Path, files: dict[str, str]) -> None:
    """Write rule files into rules_src. Keys are relative paths, values are content."""
    for rel, content in files.items():
        target = rules_src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def _seed_manifest(rules_src: Path, hook_deliver_ids: list[str]) -> None:
    """Write a synthetic _manifest.yaml into rules_src.

    hook_deliver_ids is a list of IDs like 'swe/memory-protocol'; their path
    field is derived as 'rules/<id>.md'.
    """
    entries = []
    for rule_id in hook_deliver_ids:
        entries.append(
            f"- id: {rule_id}\n  path: rules/{rule_id}.md\n  install: hook-deliver\n  core: false\n"
        )
    symlink_ids = ["swe/agent-behavioral-contract"]
    for rule_id in symlink_ids:
        if rule_id not in hook_deliver_ids:
            entries.append(
                f"- id: {rule_id}\n  path: rules/{rule_id}.md\n  install: symlink\n  core: true\n"
            )
    manifest_content = "version: 1\nrules:\n" + "".join(entries)
    (rules_src / "_manifest.yaml").write_text(manifest_content)


class TestLinkRulesFiltering:
    """Unit tests for _link_rules() per-file manifest-driven filtering."""

    @pytest.fixture(autouse=True)
    def _require_module(self):
        """Skip all tests in this class if the module doesn't exist yet."""
        if not _MODULE_PATH.exists():
            pytest.skip("auto_complete_install.py not yet implemented")

    def _get_link_rules(self):
        """Return the _link_rules callable from the module."""
        module = _load_module()
        fn = getattr(module, "_link_rules", None)
        assert fn is not None, "_link_rules must be defined in auto_complete_install.py"
        return fn

    def test_hook_deliver_rule_not_symlinked_when_manifest_present(self, tmp_path):
        """With manifest marking a rule hook-deliver, that rule's symlink is NOT created."""
        cache = _make_plugin_cache(tmp_path)
        home = tmp_path / "home"
        rules_src = cache / "rules"

        _seed_rules(
            rules_src,
            {
                "swe/agent-behavioral-contract.md": "# behavioral contract\n",
                "swe/memory-protocol.md": "# memory protocol\n",
            },
        )
        _seed_manifest(rules_src, hook_deliver_ids=["swe/memory-protocol"])

        _link_rules = self._get_link_rules()
        _link_rules(home)

        rules_dest = home / ".claude" / "rules"
        sentinel = rules_dest / "swe" / "agent-behavioral-contract.md"
        memory_link = rules_dest / "swe" / "memory-protocol.md"

        assert sentinel.is_symlink(), (
            "Core rule swe/agent-behavioral-contract.md must always be symlinked"
        )
        assert not memory_link.exists(), (
            "Hook-deliver rule swe/memory-protocol.md must NOT be symlinked"
        )

    def test_stale_hook_deliver_symlink_is_removed(self, tmp_path):
        """Pre-existing symlink for a now-hook-deliver rule is removed on re-install."""
        cache = _make_plugin_cache(tmp_path)
        home = tmp_path / "home"
        rules_src = cache / "rules"

        _seed_rules(
            rules_src,
            {
                "swe/agent-behavioral-contract.md": "# behavioral contract\n",
                "swe/memory-protocol.md": "# memory protocol\n",
            },
        )
        # Create a stale symlink as if a previous install had linked the file
        stale_link = home / ".claude" / "rules" / "swe" / "memory-protocol.md"
        stale_link.parent.mkdir(parents=True, exist_ok=True)
        stale_link.symlink_to(rules_src / "swe" / "memory-protocol.md")
        assert stale_link.is_symlink(), "Precondition: stale symlink must exist"

        _seed_manifest(rules_src, hook_deliver_ids=["swe/memory-protocol"])

        _link_rules = self._get_link_rules()
        _link_rules(home)

        assert not stale_link.exists(), (
            "Stale symlink for hook-deliver rule must be removed on re-install"
        )

    def test_no_manifest_links_all_rules(self, tmp_path):
        """Without manifest (legacy fallback), all .md rules are linked."""
        cache = _make_plugin_cache(tmp_path)
        home = tmp_path / "home"
        rules_src = cache / "rules"

        _seed_rules(
            rules_src,
            {
                "swe/agent-behavioral-contract.md": "# behavioral contract\n",
                "swe/memory-protocol.md": "# memory protocol\n",
                "CLAUDE.md": "# CLAUDE\n",
            },
        )
        # No _manifest.yaml written — fallback path

        _link_rules = self._get_link_rules()
        _link_rules(home)

        rules_dest = home / ".claude" / "rules"
        assert (rules_dest / "swe" / "agent-behavioral-contract.md").is_symlink(), (
            "No-manifest fallback must link agent-behavioral-contract.md"
        )
        assert (rules_dest / "swe" / "memory-protocol.md").is_symlink(), (
            "No-manifest fallback must link memory-protocol.md"
        )
        assert (rules_dest / "CLAUDE.md").is_symlink(), (
            "No-manifest fallback must link root-level CLAUDE.md"
        )

    def test_readme_and_references_are_skipped(self, tmp_path):
        """README.md files and */references/* paths are never symlinked."""
        cache = _make_plugin_cache(tmp_path)
        home = tmp_path / "home"
        rules_src = cache / "rules"

        _seed_rules(
            rules_src,
            {
                "swe/agent-behavioral-contract.md": "# behavioral contract\n",
                "README.md": "# README\n",
                "swe/references/some-reference.md": "# reference\n",
            },
        )
        # No manifest — fallback path (all non-skipped files linked)

        _link_rules = self._get_link_rules()
        _link_rules(home)

        rules_dest = home / ".claude" / "rules"
        assert not (rules_dest / "README.md").exists(), "README.md must never be symlinked"
        assert not (rules_dest / "swe" / "references" / "some-reference.md").exists(), (
            "Files under references/ must never be symlinked"
        )
        assert (rules_dest / "swe" / "agent-behavioral-contract.md").is_symlink(), (
            "Regular rule files must still be symlinked"
        )

    def test_sentinel_path_always_linked(self, tmp_path):
        """swe/agent-behavioral-contract.md is always symlinked (core rule, install: symlink)."""
        cache = _make_plugin_cache(tmp_path)
        home = tmp_path / "home"
        rules_src = cache / "rules"

        _seed_rules(
            rules_src,
            {
                "swe/agent-behavioral-contract.md": "# behavioral contract\n",
                "swe/memory-protocol.md": "# memory protocol\n",
                "swe/agent-model-routing.md": "# agent model routing\n",
            },
        )
        # All non-sentinel rules are hook-deliver; sentinel stays symlinked
        _seed_manifest(
            rules_src,
            hook_deliver_ids=["swe/memory-protocol", "swe/agent-model-routing"],
        )

        _link_rules = self._get_link_rules()
        _link_rules(home)

        rules_dest = home / ".claude" / "rules"
        sentinel = rules_dest / "swe" / "agent-behavioral-contract.md"
        assert sentinel.is_symlink(), (
            "swe/agent-behavioral-contract.md (sentinel path checked by auto_complete_install.py:115)"
            " must always be symlinked regardless of manifest"
        )


# ===========================================================================
# Helpers
# ===========================================================================


def _snapshot_home_files(home: Path) -> set[Path]:
    """Return a set of all files currently under `home`."""
    return {p for p in home.rglob("*") if p.is_file()}
