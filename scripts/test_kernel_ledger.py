"""Tests for kernel_ledger.py -- the adoption ledger as legal values.

A switched record is built only with every piece of its evidence and a held one only with
its reason; a status moves only along the legal moves, and a recorded run is never lost; the
lenient readers (statuses, entries, adoptions) survive a record the gate refuses. Every case builds its own wire shape, so none depends on the repository's ledger.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_ledger as kl  # noqa: E402
import kernel_model as km  # noqa: E402

AGENTS = frozenset({"researcher", "verifier", "discipline-consultant", "implementer", "sentinel"})
END_OF_DAY = datetime(2026, 10, 12, 23, 59, 59, 999999, tzinfo=timezone.utc)
PILOT_ROLES = [
    "researcher",
    "verifier",
    "discipline-consultant",
    "skill-genesis",
    "context-engineer",
]


# -- Builders: the wire shapes ---------------------------------------------------


def run(run_id: str, pairs: int = 24, passes: bool = True, eval_entry: str = "an-eval"):
    return {"id": run_id, "complete_pairs": pairs, "passes_flip_rule": passes, "entry": eval_entry}


def switched_row(**fields: object) -> dict:
    row = {
        "status": "switched",
        "since": "2026-10-12",
        "runs": [run("r1", 12, False), run("r2")],
        "passing_run": "r2",
        "probe_before_tokens": 31_000,
        "probe_after_tokens": 22_000,
        "flip_rule_ratified": True,
        "flip_ratified": True,
    }
    return {**row, **fields}


def ledger_wire(**roles: dict) -> dict:
    return {"version": 1, "eligible": PILOT_ROLES, "roles": roles}


def parse_ledger(**roles: dict) -> kl.Ledger:
    return kl.parse_ledger(ledger_wire(**roles), AGENTS)


def write(root: Path, text: str) -> None:
    (root / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / km.LEDGER_PATH).write_text(text, encoding="utf-8")


# -- The evidence-checked ledger -----------------------------------------------------


def test_a_trial_record_needs_only_when_it_began_and_its_runs() -> None:
    ledger = parse_ledger(
        researcher={"status": "trial", "since": "2026-10-12", "runs": [run("r1")]}
    )

    assert ledger.records["researcher"] == kl.Trial(
        "researcher", END_OF_DAY, (kl.Run("r1", 24, True, "an-eval"),)
    )


def test_a_switched_record_holds_every_piece_of_its_evidence() -> None:
    record = parse_ledger(verifier=switched_row()).records["verifier"]

    assert isinstance(record, kl.Switched)
    assert (record.passing_run, record.probe_before_tokens, record.probe_after_tokens) == (
        "r2",
        31_000,
        22_000,
    )


@pytest.mark.parametrize("field", kl.SWITCHED_FIELDS)
def test_a_switched_record_missing_a_field_is_refused_naming_role_and_field(field: str) -> None:
    row = switched_row()
    del row[field]

    with pytest.raises(km.KernelModelError, match=rf"role verifier: .* lacks {field}"):
        parse_ledger(verifier=row)


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"runs": [run("r2", 19)]}, "19 pairs"),
        ({"runs": [run("r2", 24, False)]}, "does not pass the flip rule"),
        ({"passing_run": "r9"}, "not among its runs"),
        ({"flip_ratified": False}, "lacks the user's flip_ratified"),
        ({"flip_rule_ratified": False}, "lacks the user's flip_rule_ratified"),
        ({"probe_after_tokens": 0}, "no positive probe_after_tokens"),
    ],
    ids=[
        "under twenty pairs",
        "not passing",
        "unknown run",
        "flip unratified",
        "rule unratified",
        "no reading",
    ],
)
def test_a_switched_record_without_sound_evidence_cannot_be_built(
    fields: dict, reason: str
) -> None:
    with pytest.raises(km.KernelModelError, match=reason):
        parse_ledger(verifier=switched_row(**fields))


def test_a_role_that_is_not_eligible_cannot_be_switched() -> None:
    with pytest.raises(km.KernelModelError, match="role implementer: is not eligible"):
        parse_ledger(implementer=switched_row())


def test_a_role_that_is_not_eligible_may_still_be_at_trial() -> None:
    ledger = parse_ledger(implementer={"status": "trial", "since": "2026-10-12", "runs": []})

    assert isinstance(ledger.records["implementer"], kl.Trial)


def test_a_record_for_an_unknown_agent_or_status_is_refused() -> None:
    with pytest.raises(km.KernelModelError, match="role ghost: no such agent"):
        parse_ledger(ghost={"status": "trial", "since": "2026-10-12", "runs": []})
    with pytest.raises(km.KernelModelError, match="role researcher: status 'done'"):
        parse_ledger(researcher={"status": "done"})


def test_the_status_reader_survives_a_record_the_gate_would_refuse() -> None:
    bare = {"since": "2026-10-12", "runs": []}
    wire = ledger_wire(
        researcher={"status": "switched", **bare}, verifier={"status": "trial", **bare}
    )

    assert dict(km.parse_statuses(wire)) == {"researcher": "switched", "verifier": "trial"}
    with pytest.raises(km.KernelModelError, match="researcher: a switched record lacks"):
        kl.parse_ledger(wire, AGENTS)


def test_a_role_the_hook_reads_otherwise_than_the_parser_is_named_with_both_readings() -> None:
    hook_reading = {"verifier": "switched"}

    found = kl.hook_misreadings(
        {"researcher": "trial", "verifier": "switched"},
        "ledger text",
        lambda _, role: hook_reading.get(role),
    )

    assert [(f.kind, f.subject) for f in found] == [("hook-misread", "role researcher")]
    assert "status None where PyYAML reads 'trial'" in found[0].detail


def test_a_role_the_hook_reads_and_the_parser_does_not_is_named_with_both_readings() -> None:
    found = kl.hook_misreadings(
        {},
        "roles:\n  verifier:\n    status: trial\n",
        lambda _, role: {"verifier": "trial"}.get(role),
    )

    assert [(f.kind, f.subject) for f in found] == [("hook-misread", "role verifier")]
    assert "status 'trial' where PyYAML reads None" in found[0].detail


def test_a_role_key_the_parser_reads_as_a_number_is_named_not_crashed_on() -> None:
    found = kl.hook_misreadings(
        {123: "trial", "verifier": "trial"},
        "roles:\n  123:\n    status: trial\n  verifier:\n    status: trial\n",
        lambda _, role: {"verifier": "trial"}.get(role),
    )

    assert [(f.kind, f.subject) for f in found] == [("hook-misread", "role 123")]
    assert "status None where PyYAML reads 'trial'" in found[0].detail


# -- The legal moves -------------------------------------------------------------------

PARENT_AT = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
BEFORE_PARENT = datetime(2026, 10, 14, 2, 32, tzinfo=timezone.utc)
AFTER_PARENT = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
BUILT_AT = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)  # the re-opening commit


def entry(status: str, since: datetime | None = BEFORE_PARENT, runs: tuple = ()) -> kl.Entry:
    return kl.Entry(status, since, runs)


def parent(**entries: kl.Entry) -> kl.ParentLedger:
    return kl.ParentLedger(entries, PARENT_AT, BUILT_AT)


def moves(before: kl.ParentLedger | None, **after: kl.Entry) -> list[tuple[str, str, str]]:
    return [(f.kind, f.subject, f.detail) for f in kl.ledger_transitions(before, after)]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (None, {}),
        (None, {"researcher": entry("trial")}),
        (parent(researcher=entry("trial")), {"researcher": entry("trial")}),
        (parent(researcher=entry("trial")), {"researcher": entry("switched")}),
        (parent(researcher=entry("switched")), {"researcher": entry("switched")}),
        (parent(), {"researcher": entry("trial"), "verifier": entry("trial")}),
        (parent(verifier=entry("held")), {"verifier": entry("held")}),
    ],
    ids=[
        "no ledger",
        "first trial",
        "trial stays",
        "trial to switched",
        "switched stays",
        "added",
        "held stays",
    ],
)
def test_a_ledger_that_stays_or_moves_forward_passes(before, after) -> None:
    assert kl.ledger_transitions(before, after) == ()


def test_a_trial_closed_without_a_flip_moves_to_held() -> None:
    assert moves(parent(verifier=entry("trial")), verifier=entry("held")) == []


def test_a_held_role_reopened_after_the_parent_commit_moves_back_to_trial() -> None:
    reopened = entry("trial", since=AFTER_PARENT)

    assert moves(parent(verifier=entry("held")), verifier=reopened) == []


@pytest.mark.parametrize(
    ("before", "after", "move"),
    [
        (None, {"researcher": entry("switched")}, "absent -> switched"),
        (parent(researcher=entry("switched")), {"researcher": entry("trial")}, "switched -> trial"),
        (parent(researcher=entry("trial")), {}, "trial -> absent"),
        (parent(researcher=entry("switched")), {}, "switched -> absent"),
        (parent(), {"researcher": entry("held")}, "absent -> held"),
        (parent(researcher=entry("held")), {"researcher": entry("switched")}, "held -> switched"),
        (parent(researcher=entry("switched")), {"researcher": entry("held")}, "switched -> held"),
        (parent(researcher=entry("held")), {}, "held -> absent"),
    ],
    ids=[
        "skips trial",
        "demoted",
        "trial dropped",
        "switched dropped",
        "held from nothing",
        "flipped from held",
        "switched held",
        "held dropped",
    ],
)
def test_a_move_off_the_legal_moves_is_reported(before, after, move: str) -> None:
    found = kl.ledger_transitions(before, after)

    assert [(f.kind, f.subject, f.detail) for f in found] == [
        ("ledger-transition", "role researcher", move)
    ]


@pytest.mark.parametrize(
    ("since", "kind"),
    [
        (None, "ledger-reopen-no-since"),
        (BEFORE_PARENT, "ledger-reopen-before-parent"),
        (PARENT_AT, "ledger-reopen-before-parent"),
        (BUILT_AT + timedelta(seconds=1), "ledger-reopen-after-commit"),
    ],
    ids=["no since", "the held record's since kept", "at the parent", "in the future"],
)
def test_a_held_role_reopened_with_a_since_outside_its_bounds_is_reported(
    since: datetime | None, kind: str
) -> None:
    found = moves(parent(verifier=entry("held")), verifier=entry("trial", since=since))

    assert [(k, subject) for k, subject, _ in found] == [(kind, "role verifier")]


def test_a_reopening_dated_at_its_own_commit_passes() -> None:
    assert moves(parent(verifier=entry("held")), verifier=entry("trial", since=BUILT_AT)) == []


# -- The liveness bound of a re-opened trial ---------------------------------------------

HOLD_AT = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
REOPEN_AT = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def version(at: datetime | None, status: str | None) -> kl.LedgerVersion:
    return kl.LedgerVersion(at, {"verifier": status} if status else {})


def judged_from(*history: kl.LedgerVersion, since: datetime = BEFORE_PARENT) -> datetime:
    adoptions = {"verifier": kl.Adoption("trial", since)}
    return kl.judged_adoptions(adoptions, history)["verifier"].since


def test_a_reopened_trial_is_judged_from_its_reopening_commit_whatever_since_it_records() -> None:
    history = (version(None, "trial"), version(REOPEN_AT, "trial"), version(HOLD_AT, "held"))

    assert judged_from(*history) == REOPEN_AT


def test_a_reopened_trial_whose_since_is_later_than_its_commit_keeps_its_since() -> None:
    later = REOPEN_AT + timedelta(hours=1)
    history = (version(None, "trial"), version(REOPEN_AT, "trial"), version(HOLD_AT, "held"))

    assert judged_from(*history, since=later) == later


def test_a_reopening_not_yet_committed_judges_no_spawn() -> None:
    assert judged_from(version(None, "trial"), version(HOLD_AT, "held")) == kl.NEVER


@pytest.mark.parametrize(
    "before", [None, "absent"], ids=["history ends at the trial", "absent before the trial"]
)
def test_a_first_trial_keeps_its_recorded_since(before: str | None) -> None:
    history = [version(None, "trial"), version(REOPEN_AT, "trial")]
    history += [version(HOLD_AT, None)] if before else []

    assert judged_from(*history) == BEFORE_PARENT


@pytest.mark.parametrize(
    ("was", "now"),
    [(("r1", "r2"), ("r1",)), (("r1", "r2"), ("r2", "r1")), (("r1", "r2"), ("r1", "r9"))],
    ids=["dropped", "reordered", "rewritten"],
)
@pytest.mark.parametrize("status", ["trial", "held", "switched"])
def test_a_run_list_that_does_not_open_with_the_parents_is_reported(
    was: tuple, now: tuple, status: str
) -> None:
    found = moves(parent(verifier=entry(status, runs=was)), verifier=entry(status, runs=now))

    assert [(kind, subject) for kind, subject, _ in found] == [
        ("ledger-runs-rewritten", "role verifier")
    ]


@pytest.mark.parametrize(
    ("was", "now"),
    [("trial", "trial"), ("trial", "held"), ("held", "trial"), ("trial", "switched")],
    ids=["at trial", "closing the trial", "reopening", "flipping"],
)
def test_a_run_appended_outside_a_held_record_passes(was: str, now: str) -> None:
    before = parent(verifier=entry(was, runs=("r1",)))

    assert moves(before, verifier=entry(now, since=AFTER_PARENT, runs=("r1", "r2"))) == []


def test_a_run_added_to_a_record_that_stays_held_is_reported() -> None:
    found = moves(
        parent(verifier=entry("held", runs=("r1",))), verifier=entry("held", runs=("r1", "r2"))
    )

    assert found == [
        (
            "ledger-held-run-added",
            "role verifier",
            "runs ['r2'] added to a held record: re-open it as a trial first",
        )
    ]


# -- A held record --------------------------------------------------------------------

HELD = {"status": "held", "since": "2026-10-12", "runs": [], "reason": "no kit reaches 20 pairs"}


def test_a_held_record_keeps_its_start_runs_and_reason() -> None:
    record = parse_ledger(verifier={**HELD, "runs": [run("r1", 24, False)]}).records["verifier"]

    assert record == kl.Held(
        "verifier", END_OF_DAY, (kl.Run("r1", 24, False, "an-eval"),), "no kit reaches 20 pairs"
    )


def test_a_held_record_may_close_a_trial_that_has_no_run() -> None:
    assert parse_ledger(verifier=HELD).records["verifier"].runs == ()


@pytest.mark.parametrize(
    "reason", [None, "", "   ", 7], ids=["absent", "empty", "blank", "no text"]
)
def test_a_held_record_that_states_no_reason_is_refused_naming_the_role(reason: object) -> None:
    with pytest.raises(km.KernelModelError, match="role verifier: a held record's reason"):
        parse_ledger(verifier={**HELD, "reason": reason})


def test_every_reader_reads_a_held_status() -> None:
    wire = ledger_wire(verifier=HELD, researcher={"status": "trial", "since": "2026-10-12"})

    assert dict(km.parse_statuses(wire)) == {"verifier": "held", "researcher": "trial"}
    assert kl.parse_entries(wire)["verifier"] == kl.Entry("held", END_OF_DAY, ())


def test_the_move_reader_survives_a_record_the_gate_would_refuse() -> None:
    wire = ledger_wire(verifier={"status": "held", "since": "someday", "runs": [run("r1"), "r2"]})

    assert kl.parse_entries(wire)["verifier"] == kl.Entry("held", None, ("r1", "r2"))


# -- Who is adopted, and since when -----------------------------------------------------


def test_a_record_dated_by_a_bare_date_begins_at_the_end_of_that_day() -> None:
    adopted = kl.parse_adoptions(ledger_wire(researcher={"status": "trial", "since": "2026-10-12"}))

    assert adopted["researcher"] == kl.Adoption("trial", END_OF_DAY)


def test_a_held_role_is_not_adopted_so_none_of_its_spawns_is_judged() -> None:
    adopted = kl.parse_adoptions(
        ledger_wire(
            verifier={"status": "held", "since": "2026-10-12", "reason": "closed"},
            researcher={"status": "switched", "since": "2026-10-12"},
        )
    )

    assert list(adopted) == ["researcher"]


@pytest.mark.parametrize(
    "since",
    ["2026-10-12T09:30:00", "2026-10-12T09:30:00Z", "2026-10-12T11:30:00+02:00"],
)
def test_a_moment_in_any_iso_form_reads_as_the_same_aware_instant(since: str) -> None:
    assert kl.since_time(since, "researcher") == datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc)


def test_a_date_the_yaml_parser_already_read_is_accepted() -> None:
    written = "version: 1\nroles:\n  researcher: {status: trial, since: 2026-10-12}\n"

    adopted = kl.parse_adoptions(km.parse_yaml(written, "the ledger"))

    assert adopted["researcher"].since == END_OF_DAY


def test_a_date_written_plain_reads_the_same_in_both_readers(tmp_path: Path) -> None:
    write(
        tmp_path,
        "version: 1\neligible: [researcher]\n"
        "roles:\n  researcher:\n    status: trial\n    since: 2026-10-12\n    runs: []\n",
    )

    checked = kl.load_ledger(tmp_path, AGENTS).records["researcher"]

    assert checked.since == kl.load_adoptions(tmp_path)["researcher"].since == END_OF_DAY


@pytest.mark.parametrize("since", [None, "", "yesterday", 20261012, ["2026-10-12"]])
def test_a_record_that_does_not_say_when_it_began_cannot_bound_a_judgement(since: object) -> None:
    with pytest.raises(km.KernelModelError, match="role researcher: since"):
        kl.parse_adoptions(ledger_wire(researcher={"status": "trial", "since": since}))


# -- The edge: files ------------------------------------------------------------------


def test_the_loaders_read_the_ledger_of_a_checkout(tmp_path: Path) -> None:
    write(
        tmp_path,
        "version: 1\neligible: [researcher]\n"
        "roles:\n  researcher: {status: trial, since: '2026-10-12', runs: []}\n",
    )

    assert kl.load_ledger(tmp_path, AGENTS).records["researcher"] == kl.Trial(
        "researcher", END_OF_DAY, ()
    )
    assert kl.load_adoptions(tmp_path)["researcher"].status == "trial"


def test_no_ledger_is_an_empty_ledger_and_adopts_nobody(tmp_path: Path) -> None:
    assert kl.load_ledger(tmp_path, AGENTS).records == {}
    assert kl.load_adoptions(tmp_path) == {}


def test_a_ledger_that_is_not_a_mapping_is_refused_naming_it(tmp_path: Path) -> None:
    write(tmp_path, "- a list\n")

    with pytest.raises(km.KernelModelError, match="kernel_adoption.yaml"):
        kl.load_ledger(tmp_path, AGENTS)
