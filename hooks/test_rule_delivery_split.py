"""The pure side of the spawn split: who receives it, and which text each unit gets.

A split recipient is only ever a plugin role whose definition was read and keeps
the instruction files; everything doubtful is a whole recipient, the safe
direction. A stored split text is trusted one unit at a time, on three digests
(the unit's body, the audience manifest, the split text itself), and any
disagreement gives that unit its whole body back.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

# Flat import, as the sibling hook tests do.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _project_scope import Managed  # noqa: E402
from _rule_delivery import (  # noqa: E402
    MANAGED_CORE_UNITS,
    AgentKind,
    Event,
    SpawnSplit,
    SplitEntry,
    distrusted_units,
    parse_agent_kind,
    parse_spawn_split,
    plan_delivery,
    rule_body,
    spawn_units,
)

MANAGED = Managed(Path("/project"), Path("/project/.ai-state"))
CORE_IDS = tuple(unit.unit_id for unit in MANAGED_CORE_UNITS)
MANIFEST = "manifest bytes as read"
FIRST, SECOND = CORE_IDS[0], CORE_IDS[1]
WHOLE = {FIRST: "## A\n\nkept\n\n## B\n\ndropped\n", SECOND: "## C\n\nall of it\n"}
SPLIT_TEXT = {FIRST: "## A\n\nkept\n", SECOND: "## C\n"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry(unit_id: str, **override: str) -> SplitEntry:
    fields = {
        "source": f"rules/{unit_id}.md",
        "whole_sha256": _sha(WHOLE[unit_id]),
        "text": SPLIT_TEXT[unit_id],
        "text_sha256": _sha(SPLIT_TEXT[unit_id]),
        **override,
    }
    return SplitEntry(**fields)


def _split(entries: dict[str, SplitEntry] | None = None) -> SpawnSplit:
    return SpawnSplit(_sha(MANIFEST), entries or {FIRST: _entry(FIRST), SECOND: _entry(SECOND)})


def _wire(split: SpawnSplit | None = None) -> dict:
    """The artifact's JSON shape for ``split``, as its one writer renders it."""
    split = split or _split()
    return {
        "schema": 1,
        "manifest_sha256": split.manifest_sha256,
        "units": {
            unit_id: {
                "source": entry.source,
                "whole_sha256": entry.whole_sha256,
                "text": entry.text,
                "text_sha256": entry.text_sha256,
            }
            for unit_id, entry in split.units.items()
        },
    }


# -- the shared body definition ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "body"),
    [
        ("---\nname: x\n---\n\n## Rule\n\ntext\n", "## Rule\n\ntext\n"),
        ("---  \nname: x\n---  \n## Rule\n", "## Rule\n"),
        ("no frontmatter\n", "no frontmatter\n"),
        ("\n\nleading blanks only\n", "leading blanks only\n"),
        ("---\nname: x\n---\n---\nkept: rule\n---\n", "---\nkept: rule\n---\n"),
        ("", ""),
    ],
)
def test_a_rule_body_is_the_file_without_its_leading_frontmatter(raw, body):
    assert rule_body(raw) == body


# -- the kind of a spawn ---------------------------------------------------------


@pytest.mark.parametrize(
    ("agent_type", "omit_claude_md", "plugin_definition_read", "expected"),
    [
        ("Explore", False, False, AgentKind.NO_INSTRUCTION_FILES),
        ("Plan", None, False, AgentKind.NO_INSTRUCTION_FILES),
        ("Explore", True, True, AgentKind.NO_INSTRUCTION_FILES),
        ("praxion:researcher", True, True, AgentKind.LEAN),
        ("researcher", True, False, AgentKind.LEAN),
        ("", True, False, AgentKind.LEAN),
        ("praxion:verifier", False, True, AgentKind.SPLIT_RECIPIENT),
        ("praxion:verifier", False, False, AgentKind.WHOLE_RECIPIENT),
        ("praxion:verifier", None, False, AgentKind.WHOLE_RECIPIENT),
        ("praxion:verifier", None, True, AgentKind.WHOLE_RECIPIENT),
        ("praxion:", False, True, AgentKind.WHOLE_RECIPIENT),
        ("other:verifier", False, True, AgentKind.WHOLE_RECIPIENT),
        ("verifier", False, True, AgentKind.WHOLE_RECIPIENT),
        ("general-purpose", False, False, AgentKind.WHOLE_RECIPIENT),
        ("custom-agent", None, False, AgentKind.WHOLE_RECIPIENT),
        (None, None, False, AgentKind.WHOLE_RECIPIENT),
    ],
)
def test_only_a_read_plugin_definition_that_keeps_the_instruction_files_splits(
    agent_type, omit_claude_md, plugin_definition_read, expected
):
    assert parse_agent_kind(agent_type, omit_claude_md, plugin_definition_read) is expected


