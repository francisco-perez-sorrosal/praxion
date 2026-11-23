"""Tests for the `copy` channel of `selection.py` -- how the audit treats copies of the checkout.

A test that copies the checkout as a whole reads every copied file, but only to copy it: those
reads are set aside, counted in a note, and what the test reads later from its copies is not
audited. Every other read of that test is judged as before. Imports only `selection`, the
layout the mutation sensor reads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import selection  # noqa: E402

COPYING_TEST = "tests/test_copies_the_checkout.py"
OTHER_COPYING_TEST = "tests/test_copies_it_too.py"
COPIED = "docs/a.txt"
COPIED_TOO = "docs/b.txt"
UNTRACKED = "build/generated.txt"
TRACKED = frozenset({COPIED, COPIED_TOO, "docs/c.txt"})


def _record(test: str, path: str, channel: str) -> str:
    return json.dumps({"t": test, "p": path, "c": channel})


def _observed(direct=(), child=(), copy=(), imported=()) -> selection.ObservedReads:
    return selection.ObservedReads(
        pairs_by_channel={
            "direct": frozenset(direct),
            "child": frozenset(child),
            "import": frozenset(imported),
            "copy": frozenset(copy),
        },
        heartbeats=frozenset({COPYING_TEST}),
        collected=frozenset({COPYING_TEST}),
    )


# -- parsing -----------------------------------------------------------------------


def test_a_record_on_the_copy_channel_is_parsed_into_its_own_channel():
    observed = selection.parse_records(
        [_record(COPYING_TEST, COPIED, "copy"), _record(COPYING_TEST, COPIED_TOO, "direct")]
    )

    assert observed.pairs_by_channel["copy"] == {(COPYING_TEST, COPIED)}
    assert observed.pairs_by_channel["direct"] == {(COPYING_TEST, COPIED_TOO)}


def test_a_trace_without_a_copy_record_has_an_empty_copy_channel():
    observed = selection.parse_records([_record(COPYING_TEST, COPIED, "direct")])

    assert observed.pairs_by_channel["copy"] == frozenset()


def test_an_unknown_channel_is_still_an_unreadable_record():
    with pytest.raises(ValueError, match="unrecognised trace record"):
        selection.parse_records([_record(COPYING_TEST, COPIED, "mirror")])


def test_the_copy_channel_is_not_a_verdict_channel():
    observed = _observed(copy=[(COPYING_TEST, COPIED)])

    assert observed.verdict_pairs() == frozenset()


# -- the note ----------------------------------------------------------------------


def test_set_aside_reads_and_the_tests_that_made_them_are_counted():
    observed = _observed(
        copy=[
            (COPYING_TEST, COPIED),
            (COPYING_TEST, COPIED_TOO),
            (OTHER_COPYING_TEST, COPIED),
        ]
    )

    note = selection.copy_note(observed, TRACKED)

    assert "3 reads by 2 tests" in note
    assert "copies of the checkout" in note
    assert "not audited" in note


def test_the_note_says_what_the_copying_tests_read_later_is_not_audited():
    note = selection.copy_note(_observed(copy=[(COPYING_TEST, COPIED)]), TRACKED)

    assert "what those tests read later from their copies is not audited" in note


def test_a_pair_read_directly_as_well_is_audited_and_not_counted_as_set_aside():
    observed = _observed(
        direct=[(COPYING_TEST, COPIED)], copy=[(COPYING_TEST, COPIED), (COPYING_TEST, COPIED_TOO)]
    )

    note = selection.copy_note(observed, TRACKED)

    assert (COPYING_TEST, COPIED) in observed.verdict_pairs()
    assert "1 reads by 1 tests" in note


def test_a_pair_read_by_a_child_as_well_is_audited_and_not_counted_as_set_aside():
    observed = _observed(child=[(COPYING_TEST, COPIED)], copy=[(COPYING_TEST, COPIED)])

    assert "none set aside" in selection.copy_note(observed, TRACKED)


def test_a_copy_whose_every_read_was_audited_too_is_not_reported_as_no_copy():
    observed = _observed(direct=[(COPYING_TEST, COPIED)], copy=[(COPYING_TEST, COPIED)])

    note = selection.copy_note(observed, TRACKED)

    assert note == (
        "copies of the checkout: none set aside (every file a copy read was also read"
        " another way, so it was audited), 0 reads by 0 tests"
    )


def test_an_untracked_copied_file_is_not_counted():
    observed = _observed(copy=[(COPYING_TEST, COPIED), (COPYING_TEST, UNTRACKED)])

    assert "1 reads by 1 tests" in selection.copy_note(observed, TRACKED)


def test_a_run_with_no_copy_says_none_was_set_aside_with_zero_reads_by_zero_tests():
    note = selection.copy_note(_observed(direct=[(COPYING_TEST, COPIED)]), TRACKED)

    assert note == (
        "copies of the checkout: none set aside (no test copied the checkout), 0 reads by 0 tests"
    )


# -- the verdict carries the note, passing or failing ------------------------------


@pytest.fixture
def traced(monkeypatch):
    """A run of `selection.run` whose edges are replaced: what was read, what the resolver says."""

    def arrange(observed: selection.ObservedReads, answers: dict[str, selection.Answer]):
        monkeypatch.setattr(selection, "_check_resolver", lambda *_: None)
        monkeypatch.setattr(selection, "_tracked_files", lambda *_: TRACKED)
        monkeypatch.setattr(selection, "_traced_suite", lambda *_: (observed, ()))
        monkeypatch.setattr(selection, "_ask_resolver", lambda *_: answers)
        return selection.run(Path("."), {})

    return arrange


def _selects(*tests: str) -> selection.Answer:
    return selection.Answer(root_selection="tests", tests=frozenset(tests))


def _copy_notes(verdict) -> list[str]:
    return [note for note in verdict.notes if note.startswith("copies of the checkout")]


def test_a_passing_verdict_carries_the_copy_note(traced):
    observed = _observed(
        direct=[(COPYING_TEST, COPIED)],
        copy=[(COPYING_TEST, COPIED_TOO), (COPYING_TEST, "docs/c.txt")],
    )

    verdict = traced(observed, {COPIED: _selects(COPYING_TEST)})

    assert verdict.passed, verdict.reason
    assert [note for note in _copy_notes(verdict) if "2 reads by 1 tests" in note]


def test_a_failing_verdict_carries_the_copy_note_and_judges_the_copying_tests_other_reads(traced):
    observed = _observed(
        direct=[(COPYING_TEST, COPIED)], copy=[(COPYING_TEST, COPIED_TOO), (COPYING_TEST, COPIED)]
    )

    verdict = traced(observed, {COPIED: _selects()})

    assert not verdict.passed
    assert verdict.unselected == ((COPYING_TEST, COPIED),)
    assert [note for note in _copy_notes(verdict) if "1 reads by 1 tests" in note]


def test_a_verdict_of_a_run_with_no_copy_carries_the_none_note(traced):
    verdict = traced(_observed(direct=[(COPYING_TEST, COPIED)]), {COPIED: _selects(COPYING_TEST)})

    assert verdict.passed, verdict.reason
    assert [note for note in _copy_notes(verdict) if "none set aside" in note and "0 reads" in note]
