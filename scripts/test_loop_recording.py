"""Tests for `_step_loop_recording.py` -- the lock a `record` call holds for its whole run.

Another holder is a second descriptor of the same file in this process: `flock` locks belong to
an open file description, so two `os.open` calls contend exactly as two processes do. Waiting is
driven by an injected clock and sleep, so no test waits on the wall clock. Imports only the
module under test, `pytest` and the standard library, so the mutation sensor can run this file.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _step_loop_recording as recording  # noqa: E402

REQUEST = "s3-a1-implement"


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / "task" / "gate" / REQUEST


@contextmanager
def held_elsewhere(run_dir: Path, content: bytes = b"") -> Iterator[int]:
    """The lock held through a descriptor of its own, as another `record` would hold it."""
    run_dir.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(run_dir / recording.LOCK_FILE, os.O_RDWR | os.O_CREAT)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(descriptor, content)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


class FakeTime:
    """A monotonic clock that moves only when the code under test sleeps."""

    def __init__(self) -> None:
        self.now, self.slept = 0.0, []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_a_held_record_reads_in_flight_and_a_finished_one_does_not(run_dir):
    with recording.holding_record(run_dir):
        during = recording.record_in_flight(run_dir)
    assert (during, recording.record_in_flight(run_dir)) == (True, False)


def test_the_lock_file_names_the_holder_and_when_it_started(run_dir):
    with recording.holding_record(run_dir):
        holder = json.loads((run_dir / recording.LOCK_FILE).read_text(encoding="utf-8"))
    assert sorted(holder) == ["pid", "started"]
    assert holder["pid"] == os.getpid()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", holder["started"]), holder
    assert datetime.fromisoformat(holder["started"].replace("Z", "+00:00")).tzinfo is not None


def test_the_lock_file_is_readable_by_all_and_writable_by_its_owner_only(run_dir):
    previous = os.umask(0o022)
    try:
        with recording.holding_record(run_dir):
            mode = (run_dir / recording.LOCK_FILE).stat().st_mode
    finally:
        os.umask(previous)
    assert stat.S_IMODE(mode) == 0o644


def test_a_longer_holder_left_by_an_earlier_record_is_replaced_whole(run_dir):
    run_dir.mkdir(parents=True)
    earlier = {"pid": 1, "started": "2026-11-16T10:00:00Z", "note": "x" * 200}
    (run_dir / recording.LOCK_FILE).write_text(json.dumps(earlier), encoding="utf-8")
    with recording.holding_record(run_dir):
        holder = json.loads((run_dir / recording.LOCK_FILE).read_text(encoding="utf-8"))
    assert sorted(holder) == ["pid", "started"]


def test_a_probe_with_no_lock_file_reads_no_record_and_creates_nothing(run_dir):
    assert recording.record_in_flight(run_dir) is False
    assert not run_dir.exists()


def test_a_probe_that_cannot_open_the_lock_file_reads_no_record(run_dir):
    run_dir.mkdir(parents=True)
    lock = run_dir / recording.LOCK_FILE
    lock.write_text("", encoding="utf-8")
    lock.chmod(0)
    try:
        assert recording.record_in_flight(run_dir) is False
    finally:
        lock.chmod(0o644)


def test_a_probe_whose_lock_call_errors_reads_no_record(run_dir, monkeypatch):
    def failing(descriptor: int, operation: int) -> None:
        raise OSError("the lock cannot be asked")

    with recording.holding_record(run_dir):
        monkeypatch.setattr(recording.fcntl, "flock", failing)
        assert recording.record_in_flight(run_dir) is False


def test_a_record_with_no_wait_left_refuses_without_sleeping(run_dir, monkeypatch):
    monkeypatch.setattr(recording, "WAIT_SECONDS", 0.0)
    time = FakeTime()
    with held_elsewhere(run_dir), pytest.raises(recording.RecordRunningError):
        with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
            pass
    assert time.slept == []


def test_a_probe_leaves_the_lock_free_for_a_record_that_starts_after_it(run_dir):
    with recording.holding_record(run_dir):
        pass
    assert recording.record_in_flight(run_dir) is False
    time = FakeTime()
    with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
        pass
    assert time.slept == []


def test_a_second_record_is_refused_naming_the_request_and_the_holder(run_dir):
    holder = json.dumps({"pid": 4242, "started": "2026-11-16T10:00:00Z"}).encode()
    time = FakeTime()
    with held_elsewhere(run_dir, holder), pytest.raises(recording.RecordRunningError) as refused:
        with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
            pytest.fail("the body ran while another record held the lock")
    assert (refused.value.request, refused.value.holder_pid) == (REQUEST, 4242)
    assert str(refused.value) == f"a record of {REQUEST} is already running in process 4242"


def test_a_second_record_waits_the_whole_wait_before_it_refuses(run_dir):
    time = FakeTime()
    with held_elsewhere(run_dir), pytest.raises(recording.RecordRunningError):
        with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
            pass
    assert time.now >= recording.WAIT_SECONDS
    assert time.now < recording.WAIT_SECONDS + recording.RETRY_SECONDS
    assert set(time.slept) == {recording.RETRY_SECONDS}


def test_a_lock_released_while_the_record_waits_is_taken(run_dir):
    other = held_elsewhere(run_dir)
    other.__enter__()
    time = FakeTime()

    def release_then_sleep(seconds: float) -> None:
        other.__exit__(None, None, None)
        time.sleep(seconds)

    with recording.holding_record(run_dir, clock=time.clock, sleep=release_then_sleep):
        assert recording.record_in_flight(run_dir) is True
    assert time.slept == [recording.RETRY_SECONDS]


@pytest.mark.parametrize(
    "content",
    [b"", b"not json", b"[4242]", b'{"pid": "4242"}', b'{"pid": true}', b"\xff\xfe"],
    ids=["empty", "not-json", "not-an-object", "pid-text", "pid-boolean", "not-utf8"],
)
def test_a_holder_whose_pid_cannot_be_read_is_named_as_unknown(run_dir, content):
    time = FakeTime()
    with held_elsewhere(run_dir, content), pytest.raises(recording.RecordRunningError) as refused:
        with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
            pass
    assert refused.value.holder_pid is None
    assert str(refused.value).endswith("already running in an unknown process")


def test_a_finished_record_leaves_no_lock_file(run_dir):
    with recording.holding_record(run_dir):
        pass
    assert not (run_dir / recording.LOCK_FILE).exists()


def test_a_lock_taken_on_a_file_its_holder_just_removed_is_taken_again_on_the_new_file(
    run_dir, monkeypatch
):
    other = held_elsewhere(run_dir)
    other.__enter__()
    taking = recording._try_lock
    removed: list[bool] = []

    def holder_lets_go_first(descriptor: int) -> bool:
        if not removed:  # the holder unlinks, then closes, after this call opened the old file
            (run_dir / recording.LOCK_FILE).unlink()
            other.__exit__(None, None, None)
            removed.append(True)
        return taking(descriptor)

    monkeypatch.setattr(recording, "_try_lock", holder_lets_go_first)
    time = FakeTime()
    with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
        monkeypatch.setattr(recording, "_try_lock", taking)
        assert recording.record_in_flight(run_dir) is True
    assert time.slept == []


def test_a_record_whose_lock_file_was_removed_meanwhile_still_ends_cleanly(run_dir):
    with recording.holding_record(run_dir):
        (run_dir / recording.LOCK_FILE).unlink()
    assert recording.record_in_flight(run_dir) is False


def test_a_record_whose_body_raises_releases_the_lock(run_dir):
    with pytest.raises(RuntimeError), recording.holding_record(run_dir):
        raise RuntimeError("the record failed")
    assert recording.record_in_flight(run_dir) is False


def test_a_refused_record_leaves_the_holders_lock_held(run_dir):
    time = FakeTime()
    with held_elsewhere(run_dir):
        with pytest.raises(recording.RecordRunningError):
            with recording.holding_record(run_dir, clock=time.clock, sleep=time.sleep):
                pass
        assert recording.record_in_flight(run_dir) is True
        assert (run_dir / recording.LOCK_FILE).exists()


def test_a_child_the_record_starts_does_not_keep_the_lock_after_the_record_ends(run_dir):
    with recording.holding_record(run_dir):
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.read()"],
            stdin=subprocess.PIPE,
            close_fds=False,
        )
    try:
        assert recording.record_in_flight(run_dir) is False
    finally:
        child.communicate(b"")
