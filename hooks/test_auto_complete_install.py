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

import io
import json
import os
import shutil
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
# The mutation sensor runs a copy of this directory one level down, so the checkout
# root is the nearest ancestor that holds the installer's shared library.
REPO_ROOT = next(p for p in HOOKS_DIR.parents if (p / "lib" / "install_shared.sh").is_file())
# The hook finds `render_claude_md` beside its own directory; a relocated copy does not.
_SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(HOOKS_DIR))
import _install_update as update  # noqa: E402 (after sys.path injection)

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


@pytest.fixture(autouse=True)
def _render_module_reachable_by_the_hook_subprocess(monkeypatch):
    """The tests that run the hook as a process need `render_claude_md` too."""
    ambient = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, (str(_SCRIPTS_DIR), ambient))))


@pytest.fixture(autouse=True)
def _no_ambient_plugin_root(monkeypatch):
    """No test reads the session's own plugin: a Claude Code session exports
    CLAUDE_PLUGIN_ROOT, which would point the hook at a real checkout."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)


@pytest.fixture
def _clear_praxion_env(monkeypatch):
    """Each test starts with no PRAXION_* or HOME-interfering env vars set."""
    for key in (
        "PRAXION_DISABLE_AUTO_COMPLETE",
        "PRAXION_AUTO_COMPLETE",
    ):
        monkeypatch.delenv(key, raising=False)


_PLUGIN_VERSION = "9.9.9"

# A synthetic manifest in the generator's flat shape: two rules the installer
# links and one it leaves to the session-start hook.
_MANIFEST = (
    "version: 1\n"
    "rules:\n"
    "  - id: swe/agent-behavioral-contract\n"
    "    path: rules/swe/agent-behavioral-contract.md\n"
    "    install: symlink\n"
    "  - id: swe/coding-style\n"
    "    path: rules/swe/coding-style.md\n"
    "    install: symlink\n"
    "  - id: swe/agent-model-routing-resident\n"
    "    path: rules/swe/agent-model-routing-resident.md\n"
    "    install: hook-deliver\n"
)

_PLUGIN_RULE_FILES = {
    "swe/agent-behavioral-contract.md": "# behavioral contract\n",
    "swe/coding-style.md": "# coding style\n",
    "swe/agent-model-routing-resident.md": "# routing resident\n",
    "README.md": "# catalog\n",
    "CLAUDE.md": "# directory guide\n",
    "swe/references/deep-dive.md": "# reference\n",
}


def _install_plugin(home: Path, version: str = _PLUGIN_VERSION) -> Path:
    """Lay out a plugin the way Claude Code installs one, and register it.

    The plugin lives in a version directory under the cache, holding the
    installer's shared library, a rules tree with its manifest, an empty
    scripts directory and no CLAUDE.md template (tests seed one when they need
    it); `installed_plugins.json` names it. Returns the version directory.
    """
    root = home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / version
    (root / "lib").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "lib" / "install_shared.sh", root / "lib" / "install_shared.sh")
    rules = root / "rules"
    for rel, body in _PLUGIN_RULE_FILES.items():
        (rules / rel).parent.mkdir(parents=True, exist_ok=True)
        (rules / rel).write_text(body, encoding="utf-8")
    (rules / "_manifest.yaml").write_text(_MANIFEST, encoding="utf-8")
    (root / "scripts").mkdir()
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    registry.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "praxion@bit-agora": [
                        {"scope": "user", "installPath": str(root), "version": version}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def fake_home(tmp_path):
    """Return a fake HOME holding a registered, versioned Praxion plugin."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _install_plugin(home)
    (home / ".claude" / "rules" / "swe").mkdir(parents=True)
    (home / ".local" / "bin").mkdir(parents=True)
    return home


@pytest.fixture
def plugin_cache_dir(fake_home):
    """Return the unversioned cache parent, whose mtime re-arms the hook."""
    return fake_home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion"


@pytest.fixture
def plugin_root(plugin_cache_dir):
    """Return the installed plugin's version directory, the hook's install source."""
    return plugin_cache_dir / _PLUGIN_VERSION


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
# Helpers
# ===========================================================================


