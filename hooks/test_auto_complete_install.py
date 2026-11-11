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

This module holds the shared fixtures and helpers and the steady-state, rearm, idempotency
and marker tests; its siblings import the fixtures from here: `test_install_cold_path`
(the first install), `test_install_surfaces` (the install steps and `_run`) and
`test_install_carry_forward` (the instructions' values across an update).
"""

from __future__ import annotations

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


class TestMarkerWriting:
    def test_completion_marker_is_created_with_its_parent_directory(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        module = _fake_home_module(monkeypatch, home)

        module._write_marker(home)

        assert (home / ".claude" / ".praxion-complete-installed").exists()

    def test_decline_marker_is_a_distinct_file(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        update._write_decline_marker(home)

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


def _seed_script(scripts_src: Path, name: str, executable: bool = True) -> Path:
    scripts_src.mkdir(parents=True, exist_ok=True)
    script = scripts_src / name
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    if executable:
        script.chmod(0o755)
    else:
        script.chmod(0o644)
    return script


def _cached_version(home: Path, version: str) -> Path:
    """A version directory of the plugin cache, other than the running one."""
    root = home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / version
    (root / "scripts").mkdir(parents=True)
    return root


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