@pytest.mark.parametrize("agent", [AgentKind.SPLIT_RECIPIENT, AgentKind.WHOLE_RECIPIENT])
def test_both_recipient_kinds_are_planned_the_three_core_units(agent):
    units = {unit_id: f"body of {unit_id}\n" for unit_id in CORE_IDS}
    plan = plan_delivery(units, set(CORE_IDS), MANAGED, Event.SUBAGENT, agent, (), ())
    assert [part.unit_id for part in plan] == list(CORE_IDS)


@pytest.mark.parametrize("agent", [AgentKind.LEAN, AgentKind.NO_INSTRUCTION_FILES])
def test_the_other_two_kinds_are_planned_nothing(agent):
    units = {unit_id: f"body of {unit_id}\n" for unit_id in CORE_IDS}
    assert plan_delivery(units, set(CORE_IDS), MANAGED, Event.SUBAGENT, agent, (), ()) == ()


# -- parsing the artifact ----------------------------------------------------------


def test_a_well_formed_artifact_parses_to_its_entries():
    assert parse_spawn_split(json.dumps(_wire())) == _split()


def test_an_artifact_with_no_units_parses_to_an_empty_table():
    wire = {"schema": 1, "manifest_sha256": _sha(MANIFEST), "units": {}}
    assert parse_spawn_split(json.dumps(wire)) == SpawnSplit(_sha(MANIFEST), {})


def _without(path: tuple[str, ...]) -> dict:
    wire = _wire()
    holder = wire
    for key in path[:-1]:
        holder = holder[key]
    del holder[path[-1]]
    return wire


def _with(path: tuple[str, ...], value) -> dict:
    wire = _wire()
    holder = wire
    for key in path[:-1]:
        holder = holder[key]
    holder[path[-1]] = value
    return wire


ENTRY = ("units", FIRST)
NOT_PARSEABLE = {
    "not json": "{not json",
    "empty": "",
    "a list": json.dumps([1]),
    "a string": json.dumps("schema"),
    "null": "null",
    "wrong schema": json.dumps(_with(("schema",), 2)),
    "boolean schema": json.dumps(_with(("schema",), True)),
    "missing schema": json.dumps(_without(("schema",))),
    "missing manifest digest": json.dumps(_without(("manifest_sha256",))),
    "missing units": json.dumps(_without(("units",))),
    "missing source": json.dumps(_without((*ENTRY, "source"))),
    "missing whole digest": json.dumps(_without((*ENTRY, "whole_sha256"))),
    "missing text": json.dumps(_without((*ENTRY, "text"))),
    "missing text digest": json.dumps(_without((*ENTRY, "text_sha256"))),
    "units not a mapping": json.dumps(_with(("units",), [])),
    "entry not a mapping": json.dumps(_with(ENTRY, "text")),
    "text not a string": json.dumps(_with((*ENTRY, "text"), 7)),
    "text a lone surrogate": json.dumps(_with((*ENTRY, "text"), "## A\n\ud800\n")),
    "source not a string": json.dumps(_with((*ENTRY, "source"), None)),
    "manifest digest not a string": json.dumps(_with(("manifest_sha256",), 12)),
    "manifest digest not hex": json.dumps(_with(("manifest_sha256",), "z" * 64)),
    "manifest digest too short": json.dumps(_with(("manifest_sha256",), "ab")),
    "manifest digest in capitals": json.dumps(_with(("manifest_sha256",), "A" * 64)),
    "whole digest not hex": json.dumps(_with((*ENTRY, "whole_sha256"), "not a digest")),
    "text digest not hex": json.dumps(_with((*ENTRY, "text_sha256"), "g" * 64)),
}


@pytest.mark.parametrize("text", NOT_PARSEABLE.values(), ids=NOT_PARSEABLE.keys())
def test_an_artifact_that_is_not_the_schema_parses_to_none(text):
    assert parse_spawn_split(text) is None


def test_a_later_writers_extra_keys_do_not_stop_the_artifact_parsing():
    wire = _wire()
    wire["generated_by"] = "later"
    wire["units"][FIRST]["note"] = "later"
    assert parse_spawn_split(json.dumps(wire)) == _split()


# -- the text each unit receives -------------------------------------------------------


