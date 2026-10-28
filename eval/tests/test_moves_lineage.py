"""A move run's ending, its continuation by move identity, what a stopped run blocks, and the
floor run a paired run may cite: each refusal shown on a known-bad input."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praxion_evals.adherence.lineage import (
    Finished,
    Interrupted,
    PartRef,
    SpendRefused,
    UnreadableTip,
)
from praxion_evals.adherence.moves.lineage import (
    Blind,
    ChangeDigest,
    CheckCounts,
    CitedFloor,
    Closed,
    FloorIdentity,
    FloorPart,
    MoveIdentity,
    NoCitation,
    NotFinished,
    OtherIdentity,
    ReadTip,
    Stopped,
    StoredRun,
    Unreadable,
    cite,
    close,
    continuable,
    continuation_refusals,
    pending_stop,
    refusal_text,
)
from praxion_evals.adherence.moves.stop import Launched, MoveStopReason

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=UTC)
DIGEST_A, DIGEST_B = "a" * 64, "b" * 64
IDENTITY = MoveIdentity(
    "Commit with a type prefix.\n", {"lean": (ChangeDigest("rules/git.md", DIGEST_A),)}
)
CHECKS = ("message", "staging")


def _stop(arm: str, scope: str) -> Stopped:
    session = Launched("t1", arm, 1)  # type: ignore[arg-type]
    return Stopped(MoveStopReason("auth", "401", arm, (session,), scope))  # type: ignore[arg-type]


FLOOR_STOP, PAIRED_BOTH, PAIRED_ONE = (
    _stop("floor", "one-arm"),
    _stop("lean", "both-arms"),
    _stop("lean", "one-arm"),
)


def _tip(ending, identity=IDENTITY, continued_by=None) -> ReadTip:
    return ReadTip("run-1", ending, identity, continued_by)


# --- endings ---


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        (Finished(), False),
        (SpendRefused(("t1",)), True),
        (Interrupted(), False),
        (FLOOR_STOP, True),
        (PAIRED_BOTH, True),
        (PAIRED_ONE, False),
    ],
)
def test_only_an_outage_or_a_spend_refusal_is_continuable(ending, expected):
    assert continuable(ending) is expected


def test_a_closed_run_is_never_continuable_and_needs_a_reason():
    assert not continuable(Closed("credential revoked", "t", {}, FLOOR_STOP))
    with pytest.raises(ValueError, match="needs a reason"):
        Closed("  ", "t", {}, FLOOR_STOP)


# --- continuation by move identity ---


def test_a_continuable_stop_under_the_same_identity_has_no_refusal():
    assert continuation_refusals(_tip(PAIRED_BOTH), IDENTITY, ()) == ()
    assert continuation_refusals(_tip(FLOOR_STOP), IDENTITY, ()) == ()


def test_a_changed_rule_text_is_refused_naming_it():
    now = replace(IDENTITY, moved_rule_text=IDENTITY.moved_rule_text + "- One more line.\n")

    refusals = continuation_refusals(_tip(PAIRED_BOTH), now, ())

    assert refusals == ("changed since the stop: the moved rule's text differs",)


def test_every_way_an_arm_change_differs_is_named():
    now = MoveIdentity(
        IDENTITY.moved_rule_text,
        {
            "lean": (ChangeDigest("rules/git.md", DIGEST_B),),
            "floor": (ChangeDigest("rules/other.md", DIGEST_A),),
        },
    )

    refusals = continuation_refusals(_tip(PAIRED_BOTH), now, ())

    assert len(refusals) == 2
    assert (
        "lean arm's change to rules/git.md has other content (aaaaaaaaaaaa -> bbbbbbbbbbbb)"
        in refusals[0]
    )
    assert "floor arm now changes rules/other.md" in refusals[1]


def test_a_dropped_arm_change_is_refused():
    now = replace(IDENTITY, arms={})

    assert continuation_refusals(_tip(PAIRED_BOTH), now, ()) == (
        "changed since the stop: the lean arm no longer changes rules/git.md",
    )


@pytest.mark.parametrize(
    ("ending", "words"),
    [
        (Finished(), "finished its plan"),
        (PAIRED_ONE, "lean arm alone"),
        (Interrupted(), "interrupted"),
        (Closed("gave up", "2026-10-28", {}, FLOOR_STOP), "closed on 2026-10-28: gave up"),
    ],
)
def test_an_ending_that_is_not_continuable_is_refused_naming_why(ending, words):
    (refusal,) = continuation_refusals(_tip(ending), IDENTITY, ())

    assert words in refusal


def test_a_continued_run_an_unknown_option_and_a_changed_tree_are_each_named():
    refusals = continuation_refusals(
        _tip(PAIRED_BOTH, continued_by="run-2"),
        IDENTITY,
        ("--seed", "--output"),
        ("tree: abc -> def",),
    )

    assert len(refusals) == 3
    assert "already has a continuation, run-2" in refusals[0]
    assert refusals[1].startswith("--seed would change what the run measures")
    assert refusals[2] == "changed since the stop: tree: abc -> def"


def test_an_unreadable_file_is_the_only_refusal():
    tip = UnreadableTip(Path("/x/run-1.json"), "not json")

    assert continuation_refusals(tip, IDENTITY, ()) == (
        "run-1.json cannot be read as a results file: not json",
    )


# --- what a stopped run blocks ---


def _stored(run: str, move: str, ending, continues=None) -> StoredRun:
    return StoredRun(PartRef(run, Path(f"{run}.json"), continues), move, ending)


def test_a_stopped_run_blocks_every_fresh_run_of_its_move_floor_or_paired():
    runs = [_stored("f1", "git", FLOOR_STOP), _stored("p1", "git", PAIRED_BOTH)]

    pending = pending_stop(runs, "git")

    assert pending is not None
    assert pending.run_id == "f1"
    assert pending_stop(runs[1:], "git").run_id == "p1"  # type: ignore[union-attr]


def test_a_stopped_run_blocks_no_other_move():
    assert pending_stop([_stored("f1", "git", FLOOR_STOP)], "adr") is None


def test_a_continued_closed_finished_or_one_arm_stopped_run_blocks_nothing():
    runs = [
        _stored("a", "git", FLOOR_STOP),
        _stored("b", "git", Finished(), continues="a"),
        _stored("c", "git", Closed("gave up", "t", {}, FLOOR_STOP)),
        _stored("d", "git", PAIRED_ONE),
    ]

    assert pending_stop(runs, "git") is None


# --- close ---


def test_closing_a_stopped_run_keeps_the_reason_the_time_and_the_interim_result():
    closed = close(_tip(FLOOR_STOP), "credential revoked", NOW, {"message": "clear"})

    assert closed == Closed("credential revoked", NOW.isoformat(), {"message": "clear"}, FLOOR_STOP)


@pytest.mark.parametrize("ending", [Finished(), Closed("again", "t", {}, FLOOR_STOP)])
def test_a_run_that_did_not_stop_cannot_be_closed(ending):
    with pytest.raises(ValueError, match="nothing to close"):
        close(_tip(ending), "why", NOW, {})


def test_a_continued_run_and_an_empty_reason_cannot_close():
    with pytest.raises(ValueError, match="only the latest part"):
        close(_tip(FLOOR_STOP, continued_by="run-2"), "why", NOW, {})
    with pytest.raises(ValueError, match="needs a reason"):
        close(_tip(FLOOR_STOP), " ", NOW, {})


# --- floor citation ---

FLOOR = FloorIdentity(
    tree="f" * 64,
    tasks=(("t1", "Commit notes."), ("t2", "Commit todo.")),
    checks=(("message", "Commit messages"), ("staging", "Staging")),
    model="claude-x",
    effort="high",
    settings=(("stop_count", "3"),),
)


def _floor(run: str, ending=None, continues=None, identity=FLOOR, counts=None) -> FloorPart:
    counts = (
        {"message": CheckCounts(1, 4), "staging": CheckCounts(2, 4)} if counts is None else counts
    )
    return FloorPart(
        PartRef(run, Path(f"{run}.json"), continues), identity, ending or Finished(), counts
    )


def test_any_part_of_a_finished_floor_lineage_resolves_to_the_whole_lineage():
    runs = {"a": _floor("a", FLOOR_STOP), "b": _floor("b", continues="a")}

    for part in ("a", "b"):
        cited = cite(runs, part, FLOOR, CHECKS)
        assert isinstance(cited, CitedFloor)
        assert cited.lineage == ("a", "b")
        assert cited.counts == {"message": CheckCounts(2, 8), "staging": CheckCounts(4, 8)}


def test_every_other_floor_run_of_the_same_identity_is_listed_beside_the_cited_one():
    elsewhere = replace(FLOOR, model="claude-y")
    runs = {
        "a": _floor("a"),
        "b": _floor("b"),
        "c": _floor("c", identity=elsewhere),
        "d": _floor("d"),
    }

    cited = cite(runs, "b", FLOOR, CHECKS)

    assert isinstance(cited, CitedFloor)
    assert (cited.lineage, cited.others) == (("b",), ("a", "d"))


def test_a_citation_of_nothing_or_of_a_run_no_floor_file_holds_is_refused():
    runs = {"a": _floor("a")}

    assert cite(runs, None, FLOOR, CHECKS) == NoCitation()
    assert cite(runs, "paired-1", FLOOR, CHECKS) == Unreadable(
        "paired-1", "no readable floor run holds run paired-1"
    )


def test_a_broken_lineage_is_refused_with_the_chain_walks_own_words():
    runs = {"b": _floor("b", continues="lost")}

    refusal = cite(runs, "b", FLOOR, CHECKS)

    assert isinstance(refusal, Unreadable)
    assert "has a gap" in refusal.reason


@pytest.mark.parametrize(
    "ending", [FLOOR_STOP, SpendRefused(), Interrupted(), Closed("why", "t", {}, FLOOR_STOP)]
)
def test_a_floor_lineage_that_stopped_or_was_closed_is_refused(ending):
    runs = {"a": _floor("a", ending)}

    refusal = cite(runs, "a", FLOOR, CHECKS)

    assert refusal == NotFinished("a", ending)
    assert "did not finish its plan" in refusal_text(refusal)


def test_a_floor_run_of_another_identity_is_refused_naming_each_difference():
    other = replace(
        FLOOR, tree="e" * 64, tasks=(("t1", "Commit notes."), ("t2", "Other.")), effort="low"
    )

    refusal = cite({"a": _floor("a")}, "a", other, CHECKS)

    assert isinstance(refusal, OtherIdentity)
    assert refusal.differences == (
        "the floor's tree differs: ffffffffffff -> eeeeeeeeeeee",
        "the floor's tasks differs: t2",
        "the floor's effort differs: high -> low",
    )


def test_a_floor_that_never_failed_a_declared_check_is_refused_naming_it():
    counts = {"message": CheckCounts(1, 4), "staging": CheckCounts(0, 4)}

    refusal = cite({"a": _floor("a", counts=counts)}, "a", FLOOR, CHECKS)

    assert refusal == Blind(("staging",))
    assert "never failed staging" in refusal_text(refusal)


def test_a_check_the_floor_never_scored_is_blind_too():
    refusal = cite({"a": _floor("a", counts={"message": CheckCounts(1, 4)})}, "a", FLOOR, CHECKS)

    assert refusal == Blind(("staging",))


def test_a_change_confined_to_the_lean_declaration_leaves_the_floor_run_citable():
    lean_changed = replace(IDENTITY, arms={"lean": (ChangeDigest("rules/git.md", DIGEST_B),)})

    assert continuation_refusals(_tip(PAIRED_BOTH), lean_changed, ())  # a paired run is refused
    assert isinstance(cite({"a": _floor("a")}, "a", FLOOR, CHECKS), CitedFloor)  # the floor is not


def test_failures_cannot_exceed_the_sessions_scored():
    with pytest.raises(ValueError, match="among the scored"):
        CheckCounts(5, 4)
