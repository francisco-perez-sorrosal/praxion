"""The retention policy: how many archives the log keeps, and what they are called.

The policy lives in one stdlib-only module that the writer and the reader share.
It is the only builder and the only parser of an archive's name, so a position is
the same number on the way out (rotation) and on the way back (discovery).
"""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

import pytest

from hooks._observation_log import retention
from hooks._observation_log.retention import archive_path, archive_position

LOG_NAME = "log.jsonl"
LOG = Path("/state") / LOG_NAME

# The policy runs on every tool call, through the writer; nothing beyond these
# may be imported.
_ALLOWED_IMPORTS = frozenset({"__future__", "datetime", "pathlib"})


def test_more_than_one_archive_is_kept() -> None:
    assert retention.ARCHIVE_COUNT >= 2


def test_the_size_cap_is_ten_mebibytes() -> None:
    assert retention.SIZE_CAP_BYTES == 10 * 1024 * 1024


def test_the_history_target_is_twenty_six_weeks() -> None:
    assert retention.HISTORY_TARGET == timedelta(weeks=26)


def test_an_archive_sits_beside_the_log_named_after_its_position() -> None:
    assert archive_path(LOG, 1) == Path("/state/log.jsonl.1")
    assert archive_path(LOG, 12) == Path("/state/log.jsonl.12")


@pytest.mark.parametrize("position", [0, -1])
def test_a_position_below_one_has_no_archive(position: int) -> None:
    with pytest.raises(ValueError, match="starts at 1"):
        archive_path(LOG, position)


@pytest.mark.parametrize("position", [1, 2, retention.ARCHIVE_COUNT, retention.ARCHIVE_COUNT + 3])
def test_a_built_name_parses_back_to_its_position(position: int) -> None:
    assert archive_position(archive_path(LOG, position), LOG_NAME) == position


def test_a_surplus_position_above_the_policy_is_still_an_archive() -> None:
    surplus = retention.ARCHIVE_COUNT + 40

    assert archive_position(Path(f"/state/{LOG_NAME}.{surplus}"), LOG_NAME) == surplus


@pytest.mark.parametrize(
    "name",
    [
        LOG_NAME,  # the active log is no archive
        f"{LOG_NAME}.0",  # positions start at one
        f"{LOG_NAME}.01",  # a name the builder never writes
        f"{LOG_NAME}.-1",
        f"{LOG_NAME}.1.bak",
        f"{LOG_NAME}.x",
        f"{LOG_NAME}.",
        f"{LOG_NAME}.١",  # a non-ASCII digit
        "other.jsonl.1",  # another file's archive
        f"x{LOG_NAME}.1",
    ],
)
def test_only_a_name_the_builder_writes_is_an_archive(name: str) -> None:
    assert archive_position(Path("/state") / name, LOG_NAME) is None


def test_the_policy_imports_nothing_beyond_the_hot_path_allowance() -> None:
    source = Path(retention.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "the policy must not import its sibling modules"
            imported.add((node.module or "").split(".")[0])

    assert imported <= _ALLOWED_IMPORTS, imported - _ALLOWED_IMPORTS
