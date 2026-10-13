"""Tests for generate_kernels.py -- the kernels each role receives, assembled from the manifest.

Behaviors over a synthetic repository (so no test depends on what the rules say today): what
is rendered and what is withheld, the universal blocks, parts and packing, the index and its
statuses, determinism, and `--check` writing nothing. Four checks run over the real repository
(each role's module set, the committed kernels being fresh, the stop-line wording, the cap),
paired with the synthetic canaries that prove the same checks bite.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_agent_shared_blocks as sb  # noqa: E402
import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CAP = km.MAX_STRING_CHARS
CONTRACT_RULE = gk.CONTRACT_SOURCE
SHARED_RULE = "rules/swe/shared.md"
CONDENSED_RULE = "rules/swe/condensed.md"
TEMPLATE = ks.USER_TEMPLATE
SECRET_TEXT = "Secret orchestrator text that no kernel may carry."
LONG_SOURCE = "## Condensed\n\nThe long source that a short form stands for.\n"
LINKS_TEXT = "**Praxion links.** Read a Praxion file from the plugin root."
RETURN_TEXT = "**Return contract.** End with one terminal marker."
USER_SENTENCE = "The user-level instruction file is not loaded for you."
CONTRACT_SOURCE_TEXT = """## Agent Behavioral Contract

Intro that points at the methodology.

- **Alpha** - first behavior.
- **Beta** - second behavior.

Self-test: did I follow the contract?

Tail about commit authorship.
"""
SHARED_SOURCE_TEXT = f"""## Shared

Shared text for every agent.

## Secret

{SECRET_TEXT}

## Duty

