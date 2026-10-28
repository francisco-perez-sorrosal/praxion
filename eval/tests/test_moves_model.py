"""The move values: each invariant has a constructor that refuses, and legal shapes build."""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path
from typing import get_args

import pytest

from praxion_evals.adherence.model import Failed, Passed
from praxion_evals.adherence.moves.model import (
    ARMS_OF,
    ArmChanges,
    Arrived,
    BothKinds,
    CheckTrigger,
    GovernedCheck,
    GovernedChecks,
    HookContext,
    KernelDerive,
    LaunchOptions,
    ManifestRowRemoved,
    MoveArm,
    MoveDeclaration,
    MoveName,
    NeverArrived,
    OnlyKind,
    PathMatched,
    Pinned,
    RelPath,
    Remove,
    RunKind,
    SessionStart,
    Take,
    Unknown,
    Write,
    admits,
)

DIGEST = "ab" * 32
RULE = RelPath.parse("rules/swe/vcs/git-conventions.md")


def a_check(name: str = "commit-message-form") -> GovernedCheck:
    return GovernedCheck(name, RULE, "Commit Message Format", ("50 characters",))


def a_write(path: str = "hooks/stage_guard.py") -> Write:
    return Write(RelPath.parse(path), Path("kit/stage_guard.py"), DIGEST)


def a_pinned(**overrides: str) -> Pinned:
    base = {
        "commit_attribution": "off",
        "model": "m",
        "effort": "high",
        "user_instructions": DIGEST,
    }
    return Pinned(**{**base, **overrides})


def a_declaration(**overrides: object) -> MoveDeclaration:
    base: dict[str, object] = {
        "move": MoveName("git-conventions"),
        "moved_rule": RULE,
        "checks": GovernedChecks((a_check(),)),
        "arms": ArmChanges(lean=(a_write(),)),
        "deliveries": (SessionStart(RULE),),
        "fixture_scope": BothKinds(),
        "launch": {},
    }
    return MoveDeclaration(**{**base, **overrides})  # type: ignore[arg-type]


def test_importing_the_package_loads_no_sibling_module() -> None:
    sys.modules.pop("praxion_evals.adherence.moves", None)
    package = importlib.import_module("praxion_evals.adherence.moves")
    assert not [name for name in vars(package) if not name.startswith("__")]


@pytest.mark.parametrize("text", ["", "Git", "git_conventions", "-git", "git-", "git--rule"])
def test_a_move_name_that_is_not_hyphenated_words_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="move name"):
        MoveName(text)


def test_a_paired_run_measures_full_and_lean_and_a_floor_run_measures_the_floor() -> None:
    assert ARMS_OF == {"floor": ("floor",), "paired": ("full", "lean")}
    assert set(ARMS_OF) == set(get_args(RunKind))
    assert {arm for arms in ARMS_OF.values() for arm in arms} == set(get_args(MoveArm))


def test_a_relative_path_is_normalised_to_one_form() -> None:
    assert RelPath.parse("./rules//swe/../swe/x.md").value == "rules/swe/x.md"


@pytest.mark.parametrize(
    "text",
    ["", "/etc/passwd", "..", "../outside.md", "a/../../b", ".", "a\\b", ".ai-state/eval_ledger/x"],
)
def test_a_path_outside_the_checkout_or_under_the_ledger_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="relative path"):
        RelPath.parse(text)


def test_a_path_built_directly_in_non_normal_form_is_refused() -> None:
    with pytest.raises(ValueError, match="normal form"):
        RelPath("a/./b")


def test_the_full_arm_has_no_changes_and_cannot_be_given_one() -> None:
    changes = ArmChanges.of({"lean": [a_write()], "floor": [Remove(RULE)]})
    assert changes.for_arm("full") == ()
    assert changes.for_arm("lean") == (a_write(),)
    with pytest.raises(ValueError, match="full arm"):
        ArmChanges.of({"full": [a_write()]})


def test_an_arm_named_outside_the_three_is_refused() -> None:
    with pytest.raises(ValueError, match="arm"):
        ArmChanges.of({"thin": [a_write()]})


def test_two_changes_to_one_path_of_one_arm_are_refused_but_two_arms_may_share_a_path() -> None:
    with pytest.raises(ValueError, match="lean arm changes a path once"):
        ArmChanges(lean=(a_write(), Remove(a_write().path)))
    assert ArmChanges(lean=(a_write(),), floor=(Remove(a_write().path),)).floor


def test_a_write_without_a_content_digest_is_refused() -> None:
    with pytest.raises(ValueError, match="sha256"):
        Write(RULE, Path("kit/x"), "not-a-digest")


@pytest.mark.parametrize("prefixes", [(), (" ",), ("- Stage", "- Stage")])
def test_a_kernel_derive_needs_distinct_non_blank_prefixes(prefixes: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="prefix"):
        KernelDerive(RULE, prefixes)


def test_a_kernel_derive_with_one_prefix_builds() -> None:
    assert KernelDerive(RULE, ("- Stage",)).prefixes == ("- Stage",)


@pytest.mark.parametrize("names", [("a",), ("a", "b")])
def test_a_move_governs_one_or_two_checks(names: tuple[str, ...]) -> None:
    assert len(GovernedChecks(tuple(a_check(n) for n in names)).checks) == len(names)


