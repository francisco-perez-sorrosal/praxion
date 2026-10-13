"""Tests for kernel_ledger.py -- the adoption ledger as legal values.

A switched record is built only with every piece of its evidence; a status moves only one
rung up the ladder; the lenient readers (statuses, adoptions) survive a record the gate
refuses. Every case builds its own wire shape, so none depends on the repository's ledger.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
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


# -- The ladder of moves -------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (None, {}),
        (None, {"researcher": "trial"}),
        ({"researcher": "trial"}, {"researcher": "trial"}),
        ({"researcher": "trial"}, {"researcher": "switched"}),
        ({"researcher": "switched"}, {"researcher": "switched"}),
        ({}, {"researcher": "trial", "verifier": "trial"}),
    ],
    ids=["no ledger", "first trial", "trial stays", "trial to switched", "switched stays", "added"],
)
def test_a_ledger_moves_forward_from_absent_to_trial_to_switched(before, after) -> None:
    assert kl.ledger_transitions(before, after) == ()


@pytest.mark.parametrize(
    ("before", "after", "move"),
    [
        (None, {"researcher": "switched"}, "absent -> switched"),
        ({"researcher": "switched"}, {"researcher": "trial"}, "switched -> trial"),
        ({"researcher": "trial"}, {}, "trial -> absent"),
        ({"researcher": "switched"}, {}, "switched -> absent"),
    ],
    ids=["skips trial", "demoted", "trial dropped", "switched dropped"],
)
def test_a_ledger_that_skips_or_reverses_a_status_is_reported(before, after, move: str) -> None:
    found = kl.ledger_transitions(before, after)

    assert [(f.kind, f.subject, f.detail) for f in found] == [
        ("ledger-transition", "role researcher", move)
    ]


# -- Who is adopted, and since when -----------------------------------------------------


def test_a_record_dated_by_a_bare_date_begins_at_the_end_of_that_day() -> None:
    adopted = kl.parse_adoptions(ledger_wire(researcher={"status": "trial", "since": "2026-10-12"}))

    assert adopted["researcher"] == kl.Adoption("trial", END_OF_DAY)


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
