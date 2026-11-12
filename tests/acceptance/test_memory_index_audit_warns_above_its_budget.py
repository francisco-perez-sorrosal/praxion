"""The memory-index audit warns once an index passes a fifth of the load limit.

An index above 5,000 bytes or 40 lines, still inside the harness load limit (200
lines, 25,000 bytes), draws exactly one size warning that names its bytes, its lines
and the ceiling, in the text output and in `--json`, and a warning alone exits 0. An
index at or below both draws no size finding; one past the load limit fails as it
does today with no second size warning; every other finding is judged as today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers.memory_index import (
    audit,
    content_kinds,
    index_lines,
    memory_home,
    names_number,
    place_index,
    size_findings,
    sized_index,
)

CEILING_BYTES = 5_000
CEILING_LINES = 40


def _names_index_size_and_ceiling(text: str, total_bytes: int, lines: int) -> list[str]:
    """What the warning text fails to name, of its bytes, its lines and the ceiling."""
    wanted = {
        f"the index's {total_bytes} bytes": total_bytes,
        f"the index's {lines} lines": lines,
        f"the {CEILING_BYTES}-byte ceiling": CEILING_BYTES,
        f"the {CEILING_LINES}-line ceiling": CEILING_LINES,
    }
    return [what for what, value in wanted.items() if not names_number(text, value)]


@pytest.mark.parametrize(
    ("total_bytes", "lines"),
    [pytest.param(5_001, 36, id="one-byte-over"), pytest.param(2_300, 41, id="one-line-over")],
)
def test_an_index_just_over_the_ceiling_draws_one_size_warning_naming_its_size(
    tmp_path: Path, total_bytes: int, lines: int
) -> None:
    home = sized_index(tmp_path, lines=lines, total_bytes=total_bytes)

    run = audit(tmp_path, "--json", str(home.index))

    findings = run.findings_for(home.index)
    sized = size_findings(findings)
    assert run.exit_code == 0, f"a warning alone must exit 0: {run.stdout}{run.stderr}"
    assert [f["severity"] for f in sized] == ["warn"], findings
    missing = _names_index_size_and_ceiling(
        json.dumps(sized[0], ensure_ascii=False), total_bytes, lines
    )
    assert missing == [], f"the size warning does not name {missing}: {sized[0]}"


@pytest.mark.parametrize(
    ("total_bytes", "lines"),
    [
        pytest.param(5_000, 36, id="exactly-the-byte-ceiling"),
        pytest.param(2_300, 40, id="exactly-the-line-ceiling"),
    ],
)
def test_an_index_at_the_ceiling_draws_no_finding(
    tmp_path: Path, total_bytes: int, lines: int
) -> None:
    home = sized_index(tmp_path, lines=lines, total_bytes=total_bytes)

    run = audit(tmp_path, "--json", str(home.index))

    assert run.exit_code == 0
    assert run.findings_for(home.index) == []


def test_the_text_output_carries_the_size_warning(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=36, total_bytes=5_001)

    run = audit(tmp_path, str(home.index))

    assert run.exit_code == 0
    stdout = run.stdout.replace(str(tmp_path.resolve()), "<sandbox>").replace(
        str(tmp_path), "<sandbox>"
    )
    warning_lines = [line for line in stdout.splitlines() if "warn" in line.lower()]
    missing = _names_index_size_and_ceiling("\n".join(warning_lines), 5_001, 36)
    assert warning_lines, f"the text output names no warning:\n{run.stdout}{run.stderr}"
    assert missing == [], f"the text warning does not name {missing}:\n{run.stdout}"


def test_an_index_near_the_load_limit_still_draws_only_one_size_warning(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=150, total_bytes=20_001)

    run = audit(tmp_path, "--json", str(home.index))

    sized = size_findings(run.findings_for(home.index))
    assert run.exit_code == 0
    assert [f["severity"] for f in sized] == ["warn"], sized
    missing = _names_index_size_and_ceiling(json.dumps(sized[0], ensure_ascii=False), 20_001, 150)
    assert missing == [], f"the one size warning does not name {missing}: {sized[0]}"


def test_an_index_past_the_load_limit_fails_with_no_second_size_finding(tmp_path: Path) -> None:
    home = sized_index(tmp_path, lines=190, total_bytes=25_001)

    run = audit(tmp_path, "--json", str(home.index))

    sized = size_findings(run.findings_for(home.index))
    assert run.exit_code == 1
    assert [f["severity"] for f in sized] == ["fail"], sized


def test_every_index_under_the_config_directory_is_judged_with_all(tmp_path: Path) -> None:
    grown = sized_index(tmp_path, lines=36, total_bytes=5_001, project_key="-work-grown")
    lean = sized_index(tmp_path, lines=12, total_bytes=1_200, project_key="-work-lean")

    run = audit(tmp_path, "--all", "--json")

    assert run.exit_code == 0
    assert [f["severity"] for f in size_findings(run.findings_for(grown.index))] == ["warn"]
    assert run.findings_for(lean.index) == []


def test_a_content_finding_is_still_reported_beside_the_size_warning(tmp_path: Path) -> None:
    home = memory_home(tmp_path)
    place_index(home, index_lines(36, 5_001))
    (home.memory_dir / "orphan_topic.md").write_text("No line links here.\n", encoding="utf-8")

    run = audit(tmp_path, "--json", str(home.index))

    findings = run.findings_for(home.index)
    assert content_kinds(findings) == ["unindexed"], findings
    assert [f["severity"] for f in size_findings(findings)] == ["warn"], findings
