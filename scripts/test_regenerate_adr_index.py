"""Tests for regenerate_adr_index.py -- the narrowing marker on the status cell.

Uses synthetic ADR files under `tmp_path` throughout -- never the real corpus.
Mirrors the `_write_adr`/fixture conventions of `test_query_adrs.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import regenerate_adr_index

FRONTMATTER = """---
id: {id}
title: {title}
status: {status}
category: {category}
date: "{date}"
summary: {summary}
tags: [{tags}]
made_by: agent
{extra}---

# Body
"""


def _write_adr(
    decisions_dir: Path,
    filename: str,
    *,
    adr_id: str,
    title: str = "A decision",
    status: str = "accepted",
    category: str = "architectural",
    date: str = "2026-01-01",
    summary: str = "a summary",
    tags: list[str] | None = None,
    superseded_in_part_by: list[str] | None = None,
) -> Path:
    decisions_dir.mkdir(parents=True, exist_ok=True)
    extra = ""
    if superseded_in_part_by:
        narrowing_list = ", ".join(f'"{n}"' for n in superseded_in_part_by)
        extra = f"superseded_in_part_by: [{narrowing_list}]\n"
    body = FRONTMATTER.format(
        id=adr_id,
        title=title,
        status=status,
        category=category,
        date=date,
        summary=summary,
        tags=", ".join(tags or []),
        extra=extra,
    )
    path = decisions_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def decisions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / ".ai-state" / "decisions"
    monkeypatch.setattr(regenerate_adr_index, "DECISIONS_DIR", root)
    monkeypatch.setattr(regenerate_adr_index, "INDEX_PATH", root / "DECISIONS_INDEX.md")
    return root


# -- Narrowing marker on the status cell --------------------------------------


def test_status_cell_carries_narrowing_marker(decisions_dir):
    _write_adr(
        decisions_dir,
        "203-narrowed.md",
        adr_id="dec-203",
        status="accepted",
        superseded_in_part_by=["dec-328"],
    )

    adrs = regenerate_adr_index.collect_adrs()
    index = regenerate_adr_index.generate_index(adrs)

    lines = [line for line in index.splitlines() if line.startswith("| dec-203 ")]
    assert len(lines) == 1
    assert "accepted (narrowed by dec-328)" in lines[0]


def test_unaffected_row_status_cell_unchanged(decisions_dir):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", status="accepted")

    adrs = regenerate_adr_index.collect_adrs()
    index = regenerate_adr_index.generate_index(adrs)

    lines = [line for line in index.splitlines() if line.startswith("| dec-001 ")]
    assert len(lines) == 1
    assert "| accepted |" in lines[0]
    assert "narrowed" not in lines[0].lower()


def test_multiple_narrowing_ids_all_named_in_status_cell(decisions_dir):
    # A record narrowed by more than one later decision -- every narrowing id
    # must be visible in the cell, not just the first.
    _write_adr(
        decisions_dir,
        "231-narrowed.md",
        adr_id="dec-231",
        status="accepted",
        superseded_in_part_by=["dec-232", "dec-999"],
    )

    adrs = regenerate_adr_index.collect_adrs()
    index = regenerate_adr_index.generate_index(adrs)

    lines = [line for line in index.splitlines() if line.startswith("| dec-231 ")]
    assert len(lines) == 1
    assert "dec-232" in lines[0]
    assert "dec-999" in lines[0]


# -- Row count / id set non-regression (DL03) ---------------------------------


def test_row_count_and_id_set_unchanged_versus_no_marker_corpus(decisions_dir):
    # A corpus mixing narrowed and unaffected records renders exactly one row
    # per record -- the marker must not duplicate, drop, or reorder rows.
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", status="accepted")
    _write_adr(
        decisions_dir,
        "203-narrowed.md",
        adr_id="dec-203",
        status="accepted",
        superseded_in_part_by=["dec-328"],
    )
    _write_adr(decisions_dir, "328-narrower.md", adr_id="dec-328", status="accepted")

    adrs = regenerate_adr_index.collect_adrs()
    index = regenerate_adr_index.generate_index(adrs)

    rows = [line for line in index.splitlines() if line.startswith("| dec-")]
    ids_in_rows = [line.split("|")[1].strip() for line in rows]
    assert ids_in_rows == ["dec-001", "dec-203", "dec-328"]
