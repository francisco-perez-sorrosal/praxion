"""Canaries for I9 and I10: a role flips or is held only with its record, which the hook can read."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kernel_checker_testkit as kit  # noqa: E402
import check_kernel_manifest as cb  # noqa: E402
import kernel_ledger as kl  # noqa: E402
import kernel_model as km  # noqa: E402
from _kernel_checker_testkit import (  # noqa: E402
    ADHERENCE,
    OUTSIDE_THE_PIN,
    commit_all,
    flipped,
    frontmatter_line,
    held_row,
    omit_claude_md,
    regenerate,
    run_checker,
    run_row,
    subjects,
    switched_row,
    trial_row,
    write_ledger,
)
from kernel_eligibility import ELIGIBLE_ROLES  # noqa: E402

# pytest finds a fixture by name in the module that uses it
template = kit.template


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    """The live inputs as they stood before any flip: each canary plants its own flag and record."""
    shutil.copytree(template, tmp_path / "checkout")
    kit.unswitched(tmp_path / "checkout")
    return tmp_path / "checkout"


def test_a_role_flipped_with_its_full_record_passes(repo: Path) -> None:
    flipped(repo)

    assert cb.check(repo) == ()


def test_the_flag_without_any_record_is_reported_by_role(repo: Path) -> None:
    omit_claude_md(repo, "researcher")

    found = [f for f in cb.check(repo) if f.kind == "I9-flag-without-record"]

    assert [f.subject for f in found] == ["role researcher"]
    assert "absent" in found[0].detail


def test_the_flag_on_a_role_still_at_trial_is_reported(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    omit_claude_md(repo, "researcher")
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-flag-without-record"]

    assert [(f.subject, "trial" in f.detail) for f in found] == [("role researcher", True)]


NOT_LITERAL_TRUE = [
    "false",
    "False",
    "yes",
    "no",
    "on",
    "off",
    "'true'",
    '"true"',
    "True",
    "1",
    "null",
    "",
]


@pytest.mark.parametrize("value", NOT_LITERAL_TRUE, ids=lambda v: v or "empty")
def test_a_flag_that_is_not_a_literal_true_is_refused_naming_role_and_value(
    repo: Path, value: str
) -> None:
    omit_claude_md(repo, "researcher", value)

    found = [f for f in cb.check(repo) if f.kind == "I9-flag-not-literal-true"]

    assert [f.subject for f in found] == ["role researcher"]
    assert repr(value) in found[0].detail


@pytest.mark.parametrize("value", ["yes", "'true'", "false"])
def test_a_flag_that_is_not_a_literal_true_does_not_count_as_setting_it(
    repo: Path, value: str
) -> None:
    omit_claude_md(repo, "researcher", value)

    assert subjects(repo, "I9-flag-without-record") == []


def test_a_flag_that_is_not_a_literal_true_on_a_switched_role_leaves_it_unflagged(
    repo: Path,
) -> None:
    write_ledger(repo, researcher=switched_row())
    omit_claude_md(repo, "researcher", "yes")
    regenerate(repo)

    assert subjects(repo, "I9-flag-not-literal-true") == ["role researcher"]
    assert subjects(repo, "I9-switch-without-flag") == ["role researcher"]


def test_a_literal_true_with_a_trailing_comment_is_the_literal(repo: Path) -> None:
    write_ledger(repo, researcher=switched_row())
    omit_claude_md(repo, "researcher", "true  # pilot")
    regenerate(repo)

    assert cb.check(repo) == ()


def test_the_last_omit_line_decides_as_in_yaml(repo: Path) -> None:
    omit_claude_md(repo, "researcher", "false")
    flipped(repo)  # inserts its true above, so the false is the last line

    assert subjects(repo, "I9-flag-not-literal-true") == ["role researcher"]


def test_the_flag_in_the_body_of_a_definition_is_not_the_flag(repo: Path) -> None:
    path = repo / "agents/researcher.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nomitClaudeMd: yes\n", encoding="utf-8")

    assert subjects(repo, "I9-flag-not-literal-true") == []


def test_a_switched_record_without_the_flag_is_reported(repo: Path) -> None:
    write_ledger(repo, researcher=switched_row())
    regenerate(repo)

    assert subjects(repo, "I9-switch-without-flag") == ["role researcher"]


@pytest.mark.parametrize("missing", kl.SWITCHED_FIELDS)
def test_a_flip_missing_a_piece_of_its_record_is_reported_naming_role_and_piece(
    repo: Path, missing: str
) -> None:
    row = switched_row()
    del row[missing]
    write_ledger(repo, researcher=row)
    omit_claude_md(repo, "researcher")
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert len(found) == 1
    assert "researcher" in found[0].detail
    assert missing in found[0].detail


def test_a_flip_resting_on_a_run_of_fewer_than_twenty_pairs_is_reported(repo: Path) -> None:
    flipped(repo, runs=[run_row(pairs=19)])

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert [f.subject for f in found] == [km.LEDGER_PATH]
    assert "19 pairs" in found[0].detail


def test_a_flip_resting_on_a_run_that_fails_the_flip_rule_is_reported(repo: Path) -> None:
    flipped(repo, runs=[run_row(passes=False)])

    assert subjects(repo, "I9-record-incomplete") == [km.LEDGER_PATH]


def test_a_flip_resting_on_a_run_from_another_eval_is_reported_by_role(repo: Path) -> None:
    flipped(repo, runs=[run_row(eval_entry="another-eval")])

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert [f.subject for f in found] == ["role researcher"]
    assert ADHERENCE in found[0].detail


def test_a_role_outside_the_eligible_list_cannot_be_flipped(repo: Path) -> None:
    flipped(repo, role=OUTSIDE_THE_PIN)

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert len(found) == 1
    assert OUTSIDE_THE_PIN in found[0].detail


def test_a_ledger_that_is_not_yaml_is_an_input_error_not_a_finding(repo: Path) -> None:
    (repo / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / km.LEDGER_PATH).write_text("roles: [unclosed", encoding="utf-8")

    assert run_checker(repo).returncode == 2


def test_a_role_climbing_one_status_from_the_parent_commit_passes(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    regenerate(repo)
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()


def test_a_role_that_skips_trial_since_the_parent_commit_is_reported(repo: Path) -> None:
    write_ledger(repo)
    regenerate(repo)
    commit_all(repo)

    flipped(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-ledger-transition"]
    assert [(f.subject, f.detail) for f in found] == [("role researcher", "absent -> switched")]


def test_a_role_falling_back_since_the_parent_commit_is_reported(repo: Path) -> None:
    flipped(repo)
    commit_all(repo)

    write_ledger(repo, researcher=trial_row())
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-ledger-transition"]
    assert [(f.subject, f.detail) for f in found] == [("role researcher", "switched -> trial")]


def test_a_ledger_that_first_appears_in_this_commit_has_no_parent_to_climb_from(
    repo: Path,
) -> None:
    (repo / "README.probe").write_text("committed before the ledger existed\n", encoding="utf-8")
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()


# -- A trial closes as held, and a held role re-opens as a new trial ------------------------------

REOPENED_AFTER_PARENT = "2026-10-14T09:00:00Z"  # commit_all commits at 2026-10-13T12:00Z


def moved(repo: Path, before: dict, after: dict) -> list[tuple[str, str, str]]:
    """The I9 move findings for a commit taking the researcher's record from `before` to `after`."""
    write_ledger(repo, researcher=before)
    commit_all(repo)
    write_ledger(repo, researcher=after)
    return [(f.kind, f.subject, f.detail) for f in cb.check(repo) if f.kind.startswith("I9-")]


