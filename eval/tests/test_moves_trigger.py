"""The trigger record says, per governed check, which channels carried the governing text, when
against the first governed action, and what the session left; a record that cannot say reads
every arrival as unknown, never as never arrived."""

from __future__ import annotations

from dataclasses import replace

import pytest

from praxion_evals.adherence.model import Failed, Passed
from praxion_evals.adherence.moves import declaration, trigger
from praxion_evals.adherence.moves.model import (
    Arrived,
    CheckTrigger,
    GateRefusal,
    GovernedCheck,
    MoveDeclaration,
    ProjectGating,
    RelPath,
    holds_phrase,
)
from praxion_evals.adherence.moves.session_record import (
    Delivery,
    Parsed,
    SessionEvents,
    ToolResult,
    ToolUse,
    Unreadable,
)
from tests.staging_check_support import git_governing_staging
from tests.test_moves_session_record import (
    hook_context,
    instructions,
    tool_call,
    tool_output,
    write_record,
)

COMMIT_FORM = "commit message form"
STAGING = "staging by name"
FORM_TEXT = "Use the imperative mood, 50 characters, and no authorship lines."
STAGING_TEXT = "Stage specific files by name; review git diff --staged for accidental inclusions."
WHOLE_RULE = f"{FORM_TEXT}\n{STAGING_TEXT}"
UNRELATED = "Session context: nothing of the rule."
CHAINED = "git add -- notes.md && git commit -m 'Add the notes'"
AMEND = "git commit --amend -m 'Add the notes'"
REFUSAL = (
    "PreToolUse:Bash hook error: [hooks/commit_gate.sh]: the subject is too long\n"
    "This hook comes from the praxion plugin."
)
COMMITTED = "[main 1a2b3c4] Add the notes"

START = Delivery("SessionStart", UNRELATED)
RULE_AT_START = Delivery("SessionStart", WHOLE_RULE)
AT_USE = Delivery("PreToolUse", WHOLE_RULE)
LAZY = Delivery("nested_memory", "the decision rule: fragments land under drafts")


@pytest.fixture(scope="module")
def git() -> MoveDeclaration:
    return git_governing_staging()


@pytest.fixture(scope="module")
def adr() -> MoveDeclaration:
    return declaration.kit("adr-conventions")


def shell(use_id: str, command: str) -> ToolUse:
    return ToolUse(use_id, "Bash", command, None)


def trigger_in(move: MoveDeclaration, check: str, events: SessionEvents) -> CheckTrigger:
    return next(t for t in trigger.triggers(move, events) if t.check == check)


def trigger_of(move: MoveDeclaration, check: str, *events) -> CheckTrigger:
    return trigger_in(move, check, Parsed(tuple(events)))


def timing_of(t: CheckTrigger, channel: str) -> str:
    arrival = t.arrivals[channel]
    assert isinstance(arrival, Arrived), f"{channel} did not arrive: {arrival}"
    return arrival.timing


# -- An unreadable record ---------------------------------------------------------------------


@pytest.mark.parametrize("check", [COMMIT_FORM, STAGING])
def test_an_unreadable_record_reads_every_arrival_as_unknown_for_every_check(git, check):
    t = trigger_in(git, check, Unreadable("the record is not one this reader knows"))

    assert set(t.arrivals) == {"session_start", "hook_context"}
    assert {type(a).__name__ for a in t.arrivals.values()} == {"Unknown"}
    assert t.history is None
    assert not t.trigger_failure