Duty text for the writer.
"""
AGENTS = {"writer": "", "reader": "", "failer": "The partial form says **Failed at** here.\n"}


def entry(source: str, heading: str, scope: str, **fields: object) -> dict:
    reason = "kept resident" if scope in ("orchestrator-only", "no-actor") else None
    return {"source": source, "heading": heading, "scope": scope, "reason": reason, **fields}


def core(source: str, heading: str, **fields: object) -> dict:
    return entry(source, heading, "core", **{"form": "verbatim", **fields})


def authored_row(text_id: str, module: str = "core", **fields: object) -> dict:
    path = f"claude/kernels/src/{text_id}.md"
    return {"id": text_id, "path": path, "module": module, "condenses": None, **fields}


def manifest_rows() -> dict:
    short_pin = ks.sha1_hex(LONG_SOURCE)
    condensed = authored_row(
        "short-form", condenses=f"{CONDENSED_RULE}#Condensed", pinned_sha=short_pin
    )
    return {
        "version": 1,
        "groups": {},
        "modules": {},
        "authored": [
            authored_row("praxion-links"),
            authored_row("return-contract"),
            authored_row("user-sentence"),
            condensed,
        ],
        "entries": [
            entry(CONTRACT_RULE, "Agent Behavioral Contract", "orchestrator-only", part="Intro"),
            core(CONTRACT_RULE, "Agent Behavioral Contract", part="- **Alpha**"),
            entry(CONTRACT_RULE, "Agent Behavioral Contract", "no-actor", part="Tail"),
            core(SHARED_RULE, "Shared"),
            entry(SHARED_RULE, "Secret", "orchestrator-only"),
            entry(SHARED_RULE, "Duty", "role", form="verbatim", agents=["writer"]),
            core(CONDENSED_RULE, "Condensed", form="condensed", text="short-form", pin=short_pin),
            entry(TEMPLATE, "Template", "no-actor"),
        ],
    }


AUTHORED_TEXTS = {
    "praxion-links": LINKS_TEXT,
    "return-contract": RETURN_TEXT,
    "user-sentence": USER_SENTENCE,
    "short-form": "The short form.",
}


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_repo(root: Path, *, manifest: Mapping | None = None) -> Path:
    write(root, CONTRACT_RULE, CONTRACT_SOURCE_TEXT)
    write(root, SHARED_RULE, SHARED_SOURCE_TEXT)
    write(root, CONDENSED_RULE, LONG_SOURCE)
    write(root, TEMPLATE, "## Template\n\nUser-level text.\n")
    for name, body in AGENTS.items():
        write(root, f"agents/{name}.md", f"---\nname: {name}\n---\n\n{body}")
    for text_id, text in AUTHORED_TEXTS.items():
        write(root, f"claude/kernels/src/{text_id}.md", text + "\n")
    write(root, km.MANIFEST_PATH, yaml.safe_dump(manifest or manifest_rows(), sort_keys=False))
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_repo(tmp_path / "plugin")


def run(root: Path, *flags: str) -> int:
    return gk.main([*flags, "--repo-root", str(root)])


def kernel_texts(root: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in (root / gk.KERNELS_DIR).glob("*.md")}


def disk_state(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


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


def test_the_blocks_stay_out_of_the_injected_strings(repo: Path) -> None:
    reader = gk.plan_kernels(repo).assembled_kernel("reader")

    assert LINKS_TEXT not in reader.strings[0].text
    assert "Shared text for every agent." in reader.strings[0].text


def test_a_role_whose_definition_says_failed_at_is_never_told_stopped_at(tmp_path: Path) -> None:
    rows = manifest_rows()
    rows["authored"].append(authored_row("stop-line"))
    root = build_repo(tmp_path / "plugin", manifest=rows)
    write(root, "claude/kernels/src/stop-line.md", "Write **Stopped at**: Phase N.\n")
    plan = gk.plan_kernels(root)

    assert "**Failed at**: Phase N." in plan.assembled_kernel("failer").strings[0].text
    assert "Stopped at" in plan.assembled_kernel("reader").strings[0].text
    assert "Stopped at" in kernel_text_of(plan, "core.md")


def kernel_text_of(plan: gk.KernelPlan, name: str) -> str:
    return plan.files[f"{gk.KERNELS_DIR}/{name}"].decode()


def test_an_unknown_role_is_refused_by_name(repo: Path) -> None:
    with pytest.raises(gk.KernelPlanError, match="no such role"):
        gk.plan_kernels(repo).assembled_kernel("nobody")


# -- The index ----------------------------------------------------------------------------


def test_the_index_projects_statuses_from_the_ledger(repo: Path) -> None:
    write(
        repo,
        km.LEDGER_PATH,
        "version: 1\neligible: [writer]\nroles:\n  writer:\n    status: trial\n    since: today\n",
    )
    run(repo)

    index = km.load_index(repo)

    assert index is not None
    assert {name: kernel.status for name, kernel in index.roles.items()} == {
        "writer": "trial",
        "reader": None,
        "failer": None,
    }


def test_the_slots_are_the_most_strings_any_role_has_plus_the_project_file_reserve(
    tmp_path: Path,
) -> None:
    root = build_repo(tmp_path / "plugin")
    run(root)
    index = km.load_index(root)

    assert index is not None
    most = max(len(role.strings) for role in index.roles.values())
    assert index.slots == most + gk.PROJECT_FILE_RESERVE


def test_a_ledger_naming_no_agent_is_refused(repo: Path, capsys) -> None:
    write(
        repo, km.LEDGER_PATH, "version: 1\nroles:\n  ghost:\n    status: trial\n    since: today\n"
    )

    assert run(repo) == 2
    assert "ghost" in capsys.readouterr().err


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


# -- The real repository ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def live() -> gk.KernelPlan:
    return gk.plan_kernels(REPO_ROOT)


WRITER_ROLES = ("systems-architect", "implementation-planner", "interface-designer")
LIVE_MODULES = {
    "verifier": ("adr-reader", "ledger-writer", "principles-anchor", "local-verifier"),
    "sentinel": ("ledger-writer",),
    "architect-validator": ("ledger-writer",),
    "systems-architect": ("adr-author", "principles-digest"),
    "implementation-planner": ("adr-author",),
    "interface-designer": ("adr-author",),
    "agentic-transactions-architect": ("adr-author",),
    "promethean": ("principles-digest",),
    "roadmap-cartographer": ("delegator",),
    "researcher": ("adr-reader",),
    "context-engineer": ("local-context-engineer",),
    "discipline-consultant": (),
    "skill-genesis": (),
    "implementer": (),
}


@pytest.mark.parametrize("role", LIVE_MODULES)
def test_each_role_holds_the_core_and_its_own_modules(live: gk.KernelPlan, role: str) -> None:
    assert live.assembled_kernel(role).modules == ("core", *LIVE_MODULES[role])


def test_the_verifier_holds_no_adr_author_text(live: gk.KernelPlan) -> None:
    adr_author = live.files[f"{gk.KERNELS_DIR}/adr-author.md"].decode()
    held = "\n".join(s.text for s in live.assembled_kernel("verifier").strings)

    paragraphs = [p for p in adr_author.split("\n\n") if len(p) > 80]
    assert paragraphs
    assert [p for p in paragraphs if p in held] == []


def test_only_the_context_engineer_holds_the_audit_subject_exemption(live: gk.KernelPlan) -> None:
    exemption = "as an audit subject"
    holders = [
        role
        for role, kernel in live.roles.items()
        if exemption in "\n".join(s.text for s in kernel.strings)
    ]

    assert holders == ["context-engineer"]


@pytest.mark.parametrize("role", ["context-engineer", "skill-genesis", "discipline-consultant"])
def test_a_role_that_words_the_stop_line_failed_at_is_not_told_stopped_at(
    live: gk.KernelPlan, role: str
) -> None:
    held = "\n".join(s.text for s in live.assembled_kernel(role).strings)

    assert "Stopped at" not in held
    assert "**Failed at**" in held


def test_every_live_string_and_file_fits_one_injected_string(live: gk.KernelPlan) -> None:
    strings = [len(s.text) for kernel in live.roles.values() for s in kernel.strings]
    files = [
        len(data.decode())
        for rel, data in live.files.items()
        if rel.startswith(gk.KERNELS_DIR) and rel.endswith(".md")
    ]

    assert max(strings) <= CAP
    assert max(files) <= CAP


# The definitions' blocks and the preamble are derived as well; the manifest checker holds them
# fresh once the first generated commit has made them so.
def test_the_committed_kernels_are_what_the_generator_produces(live: gk.KernelPlan) -> None:
    kernel_files = {rel: data for rel, data in live.files.items() if rel.startswith(gk.KERNELS_DIR)}

    assert gk.stale_files(REPO_ROOT, kernel_files) == []


# -- The definitions' blocks and the preamble ---------------------------------------------

BLOCKS = gk.UniversalBlocks(
    "- **Alpha** - first behavior.\n- **Beta** - second behavior.\nSelf-test: did I follow it?",
    LINKS_TEXT,
    RETURN_TEXT,
)
OLD_CONTRACT = "**Apply the contract**: the old way. Self-test: did I follow it?"
OLD_LINKS = "**Praxion links.** The old way to read a Praxion file."
OLD_RETURN = "**Return contract.** The old way to end."
OWN_SENTENCE = '"Register Objection" is your function here.'
TODAYS_PREAMBLE = (
    "[Praxion process active] Apply the behavioral contract: "
    "Surface Assumptions, Register Objection, Stay Surgical, Simplicity First. "
    "Use the tier selector; carry this contract into every delegation. "
    "Return a pointer, not a payload: a summary plus your .ai-work/ "
    "artifact path, not the full report."
)
FOUR_BEHAVIOURS = (
    "- **Surface Assumptions** - a.\n- **Register Objection** - b.\n"
    "- **Stay Surgical** - c.\n- **Simplicity First** - d.\nSelf-test: did I?"
)


def definition(*paragraphs: str) -> str:
    return "---\nname: writer\n---\n\n" + "\n\n".join(paragraphs) + "\n"


@pytest.fixture
def old_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    """The checker's universal blocks as definitions carry them before the first regeneration."""
    old = {
        gk.CONTRACT_SLUG: ("**Apply the contract**", OLD_CONTRACT, ("the old way. Self-test",)),
        gk.LINKS_SLUG: ("**Praxion links.**", OLD_LINKS, ("old way to read",)),
        gk.RETURN_SLUG: ("**Return contract.**", OLD_RETURN, ("old way to end",)),
    }
    shared = tuple(
        sb.SharedBlock(slug, canonical, anchor, tells, universal=True)
        for slug, (anchor, canonical, tells) in old.items()
    )
    monkeypatch.setattr(sb, "SHARED_BLOCKS", shared)


