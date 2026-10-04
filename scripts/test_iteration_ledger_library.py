"""Tests for the iteration ledger library (``scripts/iteration_ledger.py``).

The shape's invariants are table-tested at the line parser (the one place they
are enforced); the writer is shown to refuse before it touches the file; and
writing then reading is shown to be the identity over a generated sample. Every
test builds its ledger under ``tmp_path`` so the module can be mutation-tested
in isolation.
"""

from __future__ import annotations

import json
import random
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import iteration_ledger as ledger  # noqa: E402

STEP_LABEL = "Step "
GOOD_LINE = {
    "v": 1,
    "recorded_at": "2026-10-04T17:39Z",
    "step": f"{STEP_LABEL}3",
    "attempt": 1,
    "agent_id": "a3f9c2e17b",
    "verdict": "verified-complete",
    "decided_by": "check",
    "test_result": "Result: pass=12 fail=0 skip=0",
    "commit": "04569546",
    "stop_reason": "completed",
}
STAMP = "2026-10-04T17:39Z"


def record(**overrides) -> ledger.IterationRecord:
    fields = {k: v for k, v in GOOD_LINE.items() if k not in ("v", "recorded_at")}
    return ledger.IterationRecord(**{**fields, **overrides})


def write_lines(task_dir: Path, *lines: str) -> None:
    (task_dir / ledger.LEDGER_FILE).write_text("".join(f"{line}\n" for line in lines))


def line_with(**overrides) -> str:
    return json.dumps({**GOOD_LINE, **overrides})


def line_without(key: str) -> str:
    return json.dumps({k: v for k, v in GOOD_LINE.items() if k != key})


@pytest.fixture
def fixed_clock(monkeypatch):
    monkeypatch.setattr(ledger, "_utc_minute", lambda: STAMP)


# --- reading: absent, empty and located findings ---


def test_an_absent_ledger_reads_as_no_history(tmp_path):
    assert ledger.read_ledger(tmp_path) == ledger.LedgerReading((), ())


@pytest.mark.parametrize("content", ["", "\n\n", "  \n\t\n"])
def test_an_empty_or_blank_ledger_reads_as_no_history(tmp_path, content):
    (tmp_path / ledger.LEDGER_FILE).write_text(content)

    assert ledger.read_ledger(tmp_path) == ledger.LedgerReading((), ())


def test_a_malformed_line_is_reported_at_its_position_while_valid_lines_survive(tmp_path):
    write_lines(tmp_path, line_with(), "{not json", line_with(attempt=2))

    reading = ledger.read_ledger(tmp_path)

    assert [r.attempt for r in reading.records] == [1, 2]
    assert [f.position for f in reading.findings] == [2]
    assert reading.findings[0].reason.startswith("not valid JSON")


def test_positions_count_only_non_blank_lines(tmp_path):
    write_lines(tmp_path, "", line_with(), "   ", "[1]", "", line_with(v=2))

    reading = ledger.read_ledger(tmp_path)

    assert [f.position for f in reading.findings] == [2, 3]


@pytest.mark.parametrize("line", ["[1]", '"text"', "7", "null"])
def test_a_line_that_is_not_a_json_object_is_a_finding(tmp_path, line):
    write_lines(tmp_path, line)

    assert ledger.read_ledger(tmp_path).findings == (ledger.LedgerFinding(1, "not a JSON object"),)


def test_a_line_that_is_not_utf8_is_a_finding_and_later_lines_still_read(tmp_path):
    (tmp_path / ledger.LEDGER_FILE).write_bytes(b"\xff\xfe\n" + line_with().encode() + b"\n")

    reading = ledger.read_ledger(tmp_path)

    assert reading.findings == (ledger.LedgerFinding(1, "not valid UTF-8"),)
    assert len(reading.records) == 1


