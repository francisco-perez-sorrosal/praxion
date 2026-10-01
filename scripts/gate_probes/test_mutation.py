"""Tests for `mutation.py` -- the liveness probe for the mutation sensor.

The failure this closes: a probe that passes when the sensor is dead. September
2026's sensor inherited the project's parallel pytest options, every mutant run
failed, and it printed `unavailable`; the old tests used a fixture outside the
repository and never saw it. The judge below is fed every dead-sensor output the
acceptance scenarios use, and each must fail with a reason that quotes it.
Expected values come from the probe's contract (the fixture's two functions),
not from running the implementation.
"""

from __future__ import annotations

import stat
import sys
import textwrap
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation  # noqa: E402

from gate_probes.verdict import GateId, Verdict  # noqa: E402

TARGET = "liveness_target.py"
LIVE_LINE = f"Mutation: survivors=2 mutants=20 targets=[{TARGET}] (loose_label: 2)"
SEPTEMBER_REFUSAL = (
    "Mutation: unavailable reason=run-failed (every mutant's test run failed: "
    "pytest inherited the project's parallel default options)"
)


def _judged(stdout: str, exit_code: int = 0, stderr: str = "") -> str | None:
    return mutation.judge(exit_code, stdout, stderr)


# -- the pure judge ---------------------------------------------------------------


def test_the_expected_reading_passes_the_judge():
    assert _judged(LIVE_LINE + "\n") is None


def test_the_reading_is_found_among_other_output_lines():
    assert _judged("noise\n" + LIVE_LINE + "\n") is None


@pytest.mark.parametrize(
    ("label", "stdout", "exit_code", "quoted"),
    [
        ("the september refusal", SEPTEMBER_REFUSAL + "\n", 2, "reason=run-failed"),
        (
            "the layout refusal",
            "Mutation: unavailable reason=not-flat-layout (targets not in one directory)\n",
            2,
            "reason=not-flat-layout",
        ),
        (
            "success without running",
            "Mutation: survivors=0 mutants=12 targets=[module.py]\n",
            0,
            "survivors=0 mutants=12",
        ),
        ("a sensor that prints nothing", "", 0, "no `Mutation:` line"),
        (
            "a survivor outside the loose function",
            f"Mutation: survivors=1 mutants=12 targets=[{TARGET}] (strict_grade: 1)\n",
            0,
            "strict_grade",
        ),
        (
            "a survivor in unforeseen code on the wrong target",
            "Mutation: survivors=1 mutants=12 targets=[module.py] "
            "(liveness_canary_unforeseen_function: 1)\n",
            0,
            "targets=[module.py]",
        ),
        (
            "no survivor at all",
            f"Mutation: survivors=0 mutants=20 targets=[{TARGET}] ()\n",
            0,
            "survivors=0",
        ),
        (
            "nothing killed",
            f"Mutation: survivors=20 mutants=20 targets=[{TARGET}] (loose_label: 20)\n",
            0,
            "survivors=20",
        ),
        (
            "a survivor list the line cap cut off",
            f"Mutation: survivors=3 mutants=20 targets=[{TARGET}] (loose_label: 2, +1 more)\n",
            0,
            "+1 more",
        ),
        (
            "a line that breaks the grammar",
            "Mutation: survivors=lots mutants=20\n",
            0,
            "survivors=lots",
        ),
        ("a good line with a failing exit code", LIVE_LINE + "\n", 2, "exit code 2"),
    ],
)
def test_every_dead_sensor_output_fails_the_judge_and_is_quoted(label, stdout, exit_code, quoted):
    reason = _judged(stdout, exit_code)

    assert reason is not None, f"{label} passed"
    assert quoted in reason, f"{label}: the reason does not quote the sensor: {reason}"


def test_a_silent_sensor_reason_carries_the_exit_code_and_stderr_tail():
    reason = _judged("", exit_code=2, stderr="can't open file 'scripts/mutation_sensor.py'")

    assert "exit code 2" in reason
    assert "can't open file" in reason


def test_every_failure_reason_is_a_legal_failed_verdict_reason():
    # Verdict's constructor rejects any reason not of the form "expected ...; observed ...".
    for stdout in ("", SEPTEMBER_REFUSAL, "Mutation: garbled", "Mutation: survivors=0"):
        reason = _judged(stdout, 2)
        Verdict(gate=GateId.MUTATION_SENSOR, passed=False, reason=reason, elapsed_s=0.0)


# -- running the sensor in production shape -------------------------------------


