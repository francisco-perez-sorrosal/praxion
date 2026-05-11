"""
Behavioral tests for scripts/praxion-dashboard bash ctl.

Tests invoke the ctl via ``subprocess.run`` to verify lifecycle subcommand
behavior: install/build idempotency, start/status/stop lifecycle behavior,
unknown subcommand handling, uninstall with --yes flag, and help/usage output.

All tests that modify filesystem state (install, uninstall) monkeypatch HOME
to a tmp_path so the real ``~/.praxion-dashboard/`` is never touched.

Concurrent BDD/TDD state
-------------------------
The implementer and test-engineer run concurrently in this paired step.
``scripts/praxion-dashboard`` does not exist yet.  Tests are expected to fail
RED at collection time (FileNotFoundError or ENOENT from subprocess) until 14a
lands the ctl script.

REGISTERED OBJECTION — concurrent-mode GREEN trigger
------------------------------------------------------
If all tests pass GREEN on first run, the implementer landed
``scripts/praxion-dashboard`` before these tests were written.  Per
``pattern_concurrent_bdd_green_on_first_run``: not a defect when the
behavioral contract is correctly encoded.  Contract is: help exits 0,
status without install exits non-zero, install is idempotent, uninstall --yes
removes state without prompting, unknown subcommands exit non-zero.

Slow-test marking
-----------------
Tests use a mock ``pnpm`` that creates a minimal built Next.js runtime inside
the isolated dashboard home, so the suite stays fast while still verifying the
launcher contract.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Final

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORKTREE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CTL: Final[Path] = _WORKTREE_ROOT / "scripts" / "praxion-dashboard"


def _run_ctl(
    *args: str,
    home: Path | None = None,
    env_overrides: dict[str, str] | None = None,
    capture_output: bool = True,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Run praxion-dashboard ctl with optional HOME override."""
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    env.setdefault("PRAXION_DASHBOARD_TEST_MODE", "1")
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        [str(CTL), *args],
        capture_output=capture_output,
        env=env,
        check=check,
        text=True,
        **kwargs,
    )


