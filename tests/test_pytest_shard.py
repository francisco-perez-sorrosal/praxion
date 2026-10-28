"""The CI shard plugin puts every test in exactly one shard, and its shards run the suite whole."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.pytest_shard import in_shard, parse_shard

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "tests.support.pytest_shard"
NODE_IDS = tuple(
    f"tests/acceptance/test_{name}.py::test_case_{i}[param-{i % 3}]"
    for name in ("alpha", "beta", "gamma", "delta")
    for i in range(50)
)


def shards_holding(nodeid: str, count: int) -> list[int]:
    return [k for k in range(1, count + 1) if in_shard(nodeid, k, count)]


@pytest.mark.parametrize("count", [1, 2, 3, 4, 6])
def test_every_test_is_in_exactly_one_shard(count: int) -> None:
    placements = {nodeid: shards_holding(nodeid, count) for nodeid in NODE_IDS}

    assert {nodeid: len(shards) for nodeid, shards in placements.items()} == dict.fromkeys(
        NODE_IDS, 1
    )


def test_a_shard_value_reads_as_its_index_and_count() -> None:
    assert parse_shard("2/4") == (2, 4)


@pytest.mark.parametrize("value", ["0/4", "5/4", "4", "a/4", "2/0", "2/x", "", "-1/4", "2/4/1"])
def test_a_malformed_shard_value_is_a_usage_error(value: str) -> None:
    with pytest.raises(pytest.UsageError, match="K/N"):
        parse_shard(value)


def collected(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Collect-only over a scratch project with the plugin loaded, as a CI shard job does."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    env.pop("PYTEST_ADDOPTS", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", PLUGIN, "--collect-only", "-q", *args],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def node_ids(run: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in run.stdout.splitlines() if "::" in line]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    body = "import pytest\n\n\n@pytest.mark.parametrize('n', range(40))\ndef test_x(n):\n    pass\n"
    (tmp_path / "test_one.py").write_text(body, encoding="utf-8")
    (tmp_path / "test_two.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_the_shards_of_a_suite_together_collect_it_once(project: Path) -> None:
    whole = node_ids(collected(project))
    shards = [node_ids(collected(project, "--shard", f"{k}/3")) for k in (1, 2, 3)]
    every_shard = [nodeid for shard in shards for nodeid in shard]

    assert len(whole) == 80
    assert sorted(every_shard) == sorted(whole), "the shards drop or repeat a test"
    assert all(shards), "a shard of a suite this size collected nothing"


def test_a_malformed_shard_value_stops_the_run_before_collection(project: Path) -> None:
    run = collected(project, "--shard", "4/3")

    assert run.returncode == pytest.ExitCode.USAGE_ERROR, run.stdout + run.stderr
    assert "K/N" in run.stderr
