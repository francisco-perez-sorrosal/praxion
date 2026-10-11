"""Behavioral tests for `skills/skill-crafting/scripts/frontmatter_contract.py`.

The contract is the one source of the frontmatter keys a skill may carry and of the name rules.
These tests pin its invariants (disjoint tiers, required keys inside the portable core, the
accepted set as their union), the messages `name_errors` gives, its freedom from import side
effects, and its parity with the schema reference that documents the same fields for authors.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

# ---------------------------------------------------------------------------
# Paths + module under test
# ---------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent.parent  # .../praxion/
CONTRACT = REPO_ROOT / "skills" / "skill-crafting" / "scripts" / "frontmatter_contract.py"
SCHEMA = REPO_ROOT / "skills" / "skill-crafting" / "references" / "schema.md"


def _load_contract() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_frontmatter_contract_under_test", CONTRACT)
    assert spec is not None, f"cannot load {CONTRACT}"
    assert spec.loader is not None, f"cannot load {CONTRACT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = _load_contract()

# ---------------------------------------------------------------------------
# The schema reference, read the way the acceptance driver reads it: field headings
# (### `field`) and table rows whose first cell is a backticked field, outside fenced
# blocks and before the first level-2 heading naming validation.
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*(```|~~~)")
_FIELD_HEADING = re.compile(r"^###\s+`([\w-]+)`")
_FIELD_ROW = re.compile(r"^\|\s*`([\w-]+)`\s*\|")
_VALIDATION_H2 = re.compile(r"^##\s+.*validat", re.I)


def _schema_lines_before_validation() -> list[str]:
    lines, inside = [], False
    for line in SCHEMA.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            inside = not inside
            continue
        if inside:
            continue
        if _VALIDATION_H2.match(line):
            break
        lines.append(line)
    return lines


def _schema_heading_fields() -> set[str]:
    return {m.group(1) for m in map(_FIELD_HEADING.match, _schema_lines_before_validation()) if m}


def _schema_fields() -> set[str]:
    rows = {m.group(1) for m in map(_FIELD_ROW.match, _schema_lines_before_validation()) if m}
    return _schema_heading_fields() | rows


# ---------------------------------------------------------------------------
# Field-set invariants
# ---------------------------------------------------------------------------

TIERS = {
    "open standard": contract.OPEN_STANDARD_FIELDS,
    "Claude Code": contract.CLAUDE_CODE_FIELDS,
    "Praxion": contract.PRAXION_FIELDS,
}


@pytest.mark.parametrize(
    ("first", "second"),
    [("open standard", "Claude Code"), ("open standard", "Praxion"), ("Claude Code", "Praxion")],
)
def test_no_field_belongs_to_two_tiers(first: str, second: str) -> None:
    assert not TIERS[first] & TIERS[second]


def test_required_fields_are_part_of_the_open_standard() -> None:
    assert contract.REQUIRED_FIELDS == {"name", "description"}
    assert contract.REQUIRED_FIELDS <= contract.OPEN_STANDARD_FIELDS


def test_accepted_fields_are_exactly_the_union_of_the_three_tiers() -> None:
    union = contract.OPEN_STANDARD_FIELDS | contract.CLAUDE_CODE_FIELDS | contract.PRAXION_FIELDS

    assert contract.ACCEPTED_FIELDS == union
    assert len(contract.ACCEPTED_FIELDS) == 22


@pytest.mark.parametrize("field", ["background", "disallowed-tools"])
def test_claude_code_tier_carries_the_fields_documented_since_the_last_refresh(field: str) -> None:
    assert field in contract.CLAUDE_CODE_FIELDS


# ---------------------------------------------------------------------------
# name_errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["a", "skill-crafting", "a1-b2-c3", "x" * 64])
def test_a_valid_name_draws_no_error(name: str) -> None:
    assert contract.name_errors(name) == ()


def test_consecutive_hyphens_draw_one_message_naming_only_that_defect() -> None:
    assert contract.name_errors("a--b") == (
        "'name' must not contain consecutive hyphens (got 'a--b')",
    )


def test_a_name_over_the_length_limit_draws_a_length_message() -> None:
    assert contract.name_errors("a" * 65) == ("'name' exceeds 64 chars (got 65)",)


@pytest.mark.parametrize("name", ["Skill", "-skill", "skill-", "1skill", "skill\n"])
def test_a_name_breaking_the_pattern_draws_the_pattern_message(name: str) -> None:
    assert contract.name_errors(name) == (
        f"'name' must be lowercase letters/digits/hyphens, no consecutive "
        f"hyphens, no leading/trailing hyphens (got {name!r})",
    )


def test_a_name_breaking_two_rules_draws_one_message_per_rule_in_order() -> None:
    errors = contract.name_errors("A--b")

    assert [e.split(" (got")[0] for e in errors] == [
        "'name' must not contain consecutive hyphens",
        "'name' must be lowercase letters/digits/hyphens, no consecutive "
        "hyphens, no leading/trailing hyphens",
    ]


# ---------------------------------------------------------------------------
# Import has no side effect
# ---------------------------------------------------------------------------

_IMPORT_PROBE = """
import importlib.util, sys
before = set(sys.modules)
spec = importlib.util.spec_from_file_location("frontmatter_contract", sys.argv[1])
spec.loader.exec_module(importlib.util.module_from_spec(spec))
print(sorted(m for m in set(sys.modules) - before if m.split(".")[0] not in sys.stdlib_module_names))
"""


def test_importing_the_contract_prints_nothing_and_loads_only_the_standard_library(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-c", _IMPORT_PROBE, str(CONTRACT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[]\n", f"non-stdlib modules or output on import: {result.stdout!r}"
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Parity with the schema reference
# ---------------------------------------------------------------------------


def test_accepted_fields_equal_the_fields_the_schema_reference_lists() -> None:
    assert contract.ACCEPTED_FIELDS == _schema_fields()


def test_open_standard_fields_equal_the_field_headings_of_the_schema_reference() -> None:
    assert contract.OPEN_STANDARD_FIELDS == _schema_heading_fields()