def test_a_trial_closed_without_a_flip_moves_to_held(repo: Path) -> None:
    assert moved(repo, trial_row(), held_row(runs=[run_row(passes=False)])) == []


def test_a_held_role_reopened_with_a_since_after_the_parent_commit_moves_back_to_trial(
    repo: Path,
) -> None:
    reopened = {**trial_row(), "since": REOPENED_AFTER_PARENT}  # before the gate's clock

    assert moved(repo, held_row(), reopened) == []


@pytest.mark.parametrize(
    ("since", "kind"),
    [
        (None, "I9-ledger-reopen-no-since"),
        ("2026-10-12", "I9-ledger-reopen-before-parent"),
        ("2999-01-01T00:00:00Z", "I9-ledger-reopen-after-commit"),
    ],
    ids=["no since", "the held record's since kept", "in the future"],
)
def test_a_held_role_reopened_with_a_since_outside_its_bounds_is_reported(
    repo: Path, since: str | None, kind: str
) -> None:
    found = moved(repo, held_row(), {**trial_row(), "since": since})

    assert [(k, subject) for k, subject, _ in found if k.startswith("I9-ledger")] == [
        (kind, "role researcher")
    ]


@pytest.mark.parametrize(
    ("since", "refused"),
    [("2026-10-14T06:00:00Z", False), ("2026-10-14T18:00:00Z", True)],
    ids=["before the re-opening commit", "after the re-opening commit"],
)
def test_a_committed_reopening_is_judged_against_its_own_commit_time(
    repo: Path, since: str, refused: bool
) -> None:
    write_ledger(repo, researcher=held_row())
    commit_all(repo)
    write_ledger(repo, researcher={**trial_row(), "since": since})
    commit_all(repo, at="2026-10-14T12:00:00+00:00")

    found = [f.kind for f in cb.check(repo) if f.kind.startswith("I9-ledger")]

    assert found == (["I9-ledger-reopen-after-commit"] if refused else [])