def test_a_record_file_that_cannot_be_read_gives_unknown_in_the_results_words(git, tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text("not a session record\n", encoding="utf-8")

    found = trigger.records(git, path)

    assert found[0].arrivals == {"session_start": "unknown", "hook_context": "unknown"}
    assert found[0].final is None
    assert found[0].history is None


# -- When the text arrived --------------------------------------------------------------------


def test_a_rule_delivered_at_session_start_arrives_before_composition(git):
    t = trigger_of(
        git, COMMIT_FORM, RULE_AT_START, shell("t1", CHAINED), ToolResult("t1", COMMITTED)
    )

    assert timing_of(t, "session_start") == "before composition"


def test_context_between_a_call_and_its_result_arrives_before_execution(git):
    t = trigger_of(
        git, COMMIT_FORM, START, shell("t1", CHAINED), AT_USE, ToolResult("t1", COMMITTED)
    )

    assert timing_of(t, "hook_context") == "before execution"


def test_context_ahead_of_the_call_arrives_before_composition(git):
    t = trigger_of(
        git, COMMIT_FORM, START, AT_USE, shell("t1", CHAINED), ToolResult("t1", COMMITTED)
    )

    assert timing_of(t, "hook_context") == "before composition"


def test_a_path_matched_load_after_a_creating_write_arrives_after_execution(adr):
    write = ToolUse("t1", "Write", None, "/work/.ai-state/decisions/drafts/x.md")
    t = trigger_of(adr, "decision draft placement", START, write, ToolResult("t1", "created"), LAZY)

    assert timing_of(t, "path_matched") == "after execution"
    assert t.history == "right_first_time"


def test_a_write_outside_the_globs_is_no_governed_action(adr):
    write = ToolUse("t1", "Write", None, "/work/src/app.py")
    t = trigger_of(adr, "decision draft placement", START, write, ToolResult("t1", "ok"), LAZY)

    assert t.history == "never_taken"
    assert t.final is None
    assert timing_of(t, "path_matched") == "before composition"


def test_a_shell_call_that_neither_stages_nor_commits_is_no_governed_action(git):
    t = trigger_of(
        git,
        COMMIT_FORM,
        START,
        shell("t0", "git status"),
        ToolResult("t0", "clean"),
        shell("t1", CHAINED),
        AT_USE,
        ToolResult("t1", COMMITTED),
    )

    assert timing_of(t, "hook_context") == "before execution"


# -- Whether it arrived at all ----------------------------------------------------------------


def test_a_channel_that_delivered_none_of_the_governing_text_never_arrived(git):
    t = trigger_of(git, COMMIT_FORM, START, shell("t1", CHAINED), ToolResult("t1", COMMITTED))

    assert {type(a).__name__ for a in t.arrivals.values()} == {"NeverArrived"}


def test_text_holding_only_part_of_a_checks_phrases_does_not_carry_it(git):
    kernel_only = Delivery("SessionStart", "- Never include AI authorship lines")

    t = trigger_of(git, COMMIT_FORM, kernel_only)

    assert type(t.arrivals["session_start"]).__name__ == "NeverArrived"


@pytest.mark.parametrize(
    "text", ["Subject Lines Under 50 chars", "subject lines under 50", "no number here"]
)
def test_the_trigger_reader_agrees_with_the_phrase_predicate(text):
    check = GovernedCheck("form", RelPath.parse("rules/x.md"), "Form", ("SUBJECT lines", "50"))

    assert trigger._holds_governing_text(text, check) == all(
        holds_phrase(text, phrase) for phrase in check.phrases
    )


def test_a_failed_check_that_nothing_reached_is_a_trigger_failure_derived_from_the_two(git):
    t = trigger_of(git, COMMIT_FORM, START, shell("t1", CHAINED), ToolResult("t1", COMMITTED))

    assert not t.trigger_failure  # passed on the record's own reading
    assert replace(t, final=Failed("subject too long")).trigger_failure


def test_a_channel_no_record_witnesses_reads_as_unknown(git):
    gated = replace(git, deliveries=(*git.deliveries, ProjectGating("managed")))

    t = trigger_of(gated, COMMIT_FORM, START)

    assert type(t.arrivals["project_gating"]).__name__ == "Unknown"
    assert not t.trigger_failure


# -- What the session left --------------------------------------------------------------------


def test_a_commit_amended_after_the_context_arrived_reads_as_repaired(git):
    t = trigger_of(
        git,
        COMMIT_FORM,
        START,
        shell("t1", CHAINED),
        AT_USE,
        ToolResult("t1", COMMITTED),
        shell("t2", AMEND),
        ToolResult("t2", COMMITTED),
    )

    assert timing_of(t, "hook_context") == "before execution"
    assert t.history == "repaired"
    assert t.final == Passed()


def test_a_commit_a_gate_refused_and_the_session_recomposed_reads_as_right_first_time(git):
    t = trigger_of(
        git,
        COMMIT_FORM,
        START,
        shell("t1", CHAINED),
        AT_USE,
        ToolResult("t1", REFUSAL),
        shell("t2", CHAINED),
        ToolResult("t2", COMMITTED),
    )

    assert t.history == "right_first_time"
    assert t.final == Passed()
    assert t.refusals == ("the subject is too long",)
    assert timing_of(t, "hook_context") == "before execution"


def test_a_chained_add_and_commit_in_one_call_is_one_governed_action(git):
    t = trigger_of(git, STAGING, START, shell("t1", CHAINED), AT_USE, ToolResult("t1", COMMITTED))

    assert t.history == "right_first_time"
    assert timing_of(t, "hook_context") == "before execution"


def test_a_last_governed_action_the_gate_refused_is_not_repaired_and_failed(git):
    t = trigger_of(git, COMMIT_FORM, START, AT_USE, shell("t1", CHAINED), ToolResult("t1", REFUSAL))

    assert t.history == "not_repaired"
    assert isinstance(t.final, Failed)
    assert "too long" in t.final.detail


def test_a_session_that_never_staged_or_committed_never_took_the_action(git):
    t = trigger_of(git, COMMIT_FORM, RULE_AT_START)

    assert t.history == "never_taken"
    assert t.final is None
    assert t.refusals == ()


def test_a_second_write_of_the_same_file_is_a_repair_of_the_first(adr):
    path = "/work/.ai-state/decisions/drafts/x.md"
    t = trigger_of(
        adr,
        "decision draft placement",
        START,
        ToolUse("t1", "Write", None, path),
        ToolResult("t1", "created"),
        ToolUse("t2", "Write", None, path),
        ToolResult("t2", "created"),
    )

    assert t.history == "repaired"


def test_a_gate_refusal_carrying_the_governing_text_arrives_by_the_gate_channel(git):
    gated = replace(git, deliveries=(*git.deliveries, GateRefusal("Bash", RelPath("rules/x.md"))))
    reason = f"PreToolUse:Bash hook error: [hooks/gate.sh]: {FORM_TEXT}"

    t = trigger_of(gated, COMMIT_FORM, START, shell("t1", CHAINED), ToolResult("t1", reason))

    assert timing_of(t, "gate_refusal") == "before execution"


# -- The results file's words, from a record on disk ------------------------------------------


def test_records_put_arrivals_history_and_outcome_in_the_results_words(git, tmp_path):
    entries = [
        instructions(UNRELATED),
        tool_call("t1", "Bash", {"command": CHAINED}),
        hook_context("PreToolUse", WHOLE_RULE, toolUseID="t1"),
        tool_output("t1", COMMITTED),
    ]
    path = write_record(tmp_path / "session.jsonl", entries)

    found = {t.check: t for t in trigger.records(git, path)}

    assert found[COMMIT_FORM].arrivals == {
        "session_start": "never",
        "hook_context": "before execution",
    }
    assert found[COMMIT_FORM].history == "right_first_time"
    assert found[COMMIT_FORM].final == "passed"


def test_a_call_the_record_never_answers_says_nothing_about_what_the_session_left(git):
    t = trigger_of(git, COMMIT_FORM, START, shell("t1", CHAINED), AT_USE)

    assert t.history == "never_taken"
    assert t.final is None
    assert timing_of(t, "hook_context") == "before execution"