def test_each_block_is_regenerated_where_it_stands_and_no_other_paragraph_changes(
    old_wording: None,
) -> None:
    before = definition("Intro.", OLD_CONTRACT, OLD_LINKS, "Middle.", OLD_RETURN, "Outro.")

    after = gk.render_definition(before, BLOCKS)

    assert after == definition(
        "Intro.", BLOCKS.contract, BLOCKS.links, "Middle.", BLOCKS.returns, "Outro."
    )


def test_a_paragraph_that_carries_a_tell_but_lost_its_anchor_is_still_the_block(
    old_wording: None,
) -> None:
    drifted = "Reworded head: the old way to read a file."

    after = gk.render_definition(definition("Intro.", drifted), BLOCKS)

    assert drifted not in after
    assert BLOCKS.links in after


def test_the_sentence_after_the_contract_moves_to_its_own_line_and_stays_there(
    old_wording: None,
) -> None:
    before = definition("Intro.", f"{OLD_CONTRACT} {OWN_SENTENCE}")

    once = gk.render_definition(before, BLOCKS)

    assert f"{BLOCKS.contract}\n{OWN_SENTENCE}\n" in once
    assert gk.render_definition(once, BLOCKS) == once


def test_a_contract_reworded_since_it_was_generated_is_replaced_not_duplicated() -> None:
    generated = definition("Intro.", f"{BLOCKS.contract}\n{OWN_SENTENCE}")
    reworded = gk.UniversalBlocks(
        BLOCKS.contract.replace("Alpha", "Gamma"), BLOCKS.links, BLOCKS.returns
    )

    after = gk.render_definition(generated, reworded)

    assert after.count(gk.SELF_TEST_LABEL) == 1
    assert "Alpha" not in after
    assert f"{reworded.contract}\n{OWN_SENTENCE}\n" in after


