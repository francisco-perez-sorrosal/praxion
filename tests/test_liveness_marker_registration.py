"""The `liveness` pytest marker: registered, and deselected from every default run.

Whole-suite gate-liveness scenarios rebuild a copy of the repository and run
the suite inside it, so they cost minutes. They must run only in the scheduled
liveness job (`-m liveness`) -- never in the default suite, and never in the
weekly `-m large` health job. The repository's own pytest configuration is the
contract, so each case runs a real pytest against it with `-c <pyproject>` over
a throwaway probe file whose tests carry the markers under test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

PROBE_TEXT = """\
import pytest


@pytest.mark.liveness
def test_probe_liveness():
    pass


@pytest.mark.large
def test_probe_large():
    pass


def test_probe_plain():
    pass
"""


def _pytest(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the repository's pytest configuration over a probe file in `tmp_path`."""
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE_TEXT, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(PYPROJECT),
            "--rootdir",
            str(tmp_path),
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-n",
            "0",
            str(probe),
            *args,
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )


def _collected(tmp_path: Path, *args: str) -> set[str]:
    result = _pytest(tmp_path, "--collect-only", "-q", *args)
    assert result.returncode in (0, 5), result.stdout + result.stderr
    return {line.split("::")[-1] for line in result.stdout.splitlines() if "::" in line}


def test_liveness_marker_is_registered_and_deselected_by_default(tmp_path: Path) -> None:
    markers = _pytest(tmp_path, "--markers").stdout
    assert "@pytest.mark.liveness" in markers

    assert _collected(tmp_path) == {"test_probe_plain"}
    assert _collected(tmp_path, "-m", "liveness") == {"test_probe_liveness"}


def test_dash_m_large_still_selects_large_tests(tmp_path: Path) -> None:
    assert _collected(tmp_path, "-m", "large") == {"test_probe_large"}