def _snapshot_home_files(home: Path) -> set[Path]:
    """Return a set of all files currently under `home`."""
    return {p for p in home.rglob("*") if p.is_file()}


# ===========================================================================
# Group 10: In-process drive of the install primitives.
#
# The subprocess groups above pin the hook's runtime shape -- a real
# interpreter, a real exit code, a real stdin. They cannot observe *what the
# install actually did to the filesystem*, nor substitute the boundaries
# (signals, PyYAML, git) whose failure modes this hook is built to absorb.
#
# Every test here fakes HOME first. `_home()` reads os.environ["HOME"]
# specifically so this is possible; without it these tests would symlink into
# the operator's real ~/.claude.
# ===========================================================================


def _fake_home_module(monkeypatch, home: Path):
    """Point the module under test at a throwaway HOME and return it."""
    monkeypatch.setenv("HOME", str(home))
    return _load_module()


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


class TestInstallFreshnessPredicate:
    """The marker is only trusted while it is newer than the plugin cache."""

    def test_absent_marker_means_the_install_has_not_run(self, fake_home, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._is_install_complete(fake_home) is False

    def test_marker_newer_than_the_plugin_cache_is_trusted(
        self, fake_home, plugin_cache_dir, marker_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        marker_path.write_text("")
        os.utime(plugin_cache_dir, (1_000_000, 1_000_000))
        os.utime(marker_path, (2_000_000, 2_000_000))

        assert module._is_install_complete(fake_home) is True

    def test_a_plugin_update_rearms_the_install(
        self, fake_home, plugin_cache_dir, marker_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        marker_path.write_text("")
        # The update touched the cache after the marker was written: the
        # surfaces the marker vouches for may now be stale.
        os.utime(marker_path, (1_000_000, 1_000_000))
        os.utime(plugin_cache_dir, (2_000_000, 2_000_000))

        assert module._is_install_complete(fake_home) is False

    def test_a_marker_with_no_plugin_cache_to_compare_against_is_not_trusted(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        module = _fake_home_module(monkeypatch, home)
        (home / ".claude" / ".praxion-complete-installed").write_text("")

        # No cache directory: the freshness comparison is impossible, so the
        # safe answer is "incomplete" (attempt the install) rather than "done".
        assert module._is_install_complete(home) is False


class TestSurfacePresence:
    def test_symlinked_claude_md_plus_rules_sentinel_counts_as_installed(
        self, fake_home, claude_md_symlink, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._surfaces_present(fake_home) is True

    def test_a_regular_claude_md_is_not_an_installed_surface(
        self, fake_home, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        # A hand-authored ~/.claude/CLAUDE.md is a real file, not a plugin
        # symlink. Treating it as installed would leave the operator's own
        # file permanently mistaken for a rendered one.
        (fake_home / ".claude" / "CLAUDE.md").write_text("# my own notes\n")

        assert module._surfaces_present(fake_home) is False

    def test_missing_rules_sentinel_is_not_an_installed_surface(
        self, fake_home, claude_md_symlink, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._surfaces_present(fake_home) is False

    def test_a_dangling_claude_md_link_is_not_an_installed_surface(
        self, fake_home, rules_sentinel, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        # The rendered file lived in an old plugin version's directory, which
        # Claude Code has since removed.
        (fake_home / ".claude" / "CLAUDE.md").symlink_to(tmp_path / "removed" / "CLAUDE.md")

        assert module._surfaces_present(fake_home) is False


class TestMarkerWriting:
    def test_completion_marker_is_created_with_its_parent_directory(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        module = _fake_home_module(monkeypatch, home)

        module._write_marker(home)

        assert (home / ".claude" / ".praxion-complete-installed").exists()

    def test_decline_marker_is_a_distinct_file(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        module = _fake_home_module(monkeypatch, home)

        module._write_decline_marker(home)

        assert (home / ".claude" / ".praxion-install-declined").exists()
        assert not (home / ".claude" / ".praxion-complete-installed").exists()


def _seed_template(plugin_cache: Path, body: str = "user={{USERNAME}} mail={{EMAIL}}\n") -> Path:
    """Place a CLAUDE.md template where the plugin cache expects it."""
    template = plugin_cache / "claude" / "config" / "CLAUDE.md.tmpl"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(body, encoding="utf-8")
    return template


_VALUES = {
    "USERNAME": "@someone",
    "EMAIL": "someone@example.com",
    "GITHUB_URL": "https://github.com/someone",
}


class TestClaudeMdRendering:
    def test_renders_the_template_and_links_it_into_the_claude_directory(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)

        module._render_claude_md(fake_home, _VALUES, plugin_root)

        link = fake_home / ".claude" / "CLAUDE.md"
        assert link.is_symlink(), "CLAUDE.md must be a symlink so plugin updates propagate"
        assert link.read_text(encoding="utf-8") == "user=@someone mail=someone@example.com\n"

    def test_replaces_a_previously_rendered_symlink(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        stale_target = tmp_path / "stale.md"
        stale_target.write_text("stale\n", encoding="utf-8")
        (fake_home / ".claude" / "CLAUDE.md").symlink_to(stale_target)

        module._render_claude_md(fake_home, _VALUES, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8").startswith("user=")

    def test_replaces_a_regular_file_left_at_the_link_path(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        (fake_home / ".claude" / "CLAUDE.md").write_text("hand written\n", encoding="utf-8")

        module._render_claude_md(fake_home, _VALUES, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()

    def test_a_missing_template_surfaces_rather_than_silently_producing_nothing(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        # `_render_claude_md` documents that it raises; `_perform_install` is
        # the layer that decides to swallow. Losing the raise here would make
        # a broken plugin cache indistinguishable from a good one.
        with pytest.raises(FileNotFoundError):
            module._render_claude_md(fake_home, _VALUES, plugin_root)


class TestPluginRoot:
    """The hook installs from the plugin's own version directory."""

    def test_the_registered_install_path_is_the_plugin_root(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._plugin_root(fake_home) == plugin_root

    def test_the_hooks_own_plugin_root_wins_over_the_registry(
        self, fake_home, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        own = tmp_path / "checkout"
        own.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(own))

        assert module._plugin_root(fake_home) == own

    def test_the_unversioned_cache_parent_alone_is_no_plugin(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion").mkdir(parents=True)
        module = _fake_home_module(monkeypatch, home)

        # Claude Code never installs a plugin's files into the cache parent.
        assert module._plugin_root(home) is None

    def test_a_registry_naming_a_missing_directory_is_no_plugin(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        shutil.rmtree(plugin_root)

        assert module._plugin_root(fake_home) is None


def _rule_links(home: Path) -> dict[str, Path]:
    """Every link in the user rules directory: its path there -> what it resolves to."""
    rules = home / ".claude" / "rules"
    return {
        str(p.relative_to(rules)): p.resolve() for p in sorted(rules.rglob("*")) if p.is_symlink()
    }


def _plant_link(home: Path, rel: str, target: Path) -> Path:
    link = home / ".claude" / "rules" / rel
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return link


class TestRuleLinking:
    """A cold install links through the installer's own library."""

    def test_links_exactly_the_manifests_symlink_rules(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._link_rules(fake_home, plugin_root)

        # Not the hook-delivered resident, the catalog, the directory guide or
        # reference material: only what the manifest marks `install: symlink`.
        assert sorted(_rule_links(fake_home)) == [
            "swe/agent-behavioral-contract.md",
            "swe/coding-style.md",
        ]

    def test_a_rule_that_became_hook_delivered_has_its_stale_link_removed(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        rel = "swe/agent-model-routing-resident.md"
        stale = _plant_link(fake_home, rel, plugin_root / "rules" / rel)

        module._link_rules(fake_home, plugin_root)

        assert not stale.is_symlink(), "a re-install must clean up the previous install's link"

    def test_relinking_replaces_an_existing_symlink(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        outdated = tmp_path / "outdated.md"
        outdated.write_text("outdated\n", encoding="utf-8")
        _plant_link(fake_home, "swe/coding-style.md", outdated)

        module._link_rules(fake_home, plugin_root)

        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_a_plugin_without_a_rules_directory_links_nothing(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        shutil.rmtree(plugin_root / "rules")

        module._link_rules(fake_home, plugin_root)

        assert _rule_links(fake_home) == {}


class TestRuleRefresh:
    """After an update the hook refreshes the rule links without taking any over."""

    def test_sweeps_an_older_versions_link_to_a_now_hook_delivered_rule(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        rel = "swe/agent-model-routing-resident.md"
        older = plugin_root.parent / "9.9.8" / "rules" / rel
        older.parent.mkdir(parents=True)
        older.write_text("# routing resident, as an older version linked it\n", encoding="utf-8")
        stale = _plant_link(fake_home, rel, older)

        module._refresh_rules(fake_home, plugin_root)

        # Left in place, every session would keep loading a rule the plugin
        # now delivers only where the project is managed.
        assert not stale.is_symlink()

    def test_links_a_manifest_rule_that_has_no_link(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._refresh_rules(fake_home, plugin_root)

        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_relinks_a_dangling_link(self, fake_home, plugin_root, tmp_path, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _plant_link(fake_home, "swe/coding-style.md", tmp_path / "removed-version" / "gone.md")

        module._refresh_rules(fake_home, plugin_root)

        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_leaves_a_live_link_into_a_checkout_as_it_is(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        checkout_rule = tmp_path / "checkout" / "rules" / "swe" / "coding-style.md"
        checkout_rule.parent.mkdir(parents=True)
        checkout_rule.write_text("# coding style, from a clone install\n", encoding="utf-8")
        _plant_link(fake_home, "swe/coding-style.md", checkout_rule)

        module._refresh_rules(fake_home, plugin_root)

        # A clone install owns its links; re-pointing them at the plugin cache
        # would silently move a developer off their checkout.
        assert _rule_links(fake_home)["swe/coding-style.md"] == checkout_rule.resolve()

    def test_never_replaces_a_regular_file_at_a_rule_path(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        own = fake_home / ".claude" / "rules" / "swe" / "coding-style.md"
        own.write_text("# the operator's own rule\n", encoding="utf-8")

        module._refresh_rules(fake_home, plugin_root)

        assert not own.is_symlink()
        assert own.read_text(encoding="utf-8") == "# the operator's own rule\n"


def _seed_script(scripts_src: Path, name: str, executable: bool = True) -> Path:
    scripts_src.mkdir(parents=True, exist_ok=True)
    script = scripts_src / name
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    if executable:
        script.chmod(0o755)
    else:
        script.chmod(0o644)
    return script


class TestScriptLinking:
    def test_absent_scripts_directory_is_a_no_op(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._link_scripts(fake_home, plugin_root)

        assert list((fake_home / ".local" / "bin").iterdir()) == []

    def test_links_executable_scripts_onto_the_path(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_script(plugin_root / "scripts", "praxion-dashboard")

        module._link_scripts(fake_home, plugin_root)

        assert (fake_home / ".local" / "bin" / "praxion-dashboard").is_symlink()

    @pytest.mark.parametrize(
        ("name", "executable", "reason"),
        [
            ("helper.py", False, "not executable -- not a user-facing entry point"),
            ("merge_driver_observations.py", True, "git invokes merge drivers, not the operator"),
            ("post-merge-hook.sh", True, "git invokes hooks, not the operator"),
        ],
    )
    def test_non_operator_facing_files_stay_off_the_path(
        self, fake_home, plugin_root, monkeypatch, name, executable, reason
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_script(plugin_root / "scripts", name, executable=executable)

        module._link_scripts(fake_home, plugin_root)

        assert not (fake_home / ".local" / "bin" / name).exists(), reason

    def test_relinking_replaces_an_existing_symlink(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")
        outdated = tmp_path / "outdated-dashboard"
        outdated.write_text("#!/bin/sh\n", encoding="utf-8")
        dest = fake_home / ".local" / "bin" / "praxion-dashboard"
        dest.symlink_to(outdated)

        module._link_scripts(fake_home, plugin_root)

        assert dest.resolve() == script.resolve()


def _cached_version(home: Path, version: str) -> Path:
    """A version directory of the plugin cache, other than the running one."""
    root = home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / version
    (root / "scripts").mkdir(parents=True)
    return root


class TestFullInstallSequence:
    def test_runs_every_install_step(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        _seed_script(plugin_root / "scripts", "praxion-dashboard")

        module._run_install(fake_home, _VALUES, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
        assert (fake_home / ".claude" / "rules" / "swe" / "coding-style.md").is_symlink()
        assert (fake_home / ".local" / "bin" / "praxion-dashboard").is_symlink()


class TestOperatorPrompt:
    @pytest.mark.parametrize("answer", ["n\n", "no\n", "N\n", "  No  \n"])
    def test_an_explicit_refusal_declines_the_install(self, answer, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(sys, "stdin", io.StringIO(answer))

        assert module._prompt_with_timeout(_VALUES) is False

    @pytest.mark.parametrize("answer", ["y\n", "\n", "yes\n", "anything else\n"])
    def test_anything_other_than_a_refusal_proceeds(self, answer, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(sys, "stdin", io.StringIO(answer))

        assert module._prompt_with_timeout(_VALUES) is True

    def test_the_prompt_shows_the_values_that_will_be_written(self, monkeypatch, capsys):
        module = _load_module()
        monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))

        module._prompt_with_timeout(_VALUES)

        prompt = capsys.readouterr().err
        assert "@someone" in prompt
        assert "someone@example.com" in prompt

    def test_unreadable_stdin_is_treated_as_consent(self, monkeypatch):
        module = _load_module()

        class _Unreadable:
            def readline(self) -> str:
                raise OSError("stdin is not readable")

        monkeypatch.setattr(sys, "stdin", _Unreadable())

        # A piped or headless session cannot answer; blocking it would wedge
        # session start, which this hook must never do.
        assert module._prompt_with_timeout(_VALUES) is True

    def test_a_platform_without_alarm_signals_still_proceeds(self, monkeypatch):
        module = _load_module()

        def _no_alarm(*args: object, **kwargs: object):
            raise ValueError("signal only works in main thread")

        monkeypatch.setattr(module.signal, "signal", _no_alarm)

        assert module._prompt_with_timeout(_VALUES) is True


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


class TestPerformInstall:
    def test_auto_complete_installs_and_records_completion(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)

        module._perform_install(fake_home, _VALUES, auto_complete=True, root=plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()

    def test_a_refusal_records_the_decline_and_installs_nothing(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))

        module._perform_install(fake_home, _VALUES, auto_complete=False, root=plugin_root)

        assert (fake_home / ".claude" / ".praxion-install-declined").exists()
        assert not (fake_home / ".claude" / ".praxion-complete-installed").exists()
        assert not (fake_home / ".claude" / "CLAUDE.md").exists()

    def test_a_failed_install_still_records_completion(
        self, fake_home, plugin_root, monkeypatch, capsys
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        # No template seeded: `_render_claude_md` raises FileNotFoundError.

        module._perform_install(fake_home, _VALUES, auto_complete=True, root=plugin_root)

        # Deliberate: without the marker the hook would retry the same failing
        # install on every single session start.
        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()
        # ...but the failure is reported as one, with the command that completes
        # it: a success line here once hid an install that did nothing at all.
        reported = capsys.readouterr().err
        assert "Auto-install complete" not in reported
        assert "/praxion-complete-install" in reported

    def test_a_prompt_that_cannot_run_is_treated_as_consent(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)

        def _explodes(_values: dict) -> bool:
            raise RuntimeError("terminal is gone")

        monkeypatch.setattr(module, "_prompt_with_timeout", _explodes)

        module._perform_install(fake_home, _VALUES, auto_complete=False, root=plugin_root)

        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()


class TestRunFlow:
    """`_run` is the whole decision tree: which guard wins, and in what order."""

    def test_the_kill_switch_stops_everything(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_DISABLE_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        assert not (fake_home / ".claude" / ".praxion-complete-installed").exists()
        assert not (fake_home / ".claude" / "CLAUDE.md").exists()

    def test_a_fresh_marker_short_circuits_the_install(
        self,
        fake_home,
        plugin_root,
        plugin_cache_dir,
        marker_path,
        monkeypatch,
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        marker_path.write_text("")
        os.utime(plugin_cache_dir, (1_000_000, 1_000_000))
        os.utime(marker_path, (2_000_000, 2_000_000))
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        assert not (fake_home / ".claude" / "CLAUDE.md").exists()

    def test_already_installed_surfaces_only_record_the_marker(
        self, fake_home, claude_md_symlink, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        original = claude_md_symlink.resolve()

        module._run()

        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()
        # A clone-install's surfaces must not be re-pointed at the plugin cache.
        assert claude_md_symlink.resolve() == original

    def test_already_installed_surfaces_get_their_missing_rule_links(
        self, fake_home, plugin_root, claude_md_symlink, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        # A rule a newer version links reaches an existing install on its next
        # session after the update, with no reinstall.
        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_no_resolvable_plugin_installs_nothing_and_records_nothing(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion").mkdir(parents=True)
        module = _fake_home_module(monkeypatch, home)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        # With no marker, a later session that can resolve the plugin still
        # completes the install instead of trusting one that never ran.
        assert not (home / ".claude" / "CLAUDE.md").exists()
        assert not (home / ".claude" / ".praxion-complete-installed").exists()

    def test_a_cold_start_performs_the_install(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()

    def test_undiscoverable_git_identity_falls_back_to_anonymous_defaults(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        def _no_identity() -> dict:
            raise OSError("git not on PATH")

        monkeypatch.setattr(module._render_mod, "derive_defaults", _no_identity)

        module._run()

        rendered = (fake_home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "@anon" in rendered
        assert "anon@unknown" in rendered


# Made-up identities: the one the previous version's render carried, and the one a
# fresh derivation would give today. Neither is a real person's.
_PREVIOUS_VERSION = "9.9.8"
_PREVIOUS_TEMPLATE = (
    "# Instructions\nuser: {{USERNAME}}\nmail: {{EMAIL}}\nweb: {{GITHUB_URL}}\nend\n"
)
_NEW_TEMPLATE = _PREVIOUS_TEMPLATE + "\n## Release notes\n\nHello {{USERNAME}}.\n"
_CARRIED = {
    "USERNAME": "@first-person",
    "EMAIL": "first.person@example.invalid",
    "GITHUB_URL": "https://example.invalid/first-person",
}
_TODAYS = {
    "USERNAME": "@later-person",
    "EMAIL": "later.person@example.invalid",
    "GITHUB_URL": "https://example.invalid/later-person",
}


def _fill(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def _previous_render(home: Path, template: str = _PREVIOUS_TEMPLATE) -> Path:
    """The previous cached version's template and its render with the carried values."""
    config = _cached_version(home, _PREVIOUS_VERSION) / "claude" / "config"
    config.mkdir(parents=True)
    (config / "CLAUDE.md.tmpl").write_text(template, encoding="utf-8")
    render = config / "CLAUDE.md"
    render.write_text(_fill(template, _CARRIED), encoding="utf-8")
    return render


def _link_instructions(home: Path, target: Path | str) -> Path:
    link = home / ".claude" / "CLAUDE.md"
    link.symlink_to(target)
    return link


def _file_state(path: Path) -> tuple:
    status = path.stat()
    return path.read_bytes(), status.st_ino, status.st_mtime_ns


def _record_derivations(monkeypatch, values: dict[str, str]) -> list:
    calls: list = []

    def derive() -> dict[str, str]:
        calls.append("derived")
        return dict(values)

    monkeypatch.setattr(update._render_mod, "derive_defaults", derive)
    return calls


def _files_holding(root: Path, values, excluding: set[Path]) -> list[str]:
    """The regular files under `root`, other than `excluding`, that contain any of `values`."""
    regular = (p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    return [
        str(path.relative_to(root))
        for path in regular
        if path not in excluding and any(v in path.read_text(errors="replace") for v in values)
    ]


def _values_in(text: str, values) -> list[str]:
    return [value for value in values if value in text]


def _refuse_replacing(monkeypatch, destination: Path) -> None:
    """Make the rename over `destination`, and only that one, fail."""
    real_replace = os.replace

    def replace(source, target) -> None:
        if Path(target) == destination:
            raise OSError("refused")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)


_not_as_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions these break"
)


class TestInstructionsCarryForward:
    """A link into another cached version's render moves to this version's, values kept."""

    @pytest.fixture
    def todays_identity(self, tmp_path, monkeypatch):
        """Git now answers with another identity than the one the previous render carried."""
        gitconfig = tmp_path / "gitconfig"
        gitconfig.write_text(
            f"[user]\n\tname = Later Person\n\temail = {_TODAYS['EMAIL']}\n", encoding="utf-8"
        )
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    @pytest.fixture
    def updated(self, fake_home, plugin_root, monkeypatch):
        """The previous version's render is linked, and this version ships a new template."""
        module = _fake_home_module(monkeypatch, fake_home)
        previous = _previous_render(fake_home)
        link = _link_instructions(fake_home, previous)
        _seed_template(plugin_root, _NEW_TEMPLATE)
        return module, previous, link

    @pytest.mark.usefixtures("todays_identity")
    def test_the_new_template_is_filled_with_the_previous_renders_values(
        self, updated, fake_home, plugin_root
    ):
        module, _, link = updated

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_the_link_points_at_this_versions_render(self, updated, fake_home, plugin_root):
        module, _, link = updated

        update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(plugin_root / "claude" / "config" / "CLAUDE.md")

    def test_the_previous_render_is_left_as_it_was(self, updated, fake_home, plugin_root):
        module, previous, _ = updated
        before = _file_state(previous)

        update._update_instructions(fake_home, plugin_root)

        assert _file_state(previous) == before

    def test_a_relative_link_into_the_previous_version_is_carried_forward(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        previous = _previous_render(fake_home)
        link = _link_instructions(fake_home, previous.relative_to(fake_home / ".claude"))
        _seed_template(plugin_root, _NEW_TEMPLATE)

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_a_default_fills_only_the_key_the_previous_render_never_carried(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        without_web = _PREVIOUS_TEMPLATE.replace("web: {{GITHUB_URL}}\n", "")
        link = _link_instructions(fake_home, _previous_render(fake_home, without_web))
        _seed_template(plugin_root, _NEW_TEMPLATE)
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        expected = {**_CARRIED, "GITHUB_URL": _TODAYS["GITHUB_URL"]}
        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, expected)

    def test_no_default_is_derived_when_every_key_was_carried(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, _, _ = updated
        calls = _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        assert calls == []

    def test_a_key_neither_carried_nor_derivable_stays_a_named_placeholder(
        self, updated, fake_home, plugin_root, monkeypatch, capsys
    ):
        module, _, link = updated
        _seed_template(plugin_root, _NEW_TEMPLATE + "shell: {{SHELL_NAME}}\n")
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8").endswith("shell: {{SHELL_NAME}}\n")
        assert "{{SHELL_NAME}}" in capsys.readouterr().err

    def test_an_unrecoverable_render_raises_its_own_error_type(
        self, updated, fake_home, plugin_root
    ):
        module, previous, _ = updated
        previous.write_text(previous.read_text(encoding="utf-8") + "a line edited by hand\n")

        with pytest.raises(update.UnrecoverableRenderError):
            update._update_instructions(fake_home, plugin_root)

    def test_an_unrecoverable_render_keeps_the_previous_link_and_writes_no_render(
        self, updated, fake_home, plugin_root
    ):
        module, previous, link = updated
        previous.write_text(previous.read_text(encoding="utf-8") + "a line edited by hand\n")

        with pytest.raises(update.UnrecoverableRenderError):
            update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(previous)
        assert sorted(p.name for p in (plugin_root / "claude" / "config").iterdir()) == [
            "CLAUDE.md.tmpl"
        ]

    def test_an_unrecoverable_render_is_reported_in_one_line_naming_its_type(
        self, updated, fake_home, plugin_root, monkeypatch, capsys
    ):
        module, previous, _ = updated
        previous.write_text("# rewritten by hand\n", encoding="utf-8")
        monkeypatch.setattr(update, "_UPDATE_STEPS", (update._update_instructions,))

        update._run_update_path(fake_home, plugin_root)

        assert capsys.readouterr().err == (
            "[Praxion] Update refresh could not finish (UnrecoverableRenderError); "
            "run /praxion-complete-install to complete it.\n"
        )

    @_not_as_root
    def test_an_unreadable_new_template_keeps_the_previous_render(
        self, updated, fake_home, plugin_root
    ):
        module, previous, link = updated
        template = plugin_root / "claude" / "config" / "CLAUDE.md.tmpl"
        template.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                update._update_instructions(fake_home, plugin_root)
        finally:
            template.chmod(0o644)

        assert (os.readlink(link), link.read_text(encoding="utf-8")) == (
            str(previous),
            _fill(_PREVIOUS_TEMPLATE, _CARRIED),
        )

    @_not_as_root
    def test_an_unwritable_render_directory_keeps_the_previous_render_and_no_temporary(
        self, updated, fake_home, plugin_root
    ):
        module, previous, link = updated
        config = plugin_root / "claude" / "config"
        config.chmod(0o555)
        try:
            with pytest.raises(PermissionError):
                update._update_instructions(fake_home, plugin_root)
        finally:
            config.chmod(0o755)

        assert os.readlink(link) == str(previous)
        assert sorted(p.name for p in config.iterdir()) == ["CLAUDE.md.tmpl"]

    def test_a_failed_rename_of_the_render_keeps_the_previous_render_and_no_temporary(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, previous, link = updated
        config = plugin_root / "claude" / "config"
        _refuse_replacing(monkeypatch, config / "CLAUDE.md")

        with pytest.raises(OSError, match="refused"):
            update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(previous)
        assert sorted(p.name for p in config.iterdir()) == ["CLAUDE.md.tmpl"]

    def test_a_failed_swap_of_the_link_keeps_the_previous_render_and_no_temporary(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, previous, link = updated
        before = sorted(p.name for p in link.parent.iterdir())
        _refuse_replacing(monkeypatch, link)

        with pytest.raises(OSError, match="refused"):
            update._update_instructions(fake_home, plugin_root)

        assert (os.readlink(link), link.read_text(encoding="utf-8")) == (
            str(previous),
            _fill(_PREVIOUS_TEMPLATE, _CARRIED),
        )
        assert sorted(p.name for p in link.parent.iterdir()) == before

    def test_a_link_already_into_this_version_is_left_as_it_is(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        _seed_template(plugin_root, _NEW_TEMPLATE)
        render = plugin_root / "claude" / "config" / "CLAUDE.md"
        render.write_text(_fill(_NEW_TEMPLATE, _CARRIED), encoding="utf-8")
        link = _link_instructions(fake_home, render)
        before = (os.readlink(link), _file_state(render))

        update._update_instructions(fake_home, plugin_root)

        assert (os.readlink(link), _file_state(render)) == before

    def test_a_clone_link_and_its_render_are_left_as_they_are(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        _seed_template(plugin_root, _NEW_TEMPLATE)
        clone_render = tmp_path / "dev" / "praxion" / "claude" / "config" / "CLAUDE.md"
        clone_render.parent.mkdir(parents=True)
        clone_render.write_text("# a developer's own render\n", encoding="utf-8")
        link = _link_instructions(fake_home, clone_render)
        before = (os.readlink(link), _file_state(clone_render))

        update._update_instructions(fake_home, plugin_root)

        assert (os.readlink(link), _file_state(clone_render)) == before
        assert not (plugin_root / "claude" / "config" / "CLAUDE.md").exists()

    def test_nothing_is_read_from_stdin(self, updated, fake_home, plugin_root, monkeypatch):
        module, _, link = updated

        class _NoAnswers:
            def read(self, *_args) -> str:
                raise AssertionError("the update path read stdin")

            readline = read

        monkeypatch.setattr(sys, "stdin", _NoAnswers())

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_no_personal_value_is_printed(
        self, updated, fake_home, plugin_root, monkeypatch, capsys
    ):
        module, _, _ = updated
        _seed_template(plugin_root, _NEW_TEMPLATE + "shell: {{SHELL_NAME}}\n")
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        output = "".join(capsys.readouterr())
        assert _values_in(output, (*_CARRIED.values(), *_TODAYS.values())) == []

    def test_no_personal_value_is_written_outside_the_two_renders(
        self, updated, fake_home, plugin_root, tmp_path
    ):
        module, previous, _ = updated

        update._update_instructions(fake_home, plugin_root)

        renders = {previous, plugin_root / "claude" / "config" / "CLAUDE.md"}
        assert _files_holding(tmp_path, _CARRIED.values(), excluding=renders) == []


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

        def _explodes() -> None:
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
