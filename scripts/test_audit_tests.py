"""Tests for `audit_tests.py` -- the selection auditor.

The failure mode this closes: a real regression escapes the derived
selection silently, because nothing ever checks whether a full-suite failure
*would* have been caught by the narrow run. Each classification
(`real`/`flaky`/`unclassified`) and each selection outcome
(`selected`/`widened`/`missed`/`unattributable`) gets its own test, plus the
canary that matters most: a `missed` failure must exit non-zero and name the
changed paths as the suggested edge -- a silent `missed` would be the exact
gap this tool exists to close.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import audit_tests as at  # noqa: E402

# -- Fixtures and helpers -------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def base_repo(tmp_path: Path) -> Path:
    """A minimal single-pocket Python repo: `pkg/foo.py` and its layout-edge test."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["pkg"]\naddopts = "-n auto"\n', encoding="utf-8"
    )
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "foo.py").write_text("value = 1\n", encoding="utf-8")
    (pkg / "test_foo.py").write_text(
        "import foo\n\n\ndef test_value():\n    assert foo.value == 1\n", encoding="utf-8"
    )
    (pkg / "bar.py").write_text("value = 2\n", encoding="utf-8")
    (pkg / "test_bar.py").write_text(
        "import bar\n\n\ndef test_value():\n    assert bar.value == 2\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _junit(tmp_path: Path, name: str, cases: str) -> Path:
    path = tmp_path / name
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n<testsuite name="pytest">\n'
        f"{cases}\n</testsuite>\n</testsuites>\n",
        encoding="utf-8",
    )
    return path


def _failing_case(file: str, name: str = "test_value", seconds: float = 0.1) -> str:
    return f'<testcase classname="x" name="{name}" file="{file}" time="{seconds}"><failure>boom</failure></testcase>'


def _passing_case(file: str, name: str = "test_value", seconds: float = 0.1) -> str:
    return f'<testcase classname="x" name="{name}" file="{file}" time="{seconds}" />'


def _run(capsys: pytest.CaptureFixture, repo: Path, *args: str) -> tuple[int, dict]:
    exit_code = at.main(["--repo-root", str(repo), "--json", *args])
    return exit_code, json.loads(capsys.readouterr().out)


# -- JUnit parsing ----------------------------------------------------------


def test_failing_cases_reads_file_and_classname_attributes(tmp_path: Path) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    failed = at.failing_cases(junit)
    assert list(failed) == ["pkg/test_foo.py::test_value"]
    assert failed["pkg/test_foo.py::test_value"].file == "pkg/test_foo.py"


def test_failing_cases_excludes_passing_testcases(tmp_path: Path) -> None:
    junit = _junit(tmp_path, "run.xml", _passing_case("pkg/test_foo.py"))
    assert at.failing_cases(junit) == {}


def test_failing_cases_falls_back_to_classname_when_file_is_absent(tmp_path: Path) -> None:
    junit = tmp_path / "run.xml"
    junit.write_text(
        '<?xml version="1.0"?><testsuites><testsuite>'
        '<testcase classname="pkg.test_foo" name="test_value" time="0.1">'
        "<failure>boom</failure></testcase></testsuite></testsuites>",
        encoding="utf-8",
    )
    failed = at.failing_cases(junit)
    assert list(failed) == ["pkg/test_foo.py::test_value"]


def test_a_malformed_junit_file_raises_audit_error(tmp_path: Path) -> None:
    junit = tmp_path / "run.xml"
    junit.write_text("not xml", encoding="utf-8")
    with pytest.raises(at.AuditError):
        at.failing_cases(junit)


# -- Classification -----------------------------------------------------------


