"""A write that grows a memory index past its budget lands, and the session is told.

The guard lets a Write or Edit land when the index it leaves is above 5,000 bytes or
40 lines, larger than before and still inside the load limit, and returns a warning
the writing session reads: the index's bytes and lines after the write, the ceiling,
and that detail belongs in the topic files. A write that ends at or below both limits,
or does not grow the index, draws no warning; every refusal the guard makes today is
unchanged, and a write it cannot judge passes silently.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.memory_index import (
    guard_edit,
    guard_raw,
    guard_write,
    index_lines,
    lengthened,
    names_number,
    sized_index,
    text_of,
)


def _what_the_warning_leaves_out(text: str, total_bytes: int, lines: int) -> list[str]:
    wanted = {
        f"the {total_bytes} bytes after the write": names_number(text, total_bytes),
        f"the {lines} lines after the write": names_number(text, lines),
        "the 5000-byte ceiling": names_number(text, 5_000),
        "the 40-line ceiling": names_number(text, 40),
        "that detail belongs in the topic files": "topic file" in text.lower(),
    }
    return [what for what, said in wanted.items() if not said]


def test_a_write_that_crosses_the_byte_ceiling_lands_and_warns_the_session(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=39, total_bytes=4_990)
    grown = lengthened(index_lines(39, 4_990), 0, 20)

    run = guard_write(home, grown)

    assert run.lets_the_write_land, f"exit {run.exit_code}: {run.stdout}{run.stderr}"
    assert run.session_reads is not None, f"the session reads no warning: {run.stdout!r}"
    missing = _what_the_warning_leaves_out(run.session_reads, 5_010, 39)
    assert missing == [], f"the warning does not say {missing}: {run.session_reads}"


def test_an_edit_that_adds_the_forty_first_line_lands_and_warns_the_session(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=40, total_bytes=2_300)
    last = index_lines(40, 2_300)[-1]
    added = index_lines(1, 60, first=40)[0]

    run = guard_edit(home, last, f"{last}\n{added}")

    assert run.lets_the_write_land, f"exit {run.exit_code}: {run.stdout}{run.stderr}"
    assert run.session_reads is not None, f"the session reads no warning: {run.stdout!r}"
    missing = _what_the_warning_leaves_out(run.session_reads, 2_360, 41)
    assert missing == [], f"the warning does not say {missing}: {run.session_reads}"


def test_a_write_that_ends_exactly_at_the_ceiling_draws_no_warning(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=39, total_bytes=4_990)
    grown = lengthened(index_lines(39, 4_990), 0, 10)

    run = guard_write(home, grown)

    assert len(text_of(grown).encode("utf-8")) == 5_000
    assert run.lets_the_write_land
    assert run.session_reads is None, run.session_reads


def test_a_write_that_shrinks_an_index_still_over_the_ceiling_draws_no_warning(
    tmp_path: Path,
) -> None:
    home = sized_index(tmp_path, lines=45, total_bytes=6_000)
    shrunk = index_lines(45, 5_900)

    run = guard_write(home, shrunk)

    assert run.lets_the_write_land
    assert run.session_reads is None, run.session_reads


def test_a_growing_write_well_under_the_ceiling_draws_no_warning(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=20, total_bytes=2_000)
    grown = lengthened(index_lines(20, 2_000), 3, 40)

    run = guard_write(home, grown)

    assert run.lets_the_write_land
    assert run.stdout.strip() == "", run.stdout


def test_a_write_adding_an_over_long_line_to_an_index_over_the_ceiling_is_still_refused(
    tmp_path: Path,
) -> None:
    home = sized_index(tmp_path, lines=39, total_bytes=4_990)
    too_long = lengthened(index_lines(39, 4_990), 0, 40)

    run = guard_write(home, too_long)

    assert run.decision == "deny", run.stdout
    assert "150 characters" in (run.reason or ""), run.reason


def test_a_write_past_the_load_limit_is_still_refused(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=190, total_bytes=24_000)
    past = index_lines(190, 25_100)

    run = guard_write(home, past)

    assert run.decision == "deny", run.stdout


def test_a_payload_the_guard_cannot_judge_passes_silently(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=45, total_bytes=6_000)

    run = guard_raw(home, "{not json")

    assert run.exit_code == 0
    assert run.stdout.strip() == ""
