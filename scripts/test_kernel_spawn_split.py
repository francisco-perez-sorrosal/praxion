"""Tests for kernel_spawn_split.py -- the split text a spawned agent receives for a rule.

The cutter is pure, so most behaviors run over small synthetic rules: what stays around a
dropped part, what goes with a dropped section, and that a fenced heading is no heading. The
artifact is held to the hook's own parser and trust check, and the edge runs over a temporary
repository.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _rule_delivery as rd  # noqa: E402  # pyright: ignore[reportMissingImports]
import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402
import kernel_spawn_split as kss  # noqa: E402

SOURCE = "rules/swe/example.md"
FRONTMATTER = "---\ncore: true\n---\n"


def dropped(heading: str, part: str | None = None) -> km.AudienceEntry:
    return audience(heading, part, km.OrchestratorOnly("only the main session acts on it"))


def kept(heading: str, part: str | None = None) -> km.AudienceEntry:
    return audience(heading, part, km.Core(km.Verbatim()))


def audience(heading: str, part: str | None, scope: km.Scope) -> km.AudienceEntry:
    target = km.PartTarget(SOURCE, heading, part) if part else km.SectionTarget(SOURCE, heading)
    return km.AudienceEntry(target, scope)


def cut(text: str, *entries: km.AudienceEntry) -> str:
    return kss.split_text(text, ks.split_sections(SOURCE, text), entries)


# -- What stays, what goes ------------------------------------------------------------------

TWO_SECTIONS = "# Title\n\nIntro line.\n\n## Keep\n\nKept text.\n\n## Drop\n\nDropped text.\n"


def test_a_dropped_section_goes_from_its_heading_to_the_next_heading() -> None:
    result = cut(TWO_SECTIONS, kept("Keep"), dropped("Drop"))

    assert result == "# Title\n\nIntro line.\n\n## Keep\n\nKept text.\n\n"


def test_a_text_with_nothing_dropped_is_returned_as_it_stands() -> None:
    assert cut(TWO_SECTIONS, kept("Keep"), kept("Drop")) == TWO_SECTIONS


MIXED = "## Mixed\n\nLead sentence.\n\n- **A** first.\n- more of A.\n\n- **B** second.\n\n- **C** third.\n"


def test_a_dropped_part_runs_to_the_next_part_and_the_heading_stays() -> None:
    result = cut(
        MIXED,
        kept("Mixed", "Lead sentence."),
        kept("Mixed", "- **A**"),
        dropped("Mixed", "- **B**"),
        kept("Mixed", "- **C**"),
    )

    assert (
        result == "## Mixed\n\nLead sentence.\n\n- **A** first.\n- more of A.\n\n- **C** third.\n"
    )


def test_a_section_whose_first_part_is_dropped_keeps_its_heading_and_the_lines_before_it() -> None:
    result = cut(
        MIXED,
        dropped("Mixed", "Lead sentence."),
        kept("Mixed", "- **A**"),
        kept("Mixed", "- **B**"),
        kept("Mixed", "- **C**"),
    )

    assert result.startswith("## Mixed\n\n- **A** first.")


def test_a_section_all_of_whose_parts_are_dropped_goes_heading_and_all() -> None:
    text = "## Before\n\nStays.\n\n" + MIXED
    result = cut(
        text,
        kept("Before"),
        dropped("Mixed", "Lead sentence."),
        dropped("Mixed", "- **A**"),
        dropped("Mixed", "- **B**"),
        dropped("Mixed", "- **C**"),
    )

    assert result == "## Before\n\nStays.\n\n"


NESTED = "## Outer\n\nOuter text.\n\n### Inner\n\nInner text.\n\n## After\n\nAfter text.\n"


def test_a_dropped_subsection_leaves_its_parent_and_the_section_after_it() -> None:
    result = cut(NESTED, kept("Outer"), dropped("Inner"), kept("After"))

    assert result == "## Outer\n\nOuter text.\n\n## After\n\nAfter text.\n"


def test_a_heading_inside_a_fence_is_no_section_to_drop() -> None:
    text = "## Fenced\n\n```\n## Drop\n```\n\n## Drop\n\nGone.\n"

    assert cut(text, kept("Fenced"), dropped("Drop")) == "## Fenced\n\n```\n## Drop\n```\n\n"


def test_a_condensed_form_changes_nothing_kept_text_is_source_bytes() -> None:
    condensed = audience("Keep", None, km.Core(km.Condensed("short", "0" * 40)))

    assert cut(TWO_SECTIONS, condensed, kept("Drop")) == TWO_SECTIONS


def test_cutting_twice_gives_the_same_text() -> None:
    entries = (kept("Keep"), dropped("Drop"))

    assert cut(TWO_SECTIONS, *entries) == cut(TWO_SECTIONS, *entries)


def test_sections_that_are_not_the_tail_of_the_body_are_refused() -> None:
    sections = ks.split_sections(SOURCE, TWO_SECTIONS)

    with pytest.raises(kss.SplitCutError):
        kss.split_text(TWO_SECTIONS + "Trailing.\n", sections, (dropped("Drop"),))


# -- The artifact ---------------------------------------------------------------------------

MANIFEST_SHA = "a" * 64


def entry_for(body: str, text: str) -> rd.SplitEntry:
    return rd.SplitEntry(SOURCE, kss.sha256_hex(body), text, kss.sha256_hex(text))


def test_the_artifact_is_sorted_json_ending_in_a_newline() -> None:
    units = {"b/unit": entry_for("whole", "part"), "a/unit": entry_for("whole", "part")}

    rendered = kss.render_spawn_split(MANIFEST_SHA, units)

    assert rendered.endswith("}\n")
    assert list(json.loads(rendered)["units"]) == ["a/unit", "b/unit"]


def test_rendering_twice_gives_the_same_bytes() -> None:
    units = {"a/unit": entry_for("whole", "part")}

    assert kss.render_spawn_split(MANIFEST_SHA, units) == kss.render_spawn_split(
        MANIFEST_SHA, units
    )


def test_the_hook_parses_the_artifact_and_trusts_a_split_cut_for_its_body() -> None:
    entry = entry_for("whole body", "split body")
    rendered = kss.render_spawn_split(MANIFEST_SHA, {"a/unit": entry})

    parsed = rd.parse_spawn_split(rendered)

    assert parsed is not None
    assert rd.spawn_units({"a/unit": "whole body"}, parsed, MANIFEST_SHA) == {
        "a/unit": "split body"
    }


def test_a_sha256_is_over_the_utf8_bytes() -> None:
    assert kss.sha256_hex("é") == hashlib.sha256("é".encode()).hexdigest()
    assert kss.sha256_hex(b"raw") == hashlib.sha256(b"raw").hexdigest()


# -- The edge ---------------------------------------------------------------------------------

UNIT = rd.CoreUnit("swe/example", SOURCE, 1)


def build_repo(root: Path, rule: str = TWO_SECTIONS) -> km.Manifest:
    (root / SOURCE).parent.mkdir(parents=True)
    (root / SOURCE).write_text(FRONTMATTER + rule, encoding="utf-8")
    (root / km.MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / km.MANIFEST_PATH).write_bytes(b"version: 1\n")
    return km.Manifest({}, {}, (), (kept("Keep"), dropped("Drop")))


def test_the_expected_split_is_cut_from_the_body_the_hook_reads(tmp_path: Path) -> None:
    manifest = build_repo(tmp_path)

    result = kss.expected_split(tmp_path, manifest, UNIT)

    assert result is not None
    assert result.whole_sha256 == kss.sha256_hex(TWO_SECTIONS)
    assert result.text == "# Title\n\nIntro line.\n\n## Keep\n\nKept text.\n\n"
    assert result.text_sha256 == kss.sha256_hex(result.text)
    assert result.source == SOURCE


def test_a_unit_with_nothing_to_drop_has_no_split(tmp_path: Path) -> None:
    build_repo(tmp_path)
    manifest = km.Manifest({}, {}, (), (kept("Keep"), kept("Drop")))

    assert kss.expected_split(tmp_path, manifest, UNIT) is None


def test_a_unit_whose_source_is_absent_has_no_split(tmp_path: Path) -> None:
    manifest = km.Manifest({}, {}, (), (dropped("Drop"),))

    assert kss.expected_split(tmp_path, manifest, UNIT) is None


def test_the_artifact_lists_only_the_core_units_that_lose_something(tmp_path: Path) -> None:
    build_repo(tmp_path)
    unit = rd.MANAGED_CORE_UNITS[0]
    (tmp_path / unit.path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / unit.path).write_text(TWO_SECTIONS, encoding="utf-8")
    target = km.SectionTarget(unit.path, "Drop")
    entries = (km.AudienceEntry(target, km.OrchestratorOnly("main only")),)

    artifact = json.loads(kss.spawn_split_artifact(tmp_path, km.Manifest({}, {}, (), entries)))

    assert list(artifact["units"]) == [unit.unit_id]
    assert artifact["manifest_sha256"] == kss.sha256_hex(b"version: 1\n")
