"""Tests for the pure half of the pocket-run module (``scripts/_step_loop_pocket_runs.py``).

The bound a pocket's gate run is allowed, read from three sources in a fixed order, and the
node ids a pytest log shows as failed. Text in, values out: only ``pocket_bound`` touches a
file, and it does so under ``tmp_path``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _step_loop_pocket_runs import (  # noqa: E402
    DEFAULT_BOUND_SECONDS,
    POCKET_TIMEOUTS_VARIABLE,
    PocketBound,
    failed_node_ids,
    files_with_outcomes,
    no_colour_environment,
    pocket_bound,
    resolve_bound,
    with_outcome_reports,
)

DECLARES_1200 = "[tool.praxion.step-loop]\ngate-timeout-seconds = 1200\n"
NOT_POSITIVE_OR_FINITE = ["0", "-5", "inf", "nan", "1e999"]


def declaring(value: str) -> str:
    return f"[tool.praxion.step-loop]\ngate-timeout-seconds = {value}\n"


# --- The bound: source order ---


def test_a_pocket_with_no_override_and_no_declaration_gets_the_default():
    reading = resolve_bound("eval", "", None)

    assert reading.bound == PocketBound("eval", DEFAULT_BOUND_SECONDS, "default")
    assert DEFAULT_BOUND_SECONDS == 540.0
    assert reading.warnings == ()


def test_the_pockets_own_declaration_beats_the_default():
    reading = resolve_bound("eval", "", DECLARES_1200)

    assert reading.bound == PocketBound("eval", 1200.0, "declared")
    assert reading.warnings == ()


def test_an_override_for_the_pocket_beats_its_declaration():
    reading = resolve_bound("eval", "eval=90", DECLARES_1200)

    assert reading.bound == PocketBound("eval", 90.0, "override")


def test_an_override_naming_another_pocket_leaves_this_pockets_declaration_standing():
    reading = resolve_bound("eval", "dashboard_app=90,.=30", DECLARES_1200)

    assert reading.bound == PocketBound("eval", 1200.0, "declared")
    assert reading.warnings == ()


def test_the_root_pocket_is_named_by_a_dot():
    reading = resolve_bound(".", "eval=90,.=30.5", None)

    assert reading.bound == PocketBound(".", 30.5, "override")


@pytest.mark.parametrize("spelling", ["eval/", "./eval", "./eval/", "eval"])
def test_a_pocket_root_spelled_with_slashes_names_the_same_pocket(spelling):
    assert resolve_bound("eval", f"{spelling}=90", None).bound.source == "override"


def test_the_last_override_for_a_pocket_wins():
    assert resolve_bound("eval", "eval=90,eval=120", None).bound.seconds == 120.0


# --- The bound: a malformed source never removes the bound ---


@pytest.mark.parametrize("entry", ["eval", "eval=", "eval=abc", "=90", "eval=9 0", "eval==90"])
def test_a_malformed_override_entry_is_skipped_with_a_warning_naming_it(entry):
    reading = resolve_bound("eval", entry, DECLARES_1200)

    assert reading.bound == PocketBound("eval", 1200.0, "declared")
    assert len(reading.warnings) == 1
    assert entry in reading.warnings[0]
    assert POCKET_TIMEOUTS_VARIABLE in reading.warnings[0]


@pytest.mark.parametrize("seconds", NOT_POSITIVE_OR_FINITE)
def test_an_override_that_is_not_positive_and_finite_is_skipped(seconds):
    reading = resolve_bound("eval", f"eval={seconds}", None)

    assert reading.bound == PocketBound("eval", DEFAULT_BOUND_SECONDS, "default")
    assert len(reading.warnings) == 1


def test_a_good_entry_beside_a_malformed_one_still_applies():
    reading = resolve_bound("eval", "eval=oops,eval=75", None)

    assert reading.bound == PocketBound("eval", 75.0, "override")
    assert len(reading.warnings) == 1


@pytest.mark.parametrize("seconds", ["0", "-1", "inf", "nan", "true", '"900"', "[1]"])
def test_a_declaration_that_is_not_a_positive_finite_number_is_skipped(seconds):
    reading = resolve_bound("eval", "", declaring(seconds))

    assert reading.bound == PocketBound("eval", DEFAULT_BOUND_SECONDS, "default")
    assert len(reading.warnings) == 1
    assert "gate-timeout-seconds" in reading.warnings[0]


def test_a_declaration_may_be_a_float():
    assert resolve_bound("eval", "", declaring("1200.5")).bound.seconds == 1200.5


def test_a_declaration_in_unreadable_toml_is_skipped_with_a_warning():
    reading = resolve_bound("eval", "", "[tool.praxion\nnot toml")

    assert reading.bound == PocketBound("eval", DEFAULT_BOUND_SECONDS, "default")
    assert len(reading.warnings) == 1


@pytest.mark.parametrize("text", ["", "[project]\nname = 'x'\n", "[tool.praxion]\nx = 1\n"])
def test_a_file_that_declares_no_bound_contributes_nothing(text):
    reading = resolve_bound("eval", "", text)

    assert reading.bound.source == "default"
    assert reading.warnings == ()


def test_a_malformed_override_does_not_hide_a_good_declaration_from_the_next_source():
    reading = resolve_bound("eval", "eval=zero", declaring("800"))

    assert reading.bound == PocketBound("eval", 800.0, "declared")


# --- The bound value: the smart constructor ---


@pytest.mark.parametrize("seconds", [0.0, -1.0, float("inf"), float("-inf"), float("nan")])
def test_a_bound_of_no_positive_finite_seconds_cannot_be_built(seconds):
    with pytest.raises(ValueError, match="positive"):
        PocketBound("eval", seconds, "default")


def test_a_bound_names_one_of_three_sources():
    with pytest.raises(ValueError, match="source"):
        PocketBound("eval", 10.0, "guess")  # type: ignore[arg-type]


# --- The bound: the reading of a checkout ---


def test_pocket_bound_reads_the_pockets_own_pyproject(tmp_path):
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "pyproject.toml").write_text(DECLARES_1200, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(declaring("30"), encoding="utf-8")

    assert pocket_bound(tmp_path, "eval", {}).bound == PocketBound("eval", 1200.0, "declared")
    assert pocket_bound(tmp_path, ".", {}).bound == PocketBound(".", 30.0, "declared")


def test_pocket_bound_takes_the_override_from_the_environment_it_is_given(tmp_path):
    environ = {POCKET_TIMEOUTS_VARIABLE: "eval=15"}

    assert pocket_bound(tmp_path, "eval", environ).bound == PocketBound("eval", 15.0, "override")


def test_a_pocket_with_no_pyproject_gets_the_default(tmp_path):
    reading = pocket_bound(tmp_path, "eval", {})

    assert reading.bound == PocketBound("eval", DEFAULT_BOUND_SECONDS, "default")
    assert reading.warnings == ()


def test_an_unreadable_pyproject_is_skipped_with_a_warning(tmp_path):
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "pyproject.toml").write_bytes(b"\xff\xfe not utf-8")

    reading = pocket_bound(tmp_path, "eval", {})

    assert reading.bound.source == "default"
    assert len(reading.warnings) == 1


# --- The failed node ids of a log ---

PLAIN_LOG = """\
============================= test session starts ==============================
tests/test_a.py::test_one PASSED                                         [ 10%]
tests/test_a.py::test_two FAILED                                         [ 20%]
tests/test_a.py::test_three[a - b] FAILED                                [ 30%]
tests/test_b.py::test_four ERROR                                         [ 40%]
tests/test_b.py::test_five SKIPPED (why)                                 [ 50%]
"""

XDIST_LOG = """\
[gw0] [ 10%] PASSED tests/test_a.py::test_one
[gw1] [ 20%] FAILED tests/test_a.py::test_two
[gw0] [ 30%] ERROR tests/test_b.py::test_four[some thing]
"""


def test_the_failed_and_error_ids_of_a_plain_verbose_log_come_back_in_log_order():
    assert failed_node_ids(PLAIN_LOG) == (
        "tests/test_a.py::test_two",
        "tests/test_a.py::test_three[a - b]",
        "tests/test_b.py::test_four",
    )


def test_the_failed_and_error_ids_of_an_xdist_log_come_back_in_log_order():
    assert failed_node_ids(XDIST_LOG) == (
        "tests/test_a.py::test_two",
        "tests/test_b.py::test_four[some thing]",
    )


def test_an_id_shown_twice_is_kept_once_at_its_first_place():
    log = PLAIN_LOG + "tests/test_a.py::test_two ERROR                  [ 60%]\n" + XDIST_LOG

    ids = failed_node_ids(log)

    assert ids.count("tests/test_a.py::test_two") == 1
    assert ids[:3] == failed_node_ids(PLAIN_LOG)
    assert len(ids) == len(set(ids)) == 4


@pytest.mark.parametrize(
    "log",
    [
        "",
        "tests/test_a.py::test_one PASSED  [100%]\n",
        "a line that says FAILED somewhere in prose\n",
        "FAILED without an id\n",
        "== 3 passed in 0.10s ==\n",
    ],
)
def test_a_log_that_shows_no_failure_yields_no_ids(log):
    assert failed_node_ids(log) == ()


def test_a_log_cut_mid_line_still_yields_the_ids_it_completed():
    log = "tests/test_a.py::test_two FAILED   [ 20%]\ntests/test_a.py::test_thr"

    assert failed_node_ids(log) == ("tests/test_a.py::test_two",)


# --- What a run is asked to report, and the environment it is asked in ---


@pytest.mark.parametrize(
    ("argv", "asked"),
    [
        (("uv", "run", "pytest", "a.py"), ("uv", "run", "pytest", "--verbosity=1", "-rfE", "a.py")),
        (("python", "-m", "pytest", "-n", "0", "a.py"), ("python", "-m", "pytest", "--verbosity=1", "-rfE", "-n", "0", "a.py")),
        (("uv", "run", "pytest"), ("uv", "run", "pytest", "--verbosity=1", "-rfE")),
    ],
)  # fmt: skip
def test_a_pytest_invocation_is_asked_for_each_outcome_and_the_failures_and_errors_it_names(
    argv, asked
):
    assert with_outcome_reports(argv) == asked


@pytest.mark.parametrize("quiet_option", ["-q", "-qq"])
def test_a_quiet_pocket_still_prints_each_outcome_and_names_its_failure(tmp_path, quiet_option):
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.pytest.ini_options]\naddopts = "{quiet_option}"\n', encoding="utf-8"
    )
    (tmp_path / "test_pocket.py").write_text(
        "def test_passes():\n    pass\n\n\ndef test_fails():\n    assert 1 == 2\n",
        encoding="utf-8",
    )
    argv = with_outcome_reports((sys.executable, "-m", "pytest", "-p", "no:cacheprovider"))

    ran = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)

    assert "test_pocket.py::test_passes PASSED" in ran.stdout
    assert failed_node_ids(ran.stdout) == ("test_pocket.py::test_fails",)
    assert files_with_outcomes(ran.stdout) == 1


@pytest.mark.parametrize(
    "argv",
    [("npx", "vitest", "run", "src/a.test.ts"), ("pnpm", "exec", "vitest", "run"), ("cargo", "test"), ()],
)  # fmt: skip
def test_an_invocation_of_another_runner_is_left_as_it_is(argv):
    assert with_outcome_reports(argv) == argv


def test_only_the_runner_word_is_taken_for_pytest_not_a_path_that_contains_it():
    argv = ("uv", "run", "pytest", "tests/pytest/test_a.py", "pytest")

    assert with_outcome_reports(argv)[:6] == (
        "uv",
        "run",
        "pytest",
        "--verbosity=1",
        "-rfE",
        "tests/pytest/test_a.py",
    )


def test_the_child_environment_asks_for_no_colour_and_drops_the_variables_that_force_it():
    environ = {
        "PATH": "/bin",
        "FORCE_COLOR": "1",
        "CLICOLOR_FORCE": "1",
        "NO_COLOR": "",
        "PY_COLORS": "1",
    }

    assert no_colour_environment(environ) == {"PATH": "/bin", "NO_COLOR": "1", "PY_COLORS": "0"}


# --- The test files a log shows outcomes for ---


def test_the_test_files_of_a_plain_and_an_xdist_log_are_counted_once_each():
    assert files_with_outcomes(PLAIN_LOG) == 2
    assert files_with_outcomes(PLAIN_LOG + XDIST_LOG) == 2
    assert files_with_outcomes("[gw0] [ 10%] PASSED tests/test_c.py::t[a b]\n") == 1


@pytest.mark.parametrize(
    "log", ["", "== 3 passed in 0.10s ==\n", "a PASSED in prose\n", "FAILED t.py::x - why\n"]
)
def test_a_log_without_streamed_outcomes_shows_no_files(log):
    assert files_with_outcomes(log) == 0
