"""Tests for kernel_sources.py -- finding and cutting the always-loaded guidance.

The reader is the floor under the audience manifest: whatever it fails to find or
cuts differently from the manifest's author is a section nobody classified, or a
pin that never matches. So the cases pin the cuts to exact bytes, and the
discovery cases build repositories in `tmp_path` rather than trusting a list.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = ks.USER_TEMPLATE
ROOT_FILE = ks.PROJECT_INSTRUCTIONS


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _checkout(root: Path) -> Path:
    """A minimal plugin checkout: the user template, the project file, one open rule."""
    _write(root, TEMPLATE, "## Principles\n\nText.\n")
    _write(root, ROOT_FILE, "# Project\n\n## Build\n\nText.\n")
    _write(root, "rules/swe/open-rule.md", "## Open Rule\n\nText.\n")
    return root


def _headings(text: str) -> list[tuple[int, str]]:
    return [(s.level, s.heading) for s in ks.split_sections("x.md", text)]


# -- Sections ------------------------------------------------------------------


def test_headings_of_level_two_to_four_are_sections_and_no_others() -> None:
    text = "# One\n## Two\n### Three\n#### Four\n##### Five\n###### Six\n"

    assert _headings(text) == [(2, "Two"), (3, "Three"), (4, "Four")]


def test_a_hash_line_inside_a_fence_is_not_a_heading() -> None:
    text = (
        "## Real\n\n```bash\n## not a heading\n```\n\n"
        "~~~\n### nor this\n~~~\n\n"
        "````\n```\n## nor this either\n```\n````\n\n"
        "### After\n"
    )

    assert _headings(text) == [(2, "Real"), (3, "After")]


def test_a_section_runs_from_its_heading_to_the_next_heading_of_any_level() -> None:
    text = "intro\n\n## A\n\nbody a\n\n### B\nbody b\n## C\nbody c\n"

    sections = ks.split_sections("x.md", text)

    assert [s.text for s in sections] == [
        "## A\n\nbody a\n\n",
        "### B\nbody b\n",
        "## C\nbody c\n",
    ]


def test_a_heading_carries_its_text_without_hashes_or_a_closing_run() -> None:
    assert _headings("## C# Notes ##\n### Plain  \n") == [(2, "C# Notes"), (3, "Plain")]


def test_yaml_frontmatter_is_not_read_for_headings() -> None:
    text = "---\ndescription: x\n## a yaml comment\n---\n## Real\nbody\n"

    assert _headings(text) == [(2, "Real")]


def test_the_section_sha_is_the_sha1_of_its_bytes_and_is_stable() -> None:
    text = "## A\r\nbody\r\n## B\nother\n"

    first, second = ks.split_sections("x.md", text), ks.split_sections("x.md", text)

    assert first[0].sha == hashlib.sha1(b"## A\r\nbody\r\n").hexdigest()
    assert [s.sha for s in first] == [s.sha for s in second]


def test_one_changed_byte_changes_the_sha() -> None:
    before = ks.split_sections("x.md", "## A\nbody\n")[0]
    after = ks.split_sections("x.md", "## A\nbodY\n")[0]

    assert before.sha != after.sha


# -- Parts ---------------------------------------------------------------------

MIXED = (
    "## Mixed\n\n"
    "Alpha part: for the orchestrator.\nmore alpha\n\n"
    "Beta part: for every role.\n\n"
    "- Gamma part: a list item.\n"
)


def _mixed() -> ks.Section:
    return ks.split_sections("x.md", MIXED)[0]


def test_each_part_runs_from_its_prefix_to_the_next_part_and_the_last_to_the_section_end() -> None:
    parts = ks.split_parts(_mixed(), ["Alpha part:", "Beta part:", "- Gamma part:"])

    assert [p.text for p in parts] == [
        "Alpha part: for the orchestrator.\nmore alpha\n\n",
        "Beta part: for every role.\n\n",
        "- Gamma part: a list item.\n",
    ]


def test_parts_come_back_in_document_order_whatever_the_order_asked() -> None:
    parts = ks.split_parts(_mixed(), ["Beta part:", "Alpha part:"])

    assert [p.prefix for p in parts] == ["Alpha part:", "Beta part:"]


def test_text_between_the_heading_and_the_first_part_is_a_leading_part() -> None:
    section = ks.split_sections("x.md", "## S\n\nlead text\n\nAlpha: a\n")[0]

    parts = ks.split_parts(section, ["Alpha:"])

    assert [p.prefix for p in parts] == [None, "Alpha:"]
    assert parts[0].text == "## S\n\nlead text\n\n"


def test_a_heading_followed_only_by_blank_lines_has_no_leading_part() -> None:
    parts = ks.split_parts(_mixed(), ["Alpha part:"])

    assert [p.prefix for p in parts] == ["Alpha part:"]


def test_a_part_sha_covers_the_part_bytes_alone() -> None:
    part = ks.split_parts(_mixed(), ["Beta part:"])[-1]

    assert part.sha == hashlib.sha1(part.text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    ("prefix", "kind"),
    [("Delta part:", "absent"), ("Alpha", "ambiguous")],
)
def test_a_prefix_that_is_absent_or_not_unique_is_refused_by_name(prefix: str, kind: str) -> None:
    section = ks.split_sections("x.md", "## S\nAlpha one\nAlpha two\n")[0]

    with pytest.raises(ks.PartPrefixError, match=prefix) as refusal:
        ks.split_parts(section, [prefix])

    assert refusal.value.kind == kind


# -- Which files are always loaded ---------------------------------------------


def test_a_rule_without_frontmatter_is_always_loaded() -> None:
    assert not ks.is_path_scoped("## Rule\n\nText.\n")


def test_frontmatter_without_a_paths_key_is_still_always_loaded() -> None:
    assert not ks.is_path_scoped("---\ndescription: x\nnote:\n  paths: nested\n---\n## R\n")


@pytest.mark.parametrize(
    "frontmatter",
    ["paths:\n- '**/*.py'\n", "paths: ['**/*.py']\n", '"paths": "**/*.py"\n', "paths : x\n"],
)
def test_a_paths_key_in_the_frontmatter_scopes_the_rule(frontmatter: str) -> None:
    assert ks.is_path_scoped(f"---\n{frontmatter}---\n## R\n")


@pytest.mark.parametrize(
    "text",
    [
        "---\ndescription: x\n---\npaths: in the body\n",
        "## R\n\nSome text\npaths: not frontmatter\nmore\n",
        "---\npaths: an unclosed block is not frontmatter\n## R\n",
    ],
)
def test_a_paths_line_outside_closed_frontmatter_scopes_nothing(text: str) -> None:
    assert not ks.is_path_scoped(text)


def test_discovery_takes_unscoped_rules_the_template_and_the_project_file(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    _write(root, "rules/swe/scoped.md", "---\npaths:\n- '**/*.py'\n---\n## Scoped\n")
    _write(root, "rules/writing/deep/nested-rule.md", "## Nested\n")

    assert ks.always_loaded_sources(root) == (
        "rules/swe/open-rule.md",
        "rules/writing/deep/nested-rule.md",
        TEMPLATE,
        ROOT_FILE,
    )


def test_a_new_unscoped_rule_is_found_without_editing_any_list(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    before = ks.always_loaded_sources(root)

    _write(root, "rules/ml/brand-new.md", "## Brand New\n")

    assert set(ks.always_loaded_sources(root)) - set(before) == {"rules/ml/brand-new.md"}


def test_directory_guides_are_not_rules(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    _write(root, "rules/CLAUDE.md", "## Guide\n")
    _write(root, "rules/README.md", "## Catalog\n")
    _write(root, "rules/swe/README.md", "## Catalog\n")

    assert ks.always_loaded_sources(root) == ("rules/swe/open-rule.md", TEMPLATE, ROOT_FILE)


def test_the_user_template_is_read_never_its_render(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    _write(root, "claude/config/CLAUDE.md", "## Rendered\n")

    assert "claude/config/CLAUDE.md" not in ks.always_loaded_sources(root)
    assert TEMPLATE in ks.always_loaded_sources(root)


def test_a_managed_projects_instruction_file_is_never_classified(tmp_path: Path) -> None:
    _write(tmp_path, ROOT_FILE, "## Managed Project Section\n")
    _write(tmp_path, "rules/own-rule.md", "## Own Rule\n")

    with pytest.raises(ks.NotAPluginCheckoutError, match=str(tmp_path)):
        ks.always_loaded_sources(tmp_path)


def test_a_source_is_read_as_the_bytes_on_disk(tmp_path: Path) -> None:
    _write(tmp_path, "rules/a.md", "## A\r\nbody\r\n")

    (section,) = ks.load_sections(tmp_path, "rules/a.md")

    assert section.text == "## A\r\nbody\r\n"
    assert section.source == "rules/a.md"


# -- The repository as committed -----------------------------------------------


def test_the_repository_yields_its_known_sources_and_cuts_each_into_sections() -> None:
    sources = ks.always_loaded_sources(REPO_ROOT)

    assert "rules/swe/agent-behavioral-contract.md" in sources
    assert TEMPLATE in sources
    assert ROOT_FILE in sources
    assert "rules/swe/coding-style.md" not in sources, "a path-scoped rule was taken"
    assert "rules/CLAUDE.md" not in sources, "a directory guide was taken"
    assert all(ks.load_sections(REPO_ROOT, source) for source in sources)