def _fake_repo(tmp_path: Path, sensor_body: str | None) -> Path:
    """A stand-in checkout holding a fixture and (optionally) a stub sensor."""
    repo = tmp_path / "checkout"
    fixture = repo / mutation.FIXTURE_DIR
    fixture.mkdir(parents=True)
    (fixture / mutation.FIXTURE_TARGET).write_text("def f():\n    return 1\n")
    (fixture / mutation.FIXTURE_CHECKS).write_text("def test_f():\n    pass\n")
    if sensor_body is not None:
        sensor = repo / mutation.SENSOR
        sensor.parent.mkdir(parents=True, exist_ok=True)
        sensor.write_text(textwrap.dedent(sensor_body))
        sensor.chmod(sensor.stat().st_mode | stat.S_IXUSR)
    return repo


def _printing_sensor(line: str) -> str:
    return f"""\
        import json, os, sys
        from pathlib import Path
        argv = sys.argv[1:]
        targets = argv[argv.index("--targets") + 1]
        tests = argv[argv.index("--tests") + 1]
        Path(os.environ["LIVENESS_RECORD"]).write_text(json.dumps({{
            "argv": argv, "cwd": os.getcwd(),
            "target_exists": Path(targets).is_file(), "tests_exist": Path(tests).is_file(),
            "pytest_addopts": os.environ.get("PYTEST_ADDOPTS"),
        }}))
        print({line!r})
        """


def _run(repo: Path, env: dict[str, str]) -> Verdict:
    return mutation.run(repo, {"PATH": "/usr/bin:/bin", **env})


def test_a_live_sensor_passes_and_runs_over_a_copy_inside_the_checkout(tmp_path):
    import json

    repo = _fake_repo(tmp_path, _printing_sensor(LIVE_LINE))
    record = tmp_path / "record.json"

    verdict = _run(repo, {"LIVENESS_RECORD": str(record)})

    assert verdict.passed, verdict.reason
    assert verdict.gate is GateId.MUTATION_SENSOR
    seen = json.loads(record.read_text())
    scratch = repo / "tmp" / "gate-liveness"
    assert Path(seen["cwd"]).resolve() == repo.resolve()
    assert seen["target_exists"]
    assert seen["tests_exist"]
    targets = Path(seen["argv"][seen["argv"].index("--targets") + 1])
    tests = Path(seen["argv"][seen["argv"].index("--tests") + 1])
    assert targets.name == mutation.FIXTURE_TARGET
    assert tests.name == mutation.FIXTURE_CHECKS
    assert targets.parent == tests.parent
    assert scratch in targets.parents, "the copy must live inside the checkout's tree"
    assert "--timeout" in seen["argv"]


def test_a_run_leaves_no_copy_behind_even_when_the_sensor_fails(tmp_path):
    repo = _fake_repo(tmp_path, "import sys\nsys.exit(2)\n")

    verdict = _run(repo, {})

    assert not verdict.passed
    assert not (repo / "tmp").exists(), "the probe must remove what it created"


def test_a_run_keeps_a_tmp_directory_that_was_already_there(tmp_path):
    repo = _fake_repo(tmp_path, _printing_sensor(LIVE_LINE))
    (repo / "tmp").mkdir()
    (repo / "tmp" / "keep.txt").write_text("mine")

    _run(repo, {"LIVENESS_RECORD": str(tmp_path / "record.json")})

    assert (repo / "tmp" / "keep.txt").read_text() == "mine"
    assert not (repo / "tmp" / "gate-liveness").exists()


def test_a_refusing_sensor_fails_the_probe_quoting_the_refusal(tmp_path):
    repo = _fake_repo(tmp_path, _printing_sensor(SEPTEMBER_REFUSAL))

    verdict = _run(repo, {"LIVENESS_RECORD": str(tmp_path / "record.json")})

    assert not verdict.passed
    assert "reason=run-failed" in verdict.reason


def test_a_missing_sensor_fails_the_probe_and_says_so(tmp_path):
    repo = _fake_repo(tmp_path, None)

    verdict = _run(repo, {})

    assert not verdict.passed
    assert mutation.SENSOR in verdict.reason


def test_a_missing_fixture_fails_the_probe_and_says_so(tmp_path):
    repo = _fake_repo(tmp_path, _printing_sensor(LIVE_LINE))
    (repo / mutation.FIXTURE_DIR / mutation.FIXTURE_CHECKS).unlink()

    verdict = _run(repo, {"LIVENESS_RECORD": str(tmp_path / "record.json")})

    assert not verdict.passed
    assert mutation.FIXTURE_CHECKS in verdict.reason


