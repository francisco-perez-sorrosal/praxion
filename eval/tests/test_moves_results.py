"""The ``move-results/1`` codec, its atomic write under ``moves/`` alone, the index beside it, and
the earlier runs a listing names: each rule shown on a known-bad input."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence.lineage import Finished, Interrupted, SpendRefused
from praxion_evals.adherence.model import Failed, Passed
from praxion_evals.adherence.moves import results
from praxion_evals.adherence.moves.lineage import ChangeDigest, Closed, MoveIdentity, Stopped
from praxion_evals.adherence.moves.model import (
    Arrived,
    CheckTrigger,
    MoveName,
    NeverArrived,
    NothingToGrade,
    Pinned,
    Unknown,
)
from praxion_evals.adherence.moves.results import (
    EarlierMoveRuns,
    FloorRun,
    MoveRunCommon,
    MoveSession,
    PairedRun,
)
from praxion_evals.adherence.moves.stop import Launched, MoveStopReason
from tests.test_adherence_results import declared

DECLARED_AT = "2026-10-28T09:00:00+00:00"
FIRST_LAUNCH = "2026-10-28T09:05:00+00:00"
STARTED = "2026-10-28T09:10:00+00:00"
MOVE = MoveName("git-conventions")
IDENTITY = MoveIdentity(
    "Commit with a type prefix.\n", {"lean": (ChangeDigest("rules/git.md", "a" * 64),)}
)
PINNED = Pinned("none", "claude-opus-4-8", "high", "u" * 8)
STOP = Stopped(MoveStopReason("auth", "401", "lean", (Launched("t1", "lean", 1),), "both-arms"))


def trigger(check: str = "message", *, failed: bool = False):
    return CheckTrigger(
        check,
        {"session_start": Arrived("before composition"), "path_matched": NeverArrived()},
        Failed("no type prefix") if failed else Passed(),
        "not_repaired" if failed else "right_first_time",
        ("a gate said no",) if failed else (),
    )


def scored(task: str, arm: str, *, attempt: int = 1, failed: bool = False) -> MoveSession:
    return MoveSession(
        f"s-{task}-{arm}-{attempt}", task, arm, attempt, "scored", None,  # type: ignore[arg-type]
        {"message": trigger(failed=failed)}, STARTED, 0.25, 4200,
    )  # fmt: skip


def refused(task: str, arm: str) -> MoveSession:
    return MoveSession(
        f"s-{task}-{arm}-r", task, arm, 1, "refused", "no point-of-use text arrived", {}, STARTED  # type: ignore[arg-type]
    )  # fmt: skip


def common(run_id: str, arms: tuple[str, ...], sessions=(), **changes) -> MoveRunCommon:
    fields = {
        "run_id": run_id,
        "move": MOVE,
        "identity": IDENTITY,
        "settings": declared(2),
        "pinned": dict.fromkeys(arms, PINNED),
        "declared_at": DECLARED_AT,
        "first_launch_at": FIRST_LAUNCH if sessions else None,
        "seed": 7,
        "launch_orders": {},
        "sessions": tuple(sessions),
        "continues": None,
        "ending": Finished(),
        "harness_version": "2.1.312",
        "earlier": EarlierMoveRuns(),
    }
    return MoveRunCommon(**{**fields, **changes})  # type: ignore[arg-type]


def floor_run(run_id: str = "floor-1", **changes) -> FloorRun:
    sessions = changes.pop("sessions", (scored("t1", "floor", failed=True), scored("t2", "floor")))
    return FloorRun(common(run_id, ("floor",), sessions, **changes))


def paired_run(run_id: str = "paired-1", *, flip="clear", **changes) -> PairedRun:
    sessions = changes.pop(
        "sessions",
        (scored("t1", "lean"), scored("t1", "full"), scored("t2", "full"), refused("t2", "lean")),
    )
    orders = {"t1": ("lean", "full"), "t2": ("full", "lean")}
    base = common(run_id, ("full", "lean"), sessions, launch_orders=orders, **changes)
    verdicts = {} if flip == "underpowered" else {"message": "no regression"}
    return PairedRun(base, ("floor-1",), flip, verdicts)


def moves_dir(tmp_path: Path) -> Path:
    return tmp_path / ".ai-state" / "eval_ledger" / "adherence" / "moves"


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


# --- the codec ---


def test_a_floor_round_trip_keeps_every_field(tmp_path):
    run = floor_run(
        sessions=(
            scored("t1", "floor", failed=True),
            refused("t2", "floor"),
            MoveSession("s-err", "t3", "floor", 1, "errored", "auth", {}, STARTED),  # type: ignore[arg-type]
        ),
        ending=Closed("credit cut off", "2026-10-28T11:00:00+00:00", {"message": "1/1"}, STOP),
        earlier=EarlierMoveRuns(("floor-0",), (), {"old": "the moved rule's text differs"}),
    )

    path = results.write(moves_dir(tmp_path), run)

    assert results.load(path) == run


def test_a_session_that_left_nothing_to_grade_round_trips(tmp_path):
    left_nothing = replace(trigger(), final=NothingToGrade("no commit made"))
    run = floor_run(sessions=(replace(scored("t1", "floor"), checks={"message": left_nothing}),))

    path = results.write(moves_dir(tmp_path), run)

    assert results.load(path) == run


def test_the_planned_tasks_of_a_run_round_trip_and_an_older_file_records_none(tmp_path):
    run = floor_run(planned_tasks=("t1", "t2", "t3"))
    path = results.write(moves_dir(tmp_path), run)
    older = json.loads(path.read_text(encoding="utf-8"))
    del older["planned_tasks"]

    assert results.load(path).common.planned_tasks == ("t1", "t2", "t3")
    assert results.from_json(older).common.planned_tasks == ()


def test_a_run_that_launched_a_task_it_did_not_plan_is_refused():
    with pytest.raises(ValueError, match="unplanned tasks launched"):
        floor_run(planned_tasks=("t2", "t3"))  # the default sessions include t1


def test_a_paired_round_trip_keeps_every_field_and_derives_its_complete_pairs(tmp_path):
    run = paired_run()

    path = results.write(moves_dir(tmp_path), run)

    assert results.load(path) == run
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["complete_pairs"] == 1  # t2's lean take was refused
    assert document["subject"] == {"kind": "move", "name": "git-conventions"}
    assert document["allowance_method"] == "own-discordance-exact"


def test_an_unreadable_record_round_trips_as_unknown_never_as_never_arrived(tmp_path):
    unreadable = CheckTrigger.unreadable("message", ("session_start", "hook_context"))
    session = replace(scored("t1", "floor"), checks={"message": unreadable})

    path = results.write(moves_dir(tmp_path), floor_run(sessions=(session,)))

    loaded = results.load(path).common.sessions[0].checks["message"]
    assert loaded.arrivals == {"session_start": Unknown(), "hook_context": Unknown()}
    assert loaded.history is None
    assert loaded.final is None


@pytest.mark.parametrize("ending", [Finished(), STOP, SpendRefused(("t1",)), Interrupted()])
def test_every_ending_round_trips(ending):
    assert results.ending_from_json(results.ending_to_json(ending)) == ending


def test_a_floor_file_holding_a_paired_runs_fields_is_refused():
    document = results.to_json(floor_run())

    for key, value in (
        ("cited_floor", ["floor-0"]),
        ("verdicts", {"message": "x"}),
        ("flip", "clear"),
    ):
        with pytest.raises(ValueError, match="floor run carries none of a paired run's fields"):
            results.from_json({**document, key: value})


def test_a_paired_file_missing_its_citation_or_flip_is_refused():
    document = results.to_json(paired_run())

    with pytest.raises(ValueError, match="cites a floor lineage"):
        results.from_json({**document, "cited_floor": []})
    del document["flip"]
    with pytest.raises(ValueError, match="lacks 'flip'"):
        results.from_json(document)


def test_a_run_kind_that_disagrees_with_the_arms_it_pins_or_launches_is_refused():
    with pytest.raises(ValueError, match="pins the settings of"):
        FloorRun(common("floor-1", ("floor", "lean")))
    with pytest.raises(ValueError, match="launched no session in"):
        FloorRun(common("floor-1", ("floor",), (scored("t1", "lean"),)))
    with pytest.raises(ValueError, match="launched without a recorded order"):
        PairedRun(common("p", ("full", "lean"), (scored("t1", "full"),)), ("floor-1",), "clear", {})


def test_a_role_subject_a_wrong_allowance_method_and_an_unknown_schema_are_refused():
    document = results.to_json(paired_run())

    with pytest.raises(ValueError, match="names a move as its subject"):
        results.from_json({**document, "subject": {"kind": "role", "name": "researcher"}})
    with pytest.raises(ValueError, match="allowance method"):
        results.from_json({**document, "allowance_method": "none"})
    with pytest.raises(ValueError, match="unknown results schema"):
        results.from_json({**document, "schema": "move-results/2"})


def test_a_session_is_legal_in_one_shape_only():
    with pytest.raises(ValueError, match="graded no check"):
        MoveSession("s", "t", "floor", 1, "refused", "why", {"message": trigger()}, STARTED)
    with pytest.raises(ValueError, match="records the checks"):
        MoveSession("s", "t", "floor", 1, "scored", None, {}, STARTED)
    with pytest.raises(ValueError, match="reason"):
        MoveSession("s", "t", "floor", 1, "errored", None, {}, STARTED)


def test_a_session_before_the_first_launch_or_a_launch_before_the_declaration_is_refused():
    early = replace(scored("t1", "floor"), started_at="2026-10-28T09:01:00+00:00")
    with pytest.raises(ValueError, match="began before the first launch"):
        floor_run(sessions=(early,))
    with pytest.raises(ValueError, match="declared before the first launch"):
        floor_run(first_launch_at=DECLARED_AT)


# --- writing under moves/ alone ---


def test_a_move_write_leaves_the_role_directory_and_the_role_index_byte_identical(tmp_path):
    role_dir = tmp_path / ".ai-state" / "eval_ledger" / "adherence"
    role_dir.mkdir(parents=True)
    (role_dir / "20261001T000000Z-abc.json").write_text('{"role": "run"}\n')
    (role_dir / "index.json").write_text('{"schema": 2, "runs": {}}\n')
    before = tree_bytes(role_dir)

    results.write(role_dir / "moves", floor_run())
    results.write(role_dir / "moves", paired_run())

    after = tree_bytes(role_dir)
    assert {k: v for k, v in after.items() if not k.startswith("moves/")} == before
    assert sorted(k for k in after if k.startswith("moves/")) == [
        "moves/floor-1.json",
        "moves/index.json",
        "moves/paired-1.json",
    ]


def test_results_are_written_only_into_a_directory_named_moves(tmp_path):
    with pytest.raises(ValueError, match="written under moves/"):
        results.write(tmp_path / "adherence", floor_run())
    assert not (tmp_path / "adherence").exists()


def test_what_a_run_declared_cannot_change_once_written(tmp_path):
    directory = moves_dir(tmp_path)
    results.write(directory, floor_run())

    changed = floor_run(settings=declared(5))
    with pytest.raises(ValueError, match="declared cannot change"):
        results.write(directory, changed)

    grown = floor_run(
        sessions=(scored("t1", "floor"), scored("t2", "floor"), scored("t3", "floor"))
    )
    results.write(directory, grown)  # more sessions are the normal rewrite
    assert len(results.load(directory / "floor-1.json").common.sessions) == 3


# --- the index ---


def test_the_index_is_regenerated_whole_after_every_write_and_lists_floor_runs_apart(tmp_path):
    directory = moves_dir(tmp_path)
    results.write(directory, floor_run())
    results.write(directory, paired_run())

    index = json.loads((directory / "index.json").read_text(encoding="utf-8"))

    assert index["schema"] == 1
    assert index["skipped"] == []
    assert index["runs"]["floor-1"] == {
        "move": "git-conventions",
        "run_kind": "floor",
        "lineage_root": "floor-1",
        "continues": None,
        "ending": "finished",
        "standing": "finished",
    }
    assert index["runs"]["paired-1"]["run_kind"] == "paired"
    assert index["runs"]["paired-1"]["standing"] == "clear"


def test_a_floor_run_never_stands_on_a_flip_label_and_a_closed_paired_run_stands_not_clear(
    tmp_path,
):
    directory = moves_dir(tmp_path)
    closed = Closed("gave up", "2026-10-28T11:00:00+00:00", {}, STOP)
    results.write(directory, floor_run("floor-s", ending=STOP))
    results.write(directory, floor_run("floor-c", ending=closed))
    results.write(directory, paired_run("paired-c", flip="clear", ending=closed))
    results.write(directory, paired_run("paired-u", flip="underpowered", ending=STOP))

    standing = {
        k: v["standing"]
        for k, v in json.loads((directory / "index.json").read_text())["runs"].items()
    }

    assert standing == {
        "floor-s": "stopped",
        "floor-c": "closed",
        "paired-c": "not clear",
        "paired-u": "underpowered",
    }


def test_every_part_of_a_continued_lineage_carries_the_tips_standing(tmp_path):
    directory = moves_dir(tmp_path)
    results.write(directory, floor_run("part-1", ending=STOP))
    results.write(
        directory, floor_run("part-2", continues="part-1", sessions=(scored("t3", "floor"),))
    )

    runs = json.loads((directory / "index.json").read_text())["runs"]

    assert runs["part-1"]["standing"] == runs["part-2"]["standing"] == "finished"
    assert runs["part-1"]["lineage_root"] == runs["part-2"]["lineage_root"] == "part-1"
    assert runs["part-1"]["ending"] == "stopped"


def test_reindex_rebuilds_the_index_from_the_files_alone_and_names_what_is_no_run(tmp_path):
    directory = moves_dir(tmp_path)
    results.write(directory, floor_run())
    (directory / "stray.json").write_text("{not json")
    (directory / "other-name.json").write_text(json.dumps(results.to_json(floor_run("floor-9"))))
    (directory / "index.json").write_text("stale")

    results.write_index(directory)

    index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    assert list(index["runs"]) == ["floor-1"]
    assert index["skipped"] == ["other-name.json", "stray.json"]


# --- earlier runs ---


def test_earlier_floor_runs_are_listed_as_floor_runs_and_never_among_paired_draws(tmp_path):
    directory = moves_dir(tmp_path)
    results.write(directory, floor_run("floor-1"))
    results.write(directory, floor_run("floor-2"))
    results.write(directory, paired_run("paired-1"))

    listing = results.earlier_runs(directory, MOVE, IDENTITY)

    assert listing.floor == ("floor-1", "floor-2")
    assert listing.paired == ("paired-1",)
    assert listing.apart == {}


def test_a_run_of_another_identity_or_move_is_listed_apart_or_left_out(tmp_path):
    directory = moves_dir(tmp_path)
    other = replace(IDENTITY, moved_rule_text="Commit with a ticket id.\n")
    results.write(directory, floor_run("floor-1", identity=other))
    results.write(directory, floor_run("floor-2", move=MoveName("adr-conventions")))
    results.write(directory, floor_run("floor-3"))

    listing = results.earlier_runs(directory, MOVE, IDENTITY, exclude=("floor-3",))

    assert listing.floor == ()
    assert listing.apart == {"floor-1": "the moved rule's text differs"}


def test_a_continued_lineage_is_listed_once_named_by_every_part(tmp_path):
    directory = moves_dir(tmp_path)
    results.write(directory, floor_run("part-1", ending=STOP))
    results.write(directory, floor_run("part-2", continues="part-1"))

    assert results.earlier_runs(directory, MOVE, IDENTITY).floor == ("part-1 + part-2",)
