"""Tests for measure_selection_size: the pure summary core and one end-to-end run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure_selection_size as mss  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "measure_selection_size.py"
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _narrow(*tests: tuple[str, str]) -> mss.PocketRun:
    return mss.PocketRun(widened=False, tests=tests)


_WIDE = mss.PocketRun(widened=True, tests=())


# --- pocket_run ------------------------------------------------------------------


def test_a_full_selection_reads_as_widened():
    output = {"pockets": [{"root": ".", "selection": "full"}]}
    assert mss.pocket_run(output, ".") == _WIDE


def test_a_narrow_selection_lists_each_test_file_once_with_its_first_via():
    output = {
        "pockets": [
            {
                "root": ".",
                "selection": "tests",
                "tests": [
                    {"path": "tests/test_a.py", "via": "import"},
                    {"path": "tests/test_a.py", "via": "declared"},
                    {"path": "tests/test_b.py", "via": "path-literal"},
                ],
            }
        ]
    }
    run = mss.pocket_run(output, ".")
    assert run == _narrow(("tests/test_a.py", "import"), ("tests/test_b.py", "path-literal"))


def test_a_change_set_outside_the_pocket_selects_nothing_there():
    output = {"pockets": [{"root": "web", "selection": "full"}]}
    assert mss.pocket_run(output, ".") == _narrow()


# --- summarize -------------------------------------------------------------------


def test_widened_runs_count_as_the_whole_corpus_only_in_the_all_figures():
    runs = [_narrow(("t1", "import")), _narrow(("t1", "import"), ("t2", "declared")), _WIDE]
    summary = mss.summarize(runs, corpus=10)
    assert (summary.widened, summary.narrow_median, summary.all_median) == (1, 1.5, 2.0)


def test_via_share_is_measured_over_narrow_selections_only():
    runs = [_narrow(("t1", "import"), ("t2", "path-literal"), ("t3", "path-literal")), _WIDE]
    summary = mss.summarize(runs, corpus=10)
    assert summary.via_share == pytest.approx({"path-literal": 2 / 3, "import": 1 / 3})


def test_a_single_narrow_run_is_its_own_p90():
    summary = mss.summarize([_narrow(("t1", "import"), ("t2", "import"))], corpus=4)
    assert (summary.narrow_p90, summary.as_dict()["narrow"]["p90_pct"]) == (2.0, 50.0)


def test_all_runs_widened_reports_zero_narrow_figures():
    summary = mss.summarize([_WIDE, _WIDE], corpus=5)
    assert (summary.narrow_median, summary.all_median, summary.via_share) == (0.0, 5.0, {})


def test_no_change_sets_is_refused():
    with pytest.raises(mss.MeasureError):
        mss.summarize([], corpus=5)


# --- end to end ------------------------------------------------------------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=_GIT_ENV)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    (root / "pkg").mkdir()
    (root / "tests").mkdir()
    (root / "pkg" / "core.py").write_text("VALUE = 1\n")
    (root / "tests" / "test_core.py").write_text(
        "from pkg import core\n\n\ndef test_value():\n    assert core.VALUE\n"
    )
    (root / "tests" / "test_other.py").write_text("def test_other():\n    assert True\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    (root / "pkg" / "core.py").write_text("VALUE = 2\n")
    _git(root, "commit", "-qam", "change core")
    return root


def test_the_cli_measures_the_window_and_compares_against_a_ref(scratch: Path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(scratch),
            "--commits",
            "1",
            "--compare-ref",
            "HEAD",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    current = report["results"]["current"]
    assert (current["corpus"], current["runs"], current["widened"]) == (2, 1, 0)
    assert current["narrow"]["median"] == 1
    # The compared resolver is this checkout's HEAD; it measures the same tree and window.
    assert (report["results"]["HEAD"]["corpus"], report["results"]["HEAD"]["runs"]) == (2, 1)


def test_an_unknown_pocket_exits_2(scratch: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(scratch), "--pocket", "nope"],
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )
    assert result.returncode == 2
    assert "no pocket rooted at 'nope'" in result.stderr