def test_a_block_a_definition_lacks_is_appended_and_then_stays_where_it_is() -> None:
    before = definition("Intro.", RETURN_TEXT, "Outro.")

    after = gk.render_definition(before, BLOCKS)

    assert after == definition("Intro.", RETURN_TEXT, "Outro.", BLOCKS.contract, BLOCKS.links)
    assert gk.render_definition(after, BLOCKS) == after


def test_the_end_of_the_file_is_left_as_it_was_when_no_block_is_missing() -> None:
    bare = "---\nname: writer\n---\n\n" + BLOCKS.text

    assert gk.render_definition(bare, BLOCKS) == bare


def test_regenerating_the_repository_derives_the_definitions_and_the_preamble(repo: Path) -> None:
    run(repo)

    written = (repo / "agents" / "writer.md").read_text()
    assert written.endswith((repo / gk.KERNELS_DIR / gk.BLOCKS_FILE).read_text())
    assert (repo / gk.PREAMBLE_PATH).is_file()


def test_a_contract_change_flows_to_the_blocks_the_core_the_definitions_and_the_preamble(
    repo: Path,
) -> None:
    run(repo)
    write(repo, CONTRACT_RULE, CONTRACT_SOURCE_TEXT.replace("Beta", "Gamma"))

    run(repo)

    reached = {
        "blocks": (repo / gk.KERNELS_DIR / gk.BLOCKS_FILE).read_text(),
        "core": kernel_texts(repo)["core.md"],
        "definition": (repo / "agents" / "reader.md").read_text(),
        "preamble": (repo / gk.PREAMBLE_PATH).read_text(),
    }
    assert [name for name, text in reached.items() if "Gamma" not in text] == []
    assert [name for name, text in reached.items() if "Beta" in text] == []