@pytest.mark.parametrize(
    ("before", "after", "move"),
    [
        ({}, {"researcher": held_row()}, "absent -> held"),
        ({"researcher": held_row()}, {"researcher": kit.switched_row()}, "held -> switched"),
        (
            {"researcher": kit.switched_row()},
            {"researcher": held_row(runs=[run_row()])},
            "switched -> held",
        ),
        ({"researcher": held_row()}, {}, "held -> absent"),
    ],
    ids=["held from nothing", "flipped from held", "switched held", "held removed"],
)
def test_a_move_the_ledger_does_not_allow_is_reported(
    repo: Path, before: dict, after: dict, move: str
) -> None:
    write_ledger(repo, **before)
    commit_all(repo)
    write_ledger(repo, **after)

    found = [f for f in cb.check(repo) if f.kind == "I9-ledger-transition"]
    assert [(f.subject, f.detail) for f in found] == [("role researcher", move)]


def test_a_held_record_that_states_no_reason_is_reported_by_role(repo: Path) -> None:
    write_ledger(repo, researcher=held_row(reason=""))

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert len(found) == 1
    assert "role researcher: a held record's reason" in found[0].detail


@pytest.mark.parametrize(
    "runs",
    [[run_row()], [{**run_row(), "id": "r2"}, run_row()], [run_row(), {**run_row(), "id": "r9"}]],
    ids=["dropped", "reordered", "rewritten"],
)
def test_a_run_list_that_does_not_open_with_the_parents_is_reported(repo: Path, runs: list) -> None:
    recorded = [run_row(), {**run_row(), "id": "r2"}]

    found = moved(repo, {**trial_row(), "runs": recorded}, {**trial_row(), "runs": runs})

    assert [(kind, subject) for kind, subject, _ in found] == [
        ("I9-ledger-runs-rewritten", "role researcher")
    ]


def test_a_run_added_to_a_record_that_stays_held_is_reported(repo: Path) -> None:
    found = moved(repo, held_row(), held_row(runs=[run_row(passes=False)]))

    assert found == [
        (
            "I9-ledger-held-run-added",
            "role researcher",
            f"runs [{kit.CLEAR_RUN!r}] added to a held record: re-open it as a trial first",
        )
    ]


def test_the_flag_on_a_held_role_is_reported(repo: Path) -> None:
    write_ledger(repo, researcher=held_row())
    omit_claude_md(repo, "researcher")

    found = [f for f in cb.check(repo) if f.kind == "I9-flag-without-record"]

    assert [f.subject for f in found] == ["role researcher"]
    assert "is held" in found[0].detail


# -- Only the pinned roles can ever be flipped, and the ledger names none of its own ---------------


def test_a_switched_role_outside_the_pin_is_refused_by_name(repo: Path) -> None:
    write_ledger(repo, **{OUTSIDE_THE_PIN: switched_row()})
    omit_claude_md(repo, OUTSIDE_THE_PIN)
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert [f.subject for f in found] == [km.LEDGER_PATH]
    assert f"role {OUTSIDE_THE_PIN}: is not eligible" in found[0].detail


