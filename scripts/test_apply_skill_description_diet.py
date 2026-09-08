"""Tests for apply_skill_description_diet.py -- the P1.12 table-driven diet applier.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input, here an over-length table row and a check-mode
mismatch, not just that a clean table applies.
"""

from __future__ import annotations

from pathlib import Path

import apply_skill_description_diet as diet
import pytest
import yaml


def _skill(root: Path, name: str, description_block: str, *, body: str = "Body.\n") -> Path:
    path = root / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: {description_block}\nallowed-tools: [Read]\n---\n{body}",
        encoding="utf-8",
    )
    return path


def _table(root: Path, mapping: dict[str, str]) -> Path:
    path = root / "table.yaml"
    path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    return path


# -- replace_description() ----------------------------------------------------


def test_replace_description_rewrites_a_folded_block_scalar(tmp_path: Path) -> None:
    text = (
        "---\nname: foo\ndescription: >\n  Old description spanning\n"
        "  multiple lines. Triggers: bar, baz.\nallowed-tools: [Read]\n---\nBody.\n"
    )

    new_text = diet.replace_description(text, "New short description. Triggers: bar, baz.")

    assert 'description: "New short description. Triggers: bar, baz."' in new_text
    assert "allowed-tools: [Read]" in new_text
    assert new_text.endswith("Body.\n")
    assert "Old description" not in new_text


def test_replace_description_raises_without_a_description_field(tmp_path: Path) -> None:
    text = "---\nname: foo\nallowed-tools: [Read]\n---\nBody.\n"

    with pytest.raises(ValueError, match="no description"):
        diet.replace_description(text, "New description.")


# -- apply_table(): apply / idempotency ----------------------------------------


def test_apply_rewrites_the_description_from_the_table(tmp_path: Path) -> None:
    _skill(tmp_path, "foo", ">\n  Old long description. Triggers: bar, baz.")
    table = {"foo": "New short description. Triggers: bar, baz."}

    changed, findings = diet.apply_table(table, tmp_path / "skills", check=False, dry_run=False)

    assert findings == []
    assert changed == 1
    assert diet.current_description(tmp_path / "skills" / "foo" / "SKILL.md") == table["foo"]


def test_apply_is_idempotent_on_a_second_run(tmp_path: Path) -> None:
    _skill(tmp_path, "foo", ">\n  Old long description. Triggers: bar, baz.")
    table = {"foo": "New short description. Triggers: bar, baz."}
    diet.apply_table(table, tmp_path / "skills", check=False, dry_run=False)

    changed, findings = diet.apply_table(table, tmp_path / "skills", check=False, dry_run=False)

    assert changed == 0
    assert findings == []


def test_apply_reports_a_missing_skill_as_a_finding(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    table = {"absent": "Some description."}

    changed, findings = diet.apply_table(table, tmp_path / "skills", check=False, dry_run=False)

    assert changed == 0
    assert len(findings) == 1
    assert "absent" in findings[0]


# -- --check mode ---------------------------------------------------------------


def test_check_detects_drift_before_apply(tmp_path: Path) -> None:
    _skill(tmp_path, "foo", ">\n  Old long description. Triggers: bar, baz.")
    table = {"foo": "New short description. Triggers: bar, baz."}

    _, findings_before = diet.apply_table(table, tmp_path / "skills", check=True, dry_run=False)
    diet.apply_table(table, tmp_path / "skills", check=False, dry_run=False)
    _, findings_after = diet.apply_table(table, tmp_path / "skills", check=True, dry_run=False)

    assert len(findings_before) == 1
    assert "differs from the table" in findings_before[0]
    assert findings_after == []


def test_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _skill(tmp_path, "foo", ">\n  Old long description. Triggers: bar, baz.")
    original = path.read_text(encoding="utf-8")
    table = {"foo": "New short description. Triggers: bar, baz."}

    changed, findings = diet.apply_table(table, tmp_path / "skills", check=False, dry_run=True)

    assert changed == 0
    assert findings == []
    assert path.read_text(encoding="utf-8") == original
    assert "New short description" in capsys.readouterr().out


# -- load_table(): the over-300-char rejection ----------------------------------


def test_load_table_accepts_an_over_300_char_row(tmp_path: Path) -> None:
    """PM-7 (trigger-noun preservation) outranks the per-skill 300-char
    target -- an over-length row is a reported finding, not a hard block."""
    table_path = _table(tmp_path, {"foo": "x" * 301})

    table = diet.load_table(table_path)

    assert table == {"foo": "x" * 301}
    assert diet.over_cap_names(table) == ["foo"]


def test_load_table_accepts_a_row_at_exactly_300_chars(tmp_path: Path) -> None:
    table_path = _table(tmp_path, {"foo": "x" * 300})

    table = diet.load_table(table_path)

    assert table == {"foo": "x" * 300}


# -- main(): CLI exit codes -----------------------------------------------------


def test_main_exit_2_on_a_non_string_table_value(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    table_path = tmp_path / "table.yaml"
    table_path.write_text("foo: 123\n", encoding="utf-8")

    exit_code = diet.main(["--table", str(table_path), "--repo-root", str(tmp_path)])

    assert exit_code == 2


def test_main_reports_over_cap_rows_without_blocking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tmp_path, "foo", ">\n  Old description.")
    table_path = _table(tmp_path, {"foo": "x" * 301})

    exit_code = diet.main(["--table", str(table_path), "--repo-root", str(tmp_path)])

    assert exit_code == 0
    assert "INFO -- foo is 301 chars" in capsys.readouterr().out


def test_main_exit_0_on_an_empty_table(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    table_path = _table(tmp_path, {})

    exit_code = diet.main(["--table", str(table_path), "--repo-root", str(tmp_path)])

    assert exit_code == 0


def test_main_exit_1_on_check_mode_drift(tmp_path: Path) -> None:
    _skill(tmp_path, "foo", ">\n  Old long description. Triggers: bar, baz.")
    table_path = _table(tmp_path, {"foo": "New short description. Triggers: bar, baz."})

    exit_code = diet.main(["--table", str(table_path), "--repo-root", str(tmp_path), "--check"])

    assert exit_code == 1
