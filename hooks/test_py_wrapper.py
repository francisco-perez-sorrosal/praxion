"""Tests for hooks/_py.sh — the cached non-shim interpreter wrapper (P1.11).

Cites: rules/swe/gate-liveness.md — every CODE gate ships tests proving both
the pass and skip paths. `_py.sh` resolves a real python3 interpreter once per
machine (cached to a per-uid tmp file) and execs it with the caller's argv,
stdin, and exit code forwarded unmodified. These tests prove:
  - argv, stdin, and exit code all forward correctly
  - the resolved interpreter is cached to disk
  - PRAXION_PYTHON overrides resolution entirely
  - a stale (deleted) cached path triggers re-resolution
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
WRAPPER = HOOKS_DIR / "_py.sh"


def _isolated_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    """A real env with TMPDIR redirected so the cache file never touches the
    real machine-wide cache used by actual hook invocations."""
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp_path)
    env.pop("PRAXION_PYTHON", None)
    env.update(overrides)
    return env


def _write_spy(tmp_path: Path) -> Path:
    """A script that echoes argv, drains+echoes stdin, then exits with a
    code taken from its own last argv entry (so tests can assert forwarding)."""
    spy = tmp_path / "spy.py"
    spy.write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print('ARGV:' + ','.join(sys.argv[1:]))\n"
        "print('STDIN:' + data.strip())\n"
        "sys.exit(int(sys.argv[-1]))\n",
        encoding="utf-8",
    )
    return spy


def test_wrapper_is_executable() -> None:
    assert WRAPPER.exists(), f"missing {WRAPPER}"
    assert os.access(WRAPPER, os.X_OK), f"{WRAPPER} is not executable (chmod +x required)"


def test_forwards_argv_stdin_and_exit_code(tmp_path: Path) -> None:
    spy = _write_spy(tmp_path)
    env = _isolated_env(tmp_path)
    result = subprocess.run(
        [str(WRAPPER), str(spy), "hello", "world", "0"],
        input="payload-body",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "ARGV:hello,world,0" in result.stdout
    assert "STDIN:payload-body" in result.stdout


def test_forwards_nonzero_exit_code(tmp_path: Path) -> None:
    spy = _write_spy(tmp_path)
    env = _isolated_env(tmp_path)
    result = subprocess.run(
        [str(WRAPPER), str(spy), "x", "7"],
        input="",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 7


def test_resolves_and_caches_interpreter(tmp_path: Path) -> None:
    spy = _write_spy(tmp_path)
    env = _isolated_env(tmp_path)
    subprocess.run(
        [str(WRAPPER), str(spy), "x", "0"],
        input="",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    cache_file = tmp_path / f"praxion-py-{os.getuid()}"
    assert cache_file.exists(), "wrapper did not write the interpreter cache file"
    cached_path = cache_file.read_text(encoding="utf-8").strip()
    assert cached_path, "cache file is empty"
    assert os.path.isabs(cached_path)
    assert os.access(cached_path, os.X_OK)


def test_praxion_python_override_bypasses_resolution(tmp_path: Path) -> None:
    spy = _write_spy(tmp_path)
    fake_python = tmp_path / "fake_python3"
    fake_python.write_text("#!/bin/sh\necho OVERRIDE_USED\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)

    env = _isolated_env(tmp_path, PRAXION_PYTHON=str(fake_python))
    result = subprocess.run(
        [str(WRAPPER), str(spy), "x", "0"],
        input="",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert "OVERRIDE_USED" in result.stdout
    cache_file = tmp_path / f"praxion-py-{os.getuid()}"
    assert not cache_file.exists(), "override must skip resolution/caching entirely"


def test_re_resolves_when_cached_path_is_stale(tmp_path: Path) -> None:
    spy = _write_spy(tmp_path)
    env = _isolated_env(tmp_path)
    cache_file = tmp_path / f"praxion-py-{os.getuid()}"
    cache_file.write_text("/no/such/interpreter/anywhere\n", encoding="utf-8")

    result = subprocess.run(
        [str(WRAPPER), str(spy), "x", "0"],
        input="",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    refreshed = cache_file.read_text(encoding="utf-8").strip()
    assert refreshed != "/no/such/interpreter/anywhere"
    assert os.access(refreshed, os.X_OK)