@pytest.mark.parametrize("listed", [[*ELIGIBLE_ROLES, OUTSIDE_THE_PIN], list(ELIGIBLE_ROLES), []])
def test_a_ledger_that_lists_eligible_roles_of_its_own_is_refused(
    repo: Path, listed: list[str]
) -> None:
    write_ledger(repo, researcher=trial_row())
    path = repo / km.LEDGER_PATH
    path.write_text(path.read_text(encoding="utf-8") + yaml.safe_dump({"eligible": listed}))

    found = [f for f in cb.check(repo) if f.kind == "I9-eligible-in-ledger"]

    assert [f.subject for f in found] == [km.LEDGER_PATH]
    assert "kernel_eligibility" in found[0].detail


def test_a_ledger_without_an_eligible_key_raises_no_eligibility_finding(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row())

    assert subjects(repo, "I9-eligible-in-ledger") == []


# -- The eligible roles are held to the parent commit's list ----------------------------------------

PIN_PATH = "scripts/kernel_eligibility.py"
NEWLY_ELIGIBLE = ELIGIBLE_ROLES[-1]  # the parent commit's list lacks it, this tree's pin has it
LISTED_AT_PARENT = ELIGIBLE_ROLES[:-1]


def write_pin(repo: Path, roles: tuple[str, ...]) -> None:
    (repo / PIN_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / PIN_PATH).write_text(f"ELIGIBLE_ROLES = {roles!r}\n", encoding="utf-8")


def committed_pin(repo: Path, roles: tuple[str, ...]) -> None:
    """A parent commit pinning `roles` and holding no ledger and no flag."""
    write_pin(repo, roles)
    commit_all(repo)


def test_a_record_beside_a_change_of_the_eligible_roles_is_refused_naming_the_role(
    repo: Path,
) -> None:
    committed_pin(repo, LISTED_AT_PARENT)

    write_ledger(repo, researcher=trial_row())
    found = [f for f in cb.check(repo) if f.kind == "I9-eligible-with-move"]

    assert [f.subject for f in found] == ["role researcher"]
    assert f"+{NEWLY_ELIGIBLE}" in found[0].detail
    assert "adoption record" in found[0].detail


def test_a_record_beside_an_unchanged_list_of_eligible_roles_passes(repo: Path) -> None:
    committed_pin(repo, ELIGIBLE_ROLES)

    write_ledger(repo, researcher=trial_row())

    assert subjects(repo, "I9-eligible-with-move") == []


def test_a_flag_beside_a_change_of_the_eligible_roles_is_refused_naming_the_role(
    repo: Path,
) -> None:
    committed_pin(repo, LISTED_AT_PARENT)

    omit_claude_md(repo, "researcher")
    found = [f for f in cb.check(repo) if f.kind == "I9-eligible-with-move"]

    assert [f.subject for f in found] == ["role researcher"]
    assert "omitClaudeMd flag" in found[0].detail


def test_a_flag_beside_an_unchanged_list_of_eligible_roles_passes(repo: Path) -> None:
    committed_pin(repo, ELIGIBLE_ROLES)

    omit_claude_md(repo, "researcher")

    assert subjects(repo, "I9-eligible-with-move") == []


def test_a_change_of_the_eligible_roles_beside_neither_a_record_nor_a_flag_passes(
    repo: Path,
) -> None:
    committed_pin(repo, LISTED_AT_PARENT)

    (repo / "README.probe").write_text("nothing else changes\n", encoding="utf-8")

    assert subjects(repo, "I9-eligible-with-move") == []


def test_a_committed_change_of_the_eligible_roles_beside_a_record_is_judged_from_its_parent(
    repo: Path,
) -> None:
    committed_pin(repo, LISTED_AT_PARENT)
    write_ledger(repo, researcher=trial_row())
    commit_all(repo)

    assert subjects(repo, "I9-eligible-with-move") == ["role researcher"]


def test_a_move_to_switched_of_a_role_the_parent_commit_did_not_list_is_refused(
    repo: Path,
) -> None:
    write_ledger(repo, **{NEWLY_ELIGIBLE: trial_row()})
    write_pin(repo, LISTED_AT_PARENT)
    commit_all(repo)

    flipped(repo, role=NEWLY_ELIGIBLE)
    found = [f for f in cb.check(repo) if f.kind == "I9-eligible-not-yet"]

    assert [f.subject for f in found] == [f"role {NEWLY_ELIGIBLE}"]
    assert ", ".join(LISTED_AT_PARENT) in found[0].detail