def test_every_unit_with_a_matching_entry_receives_its_split_text():
    assert spawn_units(WHOLE, _split(), _sha(MANIFEST)) == SPLIT_TEXT


def test_no_artifact_gives_every_unit_whole():
    assert spawn_units(WHOLE, None, _sha(MANIFEST)) == WHOLE


def test_no_manifest_digest_gives_every_unit_whole():
    assert spawn_units(WHOLE, _split(), None) == WHOLE


def test_a_manifest_that_changed_gives_every_unit_whole():
    assert spawn_units(WHOLE, _split(), _sha("another manifest")) == WHOLE


MISMATCHES = {
    "whole body edited": {"whole_sha256": _sha("an earlier body")},
    "split text edited": {"text": SPLIT_TEXT[FIRST] + "tampered\n"},
    "text digest wrong": {"text_sha256": _sha("another text")},
}


@pytest.mark.parametrize("override", MISMATCHES.values(), ids=MISMATCHES.keys())
def test_a_unit_whose_digest_disagrees_receives_its_whole_body_alone(override):
    split = _split({FIRST: _entry(FIRST, **override), SECOND: _entry(SECOND)})
    assert spawn_units(WHOLE, split, _sha(MANIFEST)) == {
        FIRST: WHOLE[FIRST],
        **{SECOND: SPLIT_TEXT[SECOND]},
    }


def test_a_body_that_changed_since_the_cut_receives_whole_while_the_other_keeps_its_split():
    edited = {**WHOLE, SECOND: WHOLE[SECOND] + "a later line\n"}
    assert spawn_units(edited, _split(), _sha(MANIFEST)) == {
        FIRST: SPLIT_TEXT[FIRST],
        SECOND: edited[SECOND],
    }


def test_a_unit_with_no_entry_receives_whole_while_the_other_keeps_its_split():
    split = _split({FIRST: _entry(FIRST)})
    assert spawn_units(WHOLE, split, _sha(MANIFEST)) == {
        FIRST: SPLIT_TEXT[FIRST],
        SECOND: WHOLE[SECOND],
    }


def test_an_entry_for_a_unit_that_is_not_supplied_adds_nothing():
    assert spawn_units({FIRST: WHOLE[FIRST]}, _split(), _sha(MANIFEST)) == {
        FIRST: SPLIT_TEXT[FIRST]
    }


def test_no_units_give_no_units():
    assert spawn_units({}, _split(), _sha(MANIFEST)) == {}


def test_the_choice_keeps_the_order_of_the_supplied_units():
    reversed_units = dict(reversed(WHOLE.items()))
    assert list(spawn_units(reversed_units, _split(), _sha(MANIFEST))) == list(reversed_units)


def test_choosing_mutates_neither_the_units_nor_the_split():
    units = copy.deepcopy(WHOLE)
    split = _split()
    before = copy.deepcopy(split)
    spawn_units(units, split, _sha(MANIFEST))
    assert units == WHOLE
    assert split == before


# -- the units whose stored split their sources no longer trust ---------------------------


def test_a_trusted_split_distrusts_no_unit():
    assert distrusted_units(WHOLE, _split(), _sha(MANIFEST)) == ()


@pytest.mark.parametrize("override", MISMATCHES.values(), ids=MISMATCHES.keys())
def test_a_unit_whose_digest_disagrees_is_named_alone(override):
    split = _split({FIRST: _entry(FIRST, **override), SECOND: _entry(SECOND)})
    assert distrusted_units(WHOLE, split, _sha(MANIFEST)) == (FIRST,)


def test_a_split_cut_under_another_manifest_distrusts_every_unit_it_holds_in_order():
    reversed_units = dict(reversed(WHOLE.items()))
    assert distrusted_units(reversed_units, _split(), _sha("another manifest")) == (SECOND, FIRST)


def test_a_unit_with_no_entry_is_never_named_while_a_stale_one_is():
    split = _split({FIRST: _entry(FIRST, whole_sha256=_sha("an earlier body"))})
    assert distrusted_units(WHOLE, split, _sha(MANIFEST)) == (FIRST,)


def test_a_split_text_goes_through_the_unchanged_framing():
    """A chosen split body is planned like any body: one labelled part per fitting unit."""
    chosen = spawn_units(WHOLE, _split(), _sha(MANIFEST))
    plan = plan_delivery(
        chosen, set(CORE_IDS), MANAGED, Event.SUBAGENT, AgentKind.SPLIT_RECIPIENT, (), ()
    )
    assert [part.text.partition("\n\n")[2] for part in plan] == list(SPLIT_TEXT.values())