def test_a_stale_definition_is_named_by_check_and_repaired_by_regenerating(
    repo: Path, capsys
) -> None:
    run(repo)
    path = repo / "agents" / "writer.md"
    path.write_text(path.read_text().replace(LINKS_TEXT, "A hand-written links sentence."))
    capsys.readouterr()

    assert run(repo, "--check") == 1
    assert "stale: agents/writer.md" in capsys.readouterr().out
    assert run(repo) == 0
    assert run(repo, "--check") == 0


def test_a_definition_that_is_not_in_the_file_its_name_gives_is_refused(repo: Path, capsys) -> None:
    write(repo, "agents/elsewhere.md", "---\nname: nobody\n---\n\nBody.\n")

    assert run(repo) == 2
    assert "agents/nobody.md" in capsys.readouterr().err
    assert not (repo / gk.KERNELS_DIR / "core.md").exists()


def test_the_preamble_is_todays_wording_with_the_names_the_contract_gives() -> None:
    namespace: dict[str, str] = {}

    exec(gk.render_preamble(FOUR_BEHAVIOURS), namespace)  # the generated module, run as a hook does

    assert namespace["_PREAMBLE"] == TODAYS_PREAMBLE
    assert len(TODAYS_PREAMBLE) + len(gk.PREAMBLE_GAP) <= gk.PREAMBLE_BOUND


def test_a_preamble_that_would_pass_its_bound_is_refused() -> None:
    contract = FOUR_BEHAVIOURS.replace("Simplicity First", "Simplicity First " * 4)

    with pytest.raises(gk.KernelPlanError, match="over its 296"):
        gk.render_preamble(contract)


def test_a_contract_that_names_no_behaviour_gives_no_preamble() -> None:
    with pytest.raises(gk.KernelPlanError, match="no preamble wording"):
        gk.render_preamble("Self-test: did I?")


@pytest.mark.parametrize("name", sorted(km.agent_definitions(REPO_ROOT)))
def test_a_live_definition_changes_only_by_the_lines_of_its_blocks(
    live: gk.KernelPlan, name: str
) -> None:
    universal = [b for b in sb.SHARED_BLOCKS if b.universal]
    blocks_file = live.files[f"{gk.KERNELS_DIR}/{gk.BLOCKS_FILE}"].decode()
    block_lines = {line for line in blocks_file.splitlines() if line.strip()}
    path = gk.definition_path(name)
    before = (REPO_ROOT / path).read_text().splitlines()
    after = live.files[path].decode().splitlines()

    def carries(line: str) -> bool:
        return any(line.startswith(b.anchor) or any(t in line for t in b.tells) for b in universal)

    carried = [line for line in before if carries(line)]  # a per-agent sentence may move out of one

    assert [line for line in before if line not in after and not carries(line)] == []
    assert [
        line
        for line in after
        if line not in before
        and line not in block_lines
        and not any(line in old for old in carried)
    ] == []


def test_the_live_preamble_is_todays_wording_within_todays_bound(live: gk.KernelPlan) -> None:
    namespace: dict[str, str] = {}

    exec(live.files[gk.PREAMBLE_PATH].decode(), namespace)

    assert namespace["_PREAMBLE"] == TODAYS_PREAMBLE