def test_a_move_to_switched_of_a_role_the_parent_commit_listed_passes(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    write_pin(repo, LISTED_AT_PARENT)
    commit_all(repo)

    flipped(repo)

    assert subjects(repo, "I9-eligible-not-yet") == []


def test_a_role_already_switched_at_the_parent_commit_is_not_a_move(repo: Path) -> None:
    flipped(repo, role=NEWLY_ELIGIBLE)
    write_pin(repo, LISTED_AT_PARENT)
    commit_all(repo)

    write_ledger(repo, **{NEWLY_ELIGIBLE: switched_row(probe_after_tokens=21_000)})

    assert subjects(repo, "I9-eligible-not-yet") == []


def test_a_parent_commit_before_the_pin_is_held_to_the_list_its_ledger_carried(
    repo: Path,
) -> None:
    write_ledger(repo, **{NEWLY_ELIGIBLE: trial_row()})
    ledger = repo / km.LEDGER_PATH
    ledger.write_text(
        ledger.read_text(encoding="utf-8") + yaml.safe_dump({"eligible": list(LISTED_AT_PARENT)}),
        encoding="utf-8",
    )
    commit_all(repo)

    flipped(repo, role=NEWLY_ELIGIBLE)

    assert subjects(repo, "I9-eligible-not-yet") == [f"role {NEWLY_ELIGIBLE}"]


def test_a_parent_commit_that_pins_no_eligible_roles_anywhere_holds_the_move_to_none(
    repo: Path,
) -> None:
    write_ledger(repo, researcher=trial_row())
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()


def test_a_shallow_clone_without_the_parent_commit_judges_no_eligibility(
    repo: Path, tmp_path: Path
) -> None:
    committed_pin(repo, LISTED_AT_PARENT)
    write_ledger(repo, researcher=trial_row())
    commit_all(repo)
    clone = tmp_path / "shallow"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(clone)],
        check=True,
        capture_output=True,
        env=env,
        timeout=60,
    )

    assert [f for f in cb.check(clone) if f.kind.startswith("I9-eligible")] == []


# -- The flag is read from the frontmatter as YAML reads it ------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "omitClaudeMd : true",
        '"omitClaudeMd": true',
        "'omitClaudeMd': true",
        "omitClaudeMd:\n  true",
    ],
    ids=["space before colon", "quoted key", "single-quoted key", "value on next line"],
)
def test_the_flag_in_any_form_yaml_reads_as_a_literal_true_counts(repo: Path, line: str) -> None:
    frontmatter_line(repo, "researcher", line)

    assert subjects(repo, "I9-flag-without-record") == ["role researcher"]
    assert subjects(repo, "I9-flag-not-literal-true") == []


@pytest.mark.parametrize(
    "line", ["omitClaudeMd : false", '"omitClaudeMd": null', "omitClaudeMd:", "'omitClaudeMd': yes"]
)
def test_the_flag_in_any_form_yaml_reads_as_something_else_is_refused(
    repo: Path, line: str
) -> None:
    frontmatter_line(repo, "researcher", line)

    assert subjects(repo, "I9-flag-without-record") == []
    assert subjects(repo, "I9-flag-not-literal-true") == ["role researcher"]


def test_a_definition_whose_frontmatter_is_not_yaml_is_an_input_error(repo: Path) -> None:
    frontmatter_line(repo, "researcher", "omitClaudeMd: [unclosed")

    assert run_checker(repo).returncode == 2


# -- The parent commit's ledger is read as leniently as the ladder needs ---------------------------


def test_a_commit_that_completes_a_record_the_model_refuses_is_not_blocked_by_the_old_one(
    repo: Path,
) -> None:
    bare = {"status": "switched", "since": "2026-10-12", "runs": []}
    write_ledger(repo, researcher=bare)
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()