@pytest.mark.parametrize("names", [(), ("a", "b", "c")])
def test_a_move_governing_zero_or_three_checks_is_refused(names: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="one or two checks"):
        GovernedChecks(tuple(a_check(n) for n in names))


def test_two_governed_checks_may_not_share_a_name() -> None:
    with pytest.raises(ValueError, match="distinct"):
        GovernedChecks((a_check("a"), a_check("a")))


def test_a_governed_check_without_a_section_is_refused() -> None:
    with pytest.raises(ValueError, match="section"):
        GovernedCheck("commit-message-form", RULE, " ")


def test_a_delivery_that_reads_nothing_to_match_is_refused() -> None:
    with pytest.raises(ValueError, match="glob"):
        PathMatched(RULE, ())
    with pytest.raises(ValueError, match="matcher"):
        HookContext("PreToolUse", "", RULE, "each")


def test_each_delivery_names_its_channel() -> None:
    assert SessionStart.channel == "session_start"
    assert PathMatched.channel == "path_matched"
    assert HookContext.channel == "hook_context"


def test_a_fixture_scope_admits_both_kinds_or_exactly_one() -> None:
    assert admits(BothKinds(), "managed")
    assert admits(BothKinds(), "unmanaged")
    assert admits(OnlyKind("managed"), "managed")
    assert not admits(OnlyKind("managed"), "unmanaged")


def test_pinned_settings_report_the_fields_that_differ() -> None:
    assert a_pinned().differences(a_pinned()) == ()
    assert a_pinned().differences(a_pinned(effort="low", model="n")) == ("model", "effort")
    with pytest.raises(ValueError, match="model"):
        a_pinned(model=" ")


def test_a_launch_option_left_unset_stays_the_entry_default() -> None:
    declared = a_declaration(launch={"lean": LaunchOptions(effort="low")})
    assert declared.launch["lean"].effort == "low"
    assert declared.launch["full"] == LaunchOptions()
    with pytest.raises(ValueError, match="non-empty"):
        LaunchOptions(model=" ")


def test_a_declaration_names_only_the_three_arms_in_its_launch_options() -> None:
    with pytest.raises(ValueError, match="three arms"):
        a_declaration(launch={"thin": LaunchOptions()})


def test_a_declaration_cannot_be_edited_after_it_is_built() -> None:
    declared = a_declaration()
    with pytest.raises(dataclasses.FrozenInstanceError):
        declared.move = MoveName("other")  # type: ignore[misc]
    with pytest.raises(TypeError):
        declared.launch["lean"] = LaunchOptions()  # type: ignore[index]


def test_a_manifest_derive_is_a_change_of_the_arm_it_is_declared_on() -> None:
    row = ManifestRowRemoved(RelPath.parse("rules/_manifest.yaml"))
    assert ArmChanges(lean=(row,)).for_arm("lean") == (row,)


def test_an_unreadable_record_reads_every_arrival_as_unknown_never_as_never_arrived() -> None:
    trigger = CheckTrigger.unreadable("commit-message-form", ["session_start", "hook_context"])
    assert set(trigger.arrivals.values()) == {Unknown()}
    assert not trigger.trigger_failure


def test_a_record_without_history_may_not_claim_a_known_arrival() -> None:
    with pytest.raises(ValueError, match="unreadable"):
        CheckTrigger("c", {"hook_context": Arrived("before execution")}, None, None)
    with pytest.raises(ValueError, match="unreadable"):
        CheckTrigger("c", {}, None, None)


def test_a_trigger_failure_is_a_failed_check_that_nothing_ever_reached() -> None:
    never = {"hook_context": NeverArrived(), "session_start": NeverArrived()}
    assert CheckTrigger("c", never, Failed("subject too long"), "not_repaired").trigger_failure
    assert not CheckTrigger("c", never, Passed(), "right_first_time").trigger_failure
    reached = {**never, "hook_context": Arrived("after execution")}
    assert not CheckTrigger("c", reached, Failed("late"), "not_repaired").trigger_failure
    assert not CheckTrigger("c", {}, Failed("late"), "never_taken").trigger_failure


def test_a_trigger_record_keeps_its_arrivals_out_of_reach_of_edits() -> None:
    trigger = CheckTrigger("c", {"hook_context": NeverArrived()}, Passed(), "never_taken")
    with pytest.raises(TypeError):
        trigger.arrivals["session_start"] = NeverArrived()  # type: ignore[index]


def test_a_take_is_scored_or_refused_with_a_reason_never_both_or_neither() -> None:
    assert Take.taken() == Take(True, None, False)
    assert Take.taken(trigger_failure=True).trigger_failure
    assert Take.refused("lean session lacks its kernel").scored is False


@pytest.mark.parametrize(("scored", "reason"), [(True, "reason"), (False, None), (False, " ")])
def test_a_take_with_a_reason_mismatch_is_refused(scored: bool, reason: str | None) -> None:
    with pytest.raises(ValueError, match="reason"):
        Take(scored, reason)


def test_a_refused_take_cannot_be_a_trigger_failure() -> None:
    with pytest.raises(ValueError, match="scored take"):
        Take(False, "not taken", True)