# --- the shape: one case per invariant ---


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("stop_reason", "crashed"),
        ("stop_reason", 3),
        ("decided_by", "guess"),
        ("decided_by", None),
        ("verdict", "done"),
        ("verdict", "partial"),
        ("verdict", "partial@"),
        ("verdict", "verified-complete@a.py"),
        ("verdict", None),
        ("test_result", "pass=1 fail=0"),
        ("test_result", "Result: pass=1"),
        ("test_result", "Result: banana"),
        ("test_result", 12),
        ("commit", "ABCDEF1"),
        ("commit", "abc12"),
        ("commit", "a" * 41),
        ("commit", "abcdefg"),
        ("commit", 1234567),
        ("attempt", 0),
        ("attempt", -1),
        ("attempt", "1"),
        ("attempt", True),
        ("attempt", 1.0),
        ("step", "Step"),
        ("step", "Step x1"),
        ("step", f"{STEP_LABEL}1 "),
        ("step", f"{STEP_LABEL}1\n"),
        ("step", "3"),
        ("agent_id", ""),
        ("agent_id", "   "),
        ("agent_id", 9),
        ("v", 2),
        ("v", "1"),
        ("v", True),
        ("recorded_at", "2026-10-04"),
        ("recorded_at", "2026-13-04T17:39Z"),
        ("recorded_at", "2026-1-4T1:5Z"),
        ("recorded_at", "2026-10-04T17:39:00Z"),
        ("recorded_at", ""),
    ],
)
def test_a_value_that_breaks_an_invariant_is_a_finding_naming_the_key(tmp_path, key, bad_value):
    write_lines(tmp_path, line_with(**{key: bad_value}))

    reading = ledger.read_ledger(tmp_path)

    assert reading.records == ()
    assert len(reading.findings) == 1
    assert key in reading.findings[0].reason or "version" in reading.findings[0].reason


@pytest.mark.parametrize("key", list(GOOD_LINE))
def test_a_missing_key_is_a_finding_never_a_default(tmp_path, key):
    write_lines(tmp_path, line_without(key))

    reading = ledger.read_ledger(tmp_path)

    assert reading.records == ()
    assert reading.findings == (ledger.LedgerFinding(1, f"missing key {key!r}"),)


def test_an_absent_commit_key_is_not_read_as_null_but_an_explicit_null_is(tmp_path):
    write_lines(tmp_path, line_without("commit"), line_with(commit=None))

    reading = ledger.read_ledger(tmp_path)

    assert [f.position for f in reading.findings] == [1]
    assert [r.commit for r in reading.records] == [None]


@pytest.mark.parametrize("sha", ["abcdef0", "0123456789abcdef0123456789abcdef01234567"])
def test_commit_accepts_the_seven_and_forty_character_bounds(tmp_path, sha):
    write_lines(tmp_path, line_with(commit=sha))

    assert ledger.read_ledger(tmp_path).records[0].commit == sha


@pytest.mark.parametrize("verdict", [*ledger.VERDICT_WORDS[:2], "partial@src/a b.py", "partial@?"])
def test_every_reconciler_verdict_word_and_partial_with_a_path_is_accepted(tmp_path, verdict):
    write_lines(tmp_path, line_with(verdict=verdict))

    assert ledger.read_ledger(tmp_path).records[0].verdict == verdict


def test_every_verdict_word_but_the_bare_partial_is_accepted(tmp_path):
    words = [word for word in ledger.VERDICT_WORDS if word != "partial"]
    write_lines(tmp_path, *(line_with(verdict=word) for word in words))

    reading = ledger.read_ledger(tmp_path)

    assert reading.findings == ()
    assert [r.verdict for r in reading.records] == words


def test_a_declared_no_run_result_is_accepted(tmp_path):
    write_lines(tmp_path, line_with(test_result="Result: none — docs only"))

    assert ledger.read_ledger(tmp_path).findings == ()


def test_unknown_keys_are_ignored_so_the_shape_can_grow(tmp_path):
    write_lines(tmp_path, line_with(duration_s=41, notes=["x"]))

    reading = ledger.read_ledger(tmp_path)

    assert reading.findings == ()
    assert reading.records == (replace(record(), recorded_at=STAMP),)


def test_the_example_in_the_module_docstring_is_a_valid_record():
    block = ledger.__doc__.split("::", 1)[1]
    example = re.sub(r"\s*\n\s*", " ", block[block.index("{") : block.index("}") + 1])
    example = example.replace("<id>", "7")

    assert ledger.parse_record_line(example).step == f"{STEP_LABEL}7"


# --- writing ---


@pytest.mark.parametrize("stop_reason", ledger.STOP_REASONS)
def test_an_appended_record_reads_back_for_each_stop_reason(tmp_path, fixed_clock, stop_reason):
    ledger.append_record(tmp_path, record(stop_reason=stop_reason))

    assert ledger.read_ledger(tmp_path).records == (
        replace(record(stop_reason=stop_reason), recorded_at=STAMP),
    )


def test_the_writer_stamps_the_append_time_over_any_stamp_the_record_carries(tmp_path, fixed_clock):
    ledger.append_record(tmp_path, replace(record(), recorded_at="1999-01-01T00:00Z"))

    assert ledger.read_ledger(tmp_path).records[0].recorded_at == STAMP


