"""The results file: written whole and atomically, loaded strictly, verdicts recomputed."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praxion_evals.adherence import results
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.model import (
    Assessed,
    DeclaredSettings,
    Errored,
    Measured,
    NotMeasured,
    Passed,
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
) -> RunResults:
    return RunResults(
        run=RunInfo(
            id=run_id,
            model="claude-opus-5-5",
            claude_code_version="9.9.9",
            complete=True,
            refused_launches=(),
            earlier_runs={"researcher": (EarlierRun("run-0", "not clear"),)},
            extra={"seed": 7, "effort": "high"},
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


def test_earlier_runs_lists_the_same_role_on_the_same_checkout_with_its_verdict(tmp_path: Path):
    def write(name: str, run_id: str, sessions, role: str = "researcher") -> None:
        results.write_atomic(tmp_path / name, run_results(sessions, run_id=run_id, roles=(role,)))

    write("a.json", "run-a", [*pair_of_sessions("t1")])  # clear: one pair, target 1
    write("b.json", "run-b", [*pair_of_sessions("t1", commit="f" * 40)])  # another checkout
    write(
        "c.json", "run-c", [*pair_of_sessions("t1", role="verifier")], role="verifier"
    )  # another role
    (tmp_path / "notes.json").write_text('{"not": "a results file"}')
    (tmp_path / "broken.json").write_text("{")

    found = results.earlier_runs(tmp_path, "researcher", COMMIT)

    assert found == (EarlierRun("run-a", "clear"),)


def test_an_earlier_run_that_was_underpowered_says_so(tmp_path: Path):
    path = tmp_path / "a.json"
    results.write_atomic(path, run_results([*pair_of_sessions("t1")], settings=declared(5)))

    assert results.earlier_runs(tmp_path, "researcher", COMMIT) == (
        EarlierRun("run-a", "underpowered"),
    )


def test_flip_labels_follow_the_verdict_type():
    clear = results.role_verdicts(run_results([*pair_of_sessions("t1")]))["researcher"]
    unmeasured = [session("t1", "full", NotMeasured("never spawned")), session("t1", "lean")]
    short = results.role_verdicts(run_results(unmeasured))["researcher"]

    assert isinstance(clear, Assessed)
    assert results.flip_label(clear) == "clear"
    assert isinstance(short, Underpowered)
    assert results.flip_label(short) == "underpowered"
