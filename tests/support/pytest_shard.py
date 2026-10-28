"""Run one CI shard of the root suite: the tests whose node id hashes to it.

`--shard K/N` keeps each collected test whose node id's CRC-32, modulo N, is K - 1, and
deselects the rest. Every test is in exactly one of the N shards whatever is added, renamed
or moved, so N shard jobs together run the whole suite with no file list to keep in step.
The hash is over the node id, not the file, so one heavy file spreads across shards.

Loaded only by a job that asks for it, from the repository root:
`python -m pytest -p tests.support.pytest_shard --shard 2/4`. Without `--shard` it selects
everything. Under pytest-xdist each worker collects and deselects alike, since the hash
depends on the node id alone.
"""

from __future__ import annotations

import zlib

import pytest

SHARD_OPTION = "--shard"


def parse_shard(value: str) -> tuple[int, int]:
    """`K/N` as `(K, N)` with `1 <= K <= N`; any other value is a usage error."""
    index, separator, count = value.partition("/")
    if separator and index.isdigit() and count.isdigit() and 1 <= int(index) <= int(count):
        return int(index), int(count)
    raise pytest.UsageError(f"{SHARD_OPTION} takes K/N with 1 <= K <= N, not {value!r}")


def in_shard(nodeid: str, index: int, count: int) -> bool:
    return zlib.crc32(nodeid.encode("utf-8")) % count == index - 1


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        SHARD_OPTION, metavar="K/N", help="run only shard K of N of the collected tests"
    )


def pytest_configure(config: pytest.Config) -> None:
    value = config.getoption(SHARD_OPTION)
    if value is not None:
        parse_shard(value)  # a malformed value stops the run before collection


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption(SHARD_OPTION)
    if value is None:
        return
    index, count = parse_shard(value)
    kept = [item for item in items if in_shard(item.nodeid, index, count)]
    deselected = [item for item in items if not in_shard(item.nodeid, index, count)]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
