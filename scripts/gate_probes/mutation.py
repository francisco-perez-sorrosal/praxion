"""Liveness probe for the mutation sensor: does it still bite, where a pipeline runs it?

The probe copies a small fixture into a scratch directory *inside the checkout's
tree* (`tmp/`, gitignored), so the sensor's test runs see the project's own
pytest configuration, the condition under which the sensor died in September
2026 (every mutant run inherited `-n auto` and the sensor printed `unavailable`).
It then runs `scripts/mutation_sensor.py` over that copy from the checkout root,
the way a pipeline writer does, and judges the one `Mutation:` line it prints.

The fixture has a function its checks pin everywhere (`strict_grade`) and one
they leave loose at its boundary (`loose_label`). The probe passes only when the
sensor ran, killed at least one mutant, left at least one survivor, and every
survivor is in the loose function. A refusal of any kind (the layout reason
included), no output, a missing sensor, or a survivor elsewhere fails, quoting
what the sensor said. Nothing passes by default.

`judge` is pure and carries the verdict logic; `run` is the effectful edge.
Imports are flat siblings, the layout the mutation sensor reads. Tests:
`scripts/gate_probes/test_mutation.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from _step_schema import (
    MutationMalformed,
    MutationRan,
    MutationRefused,
    parse_mutation_line,
    render_mutation_line,
)

from gate_probes.verdict import GateId, Verdict

SENSOR = "scripts/mutation_sensor.py"
FIXTURE_DIR = "scripts/gate_probes/fixture"
FIXTURE_TARGET = "liveness_target.py"
FIXTURE_CHECKS = "liveness_checks.py"
LOOSE_FUNCTIONS = frozenset({"loose_label"})  # the only code the fixture's checks leave unpinned

SCRATCH_DIR = Path("tmp") / "gate-liveness"  # gitignored, inside the checkout's tree

# The CLI gives this probe 300 s. The sensor refuses by itself at its own budget,
# so a slow run reads as a refusal rather than a kill, and cleanup still runs.
SENSOR_TIMEOUT_S = 240
SENSOR_PROCESS_TIMEOUT_S = 270.0

_QUOTE_CHARS = 300


def run(repo_root: Path, env: Mapping[str, str]) -> Verdict:
    started = time.monotonic()
    reason = _probe(repo_root, env)
    elapsed = time.monotonic() - started
    if reason is None:
        return Verdict(gate=GateId.MUTATION_SENSOR, passed=True, reason="", elapsed_s=elapsed)
    return Verdict(gate=GateId.MUTATION_SENSOR, passed=False, reason=reason, elapsed_s=elapsed)


def judge(exit_code: int, stdout: str, stderr: str) -> str | None:
    """Why the sensor's output shows a dead sensor; None when it shows a live one."""
    found = [(line, parse_mutation_line(line)) for line in stdout.splitlines()]
    readings = [(line, reading) for line, reading in found if reading is not None]
    if not readings:
        return _silent_sensor(exit_code, stdout, stderr)
    line, reading = readings[-1]
    if isinstance(reading, MutationMalformed):
        return _failure("a well-formed `Mutation:` line", _quote(line))
    if isinstance(reading, MutationRefused):
        return _failure("the sensor to run over the fixture", _quote(render_mutation_line(reading)))
    return _judge_ran(reading, exit_code, line)


def _judge_ran(reading: MutationRan, exit_code: int, line: str) -> str | None:
    quoted = _quote(line)
    killed = reading.mutants - reading.survivors - reading.inconclusive
    if reading.targets != (FIXTURE_TARGET,):
        return _failure(f"targets=[{FIXTURE_TARGET}]", quoted)
    if exit_code != 0:
        return _failure("exit code 0 with the reading", f"exit code {exit_code}, {quoted}")
    if killed < 1:
        return _failure("at least one mutant killed by the fixture's checks", quoted)
    if reading.survivors < 1:
        return _failure("a survivor in the loosely checked function", quoted)
    outside = [name for name, _ in reading.per_function if name not in LOOSE_FUNCTIONS]
    if outside or reading.more:
        return _failure(
            f"survivors only in {', '.join(sorted(LOOSE_FUNCTIONS))}",
            quoted + (f" (outside: {', '.join(outside)})" if outside else ""),
        )
    return None


def _silent_sensor(exit_code: int, stdout: str, stderr: str) -> str:
    observed = f"no `Mutation:` line (exit code {exit_code}, stdout {_quote(stdout) or 'empty'}"
    if stderr.strip():
        observed += f", stderr {_quote(stderr[-_QUOTE_CHARS:])}"
    return _failure("the sensor to print a `Mutation:` line", observed + ")")


def _failure(expected: str, observed: str) -> str:
    return f"expected {expected}; observed {observed}"


def _quote(text: str) -> str:
    flattened = " ".join(text.split())
    return flattened if len(flattened) <= _QUOTE_CHARS else flattened[:_QUOTE_CHARS] + "..."


def _probe(repo_root: Path, env: Mapping[str, str]) -> str | None:
    missing = _first_missing(repo_root)
    if missing is not None:
        return _failure(f"{missing} in the checkout", "it is missing")
    with _scratch_copy(repo_root) as copy:
        argv = [
            sys.executable,
            str(repo_root / SENSOR),
            "--targets",
            str(copy / FIXTURE_TARGET),
            "--tests",
            str(copy / FIXTURE_CHECKS),
            "--timeout",
            str(SENSOR_TIMEOUT_S),
        ]
        try:
            done = subprocess.run(
                argv,
                cwd=repo_root,
                env=dict(env),
                capture_output=True,
                text=True,
                timeout=SENSOR_PROCESS_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return _failure(
                f"the sensor to finish within {SENSOR_PROCESS_TIMEOUT_S:g} seconds",
                "it was still running",
            )
    return judge(done.returncode, done.stdout, done.stderr)


def _first_missing(repo_root: Path) -> str | None:
    wanted = (SENSOR, f"{FIXTURE_DIR}/{FIXTURE_TARGET}", f"{FIXTURE_DIR}/{FIXTURE_CHECKS}")
    return next((path for path in wanted if not (repo_root / path).is_file()), None)


@contextmanager
def _scratch_copy(repo_root: Path) -> Iterator[Path]:
    """A fresh copy of the fixture under `tmp/gate-liveness/`; removed with whatever it created."""
    scratch_root = repo_root / SCRATCH_DIR
    created = [path for path in (scratch_root.parent, scratch_root) if not path.exists()]
    scratch_root.mkdir(parents=True, exist_ok=True)
    copy = Path(tempfile.mkdtemp(prefix=f"{os.getpid()}-", dir=scratch_root))
    try:
        for name in (FIXTURE_TARGET, FIXTURE_CHECKS):
            shutil.copy2(repo_root / FIXTURE_DIR / name, copy / name)
        yield copy
    finally:
        shutil.rmtree(copy, ignore_errors=True)
        for path in reversed(created):
            try:
                path.rmdir()
            except OSError:
                pass  # something else put a file there; leave it
