"""Canaries for I6 (fresh pins), I7 (no resident text in a kernel) and I8 (no stale kernel)."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kernel_checker_testkit as kit  # noqa: E402
import check_kernel_manifest as cb  # noqa: E402
import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402
from _kernel_checker_testkit import (  # noqa: E402
    PROBE_SECTION,
    UNIFIED_RULE,
    append,
    edit_index,
    kinds,
    subjects,
)

# pytest finds a fixture by name in the module that uses it
repo = kit.repo
template = kit.template

# -- I6: a condensed form's pin matches its source --------------------------------------------


def entry_where(
    root: Path, wanted: Callable[[km.AudienceEntry], bool]
) -> tuple[km.AudienceEntry, str]:
    """The first manifest entry `wanted` accepts, with the source bytes it covers."""
    evidence = cb.gather(root)
    texts = km.entry_texts(evidence.manifest, evidence.sections)
    entry = next(e for e in evidence.manifest.entries if e in texts and wanted(e))
    return entry, texts[entry]


def amend_source(root: Path, entry: km.AudienceEntry, covered: str) -> None:
    """Add a word to the last line of the source text `entry` covers."""
    path = root / entry.target.source
    stripped = covered.rstrip("\n")
    path.write_text(
        path.read_text(encoding="utf-8").replace(stripped, f"{stripped} Amended.", 1),
        encoding="utf-8",
    )


def is_authored_condensation(entry: km.AudienceEntry) -> bool:
    form = entry.form
    return isinstance(form, km.Condensed) and form.text_ref not in gk.BLOCK_TEXTS


def test_a_condensed_form_whose_source_changed_since_it_was_pinned_is_stale(repo: Path) -> None:
    entry, covered = entry_where(repo, is_authored_condensation)
    amend_source(repo, entry, covered)

    assert subjects(repo, "I6-stale-pin") == [f"{entry.target.source} '{entry.target.heading}'"]


def test_a_source_changed_where_the_form_is_verbatim_needs_no_pin(repo: Path) -> None:
    entry, covered = entry_where(repo, lambda e: isinstance(e.form, km.Verbatim))
    amend_source(repo, entry, covered)

    assert subjects(repo, "I6-stale-pin") == []


# -- I7: nothing the main session keeps resident reaches a spawn ---------------------------------


def resident_text(root: Path, scope: type) -> tuple[km.AudienceEntry, str]:
    return entry_where(root, lambda e: isinstance(e.scope, scope))


@pytest.mark.parametrize("scope", [km.OrchestratorOnly, km.NoActor])
def test_resident_text_added_to_a_committed_kernel_is_reported_with_its_section(
    repo: Path, scope: type
) -> None:
    entry, covered = resident_text(repo, scope)
    append(repo, f"{gk.KERNELS_DIR}/core.md", "\n" + covered)

    found = [f for f in cb.check(repo) if f.kind == "I7-resident-text-in-kernel"]

    assert [f.subject for f in found] == [f"{gk.KERNELS_DIR}/core.md"]
    assert entry.target.heading in found[0].detail


def test_resident_text_added_to_an_injected_string_is_reported_with_its_role(repo: Path) -> None:
    _, covered = resident_text(repo, km.OrchestratorOnly)

    def leak(index: dict) -> None:
        strings = index["roles"]["sentinel"]["strings"]
        strings[0] = strings[0] + "\n\n" + covered

    edit_index(repo, leak)

    assert f"{km.INDEX_PATH} sentinel string 1" in subjects(repo, "I7-resident-text-in-kernel")


def test_a_heading_shared_with_a_resident_section_is_not_its_text(repo: Path) -> None:
    entry, _ = resident_text(repo, km.OrchestratorOnly)
    append(repo, f"{gk.KERNELS_DIR}/core.md", f"\n## {entry.target.heading}\n")

    assert subjects(repo, "I7-resident-text-in-kernel") == []


# -- I8: no kernel is stale ----------------------------------------------------------------------


def test_a_rule_edit_nobody_regenerated_leaves_the_kernels_stale(repo: Path) -> None:
    entry, covered = entry_where(
        repo, lambda e: isinstance(e.scope, km.Role) and isinstance(e.form, km.Verbatim)
    )
    amend_source(repo, entry, covered)

    assert f"{gk.KERNELS_DIR}/{entry.scope.module}.md" in subjects(repo, "I8-stale-kernel")


def test_an_index_edited_by_hand_is_stale(repo: Path) -> None:
    edit_index(repo, lambda index: index["roles"]["sentinel"].update(status="trial"))

    assert subjects(repo, "I8-stale-kernel") == [km.INDEX_PATH]


def test_a_definition_whose_block_was_edited_by_hand_is_stale(repo: Path) -> None:
    path = repo / "agents/researcher.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "**Apply the behavioral contract**", "**Apply the behavioural contract**", 1
        ),
        encoding="utf-8",
    )

    assert subjects(repo, "I8-stale-kernel") == ["agents/researcher.md"]


def test_a_kernel_file_no_source_produces_is_stale(repo: Path) -> None:
    (repo / gk.KERNELS_DIR / "stray.md").write_text("A stray kernel.\n", encoding="utf-8")

    assert subjects(repo, "I8-stale-kernel") == [f"{gk.KERNELS_DIR}/stray.md"]


def test_sources_the_generator_cannot_assemble_are_reported_with_its_reason(repo: Path) -> None:
    authored = next(a for a in cb.gather(repo).manifest.authored if a.id == gk.RETURN_TEXT)
    (repo / authored.path).unlink()

    found = [f for f in cb.check(repo) if f.kind == "I8-stale-kernel"]

    assert [f.subject for f in found] == [gk.KERNELS_DIR]
    assert authored.path in found[0].detail


def test_sources_that_fail_the_totality_check_are_reported_once_not_twice(repo: Path) -> None:
    append(repo, UNIFIED_RULE, PROBE_SECTION)

    assert kinds(repo) == {"I1-unclassified"}


def a_line_of_a_multi_line_resident_block(root: Path) -> tuple[km.AudienceEntry, str]:
    """A resident section's line that sits in a list or table, and the entry it belongs to."""
    evidence = cb.gather(root)
    for entry, text in km.entry_texts(evidence.manifest, evidence.sections).items():
        if not isinstance(entry.scope, cb.RESIDENT_SCOPES):
            continue
        for block in re.split(r"\n\s*\n", text):
            lines = [line.strip() for line in block.splitlines()]
            named = (
                [line for line in lines[1:] if cb._names_its_source(line)] if len(lines) > 1 else []
            )
            if named:
                return entry, named[0]
    raise AssertionError("no resident section holds a list or table line that names it")


def test_one_line_of_a_resident_list_or_table_in_a_kernel_is_reported_with_its_section(
    repo: Path,
) -> None:
    entry, line = a_line_of_a_multi_line_resident_block(repo)
    append(repo, f"{gk.KERNELS_DIR}/core.md", "\n" + line + "\n")

    found = [f for f in cb.check(repo) if f.kind == "I7-resident-text-in-kernel"]

    assert [f.subject for f in found] == [f"{gk.KERNELS_DIR}/core.md"]
    assert entry.target.heading in found[0].detail


def test_one_line_of_a_resident_block_in_an_injected_string_is_reported_with_its_role(
    repo: Path,
) -> None:
    _, line = a_line_of_a_multi_line_resident_block(repo)
    edit_index(repo, lambda index: index["roles"]["researcher"]["strings"].append(line))

    assert any("researcher" in s for s in subjects(repo, "I7-resident-text-in-kernel"))


def test_a_rule_of_dashes_or_pipes_names_no_source() -> None:
    assert not cb._names_its_source("| ---------------------- | ---------------------- |")
