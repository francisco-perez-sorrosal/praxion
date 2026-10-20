"""Tests for kernel_run_evidence.py: what the gate derives from a cited run's results files.

Hermetic: each case plants results files built from literal dicts in `tmp_path` and reads them
back through `read_run_files`. A known-bad lineage or standing is refused beside the known-good
one that is read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_run_evidence as kre  # noqa: E402

ROLE = "researcher"
FIRST, SECOND, THIRD = (
    "20261101T000000Z-aaaaaa",
    "20261102T000000Z-bbbbbb",
    "20261103T000000Z-cccccc",
)
CONVENTION = "researcher: it follows the convention its project's instruction file states"


# -- Builders: results files as the eval writes them --------------------------------------


def session(task: str, arm: str, measured: bool = True, role: str = ROLE) -> dict:
    status = {"kind": "measured"} if measured else {"kind": "errored", "error_kind": "timeout"}
    setup = {"arm": arm, "role": role, "task_id": task, "template_id": f"template-{task}"}
    return {"setup": setup, "status": status}


def both_arms(*tasks: str) -> list[dict]:
    return [session(task, arm) for task in tasks for arm in ("full", "lean")]


def verdict(pairs: int = 24, flip: str = "clear", checks: tuple[str, ...] = ("C1", "C3")) -> dict:
    return {
        "underpowered": False,
        "flip": flip,
        "complete_pairs": pairs,
        "check_verdicts": dict.fromkeys(checks, "non-inferior"),
        "check_details": {name: {} for name in checks},
        "not_covered": [],
    }


def underpowered_verdict(pairs: int = 2) -> dict:
    return {
        "underpowered": True,
        "reason": f"{pairs} complete pairs, fewer than the 20 declared",
        "complete_pairs": pairs,
        "required_pairs": 20,
        "check_verdicts": {},
        "not_covered": [],
    }


def standing_entry(parts: list[str], pairs: int = 24, flip: str = "clear", scored=("C1",)) -> dict:
    return {
        "lineage_root": parts[0],
        "parts": parts,
        "complete_pairs": pairs,
        "flip": flip,
        "scored_checks": list(scored),
    }


def results(run_id: str, sessions: list[dict], **extra) -> dict:
    """A results file; `extra` adds run keys (`continues`, `ending`) or top-level keys."""
    run_keys = {key: extra.pop(key) for key in ("continues", "ending") if key in extra}
    return {
        "schema_version": "adherence/1",
        "run": {"id": run_id, **run_keys},
        "sessions": sessions,
        "verdicts": extra.pop("verdicts", {ROLE: verdict()}),
        **extra,
    }


def read(tmp_path: Path, *files: dict) -> tuple[kre.RunFile, ...]:
    for data in files:
        (tmp_path / f"{data['run']['id']}.json").write_text(json.dumps(data), encoding="utf-8")
    return kre.read_run_files(tmp_path)


# -- A one-part file written before the standing key ----------------------------------------


def test_legacy_file_reads_its_verdict_as_the_standing_of_the_run(tmp_path):
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: verdict(24, "clear")}))

    standing = kre.recorded_standing(files, FIRST, ROLE)

    assert standing == kre.Standing(24, "clear", ("C1", "C3"))


def test_legacy_scored_checks_leave_out_the_checks_the_verdict_does_not_cover(tmp_path):
    uncovered = verdict(checks=("C1", "C3", CONVENTION)) | {"not_covered": [CONVENTION]}
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: uncovered}))

    assert kre.recorded_standing(files, FIRST, ROLE).scored_checks == ("C1", "C3")


def test_legacy_scored_checks_fall_back_to_the_details_when_no_per_check_verdict_is_listed(
    tmp_path,
):
    details_only = verdict() | {"check_verdicts": {}}
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: details_only}))

    assert kre.recorded_standing(files, FIRST, ROLE).scored_checks == ("C1", "C3")


def test_legacy_underpowered_file_stands_underpowered_and_scored_nothing(tmp_path):
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: underpowered_verdict()}))

    assert kre.recorded_standing(files, FIRST, ROLE) == kre.Standing(2, "underpowered", ())
    assert kre.judged_standing(files, FIRST, ROLE) == "underpowered"


def test_legacy_scored_checks_come_from_the_check_verdicts_before_the_details(tmp_path):
    differing = verdict(checks=("C1",)) | {"check_details": {"C9": {}}}
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: differing}))

    assert kre.recorded_standing(files, FIRST, ROLE).scored_checks == ("C1",)


def test_legacy_flip_label_wins_over_an_underpowered_flag(tmp_path):
    inconsistent = verdict(flip="clear") | {"underpowered": True}
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: inconsistent}))

    assert kre.recorded_standing(files, FIRST, ROLE).flip == "clear"


def test_legacy_file_with_no_complete_pair_is_read_with_a_zero_count(tmp_path):
    files = read(tmp_path, results(FIRST, [], verdicts={ROLE: underpowered_verdict(pairs=0)}))

    assert kre.recorded_standing(files, FIRST, ROLE).complete_pairs == 0


def test_legacy_verdict_that_does_not_say_what_it_left_uncovered_is_unrecorded(tmp_path):
    silent = {key: value for key, value in verdict().items() if key != "not_covered"}
    files = read(tmp_path, results(FIRST, both_arms("t1"), verdicts={ROLE: silent}))

    assert isinstance(files[0].recorded, kre.Unrecorded)


# -- Complete pairs: the latest session of each arm wins ------------------------------------


def test_latest_session_per_arm_wins_across_the_parts_of_a_lineage(tmp_path):
    first = results(FIRST, [session("t1", "full"), session("t1", "lean", measured=False)])
    second = results(SECOND, [session("t1", "lean")], continues=FIRST)

    files = read(tmp_path, first, second)

    assert kre.derive(files, SECOND, ROLE) == kre.Derived((FIRST, SECOND), 1)
    assert kre.derive(files, FIRST, ROLE) == kre.Derived((FIRST, SECOND), 1)  # any part, same run


def test_task_whose_latest_lean_session_errored_is_not_a_complete_pair(tmp_path):
    first = results(FIRST, both_arms("t1", "t2"))
    second = results(SECOND, [session("t2", "lean", measured=False)], continues=FIRST)

    files = read(tmp_path, first, second)

    assert kre.derive(files, SECOND, ROLE).complete_pairs == 1


def test_task_whose_lean_error_came_before_its_measured_session_stays_complete(tmp_path):
    sessions = [session("t1", "lean", measured=False), session("t1", "full"), session("t1", "lean")]

    files = read(tmp_path, results(FIRST, sessions))

    assert kre.derive(files, FIRST, ROLE).complete_pairs == 1


def test_a_task_run_in_one_arm_only_is_not_a_pair_and_other_roles_are_not_counted(tmp_path):
    sessions = [session("t1", "full"), *both_arms("t2"), *[session("t3", "full", role="other")]]
    sessions += [session("t3", "lean", role="other")]

    files = read(tmp_path, results(FIRST, sessions))

    assert kre.derive(files, FIRST, ROLE).complete_pairs == 1
    assert kre.derive(files, FIRST, "other").complete_pairs == 1


# -- The lineage: a chain of continues links, or a refusal --------------------------------------


def test_a_fork_in_the_continues_links_is_refused(tmp_path):
    root = results(FIRST, both_arms("t1"))
    files = read(
        tmp_path,
        root,
        results(SECOND, both_arms("t2"), continues=FIRST),
        results(THIRD, both_arms("t3"), continues=FIRST),
    )

    with pytest.raises(kre.RunEvidenceError, match=f"continued by 2 runs: {SECOND}, {THIRD}"):
        kre.derive(files, SECOND, ROLE)


def test_a_gap_in_the_continues_links_is_refused(tmp_path):
    files = read(tmp_path, results(SECOND, both_arms("t1"), continues=FIRST))

    with pytest.raises(
        kre.RunEvidenceError, match=f"{SECOND} continues {FIRST}, which no results file holds"
    ):
        kre.derive(files, SECOND, ROLE)


def test_a_run_no_file_holds_is_refused(tmp_path):
    files = read(tmp_path, results(FIRST, []))

    with pytest.raises(kre.RunEvidenceError, match="no results file holds run " + SECOND):
        kre.derive(files, SECOND, ROLE)


def test_a_run_held_by_two_files_is_refused(tmp_path):
    (tmp_path / "again.json").write_text(json.dumps(results(FIRST, [])), encoding="utf-8")
    files = read(tmp_path, results(FIRST, []))

    with pytest.raises(kre.RunEvidenceError, match="two results files hold run"):
        kre.derive(files, FIRST, ROLE)


def test_a_loop_in_the_continues_links_is_refused(tmp_path):
    files = read(
        tmp_path,
        results(FIRST, [], continues=SECOND),
        results(SECOND, [], continues=FIRST),
    )

    with pytest.raises(kre.RunEvidenceError, match="which continues it"):
        kre.derive(files, FIRST, ROLE)


def test_a_loop_that_does_not_include_the_run_asked_about_is_refused(tmp_path):
    files = read(
        tmp_path,
        results(FIRST, [], continues=SECOND),
        results(SECOND, [], continues=THIRD),
        results(THIRD, [], continues=SECOND),
    )

    with pytest.raises(kre.RunEvidenceError, match=f"{THIRD} continues {SECOND}, which continues"):
        kre.derive(files, FIRST, ROLE)


# -- A recorded standing -------------------------------------------------------------------


def test_a_recorded_standing_is_read_as_the_lineage_standing_of_its_run(tmp_path):
    recorded = {ROLE: standing_entry([FIRST, SECOND], pairs=24, flip="clear", scored=("C1", "C2"))}
    files = read(
        tmp_path,
        results(FIRST, both_arms("t1")),
        results(SECOND, both_arms("t2"), continues=FIRST, standing=recorded),
    )

    assert kre.recorded_standing(files, FIRST, ROLE) == kre.Standing(24, "clear", ("C1", "C2"))
    assert kre.judged_standing(files, SECOND, ROLE) == "clear"
    tip = files[-1].recorded
    assert isinstance(tip, kre.Lineage)
    assert tip.standing[ROLE].parts == (FIRST, SECOND)


@pytest.mark.parametrize(
    ("standing", "reason"),
    [
        ({ROLE: standing_entry([FIRST]) | {"complete_pairs": "24"}}, "complete_pairs '24'"),
        ({ROLE: standing_entry([FIRST]) | {"complete_pairs": True}}, "complete_pairs True"),
        ({ROLE: standing_entry([FIRST]) | {"complete_pairs": -1}}, "complete_pairs -1"),
        ({ROLE: standing_entry([FIRST]) | {"flip": "maybe"}}, "none of clear, not clear, under"),
        ({ROLE: standing_entry([FIRST]) | {"scored_checks": ["C3", "C1"]}}, "sorted and unique"),
        ({ROLE: standing_entry([FIRST]) | {"scored_checks": ["C1", "C1"]}}, "sorted and unique"),
        ({ROLE: standing_entry([FIRST]) | {"parts": []}}, "lineage root as its first part"),
        ({ROLE: standing_entry([FIRST]) | {"lineage_root": SECOND}}, "lineage root as its first"),
        ({ROLE: standing_entry([FIRST]) | {"parts": FIRST}}, "is not a list"),
        ({ROLE: standing_entry([FIRST]) | {"parts": [1]}}, "1 is not text"),
        ({ROLE: {k: v for k, v in standing_entry([FIRST]).items() if k != "flip"}}, "'flip'"),
        ({ROLE: [FIRST]}, "is not a mapping"),
        ([FIRST], "is not a mapping"),
    ],
)
def test_a_malformed_standing_is_refused_naming_the_run_and_what_is_wrong(
    tmp_path, standing, reason
):
    files = read(tmp_path, results(FIRST, both_arms("t1"), standing=standing))

    assert isinstance(files[0].recorded, kre.Unrecorded)
    with pytest.raises(kre.RunEvidenceError, match="standing this gate cannot read") as refusal:
        kre.judged_standing(files, FIRST, ROLE)
    assert f"run {FIRST} records" in str(refusal.value)
    assert reason in str(refusal.value)


def test_a_standing_that_omits_the_role_is_refused_and_one_that_names_it_is_read(tmp_path):
    files = read(
        tmp_path, results(FIRST, both_arms("t1"), standing={ROLE: standing_entry([FIRST])})
    )

    assert kre.judged_standing(files, FIRST, ROLE) == "clear"
    with pytest.raises(kre.RunEvidenceError, match="records no standing for verifier"):
        kre.judged_standing(files, FIRST, "verifier")


def test_a_part_of_a_continued_run_without_a_standing_is_unrecorded_and_names_itself(tmp_path):
    first = results(FIRST, both_arms("t1"))
    second = results(SECOND, both_arms("t2"), continues=FIRST)

    files = read(tmp_path, first, second)

    assert [file.recorded for file in files] == [
        kre.Unrecorded(f"run {FIRST} is part of a continued run and records no standing"),
        kre.Unrecorded(f"run {SECOND} is part of a continued run and records no standing"),
    ]
    with pytest.raises(kre.RunEvidenceError, match=f"run {SECOND} is part of a continued run"):
        kre.recorded_standing(files, SECOND, ROLE)


def test_a_file_that_nothing_continues_keeps_its_one_part_reading(tmp_path):
    files = read(tmp_path, results(FIRST, both_arms("t1")), results(SECOND, both_arms("t2")))

    assert all(isinstance(file.recorded, kre.LegacyOnePart) for file in files)


# -- A closed ending ---------------------------------------------------------------------


def test_a_closed_tip_is_judged_not_clear_without_a_recorded_standing(tmp_path):
    first = results(FIRST, both_arms("t1"), standing={ROLE: standing_entry([FIRST])})
    closed = results(SECOND, both_arms("t2"), continues=FIRST, ending={"kind": "closed"})

    files = read(tmp_path, first, closed)

    assert kre.judged_standing(files, FIRST, ROLE) == "not clear"
    with pytest.raises(kre.RunEvidenceError):
        kre.recorded_standing(files, FIRST, ROLE)


def test_a_tip_that_ended_in_any_other_way_is_judged_by_what_it_records(tmp_path):
    ended = results(
        FIRST,
        both_arms("t1"),
        ending={"kind": "finished"},
        standing={ROLE: standing_entry([FIRST], flip="underpowered", scored=())},
    )

    files = read(tmp_path, ended)

    assert kre.judged_standing(files, FIRST, ROLE) == "underpowered"


# -- Reading the directory ---------------------------------------------------------------


def test_json_that_is_no_results_file_is_passed_over_and_the_rest_still_read(tmp_path):
    (tmp_path / "0-index.json").write_text(json.dumps({"schema": 2, "runs": {}}), encoding="utf-8")
    (tmp_path / "0-broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "0-list.json").write_text("[]", encoding="utf-8")
    (tmp_path / "0-bad-arm.json").write_text(
        json.dumps(results(SECOND, [session("t1", "middle")])), encoding="utf-8"
    )
    (tmp_path / "0-note.txt").write_text(json.dumps(results(THIRD, [])), encoding="utf-8")

    files = read(tmp_path, results(FIRST, []))

    assert [file.run_id for file in files] == [FIRST]


def test_a_directory_that_does_not_exist_holds_no_results_files(tmp_path):
    assert kre.read_run_files(tmp_path / "missing") == ()


def test_sessions_keep_their_file_order_and_whether_they_were_measured(tmp_path):
    files = read(
        tmp_path, results(FIRST, [session("b", "lean", measured=False), session("a", "full")])
    )

    assert [(s.task_id, s.template_id, s.arm, s.measured) for s in files[0].sessions] == [
        ("b", "template-b", "lean", False),
        ("a", "template-a", "full", True),
    ]
    assert files[0].ending == kre.LEGACY_ENDING
    assert files[0].continues is None


# -- The convention check's name ---------------------------------------------------------------


def test_the_convention_check_name_fills_the_role_into_the_template():
    assert kre.convention_check_name(ROLE) == CONVENTION
    assert kre.convention_check_name("verifier").startswith("verifier: it follows")
