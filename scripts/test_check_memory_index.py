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
    LOAD_LINE_CAP,
    MAX_LINE_CHARS,
    added_lines,
    all_indexes,
    audit,
    gate_messages,
    line_findings,
    main,
    project_index,
)

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


def test_an_index_near_the_cap_warns_without_failing(tmp_path: Path) -> None:
    count = int(LOAD_LINE_CAP * 0.9)
    topics = tuple(f"t{n}.md" for n in range(count))
    index_text = "".join(f"- [T{n}](t{n}.md) — hook\n" for n in range(count))
    findings = audit(_memory_dir(tmp_path, index_text, topics=topics))
    assert [(f.kind, f.severity) for f in findings] == [("near-load-limit", "warn")]


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
