"""The results file: written whole and atomically, loaded strictly, verdicts recomputed."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praxion_evals.adherence import lineage, results, session_loop
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.model import (
    Assessed,
    DeclaredSettings,
    Errored,
    Failed,
    Measured,
    NoRegression,
    NotMeasured,
    Passed,
    Regression,
    RuleRef,
    SessionRecord,
    SessionSetup,
    SessionStatus,
    Underpowered,
)
from praxion_evals.adherence.results import (
    CatalogEntry,
    EarlierRun,
    RunInfo,
    RunResults,
)
from praxion_evals.adherence.transcript import StoppedAtCap

COMMIT = "0123456789abcdef0123456789abcdef01234567"
DECLARED_AT = "2026-10-12T08:59:00Z"
STARTED_AT = "2026-10-12T09:00:00Z"
RULE = RuleRef("rules/swe/agent-behavioral-contract.md", "Agent Behavioral Contract")
MECHANICAL = CatalogEntry("C1", "mechanical", RULE, True, None)
JUDGED = CatalogEntry("C3", "judged", RULE, True, "a return that states no assumption")


def declared(required_pairs: int = 1) -> DeclaredSettings:
    return DeclaredSettings(
        margin_pp=10.0,
        method="tango-score",
        confidence=0.95,
        sidedness="one-sided",
        required_pairs=required_pairs,
        pair_slack=0,
        retry_policy="one retry per session, for infrastructure errors only",
        allowance_source=None,
        allowances={},
    )


def session(
    task: str,
    arm: str,
    status: SessionStatus | None = None,
    *,
    role: str = "researcher",
    commit: str = COMMIT,
    started_at: str = STARTED_AT,
) -> SessionRecord:
    setup = SessionSetup(arm, commit, role, task, "template", 7)  # type: ignore[arg-type]
    return SessionRecord(
        setup=setup,
        status=status or Measured({"C1": Passed(), "C3": Passed()}, 1000),
        cost_usd=0.01,
        duration_ms=1000,
        started_at=started_at,
    )


def pair_of_sessions(task: str, **kwargs) -> tuple[SessionRecord, SessionRecord]:
    return session(task, "full", **kwargs), session(task, "lean", **kwargs)


def run_results(
    sessions=(),
    *,
    run_id: str = "run-a",
    settings: DeclaredSettings | None = None,
    declared_at: str = DECLARED_AT,
    roles=("researcher",),
    observed_error=None,
    extra=None,
) -> RunResults:
    return RunResults(
        run=RunInfo(
            id=run_id,
            model="claude-opus-5-5",
            claude_code_version="9.9.9",
            complete=True,
            refused_launches=(),
            earlier_runs={"researcher": (EarlierRun("run-0", "not clear"),)},
            extra={"seed": 7, "effort": "high", **(extra or {})},
        ),
        settings=settings or declared(),
        declared_at=declared_at,
        catalog=dict.fromkeys(roles, (MECHANICAL, JUDGED)),
        arms={role: {"full": {"built": True}, "lean": {"built": True}} for role in roles},
        sessions=tuple(sessions),
        golden_bad_case_verdicts=None
        if observed_error is None
        else {"observed_error": observed_error},
    )


# ---------------------------------------------------------------------------
# The document round-trips and loads strictly
# ---------------------------------------------------------------------------


def test_a_results_file_round_trips_with_its_additive_run_keys(tmp_path: Path):
    original = run_results([*pair_of_sessions("t1")], observed_error=0.25)
    path = tmp_path / "run.json"

    results.write_atomic(path, original)
    loaded = results.load(path)

    assert loaded == original
    assert loaded.run.extra == {"seed": 7, "effort": "high"}
    assert json.loads(path.read_text())["schema_version"] == "adherence/1"


def test_load_rejects_an_unknown_schema(tmp_path: Path):
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results())
    document = json.loads(path.read_text())
    document["schema_version"] = "adherence/2"
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="adherence/2"):
        results.load(path)


@pytest.mark.parametrize("declared_at", [STARTED_AT, "2026-10-12T09:00:01Z"])
def test_load_rejects_settings_not_declared_before_every_session(tmp_path: Path, declared_at: str):
    path = tmp_path / "run.json"
    document = results.to_json(run_results([*pair_of_sessions("t1")]))
    document["settings"]["declared_at"] = declared_at
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="not before the session"):
        results.load(path)


def test_a_timestamp_without_an_offset_is_refused():
    with pytest.raises(ValueError, match="UTC offset"):
        run_results([session("t1", "full", started_at="2026-10-12T09:00:00")])


def test_a_session_of_a_role_with_no_catalog_is_refused():
    with pytest.raises(ValueError, match="no catalog"):
        run_results([session("t1", "full", role="verifier")])


def test_a_judged_check_must_record_its_golden_bad_case():
    with pytest.raises(ValueError, match="golden bad case"):
        CatalogEntry("C3", "judged", RULE, True, None)


@pytest.mark.parametrize("observed", [-0.1, 1.5])
def test_the_judges_observed_error_is_a_rate(observed: float):
    with pytest.raises(ValueError, match="rate"):
        run_results(observed_error=observed)


def test_a_catalog_entry_is_built_from_a_real_check():
    entries = [results.catalog_entry(check) for check in check_catalog("researcher")]

    judged = [e for e in entries if e.kind == "judged"]
    assert judged
    assert all(e.golden_bad_case for e in judged)
    assert all(e.golden_bad_case is None for e in entries if e.kind == "mechanical")


# ---------------------------------------------------------------------------
# The start-of-run refusal and the atomic write
# ---------------------------------------------------------------------------


def test_an_existing_file_is_refused_at_start_and_left_untouched(tmp_path: Path):
    path = tmp_path / "run.json"
    path.write_text("earlier evidence")

    with pytest.raises(FileExistsError, match="--overwrite"):
        results.refuse_existing(path, overwrite=False)

    assert path.read_text() == "earlier evidence"


def test_overwrite_and_an_absent_path_both_pass_the_start_check(tmp_path: Path):
    path = tmp_path / "run.json"
    results.refuse_existing(path, overwrite=False)
    path.write_text("earlier evidence")

    results.refuse_existing(path, overwrite=True)


def test_a_crash_between_sessions_leaves_a_loadable_file_with_every_finished_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "run.json"
    finished: list[SessionRecord] = []
    for task in ("t1", "t2"):
        finished += pair_of_sessions(task)
        results.write_atomic(path, run_results(finished))
    real_replace = os.replace

    def crash(source, target):
        raise OSError("the machine went away")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError, match="went away"):
        results.write_atomic(path, run_results([*finished, *pair_of_sessions("t3")]))
    monkeypatch.setattr(os, "replace", real_replace)

    survivor = results.load(path)
    assert [r.setup.task_id for r in survivor.sessions] == ["t1", "t1", "t2", "t2"]
    assert [p.name for p in tmp_path.iterdir()] == ["run.json"], "a temporary file was left behind"


def test_a_failure_while_serialising_writes_nothing(tmp_path: Path):
    path = tmp_path / "run.json"
    broken = replace(run_results(), golden_bad_case_verdicts={"observed_error": 0.1, "x": object()})

    with pytest.raises(TypeError):
        results.write_atomic(path, broken)

    assert list(tmp_path.iterdir()) == []


def test_the_declared_settings_cannot_change_in_a_rewrite_of_the_same_run(tmp_path: Path):
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results())

    with pytest.raises(ValueError, match="cannot change"):
        results.write_atomic(path, run_results(settings=replace(declared(), margin_pp=15.0)))
    with pytest.raises(ValueError, match="cannot change"):
        results.write_atomic(path, run_results(declared_at="2026-10-12T08:58:00Z"))

    assert results.load(path).settings.margin_pp == 10.0


def test_a_different_run_may_replace_the_file_with_other_settings(tmp_path: Path):
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results())

    results.write_atomic(
        path, run_results(run_id="run-b", settings=replace(declared(), margin_pp=15.0))
    )

    assert results.load(path).settings.margin_pp == 15.0


# ---------------------------------------------------------------------------
# Identity, pairs, verdicts and earlier runs
# ---------------------------------------------------------------------------


def test_a_run_id_is_a_utc_timestamp_and_a_random_suffix():
    moment = datetime(2026, 10, 12, 9, 0, 5, tzinfo=UTC)

    ids = {results.new_run_id(moment) for _ in range(20)}

    assert all(
        i.startswith("20261012T090005Z-") and len(i) == len("20261012T090005Z-") + 6 for i in ids
    )
    assert len(ids) > 1


def test_only_tasks_that_ran_in_both_arms_pair_and_a_retry_replaces_its_first_record():
    crashed = Errored("exit_nonzero", "crashed")
    sessions = [
        session("t1", "full"),
        session("t1", "lean", crashed),
        session("t1", "lean"),  # the retry
        session("t2", "full"),  # no lean record
    ]

    pairs = results.pairs_of(run_results(sessions), "researcher")

    assert [p.task_id for p in pairs] == ["t1"]
    assert pairs[0].complete


def test_role_verdicts_reads_a_roles_own_allowance_through_the_results_file():
    clean = Measured({"C1": Passed(), "C3": Passed()}, 1000)
    drifted = Measured({"C1": Failed("late"), "C3": Passed()}, 1000)
    sessions = [session("t1", "full", clean), session("t1", "lean", drifted)]
    calibrated = replace(
        declared(), allowance_source="calibration-1", allowances={"researcher/C1": 1}
    )

    allowed = results.role_verdicts(run_results(sessions, settings=calibrated))["researcher"]
    strict = results.role_verdicts(run_results(sessions))["researcher"]

    assert isinstance(allowed.check_verdicts["C1"], NoRegression)
    assert isinstance(strict.check_verdicts["C1"], Regression)


def test_the_stored_verdicts_are_recomputed_from_the_sessions_never_read_back(tmp_path: Path):
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results([*pair_of_sessions("t1")], settings=declared(2)))
    document = json.loads(path.read_text())
    document["verdicts"]["researcher"] = {"underpowered": False, "flip": "clear"}
    path.write_text(json.dumps(document))

    verdict = results.role_verdicts(results.load(path))["researcher"]

    assert isinstance(verdict, Underpowered)
    assert json.loads(path.read_text())["verdicts"]["researcher"]["flip"] == "clear"
    results.write_atomic(path, results.load(path))
    assert "flip" not in json.loads(path.read_text())["verdicts"]["researcher"]


# ---------------------------------------------------------------------------
# Earlier runs: listed by what they measured
# ---------------------------------------------------------------------------


def the_same(earlier: RunResults, role: str) -> tuple[str, ...]:
    return ()


def write_run(directory: Path, run_id: str, sessions, **kwargs) -> None:
    roles = kwargs.pop("roles", ("researcher",))
    results.write_atomic(
        directory / f"{run_id}.json", run_results(sessions, run_id=run_id, roles=roles, **kwargs)
    )


def listed(directory: Path, differences=the_same, replaced=None) -> results.EarlierListing:
    return results.earlier_runs(directory, ("researcher",), differences, replaced)


def test_runs_of_the_same_identity_on_other_commits_are_all_draws_in_order_with_their_verdicts(
    tmp_path: Path,
):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])  # clear: one pair, target 1
    write_run(tmp_path, "run-b", [*pair_of_sessions("t1", commit="f" * 40)], settings=declared(5))

    earlier = listed(tmp_path).by_role["researcher"]

    assert earlier.draws == (
        results.Draw(("run-a",), "clear"),
        results.Draw(("run-b",), "underpowered"),
    )
    assert (earlier.apart, earlier.calibration) == ({}, ())


def test_a_run_that_never_measured_the_role_is_not_listed_for_it(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1", role="verifier")], roles=("verifier",))

    assert listed(tmp_path).by_role["researcher"] == results.EarlierRuns((), {}, ())


def test_a_run_of_another_identity_is_named_apart_with_how_it_differs(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    write_run(tmp_path, "run-b", [*pair_of_sessions("t1")])

    def differs(earlier: RunResults, role: str) -> tuple[str, ...]:
        return ("roles.researcher.definition: 1a2b -> 3c4d",) if earlier.run.id == "run-a" else ()

    earlier = listed(tmp_path, differs).by_role["researcher"]

    assert [d.run_ids for d in earlier.draws] == [("run-b",)]
    assert earlier.apart == {"run-a": "roles.researcher.definition: 1a2b -> 3c4d"}


def test_a_calibration_run_is_listed_apart_never_as_a_draw(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")], extra={"calibration": True})

    earlier = listed(tmp_path).by_role["researcher"]

    assert (earlier.draws, earlier.calibration) == ((), ("run-a",))


def test_a_json_file_that_is_not_a_results_file_is_skipped_and_named(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    (tmp_path / "notes.json").write_text('{"not": "a results file"}')
    (tmp_path / "broken.json").write_text("{")
    (tmp_path / "list.json").write_text("[1, 2]")
    (tmp_path / "shaped.json").write_text('{"schema_version": "adherence/1", "run": []}')

    found = listed(tmp_path)

    assert found.skipped_files == ("broken.json", "list.json", "notes.json", "shaped.json")
    assert [d.run_ids for d in found.by_role["researcher"].draws] == [("run-a",)]


def test_the_run_a_listing_run_overwrites_is_no_longer_evidence(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    write_run(tmp_path, "run-b", [*pair_of_sessions("t1")])

    earlier = listed(tmp_path, replaced="run-a").by_role["researcher"]

    assert [d.run_ids for d in earlier.draws] == [("run-b",)]


def test_a_listing_is_recorded_under_the_run_and_read_back_for_each_role(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])
    write_run(tmp_path, "run-b", [*pair_of_sessions("t1")], extra={"calibration": True})
    (tmp_path / "notes.json").write_text("{}")
    listing = listed(tmp_path)

    run = run_results(extra=results.earlier_to_json(listing)).run
    reloaded = json.loads(json.dumps(run.extra))

    assert (
        results.earlier_listed(replace(run, extra=reloaded), "researcher")
        == (listing.by_role["researcher"])
    )
    assert results.skipped_files(run) == ("notes.json",)


def test_older_readers_keep_the_first_run_id_of_each_draw(tmp_path: Path):
    write_run(tmp_path, "run-a", [*pair_of_sessions("t1")])

    assert listed(tmp_path).for_older_readers() == {"researcher": (EarlierRun("run-a", "clear"),)}


def test_a_file_written_before_listings_has_no_listing_and_no_skipped_names():
    run = run_results().run

    assert results.earlier_listed(run, "researcher") is None
    assert results.skipped_files(run) == ()


def test_a_draw_names_the_run_it_took():
    with pytest.raises(ValueError, match="names the run"):
        results.Draw((), "clear")


# -- Which identity counts as the same: the runner's comparison ------------------------------------


def identity_of(definition: str, recorded: bool = True) -> RunResults:
    roles = {"researcher": {"definition_sha": definition * 64, "kernel": None}}
    extra = {
        "checkout": {"path": "/gone", "commit": "0" * 40, "dirty": False},
        "roles": ["researcher"],
        "tasks": {"researcher": []},
    }
    if recorded:
        extra["identity"] = {"tree": "t" * 64, "model": None, "roles": roles}
    return run_results(extra=extra)


def test_the_runner_compares_only_the_role_definition_and_kernel(tmp_path: Path):
    this = lineage.measured_identity(identity_of("a"), tmp_path)
    differences = session_loop._identity_differences(this, tmp_path)

    assert differences(identity_of("a"), "researcher") == ()
    assert differences(identity_of("b"), "researcher") == (
        "roles.researcher.definition: bbbbbbbbbbbb -> aaaaaaaaaaaa",
    )


def test_a_run_recording_no_identity_is_listed_apart_saying_what_its_checkout_held(tmp_path: Path):
    this = lineage.measured_identity(identity_of("a"), tmp_path)

    (how,) = session_loop._identity_differences(this, tmp_path)(
        identity_of("a", recorded=False), "researcher"
    )

    assert how.startswith("recorded no identity; its commit held ")
    assert "identity unknown" in how  # the commit is not reachable from an empty directory


def test_flip_labels_follow_the_verdict_type():
    clear = results.role_verdicts(run_results([*pair_of_sessions("t1")]))["researcher"]
    unmeasured = [session("t1", "full", NotMeasured("never spawned")), session("t1", "lean")]
    short = results.role_verdicts(run_results(unmeasured))["researcher"]

    assert isinstance(clear, Assessed)
    assert results.flip_label(clear) == "clear"
    assert isinstance(short, Underpowered)
    assert results.flip_label(short) == "underpowered"


# ---------------------------------------------------------------------------
# Kernel delivery: the marker records a flip verdict cites
# ---------------------------------------------------------------------------

DELIVERED = (
    {"session_id": "sess-1", "kernel_version": "0a1b2c3d", "slot": 1},
    {"session_id": "sess-1", "kernel_version": "0a1b2c3d", "slot": 2},
)


def lean_with_kernel(task: str, rows=DELIVERED) -> SessionRecord:
    status = Measured({"C1": Passed(), "C3": Passed()}, 1000, kernel_rows=tuple(rows))
    return session(task, "lean", status)


def test_a_sessions_kernel_marker_records_round_trip_through_the_results_file(tmp_path: Path):
    original = run_results([session("t1", "full"), lean_with_kernel("t1")])
    path = tmp_path / "run.json"

    results.write_atomic(path, original)

    assert results.load(path) == original
    stored = json.loads(path.read_text())["sessions"][1]["status"]
    assert stored["kernel_rows"] == [dict(row) for row in DELIVERED]


def test_a_forced_stop_sessions_role_ending_round_trips_through_the_results_file(tmp_path: Path):
    status = Measured({"C1": Passed(), "C3": Passed()}, 7, role_ending=StoppedAtCap(5, 5))
    ended = session("t1", "full", status)
    path = tmp_path / "run.json"

    results.write_atomic(path, run_results([ended]))

    assert results.load(path).sessions[0].status.role_ending == StoppedAtCap(5, 5)
    stored = json.loads(path.read_text())["sessions"][0]["status"]
    assert stored["role_ending"]["kind"] == "stopped_at_cap"


def test_a_session_without_markers_stores_no_kernel_rows(tmp_path: Path):
    path = tmp_path / "run.json"

    results.write_atomic(path, run_results([*pair_of_sessions("t1")]))

    assert "kernel_rows" not in json.loads(path.read_text())["sessions"][0]["status"]


def test_a_marker_record_without_its_kernel_version_is_refused_on_load(tmp_path: Path):
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results([session("t1", "full"), lean_with_kernel("t1")]))
    document = json.loads(path.read_text())
    document["sessions"][1]["status"]["kernel_rows"] = [{"session_id": "sess-1", "slot": 1}]
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="kernel_version"):
        results.load(path)


def test_the_flip_record_names_the_deliveries_of_the_lean_sessions_the_verdict_relies_on(
    tmp_path: Path,
):
    relied_on = [session("t1", "full"), lean_with_kernel("t1")]
    unpaired = [lean_with_kernel("t2", [{"session_id": "sess-2", "kernel_version": "ffffffff"}])]
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results([*relied_on, *unpaired]))

    record = json.loads(path.read_text())["kernel_delivery"]

    assert record == {
        "researcher": [
            {"task_id": "t1", "session_id": "sess-1", "kernel_version": "0a1b2c3d", "slot": 1},
            {"task_id": "t1", "session_id": "sess-1", "kernel_version": "0a1b2c3d", "slot": 2},
        ]
    }


def test_a_kernel_version_is_cited_by_its_eight_character_prefix():
    full = "0a1b2c3d" + "e" * 32
    pair = [session("t1", "full"), lean_with_kernel("t1", [{"kernel_version": full}])]

    (delivery,) = results.kernel_deliveries(run_results(pair), "researcher")

    assert delivery.kernel_version == "0a1b2c3d"
    assert (delivery.session_id, delivery.slot) == (None, None)


def test_a_role_none_of_whose_lean_sessions_carry_markers_has_no_flip_record_entry(
    tmp_path: Path,
):
    path = tmp_path / "run.json"
    results.write_atomic(path, run_results([*pair_of_sessions("t1")]))

    assert json.loads(path.read_text())["kernel_delivery"] == {}