def _make_mock_pnpm(tmp_path: Path) -> Path:
    """Write a mock pnpm that materializes a minimal built Next.js runtime."""
    bin_dir = tmp_path / "mock-bin"
    bin_dir.mkdir()

    mock_pnpm = bin_dir / "pnpm"
    mock_pnpm.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "mkdir -p node_modules/.bin .next\n"
        "cat > node_modules/.bin/next <<'EOF'\n"
        "#!/bin/sh\n"
        "set -eu\n"
        "command_name=${1:-}\n"
        "shift || true\n"
        "case \"$command_name\" in\n"
        "  build)\n"
        "    mkdir -p .next\n"
        "    printf 'test-build\\n' > .next/BUILD_ID\n"
        "    exit 0\n"
        "    ;;\n"
        "  start)\n"
        "    trap 'exit 0' TERM INT\n"
        "    while :; do\n"
        "      sleep 1\n"
        "    done\n"
        "    ;;\n"
        "  *)\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n"
        "EOF\n"
        "chmod +x node_modules/.bin/next\n"
        "exit 0\n"
    )
    mock_pnpm.chmod(mock_pnpm.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return bin_dir


# ---------------------------------------------------------------------------
# Help / usage tests (no filesystem side-effects)
# ---------------------------------------------------------------------------


def test_help_flag_exits_zero() -> None:
    """praxion-dashboard --help exits with code 0."""
    result = _run_ctl("--help")
    assert result.returncode == 0, (
        f"--help should exit 0, got {result.returncode}. stderr: {result.stderr}"
    )


def test_help_output_mentions_subcommands() -> None:
    """praxion-dashboard --help mentions the lifecycle subcommands."""
    result = _run_ctl("--help")
    combined = (result.stdout + result.stderr).lower()
    for subcommand in ("install", "start", "stop", "status"):
        assert subcommand in combined, (
            f"--help output does not mention '{subcommand}'. "
            f"Got:\n{result.stdout}\n{result.stderr}"
        )


def test_unknown_subcommand_exits_nonzero() -> None:
    """An unrecognised subcommand exits with a non-zero code."""
    result = _run_ctl("definitely-not-a-real-subcommand")
    assert result.returncode != 0, "Unknown subcommand should exit non-zero"


# ---------------------------------------------------------------------------
# Status test (no install required)
# ---------------------------------------------------------------------------


def test_status_exits_nonzero_when_not_installed(tmp_path: Path) -> None:
    """praxion-dashboard status exits non-zero when nothing is installed."""
    result = _run_ctl("status", home=tmp_path)
    assert result.returncode != 0, (
        "status should exit non-zero when the dashboard is not installed. "
        f"Got returncode={result.returncode}. stdout: {result.stdout}"
    )


def test_status_reports_distinct_ports_for_distinct_project_roots(tmp_path: Path) -> None:
    """Different project roots keep the deterministic per-root port contract."""
    first_root = tmp_path / "project-alpha"
    second_root = tmp_path / "project-beta"
    first_root.mkdir()
    second_root.mkdir()

    first = _run_ctl("status", str(first_root), home=tmp_path)
    second = _run_ctl("status", str(second_root), home=tmp_path)

    def extract_port(output: str) -> str:
        for line in output.splitlines():
            if line.strip().startswith("Port:"):
                return line.split(":", maxsplit=1)[1].strip()
        raise AssertionError(f"Port line not found in output:\n{output}")

    assert extract_port(first.stdout) != extract_port(second.stdout)


# ---------------------------------------------------------------------------
# Install idempotency tests (uses mock pnpm to avoid real downloads)
# ---------------------------------------------------------------------------


def test_install_creates_venv_directory(tmp_path: Path) -> None:
    """praxion-dashboard install creates the isolated dashboard app home."""
    mock_bin = _make_mock_pnpm(tmp_path)
    env_path = f"{mock_bin}:{os.environ.get('PATH', '')}"

    result = _run_ctl(
        "install",
        home=tmp_path,
        env_overrides={"PATH": env_path}
    )
    app_dir = tmp_path / ".praxion-dashboard" / "app"
    assert app_dir.exists(), (
        f"install should create ~/.praxion-dashboard/app/. "
        f"returncode={result.returncode}, stderr={result.stderr}"
    )
    assert (app_dir / "node_modules" / ".bin" / "next").exists()
    assert (app_dir / ".next" / "BUILD_ID").exists()


def test_install_is_idempotent(tmp_path: Path) -> None:
    """Calling praxion-dashboard install twice succeeds both times."""
    mock_bin = _make_mock_pnpm(tmp_path)
    env_path = f"{mock_bin}:{os.environ.get('PATH', '')}"

    first = _run_ctl("install", home=tmp_path, env_overrides={"PATH": env_path})
    second = _run_ctl("install", home=tmp_path, env_overrides={"PATH": env_path})

    assert first.returncode == 0, f"First install failed: {first.stderr}"
    assert second.returncode == 0, (
        f"Second install (idempotent) failed: {second.stderr}"
    )


# ---------------------------------------------------------------------------
# Uninstall test
# ---------------------------------------------------------------------------


def test_uninstall_with_yes_flag_does_not_prompt(tmp_path: Path) -> None:
    """praxion-dashboard uninstall --yes removes state without interactive prompt."""
    mock_bin = _make_mock_pnpm(tmp_path)
    env_path = f"{mock_bin}:{os.environ.get('PATH', '')}"

    _run_ctl("install", home=tmp_path, env_overrides={"PATH": env_path})

    result = _run_ctl(
        "uninstall",
        "--yes",
        home=tmp_path,
        env_overrides={"PATH": env_path},
        input="",  # Simulate empty stdin in case --yes is ignored
        timeout=10,
    )

    assert result.returncode == 0, (
        f"uninstall --yes should exit 0. returncode={result.returncode}, "
        f"stderr={result.stderr}"
    )
    dashboard_dir = tmp_path / ".praxion-dashboard"
    assert not dashboard_dir.exists(), (
        "uninstall --yes should remove ~/.praxion-dashboard/"
    )


def test_start_status_stop_roundtrip(tmp_path: Path) -> None:
    """start/status/stop work against the isolated app home and deterministic port."""
    mock_bin = _make_mock_pnpm(tmp_path)
    env_path = f"{mock_bin}:{os.environ.get('PATH', '')}"
    project_root = tmp_path / "project-root"
    project_root.mkdir()

    install = _run_ctl("install", home=tmp_path, env_overrides={"PATH": env_path})
    assert install.returncode == 0, f"Install failed: {install.stderr}"

    start = _run_ctl(
        "start",
        str(project_root),
        home=tmp_path,
        env_overrides={"PATH": env_path},
    )
    assert start.returncode == 0, f"Start failed: {start.stderr}"

    status = _run_ctl(
        "status",
        str(project_root),
        home=tmp_path,
        env_overrides={"PATH": env_path},
    )
    assert status.returncode == 0, f"Status should report running: {status.stderr}"
    assert "Running" in status.stdout

    stop = _run_ctl(
        "stop",
        str(project_root),
        home=tmp_path,
        env_overrides={"PATH": env_path},
    )
    assert stop.returncode == 0, f"Stop failed: {stop.stderr}"

    final_status = _run_ctl(
        "status",
        str(project_root),
        home=tmp_path,
        env_overrides={"PATH": env_path},
    )
    assert final_status.returncode != 0, "Status should be non-zero after stop"
    assert not (project_root / "node_modules").exists()
