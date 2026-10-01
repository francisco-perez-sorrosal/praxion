"""Driver for the selection audit, the liveness check that runs the whole suite.

The liveness run itself is reached through the acceptance driver
(`tests/acceptance/drivers/gate_liveness.py`), which owns its single binding;
this module adds what only the whole-suite scenarios need: test files that read
a file the resolver has no route to, a resolver that selects nothing, and a
direct question to the copy's resolver to confirm the route really is missing.

The canary test files never spell the paths they read as one literal, so no
literal-path route can select them; the data files' own paths appear here, in
this driver, which the copy's suite never collects as a test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

from tests.acceptance.drivers.dead_gates import (
    RESOLVER,
    mutation_sensor_parallel_inheritance_failure,
    replace_with_stub,
)
from tests.acceptance.drivers.gate_liveness import (
    ALL_GATES,
    PROJECT_LOG,
    Gate,
    LivenessRun,
    RepoCopy,
    make_copy,
    run_liveness,
)

__all__ = [
    "ALL_GATES",
    "PROJECT_LOG",
    "Gate",
    "LivenessRun",
    "RepoCopy",
    "UnroutedReads",
    "add_tests_reading_unrouted_files",
    "RESOLVER",
    "make_copy",
    "mutation_sensor_parallel_inheritance_failure",
    "resolver_selects_nothing",
    "run_liveness",
    "WHOLE_SUITE_TIMEOUT",
]

WHOLE_SUITE_TIMEOUT = 1800

CANARY_TEST = "tests/test_liveness_canary_unrouted_reads.py"
READ_DIRECTLY = "docs/liveness-canary/read-directly.txt"
READ_BY_A_CHILD_PROCESS = "docs/liveness-canary/read-by-a-child-process.txt"

_CANARY_TEST_SOURCE = '''"""Reads two files no test route points at (a liveness acceptance canary)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / ("do" + "cs") / ("liveness" + "-" + "canary")


def test_reads_a_file_directly():
    assert (FOLDER / ("read" + "-directly" + ".txt")).read_text().strip() == "direct"


def test_reads_a_file_in_a_child_process():
    target = FOLDER / ("read" + "-by-a-child" + "-process" + ".txt")
    out = subprocess.run(
        [sys.executable, "-c", "import sys; print(open(sys.argv[1]).read().strip())", str(target)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.strip() == "child"
'''


@dataclass(frozen=True)
class UnroutedReads:
    direct: tuple[str, str]  # (test file, file it reads in its own process)
    via_child_process: tuple[str, str]  # (test file, file a process it starts reads)


def _resolver_selection(copy: RepoCopy, changed: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(copy.path(RESOLVER)),
            "--repo-root",
            str(copy.root),
            "--json",
            "--changed",
            changed,
        ],
        cwd=copy.root,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout)


def _assert_unrouted(copy: RepoCopy, data_file: str) -> None:
    selection = _resolver_selection(copy, data_file)
    selected = {test["path"] for pocket in selection["pockets"] for test in pocket["tests"]}
    precondition = (
        f"precondition: a change to {data_file} must neither widen nor select {CANARY_TEST}, "
        f"or this scenario cannot show an unselected read; the resolver answered {selection}"
    )
    assert not selection["widen"], precondition
    assert CANARY_TEST not in selected, precondition


def add_tests_reading_unrouted_files(copy: RepoCopy) -> UnroutedReads:
    """Commit a test file that reads two tracked files the resolver does not route to it."""
    copy.write(READ_DIRECTLY, "direct\n")
    copy.write(READ_BY_A_CHILD_PROCESS, "child\n")
    copy.write(CANARY_TEST, _CANARY_TEST_SOURCE)
    copy.commit("tests that read files no route points at")
    _assert_unrouted(copy, READ_DIRECTLY)
    _assert_unrouted(copy, READ_BY_A_CHILD_PROCESS)
    return UnroutedReads(
        direct=(CANARY_TEST, READ_DIRECTLY),
        via_child_process=(CANARY_TEST, READ_BY_A_CHILD_PROCESS),
    )


_EMPTY_SELECTION = {
    "schema": 2,
    "changed": {"source": "explicit", "paths": []},
    "decision": "selected",
    "widen": [],
    "ignored_non_source": [],
    "pockets": [],
}


def resolver_selects_nothing(copy: RepoCopy) -> None:
    """Does nothing and reports success: an empty selection, exit 0, whatever changed."""
    replace_with_stub(copy, RESOLVER, stdout=json.dumps(_EMPTY_SELECTION) + "\n", exit_code=0)