def test_a_commit_that_removes_the_agent_of_an_adopted_role_is_not_blocked_by_the_old_ledger(
    repo: Path,
) -> None:
    write_ledger(repo, ghost=trial_row())
    commit_all(repo)

    write_ledger(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-ledger-transition"]
    assert [(f.subject, f.detail) for f in found] == [("role ghost", "trial -> absent")]


BROKEN_LEDGER = "roles: [unclosed"


def commit_broken_ledger(repo: Path) -> None:
    (repo / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / km.LEDGER_PATH).write_text(BROKEN_LEDGER, encoding="utf-8")
    commit_all(repo)


def test_a_parent_ledger_too_broken_to_read_is_an_input_error_naming_it(repo: Path) -> None:
    commit_broken_ledger(repo)

    flipped(repo)
    ran = run_checker(repo)

    assert ran.returncode == 2
    assert "parent commit's ledger cannot be read" in ran.stderr
    assert "kernel_adoption.yaml at HEAD" in ran.stderr


def test_a_parent_ledger_too_broken_to_read_is_refused_when_the_tree_is_committed_too(
    repo: Path,
) -> None:
    commit_broken_ledger(repo)
    flipped(repo)
    commit_all(repo)

    ran = run_checker(repo)

    assert ran.returncode == 2
    assert "kernel_adoption.yaml at HEAD^" in ran.stderr


def test_deleting_the_ledger_cannot_pass_as_a_first_appearance_over_an_unreadable_parent(
    repo: Path,
) -> None:
    commit_broken_ledger(repo)

    (repo / km.LEDGER_PATH).unlink()

    assert run_checker(repo).returncode == 2


def test_a_parent_commit_holding_no_ledger_is_read_as_none(repo: Path) -> None:
    commit_all(repo)

    write_ledger(repo, researcher=trial_row())

    assert cb.check(repo) == ()
    assert run_checker(repo).returncode == 0


# -- The first appearance of a ledger cannot be repeated -------------------------------------------------


def test_deleting_a_ledger_the_parent_commit_holds_is_reported(repo: Path) -> None:
    write_ledger(repo)
    commit_all(repo)

    (repo / km.LEDGER_PATH).unlink()

    assert subjects(repo, "I9-ledger-deleted") == [km.LEDGER_PATH]


def test_a_checkout_that_never_had_a_ledger_has_none_to_lose(repo: Path) -> None:
    commit_all(repo)

    assert subjects(repo, "I9-ledger-deleted") == []


# -- I10: the spawn hook reads the ledger as the gate does ---------------------------------------


def inject_kernel_status(repo: Path, role: str) -> str | None:
    return cb.inject_kernel.adoption_status(
        (repo / km.LEDGER_PATH).read_text(encoding="utf-8"), role
    )


LEDGER_HEAD = "version: 1\nroles:\n"


def test_a_ledger_in_its_generated_block_shape_is_read_alike_by_the_hook(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row(), verifier=trial_row())

    assert subjects(repo, "I10-hook-misread") == []


def test_a_held_record_in_its_generated_block_shape_is_read_alike_by_the_hook(repo: Path) -> None:
    write_ledger(repo, researcher=held_row(runs=[run_row(passes=False)]), verifier=trial_row())

    assert subjects(repo, "I10-hook-misread") == []
    assert inject_kernel_status(repo, "researcher") == "held"


@pytest.mark.parametrize(
    "record",
    [
        "    researcher:\n        status: trial\n        since: '2026-10-12'\n        runs: []\n",
        "  researcher:\n    status: 'trial'\n    since: '2026-10-12'\n    runs: []\n",
    ],
    ids=["indented four spaces", "a quoted status"],
)
def test_a_record_the_parser_reads_and_the_spawn_hook_cannot_is_reported(
    repo: Path, record: str
) -> None:
    (repo / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / km.LEDGER_PATH).write_text(LEDGER_HEAD + record, encoding="utf-8")

    found = [f for f in cb.check(repo) if f.kind == "I10-hook-misread"]

    assert [f.subject for f in found] == ["role researcher"]
    assert "status None where PyYAML reads 'trial'" in found[0].detail
    assert "generated block shape" in found[0].detail


def test_a_record_the_spawn_hook_reads_and_the_parser_discards_is_reported(repo: Path) -> None:
    record = "  verifier:\n    status: trial\n    since: '2026-10-12'\n    runs: []\n"
    (repo / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / km.LEDGER_PATH).write_text(LEDGER_HEAD + record + "roles: {}\n", encoding="utf-8")

    found = [f for f in cb.check(repo) if f.kind == "I10-hook-misread"]

    assert [f.subject for f in found] == ["role verifier"]
    assert "status 'trial' where PyYAML reads None" in found[0].detail
