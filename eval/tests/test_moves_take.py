"""An arm's take is proven from the session's own record: a full session owes the whole rule at
start, a lean session its kernel and not the whole, a floor session no line of it; a lean session
the point-of-use text never reached is scored as a trigger failure, and nothing unreadable is
ever scored."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxion_evals.adherence.moves import declaration, take
from praxion_evals.adherence.moves.model import MoveDeclaration
from tests.test_moves_session_record import (
    hook_context,
    instructions,
    lazy_rule,
    prompt,
    tool_call,
    tool_output,
    write_record,
)

RULE_PATH = "rules/swe/adr-conventions.md"
KERNEL = "Architecture Decision Records live in a folder."
OTHERS = ["- Draft a fragment first.", "- Finalize at merge."]
RULE = f"---\npaths:\n  - x/**\n---\n## ADR Conventions\n\n{KERNEL}\n\n```\n{OTHERS[0]}\n```\n{OTHERS[1]}\n| --- |\n"
UNRELATED = "Session context: nothing of the rule."


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("take") / "checkout"
    (root / RULE_PATH).parent.mkdir(parents=True)
    (root / RULE_PATH).write_text(RULE, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def move() -> MoveDeclaration:
    return declaration.kit("adr-conventions")


def session(tmp_path: Path, start: str, *later: str) -> Path:
    entries = [hook_context("SessionStart", start), prompt("Write the record.")]
    entries += [hook_context("PreToolUse", text) for text in later]
    entries.append(tool_call("toolu_1", "Bash", {"command": "git commit -m x"}))
    return write_record(tmp_path / "session.jsonl", entries)


def prove(move, checkout, arm, record):
    return take.prove(move, arm, record, checkout)


WHOLE = "\n".join([KERNEL, *OTHERS])


def test_a_full_session_carrying_the_whole_rule_at_start_is_scored(move, checkout, tmp_path):
    result = prove(move, checkout, "full", session(tmp_path, WHOLE))

    assert result.scored
    assert not result.trigger_failure


def test_a_full_session_lacking_part_of_the_rule_is_refused_naming_a_missing_line(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "full", session(tmp_path, KERNEL))

    assert not result.scored
    assert OTHERS[0] in (result.reason or "")


def test_a_lean_session_with_its_kernel_and_the_rest_at_the_point_of_use_is_scored(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "lean", session(tmp_path, KERNEL, "\n".join(OTHERS)))

    assert result.scored
    assert not result.trigger_failure


def test_a_lean_session_whose_rest_of_the_rule_was_loaded_lazily_is_scored_without_a_failure(
    move, checkout, tmp_path
):
    record = write_record(
        tmp_path / "s.jsonl", [instructions(KERNEL), lazy_rule("\n".join(OTHERS))]
    )

    result = prove(move, checkout, "lean", record)

    assert result.scored
    assert not result.trigger_failure


def test_a_lean_session_whose_point_of_use_text_never_arrived_is_scored_as_a_trigger_failure(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "lean", session(tmp_path, KERNEL))

    assert result.scored
    assert result.trigger_failure


def test_a_lean_session_given_only_part_of_the_point_of_use_text_is_a_trigger_failure(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "lean", session(tmp_path, KERNEL, OTHERS[0]))

    assert result.scored
    assert result.trigger_failure


def test_a_lean_session_carrying_the_whole_rule_at_start_is_refused(move, checkout, tmp_path):
    result = prove(move, checkout, "lean", session(tmp_path, WHOLE, WHOLE))

    assert not result.scored
    assert "whole" in (result.reason or "")


def test_a_lean_session_lacking_its_kernel_is_refused_even_with_the_point_of_use_text(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "lean", session(tmp_path, UNRELATED, "\n".join(OTHERS)))

    assert not result.scored
    assert "kernel" in (result.reason or "")


def test_a_floor_session_carrying_any_line_of_the_rule_is_refused(move, checkout, tmp_path):
    result = prove(move, checkout, "floor", session(tmp_path, f"{UNRELATED}\n{OTHERS[1]}"))

    assert not result.scored
    assert OTHERS[1] in (result.reason or "")


def test_a_floor_session_given_the_rule_at_the_point_of_use_is_refused_naming_the_channel(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "floor", session(tmp_path, UNRELATED, OTHERS[1]))

    assert not result.scored
    assert "hook_context" in (result.reason or "")
    assert OTHERS[1] in (result.reason or "")


def test_a_floor_session_whose_rule_was_loaded_lazily_is_refused_naming_the_channel(
    move, checkout, tmp_path
):
    record = write_record(
        tmp_path / "s.jsonl", [instructions(UNRELATED), lazy_rule("\n".join(OTHERS))]
    )

    result = prove(move, checkout, "floor", record)

    assert not result.scored
    assert "path_matched" in (result.reason or "")


def test_a_floor_session_whose_gate_refused_with_the_rule_text_is_refused_naming_the_channel(
    move, checkout, tmp_path
):
    refusal = f"PreToolUse:Bash hook error: [hooks/gate.sh]: {OTHERS[1]}"
    record = write_record(
        tmp_path / "s.jsonl",
        [
            instructions(UNRELATED),
            tool_call("t1", "Bash", {"command": "git commit"}),
            tool_output("t1", refusal),
        ],
    )

    result = prove(move, checkout, "floor", record)

    assert not result.scored
    assert "gate_refusal" in (result.reason or "")


def test_a_floor_session_carrying_only_the_kernel_is_refused(move, checkout, tmp_path):
    assert not prove(move, checkout, "floor", session(tmp_path, KERNEL)).scored


def test_a_floor_session_with_no_line_of_the_rule_is_scored(move, checkout, tmp_path):
    result = prove(move, checkout, "floor", session(tmp_path, UNRELATED))

    assert result.scored
    assert not result.trigger_failure


def test_headings_and_table_rules_alone_do_not_count_as_a_line_of_the_rule(
    move, checkout, tmp_path
):
    shared = "## ADR Conventions\n| --- |\n```"

    assert prove(move, checkout, "floor", session(tmp_path, f"{UNRELATED}\n{shared}")).scored


def test_text_loaded_as_an_instruction_file_counts_as_arriving_at_session_start(
    move, checkout, tmp_path
):
    record = write_record(tmp_path / "s.jsonl", [instructions(WHOLE)])

    assert prove(move, checkout, "full", record).scored


def test_a_full_session_given_the_rule_only_at_the_point_of_use_is_refused(
    move, checkout, tmp_path
):
    result = prove(move, checkout, "full", session(tmp_path, UNRELATED, WHOLE))

    assert not result.scored


@pytest.mark.parametrize("arm", ["full", "lean", "floor"])
def test_an_unreadable_record_is_refused_never_scored(move, checkout, tmp_path, arm):
    record = tmp_path / "s.jsonl"
    record.write_text("not a session record\n", encoding="utf-8")

    result = prove(move, checkout, arm, record)

    assert not result.scored
    assert "not JSON" in (result.reason or "")


def test_a_moved_rule_the_checkout_does_not_hold_is_refused(move, tmp_path):
    result = take.prove(move, "full", session(tmp_path, WHOLE), tmp_path / "empty")

    assert not result.scored
    assert "cannot be read" in (result.reason or "")


def test_the_default_checkout_is_the_one_this_package_is_installed_from():
    assert (take.CHECKOUT_ROOT / "rules" / "swe" / "adr-conventions.md").is_file()
