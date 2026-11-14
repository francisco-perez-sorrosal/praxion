"""Tests for the edge read of the refactoring skill's body in ``hooks/_skill_delivery.py``.

The read must hand back the whole body or say why it could not: a part of the skill is worse than
none (the block delivers the body whole), and no skill file may hold the hook past its second.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402

LIVE_SKILL_DIR = PLUGIN_ROOT / "skills" / delivery.REFACTORING_SKILL
HEADER = "---\nname: refactoring\ndescription: x\n---\n"
BODY = "\n# Pragmatic Refactoring\n\nSee [patterns](references/patterns.md).\n"
# A margin over the 1-second read timeout, for a loaded machine.
PROMPT_EXIT_SECONDS = 5


def skill_dir_with(tmp_path: Path, content: bytes, patterns: bool = True) -> Path:
    skill_dir = tmp_path / "refactoring"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(content)
    if patterns:
        (skill_dir / "references" / "patterns.md").write_text("patterns\n", encoding="utf-8")
    return skill_dir


@pytest.mark.skipif(
    not LIVE_SKILL_DIR.is_dir(),
    reason="a mutation sensor's copy of hooks/ sits beside no skills/ directory",
)
def test_the_live_body_reads_whole():
    text = (LIVE_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert delivery.read_body(LIVE_SKILL_DIR) == text.split("\n---\n", 1)[1]


def test_the_body_is_everything_after_the_header_untouched(tmp_path):
    skill_dir = skill_dir_with(tmp_path, (HEADER + BODY).encode("utf-8"))

    assert delivery.read_body(skill_dir) == BODY


def test_a_rule_line_inside_the_body_does_not_end_the_header_early(tmp_path):
    body = BODY + "\n---\n\nAfter a rule.\n"
    skill_dir = skill_dir_with(tmp_path, (HEADER + body).encode("utf-8"))

    assert delivery.read_body(skill_dir) == body


@pytest.mark.parametrize("content", [b"# No header\n\nText.\n", b"---\nname: refactoring\n"])
def test_a_file_without_a_closed_header_is_unreadable(tmp_path, content):
    skill_dir = skill_dir_with(tmp_path, content)

    assert delivery.read_body(skill_dir) == delivery.BodyUnreadable("skill-unreadable")


def test_a_missing_skill_file_is_unreadable(tmp_path):
    skill_dir = skill_dir_with(tmp_path, b"")
    (skill_dir / "SKILL.md").unlink()

    assert delivery.read_body(skill_dir) == delivery.BodyUnreadable("skill-unreadable")


def test_a_missing_skill_directory_is_unreadable(tmp_path):
    assert delivery.read_body(tmp_path / "absent") == delivery.BodyUnreadable("skill-unreadable")


def test_a_directory_without_the_reference_file_is_unreadable(tmp_path):
    skill_dir = skill_dir_with(tmp_path, (HEADER + BODY).encode("utf-8"), patterns=False)

    assert delivery.read_body(skill_dir) == delivery.BodyUnreadable("skill-unreadable")


def test_invalid_utf8_is_unreadable(tmp_path):
    skill_dir = skill_dir_with(tmp_path, HEADER.encode("utf-8") + b"\xff\xfe broken\n")

    assert delivery.read_body(skill_dir) == delivery.BodyUnreadable("skill-unreadable")


def padded_to(size: int) -> bytes:
    head = (HEADER + "\n").encode("utf-8")
    return head + b"x" * (size - len(head))


def test_a_file_of_exactly_the_limit_reads_whole(tmp_path):
    content = padded_to(delivery.MAX_SKILL_BYTES)
    skill_dir = skill_dir_with(tmp_path, content)

    assert delivery.read_body(skill_dir) == content.decode("utf-8").split("\n---\n", 1)[1]


def test_a_file_over_the_limit_is_unreadable_never_cut(tmp_path):
    skill_dir = skill_dir_with(tmp_path, padded_to(delivery.MAX_SKILL_BYTES + 1))

    assert delivery.read_body(skill_dir) == delivery.BodyUnreadable("skill-unreadable")


def test_a_fifo_nobody_writes_ends_as_a_timeout_within_its_bound(tmp_path):
    skill_dir = skill_dir_with(tmp_path, b"")
    fifo = skill_dir / "SKILL.md"
    fifo.unlink()
    os.mkfifo(fifo)

    started = time.monotonic()
    result = delivery.read_body(skill_dir)
    elapsed = time.monotonic() - started

    assert result == delivery.BodyUnreadable("skill-read-timeout")
    assert delivery.READ_TIMEOUT_SECONDS <= elapsed < PROMPT_EXIT_SECONDS
    # Release the reader thread blocked in open(), so the test leaves nothing waiting.
    release = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    os.close(release)


def test_the_process_exits_zero_promptly_with_a_fifo_still_blocked(tmp_path):
    skill_dir = skill_dir_with(tmp_path, b"")
    fifo = skill_dir / "SKILL.md"
    fifo.unlink()
    os.mkfifo(fifo)
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); import _skill_delivery as d; "
        "sys.exit(0 if d.read_body(__import__('pathlib').Path(sys.argv[2])) == "
        "d.BodyUnreadable('skill-read-timeout') else 1)"
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(HOOKS_DIR), str(skill_dir)],
        timeout=PROMPT_EXIT_SECONDS,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
