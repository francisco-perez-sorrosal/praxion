"""Canaries for I9 and I10: a role flips only with its record, a record the hook can read."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kernel_checker_testkit as kit  # noqa: E402
import check_kernel_manifest as cb  # noqa: E402
import kernel_ledger as kl  # noqa: E402
import kernel_model as km  # noqa: E402
from _kernel_checker_testkit import (  # noqa: E402
    ADHERENCE,
    commit_all,
    flipped,
    frontmatter_line,
    omit_claude_md,
    regenerate,
    run_checker,
    run_row,
    subjects,
    switched_row,
    trial_row,
    write_ledger,
)

# pytest finds a fixture by name in the module that uses it
repo = kit.repo
template = kit.template


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


@pytest.mark.parametrize("value", ["false", "False", ""])
def test_a_flag_set_to_false_or_left_empty_does_not_switch_a_role(repo: Path, value: str) -> None:
    omit_claude_md(repo, "researcher", value)

    assert subjects(repo, "I9-flag-without-record") == []


@pytest.mark.parametrize("value", ["true", "True", "yes", "'true'"])
def test_any_value_but_false_counts_as_the_flag(repo: Path, value: str) -> None:
    omit_claude_md(repo, "researcher", value)

    assert subjects(repo, "I9-flag-without-record") == ["role researcher"]


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
    flipped(repo, role="implementer")

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert len(found) == 1
    assert "implementer" in found[0].detail


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


# -- Only the pilot's five roles can ever be flipped -----------------------------------------------


def test_a_ledger_that_widens_its_own_eligible_list_cannot_flip_a_role_outside_the_pilot(
    repo: Path,
) -> None:
    write_ledger(repo, eligible=[*kit.PILOT, "implementer"], implementer=switched_row())
    omit_claude_md(repo, "implementer")
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-eligible-changed"]

    assert [f.subject for f in found] == [km.LEDGER_PATH]
    assert "implementer" in found[0].detail


def test_a_ledger_that_drops_a_pilot_role_from_its_eligible_list_is_reported(repo: Path) -> None:
    write_ledger(repo, eligible=kit.PILOT[1:])

    assert subjects(repo, "I9-eligible-changed") == [km.LEDGER_PATH]


def test_the_eligible_list_is_the_pilots_whatever_its_order(repo: Path) -> None:
    write_ledger(repo, eligible=list(reversed(kit.PILOT)))

    assert subjects(repo, "I9-eligible-changed") == []


def test_the_pilot_is_the_five_roles_the_design_names() -> None:
    assert sorted(cb.PILOT_ROLES) == sorted(
        ["researcher", "verifier", "discipline-consultant", "skill-genesis", "context-engineer"]
    )


# -- The flag is read from the frontmatter as YAML reads it ------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "omitClaudeMd : true",
        '"omitClaudeMd": true',
        "'omitClaudeMd': yes",
        "omitClaudeMd:\n  true",
        "omitClaudeMd: 'false'",
    ],
    ids=["space before colon", "quoted key", "single-quoted key", "value on next line", "string"],
)
def test_the_flag_in_any_form_yaml_reads_as_set_counts(repo: Path, line: str) -> None:
    frontmatter_line(repo, "researcher", line)

    assert subjects(repo, "I9-flag-without-record") == ["role researcher"]


@pytest.mark.parametrize("line", ["omitClaudeMd : false", '"omitClaudeMd": null', "omitClaudeMd:"])
def test_the_flag_that_yaml_reads_as_false_or_null_does_not_count(repo: Path, line: str) -> None:
    frontmatter_line(repo, "researcher", line)

    assert subjects(repo, "I9-flag-without-record") == []


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


def test_a_parent_ledger_too_broken_to_read_is_told_and_judged_as_none(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / km.LEDGER_PATH).write_text("roles: [unclosed", encoding="utf-8")
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()
    assert "its moves are not judged" in capsys.readouterr().err


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

LEDGER_HEAD = "version: 1\neligible:\n" + "".join(f"- {role}\n" for role in kit.PILOT) + "roles:\n"


def test_a_ledger_in_its_generated_block_shape_is_read_alike_by_the_hook(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row(), verifier=trial_row())

    assert subjects(repo, "I10-hook-misread") == []


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