def test_a_sensor_that_outlives_its_time_limit_fails_the_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(mutation, "SENSOR_PROCESS_TIMEOUT_S", 1.0)
    repo = _fake_repo(tmp_path, "import time\ntime.sleep(30)\n")

    verdict = _run(repo, {})

    assert not verdict.passed
    assert "within 1 seconds" in verdict.reason
    assert not (repo / "tmp").exists()


def test_the_sensor_is_started_without_any_pytest_options_of_its_own(tmp_path):
    # The sensor must meet the project's configuration exactly as a pipeline writer does,
    # so the probe adds no pytest option of its own on top of the scrubbed environment.
    import json

    repo = _fake_repo(tmp_path, _printing_sensor(LIVE_LINE))
    record = tmp_path / "record.json"

    _run(repo, {"LIVENESS_RECORD": str(record)})

    seen = json.loads(record.read_text())
    assert seen["pytest_addopts"] is None
    assert not any(arg.startswith("-n") for arg in seen["argv"])


# -- the exact words of each failure (the reasons are the probe's whole output) ---


def _ran(survivors: int, mutants: int, functions: str, target: str = TARGET) -> str:
    return f"Mutation: survivors={survivors} mutants={mutants} targets=[{target}] ({functions})"


@pytest.mark.parametrize(
    ("stdout", "exit_code", "stderr", "reason"),
    [
        (
            _ran(1, 12, "liveness_canary_unforeseen_function: 1", "module.py"),
            0,
            "",
            "expected targets=[liveness_target.py]; observed "
            + _ran(1, 12, "liveness_canary_unforeseen_function: 1", "module.py"),
        ),
        (
            LIVE_LINE,
            2,
            "",
            f"expected exit code 0 with the reading; observed exit code 2, {LIVE_LINE}",
        ),
        (
            _ran(20, 20, "loose_label: 20"),
            0,
            "",
            "expected at least one mutant killed by the fixture's checks; observed "
            + _ran(20, 20, "loose_label: 20"),
        ),
        (
            _ran(0, 20, ""),
            0,
            "",
            "expected a survivor in the loosely checked function; observed " + _ran(0, 20, ""),
        ),
        (
            _ran(2, 20, "strict_grade: 1, loose_label: 1"),
            0,
            "",
            "expected survivors only in loose_label; observed "
            + _ran(2, 20, "strict_grade: 1, loose_label: 1")
            + " (outside: strict_grade)",
        ),
        (
            _ran(3, 20, "loose_label: 2, +1 more"),
            0,
            "",
            "expected survivors only in loose_label; observed "
            + _ran(3, 20, "loose_label: 2, +1 more"),
        ),
        (
            "Mutation: survivors=lots mutants=20",
            0,
            "",
            "expected a well-formed `Mutation:` line; observed Mutation: survivors=lots mutants=20",
        ),
        (
            SEPTEMBER_REFUSAL,
            2,
            "",
            f"expected the sensor to run over the fixture; observed {SEPTEMBER_REFUSAL}",
        ),
        (
            "",
            0,
            "",
            "expected the sensor to print a `Mutation:` line; "
            "observed no `Mutation:` line (exit code 0, stdout empty)",
        ),
        (
            "some  noise\nmore",
            3,
            "boom\n",
            "expected the sensor to print a `Mutation:` line; observed no `Mutation:` line "
            "(exit code 3, stdout some noise more, stderr boom)",
        ),
    ],
)
def test_each_failure_reason_reads_exactly_expected_then_observed(
    stdout, exit_code, stderr, reason
):
    assert mutation.judge(exit_code, stdout, stderr) == reason


def test_a_missing_sensor_reason_is_exact(tmp_path):
    repo = _fake_repo(tmp_path, None)

    verdict = _run(repo, {})

    assert verdict.reason == f"expected {mutation.SENSOR} in the checkout; observed it is missing"


def test_a_timeout_reason_is_exact(tmp_path, monkeypatch):
    monkeypatch.setattr(mutation, "SENSOR_PROCESS_TIMEOUT_S", 1.0)
    repo = _fake_repo(tmp_path, "import time\ntime.sleep(30)\n")

    verdict = _run(repo, {})

    assert verdict.reason == (
        "expected the sensor to finish within 1 seconds; observed it was still running"
    )


def test_a_long_sensor_line_is_quoted_cut_to_the_quote_limit():
    long_line = _ran(1, 12, "strict_grade: 1", "x" * 400)

    reason = mutation.judge(0, long_line, "")

    assert reason.endswith("...")
    assert len(reason) < len(long_line)
