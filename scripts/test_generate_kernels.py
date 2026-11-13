"""Tests for generate_kernels.py -- the kernels each role receives, assembled from the manifest.

Behaviors over a synthetic repository (so no test depends on what the rules say today): what
is rendered and what is withheld, the universal blocks in the core, parts and packing, roles,
the index and its principles file, determinism, `--check` writing nothing, and the spawn split.
The checks over the real repository are in `test_generate_kernels_live.py`, the rewriting of
agent definitions and the preamble in `test_generate_kernels_definitions.py`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _generate_kernels_testkit as kit  # noqa: E402
import _rule_delivery as rd  # noqa: E402  # pyright: ignore[reportMissingImports]
import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402
import kernel_spawn_split as kss  # noqa: E402
from _generate_kernels_testkit import (  # noqa: E402
    CAP,
    CONDENSED_RULE,
    CONTRACT_RULE,
    LINKS_TEXT,
    LONG_SOURCE,
    RETURN_TEXT,
    SHARED_RULE,
    SHARED_SOURCE_TEXT,
    TEMPLATE,
    TEMPLATE_TEXT,
    authored_row,
    build_repo,
    core,
    disk_state,
    entry,
    kernel_texts,
    manifest_rows,
    run,
    write,
)

repo = kit.repo


# -- What is rendered, and what is withheld -----------------------------------------------


def test_verbatim_text_is_the_source_bytes_and_condensed_text_is_the_authored_form(
    repo: Path,
) -> None:
    run(repo)
    core_text = kernel_texts(repo)["core.md"]

    assert "Shared text for every agent." in core_text
    assert "The short form." in core_text
    assert "The long source that a short form stands for." not in core_text


def test_orchestrator_only_and_no_actor_text_reaches_no_kernel(repo: Path) -> None:
    run(repo)
    everything = "\n".join(kernel_texts(repo).values()) + (repo / km.INDEX_PATH).read_text()

    withheld = ["Secret orchestrator", "Intro that points", "Tail about commit", "User-level text"]

    assert [text for text in withheld if text in everything] == []


def test_a_kernel_only_text_lands_in_the_module_its_authored_row_names(tmp_path: Path) -> None:
    rows = manifest_rows()
    rows["modules"] = {"local-reader": {"audience": ["reader"]}}
    rows["authored"].append(authored_row("reader-note", "local-reader"))
    root = build_repo(tmp_path / "plugin", manifest=rows)
    write(root, "claude/kernels/src/reader-note.md", "A note for the reader alone.\n")

    run(root)

    assert kernel_texts(root)["local-reader.md"] == "A note for the reader alone.\n"
    assert "A note for the reader" not in kernel_texts(root)["core.md"]
    assert gk.plan_kernels(root).assembled_kernel("reader").modules == ("core", "local-reader")


def test_the_core_is_the_three_blocks_then_the_rest(repo: Path) -> None:
    run(repo)
    texts = kernel_texts(repo)

    assert (
        texts["core-blocks.md"]
        == "\n\n".join(
            [
                f"{gk.CONTRACT_LEAD_IN}\n"
                "- **Alpha** - first behavior.\n- **Beta** - second behavior.\n"
                "Self-test: did I follow the contract?",
                LINKS_TEXT,
                RETURN_TEXT,
            ]
        )
        + "\n"
    )
    assert texts["core.md"].startswith(texts["core-blocks.md"] + "\n")
    assert texts["core.md"].count(LINKS_TEXT) == texts["core.md"].count(RETURN_TEXT) == 1


def test_a_core_without_the_contract_is_refused(tmp_path: Path, capsys) -> None:
    rows = manifest_rows()
    rows["entries"][1] = entry(
        CONTRACT_RULE, "Agent Behavioral Contract", "no-actor", part="- **Alpha**"
    )
    root = build_repo(tmp_path / "plugin", manifest=rows)

    assert run(root) == 2
    assert "no behavioral contract" in capsys.readouterr().err
    assert not (root / gk.KERNELS_DIR / "core.md").exists()


def test_a_declared_module_that_places_no_text_is_refused(tmp_path: Path, capsys) -> None:
    rows = manifest_rows()
    rows["modules"] = {"hollow": {"audience": ["reader"]}}
    root = build_repo(tmp_path / "plugin", manifest=rows)

    assert run(root) == 2
    assert "'hollow' has no text" in capsys.readouterr().err


def test_a_section_with_no_entry_is_refused_and_nothing_is_written(repo: Path) -> None:
    write(repo, SHARED_RULE, SHARED_SOURCE_TEXT + "\n## Newcomer\n\nNo entry yet.\n")

    assert run(repo) == 2
    assert not (repo / gk.KERNELS_DIR / "core.md").exists()


def test_a_stale_pin_does_not_stop_generation_because_the_checker_holds_the_pins(
    repo: Path,
) -> None:
    write(repo, CONDENSED_RULE, LONG_SOURCE + "\nA new sentence.\n")

    assert run(repo) == 0
    assert "The short form." in kernel_texts(repo)["core.md"]


# -- Parts and packing ------------------------------------------------------------------


def padded_repo(tmp_path: Path, paragraphs: int = 100) -> Path:
    padding = "\n\n".join(f"Padding {i:03d}: " + "core text " * 12 for i in range(paragraphs))
    rows = manifest_rows()
    rows["entries"].append(core(SHARED_RULE, "Padding"))
    root = build_repo(tmp_path / "plugin", manifest=rows)
    write(root, SHARED_RULE, SHARED_SOURCE_TEXT + f"\n## Padding\n\n{padding}\n")
    return root


def test_a_module_above_the_cap_arrives_as_ordered_parts_that_rebuild_it(tmp_path: Path) -> None:
    root = padded_repo(tmp_path)

    run(root)
    texts = kernel_texts(root)
    parts = [
        texts[name] for name in sorted(texts) if name.startswith("core-") and name[5].isdigit()
    ]
    module = gk.assemble(*_assembled_inputs(root)).modules["core"]

    assert "core.md" not in texts
    assert len(parts) >= 2
    assert "".join(parts) == module
    assert all(len(part) <= CAP for part in parts)
    assert all(line in parts[0] for line in ("Self-test: did I follow the contract?",))


def core_parts(texts: Mapping[str, str]) -> list[str]:
    return [texts[name] for name in sorted(texts) if name.startswith("core-") and name[5].isdigit()]


def _assembled_inputs(root: Path):
    definitions = km.agent_definitions(root)
    manifest = km.load_manifest(root, definitions)
    sections = gk._load_sections(root, manifest)
    return manifest, sections, gk._read_authored(root, manifest)


def test_a_part_never_ends_in_a_blank_line_and_the_next_one_opens_with_it(tmp_path: Path) -> None:
    run(padded_repo(tmp_path))
    parts = core_parts(kernel_texts(tmp_path / "plugin"))

    assert [part.endswith("\n\n") for part in parts] == [False] * len(parts)
    assert [part.startswith("\n") for part in parts[1:]] == [True] * (len(parts) - 1)


def test_a_paragraph_longer_than_the_cap_cannot_be_split(tmp_path: Path, capsys) -> None:
    root = padded_repo(tmp_path, paragraphs=1)
    write(root, SHARED_RULE, SHARED_SOURCE_TEXT + "\n## Padding\n\n" + "x " * CAP + "\n")

    assert run(root) == 2
    assert "exceeds" in capsys.readouterr().err


def test_a_cut_never_falls_inside_a_code_fence() -> None:
    fenced = "intro\n\n```\ncode\n\nmore code\n```\n\noutro\n"

    assert gk.paragraph_atoms(fenced) == ["intro\n", "\n```\ncode\n\nmore code\n```\n", "\noutro\n"]


@pytest.mark.parametrize(
    "text",
    ["one\n", "a\n\nb\n", "a\n\n\n\nb\n\nc\n", "a  \n\nb\n", "- x\n- y\n\n- z\n"],
    ids=["single", "two", "blank runs", "trailing spaces", "list"],
)
def test_atoms_always_concatenate_back_to_the_text(text: str) -> None:
    assert "".join(gk.paragraph_atoms(text)) == text


def big_module_repo(tmp_path: Path, words: int) -> Path:
    rows = manifest_rows()
    rows["entries"].append(entry(SHARED_RULE, "Big", "role", form="verbatim", agents=["writer"]))
    root = build_repo(tmp_path / "plugin", manifest=rows)
    write(root, SHARED_RULE, SHARED_SOURCE_TEXT + "\n## Big\n\n" + "w " * words + "\n")
    return root


def test_modules_that_fit_together_share_one_string(tmp_path: Path) -> None:
    writer = gk.plan_kernels(big_module_repo(tmp_path, words=3000)).assembled_kernel("writer")

    assert [s.module for s in writer.strings] == ["core+writer"]


def test_a_module_that_does_not_fit_beside_the_core_starts_the_next_string_whole(
    tmp_path: Path,
) -> None:
    writer = gk.plan_kernels(big_module_repo(tmp_path, words=4950)).assembled_kernel("writer")

    assert [s.module for s in writer.strings] == ["core", "writer"]
    assert [len(s.text) <= CAP for s in writer.strings] == [True, True]


# -- Roles ------------------------------------------------------------------------------


def test_a_role_holds_the_core_and_exactly_the_modules_that_name_it(repo: Path) -> None:
    plan = gk.plan_kernels(repo)

    assert plan.assembled_kernel("writer").modules == ("core", "writer")
    assert plan.assembled_kernel("reader").modules == ("core",)
    assert "Duty text for the writer." not in plan.assembled_kernel("reader").strings[0].text


def test_the_first_injected_string_opens_with_the_blocks_then_the_rest_of_the_core(
    repo: Path,
) -> None:
    reader = gk.plan_kernels(repo).assembled_kernel("reader")
    blocks = kernel_texts(repo_with_kernels(repo))["core-blocks.md"].strip()

    assert reader.strings[0].text.startswith(blocks)
    assert reader.strings[0].text.count(LINKS_TEXT) == 1
    assert "Shared text for every agent." in reader.strings[0].text


def repo_with_kernels(root: Path) -> Path:
    run(root)
    return root


def test_a_role_whose_definition_says_failed_at_is_told_the_shared_wording(tmp_path: Path) -> None:
    rows = manifest_rows()
    rows["authored"].append(authored_row("stop-line"))
    root = build_repo(tmp_path / "plugin", manifest=rows)
    write(root, "claude/kernels/src/stop-line.md", "Write **Stopped at**: Phase N.\n")
    plan = gk.plan_kernels(root)

    for role in ("failer", "reader"):
        assert "**Stopped at**: Phase N." in plan.assembled_kernel(role).strings[0].text
    assert "Failed at" not in kernel_text_of(plan, "core.md")


def kernel_text_of(plan: gk.KernelPlan, name: str) -> str:
    return plan.files[f"{gk.KERNELS_DIR}/{name}"].decode()


def test_an_unknown_role_is_refused_by_name(repo: Path) -> None:
    with pytest.raises(gk.KernelPlanError, match="no such role"):
        gk.plan_kernels(repo).assembled_kernel("nobody")


# -- The index ----------------------------------------------------------------------------


def test_the_index_holds_no_adoption_status_whatever_the_ledger_says(repo: Path) -> None:
    write(
        repo,
        km.LEDGER_PATH,
        "version: 1\nroles:\n  writer:\n    status: trial\n    since: today\n",
    )
    run(repo)

    index = km.load_index(repo)

    assert index is not None
    assert {kernel.status for kernel in index.roles.values()} == {None}


def test_the_index_is_the_same_before_and_after_a_status_is_recorded(repo: Path) -> None:
    run(repo)
    before = (repo / km.INDEX_PATH).read_bytes()
    write(
        repo,
        km.LEDGER_PATH,
        "version: 1\nroles:\n  writer:\n    status: trial\n    since: today\n",
    )

    assert run(repo, "--check") == 0
    assert (repo / km.INDEX_PATH).read_bytes() == before


def test_the_slots_are_the_most_strings_any_role_has_plus_the_project_file_reserve(
    tmp_path: Path,
) -> None:
    root = build_repo(tmp_path / "plugin")
    run(root)
    index = km.load_index(root)

    assert index is not None
    most = max(len(role.strings) for role in index.roles.values())
    assert index.slots == most + gk.PROJECT_FILE_RESERVE


def test_the_principles_file_is_the_templates_principles_verbatim_without_the_framing(
    repo: Path,
) -> None:
    run(repo)

    assert kernel_texts(repo)["principles.md"] == (
        "### Wisdom\n\nWisdom text, as the template words it.\n\n"
        "### Craft\n\nCraft text, as the template words it.\n"
    )


def test_a_template_without_a_principles_section_is_refused() -> None:
    template = ks.split_sections(TEMPLATE, "## Template\n\nUser-level text.\n")

    with pytest.raises(gk.KernelPlanError, match="no 'Principles' section"):
        gk.principles_section({TEMPLATE: template})


def test_the_principle_headings_are_the_templates_level_three_headings_in_order() -> None:
    template = ks.split_sections(TEMPLATE, TEMPLATE_TEXT)

    assert gk.principle_headings({TEMPLATE: template}) == ("Wisdom", "Craft")


def test_a_template_without_a_principles_section_has_no_headings_to_read() -> None:
    template = ks.split_sections(TEMPLATE, "## Template\n\nUser-level text.\n")

    with pytest.raises(gk.KernelPlanError, match="no 'Principles' section"):
        gk.principle_headings({TEMPLATE: template})


@pytest.mark.parametrize(
    ("count", "word"), [(1, "one"), (8, "eight"), (13, "thirteen"), (20, "twenty"), (21, "21")]
)
def test_the_pointer_states_its_count_as_a_number_word_and_as_digits_beyond_twenty(
    count: int, word: str
) -> None:
    headings = [f"Principle {n}" for n in range(count)]

    filled = gk.fill_principle_markers(f"The {gk.COUNT_MARKER} are {gk.NAMES_MARKER}.", headings)

    assert filled.startswith(f"The {word} are Principle 0")


@pytest.mark.parametrize(
    ("headings", "joined"),
    [
        (["A"], "A"),
        (["A", "B"], "A and B"),
        (["A", "B", "C"], "A, B and C"),
    ],
)
def test_the_pointer_lists_the_names_with_commas_and_a_closing_and(
    headings: list[str], joined: str
) -> None:
    filled = gk.fill_principle_markers(
        f"{gk.COUNT_MARKER} principles: {gk.NAMES_MARKER}.", headings
    )

    assert filled.endswith(f": {joined}.")


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        (f"Only {gk.NAMES_MARKER} here.", f"{gk.COUNT_MARKER} 0 times"),
        (f"Only {gk.COUNT_MARKER} here.", f"{gk.NAMES_MARKER} 0 times"),
        (f"{gk.COUNT_MARKER} {gk.COUNT_MARKER} {gk.NAMES_MARKER}", f"{gk.COUNT_MARKER} 2 times"),
        (f"{gk.COUNT_MARKER} {gk.NAMES_MARKER} {gk.NAMES_MARKER}", f"{gk.NAMES_MARKER} 2 times"),
        (f"{gk.COUNT_MARKER} {gk.NAMES_MARKER} @@PRINCIPLE_ORDER@@", "unfilled marker"),
    ],
)
def test_a_pointer_whose_markers_are_missing_repeated_or_unfilled_is_refused(
    text: str, fragment: str
) -> None:
    with pytest.raises(gk.KernelPlanError, match=fragment):
        gk.fill_principle_markers(text, ["A", "B"])


def test_a_template_with_no_principle_heading_names_nothing_and_is_refused() -> None:
    with pytest.raises(gk.KernelPlanError, match="no principle headings"):
        gk.fill_principle_markers(f"{gk.COUNT_MARKER} {gk.NAMES_MARKER}", [])


def test_the_pointer_in_a_generated_kernel_names_the_templates_principles(repo: Path) -> None:
    manifest = manifest_rows()
    manifest["authored"].append(authored_row(gk.POINTER_TEXT))
    write(repo, km.MANIFEST_PATH, yaml.safe_dump(manifest, sort_keys=False))
    pointer = f"The {gk.COUNT_MARKER} principles are {gk.NAMES_MARKER}."
    write(repo, f"claude/kernels/src/{gk.POINTER_TEXT}.md", pointer + "\n")
    run(repo)

    assert "The two principles are Wisdom and Craft." in kernel_texts(repo)["core.md"]


def test_the_kernel_version_changes_when_a_kernel_byte_does(repo: Path) -> None:
    before = km.load_index(_generated(repo))
    write(repo, SHARED_RULE, SHARED_SOURCE_TEXT.replace("Shared text", "Shared words"))
    after = km.load_index(_generated(repo))

    assert before is not None
    assert after is not None
    assert before.kernel_version != after.kernel_version


def _generated(root: Path) -> Path:
    assert run(root) == 0
    return root


# -- Determinism, and --check -------------------------------------------------------------


def test_generating_twice_yields_identical_bytes(repo: Path) -> None:
    run(repo)
    first = disk_state(repo)

    assert run(repo) == 0
    assert disk_state(repo) == first


def test_check_writes_nothing_and_reports_an_absent_kernel_as_stale(repo: Path, capsys) -> None:
    before = disk_state(repo)

    assert run(repo, "--check") == 1
    assert "stale: claude/kernels/core.md" in capsys.readouterr().out
    assert disk_state(repo) == before


def test_check_passes_on_fresh_kernels_and_bites_on_an_edited_one(repo: Path) -> None:
    run(repo)
    assert run(repo, "--check") == 0

    core_file = repo / gk.KERNELS_DIR / "core.md"
    core_file.write_text(core_file.read_text() + "\nedited by hand\n")

    assert run(repo, "--check") == 1


def test_a_leftover_kernel_file_is_stale_and_regenerating_removes_it(repo: Path) -> None:
    run(repo)
    leftover = repo / gk.KERNELS_DIR / "core-1.md"
    leftover.write_text("a part nobody makes\n")

    assert run(repo, "--check") == 1
    assert run(repo) == 0
    assert not leftover.exists()


def test_a_root_without_a_manifest_is_an_input_error(tmp_path: Path, capsys) -> None:
    assert run(tmp_path) == 2
    assert "_audience.yaml does not exist" in capsys.readouterr().err


def test_a_plugin_cache_root_is_refused(tmp_path: Path, capsys) -> None:
    cache = build_repo(tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0")

    assert run(cache) == 2
    assert "plugin cache" in capsys.readouterr().err


# -- The spawn split -------------------------------------------------------------------------------

UNIT_PATH = rd.MANAGED_CORE_UNITS[0].path
UNIT_ID = rd.MANAGED_CORE_UNITS[0].unit_id
UNIT_TEXT = "## Acts\n\nEveryone acts on this.\n\n## Routing\n\nOnly the main session routes.\n"


def split_repo(root: Path, unit_text: str = UNIT_TEXT) -> Path:
    rows = manifest_rows()
    rows["entries"] += [
        core(UNIT_PATH, "Acts"),
        entry(UNIT_PATH, "Routing", "orchestrator-only"),
    ]
    build_repo(root, manifest=rows)
    write(root, UNIT_PATH, unit_text)
    return root


def written_split(root: Path) -> dict:
    return json.loads((root / kss.SPAWN_SPLIT_PATH).read_text(encoding="utf-8"))


def test_a_unit_that_loses_a_dropped_section_is_written_with_the_digests_the_hook_checks(
    tmp_path: Path,
) -> None:
    root = split_repo(tmp_path / "plugin")

    run(root)

    written = written_split(root)
    assert written["schema"] == rd.SPLIT_SCHEMA
    assert written["manifest_sha256"] == kss.sha256_hex((root / km.MANIFEST_PATH).read_bytes())
    assert written["units"][UNIT_ID] == {
        "source": UNIT_PATH,
        "whole_sha256": kss.sha256_hex(UNIT_TEXT),
        "text": "## Acts\n\nEveryone acts on this.\n\n",
        "text_sha256": kss.sha256_hex("## Acts\n\nEveryone acts on this.\n\n"),
    }


def test_a_repository_with_nothing_to_drop_writes_an_artifact_listing_no_unit(repo: Path) -> None:
    run(repo)

    assert written_split(repo)["units"] == {}


def test_generating_edits_no_source_rule_and_no_manifest(tmp_path: Path) -> None:
    root = split_repo(tmp_path / "plugin")
    sources = {rel: (root / rel).read_bytes() for rel in (UNIT_PATH, SHARED_RULE, km.MANIFEST_PATH)}

    run(root)

    assert {rel: (root / rel).read_bytes() for rel in sources} == sources


def test_an_edit_to_dropped_text_moves_the_split_and_no_kernel_or_the_index(tmp_path: Path) -> None:
    root = split_repo(tmp_path / "plugin")
    run(root)
    before = disk_state(root)

    write(root, UNIT_PATH, UNIT_TEXT.replace("main session routes", "main session decides"))
    run(root)
    after = disk_state(root)

    changed = {rel for rel in before if before[rel] != after[rel]}
    assert changed == {UNIT_PATH, kss.SPAWN_SPLIT_PATH}


def test_check_bites_on_a_hand_edited_split_and_passes_once_regenerated(repo: Path) -> None:
    split_root = split_repo(repo.parent / "split")
    run(split_root)
    assert run(split_root, "--check") == 0

    artifact = split_root / kss.SPAWN_SPLIT_PATH
    artifact.write_text(artifact.read_text().replace("Everyone acts", "Edited"))

    assert run(split_root, "--check") == 1
    run(split_root)
    assert run(split_root, "--check") == 0


def test_check_bites_on_an_absent_split(repo: Path) -> None:
    run(repo)
    (repo / kss.SPAWN_SPLIT_PATH).unlink()

    assert run(repo, "--check") == 1