def test_no_rerun_classifies_as_unclassified(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    _, payload = _run(capsys, base_repo, "--junit", str(junit))
    assert payload["failures"][0]["classification"] == "unclassified"


def test_a_failure_that_passes_on_rerun_is_flaky(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    rerun = _junit(tmp_path, "rerun.xml", _passing_case("pkg/test_foo.py"))
    _, payload = _run(capsys, base_repo, "--junit", str(junit), "--rerun", str(rerun))
    failure = payload["failures"][0]
    assert failure["classification"] == "flaky"
    assert failure["selection"] == "n/a"
    assert failure["suggested_edge"] is None


def test_canary_a_flaky_failure_exits_nonzero(tmp_path: Path, base_repo: Path, capsys) -> None:
    """Flakiness must be loud too: a passing rerun still reddens the audit's exit code."""
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    rerun = _junit(tmp_path, "rerun.xml", _passing_case("pkg/test_foo.py"))
    exit_code, payload = _run(capsys, base_repo, "--junit", str(junit), "--rerun", str(rerun))
    assert exit_code == at.EXIT_FINDINGS
    assert payload["summary"]["flaky"] == 1


def test_a_failure_that_fails_again_on_rerun_is_real(
    tmp_path: Path, base_repo: Path, capsys
) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    rerun = _junit(tmp_path, "rerun.xml", _failing_case("pkg/test_foo.py"))
    _, payload = _run(capsys, base_repo, "--junit", str(junit), "--rerun", str(rerun))
    assert payload["failures"][0]["classification"] == "real"


# -- Selection ------------------------------------------------------------------


def test_canary_a_missed_failure_exits_nonzero_with_a_suggested_edge(
    tmp_path: Path, base_repo: Path, capsys
) -> None:
    """The failure mode this tool exists to catch: a real gap must be loud, not silent."""
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_bar.py"))
    exit_code, payload = _run(capsys, base_repo, "--junit", str(junit), "--changed", "pkg/foo.py")
    failure = payload["failures"][0]
    assert failure["selection"] == "missed"
    assert failure["suggested_edge"] == {"paths": ["pkg/foo.py"], "tests": ["pkg/test_bar.py"]}
    assert payload["summary"]["missed"] == 1
    assert exit_code == at.EXIT_FINDINGS


def test_a_failure_the_graph_reaches_is_selected(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    exit_code, payload = _run(capsys, base_repo, "--junit", str(junit), "--changed", "pkg/foo.py")
    assert payload["failures"][0]["selection"] == "selected"
    assert payload["failures"][0]["suggested_edge"] is None
    assert exit_code == at.EXIT_OK


def test_a_resolver_source_change_widens_and_reports_widened(
    tmp_path: Path, base_repo: Path, capsys
) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_bar.py"))
    _, payload = _run(
        capsys, base_repo, "--junit", str(junit), "--changed", "tests/declared-deps.toml"
    )
    assert payload["failures"][0]["selection"] == "widened"
    assert payload["failures"][0]["suggested_edge"] is None


def test_no_change_set_is_unattributable(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_foo.py"))
    _, payload = _run(capsys, base_repo, "--junit", str(junit))
    assert payload["failures"][0]["selection"] == "unattributable"
    assert payload["inputs"]["change"] is None


def test_an_untracked_failing_test_is_unattributable(
    tmp_path: Path, base_repo: Path, capsys
) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_ghost.py"))
    _, payload = _run(capsys, base_repo, "--junit", str(junit), "--changed", "pkg/foo.py")
    assert payload["failures"][0]["selection"] == "unattributable"


# -- Slow tests -----------------------------------------------------------------


def test_slow_reports_the_top_n_by_duration(tmp_path: Path, base_repo: Path, capsys) -> None:
    cases = "\n".join(
        [
            _passing_case("pkg/test_foo.py", "test_a", seconds=1.0),
            _passing_case("pkg/test_foo.py", "test_b", seconds=5.0),
            _passing_case("pkg/test_foo.py", "test_c", seconds=2.0),
        ]
    )
    junit = _junit(tmp_path, "run.xml", cases)
    _, payload = _run(capsys, base_repo, "--junit", str(junit), "--slow", "2")
    assert [entry["seconds"] for entry in payload["slow"]] == [5.0, 2.0]


def test_slow_defaults_to_empty_when_not_requested(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _passing_case("pkg/test_foo.py", seconds=9.0))
    _, payload = _run(capsys, base_repo, "--junit", str(junit))
    assert payload["slow"] == []


# -- Exit codes and CLI contract ------------------------------------------------


def test_a_clean_run_exits_ok(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _passing_case("pkg/test_foo.py"))
    exit_code, payload = _run(capsys, base_repo, "--junit", str(junit))
    assert exit_code == at.EXIT_OK
    assert payload["summary"]["failures"] == 0


def test_an_unreadable_junit_path_exits_with_usage_error(base_repo: Path) -> None:
    assert (
        at.main(["--repo-root", str(base_repo), "--junit", "/nonexistent/run.xml"]) == at.EXIT_ERROR
    )


def test_human_output_prints_missed_count(tmp_path: Path, base_repo: Path, capsys) -> None:
    junit = _junit(tmp_path, "run.xml", _failing_case("pkg/test_bar.py"))
    at.main(["--repo-root", str(base_repo), "--junit", str(junit), "--changed", "pkg/foo.py"])
    out = capsys.readouterr().out
    assert "missed=1" in out


def test_a_class_based_test_keeps_its_module_file(tmp_path: Path) -> None:
    """pytest folds enclosing classes into `classname`; the file is the real module."""
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="scripts.test_x.TestFoo" name="test_a" time="0.1">'
        '<failure message="boom"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    failed = at.failing_cases(junit, frozenset({"scripts/test_x.py"}))

    assert list(failed) == ["scripts/test_x.py::TestFoo::test_a"]
    assert failed["scripts/test_x.py::TestFoo::test_a"].file == "scripts/test_x.py"