def test_the_clock_stamp_is_the_current_utc_minute():
    stamp = ledger._utc_minute()

    parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    assert abs(datetime.now(timezone.utc) - parsed) < timedelta(minutes=2)


def test_a_record_is_one_line_with_the_documented_keys_in_order(tmp_path, fixed_clock):
    ledger.append_record(tmp_path, record(agent_id="multi\nline"))

    text = (tmp_path / ledger.LEDGER_FILE).read_text()

    assert text.count("\n") == 1
    assert text.endswith("\n")
    assert list(json.loads(text)) == list(GOOD_LINE)


def test_appending_leaves_every_earlier_byte_unchanged(tmp_path, fixed_clock):
    ledger.append_record(tmp_path, record())
    before = (tmp_path / ledger.LEDGER_FILE).read_bytes()

    ledger.append_record(tmp_path, record(attempt=2, commit=None, stop_reason="turn-cap"))

    after = (tmp_path / ledger.LEDGER_FILE).read_bytes()
    assert after.startswith(before)
    assert len(after) > len(before)
    assert [r.attempt for r in ledger.read_ledger(tmp_path).records] == [1, 2]


@pytest.mark.parametrize(
    "bad",
    [
        record(stop_reason="crashed"),
        record(decided_by="guess"),
        record(verdict="done"),
        record(test_result="pass=1 fail=0"),
        record(commit="NOTHEX1"),
        record(attempt=0),
        record(step="one"),
        record(agent_id=""),
    ],
)
def test_an_invalid_record_is_refused_without_touching_the_file(tmp_path, fixed_clock, bad):
    ledger.append_record(tmp_path, record())
    before = (tmp_path / ledger.LEDGER_FILE).read_bytes()

    with pytest.raises(ledger.ShapeError):
        ledger.append_record(tmp_path, bad)

    assert (tmp_path / ledger.LEDGER_FILE).read_bytes() == before


def test_an_invalid_first_record_does_not_create_the_ledger(tmp_path, fixed_clock):
    with pytest.raises(ledger.ShapeError):
        ledger.append_record(tmp_path, record(verdict="done"))

    assert not (tmp_path / ledger.LEDGER_FILE).exists()


def test_a_version_other_than_one_on_a_record_is_refused_by_the_writer(tmp_path, fixed_clock):
    with pytest.raises(ledger.ShapeError, match="version"):
        ledger.append_record(tmp_path, record(v=2))


# --- the identity ---


def generated_records(count: int) -> list[ledger.IterationRecord]:
    rng = random.Random(20261004)
    steps = [f"{STEP_LABEL}{number}" for number in ("1", "12", "3b")]
    verdicts = [*ledger.VERDICT_WORDS[:1], "mismatch", "partial@src/a b.py", "attempts-exhausted"]
    results = [
        "Result: pass=3 fail=0 skip=0",
        "Result: pass=0 fail=2 skip=1",
        "Result: none — docs",
    ]
    commits = [None, "abcdef0", "0123456789abcdef0123456789abcdef01234567"]
    agents = ["a3f9c2e17b", 'agent "quoted"', "ünïcode-é", "tab\there"]
    return [
        record(
            step=rng.choice(steps),
            attempt=rng.randint(1, 3),
            agent_id=rng.choice(agents),
            verdict=rng.choice(verdicts),
            decided_by=rng.choice(ledger.DECIDED_BY),
            test_result=rng.choice(results),
            commit=rng.choice(commits),
            stop_reason=rng.choice(ledger.STOP_REASONS),
        )
        for _ in range(count)
    ]


def test_writing_then_reading_is_the_identity_in_order(tmp_path, fixed_clock):
    written = generated_records(80)

    for item in written:
        ledger.append_record(tmp_path, item)

    reading = ledger.read_ledger(tmp_path)
    assert reading.findings == ()
    assert reading.records == tuple(replace(item, recorded_at=STAMP) for item in written)


def test_parsing_a_rendered_record_gives_the_record_back():
    for item in generated_records(40):
        stamped = replace(item, recorded_at=STAMP)

        assert ledger.parse_record_line(ledger.render_record_line(stamped)) == stamped


def test_a_new_record_is_unstamped_and_at_version_one():
    fresh = record()

    assert (fresh.v, fresh.recorded_at) == (1, ledger.UNSTAMPED)


def test_a_closed_vocabulary_finding_lists_the_allowed_words(tmp_path):
    write_lines(tmp_path, line_with(stop_reason="crashed"))

    assert ledger.read_ledger(tmp_path).findings == (
        ledger.LedgerFinding(
            1, "stop_reason must be one of completed, turn-cap, blocked, no-marker; got 'crashed'"
        ),
    )
