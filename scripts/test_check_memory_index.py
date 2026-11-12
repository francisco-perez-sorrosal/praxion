"""Tests for check_memory_index.py -- the memory-index convention, its audit and its gate.

Every failing finding kind has a canary that feeds the bad shape and asserts the
flag (rules/swe/gate-liveness.md); the controls pin what must stay quiet:
headings, blank lines, and debt already in an index when a write adds nothing
wrong. Every tree is built under tmp_path; no real memory directory is read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from check_memory_index import (
    INDEX_BUDGET,
    LOAD_LIMIT,
    MAX_LINE_CHARS,
    IndexSize,
    added_lines,
    all_indexes,
    audit,
    budget_warning,
    gate_messages,
    line_findings,
    main,
    project_index,
)

LOAD_LINE_CAP = LOAD_LIMIT.lines

POINTER = "- [Short title](topic.md) — when it applies and the one rule"
LONG_POINTER = "- [Long title](topic.md) — " + "x" * MAX_LINE_CHARS


def _memory_dir(tmp_path: Path, index_text: str, topics: tuple[str, ...] = ("topic.md",)) -> Path:
    memory = tmp_path / "memory"
    memory.mkdir()
    for name in topics:
        (memory / name).write_text("---\nname: t\n---\nbody\n", encoding="utf-8")
    index = memory / "MEMORY.md"
    index.write_text(index_text, encoding="utf-8")
    return index


def _kinds(findings) -> list[str]:
    return [f.kind for f in findings]


def test_a_short_pointer_heading_and_blank_line_are_clean() -> None:
    assert line_findings(f"# Memory\n\n{POINTER}\n") == []


def test_canary_a_line_over_the_limit_is_too_long() -> None:
    assert _kinds(line_findings(LONG_POINTER + "\n")) == ["too-long"]


def test_canary_content_in_the_index_is_not_a_pointer() -> None:
    assert _kinds(line_findings("Status: the pipeline merged on Tuesday.\n")) == ["not-a-pointer"]


def test_canary_a_link_to_a_missing_file_dangles(tmp_path: Path) -> None:
    index = _memory_dir(tmp_path, "- [Gone](gone.md) — hook\n", topics=())
    assert _kinds(audit(index)) == ["dangling"]


def test_canary_a_file_linked_twice_is_a_duplicate(tmp_path: Path) -> None:
    index = _memory_dir(tmp_path, f"{POINTER}\n{POINTER}\n")
    assert _kinds(audit(index)) == ["duplicate"]


def test_canary_an_unlinked_topic_file_is_a_dropped_entry(tmp_path: Path) -> None:
    index = _memory_dir(tmp_path, f"{POINTER}\n", topics=("topic.md", "orphan.md"))
    findings = audit(index)
    assert _kinds(findings) == ["unindexed"]
    assert "orphan.md" in findings[0].detail


def test_canary_an_index_past_the_harness_line_cap_is_over_the_load_limit(tmp_path: Path) -> None:
    topics = tuple(f"t{n}.md" for n in range(LOAD_LINE_CAP + 1))
    index_text = "".join(f"- [T{n}](t{n}.md) — hook\n" for n in range(LOAD_LINE_CAP + 1))
    index = _memory_dir(tmp_path, index_text, topics=topics)
    assert _kinds(audit(index)) == ["over-load-limit"]


def _lines_index(count: int) -> str:
    return "".join(f"- [T{n}](t{n}.md) — hook\n" for n in range(count))


def _bytes_index(total_bytes: int) -> str:
    """One long pointer-shaped line (it also trips too-long, which these tests ignore)."""
    head = "- [T](t.md) - "
    return head + "x" * (total_bytes - len(head) - 1) + "\n"


def _size_findings(
    tmp_path: Path, name: str, text: str, topics: tuple[str, ...]
) -> list[tuple[str, str]]:
    """The (kind, severity) of each size finding for an index built in its own subdirectory."""
    root = tmp_path / name
    root.mkdir()
    findings = audit(_memory_dir(root, text, topics=topics))
    return [(f.kind, f.severity) for f in findings if f.kind in ("over-budget", "over-load-limit")]


def test_index_size_counts_lines_and_utf8_bytes() -> None:
    assert IndexSize.of("a\nbé\n") == IndexSize(lines=2, bytes=6)


def test_the_index_budget_is_strictly_below_the_load_limit_on_both_axes() -> None:
    assert INDEX_BUDGET.lines < LOAD_LIMIT.lines
    assert INDEX_BUDGET.bytes < LOAD_LIMIT.bytes


def test_canary_one_byte_over_the_budget_warns_and_exactly_at_it_is_quiet(tmp_path: Path) -> None:
    over, at = _bytes_index(INDEX_BUDGET.bytes + 1), _bytes_index(INDEX_BUDGET.bytes)
    assert IndexSize.of(over).bytes == INDEX_BUDGET.bytes + 1
    assert _size_findings(tmp_path, "over", over, ("t.md",)) == [("over-budget", "warn")]
    assert _size_findings(tmp_path, "at", at, ("t.md",)) == []


def test_canary_one_line_over_the_budget_warns_and_exactly_at_it_is_quiet(tmp_path: Path) -> None:
    over_topics = tuple(f"t{n}.md" for n in range(INDEX_BUDGET.lines + 1))
    over, at = _lines_index(INDEX_BUDGET.lines + 1), _lines_index(INDEX_BUDGET.lines)
    assert _size_findings(tmp_path, "over", over, over_topics) == [("over-budget", "warn")]
    assert _size_findings(tmp_path, "at", at, over_topics[:-1]) == []


def test_the_over_budget_detail_names_lines_bytes_and_the_budget(tmp_path: Path) -> None:
    text = _bytes_index(INDEX_BUDGET.bytes + 1)
    findings = audit(_memory_dir(tmp_path, text, topics=("t.md",)))
    (detail,) = [f.detail for f in findings if f.kind == "over-budget"]
    for phrase in ("1 lines", f"{INDEX_BUDGET.bytes + 1:,} bytes", "40 lines", "5,000 bytes"):
        assert phrase in detail


def test_canary_past_the_load_limit_fails_with_no_second_size_finding(tmp_path: Path) -> None:
    count = LOAD_LIMIT.lines + 1
    topics = tuple(f"t{n}.md" for n in range(count))
    assert _size_findings(tmp_path, "past", _lines_index(count), topics) == [
        ("over-load-limit", "fail")
    ]


def test_budget_warning_fires_when_a_write_grows_the_index_past_the_budget() -> None:
    before, after = _lines_index(INDEX_BUDGET.lines), _lines_index(INDEX_BUDGET.lines + 1)
    message = budget_warning(before, after)
    assert message is not None
    assert "41 lines" in message
    assert "one pointer line per memory; move detail into its topic file" in message


def test_budget_warning_is_quiet_for_a_write_that_ends_exactly_at_the_ceiling() -> None:
    assert budget_warning(_lines_index(10), _lines_index(INDEX_BUDGET.lines)) is None


def test_budget_warning_is_quiet_for_a_write_that_shrinks_an_index_still_above_it() -> None:
    assert budget_warning(_lines_index(60), _lines_index(50)) is None


def test_budget_warning_is_quiet_for_a_write_that_stays_under_the_budget() -> None:
    assert budget_warning(_lines_index(3), _lines_index(4)) is None


def test_budget_warning_leaves_growth_past_the_load_limit_to_the_gate() -> None:
    before = _lines_index(LOAD_LIMIT.lines)
    after = _lines_index(LOAD_LIMIT.lines + 1)
    assert budget_warning(before, after) is None
    assert gate_messages(before, after)


def test_added_lines_is_a_multiset_difference() -> None:
    assert added_lines("a\nb\n", "a\nb\nb\nc\n") == ["b", "c"]


def test_gate_ignores_debt_already_in_the_index() -> None:
    before = f"{LONG_POINTER}\n"
    after = f"{LONG_POINTER}\n- [New](new.md) — a short new entry\n"
    assert gate_messages(before, after) == []


@pytest.mark.parametrize(
    ("added", "expected"),
    [(LONG_POINTER, "characters"), ("Status: merged on Tuesday.", "content in the index")],
)
def test_canary_gate_refuses_what_the_write_adds(added: str, expected: str) -> None:
    messages = gate_messages(f"{POINTER}\n", f"{POINTER}\n{added}\n")
    assert len(messages) == 1
    assert expected in messages[0]


def test_canary_gate_refuses_growth_past_the_load_limit() -> None:
    before = "".join(f"- [T{n}](t{n}.md) — hook\n" for n in range(LOAD_LINE_CAP))
    after = before + "- [One more](more.md) — hook\n"
    assert any("load limit" in m for m in gate_messages(before, after))


def test_gate_allows_shrinking_an_index_already_past_the_limit() -> None:
    before = "".join(f"- [T{n}](t{n}.md) — hook\n" for n in range(LOAD_LINE_CAP + 5))
    after = "".join(f"- [T{n}](t{n}.md) — hook\n" for n in range(LOAD_LINE_CAP + 2))
    assert gate_messages(before, after) == []


def test_project_index_follows_the_harness_directory_naming(tmp_path: Path) -> None:
    index = project_index(Path("/Users/me/dev/my.repo"), tmp_path)
    assert index == tmp_path / "projects" / "-Users-me-dev-my-repo" / "memory" / "MEMORY.md"


def test_all_indexes_finds_project_and_agent_memories(tmp_path: Path) -> None:
    for rel in ("projects/-p/memory/MEMORY.md", "agent-memory/praxion-verifier/MEMORY.md"):
        (tmp_path / rel).parent.mkdir(parents=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    assert [p.relative_to(tmp_path).as_posix() for p in all_indexes(tmp_path)] == [
        "agent-memory/praxion-verifier/MEMORY.md",
        "projects/-p/memory/MEMORY.md",
    ]


def test_canary_cli_exits_one_on_a_failing_index_and_zero_on_a_clean_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = _memory_dir(tmp_path, f"{LONG_POINTER}\n")
    assert main([str(bad), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert [f["kind"] for f in report[str(bad)]] == ["too-long"]

    bad.write_text(f"{POINTER}\n", encoding="utf-8")
    assert main([str(bad)]) == 0


def test_cli_reports_an_unreadable_index_as_an_error(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing" / "MEMORY.md")]) == 2
