"""The rule injector is registered with room for its largest delivery and a spare slot.

Each registered `inject_rules.py --slot N` prints one part of the plan, so a plan
with more parts than slots would lose its tail without a word. These tests count
the parts of the largest delivery the injector can plan (every hook-delivered
unit and every managed core unit, in a managed scope), read with the injector's
own readers, and hold the registered slots at that count plus one: a growing rule
fails here instead of being dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inject_rules  # noqa: E402
from _project_scope import Managed  # noqa: E402
from _rule_delivery import MANAGED_CORE_UNITS, AgentKind, Event, plan_delivery  # noqa: E402

REPO_ROOT = next(
    root
    for root in Path(__file__).resolve().parents
    if (root / "rules" / "_manifest.yaml").is_file()
)
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
INJECTOR_COMMAND = "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/inject_rules.py"
EVENTS = {"SessionStart": Event.SESSION, "SubagentStart": Event.SUBAGENT}
SPARE_SLOTS = 1
SESSION_START_TIMEOUT = 15
MANAGED = Managed(REPO_ROOT, REPO_ROOT / ".ai-state")


def _injector_hooks(event: str) -> list[dict]:
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"].get(event, [])
    return [
        hook
        for group in groups
        for hook in group["hooks"]
        if hook.get("command", "").startswith(INJECTOR_COMMAND)
    ]


def _slots(event: str) -> list[int]:
    prefix = f"{INJECTOR_COMMAND} {inject_rules.SLOT_FLAG} "
    return [int(hook["command"].removeprefix(prefix)) for hook in _injector_hooks(event)]


def _largest_supply() -> dict[str, str]:
    """Every unit the injector can deliver, as it reads them: hook-deliver rows and the floor."""
    units, _ = inject_rules._hook_delivered_units(inject_rules._load_manifest(REPO_ROOT), REPO_ROOT)
    for unit in MANAGED_CORE_UNITS:
        units[unit.unit_id] = inject_rules._read_rule_body(REPO_ROOT, unit.path)
    return units


def _strings_needed(units: dict[str, str], event: Event) -> int:
    """The most strings one delivery prints: the whole managed plan, or the floor and its notice."""
    plan = plan_delivery(units, set(units), MANAGED, event, AgentKind.INHERITING, set(), set())
    core = {unit.unit_id for unit in MANAGED_CORE_UNITS}
    floor = [part for part in plan if part.unit_id in core]
    return max(len(plan), len(floor) + 1)


def _has_room(event: str, units: dict[str, str]) -> bool:
    return len(_slots(event)) >= _strings_needed(units, EVENTS[event]) + SPARE_SLOTS


REGISTERED_EVENTS = [event for event in EVENTS if _injector_hooks(event)]


def test_the_injector_is_registered_at_session_start_and_at_no_unknown_event():
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    found = {event for event in groups if _injector_hooks(event)}

    assert "SessionStart" in found
    assert found <= set(EVENTS)


@pytest.mark.parametrize("event", REGISTERED_EVENTS)
def test_every_event_has_a_slot_per_part_of_its_largest_delivery_and_a_spare(event):
    assert _has_room(event, _largest_supply()), (
        f"{event}: {len(_slots(event))} slots registered, "
        f"{_strings_needed(_largest_supply(), EVENTS[event])} strings needed plus {SPARE_SLOTS}"
    )


@pytest.mark.parametrize("event", REGISTERED_EVENTS)
def test_an_oversize_unit_leaves_the_registered_slots_short(event):
    section = "## Section\n\n" + "x" * 78 + "\n\n"
    units = {**_largest_supply(), "swe/oversize": section * 1_000}
    if event == "SubagentStart":  # a spawn plans only managed core units
        pytest.skip("the canary unit is not a core unit, so a spawn never plans it")

    assert not _has_room(event, units)


@pytest.mark.parametrize("event", REGISTERED_EVENTS)
def test_every_slot_is_registered_once_in_order_and_nothing_runs_without_a_slot(event):
    hooks = _injector_hooks(event)

    assert _slots(event) == list(range(1, len(hooks) + 1))
    assert all(f" {inject_rules.SLOT_FLAG} " in hook["command"] for hook in hooks)


def test_the_session_start_slots_keep_the_injectors_place_and_timeout():
    group = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["SessionStart"][0]
    commands = [hook["command"] for hook in group["hooks"]]
    first = commands.index(f"{INJECTOR_COMMAND} {inject_rules.SLOT_FLAG} 1")
    slots = len(_slots("SessionStart"))

    assert commands[first - 1].endswith("/hooks/inject_decisions.py")
    assert commands[first + slots].endswith("/hooks/surface_praxion_feedback.py")
    assert all(
        hook["timeout"] == SESSION_START_TIMEOUT and hook["async"] is False
        for hook in _injector_hooks("SessionStart")
    )
