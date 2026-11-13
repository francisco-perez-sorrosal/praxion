"""Tests for generate_kernels.py rewriting the agent definitions and the preamble.

The three universal blocks are regenerated where they stand in a definition and never
duplicated, a sentence of the definition's own survives, and the preamble is derived from the
contract's behaviour names, all over synthetic definitions and a synthetic repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _generate_kernels_testkit as kit  # noqa: E402
import check_agent_shared_blocks as sb  # noqa: E402
import generate_kernels as gk  # noqa: E402
from _generate_kernels_testkit import (  # noqa: E402
    CONTRACT_RULE,
    CONTRACT_SOURCE_TEXT,
    LINKS_TEXT,
    RETURN_TEXT,
    TODAYS_PREAMBLE,
    kernel_texts,
    run,
    write,
)

repo = kit.repo


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


def test_the_sentence_after_the_contract_ends_the_self_test_line_and_stays_there(
    old_wording: None,
) -> None:
    before = definition("Intro.", f"{OLD_CONTRACT} {OWN_SENTENCE}")

    once = gk.render_definition(before, BLOCKS)

    assert f"{BLOCKS.contract} {OWN_SENTENCE}\n" in once
    assert gk.render_definition(once, BLOCKS) == once


def test_a_sentence_generated_on_a_line_of_its_own_moves_up_to_the_self_test_line(
    old_wording: None,
) -> None:
    own_line = definition("Intro.", f"{BLOCKS.contract}\n{OWN_SENTENCE}")

    after = gk.render_definition(own_line, BLOCKS)

    assert f"{BLOCKS.contract} {OWN_SENTENCE}\n" in after


def test_the_generated_contract_block_opens_with_the_citation_of_the_rule() -> None:
    assert gk.CONTRACT_LEAD_IN == "**Apply the behavioral contract** (`" + CONTRACT_RULE + "`):"


def test_the_lead_in_of_a_generated_contract_is_not_a_second_contract_or_a_tail() -> None:
    generated = gk.UniversalBlocks(
        f"{gk.CONTRACT_LEAD_IN}\n{BLOCKS.contract}", LINKS_TEXT, RETURN_TEXT
    )
    before = definition(
        "Intro.", f"{generated.contract} {OWN_SENTENCE}", generated.links, generated.returns
    )

    after = gk.render_definition(before, generated)

    assert after == before
    assert after.count(gk.CONTRACT_LEAD_IN) == 1


def test_a_contract_reworded_since_it_was_generated_is_replaced_not_duplicated() -> None:
    generated = definition("Intro.", f"{BLOCKS.contract} {OWN_SENTENCE}")
    reworded = gk.UniversalBlocks(
        BLOCKS.contract.replace("Alpha", "Gamma"), BLOCKS.links, BLOCKS.returns
    )

    after = gk.render_definition(generated, reworded)

    assert after.count(gk.SELF_TEST_LABEL) == 1
    assert "Alpha" not in after
    assert f"{reworded.contract} {OWN_SENTENCE}\n" in after


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
