"""A governed check's declared phrase is text the section it names holds.

When a move's declaration is read against a checkout (its arms built, or a run or a dry run of
it prepared), a phrase the named section does not hold is refused, naming the check, the phrase,
the section and the rule file. Phrases are compared ignoring letter case; a phrase the rule
holds only outside the named section is refused. A section is a heading and every line after it
up to the next heading of the same or a higher level, sub-headings included. The git-conventions
declaration is accepted unchanged, and every phrase the adr-conventions kit declares is held by
the section its check names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers import move_declarations
from tests.acceptance.drivers.adherence_eval import install_fake_claude
from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    SECOND_MOVE,
    Declared,
    MoveRun,
    Variant,
    build_arms,
    declare,
    move_checkout,
    run_move,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REFUSED: tuple[Variant, ...] = (
    "a check phrase its section does not hold",
    "a check phrase its rule holds only outside the named section",
)


@dataclass(frozen=True)
class Phrased:
    declared: Declared
    check: dict  # the governed check carrying the variant's added phrase
    phrase: str


def _phrased(variant: Variant, workspace: Path) -> Phrased:
    declared = declare(FIRST_MOVE, variant, workspace)
    assert declared.path is not None
    check = json.loads(declared.path.read_text(encoding="utf-8"))["checks"][0]
    return Phrased(declared, check, check["phrases"][-1])


def _refusal(declared: Declared, workspace: Path) -> str | None:
    return build_arms(declared, move_checkout(workspace), workspace / "arms").refusal


# -- Refused, naming what is wrong ------------------------------------------------------------


@pytest.mark.parametrize("variant", REFUSED)
def test_a_phrase_its_named_section_does_not_hold_is_refused_when_the_arms_are_built(
    tmp_path, variant
):
    phrased = _phrased(variant, tmp_path)

    refusal = _refusal(phrased.declared, tmp_path)

    assert refusal is not None, f"the phrase {phrased.phrase!r} was accepted"


@pytest.mark.parametrize("variant", REFUSED)
def test_the_refusal_names_the_check_the_phrase_the_section_and_the_rule_file(tmp_path, variant):
    phrased = _phrased(variant, tmp_path)

    refusal = _refusal(phrased.declared, tmp_path) or ""

    named = {
        part: phrased.check[part] if part != "phrase" else phrased.phrase
        for part in ("name", "phrase", "section", "rule_file")
    }
    assert {part: value for part, value in named.items() if value not in refusal} == {}, refusal


def test_a_dry_run_of_a_declaration_carrying_an_unheld_phrase_is_refused_launching_nothing(
    tmp_path,
):
    phrased = _phrased("a check phrase its section does not hold", tmp_path)
    stand_in = install_fake_claude(tmp_path)
    run = MoveRun(FIRST_MOVE, move_checkout(tmp_path), dry_run=True, declared=phrased.declared)

    result = run_move(run, stand_in.bin_dir)

    assert result.exit_code != 0, "the dry run was not refused"
    assert phrased.phrase in result.stdout + result.stderr, result.stderr[-2000:]
    assert stand_in.launches() == []


# -- Accepted ---------------------------------------------------------------------------------


def test_a_phrase_differing_only_in_letter_case_from_its_section_is_accepted(tmp_path):
    phrased = _phrased("a check phrase differing only in letter case from its section", tmp_path)

    assert _refusal(phrased.declared, tmp_path) is None


def test_the_git_conventions_declaration_is_accepted_unchanged(tmp_path):
    assert _refusal(declare(FIRST_MOVE, "as declared", tmp_path), tmp_path) is None


def test_every_phrase_the_adr_conventions_kit_declares_is_held_by_the_section_its_check_names():
    payload = move_declarations.kit_payload(SECOND_MOVE)

    unheld = [
        (check["name"], phrase)
        for check in payload["checks"]
        for phrase in check["phrases"]
        if phrase.casefold() not in _section(check).casefold()
    ]

    assert payload["checks"], "the kit declares no governed check"
    assert unheld == [], unheld


def _section(check: dict) -> str:
    text = (REPO_ROOT / check["rule_file"]).read_text(encoding="utf-8")
    return move_declarations.section_text(text, check["section"])
